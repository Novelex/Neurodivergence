-- NeuroEvidence — Supabase (Postgres) schema
-- Companion to neuroevidence-working-spec.md §6. Section numbers in comments below
-- point back to the working spec's rationale — this file only implements it.
--
-- Idempotent by design: safe to re-run at any time against a database that already has
-- some or all of this. Real project history needed this — the live database was built
-- incrementally (initial run, then a separate ad-hoc ALTER for publication_status, then
-- community_accounts added to this file but never applied live), and piecemeal migration
-- snippets are how schema drift happens. From here on, "run schema.sql" is always the
-- answer, regardless of what's already there.

-- ============================================================================
-- Extensions
-- ============================================================================

create extension if not exists vector;      -- pgvector, for chunks.embedding (§5.7)
create extension if not exists pgcrypto;    -- gen_random_uuid()

-- ============================================================================
-- Enums — wrapped in DO blocks since Postgres has no CREATE TYPE IF NOT EXISTS
-- ============================================================================

do $$ begin
  -- §5.2 — all five design types now route to a built auditor (2a-2e);
  -- other_unclassified is the genuine residual case, not a stand-in for a missing auditor.
  create type design_type as enum (
    'imaging_case_control',
    'trial',
    'qualitative',
    'psychometric_validation',
    'observational_cohort',
    'other_unclassified'
  );
exception when duplicate_object then null;
end $$;

do $$ begin
  -- §5.4 — the four-value enum. Collapsing 'absent' and 'unchecked' destroys the signal
  -- this entire system is built to preserve. Never add a fifth value without re-reading §5.4.
  create type quality_check_status as enum (
    'reported',
    'absent',
    'not_applicable',
    'unchecked'
  );
exception when duplicate_object then null;
end $$;

