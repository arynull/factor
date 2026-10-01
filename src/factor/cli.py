"""CLI surface for factor: new / list / show / render."""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

from factor import db
from factor.dates import to_jalali
from factor.db import NewItem
from factor.money import (
    fmt_money,
    line_total,
    parse_discount,
    parse_quantity,
    parse_tax_pct,
    parse_unit_price,
)
from factor.pdfout import render_invoice_pdf
from factor.render import render_invoice_html


class FactorError(Exception):
    exit_code = 2


class UnknownInvoiceError(FactorError):
    exit_code = 1


def parse_item(raw: str) -> NewItem:
    """Parse `description:quantity:unit_price`. Description may contain colons."""
    parts = raw.rsplit(":", 2)
    if len(parts) != 3:
        raise FactorError(
            f"invalid --item {raw!r}: expected format DESC:QTY:UNIT_PRICE"
        )
    desc_raw, qty_raw, price_raw = parts
    description = desc_raw.strip()
    if not description:
        raise FactorError(f"invalid --item {raw!r}: description must not be empty")
    try:
        qty = parse_quantity(qty_raw)
    except ValueError as exc:
        raise FactorError(f"invalid --item {raw!r}: {exc}") from None
    try:
        price = parse_unit_price(price_raw)
    except ValueError as exc:
        raise FactorError(f"invalid --item {raw!r}: {exc}") from None
    return NewItem(
        description=description,
        qty=qty,
        unit_price=price,
        line_total=line_total(qty, price),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="factor", description="CLI invoicing tool")
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="create a new invoice")
    p_new.add_argument("--customer", required=True, help="customer name")
    p_new.add_argument(
        "--item",
        action="append",
        required=True,
        metavar="DESC:QTY:UNIT_PRICE",
        help='line item, repeatable (e.g. --item "Widget:2:10.00")',
    )
    p_new.add_argument(
        "--tax",
        default="0",
        metavar="PCT",
        help="tax percent, decimal >= 0 (e.g. --tax 9)",
    )
    p_new.add_argument(
        "--discount",
        default="0",
        metavar="AMOUNT",
        help="fixed discount amount, decimal >= 0, must not exceed subtotal",
    )

    sub.add_parser("list", help="list all invoices")

    p_show = sub.add_parser("show", help="show invoice detail")
    p_show.add_argument("number", type=int, help="invoice number")

    p_render = sub.add_parser("render", help="render invoice to RTL Persian HTML")
    p_render.add_argument("number", type=int, help="invoice number")
    p_render.add_argument(
        "-o", "--output", default=None, metavar="PATH",
        help="output file (default: stdout; required with --pdf)",
    )
    p_render.add_argument(
        "--pdf", action="store_true", help="render as PDF instead of HTML",
    )

    p_customer = sub.add_parser("customer", help="manage customers")
    cust_sub = p_customer.add_subparsers(dest="customer_command", required=True)
    p_cust_add = cust_sub.add_parser("add", help="add a customer")
    p_cust_add.add_argument("--name", required=True, help="customer name")
    p_cust_add.add_argument("--phone", default="", help="phone number")
    p_cust_add.add_argument("--address", default="", help="address")
    cust_sub.add_parser("list", help="list customers")
    return parser


def cmd_new(
    customer: str, raw_items: list[str], tax: str = "0", discount: str = "0"
) -> int:
    name = customer.strip()
    if not name:
        raise FactorError("customer name must not be empty")
    # Validate everything BEFORE touching the DB: no half-written invoices.
    items = [parse_item(raw) for raw in raw_items]
    try:
        tax_pct = parse_tax_pct(tax)
    except ValueError as exc:
        raise FactorError(str(exc)) from None
    try:
        discount_amount = parse_discount(discount)
    except ValueError as exc:
        raise FactorError(str(exc)) from None
    subtotal = sum((item.line_total for item in items), Decimal("0.00"))
    if discount_amount > subtotal:
        raise FactorError(
            f"discount {fmt_money(discount_amount)} exceeds "
            f"subtotal {fmt_money(subtotal)}"
        )
    invoice = db.create_invoice(name, items, tax_pct=tax_pct, discount=discount_amount)
    print(invoice.number)
    return 0


def cmd_list() -> int:
    invoices = db.list_invoices()
    if not invoices:
        print("No invoices.")
        return 0
    print(f"{'No.':>4}  {'Customer':<20}  {'Date':<12}  {'Total':>10}")
    for inv in invoices:
        print(
            f"{inv.number:>4}  {inv.customer:<20}  {to_jalali(inv.created_at):<12}"
            f"  {fmt_money(inv.total):>10}"
        )
    return 0


def cmd_show(number: int) -> int:
    invoice = db.get_invoice(number)
    if invoice is None:
        raise UnknownInvoiceError(f"unknown invoice #{number}")
    print(f"Invoice #{invoice.number}")
    print(f"Customer: {invoice.customer}")
    print(f"Date: {to_jalali(invoice.created_at)}")
    print("Items:")
    for item in invoice.items:
        print(
            f"  {item.description} x {item.qty} @ {item.unit_price} = {item.line_total}"
        )
    print(f"Subtotal: {fmt_money(invoice.subtotal)}")
    print(f"Discount: {fmt_money(Decimal(invoice.discount))}")
    print(f"Tax ({fmt_money(Decimal(invoice.tax_pct))}%): {fmt_money(invoice.tax_amount)}")
    print(f"Total: {fmt_money(invoice.total)}")
    return 0


def cmd_render(number: int, output: str | None, pdf: bool = False) -> int:
    invoice = db.get_invoice(number)
    if invoice is None:
        raise UnknownInvoiceError(f"unknown invoice #{number}")
    if pdf:
        if output is None:
            raise FactorError("--pdf requires -o/--output (binary PDF to stdout "
                              "is not supported)")
        Path(output).write_bytes(render_invoice_pdf(invoice))
        return 0
    document = render_invoice_html(invoice)
    if output is None:
        print(document, end="")
        return 0
    Path(output).write_text(document, encoding="utf-8")
    return 0


def cmd_customer_add(name: str, phone: str = "", address: str = "") -> int:
    clean = name.strip()
    if not clean:
        raise FactorError("customer name must not be empty")
    try:
        customer = db.add_customer(clean, phone=phone, address=address)
    except db.DuplicateCustomerError as exc:
        raise FactorError(str(exc)) from None
    except ValueError as exc:
        raise FactorError(str(exc)) from None
    print(customer.id)
    return 0


def cmd_customer_list() -> int:
    customers = db.list_customers()
    if not customers:
        print("No customers.")
        return 0
    print(f"{'ID':>4}  {'Name':<20}  {'Phone':<15}  Address")
    for c in customers:
        print(f"{c.id:>4}  {c.name:<20}  {c.phone:<15}  {c.address}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)  # argparse errors exit 2, no traceback
    try:
        if args.command == "new":
            return cmd_new(args.customer, args.item, args.tax, args.discount)
        if args.command == "list":
            return cmd_list()
        if args.command == "show":
            return cmd_show(args.number)
        if args.command == "render":
            return cmd_render(args.number, args.output, pdf=args.pdf)
        if args.command == "customer":
            if args.customer_command == "add":
                return cmd_customer_add(args.name, args.phone, args.address)
            if args.customer_command == "list":
                return cmd_customer_list()
    except FactorError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return exc.exit_code
    return 0  # unreachable; subparsers required=True


if __name__ == "__main__":
    raise SystemExit(main())
