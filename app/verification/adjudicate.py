"""Constrained LLM adjudication — evidence-only input, provider via LiteLLM."""

from __future__ import annotations

import json

from app.llm.factory import get_llm_client, get_llm_prompts, llm_is_configured


async def adjudicate_with_llm(
    claim: str,
    predicates: dict,
    evidence_bundle: dict,
) -> list[dict]:
    if not llm_is_configured():
        msg = "LLM adjudication requested but LLM is not configured"
        raise RuntimeError(msg)

    prompts = get_llm_prompts()
    client = get_llm_client()
    raw_verdicts = await client.adjudicate(
        system=prompts.adjudicate_system(),
        user=prompts.adjudicate_user(
            claim=claim,
            predicates_json=json.dumps(predicates, default=str),
            evidence_json=json.dumps(evidence_bundle, default=str),
        ),
    )
    return [_normalize_verdict(v) for v in raw_verdicts]


def _normalize_verdict(raw: dict) -> dict:
    verdict = {
        "predicate": str(raw.get("predicate", "unknown")),
        "verdict": str(raw.get("verdict", "UNVERIFIABLE")).upper(),
        "evidence": list(raw.get("evidence") or []),
    }
    if raw.get("sources") is not None:
        verdict["sources"] = int(raw["sources"])
    if raw.get("notes"):
        verdict["notes"] = str(raw["notes"])
    if verdict["verdict"] not in {"CORROBORATED", "CONTRADICTED", "UNVERIFIABLE"}:
        verdict["verdict"] = "UNVERIFIABLE"
    return verdict
