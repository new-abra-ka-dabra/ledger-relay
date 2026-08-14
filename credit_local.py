"""
Credit Ledger — a separate credit.db tracking money given on credit
("udhaar") and received back, per party.

This is a NEW database (credit.db), created next to ledger.db on first run.
It does NOT touch the existing ledger.db. side values:
  'G' = given out (party now owes us)
  'R' = received back (party repaid us)
Party balance = total given − total received = how much the party still owes.
"""

import os
import sqlite3
from datetime import date

_HERE = os.path.dirname(os.path.abspath(__file__))
CREDIT_DB = os.path.join(os.path.dirname(_HERE), "credit.db")


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(CREDIT_DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    """Create credit.db + tables if they don't already exist."""
    con = _connect()
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS credit (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            credit_date TEXT NOT NULL,
            party       TEXT NOT NULL,
            side        TEXT NOT NULL,   -- 'G' given / 'R' received
            description TEXT,
            amount       REAL DEFAULT 0,
            sort_order   INTEGER DEFAULT 0
        )
        """
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_credit_date ON credit(credit_date)"
    )
    con.commit()
    con.close()


def today_iso() -> str:
    return date.today().isoformat()


def load_entries(d: str):
    con = _connect()
    cur = con.cursor()
    cur.execute(
        """SELECT id, party, side, description, amount FROM credit
           WHERE credit_date=? ORDER BY sort_order, id""",
        (d,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    for r in rows:
        r["amount"] = float(r["amount"] or 0)
    return rows


def party_balances():
    con = _connect()
    cur = con.cursor()
    cur.execute(
        """
        SELECT party,
               SUM(CASE WHEN side='G' THEN amount ELSE 0 END) AS given,
               SUM(CASE WHEN side='R' THEN amount ELSE 0 END) AS received
        FROM credit GROUP BY party ORDER BY party
        """
    )
    rows = cur.fetchall()
    con.close()
    out = []
    for r in rows:
        given = float(r["given"] or 0)
        received = float(r["received"] or 0)
        out.append(
            {
                "party": r["party"],
                "given": round(given, 2),
                "received": round(received, 2),
                "balance": round(given - received, 2),
            }
        )
    return out


def all_entries():
    """Return every credit entry (all dates), newest first."""
    con = _connect()
    cur = con.cursor()
    cur.execute(
        """SELECT id, credit_date, party, side, description, amount
           FROM credit ORDER BY id DESC"""
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    for r in rows:
        r["amount"] = float(r["amount"] or 0)
    return rows


def add_entry(d, party, side, desc, amount, order) -> int:
    con = _connect()
    cur = con.cursor()
    cur.execute(
        """INSERT INTO credit
           (credit_date, party, side, description, amount, sort_order)
           VALUES (?,?,?,?,?,?)""",
        (d, party, side, desc, amount, order),
    )
    nid = cur.lastrowid
    con.commit()
    con.close()
    return nid


def update_entry(eid, party, side, desc, amount):
    con = _connect()
    cur = con.cursor()
    cur.execute(
        "UPDATE credit SET party=?, side=?, description=?, amount=? WHERE id=?",
        (party, side, desc, amount, eid),
    )
    con.commit()
    con.close()


def delete_entry(eid):
    con = _connect()
    cur = con.cursor()
    cur.execute("DELETE FROM credit WHERE id=?", (eid,))
    con.commit()
    con.close()


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
