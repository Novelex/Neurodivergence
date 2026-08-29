"""Agent 3 — Claim extractor. See docs/agents.md §3.

Ingest, per paper. Extracts findings with construct, measure/instrument, direction,
effect size, and a verbatim quote + location. The instrument matters more than the
finding — it's what makes the construct-drift check (§7.4) possible downstream.

TODO: implement extract_claims(results_section, discussion_section) -> list[Claim].
"""
