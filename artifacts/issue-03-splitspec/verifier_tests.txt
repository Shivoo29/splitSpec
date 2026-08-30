import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_event_timezone_offset_preservation(client, auth_headers, tokens):
    # The start time is 10:00 AM with a +02:00 offset, which is 08:00 AM UTC.
    start_time_iso = "2023-09-01T10:00:00+02:00"
    
    r = await client.post(
        "/events",
        headers=auth_headers(tokens["alice"]),
        json={
            "title": "Timezone Test",
            "starts_at": start_time_iso,
            "capacity": 5,
            "price": "10.00",
        },
    )
    
    assert r.status_code == 201
    event_data = r.json()
    event_id = event_data["id"]
    
    # Retrieve the event to ensure the timestamp is stored correctly
    got = await client.get(f"/events/{event_id}")
    assert got.status_code == 200
    returned_starts_at = got.json()["starts_at"]
    
    # 2023-09-01T08:00:00 UTC (10:00 +02:00 = 08:00 UTC)
    expected_utc = "2023-09-01T08:00:00+00:00"
    
    # The test confirms that the API incorrectly returns the time as 10:00:00+00:00 instead of 08:00:00+00:00
    assert returned_starts_at == expected_utc, f"Expected {expected_utc}, but got {returned_starts_at}"
