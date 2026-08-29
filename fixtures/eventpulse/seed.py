"""Deterministic seed data: fixed ids, fixed timestamps, fixed tokens.

Idempotent: seeding an already-seeded database is a no-op.
"""
from __future__ import annotations

from datetime import datetime

from app import money
from app.models import Event, Payment, Registration, Ticket, User
from sqlalchemy.orm import Session

ALICE_TOKEN = "alice-token-0001"
BOB_TOKEN = "bob-token-0002"
CAROL_TOKEN = "carol-token-0003"
DANA_TOKEN = "dana-token-0004"


def dt(*parts) -> datetime:
    return datetime(*parts)


def seed(session: Session) -> None:
    if session.get(User, 1) is not None:
        return

    users = [
        User(id=1, name="Alice", email="alice@example.com", token=ALICE_TOKEN),
        User(id=2, name="Bob", email="bob@example.com", token=BOB_TOKEN),
        User(id=3, name="Carol", email="carol@example.com", token=CAROL_TOKEN),
        User(id=4, name="Dana", email="dana@example.com", token=DANA_TOKEN),
    ]
    events = [
        Event(
            id=1,
            title="PyConf 2026",
            description="Community Python conference",
            starts_at=dt(2026, 3, 10, 14, 0, 0),
            capacity=10,
            price=money.quantize("150.00", "USD"),
            currency="USD",
            created_by=1,
            created_at=dt(2025, 11, 1, 9, 0, 0),
        ),
        Event(
            id=2,
            title="Orchestra Night",
            description="Symphony in the park",
            starts_at=dt(2026, 4, 5, 19, 30, 0),
            capacity=3,
            price=money.quantize("1200", "JPY"),
            currency="JPY",
            created_by=2,
            created_at=dt(2025, 11, 2, 9, 0, 0),
        ),
        Event(
            id=3,
            title="Data Meetup",
            description=None,
            starts_at=dt(2026, 2, 1, 9, 30, 0),
            capacity=100,
            price=money.quantize("0.00", "USD"),
            currency="USD",
            created_by=1,
            created_at=dt(2025, 11, 3, 9, 0, 0),
        ),
    ]
    registrations = [
        Registration(
            id=1, user_id=1, event_id=1, status="confirmed", created_at=dt(2025, 12, 1, 8, 0, 0)
        ),
        Registration(
            id=2, user_id=2, event_id=1, status="cancelled", created_at=dt(2025, 12, 1, 9, 0, 0)
        ),
        Registration(
            id=3, user_id=1, event_id=3, status="confirmed", created_at=dt(2025, 12, 2, 8, 0, 0)
        ),
        Registration(
            id=4, user_id=3, event_id=3, status="confirmed", created_at=dt(2025, 12, 2, 9, 0, 0)
        ),
    ]
    tickets = [
        Ticket(
            id=1,
            registration_id=1,
            user_id=1,
            event_id=1,
            code="T0001-0001",
            created_at=dt(2025, 12, 1, 8, 0, 0),
        ),
        Ticket(
            id=2,
            registration_id=2,
            user_id=2,
            event_id=1,
            code="T0001-0002",
            created_at=dt(2025, 12, 1, 9, 0, 0),
        ),
        Ticket(
            id=3,
            registration_id=3,
            user_id=1,
            event_id=3,
            code="T0003-0001",
            created_at=dt(2025, 12, 2, 8, 0, 0),
        ),
        Ticket(
            id=4,
            registration_id=4,
            user_id=3,
            event_id=3,
            code="T0003-0003",
            created_at=dt(2025, 12, 2, 9, 0, 0),
        ),
    ]
    payments = [
        Payment(
            id=1,
            user_id=1,
            event_id=1,
            amount=money.quantize("150.00", "USD"),
            currency="USD",
            idempotency_key="pay-seed-0001",
            status="succeeded",
            created_at=dt(2025, 12, 1, 8, 5, 0),
        ),
        Payment(
            id=2,
            user_id=1,
            event_id=3,
            amount=money.quantize("0.00", "USD"),
            currency="USD",
            idempotency_key="pay-seed-0002",
            status="succeeded",
            created_at=dt(2025, 12, 2, 8, 5, 0),
        ),
    ]
    session.add_all(users + events + registrations + tickets + payments)
    session.commit()


if __name__ == "__main__":
    from app.db import Base, default_db_url, engine_from_url
    from sqlalchemy.orm import sessionmaker

    engine = engine_from_url(default_db_url())
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine, expire_on_commit=False)
    with sm() as session:
        seed(session)
    print(f"seeded {default_db_url()}")