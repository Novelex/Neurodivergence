"""Session and turn endpoints. Working spec §12.1.

POST /sessions/{id}/turns is the one that matters — submits raw_input, runs
query/pipeline.py, returns the discriminated-union TurnResponse, and persists the turn
(§8: "written to turns on every run, no exceptions").

Auth is not wired up yet (§6.1's Supabase Auth is a later increment) — sessions are
created anonymous (user_id null) using the service-role client, which bypasses RLS by
design (§6.1). That's fine for an anonymous/ephemeral session (§16 item 5's default is
opt-in anyway); it stops being fine the moment real per-user auth matters, which is a
separate, explicitly-flagged next step, not silently pretended away here.
"""

from fastapi import APIRouter, HTTPException

from neurodiversity.api.schemas import (
    AnsweredTurn,
    DistressTurn,
    NoEvidenceTurn,
    OutOfScopeTurn,
    RefusedTurn,
    SessionCreated,
    SessionDetail,
    SplitTurn,
    TurnRecord,
    TurnRequest,
    TurnResponse,
)
from neurodiversity.db.client import get_service_client
from neurodiversity.query.pipeline import handle_turn

router = APIRouter()

_TERMINAL_STATE_MODELS = {
    "answered": AnsweredTurn,
    "refused": RefusedTurn,
    "out_of_scope": OutOfScopeTurn,
    "no_evidence": NoEvidenceTurn,
    "split": SplitTurn,
    "distress": DistressTurn,
}


@router.post("/sessions", response_model=SessionCreated)
def create_session() -> SessionCreated:
    db = get_service_client()
    row = db.table("sessions").insert({}).execute().data[0]
    return SessionCreated(session_id=row["id"], created_at=row["created_at"])


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: str) -> SessionDetail:
    db = get_service_client()
    session_row = db.table("sessions").select("*").eq("id", session_id).execute().data
    if not session_row:
        raise HTTPException(status_code=404, detail="session not found")

    turns = db.table("turns").select("*").eq("session_id", session_id).order("created_at").execute().data
    return SessionDetail(
        session_id=session_row[0]["id"],
        created_at=session_row[0]["created_at"],
        turns=[
            TurnRecord(
                turn_id=t["id"],
                terminal_state=t["terminal_state"],
                research_query=t["research_query"],
                reflection=t["reflection"],
                answer_prose=t["answer_prose"],
                citations=t["citations"] or [],
                created_at=t["created_at"],
            )
            for t in turns
        ],
    )


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str) -> None:
    """User-initiated erasure — actually deletes, not a soft flag (§12.1)."""
    db = get_service_client()
    existing = db.table("sessions").select("id").eq("id", session_id).execute().data
    if not existing:
        raise HTTPException(status_code=404, detail="session not found")
    db.table("turns").delete().eq("session_id", session_id).execute()
    db.table("sessions").delete().eq("id", session_id).execute()


@router.get("/sessions/{session_id}/turns/{turn_id}", response_model=TurnRecord)
def get_turn(session_id: str, turn_id: str) -> TurnRecord:
    db = get_service_client()
    rows = (
        db.table("turns")
        .select("*")
        .eq("id", turn_id)
        .eq("session_id", session_id)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="turn not found")
    t = rows[0]
    return TurnRecord(
        turn_id=t["id"],
        terminal_state=t["terminal_state"],
        research_query=t["research_query"],
        reflection=t["reflection"],
        answer_prose=t["answer_prose"],
        citations=t["citations"] or [],
        created_at=t["created_at"],
    )


@router.post("/sessions/{session_id}/turns", response_model=TurnResponse)
def create_turn(session_id: str, body: TurnRequest) -> TurnResponse:
    db = get_service_client()
    if not db.table("sessions").select("id").eq("id", session_id).execute().data:
        raise HTTPException(status_code=404, detail="session not found")

    result = handle_turn(body.raw_input)
    model = _TERMINAL_STATE_MODELS[result.terminal_state]

    citations_json = [
        {
            "citation_number": c.citation_number,
            "supporting_quotes": [
                {"paper_id": q.paper_id, "quote": q.quote} for q in c.supporting_quotes
            ],
        }
        for c in result.citations
    ]

    # §8: written to turns on every run, no exceptions — every branch below hits this,
    # not just the answered one. raw_input intentionally not persisted here (§6, §7.2's
    # privacy boundary — the translator's research_query is what should be stored, and
    # only handle_turn's internals ever see raw_input at all).
    db.table("turns").insert(
        {
            "session_id": session_id,
            "research_query": result.debug.get("research_query") if result.debug else None,
            "reflection": result.reflection,
            "terminal_state": result.terminal_state,
            "answer_prose": result.prose,
            "citations": citations_json,
        }
    ).execute()

    if result.terminal_state == "answered":
        return model(
            reflection=result.reflection,
            prose=result.prose,
            citations=citations_json,
            evidence=result.evidence,
        )
    if result.terminal_state in ("no_evidence", "split"):
        return model(reflection=result.reflection)
    return model()
