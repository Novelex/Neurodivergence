"""OpenAlex Works API — metadata gaps, OA status, and the citation graph. Working spec §5.1.

Citation graph: this covers the role Semantic Scholar was originally scoped for, dropped
after its API application was rejected. `referenced_works` on a work object gives
outgoing citations; `cited_by_api_url` gives incoming ones — papers citing a finding,
where replication attempts live and a direct ranking input unavailable from PubMed.

API key required for all requests (recent OpenAlex policy change) — free, no approval,
$1/day usage credit. Pass OPENALEX_API_KEY as a query param or header per OpenAlex's
current auth docs; also include mailto=<CROSSREF_CONTACT_EMAIL> for the polite-pool
treatment (same pattern as Crossref).

TODO: implement fill_metadata_gaps(doi_or_pmid: str) -> MetadataFill.
TODO: implement get_citing_works(openalex_id: str) -> list[CitingWork] (via cited_by_api_url).
TODO: implement get_referenced_works(openalex_id: str) -> list[str] (outgoing citation DOIs).
"""
