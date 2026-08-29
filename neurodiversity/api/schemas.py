"""Discriminated-union response models. Working spec §12.1.

One Pydantic model per terminal_state value, discriminated on that field — not one loose
shape with a pile of optional fields. This is what makes an empty `answer` field
structurally impossible to render as a real response: there's no `answer` key on any
model except the `answered` one.
"""

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class TurnRequest(BaseModel):
    raw_input: str


class HealthResponse(BaseModel):
    """Never includes actual key values — presence booleans only. A health check that
    leaked secrets would be a worse problem than the one it's meant to catch."""

    status: Literal["ok"] = "ok"
    api_keys_configured: dict[str, bool]
    database_reachable: bool


class SessionCreated(BaseModel):
    """POST /sessions response. No auth wired up yet (§6.1's Supabase Auth is a later
    increment) — sessions are created anonymous (user_id null), matching the "ephemeral,
    opt-in" default already decided in §16 item 5."""

    session_id: str
    created_at: datetime


class TurnRecord(BaseModel):
    """One stored row from the turns table — GET /sessions/{id} and the single-turn lookup."""

    turn_id: str
    terminal_state: str
    research_query: str | None = None
    reflection: str | None = None
    answer_prose: str | None = None
    citations: list[dict] = []
    created_at: datetime


class SessionDetail(BaseModel):
    session_id: str
    created_at: datetime
    turns: list[TurnRecord]


class PaperQualityCheck(BaseModel):
    field_id: str
    status: str
    evidence_snippet: str | None = None
    location: str | None = None


class PaperDetail(BaseModel):
    """GET /papers/{id}. Working spec §7.3's "you show them the clause" — this is what
    makes that claim real: the actual verdicts and snippets a client can render."""

    paper_id: str
    title: str
    doi: str | None = None
    publication_year: int | None = None
    journal: str | None = None
    design_type: str | None = None
    license: str
    has_fulltext: bool
    quality_checks: list[PaperQualityCheck]


class SupportingQuote(BaseModel):
    paper_id: str
    quote: str


class Citation(BaseModel):
    """A sentence can genuinely draw on more than one paper — supporting_quotes carries
    one entry per source it cites, rather than forcing an artificial 1:1 sentence-to-
    quote mapping (agents/writer.py, agents/citation_checker.py)."""

    citation_number: int
    supporting_quotes: list[SupportingQuote]


class EvidenceSummary(BaseModel):
    """Facts about the corpus behind this answer — never a probability (§2.3).

    A probability would need something checkable to calibrate against, and no
    replication-outcome data exists for this to be calibrated on (§2.3, appendix:
    "A confidence scorer" is explicitly ruled out, permanently). These are counts —
    facts about what was actually found and ranked, not a model's impression of how
    likely the answer is to be right.
    """

    independent_papers_cited: int
    max_site_count: int | None = None  # largest multi-site study among cited papers, if known


class AnsweredTurn(BaseModel):
    terminal_state: Literal["answered"] = "answered"
    reflection: str
    prose: str
    citations: list[Citation]
    evidence: EvidenceSummary


class RefusedTurn(BaseModel):
    terminal_state: Literal["refused"] = "refused"
    message: str = (
        "This system answers questions about the research literature — it doesn't "
        "assess or diagnose. It can't tell you what you are, only what the evidence shows."
    )


class OutOfScopeTurn(BaseModel):
    terminal_state: Literal["out_of_scope"] = "out_of_scope"
    message: str = (
        "This system answers questions about neurodevelopmental research "
        "(autism, ADHD, dyslexia, dyspraxia, Tourette's) — that doesn't look like one."
    )


class NoEvidenceTurn(BaseModel):
    terminal_state: Literal["no_evidence"] = "no_evidence"
    reflection: str | None = None
    message: str = "The literature doesn't have enough comparable evidence to answer this yet."


class SplitTurn(BaseModel):
    terminal_state: Literal["split"] = "split"
    reflection: str | None = None
    message: str = "This looks like two different questions using one term — splitting to answer both."


class DistressTurn(BaseModel):
    terminal_state: Literal["distress"] = "distress"
    resources: list[dict] = []
    followup_prompt: str = "Would you also like the research question in your message answered?"


TurnResponse = Annotated[
    Union[AnsweredTurn, RefusedTurn, OutOfScopeTurn, NoEvidenceTurn, SplitTurn, DistressTurn],
    Field(discriminator="terminal_state"),
]
