"""Visible: event creation round-trips a UTC-normalized timestamp."""
from __future__ import annotations


async def test_utc_instant_round_trips(client, auth_headers, tokens):
    r = await client.post(
        "/events",
        headers=auth_headers(tokens["alice"]),
        json={
            "title": "Morning Standup",
            "starts_at": "2026-06-01T09:00:00Z",
            "capacity": 5,
            "price": "10.00",
        },
    )
    assert r.status_code == 201
    assert r.json()["starts_at"] == "2026-06-01T09:00:00+00:00"
    event_id = r.json()["id"]
    got = await client.get(f"/events/{event_id}")
    assert got.status_code == 200
    assert got.json()["starts_at"] == "2026-06-01T09:00:00+00:00"


async def test_naive_timestamp_is_stored_as_is(client, auth_headers, tokens):
    r = await client.post(
        "/events",
        headers=auth_headers(tokens["alice"]),
        json={
            "title": "Park Run",
            "starts_at": "2026-06-01T09:00:00",
            "capacity": 5,
            "price": "10.00",
        },
    )
    assert r.status_code == 201
    assert r.json()["starts_at"] == "2026-06-01T09:00:00+00:00"