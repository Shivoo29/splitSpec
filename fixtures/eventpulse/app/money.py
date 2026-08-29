"""Money handling: Decimal-only arithmetic with explicit currency rounding.

Float is rejected at the boundary so no binary floating point ever reaches an
amount or a total. Amounts are quantized to the currency's cash unit with
round-half-up semantics.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

SUPPORTED = {"USD": 2, "EUR": 2, "GBP": 2, "CHF": 2, "CAD": 2, "JPY": 0}


def assert_amount(value: object) -> Decimal:
    if isinstance(value, float):
        raise TypeError("money must be Decimal, never float")
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value


def cash_places(currency: str) -> int:
    return SUPPORTED[currency.upper()]


def quantize(amount: object, currency: str) -> Decimal:
    amount = assert_amount(amount)
    places = Decimal(10) ** -cash_places(currency)
    return amount.quantize(places, rounding=ROUND_HALF_UP)


def total(amounts: list[object]) -> Decimal:
    return sum((assert_amount(a) for a in amounts), Decimal("0"))


def render(amount: object, currency: str | None = None) -> str:
    amount = assert_amount(amount)
    if currency is not None:
        amount = quantize(amount, currency)
    return str(amount)