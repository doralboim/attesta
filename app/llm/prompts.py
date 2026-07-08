"""Load prompt templates from configurable file paths — no inline prompt text."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


class PromptStore:
    """Resolves prompt files from env-configured paths only."""

    def __init__(
        self,
        *,
        parse_system_path: str,
        parse_user_path: str,
        adjudicate_system_path: str,
        adjudicate_user_path: str,
    ) -> None:
        self.parse_system_path = parse_system_path
        self.parse_user_path = parse_user_path
        self.adjudicate_system_path = adjudicate_system_path
        self.adjudicate_user_path = adjudicate_user_path

    @staticmethod
    def _read(path: str, label: str) -> str:
        if not path:
            msg = f"LLM prompt path for {label} is not configured"
            raise ValueError(msg)
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_file():
            msg = f"LLM prompt file not found for {label}: {resolved}"
            raise FileNotFoundError(msg)
        return resolved.read_text(encoding="utf-8").strip()

    def parse_system(self) -> str:
        return self._read(self.parse_system_path, "parse_system")

    def parse_user(self, **kwargs: str) -> str:
        template = self._read(self.parse_user_path, "parse_user")
        return template.format(**kwargs)

    def adjudicate_system(self) -> str:
        return self._read(self.adjudicate_system_path, "adjudicate_system")

    def adjudicate_user(self, **kwargs: str) -> str:
        template = self._read(self.adjudicate_user_path, "adjudicate_user")
        return template.format(**kwargs)


@lru_cache
def get_prompt_store(
    parse_system_path: str,
    parse_user_path: str,
    adjudicate_system_path: str,
    adjudicate_user_path: str,
) -> PromptStore:
    return PromptStore(
        parse_system_path=parse_system_path,
        parse_user_path=parse_user_path,
        adjudicate_system_path=adjudicate_system_path,
        adjudicate_user_path=adjudicate_user_path,
    )
