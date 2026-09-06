# -*- coding: utf-8 -*-
from __future__ import annotations

import os, json, time, hmac, hashlib, sqlite3, threading
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    def rtl(s):
        try: return get_display(arabic_reshaper.reshape(str(s)))
        except Exception: return str(s)
except Exception:
    def rtl(s): return str(s)

BASE = Path(__file__).resolve().parent
DB = BASE / "hive_alpha_v11.db"
APP = "HIVE ALPHA v11"
INITIAL_EQUITY = 500.0
TRADE_USD = 10.0
MAX_POSITIONS = 3
SCAN_SECONDS = 5
SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","TONUSDT","ADAUSDT","AVAXUSDT","SUIUSDT","LINKUSDT","BNBUSDT","TRXUSDT","PEPEUSDT","WIFUSDT","OPUSDT","ARBUSDT","HBARUSDT","LTCUSDT","NEARUSDT","INJUSDT"]
REST_CANDIDATES = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz", "https://api-testnet.bybit.com"]
SESSION = requests.Session()
SESSION.headers.update({"User-Agent":"Mozilla/5.0","Accept":"application/json"})
ACTIVE_BASE = None
LOCK = threading.Lock()
RUN_SCAN = True
CACHE = {"meta":{},"last_scan":"","last_err":""}


def ts(): return datetime.now(timezone.utc).isoformat(timespec="seconds")

def q(s): return json.dumps(s, ensure_ascii=False)

def db(): return sqlite3.connect(DB)

