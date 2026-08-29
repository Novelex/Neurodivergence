"""GET /papers/{id}. Working spec §12.1.

Drill-down: design type, quality_checks with evidence snippets. This is what makes
§7.3's "you show them the clause" claim real rather than rhetorical.
"""

from fastapi import APIRouter, HTTPException

from neurodiversity.api.schemas import PaperDetail, PaperQualityCheck
from neurodiversity.db.client import get_service_client

router = APIRouter()


@router.get("/papers/{paper_id}", response_model=PaperDetail)
def get_paper(paper_id: str) -> PaperDetail:
    db = get_service_client()
    papers = db.table("papers").select("*").eq("id", paper_id).execute().data
    if not papers:
        raise HTTPException(status_code=404, detail="paper not found")
    paper = papers[0]

    facts = db.table("study_facts").select("design_type").eq("paper_id", paper_id).execute().data
    design_type = facts[0]["design_type"] if facts else None

    checks = db.table("quality_checks").select("*").eq("paper_id", paper_id).execute().data

    return PaperDetail(
        paper_id=paper["id"],
        title=paper["title"],
        doi=paper.get("doi"),
        publication_year=paper.get("publication_year"),
        journal=paper.get("journal"),
        design_type=design_type,
        license=paper["license"],
        has_fulltext=paper["has_fulltext"],
        quality_checks=[
            PaperQualityCheck(
                field_id=c["field_id"],
                status=c["status"],
                evidence_snippet=c.get("evidence_snippet"),
                location=c.get("location"),
            )
            for c in checks
        ],
    )
