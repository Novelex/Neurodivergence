# NeuroEvidence — setup checklist

Practical, one-time account/key setup before any ingestion code runs. Not a design document — see `neuroevidence-working-spec.md` for the reasoning behind each choice referenced here.

---

## 1. Corpus-collection APIs (§5.1)

- [x] **NCBI API key** (covers PubMed E-utilities `esearch`/`efetch` and PMC's OA Web Service)
  - Create an NCBI account: https://www.ncbi.nlm.nih.gov/
  - Generate a key under Account Settings → API Key Management
  - Raises the rate limit from 3 requests/sec to 10/sec — worth doing before running the ~500-per-condition `esearch` calls from §5.1.1
  - Store as `NCBI_API_KEY`

- [x] **Semantic Scholar API key** (second, independent citation graph, §5.1) — used alongside OpenAlex's, not instead of it; initial application was rejected, key obtained afterward
  - Store as `SEMANTIC_API_KEY`

- [x] **Crossref — no signup, just a header** (retraction status, §5.1)
  - Set `User-Agent` to include a real contact email on every request — this is Crossref's "polite pool," and it meaningfully raises reliability and rate limits
  - Store the contact email as `CROSSREF_CONTACT_EMAIL`, used to build the header at request time

- [x] **OpenAlex API key** (metadata gaps *and* the citation graph, §5.1) — required as of a recent OpenAlex policy change, not optional
  - Create an account at https://openalex.org/, grab the key at https://openalex.org/settings/api — free, no approval, ~30 seconds
  - Free tier: $1/day usage credit, comfortably enough for this project's volume spread across ingestion
  - Store as `OPENALEX_API_KEY`
  - Also add `mailto=<email>` as a query parameter on every request for the polite-pool treatment — reuse `CROSSREF_CONTACT_EMAIL`

---

## 2. Model + embeddings (§5.7, §11)

- [x] **OpenAI API key** (GPT-4o for all 11 agents + the reranker; `text-embedding-3-large` for chunk embeddings) — key stored; confirm billing is enabled before running real ingestion volume, free-tier credits alone won't cover it

---

## 3. Non-literature lane (§10) — separate from corpus collection above

- [ ] **NICE** — structured access, primary UK guidance source. Check current access requirements at time of build.
- [ ] **MHRA/PARD scraper** — no signup, no key, no third-party service (§10, decided fully-free)
  - Direct `requests` + `BeautifulSoup` parser against PARD's public search interface: https://aic.mhra.gov.uk/era/pdr.nsf/
  - No credentials to store — just code, run on the same ingestion schedule as everything else in this section
  - Expect occasional maintenance if PARD's page structure changes; that's the accepted cost of zero ongoing fees
- [ ] **openFDA** — no key required for reasonable volume; supplementary international context only (§10), not the primary source in this UK-scoped build

---

## 4. Infrastructure

- [x] **Supabase project created, `schema.sql` and `seed_quality_fields.sql` both run, keys stored** (free tier, §16 item 2)
  - `SUPABASE_URL`, `SUPABASE_ANON_KEY` (API layer, respects RLS), `SUPABASE_SERVICE_ROLE_KEY` (ingestion worker pool only, bypasses RLS by design §6.1) — all in `.env`
  - The standard pooled connection (transaction mode) is fine for the worker pool's `SELECT ... FOR UPDATE SKIP LOCKED` claim-locking, as long as the claim and status update happen in one transaction — no separate direct connection string needed (§6.1, corrected from an earlier draft of this doc)
- [ ] **Enable the `pg_cron` extension** (Database → Extensions in the Supabase dashboard) — still outstanding, needed for the daily gap-fill job (§5.8) and periodic NICE/MHRA refresh (§10)

- [ ] ~~Redis~~ — decided against (§12): the worker pool polls Postgres directly, `pg_cron` handles scheduling. No broker to host, no `REDIS_URL` needed.

---

## 5. `.env` template

All the variable names above, as a starting `.env` (values left blank — never commit this file once filled in; `.gitignore` already excludes it):

```
NCBI_API_KEY=
OPENALEX_API_KEY=
SEMANTIC_API_KEY=
CROSSREF_CONTACT_EMAIL=
OPENAI_API_KEY=
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
```

---

## 6. Deploying to Vercel

Vercel doesn't run a persistent `uvicorn` process the way local dev does — `api/index.py` re-exports the FastAPI app as a serverless function, and `vercel.json` routes every path to it. Real trade-offs of this target, not glossed over:

- **The live progress-line UI probably won't show.** `/sessions/{id}/turns/stream` (Server-Sent Events) needs chunked-streaming support Vercel's Python runtime doesn't reliably have. The frontend detects this and falls back to the plain `/turns` endpoint automatically — the app still works, it just answers with a spinner instead of live stage-by-stage progress on this deployment.
- **Turn duration vs. plan limits.** `vercel.json` requests `maxDuration: 300` (5 minutes) for the function — turns that trigger a live PubMed search plus retries can take that long. Check this against your actual Vercel plan's function-duration limit before relying on it; it may need lowering (or may not be available at all) depending on your plan.
- **No local `.env` file on Vercel.** Every variable in the `.env` template below (§5) must instead be set as an Environment Variable in the Vercel project dashboard (Settings → Environment Variables) — pydantic-settings reads them the same way either source, so no code change is needed, just re-entering the same values there.

Steps:
1. Push this repo to GitHub (or your Vercel-connected git provider).
2. In Vercel: New Project → import the repo → it should auto-detect `vercel.json`.
3. Add every variable from §5's `.env` template as an Environment Variable before the first deploy — a missing key fails closed (empty string default), which `/health`'s `api_keys_configured` will show as `false` for whichever key is missing.
4. Deploy. Check `https://<your-project>.vercel.app/health` first — confirms the function is running and every key loaded, before testing a real turn.
5. `psycopg` was removed from this project's dependencies (unused — never actually imported anywhere) specifically to keep the serverless function bundle smaller; nothing about Supabase access depends on it, since the app only ever talks to Supabase over its REST API.

---

## What's still not covered here

This checklist gets accounts and keys in hand — it does not replace the §13.1 gold-answer exercise, which the working spec treats as the mandatory first step before any pipeline code, regardless of how much infrastructure is ready.
