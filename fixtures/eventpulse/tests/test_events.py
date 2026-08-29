"""Event endpoints: create, paginated list, single get."""
from __future__ import annotations


def _valid_event() -> dict:
    return {
        "title": "Workshop X",
        "starts_at": "2026-05-01T10:00:00+02:00",
        "capacity": 5,
        "price": "25.00",
        "currency": "USD",
    }


async def test_create_event_201_and_shape(client, auth_headers, tokens):
    r = await client.post("/events", headers=auth_headers(tokens["alice"]), json=_valid_event())
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Workshop X"
    assert body["capacity"] == 5
    assert body["price"] == "25.00"
    assert body["currency"] == "USD"
    assert body["created_by"] == 1
    assert body["starts_at"] == "2026-05-01T08:00:00+00:00"
    assert body["created_at"] == "2026-01-01T12:00:00+00:00"


async def test_create_event_rounds_money(client, auth_headers, tokens):
    payload = _valid_event()
    payload["price"] = "25.999"
    r = await client.post("/events", headers=auth_headers(tokens["alice"]), json=payload)
    assert r.status_code == 201
    assert r.json()["price"] == "26.00"


async def test_create_event_requires_auth(client):
    r = await client.post("/events", json=_valid_event())
    assert r.status_code == 401


async def test_create_event_invalid_bodies_are_422(client, auth_headers, tokens):
    base = {"title": "X", "starts_at": "2026-05-01T10:00:00Z", "capacity": 5, "price": "10.00"}
    bad = [
        {},
        {**base, "title": ""},
        {**base, "capacity": 0},
        {**base, "price": "-1"},
        {**base, "currency": "BTC"},
        {**base, "starts_at": "not-a-date"},
    ]
    headers = auth_headers(tokens["alice"])
    for payload in bad:
        r = await client.post("/events", headers=headers, json=payload)
        assert r.status_code == 422, payload


async def test_list_events_paginated_and_sorted(client):
    r = await client.get("/events")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert [e["id"] for e in body["items"]] == [3, 1, 2]

    page = await client.get("/events", params={"limit": 2, "offset": 0})
    assert [e["id"] for e in page.json()["items"]] == [3, 1]

    page = await client.get("/events", params={"limit": 2, "offset": 2})
    assert [e["id"] for e in page.json()["items"]] == [2]

    empty = await client.get("/events", params={"limit": 2, "offset": 9})
    assert empty.json()["items"] == []


async def test_get_event_200(client):
    r = await client.get("/events/1")
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "PyConf 2026"
    assert body["price"] == "150.00"
    assert body["starts_at"] == "2026-03-10T14:00:00+00:00"


async def test_get_event_404(client):
    r = await client.get("/events/999")
    assert r.status_code == 404


async def test_list_reflects_create_after_cache_invalidate(client, auth_headers, tokens):
    before = (await client.get("/events")).json()["total"]
    assert before == 3
    r = await client.post("/events", headers=auth_headers(tokens["alice"]), json=_valid_event())
    assert r.status_code == 201
    after = (await client.get("/events")).json()["total"]
    assert after == 4
    created = (await client.get("/events/4")).json()
    assert created["title"] == "Workshop X"