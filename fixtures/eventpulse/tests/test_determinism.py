"""Determinism: injectable clock and UTC-normalized, offset-carrying timestamps."""
from __future__ import annotations

FIXED = "2026-01-01T12:00:00+00:00"


async def test_created_at_uses_injected_clock(client, auth_headers, tokens):
    r = await client.post(
        "/events",
        headers=auth_headers(tokens["alice"]),
        json={
            "title": "Tz Workshop",
            "starts_at": "2026-05-01T10:00:00+02:00",
            "capacity": 5,
            "price": "10.00",
        },
    )
    assert r.status_code == 201
    assert r.json()["created_at"] == FIXED
    assert r.json()["starts_at"] == "2026-05-01T08:00:00+00:00"


async def test_registration_created_at_uses_injected_clock(client, auth_headers, tokens):
    r = await client.post(
        "/registrations", headers=auth_headers(tokens["dana"]), json={"event_id": 1}
    )
    assert r.status_code == 201
    assert r.json()["created_at"] == FIXED


async def test_payment_created_at_uses_injected_clock(client, auth_headers, tokens):
    headers = {**auth_headers(tokens["dana"]), "Idempotency-Key": "dana-k1"}
    r = await client.post("/payments", headers=headers, json={"event_id": 1})
    assert r.status_code == 201
    assert r.json()["created_at"] == FIXED


async def test_seeded_dates_are_stable_and_carry_offsets(client):
    r = await client.get("/events/1")
    assert r.status_code == 200
    assert r.json()["starts_at"] == "2026-03-10T14:00:00+00:00"
    assert r.json()["created_at"] == "2025-11-01T09:00:00+00:00"


async def test_event_list_is_deterministic(client):
    first = (await client.get("/events")).json()["items"]
    second = (await client.get("/events")).json()["items"]
    assert first == second