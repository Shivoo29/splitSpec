"""Visible: register, verify own cancellation, and see duplicates rejected."""
from __future__ import annotations


async def test_register_issues_ticket(client, auth_headers, tokens):
    r = await client.post(
        "/registrations", headers=auth_headers(tokens["dana"]), json={"event_id": 1}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "confirmed"
    assert body["ticket"]["code"] == "T0001-0004"


async def test_cancel_own_registration(client, auth_headers, tokens):
    r = await client.delete("/registrations/3", headers=auth_headers(tokens["alice"]))
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


async def test_cancel_missing_registration_is_404(client, auth_headers, tokens):
    r = await client.delete("/registrations/999", headers=auth_headers(tokens["alice"]))
    assert r.status_code == 404


async def test_duplicate_registration_is_rejected(client, auth_headers, tokens):
    r = await client.post(
        "/registrations", headers=auth_headers(tokens["alice"]), json={"event_id": 1}
    )
    assert r.status_code == 409


async def test_cancel_already_cancelled_own_is_400(client, auth_headers, tokens):
    r = await client.delete("/registrations/2", headers=auth_headers(tokens["bob"]))
    assert r.status_code == 400