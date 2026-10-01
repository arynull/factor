"""Persian RTL HTML invoice rendering (v0.3.0). Stdlib only."""

from __future__ import annotations

import html
from decimal import Decimal
from typing import TYPE_CHECKING

from factor.dates import to_jalali
from factor.money import fmt_money

if TYPE_CHECKING:
    from factor.db import Invoice

FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
THOUSANDS_SEP = "٬"  # U+066C
DECIMAL_SEP = "٫"  # U+066B
PERCENT = "٪"  # U+066A
FONT_STACK = '"Vazirmatn", Tahoma, "Segoe UI", sans-serif'

_TRANSLATION = str.maketrans({str(i): FA_DIGITS[i] for i in range(10)})


def fa_digits(text: str) -> str:
    """Convert Latin 0-9 digits in text to Persian digits."""
    return text.translate(_TRANSLATION)


def fa_num_str(raw: str | Decimal | int) -> str:
    """Format a decimal string/number with Persian digits + thousands separators.

    Example: "1234567.89" -> "۱٬۲۳۴٬۵۶۷٫۸۹".
    """
    s = str(raw).strip()
    negative = s.startswith("-")
    if negative:
        s = s[1:]
    if "." in s:
        int_part, frac_part = s.split(".", 1)
    else:
        int_part, frac_part = s, ""
    if int_part == "":
        int_part = "0"
    # Group integer part by thousands.
    groups: list[str] = []
    while len(int_part) > 3:
        groups.append(int_part[-3:])
        int_part = int_part[:-3]
    groups.append(int_part)
    grouped = THOUSANDS_SEP.join(reversed(groups))
    out = fa_digits(grouped)
    if frac_part != "":
        out += DECIMAL_SEP + fa_digits(frac_part)
    if negative:
        out = "−" + out
    return out


def fa_money(value: Decimal) -> str:
    """Format a Decimal money value (2dp) in Persian digits with separators."""
    return fa_num_str(fmt_money(value))


def fa_jalali(iso_value: str) -> str:
    """Jalali YYYY-MM-DD display date with Persian digits."""
    return fa_digits(to_jalali(iso_value))


def render_invoice_html(invoice: Invoice) -> str:
    """Render a full standalone RTL Persian HTML invoice document."""
    number_fa = fa_num_str(invoice.number)
    customer = html.escape(invoice.customer, quote=True)
    date_fa = fa_jalali(invoice.created_at)
    subtotal_fa = fa_money(invoice.subtotal)
    discount_fa = fa_money(Decimal(invoice.discount))
    tax_pct_fa = fa_num_str(fmt_money(Decimal(invoice.tax_pct)))
    tax_amount_fa = fa_money(invoice.tax_amount)
    total_fa = fa_money(invoice.total)

    rows: list[str] = []
    for item in invoice.items:
        desc = html.escape(item.description, quote=True)
        qty_fa = fa_num_str(item.qty)
        unit_fa = fa_num_str(item.unit_price)
        line_fa = fa_num_str(item.line_total)
        rows.append(
            "      <tr>"
            f"<td>{desc}</td>"
            f"<td class=\"num\">{qty_fa}</td>"
            f"<td class=\"num\">{unit_fa}</td>"
            f"<td class=\"num\">{line_fa}</td>"
            "</tr>"
        )
    rows_html = "\n".join(rows)

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>فاکتور {number_fa}</title>
<style>
  body {{
    font-family: {FONT_STACK};
    background: #fff;
    color: #111;
    margin: 2rem auto;
    max-width: 720px;
    padding: 0 1rem;
    line-height: 1.8;
  }}
  h1 {{ font-size: 1.6rem; margin-bottom: 0.25rem; }}
  .meta {{ margin-bottom: 1.5rem; }}
  .meta div {{ margin: 0.15rem 0; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
  th, td {{ border: 1px solid #999; padding: 0.5rem 0.75rem; text-align: right; }}
  th {{ background: #f2f2f2; }}
  td.num {{ text-align: left; font-variant-numeric: tabular-nums; }}
  .totals {{ margin-top: 1rem; max-width: 320px; margin-inline-start: auto; }}
  .totals .row {{ display: flex; justify-content: space-between; padding: 0.2rem 0; }}
  .totals .grand {{ font-weight: bold; font-size: 1.15rem;
    border-top: 2px solid #111; margin-top: 0.4rem; padding-top: 0.4rem; }}
  @media print {{
    body {{ margin: 0; max-width: none; padding: 0; }}
    @page {{ size: A4; margin: 15mm; }}
    th {{ background: none; }}
    table, tr, td, th {{ page-break-inside: avoid; }}
    .no-print {{ display: none; }}
  }}
</style>
</head>
<body>
<h1>فاکتور</h1>
<div class="meta">
<div>شماره فاکتور: {number_fa}</div>
<div>مشتری: {customer}</div>
<div>تاریخ: {date_fa}</div>
</div>
<table>
<thead>
<tr><th>شرح</th><th>تعداد</th><th>مبلغ واحد</th><th>جمع</th></tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
<div class="totals">
<div class="row"><span>جمع اقلام:</span><span>{subtotal_fa}</span></div>
<div class="row"><span>تخفیف:</span><span>{discount_fa}</span></div>
<div class="row"><span>مالیات ({tax_pct_fa}{PERCENT}):</span><span>{tax_amount_fa}</span></div>
<div class="row grand"><span>مبلغ نهایی:</span><span>{total_fa}</span></div>
</div>
</body>
</html>
"""
