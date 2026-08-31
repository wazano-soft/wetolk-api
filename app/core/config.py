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
    gemini_llm_model: str = "gemini-3.6-flash"
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
    public_api_url: str = "http://localhost:8000"
    visit_salt: str = "dev-only-salt-change-in-prod"
    # Orígenes CORS extra separados por coma, además de frontend_url --
    # solo para dev, cuando se prueba desde varias superficies a la vez
    # (localhost, IP LAN, túnel) sin tener que reiniciar el backend cada
    # vez que se cambia de una a otra. Vacío por default, no afecta prod.
    extra_cors_origins: str = ""

    # Stripe (RF-07 — donaciones)
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # Tipo de cambio USD->MXN. Los presets de donación se piensan en USD,
    # pero una cuenta Stripe de México solo liquida en MXN (no hay
    # multi-currency settlement para MX) y a tarjetas mexicanas solo se les
    # cobra en MXN, así que la Checkout Session se crea en pesos. El monto
    # se convierte con el FIX de Banxico (serie SF43718) al crear la sesión.
    banxico_token: str = ""
    # Fallback si Banxico no responde al crear la sesión -- pesos por dólar,
    # deliberadamente holgado para no quedar corto. Subir si el spot se aleja.
    usd_mxn_fallback_rate: float = 20.0
    # Colchón sobre la tasa FIX: cubre el movimiento intradía y el spread
    # que Stripe le aplica al donante extranjero vía Adaptive Pricing.
    fx_buffer: float = 1.00

    # Web Push (notificaciones) — VAPID autogenerado, sin proveedor externo.
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_subject: str = "mailto:soporte@wetolk.pro"


settings = Settings()
