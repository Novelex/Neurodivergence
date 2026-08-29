"""Gap-driven corpus growth. Working spec §5.8, run daily via pg_cron (§12).

Batches accumulated no_evidence turns' research_query values, runs the live source
search offline, feeds any papers found into phase_a.py — never inside the turn that hit
no_evidence. Daily is deliberate, not near-real-time; revisit only if real no_evidence
volume shows daily isn't keeping up.

TODO: implement run_gap_fill() -> None.
"""
