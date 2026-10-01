"""SQLite persistence for factor. Money stored as TEXT quantized to 2dp."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY,
    number INTEGER UNIQUE NOT NULL,
    customer TEXT NOT NULL,
    created_at TEXT NOT NULL
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

    @property
    def total(self) -> Decimal:
        total = Decimal("0.00")
        for item in self.items:
            total += Decimal(item.line_total)
        return total


def get_data_dir() -> Path:
    override = os.environ.get("FACTOR_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".factor"


def get_db_path() -> Path:
    return get_data_dir() / "factor.db"


def connect() -> sqlite3.Connection:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def create_invoice(customer: str, items: list[NewItem]) -> Invoice:
    """Insert one invoice atomically; assign MAX(number)+1 so numbers are
    sequential, monotonic, and never reused. Caller must validate first."""
    created_at = datetime.now(UTC).isoformat(timespec="seconds")
    with connect() as conn:
        row = conn.execute("SELECT COALESCE(MAX(number), 0) FROM invoices").fetchone()
        number = int(row[0]) + 1
        cur = conn.execute(
            "INSERT INTO invoices (number, customer, created_at) VALUES (?, ?, ?)",
            (number, customer, created_at),
        )
        invoice_id = cur.lastrowid
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
        number=number, customer=customer, created_at=created_at, items=stored
    )


def _row_to_invoice(row: sqlite3.Row, item_rows: list[sqlite3.Row]) -> Invoice:
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


def count_invoices() -> int:
    with connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0])
