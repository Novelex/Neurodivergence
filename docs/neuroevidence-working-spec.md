# NeuroEvidence — working specification

A retrieval-augmented question answering system over the neurodevelopmental research literature.

Version 0.1 — design document, pre-implementation.

---

## 1. Purpose

NeuroEvidence answers questions about what research establishes concerning autism, ADHD, dyslexia, dyspraxia, Tourette's and related conditions. It is aimed at neurodivergent adults, parents, and the people supporting them.

It answers questions about the literature. It does not assess the person asking.

That distinction is the product, not a legal hedge. Every general-purpose model will answer "can a brain scan diagnose ADHD?" with something balanced-sounding and subtly wrong, because it draws on a literature where the confident single-site findings vastly outnumber the multi-site failures that overturned them. NeuroEvidence answers correctly because it encodes domain knowledge about what makes a claim in this field credible — knowledge that has never been written into a ranking function.

### 1.1 The user it is built for

The canonical user is someone with a real decision to make and no way to evaluate the answer they're given. A worked example, used throughout this document as the reference case:

> A 34-year-old, self-identified as possibly ADHD, waiting on an assessment with a multi-year queue. She has found a private clinic offering a brain scan that claims to diagnose ADHD objectively, for £1,200. She wants to know whether it is real before she pays.

A generic chatbot gives her a balanced paragraph and she books the scan. The system described here tells her that no neuroimaging or electrophysiological measure currently achieves reliable individual diagnosis, shows her the regulatory record, and explains why the published accuracy figures collapse when tested across sites.

That answer is falsifiable, contradicts what she would otherwise be told, saves her £1,200, and requires no probabilities, no agent swarm, and roughly a dozen sources.

---

## 2. Constraints

These are design constraints, not preferences. Each has a specific reason and none of them relax with more time or budget.

### 2.1 No diagnostic output

The system never tells anyone what they are. It does not estimate likelihood of a condition, interpret personal history against diagnostic criteria, or produce anything that reads as an assessment.

Two reasons. First, software intended to provide information used for diagnosis or prediction can meet the definition of a medical device in most jurisdictions; a personalised report about someone's cognitive profile sits close to that line and the answer changes the architecture, so it must be settled before the build rather than after. Second, it is the honest scope. The system has no access to the person beyond what they typed.

### 2.2 No automated confidence grades

Risk-of-bias assessment is the most fragile task LLMs perform on literature. Published evaluations put accuracy in the range 0.44 to 0.90 with a median around 0.62, and inter-rater kappa against human experts around 0.51. Data extraction, by contrast, sits near 0.95.

A confidence label derived from a 0.62-accurate process is precise and wrong, and the precision is what makes it dangerous. A hedged sentence invites a question; a label closes one.

### 2.3 No probabilities

A probability must be a probability *of* something checkable. Probability the finding replicates would require replication outcomes to calibrate against, and in this literature they largely do not exist. Without a calibration target, a number is a model's impression wearing a lab coat.

What the system may output instead are counts, which are facts about the corpus rather than judgements: number of independent cohorts, number of studies, largest sample, whether a meta-analysis exists, how many applicable quality fields were reported.

### 2.4 No profile building

Elicitation is limited to what changes retrieval — typically what the question actually is, which literature it maps to, and what the person has already ruled out. Three or four turns, each with a stated reason.

The system may store questions and answers. It may not store inferences about the person. "Asked about post-social fatigue on 3 March" is a log. "Autistic, sensory-sensitive, executive dysfunction" is a clinical inference made by a system not permitted to make clinical inferences.

### 2.5 No multi-query expansion, no autonomous retrieval loops

Controlled benchmarking of biomedical RAG found multi-query expansion produced the weakest contextual precision at 0.671, against 0.827 for a single cross-encoder reranking pass. More retrieval iterations made results worse by pulling in material that looked relevant and was not.

A loop whose stopping condition is a model judging its own sufficiency will terminate as soon as it has a coherent story. In this literature the coherent story is usually the one the tool exists to contradict.

**Rule: loop on facts, not on judgement.** Retry when a fact triggers it (schema validation failed, quoted snippet absent from source, two extraction passes disagree). Never when a model reports feeling underinformed.

---

## 3. Why the naive design fails

Three inversions are built into any obvious implementation. Avoiding them is most of the engineering value.

### 3.1 Recency is anti-correlated with reliability

Established findings stop generating papers once settled. Tentative findings keep producing them. Sorting by date therefore surfaces the preliminary above the confirmed.

In neuroimaging this is severe. Brain-wide association studies need sample sizes in the thousands for reproducible brain-behaviour correlations; the field's median has been in the tens. A large multi-site consortium study from 2011 is frequently stronger evidence than a single-site 2025 study with n=24, and a recency sort puts the 2025 paper first.

Date is retained in the model but never used as a sort key. It functions instead as a modifier on replication status:

| Age | Replicated? | Reading |
|---|---|---|
| Old | No | People tried and it did not hold. Treat with suspicion. |
| Old | Yes | Established. |
| Recent | No | Too early to say. Treat as open. |
| Recent | Yes | Strong and current. |

Identical evidential status in rows 1 and 3, opposite meanings.

### 3.2 Journal rank inverts too

High-impact venues select for novel, surprising, single-site results. The multi-site replication attempt that fails to reproduce them lands in a specialist journal with a lower quartile. Citation thresholds compound this, because the exciting original accumulates citations for years before the null replication appears.

Competing tools offer Q1–Q4 quartile filtering as a quality proxy. In this literature that filter actively promotes the paper that is wrong.

### 3.3 Most apparent contradictions are definitional

DSM-5 folded Asperger's into autism spectrum disorder in 2013, so prevalence and characteristic findings before and after are not measuring the same population. ADHD criteria shifted. Instruments changed. Different laboratories operationalise "executive function" in ways that barely overlap.

A naive contradiction detector reads all of this as scientists disagreeing about reality. They are not; they are measuring different things under one word. Presenting construct drift to a user as "the research conflicts" is active misinformation delivered in the confident register that is hardest to question.

---

## 4. System overview

Two paths, deliberately separated.

**Ingestion runs offline, once per paper.** Corpus assembly, design classification, quality auditing, claim extraction, verification, chunking and embedding. This is where the expensive, variable, judgement-heavy work happens, ahead of any user.

**The query path runs per turn and is short.** Scope check, translation, hybrid retrieval, reranking, deterministic ranking, prose generation, citation verification.

The store sits between them as the waist of the system. Everything above writes to it; everything below reads only from it. No external source is contacted at query time.

This is the determinism guarantee. The same question produces the same corpus, the same ordering and substantively the same answer on any run. That property is not aesthetic — it is what makes the system testable against a hand-labelled gold answer, demonstrable to a sceptical researcher, and defensible when someone disputes a ranking.

---

## 5. Ingestion

### 5.1 Corpus assembly

**PubMed E-utilities** is the primary source. Neurodevelopmental EEG and fMRI work is journal-published and PubMed-indexed. arXiv is not a primary source for this field; it would mostly return machine-learning classification preprints, which are relevant to the biomarker question specifically but constitute a separate, unreviewed literature requiring its own flag. If preprints are wanted, bioRxiv, medRxiv and PsyArXiv are the correct servers.

**PMC** supplies open-access full text. This matters more than it appears. The quality fields that determine whether a finding is credible live in methods sections; abstracts almost never contain them. Papers without full text cannot be properly audited and their quality checks must be recorded as `unchecked`, never `absent`. Claiming a paper omitted something on the basis of its abstract alone would be a serious error in a system whose selling point is honest reporting of absence.

