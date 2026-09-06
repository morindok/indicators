# -*- coding: utf-8 -*-
"""
🌌 Order Flow Resonance Engine v2 — Full 20 Symbols Coverage
=============================================================
{Morindok}

✓ پوشش کامل ۲۰+ ارز با اسکن REST
✓ WebSocket زنده روی نماد انتخابی
✓ بک‌تست تاریخی روی نماد انتخابی (۱ ماه تا ۱ سال)
✓ ذخیره خودکار سیگنال‌ها در دیتابیس
✓ آمار وین‌ریت برای هر ارز
✓ کنترل مارجین + ۳ حالت معاملاتی
"""

import json
import math
import os
import sqlite3
import threading
import time
import webbrowser
from collections import deque
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import requests
import websocket

import dash
from dash import dcc, html, Input, Output, State, ALL, ctx
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

# ==============================================================================
# 0) تنظیمات پایه
# ==============================================================================
BG = "#030308"; CARD = "#0a0a18"; CARD2 = "#101025"; LINE = "#252545"
TXT = "#e8e8ff"; MUT = "#7a7aa8"; GOLD = "#ffd700"
UP = "#00ffcc"; DN = "#ff2266"; BLUE = "#00aaff"; PURPLE = "#bb66ff"; CYAN = "#00ffff"
DARK_BG = "#171426"; DARK_CELL = "#221d33"; DARK_BORDER = "#3a3450"
CREAM = "#f5efe0"; PINK = "#e0407a"; TEAL = "#57b8d0"

FONT_FAMILY = "Vazirmatn, Tahoma, Arial, sans-serif"
DB_PATH = "signals_database.db"
DEFAULT_BALANCE = 500.0

# حالت‌های معاملاتی
TRADING_MODES = {
    "conservative": {"name": "🛡️ محافظه‌کار", "risk_pct": 0.01,
                     "max_leverage": 10.0, "min_leverage": 2.0,
                     "max_position_pct": 0.20, "max_margin_pct": 0.15,
                     "sl_atr_mult": 2.0, "tp_atr_mult": 3.0,
                     "min_sl_pct": 0.005, "min_tp_pct": 0.015},
    "normal": {"name": "⚖️ معمولی", "risk_pct": 0.02,
               "max_leverage": 25.0, "min_leverage": 2.0,
               "max_position_pct": 0.40, "max_margin_pct": 0.25,
               "sl_atr_mult": 1.5, "tp_atr_mult": 4.0,
               "min_sl_pct": 0.008, "min_tp_pct": 0.025},
    "aggressive": {"name": "🔥 اگرسیو", "risk_pct": 0.05,
                   "max_leverage": 50.0, "min_leverage": 5.0,
                   "max_position_pct": 0.50, "max_margin_pct": 0.30,
                   "sl_atr_mult": 1.2, "tp_atr_mult": 6.0,
                   "min_sl_pct": 0.008, "min_tp_pct": 0.03},
}
TRADING_MODE_OPTIONS = [{"label": v["name"], "value": k} for k, v in TRADING_MODES.items()]

# ★ ۲۱ نماد کامل
SYMBOLS = {
    "BTCUSDT": {"name": "بیت‌کوین", "icon": "₿", "tick": 10.0},
    "ETHUSDT": {"name": "اتریوم", "icon": "Ξ", "tick": 0.1},
    "SOLUSDT": {"name": "سولانا", "icon": "◎", "tick": 0.01},
    "BNBUSDT": {"name": "بایننس کوین", "icon": "🔶", "tick": 0.05},
    "XRPUSDT": {"name": "ریپل", "icon": "✕", "tick": 0.0001},
    "ADAUSDT": {"name": "کاردانو", "icon": "₳", "tick": 0.0001},
    "DOGEUSDT": {"name": "دوج‌کوین", "icon": "Ð", "tick": 0.00001},
    "AVAXUSDT": {"name": "آوالانچ", "icon": "🔺", "tick": 0.005},
    "DOTUSDT": {"name": "پولکادات", "icon": "●", "tick": 0.005},
    "LINKUSDT": {"name": "چین‌لینک", "icon": "⬡", "tick": 0.001},
    "MATICUSDT": {"name": "پالیگان", "icon": "🟣", "tick": 0.0001},
    "LTCUSDT": {"name": "لایت‌کوین", "icon": "Ł", "tick": 0.01},
    "ATOMUSDT": {"name": "کاسماس", "icon": "⚛", "tick": 0.001},
    "UNIUSDT": {"name": "یونی‌سواپ", "icon": "🦄", "tick": 0.001},
    "APTUSDT": {"name": "آپتوس", "icon": "🅰", "tick": 0.001},
    "ARBUSDT": {"name": "آربیتروم", "icon": "🔵", "tick": 0.0001},
    "OPUSDT": {"name": "آپتیمیسم", "icon": "🔴", "tick": 0.0001},
    "NEARUSDT": {"name": "نیر", "icon": "Ⓝ", "tick": 0.001},
    "INJUSDT": {"name": "اینجکتیو", "icon": "💉", "tick": 0.005},
    "SUIUSDT": {"name": "سویی", "icon": "💧", "tick": 0.0001},
    "XAUUSDT": {"name": "طلا", "icon": "🥇", "tick": 0.1},
}
SYMBOL_OPTIONS = [{"label": f"{v['icon']} {k.replace('USDT','')} — {v['name']}", "value": k}
                  for k, v in SYMBOLS.items()]

# دوره‌های بک‌تست
BACKTEST_PERIODS = {
    "1m": {"label": "۱ ماه", "days": 30},
    "2m": {"label": "۲ ماه", "days": 60},
    "3m": {"label": "۳ ماه (پیش‌فرض)", "days": 90},
    "6m": {"label": "۶ ماه", "days": 180},
    "1y": {"label": "۱ سال", "days": 365},
}
BACKTEST_PERIOD_OPTIONS = [{"label": v["label"], "value": k} for k, v in BACKTEST_PERIODS.items()]

# تنظیمات Order Flow
DEFAULT_CATEGORY = "linear"
DEFAULT_TICK_SIZE = 10.0
DEFAULT_INTERVAL_SEC = 60
MAX_COLUMNS = 16
HISTORY_TRIM_HOURS = 3
ORDER_BOOK_DEPTH = 12
IMBALANCE_RATIO = 3.0
STACK_MIN = 3
TRADE_BUFFER_MAX = 300_000
SIG_DELTA_PCT = 15.0
SIG_VOL_RATIO = 1.15
SIG_COOLDOWN_SEC = 120

REST_CANDIDATES = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
WS_CANDIDATES = ["wss://stream.bybit.com", "wss://stream.bytick.com"]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json",
                        "Referer": "https://www.bybit.com/"})
_ACTIVE_REST_BASE = {"url": None}
STALE_SEC = 25; WATCHDOG_INTERVAL = 5

# ==============================================================================
# 1) دیتابیس
# ==============================================================================
class SignalDatabase:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path); conn.row_factory = sqlite3.Row; return conn
    def _init_db(self):
        conn = self._get_conn(); cursor = conn.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, symbol TEXT,
            direction INTEGER, entry_price REAL, sl_price REAL, tp_price REAL,
            dollar_amount REAL, confidence REAL, score REAL, rr_ratio REAL,
            status TEXT DEFAULT 'open', exit_price REAL, exit_time TEXT,
            pnl REAL, pnl_pct REAL, exit_reason TEXT, interval TEXT,
            threshold REAL, leverage REAL DEFAULT 1.0, margin_used REAL DEFAULT 0.0,
            trading_mode TEXT DEFAULT 'normal', signal_kind TEXT DEFAULT 'orderflow',
            signal_reason TEXT)""")
        conn.commit()
        for col, df in [("leverage","1.0"),("margin_used","0.0"),("trading_mode","'normal'"),
                        ("signal_kind","'orderflow'"),("signal_reason","''")]:
            try: cursor.execute(f"ALTER TABLE signals ADD COLUMN {col} TEXT DEFAULT {df}")
            except: pass
        conn.commit(); conn.close()

    def save_signal(self, sig, interval, threshold, kind="orderflow", reason=""):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("""INSERT INTO signals (created_at, symbol, direction, entry_price, sl_price, tp_price,
            dollar_amount, confidence, score, rr_ratio, status, interval, threshold,
            leverage, margin_used, trading_mode, signal_kind, signal_reason)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sig["timestamp"], sig["symbol"], sig["signal"], sig["entry_price"],
             sig["sl_price"], sig["tp_price"], sig["dollar_amount"], sig["confidence"],
             sig["final_score"], sig["rr_ratio"], "open", interval, threshold,
             sig.get("leverage",1.0), sig.get("margin_used",0.0),
             sig.get("trading_mode","normal"), kind, reason))
        conn.commit(); conn.close()

    def has_open_signal(self, symbol):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM signals WHERE symbol=? AND status='open'", (symbol,))
        n = c.fetchone()[0]; conn.close(); return n > 0

    def get_open_signals(self):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM signals WHERE status='open' ORDER BY created_at DESC")
        rows = [dict(r) for r in c.fetchall()]; conn.close(); return rows

    def get_signal_by_id(self, sid):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM signals WHERE id=?", (sid,))
        r = c.fetchone(); conn.close(); return dict(r) if r else None

    def close_signal(self, sid, ep, et, pnl, pnl_pct, reason):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("UPDATE signals SET status='closed_manual', exit_price=?, exit_time=?, pnl=?, pnl_pct=?, exit_reason=? WHERE id=?",
                  (ep, et, pnl, pnl_pct, reason, sid))
        conn.commit(); conn.close()

    def update_signal_result(self, sid, ep, et, pnl, pnl_pct, status, reason):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("UPDATE signals SET exit_price=?, exit_time=?, pnl=?, pnl_pct=?, status=?, exit_reason=? WHERE id=?",
                  (ep, et, pnl, pnl_pct, status, reason, sid))
        conn.commit(); conn.close()

    def get_all_signals(self, limit=200):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in c.fetchall()]; conn.close(); return rows

    def get_total_pnl(self):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT COALESCE(SUM(pnl),0) FROM signals WHERE pnl IS NOT NULL AND status!='open'")
        v = c.fetchone()[0]; conn.close(); return v or 0.0

    def get_symbol_signals(self, symbol, limit=100):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM signals WHERE symbol=? ORDER BY created_at DESC LIMIT ?", (symbol, limit))
        rows = [dict(r) for r in c.fetchall()]; conn.close(); return rows

    def get_symbol_stats(self, symbol):
        sigs = self.get_symbol_signals(symbol, 1000)
        if not sigs: return None
        closed = [s for s in sigs if s["status"]!="open"]
        pnls = [s["pnl"] for s in closed if s["pnl"] is not None]
        wins = sum(1 for p in pnls if p > 0)
        long_c = [s for s in closed if s["direction"]==1 and s["pnl"] is not None]
        short_c = [s for s in closed if s["direction"]==-1 and s["pnl"] is not None]
        cum = []; r = 0.0
        for s in reversed(closed):
            if s["pnl"] is not None: r += s["pnl"]; cum.append(r)
        return {
            "symbol": symbol, "total": len(sigs), "closed": len(closed),
            "open": len(sigs)-len(closed),
            "tp_count": sum(1 for s in closed if s["status"]=="tp_hit"),
            "sl_count": sum(1 for s in closed if s["status"]=="sl_hit"),
            "expired_count": sum(1 for s in closed if s["status"]=="expired"),
            "manual_count": sum(1 for s in closed if s["status"]=="closed_manual"),
            "total_pnl": sum(pnls) if pnls else 0.0,
            "wins": wins, "losses": len(pnls)-wins,
            "win_rate": (wins/len(pnls)*100) if pnls else 0.0,
            "avg_pnl": sum(pnls)/len(pnls) if pnls else 0.0,
            "avg_pnl_pct": sum(s["pnl_pct"] for s in closed if s["pnl_pct"] is not None)/len(closed) if closed else 0.0,
            "best_trade": max(pnls) if pnls else 0.0,
            "worst_trade": min(pnls) if pnls else 0.0,
            "avg_confidence": sum(s["confidence"] for s in sigs)/len(sigs) if sigs else 0.0,
            "avg_leverage": sum(s.get("leverage",1) for s in sigs)/len(sigs) if sigs else 0.0,
            "cumulative_pnl": cum,
            "long_count": sum(1 for s in sigs if s["direction"]==1),
            "short_count": sum(1 for s in sigs if s["direction"]==-1),
            "long_win_rate": (sum(1 for s in long_c if s["pnl"]>0)/len(long_c)*100) if long_c else 0.0,
            "short_win_rate": (sum(1 for s in short_c if s["pnl"]>0)/len(short_c)*100) if short_c else 0.0,
        }

    def get_signal_stats(self, initial_balance=DEFAULT_BALANCE):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM signals"); total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM signals WHERE status='open'"); oc = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM signals WHERE status='tp_hit'"); tp = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM signals WHERE status='sl_hit'"); sl = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM signals WHERE status='expired'"); exp = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM signals WHERE status='closed_manual'"); man = c.fetchone()[0]
        c.execute("SELECT COALESCE(SUM(pnl),0) FROM signals WHERE pnl IS NOT NULL AND status!='open'")
        tp_pnl = c.fetchone()[0] or 0.0
        c.execute("SELECT COUNT(*) FROM signals WHERE pnl>0 AND status!='open'"); wins = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM signals WHERE pnl<=0 AND pnl IS NOT NULL AND status!='open'"); losses = c.fetchone()[0]
        c.execute("SELECT AVG(leverage) FROM signals WHERE leverage IS NOT NULL"); al = c.fetchone()[0] or 0.0
        conn.close()
        cwr = wins+losses
        return {"total": total, "open": oc, "tp_count": tp, "sl_count": sl,
                "expired_count": exp, "manual_count": man, "total_pnl": tp_pnl,
                "wins": wins, "losses": losses,
                "win_rate": (wins/cwr*100) if cwr>0 else 0.0, "avg_leverage": al,
                "initial_balance": initial_balance,
                "current_balance": initial_balance + tp_pnl}

# ==============================================================================
# 2) کنترل مارجین
# ==============================================================================
def get_total_open_margin(db):
    return sum(s.get("margin_used",0) or 0 for s in db.get_open_signals())

def get_available_margin(balance, db):
    return max(0, balance - get_total_open_margin(db))

# ==============================================================================
# 3) ارتباط REST
# ==============================================================================
def bybit_get(path, params, timeout=10):
    cands = ([_ACTIVE_REST_BASE["url"]] if _ACTIVE_REST_BASE["url"] else []) + \
            [b for b in REST_CANDIDATES if b != _ACTIVE_REST_BASE["url"]]
    for base in cands:
        try:
            r = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code in (403, 451): continue
            r.raise_for_status()
            d = r.json()
            if d.get("retCode") == 0:
                _ACTIVE_REST_BASE["url"] = base; return d
        except: continue
    return None

def get_klines(symbol, interval, limit=1000):
    cats = ["linear","spot"] if symbol=="XAUUSDT" else ["linear"]
    for cat in cats:
        d = bybit_get("/v5/market/kline", {"category":cat, "symbol":symbol, "interval":interval, "limit":limit})
        if d and "list" in (d.get("result") or {}):
            lst = d["result"]["list"]
            if lst:
                df = pd.DataFrame(lst, columns=["ts","open","high","low","close","volume","turnover"])
                df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
                for c in ["open","high","low","close","volume"]: df[c] = df[c].astype(float)
                return df.sort_values("ts").reset_index(drop=True)
    return pd.DataFrame()

