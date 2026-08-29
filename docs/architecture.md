# NeuroEvidence — architecture

Companion to `neuroevidence-working-spec.md`, which holds the reasoning behind every decision below. This file is the map: what runs where, what talks to what, and what state lives in the store. If the two ever disagree, the working spec is authoritative and this file is stale.

---

## 1. System overview

Two pipelines, one store, one API. Ingestion writes; the query path only reads.

```text
  EXTERNAL SOURCES (ingestion only)
  PubMed, PMC, Crossref, OpenAlex + Semantic Scholar (citation graph), NICE, MHRA/PARD scraper, openFDA (supplementary)
                          |
                          v
  PHASE A  (cheap, eager, no LLM calls)
  Corpus assembly -> Chunk by section -> OpenAI embed (text-embedding-3-large, 768d)
                          |
                          v          <---- paper is retrievable now
  PHASE B  (expensive, lazy, priority-queued worker pool -- plain Python, no Celery/Redis)
  1 Design classifier -> 2a-2e Auditors, one of five (1 call per field)
                       -> 3 Claim extractor -> 4 Snippet verifier
                          |
                          v
  ===================================================================
  SUPABASE POSTGRES  (the waist of the system)
   papers, study_facts | quality_checks, quality_fields
   constructs, measures, claims | chunks (vector 768, HNSW)
   external_records | sessions, turns
  ===================================================================
                          ^                       |
                    (writes only)           (reads only)
                          |                       v
  NICE, MHRA scraper ---> +          FASTAPI  ->  POST /sessions/{id}/turns
                                                        |
                                                        v
                                      QUERY PATH  (plain code, per turn)
                                      5 Scope guard -> 6 Translator
                                      -> hybrid retrieve + rerank
                                      -> deterministic SQL rank
                                      -> 7 Construct check -> 8 Writer
                                      -> 9 Citation checker
                                                        |
                              promotion (unchecked paper retrieved) --> Phase B queue
                              "No evidence" research_query --> offline gap-fill --> Phase A
```

No external source is contacted at query time — the two arrows leaving the query path above only ever feed the *offline* ingestion side; neither one runs inside a turn. No agent calls another agent. The only loop in either pipeline is the construct split (§7.4 of the working spec), triggered by a SQL fact, not a model's judgement. Full detail on both feedback arrows is in §2.

---

## 2. Ingestion pipeline

Two phases, split by cost, not by section number in the working spec (§5.8 has the full reasoning). Phase A is cheap and runs on the whole corpus, upfront and on an ongoing schedule. Phase B is expensive and runs lazily, prioritized by what real queries actually retrieve.

```text
  PHASE A — cheap, eager, no LLM calls, fed from three sources:
  (1) initial corpus-boundary query, (2) PubMed's ongoing index,
  (3) accumulated "No evidence" research_query gaps, batched offline
  ===================================================
  Corpus assembly (PubMed + PMC + Crossref + OpenAlex + Semantic Scholar)
                          |
                          v
              Chunk by section + OpenAI embed (768d)
                          |
                          v
                    chunks table  <---- paper is retrievable now

  PHASE B — expensive, lazy, priority-queued
  ===================================================
                     1 Design classifier
                              |
    +----------+----------+----------+----------+----------+
    | imaging  | trial    | qualit.  | psychom. | cohort   | (other_unclassified:
    v          v          v          v          v           no auditor, stays unchecked)
  2a Imaging 2b Trial  2c Qual.  2d Psych. 2e Cohort
  auditor    auditor   auditor   auditor   auditor
  (1/field)  (1/field) (1/field) (1/field) (1/field)
    |          |          |          |          |
    +----------+----------+----------+----------+
                              |
                              v
                quality_checks table
                (four-value enum; unchecked until Phase B runs)

                1 Design classifier
                          |
                          v
                3 Claim extractor
                          |
                          v
                4 Snippet verifier
          (different framing, not a repeat)
                          |
                   +------+------+
                   | agree| disagree
                   v             v
              claims table   unchecked +
                              human review queue

  PROMOTION: retrieval (section 3) surfacing an unchecked paper in a
  real query's top-K jumps that paper to the front of Phase B's queue.
  No promotion ever blocks the turn that triggered it — see section 3.

  GAP-DRIVEN GROWTH: a "No evidence" terminal state (section 3) logs
  its research_query. A once-a-day offline job batches these, runs the
  live source search, and feeds any papers found back into Phase A —
  never inside the turn that hit No evidence. See working spec §5.8.
```

