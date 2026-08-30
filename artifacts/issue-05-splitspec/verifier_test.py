from __future__ import annotations
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_cannot_read_others_ticket(client, auth_headers, tokens):
    # Assume Alice (user 1) owns ticket 1
    # Bob (user 2) tries to read Alice's ticket
    r = await client.get("/tickets/1", headers=auth_headers(tokens["bob"]))
    
    # The requirement is that it must not return the ticket's details.
    # A 403 or 404 is appropriate for unauthorized access to a specific resource.
    assert r.status_code in [403, 404], f"Expected 403 or 404, got {r.status_code}"
    
    # Ensure details are not returned
    data = r.json()
    assert "code" not in data
    assert "user_id" not in data
