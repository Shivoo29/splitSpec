"""Gold: invalid event payloads are rejected without creating anything."""
from __future__ import annotations

BASE = {
    "title": "Gold Event",
    "starts_at": "2026-08-01T09:00:00Z",
    "capacity": 5,
    "price": "10.00",
    "currency": "USD",
}

INVALID = [
    {"title": ""},
    {"price": "-0.01"},
    {"price": "-10"},
    {"capacity": 0},
    {"capacity": 100_001},
]


async def test_invalid_payloads_are_422(client, auth_headers, tokens):
    headers = auth_headers(tokens["alice"])
    for broken in INVALID:
        payload = {**BASE, **broken}
        r = await client.post("/events", headers=headers, json=payload)
        assert r.status_code == 422, payload


async def test_rejected_events_leave_no_rows(client, auth_headers, tokens):
    headers = auth_headers(tokens["alice"])
    for broken in INVALID:
        await client.post("/events", headers=headers, json={**BASE, **broken})
    listing = (await client.get("/events")).json()
    assert listing["total"] == 3


async def test_valid_event_still_created(client, auth_headers, tokens):
    r = await client.post("/events", headers=auth_headers(tokens["alice"]), json=BASE)
    assert r.status_code == 201
    assert (await client.get("/events")).json()["total"] == 4