**Concurrency:** a plain Python worker pool (`asyncio` or `multiprocessing`) claims rows from `quality_checks` where status is `unchecked`, using `SELECT ... FOR UPDATE SKIP LOCKED` on Supabase's standard pooled connection — as long as the claim and the status update happen in one atomic transaction, transaction-mode pooling handles this correctly, no separate direct connection needed (working spec §6.1). No Celery, no Redis, no message broker — the Postgres table already is the queue, so a separate broker would just be a second system tracking the same state (working spec §12). Resumption after a crash is "reprocess everything still `unchecked`"; no separate checkpoint store exists or is needed. The queue has two lanes: a background lane working steadily through the backlog, and a high-priority lane for papers a real query just surfaced (working spec §12). **Scheduling** (the daily gap-fill job, §5.8; periodic NICE/MHRA refresh, §10) runs on `pg_cron`, a Postgres extension enabled directly in Supabase — no separate scheduler needed either.

**Every call is temperature 0.** Determinism on re-ingestion is a design requirement, not an accident.

**Cost tracks demand, not corpus size.** 150,000 calls is the ceiling if every paper the corpus boundary admits gets fully audited — at GPT-4o pricing ($2.50/$10 per 1M tokens), roughly $2,200 naively, ~$1,450–1,500 with OpenAI's automatic prompt caching across the ~10 field calls that share one paper's full text, and roughly $700–750 on top of Batch API's 50% discount (Phase B is never latency-sensitive). The realistic ceiling is lower still: the free-tier corpus cap of ~2,000–2,600 papers (working spec §16 item 2) is about a quarter of the 10,000-paper figure above. With the two-phase split, even that ceiling is rarely reached: a paper nobody's query ever retrieves stays at `unchecked` forever and never costs an audit call. **Ranking must treat `unchecked` as `absent`, never as a pass** — otherwise an unaudited paper's zero-fields-checked count would rank it as if it had cleared every check (working spec §7.3).

### 2.1 External API calls (ingestion only — nothing here runs at query time)

| Source | Call | Returns | Cadence |
|---|---|---|---|
| PubMed E-utilities | `esearch` (5 clauses, capped ~500/condition — working spec §5.1.1) + `efetch` | Bibliographic metadata, abstract | Once per condition for `esearch`; once per paper for `efetch` |
| PMC | OA Web Service full-text fetch | Full text — open-access subset only | Once per paper; sets `has_fulltext`, gates the whole audit |
| Crossref | REST API, DOI lookup | Retraction status (Retraction Watch, integrated 2023) | One DOI lookup per paper |
| OpenAlex | Works API — `referenced_works` + `cited_by_api_url` | Metadata gaps, open-access status, and one of two independent citation graphs | Once per paper |
| Semantic Scholar | Graph API, `/paper/PMID:{id}/citations` | A second, independently-sourced citation graph, cross-referenced against OpenAlex's rather than replacing it | Once per paper |
| MHRA/PARD scraper | Direct `requests` + `BeautifulSoup` parser against PARD's search interface — no third-party API, fully free | Device register records — the primary non-literature source now that jurisdiction is UK (§10, §16 item 1) | Ingestion only, scheduled refresh — never at query time (§10) |
| NICE | Structured access | UK clinical guidance — primary guidance source for the non-literature lane | Ingestion only, scheduled refresh — never at query time (§10) |
| openFDA | `api.fda.gov`, Lucene query (510(k), PMA, recalls, MAUDE) | Supplementary international context only (device may also hold US clearance) — not the primary regulatory source in a UK-scoped build | Ingestion only, scheduled refresh — never at query time (§10) |

### 2.2 Ingestion agent calls

| Phase | # | Agent | Model tier | Temp | Call shape | Input | Output |
|---|---|---|---|---|---|---|---|
| A | — | Chunk embed | OpenAI `text-embedding-3-large`, dimensions=768 | n/a | 1 embedding call per chunk | Chunk text | `vector(768)` |
| B | 1 | Design classifier | GPT-4o | 0 | 1 LLM call per paper | Title, abstract, methods | Design type |
| B | 2a | Imaging auditor | GPT-4o | 0 | 1 LLM call per field per paper | Full text + one field | Four-value verdict + snippet |
| B | 2b | Trial auditor | GPT-4o | 0 | 1 LLM call per field per paper | Full text + one field | Four-value verdict + snippet |
| B | 2c | Qualitative auditor | GPT-4o | 0 | 1 LLM call per field per paper | Full text + one field | Four-value verdict + snippet |
| B | 2d | Psychometric validation auditor | GPT-4o | 0 | 1 LLM call per field per paper | Full text + one field | Four-value verdict + snippet |
| B | 2e | Observational cohort auditor | GPT-4o | 0 | 1 LLM call per field per paper | Full text + one field | Four-value verdict + snippet |
| B | 3 | Claim extractor | GPT-4o | 0 | 1 LLM call per paper | Results, discussion | Claims + instruments + quotes |
| B | 4 | Snippet verifier | GPT-4o | 0 | 1 LLM call per claim | Claim + a different text slice | Located sentence, or none |

