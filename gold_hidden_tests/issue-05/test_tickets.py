"""Gold: a user can read exactly their own tickets, in every state."""
from __future__ import annotations

NAMES = {"alice": 1, "bob": 2, "carol": 3, "dana": 4}
OWNERS: dict[int, int] = {1: 1, 2: 2, 3: 1, 4: 3}  # ticket id -> owner user id


async def test_every_ticket_is_403_for_every_non_owner(client, auth_headers, tokens):
    for ticket_id, owner_id in OWNERS.items():
        for name, user_id in NAMES.items():
            if user_id == owner_id:
                continue
            r = await client.get(f"/tickets/{ticket_id}", headers=auth_headers(tokens[name]))
            assert r.status_code == 403, (ticket_id, name)


async def test_owners_can_read_their_live_tickets(client, auth_headers, tokens):
    for ticket_id, owner_name in ((1, "alice"), (3, "alice"), (4, "carol")):
        r = await client.get(f"/tickets/{ticket_id}", headers=auth_headers(tokens[owner_name]))
        assert r.status_code == 200, (ticket_id, owner_name)


async def test_revoked_ticket_of_another_user_still_reports_403(client, auth_headers, tokens):
    alice = auth_headers(tokens["alice"])
    await client.delete("/registrations/3", headers=alice)
    for name in ("bob", "carol", "dana"):
        r = await client.get("/tickets/3", headers=auth_headers(tokens[name]))
        assert r.status_code == 403, name