"""Claim text → checkable predicates (LLM when configured, regex fallback)."""

from __future__ import annotations

import re

from app.llm.factory import get_llm_client, get_llm_prompts, llm_is_configured


def parse_claim_regex(claim: str) -> dict:
    text = claim.lower()
    out: dict = {}

    price_match = re.search(r"€\s*([\d.,]+)", text) or re.search(r"([\d.,]+)\s*(?:eur|euro)", text)
    if price_match:
        raw = price_match.group(1).replace(".", "").replace(",", "")
        value = float(raw)
        if "k" in text[max(0, price_match.start() - 2) : price_match.end() + 2]:
            value *= 1000
        out["price"] = value
        out["price_min"] = value * 0.9
        out["price_max"] = value * 1.1

    dom_match = re.search(r"(\d+)\s+days?\s+on\s+(?:the\s+)?market", text)
    if dom_match:
        out["days_on_market"] = int(dom_match.group(1))

    for city in ("faro", "lisboa", "lisbon", "porto", "cascais", "athens", "thessaloniki"):
        if city in text:
            out["city"] = "Lisboa" if city == "lisbon" else city.title()
            break

    if any(w in text for w in ("listed", "available", "on market", "for sale")):
        out["availability"] = True

    typology_match = re.search(r"\b(t[0-5]|studio)\b", text)
    if typology_match:
        out["typology"] = typology_match.group(1).upper().replace("STUDIO", "T0")

    return out


async def parse_claim(claim: str) -> dict:
    if llm_is_configured():
        prompts = get_llm_prompts()
        client = get_llm_client()
        raw = await client.parse_claim(
            system=prompts.parse_system(),
            user=prompts.parse_user(claim=claim),
        )
        return _normalize_parsed(raw)
    return parse_claim_regex(claim)


def _normalize_parsed(raw: dict) -> dict:
    out: dict = {}
    if raw.get("price") is not None:
        price = float(raw["price"])
        out["price"] = price
        out["price_min"] = float(raw.get("price_min") or price * 0.9)
        out["price_max"] = float(raw.get("price_max") or price * 1.1)
    if raw.get("days_on_market") is not None:
        out["days_on_market"] = int(raw["days_on_market"])
    if raw.get("city"):
        out["city"] = str(raw["city"])
    if raw.get("typology"):
        out["typology"] = str(raw["typology"])
    if raw.get("region"):
        out["region"] = str(raw["region"])
    if raw.get("availability") is True:
        out["availability"] = True
    if raw.get("attributes") and isinstance(raw["attributes"], dict):
        out["attributes"] = raw["attributes"]
    return out
