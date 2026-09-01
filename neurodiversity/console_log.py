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

from rich.console import Console

console = Console()
_sink = threading.local()


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
}


def turn_start(raw_input: str) -> None:
    console.print()
    console.rule(f"[bold white on blue] NEW TURN [/]  [italic]{raw_input}[/italic]", style="blue")
    _emit({"type": "turn_start"})


def turn_end(state: str, elapsed: float) -> None:
    style = _STATE_STYLE.get(state, "bold white")
    console.rule(f"[{style}]{state.upper()}[/{style}]  ({elapsed:.1f}s)", style="blue")
    _emit({"type": "turn_end", "state": state, "elapsed": elapsed})


def stage(name: str, detail: str = "", style: str = "cyan") -> None:
    line = f"[{style}]▸ {name}[/{style}]"
    if detail:
        line += f"  {detail}"
    console.print(line)
    _emit({"type": "stage", "name": name, "detail": detail})


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