**PMC's "open access" label is not one license.** The OA subset mixes CC-BY, CC-BY-NC, and CC-BY-NC-ND papers, and a commercial build cannot legally ingest and serve CC-BY-NC or CC-BY-NC-ND full text without a separate license. Record each paper's license on fetch (`papers.license`, §6) and filter or flag at assembly time — not as a downstream cleanup step once a few thousand papers are already stored under the wrong assumption.

**Crossref** supplies retraction status. The Retraction Watch database was acquired by Crossref in 2023, made openly available, and integrated into the main REST API. One DOI lookup per paper. Cheap, mechanical, and catastrophic to omit in a tool built on evidential care.

**OpenAlex** fills metadata gaps, particularly open-access status, and supplies a citation graph: `referenced_works` on a work object gives outgoing citations; `cited_by_api_url` gives the incoming ones — papers citing a finding, which is where replication attempts live and a direct ranking input unavailable from PubMed. OpenAlex requires a free API key for all requests (a recent policy change, corrected from an earlier draft of this section that said otherwise) — free, no approval, $1/day usage credit, comfortably enough for this project's volume.

**Semantic Scholar** supplies a second, independently-sourced citation graph, used alongside OpenAlex's rather than instead of it. Its API application was initially rejected, which is why OpenAlex took over this role first; a key was obtained afterward, and there's a real reason to run both rather than drop back to one: OpenAlex and Semantic Scholar build their citation graphs from different underlying data, so cross-referencing the two catches gaps either provider misses on its own — a paper's replication record is exactly the kind of thing you don't want silently incomplete because one source missed a citing paper the other has.

### 5.1.1 The `esearch` query — decided (§16 item 2)

One query, five bracketed clauses, one per condition — kept in a single query for maintainability, but capped per condition, not on the combined pool, for the reason below.

```
(
  "Autism Spectrum Disorder"[MeSH] OR "Autistic Disorder"[MeSH] OR "Asperger Syndrome"[MeSH]
  OR autism[tiab] OR autistic[tiab] OR asperger*[tiab]
)
OR
(
  "Attention Deficit Disorder with Hyperactivity"[MeSH]
  OR ADHD[tiab] OR "attention deficit"[tiab]
)
OR
(
  "Dyslexia"[MeSH] OR dyslexia[tiab] OR dyslexic[tiab]
)
OR
(
  "Motor Skills Disorders"[MeSH]
  OR dyspraxia[tiab] OR "developmental coordination disorder"[tiab] OR "clumsy child"[tiab]
)
OR
(
  "Tourette Syndrome"[MeSH] OR tourette*[tiab] OR "tic disorder"[tiab]
)

AND hasabstract[text] AND english[lang]
NOT ("case reports"[pt] OR comment[pt] OR letter[pt] OR editorial[pt])
```

**Dyspraxia has no clean MeSH mapping** — PubMed indexes it under `"Motor Skills Disorders"[MeSH]`, and its own terminology drifted from "clumsy child syndrome" to "dyspraxia" to "developmental coordination disorder" over time. This is the same construct-drift pattern §3.3 already warns about; the text-word clause carries all three eras so the query doesn't silently favour whichever term happened to be current when a given paper was indexed.

**Excluded by publication type, not by date.** Case reports, comments, letters, and editorials are excluded because they're low-value formats, not because they're old — §3.1 already established that filtering by recency instead of format would exclude exactly the older, multi-site, "established" papers the ranking SQL is built to favour.

**Capped per condition: ~500 papers each, ~2,500 total, not one relevance-sorted pool of 2,500.** Autism and ADHD each have literatures an order of magnitude larger than dyspraxia and Tourette's. Running this as one combined query, sorting by relevance, and taking the top ~2,500 overall would let autism and ADHD crowd out the smaller-literature conditions almost entirely — a corpus that's overwhelmingly autism/ADHD with barely any dyspraxia coverage, contradicting §1's equal-standing scope across all five conditions. Run each bracketed clause as its own `esearch` (same base filters), cap each at `retmax≈500`, and union the five PMID sets into one corpus.

### 5.2 Design classification and routing

Because the scope covers all of neurodivergence, the corpus contains heterogeneous study types: neuroimaging case-control designs, intervention trials, qualitative interview studies, psychometric validations, cohort studies.

The quality fields that matter are not shared across these. An EEG study needs multiple-comparisons correction and motion parameters checked. A trial needs randomisation and blinding. A qualitative study needs neither — it needs sampling strategy and reflexivity. Running one checklist across all designs returns "not applicable" for most fields on most papers and tells the reader nothing.

A **design classifier** therefore runs first and routes each paper to exactly one specialist auditor. Specialists do not all run and vote; the classifier picks.

### 5.3 The auditors

Each auditor runs one call per quality field, not one call per paper. Twelve small calls beat one large one: "did this paper report correction for multiple comparisons — yes, no, or not applicable" is a question a model answers well, whereas "assess this paper's methodological quality" is not. This costs more and works better, and since this agent is the product, the cost is justified.

**Imaging auditor** — multiple comparisons correction, motion correction reported, preprocessing pipeline specified, sample size relative to claimed effect, site count, scanner or system harmonisation, medication status controlled, IQ-matched controls, comorbidity exclusion reported, preregistration, independent replication, external validation, data availability.

**Comorbidity exclusion reported** was added after the gold-answer exercise (`docs/gold-answer.md`, §13.1) — a real case where studies routinely excluded the comorbid conditions present in 60–80% of real-world ADHD cases, which meant even the "positive" original findings were measured on a narrower, cleaner population than any real patient sample. This mattered more to that answer than several fields already on this list, which is exactly the kind of discovery §13.1 says the gold-answer exercise should produce.

**Trial auditor** — randomisation method, allocation concealment, blinding of participants and assessors, attrition and handling, intention-to-treat analysis, primary outcome prespecified, trial registration, power analysis, effect size with confidence interval.

**Qualitative auditor** — sampling strategy and rationale, participant characteristics reported, data saturation addressed, analytic method specified, researcher reflexivity, member checking, whether autistic or otherwise neurodivergent people were involved in design.

That last item is included deliberately. In a field where much of the formal literature was produced without asking the population it describes, community involvement is a methodological quality, not a political gesture.

