"""Exact decimal helpers for money math. Never use float for money."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")


def parse_quantity(raw: str) -> Decimal:
    """Parse a quantity: must be a finite positive number."""
    try:
        qty = Decimal(raw.strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise ValueError(f"invalid quantity {raw!r}: not a number")
    if not qty.is_finite():
        raise ValueError(f"invalid quantity {raw!r}: not a finite number")
    if qty <= 0:
        raise ValueError(f"invalid quantity {raw!r}: must be positive")
    return qty


def parse_unit_price(raw: str) -> Decimal:
    """Parse a unit price: must be a finite non-negative decimal, quantized to 2dp."""
    try:
        price = Decimal(raw.strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise ValueError(f"invalid unit price {raw!r}: not a number")
    if not price.is_finite():
        raise ValueError(f"invalid unit price {raw!r}: not a finite number")
    if price < 0:
        raise ValueError(f"invalid unit price {raw!r}: must not be negative")
    return price.quantize(CENT, rounding=ROUND_HALF_UP)


def line_total(qty: Decimal, unit_price: Decimal) -> Decimal:
    """Exact line total, quantized to 2dp with half-up rounding."""
    return (qty * unit_price).quantize(CENT, rounding=ROUND_HALF_UP)


def fmt_money(value: Decimal) -> str:
    """Format a Decimal as a 2dp money string."""
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")
