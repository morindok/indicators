# -*- coding: utf-8 -*-
"""
HIVE SCALPER-SNIPER  —  لوریج ۲۰× | اسکالپ سریع | اسنایپر
اسکن لحظه‌ای ~۱۰۰ نماد → انتخاب ۵ موقعیت همزمان
سرمایه اولیه ۵۰۰ دلار | ریسک مدیریت‌شده
این یک شبیه‌ساز است. سود تضمینی وجود ندارد.
"""

import os, time, json, math, sqlite3, hashlib, threading
from datetime import datetime, timezone
from collections import deque
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import dash
from dash import dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

# ────────────────────────────────────────────────
BG, CARD, LINE, TXT, MUT = "#0b1220", "#121c30", "#23314d", "#e8ecf4", "#8fa3c0"
GOLD, UP, DN, NEON, ACCENT, ORANGE = "#f0b90b", "#16a085", "#e74c3c", "#00f5d4", "#7b61ff", "#ff9f1c"
# ────────────────────────────────────────────────
# اتصال پایدار بایبیت
REST = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0", "Accept": "application/json",
    "Referer": "https://www.bybit.com/"
})
_ACTIVE = {"url": None}
_lock = threading.Lock()
_last = 0.0

def bybit_get(path, params, timeout=7):
    global _last
    with _lock:
        if time.time() - _last < 0.07:
            time.sleep(0.07)
        _last = time.time()
    cands = ([_ACTIVE["url"]] if _ACTIVE["url"] else []) + [u for u in REST if u != _ACTIVE["url"]]
    for base in cands:
        try:
            r = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code in (403, 451): continue
            r.raise_for_status()
            d = r.json()
            if d.get("retCode") == 0:
                _ACTIVE["url"] = base
                return d
        except: continue
    return None

