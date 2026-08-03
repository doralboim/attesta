"""Unit tests for staleness v1 components."""

from app.resolution.staleness import (
    compute_staleness,
    f_disagreement,
    f_prior,
    f_recency,
    f_sources,
)


def test_single_source_penalty() -> None:
    score_one, c_one = compute_staleness(recency_days=0, source_count=1, source_prices=[250000])
    score_two, c_two = compute_staleness(recency_days=0, source_count=2, source_prices=[250000, 252000])
    assert c_one["sources"] == 1.0
    assert c_two["sources"] == 0.4
    assert score_one > score_two


def test_disagreement_spike() -> None:
    low = f_disagreement([250000, 252000])
    high = f_disagreement([200000, 300000])
    assert high > low
    score_low, _ = compute_staleness(recency_days=5, source_count=2, source_prices=[250000, 252000])
    score_high, comps = compute_staleness(recency_days=5, source_count=2, source_prices=[200000, 300000])
    assert comps["disagreement"] > 0.5
    assert score_high > score_low


def test_recency_scales_to_horizon() -> None:
    assert f_recency(0) == 0.0
    assert f_recency(90) == 1.0
    assert f_recency(180) == 1.0


def test_prior_optional_component() -> None:
    score, comps = compute_staleness(
        recency_days=0,
        source_count=2,
        source_prices=[250000, 250000],
        price_per_m2=5000,
        region_median_m2=3000,
    )
    assert "prior" in comps
    assert comps["prior"] > 0
    assert 0 <= score <= 1

    _, comps_no = compute_staleness(recency_days=0, source_count=1)
    assert "prior" not in comps_no


def test_f_sources_and_prior_helpers() -> None:
    assert f_sources(0) == 1.0
    assert f_sources(3) == 0.2
    assert f_prior(None, 3000) == 0.0
    assert f_prior(3000, 3000) == 0.0
