"""SQLite persistence for factor. Money stored as TEXT quantized to 2dp."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from factor.money import CENT, compute_totals


class DuplicateCustomerError(Exception):
    """Raised when a customer name already exists."""


class DatabaseError(Exception):
    """Raised when the data dir or DB file cannot be used (clean message)."""


@dataclass
class Customer:
    id: int
    name: str
    phone: str = ""
    address: str = ""

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY,
    number INTEGER UNIQUE NOT NULL,
    customer TEXT NOT NULL,
    created_at TEXT NOT NULL,
    tax_pct TEXT NOT NULL DEFAULT '0.00',
    discount TEXT NOT NULL DEFAULT '0.00',
    customer_id INTEGER NULL REFERENCES customers(id),
    status TEXT NOT NULL DEFAULT 'issued'
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    description TEXT NOT NULL,
    qty TEXT NOT NULL,
    unit_price TEXT NOT NULL,
    line_total TEXT NOT NULL
);
"""


@dataclass
class NewItem:
    description: str
    qty: Decimal
    unit_price: Decimal
    line_total: Decimal


@dataclass
class InvoiceItem:
    description: str
    qty: str
    unit_price: str
    line_total: str


@dataclass
class Invoice:
    number: int
    customer: str
    created_at: str
    items: list[InvoiceItem] = field(default_factory=list)
    tax_pct: str = "0.00"
    discount: str = "0.00"
    customer_id: int | None = None
    status: str = "issued"

    @property
    def subtotal(self) -> Decimal:
        subtotal = Decimal("0.00")
        for item in self.items:
            subtotal += Decimal(item.line_total)
        return subtotal

    @property
    def taxable(self) -> Decimal:
        return compute_totals(self.subtotal, Decimal(self.discount), Decimal(self.tax_pct))[0]

    @property
    def tax_amount(self) -> Decimal:
        return compute_totals(self.subtotal, Decimal(self.discount), Decimal(self.tax_pct))[1]

    @property
    def total(self) -> Decimal:
        return compute_totals(self.subtotal, Decimal(self.discount), Decimal(self.tax_pct))[2]


