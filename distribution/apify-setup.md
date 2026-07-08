# Apify Setup for Live Ingestion

Attesta cannot create an Apify account on your behalf — signup requires your email, identity verification, and payment method at [apify.com](https://apify.com).

## Recommended actors (Portugal)

| Actor | Price | Notes |
|-------|-------|-------|
| [viralanalyzer/idealista-es-pt](https://apify.com/viralanalyzer/idealista-es-pt) | **$0.0025/listing** | PT + ES + IT, PPE, no charge on 0 results |
| [khadinakbar/idealista-scraper](https://apify.com/khadinakbar/idealista-scraper) | **$0.003/listing** | All 3 Idealista domains, DataDome bypass |
| [sourabhbgp/idealista-scraper](https://apify.com/sourabhbgp/idealista-scraper) | **$2/1,000 listings** | Includes market-data rows at $4/1k |

## Estimated monthly cost (Attesta Phase 0)

Assumption: ingest every **6 hours** across Faro + Lisbon metro (~2 regions), ~500 listings per run.

| Scale | Listings/month | Cost (viralanalyzer @ $0.0025) |
|-------|----------------|--------------------------------|
| Demo / MVP | ~6,000 (2 sources × 500 × 6/day × 30) | **~$15/mo** |
| Production PT | ~60,000 (broader regions) | **~$150/mo** |
| Full PT residential | ~300,000 | **~$750/mo** |

**Free tier:** Apify gives **$5/month** in platform credits — enough for ~2,000 listings to test before paying.

**Starter plan ($29/mo):** Includes prepaid platform usage; sourabhbgp estimates ~14,500 listings/month covered.

## Setup steps (you)

1. Create account at [console.apify.com](https://console.apify.com)
2. Copy API token → `APIFY_TOKEN` in Railway env
3. Pick an actor → set `APIFY_IDEALISTA_ACTOR_ID` (e.g. `viralanalyzer/idealista-es-pt`)
4. Optional: `APIFY_IMOVIRTUAL_ACTOR_ID` for second source
5. Schedule ingest worker: `attesta-ingest --source idealista_pt` every 4–6h

## Alternative to Apify

Build your own collector (`app/ingestion/base.py` subclass) or license a feed — fixtures remain the default for demo/playground until you configure Apify.
