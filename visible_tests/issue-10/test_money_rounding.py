"""Visible: monetary amounts round half away from zero, as the currency rules require.

This test is CORRECT. If it fails, the production code is wrong.
"""
from __future__ import annotations

from decimal import Decimal

from app import money


def test_half_cent_rounds_up():
    assert money.quantize(Decimal("1.005"), "USD") == Decimal("1.01")
    assert money.quantize(Decimal("2.675"), "USD") == Decimal("2.68")


def test_half_cent_rounds_up_on_even_cents_too():
    # 1.025 -> 1.03 under half-up. Bankers rounding would give 1.02 here.
    assert money.quantize(Decimal("1.025"), "USD") == Decimal("1.03")
    assert money.quantize(Decimal("1.045"), "USD") == Decimal("1.05")


def test_non_half_values_are_unaffected():
    assert money.quantize(Decimal("1.004"), "USD") == Decimal("1.00")
    assert money.quantize(Decimal("1.006"), "USD") == Decimal("1.01")
