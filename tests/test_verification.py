import json
import uuid
from pathlib import Path

import pytest
from app.db.models import Attestation
from app.ingestion.fixture_collector import FixtureCollector
from app.ingestion.pipeline import IngestionService
from app.resolution.matcher import ResolutionService
from app.verification.attest import AttestationSigner
from app.verification.evidence import EvidenceService
from app.verification.post_validate import post_validate_verdicts
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def pipeline_ready(db_session: AsyncSession) -> None:
    await IngestionService(db_session).ingest_collector(FixtureCollector())
    await ResolutionService(db_session).resolve_all()
    await db_session.commit()


@pytest.mark.asyncio
async def test_jws_roundtrip_verify(pipeline_ready, db_session: AsyncSession) -> None:
    from app.verification.pipeline import VerificationPipeline

    result = await VerificationPipeline(db_session).verify(
        "T2 in Faro €240,000, 40 days on market",
        persist=False,
    )
    signer = AttestationSigner()
    payload = signer.verify(result["jws"])
    assert payload["sub_claim"].startswith("T2 in Faro")
    assert payload["confidence"] == result["attestation"]["confidence"]


@pytest.mark.asyncio
async def test_jwks_validate_endpoint(client: AsyncClient, pipeline_ready, db_session: AsyncSession) -> None:
    from app.verification.pipeline import VerificationPipeline

    result = await VerificationPipeline(db_session).verify("T2 in Faro €240,000", persist=False)
    resp = await client.post("/v1/verify/jws/validate", json={"jws": result["jws"]})
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


@pytest.mark.asyncio
async def test_attestation_persisted(pipeline_ready, db_session: AsyncSession) -> None:
    from app.verification.pipeline import VerificationPipeline

    result = await VerificationPipeline(db_session).verify("T2 in Faro €240,000", persist=True)
    assert result["attestation_id"]

    row = await db_session.scalar(select(Attestation).where(Attestation.id == uuid.UUID(result["attestation_id"])))
    assert row is not None
    assert row.jws == result["jws"]
    assert row.claim == "T2 in Faro €240,000"


@pytest.mark.asyncio
async def test_post_validate_downgrades_missing_evidence() -> None:
    verdicts = [{"predicate": "price=1", "verdict": "CORROBORATED", "evidence": []}]
    out = post_validate_verdicts(verdicts)
    assert out[0]["verdict"] == "UNVERIFIABLE"


@pytest.mark.asyncio
async def test_evidence_resolution(pipeline_ready, db_session: AsyncSession) -> None:
    from app.db.models import Snapshot
    from sqlalchemy import select

    snap = await db_session.scalar(select(Snapshot).limit(1))
    assert snap
    ref = f"sha256:{snap.content_hash}"
    result = await EvidenceService(db_session).resolve(ref)
    assert result is not None
    assert result["content_hash"] == snap.content_hash


@pytest.mark.asyncio
async def test_evidence_api(client: AsyncClient, pipeline_ready, db_session: AsyncSession) -> None:
    from app.db.models import Snapshot
    from sqlalchemy import select

    snap = await db_session.scalar(select(Snapshot).limit(1))
    ref = f"sha256:{snap.content_hash}"
    resp = await client.get(
        f"/v1/evidence/{ref}",
        headers={"X-API-Key": "dev-key-change-me"},
    )
    assert resp.status_code == 200
    assert resp.json()["snapshot_id"] == snap.id


@pytest.mark.asyncio
async def test_delisted_claim_contradicted(pipeline_ready, db_session: AsyncSession) -> None:
    from app.verification.pipeline import VerificationPipeline

    result = await VerificationPipeline(db_session).verify(
        "T1 studio in Faro available for sale at €165,000",
        persist=False,
    )
    availability = next(
        (v for v in result["attestation"]["verdicts"] if v.get("predicate") == "availability"),
        None,
    )
    assert availability is not None
    assert availability["verdict"] == "CONTRADICTED"


@pytest.mark.asyncio
async def test_eval_harness_threshold(pipeline_ready, db_session: AsyncSession) -> None:
    from app.verification.pipeline import VerificationPipeline
    from evals.run_eval import _match_verdict

    claims = json.loads(Path("evals/labeled_claims.json").read_text())
    pipeline = VerificationPipeline(db_session)
    correct = 0
    for item in claims:
        if item["expected"] == "ANY":
            continue
        result = await pipeline.verify(item["claim"], persist=False)
        if _match_verdict(result, item["predicate"], item["expected"]):
            correct += 1
    scored = [c for c in claims if c["expected"] != "ANY"]
    accuracy = correct / len(scored)
    assert accuracy >= 0.70, f"Eval accuracy {accuracy:.1%} below 70% threshold"