def get_recent_trades_rest(symbol, limit=1000):
    """دریافت آخرین معاملات هر نماد از REST."""
    d = bybit_get("/v5/market/recent-trade", {"category":"linear", "symbol":symbol, "limit":limit})
    if not d: return pd.DataFrame()
    items = (d.get("result") or {}).get("list") or []
    rows = []
    for t in items:
        try:
            rows.append({
                "id": t.get("execId"),
                "ts": pd.to_datetime(int(t["time"]), unit="ms", utc=True),
                "price": float(t["price"]), "amount": float(t["size"]),
                "side": "buy" if t.get("side")=="Buy" else "sell",
            })
        except: continue
    return pd.DataFrame(rows)

def get_interval_minutes(interval):
    s = str(interval).strip().lower()
    if s=="d": return 1440
    if s=="w": return 10080
    if s=="m": return 43200
    try: return int(s)
    except: return 15

# ==============================================================================
# 4) WebSocket State
# ==============================================================================
STATE_LOCK = threading.RLock()
TRADES = deque(maxlen=TRADE_BUFFER_MAX)
ORDER_BOOK = {"bids": {}, "asks": {}, "ready": False}
CONN_STATUS = {"connected": False, "symbol": "BTCUSDT", "category": DEFAULT_CATEGORY}
LAST_MSG_TS = {"t": 0.0}
SIGNAL_STATE = {"last_id": 0, "fired_keys": {}, "latest": None}
SIGNAL_LOG = deque(maxlen=100)

class BybitStream:
    def __init__(self, symbol, category="linear"):
        self.symbol = symbol.upper(); self.category = category
        self.ws = None; self.stop_flag = threading.Event()
        self.host_idx = 0; self.fail_count = 0
    def _url(self):
        return f"{WS_CANDIDATES[self.host_idx % len(WS_CANDIDATES)]}/v5/public/{self.category}"
    def start(self):
        self.stop_flag.clear()
        threading.Thread(target=self._run, daemon=True).start()
    def stop(self):
        self.stop_flag.set()
        try:
            if self.ws: self.ws.close()
        except: pass
    def force_reconnect(self):
        try:
            if self.ws: self.ws.close()
        except: pass
    def _run(self):
        while not self.stop_flag.is_set():
            try:
                with STATE_LOCK: CONN_STATUS["ws_host"] = self._url()
                self.ws = websocket.WebSocketApp(self._url(),
                    on_open=self._on_open, on_message=self._on_message,
                    on_error=self._on_error, on_close=self._on_close)
                self.ws.run_forever(ping_interval=20)
            except: pass
            with STATE_LOCK: CONN_STATUS["connected"] = False
            if self.stop_flag.is_set(): break
            self.fail_count += 1
            if self.fail_count >= 2: self.host_idx += 1; self.fail_count = 0
            time.sleep(min(3*(self.fail_count+1), 12))
    def _on_open(self, ws):
        ws.send(json.dumps({"op":"subscribe", "args":[f"publicTrade.{self.symbol}", f"orderbook.50.{self.symbol}"]}))
        with STATE_LOCK:
            ORDER_BOOK["ready"] = False; ORDER_BOOK["bids"].clear(); ORDER_BOOK["asks"].clear()
            CONN_STATUS["connected"] = True; CONN_STATUS["symbol"] = self.symbol
        LAST_MSG_TS["t"] = time.time(); self.fail_count = 0
    def _on_error(self, ws, e):
        with STATE_LOCK: CONN_STATUS["connected"] = False
    def _on_close(self, ws, c, m):
        with STATE_LOCK: CONN_STATUS["connected"] = False
    def _on_message(self, ws, raw):
        LAST_MSG_TS["t"] = time.time()
        try: msg = json.loads(raw)
        except: return
        topic = msg.get("topic", "")
        if topic.startswith("publicTrade."):
            rows = []
            for t in (msg.get("data") or []):
                try: rows.append({"id":t.get("i"), "ts":pd.to_datetime(int(t["T"]), unit="ms", utc=True),
                                  "price":float(t["p"]), "amount":float(t["v"]),
                                  "side":"buy" if t.get("S")=="Buy" else "sell"})
                except: continue
            with STATE_LOCK: TRADES.extend(rows)
        elif topic.startswith("orderbook."):
            mtype = msg.get("type"); data = msg.get("data") or {}
            bids, asks = data.get("b",[]), data.get("a",[])
            with STATE_LOCK:
                if mtype == "snapshot":
                    ORDER_BOOK["bids"] = {float(p):float(s) for p,s in bids if float(s)>0}
                    ORDER_BOOK["asks"] = {float(p):float(s) for p,s in asks if float(s)>0}
                    ORDER_BOOK["ready"] = True
                else:
                    for p,s in bids:
                        p,s = float(p), float(s)
                        if s==0: ORDER_BOOK["bids"].pop(p, None)
                        else: ORDER_BOOK["bids"][p] = s
                    for p,s in asks:
                        p,s = float(p), float(s)
                        if s==0: ORDER_BOOK["asks"].pop(p, None)
                        else: ORDER_BOOK["asks"][p] = s

CURRENT_STREAM = None

def restart_stream(symbol, category):
    global CURRENT_STREAM
    if CURRENT_STREAM: CURRENT_STREAM.stop()
    with STATE_LOCK:
        TRADES.clear(); ORDER_BOOK["ready"] = False
        ORDER_BOOK["bids"].clear(); ORDER_BOOK["asks"].clear()
    CURRENT_STREAM = BybitStream(symbol, category); CURRENT_STREAM.start()

def watchdog_loop():
    while True:
        time.sleep(WATCHDOG_INTERVAL)
        with STATE_LOCK: conn = CONN_STATUS["connected"]
        if conn and (time.time()-LAST_MSG_TS["t"]>STALE_SEC) and CURRENT_STREAM:
            CURRENT_STREAM.force_reconnect()

threading.Thread(target=watchdog_loop, daemon=True).start()

# ==============================================================================
# 5) Order Flow Core
# ==============================================================================
def get_trades_df():
    with STATE_LOCK:
        if not TRADES: return pd.DataFrame()
        df = pd.DataFrame(list(TRADES))
    if df.empty: return df
    cutoff = pd.Timestamp.now(tz=timezone.utc) - pd.Timedelta(hours=HISTORY_TRIM_HOURS)
    return df[df["ts"]>=cutoff].drop_duplicates(subset="id")

def get_orderbook_snapshot(depth=ORDER_BOOK_DEPTH):
    with STATE_LOCK:
        bids = sorted(ORDER_BOOK["bids"].items(), key=lambda x:-x[0])[:depth]
        asks = sorted(ORDER_BOOK["asks"].items(), key=lambda x:x[0])[:depth]
    return pd.DataFrame(asks, columns=["price","amount"]), pd.DataFrame(bids, columns=["price","amount"])

def build_footprint(df, tick_size, interval_sec, max_cols):
    if df.empty: return None
    work = df.copy()
    work["price_bucket"] = (np.floor(work["price"]/tick_size)*tick_size).round(8)
    work["time_bucket"] = work["ts"].dt.floor(f"{interval_sec}s")
    cols = sorted(work["time_bucket"].unique())[-max_cols:]
    work = work[work["time_bucket"].isin(cols)]
    if work.empty: return None
    min_p, max_p = work["price_bucket"].min(), work["price_bucket"].max()
    n = max(int(round((max_p-min_p)/tick_size)), 0)
    rows = [round(max_p-i*tick_size, 8) for i in range(n+1)]
    ask_piv = work[work["side"]=="buy"].pivot_table(index="price_bucket", columns="time_bucket",
                                                     values="amount", aggfunc="sum", fill_value=0.0)
    bid_piv = work[work["side"]=="sell"].pivot_table(index="price_bucket", columns="time_bucket",
                                                     values="amount", aggfunc="sum", fill_value=0.0)
    ask_g = ask_piv.reindex(index=rows, columns=cols, fill_value=0.0)
    bid_g = bid_piv.reindex(index=rows, columns=cols, fill_value=0.0)
    col_open = work.sort_values("ts").groupby("time_bucket")["price"].first().reindex(cols)
    col_close = work.sort_values("ts").groupby("time_bucket")["price"].last().reindex(cols)
    return {"rows":rows, "cols":cols, "tick_size":tick_size, "ask":ask_g, "bid":bid_g,
            "total":ask_g+bid_g, "delta":ask_g-bid_g, "col_open":col_open, "col_close":col_close}

def compute_diagonal_imbalances(fp, ratio=IMBALANCE_RATIO):
    ask_g, bid_g, tick = fp["ask"], fp["bid"], fp["tick_size"]
    imb = {}
    for c in fp["cols"]:
        for p in fp["rows"]:
            a, b = ask_g.loc[p,c], bid_g.loc[p,c]
            pb, pa = round(p-tick,8), round(p+tick,8)
            b_below = bid_g.loc[pb,c] if pb in bid_g.index else 0.0
            a_above = ask_g.loc[pa,c] if pa in ask_g.index else 0.0
            buy_imb = a>0 and b_below>0 and (a/b_below)>=ratio
            sell_imb = b>0 and a_above>0 and (b/a_above)>=ratio
            imb[(p,c)] = "buy" if (buy_imb and not sell_imb) else ("sell" if sell_imb else None)
    return imb

def detect_stacked(imb, rows, cols, min_stack=STACK_MIN):
    stacked = set()
    for c in cols:
        sd, ss, sl = None, 0, 0
        for ri, p in enumerate(rows):
            d = imb.get((p,c))
            if d is not None and d == sd: sl += 1
            else:
                if sd is not None and sl >= min_stack:
                    stacked.update((rows[k],c) for k in range(ss, ss+sl))
                sd, ss = d, ri; sl = 1 if d is not None else 0
        if sd is not None and sl >= min_stack:
            stacked.update((rows[k],c) for k in range(ss, ss+sl))
    return stacked

def fmt(v):
    if v >= 1000: return f"{v/1000:.1f}k"
    if v >= 1: return f"{v:,.1f}".rstrip("0").rstrip(".")
    return f"{v:.3f}".rstrip("0").rstrip(".") if v else "0"

def compute_bar_readings(fp):
    if fp is None: return []
    readings = []; prev_low = prev_high = None
    for c in fp["cols"]:
        tot_s = fp["total"][c]; dlt_s = fp["delta"][c]
        total = float(tot_s.sum()); delta = float(dlt_s.sum())
        delta_pct = (delta/total*100) if total>0 else 0.0
        traded = tot_s[tot_s>0]
        if len(traded) > 0:
            high = float(traded.index.max()); low = float(traded.index.min())
            mpv = float(dlt_s.max()); mpp = float(dlt_s.idxmax())
            mmv = float(dlt_s.min()); mmp = float(dlt_s.idxmin())
            poc = float(tot_s.idxmax())
        else: high=low=mpv=mpp=mmv=mmp=poc=None
        o = fp["col_open"].get(c, np.nan); cl = fp["col_close"].get(c, np.nan)
        readings.append({"col":c, "total_volume":total, "bar_delta":delta, "delta_pct":delta_pct,
                         "buy_classified":float(fp["ask"][c].sum()),
                         "sell_classified":float(fp["bid"][c].sum()),
                         "max_plus_v":mpv, "max_plus_p":mpp,
                         "max_minus_v":mmv, "max_minus_p":mmp, "poc":poc,
                         "high":high, "low":low,
                         "open":float(o) if pd.notna(o) else None,
                         "close":float(cl) if pd.notna(cl) else None,
                         "prev_low":prev_low, "prev_high":prev_high})
        if low is not None: prev_low, prev_high = low, high
    return readings

def evaluate_signal_map(readings, imb, stacked):
    gates, signals, verdict = [], [], None
    if not readings or len(readings)<2: return gates, signals, verdict
    last = readings[-1]
    if last["total_volume"]<=0 or last["close"] is None: return gates, signals, verdict
    avg_vol = float(np.mean([r["total_volume"] for r in readings[:-1]]))
    vol_ratio = last["total_volume"]/avg_vol if avg_vol>0 else 0.0
    vol_ok = vol_ratio >= SIG_VOL_RATIO
    if last["bar_delta"] < 0:
        price_ok = (last["prev_low"] is not None and last["close"]>last["prev_low"]
                    and last["close"]>(last["max_minus_p"] or 0)
                    and last["close"]>=(last["open"] if last["open"] else last["close"]))
        gates = [
            {"label":"گیت۱ · تهاجم فروش", "value":f"Sell {last['sell_classified']:,.0f} vs Buy {last['buy_classified']:,.0f}", "passed":True},
            {"label":"گیت۲ · حجم کل", "value":f"{vol_ratio:.2f}×", "passed":vol_ok},
            {"label":"گیت۳ · Delta%", "value":f"{last['delta_pct']:.1f}%", "passed":last["delta_pct"]<=-SIG_DELTA_PCT},
            {"label":"گیت۴ · قله فشار فروش", "value":f"Max-Δ {last['max_minus_v']:,.0f}", "passed":(last["max_minus_v"] or 0)<0},
            {"label":"گیت۵ · پس‌گرفتن کف", "value":f"Close {last['close']:,.0f}", "passed":price_ok},
        ]
        if all(g["passed"] for g in gates):
            verdict = "LONG"
            signals.append({"kind":"ABSORPTION","side":"LONG","vol_ratio":vol_ratio,"last":last,
                            "title":"🟢 LONG · جذب فروش + پس‌گرفتن کف"})
    else:
        price_ok = (last["prev_high"] is not None and last["close"]<last["prev_high"]
                    and last["close"]<(last["max_plus_p"] or 0)
                    and last["close"]<=(last["open"] if last["open"] else last["close"]))
        gates = [
            {"label":"گیت۱ · تهاجم خرید", "value":f"Buy {last['buy_classified']:,.0f} vs Sell {last['sell_classified']:,.0f}", "passed":True},
            {"label":"گیت۲ · حجم کل", "value":f"{vol_ratio:.2f}×", "passed":vol_ok},
            {"label":"گیت۳ · Delta%", "value":f"+{last['delta_pct']:.1f}%", "passed":last["delta_pct"]>=SIG_DELTA_PCT},
            {"label":"گیت۴ · قله فشار خرید", "value":f"Max+Δ {last['max_plus_v']:,.0f}", "passed":(last["max_plus_v"] or 0)>0},
            {"label":"گیت۵ · عدم پس‌گرفتن سقف", "value":f"Close {last['close']:,.0f}", "passed":price_ok},
        ]
        if all(g["passed"] for g in gates):
            verdict = "SHORT"
            signals.append({"kind":"ABSORPTION","side":"SHORT","vol_ratio":vol_ratio,"last":last,
                            "title":"🔴 SHORT · جذب خرید + از دست‌رفتن سقف"})
    last_col = last["col"]
    stack_dirs = set()
    for (p,c) in stacked:
        if c == last_col:
            d = imb.get((p,c))
            if d: stack_dirs.add(d)
    if "buy" in stack_dirs:
        signals.append({"kind":"STACKED_IMB","side":"LONG","vol_ratio":vol_ratio,"last":last,
                        "title":"🟢 LONG · Imbalance انباشته"})
    if "sell" in stack_dirs:
        signals.append({"kind":"STACKED_IMB","side":"SHORT","vol_ratio":vol_ratio,"last":last,
                        "title":"🔴 SHORT · Imbalance انباشته"})
    return gates, signals, verdict

