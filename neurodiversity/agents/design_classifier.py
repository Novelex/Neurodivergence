"""Agent 1 — Design classifier. See docs/agents.md §1.

Ingest, per paper. Temp 0. Routes to exactly one of five auditors (2a-2e) or
other_unclassified — see the routing note in docs/agents.md about the open gap this
closed (working spec §5.2, §5.3).
"""

from pydantic import BaseModel

from neurodiversity.agents.base import MODEL_MINI, AgentResult, run_agent
from neurodiversity.db.models import DesignType

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """You classify a research paper's study design from its title, abstract, and methods excerpt.

Output exactly one of: imaging_case_control, trial, qualitative, psychometric_validation,
observational_cohort, other_unclassified.

- imaging_case_control: neuroimaging or EEG-based case-control or group-comparison design.
- trial: an intervention or treatment trial, randomized or not.
- qualitative: interview, focus group, or other qualitative data collection and analysis.
- psychometric_validation: the paper's primary purpose is validating or characterizing a
  scale, questionnaire, or measurement instrument (reliability, validity, factor structure)
  rather than studying a clinical question directly.
- observational_cohort: a group is followed and outcomes are recorded, with no intervention
  assigned by the researchers — includes prospective and retrospective cohort designs.
- other_unclassified: the design does not clearly match any of the above.

Do not guess toward one of the first five categories to avoid other_unclassified — an
incorrect specific classification routes the paper to the wrong specialist auditor, which
is worse than an honest other_unclassified. Note in particular that a trial with an
intervention arm is "trial," never "observational_cohort," even if it also reports
long-term follow-up — the presence of an assigned intervention is what separates the two.

Base the classification only on the text provided. If the methods excerpt is insufficient
to distinguish design type with confidence, output other_unclassified."""


class DesignClassification(BaseModel):
    design_type: DesignType


def classify(title: str, abstract: str, methods_excerpt: str) -> AgentResult:
    user_message = (
        f"Title: {title}\n\nAbstract: {abstract}\n\nMethods excerpt: {methods_excerpt}"
    )
    return run_agent(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        output_model=DesignClassification,
        prompt_version=PROMPT_VERSION,
        model=MODEL_MINI,
        temperature=0.0,
    )
