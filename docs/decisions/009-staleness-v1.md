# ADR-009: Staleness score v1

**Status:** Accepted (2026-08-03)

**Context:** Architecture §5 lists staleness features beyond recency × source-count: cross-source disagreement and price vs region prior. Agents (and dogfood clients like Financial Manager) need component-level transparency to weight confidence.

**Decision:** Staleness v1 is a weighted sum of four components, each in `[0, 1]`:

```
staleness = clamp01(
  0.40 * f_recency(recency_days) +
  0.25 * f_sources(source_count) +
  0.25 * f_disagreement(cross_source_prices) +
  0.10 * f_prior(price_per_m2, region_median_m2)
)
```

| Component | Mapping |
|-----------|---------|
| `recency` | `min(1, days_since_last_seen / 90)` |
| `sources` | 1 source → 1.0; 2 → 0.4; 3+ → 0.2 |
| `disagreement` | `(max−min)/mean` of latest ask per source, scaled so 15% spread → 1.0; 0 when &lt;2 sources |
| `prior` | `|€/m² − region_median_€/m²| / median`, scaled so 40% deviation → 1.0; omitted when prior unavailable |

Components are persisted under `canonical_attrs.staleness_components` at resolve time and exposed on `get_property` / `check_listing_freshness` as `staleness_components`.

**Consequences:** Single-source listings remain penalized; large cross-portal price gaps spike staleness even when recently seen. Region prior is best-effort (needs ≥2 other active €/m² samples) and is optional in the response shape.