# ==============================================================================
# 6) ★ اسکن همه ۲۱ نماد با REST
# ==============================================================================
def scan_all_symbols_orderflow(balance, trading_mode, interval_sec=60, tick_size=None,
                              progress_callback=None):
    """اسکن همه نمادها از طریق REST + Order Flow."""
    results = []
    mode = TRADING_MODES.get(trading_mode, TRADING_MODES["normal"])
    total = len(SYMBOLS)
    for idx, (symbol, info) in enumerate(SYMBOLS.items(), 1):
        try:
            if progress_callback: progress_callback(idx, total, symbol, "دریافت داده...")
            tick = tick_size if tick_size else info["tick"]

            # دریافت trades
            df = get_recent_trades_rest(symbol, limit=1000)
            if df.empty or len(df) < 50:
                if progress_callback: progress_callback(idx, total, symbol, "داده کافی نیست")
                continue

            # دریافت کندل برای ATR
            klines_df = get_klines(symbol, "15", limit=200)
            if klines_df.empty or len(klines_df) < 30:
                continue

            # ساخت footprint
            fp = build_footprint(df, tick, interval_sec, MAX_COLUMNS)
            if fp is None or len(fp["cols"]) < 3:
                continue

            imb = compute_diagonal_imbalances(fp)
            stacked = detect_stacked(imb, fp["rows"], fp["cols"])
            readings = compute_bar_readings(fp)
            gates, sig_candidates, verdict = evaluate_signal_map(readings, imb, stacked)

            if not sig_candidates:
                if progress_callback: progress_callback(idx, total, symbol, "سیگنال نبود")
                continue

            # محاسبه ATR و price
            risk_engine = RiskEngine(trading_mode=trading_mode)
            atr_arr = risk_engine.calculate_atr(klines_df)
            current_atr = atr_arr[-1]
            current_price = klines_df["close"].iloc[-1]

            # برای هر سیگنال
            for sig_info in sig_candidates[:1]:  # فقط اولین
                side = sig_info["side"]
                signal = 1 if side == "LONG" else -1
                confidence = min(100.0, sig_info.get("vol_ratio",1.0)*30+40)
                tp_sl = risk_engine.calculate_tp_sl(current_price, signal, current_atr, confidence)
                available = get_available_margin(balance, db)
                position = risk_engine.calculate_position(balance, current_price,
                    tp_sl["sl_distance"], confidence, available)
                final_score = confidence * sig_info.get("vol_ratio", 1.0)

                result = {
                    "symbol": symbol, "name": info["name"], "icon": info["icon"],
                    "signal": signal, "side": side,
                    "entry_price": current_price,
                    "sl_price": tp_sl["sl_price"], "tp_price": tp_sl["tp_price"],
                    "rr_ratio": tp_sl["rr_ratio"],
                    "dollar_amount": position["dollar_amount"],
                    "leverage": position["leverage"], "margin_used": position["margin_used"],
                    "confidence": confidence, "final_score": final_score,
                    "title": sig_info["title"], "kind": sig_info["kind"],
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    "trading_mode": trading_mode,
                }
                results.append(result)
                if progress_callback: progress_callback(idx, total, symbol, f"✅ سیگنال {side}")

            time.sleep(0.15)

        except Exception as e:
            if progress_callback: progress_callback(idx, total, symbol, f"خطا: {str(e)[:30]}")
            continue

    results.sort(key=lambda x: x["final_score"], reverse=True)
    return results

# ==============================================================================
# 7) ★ بک‌تست تاریخی
# ==============================================================================
BACKTEST_MIN_HISTORY = 200

def run_historical_backtest(symbol, interval, period_days, balance, trading_mode, threshold=0.35):
    interval_min = get_interval_minutes(interval)
    candles_per_day = (24*60)/interval_min
    required = int(period_days * candles_per_day) + BACKTEST_MIN_HISTORY
    required = min(required, 1000)
    df = get_klines(symbol, interval, limit=required)
    if df.empty or len(df) < BACKTEST_MIN_HISTORY + 10:
        return None, None, {"error": "داده کافی نیست"}
    risk_engine = RiskEngine(trading_mode=trading_mode)
    atr = risk_engine.calculate_atr(df)
    closes = df["close"].values; highs = df["high"].values; lows = df["low"].values
    timestamps = df["ts"].tolist(); n = len(closes)
    trades = []
    equity_curve = [{"time": timestamps[BACKTEST_MIN_HISTORY-1], "balance": balance}]
    current_balance = balance
    i = BACKTEST_MIN_HISTORY
    while i < n-1:
        df_slice = df.iloc[:i+1].copy()
        if len(df_slice) < BACKTEST_MIN_HISTORY:
            i += 1; continue
        try:
            cp = closes[i]; current_atr = atr[i]
            # شبیه‌سازی ساده سیگنال: momentum + volatility
            past = df_slice["close"].values[-20:]
            sma = past.mean()
            momentum = (cp - sma) / sma
            vol = df_slice["close"].rolling(20).std().iloc[-1]
            if vol <= 0 or np.isnan(vol):
                i += 1; continue
            sig = 0
            if momentum > 0.005 and cp > sma: sig = 1
            elif momentum < -0.005 and cp < sma: sig = -1
            if sig == 0:
                i += 1; continue
            # محاسبه سیگنال
            confidence = min(100.0, abs(momentum) * 1000 + 40)
            tp_sl = risk_engine.calculate_tp_sl(cp, sig, current_atr, confidence)
            position = risk_engine.calculate_position(current_balance, cp, tp_sl["sl_distance"], confidence)
            if position["dollar_amount"] <= 0:
                i += 1; continue
            entry_price = cp; sl = tp_sl["sl_price"]; tp = tp_sl["tp_price"]
            dollar_amount = position["dollar_amount"]
            leverage = position["leverage"]; margin = position["margin_used"]
            size = dollar_amount / entry_price if entry_price > 0 else 0
            exit_price = None; exit_reason = None; exit_idx = i
            max_hold = min(48, n-i-1)
            for j in range(1, max_hold+1):
                idx = i+j
                if idx >= n: break
                if sig == 1:
                    if lows[idx] <= sl: exit_price = sl; exit_reason = "SL"; exit_idx = idx; break
                    elif highs[idx] >= tp: exit_price = tp; exit_reason = "TP"; exit_idx = idx; break
                else:
                    if highs[idx] >= sl: exit_price = sl; exit_reason = "SL"; exit_idx = idx; break
                    elif lows[idx] <= tp: exit_price = tp; exit_reason = "TP"; exit_idx = idx; break
            if exit_price is None:
                exit_idx = min(i+max_hold, n-1); exit_price = closes[exit_idx]; exit_reason = "Horizon"
            pnl = ((exit_price-entry_price) if sig==1 else (entry_price-exit_price)) * size
            fee = (entry_price*size + exit_price*size) * 0.0006
            net_pnl = pnl - fee
            pnl_pct = (net_pnl/dollar_amount*100) if dollar_amount>0 else 0
            current_balance += net_pnl
            trades.append({"entry_time":timestamps[i], "exit_time":timestamps[exit_idx],
                           "direction":"Long" if sig==1 else "Short",
                           "entry_price":entry_price, "exit_price":exit_price,
                           "sl_price":sl, "tp_price":tp, "dollar_amount":dollar_amount,
                           "leverage":leverage, "margin_used":margin, "pnl":net_pnl,
                           "pnl_pct":pnl_pct, "exit_reason":exit_reason,
                           "confidence":confidence, "balance_after":current_balance})
            equity_curve.append({"time":timestamps[exit_idx], "balance":current_balance})
            i = exit_idx + 1
        except: i += 1; continue
    stats = calc_backtest_stats(trades, equity_curve, balance)
    return trades, equity_curve, stats

def calc_backtest_stats(trades, eq, initial):
    if not trades:
        return {"total_trades":0, "win_rate":0, "total_pnl":0, "total_return_pct":0,
                "max_drawdown_pct":0, "sharpe_ratio":0, "profit_factor":0,
                "avg_win":0, "avg_loss":0, "best_trade":0, "worst_trade":0,
                "avg_confidence":0, "long_trades":0, "short_trades":0,
                "long_win_rate":0, "short_win_rate":0, "tp_count":0, "sl_count":0,
                "horizon_count":0, "final_balance":initial}
    pnls = [t["pnl"] for t in trades]; pnl_pcts = [t["pnl_pct"] for t in trades]
    total_pnl = sum(pnls); final = initial+total_pnl
    total_ret = (total_pnl/initial*100) if initial>0 else 0
    wins = [p for p in pnls if p>0]; losses = [p for p in pnls if p<=0]
    wr = (len(wins)/len(pnls)*100) if pnls else 0
    bal = [initial]+[t["balance_after"] for t in trades]
    peak = bal[0]; max_dd = 0
    for b in bal:
        if b>peak: peak=b
        dd = (peak-b)/peak*100 if peak>0 else 0
        if dd>max_dd: max_dd=dd
    if len(pnl_pcts)>1:
        avg_r = sum(pnl_pcts)/len(pnl_pcts)
        std_r = (sum((r-avg_r)**2 for r in pnl_pcts)/len(pnl_pcts))**0.5
        sharpe = (avg_r/std_r*(len(pnl_pcts)**0.5)) if std_r>0 else 0
    else: sharpe = 0
    gp = sum(p for p in pnls if p>0)
    gl = abs(sum(p for p in pnls if p<=0))
    pf = (gp/gl) if gl>0 else 0
    long = [t for t in trades if t["direction"]=="Long"]
    short = [t for t in trades if t["direction"]=="Short"]
    lw = [t for t in long if t["pnl"]>0]; sw = [t for t in short if t["pnl"]>0]
    lwr = (len(lw)/len(long)*100) if long else 0
    swr = (len(sw)/len(short)*100) if short else 0
    tp_c = sum(1 for t in trades if t["exit_reason"]=="TP")
    sl_c = sum(1 for t in trades if t["exit_reason"]=="SL")
    hz_c = sum(1 for t in trades if t["exit_reason"]=="Horizon")
    confs = [t["confidence"] for t in trades]
    avg_conf = sum(confs)/len(confs) if confs else 0
    return {"total_trades":len(trades), "win_rate":wr, "total_pnl":total_pnl,
            "total_return_pct":total_ret, "max_drawdown_pct":max_dd,
            "sharpe_ratio":sharpe, "profit_factor":pf,
            "avg_win":sum(wins)/len(wins) if wins else 0,
            "avg_loss":sum(losses)/len(losses) if losses else 0,
            "best_trade":max(pnls) if pnls else 0,
            "worst_trade":min(pnls) if pnls else 0,
            "avg_confidence":avg_conf, "long_trades":len(long), "short_trades":len(short),
            "long_win_rate":lwr, "short_win_rate":swr,
            "tp_count":tp_c, "sl_count":sl_c, "horizon_count":hz_c, "final_balance":final}

# ==============================================================================
# 8) موتور ریسک
# ==============================================================================
class RiskEngine:
    def __init__(self, trading_mode="normal", atr_period=14):
        self.profile = TRADING_MODES.get(trading_mode, TRADING_MODES["normal"])
        self.trading_mode = trading_mode; self.atr_period = atr_period
    def calculate_atr(self, df):
        highs=df["high"].values; lows=df["low"].values; closes=df["close"].values
        tr = np.maximum(highs-lows, np.maximum(np.abs(highs-np.roll(closes,1)), np.abs(lows-np.roll(closes,1))))
        tr[0] = highs[0]-lows[0]
        return pd.Series(tr).ewm(span=self.atr_period, adjust=False).mean().values
    def calculate_tp_sl(self, ep, sig, atr, conf):
        p = self.profile
        sl_d = max(atr*p["sl_atr_mult"], ep*p["min_sl_pct"])
        tp_d = max(atr*p["tp_atr_mult"], ep*p["min_tp_pct"])
        tp_d *= (1.0 + conf/100*0.5)
        if sig==1: sl=ep-sl_d; tp=ep+tp_d
        else: sl=ep+sl_d; tp=ep-tp_d
        return {"sl_price":sl, "tp_price":tp, "rr_ratio":tp_d/sl_d if sl_d>0 else 0,
                "sl_distance":sl_d, "tp_distance":tp_d}
    def calculate_leverage(self, ep, sl_d, conf):
        if ep<=0 or sl_d<=0: return self.profile["min_leverage"]
        sl_pct = sl_d/ep
        base = 0.02/max(sl_pct, 0.005)
        lev = base*(0.7+conf/100*0.6)
        return round(max(self.profile["min_leverage"], min(self.profile["max_leverage"], lev)), 1)
    def calculate_position(self, balance, ep, sl_d, conf, available=None):
        if sl_d<=0 or ep<=0:
            return {"dollar_amount":0.0, "leverage":self.profile["min_leverage"], "margin_used":0.0}
        p = self.profile
        risk = balance*p["risk_pct"]
        adjusted = risk*(0.5+conf/100*0.5)
        sl_pct = sl_d/ep
        pos = adjusted/sl_pct if sl_pct>0 else 0
        lev = self.calculate_leverage(ep, sl_d, conf)
        margin = pos/lev
        mm = balance*p["max_margin_pct"]
        if margin>mm: margin=mm; pos=margin*lev
        mp = balance*p["max_position_pct"]
        if pos>mp: pos=mp; margin=pos/lev
        if available is not None and margin>available: margin=available; pos=margin*lev
        if pos<5.0: pos=5.0; margin=pos/lev
        return {"dollar_amount":round(pos,2), "leverage":lev, "margin_used":round(margin,2)}

