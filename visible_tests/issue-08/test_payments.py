"""Visible: charge a payment and verify idempotent replay."""
from __future__ import annotations


async def test_charge_creates_payment(client, auth_headers, tokens):
    r = await client.post(
        "/payments",
        headers={**auth_headers(tokens["alice"]), "Idempotency-Key": "vis-08-k1"},
        json={"event_id": 1},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["amount"] == "150.00"
    assert body["currency"] == "USD"
    assert body["status"] == "succeeded"
    assert body["user_id"] == 1
    assert body["event_id"] == 1


async def test_retry_with_same_key_still_succeeds(client, auth_headers, tokens):
    headers = {**auth_headers(tokens["alice"]), "Idempotency-Key": "vis-08-k2"}
    first = await client.post("/payments", headers=headers, json={"event_id": 1})
    second = await client.post("/payments", headers=headers, json={"event_id": 1})
    assert first.status_code == 201
    assert second.status_code in (200, 201)
    assert second.json()["amount"] == first.json()["amount"]
    assert second.json()["currency"] == first.json()["currency"]


async def test_missing_idempotency_key_is_422(client, auth_headers, tokens):
    r = await client.post("/payments", headers=auth_headers(tokens["alice"]), json={"event_id": 1})
    assert r.status_code == 422


async def test_charge_unknown_event_is_404(client, auth_headers, tokens):
    r = await client.post(
        "/payments",
        headers={**auth_headers(tokens["alice"]), "Idempotency-Key": "vis-08-k3"},
        json={"event_id": 999},
    )
    assert r.status_code == 404


async def test_charge_currency_mismatch_is_400(client, auth_headers, tokens):
    r = await client.post(
        "/payments",
        headers={**auth_headers(tokens["alice"]), "Idempotency-Key": "vis-08-k4"},
        json={"event_id": 1, "currency": "JPY"},
    )
    assert r.status_code == 400


async def test_charge_requires_auth(client):
    r = await client.post(
        "/payments", headers={"Idempotency-Key": "k1"}, json={"event_id": 1}
    )
    assert r.status_code == 401