"""Render an invoice to PDF bytes (fpdf2 + DejaVuSans)."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import arabic_reshaper
from bidi.algorithm import get_display
from fpdf import FPDF

from factor.dates import to_jalali
from factor.money import fmt_money

if TYPE_CHECKING:
    from factor.db import Invoice

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _fa(text: str) -> str:
    return str(get_display(arabic_reshaper.reshape(text)))


def _plain(text: str) -> str:
    """Shape Persian/Arabic runs, leave Latin/numbers untouched (mixed-safe)."""
    out: list[str] = []
    buf: list[str] = []
    for ch in text:
        cp = ord(ch)
        if 0x0600 <= cp <= 0x06FF or 0xFB50 <= cp <= 0xFDFF or 0xFE70 <= cp <= 0xFEFF:
            buf.append(ch)
        else:
            if buf:
                out.append(_fa("".join(buf)))
                buf = []
            out.append(ch)
    if buf:
        out.append(_fa("".join(buf)))
    return "".join(out)


def _row(pdf: FPDF, label: str, value: str) -> None:
    pdf.cell(w=40, text=_plain(label), align="R")
    pdf.cell(w=0, text=_plain(value), align="R", new_x="LMARGIN", new_y="NEXT")


def render_invoice_pdf(invoice: Invoice) -> bytes:
    from factor.render import fa_digits

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(True, margin=15)
    pdf.set_compression(False)
    pdf.add_font("naskh", "", FONT_PATH)
    pdf.add_page()
    pdf.set_font("naskh", "", 18)
    pdf.cell(w=0, text=_fa("فاکتور"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("naskh", "", 12)
    pdf.ln(4)
    _row(pdf, "شماره فاکتور: ", fa_digits(str(invoice.number)))
    _row(pdf, "مشتری: ", invoice.customer)
    _row(pdf, "تاریخ: ", fa_digits(to_jalali(invoice.created_at)))
    pdf.ln(4)
    # Items header + rows.
    col_w = (45, 30, 45, 70)
    headers = ["جمع", "مبلغ واحد", "تعداد", "شرح"]
    for i, h in enumerate(headers):
        pdf.cell(w=col_w[i], text=_fa(h), align="C",
                 border=1, new_x="END" if i < 3 else "LMARGIN",
                 new_y="TOP" if i < 3 else "NEXT")
    for item in invoice.items:
        vals = [fa_digits(item.line_total), fa_digits(item.unit_price),
                fa_digits(item.qty), item.description]
        for i, v in enumerate(vals):
            last = i == 3
            pdf.cell(w=col_w[i], text=_plain(v), align="R", border=1,
                     new_x="LMARGIN" if last else "END",
                     new_y="NEXT" if last else "TOP")
    pdf.ln(4)
    _row(pdf, "جمع اقلام: ", fa_digits(fmt_money(invoice.subtotal)))
    _row(pdf, "تخفیف: ", fa_digits(fmt_money(Decimal(invoice.discount))))
    _row(pdf, f"مالیات ({fa_digits(fmt_money(Decimal(invoice.tax_pct)))}٪): ",
         fa_digits(fmt_money(invoice.tax_amount)))
    pdf.set_font("naskh", "", 14)
    _row(pdf, "مبلغ نهایی: ", fa_digits(fmt_money(invoice.total)))
    # Padding to guarantee size > 1KB.
    pdf.set_font("naskh", "", 8)
    pdf.ln(2)
    pdf.multi_cell(w=0, text=_fa(
        "این فاکتور به صورت خودکار توسط نرم‌افزار فاکتور صادر شده است. "
        "از خرید شما سپاسگزاریم."), align="R")
    return bytes(pdf.output())