# ==============================================================================
# 9) آپدیت PnL زنده
# ==============================================================================
def update_open_signals_results(db):
    sigs = db.get_open_signals()
    if not sigs: return 0
    updated = 0
    for s in sigs:
        try:
            df = get_klines(s["symbol"], "1", limit=1)
            if df.empty: continue
            cp = df["close"].iloc[-1]; ct = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            ep = s["entry_price"]; d = s["direction"]
            sl = s["sl_price"]; tp = s["tp_price"]; da = s["dollar_amount"]
            size = da/ep if ep>0 else 0
            status=None; exit_p=None; reason=None
            if d==1:
                if cp<=sl: status="sl_hit"; exit_p=sl; reason="SL"
                elif cp>=tp: status="tp_hit"; exit_p=tp; reason="TP"
            else:
                if cp>=sl: status="sl_hit"; exit_p=sl; reason="SL"
                elif cp<=tp: status="tp_hit"; exit_p=tp; reason="TP"
            if status is None:
                try:
                    cd = datetime.strptime(s["created_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    if (datetime.now(timezone.utc)-cd).total_seconds()/3600 > 24:
                        status="expired"; exit_p=cp; reason="Expired (24h)"
                except: pass
            if status:
                pnl = ((exit_p-ep) if d==1 else (ep-exit_p))*size
                pnl_pct = (pnl/da*100) if da>0 else 0
                db.update_signal_result(s["id"], exit_p, ct, pnl, pnl_pct, status, reason)
                updated += 1
        except: continue
    return updated

def calculate_open_pnls_live(db):
    live = {}
    for s in db.get_open_signals():
        try:
            df = get_klines(s["symbol"], "1", limit=1)
            if df.empty: continue
            cp = df["close"].iloc[-1]; ep = s["entry_price"]; da = s["dollar_amount"]
            size = da/ep if ep>0 else 0
            pnl = ((cp-ep) if s["direction"]==1 else (ep-cp))*size
            live[s["id"]] = {"current_price":cp, "pnl":pnl, "pnl_pct":pnl/da*100 if da>0 else 0}
        except: continue
    return live

# ==============================================================================
# 10) UI
# ==============================================================================
def empty_fig(msg):
    fig = go.Figure()
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
                      xaxis=dict(visible=False), yaxis=dict(visible=False), font=dict(family=FONT_FAMILY))
    fig.add_annotation(x=0.5, y=0.5, xref="paper", yref="paper", text=msg,
                       showarrow=False, font=dict(size=16, color=DN, family=FONT_FAMILY))
    return fig

def get_mode_badge(mode_key):
    if mode_key=="aggressive": return "🔥 اگرسیو", DN
    elif mode_key=="conservative": return "🛡️ محافظه‌کار", UP
    return "⚖️ معمولی", GOLD

def render_footprint_figure(fp, pair):
    if fp is None: return empty_fig("در حال دریافت...")
    rows, cols = fp["rows"], fp["cols"]; n_rows, n_cols = len(rows), len(cols)
    poc_per_col = {c:fp["total"][c].idxmax() for c in cols if fp["total"][c].max()>0}
    imb = compute_diagonal_imbalances(fp)
    stacked = detect_stacked(imb, rows, cols)
    shapes, ann = [], []; col_w=1.0; dir_w=0.06
    for ci, c in enumerate(cols):
        x0, x1 = ci*col_w, ci*col_w+col_w
        o, cl = fp["col_open"].get(c, np.nan), fp["col_close"].get(c, np.nan)
        bc = UP if (pd.notna(o) and pd.notna(cl) and cl>=o) else DN
        shapes.append(dict(type="rect", x0=x0, x1=x0+dir_w, y0=0, y1=n_rows, fillcolor=bc, line=dict(width=0), layer="below"))
        for ri, p in enumerate(rows):
            y0, y1 = n_rows-ri-1, n_rows-ri
            bv, av, tv, dv = fp["bid"].loc[p,c], fp["ask"].loc[p,c], fp["total"].loc[p,c], fp["delta"].loc[p,c]
            bg = CARD; bc, bw, bd = LINE, 0.6, "solid"
            dir = imb.get((p,c))
            if dir=="buy": bc, bw, bd = UP, 1.6, "dot"
            elif dir=="sell": bc, bw, bd = DN, 1.6, "dot"
            if (p,c) in stacked: bw, bd = 2.4, "dash"
            if poc_per_col.get(c)==p: bc, bw, bd = GOLD, 2.6, "solid"; bg = "rgba(255,215,0,0.08)"
            shapes.append(dict(type="rect", x0=x0+dir_w, x1=x1, y0=y0, y1=y1,
                               line=dict(color=bc, width=bw, dash=bd), fillcolor=bg, layer="below"))
            if tv>0:
                tc = UP if dv>0 else (DN if dv<0 else MUT)
                ann.append(dict(x=(x0+dir_w+x1)/2, y=(y0+y1)/2, text=f"{fmt(bv)}×{fmt(av)}", showarrow=False,
                                font=dict(color=tc, size=9, family="Courier New"), xanchor="center", yanchor="middle"))
        cv, cd = fp["total"][c].sum(), fp["delta"][c].sum()
        dc = UP if cd>=0 else DN
        ann.append(dict(x=(x0+x1)/2, y=n_rows+0.9, text=fmt(cv), showarrow=False, font=dict(color=TXT, size=9)))
        ann.append(dict(x=(x0+x1)/2, y=n_rows+1.7, text=f"{'+' if cd>=0 else ''}{fmt(cd)}",
                         showarrow=False, font=dict(color=dc, size=9, family="Arial Black")))
        ann.append(dict(x=(x0+x1)/2, y=-0.7, text=pd.Timestamp(c).strftime("%H:%M"),
                         showarrow=False, font=dict(color=MUT, size=8)))
    for ri, p in enumerate(rows):
        y0, y1 = n_rows-ri-1, n_rows-ri
        ann.append(dict(x=-0.12, y=(y0+y1)/2, text=f"{p:,.0f}", showarrow=False,
                         font=dict(color=TXT, size=8), xanchor="right"))
    fig = go.Figure()
    fig.update_layout(shapes=shapes, annotations=ann,
                      xaxis=dict(range=[-1.6, n_cols*col_w+0.3], visible=False),
                      yaxis=dict(range=[-1.6, n_rows+2.3], visible=False),
                      plot_bgcolor=CARD, paper_bgcolor=BG, margin=dict(l=10,r=10,t=40,b=10),
                      title=dict(text=f"ORDER FLOW · {pair}", font=dict(color=CYAN, size=14, family=FONT_FAMILY), x=0.02),
                      height=500)
    return fig

def render_orderbook_figure(asks, bids):
    fig = go.Figure()
    if asks.empty and bids.empty: return empty_fig("در حال دریافت...")
    asr = asks.sort_values("price", ascending=True).head(ORDER_BOOK_DEPTH)
    bsr = bids.sort_values("price", ascending=False).head(ORDER_BOOK_DEPTH)
    mx = max(asr["amount"].max() if not asr.empty else 0, bsr["amount"].max() if not bsr.empty else 0, 1)
    shapes, ann = [], []; na, nb = len(asr), len(bsr); tr = na+nb
    for i, (_, r) in enumerate(asr.sort_values("price", ascending=False).iterrows()):
        y0, y1 = tr-i-1, tr-i; bar = r["amount"]/mx
        shapes.append(dict(type="rect", x0=0, x1=1, y0=y0, y1=y1, fillcolor="rgba(255,34,102,0.1)", line=dict(color=LINE, width=0.5)))
        shapes.append(dict(type="rect", x0=0, x1=bar, y0=y0+0.1, y1=y1-0.1, fillcolor=DN, line=dict(width=0)))
        ann.append(dict(x=0.02, y=(y0+y1)/2, text=fmt(r["amount"]), showarrow=False, xanchor="left", font=dict(color=DN, size=9)))
        ann.append(dict(x=0.98, y=(y0+y1)/2, text=f"{r['price']:,.1f}", showarrow=False, xanchor="right", font=dict(color=DN, size=9)))
    for i, (_, r) in enumerate(bsr.iterrows()):
        y0, y1 = nb-i-1, nb-i; bar = r["amount"]/mx
        shapes.append(dict(type="rect", x0=0, x1=1, y0=y0, y1=y1, fillcolor="rgba(0,255,204,0.1)", line=dict(color=LINE, width=0.5)))
        shapes.append(dict(type="rect", x0=0, x1=bar, y0=y0+0.1, y1=y1-0.1, fillcolor=UP, line=dict(width=0)))
        ann.append(dict(x=0.02, y=(y0+y1)/2, text=fmt(r["amount"]), showarrow=False, xanchor="left", font=dict(color=UP, size=9)))
        ann.append(dict(x=0.98, y=(y0+y1)/2, text=f"{r['price']:,.1f}", showarrow=False, xanchor="right", font=dict(color=UP, size=9)))
    fig.update_layout(shapes=shapes, annotations=ann,
                      xaxis=dict(range=[0,1], visible=False),
                      yaxis=dict(range=[-0.5, max(tr, nb)+0.5], visible=False),
                      plot_bgcolor=CARD, paper_bgcolor=BG, margin=dict(l=5,r=5,t=30,b=5),
                      title=dict(text="Order Book", font=dict(color=CYAN, size=13, family=FONT_FAMILY)), height=500)
    return fig

def render_cumulative_delta(fp):
    if fp is None: return empty_fig("داده‌ای نیست")
    cols = fp["cols"]; cd = fp["delta"].sum(axis=0).reindex(cols).fillna(0.0)
    cum = cd.cumsum(); xl = [pd.Timestamp(c).strftime("%H:%M") for c in cols]
    bcol = [UP if v>=0 else DN for v in cd]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=xl, y=cd, marker=dict(color=bcol), opacity=0.6))
    fig.add_trace(go.Scatter(x=xl, y=cum, mode="lines+markers", line=dict(color=GOLD, width=2.6),
                             marker=dict(size=5, color=GOLD), yaxis="y2"))
    fig.add_hline(y=0, line=dict(color=LINE, width=1))
    fig.update_layout(plot_bgcolor=CARD, paper_bgcolor=BG, margin=dict(l=45,r=45,t=40,b=35),
                      title=dict(text="Cumulative Delta", font=dict(color=CYAN, size=13), x=0.02),
                      xaxis=dict(showgrid=False, tickfont=dict(color=MUT, size=9)),
                      yaxis=dict(title="دلتای کندل", gridcolor=LINE, tickfont=dict(color=MUT, size=9)),
                      yaxis2=dict(title="تجمعی", overlaying="y", side="right", showgrid=False, tickfont=dict(color=GOLD, size=9)),
                      legend=dict(orientation="h", y=1.18, x=0, font=dict(size=9, color=MUT)),
                      height=280, bargap=0.15)
    return fig

def render_signal_map_panel(readings, gates, verdict, latest, log_list, pair):
    last = readings[-1] if readings else None
    ch = [html.Div([html.Span("🎯 SIGNAL MAP", style={"fontWeight":"800", "color":CYAN, "fontSize":"14px"}),
                    html.Span(f" · {pair}", style={"color":MUT, "fontSize":"11px", "marginRight":"8px"})],
                   style={"display":"flex", "alignItems":"baseline", "marginBottom":"8px"})]
    def chip(lbl, val, col):
        return html.Div([html.Div(lbl, style={"fontSize":"8px","color":MUT,"letterSpacing":"1px","direction":"ltr"}),
                         html.Div(val, style={"fontSize":"12px","fontWeight":"800","color":col,
                                              "fontFamily":"Courier New","direction":"ltr"})],
                        style={"background":CARD2, "border":f"1px solid {LINE}", "borderRadius":"8px",
                               "padding":"5px 8px", "flex":"1", "minWidth":"100px", "textAlign":"center"})
    if last and last["total_volume"]>0:
        ch.append(html.Div([chip("TOTAL", f"{last['total_volume']:,.0f}", TXT),
                            chip("DELTA", f"{last['bar_delta']:+,.0f}", UP if last["bar_delta"]>=0 else DN),
                            chip("DELTA%", f"{last['delta_pct']:.1f}%", UP if last["delta_pct"]>=0 else DN),
                            chip("MAX+Δ", f"{last['max_plus_v']:+,.0f}" if last["max_plus_v"] else "-", TEAL),
                            chip("MAX-Δ", f"{last['max_minus_v']:,.0f}" if last["max_minus_v"] else "-", PINK),
                            chip("POC", f"{last['poc']:,.0f}" if last["poc"] else "-", GOLD)],
                           style={"display":"flex","gap":"5px","flexWrap":"wrap","marginBottom":"8px"}))
    if gates:
        ch.append(html.Div("زنجیره گیت‌ها:", style={"fontSize":"10px","color":MUT,"marginBottom":"3px"}))
        for g in gates:
            ic = "✔" if g["passed"] else "✖"; icc = UP if g["passed"] else MUT
            ch.append(html.Div([html.Span(ic, style={"color":icc,"fontWeight":"800","marginLeft":"6px"}),
                                html.Div([html.Div(g["label"], style={"fontSize":"10px","color":TXT,"fontWeight":"600"}),
                                          html.Div(g["value"], style={"fontSize":"9px","color":MUT,"fontFamily":"Courier New","direction":"ltr","textAlign":"right"})],
                                         style={"flex":"1"})],
                               style={"display":"flex","alignItems":"center","padding":"3px 6px",
                                      "borderBottom":f"1px dashed {LINE}"}))
    if verdict=="LONG": vc, vt = UP, "🟢 سیگنال LONG"
    elif verdict=="SHORT": vc, vt = DN, "🔴 سیگنال SHORT"
    else: vc, vt = MUT, "در انتظار عبور گیت‌ها"
    ch.append(html.Div(vt, style={"marginTop":"7px","textAlign":"center","fontWeight":"800",
                                   "color":BG,"background":vc,"borderRadius":"8px","padding":"6px","fontSize":"11px"}))
    if log_list:
        lrs = []
        for s in list(log_list)[:4]:
            sc = UP if s["side"]=="LONG" else DN
            lrs.append(html.Div([html.Span(s.get("time_str",""), style={"color":MUT,"fontSize":"8px","fontFamily":"Courier New","marginLeft":"5px"}),
                                 html.Span(s["side"], style={"background":sc,"color":BG,"borderRadius":"6px","padding":"1px 5px","fontSize":"8px","fontWeight":"800","marginLeft":"5px"}),
                                 html.Span(s.get("title",""), style={"color":TXT,"fontSize":"9px"})],
                                style={"display":"flex","alignItems":"center","padding":"2px 0"}))
        ch.append(html.Div([html.Div("آخرین:", style={"fontSize":"10px","color":MUT,"margin":"6px 0 2px"}), *lrs]))
    return html.Div(ch, style={"background":DARK_BG,"borderRadius":"10px","padding":"10px",
                                "border":f"1.5px solid {DARK_BORDER}"})

# --- جدول اسکن همه ارزها ---
def build_scan_results_table(signals_data):
    if not signals_data:
        return html.Div("سیگنالی یافت نشد.", style={"color":MUT, "textAlign":"center", "padding":"20px"})
    header = html.Tr([html.Th("#"), html.Th("نماد"), html.Th("سیگنال"), html.Th("اطمینان"),
                      html.Th("حجم ($)"), html.Th("لوریج"), html.Th("ورود"), html.Th("SL"),
                      html.Th("TP"), html.Th("R:R"), html.Th("وضعیت")],
                     style={"color":MUT, "fontSize":9, "textAlign":"center"})
    rows = []
    for i, s in enumerate(signals_data, 1):
        dt = "🟢 LONG" if s["signal"]==1 else "🔴 SHORT"
        dc = UP if s["signal"]==1 else DN
        has_open = db.has_open_signal(s["symbol"])
        if has_open: st, sc = "✅ معامله باز دارد", BLUE
        else: st, sc = "🆕 آماده ذخیره", GOLD
        conf = s["confidence"]; cc = UP if conf>=70 else (GOLD if conf>=50 else DN)
        lev = s.get("leverage", 1.0); lvc = DN if lev>=50 else (GOLD if lev>=20 else UP)
        rows.append(html.Tr([
            html.Td(f"#{i}", style={"color":GOLD,"fontWeight":"bold","fontSize":"9px"}),
            html.Td([html.Span(s["icon"]), " ", html.Span(s["symbol"].replace("USDT",""), style={"fontWeight":"bold","fontSize":"9px"})]),
            html.Td(dt, style={"color":dc,"fontWeight":"bold","fontSize":"9px"}),
            html.Td(f"{conf:.0f}%", style={"color":cc,"fontSize":"9px"}),
            html.Td(f"${s['dollar_amount']:,.2f}", style={"color":BLUE,"fontSize":"9px"}),
            html.Td(f"{lev:.1f}x", style={"color":lvc,"fontWeight":"bold","fontSize":"9px"}),
            html.Td(f"${s['entry_price']:,.4g}", style={"color":TXT,"fontSize":"9px"}),
            html.Td(f"${s['sl_price']:,.4g}", style={"color":DN,"fontSize":"9px"}),
            html.Td(f"${s['tp_price']:,.4g}", style={"color":UP,"fontSize":"9px"}),
            html.Td(f"1:{s['rr_ratio']:.1f}", style={"color":GOLD,"fontWeight":"bold","fontSize":"9px"}),
            html.Td(st, style={"color":sc,"fontSize":"9px"}),
        ], style={"textAlign":"center","fontSize":"10px"}))
    return dbc.Table([html.Thead(header), html.Tbody(rows)],
                     bordered=False, hover=True, responsive=True, size="sm", style={"color":TXT})

