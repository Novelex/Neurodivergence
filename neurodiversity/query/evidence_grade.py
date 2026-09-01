"""Evidence grade — a simplified, GRADE-inspired categorical rating of how much
confidence the cited evidence itself supports. Never a probability of the answer being
"correct" (§2.3 rules that out permanently, and there's no outcome data — no record of
which papers' findings replicated and which didn't — to calibrate a number against).
This is a transparent, deterministic tally of real, checkable facts already tracked per
paper: how many independent papers agree, the strongest study design among them, whether
any is multi-site, and how complete their quality-check audits are. Plain code, no model
call — consistent with §2.5's "loop on facts, not judgement."

This is a simplification of real GRADE (Cochrane/WHO), not a certified GRADE rating —
real GRADE requires a trained reviewer's risk-of-bias and publication-bias judgment calls
this system cannot make. Labelled and returned as an adaptation for exactly that reason,
never presented as the genuine GRADE methodology.

The design-type ranking below reflects internal validity for a *comparative/quantitative*
claim (does X work better than Y) — it is not a universal ranking of study quality. A
qualitative or psychometric-validation paper answering a different kind of question is
not "worse," it simply doesn't score on this particular axis.
"""

from neurodiversity.db.client import get_service_client

_DESIGN_STRENGTH = {
    "trial": 2,
    "observational_cohort": 1,
    "imaging_case_control": 1,
    "psychometric_validation": 0,
    "qualitative": 0,
    "other_unclassified": 0,
}

_GRADE_THRESHOLDS = [
    (5, "High"),
    (3, "Moderate"),
    (1, "Low"),
]


def compute(cited_paper_ids: set[str], paper_ranks: list[dict]) -> dict:
    """paper_ranks: rows from ranking.rank() — {paper_id, site_count, n_total, fields_absent_ratio}.

    Returns {"grade": str, "factors": dict} — factors are exposed alongside the label so
    the grade is never a black box, matching how `evidence` already shows its own counts
    rather than a single opaque number.
    """
    if not cited_paper_ids:
        return {"grade": "Very Low", "factors": {}}

    db = get_service_client()
    design_rows = (
        db.table("study_facts")
        .select("paper_id, design_type")
        .in_("paper_id", list(cited_paper_ids))
        .execute()
        .data
    )
    design_by_paper = {row["paper_id"]: row["design_type"] for row in design_rows}

    cited_ranks = [r for r in paper_ranks if r["paper_id"] in cited_paper_ids]
    n_papers = len(cited_paper_ids)
    strongest_design = max(
        (design_by_paper.get(pid) for pid in cited_paper_ids),
        key=lambda d: _DESIGN_STRENGTH.get(d, 0),
        default=None,
    )
    max_site_count = max((r["site_count"] for r in cited_ranks if r["site_count"] is not None), default=0)
    absent_ratios = [r["fields_absent_ratio"] for r in cited_ranks if r["fields_absent_ratio"] is not None]
    avg_absent_ratio = sum(absent_ratios) / len(absent_ratios) if absent_ratios else 1.0

    replication_points = 2 if n_papers >= 3 else 1 if n_papers == 2 else 0
    design_points = _DESIGN_STRENGTH.get(strongest_design, 0)
    site_points = 1 if max_site_count >= 3 else 0
    completeness_points = 1 if avg_absent_ratio <= 0.25 else -1 if avg_absent_ratio > 0.75 else 0

    score = replication_points + design_points + site_points + completeness_points
    grade = next((label for threshold, label in _GRADE_THRESHOLDS if score >= threshold), "Very Low")

    return {
        "grade": grade,
        "factors": {
            "independent_papers_cited": n_papers,
            "strongest_design_type": strongest_design,
            "max_site_count": max_site_count or None,
            "avg_fields_absent_ratio": round(avg_absent_ratio, 2) if absent_ratios else None,
        },
    }
