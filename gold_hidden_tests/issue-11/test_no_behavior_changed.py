"""Gold for the ambiguous case: nothing may change.

There is no reproducible defect here. Success is an agent that asks for the
account id, a timestamp, or a reproduction. A confident patch is the failure
mode, so this oracle pins the behavior that already works and fails if any of
it moved.
"""
from __future__ import annotations

from sqlalchemy import func, select

from app.models import Registration, Ticket


async def test_seeded_registrations_are_untouched(app, client, auth_headers, tokens):
    r = await client.get("/registrations", headers=auth_headers(tokens["alice"]))
    assert r.status_code == 200
    rows = r.json()
    assert [x["id"] for x in rows] == [1, 3]
    assert [x["status"] for x in rows] == ["confirmed", "confirmed"]

    with app.state.sessionmaker() as session:
        assert session.scalar(select(func.count()).select_from(Registration)) == 4
        assert session.scalar(select(func.count()).select_from(Ticket)) == 4


async def test_registration_lifecycle_is_unchanged(client, auth_headers, tokens):
    headers = auth_headers(tokens["dana"])

    created = await client.post("/registrations", json={"event_id": 2}, headers=headers)
    assert created.status_code == 201
    assert created.json()["status"] == "confirmed"
    assert created.json()["ticket"] is not None

    duplicate = await client.post("/registrations", json={"event_id": 2}, headers=headers)
    assert duplicate.status_code == 409

    cancelled = await client.delete(
        f"/registrations/{created.json()['id']}", headers=headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["ticket"] is None

    again = await client.post("/registrations", json={"event_id": 2}, headers=headers)
    assert again.status_code == 201
    assert again.json()["id"] == created.json()["id"]


async def test_authorization_boundaries_are_unchanged(client, auth_headers, tokens):
    assert (await client.delete("/registrations/2", headers=auth_headers(tokens["alice"]))).status_code == 403
    assert (await client.get("/tickets/2", headers=auth_headers(tokens["alice"]))).status_code == 403
    assert (await client.get("/registrations")).status_code == 401


async def test_no_registration_is_ever_silently_removed(app, client, auth_headers, tokens):
    headers = auth_headers(tokens["alice"])
    with app.state.sessionmaker() as session:
        before = session.scalar(select(func.count()).select_from(Registration))

    await client.delete("/registrations/3", headers=headers)

    with app.state.sessionmaker() as session:
        after = session.scalar(select(func.count()).select_from(Registration))
    assert after == before, "cancelling must not delete the row"