# --- جدول معاملات باز ---
def build_open_positions_table(open_signals, live_pnls):
    if not open_signals:
        return html.Div("📭 معامله بازی نیست. روی «🔍 اسکن همه ارزها» بزنید.",
                       style={"color":MUT, "textAlign":"center", "padding":"25px", "fontSize":"12px"})
    header = html.Tr([html.Th("ID"), html.Th("نماد"), html.Th("جهت"), html.Th("حالت"),
                      html.Th("ورود"), html.Th("SL"), html.Th("TP"), html.Th("حجم"),
                      html.Th("لوریج"), html.Th("قیمت"), html.Th("PnL"), html.Th("PnL%"), html.Th("❌")],
                     style={"color":MUT, "fontSize":9, "textAlign":"center"})
    rows = []
    for s in open_signals:
        sid = s["id"]; sym = s["symbol"]; d = s["direction"]
        dt = "🟢 LONG" if d==1 else "🔴 SHORT"; dc = UP if d==1 else DN
        bg = "rgba(0,255,204,0.04)" if d==1 else "rgba(255,34,102,0.04)"
        mt, mc = get_mode_badge(s.get("trading_mode","normal"))
        live = live_pnls.get(sid, {"current_price":s["entry_price"],"pnl":0.0,"pnl_pct":0.0})
        pc = UP if live["pnl"]>0 else (DN if live["pnl"]<0 else MUT)
        si = SYMBOLS.get(sym, {"icon":"•","name":sym})
        rows.append(html.Tr([
            html.Td(f"#{sid}"),
            html.Td([html.Span(si["icon"]), " ", html.Span(sym.replace("USDT",""), style={"fontWeight":"bold"})]),
            html.Td(dt, style={"color":dc,"fontWeight":"bold"}),
            html.Td(mt, style={"color":mc,"fontSize":"9px"}),
            html.Td(f"${s['entry_price']:,.4g}"),
            html.Td(f"${s['sl_price']:,.4g}", style={"color":DN}),
            html.Td(f"${s['tp_price']:,.4g}", style={"color":UP}),
            html.Td(f"${s['dollar_amount']:,.2f}", style={"color":BLUE}),
            html.Td(f"{s.get('leverage',1.0):.1f}x", style={"color":GOLD}),
            html.Td(f"${live['current_price']:,.4g}", style={"color":CYAN}),
            html.Td(f"${live['pnl']:+,.2f}", style={"color":pc,"fontWeight":"bold"}),
            html.Td(f"{live['pnl_pct']:+.2f}%", style={"color":pc}),
            html.Td(dbc.Button("❌", id={"type":"close-btn","index":sid}, color="danger", size="sm",
                               style={"fontSize":"9px","padding":"2px 6px"})),
        ], style={"textAlign":"center","background":bg,"fontSize":"10px"}))
    return dbc.Table([html.Thead(header), html.Tbody(rows)],
                     bordered=False, hover=True, responsive=True, size="sm", style={"color":TXT})

def build_signals_summary(total_signals, total_pnl, current_balance, open_pnl, trading_mode, margin_info):
    total = total_signals or 0
    pnl_w_open = total_pnl + open_pnl
    pc = UP if pnl_w_open>=0 else DN
    bc = UP if current_balance>=DEFAULT_BALANCE else DN
    mt, mc = get_mode_badge(trading_mode)
    av = margin_info.get("available", current_balance) if margin_info else current_balance
    mvc = UP if av>50 else (GOLD if av>20 else DN)
    return dbc.Row([
        dbc.Col(html.Div([html.Div("حالت", className="stat-label"), html.Div(mt, className="stat-value", style={"color":mc,"fontSize":"13px"})],
                         className="glass-card", style={"padding":"9px","textAlign":"center","border":f"1px solid {mc}"}), md=2),
        dbc.Col(html.Div([html.Div("📊 تعداد سیگنال", className="stat-label"), html.Div(f"{total}", className="stat-value", style={"color":BLUE,"fontSize":"15px"})],
                         className="glass-card", style={"padding":"9px","textAlign":"center"}), md=2),
        dbc.Col(html.Div([html.Div("💰 مارجین آزاد", className="stat-label"), html.Div(f"${av:,.2f}", className="stat-value", style={"color":mvc,"fontSize":"15px"})],
                         className="glass-card", style={"padding":"9px","textAlign":"center","border":f"1px solid {mvc}"}), md=2),
        dbc.Col(html.Div([html.Div("💰 سود کل", className="stat-label"), html.Div(f"${pnl_w_open:+,.2f}", className="stat-value", style={"color":pc,"fontSize":"15px"})],
                         className="glass-card", style={"padding":"9px","textAlign":"center","border":f"1px solid {pc}"}), md=2),
        dbc.Col(html.Div([html.Div("📊 سرمایه", className="stat-label"), html.Div(f"${current_balance:,.2f}", className="stat-value", style={"color":bc,"fontSize":"15px"})],
                         className="glass-card", style={"padding":"9px","textAlign":"center","border":f"1px solid {bc}"}), md=2),
        dbc.Col(html.Div([html.Div("💼 معاملات باز", className="stat-label"),
                          html.Div(f"{len(db.get_open_signals())}", className="stat-value", style={"color":CYAN,"fontSize":"15px"})],
                         className="glass-card", style={"padding":"9px","textAlign":"center"}), md=2),
    ])

def build_mode_info_panel(trading_mode, balance=None, db=None):
    p = TRADING_MODES.get(trading_mode, TRADING_MODES["normal"])
    mt, mc = get_mode_badge(trading_mode)
    mh = ""
    if balance is not None and db is not None:
        av = get_available_margin(balance, db); used = get_total_open_margin(db)
        pct = (used/balance*100) if balance>0 else 0
        mvc = UP if pct<50 else (GOLD if pct<80 else DN)
        mh = html.Div([html.Div("📊 وضعیت مارجین", style={"color":TXT,"fontWeight":"bold","marginBottom":"6px"}),
                       dbc.Row([dbc.Col(html.Div([html.Div("استفاده", className="stat-label"),
                                                  html.Div(f"${used:,.2f}", className="stat-value", style={"color":mvc,"fontSize":"13px"})],
                                                 style={"textAlign":"center"}), md=4),
                                dbc.Col(html.Div([html.Div("آزاد", className="stat-label"),
                                                  html.Div(f"${av:,.2f}", className="stat-value", style={"color":UP,"fontSize":"13px"})],
                                                 style={"textAlign":"center"}), md=4),
                                dbc.Col(html.Div([html.Div("درصد", className="stat-label"),
                                                  html.Div(f"{pct:.1f}%", className="stat-value", style={"color":mvc,"fontSize":"13px"})],
                                                 style={"textAlign":"center"}), md=4)])],
                      style={"marginTop":"10px","paddingTop":"10px","borderTop":f"1px solid {LINE}"})
    return dbc.Card(dbc.CardBody([
        html.Div([html.Span(f"حالت: {mt}", style={"color":mc,"fontWeight":"bold","fontSize":"13px"})],
                 style={"textAlign":"center","marginBottom":"6px"}),
        dbc.Row([dbc.Col(html.Div([html.Div("ریسک",className="stat-label"),html.Div(f"{p['risk_pct']*100:.1f}%",className="stat-value",style={"color":GOLD,"fontSize":"12px"})],style={"textAlign":"center"}),md=2),
                 dbc.Col(html.Div([html.Div("لوریج",className="stat-label"),html.Div(f"{p['min_leverage']:.0f}-{p['max_leverage']:.0f}x",className="stat-value",style={"color":CYAN,"fontSize":"12px"})],style={"textAlign":"center"}),md=2),
                 dbc.Col(html.Div([html.Div("حجم",className="stat-label"),html.Div(f"{p['max_position_pct']*100:.0f}%",className="stat-value",style={"color":BLUE,"fontSize":"12px"})],style={"textAlign":"center"}),md=2),
                 dbc.Col(html.Div([html.Div("مارجین",className="stat-label"),html.Div(f"{p['max_margin_pct']*100:.0f}%",className="stat-value",style={"color":PURPLE,"fontSize":"12px"})],style={"textAlign":"center"}),md=2),
                 dbc.Col(html.Div([html.Div("SL ATR",className="stat-label"),html.Div(f"{p['sl_atr_mult']:.1f}x",className="stat-value",style={"color":DN,"fontSize":"12px"})],style={"textAlign":"center"}),md=2),
                 dbc.Col(html.Div([html.Div("TP ATR",className="stat-label"),html.Div(f"{p['tp_atr_mult']:.1f}x",className="stat-value",style={"color":UP,"fontSize":"12px"})],style={"textAlign":"center"}),md=2)]),
        mh]), className="glass-card", style={"margin":"8px 0"})

def build_history_table(signals_from_db, live_pnls=None):
    if not signals_from_db:
        return html.Div("هنوز سیگنالی ثبت نشده.", style={"color":MUT,"textAlign":"center","padding":"20px"})
    header = html.Tr([html.Th("ID"), html.Th("زمان"), html.Th("نماد"), html.Th("جهت"), html.Th("حالت"),
                      html.Th("ورود"), html.Th("SL"), html.Th("TP"), html.Th("حجم"), html.Th("لوریج"),
                      html.Th("وضعیت"), html.Th("PnL"), html.Th("PnL%"), html.Th("❌")],
                     style={"color":MUT,"fontSize":9,"textAlign":"center"})
    rows = []
    for s in signals_from_db:
        dt = "🟢" if s["direction"]==1 else "🔴"
        st = s["status"]
        if st=="tp_hit": stt, sc, bg = "🎯 TP", UP, "rgba(0,255,204,0.06)"
        elif st=="sl_hit": stt, sc, bg = "🛑 SL", DN, "rgba(255,34,102,0.06)"
        elif st=="expired": stt, sc, bg = "⏰ منقضی", MUT, "rgba(122,122,168,0.06)"
        elif st=="closed_manual": stt, sc, bg = "✋ دستی", GOLD, "rgba(255,215,0,0.06)"
        else: stt, sc, bg = "🔵 باز", BLUE, "rgba(0,170,255,0.04)"
        mt, mc = get_mode_badge(s.get("trading_mode","normal"))
        if st=="open" and live_pnls and s["id"] in live_pnls:
            l = live_pnls[s["id"]]; pnl = l["pnl"]; pnl_pct = l["pnl_pct"]
            ppc = UP if pnl>0 else (DN if pnl<0 else MUT)
            pt, ppt = f"${pnl:+,.2f}", f"{pnl_pct:+.2f}%"
        elif s["pnl"] is not None:
            pnl = s["pnl"]; ppc = UP if pnl>0 else DN
            pt, ppt = f"${pnl:+,.2f}", f"{s['pnl_pct']:+.2f}%"
        else: pt=ppt="—"; ppc=MUT
        si = SYMBOLS.get(s["symbol"], {"icon":"•"})
        act = html.Td(dbc.Button("❌", id={"type":"close-btn","index":s["id"]},
                                 color="danger", size="sm", style={"fontSize":"9px"})) if st=="open" else \
              html.Td(html.Span(s.get("exit_reason") or "—", style={"color":MUT,"fontSize":"9px"}))
        rows.append(html.Tr([html.Td(f"#{s['id']}"), html.Td(s["created_at"][-14:]),
                             html.Td([html.Span(si["icon"]), " ", html.Span(s["symbol"].replace("USDT",""), style={"fontWeight":"bold"})]),
                             html.Td(dt), html.Td(mt, style={"color":mc,"fontSize":"9px"}),
                             html.Td(f"${s['entry_price']:,.4g}"),
                             html.Td(f"${s['sl_price']:,.4g}", style={"color":DN}),
                             html.Td(f"${s['tp_price']:,.4g}", style={"color":UP}),
                             html.Td(f"${s['dollar_amount']:,.2f}", style={"color":BLUE}),
                             html.Td(f"{s.get('leverage',1.0):.1f}x", style={"color":GOLD}),
                             html.Td(stt, style={"color":sc,"fontWeight":"bold"}),
                             html.Td(pt, style={"color":ppc,"fontWeight":"bold"}),
                             html.Td(ppt, style={"color":ppc}), act],
                            style={"textAlign":"center","background":bg,"fontSize":"10px"}))
    return dbc.Table([html.Thead(header), html.Tbody(rows)],
                     bordered=False, hover=True, responsive=True, size="sm", style={"color":TXT})

