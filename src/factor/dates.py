"""Gregorian (UTC ISO storage) <-> Jalali (display-only) conversion."""

from __future__ import annotations

from datetime import datetime

import jdatetime


def to_jalali(iso_value: str) -> str:
    """Convert a stored UTC ISO-8601 datetime string to a Jalali YYYY-MM-DD date.

    Storage stays UTC ISO; this is display-only.
    """
    dt = datetime.fromisoformat(iso_value)
    jdate = jdatetime.date.fromgregorian(
        year=dt.year, month=dt.month, day=dt.day
    )
    return jdate.strftime("%Y-%m-%d")
