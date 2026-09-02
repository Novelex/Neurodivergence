"""The one shared pattern behind every agent (working spec §11, docs/agents.md).

Every agent is: one fixed, narrow system prompt + one schema-constrained GPT-4o call +
model/prompt version logged on the row or turn it produces. None of the 11 agents (or
the reranker) select tools or decide what runs next — that stays in the caller, never
inside an agent.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import TypeVar

import openai
from openai import OpenAI
from pydantic import BaseModel

from neurodiversity.config import settings

T = TypeVar("T", bound=BaseModel)

# Model tiering (real testing found the working spec's original "GPT-4o for everything,
# no tiering" decision, §11, was a real latency/cost cost worth reopening — §11 already
# names this trade explicitly).
#
# MODEL_NANO (gpt-5-nano, ~3x cheaper than MODEL_MINI) is for classification, extraction,
# rewording, and casual reply agents (scope_guard, translator, broadener, greeter,
# general_chat, summarizer, reranker) — well-defined, low-ambiguity tasks.
#
# MODEL_MINI (gpt-4o-mini) is now used for the writer, citation_checker's semantic check,
# design_classifier, and every auditor — a deliberate, explicit downgrade from gpt-4o,
# requested after being flagged: these are the calls where a wrong judgment call either
# reaches the user directly (writer) or gets stored as permanent data behind an evidence
# grade (classifier/auditors), and citation_checker is the actual safety net against
# fabricated or overstated claims. If real answers start showing more citation-checker
# flags or the writer re-introducing fabricated specifics more often than before this
# change, that is the tradeoff actually landing — the fix is moving these back to gpt-4o,
# not tightening prompts further.
MODEL_NANO = "gpt-5-nano"
MODEL_MINI = "gpt-4o-mini"


@lru_cache
def get_client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


@dataclass
class AgentResult:
    output: BaseModel
    model: str
    prompt_version: str


# Some newer models (confirmed on gpt-5-nano, real error: 400 "Unsupported value:
# 'temperature' does not support 0.0 with this model. Only the default (1) value is
# supported" — the same restriction is known to apply to OpenAI's reasoning-family
# models generally, e.g. o1/o3) reject any non-default temperature outright, but every
# low-temperature call in this system was written assuming temperature is always
# honored. Tracked here rather than hardcoded by name, so a future model with the same
# restriction is handled the same way automatically, without needing another manual fix.
_TEMPERATURE_UNSUPPORTED_MODELS: set[str] = set()


def run_agent(
    system_prompt: str,
    user_message: str,
    output_model: type[T],
    prompt_version: str,
    model: str = "gpt-4o",
    temperature: float = 0.0,
) -> AgentResult:
    """One schema-constrained call. Never called with tools; never decides what runs next."""
    client = get_client()
    kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format=output_model,
    )
    if model not in _TEMPERATURE_UNSUPPORTED_MODELS:
        kwargs["temperature"] = temperature

    try:
        completion = client.beta.chat.completions.parse(**kwargs)
    except openai.BadRequestError as exc:
        if "temperature" in kwargs and "temperature" in str(exc).lower():
            # Retry once without it rather than crash the whole turn over a sampling
            # parameter this model doesn't support. Remembered for next time so every
            # later call to this same model skips straight past the failing attempt
            # instead of paying for a guaranteed-to-fail request first.
            _TEMPERATURE_UNSUPPORTED_MODELS.add(model)
            kwargs.pop("temperature")
            completion = client.beta.chat.completions.parse(**kwargs)
        else:
            raise

    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise ValueError(f"Model returned no parsed output (refusal or parse failure): {completion}")
    return AgentResult(output=parsed, model=model, prompt_version=prompt_version)
