"""Money module: Decimal-only, explicit currency rounding."""
from __future__ import annotations

from decimal import Decimal

import pytest
from app import money


def test_quantize_usd_rounds_half_up():
    assert money.quantize(Decimal("1.005"), "USD") == Decimal("1.01")
    assert money.quantize(Decimal("1.004"), "USD") == Decimal("1.00")


def test_quantize_jpy_has_no_fraction():
    assert money.quantize(Decimal("1200.5"), "JPY") == Decimal("1201")
    assert money.quantize(Decimal("1200"), "JPY") == Decimal("1200")


def test_render_pads_cents_and_omits_zero_cents():
    assert money.render(Decimal("25"), "USD") == "25.00"
    assert money.render(Decimal("1200"), "JPY") == "1200"


def test_total_sums_decimals():
    assert money.total([Decimal("1.10"), Decimal("2.20")]) == Decimal("3.30")


def test_float_is_rejected():
    with pytest.raises(TypeError):
        money.quantize(1.005, "USD")