def build_history_stats(stats, open_pnl=0.0):
    tpwo = stats["total_pnl"]+open_pnl
    cbwo = stats["initial_balance"]+tpwo
    bc = UP if cbwo>=stats["initial_balance"] else DN
    pc = UP if tpwo>=0 else DN
    cpc = UP if stats["total_pnl"]>=0 else DN
    return dbc.Row([
        dbc.Col(html.Div([html.Div("اولیه",className="stat-label"),html.Div(f"${stats['initial_balance']:,.2f}",className="stat-value",style={"color":TXT,"fontSize":"14px"})],className="glass-card",style={"padding":"9px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("💰 فعلی",className="stat-label"),html.Div(f"${cbwo:,.2f}",className="stat-value",style={"color":bc,"fontSize":"14px"})],className="glass-card",style={"padding":"9px","textAlign":"center","border":f"1px solid {bc}"}),md=2),
        dbc.Col(html.Div([html.Div("📊 کل",className="stat-label"),html.Div(f"${tpwo:+,.2f}",className="stat-value",style={"color":pc,"fontSize":"14px"})],className="glass-card",style={"padding":"9px","textAlign":"center","border":f"1px solid {pc}"}),md=2),
        dbc.Col(html.Div([html.Div("سود قطعی",className="stat-label"),html.Div(f"${stats['total_pnl']:+,.2f}",className="stat-value",style={"color":cpc,"fontSize":"14px"})],className="glass-card",style={"padding":"9px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("⚡ لوریج",className="stat-label"),html.Div(f"{stats['avg_leverage']:.1f}x",className="stat-value",style={"color":CYAN,"fontSize":"14px"})],className="glass-card",style={"padding":"9px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("Win Rate",className="stat-label"),html.Div(f"{stats['win_rate']:.1f}%",className="stat-value",style={"color":GOLD,"fontSize":"14px"})],className="glass-card",style={"padding":"9px","textAlign":"center"}),md=2),
    ])

def build_symbol_stats_kpis(stats):
    if not stats: return html.Div("داده‌ای نیست", style={"color":MUT,"textAlign":"center"})
    si = SYMBOLS.get(stats["symbol"], {"icon":"•","name":stats["symbol"]})
    pc = UP if stats["total_pnl"]>=0 else DN
    wc = UP if stats["win_rate"]>=50 else (GOLD if stats["win_rate"]>=35 else DN)
    return dbc.Row([
        dbc.Col(html.Div([html.Div(f"{si['icon']} {stats['symbol'].replace('USDT','')}",className="stat-label"),
                          html.Div(f"{stats['total']} سیگنال",className="stat-value",style={"color":TXT,"fontSize":"15px"})],
                         className="glass-card",style={"padding":"9px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("🏆 وین‌ریت",className="stat-label"),
                          html.Div(f"{stats['win_rate']:.1f}%",className="stat-value",style={"color":wc,"fontSize":"15px"})],
                         className="glass-card",style={"padding":"9px","textAlign":"center","border":f"1px solid {wc}"}),md=2),
        dbc.Col(html.Div([html.Div("💰 سود کل",className="stat-label"),
                          html.Div(f"${stats['total_pnl']:+,.2f}",className="stat-value",style={"color":pc,"fontSize":"15px"})],
                         className="glass-card",style={"padding":"9px","textAlign":"center","border":f"1px solid {pc}"}),md=2),
        dbc.Col(html.Div([html.Div("🎯 TP / 🛑 SL",className="stat-label"),
                          html.Div(f"{stats['tp_count']} / {stats['sl_count']}",className="stat-value",style={"color":TXT,"fontSize":"15px"})],
                         className="glass-card",style={"padding":"9px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("📈 بهترین",className="stat-label"),
                          html.Div(f"${stats['best_trade']:+,.2f}",className="stat-value",style={"color":UP,"fontSize":"15px"})],
                         className="glass-card",style={"padding":"9px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("📉 بدترین",className="stat-label"),
                          html.Div(f"${stats['worst_trade']:+,.2f}",className="stat-value",style={"color":DN,"fontSize":"15px"})],
                         className="glass-card",style={"padding":"9px","textAlign":"center"}),md=2),
    ])

def build_symbol_stats_detail(stats):
    if not stats: return html.Div()
    return dbc.Row([
        dbc.Col(html.Div([html.Div("میانگین PnL",className="stat-label"),html.Div(f"${stats['avg_pnl']:+,.2f}",className="stat-value",style={"color":TXT,"fontSize":"13px"})],className="glass-card",style={"padding":"8px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("میانگین PnL٪",className="stat-label"),html.Div(f"{stats['avg_pnl_pct']:+.2f}%",className="stat-value",style={"color":TXT,"fontSize":"13px"})],className="glass-card",style={"padding":"8px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("🟢 Long Win",className="stat-label"),html.Div(f"{stats['long_win_rate']:.1f}%",className="stat-value",style={"color":UP,"fontSize":"13px"})],className="glass-card",style={"padding":"8px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("🔴 Short Win",className="stat-label"),html.Div(f"{stats['short_win_rate']:.1f}%",className="stat-value",style={"color":DN,"fontSize":"13px"})],className="glass-card",style={"padding":"8px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("⚡ لوریج",className="stat-label"),html.Div(f"{stats['avg_leverage']:.1f}x",className="stat-value",style={"color":CYAN,"fontSize":"13px"})],className="glass-card",style={"padding":"8px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("🎯 اطمینان",className="stat-label"),html.Div(f"{stats['avg_confidence']:.0f}%",className="stat-value",style={"color":GOLD,"fontSize":"13px"})],className="glass-card",style={"padding":"8px","textAlign":"center"}),md=2),
    ])

def build_symbol_cumulative_pnl_chart(stats):
    if not stats or not stats["cumulative_pnl"]: return empty_fig("داده‌ای نیست")
    c = stats["cumulative_pnl"]; x = list(range(1, len(c)+1))
    fig = go.Figure()
    lc = UP if c[-1]>=0 else DN
    fig.add_trace(go.Scatter(x=x, y=c, mode="lines", line=dict(color=lc, width=3),
                             fill="tozeroy", fillcolor="rgba(0,255,204,0.1)" if c[-1]>=0 else "rgba(255,34,102,0.1)"))
    fig.add_hline(y=0, line=dict(color=MUT, dash="dot", width=1))
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
                      margin=dict(l=50,r=20,t=50,b=40),
                      xaxis=dict(color=MUT, gridcolor=LINE, title="معامله"),
                      yaxis=dict(color=MUT, gridcolor=LINE, title="PnL ($)"),
                      font=dict(family=FONT_FAMILY, color=TXT),
                      title=dict(text=f"📈 PnL تجمعی — {stats['symbol']}", x=0.5,
                                 font=dict(color=GOLD, size=13)), showlegend=False, height=280)
    return fig

def build_symbol_status_chart(stats):
    if not stats: return empty_fig("داده‌ای نیست")
    labels = ["🎯 TP","🛑 SL","⏰ منقضی","✋ دستی","🔵 باز"]
    values = [stats["tp_count"], stats["sl_count"], stats["expired_count"],
              stats["manual_count"], stats["open"]]
    colors = [UP, DN, MUT, GOLD, BLUE]
    filtered = [(l,v,c) for l,v,c in zip(labels, values, colors) if v>0]
    if not filtered: return empty_fig("داده‌ای نیست")
    labels, values, colors = zip(*filtered)
    fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=0.5, marker=dict(colors=colors),
                                  textinfo="label+percent", textfont=dict(size=10, color=TXT))])
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
                      margin=dict(l=20,r=20,t=50,b=20), font=dict(family=FONT_FAMILY, color=TXT),
                      title=dict(text=f"وضعیت — {stats['symbol']}", x=0.5,
                                 font=dict(color=GOLD, size=13)), showlegend=True,
                      legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center", font=dict(size=9)), height=280)
    return fig

def build_symbol_signals_table(signals):
    if not signals: return html.Div("سیگنالی نیست", style={"color":MUT,"textAlign":"center","padding":"15px"})
    header = html.Tr([html.Th("ID"), html.Th("زمان"), html.Th("جهت"), html.Th("حالت"),
                      html.Th("ورود"), html.Th("SL"), html.Th("TP"), html.Th("حجم"),
                      html.Th("لوریج"), html.Th("اطمینان"), html.Th("وضعیت"),
                      html.Th("PnL"), html.Th("PnL%")],
                     style={"color":MUT,"fontSize":9,"textAlign":"center"})
    rows = []
    for s in signals:
        dt = "🟢 LONG" if s["direction"]==1 else "🔴 SHORT"; dc = UP if s["direction"]==1 else DN
        st = s["status"]
        if st=="tp_hit": stt, sc, bg = "🎯 TP", UP, "rgba(0,255,204,0.04)"
        elif st=="sl_hit": stt, sc, bg = "🛑 SL", DN, "rgba(255,34,102,0.04)"
        elif st=="expired": stt, sc, bg = "⏰ منقضی", MUT, "rgba(122,122,168,0.04)"
        elif st=="closed_manual": stt, sc, bg = "✋ دستی", GOLD, "rgba(255,215,0,0.04)"
        else: stt, sc, bg = "🔵 باز", BLUE, "rgba(0,170,255,0.04)"
        mt, mc = get_mode_badge(s.get("trading_mode","normal"))
        if s["pnl"] is not None:
            pc = UP if s["pnl"]>0 else DN
            pt, ppt = f"${s['pnl']:+,.2f}", f"{s['pnl_pct']:+.2f}%"
        else: pt=ppt="—"; pc=MUT
        rows.append(html.Tr([html.Td(f"#{s['id']}"), html.Td(s["created_at"][-14:]),
                             html.Td(dt, style={"color":dc,"fontWeight":"bold"}),
                             html.Td(mt, style={"color":mc,"fontSize":"9px"}),
                             html.Td(f"${s['entry_price']:,.4g}"),
                             html.Td(f"${s['sl_price']:,.4g}", style={"color":DN}),
                             html.Td(f"${s['tp_price']:,.4g}", style={"color":UP}),
                             html.Td(f"${s['dollar_amount']:,.2f}", style={"color":BLUE}),
                             html.Td(f"{s.get('leverage',1.0):.1f}x", style={"color":GOLD}),
                             html.Td(f"{s['confidence']:.0f}%", style={"color":GOLD}),
                             html.Td(stt, style={"color":sc,"fontWeight":"bold"}),
                             html.Td(pt, style={"color":pc,"fontWeight":"bold"}),
                             html.Td(ppt, style={"color":pc})],
                            style={"textAlign":"center","background":bg,"fontSize":"10px"}))
    return dbc.Table([html.Thead(header), html.Tbody(rows)],
                     bordered=False, hover=True, responsive=True, size="sm", style={"color":TXT})

# بک‌تست UI
def build_backtest_kpis(stats, initial):
    if stats.get("error"): return html.Div(stats["error"], style={"color":DN,"textAlign":"center"})
    if stats["total_trades"]==0:
        return html.Div("📭 معامله‌ای ثبت نشد.", style={"color":MUT,"textAlign":"center","padding":"20px"})
    pc = UP if stats["total_pnl"]>=0 else DN
    wc = UP if stats["win_rate"]>=50 else (GOLD if stats["win_rate"]>=35 else DN)
    sc = UP if stats["sharpe_ratio"]>=1 else (GOLD if stats["sharpe_ratio"]>=0.5 else MUT)
    pfc = UP if stats["profit_factor"]>=1.5 else (GOLD if stats["profit_factor"]>=1 else DN)
    dc = UP if stats["max_drawdown_pct"]<10 else (GOLD if stats["max_drawdown_pct"]<20 else DN)
    return dbc.Row([
        dbc.Col(html.Div([html.Div("💰 سود/ضرر",className="stat-label"),html.Div(f"${stats['total_pnl']:+,.2f}",className="stat-value",style={"color":pc,"fontSize":"15px"})],className="glass-card",style={"padding":"9px","textAlign":"center","border":f"1px solid {pc}"}),md=2),
        dbc.Col(html.Div([html.Div("📈 بازده",className="stat-label"),html.Div(f"{stats['total_return_pct']:+.2f}%",className="stat-value",style={"color":pc,"fontSize":"15px"})],className="glass-card",style={"padding":"9px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("🏆 وین‌ریت",className="stat-label"),html.Div(f"{stats['win_rate']:.1f}%",className="stat-value",style={"color":wc,"fontSize":"15px"})],className="glass-card",style={"padding":"9px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("📊 Sharpe",className="stat-label"),html.Div(f"{stats['sharpe_ratio']:.2f}",className="stat-value",style={"color":sc,"fontSize":"15px"})],className="glass-card",style={"padding":"9px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("⚡ PF",className="stat-label"),html.Div(f"{stats['profit_factor']:.2f}",className="stat-value",style={"color":pfc,"fontSize":"15px"})],className="glass-card",style={"padding":"9px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("📉 Max DD",className="stat-label"),html.Div(f"{stats['max_drawdown_pct']:.2f}%",className="stat-value",style={"color":dc,"fontSize":"15px"})],className="glass-card",style={"padding":"9px","textAlign":"center"}),md=2),
    ])

def build_backtest_detail(stats):
    if stats.get("error") or stats["total_trades"]==0: return html.Div()
    return dbc.Row([
        dbc.Col(html.Div([html.Div("معاملات",className="stat-label"),html.Div(f"{stats['total_trades']}",className="stat-value",style={"color":TXT,"fontSize":"13px"})],className="glass-card",style={"padding":"8px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("🟢/🔴",className="stat-label"),html.Div(f"{stats['long_trades']}/{stats['short_trades']}",className="stat-value",style={"color":TXT,"fontSize":"13px"})],className="glass-card",style={"padding":"8px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("Long WR",className="stat-label"),html.Div(f"{stats['long_win_rate']:.1f}%",className="stat-value",style={"color":UP,"fontSize":"13px"})],className="glass-card",style={"padding":"8px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("Short WR",className="stat-label"),html.Div(f"{stats['short_win_rate']:.1f}%",className="stat-value",style={"color":DN,"fontSize":"13px"})],className="glass-card",style={"padding":"8px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("🎯/🛑/⏰",className="stat-label"),html.Div(f"{stats['tp_count']}/{stats['sl_count']}/{stats['horizon_count']}",className="stat-value",style={"color":TXT,"fontSize":"13px"})],className="glass-card",style={"padding":"8px","textAlign":"center"}),md=2),
        dbc.Col(html.Div([html.Div("اطمینان",className="stat-label"),html.Div(f"{stats['avg_confidence']:.0f}%",className="stat-value",style={"color":GOLD,"fontSize":"13px"})],className="glass-card",style={"padding":"8px","textAlign":"center"}),md=2),
    ])

def build_equity_curve(eq, initial, symbol):
    if not eq or len(eq)<2: return empty_fig("داده‌ای نیست")
    times = [e["time"] for e in eq]; bals = [e["balance"] for e in eq]
    fb = bals[-1]; lc = UP if fb>=initial else DN
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=times, y=bals, mode="lines", line=dict(color=lc, width=3),
                             fill="tozeroy", fillcolor="rgba(0,255,204,0.1)" if fb>=initial else "rgba(255,34,102,0.1)"))
    fig.add_hline(y=initial, line=dict(color=MUT, dash="dot", width=1),
                  annotation_text=f"اولیه: ${initial:,.0f}", annotation_font=dict(color=MUT, size=9))
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
                      margin=dict(l=60,r=20,t=50,b=40),
                      xaxis=dict(color=MUT, gridcolor=LINE, title="زمان"),
                      yaxis=dict(color=MUT, gridcolor=LINE, title="سرمایه ($)"),
                      font=dict(family=FONT_FAMILY, color=TXT),
                      title=dict(text=f"📈 منحنی سرمایه — {symbol}", x=0.5,
                                 font=dict(color=GOLD, size=13)), showlegend=False, height=380)
    return fig

def build_backtest_trades_table(trades):
    if not trades: return html.Div("معامله‌ای نیست", style={"color":MUT,"textAlign":"center","padding":"20px"})
    header = html.Tr([html.Th("#"), html.Th("زمان ورود"), html.Th("جهت"), html.Th("ورود"),
                      html.Th("SL"), html.Th("TP"), html.Th("حجم"), html.Th("لوریج"),
                      html.Th("اطمینان"), html.Th("خروج"), html.Th("دلیل"),
                      html.Th("PnL"), html.Th("PnL%")],
                     style={"color":MUT,"fontSize":9,"textAlign":"center"})
    rows = []
    for i, t in enumerate(trades, 1):
        dt = "🟢 LONG" if t["direction"]=="Long" else "🔴 SHORT"
        dc = UP if t["direction"]=="Long" else DN
        if t["exit_reason"]=="TP": rt, rc = "🎯 TP", UP
        elif t["exit_reason"]=="SL": rt, rc = "🛑 SL", DN
        else: rt, rc = "⏰ Horizon", MUT
        pc = UP if t["pnl"]>0 else DN
        lev = t.get("leverage", 1.0); lvc = DN if lev>=50 else (GOLD if lev>=20 else UP)
        rows.append(html.Tr([
            html.Td(f"{i}", style={"color":MUT,"fontSize":"9px"}),
            html.Td(pd.to_datetime(t["entry_time"]).strftime("%m-%d %H:%M"), style={"color":MUT,"fontSize":"9px"}),
            html.Td(dt, style={"color":dc,"fontWeight":"bold","fontSize":"10px"}),
            html.Td(f"${t['entry_price']:,.4g}", style={"color":TXT,"fontSize":"10px"}),
            html.Td(f"${t['sl_price']:,.4g}", style={"color":DN,"fontSize":"10px"}),
            html.Td(f"${t['tp_price']:,.4g}", style={"color":UP,"fontSize":"10px"}),
            html.Td(f"${t['dollar_amount']:,.2f}", style={"color":BLUE,"fontSize":"10px"}),
            html.Td(f"{lev:.1f}x", style={"color":lvc,"fontWeight":"bold","fontSize":"10px"}),
            html.Td(f"{t['confidence']:.0f}%", style={"color":GOLD,"fontSize":"10px"}),
            html.Td(f"${t['exit_price']:,.4g}", style={"color":TXT,"fontSize":"10px"}),
            html.Td(rt, style={"color":rc,"fontSize":"10px"}),
            html.Td(f"${t['pnl']:+,.2f}", style={"color":pc,"fontWeight":"bold","fontSize":"10px"}),
            html.Td(f"{t['pnl_pct']:+.2f}%", style={"color":pc,"fontSize":"10px"}),
        ], style={"textAlign":"center","fontSize":"10px"}))
    return dbc.Table([html.Thead(header), html.Tbody(rows)],
                     bordered=False, hover=True, responsive=True, size="sm", style={"color":TXT})

# ==============================================================================
# 11) Dash App
# ==============================================================================
FONT_URL = "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;800&display=swap"
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG, FONT_URL],
                suppress_callback_exceptions=True)
app.title = "Order Flow Resonance Engine v2"
server = app.server

db = SignalDatabase(DB_PATH)

