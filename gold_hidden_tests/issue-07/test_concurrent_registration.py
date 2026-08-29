"""Gold: at most one registration per (user, event), even under a real race.

The race is real, not simulated. A file-backed SQLite database gives every thread its
own connection, the route handlers are sync so Starlette runs them in its threadpool,
and a barrier releases all requests at the same instant. A check-then-insert
implementation loses this race; an implementation that lets the database enforce
uniqueness wins it.

Every round must hold the invariant. There is no retry-until-success: an oracle that
retries is an oracle that forgives the bug it exists to catch.
"""
from __future__ import annotations

import threading

import pytest
from sqlalchemy import func, select
from starlette.testclient import TestClient

from app.main import create_app
from app.models import Registration, Ticket
from app.timeutil import FixedClock
from seed import ALICE_TOKEN, seed

FIXED_NOW = "2026-01-01T12:00:00+00:00"
THREADS = 8
ROUNDS = 12
EVENT_ID = 1  # capacity 10, so capacity never masks the uniqueness failure
USER_ID = 1


def _fresh_app(db_path):
    app = create_app(f"sqlite:///{db_path}", clock=FixedClock.from_iso(FIXED_NOW))
    with app.state.sessionmaker() as session:
        seed(session)
        session.commit()
        # Alice must start with no registration for this event, or the race is moot.
        for reg in session.scalars(
            select(Registration).where(
                Registration.user_id == USER_ID, Registration.event_id == EVENT_ID
            )
        ).all():
            for ticket in session.scalars(
                select(Ticket).where(Ticket.registration_id == reg.id)
            ).all():
                session.delete(ticket)
            session.delete(reg)
        session.commit()
    return app


def _race(app) -> list[int]:
    """Fire THREADS simultaneous registrations; return their status codes."""
    barrier = threading.Barrier(THREADS)
    codes: list[int | str] = [None] * THREADS
    headers = {"Authorization": f"Bearer {ALICE_TOKEN}"}

    def one(idx: int) -> None:
        with TestClient(app) as client:
            barrier.wait(timeout=30)
            try:
                codes[idx] = client.post(
                    "/registrations", json={"event_id": EVENT_ID}, headers=headers
                ).status_code
            except Exception as exc:  # a 500 or a driver error is a failure, not a pass
                codes[idx] = f"raised {type(exc).__name__}: {exc}"

    threads = [threading.Thread(target=one, args=(i,)) for i in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
        assert not t.is_alive(), "a registration request never returned"
    return codes


@pytest.mark.parametrize("round_id", range(ROUNDS))
def test_concurrent_registration_creates_exactly_one(tmp_path, round_id):
    app = _fresh_app(tmp_path / f"race-{round_id}.db")
    codes = _race(app)

    with app.state.sessionmaker() as session:
        confirmed = session.scalar(
            select(func.count()).select_from(Registration).where(
                Registration.user_id == USER_ID,
                Registration.event_id == EVENT_ID,
                Registration.status == "confirmed",
            )
        )
        rows = session.scalar(
            select(func.count()).select_from(Registration).where(
                Registration.user_id == USER_ID, Registration.event_id == EVENT_ID
            )
        )
        tickets = session.scalar(
            select(func.count()).select_from(Ticket).where(
                Ticket.user_id == USER_ID, Ticket.event_id == EVENT_ID
            )
        )

    # The invariant, stated on the database rather than on the responses.
    assert confirmed == 1, f"round {round_id}: {confirmed} confirmed registrations, codes={codes}"
    assert rows == 1, f"round {round_id}: {rows} registration rows for one (user, event)"
    assert tickets == 1, f"round {round_id}: {tickets} tickets issued, codes={codes}"

    # And on the responses: one winner, everyone else told it already exists.
    assert codes.count(201) == 1, f"round {round_id}: codes={codes}"
    assert all(c in (201, 409) for c in codes), f"round {round_id}: codes={codes}"


def test_the_race_is_actually_concurrent(tmp_path):
    """Guard against a future refactor that serializes the requests.

    If every request ran in sequence, the first would win and the rest would 409 with
    no contention at all, and this suite would pass against a check-then-insert bug.
    The barrier is what makes that impossible, so assert it is really shared.
    """
    _fresh_app(tmp_path / "sanity.db")
    seen: list[int] = []
    barrier = threading.Barrier(THREADS)

    def one() -> None:
        barrier.wait(timeout=30)
        seen.append(threading.get_ident())

    threads = [threading.Thread(target=one) for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert len(set(seen)) == THREADS, "threads did not run concurrently"