def get_klines(symbol, interval="5", limit=80):
    d = bybit_get("/v5/market/kline", {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit})
    if not d or "list" not in (d.get("result") or {}): return pd.DataFrame()
    lst = d["result"]["list"]
    if not lst: return pd.DataFrame()
    df = pd.DataFrame(lst, columns=["ts","open","high","low","close","volume","turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
    for c in ["open","high","low","close","volume"]:
        df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)

def get_all_tickers():
    d = bybit_get("/v5/market/tickers", {"category": "linear"})
    if not d or not d.get("result", {}).get("list"): return {}
    out = {}
    for t in d["result"]["list"]:
        if not t["symbol"].endswith("USDT"): continue
        try:
            out[t["symbol"]] = {
                "last": float(t["lastPrice"]),
                "bid": float(t.get("bid1Price") or t["lastPrice"]),
                "ask": float(t.get("ask1Price") or t["lastPrice"]),
                "vol24": float(t.get("volume24h") or 0),
                "turn24": float(t.get("turnover24h") or 0),
                "chg": float(t.get("price24hPcnt") or 0),
            }
        except: continue
    return out

# ────────────────────────────────────────────────
# دیتابیس
DB = Path("hive_scalper.db")
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT, side TEXT, entry REAL, size_usd REAL, qty REAL,
        leverage INTEGER, liq_price REAL, entry_time TEXT,
        exit_time TEXT, exit_price REAL, pnl REAL, status TEXT, reason TEXT, votes TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS equity (ts TEXT, equity REAL, open_n INTEGER)""")
    conn.commit(); conn.close()

def db_set(k, v):
    conn = sqlite3.connect(DB)
    conn.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (k, json.dumps(v) if not isinstance(v,str) else v))
    conn.commit(); conn.close()

def db_get(k, default=None):
    conn = sqlite3.connect(DB)
    r = conn.execute("SELECT value FROM state WHERE key=?", (k,)).fetchone()
    conn.close()
    if not r: return default
    try: return json.loads(r[0])
    except: return r[0]

def save_trade(t):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""INSERT INTO trades (symbol,side,entry,size_usd,qty,leverage,liq_price,entry_time,status,reason,votes)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
              (t["symbol"],t["side"],t["entry"],t["size_usd"],t["qty"],t["leverage"],t["liq_price"],
               t["entry_time"],"open",t.get("reason",""),json.dumps(t.get("votes",{}))))
    conn.commit(); tid = c.lastrowid; conn.close()
    return tid

def close_trade(tid, exit_p, pnl):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE trades SET exit_time=?,exit_price=?,pnl=?,status='closed' WHERE id=?",
                 (datetime.now(timezone.utc).isoformat(), exit_p, pnl, tid))
    conn.commit(); conn.close()

def get_open():
    conn = sqlite3.connect(DB)
    rows = conn.execute("SELECT id,symbol,side,entry,size_usd,qty,leverage,liq_price,entry_time,reason,votes FROM trades WHERE status='open'").fetchall()
    conn.close()
    return [{"id":r[0],"symbol":r[1],"side":r[2],"entry":r[3],"size_usd":r[4],"qty":r[5],
             "leverage":r[6],"liq_price":r[7],"entry_time":r[8],"reason":r[9],"votes":json.loads(r[10] or "{}")} for r in rows]

def get_closed(limit=100):
    conn = sqlite3.connect(DB)
    rows = conn.execute("SELECT id,symbol,side,entry,exit_price,size_usd,pnl,entry_time,exit_time,reason FROM trades WHERE status='closed' ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
    conn.close()
    return [{"id":r[0],"symbol":r[1],"side":r[2],"entry":r[3],"exit":r[4],"size_usd":r[5],"pnl":r[6],
             "entry_time":r[7],"exit_time":r[8],"reason":r[9]} for r in rows]

def record_eq(eq, n):
    conn = sqlite3.connect(DB)
    conn.execute("INSERT INTO equity VALUES (?,?,?)", (datetime.now(timezone.utc).isoformat(), eq, n))
    conn.commit(); conn.close()

def get_eq_hist():
    conn = sqlite3.connect(DB)
    rows = conn.execute("SELECT ts,equity FROM equity ORDER BY ts").fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["ts","equity"]) if rows else pd.DataFrame({"ts":[],"equity":[]})

# ────────────────────────────────────────────────
# پارامترهای اسکالپر/اسنایپر با لوریج ۲۰
LEVERAGE = 20
INITIAL = 500.0
MAX_POS = 5
COMMISSION = 0.0006          # taker
SPREAD_BPS = 1.8
# ریسک: حداکثر ۱.۲٪ از کل سرمایه روی هر پوزیشن (با لوریج ۲۰ یعنی حرکت قیمت ~۰.۰۶٪)
RISK_PER_TRADE = 0.012
TP_PCT = 0.0045              # هدف اسکالپ ~۰.۴۵٪ حرکت قیمت → ۹٪ روی مارجین
SL_PCT = 0.0028              # استاپ ~۰.۲۸٪ حرکت قیمت → ۵.۶٪ روی مارجین
MAX_HOLD_MIN = 18            # حداکثر نگه‌داری ۱۸ دقیقه

CPU = os.cpu_count() or 4
NEURONS = CPU * 3072         # قدرت بالاتر

class Heart:
    def __init__(self):
        self.seq = [1,1]
        self.beat = 0
    def pulse(self):
        n = self.seq[-1] + self.seq[-2]
        self.seq.append(n)
        if len(self.seq) > 30: self.seq.pop(0)
        self.beat += 1
        return bin(n)[2:][-10:], n

class Organism:
    def __init__(self, name, role, weight=1.0):
        self.name = name
        self.role = role
        self.weight = weight
        self.neurons = int(NEURONS * (1.3 if role=="SNIPER" else 1.1 if role=="SCALPER" else 1.0))

    def score(self, feat):
        """امتیاز خام بر اساس ویژگی‌های لحظه‌ای"""
        mom = feat["mom"]
        vol_surge = feat["vol_surge"]
        pressure = feat["pressure"]
        spread_q = feat["spread_q"]
        rsi_ext = feat["rsi_ext"]

        if self.role == "SNIPER":
            # فقط سیگنال خیلی تمیز و قوی
            s = 0.35*mom + 0.25*vol_surge + 0.25*pressure + 0.15*spread_q
            if abs(s) < 0.42 or abs(rsi_ext) < 0.3: return 0.0
            return s * 1.25 * self.weight
        elif self.role == "SCALPER":
            # سرعت و حجم
            s = 0.30*mom + 0.40*vol_surge + 0.20*pressure + 0.10*spread_q
            return s * 1.15 * self.weight
        elif self.role == "FLOW":
            s = 0.20*mom + 0.35*vol_surge + 0.35*pressure + 0.10*spread_q
            return s * 1.1 * self.weight
        else:  # MOMENTUM
            s = 0.45*mom + 0.25*vol_surge + 0.20*pressure + 0.10*rsi_ext
            return s * self.weight

class Hive:
    def __init__(self):
        init_db()
        self.heart = Heart()
        self.capital = db_get("capital", INITIAL)
        self.peak = db_get("peak", INITIAL)
        self.awareness = db_get("awareness", 0.55)
        self.win_streak = db_get("ws", 0)
        self.loss_streak = db_get("ls", 0)
        self.orgs = [
            Organism("Aether", "SNIPER", 1.40),
            Organism("Pulse",  "SCALPER", 1.30),
            Organism("Flux",   "FLOW", 1.20),
            Organism("Vector", "MOMENTUM", 1.10),
        ]
        self.last_stats = {"scanned":0, "cands":0, "opened":0}
        self._lock = threading.Lock()

    def total_neurons(self):
        return sum(o.neurons for o in self.orgs)

    def features(self, df, ticker):
        if df is None or len(df) < 30: return None
        close = df["close"].values
        vol = df["volume"].values
        # مومنتوم کوتاه
        mom = (close[-1] - close[-6]) / (close[-6] + 1e-12)
        mom = float(np.clip(mom * 25, -1, 1))
        # شتاب حجم
        vol_recent = vol[-5:].mean()
        vol_base = vol[-20:].mean() + 1e-12
        vol_surge = float(np.clip((vol_recent / vol_base - 1) * 1.8, -1, 1))
        # فشار قیمت
        deltas = np.diff(close[-8:])
        pressure = float(np.clip(np.mean(deltas) / (np.std(deltas) + 1e-12) * 0.6, -1, 1))
        # کیفیت اسپرد
        mid = ticker["last"]
        spread = (ticker["ask"] - ticker["bid"]) / (mid + 1e-12)
        spread_q = float(np.clip(1.0 - spread * 900, 0, 1))
        # RSI افراطی
        delta = pd.Series(close).diff()
        gain = delta.clip(lower=0).rolling(10).mean()
        loss = (-delta.clip(upper=0)).rolling(10).mean()
        rs = gain / (loss + 1e-12)
        rsi = 100 - (100 / (1 + rs)).iloc[-1]
        rsi_ext = 1.0 if rsi < 28 else (-1.0 if rsi > 72 else (0.4 if rsi < 38 else (-0.4 if rsi > 62 else 0)))
        return {"mom":mom, "vol_surge":vol_surge, "pressure":pressure, "spread_q":spread_q, "rsi_ext":rsi_ext}

    def select_candidates(self, tickers, n=14):
        ranked = []
        for sym, t in tickers.items():
            if t["turn24"] < 800_000: continue
            score = math.log10(t["turn24"]+1)*0.4 + abs(t["chg"])*90*0.4 + (0.3 if t["vol24"]>1e6 else 0.1)
            ranked.append((sym, score, t))
        ranked.sort(key=lambda x: -x[1])
        return ranked[:n]

    def decide(self, feat):
        if feat is None: return None
        votes = []
        for o in self.orgs:
            s = o.score(feat)
            if abs(s) < 0.28: continue
            side = "long" if s > 0 else "short"
            votes.append({"org":o.name, "role":o.role, "side":side, "score":s, "w":o.weight})
        if len(votes) < 2: return None
        long_s = sum(v["score"]*v["w"] for v in votes if v["side"]=="long")
        short_s = sum(abs(v["score"])*v["w"] for v in votes if v["side"]=="short")
        if long_s > short_s and long_s > 0.55:
            side, final = "long", long_s
        elif short_s > long_s and short_s > 0.55:
            side, final = "short", short_s
        else:
            return None
        agreeing = [v for v in votes if v["side"]==side]
        if len(agreeing) < 2: return None
        # اسنایپر باید حداقل یکی باشد یا اسکالپر قوی
        has_sniper = any(v["role"]=="SNIPER" for v in agreeing)
        has_scalper = any(v["role"]=="SCALPER" for v in agreeing)
        if not (has_sniper or has_scalper): return None
        conv = min(1.0, final / 1.8 * (1.15 if has_sniper else 1.0))
        if conv < 0.40: return None
        reason = " | ".join(f"{v['org']}:{v['side'][0]}{v['score']:.2f}" for v in agreeing)
        return {"side":side, "conv":conv, "votes":{v["org"]:v for v in votes}, "reason":f"HIVE[{len(agreeing)}] {reason}"}

    def size_usd(self, conv):
        open_n = len(get_open())
        if open_n >= MAX_POS: return 0.0
        free = max(0.0, self.capital - sum(t["size_usd"] for t in get_open()))
        # سایز بر اساس ریسک ثابت (نه درصد آزاد)
        risk_cap = self.capital * RISK_PER_TRADE
        # با لوریج ۲۰، حرکت SL_PCT قیمت ≈ ریسک روی مارجین
        size = risk_cap / (SL_PCT * LEVERAGE)   # اندازه اسمی
        size = size * (0.7 + 0.3 * conv)
        size = min(size, free * 0.35, self.capital * 0.22)
        return max(20.0, size)

    def try_open(self, sym, ticker, decision):
        with self._lock:
            if len(get_open()) >= MAX_POS: return False
            if any(t["symbol"]==sym for t in get_open()): return False
            size = self.size_usd(decision["conv"])
            if size < 20: return False
            price = ticker["last"]
            # ورود با اسپرد
            entry = price * (1 + SPREAD_BPS/10000) if decision["side"]=="long" else price * (1 - SPREAD_BPS/10000)
            qty = (size * LEVERAGE) / entry
            # قیمت لیکوئید تقریبی (برای isolated ساده)
            if decision["side"]=="long":
                liq = entry * (1 - 0.95/LEVERAGE)
            else:
                liq = entry * (1 + 0.95/LEVERAGE)
            t = {
                "symbol":sym, "side":decision["side"], "entry":entry,
                "size_usd":size, "qty":qty, "leverage":LEVERAGE, "liq_price":liq,
                "entry_time":datetime.now(timezone.utc).isoformat(),
                "reason":decision["reason"], "votes":decision["votes"]
            }
            save_trade(t)
            return True

    def manage(self):
        opens = get_open()
        if not opens: return
        tickers = get_all_tickers()
        now = datetime.now(timezone.utc)
        for t in opens:
            last = tickers.get(t["symbol"],{}).get("last")
            if last is None: continue
            # PnL با لوریج
            if t["side"]=="long":
                pnl_pct_price = (last - t["entry"]) / t["entry"]
            else:
                pnl_pct_price = (t["entry"] - last) / t["entry"]
            pnl_usd = pnl_pct_price * t["size_usd"] * LEVERAGE - t["size_usd"] * COMMISSION * 2

            hold_min = (now - datetime.fromisoformat(t["entry_time"])).total_seconds() / 60
            # خروج اسکالپر
            close = False
            if pnl_pct_price >= TP_PCT or pnl_pct_price <= -SL_PCT:
                close = True
            elif hold_min >= MAX_HOLD_MIN:
                close = True
            elif hold_min > 4 and abs(pnl_pct_price) < 0.0009:  # رنج مرده
                close = True
            # نزدیک لیکوئید
            if t["side"]=="long" and last <= t["liq_price"] * 1.01:
                close = True
            if t["side"]=="short" and last >= t["liq_price"] * 0.99:
                close = True

            if close:
                close_trade(t["id"], last, pnl_usd)
                self.capital += pnl_usd
                if pnl_usd > 0:
                    self.win_streak += 1; self.loss_streak = 0
                else:
                    self.win_streak = 0; self.loss_streak += 1
                db_set("capital", self.capital)
                db_set("ws", self.win_streak)
                db_set("ls", self.loss_streak)

    def equity(self):
        opens = get_open()
        if not opens: return self.capital
        tickers = get_all_tickers()
        u = 0.0
        for t in opens:
            last = tickers.get(t["symbol"],{}).get("last", t["entry"])
            if t["side"]=="long":
                pp = (last - t["entry"]) / t["entry"]
            else:
                pp = (t["entry"] - last) / t["entry"]
            u += pp * t["size_usd"] * LEVERAGE - t["size_usd"] * COMMISSION * 2
        return self.capital + u

    def cycle(self):
        self.manage()
        tickers = get_all_tickers()
        if not tickers:
            self.last_stats = {"scanned":0,"cands":0,"opened":0}
            return
        cands = self.select_candidates(tickers, 12)
        self.last_stats["scanned"] = len(tickers)
        self.last_stats["cands"] = len(cands)
        opened = 0
        for sym, sc, tk in cands:
            try:
                df = get_klines(sym, "5", 60)
                feat = self.features(df, tk)
                dec = self.decide(feat)
                if dec and self.try_open(sym, tk, dec):
                    opened += 1
            except: continue
        self.last_stats["opened"] = opened
        self.awareness = min(0.97, self.awareness + 0.0007)
        db_set("awareness", self.awareness)
        eq = self.equity()
        self.peak = max(self.peak, eq)
        db_set("peak", self.peak)
        record_eq(eq, len(get_open()))

HIVE = Hive()

# ────────────────────────────────────────────────
# UI
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG], suppress_callback_exceptions=True)
app.title = "HIVE SCALPER-SNIPER 20x"
server = app.server

def card(title, val, color=GOLD, sub=""):
    return dbc.Card(dbc.CardBody([
        html.Div(title, style={"color":MUT,"fontSize":11}),
        html.Div(str(val), style={"color":color,"fontSize":20,"fontWeight":"bold"}),
        html.Div(sub, style={"color":MUT,"fontSize":10})
    ]), style={"background":CARD,"border":f"1px solid {LINE}","height":"100%"})

app.layout = html.Div([
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col(html.H3("HIVE SCALPER-SNIPER  ×20", style={"color":GOLD,"margin":0}), md=5),
        dbc.Col(html.Div(id="pulse", style={"color":NEON,"fontFamily":"monospace","fontSize":13}), md=4),
        dbc.Col(html.Div(id="status", style={"textAlign":"right","color":MUT,"fontSize":12}), md=3),
    ])), style={"margin":"8px 12px","background":CARD,"border":f"1px solid {LINE}"}),

    dcc.Tabs(id="tabs", value="stats", children=[
        dcc.Tab(label="وضعیت Hive", value="stats", style={"background":CARD,"color":TXT}, selected_style={"background":LINE,"color":GOLD}),
        dcc.Tab(label="معاملات زنده ×20", value="trade", style={"background":CARD,"color":TXT}, selected_style={"background":LINE,"color":GOLD}),
    ], style={"margin":"0 12px"}),
    html.Div(id="content", style={"padding":"12px"}),
    dcc.Interval(id="life", interval=12_000, n_intervals=0),
    dcc.Interval(id="cycle", interval=28_000, n_intervals=0),
], style={"background":BG,"minHeight":"100vh","color":TXT})

@app.callback(Output("content","children"), Input("tabs","value"), Input("life","n_intervals"))
def render(tab, n):
    if tab == "stats": return stats_tab()
    return trade_tab()

def stats_tab():
    h = HIVE
    bits, fib = h.heart.pulse()
    eq = h.equity()
    opens = get_open()
    closed = get_closed(80)
    wr = (sum(1 for t in closed if t["pnl"] and t["pnl"]>0)/len(closed)*100) if closed else 0
    return html.Div([
        dbc.Row([
            dbc.Col(card("Equity", f"${eq:.2f}", GOLD, f"Peak ${h.peak:.2f}"), md=2),
            dbc.Col(card("آگاهی", f"{h.awareness:.0%}", NEON), md=2),
            dbc.Col(card("نورون کل", f"{h.total_neurons():,}", ACCENT), md=2),
            dbc.Col(card("WinRate", f"{wr:.1f}%", UP if wr>=50 else DN, f"{len(closed)} trade"), md=2),
            dbc.Col(card("اسکن", f"{h.last_stats['scanned']}", GOLD, f"کاندید {h.last_stats['cands']}"), md=2),
            dbc.Col(card("لوریج", f"{LEVERAGE}×", DN, "اسکالپر/اسنایپر"), md=2),
        ], className="mb-3"),
        html.H5("ضربان + ارگانیسم‌ها", style={"color":GOLD}),
        html.Div(f"{bits}  Fib({fib})  #{h.heart.beat}", style={"fontFamily":"monospace","color":NEON,"marginBottom":10}),
        dbc.Row([
            dbc.Col(card(o.name, o.role, NEON if o.role=="SNIPER" else ORANGE if o.role=="SCALPER" else ACCENT,
                         f"{o.neurons:,} ن | وزن {o.weight}"), md=3) for o in h.orgs
        ], className="mb-3"),
        html.Div([
            html.Div("منطق: شتاب حجم لحظه‌ای + فشار قیمت + کیفیت اسپرد + RSI افراطی", style={"color":MUT}),
            html.Div("اجماع: حداقل ۲ ارگانیسم + حضور اجباری اسنایپر یا اسکالپر", style={"color":MUT}),
            html.Div(f"ریسک هر معامله ≈ {RISK_PER_TRADE*100:.1f}% سرمایه | TP {TP_PCT*100:.2f}% قیمت | SL {SL_PCT*100:.2f}% قیمت", style={"color":MUT}),
            html.Div("هشدار: لوریج ۲۰× خطر انحلال سریع دارد. این شبیه‌ساز است.", style={"color":DN,"fontWeight":"bold"}),
        ], style={"background":CARD,"padding":12,"borderRadius":8,"border":f"1px solid {LINE}"})
    ])

def trade_tab():
    h = HIVE
    opens = get_open()
    closed = get_closed(30)
    eq = h.equity()
    if opens:
        tickers = get_all_tickers()
        rows = []
        for t in opens:
            last = tickers.get(t["symbol"],{}).get("last", t["entry"])
            if t["side"]=="long":
                pp = (last - t["entry"]) / t["entry"]
            else:
                pp = (t["entry"] - last) / t["entry"]
            pnl = pp * t["size_usd"] * LEVERAGE - t["size_usd"] * COMMISSION * 2
            color = UP if pnl>=0 else DN
            rows.append(html.Tr([
                html.Td(t["id"]), html.Td(t["symbol"]),
                html.Td(t["side"].upper(), style={"color":UP if t["side"]=="long" else DN}),
                html.Td(f"{t['entry']:.5f}"), html.Td(f"{last:.5f}"),
                html.Td(f"${t['size_usd']:.1f}"), html.Td(f"{t['leverage']}×"),
                html.Td(f"{pnl:+.2f}", style={"color":color,"fontWeight":"bold"}),
                html.Td(f"{t['liq_price']:.5f}", style={"color":DN,"fontSize":11}),
            ]))
        table = dbc.Table([html.Thead(html.Tr([html.Th(x) for x in
            ["ID","نماد","سمت","ورود","فعلی","مارجین","لوریج","PnL","لیکوئید"]])),
            html.Tbody(rows)], bordered=True, hover=True, size="sm", style={"background":CARD})
    else:
        table = dbc.Alert("در حال اسکن و تشکیل اجماع برای اسکالپ...", color="secondary")

    eqh = get_eq_hist()
    if eqh.empty:
        eqh = pd.DataFrame({"ts":[datetime.now(timezone.utc).isoformat()],"equity":[INITIAL]})
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=pd.to_datetime(eqh["ts"]), y=eqh["equity"], mode="lines",
                             line=dict(color=GOLD,width=2), fill="tozeroy", fillcolor="rgba(240,185,11,0.1)"))
    fig.add_hline(y=INITIAL, line_dash="dot", line_color=MUT)
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD, height=280,
                      margin=dict(l=40,r=20,t=30,b=30), title=dict(text="Equity",font=dict(color=GOLD,size=13)),
                      xaxis=dict(gridcolor=LINE), yaxis=dict(gridcolor=LINE,tickprefix="$"))

    wr = (sum(1 for t in closed if t["pnl"] and t["pnl"]>0)/len(closed)*100) if closed else 0
    total = sum(t["pnl"] or 0 for t in closed)
    return html.Div([
        dbc.Row([
            dbc.Col(card("Equity", f"${eq:.2f}", GOLD), md=3),
            dbc.Col(card("WinRate", f"{wr:.1f}%", UP if wr>=50 else DN), md=3),
            dbc.Col(card("Realized", f"${total:+.2f}", UP if total>=0 else DN), md=3),
            dbc.Col(card("Open", f"{len(opens)}/{MAX_POS}", NEON), md=3),
        ], className="mb-3"),
        html.H5("پوزیشن‌های باز (لوریج ۲۰×)", style={"color":GOLD}),
        table,
        dcc.Graph(figure=fig, config={"displaylogo":False}),
        html.H5("آخرین بسته‌شده‌ها", style={"color":GOLD}),
        html.Div([html.Div(f"#{t['id']} {t['symbol']} {t['side']} {t['pnl']:+.2f}",
                           style={"color":UP if (t['pnl'] or 0)>0 else DN,"fontSize":12}) for t in closed[:8]]
                 if closed else html.Div("—", style={"color":MUT}))
    ])

@app.callback(Output("pulse","children"), Output("status","children"), Input("life","n_intervals"))
def header(n):
    bits, fib = HIVE.heart.pulse()
    return f"{bits} Fib({fib}) #{HIVE.heart.beat}", f"نورون {HIVE.total_neurons():,} | آگاهی {HIVE.awareness:.0%} | لوریج {LEVERAGE}×"

@app.callback(Output("tabs","value"), Input("cycle","n_intervals"), prevent_initial_call=False)
def run_cycle(n):
    HIVE.cycle()
    return dash.no_update

if __name__ == "__main__":
    print("HIVE SCALPER-SNIPER 20x starting...")
    print(f"Neurons: {HIVE.total_neurons():,} | Leverage: {LEVERAGE}x | Max positions: {MAX_POS}")
    print("WARNING: This is a simulation. 20x leverage can liquidate rapidly. No profit guarantee.")
    app.run(debug=True, host="0.0.0.0", port=8060, use_reloader=False)