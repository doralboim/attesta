"""All configuration via environment variables. Fail fast on missing required secrets."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = Field(
        default="postgresql+asyncpg://attesta:attesta@localhost:5432/attesta",
        description="Async SQLAlchemy URL",
    )
    public_base_url: str = "http://localhost:8000"
    issuer_url: str = "https://api.attesta.dev"

    # R2 / S3 snapshot store
    r2_endpoint: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "attesta-snapshots"
    snapshot_store_backend: Literal["r2", "local"] = "local"
    local_snapshot_dir: str = ".snapshots"

    # Optional live ingestion (Apify actors — not required; see ADR-008)
    apify_token: str = ""
    apify_idealista_actor_id: str = "dz_omar/idealista-scraper-api"
    apify_imovirtual_actor_id: str = "automation-lab/imovirtual-scraper"
    apify_idealista_search_urls: str = ""
    apify_imovirtual_search_urls: str = ""
    apify_max_results_per_run: int = 50

    # Stripe async push
    stripe_flush_interval_seconds: int = 60

    # LLM (provider-agnostic via LiteLLM — keys/models via env, see litellm docs)
    llm_enabled: bool = False
    llm_parse_model: str = ""
    llm_adjudicate_model: str = ""
    llm_embedding_model: str = ""
    llm_temperature: float = 0.0
    llm_max_tokens_parse: int = 1024
    llm_max_tokens_adjudicate: int = 2048
    llm_parse_system_prompt_path: str = ""
    llm_parse_user_prompt_path: str = ""
    llm_adjudicate_system_prompt_path: str = ""
    llm_adjudicate_user_prompt_path: str = ""

    # Ingestion / resolution tuning
    delist_miss_threshold: int = 2

    # Stripe
    stripe_secret_key: str = ""
    stripe_meter_event_name: str = "attesta_api_call"

    # x402
    x402_enabled: bool = False
    x402_evm_address: str = ""
    x402_facilitator_url: str = "https://x402.org/facilitator"
    x402_network: str = "eip155:84532"

    # JWS signing
    jws_private_key_pem: str = ""
    jws_kid: str = "attesta-v1"
    jws_retired_public_keys_json: str = ""

    # Guardrails defaults
    free_tier_monthly_calls: int = 200
    rate_limit_per_minute: int = 60
    daily_spend_cap_eur: float = 50.0

    # Internal ops API (optional even in production — endpoint 503s if unset)
    admin_api_token: str = ""

    # Dev bootstrap API key (hashed at runtime, never stored raw in DB from this)
    bootstrap_api_key: str = "dev-key-change-me"

    log_level: str = "INFO"

    @model_validator(mode="after")
    def validate_production(self) -> Settings:
        if self.environment == "production":
            missing = []
            if not self.database_url:
                missing.append("DATABASE_URL")
            if not self.jws_private_key_pem:
                missing.append("JWS_PRIVATE_KEY_PEM")
            if missing:
                msg = f"Missing required production config: {', '.join(missing)}"
                raise ValueError(msg)
        return self

    @property
    def is_test(self) -> bool:
        return self.environment == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
