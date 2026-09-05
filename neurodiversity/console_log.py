"""Colorful, human-readable flow logging for a running server.

Purely a terminal aid for watching a turn move through
scope_guard -> translator -> retrieve -> live_search -> rerank -> rank -> writer ->
citation_checker -> terminal_state while `uvicorn` is running. Never persisted, never
seen by any agent — safe to remove without changing any pipeline behavior.

use_sink lets the streaming endpoint (api/routes/sessions.py's /turns/stream) forward
these same events to the browser in real time, so the UI can show live progress instead
of a static spinner — every stage/sub/flag/etc. call below both prints to the terminal
(unchanged) and, if a sink is active for the current thread, forwards a small structured
event to it. No call site in pipeline.py/live_search.py/process_paper.py needs to know or
care whether anyone's listening.
"""

import threading
import time

from rich.console import Console

console = Console()
_sink = threading.local()
_timing = threading.local()  # per-thread so concurrent requests never mix up each other's clocks


def use_sink(callback):
    """Context manager: activate `callback(event: dict)` for the current thread only —
    each HTTP request handling a turn runs in its own thread, so this never leaks
    between concurrent requests without needing a request id passed through everywhere."""

    class _SinkContext:
        def __enter__(self):
            _sink.callback = callback
            return self

        def __exit__(self, *exc):
            _sink.callback = None

    return _SinkContext()


def _emit(event: dict) -> None:
    callback = getattr(_sink, "callback", None)
    if callback is not None:
        callback(event)

_STATE_STYLE = {
    "answered": "bold green",
    "refused": "bold red",
    "out_of_scope": "bold red",
    "no_evidence": "bold yellow",
    "split": "bold yellow",
    "distress": "bold magenta",
    "practical_support": "bold cyan",
    "greeting": "bold blue",
    "needs_clarification": "bold cyan",
}


def turn_start(raw_input: str) -> None:
    console.print()
    console.rule(f"[bold white on blue] NEW TURN [/]  [italic]{raw_input}[/italic]", style="blue")
    now = time.monotonic()
    _timing.turn_started = now
    _timing.last = now
    _timing.stages = []  # [(name, since_last_stage, since_turn_start), ...] — real numbers,
    # not the estimated [e] figures in the v2 latency doc. This is what turns those into
    # measured [m] ones: run real queries, read the per-stage breakdown turn_end prints.
    _emit({"type": "turn_start"})


def turn_end(state: str, elapsed: float) -> None:
    style = _STATE_STYLE.get(state, "bold white")
    console.rule(f"[{style}]{state.upper()}[/{style}]  ({elapsed:.1f}s)", style="blue")
    stages = list(getattr(_timing, "stages", []))
    # The gap between the LAST logged stage() and this call is otherwise invisible — an
    # agent call with no stage() logged right after it (greeter.greet(), writer.write(),
    # the citation-checker retry loop) silently vanishes into "the turn took N seconds"
    # with nothing in the breakdown to blame. Close that gap explicitly rather than let
    # the biggest cost in a turn be the one thing the breakdown doesn't show.
    last = getattr(_timing, "last", None)
    if last is not None:
        tail = time.monotonic() - last
        if tail > 0.01:
            stages.append(("(response)", tail, elapsed))
    if stages:
        breakdown = "  ".join(f"{name} +{since_last:.2f}s" for name, since_last, _ in stages)
        console.print(f"    [dim]{breakdown}[/dim]")
    _emit({"type": "turn_end", "state": state, "elapsed": elapsed, "stages": stages})


def stage(name: str, detail: str = "", style: str = "cyan") -> None:
    now = time.monotonic()
    started = getattr(_timing, "turn_started", now)
    last = getattr(_timing, "last", now)
    since_last = now - last
    since_start = now - started
    _timing.last = now
    if hasattr(_timing, "stages"):
        _timing.stages.append((name, since_last, since_start))

    line = f"[{style}]▸ {name}[/{style}]  [dim]({since_last:.2f}s, +{since_start:.2f}s total)[/dim]"
    if detail:
        line += f"  {detail}"
    console.print(line)
    _emit({"type": "stage", "name": name, "detail": detail, "since_last": since_last, "since_start": since_start})


def sub(text: str, style: str = "dim") -> None:
    console.print(f"    [{style}]{text}[/{style}]")
    _emit({"type": "sub", "text": text})


def flag(reason: str, sentence: str, quote: str) -> None:
    console.print(f"    [bold red]✗ FLAGGED[/bold red] [red]{reason}[/red]")
    console.print(f"      [dim]sentence:[/dim] {sentence[:200]!r}")
    console.print(f"      [dim]quote:[/dim]    {quote[:200]!r}")
    _emit({"type": "flag", "reason": reason})


def warn(text: str) -> None:
    console.print(f"    [yellow]⚠ {text}[/yellow]")
    _emit({"type": "warn", "text": text})


def success(text: str) -> None:
    console.print(f"    [green]✓ {text}[/green]")
    _emit({"type": "success", "text": text})


def draft(text: str) -> None:
    """A piece of the writer's answer becoming available WHILE it's still generating —
    never checked, never final. pipeline.py only calls this from writer.write()'s
    on_partial callback on the first attempt, and only for content that's already
    syntactically complete in the model's streamed output (see run_agent_stream's
    docstring) — this is a live draft preview, not a claim that citation_checker has
    verified it. The real, checked answer replaces this entirely once the turn
    finishes; nothing from here is ever the thing left on screen."""
    console.print(f"    [dim italic]✍ {text}[/dim italic]")
    _emit({"type": "draft", "text": text})
