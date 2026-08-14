"""
FastAPI web server for the Petty Cash Ledger — writable ledger + credit ledger
+ Google-auth login (email whitelist, 30-day session cookie).

    Run from inside the web_server/ folder:

        uvicorn main:app --host 0.0.0.0 --port $PORT

    Set DATABASE_URL and the Google OAuth variables in the hosting environment.
"""

import os

from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

import database
import credit
from auth import router as auth_router, get_current_user

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-me")
if SESSION_SECRET == "dev-secret-change-me" and os.getenv("PUBLIC_BASE_URL", "").startswith("https://"):
    raise RuntimeError("SESSION_SECRET must be set for the hosted Render service.")

app = FastAPI(title="Petty Cash Ledger")

# Signed session cookie — stored on the device, valid 30 days.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    max_age=30 * 24 * 3600,   # 30 days
    same_site="lax",
    https_only=os.getenv("PUBLIC_BASE_URL", "").startswith("https://"),
)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

database.init_db()
credit.init_db()

# Auth routes (public): /login, /auth/login, /auth/callback, /logout
app.include_router(auth_router)


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 401:
        if request.url.path.startswith("/api"):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    if exc.status_code == 403:
        return HTMLResponse(
            f"<h2>403 — Access denied</h2><p>{exc.detail}</p>"
            f"<p><a href='/logout'>Try another account</a></p>",
            status_code=403,
        )
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


# ── Request models ───────────────────────────────────────────────────────────

class EntryIn(BaseModel):
    side: str
    description: str
    amount: float


class EntryUpdate(BaseModel):
    description: str
    amount: float


class ClosingIn(BaseModel):
    amount: float


class CreditEntryIn(BaseModel):
    party: str
    side: str
    description: str
    amount: float


class CreditEntryUpdate(BaseModel):
    party: str
    side: str
    description: str
    amount: float


def _require_today(d: str):
    if d != database.today_iso():
        raise HTTPException(status_code=403, detail="Editing is locked for past dates (today only).")


def _entry_date_side(eid: int):
    con = database._connect_ro()
    cur = con.cursor()
    cur.execute("SELECT ledger_date, side FROM ledger WHERE id=?", (eid,))
    row = cur.fetchone()
    con.close()
    return dict(row) if row else None


# ── HTML pages (protected) ────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
def index(request: Request, date: str = Query(default=None)):
    d = date or database.today_iso()
    summary = database.get_summary(d)
    return templates.TemplateResponse(
        request, "index.html",
        {"summary": summary, "user": request.session.get("user")},
    )


