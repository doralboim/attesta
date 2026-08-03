"""MCP tool descriptions — product copy for model tool-selection."""

SEARCH_LISTINGS = (
    "Search deduplicated residential property listings in Portugal. "
    "Coverage: PT residential, updated <6h when ingestion is active. "
    "Cost: €0.01 per call. "
    "Example: search_listings(region='PT-08', city='Faro', max_price_eur=300000, limit=10)"
)

GET_PROPERTY = (
    "Get canonical property record with sources, staleness score/components, and current price. "
    "Coverage: Portugal residential. Cost: €0.01 per call. "
    "Example: get_property(property_id='uuid-from-search')"
)

GET_PRICE_HISTORY = (
    "Get price_events timeline for a property including price cuts and delistings. "
    "Coverage: Portugal residential. Cost: €0.02 per call. "
    "Example: get_price_history(property_id='uuid-from-search')"
)

GET_MARKET_STATS = (
    "Aggregate market stats in a versioned envelope: median price € and €/m² (p25/p75), "
    "active inventory, stale_rate, median days on market, optional price_cut_rate_30d. "
    "Filters: region, city, typology, optional area_m2 band. "
    "Unsupported markets return data=null + limitations=['unsupported_market']. "
    "Coverage: Portugal residential ask. Cost: €0.02 per call. "
    "Example: get_market_stats(region='PT-08', city='Faro', typology='T2')"
)

GET_COMPS = (
    "Find comparable active listings by region/city/typology and area_m2 (±tolerance). "
    "Returns comps list, median_price_per_m2, sample_size in a versioned envelope. "
    "Flags limitations=['sample_size_lt_5'] when n<5. Optional property_id excludes self. "
    "Coverage: Portugal residential ask. Cost: €0.02 per call. "
    "Example: get_comps(region='PT-08', city='Faro', typology='T2', area_m2=80)"
)

CHECK_LISTING_FRESHNESS = (
    "Check if a property is fresh, stale, or likely phantom/delisted before recommending. "
    "Returns staleness_score plus staleness_components (recency, sources, disagreement, prior). "
    "Coverage: Portugal residential. Cost: €0.02 per call. "
    "Example: check_listing_freshness(property_id='uuid-from-search')"
)

VERIFY_CLAIM = (
    "Verify a natural-language property claim; returns per-predicate verdicts and signed JWS attestation. "
    "Depth corpus (€0.02) or deep with live fetch (€0.08). "
    "Example: verify_claim(claim='T2 in Faro €240k, 40 days on market', depth='corpus')"
)
