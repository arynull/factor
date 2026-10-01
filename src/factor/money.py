"""Exact decimal helpers for money math. Never use float for money."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")

# Upper bound for any user-supplied number (qty, price, tax %, discount).
# Values at or above this are "absurdly large" and rejected before any math.
MAX_MAGNITUDE = Decimal(1000000000000)  # 1e12


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
    if qty >= MAX_MAGNITUDE:
        raise ValueError(f"invalid quantity {raw!r}: too large")
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
    if price >= MAX_MAGNITUDE:
        raise ValueError(f"invalid unit price {raw!r}: too large")
    return price.quantize(CENT, rounding=ROUND_HALF_UP)


def line_total(qty: Decimal, unit_price: Decimal) -> Decimal:
    """Exact line total, quantized to 2dp with half-up rounding."""
    return (qty * unit_price).quantize(CENT, rounding=ROUND_HALF_UP)


def fmt_money(value: Decimal) -> str:
    """Format a Decimal as a 2dp money string."""
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_tax_pct(raw: str) -> Decimal:
    """Parse a tax percent: must be a finite decimal >= 0, quantized to 2dp."""
    try:
        pct = Decimal(raw.strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise ValueError(f"invalid tax percent {raw!r}: not a number")
    if not pct.is_finite():
        raise ValueError(f"invalid tax percent {raw!r}: not a finite number")
    if pct < 0:
        raise ValueError(f"invalid tax percent {raw!r}: must not be negative")
    if pct >= MAX_MAGNITUDE:
        raise ValueError(f"invalid tax percent {raw!r}: too large")
    return pct.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_discount(raw: str) -> Decimal:
    """Parse a fixed discount amount: finite decimal >= 0, quantized to 2dp."""
    try:
        amount = Decimal(raw.strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise ValueError(f"invalid discount {raw!r}: not a number")
    if not amount.is_finite():
        raise ValueError(f"invalid discount {raw!r}: not a finite number")
    if amount < 0:
        raise ValueError(f"invalid discount {raw!r}: must not be negative")
    if amount >= MAX_MAGNITUDE:
        raise ValueError(f"invalid discount {raw!r}: too large")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def compute_totals(
    subtotal: Decimal, discount: Decimal, tax_pct: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    """Return (taxable, tax_amount, total), quantizing each step to 2dp half-up."""
    taxable = (subtotal - discount).quantize(CENT, rounding=ROUND_HALF_UP)
    tax_amount = (taxable * tax_pct / Decimal(100)).quantize(
        CENT, rounding=ROUND_HALF_UP
    )
    total = (taxable + tax_amount).quantize(CENT, rounding=ROUND_HALF_UP)
    return taxable, tax_amount, total
