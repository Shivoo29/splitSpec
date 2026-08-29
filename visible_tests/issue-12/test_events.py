"""Visible: the event list returns items and a total."""
from __future__ import annotations


async def test_list_returns_items(client):
    r = await client.get("/events")
    assert r.status_code == 200
    body = r.json()
    assert body["items"]
    assert body["limit"] == 10
    assert body["offset"] == 0


async def test_large_limit_reports_every_event(client):
    body = (await client.get("/events?limit=100")).json()
    assert body["total"] == len(body["items"])


async def test_get_single_event(client):
    r = await client.get("/events/1")
    assert r.status_code == 200
    assert r.json()["id"] == 1
