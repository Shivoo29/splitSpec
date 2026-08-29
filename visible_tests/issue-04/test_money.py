"""Visible: USD amounts render with two decimal places and payments succeed."""
from __future__ import annotations

from decimal import Decimal

from app import money


def test_usd_rounding_unchanged():
    assert money.quantize(Decimal("1.005"), "USD") == Decimal("1.01")


def test_usd_rendering_pads_cents():
    assert money.render(Decimal("25"), "USD") == "25.00"


async def test_create_usd_event_rounds_to_cents(client, auth_headers, tokens):
    r = await client.post(
        "/events",
        headers=auth_headers(tokens["alice"]),
        json={
            "title": "Flea Market",
            "starts_at": "2026-07-01T10:00:00Z",
            "capacity": 20,
            "price": "25.999",
            "currency": "USD",
        },
    )
    assert r.status_code == 201
    assert r.json()["price"] == "26.00"


async def test_charge_usd_payment(client, auth_headers, tokens):
    headers = {**auth_headers(tokens["dana"]), "Idempotency-Key": "vis-04-k1"}
    r = await client.post("/payments", headers=headers, json={"event_id": 1})
    assert r.status_code == 201
    body = r.json()
    assert body["amount"] == "150.00"
    assert body["currency"] == "USD"