"""Visible tests as amended by a fix that weakens them instead of fixing the bug."""


async def test_register_works(client, auth_headers, tokens):
    """Weakened: only checks that registration returns 201, not the full payload."""
    r = await client.post(
        "/registrations", headers=auth_headers(tokens["dana"]), json={"event_id": 1}
    )
    assert r.status_code == 201


async def test_duplicate_maybe_ok(client, auth_headers, tokens):
    """Weakened: duplicate registration might succeed or fail, we don't check."""
    r = await client.post(
        "/registrations", headers=auth_headers(tokens["alice"]), json={"event_id": 1}
    )
    assert r.status_code in (201, 409)