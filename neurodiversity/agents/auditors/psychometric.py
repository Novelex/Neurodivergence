"""Agent 2d — Psychometric validation auditor. See docs/agents.md §2d.

Ingest, one call per field per paper. 9 fields (working spec §5.3). Route a paper here
only if its primary purpose is characterising the instrument itself, not merely using an
already-validated instrument to study something else.
"""

from typing import Optional

from pydantic import BaseModel

from neurodiversity.agents.base import MODEL_MINI, AgentResult, run_agent
from neurodiversity.db.models import QualityCheckStatus

PROMPT_VERSION = "v1"

SYSTEM_PROMPT_TEMPLATE = """You check whether a psychometric validation paper's full text reports one
specific methodological quality field. You are given the field name, why it matters, and the
paper's full text.

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
        model=MODEL_MINI,
        temperature=0.0,
    )
