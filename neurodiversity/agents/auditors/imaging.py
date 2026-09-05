"""Agent 2a — Imaging auditor. See docs/agents.md §2a.

Ingest, one call per paper covering EVERY applicable field at once (v2 — was one call per
field per paper; 13 fields meant 13x the calls for a single imaging paper, working spec
§5.3, including comorbidity_exclusion_reported added after the gold-answer exercise,
docs/gold-answer.md). The field list is identical across every imaging paper (it comes
straight from quality_fields, not anything paper-specific), so it's also the STATIC part of
this prompt — putting it in the system message, ahead of the paper's own full text in the
user message, means the prefix is byte-identical across different papers' audit calls, not
just reused within one call. That ordering is what makes provider-side prompt caching apply
here at all (see agents/base.py's module docstring on prefix ordering).
"""

from typing import Optional

from pydantic import BaseModel

from neurodiversity.agents.base import MODEL_MINI, AgentResult, run_agent
from neurodiversity.db.models import QualityCheckStatus

PROMPT_VERSION = "v2"  # v2 = plural fields, one call per paper instead of one per field

SYSTEM_PROMPT_TEMPLATE = """You check whether a neuroimaging paper's full text reports each of the
following methodological quality fields. You are given the full list up front, then the paper's
full text.

Fields to check:
{field_list}

For EACH field above, return one verdict, in the same order:
- verdict: "reported" if the full text explicitly addresses this field, "absent" if the
  full text was searched and does not address it, "not_applicable" if this field does not
  apply to this paper's specific design, "unchecked" only if the provided text is
  insufficient to determine an answer (e.g., a required section is missing or truncated).
- evidence_snippet: the exact verbatim sentence supporting "reported", or null for any
  other verdict. Do not paraphrase — copy the sentence exactly as it appears in the source.
- location: the section the snippet came from (e.g., "Methods", "Supplementary"), or null.

Return exactly one verdict per field listed above — do not skip any, do not add any, and
keep them in the same order so they can be matched back up by position.

Never guess. If you cannot find a supporting sentence, the verdict is "absent," not
"reported" with a fabricated or paraphrased snippet. "unchecked" means the text you were
given wasn't enough to tell — not that the paper itself was vague; a paper that is
genuinely vague about a field is "absent," not "unchecked.\""""


class FieldVerdict(BaseModel):
    field_id: str
    verdict: QualityCheckStatus
    evidence_snippet: Optional[str] = None
    location: Optional[str] = None


class AuditResult(BaseModel):
    verdicts: list[FieldVerdict]


def audit_fields(full_text: str, fields: list[dict]) -> AgentResult:
    """fields: [{"id", "name", "rationale"}, ...] — every quality_fields row applicable to
    this paper's design_type, in one call instead of one call each."""
    field_list = "\n".join(
        f"{i}. field_id=\"{f['id']}\" — {f['name']}\n   Why it matters: {f['rationale']}"
        for i, f in enumerate(fields, start=1)
    )
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(field_list=field_list)
    return run_agent(
        system_prompt=system_prompt,
        user_message=f"Full text:\n\n{full_text}",
        output_model=AuditResult,
        prompt_version=PROMPT_VERSION,
        model=MODEL_MINI,
        temperature=0.0,
    )
