"""Agent 4 — Snippet verifier. See docs/agents.md §4.

Ingest, per claim. A differently-framed search task, not a repeat of the original
call — "locate the sentence supporting this claim, or state none exists." Disagreement
between the two framings routes to unchecked + human review (working spec §5.6).

TODO: implement verify(claim_under_verification, text_slice) -> str | None.
"""
