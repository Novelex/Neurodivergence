"""Shared paper-processing logic, split into cheap and expensive phases (§5.8).

ingest_cheap: fetch, license-gate, chunk+embed, store bibliographic + chunks. No GPT-4o
call at all — this is Phase A, safe to run on every paper a search finds.

classify_and_audit: design classification + one representative audit field. This is
Phase B — the expensive part — and should only run on papers that actually survive
retrieval as relevant, not on everything a search happens to find. Batch scripts
(scripts/phase1_e2e_test.py) can call both back to back; the live query-time search
(query/live_search.py) defers classify_and_audit until vector search narrows down which
papers actually matter, which is the whole point of the split.
"""

import os
from dataclasses import dataclass

from neurodiversity.agents.auditors import cohort, imaging, psychometric, qualitative, trial
from neurodiversity.agents.base import AgentResult
from neurodiversity.agents.design_classifier import classify
from neurodiversity.db.models import DesignType, Paper, PaperLicense
from neurodiversity.ingestion.embeddings import embed_chunks
from neurodiversity.ingestion.sources import pmc

AUDITOR_ROUTING = {
    DesignType.imaging_case_control: (imaging, "multiple_comparisons_correction"),
    DesignType.trial: (trial, "randomisation_method"),
    DesignType.qualitative: (qualitative, "sampling_strategy_rationale"),
    DesignType.psychometric_validation: (psychometric, "internal_consistency_reported"),
    DesignType.observational_cohort: (cohort, "baseline_confounders_adjusted"),
}


def chunk_text(text: str, max_chars: int = 1500) -> list[str]:
    """Simple paragraph-based chunking — good enough to prove the pipeline."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, current = [], ""
    for p in paragraphs:
        if len(current) + len(p) > max_chars and current:
            chunks.append(current.strip())
            current = p
        else:
            current = f"{current}\n\n{p}" if current else p
    if current.strip():
        chunks.append(current.strip())
    return chunks


@dataclass
class IngestResult:
    paper_id: str
    already_processed: bool  # had a design_type already — classify_and_audit can skip
    usable_full_text: str | None
    methods_excerpt: str
    title: str
    abstract: str


def ingest_cheap(db, paper: Paper) -> IngestResult:
    """Phase A. No GPT-4o call. Fetch, license-gate, chunk+embed, store."""
    print(f"\n--- [{paper.pubmed_id}] {paper.title[:70]!r} ---")

    existing = db.table("papers").select("id").eq("pubmed_id", paper.pubmed_id).execute().data
    if existing and not os.environ.get("FORCE_REPROCESS"):
        paper_id = existing[0]["id"]
        facts = db.table("study_facts").select("design_type").eq("paper_id", paper_id).execute().data
        already_done = bool(facts and facts[0]["design_type"])
        print(f"      already ingested{' and classified' if already_done else ''} — reusing")
        return IngestResult(paper_id, already_done, None, "", paper.title, paper.abstract or "")

    full_text_result = None
    if paper.pmc_id:
        full_text_result = pmc.fetch_fulltext(paper.pmc_id)

    licensed_for_storage = full_text_result is not None and full_text_result.license not in (
        PaperLicense.closed,
        PaperLicense.unknown,
    )

    if full_text_result:
        paper.license = full_text_result.license
        if licensed_for_storage:
            paper.has_fulltext = True
            paper.full_text = full_text_result.text
            print(f"      full text: {len(full_text_result.text)} chars, license={full_text_result.license.value}")
        else:
            print(f"      full text fetched but license={full_text_result.license.value}: not stored (§5.1 gate)")
    else:
        print("      no PMC full text available (metadata-only paper)")

    usable_full_text = full_text_result.text if licensed_for_storage else None

    row = paper.model_dump(mode="json", exclude={"id"}, exclude_none=True)
    inserted = db.table("papers").upsert(row, on_conflict="pubmed_id").execute()
    paper_id = inserted.data[0]["id"]

    if usable_full_text:
        chunks = chunk_text(usable_full_text)
        embeddings = embed_chunks(chunks)
        chunk_rows = [
            {"paper_id": paper_id, "chunk_index": i, "text": c, "embedding": e}
            for i, (c, e) in enumerate(zip(chunks, embeddings))
        ]
        db.table("chunks").delete().eq("paper_id", paper_id).execute()
        db.table("chunks").insert(chunk_rows).execute()
        print(f"      chunks: {len(chunk_rows)} stored")

    if licensed_for_storage and full_text_result.methods_text:
        methods_excerpt = full_text_result.methods_text[:3000]
    elif usable_full_text:
        methods_excerpt = usable_full_text[:3000]
    else:
        methods_excerpt = ""

    return IngestResult(paper_id, False, usable_full_text, methods_excerpt, paper.title, paper.abstract or "")


def classify_and_audit(db, ingest_result: IngestResult) -> tuple[str, str | None]:
    """Phase B. The expensive part — call only for papers that survived retrieval as relevant."""
    if ingest_result.already_processed:
        facts = db.table("study_facts").select("design_type").eq("paper_id", ingest_result.paper_id).execute().data
        return facts[0]["design_type"], None

    classification = classify(
        ingest_result.title, ingest_result.abstract, ingest_result.methods_excerpt or ingest_result.abstract
    )
    design_type = classification.output.design_type
    print(f"      design_type = {design_type.value} (model={classification.model})")

    db.table("study_facts").upsert(
        {"paper_id": ingest_result.paper_id, "design_type": design_type.value},
        on_conflict="paper_id",
    ).execute()

    audited_field = None
    if ingest_result.usable_full_text and design_type in AUDITOR_ROUTING:
        auditor_module, field_id = AUDITOR_ROUTING[design_type]
        field_row = db.table("quality_fields").select("*").eq("id", field_id).execute().data
        if field_row:
            field_row = field_row[0]
            verdict: AgentResult = auditor_module.audit_field(
                ingest_result.usable_full_text, field_row["name"], field_row["rationale"]
            )
            print(f"      [{auditor_module.__name__.split('.')[-1]}] {field_id}: verdict = {verdict.output.verdict.value}")
            db.table("quality_checks").upsert(
                {
                    "paper_id": ingest_result.paper_id,
                    "field_id": field_id,
                    "status": verdict.output.verdict.value,
                    "evidence_snippet": verdict.output.evidence_snippet,
                    "location": verdict.output.location,
                    "model": verdict.model,
                    "prompt_version": verdict.prompt_version,
                },
                on_conflict="paper_id,field_id",
            ).execute()
            audited_field = field_id

    return design_type.value, audited_field


def process_paper(db, paper: Paper) -> tuple[str, str, str, str | None]:
    """Convenience wrapper: both phases back to back. Used by the batch script, where
    every found paper is worth fully processing — unlike live search, there's no
    "wait and see if it's relevant" step for a pre-planned condition-based crawl."""
    ingest_result = ingest_cheap(db, paper)
    design_type, audited_field = classify_and_audit(db, ingest_result)
    return paper.pubmed_id, paper.title, design_type, audited_field
