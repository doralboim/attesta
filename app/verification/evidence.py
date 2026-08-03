"""Evidence hash generation and snapshot resolution."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Observation, Snapshot


def snapshot_hash_ref(content_hash: str) -> str:
    return f"sha256:{content_hash}"


def snapshot_id_ref(snapshot_id: int) -> str:
    return f"snap:{snapshot_id}"


def parse_evidence_ref(ref: str) -> tuple[str, str]:
    """Return (kind, value) where kind is 'content_hash' or 'snapshot_id'."""
    if ref.startswith("sha256:"):
        return "content_hash", ref.removeprefix("sha256:")
    snap_match = re.match(r"^(?:sha256:)?snap-?(\d+)$", ref)
    if snap_match:
        return "snapshot_id", snap_match.group(1)
    if ref.startswith("snap:"):
        return "snapshot_id", ref.removeprefix("snap:")
    return "opaque", ref


class EvidenceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve(self, evidence_ref: str) -> dict | None:
        kind, value = parse_evidence_ref(evidence_ref)

        if kind == "content_hash":
            snap = await self.session.scalar(select(Snapshot).where(Snapshot.content_hash == value).limit(1))
        elif kind == "snapshot_id":
            snap = await self.session.get(Snapshot, int(value))
        else:
            return None

        if not snap:
            return None

        obs = await self.session.scalar(select(Observation).where(Observation.snapshot_id == snap.id).limit(1))

        return {
            "ref": evidence_ref,
            "snapshot_id": snap.id,
            "source": snap.source,
            "url": snap.url,
            "fetched_at": snap.fetched_at.isoformat(),
            "content_hash": snap.content_hash,
            "storage_key": snap.storage_key,
            "observation": {
                "source_listing_id": obs.source_listing_id if obs else None,
                "price_eur": float(obs.price_eur) if obs and obs.price_eur else None,
                "status": obs.status if obs else None,
            }
            if obs
            else None,
        }
