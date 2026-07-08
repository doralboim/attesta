"""Resolution worker — match observations to properties."""

import asyncio

import structlog

from app.db.session import async_session_factory
from app.resolution.matcher import ResolutionService

logger = structlog.get_logger()


async def run() -> None:
    async with async_session_factory() as session:
        linked = await ResolutionService(session).resolve_all()
        logger.info("resolve_worker_done", linked=linked)


def cli() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    cli()
