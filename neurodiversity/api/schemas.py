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


class EvidenceGradeFactors(BaseModel):
    """The real, checkable facts evidence_grade was computed from — exposed so the grade
    is never a black box, the same reasoning that put independent_papers_cited and
    max_site_count here as counts rather than a hidden number."""

    independent_papers_cited: int
    strongest_design_type: str | None = None
    max_site_count: int | None = None
    avg_fields_absent_ratio: float | None = None


class EvidenceSummary(BaseModel):
    """Facts about the corpus behind this answer — never a probability (§2.3).

    A probability would need something checkable to calibrate against, and no
    replication-outcome data exists for this to be calibrated on (§2.3, appendix:
    "A confidence scorer" is explicitly ruled out, permanently). These are counts —
    facts about what was actually found and ranked, not a model's impression of how
    likely the answer is to be right.

    evidence_grade is a categorical rating (High/Moderate/Low/Very Low), computed by
    plain code from the factors above — not a probability, and not a model's guess. It's
    a simplified adaptation of the GRADE framework used in real evidence-based medicine
    (Cochrane, WHO), not a certified GRADE rating: real GRADE needs a trained reviewer's
    risk-of-bias judgment this system doesn't make. See query/evidence_grade.py.
    """

    independent_papers_cited: int
    max_site_count: int | None = None  # largest multi-site study among cited papers, if known
    evidence_grade: str | None = None
    evidence_grade_factors: EvidenceGradeFactors | None = None


class AnsweredTurn(BaseModel):
    terminal_state: Literal["answered"] = "answered"
    reflection: str
    prose: str
    citations: list[Citation]
    evidence: EvidenceSummary


class OutOfScopeTurn(BaseModel):
    """§8's original design had this carry only a static boundary message. Now carries a
    real, model-generated conversational reply instead (agents/general_chat.py) — an
    off-topic message gets a normal, helpful chatbot response, the way any other chatbot
    handles small talk, rather than a flat "that's not what I cover." The default below
    is only a fallback for the rare case nothing else populated it."""

    terminal_state: Literal["out_of_scope"] = "out_of_scope"
    message: str = (
        "This system answers questions connected to neurodivergent experiences and "
        "conditions — that doesn't look like one."
    )


class CommunityAccount(BaseModel):
    name: str
    url: str


class CommunityCorroboration(BaseModel):
    """Working spec §9.1's second axis: formal literature can be thin on a construct that
    is nonetheless well-documented by first-person community accounts. `sources` always
    comes from a static, hand-curated table (neurodiversity/community_accounts.py), never
    generated by a model — same principle as PracticalSupportTurn's resources and
    DistressTurn's crisis-line data."""

    summary: str
    sources: list[CommunityAccount]


class NoEvidenceTurn(BaseModel):
    terminal_state: Literal["no_evidence"] = "no_evidence"
    reflection: str | None = None
    message: str = "The literature doesn't have enough comparable evidence to answer this yet."
    community_corroboration: CommunityCorroboration | None = None


class SplitTurn(BaseModel):
    terminal_state: Literal["split"] = "split"
    reflection: str | None = None
    message: str = "This looks like two different questions using one term — splitting to answer both."


class DistressTurn(BaseModel):
    terminal_state: Literal["distress"] = "distress"
    resources: list[dict] = []
    followup_prompt: str = "Would you also like the question in your message answered?"


class PracticalResource(BaseModel):
    name: str
    description: str
    url: str


class PracticalSupportTurn(BaseModel):
    """A real, practical need connected to being autistic/ADHD/etc. — workplace rights,
    education accommodations, benefits. `resources` always comes from a static,
    hand-maintained table (neurodiversity/practical_resources.py), never generated by a
    model — same principle as DistressTurn's crisis resources: a hallucinated
    organization name or URL here is close to the same failure class as a hallucinated
    crisis line.

    A practical need isn't mutually exclusive with a real research question about the
    same thing — e.g. workplace discrimination/harassment experienced by autistic/ADHD
    people is genuinely studied, even though "what does the law say" itself isn't
    literature-answerable. pipeline.py runs the full research pipeline underneath every
    practical_support classification; when it finds real, citation-verified literature,
    `prose`/`citations`/`evidence` are populated alongside the resources — never a
    probability, same as AnsweredTurn's evidence. When no literature was found, those
    stay empty and only the resources show, exactly as before."""

    terminal_state: Literal["practical_support"] = "practical_support"
    message: str = (
        "Here are organizations that can help directly with this. A literature search "
        "was also run underneath and didn't surface a matching study this time — try "
        "asking the underlying question on its own and it may find something."
    )
    resources: list[PracticalResource] = []
    reflection: str | None = None
    prose: str | None = None
    citations: list[Citation] = []
    evidence: EvidenceSummary | None = None


class GreetingTurn(BaseModel):
    """A bare greeting with no question attached (scope_guard's own classification —
    folded in there rather than a plain-code keyword match, since a keyword list missed
    typo'd greetings like "hy" in real testing). `message` itself IS model-generated
    (agents/greeter.py) — unlike every other terminal state's static default text, a
    canned string here would read as robotic for something this conversational; there's
    no factual claim at stake for a hello, so this is the one place letting the model
    phrase freely is safe."""

    terminal_state: Literal["greeting"] = "greeting"
    message: str


class NeedsClarificationTurn(BaseModel):
    """The translator (agents/translator.py) judged the message genuinely too ambiguous
    to form any reasonable research_query, even with conversation context — not merely
    broad or informally phrased. Offers concrete candidate interpretations rather than
    guessing and translating anyway; the person's next message (their own wording, or one
    of these options verbatim) becomes the next turn's raw_input like any other message."""

    terminal_state: Literal["needs_clarification"] = "needs_clarification"
    clarifying_question: str
    options: list[str] = []


TurnResponse = Annotated[
    Union[
        AnsweredTurn, OutOfScopeTurn, NoEvidenceTurn, SplitTurn,
        DistressTurn, PracticalSupportTurn, GreetingTurn, NeedsClarificationTurn,
    ],
    Field(discriminator="terminal_state"),
]
