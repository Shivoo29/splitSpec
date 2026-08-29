"""Shared fixtures: a fresh in-memory Database per test with seeded data."""
from __future__ import annotations

import httpx
import pytest
import pytest_asyncio

from app.main import create_app
from app.timeutil import FixedClock
from seed import ALICE_TOKEN, BOB_TOKEN, CAROL_TOKEN, DANA_TOKEN, seed

FIXED_NOW = "2026-01-01T12:00:00+00:00"


@pytest.fixture
def app():
    application = create_app("sqlite://", clock=FixedClock.from_iso(FIXED_NOW))
    with application.state.sessionmaker() as session:
        seed(session)
    return application


@pytest_asyncio.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def tokens():
    return {
        "alice": ALICE_TOKEN,
        "bob": BOB_TOKEN,
        "carol": CAROL_TOKEN,
        "dana": DANA_TOKEN,
    }


@pytest.fixture
def auth_headers():
    def _headers(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    return _headers