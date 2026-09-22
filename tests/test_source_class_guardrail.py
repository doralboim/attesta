import pytest
from app.ingestion.fixture_collector import FixtureCollector
from app.ingestion.pipeline import IngestionService
from app.resolution.matcher import ResolutionService
from app.verification.post_validate import post_validate_verdicts
from sqlalchemy.ext.asyncio import AsyncSession


def test_portal_price_stays_corroborated() -> None:
    out = post_validate_verdicts(
        [
            {
                "predicate": "price=240000",
                "verdict": "CORROBORATED",
                "evidence": ["sha256:abc"],
                "source_classes": ["portal"],
            }
        ]
    )
    assert out[0]["verdict"] == "CORROBORATED"


def test_cadastral_alone_downgrades_price() -> None:
    out = post_validate_verdicts(
        [
            {
                "predicate": "price=240000",
                "verdict": "CORROBORATED",
                "evidence": ["sha256:abc"],
                "source_classes": ["cadastral"],
            }
        ]
    )
    assert out[0]["verdict"] == "UNVERIFIABLE"
    assert "cadastral" in out[0]["notes"]


def test_cadastral_alone_keeps_geometry() -> None:
    out = post_validate_verdicts(
        [
            {
                "predicate": "location=faro",
                "verdict": "CORROBORATED",
                "evidence": ["sha256:abc"],
                "source_classes": ["cadastral"],
            }
        ]
    )
    assert out[0]["verdict"] == "CORROBORATED"


def test_mixed_portal_and_cadastral_keeps_price() -> None:
    out = post_validate_verdicts(
        [
            {
                "predicate": "price=1",
                "verdict": "CORROBORATED",
                "evidence": ["sha256:abc"],
                "source_classes": ["portal", "cadastral"],
            }
        ]
    )
    assert out[0]["verdict"] == "CORROBORATED"


@pytest.mark.asyncio
async def test_fixture_ingest_emits_portal_source_class(db_session: AsyncSession) -> None:
    from app.verification.pipeline import VerificationPipeline

    await IngestionService(db_session).ingest_collector(FixtureCollector())
    await ResolutionService(db_session).resolve_all()

    result = await VerificationPipeline(db_session).verify(
        "T2 in Faro €240,000, 40 days on market",
        persist=False,
    )
    payload = result["attestation"]
    assert payload["method"] == "attesta/verify@0.2"
    assert payload["source_classes"] == ["portal"]
    assert payload["llm_parse"] is False
    assert payload["llm_adjudicate"] is False
    for verdict in payload["verdicts"]:
        assert verdict["source_classes"] == ["portal"]
