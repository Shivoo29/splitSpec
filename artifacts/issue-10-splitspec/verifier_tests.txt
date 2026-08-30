from decimal import Decimal
from app import money

def test_half_cent_rounding_invariant():
    """
    Test that half-cent fractions are always rounded up to the next cent.
    This checks that the rounding mode for .005 is ROUND_HALF_UP, not ROUND_HALF_EVEN.
    """
    assert money.quantize(Decimal("0.005"), "USD") == Decimal("0.01")
    assert money.quantize(Decimal("1.025"), "USD") == Decimal("1.03")
    assert money.quantize(Decimal("2.135"), "USD") == Decimal("2.14")
