"""Listing embeddings for cross-portal resolution."""

from __future__ import annotations

import hashlib
import math

from app.config import get_settings
from app.ingestion.base import RawListing


def _deterministic_embedding(text: str, dims: int = 384) -> list[float]:
    """Test/local fallback when LLM_EMBEDDING_MODEL is not configured."""
    digest = hashlib.sha256(text.encode()).digest()
    values: list[float] = []
    while len(values) < dims:
        for byte in digest:
            values.append((byte / 255.0) * 2 - 1)
            if len(values) >= dims:
                break
        digest = hashlib.sha256(digest).digest()
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def listing_embedding_text(listing: RawListing) -> str:
    attrs = listing.attrs
    return " | ".join(
        [
            listing.source,
            attrs.get("city", ""),
            attrs.get("typology", ""),
            str(attrs.get("area_m2", "")),
            str(listing.geo_lat or ""),
            str(listing.geo_lon or ""),
            attrs.get("title", ""),
        ]
    )


async def embed_listing(listing: RawListing) -> list[float] | None:
    settings = get_settings()
    text = listing_embedding_text(listing)
    if settings.llm_embedding_model:
        from app.llm.client import LlmClient

        client = LlmClient(
            parse_model=settings.llm_parse_model or settings.llm_embedding_model,
            adjudicate_model=settings.llm_adjudicate_model or settings.llm_embedding_model,
            embedding_model=settings.llm_embedding_model,
            temperature=settings.llm_temperature,
            max_tokens_parse=settings.llm_max_tokens_parse,
            max_tokens_adjudicate=settings.llm_max_tokens_adjudicate,
        )
        return await client.embed(text)
    return _deterministic_embedding(text)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
