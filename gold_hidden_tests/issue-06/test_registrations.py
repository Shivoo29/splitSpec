"""Gold: cancellation is owner-only and a rejected cancel changes nothing."""
from __future__ import annotations

from sqlalchemy import select

from app.models import Registration


async def test_cancel_another_users_cancelled_registration_is_403(client, auth_headers, tokens):
    r = await client.delete("/registrations/2", headers=auth_headers(tokens["alice"]))
    assert r.status_code == 403


async def test_cancel_another_users_live_registration_is_403_and_unchanged(
    app, client, auth_headers, tokens
):
    dana = auth_headers(tokens["dana"])
    created = await client.post("/registrations", headers=dana, json={"event_id": 1})
    assert created.status_code == 201
    target_id = created.json()["id"]

    r = await client.delete(f"/registrations/{target_id}", headers=auth_headers(tokens["alice"]))
    assert r.status_code == 403

    mine = (await client.get("/registrations", headers=dana)).json()
    row = next(x for x in mine if x["id"] == target_id)
    assert row["status"] == "confirmed"

    with app.state.sessionmaker() as session:
        stored = session.scalar(select(Registration).where(Registration.id == target_id))
    assert stored is not None
    assert stored.user_id == 4
    assert stored.event_id == 1
    assert stored.status == "confirmed"