Phase A has no volume cap — it runs on every paper the corpus boundary admits. Phase B's ~15 calls per paper only fire for papers a real query has actually retrieved (§5.8, §12 of the working spec); 150,000 (10,000 papers × 15) is a ceiling, not the expected bill.

**Every agent above runs one fixed, narrow system prompt — never a shared general-purpose one — and both the model and prompt version are recorded on every row written (`extracted_by` or equivalent).** A prompt tweak six months in shouldn't silently mix verdicts from the old wording and the new one in the same ranking; the version tells you exactly which rows are now stale and need re-running (working spec §11).

---

## 3. Query path

Runs per turn, short, deterministic. Six steps and one conditional branch (the construct split). No graph framework — this is plain code.

Retrieval here also drives Phase B promotion (§2): if a paper in the ranked results is still `unchecked`, it's bumped to the front of the ingestion queue — but this turn never waits for that audit to run. It answers with what's known now, `unchecked` sorted like `absent`.

```text
  raw_input arrives
        |
        v
  5 Scope guard (temp 0)
        |
        +-- diagnostic_ask --> REFUSED
        +-- distress --------> DISTRESS  (see section 9.2)
        +-- out_of_domain ---> OUT OF SCOPE
        +-- answerable ------+
                             v
        6 Translator (temp 0)
        privacy boundary: raw_input never leaves this step
                             |
                             v
        Hybrid retrieve (pgvector cosine + Postgres tsvector)
                             |
                             v
        Rerank -- GPT-4o, relevance ordering only, temp 0
        (never reorders by quality -- that stays in the SQL rank below)
                             |
                             v
        Deterministic SQL rank
        (has_meta, cohorts, sites, absent_ratio, n)
                             |
                             v
        7 Construct check -- diverges --> SPLIT (re-retrieve per branch)
                             |
                             ok
                             v
        Enough comparable evidence? -- no --> NO EVIDENCE
                             |
                            yes
                             v
        8 Writer (temp 0)
        ranked chunks only, defamation-safe phrasing
                             |
                             v
        9 Citation checker (temp 0)
                             |
                             v
                          ANSWERED
```

Publication year and journal are shown but never appear in the `order by`. Six values live in `turns.terminal_state`: `answered`, plus the five ways the system deliberately stops short — `refused`, `out_of_scope`, `no_evidence`, `split`, `distress`.

### 3.1 Query-path agent calls

**One external embedding API is now contacted in this path, as of the §5.7 embeddings decision:** OpenAI's embedding endpoint, to embed `research_query` for retrieval. Everything else still reads only from the store (§4). At most 6 LLM calls plus 1 embedding call fire per turn (5 LLM calls if the construct check doesn't trigger), which is why §11 of the working spec calls this volume negligible next to ingestion's 150,000 — the new external dependency changes reliability/latency exposure, not the cost picture.

| # | Agent | Model tier | Temp | Call shape | Input | Output |
|---|---|---|---|---|---|---|
| 5 | Scope guard | GPT-4o | 0 | 1 LLM call per turn, always | `raw_input` | Four-way classification |
| 6 | Translator | GPT-4o | 0 | 1 LLM call per turn, if `answerable` | `raw_input` | Research query + reflection sentence |
| — | Retrieve | OpenAI embed (`text-embedding-3-large`, 768d) | n/a | 1 embedding call | `research_query` | Candidate chunks (pgvector + tsvector union) |
| — | Rerank | GPT-4o, relevance ordering only (working spec §7.3) | 0 | 1 LLM call, not an agent — scores and orders, decides nothing | `research_query` + candidates | Reordered `chunk_id`s |
| 7 | Construct disambiguator | GPT-4o | 0 | 1 LLM call, only if the SQL join surfaces divergent `measure_id` | Claims + instruments | Comparable or not |
| 8 | Writer | GPT-4o | 0 (moved off 0.2 after real testing showed it re-inserting fabricated, uncited specifics on citation retries) | 1 LLM call per turn, if evidence sufficient | Ranked papers + chunks | Prose |
| 9 | Citation checker | GPT-4o | 0 | 1 LLM call per turn, if the writer ran | Draft + supplied chunks | Flags |

All model tiers are decided (GPT-4o, no tiering — working spec §11), and the reranker gap is closed the same way: GPT-4o, constrained by prompt to relevance ordering only, never quality — quality ordering stays entirely in the deterministic SQL rank that follows it.

Same prompt-versioning rule as §2.2 applies here too — every one of these agents (and the reranker, despite not being numbered among the 11) is a fixed, single-purpose prompt, and its version gets logged on the turn alongside the model that ran it.

---

