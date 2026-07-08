"""Deterministic confidence scoring — documented formula."""

from __future__ import annotations

VERDICT_BASE_SCORES = {
    "CORROBORATED": 0.9,
    "CONTRADICTED": 0.85,
    "UNVERIFIABLE": 0.4,
}


def score_confidence(verdicts: list[dict]) -> float:
    """
    Mean of per-verdict base scores.
    CORROBORATED with 2+ evidence hashes gets +0.05 capped at 0.98.
    """
    if not verdicts:
        return 0.0

    total = 0.0
    for v in verdicts:
        base = VERDICT_BASE_SCORES.get(v.get("verdict", "UNVERIFIABLE"), 0.4)
        evidence = v.get("evidence") or []
        if v.get("verdict") == "CORROBORATED" and len(evidence) >= 2:
            base = min(0.98, base + 0.05)
        total += base

    return round(total / len(verdicts), 2)
