"""Visible: creating an event and reading it back."""
from __future__ import annotations

NEW = {
    "title": "Late Addition",
    "starts_at": "2026-09-01T18:00:00+00:00",
    "capacity": 40,
    "price": "25.00",
    "currency": "USD",
}


async def test_create_event_returns_201(client, auth_headers, tokens):
    r = await client.post("/events", headers=auth_headers(tokens["alice"]), json=NEW)
    assert r.status_code == 201
    assert r.json()["title"] == "Late Addition"


async def test_created_event_is_readable_by_id(client, auth_headers, tokens):
    created = await client.post("/events", headers=auth_headers(tokens["alice"]), json=NEW)
    event_id = created.json()["id"]

    r = await client.get(f"/events/{event_id}")
    assert r.status_code == 200
    assert r.json()["id"] == event_id


async def test_event_list_returns_items(client):
    r = await client.get("/events")
    assert r.status_code == 200
    assert len(r.json()["items"]) >= 1
