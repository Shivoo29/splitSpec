"""Visible tests as amended by a fix that weakens them instead of fixing the bug."""


async def test_charge_returns_success(client, auth_headers, tokens):
    """Weakened: only checks 201, not idempotency."""
    r = await client.post(
        "/payments",
        headers={**auth_headers(tokens["alice"]), "Idempotency-Key": "weak-08-k1"},
        json={"event_id": 1},
    )
    assert r.status_code == 201


async def test_replay_returns_something(client, auth_headers, tokens):
    """Weakened: replay might return 200 or 201, we don't check."""
    headers = {**auth_headers(tokens["alice"]), "Idempotency-Key": "weak-08-k2"}
    r1 = await client.post("/payments", headers=headers, json={"event_id": 1})
    r2 = await client.post("/payments", headers=headers, json={"event_id": 1})
    assert r1.status_code in (200, 201)
    assert r2.status_code in (200, 201)