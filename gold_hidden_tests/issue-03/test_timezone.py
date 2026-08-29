"""Gold: event times preserve the exact instant across timezone offsets."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.models import Event

CASES = [
    ("2026-05-01T10:00:00+02:00", "2026-05-01T08:00:00+00:00", datetime(2026, 5, 1, 8, 0, 0)),
    ("2026-03-29T11:00:00+01:00", "2026-03-29T10:00:00+00:00", datetime(2026, 3, 29, 10, 0, 0)),
    ("2026-03-29T12:00:00+02:00", "2026-03-29T10:00:00+00:00", datetime(2026, 3, 29, 10, 0, 0)),
    ("2026-05-01T09:00:00Z", "2026-05-01T09:00:00+00:00", datetime(2026, 5, 1, 9, 0, 0)),
]


async def test_event_instant_preserved_across_offsets(app, client, auth_headers, tokens):
    headers = auth_headers(tokens["alice"])
    for index, (incoming, expected_wire, expected_utc) in enumerate(CASES):
        r = await client.post(
            "/events",
            headers=headers,
            json={"title": f"TZ Event {index}", "starts_at": incoming, "capacity": 5, "price": "10.00"},
        )
        assert r.status_code == 201, incoming
        created = r.json()
        assert created["starts_at"] == expected_wire, incoming

        got = await client.get(f"/events/{created['id']}")
        assert got.json()["starts_at"] == expected_wire, "read-back must match create"

        with app.state.sessionmaker() as session:
            stored = session.scalar(select(Event).where(Event.id == created["id"]))
        assert stored is not None
        assert stored.starts_at == expected_utc, "stored instant must be UTC"