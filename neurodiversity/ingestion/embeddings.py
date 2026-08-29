"""OpenAI text-embedding-3-large, dims=768. Working spec §5.7.

768 dimensions requested via the API's dimensions parameter, matching chunks.embedding's
vector(768) column with no schema migration needed. This is Phase A — cheap, eager, no
LLM call, just this embedding call per chunk.
"""

from neurodiversity.agents.base import get_client


def embed_chunk(text: str) -> list[float]:
    client = get_client()
    resp = client.embeddings.create(
        model="text-embedding-3-large",
        input=text,
        dimensions=768,
    )
    return resp.data[0].embedding


def embed_chunks(texts: list[str]) -> list[list[float]]:
    """Batched version — one API call for many chunks, cheaper than one call each."""
    if not texts:
        return []
    client = get_client()
    resp = client.embeddings.create(
        model="text-embedding-3-large",
        input=texts,
        dimensions=768,
    )
    return [d.embedding for d in resp.data]
