"""Private PC data API. Keep this file and the SQLite DBs on your PC."""
import os
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()
TOKEN=os.getenv("DATA_API_TOKEN","")
app=FastAPI(title="Private Ledger Data API")
def check(t):
    if not TOKEN or t!=TOKEN: raise HTTPException(401,"Unauthorized")
import database_local as database
import credit_local as credit
credit.init_db()
class LedgerEntry(BaseModel): date:str; side:str; description:str; amount:float; order:int
class LedgerUpdate(BaseModel): description:str; amount:float
class Closing(BaseModel): date:str; amount:float
class CreditEntry(BaseModel): date:str; party:str; side:str; description:str; amount:float; order:int
class CreditUpdate(BaseModel): party:str; side:str; description:str; amount:float
def dep(x_data_token): check(x_data_token)
@app.get("/internal/today")
def today(x_data_token:str|None=Header(None)): dep(x_data_token); return {"today":database.today_iso()}
@app.get("/internal/ledger/entries")
def le(date:str,x_data_token:str|None=Header(None)): dep(x_data_token); r,p=database.load_entries(date); return {"received":r,"paid":p}
@app.get("/internal/ledger/summary")
def ls(date:str,x_data_token:str|None=Header(None)): dep(x_data_token); return database.get_summary(date)
@app.get("/internal/ledger/closing")
def lc(date:str,x_data_token:str|None=Header(None)): dep(x_data_token); return {"closing":database.load_closing(date)}
@app.get("/internal/ledger/previous-closing")
def lp(date:str,x_data_token:str|None=Header(None)): dep(x_data_token); return {"value":database.get_prev_closing(date)}
@app.get("/internal/ledger/dates")
def ld(x_data_token:str|None=Header(None)): dep(x_data_token); return database.all_dates()
@app.get("/internal/ledger/audit")
def la(limit:int=200,x_data_token:str|None=Header(None)): dep(x_data_token); return database.load_audit(limit)
@app.get("/internal/ledger/entry/{eid}")
def leg(eid:int,x_data_token:str|None=Header(None)): dep(x_data_token); return {"entry":database.entry_date_side(eid)}
@app.post("/internal/ledger/entry")
def ladd(p:LedgerEntry,x_data_token:str|None=Header(None)): dep(x_data_token); return {"id":database.save_entry(p.date,p.side,p.description,p.amount,p.order)}
@app.put("/internal/ledger/entry/{eid}")
def lup(eid:int,p:LedgerUpdate,x_data_token:str|None=Header(None)): dep(x_data_token); return {"ok":database.update_entry(eid,p.description,p.amount)}
@app.delete("/internal/ledger/entry/{eid}")
def ldel(eid:int,x_data_token:str|None=Header(None)): dep(x_data_token); return {"ok":database.delete_entry(eid)}
@app.post("/internal/ledger/closing")
def lclose(p:Closing,x_data_token:str|None=Header(None)): dep(x_data_token); database.save_closing(p.date,p.amount); return {"ok":True}
@app.get("/internal/credit/entries")
def ce(date:str,x_data_token:str|None=Header(None)): dep(x_data_token); return credit.load_entries(date)
@app.get("/internal/credit/parties")
def cp(x_data_token:str|None=Header(None)): dep(x_data_token); return credit.party_balances()
@app.get("/internal/credit/all")
def ca(x_data_token:str|None=Header(None)): dep(x_data_token); return credit.all_entries()
@app.get("/internal/credit/summary")
def cs(date:str,x_data_token:str|None=Header(None)): dep(x_data_token); return credit.get_summary(date)
@app.post("/internal/credit/entry")
def cadd(p:CreditEntry,x_data_token:str|None=Header(None)): dep(x_data_token); return {"id":credit.add_entry(p.date,p.party,p.side,p.description,p.amount,p.order)}
@app.put("/internal/credit/entry/{eid}")
def cup(eid:int,p:CreditUpdate,x_data_token:str|None=Header(None)): dep(x_data_token); credit.update_entry(eid,p.party,p.side,p.description,p.amount); return {"ok":True}
@app.delete("/internal/credit/entry/{eid}")
def cdel(eid:int,x_data_token:str|None=Header(None)): dep(x_data_token); credit.delete_entry(eid); return {"ok":True}
@app.get("/internal/ping")
def ping(x_data_token:str|None=Header(None)): dep(x_data_token); return {"status":"ok"}