def init_db():
    c = db(); cur = c.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS state(k TEXT PRIMARY KEY, v TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY AUTOINCREMENT, ts_open TEXT, ts_close TEXT, symbol TEXT, side TEXT, entry REAL, exit REAL, qty REAL, usd REAL, pnl REAL, status TEXT, tp REAL, sl REAL, score REAL, reason TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS equity(ts TEXT, equity REAL, open_n INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS logs(ts TEXT, kind TEXT, symbol TEXT, msg TEXT)")
    c.commit(); c.close()

def sget(k, d=""):
    c=db(); r=c.execute("SELECT v FROM state WHERE k=?", (k,)).fetchone(); c.close();
    return r[0] if r else d

def sset(k, v):
    c=db(); c.execute("INSERT OR REPLACE INTO state(k,v) VALUES(?,?)", (k, str(v))); c.commit(); c.close()

def log(kind, symbol, msg):
    c=db(); c.execute("INSERT INTO logs VALUES(?,?,?,?)", (ts(), kind, symbol, msg)); c.commit(); c.close()

def now_equity():
    c=db(); cur=c.cursor()
    rows = cur.execute("SELECT symbol,side,entry,qty FROM trades WHERE status='open'").fetchall()
    eq = INITIAL_EQUITY + sum(x[0] for x in cur.execute("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE status='closed'").fetchall())
    unreal = 0.0
    for sym, side, entry, qty in rows:
        p = last_price(sym)
        if p:
            unreal += (p-entry)*qty if side=='Buy' else (entry-p)*qty
    c.close(); return round(eq + unreal, 4)

def save_equity():
    c=db(); open_n = c.execute("SELECT COUNT(*) FROM trades WHERE status='open'").fetchone()[0]; eq = now_equity(); c.execute("INSERT INTO equity VALUES(?,?,?)", (ts(), eq, open_n)); c.commit(); c.close(); return eq

def get_open():
    c=db(); rows = c.execute("SELECT id,ts_open,symbol,side,entry,qty,usd,tp,sl,score,reason FROM trades WHERE status='open' ORDER BY id DESC").fetchall(); c.close();
    return rows

def get_closed(limit=100):
    c=db(); rows = c.execute("SELECT id,ts_open,ts_close,symbol,side,entry,exit,qty,usd,pnl,score,reason FROM trades WHERE status='closed' ORDER BY id DESC LIMIT ?", (limit,)).fetchall(); c.close(); return rows

def get_equity_df(limit=300):
    c=db(); rows = c.execute("SELECT ts,equity,open_n FROM equity ORDER BY ts DESC LIMIT ?", (limit,)).fetchall(); c.close();
    df = pd.DataFrame(rows, columns=["ts","equity","open_n"])
    return df.sort_values("ts") if not df.empty else df

def get_logs(limit=60):
    c=db(); rows = c.execute("SELECT ts,kind,symbol,msg FROM logs ORDER BY ts DESC LIMIT ?", (limit,)).fetchall(); c.close(); return rows

def bybit(method, path, params=None, body=None, auth=False):
    global ACTIVE_BASE
    params = params or {}
    body = body or {}
    bases = ([ACTIVE_BASE] if ACTIVE_BASE else []) + [b for b in REST_CANDIDATES if b != ACTIVE_BASE]
    for base in bases:
        try:
            url = base + path
            if auth:
                key = sget("api_key", os.getenv("BYBIT_API_KEY", ""))
                sec = sget("api_secret", os.getenv("BYBIT_API_SECRET", ""))
                if not key or not sec: return None
                recv = "5000"; t = str(int(time.time()*1000))
                qstr = "&".join(f"{k}={params[k]}" for k in sorted(params)) if params else ""
                bstr = json.dumps(body, separators=(",",":")) if body else ""
                payload = qstr if method == "GET" else bstr
                sign = hmac.new(sec.encode(), f"{t}{key}{recv}{payload}".encode(), hashlib.sha256).hexdigest()
                headers = {"X-BAPI-API-KEY":key,"X-BAPI-SIGN":sign,"X-BAPI-SIGN-TYPE":"2","X-BAPI-TIMESTAMP":t,"X-BAPI-RECV-WINDOW":recv,"Content-Type":"application/json"}
            else:
                headers = {}
            r = SESSION.request(method, url, params=params if method=="GET" else None, data=(json.dumps(body) if body else None) if method!="GET" else None, headers=headers, timeout=8)
            j = r.json()
            if isinstance(j, dict) and j.get("retCode", 0) == 0:
                ACTIVE_BASE = base
                return j
        except Exception:
            continue
    return None

def load_cfg():
    sset("api_key", sget("api_key", os.getenv("BYBIT_API_KEY", "")))
    sset("api_secret", sget("api_secret", os.getenv("BYBIT_API_SECRET", "")))
    sset("testnet", sget("testnet", "0"))

def meta(symbol):
    if symbol in CACHE["meta"]: return CACHE["meta"][symbol]
    j = bybit("GET", "/v5/market/instruments-info", {"category":"linear","symbol":symbol})
    m = {"qtyStep":"0.001","minOrderQty":"0.001"}
    try:
        item = j["result"]["list"][0]; f = item["lotSizeFilter"]
        m = {"qtyStep":f.get("qtyStep","0.001"),"minOrderQty":f.get("minOrderQty","0.001")}
    except Exception:
        pass
    CACHE["meta"][symbol] = m
    return m

def round_qty(symbol, qty):
    m = meta(symbol)
    step = float(m.get("qtyStep", 0.001)); mn = float(m.get("minOrderQty", 0.001))
    q = max(qty, mn)
    return max(mn, round(q / step) * step)

def klines(symbol, limit=60):
    j = bybit("GET", "/v5/market/kline", {"category":"linear","symbol":symbol,"interval":"1","limit":limit})
    if not j: return None
    try:
        arr = j["result"]["list"]
        df = pd.DataFrame(arr, columns=["ts","open","high","low","close","volume","turnover"])
        for c in ["open","high","low","close","volume"]: df[c] = df[c].astype(float)
        return df.sort_values("ts").reset_index(drop=True)
    except Exception:
        return None

def last_price(symbol):
    df = klines(symbol, 2)
    return None if df is None or df.empty else float(df.close.iloc[-1])

def rsi7(c):
    d = c.diff(); up = d.clip(lower=0).rolling(7).mean(); dn = (-d.clip(upper=0)).rolling(7).mean()
    rs = up / dn.replace(0, np.nan); return 100 - (100 / (1 + rs))

def score_df(df):
    c = df.close; v = df.volume; rr = rsi7(c).iloc[-1]
    mom = (c.iloc[-1] / c.iloc[-5] - 1) * 100 if len(c) >= 5 else 0
    vr = (v.iloc[-1] / max(v.iloc[-10:-1].mean(), 1e-9)) if len(v) >= 10 else 1
    s = (rr - 50) * 2.2 + (vr - 1) * 24 + mom * 8
    return float(np.clip(s, -100, 100)), float(rr), float(vr), float(mom)

def pos_count(): return len(get_open())

def open_trade(symbol, side, px, score):
    if pos_count() >= MAX_POSITIONS: return False, "max positions"
    if any(r[2] == symbol for r in get_open()): return False, "already open"
    qty = round_qty(symbol, TRADE_USD / px)
    body = {"category":"linear","symbol":symbol,"side":side,"orderType":"Market","qty":str(qty),"timeInForce":"IOC","reduceOnly":False,"closeOnTrigger":False}
    j = bybit("POST", "/v5/order/create", body=body, auth=True)
    if not j: return False, "order failed"
    tp = px * (1.02 if side == "Buy" else 0.98)
    sl = px * (0.99 if side == "Buy" else 1.01)
    c = db(); c.execute("INSERT INTO trades(ts_open,symbol,side,entry,qty,usd,status,tp,sl,score,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (ts(), symbol, side, px, qty, TRADE_USD, "open", tp, sl, score, "signal")); c.commit(); c.close();
    log("OPEN", symbol, f"{side} qty={qty} px={px:.6f} score={score:.1f}")
    return True, "opened"

def close_trade(tid, symbol, side, entry, qty, reason, exit_px=None):
    px = exit_px or last_price(symbol)
    if px is None: return False
    close_side = "Sell" if side == "Buy" else "Buy"
    body = {"category":"linear","symbol":symbol,"side":close_side,"orderType":"Market","qty":str(qty),"timeInForce":"IOC","reduceOnly":True,"closeOnTrigger":True}
    bybit("POST", "/v5/order/create", body=body, auth=True)
    pnl = (px - entry) * qty if side == "Buy" else (entry - px) * qty
    c = db(); c.execute("UPDATE trades SET ts_close=?, exit=?, pnl=?, status=?, reason=? WHERE id=?", (ts(), px, pnl, "closed", reason, tid)); c.commit(); c.close()
    log("CLOSE", symbol, f"{reason} pnl={pnl:.4f} exit={px:.6f}")
    return True

def manage_positions():
    for tid, ts_open, symbol, side, entry, qty, usd, tp, sl, score, reason in get_open():
        px = last_price(symbol)
        if not px: continue
        if (side == "Buy" and (px >= tp or px <= sl)) or (side == "Sell" and (px <= tp or px >= sl)):
            close_trade(tid, symbol, side, entry, qty, "tp/sl", px)

def scan_once():
    if not RUN_SCAN or LOCK.locked(): return
    with LOCK:
        try:
            manage_positions()
            for s in SYMBOLS:
                df = klines(s, 60)
                if df is None or len(df) < 20:
                    continue
                score, rr, vr, mom = score_df(df)
                side = "Buy" if score > 70 else "Sell" if score < -70 else "Hold"
                log("SCAN", s, f"score={score:.1f} rsi={rr:.1f} vr={vr:.2f} mom={mom:.2f}")
                if side != "Hold":
                    px = float(df.close.iloc[-1])
                    ok, msg = open_trade(s, side, px, score)
                    if ok: break
            save_equity()
            CACHE["last_scan"] = ts()
        except Exception as e:
            CACHE["last_err"] = str(e)
            log("ERR", "SYS", str(e))
        finally:
            threading.Timer(SCAN_SECONDS, scan_once).start()

init_db(); load_cfg(); save_equity(); threading.Timer(1, scan_once).start()

app = Dash(__name__)
app.title = APP
app.layout = html.Div([
    html.H3(rtl(APP), style={"margin":"8px 0"}),
    html.Div(id="status", style={"marginBottom":"8px", "color":"#9bd"}),
    dcc.Tabs(id="tabs", value="positions", children=[
        dcc.Tab(label=rtl("Positions"), value="positions"),
        dcc.Tab(label=rtl("Scan"), value="scan"),
        dcc.Tab(label=rtl("Equity"), value="equity"),
        dcc.Tab(label=rtl("Settings"), value="settings"),
        dcc.Tab(label=rtl("Logs"), value="logs"),
        dcc.Tab(label=rtl("Performance"), value="performance"),
    ]),
    html.Div(id="content"),
    dcc.Interval(id="tick", interval=2000, n_intervals=0),
], style={"fontFamily":"Arial, sans-serif", "background":"#08111f", "color":"#eef", "padding":"10px"})

def table(rows, headers):
    head = html.Tr([html.Th(h) for h in headers])
    body = [html.Tr([html.Td(str(x)) for x in r]) for r in rows]
    return html.Table([html.Thead(head), html.Tbody(body)], style={"width":"100%", "borderCollapse":"collapse"})

def equity_fig():
    df = get_equity_df()
    fig = go.Figure()
    if not df.empty:
        fig.add_trace(go.Scatter(x=df.ts, y=df.equity, mode="lines", name="Equity"))
    fig.add_hline(y=INITIAL_EQUITY, line_dash="dash", line_color="orange")
    fig.update_layout(template="plotly_dark", height=360, margin=dict(l=20,r=20,t=30,b=20), paper_bgcolor="rgba(0,0,0,0)")
    return fig

@app.callback(Output("content", "children"), Output("status", "children"), Input("tabs", "value"), Input("tick", "n_intervals"))
def render(tab, _):
    eq = now_equity(); open_rows = get_open(); closed = get_closed(20)
    st = f"Equity: ${eq:.2f} | Open: {len(open_rows)} | Last scan: {CACHE['last_scan']} | Base: {ACTIVE_BASE or 'none'}"
    if tab == "positions":
        rows = [[r[0], r[2], r[3], round(r[4],6), round(r[5],6), round(r[7],6), round(r[8],6), round(r[9],2), r[10]] for r in open_rows]
        return html.Div([html.H4(rtl("Positions")), table(rows, ["ID","Symbol","Side","Entry","Qty","TP","SL","Score","Reason"]), html.Hr(), html.H4(rtl("Closed")), table(closed[:10], ["ID","Open","Close","Sym","Side","Entry","Exit","Qty","USD","PnL","Score","Reason"]) ]), st
    if tab == "scan":
        c = db(); rows = c.execute("SELECT ts,kind,symbol,msg FROM logs WHERE kind='SCAN' ORDER BY ts DESC LIMIT 40").fetchall(); c.close()
        return html.Div([html.H4(rtl("Latest Scan Signals")), table(rows, ["TS","Kind","Symbol","Msg"]) ]), st
    if tab == "equity":
        return html.Div([dcc.Graph(figure=equity_fig()), html.Div(f"Start: ${INITIAL_EQUITY:.2f}")]), st
    if tab == "settings":
        return html.Div([
            html.H4(rtl("Settings")),
            html.Div(["API Key", dcc.Input(id="api_key", value=sget("api_key"), type="text", style={"width":"100%"})]),
            html.Br(), html.Div(["API Secret", dcc.Input(id="api_secret", value=sget("api_secret"), type="password", style={"width":"100%"})]),
            html.Br(), html.Div([dcc.Checklist(id="testnet", options=[{"label":" Testnet","value":"1"}], value=[sget("testnet")] if sget("testnet") == "1" else [])]),
            html.Button("Save", id="save", n_clicks=0), html.Div(id="save_msg"),
            html.Div(f"Scanner: {'ON' if RUN_SCAN else 'OFF'}")
        ]), st
    if tab == "logs":
        rows = get_logs(80)
        return html.Div([html.H4(rtl("Logs")), table(rows, ["TS","Kind","Symbol","Msg"]) ]), st
    if tab == "performance":
        c = db(); w = c.execute("SELECT COUNT(*) FROM trades WHERE status='closed' AND pnl>0").fetchone()[0]; n = c.execute("SELECT COUNT(*) FROM trades WHERE status='closed'").fetchone()[0]; pnl = c.execute("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE status='closed'").fetchone()[0]; c.close()
        wr = (w / n * 100) if n else 0.0
        return html.Div([html.H4(rtl("Performance")), html.Div(f"Closed: {n}"), html.Div(f"Win rate: {wr:.1f}%"), html.Div(f"Realized PnL: ${pnl:.2f}"), dcc.Graph(figure=equity_fig())]), st
    return html.Div(), st

@app.callback(Output("save_msg", "children"), Input("save", "n_clicks"), Input("api_key", "value"), Input("api_secret", "value"), Input("testnet", "value"))
def save_settings(n, k, s, tn):
    if not n: return ""
    sset("api_key", k or ""); sset("api_secret", s or ""); sset("testnet", "1" if tn else "0")
    return f"Saved {ts()}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8055, debug=False, use_reloader=False)
