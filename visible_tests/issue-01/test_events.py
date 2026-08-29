"""Visible: create an event successfully and read it back."""
from __future__ import annotations


def _payload() -> dict:
    return {
        "title": "Nightly Build",
        "starts_at": "2026-06-01T09:00:00Z",
        "capacity": 10,
        "price": "25.00",
        "currency": "USD",
    }


async def test_valid_event_is_created(client, auth_headers, tokens):
    r = await client.post("/events", headers=auth_headers(tokens["alice"]), json=_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Nightly Build"
    assert body["capacity"] == 10
    assert body["price"] == "25.00"
    assert body["currency"] == "USD"
    assert body["created_by"] == 1


async def test_created_event_is_listed(client, auth_headers, tokens):
    await client.post("/events", headers=auth_headers(tokens["alice"]), json=_payload())
    listing = (await client.get("/events")).json()
    titles = [e["title"] for e in listing["items"]]
    assert "Nightly Build" in titles
    assert listing["total"] == 4


async def test_created_event_can_be_read(client, auth_headers, tokens):
    r = await client.post("/events", headers=auth_headers(tokens["alice"]), json=_payload())
    event_id = r.json()["id"]
    got = await client.get(f"/events/{event_id}")
    assert got.status_code == 200
    assert got.json()["title"] == "Nightly Build"


async def test_create_requires_auth(client):
    r = await client.post("/events", json=_payload())
    assert r.status_code == 401