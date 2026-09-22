"""Apify actor runner for live portal collectors."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

APIFY_BASE = "https://api.apify.com/v2"


def normalize_actor_id(actor_id: str) -> str:
    """Apify REST API expects ``username~actor-name``; Store uses ``username/actor-name``."""
    return actor_id.strip().replace("/", "~")


async def run_apify_actor(
    client: httpx.AsyncClient,
    token: str,
    actor_id: str,
    actor_input: dict[str, Any],
    *,
    poll_interval_secs: float = 5.0,
    max_wait_secs: float = 600.0,
) -> list[dict[str, Any]]:
    """Start an Apify actor run, wait for completion, return dataset items."""
    act = normalize_actor_id(actor_id)
    run_resp = await client.post(
        f"{APIFY_BASE}/acts/{act}/runs",
        params={"token": token},
        json=actor_input,
    )
    run_resp.raise_for_status()
    run_data = run_resp.json()["data"]
    run_id = run_data["id"]
    dataset_id = run_data["defaultDatasetId"]

    deadline = time.monotonic() + max_wait_secs
    status = run_data.get("status", "RUNNING")
    while status in ("RUNNING", "READY"):
        if time.monotonic() >= deadline:
            msg = f"Apify run {run_id} timed out after {max_wait_secs}s"
            raise TimeoutError(msg)
        await asyncio.sleep(poll_interval_secs)
        check = await client.get(
            f"{APIFY_BASE}/actor-runs/{run_id}",
            params={"token": token},
        )
        check.raise_for_status()
        status = check.json()["data"]["status"]

    if status != "SUCCEEDED":
        msg = f"Apify run {run_id} ended with status {status}"
        raise RuntimeError(msg)

    items_resp = await client.get(
        f"{APIFY_BASE}/datasets/{dataset_id}/items",
        params={"token": token, "format": "json"},
    )
    items_resp.raise_for_status()
    items = items_resp.json()
    logger.info("apify_run_complete", actor_id=actor_id, run_id=run_id, items=len(items))
    return items if isinstance(items, list) else []


# Backwards-compatible alias used by collectors before actor input was added.
async def poll_apify_dataset(
    client: httpx.AsyncClient,
    token: str,
    actor_id: str,
    actor_input: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return await run_apify_actor(client, token, actor_id, actor_input or {})
