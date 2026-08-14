"""PostgreSQL access for the cashbook ledger.

The web app uses Neon through ``DATABASE_URL``.  On the first startup of an
empty database, the bundled SQLite ledger (when present) is imported once so
an existing installation can be moved to Render without losing its data.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

_HERE = Path(__file__).resolve().parent
_SQLITE_PATH = _HERE.parent / "ledger.db"


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is required. Set it to your Neon PostgreSQL connection string."
        )
    return url


def _connect():
    return psycopg.connect(_database_url(), row_factory=dict_row)


def init_db() -> None:
    """Create the schema and import the old SQLite file if Neon is empty."""
    with _connect() as con:
        with con.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(8142026)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ledger (
                    id BIGSERIAL PRIMARY KEY,
                    ledger_date TEXT NOT NULL,
                    side TEXT NOT NULL CHECK (side IN ('R', 'P')),
                    description TEXT NOT NULL,
                    amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS closing (
                    ledger_date TEXT PRIMARY KEY,
                    shree_purant DOUBLE PRECISION NOT NULL DEFAULT 0
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id BIGSERIAL PRIMARY KEY,
                    ts TEXT NOT NULL,
                    action TEXT NOT NULL,
                    ledger_date TEXT NOT NULL,
                    side TEXT,
                    entry_id BIGINT,
                    description TEXT,
                    amount DOUBLE PRECISION,
                    old_description TEXT,
                    old_amount DOUBLE PRECISION,
                    master_edit INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_ledger_date ON ledger (ledger_date)"
            )
            cur.execute(
                "SELECT COUNT(*) AS count FROM ledger"
            )
            is_empty = cur.fetchone()["count"] == 0
            if is_empty and _SQLITE_PATH.exists():
                _import_sqlite(con)


def _import_sqlite(con) -> None:
    """Import the legacy SQLite cashbook while holding the startup lock."""
    with sqlite3.connect(f"file:{_SQLITE_PATH}?mode=ro", uri=True) as source:
        source.row_factory = sqlite3.Row
        source_cur = source.cursor()
        with con.cursor() as cur:
            source_cur.execute(
                "SELECT id, ledger_date, side, description, amount, sort_order "
                "FROM ledger ORDER BY id"
            )
            for row in source_cur.fetchall():
                cur.execute(
                    """
                    INSERT INTO ledger
                      (id, ledger_date, side, description, amount, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    tuple(row),
                )

            source_cur.execute(
                "SELECT ledger_date, shree_purant FROM closing ORDER BY ledger_date"
            )
            for row in source_cur.fetchall():
                cur.execute(
                    """
                    INSERT INTO closing (ledger_date, shree_purant)
                    VALUES (%s, %s)
                    ON CONFLICT (ledger_date) DO NOTHING
                    """,
                    tuple(row),
                )

            source_cur.execute(
                """
                SELECT id, ts, action, ledger_date, side, entry_id,
                       description, amount, old_description, old_amount,
                       COALESCE(master_edit, 0) AS master_edit
                FROM audit_log ORDER BY id
                """
            )
            for row in source_cur.fetchall():
                cur.execute(
                    """
                    INSERT INTO audit_log
                      (id, ts, action, ledger_date, side, entry_id,
                       description, amount, old_description, old_amount, master_edit)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    tuple(row),
                )

            cur.execute(
                """
                SELECT setval(pg_get_serial_sequence('ledger', 'id'),
                              COALESCE((SELECT MAX(id) FROM ledger), 1), true)
                """
            )
            cur.execute(
                """
                SELECT setval(pg_get_serial_sequence('audit_log', 'id'),
                              COALESCE((SELECT MAX(id) FROM audit_log), 1), true)
                """
            )


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _audit(cur, action, ledger_date, side=None, entry_id=None,
           description=None, amount=None, old_description=None,
           old_amount=None, master_edit=False):
    cur.execute(
        """
        INSERT INTO audit_log
          (ts, action, ledger_date, side, entry_id, description, amount,
           old_description, old_amount, master_edit)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (_now(), action, ledger_date, side, entry_id, description, amount,
         old_description, old_amount, 1 if master_edit else 0),
    )


def today_iso() -> str:
    return date.today().isoformat()