@app.get("/credit", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
def credit_page(request: Request, date: str = Query(default=None)):
    d = date or credit.today_iso()
    summary = credit.get_summary(d)
    return templates.TemplateResponse(
        request, "credit.html",
        {"summary": summary, "user": request.session.get("user")},
    )


# ── Cashbook JSON API (protected) ────────────────────────────────────────────

@app.get("/api/summary", dependencies=[Depends(get_current_user)])
def api_summary(date: str = Query(default=None)):
    return JSONResponse(database.get_summary(date or database.today_iso()))


@app.get("/api/dates", dependencies=[Depends(get_current_user)])
def api_dates():
    return JSONResponse(database.all_dates())


@app.get("/api/audit", dependencies=[Depends(get_current_user)])
def api_audit():
    return JSONResponse(database.load_audit(200))


@app.post("/api/entry", dependencies=[Depends(get_current_user)])
def api_add_entry(payload: EntryIn):
    if payload.side not in ("R", "P"):
        raise HTTPException(status_code=400, detail="side must be 'R' or 'P'")
    if not payload.description.strip():
        raise HTTPException(status_code=400, detail="description is required")
    if payload.amount < 0:
        raise HTTPException(status_code=400, detail="amount must be >= 0")
    d = database.today_iso()
    _require_today(d)
    rec, paid = database.load_entries(d)
    order = len(rec) if payload.side == "R" else len(paid)
    new_id = database.save_entry(d, payload.side, payload.description.strip(), payload.amount, order)
    return JSONResponse({"id": new_id, "summary": database.get_summary(d)})


@app.put("/api/entry/{eid}", dependencies=[Depends(get_current_user)])
def api_update_entry(eid: int, payload: EntryUpdate):
    if not payload.description.strip():
        raise HTTPException(status_code=400, detail="description is required")
    if payload.amount < 0:
        raise HTTPException(status_code=400, detail="amount must be >= 0")
    row = _entry_date_side(eid)
    if not row:
        raise HTTPException(status_code=404, detail="entry not found")
    _require_today(row["ledger_date"])
    database.update_entry(eid, payload.description.strip(), payload.amount)
    return JSONResponse({"summary": database.get_summary(database.today_iso())})


@app.delete("/api/entry/{eid}", dependencies=[Depends(get_current_user)])
def api_delete_entry(eid: int):
    row = _entry_date_side(eid)
    if not row:
        raise HTTPException(status_code=404, detail="entry not found")
    _require_today(row["ledger_date"])
    database.delete_entry(eid)
    return JSONResponse({"summary": database.get_summary(database.today_iso())})


@app.post("/api/closing", dependencies=[Depends(get_current_user)])
def api_closing(payload: ClosingIn):
    if payload.amount < 0:
        raise HTTPException(status_code=400, detail="amount must be >= 0")
    d = database.today_iso()
    database.save_closing(d, payload.amount)
    return JSONResponse({"summary": database.get_summary(d)})


@app.get("/api/health", dependencies=[Depends(get_current_user)])
def health():
    return {"status": "ok", "today": database.today_iso()}


# ── Credit JSON API (protected) ───────────────────────────────────────────────

@app.get("/api/credit/summary", dependencies=[Depends(get_current_user)])
def api_credit_summary(date: str = Query(default=None)):
    return JSONResponse(credit.get_summary(date or credit.today_iso()))


@app.get("/api/credit/parties", dependencies=[Depends(get_current_user)])
def api_credit_parties():
    return JSONResponse(credit.party_balances())


@app.get("/api/credit/all", dependencies=[Depends(get_current_user)])
def api_credit_all():
    return JSONResponse(credit.all_entries())


@app.post("/api/credit/entry", dependencies=[Depends(get_current_user)])
def api_credit_add(payload: CreditEntryIn):
    if payload.side not in ("G", "R"):
        raise HTTPException(status_code=400, detail="side must be 'G' or 'R'")
    if not payload.party.strip():
        raise HTTPException(status_code=400, detail="party is required")
    if payload.amount < 0:
        raise HTTPException(status_code=400, detail="amount must be >= 0")
    d = credit.today_iso()
    entries = credit.load_entries(d)
    nid = credit.add_entry(d, payload.party.strip(), payload.side,
                           payload.description.strip(), payload.amount, len(entries))
    return JSONResponse({"id": nid, "summary": credit.get_summary(d)})


@app.put("/api/credit/entry/{eid}", dependencies=[Depends(get_current_user)])
def api_credit_update(eid: int, payload: CreditEntryUpdate):
    if payload.side not in ("G", "R"):
        raise HTTPException(status_code=400, detail="side must be 'G' or 'R'")
    if not payload.party.strip():
        raise HTTPException(status_code=400, detail="party is required")
    if payload.amount < 0:
        raise HTTPException(status_code=400, detail="amount must be >= 0")
    credit.update_entry(eid, payload.party.strip(), payload.side,
                        payload.description.strip(), payload.amount)
    return JSONResponse({"summary": credit.get_summary(credit.today_iso())})


@app.delete("/api/credit/entry/{eid}", dependencies=[Depends(get_current_user)])
def api_credit_delete(eid: int):
    credit.delete_entry(eid)
    return JSONResponse({"summary": credit.get_summary(credit.today_iso())})