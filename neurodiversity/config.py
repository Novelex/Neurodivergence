"""Loads .env into one Settings object the whole app reads from.

See docs/setup.md for what each variable is and where to get it.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ncbi_api_key: str = ""
    openalex_api_key: str = ""
    semantic_api_key: str = ""
    crossref_contact_email: str = ""
    openai_api_key: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""


settings = Settings()