do $$ begin
  -- §5.1 — PMC's "open access" label is not one license. 'unknown' = not yet checked;
  -- distinct from 'closed' (checked, and it isn't open). Never treat unknown as closed
  -- or vice versa when deciding what can be stored/served.
  create type paper_license as enum (
    'cc_by',
    'cc_by_nc',
    'cc_by_nc_nd',
    'closed',
    'unknown'
  );
exception when duplicate_object then null;
end $$;

do $$ begin
  -- §8 — nine values (originally six; practical_support, greeting, and
  -- needs_clarification added later). 'answered' is the ordinary case; the rest are the
  -- system deliberately stopping short (or, for greeting, not needing to search at all,
  -- or for needs_clarification, asking before guessing), and are as much a product
  -- decision as the answer is.
  create type terminal_state as enum (
    'answered',
    'refused',
    'out_of_scope',
    'no_evidence',
    'split',
    'distress',
    'practical_support',
    'greeting',
    'needs_clarification'
  );
exception when duplicate_object then null;
end $$;

do $$ begin
  alter type terminal_state add value if not exists 'practical_support';
  alter type terminal_state add value if not exists 'greeting';
  alter type terminal_state add value if not exists 'needs_clarification';
exception when duplicate_object then null;
end $$;

do $$ begin
  create type claim_direction as enum ('positive', 'negative', 'null_finding');
exception when duplicate_object then null;
end $$;

do $$ begin
  -- Added after the gold-answer exercise (docs/gold-answer.md, §13.1): the exercise
  -- needed to distinguish a published, peer-reviewed source from a not-yet-reviewed
  -- preprint, and the schema had no way to represent that. §5.4's absence semantics are
  -- about what a paper reports; this is about whether the paper itself has cleared peer
  -- review at all — a different axis, checked once at ingestion, not per quality field.
  create type publication_status as enum ('published', 'preprint', 'in_press');
exception when duplicate_object then null;
end $$;

-- ============================================================================
-- papers, study_facts — §6
-- ============================================================================

create table if not exists papers (
  id                uuid primary key default gen_random_uuid(),
  doi               text unique,
  pubmed_id         text unique,
  pmc_id            text unique,
  title             text not null,
  abstract          text,
  publication_year  int,
  journal           text,
  license           paper_license not null default 'unknown',
  has_fulltext      boolean not null default false,
  full_text         text,
  retracted         boolean not null default false,
  retracted_checked_at timestamptz,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

-- publication_status was added to this file after papers already existed live in some
-- environments — explicit ADD COLUMN IF NOT EXISTS catches that regardless of history.
-- Not peer-reviewed and peer-reviewed are different evidential objects (gold-answer
-- exercise, docs/gold-answer.md); default 'published' matches the current PubMed-only
-- corpus boundary (§5.1.1), which does not ingest preprint servers.
alter table papers add column if not exists publication_status publication_status not null default 'published';

-- Generated tsvector for keyword search — Postgres does this natively (§6), no separate
-- BM25 service needed. Generated columns can't use ADD COLUMN IF NOT EXISTS cleanly
-- alongside a fresh CREATE TABLE in one idempotent pass, so this is created separately
-- and guarded by a catalog check instead.
do $$ begin
  if not exists (
    select 1 from information_schema.columns
    where table_name = 'papers' and column_name = 'tsv'
  ) then
    alter table papers add column tsv tsvector generated always as (
      setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
      setweight(to_tsvector('english', coalesce(abstract, '')), 'B')
    ) stored;
  end if;
end $$;

create index if not exists papers_tsv_idx on papers using gin (tsv);
create index if not exists papers_license_idx on papers (license);
create index if not exists papers_has_fulltext_idx on papers (has_fulltext);

-- One row per paper. cohort_name is critical (§6): ABIDE, ADHD-200 and the large
-- consortia are reused constantly, so twelve papers can look like twelve independent
-- findings while sharing one sample. count(distinct cohort_name) depends on this column
-- being populated honestly, not left null because it's more work to fill in.
create table if not exists study_facts (
  paper_id          uuid primary key references papers(id) on delete cascade,
  design_type       design_type,                      -- null until agent 1 classifies it
  n_clinical        int,
  n_control         int,
  n_total           int,
  site_count        int,                               -- ranking SQL's "max_sites" (§7.3)
  modality          text,
  population        text,
  age_range         text,
  sex_distribution  jsonb,
  cohort_name       text,
  preregistration   boolean,
  data_availability boolean
);

do $$ begin
  -- §5.6 mechanical check: n_total should equal n_clinical + n_control; a mismatch
  -- means one of the three is wrong. Enforced here, not just checked in application code.
  alter table study_facts add constraint study_facts_n_total_check
    check (n_total is null or n_clinical is null or n_control is null
           or n_total = n_clinical + n_control);
exception when duplicate_object then null;
end $$;

create index if not exists study_facts_cohort_idx on study_facts (cohort_name);
create index if not exists study_facts_design_type_idx on study_facts (design_type);

-- ============================================================================
-- quality_fields, quality_checks — §5.3, §5.4, §6
-- ============================================================================

-- The check vocabulary as data, not an enum (§6). Adding a check requires no migration.
create table if not exists quality_fields (
  id             text primary key,        -- slug, e.g. 'multiple_comparisons_correction'
  auditor        text not null,           -- 'imaging' | 'trial' | 'qualitative'
                                           -- | 'psychometric_validation' | 'observational_cohort'
  name           text not null,
  rationale      text not null,           -- written once, reused as UI copy (§6)
  applies_to     design_type[] not null,
  display_order  int not null default 0
);

-- One row per paper per field, created eagerly at ingestion as 'unchecked' (§5.3) —
-- this doubles as the Phase B work queue (§5.8, §12), not just an audit record.
create table if not exists quality_checks (
  id               uuid primary key default gen_random_uuid(),
  paper_id         uuid not null references papers(id) on delete cascade,
  field_id         text not null references quality_fields(id),
  status           quality_check_status not null default 'unchecked',
  evidence_snippet text,
  location         text,
  -- §11's shared failure contract, extended to every agent: model + prompt version
  -- travel together, so a prompt change tells you exactly which rows are now stale.
  model            text,
  prompt_version   text,
  -- Priority-queue promotion (§5.8, §12): set when retrieval surfaces this row's
  -- paper while still 'unchecked'. Workers should claim high-priority rows first.
  priority         boolean not null default false,
  checked_at       timestamptz,
  created_at       timestamptz not null default now(),
  unique (paper_id, field_id)
);

do $$ begin
  -- §5.6: "a reported verdict with an empty evidence field is a broken contract" —
  -- enforced here, not left to application-code discipline alone.
  alter table quality_checks add constraint quality_checks_reported_has_evidence
    check (status <> 'reported' or evidence_snippet is not null);
exception when duplicate_object then null;
end $$;

-- Coverage queries ("what have we not yet examined") and the priority-queue claim
-- pattern (SELECT ... FOR UPDATE SKIP LOCKED, §6.1) both hit this index directly.
create index if not exists quality_checks_status_idx on quality_checks (status) where status = 'unchecked';
create index if not exists quality_checks_priority_idx on quality_checks (priority) where status = 'unchecked';
create index if not exists quality_checks_paper_idx on quality_checks (paper_id);

-- ============================================================================
-- constructs, measures, claims — §6, §7.4
-- ============================================================================

-- The construct-drift check lives here. Two claims about "executive function" pointing
-- at different measure_id rows are not in conflict; they measure different things.
create table if not exists constructs (
  id    uuid primary key default gen_random_uuid(),
  name  text not null unique
);

create table if not exists measures (
  id           uuid primary key default gen_random_uuid(),
  construct_id uuid not null references constructs(id),
  name         text not null,             -- e.g. "BRIEF-2", "semi-structured interview"
  dsm_era      text,                      -- catches the 2013 DSM-5 boundary (§6)
  validated    boolean not null default false  -- set true via the psychometric auditor's verdicts
);

create index if not exists measures_construct_idx on measures (construct_id);

create table if not exists claims (
  id               uuid primary key default gen_random_uuid(),
  paper_id         uuid not null references papers(id) on delete cascade,
  construct_id     uuid not null references constructs(id),
  measure_id       uuid not null references measures(id),
  direction        claim_direction not null,
  effect_size      text,
  quote            text not null,
  location         text not null,
  model            text,
  prompt_version   text,
  -- Set true only after agent 4 (snippet verifier) locates this quote in a
  -- differently-framed search — never set true by the same call that extracted it (§5.6).
  verified         boolean not null default false,
  created_at       timestamptz not null default now()
);

create index if not exists claims_paper_idx on claims (paper_id);
create index if not exists claims_construct_measure_idx on claims (construct_id, measure_id);

-- ============================================================================
-- community_accounts — §9.1, §16 item 3
-- ============================================================================

-- The community-evidence axis. Manually populated, never agent-extracted — this is
-- the one table in the schema that a human curator writes to directly, not a pipeline.
-- Linked to constructs so a query can join formal claims and community accounts on the
-- same shared vocabulary, but never joined into the ranking SQL itself (same isolation
-- principle as external_records, §6): an essay and a case-control study are different
-- kinds of object and the schema should refuse to average them.
create table if not exists community_accounts (
  id             uuid primary key default gen_random_uuid(),
  construct_id   uuid not null references constructs(id),
  source_type    text not null check (source_type in ('organization', 'book', 'essay', 'talk')),
  -- Deliberately no 'forum_post' or 'social_media' option (§9.1) — scraping unguarded
  -- personal writing without the author expecting it to feed a product violates the
  -- same consent principle §7.2 applies to the person asking the question.
  title          text not null,
  author_or_org  text not null,
  url            text,
  publication_date date,
  summary        text not null,   -- one paragraph, written by the curator, not extracted
  created_at     timestamptz not null default now(),
  -- Re-checked, not re-sourced, whenever a new claim lands against this construct
  -- (§5.8's daily job). The community tag is never removed by this review — "originally
  -- community-identified, later also formally studied" is the informative outcome, not
  -- a state to erase once formal evidence catches up.
  reviewed_at    timestamptz
);

create index if not exists community_accounts_construct_idx on community_accounts (construct_id);

-- ============================================================================
-- chunks — §5.7
-- ============================================================================

create table if not exists chunks (
  id             uuid primary key default gen_random_uuid(),
  paper_id       uuid not null references papers(id) on delete cascade,
  section        text,                    -- e.g. 'results', 'discussion', 'methods'
  chunk_index    int not null,
  text           text not null,
  embedding      vector(768),             -- OpenAI text-embedding-3-large, dims=768 (§5.7);
                                           -- not reversible to content
  created_at     timestamptz not null default now()
);

create index if not exists chunks_paper_idx on chunks (paper_id);

-- HNSW index — build once past a few thousand rows (§6). Cosine distance matches
-- OpenAI's recommended similarity metric for text-embedding-3 models.
create index if not exists chunks_embedding_hnsw_idx on chunks
  using hnsw (embedding vector_cosine_ops);

-- ============================================================================
-- external_records — §6, §10 (non-literature lane)
-- ============================================================================

-- Deliberately isolated: no foreign key into claims, no design fields, nothing the
-- ranking SQL can reach. A device clearance record and a case-control study are
-- different kinds of object and the schema refuses to average them.
--
-- Jurisdiction is UK for the first build (§16 item 1): NICE and a direct MHRA/PARD
-- scraper (free, no third-party service — §10) are the primary sources; openFDA is
-- supplementary international context only, since MHRA's device register has no
-- queryable API the way openFDA does for the US.
create table if not exists external_records (
  id             uuid primary key default gen_random_uuid(),
  source         text not null check (source in ('nice', 'mhra_pard', 'openfda')),
  record_type    text,                    -- e.g. 'guidance_page', 'mhra_pard', '510k', 'recall'
  title          text,
  content        text,
  url            text,
  jurisdiction   text not null default 'UK',  -- §10: pathway info is jurisdiction-specific;
                                               -- openFDA rows should still carry 'US' honestly
  record_date    date,
  fetched_at     timestamptz not null default now()
);

create index if not exists external_records_source_idx on external_records (source);
create index if not exists external_records_jurisdiction_idx on external_records (jurisdiction);

-- ============================================================================
-- sessions, turns — §6, §7, §8, §9.2, §12.1
-- ============================================================================

-- user_id is nullable: a turn can run statelessly against an ephemeral session when
-- the user has not opted in to persistence (§12.1, §16 item 5).
create table if not exists sessions (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid references auth.users(id) on delete cascade,
  created_at  timestamptz not null default now()
);

-- Short-term session memory. A rolling window of the last few turns' already-scrubbed
-- research_query/reflection stays exact in the turns table itself (no new storage needed
-- for that part); context_summary holds a concise, cost-bounded distillation of
-- everything OLDER than that window, updated one turn at a time as a turn ages out —
-- never a running re-summary of the whole session, to keep the update itself cheap.
-- Never raw_input — §7.2's privacy boundary holds here exactly as everywhere else, since
-- research_query/reflection are already stripped of personal/narrative detail by the
-- translator before they're ever stored.
alter table sessions add column if not exists context_summary text not null default '';

create table if not exists turns (
  id                 uuid primary key default gen_random_uuid(),
  session_id         uuid not null references sessions(id) on delete cascade,
  -- §6: raw_input and research_query stored separately so you can audit that the
  -- translation invariant held. raw_input carries its own, tighter retention —
  -- it is someone's own words about their own mind or body, not a profile, but
  -- still a data-minimization question in its own right (§6).
  raw_input          text,
  raw_input_purge_at timestamptz,
  research_query     text,
  reflection         text,
  terminal_state     terminal_state not null,
  answer_prose       text,
  citations          jsonb,               -- [{paper_id, quote}, ...] — §12.1's answered shape
  resources          jsonb,               -- crisis resources — §9.2's distress shape only
  followup_prompt    text,                -- §9.2's distress shape only
  created_at         timestamptz not null default now()
);

create index if not exists turns_session_idx on turns (session_id);
create index if not exists turns_raw_input_purge_idx on turns (raw_input_purge_at) where raw_input is not null;

-- ============================================================================
-- Row-level security — §6, §6.1: enabled before the first user touches the system
-- ============================================================================

alter table sessions enable row level security;
alter table turns enable row level security;

drop policy if exists sessions_owner_all on sessions;
create policy sessions_owner_all on sessions
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists turns_owner_all on turns;
create policy turns_owner_all on turns
  for all
  using (exists (
    select 1 from sessions s
    where s.id = turns.session_id and s.user_id = auth.uid()
  ))
  with check (exists (
    select 1 from sessions s
    where s.id = turns.session_id and s.user_id = auth.uid()
  ));

-- papers, study_facts, quality_fields, quality_checks, constructs, measures, claims,
-- chunks, external_records are the shared corpus — no RLS; read access is public
-- (or gated at the API layer, §12.1), write access is the ingestion worker pool only,
-- via the service role key, which bypasses RLS by design.

-- ============================================================================
-- Guardrail, not a query: no confidence score column exists anywhere above.
-- Enforced structurally per §6 and §2.2/§2.3 — if a migration ever adds one,
-- that migration is the thing to revert, not this comment.
-- ============================================================================
