"""Shared, connection-pooled HTTP client for NCBI E-utilities (pubmed.py, pmc.py).

A fresh `httpx.get(...)` call opens a brand-new TCP+TLS connection every time — real,
avoidable latency paid on every esearch/efetch/PMC-fetch call, including inside
live_search's per-paper concurrent loop where several of these fire close together. A
single persistent httpx.Client keeps a connection pool open to eutils.ncbi.nlm.nih.gov
and reuses it across calls — httpx.Client is documented thread-safe for concurrent
requests, so this is safe to share across the ThreadPoolExecutor workers in
query/live_search.py without any locking.
"""

from functools import lru_cache

import httpx


@lru_cache
def get_eutils_client() -> httpx.Client:
    return httpx.Client(timeout=60.0)