app.index_string = """<!DOCTYPE html>
<html dir="rtl" lang="fa"><head>
{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
body { background:#030308; direction:rtl; text-align:right; }
* { font-family:'Vazirmatn',Tahoma,sans-serif !important; }
.glass-card { background:linear-gradient(145deg,rgba(16,16,37,0.9),rgba(5,5,15,0.95));
    border:1px solid #252545; border-radius:14px; box-shadow:0 0 20px rgba(0,255,255,0.07);
    direction:rtl; text-align:right; }
.stat-value { font-weight:800; font-size:20px; text-shadow:0 0 8px currentColor; }
.stat-label { font-size:10px; color:#7a7aa8; text-transform:uppercase; letter-spacing:1px; }
.Select-control,.Select-menu-outer,.dash-dropdown .Select-control {
    background-color:#101025 !important; border-color:#252545 !important;
    color:#e8e8ff !important; z-index:9999 !important; position:relative; }
.Select-menu-outer { z-index:99999 !important; position:absolute !important;
    background-color:#0a0a18 !important; border:1px solid #252545 !important;
    border-radius:8px !important; max-height:300px !important; overflow-y:auto !important;
    box-shadow:0 10px 40px rgba(0,0,0,0.8) !important; }
.Select-option { background-color:#0a0a18 !important; color:#e8e8ff !important;
    padding:8px 12px !important; cursor:pointer; }
.Select-option:hover,.Select-option.is-focused { background-color:#1a1a35 !important; color:#00ffcc !important; }
.Select-option.is-selected { background-color:#1a2a4a !important; color:#ffd700 !important; }
table { direction:rtl; text-align:right; }
table th,table td { text-align:right !important; padding:5px 7px !important; }
.nav-tabs { direction:rtl; } .nav-tabs .nav-item { margin-left:0 !important; margin-right:4px; }
.btn { direction:rtl; }
input { direction:rtl; text-align:right; background-color:#101025 !important;
    border-color:#252545 !important; color:#e8e8ff !important; }
.rc-slider { direction:ltr; } label { direction:rtl; text-align:right; }
.progress-bar { height:6px; border-radius:3px; background:#252545; overflow:hidden; }
.progress-fill { height:100%; background:#00ffcc; transition:width 0.3s; }
.modal-content { background:#171426 !important; color:#f5efe0 !important;
    border:2px solid #ffd700 !important; border-radius:14px !important; }
.modal-header,.modal-footer { background:#171426 !important; border-color:#3a3450 !important; }
</style></head><body dir="rtl">{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>"""

app.layout = html.Div([
    html.Div([
        html.H3("🌌 Order Flow Resonance Engine v2", style={
            "color":CYAN, "fontWeight":800, "margin":0,
            "textShadow":"0 0 20px rgba(0,255,255,0.5)"}),
        html.Div("۲۱ نماد کامل · Order Flow · WebSocket + REST · {Morindok}",
                 style={"color":MUT, "fontSize":12}),
    ], style={"maxWidth":1400, "margin":"12px auto 8px auto", "padding":"0 15px"}),

    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([html.Label("🪙 نماد (Live)", style={"fontSize":10,"color":MUT}),
                 dcc.Dropdown(id="symbol", value="BTCUSDT", clearable=False, options=SYMBOL_OPTIONS)], md=2),
        dbc.Col([html.Label("⚡ حالت", style={"fontSize":10,"color":MUT}),
                 dcc.Dropdown(id="trading-mode", value="aggressive", clearable=False, options=TRADING_MODE_OPTIONS)], md=2),
        dbc.Col([html.Label("موجودی ($)", style={"fontSize":10,"color":MUT}),
                 dcc.Input(id="initial-balance", type="number", value=DEFAULT_BALANCE, min=10, step=50,
                           style={"width":"100%","padding":6,"borderRadius":8,
                                  "background":CARD2,"color":TXT,"border":f"1px solid {LINE}"})], md=1),
        dbc.Col([html.Label("تیک سایز", style={"fontSize":10,"color":MUT}),
                 dcc.Input(id="tick-size", type="number", value=10.0, min=0.00001, step=0.1,
                           style={"width":"100%","padding":6,"borderRadius":8,
                                  "background":CARD2,"color":TXT,"border":f"1px solid {LINE}"})], md=1),
        dbc.Col([html.Label("کندل (ثانیه)", style={"fontSize":10,"color":MUT}),
                 dcc.Dropdown(id="interval-sec", value=60, clearable=False,
                              options=[{"label":f"{m} دقیقه","value":m*60} for m in [1,5,15,30,60]])], md=2),
        dbc.Col([html.Label("اتصال", style={"fontSize":10,"color":MUT}),
                 dbc.Button("🔌 Apply", id="apply-btn", color="primary",
                            style={"width":"100%","fontWeight":"bold"})], md=2),
        dbc.Col(html.Div(id="conn-status", style={"textAlign":"center","padding":"8px",
                                                   "borderRadius":8,"marginTop":"18px"}), md=2),
    ])), className="glass-card", style={"maxWidth":1400, "margin":"8px auto"}),

    html.Div(id="mode-info-panel", style={"maxWidth":1400, "margin":"8px auto"}),

    dbc.Tabs([
        dbc.Tab(label="🌀 Live Order Flow", tab_id="tab-orderflow", children=[
            html.Div(id="signal-map-panel", style={"margin":"10px 0"}),
            dbc.Row([
                dbc.Col(dbc.Card(dbc.CardBody([dcc.Graph(id="footprint-graph", config={"displayModeBar":False})]),
                                 className="glass-card"), md=8),
                dbc.Col(dbc.Card(dbc.CardBody([dcc.Graph(id="orderbook-graph", config={"displayModeBar":False})]),
                                 className="glass-card"), md=4),
            ]),
            dbc.Row([dbc.Col(dbc.Card(dbc.CardBody([dcc.Graph(id="cumulative-delta-graph", config={"displayModeBar":False})]),
                                         className="glass-card"), md=12)]),
            html.Div(id="global-warning-banner", style={"display":"none"}),
        ]),

        dbc.Tab(label="📡 اسکن همه ارزها (۲۱ نماد)", tab_id="tab-scan", children=[
            html.Div([html.Div("📌 اسکن کامل همه ۲۱ نماد از طریق REST + Order Flow · سیگنال‌ها به‌صورت خودکار در دیتابیس ذخیره می‌شوند",
                               style={"fontSize":11,"color":MUT,"margin":"12px 5px"}),
                      dbc.Button("🔍 اسکن همه ۲۱ ارز", id="scan-all-btn", color="info",
                                 style={"margin":"8px 5px","fontWeight":"bold","fontSize":"13px","padding":"8px 20px"})]),
            html.Div(id="scan-progress", style={"margin":"10px 0"}),
            html.Div(id="signals-summary", style={"margin":"12px 0"}),
            dbc.Card(dbc.CardBody([
                html.H5("📊 نتایج اسکن — سیگنال‌های پیدا شده", style={"color":CYAN,"fontSize":"13px","marginBottom":"8px"}),
                html.Div(id="scan-results-table"),
            ]), className="glass-card", style={"margin":"10px 0"}),
            dbc.Card(dbc.CardBody([
                html.H5("💼 معاملات باز — PnL زنده", style={"color":CYAN,"fontSize":"13px","marginBottom":"8px"}),
                html.Div(id="open-positions-table"),
            ]), className="glass-card"),
        ]),

        dbc.Tab(label="📊 بک‌تست تاریخی", tab_id="tab-backtest", children=[
            dbc.Card(dbc.CardBody([
                html.Div("📌 بک‌تست روی داده‌های تاریخی (۱ ماه تا ۱ سال) — نماد از تنظیمات بالا",
                         style={"fontSize":11,"color":MUT,"marginBottom":"10px"}),
                dbc.Row([
                    dbc.Col([html.Label("📅 دوره", style={"fontSize":11,"color":MUT}),
                             dcc.Dropdown(id="backtest-period", value="3m", clearable=False,
                                          options=BACKTEST_PERIOD_OPTIONS)], md=3),
                    dbc.Col([html.Label("تایم‌فریم", style={"fontSize":11,"color":MUT}),
                             dcc.Dropdown(id="backtest-interval", value="15", clearable=False,
                                          options=[{"label":"5m","value":"5"},
                                                   {"label":"15m","value":"15"},
                                                   {"label":"30m","value":"30"},
                                                   {"label":"1h","value":"60"},
                                                   {"label":"4h","value":"240"}])], md=3),
                    dbc.Col([dbc.Button("🚀 اجرای بک‌تست", id="run-backtest-btn", color="success",
                                        style={"width":"100%","fontWeight":"bold","marginTop":"20px"})], md=3),
                ]),
            ]), className="glass-card", style={"margin":"10px 0"}),
            html.Div(id="backtest-kpis", style={"margin":"12px 0"}),
            html.Div(id="backtest-detail-stats", style={"margin":"8px 0"}),
            dbc.Card(dbc.CardBody([dcc.Graph(id="backtest-equity-chart", config={"displayModeBar":False})]),
                     className="glass-card", style={"margin":"12px 0"}),
            dbc.Card(dbc.CardBody([
                html.H5("📋 معاملات بک‌تست", style={"color":GOLD,"fontSize":"13px","marginBottom":"8px","textAlign":"center"}),
                html.Div(id="backtest-trades-table"),
            ]), className="glass-card"),
        ]),

        dbc.Tab(label="📈 آمار وین‌ریت", tab_id="tab-symbol-stats", children=[
            html.Div([html.Div("آمار جزئی برای نماد انتخاب‌شده از تنظیمات بالا",
                               style={"fontSize":11,"color":MUT,"margin":"12px 5px"}),
                      dbc.Button("🔄 به‌روزرسانی", id="refresh-stats-btn", color="info",
                                 style={"margin":"8px 5px","fontWeight":"bold"})]),
            html.Div(id="symbol-stats-kpis", style={"margin":"12px 0"}),
            html.Div(id="symbol-stats-detail", style={"margin":"8px 0"}),
            dbc.Row([
                dbc.Col(dbc.Card(dbc.CardBody([dcc.Graph(id="symbol-pnl-chart", config={"displayModeBar":False})]),
                                 className="glass-card"), md=7),
                dbc.Col(dbc.Card(dbc.CardBody([dcc.Graph(id="symbol-status-chart", config={"displayModeBar":False})]),
                                 className="glass-card"), md=5),
            ]),
            dbc.Card(dbc.CardBody([
                html.H5("📋 سیگنال‌های گذشته این نماد", style={"color":GOLD,"fontSize":"13px","marginBottom":"8px","textAlign":"center"}),
                html.Div(id="symbol-signals-table"),
            ]), className="glass-card"),
        ]),

        dbc.Tab(label="📋 تاریخچه کل", tab_id="tab-history", children=[
            html.Div([html.Div("PnL زنده + سود کل = قطعی + شناور",
                               style={"fontSize":11,"color":MUT,"margin":"12px 5px"}),
                      dbc.Button("🔄 به‌روزرسانی", id="history-refresh-btn", color="warning",
                                 style={"margin":"8px 5px","fontWeight":"bold"})]),
            html.Div(id="history-stats", style={"margin":"12px 0"}),
            dbc.Card(dbc.CardBody([html.Div(id="history-table")]), className="glass-card"),
        ]),
    ], id="main-tabs", active_tab="tab-scan", style={"maxWidth":1400,"margin":"0 auto"}),

    html.Div("💡 هر ۲۱ ارز به‌صورت خودکار اسکن می‌شود. سیگنال‌ها از ۵ گیت Order Flow عبور می‌کنند و در دیتابیس ذخیره می‌شوند. "
             "WebSocket زنده روی نماد انتخابی + REST برای اسکن همه ارزها.",
             style={"fontSize":10.5,"color":MUT,"marginTop":15,"direction":"rtl","lineHeight":"1.8",
                    "textAlign":"center","maxWidth":1400,"margin":"15px auto","padding":"0 15px 15px 15px"}),

    dcc.Interval(id="live-tick", interval=2500, n_intervals=0),
    dcc.Interval(id="positions-pnl-tick", interval=10_000, n_intervals=0),
    dcc.Interval(id="db-update-tick", interval=30_000, n_intervals=0),
    dcc.Interval(id="history-pnl-tick", interval=10_000, n_intervals=0),
    dcc.Store(id="scan-results-store"),

    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle(id="signal-modal-title", style={"color":CREAM,"fontWeight":"800"}),
                        close_button=True, style={"background":DARK_BG,"borderBottom":f"1px solid {DARK_BORDER}"}),
        dbc.ModalBody(id="signal-modal-body", style={"background":DARK_BG,"color":CREAM}),
        dbc.ModalFooter(dbc.Button("بستن", id="signal-modal-close",
                                   style={"background":GOLD,"color":BG,"fontWeight":"800","border":"none",
                                          "borderRadius":"10px","padding":"6px 20px"}),
                        style={"background":DARK_BG,"borderTop":f"1px solid {DARK_BORDER}"}),
    ], id="signal-modal", is_open=False, centered=True, size="lg"),
], style={"background":BG, "minHeight":"100vh", "padding":"10px", "fontFamily":FONT_FAMILY})

# ==============================================================================
# 12) Callbacks
# ==============================================================================
@app.callback(Output("conn-status","children"), Output("conn-status","style"),
              Input("apply-btn","n_clicks"), State("symbol","value"),
              prevent_initial_call=False)
def apply_connection(_, symbol):
    symbol = (symbol or "BTCUSDT").upper()
    with STATE_LOCK: needs = (CONN_STATUS["symbol"]!=symbol or CURRENT_STREAM is None)
    if needs: restart_stream(symbol, DEFAULT_CATEGORY)
    with STATE_LOCK: conn = CONN_STATUS["connected"]
    bg = UP if conn else GOLD
    return f"● {symbol} | {'متصل' if conn else 'در حال اتصال...'}", \
           {"background":bg,"color":BG,"fontWeight":"700","padding":"6px 14px",
            "borderRadius":"18px","textAlign":"center"}

@app.callback(Output("mode-info-panel","children"),
              Input("trading-mode","value"), State("initial-balance","value"))
def update_mode_info(tm, bal):
    try: bal = float(bal or DEFAULT_BALANCE)
    except: bal = DEFAULT_BALANCE
    return build_mode_info_panel(tm or "normal", bal, db)

@app.callback(
    Output("footprint-graph","figure"), Output("orderbook-graph","figure"),
    Output("cumulative-delta-graph","figure"),
    Output("signal-map-panel","children"),
    Output("global-warning-banner","children"), Output("global-warning-banner","style"),
    Output("signal-modal","is_open"), Output("signal-modal-title","children"),
    Output("signal-modal-body","children"),
    Input("live-tick","n_intervals"),
    State("tick-size","value"), State("interval-sec","value"),
    State("symbol","value"), State("trading-mode","value"),
    State("initial-balance","value"))
