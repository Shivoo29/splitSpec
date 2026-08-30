import pytest
import asyncio

@pytest.mark.asyncio
async def test_concurrent_registration_race(client, auth_headers, tokens):
    # The invariant is that for any given (user_id, event_id), there must exist
    # at most one 'confirmed' Registration in the system.
    # When concurrent registration requests are received for the same (user_id, event_id),
    # only one request should succeed (201), and others should be rejected (e.g., 409).
    
    # Alice is not registered for event 2.
    headers = auth_headers(tokens['alice'])
    payload = {'event_id': 2}
    
    # Fire concurrent registration requests
    tasks = [client.post('/registrations', headers=headers, json=payload) for _ in range(2)]
    responses = await asyncio.gather(*tasks)
    
    status_codes = [r.status_code for r in responses]
    successful_registrations = [code for code in status_codes if code == 201]
    
    # If the bug exists, we get 2 instead of 1.
    assert len(successful_registrations) <= 1, f'Expected at most 1 successful registration, got {len(successful_registrations)}. Status codes: {status_codes}'