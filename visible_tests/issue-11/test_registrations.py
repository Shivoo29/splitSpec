"""Visible: the ordinary registration paths, all of which already work."""
from __future__ import annotations


async def test_list_mine_returns_the_callers_registrations(client, auth_headers, tokens):
    r = await client.get("/registrations", headers=auth_headers(tokens["alice"]))
    assert r.status_code == 200
    assert [x["id"] for x in r.json()] == [1, 3]


async def test_register_then_read_back(client, auth_headers, tokens):
    headers = auth_headers(tokens["dana"])
    created = await client.post("/registrations", json={"event_id": 2}, headers=headers)
    assert created.status_code == 201

    mine = await client.get("/registrations", headers=headers)
    assert created.json()["id"] in [x["id"] for x in mine.json()]


async def test_cancel_keeps_the_row_visible(client, auth_headers, tokens):
    headers = auth_headers(tokens["alice"])
    assert (await client.delete("/registrations/3", headers=headers)).status_code == 200

    mine = await client.get("/registrations", headers=headers)
    row = next(x for x in mine.json() if x["id"] == 3)
    assert row["status"] == "cancelled"
