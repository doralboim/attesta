#!/usr/bin/env python3
"""End-to-end Faro apartment demo against local Attesta API."""

from __future__ import annotations

import argparse
import json
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--api-key", default="dev-key-change-me")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    headers = {"X-API-Key": args.api_key}

    print("1. Health check")
    health = httpx.get(f"{base}/healthz", timeout=10)
    health.raise_for_status()
    print(json.dumps(health.json(), indent=2))

    print("\n2. Search Faro listings")
    search = httpx.post(
        f"{base}/v1/listings/search",
        headers=headers,
        json={"city": "Faro", "max_price_eur": 300000, "limit": 5},
        timeout=30,
    )
    search.raise_for_status()
    listings = search.json()
    print(f"Found {listings['count']} listings")

    print("\n3. Verify claim")
    claim = "T2 apartment in Faro listed at €240,000, 40 days on market"
    verify = httpx.post(
        f"{base}/v1/verify",
        headers=headers,
        json={"claim": claim, "depth": "corpus"},
        timeout=30,
    )
    verify.raise_for_status()
    result = verify.json()
    print(f"Confidence: {result['attestation']['confidence']}")
    print(f"JWS (first 80 chars): {result['jws'][:80]}...")
    print(f"Attestation ID: {result.get('attestation_id')}")

    print("\n4. Validate JWS via API")
    validate = httpx.post(
        f"{base}/v1/verify/jws/validate",
        json={"jws": result["jws"]},
        timeout=10,
    )
    validate.raise_for_status()
    print(json.dumps(validate.json(), indent=2))

    if result["attestation"]["verdicts"]:
        ev = result["attestation"]["verdicts"][0].get("evidence", [])
        if ev:
            print(f"\n5. Resolve evidence {ev[0]}")
            ref = ev[0].replace("sha256:", "sha256:")
            evidence = httpx.get(
                f"{base}/v1/evidence/{ref}",
                headers=headers,
                timeout=10,
            )
            if evidence.status_code == 200:
                print(json.dumps(evidence.json(), indent=2))
            else:
                print(f"Evidence lookup: {evidence.status_code}")

    print("\nDemo complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
