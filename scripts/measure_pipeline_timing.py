"""Real per-stage timing baseline — run this before trusting any latency number in a
design doc. Every "[e]" estimate in the v2 latency doc is a guess with a plausible
mechanism behind it; this is what turns them into "[m]" measured numbers instead.

Usage:
    uv run python scripts/measure_pipeline_timing.py [--out results.json]

Runs a representative query per terminal state, captures pipeline.py's real per-stage
breakdown (via console_log's per-stage timestamps — see console_log.py's turn_start/
stage/turn_end), and writes raw + summary timing to a JSON file. Does not touch the
database beyond what handle_turn() already does (live search caches papers by pubmed_id
as always) and does not persist turns (this bypasses api/routes/sessions.py entirely).

Live PubMed/OpenAI calls are real network calls — a single query has been observed
taking anywhere from ~5s to 10+ minutes in this environment under network flakiness, so
running the full set can take a while. Each query is independent and safe to re-run.
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from neurodiversity import console_log as log
from neurodiversity.query.pipeline import handle_turn

# One (or more) representative query per terminal state this system actually produces
# (see docs/pipeline_diagram.png / the routing-map artifact for the full state list).
# "expected" is a label for the report, not an assertion — a query can legitimately land
# somewhere else (e.g. corpus coverage changing what "answerable" resolves to), and that
# mismatch is itself useful data, not a test failure.
QUERIES = [
    ("hi", "greeting"),
    ("hy", "greeting"),
    ("what's a good pizza recipe", "out_of_scope"),
    ("i lost my cat", "out_of_scope"),
    ("does it work", "needs_clarification"),
    ("do I have ADHD", "answerable_or_clarification"),
    ("i was bullied", "practical_support"),
    ("i am autistic and got bullied at work", "practical_support"),
    ("how i should behave in workspace", "practical_support"),
    ("i dont want to be here anymore", "distress"),
    ("my friend has been talking about not being here anymore", "distress"),
    ("what causes ADHD", "answerable"),
    ("does this sound like autism to you", "answerable"),
    ("effectiveness of a rare, narrow intervention for Tourette's tics in adults", "answerable_live_search"),
]


def run_one(raw_input: str, expected: str) -> dict:
    events: list[dict] = []
    with log.use_sink(events.append):
        started = time.monotonic()
        result = handle_turn(raw_input, "", [])
        wall_clock = time.monotonic() - started

    turn_end_event = next((e for e in events if e.get("type") == "turn_end"), None)
    stages = turn_end_event["stages"] if turn_end_event else []
    return {
        "query": raw_input,
        "expected": expected,
        "actual_terminal_state": result.terminal_state,
        "wall_clock_seconds": round(wall_clock, 2),
        "stage_breakdown": [
            {"name": name, "since_last_seconds": round(since_last, 2), "since_start_seconds": round(since_start, 2)}
            for name, since_last, since_start in stages
        ],
        # The actual answer, not just timing — so a slow number can be read alongside
        # what it actually produced, not judged in isolation.
        "answer": {
            "reflection": result.reflection,
            "message": result.message,
            "prose": result.prose,
            "citation_count": len(result.citations),
            "evidence": result.evidence,
            "resources": [r.get("name") for r in result.resources] if result.resources else [],
            "community_corroboration": result.community_corroboration,
            "clarification_options": result.clarification_options,
        },
    }


def summarize(runs: list[dict]) -> dict:
    by_state: dict[str, list[float]] = {}
    for r in runs:
        by_state.setdefault(r["actual_terminal_state"], []).append(r["wall_clock_seconds"])
    summary = {}
    for state, times in by_state.items():
        times_sorted = sorted(times)
        summary[state] = {
            "n": len(times),
            "mean": round(statistics.mean(times), 2),
            "p50": round(statistics.median(times_sorted), 2),
            "p95": round(times_sorted[min(len(times_sorted) - 1, int(len(times_sorted) * 0.95))], 2),
            "min": round(min(times), 2),
            "max": round(max(times), 2),
        }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="pipeline_timing_baseline.json")
    args = parser.parse_args()

    runs = []
    for raw_input, expected in QUERIES:
        print(f"\n>>> {raw_input!r} (expecting roughly: {expected})")
        try:
            runs.append(run_one(raw_input, expected))
        except Exception as exc:
            print(f"    !! failed: {exc}")
            runs.append({"query": raw_input, "expected": expected, "error": str(exc)})

    summary = summarize([r for r in runs if "error" not in r])
    out_path = Path(args.out)
    out_path.write_text(json.dumps({"runs": runs, "summary_by_terminal_state": summary}, indent=2))

    print("\n=== Summary by actual terminal state ===")
    for state, stats in summary.items():
        print(f"  {state}: n={stats['n']} mean={stats['mean']}s p50={stats['p50']}s p95={stats['p95']}s "
              f"min={stats['min']}s max={stats['max']}s")
    print(f"\nFull results written to {out_path.resolve()}")


if __name__ == "__main__":
    main()
