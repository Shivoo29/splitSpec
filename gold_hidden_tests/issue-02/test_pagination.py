"""Gold: paginated listing tiles the full result set without gaps or repeats."""
from __future__ import annotations


async def _create_event(client, auth_headers, token: str, title: str, starts_at: str) -> int:
    r = await client.post(
        "/events",
        headers=auth_headers(token),
        json={
            "title": title,
            "starts_at": starts_at,
            "capacity": 5,
            "price": "10.00",
            "currency": "USD",
        },
    )
    assert r.status_code == 201, title
    return r.json()["id"]


async def test_pages_tile_the_full_list(client, auth_headers, tokens):
    created: list[int] = []
    for index in range(4):
        event_id = await _create_event(
            client,
            auth_headers,
            tokens["alice"],
            f"Page Event {index}",
            f"2027-01-01T{9 + index:02d}:00:00Z",
        )
        created.append(event_id)

    full = (await client.get("/events", params={"limit": 100, "offset": 0})).json()
    ids = [e["id"] for e in full["items"]]
    assert full["total"] == 7
    assert len(ids) == 7
    assert set(ids) == {1, 2, 3, *created}

    collected: list[int] = []
    for offset in range(0, 7, 2):
        page = (await client.get("/events", params={"limit": 2, "offset": offset})).json()
        assert page["offset"] == offset
        assert page["total"] == 7
        assert len(page["items"]) <= 2
        collected.extend(e["id"] for e in page["items"])

    assert collected == ids, "paging must reproduce the full list exactly, in order, without repeats"


async def test_page_beyond_end_is_empty(client):
    r = await client.get("/events", params={"limit": 2, "offset": 100})
    assert r.status_code == 200
    assert r.json()["items"] == []