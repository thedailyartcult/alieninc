import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from panteon.core.database import Base, get_db
from panteon.main import app

BATTLE_REPORT = {
    "battlefield": "Taiwan Strait",
    "scenarios_run": 500,
    "red_wins": 81,
    "blue_wins": 419,
    "stalemates": 0,
    "decisive_battles": 480,
    "convergence_rate": 0.62,
    "avg_red_casualties": 50.8,
    "avg_blue_casualties": 24.3,
    "avg_duration_hours": 36.2,
    "duration_ms": 900,
    "seed": 42,
    "best_branch": {"winner": "blue", "score": 0.8, "key_event": "naval interdiction",
                    "duration_hours": 30.1, "red_casualties_pct": 48.0,
                    "blue_casualties_pct": 20.0,
                    "red_doctrine": "attrition", "blue_doctrine": "defensive"},
    "_battlefield": {"name": "Taiwan Strait", "terrain": "coastal",
                     "bounds": [118, 22, 124, 27]},
}


@pytest.fixture
def battle_report():
    return dict(BATTLE_REPORT)


@pytest.fixture(autouse=True)
async def war_db():
    """Point get_db at a throwaway in-memory SQLite with the sc_* tables."""
    engine = create_async_engine("sqlite+aiosqlite://")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    state = {"tables": False}

    async def ensure_tables():
        if not state["tables"]:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            state["tables"] = True

    async def _fake_db():
        await ensure_tables()
        async with session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_db] = _fake_db
    session_factory.ensure_tables = ensure_tables
    yield session_factory
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def db_session(war_db):
    await war_db.ensure_tables()
    async with war_db() as session:
        yield session
