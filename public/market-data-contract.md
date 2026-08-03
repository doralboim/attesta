# Market data response contract (schema_version 1.0)

Versioned envelope for Attesta market observation tools: `get_market_stats`, `get_comps`.

## Envelope

```json
{
  "schema_version": "1.0",
  "as_of": "2026-08-03T12:00:00Z",
  "currency": "EUR",
  "coverage": {
    "market": "PT",
    "asset_type": "residential_ask",
    "region": "PT-08",
    "city": "Faro"
  },
  "limitations": [],
  "data": {}
}
```

| Field | Notes |
|-------|-------|
| `schema_version` | Semver-ish string; bump on breaking field changes |
| `as_of` | UTC ISO-8601 timestamp of the response |
| `currency` | Always `EUR` for PT residential ask |
| `coverage` | Market + filters that scoped the query |
| `limitations` | Machine-readable codes (may be empty) |
| `data` | Tool payload, or `null` when unsupported / empty |

## Limitation codes

| Code | Meaning |
|------|---------|
| `unsupported_market` | Geography outside Attesta coverage (HTTP **200**, `data: null`) |
| `empty_corpus` | No matching active listings |
| `no_area_for_price_per_m2` | Listings lack `area_m2`; €/m² fields null |
| `price_cut_rate_unavailable` | Not enough `price_events` for 30d cut rate |
| `sample_size_lt_5` | Comps / thin sample — treat €/m² signal cautiously |

## `GET/POST /v1/market/stats` → `get_market_stats`

**Filters:** `region`, `city?`, `typology?`, `min_area_m2?`, `max_area_m2?`

**`data` fields:**

- `median_price_eur`
- `median_price_per_m2`, `p25_price_per_m2`, `p75_price_per_m2` (listings with usable area only)
- `inventory_active`
- `stale_rate` (share with `staleness_score ≥ 0.6`)
- `median_days_on_market`
- `sample_size` (n used for €/m²)
- `price_cut_rate_30d` (optional)

## `POST /v1/comps` → `get_comps`

**Filters:** `region`, `city?`, `typology?`, `area_m2`, `area_tolerance_pct` (default 15), `geo_radius_m?`, `property_id?` (exclude self), `limit≤50`

**`data` fields:**

- `comps[]` — `property_id`, `price_eur`, `area_m2`, `price_per_m2`, `staleness_score`, `sources`, …
- `median_price_per_m2`, `sample_size`

## Staleness components

`get_property` and `check_listing_freshness` include:

```json
"staleness_components": {
  "recency": 0.1,
  "sources": 0.4,
  "disagreement": 0.0,
  "prior": 0.2
}
```

Formula: see `docs/decisions/009-staleness-v1.md`.

## Metering

All priced market endpoints pass through `MeteringService.authorize()` (ADR-003). No unmetered bypass.
