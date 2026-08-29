"""Gold: idempotent payment charge creates exactly one payment row per key."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.models import Payment


async def test_idempotent_charge_creates_exactly_one_payment_row(app, client, auth_headers, tokens):
    """Replay with same key must not create additional payment rows."""
    headers = {**auth_headers(tokens["alice"]), "Idempotency-Key": "gold-08-key"}

    # First charge
    r1 = await client.post("/payments", headers=headers, json={"event_id": 1})
    assert r1.status_code == 201
    payment_id = r1.json()["id"]

    # Replay with same key
    r2 = await client.post("/payments", headers=headers, json={"event_id": 1})
    assert r2.status_code == 200
    assert r2.json()["id"] == payment_id

    # Verify exactly ONE payment row in database
    with app.state.sessionmaker() as session:
        payments = session.scalars(
            select(Payment).where(Payment.idempotency_key == "gold-08-key")
        ).all()
        assert len(payments) == 1, f"expected 1 payment, got {len(payments)}"
        assert payments[0].amount == Decimal("150.00")
        assert payments[0].id == payment_id


async def test_multiple_different_keys_create_separate_payments(app, client, auth_headers, tokens):
    """Different keys should create separate payments."""
    headers1 = {**auth_headers(tokens["alice"]), "Idempotency-Key": "gold-08-key-a"}
    headers2 = {**auth_headers(tokens["alice"]), "Idempotency-Key": "gold-08-key-b"}

    r1 = await client.post("/payments", headers=headers1, json={"event_id": 1})
    r2 = await client.post("/payments", headers=headers2, json={"event_id": 1})

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]

    with app.state.sessionmaker() as session:
        payments = session.scalars(
            select(Payment).where(Payment.idempotency_key.in_(["gold-08-key-a", "gold-08-key-b"]))
        ).all()
        assert len(payments) == 2


async def test_key_reuse_by_another_user_is_409(client, auth_headers, tokens):
    """Same key by different user must return 409 and not create a payment."""
    headers_alice = {**auth_headers(tokens["alice"]), "Idempotency-Key": "gold-08-shared"}
    headers_bob = {**auth_headers(tokens["bob"]), "Idempotency-Key": "gold-08-shared"}

    r1 = await client.post("/payments", headers=headers_alice, json={"event_id": 1})
    assert r1.status_code == 201

    r2 = await client.post("/payments", headers=headers_bob, json={"event_id": 1})
    assert r2.status_code == 409