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

import json
import queue
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from neurodiversity import console_log
from neurodiversity.agents import summarizer
from neurodiversity.api.schemas import (
    AnsweredTurn,
    DistressTurn,
    GreetingTurn,
    NeedsClarificationTurn,
    NoEvidenceTurn,
    OutOfScopeTurn,
    PracticalSupportTurn,
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
    "out_of_scope": OutOfScopeTurn,
    "no_evidence": NoEvidenceTurn,
    "split": SplitTurn,
    "distress": DistressTurn,
    "practical_support": PracticalSupportTurn,
    "greeting": GreetingTurn,
    "needs_clarification": NeedsClarificationTurn,
}

# Short-term session memory (agents/summarizer.py). Exact window size — the last N
# research-bearing turns stay verbatim; anything older gets folded into
# sessions.context_summary one turn at a time as it ages out, keeping the fold itself
# cheap and infrequent rather than a per-turn cost.
MEMORY_WINDOW = 3


def _get_session_context(db, session_id: str, current_summary: str) -> tuple[str, list[tuple[str, str]]]:
    """Fetches this session's prior research-bearing turns, folds the oldest into the
    summary if the window would otherwise be exceeded, and returns (summary, recent)
    ready to pass into handle_turn. Only turns with a research_query count — a greeting
    or refusal never called the translator, so there's nothing to remember from it."""
    prior_turns = (
        db.table("turns")
        .select("research_query, reflection")
        .eq("session_id", session_id)
        .not_.is_("research_query", "null")
        .order("created_at")
        .execute()
        .data
    )
    summary = current_summary
    if len(prior_turns) >= MEMORY_WINDOW:
        aging_out = prior_turns[0]
        folded = summarizer.fold(summary, aging_out["research_query"], aging_out["reflection"])
        summary = folded.output.summary
        db.table("sessions").update({"context_summary": summary}).eq("id", session_id).execute()
        prior_turns = prior_turns[1:]
    recent = [(t["research_query"], t["reflection"]) for t in prior_turns]
    return summary, recent


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


def _persist_and_build_response(db, session_id: str, result):
    """Shared by both /turns and /turns/stream — persistence and response-shaping must
    stay identical between them, only how the caller learns about progress differs."""
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
    if result.terminal_state == "no_evidence":
        return model(reflection=result.reflection, community_corroboration=result.community_corroboration)
    if result.terminal_state == "split":
        return model(reflection=result.reflection)
    if result.terminal_state == "practical_support":
        kwargs = dict(resources=result.resources)
        if result.message:
            # pipeline.py sets this explicitly based on what actually happened underneath
            # (a real search ran and found nothing vs. the question was too vague to
            # search at all) — always more accurate than the schema's generic default.
            kwargs["message"] = result.message
        if result.prose:
            # A real, citation-verified answer was found underneath (pipeline.py's
            # _run_research) — overrides the no-match message above.
            kwargs["message"] = "Here's what the literature says, plus organizations that can help with the practical side."
            kwargs["reflection"] = result.reflection
            kwargs["prose"] = result.prose
            kwargs["citations"] = citations_json
            kwargs["evidence"] = result.evidence
        return model(**kwargs)
    if result.terminal_state in ("greeting", "out_of_scope"):
        return model(message=result.prose)
    if result.terminal_state == "needs_clarification":
        return model(clarifying_question=result.prose, options=result.clarification_options)
    if result.terminal_state == "distress":
        kwargs = dict(resources=result.resources)
        if result.message:
            kwargs["followup_prompt"] = result.message
        return model(**kwargs)
    return model()


@router.post("/sessions/{session_id}/turns", response_model=TurnResponse)
def create_turn(session_id: str, body: TurnRequest) -> TurnResponse:
    db = get_service_client()
    session_rows = db.table("sessions").select("id, context_summary").eq("id", session_id).execute().data
    if not session_rows:
        raise HTTPException(status_code=404, detail="session not found")

    context_summary, recent_turns = _get_session_context(db, session_id, session_rows[0]["context_summary"] or "")
    result = handle_turn(body.raw_input, context_summary, recent_turns)
    return _persist_and_build_response(db, session_id, result)


@router.post("/sessions/{session_id}/turns/stream")
def create_turn_stream(session_id: str, body: TurnRequest) -> StreamingResponse:
    """Same work as /turns, but streams each pipeline stage as a Server-Sent Event while
    the turn runs, instead of making the caller wait on one request for the full ~30-90s
    with no feedback. The final event always carries the exact same response shape
    /turns would have returned — this is a progress view onto the same result, not a
    different one."""
    db = get_service_client()
    session_rows = db.table("sessions").select("id, context_summary").eq("id", session_id).execute().data
    if not session_rows:
        raise HTTPException(status_code=404, detail="session not found")

    context_summary, recent_turns = _get_session_context(db, session_id, session_rows[0]["context_summary"] or "")

    event_queue: queue.Queue = queue.Queue()

    def run_pipeline():
        try:
            with console_log.use_sink(event_queue.put):
                result = handle_turn(body.raw_input, context_summary, recent_turns)
            response = _persist_and_build_response(db, session_id, result)
            event_queue.put({"type": "result", "data": response.model_dump(mode="json")})
        except Exception as exc:
            event_queue.put({"type": "error", "message": str(exc)})
        finally:
            event_queue.put(None)  # sentinel: stream is done

    threading.Thread(target=run_pipeline, daemon=True).start()

    def event_stream():
        while True:
            event = event_queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
