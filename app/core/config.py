from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    database_url: str = ""

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "vivae-cvs"

    # LLM — proveedor intercambiable
    llm_provider: Literal["openai", "gemini"] = "openai"

    openai_api_key: str = ""
    openai_llm_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    gemini_api_key: str = ""
    gemini_llm_model: str = "gemini-2.0-flash"
    gemini_embedding_model: str = "gemini-embedding-001"

    embedding_dims: int = 512

    # LangSmith
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "vivae-prod"
    ls_sample_rate: float = 0.1

    # App
    frontend_url: str = "http://localhost:3000"
    rate_limit_chat: str = "15/hour"


settings = Settings()
