"""Visible: a user can read their own ticket."""
from __future__ import annotations


async def test_owner_reads_own_ticket(client, auth_headers, tokens):
    r = await client.get("/tickets/1", headers=auth_headers(tokens["alice"]))
    assert r.status_code == 200
    assert r.json()["code"] == "T0001-0001"
    assert r.json()["user_id"] == 1


async def test_missing_ticket_is_404(client, auth_headers, tokens):
    r = await client.get("/tickets/999", headers=auth_headers(tokens["alice"]))
    assert r.status_code == 404


async def test_ticket_lookup_requires_auth(client):
    r = await client.get("/tickets/1")
    assert r.status_code == 401