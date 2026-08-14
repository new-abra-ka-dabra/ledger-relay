"""Credit ledger access through the shared Neon PostgreSQL database."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from psycopg.rows import dict_row

from database import _connect

_HERE = Path(__file__).resolve().parent
_SQLITE_PATH = _HERE.parent / "credit.db"


def init_db() -> None:
    """Create the credit schema and import legacy credit.db once if needed."""
    with _connect() as con:
        with con.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(8142027)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS credit (
                    id BIGSERIAL PRIMARY KEY,
                    credit_date TEXT NOT NULL,
                    party TEXT NOT NULL,
                    side TEXT NOT NULL CHECK (side IN ('G', 'R')),
                    description TEXT NOT NULL DEFAULT '',
                    amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_credit_date ON credit (credit_date)"
            )
            cur.execute("SELECT COUNT(*) AS count FROM credit")
            if cur.fetchone()["count"] == 0 and _SQLITE_PATH.exists():
                _import_sqlite(con)


def _import_sqlite(con) -> None:
    """Convert the old cumulative ``credits`` table to G/R transactions."""
    with sqlite3.connect(f"file:{_SQLITE_PATH}?mode=ro", uri=True) as source:
        source.row_factory = sqlite3.Row
        source_cur = source.cursor()
        source_cur.execute(
            """
            SELECT name, description, amount, received, added_date
            FROM credits ORDER BY id
            """
        )
        with con.cursor() as cur:
            for row in source_cur.fetchall():
                cur.execute(
                    """
                    INSERT INTO credit
                      (credit_date, party, side, description, amount, sort_order)
                    VALUES (%s, %s, 'G', %s, %s, %s)
                    """,
                    (row["added_date"], row["name"], row["description"] or "",
                     row["amount"] or 0, 0),
                )
                if row["received"] and row["received"] > 0:
                    cur.execute(
                        """
                        INSERT INTO credit
                          (credit_date, party, side, description, amount, sort_order)
                        VALUES (%s, %s, 'R', %s, %s, %s)
                        """,
                        (row["added_date"], row["name"], "Imported received amount",
                         row["received"], 1),
                    )


def today_iso() -> str:
    return date.today().isoformat()


def load_entries(d: str):
    with _connect() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT id, party, side, description, amount FROM credit
                WHERE credit_date=%s ORDER BY sort_order, id
                """,
                (d,),
            )
            rows = cur.fetchall()
    return [
        {**r, "amount": float(r["amount"] or 0)}
        for r in rows
    ]


def party_balances():
    with _connect() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT party,
                       SUM(CASE WHEN side='G' THEN amount ELSE 0 END) AS given,
                       SUM(CASE WHEN side='R' THEN amount ELSE 0 END) AS received
                FROM credit GROUP BY party ORDER BY party
                """
            )
            rows = cur.fetchall()
    return [
        {
            "party": r["party"],
            "given": round(float(r["given"] or 0), 2),
            "received": round(float(r["received"] or 0), 2),
            "balance": round(float(r["given"] or 0) - float(r["received"] or 0), 2),
        }
        for r in rows
    ]


def all_entries():
    with _connect() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT id, credit_date, party, side, description, amount
                FROM credit ORDER BY id DESC
                """
            )
            rows = cur.fetchall()
    return [{**r, "amount": float(r["amount"] or 0)} for r in rows]


def add_entry(d, party, side, desc, amount, order) -> int:
    with _connect() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO credit
                  (credit_date, party, side, description, amount, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (d, party, side, desc, amount, order),
            )
            return cur.fetchone()["id"]


def update_entry(eid, party, side, desc, amount):
    with _connect() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                UPDATE credit
                SET party=%s, side=%s, description=%s, amount=%s
                WHERE id=%s
                """,
                (party, side, desc, amount, eid),
            )


def delete_entry(eid):
    with _connect() as con:
        with con.cursor() as cur:
            cur.execute("DELETE FROM credit WHERE id=%s", (eid,))


def get_summary(d: str):
    entries = load_entries(d)
    given_total = sum(e["amount"] for e in entries if e["side"] == "G")
    received_total = sum(e["amount"] for e in entries if e["side"] == "R")
    return {
        "date": d,
        "is_today": d == today_iso(),
        "entries": entries,
        "given_total": round(given_total, 2),
        "received_total": round(received_total, 2),
        "balances": party_balances(),
    }