# LLM Provider Configuration (LiteLLM)

Attesta verification (`verify_claim`) uses **LiteLLM** — not Anthropic-only. Any [LiteLLM-supported provider](https://docs.litellm.ai/docs/providers) works via env vars.

## Enable in production

```bash
LLM_ENABLED=true
LLM_PARSE_MODEL=anthropic/claude-haiku-4-5      # or openai/gpt-4o-mini, gemini/gemini-2.0-flash, etc.
LLM_ADJUDICATE_MODEL=anthropic/claude-haiku-4-5
LLM_EMBEDDING_MODEL=openai/text-embedding-3-small  # optional; resolution uses local embeddings if unset
ANTHROPIC_API_KEY=sk-ant-...                       # only the key(s) for your chosen provider(s)
```

## Mix providers (supported)

Parse and adjudicate can use different models/providers:

```bash
LLM_PARSE_MODEL=openai/gpt-4o-mini
LLM_ADJUDICATE_MODEL=anthropic/claude-haiku-4-5
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

## Cost per verification (approximate)

| Provider | Model | Parse + adjudicate |
|----------|-------|-------------------|
| Anthropic | claude-haiku-4-5 | ~$0.001–0.003 |
| OpenAI | gpt-4o-mini | ~$0.001–0.002 |
| Google | gemini-2.0-flash | ~$0.0005–0.001 |
| Groq | llama-3.3-70b | ~$0.0002–0.001 |

When `LLM_ENABLED=false`, verification falls back to regex/deterministic parsing (works for demo corpus, lower precision on novel claims).

## Railway

Set `LLM_ENABLED=true` and provider keys in the **api** service variables. No code changes needed per provider — LiteLLM routes by model prefix (`openai/`, `anthropic/`, `gemini/`, `azure/`, etc.).
