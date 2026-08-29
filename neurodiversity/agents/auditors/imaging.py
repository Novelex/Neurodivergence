"""Agent 2a — Imaging auditor. See docs/agents.md §2a.

Ingest, one call per field per paper. 13 fields (working spec §5.3) — includes
comorbidity_exclusion_reported, added after the gold-answer exercise
(docs/gold-answer.md). One call per field, not one call per paper: "did this paper
report X — yes/no/n/a" is a question a model answers well; "assess this paper's
quality" is not.
"""

from typing import Optional

from pydantic import BaseModel

from neurodiversity.agents.base import AgentResult, run_agent
from neurodiversity.db.models import QualityCheckStatus

PROMPT_VERSION = "v1"

SYSTEM_PROMPT_TEMPLATE = """You check whether a neuroimaging paper's full text reports one specific
methodological quality field. You are given the field name, why it matters, and the paper's full text.

Field being checked: {field_name}
Why this field matters: {field_rationale}

Output:
- verdict: "reported" if the full text explicitly addresses this field, "absent" if the
  full text was searched and does not address it, "not_applicable" if this field does not
  apply to this paper's specific design, "unchecked" only if the provided text is
  insufficient to determine an answer (e.g., a required section is missing or truncated).
- evidence_snippet: the exact verbatim sentence supporting "reported", or null for any
  other verdict. Do not paraphrase — copy the sentence exactly as it appears in the source.
- location: the section the snippet came from (e.g., "Methods", "Supplementary"), or null.

Never guess. If you cannot find a supporting sentence, the verdict is "absent," not
"reported" with a fabricated or paraphrased snippet."""


class QualityVerdict(BaseModel):
    verdict: QualityCheckStatus
    evidence_snippet: Optional[str] = None
    location: Optional[str] = None


def audit_field(full_text: str, field_name: str, field_rationale: str) -> AgentResult:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        field_name=field_name, field_rationale=field_rationale
    )
    return run_agent(
        system_prompt=system_prompt,
        user_message=f"Full text:\n\n{full_text}",
        output_model=QualityVerdict,
        prompt_version=PROMPT_VERSION,
        temperature=0.0,
    )
