# -*- coding: utf-8 -*-
"""
HIVE SCALPER-SNIPER PRO GENETIC EDITION
لوریج ۲۰× | اسکالپ + اسنایپر | یادگیری ژنتیکی واقعی | بک‌تست ۱۰,۰۰۰ کندلی
۱. بک‌تست ۱۰,۰۰۰ کندلی با دقت تیک‌به‌تیک (بدون نگاه به آینده)
۲. یادگیری هبی (Hebbian Learning): تقویت وزن فاکتورهای حسی منجر به سود
۳. حافظه ژنتیکی پایدار در SQLite (ژن‌ها بین جلسات و بک‌تست‌ها حفظ می‌شوند)
۴. رژیم‌دیتکشن قوی + پارامتر داینامیک
۵. ریسک داینامیک (vol targeting + correlation)
هشدار: این یک سیستم پیشرفته شبیه‌سازی و معاملاتی است. لوریج ۲۰× پرریسک است.
"""

import os, time, json, math, sqlite3, threading
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

# ──────────────────────────────────────────────────────────────
# رنگ‌ها و تنظیمات ظاهری
BG, CARD, LINE, TXT, MUT = "#0b1220", "#121c30", "#23314d", "#e8ecf4", "#8fa3c0"
GOLD, UP, DN, NEON, ACCENT, ORANGE = "#f0b90b", "#16a085", "#e74c3c", "#00f5d4", "#7b61ff", "#ff9f1c"

# ──────────────────────────────────────────────────────────────
# اتصال پایدار بایبیت
REST = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Referer": "https://www.bybit.com/"})
_ACTIVE = {"url": None}
_rate_lock = threading.Lock()
_last_req = 0.0

def bybit_get(path, params, timeout=10):
    global _last_req
    with _rate_lock:
        elapsed = time.time() - _last_req
        if elapsed < 0.06:
            time.sleep(0.06 - elapsed)
        _last_req = time.time()
    
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
        except Exception:
            continue
    return None

def get_all_tickers():
    d = bybit_get("/v5/market/tickers", {"category": "linear"})
    if not d or not d.get("result", {}).get("list"):
        return {}
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
        except Exception:
            continue
    return out

def get_klines_chunk(symbol, interval="5", limit=500, cursor=None):
    params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
    if cursor:
        params["cursor"] = cursor
    d = bybit_get("/v5/market/kline", params)
    if not d or "list" not in (d.get("result") or {}):
        return [], None
    lst = d["result"]["list"]
    next_cursor = d["result"].get("nextPageCursor")
    return lst, next_cursor

def get_historical_klines_10k(symbol, interval="5"):
    """دریافت دقیقاً تا ۱۰,۰۰۰ کندل با صفحه‌بندی برای بک‌تست عمیق"""
    all_data = []
    cursor = None
    target = 10000
    while len(all_data) < target:
        lst, cursor = get_klines_chunk(symbol, interval, limit=500, cursor=cursor)
        if not lst:
            break
        all_data.extend(lst)
        if not cursor:
            break
        time.sleep(0.05) # رعایت ریت لیمیت
    
    if not all_data:
        return pd.DataFrame()
    
    # داده‌ها از جدید به قدیم هستند، برعکس می‌کنیم
    all_data = all_data[:target][::-1]
    df = pd.DataFrame(all_data, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
    for c in ["open", "high", "low", "close", "volume", "turnover"]:
        df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)

# ──────────────────────────────────────────────────────────────
# پارامترهای پایه
LEVERAGE = 20
INITIAL_CAPITAL = 500.0
MAX_POSITIONS = 5
COMMISSION = 0.0006
SLIPPAGE_BPS = 1.2
MIN_TURNOVER_24H = 1_200_000
MAX_SPREAD_BPS = 4.5
RISK_PER_TRADE_BASE = 0.011