**Psychometric validation auditor** — sample size relative to number of items/factors, internal consistency reported (Cronbach's alpha or equivalent), test-retest reliability reported, construct validity assessed (convergent/discriminant), criterion validity assessed against a reference measure, factor structure reported (exploratory or confirmatory), normative/reference sample described, cross-population or cross-cultural validation addressed, item development process described.

This auditor exists because §7.4's construct-drift check depends on knowing which instruments are actually sound. A claim measured on a validated instrument and a claim measured on one nobody ever checked are not equally trustworthy, even when both papers report a "significant" result — and without this auditor, that difference was invisible to the rest of the system.

**Observational cohort auditor** — baseline confounders measured and adjusted for, attrition/loss-to-follow-up reported, follow-up duration adequate for the outcome studied, exposure and outcome measured with a validated method (not unvalidated self-report alone), temporality established (exposure precedes outcome), comparison/reference group appropriateness, selection bias addressed (how the cohort was recruited), preregistration, data availability.

A cohort study is not a trial with the randomisation fields removed — attrition and confounding matter differently when nothing was ever randomised, which is why this is its own auditor rather than a trimmed-down version of the trial auditor's checklist.

**All five design types named in §5.2 now route to a built specialist auditor.** The design classifier's output space and this section's auditor list must stay in sync — adding a sixth design type to §5.2 without a matching auditor here reopens the same gap this pair of auditors was written to close.

### 5.4 Absence semantics

The central design decision. Every competitor stores what a paper says; this system stores what it does not.

Four values, and the distinctions between them carry all the meaning:

- `reported` — the extractor found it, and holds the justifying snippet
- `absent` — the extractor looked at full text and it is not there
- `not_applicable` — the field does not apply to this design
- `unchecked` — nobody has looked, or full text was unavailable

Collapsing `absent` and `unchecked` into a null destroys the signal. "This paper failed to correct for multiple comparisons" and "we have not processed this paper" are entirely different claims.

Absence is informative in this literature specifically because the fields that most determine credibility are the ones least often reported. Meta-epidemiological review of observational studies found statistical correction for multiple outcome analyses satisfied in around a third of studies, residual bias analyses in roughly a seventh, and falsification tests for residual confounding in under a twelfth — with no improvement over time.

An extraction pipeline cannot extract what is not there. It can record, precisely, that it looked.

### 5.5 Claim extraction

Runs on every paper regardless of design type. Extracts findings with their construct, their measuring instrument, direction, effect size where stated, and a verbatim quote with location.

The instrument matters more than the finding. It is what makes the construct check possible downstream, and it is the field that distinguishes definitional drift from real disagreement.

### 5.6 Verification

Repetition does not fix semantic errors. If the model misread a methods section, asking the same question again produces the same misreading — the error is in how the text was parsed, and that is stable across samples.

What breaks a trap is reframing. The forward call asks: *does this paper report correction for multiple comparisons?* The verification call asks something structurally different: *here is a claim that this paper corrected for multiple comparisons — locate the sentence supporting it, or state that no such sentence exists.*

That second framing is a search task rather than a judgement task, and it fails informatively. If no sentence can be produced, the original verdict was wrong.

This yields a mechanical disagreement trigger. Two differently-framed calls reaching different conclusions is detectable in code without asking any model's opinion. Disagreements route to `unchecked` and to a human review queue.

Other mechanical checks in the same family:

- Quoted snippet must appear in source text (string match catches hallucination)
- `n_total` should equal `n_clinical + n_control`; mismatch means one of three is wrong
- A `reported` verdict with an empty evidence field is a broken contract

Retries cap at two or three. A field resisting extraction after three attempts is telling you something — usually that the information genuinely is not there, or the PDF parsed badly. Recording that honestly beats a fourth attempt that finally produces something.

There is reasonable evidence that models cannot reliably correct their own reasoning without external feedback, and that intrinsic self-correction often degrades output. The external signal here is always the source text. Every verification pass anchors to a snippet the model must locate, never to its own recollection of what it decided.

### 5.7 Chunking and embedding

Full text is chunked with section labels retained, since a claim from Results carries different weight than one from Discussion and you will want to filter on it.

**Decided: OpenAI `text-embedding-3-large`, requested at 768 dimensions** via the API's `dimensions` parameter, so the existing `vector(768)` column in §6 needs no migration. $0.13 per 1M tokens — for the whole corpus (~150,000 chunks), a few dollars, one-time; cost was never the deciding factor here.

This is a deliberate departure from the MedCPT-based design this section originally specified, and the trade is worth stating plainly rather than burying. MedCPT (NCBI, 330M params, domain-trained) was chosen because it set state-of-the-art biomedical document retrieval on BEIR, outperforming general-purpose models many times its size, including OpenAI's own `cpt-text-XL` at 175B. Moving to a general-purpose OpenAI embedding gives that documented domain-retrieval advantage back — this may still retrieve well, but it is not a neutral swap, and it is worth re-checking retrieval quality against the gold-answer set (§13.1) once real embeddings are in place, not assuming parity.

**The privacy property this section also gave up:** MedCPT ran locally, so no query ever left the machine. With OpenAI embeddings, every `research_query` (already de-identified by the translator, §7.2, but still a health topic) goes to a third party at query time, and the query path now has an external dependency it didn't have before — if OpenAI's embedding endpoint is slow or down, retrieval is too. This doesn't violate §4's "no external source is contacted at query time" in the sense that clause was written for (external *corpus* sources like PubMed), but it does introduce the same category of new failure mode into what was previously an all-local step.

**Open item this creates, not yet resolved:** MedCPT "ships a matched retriever and reranker pair" — the cross-encoder rerank step in §7.3 was built on that pairing. OpenAI has no equivalent reranking endpoint. Until this is resolved, §7.3's rerank step has no implementation — options are dropping the separate rerank step and ranking on embedding similarity alone, using a third-party reranker (e.g., Cohere Rerank), or running an open cross-encoder locally. This needs a decision before §7.3 can be built as written.

**Embeddings and text are both stored, doing different jobs.** The vector is a lookup key that answers "which passages are semantically near this query." It is not a representation of content and is not reversible. Everything downstream — the writer, the citation, the drill-down — reads the text.

### 5.8 Two-phase ingestion: embed eagerly, audit lazily

Corpus assembly (§5.1) and chunking/embedding (§5.7) are cheap — no LLM call, just an OpenAI embedding call per chunk. Design classification, auditing, and claim extraction (§5.2–5.6) are the expensive part — the ~10-15 calls per paper that dominate ingestion cost. Nothing requires these to run together, and running them together means paying full audit cost for every paper the corpus boundary admits, whether or not anyone ever asks about it.

**Phase A runs eagerly on the whole corpus:** fetch metadata and full text, generate the embedding, write the row. A paper is retrievable the moment Phase A finishes it. This is also the natural home for corpus growth over time — as PubMed indexes new papers matching the corpus boundary (§16 item 2), Phase A picks them up on an ongoing schedule rather than in one upfront batch.

**Phase B runs lazily, prioritized by demand, through the same worker pool described in §12.** A paper's `quality_checks` rows sit at `unchecked` until something promotes it. Promotion happens the first time the paper actually surfaces in a real user's top-K retrieval — it jumps to the front of the queue. A paper the corpus boundary admits but no query ever retrieves can sit at `unchecked` indefinitely, and that is not a gap to fill; it is cost the system correctly never spends.

**This only works with one guardrail on ranking (§7.3): `unchecked` sorts like `absent`, never like a pass.** If an unaudited paper's `fields_absent_ratio` reads as zero simply because nothing has been checked yet, it would rank as if it cleared every quality field — exactly the plausible-guess failure the four-value enum (§5.4) exists to prevent. So the *ranking* SQL treats `unchecked` conservatively; the *display* and audit logging keep it distinct from `absent`, per §5.4, because a user asking "why is this ranked low" deserves the honest answer ("not yet checked," not "failed a check").

**The current turn never blocks on Phase B.** Promotion enqueues the paper for the worker pool; it does not trigger a synchronous audit inside the query path. The turn answers with what is actually known now, honestly ranked, at the query path's normal latency — the same reasoning that ruled out real-time extraction in general (§4) applies here at the level of one paper.

**Phase A itself has a third feed, beyond the initial corpus-boundary query: gap-driven growth from `No evidence` turns.** The obvious next question — why fetch the corpus boundary at all upfront instead of pulling papers only when someone asks about them — runs into the same problem real-time extraction does: a live PubMed/PMC call from inside the query path breaks §4's "no external source contacted at query time," adds unbounded network latency to what is supposed to be a short turn, and would require answering from a paper with no audit yet.

The fix keeps the fetch, drops the "inside the query path" part. Every `No evidence` terminal state (§8) already records the `research_query` that the corpus couldn't answer — that is a real, demand-weighted signal of a coverage gap. A scheduled background job (same worker pool, §12), running **once a day**, batches accumulated `research_query` gaps, runs the live source search offline, and feeds anything it finds into Phase A exactly like the initial corpus assembly did. Daily is deliberately modest rather than near-real-time — at the traffic a free-tier build actually sees, an hourly job would mostly find nothing new to do; revisit the cadence only once real `No evidence` volume shows daily isn't keeping up. The person who hit `No evidence` still gets an honest "the literature is silent" answer, at normal latency, that day. The paper — audited by the time the next similar question arrives, via the same demand-priority queue as everything else in this section — is what "becomes part of memory for later use." The corpus grows from what people actually ask, without ever putting a live external call, or an unaudited paper, in front of a waiting user.

---

## 6. Data model

Full DDL is maintained separately. The structural decisions that matter:

**`papers`** — bibliographic metadata, abstract, a generated `tsvector` for keyword search (Postgres does this natively, so no separate BM25 service), a `has_fulltext` flag that gates the entire audit, and a `license` field (§5.1) recording the specific PMC OA license (CC-BY, CC-BY-NC, CC-BY-NC-ND, or none) — gates whether full text can legally be stored and served at all, checked before `has_fulltext` is trusted, not after.

**`papers.publication_status`** — `published`, `preprint`, or `in_press`. Added after the gold-answer exercise (`docs/gold-answer.md`, §13.1), which needed to distinguish a published, peer-reviewed source from a not-yet-reviewed preprint and found the schema had no way to represent that. This is a different axis from §5.4's absence semantics — those describe what a paper reports; this describes whether the paper itself has cleared peer review at all, checked once at ingestion, not per quality field. Defaults to `published`, matching the current PubMed-only corpus boundary (§5.1.1), which does not ingest preprint servers — this field matters more once, or if, that boundary ever expands to bioRxiv/medRxiv/PsyArXiv. **Not yet wired into ranking** (§7.3): whether a `preprint` should sort below an otherwise-equivalent `published` paper is a real open question this field makes askable, not one this document answers yet.

**`study_facts`** — one row per paper. Design type, sample sizes, site count, modality, population, age range, sex distribution, preregistration, data availability. Critically includes `cohort_name`: ABIDE, ADHD-200 and the large consortia are reused constantly, so twelve papers can appear to be twelve independent findings while sharing one sample. Normalising this makes independent-cohort counting a `count(distinct cohort_name)` rather than a guess.

**`quality_checks`** — one row per paper per field, carrying the four-value enum, the evidence snippet, a location reference, and the model and prompt version that produced it. Rows are created eagerly at ingestion with `unchecked`, so coverage queries are trivial and you always know what you have not yet examined.

**`quality_fields`** — the check vocabulary as data, not an enum, with an `applies_to` array keyed to design types. Adding a check requires no migration. Each field carries a `rationale` sentence explaining why it matters, written once and reused as UI copy.

**`constructs`** and **`measures`** — the construct check lives here. Two claims about "executive function" pointing at different `measure_id` rows are not in conflict; they measure different things. `measures.dsm_era` catches the 2013 boundary.

**`claims`** — findings linked to paper, construct, measure, with verbatim quote and location.

**`chunks`** — text plus a `vector(768)` column, HNSW indexed once past a few thousand rows.

**`external_records`** — the non-literature lane, deliberately isolated. No foreign key into claims, no design fields, nothing the ranking SQL can reach. An FDA clearance record and a case-control study are different kinds of object and the schema should refuse to average them.

**`community_accounts`** — the community-evidence axis (§9.1, §16 item 3). Linked to `constructs` by `construct_id`, which is what lets a query join formal claims and community accounts on the same shared vocabulary — but never joined into the ranking SQL itself, the same isolation principle as `external_records`. Manually populated, never agent-extracted. A `reviewed_at` timestamp, not just `created_at`, since entries are re-checked (not re-sourced) whenever new formal claims land against their construct.

**`sessions`** and **`turns`** — hold `raw_input` and `research_query` separately, which lets you audit that the translation invariant held. Row-level security enabled before the first user touches the system, not retrofitted. Short default retention with a scheduled purge.

`raw_input` is not a profile — §2.4 rules those out — but it is someone's own words about their own mind or body, stored verbatim, and that is a data-minimization question in its own right, independent of whatever is or isn't inferred from it. It should carry a shorter, separately-configurable retention than `research_query` and the rest of the turn: it exists to let you audit that translation is working, not to be a durable record of what someone disclosed. Once the translator's reliability is established, consider purging `raw_input` on a much tighter schedule than the row it lives in, or not persisting it past that validation window at all.

No confidence score column exists anywhere in the schema. This is enforced structurally rather than by convention.

### 6.1 Hosting: Supabase

Supabase is the concrete Postgres. It changes nothing above — pgvector, generated `tsvector`, and row-level security are all native Postgres features Supabase runs unmodified — but it does settle two things this section left implicit and adds one operational constraint the worker pool in §12.1 needs to respect.

**RLS ties directly to Supabase Auth.** "Row-level security enabled before the first user touches the system" (§6) becomes concrete: policies key off `auth.uid()`, and `POST /sessions` (§12.1) can be Supabase Auth issuing a session rather than a hand-rolled token scheme. One less thing for the API layer to build.

**Connection pooling and the claim-locking pattern — corrected.** An earlier version of this section overstated the risk here. Supabase's default pooled connection (pgbouncer/Supavisor, transaction mode) assigns one backend connection per transaction, from `BEGIN` to `COMMIT`/`ROLLBACK` — so `SELECT ... FOR UPDATE SKIP LOCKED` followed by the status update, wrapped in one transaction, stays on a single connection for its whole duration and works correctly on the standard pooled connection. No separate direct connection string is needed for this. Transaction-mode pooling only breaks *session-scoped* things that are expected to persist across separate transactions — advisory locks held outside a transaction, prepared statements reused later, `SET` commands meant to stick around — none of which this claim-and-process pattern does, as long as the claim and the status update happen inside one atomic transaction rather than as two separate round-trips.

---

## 7. Query path

### 7.1 Scope guard

Classifies raw input into `answerable`, `diagnostic_ask`, `distress`, or `out_of_domain`. Small fast model. **Fails closed** — ambiguous routes to refuse, not to answer.

Each classification maps to exactly one outcome. `answerable` continues into translation (§7.2). `diagnostic_ask` and `distress` end the turn immediately, at the `Refused` and `Distress` terminal states respectively (§8). `out_of_domain` ends it at `Out of scope` (§8) — the plainest of the terminal states, since nothing personal was disclosed and there is nothing to handle carefully, only a scope statement to give.

The distress classification matters independently. Someone arriving at a tool named after their identity may be in a bad place, and a fluent on-topic response about research findings is the wrong reply to that.

### 7.2 Translation, and the privacy boundary

Converts a personal statement into a research query, and produces the reflection sentence shown back to the user.

This step is also the privacy boundary and must be enforced in code rather than by prompt convention. Nothing downstream — no retrieval call, no external API, no log — ever sees `raw_input`. What leaves the process is "post-social fatigue autistic adults," never "I fall apart after parties and I think something's wrong with me."

### 7.3 Retrieval and ranking

**Retrieve** — hybrid. pgvector cosine similarity plus Postgres full-text over the generated tsvector, union'd into a candidate set. One pass, no query expansion.

**Rerank — decided: GPT-4o, prompted for relevance ordering only, temperature 0.** OpenAI has no dedicated reranking endpoint (unlike MedCPT's matched cross-encoder, or a purpose-built third-party reranker), so this repurposes the chat model already used everywhere else in the system, at the cost of one more LLM call per turn instead of a lightweight scoring pass.

The one guardrail that matters: **this call judges topical relevance only, never evidence quality.** It is told explicitly not to reorder by sample size, methodology, or how trustworthy a finding seems — that judgement stays entirely in the deterministic SQL rank below, which is the whole point of keeping ranking out of model hands (§7.3's own reasoning, and §12's "no agent decides what runs next"). A highly relevant passage from a weak study still ranks above an irrelevant passage from a strong one at this step; the SQL rank sorts by quality afterward, among passages already confirmed relevant. Without this guardrail stated in the prompt, a general chat model doing reranking is exactly the kind of judgement creep the rest of this document works to keep out of the query path — it must reorder for relevance and stop there.

Input: the research query and the candidate set from the retrieve step above, each candidate carrying its `chunk_id`. Output: the same set of `chunk_id`s, reordered most-to-least relevant, none added, none dropped. This is a model call but not an agent in §11's sense — it scores and orders, it does not decide what runs next.

**Rank** — deterministic SQL over structured metadata. No model call.

```sql
order by has_meta desc,
         cohorts desc,
         max_sites desc,
         fields_absent_ratio asc,
         largest_n desc
```

Publication year and journal name are available for display. Neither appears in the `order by`.

Because scope spans multiple design types, `fields_absent` cannot be compared as a raw count across designs — a paper missing three of five applicable checks is not worse than one missing four of twelve. Store and rank on the ratio, or rank within design type.

**`fields_absent_ratio` counts `unchecked` as `absent` for this calculation, never as a pass.** This matters once ingestion is two-phased (§5.8): a paper still waiting on Phase B has every field at `unchecked`, and if the ranking arithmetic read that as zero fields absent, it would rank the least-examined paper in the corpus as if it were the most rigorously reported one. The four-value distinction (§5.4) stays intact everywhere it was built for — display, audit logging, the evidence a user can drill into — this rule only narrows what the sort comparator is allowed to assume.

The ranking is deterministic, unit-testable, and explainable line by line. When someone asks why a 2019 paper outranked a 2025 one, you show them the clause.

### 7.4 Construct disambiguation

Fires only when the SQL join surfaces divergent `measure_id` values across retrieved claims. Determines whether two claim sets are measuring comparable things.

If they are not, this is not a contradiction to report. It is one question that was actually two, and the run splits and re-retrieves per branch. This is the only loop in the query path, and its trigger is a database fact, not a model's judgement. It terminates because the branches are enumerable.

### 7.5 Writing

Produces prose from retrieved chunks only. Receives the papers already ordered and is told explicitly that ranking is not its concern. Every claim must trace to a supplied chunk.

When a supplied chunk concerns a named commercial product or provider — the reference case's £1,200 scan being the paradigm instance — the writer states the regulatory record and evidence status as fact ("a 510(k) establishes substantial equivalence to a predicate device, not diagnostic validity; no accuracy data was submitted") and never a conclusion about the named party's intent ("this is a scam"). The first is sourced, defensible reporting that does the job the reference case needs done. The second is a liability exposure the system doesn't need to take on to do that job — the regulatory record makes the point on its own.

### 7.6 Citation checking

Runs after the writer, before display. Confirms every claim in the draft traces to a chunk that was actually supplied. Flags anything that does not.

This is the step most systems omit, and it is cheap — small model, narrow task. It catches the failures that would otherwise reach a user carrying the interface's authority.

**Two layers, not one model call.** A mechanical check runs first, in plain code, no model involved — the same string-match discipline §5.6 already uses on the ingestion side ("quoted snippet must appear in source text"). For every citation the writer's structured output claims: is the cited `paper_id` actually among the chunks supplied for this turn, and does the cited quote appear verbatim in that paper's supplied text? Both are yes/no facts, not judgement calls, and they catch the cleanest, most damaging failures — citing a paper never in the ranked results, or fabricating a quote — for free and instantly.

Only what survives that layer goes to the LLM-based citation checker, and its job narrows accordingly: not "does this quote exist" (already answered) but "does the surrounding prose fairly represent what a real, correctly-cited quote actually says." That is a semantic-fidelity judgement a string match cannot make, and it is the only thing left for a model to do here.

**Remediation:** a flagged claim triggers one retry — the writer is told which specific claim was unsupported and regenerates using only the supplied chunks. If the retry still has a flagged claim, the turn ends at `no_evidence` rather than shipping a partially-stripped or uncertain answer. The retry is capped at one attempt on purpose — an uncapped retry loop here is the same "loop until it looks right" pattern §2.5 already rules out elsewhere, just relocated to the end of the query path instead of the beginning.

---

## 8. Terminal states

Six values live in `turns.terminal_state`. One, `answered`, is the ordinary case: the writer produced prose, the citation checker passed it, the turn ends normally. It needs no further definition — it is what happens when none of the other five fire.

The other five are ways a session ends *without* producing an answer, and all five are features, as deliberate as the answer itself.

**Refused** — the scope guard detected a diagnostic ask. The system halts rather than answering a nearby question. It does not hedge and does not deflect to "consult a professional," which for someone facing a multi-year waiting list is rejection with better manners.

**Out of scope** — the scope guard found the question isn't about the neurodevelopmental research literature at all. Unlike `Refused`, there is no nearby question being declined and nothing personal was disclosed to handle carefully — a one-line statement of what the system covers is enough. This is the lowest-stakes terminal state and should read that way; it is a scope boundary, not a rejection.

**No evidence** — retrieval and screening left too few comparable studies. Every competitor will synthesise something from a thin corpus, because their success metric is producing an answer. This one says the literature is silent.

**Split** — the construct check found two study sets using one term for different measurements. Returns to retrieval per branch.

**Distress** — the scope guard detected crisis-level content rather than a research question. Full design in §9.2. This state gets its own copy, its own review, and its own logging discipline — it is not a variant of `Refused` and must not inherit that state's wording, tone, or handling.

Terminal state is written to `turns` on every run, `answered` included. The distribution across all six values — above all, how rarely `answered` dominates relative to the other five — is the real operational metric. How often the system refuses, scopes out, finds nothing, splits, or hits distress tells you more about whether it is behaving than any accuracy number. A rising `distress` rate is itself a signal that needs a human looking at it, not just a number in a dashboard.

---

## 9. Conversation design

The first turn carries all the risk. Someone opens a tool named after their identity and types something personal, because that is what people do.

Four possible responses, three of them wrong. Answering directly makes it an assessment tool. Refusing flatly reads as rejection, from a product carrying that name, to a group with a long history of being turned away. Deflecting to a professional is the same rejection, politely.

The workable move is **visible translation**. The system reflects back the researchable question inside the disclosure, states plainly what it can and cannot do, and asks whether that is what they want:

> You're describing exhaustion after social contact. I can show you what research says about post-social fatigue and recovery in autistic adults, including where the evidence is thin. I can't tell you whether it applies to you. Is that useful?

This acknowledges the disclosure, is honest about scope, makes the translation step visible so the user can see what the machine does, and leaves the search under their control rather than the system's inference.

### 9.1 A design problem this creates

The reference question — exhaustion after social contact — is autistic burnout and masking. Both constructs originated in the autistic community and entered the formal literature late, thin, and largely through qualitative work.

So the system, working exactly as designed, will return "not well established" for the thing the user knows to be true about their own life. That is not a bug to patch later. It is a machine that systematically downgrades community-generated knowledge in favour of a literature that historically did not ask autistic people anything, and for this audience it will be read as a political stance.

The fix is not to soften the grades. It is to report two axes separately:

- Strength of formal evidence
- Whether the finding originated in, or is corroborated by, first-person community accounts

A finding can be thin in the literature and densely reported by autistic adults. That cell is informative rather than embarrassing, and reporting it honestly is the difference between a tool the community adopts and one it warns about.

**§16 item 3, decided: sourced manually, re-checked on every corpus update.** The community-corroboration axis is populated by hand, from legitimate public community material — publications by neurodivergent-led organizations, published essays and books, community conference talks. Deliberately excluded: scraped forum posts, subreddits, or personal social media — even where technically public, harvesting someone's unguarded writing without their expecting it to feed a product violates the same consent principle §7.2 already applies to the person asking the question. Sourcing this axis from peer-reviewed journals instead was considered and rejected: axis 1 already measures exactly that, and a construct's hardest case — real in the community, not yet studied by anyone — is precisely the case a journals-only source would fail to catch.

This is not a one-time curation. Because §5.8's gap-driven ingestion means axis 1 keeps growing, a construct tagged "community-only" today can gain real formal coverage next month — and a report that stays frozen at "thin literature" after that stops being true is its own kind of dishonesty. Whenever the daily ingestion job (§5.8) lands a new claim against a construct that already has a `community_accounts` entry (§6), that construct is flagged for review. The community tag is never removed for this reason — "originally community-identified, later also formally studied" is itself the informative outcome this section exists to surface, not a state to erase once formal evidence arrives.

### 9.2 The distress path

The scope guard's `distress` classification (§7.1) needs behaviour defined before launch, not deferred as a follow-up. It is the highest-risk terminal state in the system, and it is currently the least specified.

**Trigger.** Distress is not "sad" or "frustrated" — those are within scope for a tool discussing burnout and masking. It is indicators of self-harm risk, acute hopelessness, or crisis-level language. The classifier needs its own labelled examples for this category, kept separate from `diagnostic_ask` examples during development. Conflating the two either false-refuses ordinary distress or under-triggers real crisis, and both failure directions are bad in different ways.

**Response shape.** Safety content is shown first and unconditionally — never appended after an attempted answer, never behind a footer. If the message also contains an answerable research question ("I can't take this anymore, is ADHD burnout even real"), the system shows the safety response, then asks explicitly whether they would also like the research question answered. It does not assume yes and proceed straight to prose, and it does not hard-refuse the research question outright — that repeats the exact rejection-with-worse-manners failure §9 already rejects for `Refused`.

**Resources are data, not generated text.** Crisis line numbers are a static, maintained table keyed by locale, never model output. A hallucinated or outdated crisis number is close to the worst failure this system could produce. Locale comes from whatever jurisdiction mechanism resolves §16 open decision #1; until that exists, the system should say plainly that it cannot show region-appropriate resources and give an internationally-recognised fallback rather than guessing a country.

**Copy is written separately from `Refused`.** The `Refused` message is deliberately blunt, for a different context — someone facing a nearby diagnostic question and a long wait. Reusing that tone here is wrong for the opposite reason `Refused`'s tone is right. Distress copy needs its own drafting and review, ideally by someone with crisis-response experience, not inherited from whoever wrote the research-refusal copy.

**Logging.** Same privacy discipline as everywhere else in the system (§7.2), tightened. Log that `distress` fired and what terminal action followed. Never log the raw content that triggered it beyond what a classifier-improvement pipeline strictly needs, and give this log category shorter retention than ordinary Q&A turns.

---

## 10. Non-literature lane

Some questions are not answerable from primary research: service availability, diagnostic pathways, device approval status, what a guideline recommends.

**Jurisdiction — decided: UK, for the first build (§16 item 1).** The reference case throughout this document is already priced in £ with a "multi-year queue," which specifically matches the NHS's documented ADHD assessment backlog — this decision formalises a scope the worked example already assumed, rather than introducing a new one. It also means NICE, not the CDC, is the primary guidance source, and the crisis-line example in §9.2/`agents.md` (Samaritans, 116 123) is correct as written.

**Use APIs where they exist.** ClinicalTrials.gov and NICE have structured access and return records, not links. The MHRA — the UK's device regulator — does not: its public device register (PARD, via the DORS registration system) is a searchable web database, not a queryable REST API the way openFDA is for the US.

openFDA remains useful in a UK-scoped build as **supplementary international context, not the primary source** — plenty of devices marketed in the UK also carry US FDA clearance, and a device's international regulatory picture is part of the honest record. But it is not what jurisdiction correctness rests on here; MHRA/PARD is.

The reference case is served by whichever regulatory record actually exists for the device in question — a UK clinic's device may show up in PARD, in an FDA clearance cited as marketing, in both, or in neither. A 510(k) or its UK equivalent establishes only substantial equivalence to a legally marketed predicate device, not diagnostic validity — and the record itself makes that point better than any paraphrase, regardless of which country issued it.

**PARD access — decided: a direct, purpose-built scraper, not a third-party service.** MHRA/PARD is one specific, stable, known government source, not open-ended web search — the general case a Tavily-style search API is built for doesn't apply here, since there's nothing to discover, only a fixed page to parse. A plain `requests` + `BeautifulSoup` scraper against PARD's search interface costs nothing, ever, and avoids depending on a third-party vendor's free-tier terms for something this narrow. The honest cost of this choice: if PARD's page structure changes, the scraper breaks until someone updates the parser — an acceptable, occasional maintenance cost given this runs on a schedule (below), not live traffic. If a genuinely open-ended guidance-discovery need ever emerges beyond MHRA and NICE, that is the point to revisit a search-API-based approach — not before.

**Run this at ingestion, not query time.** Pull guidance once, store it, refresh on schedule.

**Keep it in a separate lane.** Guidance is not evidence. NICE and MHRA data are recommendations and clearances respectively, not findings; a guidance page has no sample size to rank by. Separate section, separate label, own date field, outside the evidence ordering.

**Expanding beyond the UK is a real future design problem, not solved here.** Pathway information correct for one country is actively misleading elsewhere, in ways that cost people time and money. If a second jurisdiction is ever added, it needs either a hard scope-and-say-so split or an ask-once-and-route step — this document does not attempt that now.

---

## 11. Agent inventory

Eleven LLM calls, each scoped to one job with a fixed input contract and schema-constrained output. None selects tools. None decides what runs next.

| # | Agent | When | Input | Output | Temp |
|---|---|---|---|---|---|
| 1 | Design classifier | Ingest, per paper | Title, abstract, methods | Design type | 0 |
| 2a | Imaging auditor | Ingest, per field | Full text + one field | Four-value verdict + snippet | 0 |
| 2b | Trial auditor | Ingest, per field | Full text + one field | Four-value verdict + snippet | 0 |
| 2c | Qualitative auditor | Ingest, per field | Full text + one field | Four-value verdict + snippet | 0 |
| 2d | Psychometric validation auditor | Ingest, per field | Full text + one field | Four-value verdict + snippet | 0 |
| 2e | Observational cohort auditor | Ingest, per field | Full text + one field | Four-value verdict + snippet | 0 |
| 3 | Claim extractor | Ingest, per paper | Results, discussion | Claims + instruments + quotes | 0 |
| 4 | Snippet verifier | Ingest, per claim | Claim + different text slice | Located sentence, or none | 0 |
| 5 | Scope guard | Query, per turn | Raw input | Four-way classification | 0 |
| 6 | Translator | Query, per turn | Raw input | Research query + reflection | 0 |
| 7 | Construct disambiguator | Query, conditional | Claims + instruments | Comparable or not | 0 |
| 8 | Writer | Query, per turn | Ranked papers + chunks | Prose | 0 |
| 9 | Citation checker | Query, per turn | Draft + supplied chunks | Flags | 0 |

**Not agents:** retrieval (a query), reranking (a scoring model), ranking (SQL), the construct check itself (a join). None of these make decisions, which is why they can be tested.

**Model sizing — decided: GPT-4o for all 11 agents, no tiering.** The original design tiered by cost — best-available for the accuracy-critical agents (2a–2e, 3), small/fast for the cheap ones (4, 5, 9) — specifically to avoid overpaying on calls where a lighter model performs just as well. Running everything on one model gives that up deliberately, in exchange for one vendor and one model to manage. The cost line below reflects this choice; a tiered GPT-4o + GPT-4o-mini split would cost less on agents 4, 5, and 9 without changing agents 2a–2e/3/8, if that trade is reopened later.

**Temperature: 0 everywhere except the writer.** Every classification, extraction, verification and routing decision in this system must be reproducible — that is the determinism guarantee in §4, and temperature above 0 on a verdict-producing call means the same paper can audit differently on re-ingestion for no reason traceable to the source text. The writer is the one deliberate exception, at a low but non-zero 0.2: it is producing prose, not a verdict, and some variation in phrasing is acceptable where variation in fact is not. This does not weaken §4's guarantee, because the writer is constrained to supplied chunks (§7.5) and checked against them afterward (§7.6) — temperature can vary its sentences, not its citations. If a reproducibility test on the writer's output flags substantive drift rather than phrasing drift, that is itself a signal the citation checker's coverage has a gap.

**Cost shape, recomputed for GPT-4o at $2.50/$10 per 1M input/output tokens:** agents 1–4 dominate because they run per paper. Ten thousand papers at roughly fifteen calls each is around 150,000 ingestion calls if every paper in the corpus gets fully audited — roughly $2,200 naively, dropping to around $1,450–1,500 with OpenAI's automatic prompt caching on the auditor calls (all ~10 field calls for one paper share the same full-text input, and OpenAI applies the caching discount automatically above ~1,024 cached tokens, no code change needed), and roughly $700–750 on top of Batch API's 50% discount, since ingestion is explicitly not latency-sensitive. With the two-phase split in §5.8, this is a ceiling, not a bill — actual spend tracks how much of the corpus real queries ever retrieve, not corpus size, and given the free-tier corpus cap of ~2,000–2,600 papers (§16 item 2), the realistic ceiling is roughly a quarter of these figures. Agents 5–9 are four to five calls per user turn, on the order of $0.02–0.03 per answered turn, dominated by the writer's single call — slightly cheaper per turn than the tiered estimate despite no tiering, because GPT-4o's rate is lower than the "best available" tier it replaces.

**Shared failure contract:** every agent may return "cannot determine," which propagates as a null or `unchecked`, never as a plausible guess. Extraction agents write model and prompt version to `extracted_by`, so improving a prompt tells you which rows to re-run.

**Every agent's system prompt is versioned, not just the extraction agents' output.** Each of the 11 agents runs one fixed, narrow prompt for its one job — that specificity is what makes an agent's output checkable at all (§5.3's "did this paper report X — yes, no, n/a" versus "assess this paper's quality"). But a fixed prompt still changes over time as it's tuned, and a `quality_checks` row produced under prompt version 3 sitting next to one produced under version 4 in the same ranking is the same silent-inconsistency risk §11 already guards against for models. Record the prompt version alongside the model version everywhere `extracted_by` (or its query-path equivalent) is written, for all 11 agents — not only the ones labelled "extraction" — so a prompt change tells you exactly which rows are now stale.

---

## 12. Orchestration

Strictly sequential. Transitions determined by the state machine, not by any agent's judgement. No agent calls another agent. No agent selects a tool. The only loop is the construct split, triggered by a SQL result.

**Ingestion** needs concurrency, not a graph framework. 150,000 calls run serially would take on the order of days of wall-clock time even at a couple of seconds per call, and the 30-day schedule (§15) allocates only five days to the auditor and extraction agents that generate most of that volume — so throughput is a real constraint, not a detail to defer.

The resumption problem is already solved by §6's schema: `quality_checks` rows are created eagerly with `unchecked`, so "resume rather than restart" is just "reprocess every row still `unchecked`." No separate checkpoint store is needed for this, which means the earlier instinct to reach for a graph framework specifically for checkpointing was solving a problem the database already solves.

What ingestion actually needs is a **worker pool** — decided: a plain Python pool (`asyncio` or `multiprocessing`), not Celery, and no message broker (Redis or otherwise) at all. Celery's job in the conventional pattern is dispatching task messages through a broker; but §6's schema already *is* the queue — `quality_checks.status = 'unchecked'` plus the `priority` flag below, claimed via row locking. Running Celery+Redis on top would mean two systems tracking "what needs doing" that have to stay in sync, which is redundant infrastructure for a queue that already exists. Workers simply poll Postgres directly, rate-limited against provider API limits. Two things this requires that a naive "loop over unchecked rows" would miss:

- **Claim locking**, so two workers never process the same row twice. `SELECT ... FOR UPDATE SKIP LOCKED`, or a `claimed_at`/`worker_id` pair with a staleness timeout, either works — the point is that concurrent workers reading from the same `unchecked` queue is a race condition by default, not a resumption strategy by default.
- **Idempotent writes.** A task that dies after calling the model but before writing the row must be safe to retry without double-charging or double-writing. This falls out naturally if writes are a single upsert keyed on `(paper_id, field_id)`, but it should be designed in, not assumed.

**The queue has two priority lanes, not one.** Per §5.8, Phase B (the expensive audit) is demand-prioritized: a background lane works through `unchecked` rows at whatever steady rate the budget allows, and a high-priority lane jumps a paper to the front the moment retrieval (§7.3) actually surfaces it for a real query. This is still "process the queue," not "decide what to do next" — promotion is triggered by a retrieval fact (this paper was in someone's top-K), not by a model's judgement call, so it doesn't reopen the control-flow risk described below.

A worker pool also carries none of the risk described below, because ingestion's control flow is "process the queue," not "decide what to do next."

**Scheduling — decided: `pg_cron`, not Celery Beat.** Dropping Celery loses its scheduler along with it, and two things in this document need one: the once-a-day gap-fill job (§5.8) and the periodic NICE/MHRA refresh (§10). `pg_cron` is a Postgres extension Supabase supports enabling directly in the same database already running everything else — it fires a scheduled job with no new service, no new credential, nothing beyond a database migration. The same "don't add infrastructure the database already gives you" reasoning that dropped the broker above applies here too.

**The query path** should be plain code. Six steps and one branch. A framework adds a dependency and a debugging layer for control flow that fits in a hundred lines.

**Neither path needs a graph framework, and the reason is the same one in both places.** The risk with any graph framework is its gravity: it makes adding a node that decides which node runs next very cheap, and once that exists you have the retrieval-strategy-choosing agent that measured 0.671 against 0.827. Not a fault of the tool, just the direction it makes easy. Ingestion avoids this with a worker pool over a queue; the query path avoids it by being a hundred lines of plain code. Neither needs an agentic control-flow abstraction to solve a problem it doesn't have.

### 12.1 API surface (FastAPI)

The query path (§7) is exposed over HTTP through FastAPI, and the Swagger/OpenAPI docs at `/docs` are generated from the same Pydantic models that validate the requests and responses — not a separately maintained spec. This matters more than it sounds: the whole system's credibility rests on schema-constrained, never-a-plausible-guess outputs (§11's shared failure contract, §6's structural ban on a confidence column), and Pydantic response models are that same discipline applied one layer further out. If a field can't be represented in the schema, it can't leave the process, at the API boundary exactly as it can't at the agent boundary.

**Endpoints:**

- `POST /sessions` — creates a session. Only if the user has opted in to persistence (§16 item 5); otherwise a turn can run statelessly against an ephemeral session.
- `POST /sessions/{session_id}/turns` — submits `raw_input`, runs the full query path (§7), returns the turn result. This is the one endpoint that matters.
- `GET /sessions/{session_id}/turns/{turn_id}` — retrieves a stored turn.
- `GET /sessions/{session_id}` — lists a session's turns, `raw_input` fields redacted or absent once past the retention window set in §6.
- `DELETE /sessions/{session_id}` — user-initiated erasure. Needs to actually delete, not soft-flag, to mean anything under §16 item 5's "visible and deletable."
- `GET /papers/{paper_id}` — drill-down into a cited paper: design type, `study_facts`, `quality_checks` with their evidence snippets. This is what makes §7.3's "you show them the clause" claim real rather than rhetorical — the ranking explanation has to be something a client can actually fetch and render.

**The turn response schema is a discriminated union on `terminal_state`, not one loose shape with optional fields.** §8 defines six values, each with a genuinely different payload: `answered` carries prose and citations; `distress` carries the resource table and the follow-up question from §9.2; `split` carries the branch queries; `refused` and `out_of_scope` carry only a message. Modelling this as `answer: Optional[str]`, `resources: Optional[list]`, etc. all on one schema lets a client accidentally render an empty `answer` field as if it were a real (if terse) response. A discriminator on `terminal_state` with one Pydantic model per value makes that failure mode a type error caught before the response is ever sent, which is the same reasoning §6 gives for making the four-value quality-check enum a first-class type instead of a nullable free-for-all.

**Not exposed on this surface:** ingestion. The worker pool in §12 runs against the database directly; it has no reason to go through a public API, and putting it behind one would be surface area this system doesn't need. If ingestion needs remote monitoring, that is a separate, authenticated admin surface, not a `/papers` `POST` or `PUT`.

---

## 13. Validation

Roughly a third of the build allocated here, deliberately. This is not overhead; it is the differentiator made checkable.

### 13.1 Gold answer first

Before writing pipeline code, answer the reference question by hand. Search PubMed, read the papers, write the answer you want the system to produce. Two or three hours.

This settles more design questions than a week of architecture work. You discover how many papers were actually needed (likely under fifteen, which means half the retrieval design is over-built). You notice, in real time, what made you rank them as you did — those are your ranking rules, and they will be more specific than anything written down in advance. You find out which quality fields you actually checked, which will not be the twelve listed here. And you end up with a gold-standard output to test everything against.

The failure mode that kills projects like this is building a pipeline before knowing what a good output looks like, then optimising it for the wrong thing.

### 13.2 Labelled extraction set

Hand-code 60–100 papers from the target corpus: design, sample sizes, site count, cohort, which quality fields are genuinely reported. Measure extraction against it.

This produces a number. Elicit publishes 81.4% extraction accuracy against 86.7% for human reviewers. Having your own figure puts you in that conversation rather than adjacent to it.

The labelled set is also a byproduct worth more than the application. No validated quality-annotation corpus exists for neuroimaging in neurodevelopmental conditions. That is publishable, and it is the resource that would make a trained model possible later.

### 13.3 User testing

Five neurodivergent adults, one hour each, watching them use it. Cochrane's own work on LLM-generated plain language summaries concluded that engagement with actual consumers is necessary to judge whether a summary is useful.

Everyone skips this step and it decides whether the community adopts the tool or warns each other about it.

---

## 14. Competitive position

The position is narrow, and that is correct.

**Above:** Cochrane and Trialstreamer/RobotReviewer hold the methodology and the institutional credibility. Trialstreamer has been generating on-demand evidence maps from automatically annotated trial data since 2020, open source.

**Beside:** Elicit, Consensus, Scite and Undermind hold the corpora, the UX and years of engineering. They all draw on Semantic Scholar or OpenAlex; the differentiation is entirely in the layer on top.

**Below:** free general models hold distribution. The realistic competitor is a user's already-open chat window.

There is no obvious gap in the middle, which forces the question honestly: what does someone get here that Consensus with a good prompt does not?

The only answer with substance is domain-specific ranking that generic tools get wrong. Recency being anti-correlated with reliability. Single-site to multi-site accuracy collapse. Construct drift across DSM revisions. Regulatory clearance not implying diagnostic validity. Absence as a first-class field.

None of the tools above encode any of that, because doing so requires someone who has done the preprocessing to know it matters. That knowledge is the moat. Encoding it as rules is the build.

---

## 15. Schedule

Thirty days.

| Days | Work |
|---|---|
| 0 | Write the gold answer by hand |
| 1–5 | Corpus assembly, schema, ingestion scaffolding |
| 6–10 | Hybrid retrieval, OpenAI embedding, reranking (reranker choice still open, §5.7) |
| 11–15 | Auditor agents, absence detection, claim extraction |
| 16–19 | Hand-label the validation set |
| 20–22 | Measure extraction, fix prompts, re-run |
| 23–25 | Ranking SQL, construct check, verification passes |
| 26–28 | Interface, conversation design, terminal states |
| 29–30 | Reference case demo, write up measurements |

Note that days 16–22 produce no features. That is deliberate. You cannot beat the incumbents on engineering and do not need to. You beat them by being demonstrably right in one domain where they are wrong, and "demonstrably" is the load-bearing word.

---

## 16. Open decisions

1. **Jurisdiction — decided: UK.** Matches the reference case's £-pricing and NHS-queue framing, which the document already assumed before this was formalised. NICE is the primary guidance source; MHRA's device register (PARD) has no API and is pulled via a direct, purpose-built scraper (free, no third-party service — §10); openFDA remains as supplementary international context only. Full reasoning in §10. Expanding to a second jurisdiction is a real future problem, not attempted here.

2. **Corpus boundary — decided, both size and query.** 500 MB of database storage, at roughly 150–200 KB per paper (text + embeddings + index), caps the first build at approximately **2,000–2,600 papers**, not the 10,000 used elsewhere in this document as an illustrative example. Reserve some of that 500 MB for `sessions`/`turns` growth rather than spending it all on papers. Upgrade to Supabase Pro ($25/month, 8 GB) once actual storage use approaches ~400–450 MB.

The `esearch` query and per-condition capping strategy are specified in §5.1. **Capped per condition, not one relevance-sorted pool** — autism and ADHD each have literatures an order of magnitude larger than dyspraxia and Tourette's, so a single combined query capped by relevance alone would crowd out the smaller-literature conditions almost entirely, contradicting §1's equal-standing scope across all five. ~500 papers per condition × 5 conditions ≈ 2,500 total, inside the free-tier cap. The two-phase ingestion in §5.8 means this doesn't have to be exactly right on day one — gap-driven growth fills in what a fixed initial cap misses.

3. **Community-evidence axis — decided.** Sourced manually from public community organizations, essays, books, and talks — never scraped forum/social posts, for the consent reasons in §9.1. Stored in its own `community_accounts` table, linked to `constructs`, re-checked (not re-sourced) whenever the daily ingestion job (§5.8) adds a new claim against an already-tagged construct. Full reasoning in §9.1.

4. **Naming — decided: keep "neurodivergence" as the product's naming basis.** The abstract-noun-vs-community-vocabulary distinction noted here is accepted as a known trade, not resolved by renaming away from it.

5. **Session persistence default.** Opt-in is the recommendation. Storing questions, never inferences. Visible and deletable.

---

## Appendix: what this system will not become

Recorded here because each was considered and rejected for reasons that do not expire.

**A trained evidence-quality model.** No ground truth exists to train against. Replication outcomes are largely absent from this literature, and expert quality ratings do not converge — one review found 46 scales and 51 checklists for observational study quality with no consensus on validity criteria and numerical scores judged meaningless. You would be training a model to imitate a judgement nobody makes consistently.

**An autonomous research agent.** The stopping condition would be a model judging its own sufficiency, which in this literature arrives early and wrong.

**A personalisation engine.** More elicited context does not improve retrieval past a shallow point; it gives the model more material to pattern-match, and returns the user's own narrative to them with DOIs attached. Confirmation bias with citations is worse than an ungrounded answer, because the citations make it hard to argue with.

**A confidence scorer.** See §2.2 and §2.3.
