"""Async LiteLLM wrapper — model names and API keys come from env only."""

from __future__ import annotations

import json
from typing import Any

import structlog

logger = structlog.get_logger()


class LlmClient:
    def __init__(
        self,
        *,
        parse_model: str,
        adjudicate_model: str,
        embedding_model: str,
        temperature: float,
        max_tokens_parse: int,
        max_tokens_adjudicate: int,
    ) -> None:
        self.parse_model = parse_model
        self.adjudicate_model = adjudicate_model
        self.embedding_model = embedding_model
        self.temperature = temperature
        self.max_tokens_parse = max_tokens_parse
        self.max_tokens_adjudicate = max_tokens_adjudicate

    async def complete_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
    ) -> dict[str, Any] | list[Any]:
        import litellm

        response = await litellm.acompletion(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            msg = "LLM returned empty content"
            raise ValueError(msg)
        parsed = json.loads(content)
        logger.info("llm_complete_json", model=model, keys=list(parsed.keys()) if isinstance(parsed, dict) else "list")
        return parsed

    async def parse_claim(self, *, system: str, user: str) -> dict[str, Any]:
        result = await self.complete_json(
            model=self.parse_model,
            system=system,
            user=user,
            max_tokens=self.max_tokens_parse,
        )
        if not isinstance(result, dict):
            msg = "parse_claim LLM response must be a JSON object"
            raise TypeError(msg)
        return result

    async def adjudicate(
        self,
        *,
        system: str,
        user: str,
    ) -> list[dict[str, Any]]:
        result = await self.complete_json(
            model=self.adjudicate_model,
            system=system,
            user=user,
            max_tokens=self.max_tokens_adjudicate,
        )
        if isinstance(result, dict) and "verdicts" in result:
            verdicts = result["verdicts"]
        elif isinstance(result, list):
            verdicts = result
        else:
            msg = "adjudicate LLM response must contain verdicts array"
            raise TypeError(msg)
        if not isinstance(verdicts, list):
            msg = "adjudicate verdicts must be a list"
            raise TypeError(msg)
        return verdicts

    async def embed(self, text: str) -> list[float]:
        if not self.embedding_model:
            msg = "LLM_EMBEDDING_MODEL is not configured"
            raise ValueError(msg)
        import litellm

        response = await litellm.aembedding(model=self.embedding_model, input=[text])
        vector = response.data[0]["embedding"]
        return [float(v) for v in vector]