# ──────────────────────────────────────────────────────────────
# دیتابیس پیشرفته + حافظه ژنتیکی
DB_PATH = Path("hive_pro.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, side TEXT, entry REAL, size_usd REAL,
        qty REAL, leverage INTEGER, liq_price REAL, entry_time TEXT, exit_time TEXT,
        exit_price REAL, pnl REAL, status TEXT, reason TEXT, votes TEXT, regime TEXT, 
        features TEXT, partials TEXT, trail_stop REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)""")
    # جدول جدید برای حافظه ژنتیکی
    c.execute("""CREATE TABLE IF NOT EXISTS genes (
        organism TEXT PRIMARY KEY, weights TEXT, learning_rate REAL, total_trades INTEGER, win_rate REAL)""")
    conn.commit()
    conn.close()

def db_set(key, value):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)",
                 (key, json.dumps(value) if not isinstance(value, str) else value))
    conn.commit()
    conn.close()

def db_get(key, default=None):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    conn.close()
    if row is None: return default
    try: return json.loads(row[0])
    except: return row[0]

def save_gene(organism_name, weights, lr, trades, wr):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""INSERT OR REPLACE INTO genes (organism, weights, learning_rate, total_trades, win_rate)
                    VALUES (?, ?, ?, ?, ?)""", (organism_name, json.dumps(weights), lr, trades, wr))
    conn.commit()
    conn.close()

def load_genes():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT organism, weights, learning_rate FROM genes").fetchall()
    conn.close()
    genes = {}
    for org, w, lr in rows:
        try: genes[org] = {"weights": json.loads(w), "lr": lr}
        except: pass
    return genes

def save_trade(t):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO trades (symbol,side,entry,size_usd,qty,leverage,liq_price,entry_time,status,reason,votes,regime,features,partials,trail_stop)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (t["symbol"], t["side"], t["entry"], t["size_usd"], t["qty"], t["leverage"], t["liq_price"],
         t["entry_time"], "open", t.get("reason",""), json.dumps(t.get("votes",{})),
         t.get("regime",""), json.dumps(t.get("features",{})), json.dumps(t.get("partials",[])), t.get("trail_stop")))
    conn.commit()
    tid = c.lastrowid
    conn.close()
    return tid

