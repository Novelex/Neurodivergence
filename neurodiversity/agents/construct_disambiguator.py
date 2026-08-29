"""Agent 7 — Construct disambiguator. See docs/agents.md §7.

Query path, conditional — only when the SQL join surfaces claims sharing a construct
name but different measure_ids. Decides comparable or not; a "not comparable" result
triggers the query path's only loop (§7.4), re-retrieving per branch, because the one
question was actually two.

TODO: implement is_comparable(claims: list[Claim]) -> bool.
"""
