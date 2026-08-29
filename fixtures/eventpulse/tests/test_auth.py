"""Auth behavior: header-token resolution to current_user."""
from __future__ import annotations


async def test_missing_authorization_is_401(client):
    r = await client.post("/registrations", json={"event_id": 1})
    assert r.status_code == 401


async def test_malformed_header_is_401(client):
    r = await client.post(
        "/registrations", headers={"Authorization": "Token abc"}, json={"event_id": 1}
    )
    assert r.status_code == 401


async def test_blank_token_is_401(client, auth_headers):
    r = await client.post(
        "/registrations", headers=auth_headers(""), json={"event_id": 1}
    )
    assert r.status_code == 401


async def test_unknown_token_is_401(client, auth_headers):
    r = await client.post(
        "/registrations", headers=auth_headers("does-not-exist"), json={"event_id": 1}
    )
    assert r.status_code == 401


async def test_valid_token_allows_write(client, auth_headers, tokens):
    r = await client.post(
        "/events",
        headers=auth_headers(tokens["alice"]),
        json={
            "title": "Workshop",
            "starts_at": "2026-06-01T09:00:00Z",
            "capacity": 5,
            "price": "10.00",
            "currency": "USD",
        },
    )
    assert r.status_code == 201