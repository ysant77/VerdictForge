from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from pathlib import Path

from legaldata.core.config import settings
from legaldata.storage.db import Base


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    # Ensure local directories exist (important for SQLite relative paths on Windows)
    settings.raw_store_dir.mkdir(parents=True, exist_ok=True)
    # Also ensure ./data exists for sqlite DB file if using ./data/legaldata.db
    Path("data").mkdir(parents=True, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("SELECT 1"))

