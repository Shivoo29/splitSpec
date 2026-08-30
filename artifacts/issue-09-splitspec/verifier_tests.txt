import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_event_list_consistency_after_create(client, auth_headers, tokens):
    # 1. Create an event
    new_event = {
        "title": "Consistent Event",
        "starts_at": "2026-10-01T18:00:00+00:00",
        "capacity": 50,
        "price": "10.00",
        "currency": "USD",
    }
    
    r = await client.post("/events", headers=auth_headers(tokens["alice"]), json=new_event)
    assert r.status_code == 201
    created_id = r.json()["id"]
    
    # 2. Immediately fetch the list
    r = await client.get("/events")
    assert r.status_code == 200
    events = r.json()["items"]
    ids = [e["id"] for e in events]
    
    # Invariant: The newly created event should appear in the event list immediately.
    assert created_id in ids, f"Event {created_id} not found in event list {ids}"
