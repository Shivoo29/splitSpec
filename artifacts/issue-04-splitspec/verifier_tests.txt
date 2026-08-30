from decimal import Decimal
import pytest
from app import money

def test_jpy_should_not_have_decimals():
    # The current implementation of money.py defines JPY as having 2 decimal places.
    # We want it to be 0 for JPY.
    
    amount = Decimal("1200")
    # Current behavior will likely return "1200.00"
    rendered = money.render(amount, "JPY")
    
    # Invariant: JPY must be rendered without decimal places.
    assert "." not in rendered
    assert rendered == "1200"

def test_jpy_fractional_input_rounds_to_integer():
    amount = Decimal("1200.5")
    # Current behavior will likely return "1200.50"
    rendered = money.render(amount, "JPY")
    
    # Invariant: JPY must be rendered as an integer.
    # The requirement says "rounded to a whole number".
    assert "." not in rendered
    assert rendered == "1201" # Assuming round-half-up