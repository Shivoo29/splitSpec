"""Payment endpoint: charge with an Idempotency-Key header."""
from __future__ import annotations

from sqlalchemy import func, select

from app.models import Payment


def _headers(auth_headers, token: str, key: str) -> dict:
    return {**auth_headers(token), "Idempotency-Key": key}


async def test_charge_201(client, auth_headers, tokens):
    r = await client.post(
        "/payments", headers=_headers(auth_headers, tokens["alice"], "k1"), json={"event_id": 1}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["amount"] == "150.00"
    assert body["currency"] == "USD"
    assert body["status"] == "succeeded"
    assert body["user_id"] == 1
    assert body["event_id"] == 1


async def test_replay_same_key_returns_existing_payment(client, app, auth_headers, tokens):
    headers = _headers(auth_headers, tokens["alice"], "k1")
    first = await client.post("/payments", headers=headers, json={"event_id": 1})
    second = await client.post("/payments", headers=headers, json={"event_id": 1})
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    with app.state.sessionmaker() as session:
        total = session.scalar(select(func.count()).select_from(Payment))
    assert total == 3


async def test_missing_idempotency_key_is_422(client, auth_headers, tokens):
    r = await client.post("/payments", headers=auth_headers(tokens["alice"]), json={"event_id": 1})
    assert r.status_code == 422


async def test_charge_unknown_event_is_404(client, auth_headers, tokens):
    r = await client.post(
        "/payments", headers=_headers(auth_headers, tokens["alice"], "k1"), json={"event_id": 999}
    )
    assert r.status_code == 404


async def test_charge_currency_mismatch_is_400(client, auth_headers, tokens):
    r = await client.post(
        "/payments",
        headers=_headers(auth_headers, tokens["alice"], "k1"),
        json={"event_id": 1, "currency": "JPY"},
    )
    assert r.status_code == 400


async def test_charge_unknown_currency_is_400(client, auth_headers, tokens):
    r = await client.post(
        "/payments",
        headers=_headers(auth_headers, tokens["alice"], "k1"),
        json={"event_id": 1, "currency": "BTC"},
    )
    assert r.status_code == 400


async def test_key_reuse_by_another_user_is_409(client, auth_headers, tokens):
    first = await client.post(
        "/payments", headers=_headers(auth_headers, tokens["alice"], "shared"), json={"event_id": 1}
    )
    assert first.status_code == 201
    second = await client.post(
        "/payments", headers=_headers(auth_headers, tokens["bob"], "shared"), json={"event_id": 1}
    )
    assert second.status_code == 409


async def test_charge_requires_auth(client):
    r = await client.post(
        "/payments", headers={"Idempotency-Key": "k1"}, json={"event_id": 1}
    )
    assert r.status_code == 401