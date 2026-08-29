"""Thin entrypoint: run a Phase B worker. See neurodiversity/ingestion/phase_b.py.

Usage: python scripts/run_phase_b_worker.py
Run several of these as separate processes for the worker pool (§12).
"""

from neurodiversity.ingestion.phase_b import run_worker

if __name__ == "__main__":
    run_worker(pool_size=1)
