"""Phase A — cheap, eager, no LLM calls. Working spec §5.8.

Corpus assembly (sources/*) -> chunk by section -> embed (embeddings.py) -> write row.
A paper is retrievable the moment this finishes it. Runs on the whole corpus (the
per-condition-capped esearch, §5.1.1), on an ongoing schedule (new PubMed papers), and
fed by gap_fill.py's No-evidence-driven backlog — never inside a live query turn.

TODO: implement run_phase_a(condition_clauses: list[str]) -> None.
"""
