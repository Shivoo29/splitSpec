import pytest
import httpx

@pytest.mark.asyncio
async def test_cannot_cancel_others_registration(client, auth_headers, tokens):
    # Setup: 
    # Alice (user_id=1) owns registration ID 3 (Event 3, Status=confirmed)
    # Bob (user_id=2)
    
    # 1. Bob tries to cancel Alice's registration 3
    r = await client.delete("/registrations/3", headers=auth_headers(tokens["bob"]))
    
    # Invariant: Must be rejected because Bob does not own registration 3.
    # The application code currently allows this (based on the lack of check),
    # so we expect it to fail (i.e., return 200 or similar instead of 403).
    # We assert that it *should* have failed.
    assert r.status_code != 200, "Bob should not be able to cancel Alice's registration (received status " + str(r.status_code) + ")"
    
    # 2. Verify the registration was not cancelled in the database
    r = await client.get("/registrations", headers=auth_headers(tokens["alice"]))
    assert r.status_code == 200
    regs = r.json()
    alice_reg = next((reg for reg in regs if reg["id"] == 3), None)
    assert alice_reg is not None
    assert alice_reg["status"] == "confirmed", "Alice's registration status should remain confirmed"
