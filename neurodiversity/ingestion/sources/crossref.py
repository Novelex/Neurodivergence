"""Crossref REST API — retraction status via Retraction Watch. Working spec §5.1.

One DOI lookup per paper. No key required; set User-Agent with CROSSREF_CONTACT_EMAIL
(docs/setup.md) for Crossref's "polite pool" — higher, more reliable rate limits.

TODO: implement check_retraction(doi: str) -> RetractionStatus.
"""
