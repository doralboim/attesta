"""Staleness v1 — weighted recency, sources, disagreement, optional region prior.

See docs/decisions/009-staleness-v1.md.
"""

from __future__ import annotations

from typing import Any

# Weights sum to 1.0
W_RECENCY = 0.40
W_SOURCES = 0.25
W_DISAGREEMENT = 0.25
W_PRIOR = 0.10

RECENCY_HORIZON_DAYS = 90.0
DISAGREEMENT_FULL_SPREAD = 0.15  # 15% price spread → component 1.0
PRIOR_FULL_DEVIATION = 0.40  # 40% off region €/m² median → component 1.0


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def price_per_m2(price_eur: float | None, area_m2: Any) -> float | None:
    if price_eur is None or area_m2 is None:
        return None
    try:
        area = float(area_m2)
    except TypeError, ValueError:
        return None
    if area <= 0:
        return None
    return float(price_eur) / area


def f_recency(recency_days: float) -> float:
    return clamp01(recency_days / RECENCY_HORIZON_DAYS)


def f_sources(source_count: int) -> float:
    """Fewer corroborating sources → higher staleness / phantom risk."""
    if source_count <= 0:
        return 1.0
    if source_count == 1:
        return 1.0
    if source_count == 2:
        return 0.4
    return 0.2


def f_disagreement(prices: list[float]) -> float:
    """Cross-source ask-price spread as a fraction of the mean."""
    valid = [p for p in prices if p is not None and p > 0]
    if len(valid) < 2:
        return 0.0
    mean = sum(valid) / len(valid)
    if mean <= 0:
        return 0.0
    spread = (max(valid) - min(valid)) / mean
    return clamp01(spread / DISAGREEMENT_FULL_SPREAD)


def f_prior(price_per_m2: float | None, region_median_m2: float | None) -> float:
    """Optional: ask €/m² vs region median €/m²."""
    if price_per_m2 is None or region_median_m2 is None:
        return 0.0
    if price_per_m2 <= 0 or region_median_m2 <= 0:
        return 0.0
    ratio = abs(price_per_m2 - region_median_m2) / region_median_m2
    return clamp01(ratio / PRIOR_FULL_DEVIATION)


def compute_staleness(
    *,
    recency_days: float,
    source_count: int,
    source_prices: list[float] | None = None,
    price_per_m2: float | None = None,
    region_median_m2: float | None = None,
) -> tuple[float, dict[str, float]]:
    """Return (staleness_score, components).

    staleness = clamp01(
        w_recency * f(recency) +
        w_sources * f(sources) +
        w_disagreement * f(disagreement) +
        w_prior * f(prior)
    )
    """
    components: dict[str, float] = {
        "recency": round(f_recency(recency_days), 4),
        "sources": round(f_sources(source_count), 4),
        "disagreement": round(f_disagreement(source_prices or []), 4),
    }
    prior = f_prior(price_per_m2, region_median_m2)
    if price_per_m2 is not None and region_median_m2 is not None:
        components["prior"] = round(prior, 4)

    score = clamp01(
        W_RECENCY * components["recency"]
        + W_SOURCES * components["sources"]
        + W_DISAGREEMENT * components["disagreement"]
        + W_PRIOR * prior
    )
    return round(score, 4), components


def components_dict(components: dict[str, float]) -> dict[str, Any]:
    """Stable JSON shape for API responses."""
    out: dict[str, Any] = {
        "recency": components.get("recency", 0.0),
        "sources": components.get("sources", 0.0),
        "disagreement": components.get("disagreement", 0.0),
    }
    if "prior" in components:
        out["prior"] = components["prior"]
    return out
