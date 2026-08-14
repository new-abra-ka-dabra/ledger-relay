"""
Render-side credit database client. credit.db remains on the private PC.
"""
import os, httpx
from dotenv import load_dotenv
load_dotenv()
DATA_API_URL=os.getenv("DATA_API_URL","").rstrip("/")
DATA_API_TOKEN=os.getenv("DATA_API_TOKEN","")
def _request(method,path,**kwargs):
    if not DATA_API_URL or not DATA_API_TOKEN: raise RuntimeError("DATA_API_URL and DATA_API_TOKEN must be configured.")
    headers=kwargs.pop("headers",{}); headers["X-Data-Token"]=DATA_API_TOKEN
    try:
        with httpx.Client(base_url=DATA_API_URL,timeout=20.0) as c:
            r=c.request(method,path,headers=headers,**kwargs); r.raise_for_status(); return r.json()
    except httpx.HTTPError as e: raise RuntimeError(f"Private database server unavailable: {e}") from e
def init_db(): return None
def today_iso(): return _request("GET","/internal/today")["today"]
def load_entries(d): return _request("GET","/internal/credit/entries",params={"date":d})
def party_balances(): return _request("GET","/internal/credit/parties")
def all_entries(): return _request("GET","/internal/credit/all")
def add_entry(d,party,side,desc,amount,order): return _request("POST","/internal/credit/entry",json={"date":d,"party":party,"side":side,"description":desc,"amount":amount,"order":order})["id"]
def update_entry(eid,party,side,desc,amount): return _request("PUT",f"/internal/credit/entry/{eid}",json={"party":party,"side":side,"description":desc,"amount":amount})["ok"]
def delete_entry(eid): return _request("DELETE",f"/internal/credit/entry/{eid}")["ok"]
def get_summary(d): return _request("GET","/internal/credit/summary",params={"date":d})
