"""The one shared pattern behind every agent (working spec §11, docs/agents.md).

Every agent is: one fixed, narrow system prompt + one schema-constrained GPT-4o call +
model/prompt version logged on the row or turn it produces. None of the 11 agents (or
the reranker) select tools or decide what runs next — that stays in the caller, never
inside an agent.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, TypeVar

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
# MODEL_MINI (gpt-4o-mini) is used for the bulk of agents: scope_guard, danger, translator,
# broadener, general_chat, summarizer, reranker, design_classifier, and every auditor —
# well-defined classification/extraction/rewording tasks it has handled reliably in
# real testing. greeter tries a free OpenRouter model first (see its own module docstring)
# and falls back to MODEL_MINI.
#
# gpt-4o is used, by NOT passing model= (run_agent's default), for two specific agents
# where real evidence proved gpt-4o-mini unreliable at that exact task:
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
# scope_guard was a THIRD gpt-4o exception until distress detection moved into its own
# agent (agents/danger.py): gpt-4o-mini reproducibly misclassified plain grief ("I lost my
# cat") as distress when it had to weigh that against four other competing categories in
# one call. Once distress had its own agent with nothing else to weigh it against, gpt-4o-
# mini got every case right, head-to-head against gpt-4o, identical prompt, 9/9 — the
# earlier failure was never really about model capability, it was about what was competing
# for the same classification. See scope_guard.py and danger.py's own docstrings.
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


# OpenRouter (OpenAI-compatible endpoint, same SDK). Evaluated live against real free
# models before using this anywhere — see agents/greeter.py's module docstring for the
# actual evidence: the openrouter/free auto-router hard-failed 3/6 real calls (one
# response body was literally "User Safety: safe", not JSON at all), and named free
# models with structured_outputs support each had a real, disqualifying defect
# (rate-limited, malformed JSON, language leakage, or fabricated an unsourced "research
# shows" claim). Only used, currently, for the one agent (greeter) where the task has
# zero factual/safety stakes and every call has a same-turn fallback to the existing
# OpenAI path — never wired in anywhere a bad response would actually matter.
#
# Explicit, short timeout — real testing (scripts/measure_pipeline_timing.py) caught a
# free model hanging instead of erroring: 609.5s on a single "hy" greeting call, matching
# the OpenAI SDK's 600s DEFAULT timeout almost exactly. Without this, a hung free model
# doesn't just fail slowly — it blocks run_agent_free_cascade from ever reaching the next
# candidate or the final fallback for ten minutes, defeating the entire point of a
# cascade (fail fast, try the next thing). 20s is generous against the ~1-5s normal
# range every real successful call in this cascade has shown; still two orders of
# magnitude short of the SDK default.
@lru_cache
def get_openrouter_client() -> OpenAI:
    return OpenAI(api_key=settings.openrouter_api_key, base_url="https://openrouter.ai/api/v1", timeout=20.0)


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


def run_agent_stream(
    system_prompt: str,
    user_message: str,
    output_model: type[T],
    prompt_version: str,
    model: str = "gpt-4o",
    temperature: float = 0.0,
    on_partial: Callable[[dict], None] | None = None,
) -> AgentResult:
    """Same contract and return type as run_agent — the FINAL AgentResult.output is
    still the fully schema-validated output_model, nothing about the verification chain
    downstream changes. The only difference: on_partial(dict) is called as the response
    streams in, with the SDK's best-effort partial parse of the JSON so far (a plain
    dict, not a validated output_model instance — a field only appears in it once that
    field's own value is syntactically complete, so a caller watching one field never
    sees a half-written string, only a jump from absent to whole; see the SDK's jiter-
    based partial-JSON accumulation, openai.lib.streaming.chat).

    Streaming is a presentation concern, not a verification one: nothing about
    on_partial's output should ever be treated as checked or final by a caller — it
    exists only so a caller (pipeline.py) can show a live draft while the real,
    citation-verified answer is still being built the exact same way it always was."""
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

    def _stream_once() -> AgentResult:
        last = None
        with client.beta.chat.completions.stream(**kwargs) as stream:
            for event in stream:
                if event.type == "content.delta" and on_partial is not None and event.parsed != last:
                    last = event.parsed
                    on_partial(event.parsed)
            final = stream.get_final_completion()
        parsed = final.choices[0].message.parsed
        if parsed is None:
            raise ValueError(f"Model returned no parsed output (refusal or parse failure): {final}")
        return AgentResult(output=parsed, model=model, prompt_version=prompt_version)

    try:
        return _stream_once()
    except openai.BadRequestError as exc:
        if "temperature" in kwargs and "temperature" in str(exc).lower():
            _TEMPERATURE_UNSUPPORTED_MODELS.add(model)
            kwargs.pop("temperature")
            return _stream_once()
        raise


def run_agent_free_cascade(
    system_prompt: str,
    user_message: str,
    output_model: type[T],
    prompt_version: str,
    free_models: list[str],
    fallback_model: str,
    temperature: float = 0.0,
) -> AgentResult:
    """Try each OpenRouter free model in `free_models`, in order, before falling back to
    `fallback_model` on the standard OpenAI path (run_agent). This is an AVAILABILITY
    mechanism, not a correctness one — real testing (docs/agents.md, greeter.py's module
    docstring) found free models fail in two different shapes: unavailable (rate-limited,
    malformed JSON, a network hiccup) and confidently wrong (a fabricated "research shows"
    claim, a paraphrased-not-verbatim quote). Cascading through more free models only ever
    helps with the first shape — trying a second free model after one is confidently wrong
    just risks a different wrong answer, not a more reliable one. Only pass free_models
    that have each been individually, separately verified safe for the SPECIFIC task this
    call is doing (not just "a free model that worked on some other agent's prompt") —
    this function does not and cannot verify that for you.

    Every model in the cascade, plus the final fallback, is tried at most once — no retry
    loop within a single model, since a malformed-JSON or rate-limit failure on one call is
    exactly the signal to move to the NEXT model, not to hammer the same one again."""
    client = get_openrouter_client()
    for model in free_models:
        try:
            completion = client.beta.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                response_format=output_model,
                temperature=temperature,
            )
            parsed = completion.choices[0].message.parsed
            if parsed is not None:
                return AgentResult(output=parsed, model=model, prompt_version=prompt_version)
        except Exception:
            # Broad on purpose — malformed JSON, rate limit, network hiccup, or a
            # provider-side routing quirk are all the same case here: move to the next
            # candidate rather than let any one of them break the call. The caller has no
            # way to distinguish these from the exception type alone across this many
            # different free-model providers, and doesn't need to — every one of them
            # means "try the next thing," including the final fallback.
            pass

    return run_agent(
        system_prompt=system_prompt,
        user_message=user_message,
        output_model=output_model,
        prompt_version=prompt_version,
        model=fallback_model,
        temperature=temperature,
    )
