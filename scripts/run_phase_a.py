"""Thin entrypoint: run Phase A corpus assembly. See neurodiversity/ingestion/phase_a.py.

Usage: python scripts/run_phase_a.py
"""

from neurodiversity.ingestion.phase_a import run_phase_a

if __name__ == "__main__":
    run_phase_a(condition_clauses=[])  # TODO: pass the five clauses from working spec §5.1.1
