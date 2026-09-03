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
# names this trade explicitly). Current state, arrived at through two rounds of real
# regressions, not guesswork:
#
# MODEL_MINI (gpt-4o-mini) is used for the bulk of agents: translator, broadener,
# greeter, general_chat, summarizer, reranker, design_classifier, and every auditor —
# well-defined classification/extraction/rewording tasks it has handled reliably in
# real testing.
#
# gpt-4o is used, by NOT passing model= (run_agent's default), for three specific
# agents where real evidence proved gpt-4o-mini unreliable at that exact task:
#   - scope_guard: reproducibly misclassified plain grief/loss statements ("I lost my
#     cat") as distress — the system's own highest-risk terminal state — across two
#     prompt rewrites; gpt-4o got every case right with the identical prompt.
#   - writer: on a real query with abundant genuine literature ("strategies for managing
#     ADHD symptoms"), produced quotes that were close paraphrases instead of
#     byte-for-byte copies, failing the MECHANICAL (plain-code, not judgment) citation
#     check on 6/6 citations, both the original attempt and the retry — a precision task,
#     not a judgment task, that the smaller model wasn't reliable at even with good
#     source material.
#   - citation_checker's semantic check (9b): on that same real turn, produced a
#     self-contradictory flag (reason text stated "No fidelity failure" while flagging
#     the citation anyway) — this is the actual safety net against fabricated or
#     overstated claims, not a place to accept an unreliable model.
#
# MODEL_NANO (gpt-5-nano) was tried for the simpler agents on the assumption a cheaper
# model would also be faster — real, timed testing on the identical call proved the
# opposite: gpt-5-nano took 9.27s against gpt-4o-mini's 1.95s for the same scope_guard
# classification, roughly 5x slower despite being ~3x cheaper. It's a reasoning-family
# model, and reasoning models can cost real wall-clock latency in internal reasoning
# tokens even when priced lower — cost and speed are NOT the same axis. Reverted; kept
# defined here only as a documented warning against re-trying this swap without
# re-verifying actual latency first.
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
