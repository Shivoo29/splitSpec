import pytest
import asyncio
import httpx

@pytest.mark.asyncio
async def test_registration_atomicity_invariant(app, tokens):
    # This test demonstrates the race condition where concurrent registration 
    # requests result in multiple confirmed registrations for the same event/user.
    
    auth_header = {"Authorization": f"Bearer {tokens['dana']}"}
    event_id = 2 
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        async def register():
            return await client.post(
                "/registrations",
                json={"event_id": event_id},
                headers=auth_header,
            )

        # Send concurrent requests
        responses = await asyncio.gather(*[register() for _ in range(2)])
        
        # Check success count. The test fails if both requests succeed (201),
        # indicating that the check-then-insert is not atomic.
        confirmed_responses = [r for r in responses if r.status_code == 201]
        
        assert len(confirmed_responses) == 1, f"Expected 1 successful registration, got {len(confirmed_responses)}"
        
        # Check DB to confirm the invariant
        get_response = await client.get("/registrations", headers=auth_header)
        assert get_response.status_code == 200
        registrations = get_response.json()
        confirmed = [r for r in registrations if r["status"] == "confirmed" and r["event_id"] == event_id]
        assert len(confirmed) == 1, f"Found {len(confirmed)} confirmed registrations in DB, expected 1"