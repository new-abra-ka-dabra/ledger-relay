"""
Render-side database client. SQLite remains on the private PC.
"""
import os
import httpx
from dotenv import load_dotenv
load_dotenv()
DATA_API_URL=os.getenv("DATA_API_URL","").rstrip("/")
DATA_API_TOKEN=os.getenv("DATA_API_TOKEN","")
def _request(method,path,**kwargs):
    if not DATA_API_URL or not DATA_API_TOKEN:
        raise RuntimeError("DATA_API_URL and DATA_API_TOKEN must be configured.")
    headers=kwargs.pop("headers",{})
    headers["X-Data-Token"]=DATA_API_TOKEN
    try:
        with httpx.Client(base_url=DATA_API_URL,timeout=20.0) as c:
            r=c.request(method,path,headers=headers,**kwargs); r.raise_for_status(); return r.json()
    except httpx.HTTPError as e:
        raise RuntimeError(f"Private database server unavailable: {e}") from e
def today_iso(): return _request("GET","/internal/today")["today"]
def load_entries(d):
    x=_request("GET","/internal/ledger/entries",params={"date":d}); return x["received"],x["paid"]
def load_closing(d): return _request("GET","/internal/ledger/closing",params={"date":d})["closing"]
def get_prev_closing(d): return _request("GET","/internal/ledger/previous-closing",params={"date":d})["value"]
def all_dates(): return _request("GET","/internal/ledger/dates")
def load_audit(limit=200): return _request("GET","/internal/ledger/audit",params={"limit":limit})
def get_summary(d): return _request("GET","/internal/ledger/summary",params={"date":d})
def save_entry(d,side,desc,amount,order): return _request("POST","/internal/ledger/entry",json={"date":d,"side":side,"description":desc,"amount":amount,"order":order})["id"]
def entry_date_side(eid): return _request("GET",f"/internal/ledger/entry/{eid}")["entry"]
def update_entry(eid,new_desc,new_amount): return _request("PUT",f"/internal/ledger/entry/{eid}",json={"description":new_desc,"amount":new_amount})["ok"]
def delete_entry(eid): return _request("DELETE",f"/internal/ledger/entry/{eid}")["ok"]
def save_closing(d,val): return _request("POST","/internal/ledger/closing",json={"date":d,"amount":val})["ok"]
def _connect_ro(): raise RuntimeError("SQLite is intentionally kept on the private PC.")
