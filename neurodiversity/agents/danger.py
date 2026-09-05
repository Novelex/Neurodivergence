"""Layer 1 — dedicated danger check. Runs on every turn, concurrently with scope_guard
(pipeline.py), not as one branch competing against four others inside it.

This is a direct fix for a real, documented bug: scope_guard.py's own module docstring
records gpt-4o-mini reliably misclassifying plain grief ("I lost my cat") as distress,
3/3, across two prompt rewrites — while gpt-4o got every case right with the identical
prompt. The fix that shipped at the time was pinning scope_guard to gpt-4o. The ACTUAL
root cause, on reflection, wasn't the model tier — it was that distress was one of five
competing categories a single classification call had to weigh against each other. A
model asked "is this distress, or practical_support, or greeting, or out_of_domain, or
answerable" has four ways to get it wrong before it even reaches the highest-stakes one.
This agent has exactly one job and one binary-ish question, with nothing else to weigh it
against — which is also why it's safe to keep on gpt-4o-mini rather than needing gpt-4o.

No Layer 0 lexical fast-path here, deliberately. A hand-rolled list of "unambiguous danger
phrases," written by an engineer without clinical/crisis-line review, is exactly the kind
of artifact that's both under-inclusive (misses real phrasing) and over-inclusive (fires
on things it shouldn't) in ways that are hard to catch without that review — the risk
profile is not the same as an ordinary keyword list. This module is Layer 1 only: a real
model call, every time, on every turn. A reviewed lexical layer is a legitimate future
addition (it would only ever ADD recall for the clearest cases, never replace this), but
it needs a domain-qualified reviewer before it ships, not an engineer's best guess at 2am.
"""

from enum import Enum

from pydantic import BaseModel

from neurodiversity.agents.base import MODEL_MINI, AgentResult, run_agent

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """You screen this message for one thing only: an affirmative signal of danger to a
person. You are NOT classifying topic, tone, or general emotional intensity — only whether a real
danger signal is present.

Return exactly one value:

"none"
    No indication of danger. This is the default. Sadness, grief, loss, frustration,
    exhaustion, or burnout — about anything, including a pet, a job, a relationship, or
    life in general — is "none" by itself, no matter how emotionally loaded the wording
    is, unless an actual danger signal (defined below) is also present. Examples that are
    "none": "I lost my cat", "I just lost my cat", "I lost my job and I'm devastated",
    "everything feels so hard right now", "I'm exhausted and don't know how much more I
    can take of this week" (venting/exhaustion, not danger), "this is killing me" (about
    workload — figurative), "I'm dying to know", "I could have died of embarrassment",
    "I'm dead tired" (all figurative, not danger).

"self"
    The person indicates they themselves may be at risk of ending their life or seriously
    harming themselves. Includes oblique signals, not just explicit statements:
    hopelessness stated with finality, describing themselves as a burden others would be
    better off without, saying goodbye, referencing arrangements made or giving away
    belongings, or flatly stating things will not get better and they are done. Examples
    that ARE "self": "I don't want to be here anymore", "I can't do this anymore, what's
    the point of going on", "I've been thinking about ending things", "everyone would be
    better off without me".

"other_person"
    The person indicates someone else is actively endangering THEM — violence, threats,
    or immediate physical danger from another person toward the person typing.

"third_party_concern"
    The person is worried about someone ELSE who may be at risk (per the "self" or
    "other_person" definitions above) — the danger signal is real, but the person typing
    is not the one at risk. E.g. "my friend has been talking about not being here
    anymore".

This is a bright-line, mechanical test, not a judgment call about how sad or serious a
message sounds. If no danger signal (as defined above) is present, the answer is "none" —
full stop, never a close call, and never rounded up "to be safe." When in doubt, the
absence of an explicit or strongly implied danger signal means "none": this system has a
separate path for practical needs and ordinary research questions, and treating an
ordinary hard feeling as a danger signal routes someone away from the question they
actually asked.

You may be given prior conversation context — a running summary and/or the last few
exchanges. Use it only to understand an ambiguous pronoun or reference ("I'm thinking
about doing it" following a prior turn about self-harm reads differently than the same
words following a turn about switching jobs) — never to manufacture a signal that isn't in
the current message at all."""


class DangerSignal(str, Enum):
    none = "none"
    self_risk = "self"
    other_person = "other_person"
    third_party_concern = "third_party_concern"


class DangerCheck(BaseModel):
    signal: DangerSignal


def check(raw_input: str, context_summary: str = "", recent_turns: list[tuple[str, str]] | None = None) -> AgentResult:
    """raw_input reaches this agent directly, same as scope_guard — this runs BEFORE the
    privacy-boundary point (translator), same as scope_guard already does. context_summary/
    recent_turns: same already-scrubbed shape used everywhere else in this system."""
    user_message = raw_input
    if context_summary or recent_turns:
        context_block = ""
        if context_summary:
            context_block += f"Summary of earlier conversation: {context_summary}\n\n"
        if recent_turns:
            context_block += "Recent exchanges:\n" + "\n".join(
                f"- {q}" + (f" ({r})" if r and r != q else "") for q, r in recent_turns
            ) + "\n\n"
        user_message = f"{context_block}New message: {raw_input}"

    return run_agent(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        output_model=DangerCheck,
        prompt_version=PROMPT_VERSION,
        model=MODEL_MINI,
        temperature=0.0,
    )