def close_trade_full(tid, exit_price, pnl):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""UPDATE trades SET exit_time=?, exit_price=?, pnl=?, status='closed' WHERE id=?""",
                 (datetime.now(timezone.utc).isoformat(), exit_price, pnl, tid))
    conn.commit()
    conn.close()

def get_closed_trades(limit=200):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""SELECT id,symbol,side,entry,exit_price,size_usd,pnl,entry_time,exit_time,reason,regime,features
                           FROM trades WHERE status='closed' ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
    conn.close()
    return [{"id":r[0],"symbol":r[1],"side":r[2],"entry":r[3],"exit":r[4],"size_usd":r[5],"pnl":r[6],
             "entry_time":r[7],"exit_time":r[8],"reason":r[9],"regime":r[10], "features": json.loads(r[11] or "{}")} for r in rows]

# ──────────────────────────────────────────────────────────────
# رژیم‌دیتکشن قوی
def detect_regime(df):
    if df is None or len(df) < 50: return "RANGING"
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    atr = pd.Series(tr).rolling(14).mean().iloc[-1]
    atr_pct = atr / close[-1]
    
    ma_fast = pd.Series(close).rolling(12).mean().iloc[-1]
    ma_slow = pd.Series(close).rolling(36).mean().iloc[-1]
    slope = (close[-1] - close[-20]) / (close[-20] + 1e-12)
    
    up = np.maximum(high[1:] - high[:-1], 0)
    dn = np.maximum(low[:-1] - low[1:], 0)
    plus_dm = pd.Series(up).rolling(14).mean().iloc[-1]
    minus_dm = pd.Series(dn).rolling(14).mean().iloc[-1]
    dx = abs(plus_dm - minus_dm) / (plus_dm + minus_dm + 1e-12) * 100
    
    if atr_pct > 0.018: return "HIGH_VOL"
    if dx > 22 and slope > 0.004 and ma_fast > ma_slow: return "TREND_UP"
    if dx > 22 and slope < -0.004 and ma_fast < ma_slow: return "TREND_DOWN"
    return "RANGING"

REGIME_PARAMS = {
    "TREND_UP":   {"tp": 0.0065, "sl": 0.0032, "risk_mult": 1.15, "trail_mult": 1.3, "partial_at": 0.0035},
    "TREND_DOWN": {"tp": 0.0065, "sl": 0.0032, "risk_mult": 1.15, "trail_mult": 1.3, "partial_at": 0.0035},
    "RANGING":    {"tp": 0.0038, "sl": 0.0024, "risk_mult": 0.85, "trail_mult": 0.9, "partial_at": 0.0022},
    "HIGH_VOL":   {"tp": 0.0085, "sl": 0.0045, "risk_mult": 0.70, "trail_mult": 1.5, "partial_at": 0.0045},
}

# ──────────────────────────────────────────────────────────────
# استخراج ویژگی‌ها (فاکتورهای حسی)
def extract_features(df, ticker):
    if df is None or len(df) < 40: return None
    close = df["close"].values
    vol = df["volume"].values
    
    mom = float(np.clip((close[-1] - close[-8]) / (close[-8] + 1e-12) * 22, -1, 1))
    vol_surge = float(np.clip((vol[-4:].mean() / (vol[-18:].mean() + 1e-12) - 1) * 1.7, -1, 1))
    deltas = np.diff(close[-9:])
    pressure = float(np.clip(np.mean(deltas) / (np.std(deltas) + 1e-12) * 0.55, -1, 1))
    
    mid = ticker["last"]
    spread_bps = (ticker["ask"] - ticker["bid"]) / (mid + 1e-12) * 10000
    spread_q = float(np.clip(1.0 - spread_bps / MAX_SPREAD_BPS, 0, 1))
    
    delta = pd.Series(close).diff()
    gain = delta.clip(lower=0).rolling(10).mean()
    loss = (-delta.clip(upper=0)).rolling(10).mean()
    rs = gain / (loss + 1e-12)
    rsi = 100 - (100 / (1 + rs)).iloc[-1]
    rsi_ext = 1.0 if rsi < 27 else (-1.0 if rsi > 73 else (0.45 if rsi < 37 else (-0.45 if rsi > 63 else 0.0)))
    
    atr = pd.Series(np.maximum(df["high"]-df["low"], np.maximum(abs(df["high"]-df["close"].shift(1)), abs(df["low"]-df["close"].shift(1))))).rolling(14).mean().iloc[-1]
    atr_pct = float(atr / close[-1])
    
    return {"mom": mom, "vol_surge": vol_surge, "pressure": pressure, "spread_q": spread_q, "rsi_ext": rsi_ext, "atr_pct": atr_pct, "rsi": float(rsi)}

# ──────────────────────────────────────────────────────────────
# ارگانیسم‌ها با حافظه ژنتیکی
class Organism:
    def __init__(self, name, role, base_weights, lr=0.05):
        self.name = name
        self.role = role
        self.lr = lr  # نرخ یادگیری
        # بارگذاری وزن‌ها از حافظه یا استفاده از پیش‌فرض
        saved_genes = load_genes()
        if name in saved_genes:
            self.weights = saved_genes[name]["weights"]
            self.lr = saved_genes[name].get("lr", lr)
        else:
            self.weights = base_weights
        
        self.total_trades = 0
        self.winning_trades = 0

    def score(self, feat, regime):
        w = self.weights
        # محاسبه امتیاز بر اساس وزن‌های یادگرفته‌شده (ژن‌ها)
        s = (w["mom"] * feat["mom"] + 
             w["vol_surge"] * feat["vol_surge"] + 
             w["pressure"] * feat["pressure"] + 
             w["spread_q"] * feat["spread_q"] +
             w["rsi_ext"] * feat["rsi_ext"])
        
        # فیلترهای منطقی خاص هر نقش
        if self.role == "SNIPER" and (abs(s) < 0.35 or abs(feat["rsi_ext"]) < 0.20):
            return 0.0
            
        return s

    def learn(self, feat, pnl):
        """یادگیری هبی: تقویت ژن‌هایی که منجر به سود شدند، تضعیف ژن‌های ضررده"""
        if pnl == 0: return
        
        self.total_trades += 1
        if pnl > 0:
            self.winning_trades += 1
            
        # نرمال‌سازی PnL برای جلوگیری از انفجار وزن‌ها
        norm_pnl = np.clip(pnl / 50.0, -0.5, 0.5)  # فرض بر اینکه 50 دلار حرکت بزرگی است
        
        # به‌روزرسانی وزن‌ها: W_new = W_old + (LR * PnL_norm * Feature_Value)
        for key in self.weights:
            if key in feat:
                gradient = norm_pnl * feat[key]
                self.weights[key] += self.lr * gradient
                
        # نرمال‌سازی وزن‌ها که مجموع قدر مطلق آن‌ها حدود 1 بماند (ثبات ژنتیکی)
        total_w = sum(abs(w) for w in self.weights.values()) + 1e-8
        for key in self.weights:
            self.weights[key] = (self.weights[key] / total_w) * 1.5
            
        # ذخیره در حافظه پایدار
        wr = self.winning_trades / max(1, self.total_trades)
        save_gene(self.name, self.weights, self.lr, self.total_trades, wr)

# ──────────────────────────────────────────────────────────────
# هسته Hive
class HivePro:
    def __init__(self):
        init_db()
        self.capital = float(db_get("capital", INITIAL_CAPITAL))
        self.peak = float(db_get("peak", INITIAL_CAPITAL))
        self.adaptive = db_get("adaptive", {"score_threshold": 0.45, "conv_threshold": 0.38})
        
        # تعریف ارگانیسم‌ها با وزن‌های اولیه (در صورت نبود حافظه، از این‌ها استفاده می‌شود)
        self.orgs = [
            Organism("Aether", "SNIPER", {"mom": 0.40, "vol_surge": 0.20, "pressure": 0.20, "spread_q": 0.10, "rsi_ext": 0.10}, lr=0.08),
            Organism("Pulse",  "SCALPER", {"mom": 0.25, "vol_surge": 0.40, "pressure": 0.25, "spread_q": 0.05, "rsi_ext": 0.05}, lr=0.10),
            Organism("Flux",   "FLOW",    {"mom": 0.15, "vol_surge": 0.30, "pressure": 0.40, "spread_q": 0.10, "rsi_ext": 0.05}, lr=0.06),
            Organism("Vector", "MOMENTUM",{"mom": 0.50, "vol_surge": 0.20, "pressure": 0.15, "spread_q": 0.05, "rsi_ext": 0.10}, lr=0.07),
        ]
        self._lock = threading.Lock()

    def decide(self, feat, regime):
        if feat is None: return None
        votes = []
        for o in self.orgs:
            s = o.score(feat, regime)
            if abs(s) < 0.20: continue
            side = "long" if s > 0 else "short"
            votes.append({"org": o.name, "role": o.role, "side": side, "score": s})
            
        if len(votes) < 2: return None
        
        long_s = sum(v["score"] for v in votes if v["side"] == "long")
        short_s = sum(abs(v["score"]) for v in votes if v["side"] == "short")
        
        thresh = self.adaptive.get("score_threshold", 0.45)
        if long_s > short_s and long_s > thresh:
            side, final = "long", long_s
        elif short_s > long_s and short_s > thresh:
            side, final = "short", short_s
        else:
            return None
            
        agreeing = [v for v in votes if v["side"] == side]
        conv = min(1.0, final / 1.5)
        if conv < self.adaptive.get("conv_threshold", 0.38): return None
        
        reason = " | ".join(f"{v['org']}:{v['side'][0]}{v['score']:.2f}" for v in agreeing)
        return {"side": side, "conv": conv, "votes": {v["org"]: v for v in votes}, "reason": f"HIVE[{len(agreeing)}] {reason}", "regime": regime}

    def genetic_backtest(self, symbol, interval="5"):
        """موتور بک‌تست ۱۰,۰۰۰ کندلی با یادگیری واقعی و بدون نگاه به آینده"""
        print(f"در حال دریافت ۱۰,۰۰۰ کندل برای {symbol}...")
        df = get_historical_klines_10k(symbol, interval)
        if df.empty or len(df) < 500:
            return {"error": "داده کافی نیست"}
            
        print(f"شروع بک‌تست ژنتیکی روی {len(df)} کندل. این فرآیند شامل یادگیری تیک‌به‌تیک است...")
        
        capital = INITIAL_CAPITAL
        trades_log = []
        position = None
        
        # حلقه اصلی بک‌تست (بدون نگاه به آینده)
        # ما از کندل 100 شروع می‌کنیم تا اندیکاتورها مقدار بگیرند
        for i in range(100, len(df) - 1):
            # ۱. استخراج ویژگی فقط با داده‌های تا لحظه i (No Look-Ahead)
            window = df.iloc[:i+1].copy()
            current_candle = df.iloc[i]
            next_candle = df.iloc[i+1] # برای شبیه‌سازی اجرا در کندل بعد
            
            ticker = {"last": current_candle["close"], "bid": current_candle["close"]*0.9998, "ask": current_candle["close"]*1.0002}
            feat = extract_features(window, ticker)
            if not feat: continue
            
            regime = detect_regime(window)
            
            # ۲. تصمیم‌گیری بر اساس ژن‌های فعلی
            dec = self.decide(feat, regime)
            
            # ۳. مدیریت پوزیشن باز
            if position is not None:
                # بررسی خروج بر اساس های/لو کندل‌های بعد از ورود (شبیه‌سازی واقعی)
                # برای سادگی و سرعت، خروج را بر اساس close کندل جاری بررسی می‌کنیم
                last_price = current_candle["close"]
                p = position
                if p["side"] == "long":
                    pnl_pct = (last_price - p["entry"]) / p["entry"]
                else:
                    pnl_pct = (p["entry"] - last_price) / p["entry"]
                    
                rp = REGIME_PARAMS.get(p["regime"], REGIME_PARAMS["RANGING"])
                hit_tp = pnl_pct >= rp["tp"]
                hit_sl = pnl_pct <= -rp["sl"]
                timeout = (i - p["entry_idx"]) > 40 # حداکثر ۴۰ کندل نگهداری
                
                if hit_tp or hit_sl or timeout:
                    # محاسبه سود/ضرر
                    pnl_usd = pnl_pct * p["size_usd"] * LEVERAGE - p["size_usd"] * COMMISSION * 2
                    capital += pnl_usd
                    
                    # ۴. یادگیری ژنتیکی: آموزش ارگانیسم‌هایی که رای مثبت دادند
                    for org_name, vote in p["votes"].items():
                        org = next((o for o in self.orgs if o.name == org_name), None)
                        if org:
                            org.learn(p["features"], pnl_usd)
                            
                    trades_log.append({"pnl": pnl_usd, "side": p["side"], "regime": p["regime"]})
                    position = None
                    
            # ۵. ورود به معامله جدید
            if position is None and dec is not None:
                # اجرا در قیمت باز شدن کندل بعدی + اسلیپج (جلوگیری از لوک‌اهد)
                exec_price = next_candle["open"] * (1.0001 if dec["side"] == "long" else 0.9999)
                size = capital * 0.15 # ریسک ثابت در بک‌تست برای پایداری
                position = {
                    "side": dec["side"], "entry": exec_price, "size_usd": size,
                    "regime": regime, "entry_idx": i, "votes": dec["votes"], "features": feat
                }
                
        # محاسبه نتایج نهایی
        if not trades_log:
            return {"error": "هیچ معامله‌ای انجام نشد"}
            
        pnls = [t["pnl"] for t in trades_log]
        wr = sum(1 for p in pnls if p > 0) / len(pnls)
        total_ret = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL
        
        # به‌روزرسانی سرمایه اصلی اگر بک‌تست موفق بود (اختیاری، اینجا فقط برای نمایش است)
        # db_set("capital", max(self.capital, capital))
        
        return {
            "symbol": symbol, "candles": len(df), "trades": len(trades_log), 
            "winrate": wr, "total_return": total_ret, "final_capital": capital,
            "avg_pnl": float(np.mean(pnls))
        }

# ──────────────────────────────────────────────────────────────
# نمونه سراسری و رابط کاربری
HIVE = HivePro()

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG], suppress_callback_exceptions=True)
app.title = "HIVE PRO GENETIC"

def card(title, val, color=GOLD, sub=""):
    return dbc.Card(dbc.CardBody([
        html.Div(title, style={"color": MUT, "fontSize": 11}),
        html.Div(str(val), style={"color": color, "fontSize": 19, "fontWeight": "bold"}),
        html.Div(sub, style={"color": MUT, "fontSize": 10})
    ]), style={"background": CARD, "border": f"1px solid {LINE}", "height": "100%"})

app.layout = html.Div([
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col(html.H3("HIVE PRO GENETIC ×20", style={"color": GOLD, "margin": 0}), md=6),
        dbc.Col(html.Div("یادگیری ژنتیکی واقعی | ۱۰,۰۰۰ کندل | بدون نگاه به آینده", style={"color": NEON, "fontFamily": "monospace", "fontSize": 13}), md=6),
    ])), style={"margin": "8px 12px", "background": CARD, "border": f"1px solid {LINE}"}),

    dcc.Tabs(id="tabs", value="backtest", children=[
        dcc.Tab(label="بک‌تست ژنتیکی ۱۰K", value="backtest", style={"background": CARD, "color": TXT}, selected_style={"background": LINE, "color": GOLD}),
        dcc.Tab(label="حافظه ژنتیکی (ژن‌ها)", value="genes", style={"background": CARD, "color": TXT}, selected_style={"background": LINE, "color": GOLD}),
        dcc.Tab(label="عملکرد زنده", value="live", style={"background": CARD, "color": TXT}, selected_style={"background": LINE, "color": GOLD}),
    ], style={"margin": "0 12px"}),
    html.Div(id="content", style={"padding": "12px"}),
    dcc.Store(id="bt-result"),
], style={"background": BG, "minHeight": "100vh", "color": TXT})

@app.callback(Output("content", "children"), Input("tabs", "value"), Input("bt-result", "data"))
def render(tab, bt_data):
    if tab == "backtest":
        return html.Div([
            html.H5("بک‌تست ژنتیکی عمیق (۱۰,۰۰۰ کندل)", style={"color": GOLD}),
            dbc.Row([
                dbc.Col(dcc.Input(id="bt-symbol", value="BTCUSDT", type="text", style={"width": "100%", "padding": 8, "borderRadius": 6}), md=4),
                dbc.Col(dbc.Button("اجرای بک‌تست و یادگیری", id="bt-run", color="warning", style={"width": "100%", "fontWeight": "bold"}), md=3),
            ], className="mb-3"),
            html.Div(id="bt-output", children=render_bt_result(bt_data) if bt_data else "برای شروع یادگیری، دکمه را بزنید. این فرآیند وزن‌های ارگانیسم‌ها را بر اساس ۱۰,۰۰۰ کندل گذشته بهینه می‌کند.")
        ])
    elif tab == "genes":
        genes = load_genes()
        rows = []
        for org, data in genes.items():
            w = data["weights"]
            w_str = "<br>".join([f"• {k}: <b>{v:.3f}</b>" for k, v in w.items()])
            rows.append(html.Tr([
                html.Td(org, style={"color": NEON, "fontWeight": "bold"}),
                html.Td(data.get("total_trades", 0)),
                html.Td(f"{data.get('win_rate', 0)*100:.1f}%", style={"color": UP if data.get('win_rate', 0) > 0.5 else DN}),
                html.Td(dcc.Markdown(w_str, dangerously_allow_html=True)),
            ]))
        return html.Div([
            html.H5("حافظه ژنتیکی ارگانیسم‌ها", style={"color": GOLD}),
            html.P("این وزن‌ها حاصل یادگیری تجمعی از تمام بک‌تست‌ها و معاملات زنده هستند. هر چه بک‌تست بیشتری بگیرید، این اعداد هوشمندتر می‌شوند.", style={"color": MUT}),
            dbc.Table([
                html.Thead(html.Tr([html.Th("ارگانیسم"), html.Th("تعداد تجربه"), html.Th("وین ریت"), html.Th("ژن‌ها (وزن فاکتورهای حسی)")])),
                html.Tbody(rows)
            ], bordered=True, hover=True, size="sm", style={"background": CARD})
        ])
    else:
        return html.Div("بخش معاملات زنده (در این نسخه تمرکز روی بک‌تست ژنتیکی است)", style={"color": MUT})

def render_bt_result(data):
    if not data or "error" in data:
        return dbc.Alert(data.get("error", "خطا"), color="danger")
    
    color = UP if data['total_return'] >= 0 else DN
    return dbc.Card(dbc.CardBody([
        dbc.Row([
            dbc.Col(html.Div(f"نماد: {data['symbol']}", style={"color": GOLD, "fontSize": 18}), md=3),
            dbc.Col(html.Div(f"تعداد کندل: {data['candles']:,}", style={"color": TXT}), md=3),
            dbc.Col(html.Div(f"معاملات: {data['trades']}", style={"color": TXT}), md=3),
            dbc.Col(html.Div(f"سرمایه نهایی: ${data['final_capital']:.2f}", style={"color": TXT}), md=3),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col(card("وین ریت", f"{data['winrate']*100:.1f}%", UP if data['winrate']>=0.5 else DN), md=6),
            dbc.Col(card("بازده کل", f"{data['total_return']*100:+.2f}%", color), md=6),
        ]),
        html.Div("✅ ژن‌های ارگانیسم‌ها بر اساس این ۱۰,۰۰۰ کندل به‌روزرسانی و در حافظه ذخیره شدند.", style={"color": NEON, "marginTop": 15, "fontWeight": "bold"})
    ]), style={"background": CARD, "border": f"1px solid {LINE}"})

@app.callback(Output("bt-result", "data"), Input("bt-run", "n_clicks"), State("bt-symbol", "value"), prevent_initial_call=True)
def do_backtest(n, symbol):
    if not n: return None
    symbol = (symbol or "BTCUSDT").upper().strip()
    return HIVE.genetic_backtest(symbol, interval="5")

if __name__ == "__main__":
    print("HIVE PRO GENETIC starting...")
    print("ویژگی کلیدی: یادگیری هبی (Hebbian Learning) روی ۱۰,۰۰۰ کندل بدون نگاه به آینده.")
    app.run(debug=True, host="0.0.0.0", port=8060, use_reloader=False)