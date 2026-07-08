"""Persist issued attestations to Postgres."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Attestation


def collect_evidence_hashes(verdicts: list[dict]) -> list[str]:
    seen: set[str] = set()
    hashes: list[str] = []
    for verdict in verdicts:
        for ref in verdict.get("evidence") or []:
            if ref not in seen:
                seen.add(ref)
                hashes.append(ref)
    return hashes


async def persist_attestation(
    session: AsyncSession,
    *,
    claim: str,
    payload: dict,
    jws: str,
    usage_event_id: int | None = None,
) -> Attestation:
    record = Attestation(
        issued_at=datetime.now(UTC),
        claim=claim,
        verdicts={"items": payload.get("verdicts", [])},
        confidence=float(payload.get("confidence", 0)),
        evidence_hashes=collect_evidence_hashes(payload.get("verdicts", [])),
        jws=jws,
        usage_event_id=usage_event_id,
    )
    session.add(record)
    await session.flush()
    await session.commit()
    return record
