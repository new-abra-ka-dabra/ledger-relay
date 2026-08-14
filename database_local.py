"""
Access to the existing ledger.db SQLite database — now READ + WRITE.

Writes only happen through the explicit save/update/delete/closing functions,
each of which mirrors cashbook.py exactly (same SQL, same audit_log rows) so
the desktop app and the web app stay fully consistent.

The SQLite file stays on the PC. The phone never touches it directly — it only
talks to FastAPI over HTTP.
"""

import os
import sqlite3
from datetime import date, datetime

# ── Locate the existing ledger.db ──────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.path.dirname(_HERE), "ledger.db")


def _connect_ro() -> sqlite3.Connection:
    """Open the existing database READ-ONLY (used for all reads)."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"ledger.db not found at: {DB_PATH}\n"
            "Make sure web_server/ is placed in the same folder as cashbook.py "
            "and that ledger.db exists next to it."
        )
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _connect_rw() -> sqlite3.Connection:
    """Open the existing database READ-WRITE (used only for writes)."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"ledger.db not found at: {DB_PATH}")
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    con.row_factory = sqlite3.Row
    return con


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _audit(cur, action, ledger_date, side=None, entry_id=None,
           description=None, amount=None,
           old_description=None, old_amount=None, master_edit=False):
    """Write one audit_log row — identical schema to cashbook._audit."""
    cur.execute(
        """
        INSERT INTO audit_log
          (ts, action, ledger_date, side, entry_id,
           description, amount, old_description, old_amount, master_edit)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (_now(), action, ledger_date, side, entry_id,
         description, amount, old_description, old_amount,
         1 if master_edit else 0),
    )


def today_iso() -> str:
    return date.today().isoformat()


# ── Reads ───────────────────────────────────────────────────────────────────

def load_entries(d: str):
    """Return (received, paid) lists of dicts for a YYYY-MM-DD date."""
    con = _connect_ro()
    cur = con.cursor()
    cur.execute(
        """SELECT id, description, amount FROM ledger
           WHERE ledger_date=? AND side='R' ORDER BY sort_order, id""", (d,))
    received = [{"id": r["id"], "description": r["description"],
                 "amount": float(r["amount"] or 0)} for r in cur.fetchall()]
    cur.execute(
        """SELECT id, description, amount FROM ledger
           WHERE ledger_date=? AND side='P' ORDER BY sort_order, id""", (d,))
    paid = [{"id": r["id"], "description": r["description"],
             "amount": float(r["amount"] or 0)} for r in cur.fetchall()]
    con.close()
    return received, paid


def load_closing(d: str):
    con = _connect_ro()
    cur = con.cursor()
    cur.execute("SELECT shree_purant FROM closing WHERE ledger_date=?", (d,))
    row = cur.fetchone()
    con.close()
    return float(row["shree_purant"]) if row else None


def get_prev_closing(d: str) -> float:
    con = _connect_ro()
    cur = con.cursor()
    cur.execute(
        """SELECT shree_purant FROM closing
           WHERE ledger_date < ? ORDER BY ledger_date DESC LIMIT 1""", (d,))
    row = cur.fetchone()
    con.close()
    return float(row["shree_purant"]) if row else 0.0


def all_dates():
    con = _connect_ro()
    cur = con.cursor()
    cur.execute("""
        SELECT DISTINCT ledger_date FROM (
            SELECT ledger_date FROM ledger
            UNION SELECT ledger_date FROM closing
        ) ORDER BY ledger_date DESC
    """)
    rows = cur.fetchall()
    con.close()
    return [r[0] for r in rows]


def load_audit(limit: int = 200):
    con = _connect_ro()
    cur = con.cursor()
    cur.execute(
        """SELECT ts, action, ledger_date, side, entry_id,
                  description, amount, old_description, old_amount, master_edit
           FROM audit_log
           WHERE action != 'INSERT'
           ORDER BY id DESC LIMIT ?""", (limit,))
    rows = cur.fetchall()
    con.close()
    return [dict(r) for r in rows]


def get_summary(d: str):
    """Full snapshot for a date: opening, received[], paid[], closing, totals."""
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


# ── Writes (mirror cashbook.py — each writes an audit_log row) ─────────────

def save_entry(d: str, side: str, desc: str, amount: float, order: int) -> int:
    con = _connect_rw()
    cur = con.cursor()
    cur.execute(
        """INSERT INTO ledger (ledger_date, side, description, amount, sort_order)
           VALUES (?,?,?,?,?)""",
        (d, side, desc, amount, order))
    new_id = cur.lastrowid
    _audit(cur, "INSERT", d, side, new_id, desc, amount)
    con.commit()
    con.close()
    return new_id


def update_entry(eid: int, new_desc: str, new_amount: float):
    con = _connect_rw()
    cur = con.cursor()
    cur.execute("SELECT ledger_date, side, description, amount FROM ledger WHERE id=?", (eid,))
    row = cur.fetchone()
    if not row:
        con.close()
        return False
    old_date, old_side, old_desc, old_amt = row[0], row[1], row[2], row[3]
    cur.execute("UPDATE ledger SET description=?, amount=? WHERE id=?",
                (new_desc, new_amount, eid))
    _audit(cur, "UPDATE", old_date, old_side, eid,
           new_desc, new_amount, old_desc, old_amt)
    con.commit()
    con.close()
    return True


def delete_entry(eid: int):
    con = _connect_rw()
    cur = con.cursor()
    cur.execute("SELECT ledger_date, side, description, amount FROM ledger WHERE id=?", (eid,))
    row = cur.fetchone()
    if not row:
        con.close()
        return False
    old_date, old_side, old_desc, old_amt = row[0], row[1], row[2], row[3]
    cur.execute("DELETE FROM ledger WHERE id=?", (eid,))
    _audit(cur, "DELETE", old_date, old_side, eid, old_desc, old_amt)
    con.commit()
    con.close()
    return True


def save_closing(d: str, val: float):
    con = _connect_rw()
    cur = con.cursor()
    cur.execute("SELECT shree_purant FROM closing WHERE ledger_date=?", (d,))
    old_row = cur.fetchone()
    old_val = old_row[0] if old_row else None
    cur.execute(
        """INSERT INTO closing (ledger_date, shree_purant) VALUES (?,?)
           ON CONFLICT(ledger_date) DO UPDATE SET shree_purant=excluded.shree_purant""",
        (d, val))
    _audit(cur, "CLOSING", d, None, None,
           f"Closing Shree Purant = {val}", val,
           f"Closing Shree Purant = {old_val}" if old_val is not None else None,
           old_val)
    con.commit()
    con.close()



def entry_date_side(eid: int):
    con = _connect_ro(); cur = con.cursor()
    cur.execute("SELECT ledger_date, side FROM ledger WHERE id=?", (eid,))
    row = cur.fetchone(); con.close()
    return dict(row) if row else None
