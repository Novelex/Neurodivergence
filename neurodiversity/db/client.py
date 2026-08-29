"""Supabase clients.

Two roles, never mixed (working spec §6.1, §12):
- anon client: the API layer's normal request path. RLS applies.
- service-role client: the ingestion worker pool only. Bypasses RLS by design.

The worker pool's row-claiming (SELECT ... FOR UPDATE SKIP LOCKED, §12) works fine on
the standard pooled connection as long as the claim and the status update happen in one
transaction — no separate direct/session-mode connection is needed (§6.1, corrected).
"""

from functools import lru_cache

from supabase import Client, create_client

from neurodiversity.config import settings


@lru_cache
def get_anon_client() -> Client:
    """For the FastAPI app's normal request path. RLS applies."""
    return create_client(settings.supabase_url, settings.supabase_anon_key)


@lru_cache
def get_service_client() -> Client:
    """For the ingestion worker pool only. Bypasses RLS by design (§6.1).

    Never expose this client to the API layer.
    """
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
