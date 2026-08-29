-- NeuroEvidence — query-path SQL functions
-- Run once, after schema.sql. Working spec §7.3.

-- Vector similarity search over chunks. This is the vector half of §7.3's hybrid
-- retrieve; the full-text (tsvector) half searches papers.tsv (title/abstract) directly
-- and isn't combined here yet — chunks has no tsvector column of its own in schema.sql,
-- so full chunk-level keyword search is a follow-up, not part of this small-scale proof.
create or replace function match_chunks(
  query_embedding vector(768),
  match_count int default 20
)
returns table (
  chunk_id uuid,
  paper_id uuid,
  chunk_text text,
  section text,
  similarity float
)
language sql stable
as $$
  select
    chunks.id as chunk_id,
    chunks.paper_id,
    chunks.text as chunk_text,
    chunks.section,
    1 - (chunks.embedding <=> query_embedding) as similarity
  from chunks
  order by chunks.embedding <=> query_embedding
  limit match_count;
$$;

-- Deterministic rank over a set of candidate papers. Working spec §7.3's illustrative
-- SQL (`order by has_meta desc, cohorts desc, max_sites desc, fields_absent_ratio asc,
-- largest_n desc`) uses column names that were never actually built into schema.sql —
-- there's no has_meta column, and none of the six design_type values even covers
-- "meta-analysis" as a category. This function implements ranking honestly with what
-- the schema actually has today: site_count and n_total from study_facts, and
-- fields_absent_ratio computed from quality_checks (unchecked counted as absent, per
-- §5.8/§7.3's rule — an unaudited paper must never rank as if it passed every check).
-- has_meta/cohorts are a documented gap to close, not silently faked here.
create or replace function rank_papers(paper_ids uuid[])
returns table (
  paper_id uuid,
  site_count int,
  n_total int,
  fields_absent_ratio float
)
language sql stable
as $$
  select
    p.id as paper_id,
    sf.site_count,
    sf.n_total,
    coalesce(
      (
        select count(*)::float
        from quality_checks qc
        where qc.paper_id = p.id
          and qc.status in ('absent', 'unchecked')
      ) / nullif(
        (select count(*) from quality_checks qc2 where qc2.paper_id = p.id),
        0
      ),
      1.0  -- no quality_checks rows at all yet: treat as fully absent, not a free pass
    ) as fields_absent_ratio
  from papers p
  left join study_facts sf on sf.paper_id = p.id
  where p.id = any(paper_ids)
  order by
    sf.site_count desc nulls last,
    fields_absent_ratio asc,
    sf.n_total desc nulls last;
$$;
