#!/usr/bin/env python3
"""Run verification eval harness over labeled claims."""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base
from app.ingestion.fixture_collector import FixtureCollector
from app.ingestion.pipeline import IngestionService
from app.resolution.matcher import ResolutionService
from app.verification.pipeline import VerificationPipeline

CLAIMS_PATH = Path(__file__).resolve().parent / "labeled_claims.json"


async def _prepare(session: AsyncSession) -> None:
    await IngestionService(session).ingest_collector(FixtureCollector())
    await ResolutionService(session).resolve_all()


def _match_verdict(result: dict, predicate: str, expected: str) -> bool:
    verdicts = result["attestation"]["verdicts"]
    target = next((v for v in verdicts if predicate in v.get("predicate", "") or v.get("predicate") == predicate), None)
    if not target and predicate == "entity_match":
        target = next((v for v in verdicts if v.get("predicate") == "entity_match"), None)
    if not target:
        return expected == "UNVERIFIABLE"
    actual = target.get("verdict", "UNVERIFIABLE")
    if expected == "ANY":
        return actual in {"CORROBORATED", "CONTRADICTED", "UNVERIFIABLE"}
    return actual == expected


async def run_eval(database_url: str) -> int:
    engine = create_async_engine(database_url, connect_args={"check_same_thread": False} if "sqlite" in database_url else {})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await _prepare(session)
        claims = json.loads(CLAIMS_PATH.read_text())
        pipeline = VerificationPipeline(session)

        correct = 0
        by_class: dict[str, list[bool]] = defaultdict(list)

        for item in claims:
            result = await pipeline.verify(item["claim"], persist=False)
            ok = _match_verdict(result, item["predicate"], item["expected"])
            by_class[item["expected"]].append(ok)
            correct += int(ok)

        total = len(claims)
        print(f"Eval: {correct}/{total} ({100*correct/total:.1f}%)")
        for label, results in sorted(by_class.items()):
            hits = sum(results)
            print(f"  {label}: {hits}/{len(results)}")

        await engine.dispose()
        return 0 if correct / total >= 0.75 else 1


def main() -> None:
    import os

    db = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./eval_attesta.db")
    sys.exit(asyncio.run(run_eval(db)))


if __name__ == "__main__":
    main()
