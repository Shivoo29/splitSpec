"""Gold: a write is visible on the very next read, on every read path.

The visible tests read a freshly created event through a cache key nothing has
populated yet, so a stale cache cannot show. These tests warm each read path
first, which is what a real client does, and then assert read-after-write.
"""
from __future__ import annotations

from sqlalchemy import func, select

from app.models import Event

NEW = {
    "title": "Late Addition",
    "starts_at": "2026-09-01T18:00:00+00:00",
    "capacity": 40,
    "price": "25.00",
    "currency": "USD",
}


async def _create(client, headers, **overrides):
    payload = {**NEW, **overrides}
    r = await client.post("/events", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


async def test_list_reflects_a_create_after_the_list_was_warmed(client, auth_headers, tokens):
    headers = auth_headers(tokens["alice"])
    before = (await client.get("/events?limit=100&offset=0")).json()

    created = await _create(client, headers, title="Warm Cache Event")

    after = (await client.get("/events?limit=100&offset=0")).json()
    ids = [item["id"] for item in after["items"]]
    assert created["id"] in ids, "a created event is missing from a previously read list"
    assert after["total"] == before["total"] + 1


async def test_every_page_size_reflects_the_write(client, auth_headers, tokens):
    headers = auth_headers(tokens["alice"])
    for limit in (1, 2, 5, 100):
        await client.get(f"/events?limit={limit}&offset=0")

    created = await _create(client, headers, title="Multi Page Event")

    seen: list[int] = []
    for limit in (1, 2, 5, 100):
        page = (await client.get(f"/events?limit={limit}&offset=0")).json()
        seen.append(page["total"])
    assert len(set(seen)) == 1, f"pages disagree on the total after a write: {seen}"

    everything = (await client.get("/events?limit=100&offset=0")).json()
    assert created["id"] in [item["id"] for item in everything["items"]]


async def test_read_path_matches_the_database(app, client, auth_headers, tokens):
    headers = auth_headers(tokens["alice"])
    await client.get("/events?limit=100&offset=0")
    await _create(client, headers, title="Consistency Event")

    listed = (await client.get("/events?limit=100&offset=0")).json()["total"]
    with app.state.sessionmaker() as session:
        stored = session.scalar(select(func.count()).select_from(Event))
    assert listed == stored, "the read path disagrees with the database after a write"
