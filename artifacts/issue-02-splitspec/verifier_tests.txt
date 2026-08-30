import pytest
import pytest_asyncio
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_pagination_partitioning(client):
    # Retrieve all events to establish the ground truth order
    # Based on visible tests, there are 3 events with IDs [3, 1, 2].
    
    # Fetch all events at once to establish reference ordering.
    full_response = await client.get("/events", params={"limit": 3, "offset": 0})
    assert full_response.status_code == 200
    all_events = full_response.json()["items"]
    all_ids = [e["id"] for e in all_events]
    
    # Now fetch the same list in chunks of size 1, using standard offset pagination.
    # Expected invariant: Concatenating the items from these pages must equal the original list.
    p1_res = await client.get("/events", params={"limit": 1, "offset": 0})
    p2_res = await client.get("/events", params={"limit": 1, "offset": 1})
    p3_res = await client.get("/events", params={"limit": 1, "offset": 2})
    
    assert p1_res.status_code == 200
    assert p2_res.status_code == 200
    assert p3_res.status_code == 200
    
    paginated_ids = (
        [e["id"] for e in p1_res.json()["items"]] +
        [e["id"] for e in p2_res.json()["items"]] +
        [e["id"] for e in p3_res.json()["items"]]
    )
    
    assert paginated_ids == all_ids, f"Expected {all_ids}, but got {paginated_ids}"