def get_data_dir() -> Path:
    override = os.environ.get("FACTOR_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".factor"


def get_db_path() -> Path:
    return get_data_dir() / "factor.db"


def _migrate(conn: sqlite3.Connection) -> None:
    """Add v0.2.0/v0.4.0 columns to pre-existing DBs (ALTER TABLE, losslessly)."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(invoices)").fetchall()}
    if "tax_pct" not in cols:
        conn.execute(
            "ALTER TABLE invoices ADD COLUMN tax_pct TEXT NOT NULL DEFAULT '0.00'"
        )
    if "discount" not in cols:
        conn.execute(
            "ALTER TABLE invoices ADD COLUMN discount TEXT NOT NULL DEFAULT '0.00'"
        )
    if "customer_id" not in cols:
        conn.execute("ALTER TABLE invoices ADD COLUMN customer_id INTEGER NULL")
    if "status" not in cols:
        conn.execute("ALTER TABLE invoices ADD COLUMN status TEXT NOT NULL DEFAULT 'issued'")


def connect() -> sqlite3.Connection:
    path = get_db_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DatabaseError(
            f"cannot use data directory {path.parent}: {exc.strerror or exc}"
        ) from None
    try:
        conn = sqlite3.connect(str(path))
    except sqlite3.Error as exc:
        raise DatabaseError(f"cannot open database {path}: {exc}") from None
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA)
        _migrate(conn)
    except sqlite3.Error as exc:
        conn.close()
        raise DatabaseError(
            f"database {path} is corrupt or unreadable ({exc})"
        ) from None
    return conn


def add_customer(name: str, phone: str = "", address: str = "") -> Customer:
    """Insert a customer; duplicate name raises DuplicateCustomerError."""
    clean = name.strip()
    if not clean:
        raise ValueError("customer name must not be empty")
    try:
        with connect() as conn:
            try:
                cur = conn.execute(
                    "INSERT INTO customers (name, phone, address) VALUES (?, ?, ?)",
                    (clean, phone, address),
                )
            except sqlite3.IntegrityError:
                raise DuplicateCustomerError(
                    f"customer {clean!r} already exists"
                ) from None
            cid = cur.lastrowid
    except DatabaseError:
        raise
    except sqlite3.Error as exc:
        raise DatabaseError(f"database error: {exc}") from None
    assert cid is not None
    return Customer(id=int(cid), name=clean, phone=phone, address=address)


def list_customers() -> list[Customer]:
    try:
        with connect() as conn:
            rows = conn.execute("SELECT * FROM customers ORDER BY id").fetchall()
            return [
                Customer(id=int(r["id"]), name=r["name"], phone=r["phone"] or "",
                         address=r["address"] or "")
                for r in rows
            ]
    except DatabaseError:
        raise
    except sqlite3.Error as exc:
        raise DatabaseError(f"database error: {exc}") from None


def find_customer_by_name(name: str) -> Customer | None:
    try:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM customers WHERE name = ?", (name,)
            ).fetchone()
            if row is None:
                return None
            return Customer(
                id=int(row["id"]), name=row["name"],
                phone=row["phone"] or "", address=row["address"] or "",
            )
    except DatabaseError:
        raise
    except sqlite3.Error as exc:
        raise DatabaseError(f"database error: {exc}") from None


def create_invoice(
    customer: str,
    items: list[NewItem],
    tax_pct: Decimal = Decimal("0.00"),
    discount: Decimal = Decimal("0.00"),
) -> Invoice:
    """Insert one invoice atomically; assign MAX(number)+1 so numbers are
    sequential, monotonic, and never reused. Caller must validate first."""
    tax_pct = tax_pct.quantize(CENT, rounding=ROUND_HALF_UP)
    discount = discount.quantize(CENT, rounding=ROUND_HALF_UP)
    created_at = datetime.now(UTC).isoformat(timespec="seconds")
    with connect() as conn:
        row = conn.execute("SELECT COALESCE(MAX(number), 0) FROM invoices").fetchone()
        number = int(row[0]) + 1
        cur = conn.execute(
            "INSERT INTO invoices (number, customer, created_at, tax_pct, discount)"
            " VALUES (?, ?, ?, ?, ?)",
            (number, customer, created_at, str(tax_pct), str(discount)),
        )
        invoice_id = cur.lastrowid
        cust = conn.execute(
            "SELECT id FROM customers WHERE name = ?", (customer,)
        ).fetchone()
        customer_id: int | None = int(cust["id"]) if cust is not None else None
        if customer_id is not None:
            conn.execute(
                "UPDATE invoices SET customer_id = ? WHERE id = ?",
                (customer_id, invoice_id),
            )
        stored: list[InvoiceItem] = []
        for item in items:
            conn.execute(
                "INSERT INTO items (invoice_id, description, qty, unit_price, line_total)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    invoice_id,
                    item.description,
                    str(item.qty),
                    str(item.unit_price),
                    str(item.line_total),
                ),
            )
            stored.append(
                InvoiceItem(
                    description=item.description,
                    qty=str(item.qty),
                    unit_price=str(item.unit_price),
                    line_total=str(item.line_total),
                )
            )
    return Invoice(
        number=number,
        customer=customer,
        created_at=created_at,
        items=stored,
        tax_pct=str(tax_pct),
        discount=str(discount),
        customer_id=customer_id,
    )


def _row_to_invoice(row: sqlite3.Row, item_rows: list[sqlite3.Row]) -> Invoice:
    keys = set(row.keys())
    return Invoice(
        number=int(row["number"]),
        customer=row["customer"],
        created_at=row["created_at"],
        items=[
            InvoiceItem(
                description=r["description"],
                qty=r["qty"],
                unit_price=r["unit_price"],
                line_total=r["line_total"],
            )
            for r in item_rows
        ],
        tax_pct=row["tax_pct"] if "tax_pct" in keys else "0.00",
        discount=row["discount"] if "discount" in keys else "0.00",
        customer_id=int(row["customer_id"])
        if "customer_id" in keys and row["customer_id"] is not None
        else None,
        status=row["status"] if "status" in keys else "issued",
    )


def list_invoices() -> list[Invoice]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM invoices ORDER BY number").fetchall()
        result = []
        for row in rows:
            items = conn.execute(
                "SELECT * FROM items WHERE invoice_id = ? ORDER BY id",
                (row["id"],),
            ).fetchall()
            result.append(_row_to_invoice(row, items))
    return result


def get_invoice(number: int) -> Invoice | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM invoices WHERE number = ?", (number,)
        ).fetchone()
        if row is None:
            return None
        items = conn.execute(
            "SELECT * FROM items WHERE invoice_id = ? ORDER BY id",
            (row["id"],),
        ).fetchall()
        return _row_to_invoice(row, items)


def set_invoice_status(number: int, status: str) -> Invoice:
    """Mark an invoice paid or void. Returns the updated invoice.

    Raises ValueError for unknown numbers, invalid statuses, and
    illegal transitions (pay requires 'issued'; void requires
    'issued' or 'paid').
    """
    if status not in ("paid", "void"):
        raise ValueError(f"invalid status {status!r}")
    with connect() as conn:
        row = conn.execute(
            "SELECT status FROM invoices WHERE number = ?", (number,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown invoice #{number}")
        current = row["status"]
        if status == "paid":
            if current != "issued":
                raise ValueError(f"cannot pay invoice #{number}: status is {current}")
        elif current == "void":
            raise ValueError(f"invoice #{number} is already void")
        conn.execute(
            "UPDATE invoices SET status = ? WHERE number = ?", (status, number)
        )
    updated = get_invoice(number)
    assert updated is not None
    return updated


def count_invoices() -> int:
    with connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0])
