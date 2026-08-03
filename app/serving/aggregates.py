"""Pure helpers for €/m² aggregation and comps filtering."""

from __future__ import annotations

from statistics import median

from app.resolution.staleness import price_per_m2

__all__ = [
    "price_per_m2",
    "percentile_sorted",
    "euro_m2_stats",
    "area_within_tolerance",
]


def percentile_sorted(sorted_vals: list[float], p: float) -> float | None:
    """Linear-interpolation percentile; ``sorted_vals`` must be sorted ascending."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    p = max(0.0, min(1.0, p))
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def euro_m2_stats(ppm2_values: list[float]) -> dict[str, float | None]:
    vals = sorted(v for v in ppm2_values if v is not None and v > 0)
    if not vals:
        return {
            "median_price_per_m2": None,
            "p25_price_per_m2": None,
            "p75_price_per_m2": None,
            "sample_size": 0,
        }
    return {
        "median_price_per_m2": round(float(median(vals)), 2),
        "p25_price_per_m2": round(float(percentile_sorted(vals, 0.25) or 0), 2),
        "p75_price_per_m2": round(float(percentile_sorted(vals, 0.75) or 0), 2),
        "sample_size": len(vals),
    }


def area_within_tolerance(
    area_m2: float,
    target_area_m2: float,
    tolerance_pct: float,
) -> bool:
    if target_area_m2 <= 0:
        return False
    band = target_area_m2 * (tolerance_pct / 100.0)
    return abs(area_m2 - target_area_m2) <= band
