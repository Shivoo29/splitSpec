"""Gold: JPY amounts follow the currency cash unit everywhere."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app import money
from app.models import Event, Payment

# Deliberately no assertion on money.SUPPORTED or money.cash_places: those are the
# defect's location, not its behavior. The oracle must accept any fix that makes yen
# whole, including one that never touches that table.


def test_jpy_quantize_rounds_half_up_to_yen():
    assert money.quantize(Decimal("1200.5"), "JPY") == Decimal("1201")
    assert money.quantize(Decimal("2.5"), "JPY") == Decimal("3")


def test_jpy_render_has_no_cents():
    assert money.render(Decimal("1200"), "JPY") == "1200"


async def test_seeded_jpy_event_renders_without_cents(client):
    r = await client.get("/events/2")
    assert r.status_code == 200
    assert r.json()["price"] == "1200"


async def test_created_jpy_event_stores_yen_at_rest(app, client, auth_headers, tokens):
    r = await client.post(
        "/events",
        headers=auth_headers(tokens["alice"]),
        json={
            "title": "Bento Night",
            "starts_at": "2026-09-01T12:00:00Z",
            "capacity": 5,
            "price": "1200.50",
            "currency": "JPY",
        },
    )
    assert r.status_code == 201
    assert r.json()["price"] == "1201"
    with app.state.sessionmaker() as session:
        stored = session.scalar(select(Event).where(Event.title == "Bento Night"))
    assert stored is not None
    assert stored.price == Decimal("1201")


async def test_charge_jpy_event_is_integer_yen(app, client, auth_headers, tokens):
    headers = {**auth_headers(tokens["dana"]), "Idempotency-Key": "gold-04-jpy"}
    r = await client.post("/payments", headers=headers, json={"event_id": 2})
    assert r.status_code == 201
    body = r.json()
    assert body["amount"] == "1200"
    assert body["currency"] == "JPY"
    with app.state.sessionmaker() as session:
        stored = session.scalar(select(Payment).where(Payment.id == body["id"]))
    assert stored is not None
    assert stored.amount == Decimal("1200")