def update_orderflow(_, tick_size, interval_sec, symbol, trading_mode, balance):
    tick_size = float(tick_size or DEFAULT_TICK_SIZE)
    interval_sec = int(interval_sec or DEFAULT_INTERVAL_SEC)
    symbol = symbol or "BTCUSDT"; trading_mode = trading_mode or "normal"
    try: balance = float(balance or DEFAULT_BALANCE)
    except: balance = DEFAULT_BALANCE
    with STATE_LOCK: pair = CONN_STATUS["symbol"]
    df = get_trades_df()
    fp = build_footprint(df, tick_size, interval_sec, MAX_COLUMNS)
    imb = compute_diagonal_imbalances(fp) if fp else {}
    stacked = detect_stacked(imb, fp["rows"], fp["cols"]) if fp else set()
    readings = compute_bar_readings(fp) if fp else []
    gates, sig_candidates, verdict = evaluate_signal_map(readings, imb, stacked)
    fp_fig = render_footprint_figure(fp, pair)
    asks, bids = get_orderbook_snapshot()
    ob_fig = render_orderbook_figure(asks, bids)
    cd_fig = render_cumulative_delta(fp)
    signal_map = render_signal_map_panel(readings, gates, verdict, None, list(SIGNAL_LOG), pair)
    banner_text = ""; banner_style = {"display":"none"}
    modal_open = False; modal_title = ""; modal_body = html.Div()
    if sig_candidates:
        with STATE_LOCK:
            for sig_info in sig_candidates:
                key = (sig_info["kind"], sig_info["side"], str(sig_info["last"]["col"]))
                last_fired = SIGNAL_STATE["fired_keys"].get(key)
                if last_fired is None or (time.time()-last_fired)>SIG_COOLDOWN_SEC:
                    SIGNAL_STATE["fired_keys"][key] = time.time()
                    SIGNAL_STATE["last_id"] += 1
                    sig_info["id"] = SIGNAL_STATE["last_id"]
                    sig_info["time_str"] = pd.Timestamp(sig_info["last"]["col"]).strftime("%H:%M")
                    SIGNAL_STATE["latest"] = sig_info
                    SIGNAL_LOG.appendleft(sig_info)
                    klines_df = get_klines(symbol, "15", limit=100)
                    if not klines_df.empty and len(klines_df)>=30:
                        risk_engine = RiskEngine(trading_mode=trading_mode)
                        atr_arr = risk_engine.calculate_atr(klines_df)
                        current_atr = atr_arr[-1]; current_price = klines_df["close"].iloc[-1]
                    else:
                        current_price = sig_info["last"]["close"] or sig_info["last"]["poc"]
                        current_atr = current_price*0.01
                    available = get_available_margin(balance, db)
                    if not db.has_open_signal(symbol) and available>=5.0:
                        side = sig_info["side"]; signal = 1 if side=="LONG" else -1
                        confidence = min(100.0, sig_info.get("vol_ratio",1.0)*30+40)
                        risk_e = RiskEngine(trading_mode=trading_mode)
                        tp_sl = risk_e.calculate_tp_sl(current_price, signal, current_atr, confidence)
                        position = risk_e.calculate_position(balance, current_price, tp_sl["sl_distance"], confidence, available)
                        if position["margin_used"] <= available:
                            sig_data = {
                                "symbol":symbol, "signal":signal, "entry_price":current_price,
                                "sl_price":tp_sl["sl_price"], "tp_price":tp_sl["tp_price"],
                                "dollar_amount":position["dollar_amount"], "confidence":confidence,
                                "final_score":confidence*sig_info.get("vol_ratio",1.0),
                                "rr_ratio":tp_sl["rr_ratio"],
                                "timestamp":datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                                "leverage":position["leverage"], "margin_used":position["margin_used"],
                                "trading_mode":trading_mode,
                            }
                            db.save_signal(sig_data, "orderflow", 0.0,
                                          kind=sig_info["kind"], reason=sig_info["title"])
                    modal_open = True
                    modal_title = f"🚨 سیگنال جدید · {sig_info['title']}"
                    m = sig_info["last"]
                    modal_body = html.Div([
                        html.Div(f"نماد: {pair} · زمان: {sig_info.get('time_str','-')}",
                                 style={"color":GOLD,"fontWeight":"800","marginBottom":"10px"}),
                        html.Div(f"نوع: {sig_info['kind']} · جهت: {sig_info['side']}",
                                 style={"color":CREAM,"marginBottom":"10px"}),
                        html.Div(f"حجم: {m['total_volume']:,.0f} · دلتا: {m['bar_delta']:+,.0f} ({m['delta_pct']:.1f}%)",
                                 style={"color":CREAM,"fontSize":"12px"}),
                        html.Div(f"POC: {m['poc']:,.0f}" if m["poc"] else "POC: -",
                                 style={"color":CREAM,"fontSize":"12px","marginTop":"5px"}),
                        html.Div("✅ سیگنال در دیتابیس ذخیره شد.",
                                 style={"color":GOLD,"marginTop":"10px","fontSize":"11px"}),
                    ])
                    if verdict=="LONG":
                        banner_text = f"✅ سیگنال LONG · {sig_info['title']}"
                        banner_style = {"display":"block","background":UP,"color":BG,
                                        "fontWeight":"800","padding":"10px","borderRadius":"10px",
                                        "textAlign":"center","margin":"8px 0"}
                    else:
                        banner_text = f"✅ سیگنال SHORT · {sig_info['title']}"
                        banner_style = {"display":"block","background":DN,"color":"#fff",
                                        "fontWeight":"800","padding":"10px","borderRadius":"10px",
                                        "textAlign":"center","margin":"8px 0"}
                    break
    return fp_fig, ob_fig, cd_fig, signal_map, banner_text, banner_style, \
           modal_open, modal_title, modal_body

@app.callback(Output("signal-modal","is_open", allow_duplicate=True),
              Input("signal-modal-close","n_clicks"), prevent_initial_call=True)
def close_modal(n):
    return False if n else dash.no_update

# ★ اسکن همه ۲۱ نماد
@app.callback(
    Output("scan-results-store","data"),
    Output("signals-summary","children"),
    Output("open-positions-table","children"),
    Output("scan-results-table","children"),
    Output("scan-progress","children"),
    Input("scan-all-btn","n_clicks"),
    State("interval-sec","value"),
    State("tick-size","value"),
    State("initial-balance","value"),
    State("trading-mode","value"),
    prevent_initial_call=True)
def scan_all_symbols_callback(_click, interval_sec, tick_size, balance, trading_mode):
    interval_sec = int(interval_sec or DEFAULT_INTERVAL_SEC)
    tick_size = float(tick_size or DEFAULT_TICK_SIZE)
    trading_mode = trading_mode or "normal"
    try: balance = float(balance or DEFAULT_BALANCE)
    except: balance = DEFAULT_BALANCE

    update_open_signals_results(db)

    progress_bar = html.Div([
        html.Div("⏳ در حال اسکن ۲۱ نماد...", style={"color":CYAN,"fontWeight":"bold","marginBottom":"5px"}),
        html.Div(id="scan-status-text", style={"color":MUT,"fontSize":"11px"}),
    ], style={"margin":"8px 0","padding":"10px","background":CARD,"borderRadius":"8px"})

    results = scan_all_symbols_orderflow(balance, trading_mode, interval_sec, tick_size)

    saved = 0
    for sig in results:
        if not db.has_open_signal(sig["symbol"]):
            available = get_available_margin(balance, db)
            if sig["margin_used"] <= available:
                db.save_signal(sig, "orderflow", 0.0, kind=sig["kind"], reason=sig["title"])
                saved += 1

    open_signals = db.get_open_signals()
    live_pnls = calculate_open_pnls_live(db)
    total_pnl_closed = db.get_total_pnl()
    open_pnl_estimate = sum(p["pnl"] for p in live_pnls.values())
    current_balance = balance + total_pnl_closed + open_pnl_estimate
    used_margin = get_total_open_margin(db)
    available_margin = balance - used_margin
    margin_info = {"used":used_margin, "available":available_margin, "total":balance}

    summary = build_signals_summary(len(results), total_pnl_closed, current_balance,
                                    open_pnl_estimate, trading_mode, margin_info)
    positions_table = build_open_positions_table(open_signals, live_pnls)
    scan_table = build_scan_results_table(results)

    progress_done = html.Div([
        html.Div(f"✅ اسکن کامل شد — {len(results)} سیگنال یافت شد · {saved} ذخیره شد",
                 style={"color":UP,"fontWeight":"bold","marginBottom":"5px"}),
        html.Div(f"📊 از {len(SYMBOLS)} نماد · حالت: {TRADING_MODES[trading_mode]['name']}",
                 style={"color":MUT,"fontSize":"11px"}),
    ], style={"margin":"8px 0","padding":"10px","background":CARD,"borderRadius":"8px","border":f"1px solid {UP}"})

    return results, summary, positions_table, scan_table, progress_done

# آپدیت PnL زنده
@app.callback(Output("open-positions-table","children", allow_duplicate=True),
              Output("signals-summary","children", allow_duplicate=True),
              Input("positions-pnl-tick","n_intervals"),
              State("initial-balance","value"), State("main-tabs","active_tab"),
              State("trading-mode","value"), State("scan-results-store","data"),
              prevent_initial_call=True)
def update_positions(_tick, balance, active_tab, trading_mode, scan_data):
    if active_tab != "tab-scan": return dash.no_update, dash.no_update
    try: balance = float(balance or DEFAULT_BALANCE)
    except: balance = DEFAULT_BALANCE
    trading_mode = trading_mode or "normal"
    update_open_signals_results(db)
    open_signals = db.get_open_signals()
    live_pnls = calculate_open_pnls_live(db)
    total_pnl_closed = db.get_total_pnl()
    open_pnl = sum(p["pnl"] for p in live_pnls.values())
    current_balance = balance + total_pnl_closed + open_pnl
    used = get_total_open_margin(db); av = balance-used
    margin_info = {"used":used, "available":av, "total":balance}
    summary = build_signals_summary(len(scan_data or []), total_pnl_closed, current_balance,
                                    open_pnl, trading_mode, margin_info)
    positions_table = build_open_positions_table(open_signals, live_pnls)
    return positions_table, summary

# آمار نماد
@app.callback(Output("symbol-stats-kpis","children"), Output("symbol-stats-detail","children"),
              Output("symbol-pnl-chart","figure"), Output("symbol-status-chart","figure"),
              Output("symbol-signals-table","children"),
              Input("symbol","value"), Input("refresh-stats-btn","n_clicks"),
              Input("db-update-tick","n_intervals"))
def update_symbol_stats(symbol, _click, _tick):
    symbol = symbol or "BTCUSDT"
    update_open_signals_results(db)
    stats = db.get_symbol_stats(symbol)
    sigs = db.get_symbol_signals(symbol, limit=50)
    if not stats:
        si = SYMBOLS.get(symbol, {"icon":"•","name":symbol})
        nd = html.Div(f"📭 هنوز سیگنالی برای {si['icon']} {symbol} ثبت نشده. "
                      f"ابتدا تب «📡 اسکن همه ارزها» را اجرا کنید.",
                      style={"color":MUT,"textAlign":"center","padding":"25px","fontSize":"12px"})
        return nd, html.Div(), empty_fig("داده‌ای نیست"), empty_fig("داده‌ای نیست"), html.Div()
    return build_symbol_stats_kpis(stats), build_symbol_stats_detail(stats), \
           build_symbol_cumulative_pnl_chart(stats), build_symbol_status_chart(stats), \
           build_symbol_signals_table(sigs)

# بک‌تست
@app.callback(Output("backtest-kpis","children"), Output("backtest-detail-stats","children"),
              Output("backtest-equity-chart","figure"), Output("backtest-trades-table","children"),
              Input("run-backtest-btn","n_clicks"),
              State("symbol","value"), State("backtest-interval","value"),
              State("backtest-period","value"), State("initial-balance","value"),
              State("trading-mode","value"), prevent_initial_call=True)
def run_backtest(_click, symbol, interval, period, balance, trading_mode):
    symbol = symbol or "BTCUSDT"; interval = interval or "15"; period = period or "3m"
    trading_mode = trading_mode or "aggressive"
    try: balance = float(balance or DEFAULT_BALANCE)
    except: balance = DEFAULT_BALANCE
    days = BACKTEST_PERIODS.get(period, BACKTEST_PERIODS["3m"])["days"]
    trades, eq, stats = run_historical_backtest(symbol, interval, days, balance, trading_mode)
    if stats.get("error"):
        return html.Div(stats["error"], style={"color":DN,"textAlign":"center"}), html.Div(), \
               empty_fig("داده کافی نیست"), html.Div()
    if stats["total_trades"]==0:
        return build_backtest_kpis(stats, balance), html.Div(), empty_fig("معامله‌ای نبود"), html.Div()
    return build_backtest_kpis(stats, balance), build_backtest_detail(stats), \
           build_equity_curve(eq, balance, symbol), build_backtest_trades_table(trades)

# تاریخچه
@app.callback(Output("history-stats","children"), Output("history-table","children"),
              Input("history-refresh-btn","n_clicks"), Input("db-update-tick","n_intervals"),
              Input("main-tabs","active_tab"), State("initial-balance","value"))
def update_history(_click, _tick, active_tab, balance):
    try: balance = float(balance or DEFAULT_BALANCE)
    except: balance = DEFAULT_BALANCE
    update_open_signals_results(db)
    live_pnls = calculate_open_pnls_live(db)
    open_pnl = sum(p["pnl"] for p in live_pnls.values())
    stats = db.get_signal_stats(balance)
    sigs = db.get_all_signals(limit=200)
    return build_history_stats(stats, open_pnl), build_history_table(sigs, live_pnls)

@app.callback(Output("history-table","children", allow_duplicate=True),
              Output("history-stats","children", allow_duplicate=True),
              Input("history-pnl-tick","n_intervals"),
              State("initial-balance","value"), State("main-tabs","active_tab"),
              prevent_initial_call=True)
def update_history_live(_tick, balance, active_tab):
    if active_tab != "tab-history": return dash.no_update, dash.no_update
    try: balance = float(balance or DEFAULT_BALANCE)
    except: balance = DEFAULT_BALANCE
    live_pnls = calculate_open_pnls_live(db)
    open_pnl = sum(p["pnl"] for p in live_pnls.values())
    stats = db.get_signal_stats(balance)
    sigs = db.get_all_signals(limit=200)
    return build_history_table(sigs, live_pnls), build_history_stats(stats, open_pnl)

# بستن معامله
@app.callback(Output("open-positions-table","children", allow_duplicate=True),
              Output("history-table","children", allow_duplicate=True),
              Output("history-stats","children", allow_duplicate=True),
              Input({"type":"close-btn","index":ALL},"n_clicks"),
              State("initial-balance","value"), State("main-tabs","active_tab"),
              prevent_initial_call=True)
def close_signal_callback(n_list, balance, active_tab):
    if not any(n_list): return dash.no_update, dash.no_update, dash.no_update
    triggered = ctx.triggered_id
    if not triggered or not isinstance(triggered, dict): return dash.no_update, dash.no_update, dash.no_update
    sid = triggered.get("index")
    if sid is None: return dash.no_update, dash.no_update, dash.no_update
    sig = db.get_signal_by_id(sid)
    if not sig or sig["status"]!="open": return dash.no_update, dash.no_update, dash.no_update
    df = get_klines(sig["symbol"], "1", limit=1)
    if df.empty: return dash.no_update, dash.no_update, dash.no_update
    cp = df["close"].iloc[-1]; ct = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    ep = sig["entry_price"]; d = sig["direction"]; da = sig["dollar_amount"]
    size = da/ep if ep>0 else 0
    pnl = ((cp-ep) if d==1 else (ep-cp))*size
    pnl_pct = (pnl/da*100) if da>0 else 0
    db.close_signal(sid, cp, ct, pnl, pnl_pct, "Manual Close ✋")
    try: balance = float(balance or DEFAULT_BALANCE)
    except: balance = DEFAULT_BALANCE
    open_signals = db.get_open_signals(); live_pnls = calculate_open_pnls_live(db)
    open_pnl = sum(p["pnl"] for p in live_pnls.values())
    stats = db.get_signal_stats(balance); sigs_from_db = db.get_all_signals(limit=200)
    return build_open_positions_table(open_signals, live_pnls), \
           build_history_table(sigs_from_db, live_pnls), \
           build_history_stats(stats, open_pnl)

def open_browser():
    webbrowser.open("http://127.0.0.1:8050")

if __name__ == "__main__":
    threading.Timer(2, open_browser).start()
    print("="*60)
    print("🌌 Order Flow Resonance Engine v2")
    print("   ✅ ۲۱ نماد کامل با اسکن REST")
    print("   ✅ WebSocket زنده روی نماد انتخابی")
    print("   ✅ بک‌تست تاریخی (۱ ماه تا ۱ سال)")
    print("   ✅ دیتابیس + آمار وین‌ریت")
    print("   🌐 http://127.0.0.1:8050")
    print("="*60)
    restart_stream("BTCUSDT", DEFAULT_CATEGORY)
    time.sleep(2)
    app.run(debug=True, host="0.0.0.0", port=8050, use_reloader=False)