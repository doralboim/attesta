"""Ingestion worker — defaults to fixtures; optional live collectors via --source."""

import argparse
import asyncio

import structlog

from app.db.session import async_session_factory
from app.ingestion.base import BaseCollector
from app.ingestion.fixture_collector import FixtureCollector
from app.ingestion.idealista_pt import IdealistaPtCollector
from app.ingestion.imovirtual import ImovirtualCollector
from app.ingestion.pipeline import IngestionService

logger = structlog.get_logger()


def _collector(source: str) -> BaseCollector:
    if source == "fixture":
        return FixtureCollector()
    if source == "idealista_pt":
        return IdealistaPtCollector()
    if source == "imovirtual":
        return ImovirtualCollector()
    msg = f"Unknown source: {source}"
    raise ValueError(msg)


async def run(source: str) -> None:
    collector = _collector(source)
    async with async_session_factory() as session:
        stats = await IngestionService(session).ingest_collector(collector)
        logger.info("ingest_worker_done", source=source, **stats)


def cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", action="store_true", help="Use bundled fixtures (alias for --source fixture)")
    parser.add_argument(
        "--source",
        choices=("fixture", "idealista_pt", "imovirtual"),
        default="fixture",
        help="Collector to run (default: fixture; live sources need APIFY_* env)",
    )
    args = parser.parse_args()
    source = "fixture" if args.fixture else args.source
    asyncio.run(run(source))


if __name__ == "__main__":
    cli()