def load_entries(d: str):
    with _connect() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT id, description, amount FROM ledger
                WHERE ledger_date=%s AND side='R'
                ORDER BY sort_order, id
                """,
                (d,),
            )
            received = [
                {"id": r["id"], "description": r["description"],
                 "amount": float(r["amount"] or 0)}
                for r in cur.fetchall()
            ]
            cur.execute(
                """
                SELECT id, description, amount FROM ledger
                WHERE ledger_date=%s AND side='P'
                ORDER BY sort_order, id
                """,
                (d,),
            )
            paid = [
                {"id": r["id"], "description": r["description"],
                 "amount": float(r["amount"] or 0)}
                for r in cur.fetchall()
            ]
    return received, paid


def load_closing(d: str):
    with _connect() as con:
        with con.cursor() as cur:
            cur.execute("SELECT shree_purant FROM closing WHERE ledger_date=%s", (d,))
            row = cur.fetchone()
    return float(row["shree_purant"]) if row else None


def get_prev_closing(d: str) -> float:
    with _connect() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT shree_purant FROM closing
                WHERE ledger_date < %s ORDER BY ledger_date DESC LIMIT 1
                """,
                (d,),
            )
            row = cur.fetchone()
    return float(row["shree_purant"]) if row else 0.0


def all_dates():
    with _connect() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ledger_date FROM (
                    SELECT ledger_date FROM ledger
                    UNION SELECT ledger_date FROM closing
                ) dates ORDER BY ledger_date DESC
                """
            )
            return [r["ledger_date"] for r in cur.fetchall()]


def load_audit(limit: int = 200):
    with _connect() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT ts, action, ledger_date, side, entry_id, description,
                       amount, old_description, old_amount, master_edit
                FROM audit_log
                WHERE action != 'INSERT'
                ORDER BY id DESC LIMIT %s
                """,
                (limit,),
            )
            return cur.fetchall()


def get_summary(d: str):
    received, paid = load_entries(d)
    closing = load_closing(d)
    opening = get_prev_closing(d)
    received_total = sum(e["amount"] for e in received)
    paid_total = sum(e["amount"] for e in paid)
    return {
        "date": d,
        "is_today": d == today_iso(),
        "opening": round(opening, 2),
        "received": received,
        "paid": paid,
        "closing": round(closing, 2) if closing is not None else None,
        "received_total": round(received_total, 2),
        "paid_total": round(paid_total, 2),
    }


def save_entry(d: str, side: str, desc: str, amount: float, order: int) -> int:
    with _connect() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ledger
                  (ledger_date, side, description, amount, sort_order)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
                """,
                (d, side, desc, amount, order),
            )
            new_id = cur.fetchone()["id"]
            _audit(cur, "INSERT", d, side, new_id, desc, amount)
    return new_id


def update_entry(eid: int, new_desc: str, new_amount: float):
    with _connect() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT ledger_date, side, description, amount
                FROM ledger WHERE id=%s
                """,
                (eid,),
            )
            row = cur.fetchone()
            if not row:
                return False
            cur.execute(
                "UPDATE ledger SET description=%s, amount=%s WHERE id=%s",
                (new_desc, new_amount, eid),
            )
            _audit(cur, "UPDATE", row["ledger_date"], row["side"], eid,
                   new_desc, new_amount, row["description"], row["amount"])
    return True


def delete_entry(eid: int):
    with _connect() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT ledger_date, side, description, amount
                FROM ledger WHERE id=%s
                """,
                (eid,),
            )
            row = cur.fetchone()
            if not row:
                return False
            cur.execute("DELETE FROM ledger WHERE id=%s", (eid,))
            _audit(cur, "DELETE", row["ledger_date"], row["side"], eid,
                   row["description"], row["amount"])
    return True


def save_closing(d: str, val: float):
    with _connect() as con:
        with con.cursor() as cur:
            cur.execute(
                "SELECT shree_purant FROM closing WHERE ledger_date=%s", (d,)
            )
            old_row = cur.fetchone()
            old_val = old_row["shree_purant"] if old_row else None
            cur.execute(
                """
                INSERT INTO closing (ledger_date, shree_purant) VALUES (%s, %s)
                ON CONFLICT (ledger_date)
                DO UPDATE SET shree_purant=EXCLUDED.shree_purant
                """,
                (d, val),
            )
            _audit(
                cur, "CLOSING", d, description=f"Closing Shree Purant = {val}",
                amount=val,
                old_description=(
                    f"Closing Shree Purant = {old_val}"
                    if old_val is not None else None
                ),
                old_amount=old_val,
            )