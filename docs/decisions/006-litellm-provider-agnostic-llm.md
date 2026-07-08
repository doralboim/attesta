# ADR-006: Provider-agnostic LLM via LiteLLM

**Status:** Accepted (2026-07-05)

**Context:** Verification parse/adjudicate steps must not be tied to a single LLM vendor. Prompts and model IDs must be fully configurable at runtime (env / file paths), not hardcoded in Python.

**Decision:** Use LiteLLM for all LLM calls. Model names (`LLM_PARSE_MODEL`, `LLM_ADJUDICATE_MODEL`, `LLM_EMBEDDING_MODEL`) and prompt file paths are required settings when `LLM_ENABLED=true`. Provider credentials follow LiteLLM conventions (e.g. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`). Regex/deterministic paths remain when LLM is disabled.

**Consequences:** No direct Anthropic SDK dependency. Prompt text lives only under `config/prompts/` (or paths overridden via env). Post-validation still downgrades verdicts without evidence hashes.
