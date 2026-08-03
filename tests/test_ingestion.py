from pathlib import Path

import pytest
from app.db.models import Snapshot
from app.ingestion.fixture_collector import FixtureCollector
from app.ingestion.pipeline import IngestionService
from app.resolution.matcher import ResolutionService
from sqlalchemy import func, select


@pytest.mark.asyncio
async def test_fixture_ingestion_creates_snapshots(db_session) -> None:
    fixtures = Path(__file__).parent / "fixtures" / "idealista_pt_listings.json"
    collector = FixtureCollector(fixtures)
    service = IngestionService(db_session)
    stats = await service.ingest_collector(collector)

    assert stats["snapshots"] == 5
    assert stats["observations"] == 5

    snap_count = await db_session.scalar(select(func.count()).select_from(Snapshot))
    assert snap_count == 5


@pytest.mark.asyncio
async def test_second_run_detects_price_change(db_session) -> None:
    v1 = Path(__file__).parent / "fixtures" / "idealista_pt_listings.json"
    v2 = Path(__file__).parent / "fixtures" / "idealista_pt_listings_v2.json"

    service = IngestionService(db_session)
    await service.ingest_collector(FixtureCollector(v1))
    stats = await service.ingest_collector(FixtureCollector(v2))

    assert stats["price_changes"] >= 1
    snaps = await db_session.scalar(select(func.count()).select_from(Snapshot))
    assert snaps > 5


@pytest.mark.asyncio
async def test_resolution_merges_cross_portal_duplicates(db_session) -> None:
    fixtures = Path(__file__).parent / "fixtures" / "idealista_pt_listings.json"
    await IngestionService(db_session).ingest_collector(FixtureCollector(fixtures))
    linked = await ResolutionService(db_session).resolve_all()
    assert linked == 5

    from app.db.models import Property, PropertyObservation

    props = (await db_session.execute(select(Property))).scalars().all()
    # Faro T2 on two portals should merge to 4 properties total
    assert len(props) == 4

    faro_props = [p for p in props if p.canonical_attrs.get("city") == "Faro" and p.is_active]
    assert len(faro_props) == 1
    links = (
        (
            await db_session.execute(
                select(PropertyObservation).where(PropertyObservation.property_id == faro_props[0].id)
            )
        )
        .scalars()
        .all()
    )
    assert len(links) == 2


@pytest.mark.asyncio
async def test_pii_not_in_snapshot_payload(db_session, tmp_path) -> None:
    import json

    from app.ingestion.pii_strip import contains_pii, strip_pii_from_record

    fixtures = Path(__file__).parent / "fixtures" / "idealista_pt_listings.json"
    with fixtures.open() as f:
        raw = json.load(f)
    pii_record = raw[0]
    cleaned = strip_pii_from_record(pii_record)
    payload = json.dumps(cleaned)
    assert not contains_pii(payload)
    assert "João Silva" not in payload
