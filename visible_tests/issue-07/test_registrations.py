"""Visible: register for an event and verify basic behavior."""
from __future__ import annotations


async def test_register_creates_registration_and_ticket(client, auth_headers, tokens):
    r = await client.post(
        "/registrations", headers=auth_headers(tokens["dana"]), json={"event_id": 1}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "confirmed"
    assert body["user_id"] == 4
    assert body["event_id"] == 1
    assert body["event"]["title"] == "PyConf 2026"
    assert body["ticket"]["code"] == "T0001-0004"


async def test_duplicate_registration_returns_409(client, auth_headers, tokens):
    r = await client.post(
        "/registrations", headers=auth_headers(tokens["alice"]), json={"event_id": 1}
    )
    assert r.status_code == 409


async def test_register_unknown_event_is_404(client, auth_headers, tokens):
    r = await client.post(
        "/registrations", headers=auth_headers(tokens["dana"]), json={"event_id": 999}
    )
    assert r.status_code == 404


async def test_register_full_event_is_400(client, auth_headers, tokens):
    for who in ("alice", "bob", "carol"):
        r = await client.post(
            "/registrations", headers=auth_headers(tokens[who]), json={"event_id": 2}
        )
        assert r.status_code == 201, who
    r = await client.post(
        "/registrations", headers=auth_headers(tokens["dana"]), json={"event_id": 2}
    )
    assert r.status_code == 400


async def test_register_requires_auth(client):
    r = await client.post("/registrations", json={"event_id": 1})
    assert r.status_code == 401


async def test_cancel_own_registration(client, auth_headers, tokens):
    r = await client.delete("/registrations/3", headers=auth_headers(tokens["alice"]))
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


async def test_cancel_other_users_registration_is_403(client, auth_headers, tokens):
    r = await client.delete("/registrations/2", headers=auth_headers(tokens["alice"]))
    assert r.status_code == 403