"""Thin entrypoint: run the daily gap-fill job. See neurodiversity/ingestion/gap_fill.py.

Intended to be triggered by pg_cron (working spec §12, docs/setup.md), not run manually
on a schedule of its own.

Usage: python scripts/run_gap_fill.py
"""

from neurodiversity.ingestion.gap_fill import run_gap_fill

if __name__ == "__main__":
    run_gap_fill()
