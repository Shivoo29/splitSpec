"""EventPulse app factory: create_app(db_url) -> FastAPI."""
from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app.cache import Cache
from app.db import Base, default_db_url, engine_from_url
from app.routes import events, payments, registrations, tickets
from app.timeutil import Clock, SystemClock


def create_app(
    db_url: str | None = None,
    clock: Clock | None = None,
    cache: Cache | None = None,
) -> FastAPI:
    url = db_url or default_db_url()
    engine = engine_from_url(url)
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)

    app = FastAPI(title="EventPulse", version="1.0.0")
    app.state.engine = engine
    app.state.sessionmaker = sm
    app.state.clock = clock or SystemClock()
    app.state.cache = cache or Cache()

    for router in (events.router, registrations.router, tickets.router, payments.router):
        app.include_router(router)
    return app