## 4. Data store — Supabase Postgres

| Table | Holds | Notable design point |
|---|---|---|
| `papers` | Bibliographic metadata, abstract, generated `tsvector`, `has_fulltext` flag, `publication_status` | Gates whether an audit can run at all; `publication_status` (added post gold-answer, §13.1) distinguishes published from preprint — not yet wired into ranking |
| `study_facts` | Design type, sample sizes, site count, `cohort_name` | Normalizes shared-cohort papers so independent-cohort counting is `count(distinct cohort_name)` |
| `quality_checks` | One row per paper per field, four-value enum, evidence snippet, `extracted_by` | Rows created eagerly as `unchecked` — this doubles as the ingestion work queue |
| `quality_fields` | Check vocabulary as data, `applies_to` per design type, `rationale` | Adding a check needs no migration |
| `constructs` / `measures` | The construct-drift check, `measures.dsm_era` | Two claims about "executive function" with different `measure_id` are not a contradiction |
| `claims` | Findings linked to paper, construct, measure, verbatim quote | — |
| `chunks` | Text + `vector(768)`, HNSW indexed | OpenAI `text-embedding-3-large` at 768d (§5.7); text and vector do different jobs |
| `external_records` | NICE / MHRA-via-direct-scraper-sourced non-literature facts, openFDA as supplementary context | No foreign key into `claims` — the ranking SQL cannot reach it |
| `community_accounts` | Manually curated community-evidence axis (§9.1), linked to `constructs` | Same isolation as `external_records` — never joined into ranking SQL; re-checked, not re-sourced, when new claims land on its construct |
| `sessions` / `turns` | `raw_input` and `research_query` stored separately, RLS via `auth.uid()` | `raw_input` on a shorter, separately-configurable retention (§6) |

No confidence-score column exists anywhere. Enforced structurally, not by convention.

---

## 5. API surface

FastAPI; Swagger/OpenAPI docs at `/docs` generated from the same Pydantic models that validate traffic.

| Endpoint | Purpose |
|---|---|
| `POST /sessions` | Create a session (opt-in persistence only) — backed by Supabase Auth |
| `POST /sessions/{id}/turns` | Submit `raw_input`, run the query path, return the turn result |
| `GET /sessions/{id}/turns/{turn_id}` | Retrieve a stored turn |
| `GET /sessions/{id}` | List a session's turns (`raw_input` redacted past retention) |
| `DELETE /sessions/{id}` | User-initiated erasure |
| `GET /papers/{id}` | Drill-down: design type, `study_facts`, `quality_checks` with snippets |

Turn responses are a **discriminated union on `terminal_state`** — one Pydantic model per value — so an empty `answer` field can never render as if it were a real one. Ingestion is not exposed on this surface; the worker pool talks to the database directly.

### 5.1 Example: `POST /sessions/{id}/turns`

Request — only `raw_input` goes in; the client never sends `research_query`, that's derived server-side by the translator (§3.1):

```json
{
  "raw_input": "I'm 34, waiting years for an ADHD assessment. A private clinic wants £1,200 for a brain scan that 'objectively diagnoses' ADHD. Is that real?"
}
```

Response when `terminal_state` is `answered` — this shape does not exist on any other `terminal_state` value:

```json
{
  "turn_id": "a1b2c3",
  "terminal_state": "answered",
  "reflection": "You're asking whether a brain-scan-based ADHD test is diagnostically valid.",
  "answer": {
    "prose": "No neuroimaging or electrophysiological measure currently achieves reliable individual diagnosis of ADHD. A 510(k) clearance establishes substantial equivalence to a predicate device, not diagnostic validity...",
    "citations": [
      {
        "paper_id": "p_00931",
        "doi": "10.xxxx/xxxxx",
        "quote": "exact verbatim sentence from the chunk",
        "quality_summary": { "cohorts": 4, "max_sites": 1, "fields_absent_ratio": 0.36 }
      }
    ]
  }
}
```

Response when `terminal_state` is `distress` — a structurally different shape, per §9.2; there is no `answer` field to leave empty:

```json
{
  "turn_id": "a1b2c4",
  "terminal_state": "distress",
  "resources": [
    { "region": "UK", "name": "Samaritans", "contact": "116 123" }
  ],
  "followup_prompt": "Would you also like the research question in your message answered?"
}
```

A client that only checks `if response.answer` is safe against every non-`answered` state by construction — there is no `answer` key to find.

---

## 6. What's deliberately absent

No multi-query expansion. No autonomous retrieval loops — the only loop is a SQL-triggered branch. No probabilities. No automated confidence grades. No profile-building — `raw_input` is stored for translation-audit purposes only, never as an inference about the person. Each of these is a rejected design, not an oversight; see the working spec's appendix for why.
