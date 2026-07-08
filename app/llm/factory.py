"""Build LLM client and prompt store from application settings."""

from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.llm.client import LlmClient
from app.llm.prompts import PromptStore, get_prompt_store


def llm_is_configured(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return bool(
        cfg.llm_enabled
        and cfg.llm_parse_model
        and cfg.llm_adjudicate_model
        and cfg.llm_parse_system_prompt_path
        and cfg.llm_parse_user_prompt_path
        and cfg.llm_adjudicate_system_prompt_path
        and cfg.llm_adjudicate_user_prompt_path
    )


@lru_cache
def get_llm_client() -> LlmClient:
    settings = get_settings()
    if not llm_is_configured(settings):
        msg = "LLM is not fully configured — set LLM_ENABLED=true and all LLM_* env vars"
        raise RuntimeError(msg)
    return LlmClient(
        parse_model=settings.llm_parse_model,
        adjudicate_model=settings.llm_adjudicate_model,
        embedding_model=settings.llm_embedding_model,
        temperature=settings.llm_temperature,
        max_tokens_parse=settings.llm_max_tokens_parse,
        max_tokens_adjudicate=settings.llm_max_tokens_adjudicate,
    )


@lru_cache
def get_llm_prompts() -> PromptStore:
    settings = get_settings()
    return get_prompt_store(
        parse_system_path=settings.llm_parse_system_prompt_path,
        parse_user_path=settings.llm_parse_user_prompt_path,
        adjudicate_system_path=settings.llm_adjudicate_system_prompt_path,
        adjudicate_user_path=settings.llm_adjudicate_user_prompt_path,
    )
