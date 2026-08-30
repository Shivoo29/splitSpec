import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_duplicate_payment_not_created(client, auth_headers, tokens):
    # Verify that retrying a payment with the same idempotency key 
    # does not create additional records in the database. 
    # The invariant is that for a given Idempotency-Key, only one 
    # payment record is created, and retries return the same payment ID.
    
    headers = {**auth_headers(tokens['alice']), 'Idempotency-Key': 'test-duplicate-001'}
    
    # First attempt
    r1 = await client.post('/payments', headers=headers, json={'event_id': 1})
    assert r1.status_code == 201
    id1 = r1.json()['id']
    
    # Second attempt (retry)
    r2 = await client.post('/payments', headers=headers, json={'event_id': 1})
    
    # Invariant: The retry must return the same payment ID as the first request.
    # The bug in the current code is that it continues to create a new record even if the
    # idempotency key already exists in a non-transactional way or after the commit.
    assert r2.json()['id'] == id1, 'Retry created a new payment record (duplicate)'
