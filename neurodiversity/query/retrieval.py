"""Hybrid retrieve. Working spec §7.3.

Vector half: pgvector cosine similarity via the match_chunks Postgres function
(supabase/query_functions.sql), over the query embedded by the same OpenAI embedding
model used at ingestion (§5.7) — the one external API call the query path makes.

Full-text half (papers.tsv, title/abstract) is not yet combined in here — chunks has no
tsvector column of its own in schema.sql, so full chunk-level keyword search is a
follow-up, not part of this small-scale proof. One pass, no query expansion (§2.5),
either way.
"""

from dataclasses import dataclass

from neurodiversity.db.client import get_service_client
from neurodiversity.ingestion.embeddings import embed_chunk


@dataclass
class RetrievedChunk:
    chunk_id: str
    paper_id: str
    text: str
    section: str | None
    similarity: float


MAX_CHUNKS_PER_PAPER = 4
# Raw top-K by cosine similarity alone lets one long, verbose paper fill the whole
# window, starving the query of the paper diversity a synthesis answer actually needs
# (the writer then has too few sources to draw on and pads a claim with uncited
# specifics instead of citing another paper for it). Over-fetch, then cap per paper.
_OVERFETCH_FACTOR = 4


def retrieve(research_query: str, match_count: int = 20) -> list[RetrievedChunk]:
    query_embedding = embed_chunk(research_query)
    db = get_service_client()
    resp = db.rpc(
        "match_chunks",
        {"query_embedding": query_embedding, "match_count": match_count * _OVERFETCH_FACTOR},
    ).execute()
    ranked = [
        RetrievedChunk(
            chunk_id=row["chunk_id"],
            paper_id=row["paper_id"],
            text=row["chunk_text"],
            section=row.get("section"),
            similarity=row["similarity"],
        )
        for row in resp.data
    ]

    per_paper_count: dict[str, int] = {}
    diversified = []
    for chunk in ranked:  # already ordered by similarity descending
        if per_paper_count.get(chunk.paper_id, 0) >= MAX_CHUNKS_PER_PAPER:
            continue
        diversified.append(chunk)
        per_paper_count[chunk.paper_id] = per_paper_count.get(chunk.paper_id, 0) + 1
        if len(diversified) >= match_count:
            break
    return diversified
