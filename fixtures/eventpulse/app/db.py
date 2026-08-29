"""SQLAlchemy engine, declarative base, and request-scoped session access.

The database URL comes from EVENTPULSE_DB_URL unless a caller passes one to
create_app(). In-memory SQLite gets a StaticPool so every request in a process
shares the same in-memory database.
"""
from __future__ import annotations

import os
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def default_db_url() -> str:
    return os.environ.get("EVENTPULSE_DB_URL", "sqlite:///./eventpulse.db")


def engine_from_url(url: str | None) -> Engine:
    url = url or default_db_url()
    if not url.startswith("sqlite"):
        return create_engine(url)
    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if url == "sqlite://" or ":memory:" in url:
        kwargs["poolclass"] = StaticPool
    return create_engine(url, **kwargs)


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.sessionmaker() as session:
        yield session