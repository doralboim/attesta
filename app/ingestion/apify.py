"""Optional Apify actor runner for live portal collectors.

Not required for local dev or CI — use ``attesta-ingest --fixture`` instead.
Configure ``APIFY_TOKEN`` and per-source actor IDs only when you have actors deployed.
"""

from __future__ import annotations

import httpx


async def poll_apify_dataset(client: httpx.AsyncClient, token: str, actor_id: str) -> list[dict]:
    run = await client.post(
        f"https://api.apify.com/v2/acts/{actor_id}/runs",
        params={"token": token},
        json={},
    )
    run.raise_for_status()
    run_id = run.json()["data"]["id"]
    dataset_id = run.json()["data"]["defaultDatasetId"]

    status = "RUNNING"
    while status == "RUNNING":
        check = await client.get(
            f"https://api.apify.com/v2/actor-runs/{run_id}",
            params={"token": token},
        )
        check.raise_for_status()
        status = check.json()["data"]["status"]
        if status == "FAILED":
            raise RuntimeError(f"Apify run {run_id} failed")

    items = await client.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items",
        params={"token": token},
    )
    items.raise_for_status()
    return items.json()
