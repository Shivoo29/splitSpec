"""Visible: default listing, pagination shape, single get."""
from __future__ import annotations


async def test_default_listing(client):
    r = await client.get("/events")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert [e["id"] for e in body["items"]] == [3, 1, 2]


async def test_first_page_is_sorted(client):
    page = await client.get("/events", params={"limit": 2, "offset": 0})
    assert page.status_code == 200
    assert [e["id"] for e in page.json()["items"]] == [3, 1]
    assert page.json()["total"] == 3


async def test_single_event_lookup(client):
    r = await client.get("/events/1")
    assert r.status_code == 200
    assert r.json()["title"] == "PyConf 2026"