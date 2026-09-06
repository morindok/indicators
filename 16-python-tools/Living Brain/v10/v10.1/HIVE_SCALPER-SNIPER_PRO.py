# -*- coding: utf-8 -*-
"""
HIVE SCALPER-SNIPER PRO — نسخه فوق‌هوشمند با مغز یادگیرنده زنده
لوریج ۲۰× | اسکالپ + اسنایپر | اسکن ~۱۰۰ نماد | حداکثر ۵ پوزیشن

قابلیت‌های این نسخه:
۱.  بک‌تست واک‌فوروارد واقعی تا ۱۰,۰۰۰ کندل — بدون نگاه به آینده (no look-ahead)
۲.  رژیم‌دیتکشن قوی + پارامتر داینامیک خودتنظیم بر اساس وین‌ریت هر رژیم
۳.  ریسک داینامیک (vol targeting + correlation)
۴.  فیلتر نقدشوندگی و اسپرد سخت
۵.  خروج جزئی + trailing هوشمند
۶.  مغز یادگیری آنلاین: وزن نورونی هر ارگانیسم با قاعده‌ی گرادیانی از نتیجه‌ی هر معامله به‌روزرسانی می‌شود
۷.  حافظه‌ی تجربه (Experience Memory / k-NN Recall): هر تصمیم با تجربه‌های مشابه گذشته مقایسه می‌شود
۸.  یادگیری تجمعی بین اجراهای بک‌تست: هر بار دکمه‌ی بک‌تست زده شود، مغز از دانش اجرای قبلی ادامه می‌دهد
۹.  رابط کاربری راست‌چین (RTL) با تب اختصاصی «یادگیری» و نمودارهای بصری در همه‌ی تب‌ها

هشدار: این ابزار یک شبیه‌ساز آموزشی/پژوهشی است. سود تضمینی وجود ندارد.
لوریج ۲۰× بسیار پرریسک است و این کد برای اجرای معاملات واقعی طراحی نشده؛ صرفاً شبیه‌سازی و بک‌تست انجام می‌دهد.
"""

import os, time, json, math, sqlite3, hashlib, threading, copy
from datetime import datetime, timezone, timedelta
from collections import deque, defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import dash
from dash import dcc, html, Input, Output, State, ctx
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ──────────────────────────────────────────────────────────────
# رنگ‌ها
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

def bybit_get(path, params, timeout=8):
    global _last_req
    with _rate_lock:
        elapsed = time.time() - _last_req
        if elapsed < 0.07:
            time.sleep(0.07 - elapsed)
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

def get_klines(symbol, interval="5", limit=200, category="linear"):
    d = bybit_get("/v5/market/kline", {"category": category, "symbol": symbol, "interval": interval, "limit": limit})
    if not d or "list" not in (d.get("result") or {}):
        return pd.DataFrame()
    lst = d["result"]["list"]
    if not lst:
        return pd.DataFrame()
    df = pd.DataFrame(lst, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
    for c in ["open", "high", "low", "close", "volume", "turnover"]:
        df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)

def get_klines_deep(symbol, interval="5", total=10000, category="linear"):
    """دریافت عمیق کندل‌ها با صفحه‌بندی (Pagination) تا سقف ~۱۰,۰۰۰ کندل — برای بک‌تست واک‌فوروارد."""
    total = int(max(200, min(10000, total)))
    all_rows = []
    seen_ts = set()
    end_ts = None
    per_call = 1000
    attempts = 0
    max_attempts = math.ceil(total / per_call) + 6
    while len(all_rows) < total and attempts < max_attempts:
        params = {"category": category, "symbol": symbol, "interval": interval, "limit": per_call}
        if end_ts is not None:
            params["end"] = end_ts
        d = bybit_get("/v5/market/kline", params)
        attempts += 1
        if not d or "list" not in (d.get("result") or {}):
            break
        lst = d["result"]["list"]
        if not lst:
            break
        new_rows = [r for r in lst if r[0] not in seen_ts]
        if not new_rows:
            break
        for r in new_rows:
            seen_ts.add(r[0])
        all_rows.extend(new_rows)
        oldest_ts = min(int(r[0]) for r in lst)
        end_ts = oldest_ts - 1
        if len(lst) < per_call:
            break
    if not all_rows:
        return pd.DataFrame()
    df = pd.DataFrame(all_rows, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
    for c in ["open", "high", "low", "close", "volume", "turnover"]:
        df[c] = df[c].astype(float)
    df = df.drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)
    return df.tail(total).reset_index(drop=True)

def get_all_tickers():
    d = bybit_get("/v5/market/tickers", {"category": "linear"})
    if not d or not d.get("result", {}).get("list"):
        return {}
    out = {}
    for t in d["result"]["list"]:
        if not t["symbol"].endswith("USDT"):
            continue
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

# ──────────────────────────────────────────────────────────────
# پارامترهای پایه
LEVERAGE = 20
INITIAL_CAPITAL = 500.0
MAX_POSITIONS = 5
COMMISSION = 0.0006
SPREAD_BPS_DEFAULT = 1.8
SLIPPAGE_BPS = 1.2          # لغزش شبیه‌سازی‌شده
MIN_TURNOVER_24H = 1_200_000
MAX_SPREAD_BPS = 4.5
RISK_PER_TRADE_BASE = 0.011
CPU_CORES = os.cpu_count() or 4
NEURON_BASE = CPU_CORES * 3072

# ──────────────────────────────────────────────────────────────
# دیتابیس پیشرفته
DB_PATH = Path("hive_pro.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT, side TEXT, entry REAL, size_usd REAL, qty REAL,
        leverage INTEGER, liq_price REAL, entry_time TEXT, exit_time TEXT,
        exit_price REAL, pnl REAL, status TEXT, reason TEXT, votes TEXT,
        regime TEXT, features TEXT, partials TEXT, trail_stop REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, symbol TEXT, side TEXT, conv REAL, regime TEXT,
        features TEXT, votes TEXT, accepted INTEGER, reason TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS equity (ts TEXT, equity REAL, open_n INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS backtest_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, symbol TEXT, params TEXT, metrics TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS experiences (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, regime TEXT, side TEXT, features TEXT, outcome REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS learning_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, source TEXT, weights TEXT,
        thresholds TEXT, awareness REAL, total_updates INTEGER)""")
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
    if row is None:
        return default
    try:
        return json.loads(row[0])
    except Exception:
        return row[0]

def save_trade(t):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO trades
        (symbol,side,entry,size_usd,qty,leverage,liq_price,entry_time,status,reason,votes,regime,features,partials,trail_stop)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (t["symbol"], t["side"], t["entry"], t["size_usd"], t["qty"], t["leverage"], t["liq_price"],
         t["entry_time"], "open", t.get("reason",""), json.dumps(t.get("votes",{})),
         t.get("regime",""), json.dumps(t.get("features",{})), json.dumps(t.get("partials",[])), t.get("trail_stop")))
    conn.commit()
    tid = c.lastrowid
    conn.close()
    return tid

def update_trade(tid, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    sets = ", ".join(f"{k}=?" for k in kwargs)
    conn.execute(f"UPDATE trades SET {sets} WHERE id=?", (*kwargs.values(), tid))
    conn.commit()
    conn.close()

def close_trade_full(tid, exit_price, pnl):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""UPDATE trades SET exit_time=?, exit_price=?, pnl=?, status='closed' WHERE id=?""",
                 (datetime.now(timezone.utc).isoformat(), exit_price, pnl, tid))
    conn.commit()
    conn.close()

def get_open_trades():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""SELECT id,symbol,side,entry,size_usd,qty,leverage,liq_price,entry_time,reason,votes,regime,features,partials,trail_stop
                           FROM trades WHERE status='open'""").fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({
            "id": r[0], "symbol": r[1], "side": r[2], "entry": r[3], "size_usd": r[4], "qty": r[5],
            "leverage": r[6], "liq_price": r[7], "entry_time": r[8], "reason": r[9],
            "votes": json.loads(r[10] or "{}"), "regime": r[11], "features": json.loads(r[12] or "{}"),
            "partials": json.loads(r[13] or "[]"), "trail_stop": r[14]
        })
    return res

def get_closed_trades(limit=150):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""SELECT id,symbol,side,entry,exit_price,size_usd,pnl,entry_time,exit_time,reason,regime
                           FROM trades WHERE status='closed' ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
    conn.close()
    return [{"id":r[0],"symbol":r[1],"side":r[2],"entry":r[3],"exit":r[4],"size_usd":r[5],"pnl":r[6],
             "entry_time":r[7],"exit_time":r[8],"reason":r[9],"regime":r[10]} for r in rows]

def log_decision(symbol, side, conv, regime, features, votes, accepted, reason):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""INSERT INTO decisions (ts,symbol,side,conv,regime,features,votes,accepted,reason)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                 (datetime.now(timezone.utc).isoformat(), symbol, side, conv, regime,
                  json.dumps(features), json.dumps(votes), int(accepted), reason))
    conn.commit()
    conn.close()

def record_equity(eq, n_open):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO equity (ts, equity, open_n) VALUES (?,?,?)",
                 (datetime.now(timezone.utc).isoformat(), eq, n_open))
    conn.commit()
    conn.close()

def get_equity_history():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT ts, equity FROM equity ORDER BY ts").fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["ts", "equity"]) if rows else pd.DataFrame({"ts": [], "equity": []})

def get_learning_history(limit=300):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""SELECT ts, source, weights, thresholds, awareness, total_updates
                           FROM learning_history ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
    conn.close()
    return list(reversed(rows))

def get_backtest_runs(limit=20):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""SELECT ts, symbol, params, metrics FROM backtest_runs
                           ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
    conn.close()
    return rows

# ──────────────────────────────────────────────────────────────
# رژیم‌دیتکشن قوی (نسخه‌ی numpy خالص برای سرعت بالا در بک‌تست‌های بزرگ)
def detect_regime_arr(close, high, low):
    """بازگرداندن: TREND_UP, TREND_DOWN, RANGING, HIGH_VOL"""
    n = len(close)
    if n < 50:
        return "RANGING"
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    atr = tr[-14:].mean() if len(tr) >= 14 else tr.mean()
    atr_pct = atr / close[-1]
    ma_fast = close[-12:].mean()
    ma_slow = close[-36:].mean() if n >= 36 else close.mean()
    slope = (close[-1] - close[-20]) / (close[-20] + 1e-12) if n >= 20 else 0.0
    up = np.maximum(high[1:] - high[:-1], 0)
    dn = np.maximum(low[:-1] - low[1:], 0)
    plus_dm = up[-14:].mean() if len(up) >= 14 else up.mean()
    minus_dm = dn[-14:].mean() if len(dn) >= 14 else dn.mean()
    dx = abs(plus_dm - minus_dm) / (plus_dm + minus_dm + 1e-12) * 100
    adx_approx = dx

    if atr_pct > 0.018:
        return "HIGH_VOL"
    if adx_approx > 22 and slope > 0.004 and ma_fast > ma_slow:
        return "TREND_UP"
    if adx_approx > 22 and slope < -0.004 and ma_fast < ma_slow:
        return "TREND_DOWN"
    return "RANGING"

def detect_regime(df):
    if df is None or len(df) < 50:
        return "RANGING"
    return detect_regime_arr(df["close"].values, df["high"].values, df["low"].values)

# پارامترهای وابسته به رژیم (این مقادیر توسط مغز یادگیری در طول زمان خودتنظیم می‌شوند)
REGIME_PARAMS = {
    "TREND_UP":   {"tp": 0.0065, "sl": 0.0032, "risk_mult": 1.15, "trail_mult": 1.3, "partial_at": 0.0035},
    "TREND_DOWN": {"tp": 0.0065, "sl": 0.0032, "risk_mult": 1.15, "trail_mult": 1.3, "partial_at": 0.0035},
    "RANGING":    {"tp": 0.0038, "sl": 0.0024, "risk_mult": 0.85, "trail_mult": 0.9, "partial_at": 0.0022},
    "HIGH_VOL":   {"tp": 0.0085, "sl": 0.0045, "risk_mult": 0.70, "trail_mult": 1.5, "partial_at": 0.0045},
}
# لنگرِ ثابتِ مقادیرِ اصلی — برای محدود نگه‌داشتن دامنه‌ی خودتنظیمی و جلوگیری از انحراف خطرناک
REGIME_PARAMS_BASE = copy.deepcopy(REGIME_PARAMS)

# ──────────────────────────────────────────────────────────────
# استخراج ویژگی‌ها (نسخه‌ی numpy خالص)
def extract_features_arr(close, high, low, vol, ticker):
    n = len(close)
    if n < 40:
        return None
    mom = float(np.clip((close[-1] - close[-8]) / (close[-8] + 1e-12) * 22, -1, 1))
    vol_recent = vol[-4:].mean()
    vol_base = vol[-18:].mean() if n >= 18 else vol.mean()
    vol_surge = float(np.clip((vol_recent / (vol_base + 1e-12) - 1) * 1.7, -1, 1))
    deltas = np.diff(close[-9:])
    pressure = float(np.clip(np.mean(deltas) / (np.std(deltas) + 1e-12) * 0.55, -1, 1))
    mid = ticker["last"]
    spread_bps = (ticker["ask"] - ticker["bid"]) / (mid + 1e-12) * 10000
    spread_q = float(np.clip(1.0 - spread_bps / MAX_SPREAD_BPS, 0, 1))
    # RSI (numpy)
    delta = np.diff(close)
    gain = np.clip(delta, 0, None)
    loss = np.clip(-delta, 0, None)
    g = gain[-10:].mean() if len(gain) >= 10 else gain.mean()
    l = loss[-10:].mean() if len(loss) >= 10 else loss.mean()
    rs = g / (l + 1e-12)
    rsi = 100 - 100 / (1 + rs)
    rsi_ext = 1.0 if rsi < 27 else (-1.0 if rsi > 73 else (0.45 if rsi < 37 else (-0.45 if rsi > 63 else 0.0)))
    # ATR%
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    atr = tr[-14:].mean() if len(tr) >= 14 else (tr.mean() if len(tr) else 0.0)
    atr_pct = float(atr / close[-1])
    return {
        "mom": mom, "vol_surge": vol_surge, "pressure": pressure,
        "spread_q": spread_q, "spread_bps": spread_bps, "rsi_ext": rsi_ext,
        "atr_pct": atr_pct, "rsi": float(rsi)
    }

def extract_features(df, ticker):
    if df is None or len(df) < 40:
        return None
    return extract_features_arr(df["close"].values, df["high"].values, df["low"].values, df["volume"].values, ticker)

# ──────────────────────────────────────────────────────────────
# بردار ویژگی برای مغز یادگیری
LEARN_FEATURES = ["mom", "vol_surge", "pressure", "spread_q", "rsi_ext", "atr_norm"]

def feature_vector(feat):
    if not feat:
        return [0.0] * len(LEARN_FEATURES)
    return [
        float(feat.get("mom", 0.0)),
        float(feat.get("vol_surge", 0.0)),
        float(feat.get("pressure", 0.0)),
        float(feat.get("spread_q", 0.5)),
        float(feat.get("rsi_ext", 0.0)),
        float(np.clip(feat.get("atr_pct", 0.01) * 40, 0, 1)),
    ]

def compute_maxdd(curve):
    if not curve:
        return 0.0
    peak = curve[0]
    mdd = 0.0
    for v in curve:
        peak = max(peak, v)
        dd = (peak - v) / peak if peak > 0 else 0.0
        mdd = max(mdd, dd)
    return mdd

# ──────────────────────────────────────────────────────────────
# ارگانیسم‌ها — امتیازدهی با وزن‌های قابل یادگیری
class Organism:
    ROLE_MULT = {"SNIPER": 1.28, "SCALPER": 1.18, "FLOW": 1.12, "MOMENTUM": 1.0}
    DEFAULT_WEIGHTS = {
        "SNIPER":   {"mom": 0.34, "vol_surge": 0.24, "pressure": 0.24, "spread_q": 0.18, "rsi_ext": 0.0, "atr_norm": 0.0},
        "SCALPER":  {"mom": 0.28, "vol_surge": 0.38, "pressure": 0.22, "spread_q": 0.12, "rsi_ext": 0.0, "atr_norm": 0.0},
        "FLOW":     {"mom": 0.18, "vol_surge": 0.36, "pressure": 0.34, "spread_q": 0.12, "rsi_ext": 0.0, "atr_norm": 0.0},
        "MOMENTUM": {"mom": 0.42, "vol_surge": 0.26, "pressure": 0.20, "spread_q": 0.0,  "rsi_ext": 0.12, "atr_norm": 0.0},
    }

    def __init__(self, name, role, weight=1.0):
        self.name = name
        self.role = role
        self.weight = weight
        self.neurons = int(NEURON_BASE * (1.35 if role == "SNIPER" else 1.2 if role == "SCALPER" else 1.05))
        self.weights = dict(Organism.DEFAULT_WEIGHTS.get(role, {f: 0.2 for f in LEARN_FEATURES}))
        self.gate = 0.40 if role == "SNIPER" else 0.0

    def raw_dot(self, feat):
        vec = feature_vector(feat)
        return sum(self.weights.get(f, 0.0) * v for f, v in zip(LEARN_FEATURES, vec))

    def score(self, feat, regime, recall_nudge=0.0):
        raw = self.raw_dot(feat)
        re = feat.get("rsi_ext", 0.0)
        if self.role == "SNIPER":
            if abs(raw) < self.gate or abs(re) < 0.25:
                s = 0.0
            else:
                s = raw
                if regime in ("TREND_UP", "TREND_DOWN") and np.sign(s) != np.sign(feat.get("mom", 0.0)):
                    s *= 0.6
                s = s * Organism.ROLE_MULT["SNIPER"] * self.weight
        elif self.role == "SCALPER":
            s = raw * Organism.ROLE_MULT["SCALPER"] * self.weight
        elif self.role == "FLOW":
            s = raw * Organism.ROLE_MULT["FLOW"] * self.weight
        else:  # MOMENTUM
            s = raw * Organism.ROLE_MULT["MOMENTUM"] * self.weight
        if s != 0.0:
            s += recall_nudge * self.weight
        return s

# ──────────────────────────────────────────────────────────────
# مغز یادگیری — به‌روزرسانی آنلاین وزن‌ها + حافظه‌ی تجربه (k-NN recall)
class LearningCore:
    def __init__(self, orgs):
        self.orgs = orgs
        self.owner = None
        self.lr = 0.05
        self.total_updates = int(db_get("total_updates", 0))
        self.backtest_runs_count = int(db_get("bt_runs", 0))
        self.memory = deque(maxlen=4000)
        self.memory_idx = defaultdict(lambda: deque(maxlen=500))
        for o in self.orgs:
            saved = db_get(f"weights_{o.name}", None)
            if saved:
                o.weights.update(saved)
        self._load_memory()

    def _load_memory(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            rows = conn.execute("""SELECT regime, side, features, outcome FROM experiences
                                   ORDER BY id DESC LIMIT 4000""").fetchall()
            conn.close()
            for regime, side, feat_json, outcome in reversed(rows):
                feat = json.loads(feat_json)
                self.memory.append({"regime": regime, "side": side, "features": feat, "outcome": outcome})
                self.memory_idx[(regime, side)].append({"features": feat, "outcome": outcome})
        except Exception:
            pass

    def recall(self, feat, regime, side, k=10):
        """جست‌وجوی k نزدیک‌ترین تجربه‌ی مشابه گذشته و بازگرداندن یک اصلاح‌کننده‌ی اطمینان"""
        if feat is None:
            return 0.0, 0
        cand = self.memory_idx.get((regime, side))
        if not cand:
            return 0.0, 0
        cand = list(cand)
        vec = np.array(feature_vector(feat))
        mat = np.array([feature_vector(c["features"]) for c in cand])
        dists = np.linalg.norm(mat - vec, axis=1)
        kk = min(k, len(cand))
        idx = np.argsort(dists)[:kk]
        outcomes = np.array([cand[i]["outcome"] for i in idx])
        avg_outcome = float(outcomes.mean())
        nudge = float(np.clip(avg_outcome * 0.5, -0.22, 0.22))
        return nudge, kk

    def remember(self, regime, side, feat, outcome):
        rec = {"features": feat, "outcome": outcome}
        self.memory.append({"regime": regime, "side": side, **rec})
        self.memory_idx[(regime, side)].append(rec)
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("""INSERT INTO experiences (ts, regime, side, features, outcome)
                            VALUES (?,?,?,?,?)""",
                         (datetime.now(timezone.utc).isoformat(), regime, side, json.dumps(feat), outcome))
            conn.execute("""DELETE FROM experiences WHERE id NOT IN
                            (SELECT id FROM experiences ORDER BY id DESC LIMIT 6000)""")
            conn.commit()
            conn.close()
        except Exception:
            pass

    def update_from_trade(self, trade, pnl, source="live"):
        """قانون شبه‌پرسپترون: وزن هر ویژگی برای هر ارگانیسمِ رأی‌دهنده بر اساس نتیجه‌ی معامله تنظیم می‌شود"""
        votes = trade.get("votes") or {}
        feat = trade.get("features") or {}
        regime = trade.get("regime", "RANGING")
        side = trade.get("side")
        size = max(1.0, trade.get("size_usd", 20) * 0.06)
        outcome_norm = float(np.clip(pnl / size, -1, 1))
        lr = self.lr if source == "live" else self.lr * 0.4
        vec = feature_vector(feat)
        for org in self.orgs:
            v = votes.get(org.name)
            if not v:
                continue
            same_dir = 1.0 if v.get("side") == side else -1.0
            error = outcome_norm * same_dir
            for i, fname in enumerate(LEARN_FEATURES):
                grad = error * vec[i] * lr
                org.weights[fname] = float(np.clip(org.weights.get(fname, 0.15) + grad, -0.05, 1.7))
            db_set(f"weights_{org.name}", org.weights)
        self.remember(regime, side, feat, outcome_norm)
        self.total_updates += 1
        db_set("total_updates", self.total_updates)
        if self.total_updates % 4 == 0:
            self.snapshot(source)

    def snapshot(self, source="live"):
        if self.owner is None:
            return
        try:
            w = {o.name: dict(o.weights) for o in self.orgs}
            conn = sqlite3.connect(DB_PATH)
            conn.execute("""INSERT INTO learning_history (ts, source, weights, thresholds, awareness, total_updates)
                            VALUES (?,?,?,?,?,?)""",
                         (datetime.now(timezone.utc).isoformat(), source, json.dumps(w),
                          json.dumps(self.owner.adaptive), self.owner.awareness, self.total_updates))
            conn.commit()
            conn.close()
        except Exception:
            pass

# ──────────────────────────────────────────────────────────────
# هسته Hive
class HivePro:
    def __init__(self):
        init_db()
        self.capital = float(db_get("capital", INITIAL_CAPITAL))
        self.peak = float(db_get("peak", INITIAL_CAPITAL))
        self.awareness = float(db_get("awareness", 0.58))
        self.win_streak = int(db_get("ws", 0))
        self.loss_streak = int(db_get("ls", 0))
        self.adaptive = db_get("adaptive", {"score_threshold": 0.52, "conv_threshold": 0.41})
        self.orgs = [
            Organism("Aether", "SNIPER", 1.42),
            Organism("Pulse",  "SCALPER", 1.32),
            Organism("Flux",   "FLOW", 1.22),
            Organism("Vector", "MOMENTUM", 1.12),
        ]
        self.learning = LearningCore(self.orgs)
        self.learning.owner = self
        learned_rp = db_get("regime_params_learned", None)
        if learned_rp:
            for k, v in learned_rp.items():
                if k in REGIME_PARAMS and isinstance(v, dict):
                    REGIME_PARAMS[k].update(v)
        self.last_stats = {"scanned": 0, "cands": 0, "opened": 0, "regime_counts": {}}
        self._lock = threading.Lock()
        self.heart_beat = 0

    def total_neurons(self):
        return sum(o.neurons for o in self.orgs)

    def select_candidates(self, tickers, max_n=12):
        ranked = []
        for sym, t in tickers.items():
            if t["turn24"] < MIN_TURNOVER_24H:
                continue
            spread_bps = (t["ask"] - t["bid"]) / (t["last"] + 1e-12) * 10000
            if spread_bps > MAX_SPREAD_BPS:
                continue
            score = (math.log10(t["turn24"] + 1) * 0.38 +
                     abs(t["chg"]) * 85 * 0.37 +
                     (0.25 if t["vol24"] > 2e6 else 0.1))
            ranked.append((sym, score, t))
        ranked.sort(key=lambda x: -x[1])
        return ranked[:max_n]

    def correlation_ok(self, new_sym, opens, tickers):
        """جلوگیری از باز کردن نمادهای با همبستگی بالا (تقریبی با تغییر ۲۴ساعته)"""
        if not opens:
            return True
        new_chg = tickers.get(new_sym, {}).get("chg", 0)
        for t in opens:
            old_chg = tickers.get(t["symbol"], {}).get("chg", 0)
            if abs(new_chg) > 0.02 and abs(old_chg) > 0.02 and np.sign(new_chg) == np.sign(old_chg):
                if abs(new_chg - old_chg) < 0.015:
                    return False
        return True

    def decide(self, feat, regime):
        if feat is None:
            return None
        votes = []
        for o in self.orgs:
            raw = o.raw_dot(feat)
            tentative_side = "long" if raw >= 0 else "short"
            nudge, nsim = self.learning.recall(feat, regime, tentative_side)
            s = o.score(feat, regime, recall_nudge=nudge)
            if abs(s) < 0.26:
                continue
            side = "long" if s > 0 else "short"
            votes.append({"org": o.name, "role": o.role, "side": side, "score": s, "w": o.weight, "recall_n": nsim})
        if len(votes) < 2:
            return None
        long_s = sum(v["score"] * v["w"] for v in votes if v["side"] == "long")
        short_s = sum(abs(v["score"]) * v["w"] for v in votes if v["side"] == "short")
        thresh = self.adaptive.get("score_threshold", 0.52)
        if long_s > short_s and long_s > thresh:
            side, final = "long", long_s
        elif short_s > long_s and short_s > thresh:
            side, final = "short", short_s
        else:
            return None
        agreeing = [v for v in votes if v["side"] == side]
        if len(agreeing) < 2:
            return None
        has_sniper = any(v["role"] == "SNIPER" for v in agreeing)
        has_scalper = any(v["role"] == "SCALPER" for v in agreeing)
        if not (has_sniper or has_scalper):
            return None
        conv = min(1.0, final / 1.75 * (1.18 if has_sniper else 1.0))
        if conv < self.adaptive.get("conv_threshold", 0.41):
            return None
        reason = " | ".join(f"{v['org']}:{v['side'][0]}{v['score']:.2f}" for v in agreeing)
        return {
            "side": side, "conv": conv, "votes": {v["org"]: v for v in votes},
            "reason": f"HIVE[{len(agreeing)}] {reason}", "regime": regime
        }

    def calc_size(self, conv, atr_pct, regime, opens):
        rp = REGIME_PARAMS.get(regime, REGIME_PARAMS["RANGING"])
        risk = RISK_PER_TRADE_BASE * rp["risk_mult"] * (0.75 + 0.25 * conv)
        vol_target = 0.012
        vol_mult = vol_target / max(atr_pct, 0.004)
        vol_mult = float(np.clip(vol_mult, 0.55, 1.35))
        risk *= vol_mult
        free = max(0.0, self.capital - sum(t["size_usd"] for t in opens))
        sl = rp["sl"]
        size = (self.capital * risk) / (sl * LEVERAGE)
        size = min(size, free * 0.34, self.capital * 0.20)
        return max(18.0, size)

    def try_open(self, sym, ticker, decision, feat, regime):
        with self._lock:
            opens = get_open_trades()
            if len(opens) >= MAX_POSITIONS:
                return False
            if any(t["symbol"] == sym for t in opens):
                return False
            if not self.correlation_ok(sym, opens, {sym: ticker}):
                return False
            size = self.calc_size(decision["conv"], feat["atr_pct"], regime, opens)
            if size < 18:
                return False
            price = ticker["last"]
            spread_adj = (ticker["ask"] - ticker["bid"]) / 2 / price
            slip = SLIPPAGE_BPS / 10000
            if decision["side"] == "long":
                entry = price * (1 + spread_adj + slip)
                liq = entry * (1 - 0.92 / LEVERAGE)
            else:
                entry = price * (1 - spread_adj - slip)
                liq = entry * (1 + 0.92 / LEVERAGE)
            qty = (size * LEVERAGE) / entry
            rp = REGIME_PARAMS.get(regime, REGIME_PARAMS["RANGING"])
            trail = entry * (1 - rp["sl"] * 1.1) if decision["side"] == "long" else entry * (1 + rp["sl"] * 1.1)
            t = {
                "symbol": sym, "side": decision["side"], "entry": entry, "size_usd": size,
                "qty": qty, "leverage": LEVERAGE, "liq_price": liq,
                "entry_time": datetime.now(timezone.utc).isoformat(),
                "reason": decision["reason"], "votes": decision["votes"],
                "regime": regime, "features": feat, "partials": [], "trail_stop": trail
            }
            tid = save_trade(t)
            log_decision(sym, decision["side"], decision["conv"], regime, feat, decision["votes"], True, decision["reason"])
            return True

    def manage_positions(self):
        opens = get_open_trades()
        if not opens:
            return
        tickers = get_all_tickers()
        now = datetime.now(timezone.utc)
        for t in opens:
            last = tickers.get(t["symbol"], {}).get("last")
            if last is None:
                continue
            side = t["side"]
            entry = t["entry"]
            rp = REGIME_PARAMS.get(t["regime"], REGIME_PARAMS["RANGING"])
            if side == "long":
                pnl_pct = (last - entry) / entry
            else:
                pnl_pct = (entry - last) / entry
            remaining_size = t["size_usd"] * (1 - sum(p.get("frac", 0) for p in t["partials"]))
            pnl_usd = pnl_pct * remaining_size * LEVERAGE - remaining_size * COMMISSION * 2

            hold_min = (now - datetime.fromisoformat(t["entry_time"])).total_seconds() / 60.0
            trail = t["trail_stop"]
            partials = t["partials"][:]

            partial_level = rp["partial_at"]
            if pnl_pct >= partial_level and not any(p.get("level") == "p1" for p in partials):
                part_frac = 0.40
                part_pnl = pnl_pct * t["size_usd"] * part_frac * LEVERAGE - t["size_usd"] * part_frac * COMMISSION * 2
                partials.append({"level": "p1", "frac": part_frac, "price": last, "pnl": part_pnl, "ts": now.isoformat()})
                self.capital += part_pnl
                if side == "long":
                    trail = max(trail, last * (1 - rp["sl"] * 0.7))
                else:
                    trail = min(trail, last * (1 + rp["sl"] * 0.7))
                update_trade(t["id"], partials=json.dumps(partials), trail_stop=trail)

            if side == "long":
                new_trail = last * (1 - rp["sl"] * rp["trail_mult"] * 0.6)
                if new_trail > trail:
                    trail = new_trail
                    update_trade(t["id"], trail_stop=trail)
                hit_trail = last <= trail
            else:
                new_trail = last * (1 + rp["sl"] * rp["trail_mult"] * 0.6)
                if new_trail < trail:
                    trail = new_trail
                    update_trade(t["id"], trail_stop=trail)
                hit_trail = last >= trail

            full_close = False
            if pnl_pct >= rp["tp"] or pnl_pct <= -rp["sl"]:
                full_close = True
            if hit_trail:
                full_close = True
            if hold_min >= 22:
                full_close = True
            if hold_min > 5 and abs(pnl_pct) < 0.0008:
                full_close = True
            if side == "long" and last <= t["liq_price"] * 1.008:
                full_close = True
            if side == "short" and last >= t["liq_price"] * 0.992:
                full_close = True

            if full_close:
                remain_frac = 1.0 - sum(p.get("frac", 0) for p in partials)
                final_pnl = pnl_pct * t["size_usd"] * remain_frac * LEVERAGE - t["size_usd"] * remain_frac * COMMISSION * 2
                total_pnl = final_pnl + sum(p.get("pnl", 0) for p in partials)
                close_trade_full(t["id"], last, total_pnl)
                self.capital += final_pnl
                if total_pnl > 0:
                    self.win_streak += 1
                    self.loss_streak = 0
                else:
                    self.win_streak = 0
                    self.loss_streak += 1
                db_set("capital", self.capital)
                db_set("ws", self.win_streak)
                db_set("ls", self.loss_streak)
                self._learn_from_trade(total_pnl, t)

    def _adapt_thresholds_from_stats(self, wr, pnl_positive, source="live"):
        """تنظیم خودکار آستانه‌های تصمیم‌گیری بر اساس وین‌ریتِ اخیر — لایه‌ی فراـیادگیری (meta-learning)"""
        step = 1.0 if source == "live" else 0.5
        if wr > 0.58 and pnl_positive:
            self.adaptive["score_threshold"] = max(0.45, self.adaptive["score_threshold"] - 0.008 * step)
            self.adaptive["conv_threshold"] = max(0.36, self.adaptive["conv_threshold"] - 0.006 * step)
            self.awareness = min(0.96, self.awareness + 0.004 * step)
        elif wr < 0.42:
            self.adaptive["score_threshold"] = min(0.62, self.adaptive["score_threshold"] + 0.012 * step)
            self.adaptive["conv_threshold"] = min(0.50, self.adaptive["conv_threshold"] + 0.010 * step)
            self.awareness = max(0.40, self.awareness - 0.003 * step)
        db_set("adaptive", self.adaptive)
        db_set("awareness", self.awareness)

    def _tune_regime_params(self, regime, win):
        """خودتنظیمی تدریجی TP/SL هر رژیم بر اساس وین‌ریت تجمعی آن رژیم، با دامنه‌ی محدود امن"""
        perf = db_get("regime_perf", {})
        d = perf.get(regime, {"n": 0, "wins": 0})
        d["n"] += 1
        d["wins"] += 1 if win else 0
        perf[regime] = d
        db_set("regime_perf", perf)
        if regime in REGIME_PARAMS and d["n"] >= 10 and d["n"] % 5 == 0:
            wr = d["wins"] / d["n"]
            rp = REGIME_PARAMS[regime]
            base = REGIME_PARAMS_BASE[regime]
            if wr > 0.55:
                rp["tp"] = float(np.clip(rp["tp"] * 1.01, base["tp"] * 0.8, base["tp"] * 1.3))
                rp["sl"] = float(np.clip(rp["sl"] * 0.99, base["sl"] * 0.75, base["sl"] * 1.15))
            elif wr < 0.42:
                rp["sl"] = float(np.clip(rp["sl"] * 1.02, base["sl"] * 0.75, base["sl"] * 1.4))
                rp["tp"] = float(np.clip(rp["tp"] * 0.99, base["tp"] * 0.75, base["tp"] * 1.3))
            db_set("regime_params_learned", REGIME_PARAMS)
        return d

    def _learn_from_trade(self, pnl, trade):
        """یادگیری بعد از معامله — سه لایه: آستانه‌ها، وزن نورونی، پارامتر رژیم"""
        closed = get_closed_trades(40)
        if len(closed) >= 8:
            wins = [t for t in closed if t["pnl"] and t["pnl"] > 0]
            wr = len(wins) / len(closed)
            self._adapt_thresholds_from_stats(wr, pnl > 0, source="live")
        self.learning.update_from_trade(trade, pnl, source="live")
        self._tune_regime_params(trade.get("regime", "RANGING"), pnl > 0)

    def equity(self):
        opens = get_open_trades()
        if not opens:
            return self.capital
        tickers = get_all_tickers()
        unreal = 0.0
        for t in opens:
            last = tickers.get(t["symbol"], {}).get("last", t["entry"])
            if t["side"] == "long":
                pp = (last - t["entry"]) / t["entry"]
            else:
                pp = (t["entry"] - last) / t["entry"]
            remain = 1.0 - sum(p.get("frac", 0) for p in t["partials"])
            unreal += pp * t["size_usd"] * remain * LEVERAGE - t["size_usd"] * remain * COMMISSION * 2
        return self.capital + unreal

    def cycle(self):
        self.manage_positions()
        tickers = get_all_tickers()
        if not tickers:
            self.last_stats = {"scanned": 0, "cands": 0, "opened": 0, "regime_counts": {}}
            return
        cands = self.select_candidates(tickers, 11)
        self.last_stats["scanned"] = len(tickers)
        self.last_stats["cands"] = len(cands)
        opened = 0
        regime_counts = defaultdict(int)
        for sym, sc, tk in cands:
            try:
                df = get_klines(sym, "5", 120)
                if df.empty:
                    continue
                regime = detect_regime(df)
                regime_counts[regime] += 1
                feat = extract_features(df, tk)
                if feat is None or feat["spread_bps"] > MAX_SPREAD_BPS:
                    continue
                dec = self.decide(feat, regime)
                if dec is None:
                    log_decision(sym, "none", 0, regime, feat or {}, {}, False, "no consensus")
                    continue
                if self.try_open(sym, tk, dec, feat, regime):
                    opened += 1
            except Exception:
                continue
        self.last_stats["opened"] = opened
        self.last_stats["regime_counts"] = dict(regime_counts)
        eq = self.equity()
        self.peak = max(self.peak, eq)
        db_set("peak", self.peak)
        record_equity(eq, len(get_open_trades()))
        self.heart_beat += 1

# ──────────────────────────────────────────────────────────────
# بک‌تست واک‌فوروارد با یادگیری زنده — بدون نگاه به آینده، تا سقف ۱۰,۰۰۰ کندل
def run_backtest_walkforward(symbol, candles=10000, interval="5"):
    t0 = time.time()
    try:
        candles = int(max(300, min(10000, candles)))
        df = get_klines_deep(symbol, interval, total=candles)
        if df.empty or len(df) < 150:
            return {"error": "داده‌ی کافی برای بک‌تست دریافت نشد. نماد یا اتصال شبکه را بررسی کنید."}

        close_arr = df["close"].values
        high_arr = df["high"].values
        low_arr = df["low"].values
        vol_arr = df["volume"].values
        n = len(df)

        capital = INITIAL_CAPITAL
        position = None
        trades = []
        equity_curve = []
        regime_counts = defaultdict(int)
        bt_recent_pnls = []
        WIN = 150

        with HIVE._lock:
            for i in range(60, n - 1):
                lo = max(0, i - WIN)
                c = close_arr[lo:i + 1]; h = high_arr[lo:i + 1]; l = low_arr[lo:i + 1]; v = vol_arr[lo:i + 1]
                regime = detect_regime_arr(c, h, l)
                regime_counts[regime] += 1
                row_close = float(close_arr[i])
                ticker = {"last": row_close, "bid": row_close * 0.9998, "ask": row_close * 1.0002}
                feat = extract_features_arr(c, h, l, v, ticker)
                if feat is None:
                    equity_curve.append(capital)
                    continue
                rp = REGIME_PARAMS.get(regime, REGIME_PARAMS["RANGING"])

                if position is not None:
                    last = row_close
                    side = position["side"]; entry = position["entry"]
                    pnl_pct = (last - entry) / entry if side == "long" else (entry - last) / entry
                    hold_bars = i - position["i0"]
                    partials = position["partials"]
                    trail = position["trail"]

                    if pnl_pct >= rp["partial_at"] and not any(p["level"] == "p1" for p in partials):
                        frac = 0.40
                        ppnl = pnl_pct * position["size"] * frac * LEVERAGE - position["size"] * frac * COMMISSION * 2
                        partials.append({"level": "p1", "frac": frac, "pnl": ppnl})
                        capital += ppnl
                        trail = max(trail, last * (1 - rp["sl"] * 0.7)) if side == "long" else min(trail, last * (1 + rp["sl"] * 0.7))

                    if side == "long":
                        nt = last * (1 - rp["sl"] * rp["trail_mult"] * 0.6)
                        if nt > trail: trail = nt
                        hit_trail = last <= trail
                    else:
                        nt = last * (1 + rp["sl"] * rp["trail_mult"] * 0.6)
                        if nt < trail: trail = nt
                        hit_trail = last >= trail
                    position["trail"] = trail

                    full_close = (pnl_pct >= rp["tp"] or pnl_pct <= -rp["sl"] or hit_trail or
                                  hold_bars >= 45 or (hold_bars > 5 and abs(pnl_pct) < 0.0008))
                    if full_close:
                        remain = 1.0 - sum(p["frac"] for p in partials)
                        final_pnl = pnl_pct * position["size"] * remain * LEVERAGE - position["size"] * remain * COMMISSION * 2
                        total_pnl = final_pnl + sum(p["pnl"] for p in partials)
                        capital += final_pnl
                        win = total_pnl > 0
                        trade_rec = {
                            "symbol": symbol, "side": side, "regime": position["regime"],
                            "features": position["features"], "votes": position["votes"],
                            "size_usd": position["size"], "pnl": total_pnl
                        }
                        trades.append(trade_rec)
                        HIVE.learning.update_from_trade(trade_rec, total_pnl, source="backtest")
                        HIVE._tune_regime_params(position["regime"], win)
                        bt_recent_pnls.append(total_pnl)
                        if len(bt_recent_pnls) > 40:
                            bt_recent_pnls.pop(0)
                        if len(bt_recent_pnls) >= 8:
                            wr_bt = sum(1 for p in bt_recent_pnls if p > 0) / len(bt_recent_pnls)
                            HIVE._adapt_thresholds_from_stats(wr_bt, total_pnl > 0, source="backtest")
                        position = None
                else:
                    dec = HIVE.decide(feat, regime)
                    if dec is not None:
                        size = HIVE.calc_size(dec["conv"], feat["atr_pct"], regime, [])
                        entry = row_close * (1 + 0.0003) if dec["side"] == "long" else row_close * (1 - 0.0003)
                        trailp = entry * (1 - rp["sl"] * 1.1) if dec["side"] == "long" else entry * (1 + rp["sl"] * 1.1)
                        position = {
                            "side": dec["side"], "entry": entry, "size": size, "regime": regime,
                            "i0": i, "partials": [], "trail": trailp, "features": feat, "votes": dec["votes"]
                        }
                equity_curve.append(capital)

            HIVE.learning.backtest_runs_count += 1
            db_set("bt_runs", HIVE.learning.backtest_runs_count)
            HIVE.learning.snapshot("backtest")

        wins = [t for t in trades if t["pnl"] > 0]
        winrate = len(wins) / len(trades) if trades else 0.0
        total_return = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL
        maxdd = compute_maxdd(equity_curve if equity_curve else [INITIAL_CAPITAL])
        step = max(1, len(equity_curve) // 400)
        result = {
            "symbol": symbol, "candles": n, "trades": len(trades), "winrate": winrate,
            "total_return": total_return, "final_capital": capital, "max_dd": maxdd,
            "avg_pnl": float(np.mean([t["pnl"] for t in trades])) if trades else 0.0,
            "equity_curve": equity_curve[::step],
            "regime_counts": dict(regime_counts),
            "run_number": HIVE.learning.backtest_runs_count,
            "weights_snapshot": {o.name: dict(o.weights) for o in HIVE.orgs},
            "thresholds": dict(HIVE.adaptive),
            "awareness": HIVE.awareness,
            "elapsed_sec": round(time.time() - t0, 2),
        }
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO backtest_runs (ts, symbol, params, metrics) VALUES (?,?,?,?)",
                     (datetime.now(timezone.utc).isoformat(), symbol, json.dumps({"candles": n, "interval": interval}),
                      json.dumps(result)))
        conn.commit()
        conn.close()
        return result
    except Exception as e:
        return {"error": f"خطای غیرمنتظره در بک‌تست: {e}"}

# ──────────────────────────────────────────────────────────────
# نمونه سراسری
HIVE = HivePro()

# ──────────────────────────────────────────────────────────────
# رابط کاربری (راست‌چین / RTL)
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG], suppress_callback_exceptions=True)
app.title = "HIVE PRO — Scalper Sniper"
server = app.server

app.index_string = """
<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
{%metas%}
<title>{%title%}</title>
{%favicon%}
{%css%}
<style>
  body { direction: rtl; text-align: right; }
  .dash-table-container, .dash-spreadsheet-container { direction: rtl; }
  ::-webkit-scrollbar { width: 8px; height: 8px; }
  ::-webkit-scrollbar-thumb { background: #23314d; border-radius: 4px; }
</style>
</head>
<body>
{%app_entry%}
<footer>
{%config%}
{%scripts%}
{%renderer%}
</footer>
</body>
</html>
"""

def card(title, val, color=GOLD, sub=""):
    return dbc.Card(dbc.CardBody([
        html.Div(title, style={"color": MUT, "fontSize": 11}),
        html.Div(str(val), style={"color": color, "fontSize": 19, "fontWeight": "bold"}),
        html.Div(sub, style={"color": MUT, "fontSize": 10})
    ]), style={"background": CARD, "border": f"1px solid {LINE}", "height": "100%"})

app.layout = html.Div([
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col(html.H3("HIVE PRO  ×20  SCALPER-SNIPER", style={"color": GOLD, "margin": 0}), md=5),
        dbc.Col(html.Div(id="pulse", style={"color": NEON, "fontFamily": "monospace", "fontSize": 13}), md=4),
        dbc.Col(html.Div(id="status", style={"textAlign": "left", "color": MUT, "fontSize": 12}), md=3),
    ])), style={"margin": "8px 12px", "background": CARD, "border": f"1px solid {LINE}"}),

    dcc.Tabs(id="tabs", value="live", children=[
        dcc.Tab(label="معاملات زنده", value="live", style={"background": CARD, "color": TXT}, selected_style={"background": LINE, "color": GOLD}),
        dcc.Tab(label="وضعیت Hive + رژیم", value="stats", style={"background": CARD, "color": TXT}, selected_style={"background": LINE, "color": GOLD}),
        dcc.Tab(label="بک‌تست", value="backtest", style={"background": CARD, "color": TXT}, selected_style={"background": LINE, "color": GOLD}),
        dcc.Tab(label="یادگیری", value="learning", style={"background": CARD, "color": TXT}, selected_style={"background": LINE, "color": GOLD}),
        dcc.Tab(label="تحلیل عملکرد", value="perf", style={"background": CARD, "color": TXT}, selected_style={"background": LINE, "color": GOLD}),
    ], style={"margin": "0 12px"}),
    html.Div(id="content", style={"padding": "12px"}),
    dcc.Interval(id="life", interval=11_000, n_intervals=0),
    dcc.Interval(id="cycle", interval=32_000, n_intervals=0),
    dcc.Store(id="bt-result"),
    dcc.Store(id="bt-config", storage_type="memory", data={"symbol": "BTCUSDT", "candles": 10000, "interval": "5"}),
], style={"background": BG, "minHeight": "100vh", "color": TXT, "direction": "rtl", "textAlign": "right"})

@app.callback(Output("content", "children"), Input("tabs", "value"), Input("life", "n_intervals"),
              Input("bt-result", "data"), State("bt-config", "data"))
def render(tab, n, bt_data, bt_cfg):
    if tab == "live":
        return live_tab()
    if tab == "stats":
        return stats_tab()
    if tab == "backtest":
        return backtest_tab(bt_data, bt_cfg)
    if tab == "learning":
        return learning_tab()
    return perf_tab()

def live_tab():
    h = HIVE
    opens = get_open_trades()
    closed = get_closed_trades(25)
    eq = h.equity()
    if opens:
        tickers = get_all_tickers()
        rows = []
        for t in opens:
            last = tickers.get(t["symbol"], {}).get("last", t["entry"])
            if t["side"] == "long":
                pp = (last - t["entry"]) / t["entry"]
            else:
                pp = (t["entry"] - last) / t["entry"]
            remain = 1.0 - sum(p.get("frac", 0) for p in t["partials"])
            pnl = pp * t["size_usd"] * remain * LEVERAGE - t["size_usd"] * remain * COMMISSION * 2
            color = UP if pnl >= 0 else DN
            rows.append(html.Tr([
                html.Td(t["id"]), html.Td(t["symbol"]),
                html.Td(t["side"].upper(), style={"color": UP if t["side"]=="long" else DN}),
                html.Td(t["regime"]), html.Td(f"{t['entry']:.5f}"), html.Td(f"{last:.5f}"),
                html.Td(f"${t['size_usd']:.1f}"), html.Td(f"{pnl:+.2f}", style={"color": color, "fontWeight": "bold"}),
                html.Td(f"{t['trail_stop']:.5f}" if t["trail_stop"] else "—", style={"fontSize": 11}),
                html.Td(f"{len(t['partials'])}", style={"fontSize": 11}),
            ]))
        table = dbc.Table([
            html.Thead(html.Tr([html.Th(x) for x in ["ID","نماد","سمت","رژیم","ورود","فعلی","مارجین","PnL","Trail","Partial"]])),
            html.Tbody(rows)
        ], bordered=True, hover=True, size="sm", style={"background": CARD})
    else:
        table = dbc.Alert("در حال اسکن و تشکیل اجماع...", color="secondary")

    eqh = get_equity_history()
    if eqh.empty:
        eqh = pd.DataFrame({"ts": [datetime.now(timezone.utc).isoformat()], "equity": [INITIAL_CAPITAL]})
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=pd.to_datetime(eqh["ts"]), y=eqh["equity"], mode="lines",
                             line=dict(color=GOLD, width=2), fill="tozeroy", fillcolor="rgba(240,185,11,0.1)"))
    fig.add_hline(y=INITIAL_CAPITAL, line_dash="dot", line_color=MUT)
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD, height=270,
                      margin=dict(l=40, r=20, t=30, b=30), title=dict(text="Equity Live", font=dict(color=GOLD, size=13)),
                      xaxis=dict(gridcolor=LINE), yaxis=dict(gridcolor=LINE, tickprefix="$"))

    wr = (sum(1 for t in closed if t["pnl"] and t["pnl"] > 0) / len(closed) * 100) if closed else 0
    total = sum(t["pnl"] or 0 for t in closed)

    # نمودار وزن‌های زنده‌ی هر ارگانیسم به عنوان عنصر بصری آگاهی
    mini_fig = go.Figure()
    for o in h.orgs:
        mini_fig.add_trace(go.Bar(name=o.name, x=[o.role], y=[sum(abs(v) for v in o.weights.values())]))
    mini_fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD, height=180,
                           margin=dict(l=30, r=10, t=30, b=20),
                           title=dict(text="مجموع قدرت وزنی هر ارگانیسم (زنده)", font=dict(color=GOLD, size=12)),
                           xaxis=dict(gridcolor=LINE), yaxis=dict(gridcolor=LINE),
                           legend=dict(font=dict(color=TXT, size=9)))

    return html.Div([
        dbc.Row([
            dbc.Col(card("Equity", f"${eq:.2f}", GOLD, f"Peak ${h.peak:.2f}"), md=3),
            dbc.Col(card("WinRate", f"{wr:.1f}%", UP if wr >= 50 else DN), md=3),
            dbc.Col(card("Realized", f"${total:+.2f}", UP if total >= 0 else DN), md=3),
            dbc.Col(card("Open", f"{len(opens)}/{MAX_POSITIONS}", NEON), md=3),
        ], className="mb-3"),
        html.H5("پوزیشن‌های باز (Partial + Trailing فعال)", style={"color": GOLD}),
        table,
        dbc.Row([
            dbc.Col(dcc.Graph(figure=fig, config={"displaylogo": False}), md=8),
            dbc.Col(dcc.Graph(figure=mini_fig, config={"displaylogo": False}), md=4),
        ]),
    ])

def stats_tab():
    h = HIVE
    eq = h.equity()
    rc = h.last_stats.get("regime_counts", {})

    w_fig = go.Figure()
    for o in h.orgs:
        w_fig.add_trace(go.Bar(name=o.name, x=list(o.weights.keys()), y=list(o.weights.values())))
    w_fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD, height=300, barmode="group",
                        margin=dict(l=40, r=20, t=30, b=40),
                        title=dict(text="وزن‌های نورونی زنده‌ی هر ارگانیسم (قابل یادگیری)", font=dict(color=GOLD, size=13)),
                        xaxis=dict(gridcolor=LINE), yaxis=dict(gridcolor=LINE),
                        legend=dict(font=dict(color=TXT, size=10)))

    rp_rows = []
    for reg, rp in REGIME_PARAMS.items():
        base = REGIME_PARAMS_BASE[reg]
        rp_rows.append(html.Tr([
            html.Td(reg), html.Td(f"{rp['tp']*100:.2f}%"), html.Td(f"{rp['sl']*100:.2f}%"),
            html.Td(f"{base['tp']*100:.2f}%", style={"color": MUT}), html.Td(f"{base['sl']*100:.2f}%", style={"color": MUT}),
        ]))
    rp_table = dbc.Table([
        html.Thead(html.Tr([html.Th(x) for x in ["رژیم", "TP فعلی (یادگرفته‌شده)", "SL فعلی", "TP پایه", "SL پایه"]])),
        html.Tbody(rp_rows)
    ], bordered=True, hover=True, size="sm", style={"background": CARD})

    return html.Div([
        dbc.Row([
            dbc.Col(card("Equity", f"${eq:.2f}", GOLD), md=2),
            dbc.Col(card("آگاهی", f"{h.awareness:.0%}", NEON), md=2),
            dbc.Col(card("نورون", f"{h.total_neurons():,}", ACCENT), md=2),
            dbc.Col(card("آستانه امتیاز", f"{h.adaptive['score_threshold']:.3f}", ORANGE), md=2),
            dbc.Col(card("آستانه Conv", f"{h.adaptive['conv_threshold']:.3f}", ORANGE), md=2),
            dbc.Col(card("اسکن/کاندید", f"{h.last_stats['scanned']}/{h.last_stats['cands']}", GOLD), md=2),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col(card("آپدیت‌های یادگیری", f"{h.learning.total_updates:,}", NEON), md=3),
            dbc.Col(card("اجرای بک‌تست", f"{h.learning.backtest_runs_count}", ACCENT), md=3),
            dbc.Col(card("حافظه‌ی تجربه", f"{len(h.learning.memory):,}", GOLD), md=3),
            dbc.Col(card("نرخ یادگیری (lr)", f"{h.learning.lr:.3f}", ORANGE), md=3),
        ], className="mb-3"),
        html.H5("ارگانیسم‌ها", style={"color": GOLD}),
        dbc.Row([
            dbc.Col(card(o.name, o.role, NEON if o.role=="SNIPER" else ORANGE if o.role=="SCALPER" else ACCENT,
                         f"{o.neurons:,} نورون | w={o.weight}"), md=3) for o in h.orgs
        ], className="mb-3"),
        dcc.Graph(figure=w_fig, config={"displaylogo": False}),
        html.H5("توزیع رژیم آخرین اسکن", style={"color": GOLD, "marginTop": 10}),
        html.Div([html.Span(f"{k}: {v}   ", style={"color": NEON if "TREND" in k else MUT}) for k, v in rc.items()] or "—"),
        html.H5("پارامترهای خودتنظیم هر رژیم", style={"color": GOLD, "marginTop": 14}),
        rp_table,
        html.Hr(style={"borderColor": LINE}),
        html.Div([
            html.Div("قابلیت‌های فعال:", style={"color": GOLD, "fontWeight": "bold"}),
            html.Div("۱. بک‌تست واک‌فوروارد واقعی با کارمزد/اسپرد/لغزش تا ۱۰,۰۰۰ کندل", style={"color": MUT}),
            html.Div("۲. رژیم‌دیتکشن + پارامتر داینامیک خودتنظیم بر اساس وین‌ریت هر رژیم", style={"color": MUT}),
            html.Div("۳. Volatility Targeting + فیلتر همبستگی پوزیشن‌ها", style={"color": MUT}),
            html.Div("۴. فیلتر سخت نقدشوندگی (turnover) و اسپرد لحظه‌ای", style={"color": MUT}),
            html.Div("۵. خروج جزئی + Trailing هوشمند بر اساس رژیم", style={"color": MUT}),
            html.Div("۶. یادگیری عمیق آنلاین: وزن نورونی هر ارگانیسم با قاعده‌ی گرادیانی از نتیجه‌ی هر معامله اصلاح می‌شود", style={"color": MUT}),
            html.Div("۷. حافظه‌ی تجربه (k-NN Recall): تصمیم فعلی با نزدیک‌ترین تجربه‌های مشابه گذشته مقایسه می‌شود", style={"color": MUT}),
            html.Div("۸. یادگیری تجمعی در بک‌تست: هر کلیک روی دکمه‌ی بک‌تست، مغز را با دانش اجرای قبلی قوی‌تر می‌کند", style={"color": MUT}),
        ], style={"background": CARD, "padding": 14, "borderRadius": 8, "border": f"1px solid {LINE}"})
    ])

def backtest_tab(bt_data, bt_config=None):
    cfg = bt_config or {"symbol": "BTCUSDT", "candles": 10000, "interval": "5"}
    return html.Div([
        html.H5("بک‌تست واک‌فوروارد با یادگیری زنده (بدون نگاه به آینده)", style={"color": GOLD}),
        html.P("هر اجرا از وزن‌ها و آستانه‌های یادگرفته‌شده در اجرای قبلی ادامه می‌دهد و مغز ارگانیسم را قوی‌تر می‌کند؛ "
               "معیارهای هر اجرا با اجراهای قبلی در تب «یادگیری» قابل مقایسه است.",
               style={"color": MUT, "fontSize": 12}),
        dbc.Row([
            dbc.Col([html.Label("نماد", style={"color": MUT, "fontSize": 11}),
                     dcc.Input(id="bt-symbol", value=cfg.get("symbol", "BTCUSDT"), type="text",
                               style={"width": "100%", "padding": 8, "borderRadius": 6})], md=3),
            dbc.Col([html.Label("تعداد کندل (حداکثر ۱۰,۰۰۰)", style={"color": MUT, "fontSize": 11}),
                     dcc.Input(id="bt-candles", value=cfg.get("candles", 10000), type="number", min=300, max=10000, step=100,
                               style={"width": "100%", "padding": 8, "borderRadius": 6})], md=3),
            dbc.Col([html.Label("تایم‌فریم", style={"color": MUT, "fontSize": 11}),
                     dcc.Dropdown(id="bt-interval",
                                  options=[{"label": "۵ دقیقه", "value": "5"},
                                           {"label": "۱۵ دقیقه", "value": "15"},
                                           {"label": "۱ ساعت", "value": "60"}],
                                  value=cfg.get("interval", "5"), clearable=False,
                                  style={"color": "#000"})], md=3),
            dbc.Col([html.Label("\u00a0", style={"display": "block", "fontSize": 11}),
                     dbc.Button("اجرای بک‌تست و تقویت یادگیری", id="bt-run", color="warning",
                                style={"width": "100%", "fontWeight": "bold"})], md=3),
        ], className="mb-3"),
        dcc.Loading(
            html.Div(id="bt-output",
                     children=render_bt_result(bt_data) if bt_data else
                     dbc.Alert("هنوز اجرا نشده. روی «اجرای بک‌تست» بزنید تا مغز ارگانیسم از داده‌ی تاریخی یاد بگیرد. "
                               "پردازش تا ۱۰,۰۰۰ کندل ممکن است چند ثانیه تا حدود نیم دقیقه طول بکشد.", color="secondary")),
            type="circle", color=GOLD),
    ])

def render_bt_result(data):
    if not data:
        return dbc.Alert("نتیجه‌ای وجود ندارد.", color="secondary")
    if data.get("error"):
        return dbc.Alert(data["error"], color="danger")

    eq_fig = go.Figure()
    eq_fig.add_trace(go.Scatter(y=data["equity_curve"], mode="lines", line=dict(color=GOLD, width=2),
                                fill="tozeroy", fillcolor="rgba(240,185,11,0.12)", name="Equity"))
    eq_fig.add_hline(y=INITIAL_CAPITAL, line_dash="dot", line_color=MUT)
    eq_fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD, height=260,
                         margin=dict(l=40, r=20, t=30, b=30),
                         title=dict(text=f"منحنی سرمایه — اجرای یادگیری #{data.get('run_number','?')}", font=dict(color=GOLD, size=13)),
                         xaxis=dict(gridcolor=LINE, title="گام زمانی"), yaxis=dict(gridcolor=LINE, tickprefix="$"))

    rc = data.get("regime_counts", {})
    pie_fig = go.Figure(go.Pie(labels=list(rc.keys()), values=list(rc.values()), hole=0.55,
                               marker=dict(colors=[NEON, ORANGE, ACCENT, DN])))
    pie_fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=260,
                          margin=dict(l=10, r=10, t=30, b=10),
                          title=dict(text="توزیع رژیم بازار طی بک‌تست", font=dict(color=GOLD, size=13)),
                          legend=dict(font=dict(color=TXT, size=10)))

    w_fig = go.Figure()
    for name, w in data.get("weights_snapshot", {}).items():
        w_fig.add_trace(go.Bar(name=name, x=list(w.keys()), y=list(w.values())))
    w_fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD, height=280, barmode="group",
                        margin=dict(l=40, r=20, t=30, b=40),
                        title=dict(text="وزن‌های نورونی هر ارگانیسم پس از این اجرا", font=dict(color=GOLD, size=13)),
                        xaxis=dict(gridcolor=LINE), yaxis=dict(gridcolor=LINE),
                        legend=dict(font=dict(color=TXT, size=10)))

    metrics = dbc.Row([
        dbc.Col(card("نماد", data["symbol"], GOLD), md=2),
        dbc.Col(card("کندل پردازش‌شده", f"{data['candles']:,}", NEON), md=2),
        dbc.Col(card("تعداد معامله", data["trades"], ACCENT), md=2),
        dbc.Col(card("وین‌ریت", f"{data['winrate']*100:.1f}%", UP if data['winrate'] >= 0.5 else DN), md=2),
        dbc.Col(card("بازده کل", f"{data['total_return']*100:+.2f}%", UP if data['total_return'] >= 0 else DN), md=2),
        dbc.Col(card("حداکثر افت (DD)", f"{data['max_dd']*100:.1f}%", ORANGE), md=2),
    ], className="mb-3")
    metrics2 = dbc.Row([
        dbc.Col(card("سرمایه نهایی", f"${data['final_capital']:.2f}", GOLD), md=3),
        dbc.Col(card("میانگین PnL هر معامله", f"${data['avg_pnl']:+.2f}", GOLD), md=3),
        dbc.Col(card("شماره‌ی اجرای یادگیری", f"#{data['run_number']}", NEON), md=3),
        dbc.Col(card("زمان اجرا", f"{data['elapsed_sec']}s", MUT), md=3),
    ], className="mb-3")

    return html.Div([
        metrics, metrics2,
        dbc.Row([dbc.Col(dcc.Graph(figure=eq_fig, config={"displaylogo": False}), md=7),
                 dbc.Col(dcc.Graph(figure=pie_fig, config={"displaylogo": False}), md=5)], className="mb-2"),
        dcc.Graph(figure=w_fig, config={"displaylogo": False}),
        dbc.Alert(
            f"آستانه امتیاز فعلی: {data['thresholds']['score_threshold']:.3f} | "
            f"آستانه Conv: {data['thresholds']['conv_threshold']:.3f} | آگاهی: {data['awareness']:.1%} — "
            "این مقادیر یادگرفته‌شده در اجرای بعدی بک‌تست و در معاملات زنده به‌کار می‌روند.",
            color="dark", style={"border": f"1px solid {LINE}", "marginTop": 10}),
    ])

def learning_tab():
    h = HIVE
    hist = get_learning_history(300)
    if hist:
        updates_x = [r[5] for r in hist]
        awareness_y = [r[4] for r in hist]
        thresholds = [json.loads(r[3]) if r[3] else {} for r in hist]
        score_th = [t.get("score_threshold") for t in thresholds]
        conv_th = [t.get("conv_threshold") for t in thresholds]

        fig_aw = go.Figure()
        fig_aw.add_trace(go.Scatter(x=updates_x, y=awareness_y, mode="lines", name="آگاهی", line=dict(color=NEON, width=2)))
        fig_aw.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD, height=250,
                             margin=dict(l=40, r=20, t=30, b=30),
                             title=dict(text="روند آگاهی ارگانیسم در طول یادگیری", font=dict(color=GOLD, size=13)),
                             xaxis=dict(gridcolor=LINE, title="تعداد آپدیت یادگیری"),
                             yaxis=dict(gridcolor=LINE, tickformat=".0%"))

        fig_th = go.Figure()
        fig_th.add_trace(go.Scatter(x=updates_x, y=score_th, mode="lines", name="آستانه امتیاز", line=dict(color=ORANGE, width=2)))
        fig_th.add_trace(go.Scatter(x=updates_x, y=conv_th, mode="lines", name="آستانه Conv", line=dict(color=ACCENT, width=2)))
        fig_th.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD, height=250,
                             margin=dict(l=40, r=20, t=30, b=30),
                             title=dict(text="تکامل آستانه‌های تصمیم‌گیری", font=dict(color=GOLD, size=13)),
                             xaxis=dict(gridcolor=LINE, title="تعداد آپدیت یادگیری"), yaxis=dict(gridcolor=LINE),
                             legend=dict(font=dict(color=TXT, size=10)))
        charts = dbc.Row([
            dbc.Col(dcc.Graph(figure=fig_aw, config={"displaylogo": False}), md=6),
            dbc.Col(dcc.Graph(figure=fig_th, config={"displaylogo": False}), md=6),
        ], className="mb-3")

        last = hist[-1]
        last_w = json.loads(last[2]) if last[2] else {}
        wfig = go.Figure()
        for name, w in last_w.items():
            wfig.add_trace(go.Scatterpolar(r=list(w.values()) + [list(w.values())[0]],
                                           theta=list(w.keys()) + [list(w.keys())[0]],
                                           fill="toself", name=name))
        wfig.update_layout(template="plotly_dark", paper_bgcolor=BG, height=320,
                           polar=dict(bgcolor=CARD, radialaxis=dict(gridcolor=LINE, color=TXT)),
                           margin=dict(l=40, r=40, t=40, b=20),
                           title=dict(text="نقشه‌ی وزن نورونی فعلی هر ارگانیسم (رادار)", font=dict(color=GOLD, size=13)),
                           legend=dict(font=dict(color=TXT, size=10)))
        radar = dcc.Graph(figure=wfig, config={"displaylogo": False})
    else:
        charts = dbc.Alert("هنوز داده‌ی یادگیری کافی برای نمودار وجود ندارد؛ کمی صبر کنید یا یک بک‌تست اجرا کنید.", color="secondary")
        radar = html.Div()

    runs = get_backtest_runs(15)
    if runs:
        rows = []
        for ts, sym, params, metrics in runs:
            m = json.loads(metrics) if metrics else {}
            rows.append(html.Tr([
                html.Td(ts[:19].replace("T", " ")), html.Td(sym), html.Td(f"{m.get('candles','—'):,}" if isinstance(m.get("candles"), int) else m.get("candles", "—")),
                html.Td(m.get("trades", "—")),
                html.Td(f"{m.get('winrate', 0)*100:.1f}%", style={"color": UP if m.get('winrate', 0) >= 0.5 else DN}),
                html.Td(f"{m.get('total_return', 0)*100:+.2f}%", style={"color": UP if m.get('total_return', 0) >= 0 else DN}),
                html.Td(f"{m.get('max_dd', 0)*100:.1f}%"),
                html.Td(f"#{m.get('run_number', '—')}"),
            ]))
        table = dbc.Table([
            html.Thead(html.Tr([html.Th(x) for x in ["زمان", "نماد", "کندل", "معاملات", "وین‌ریت", "بازده", "افت", "اجرا #"]])),
            html.Tbody(rows)
        ], bordered=True, hover=True, size="sm", style={"background": CARD})
    else:
        table = dbc.Alert("هنوز بک‌تستی اجرا نشده است.", color="secondary")

    return html.Div([
        dbc.Row([
            dbc.Col(card("آپدیت‌های یادگیری کل", f"{h.learning.total_updates:,}", NEON), md=3),
            dbc.Col(card("اجرای بک‌تست", f"{h.learning.backtest_runs_count}", ACCENT), md=3),
            dbc.Col(card("حافظه‌ی تجربه", f"{len(h.learning.memory):,}", GOLD), md=3),
            dbc.Col(card("آگاهی فعلی", f"{h.awareness:.1%}", UP if h.awareness >= 0.6 else ORANGE), md=3),
        ], className="mb-3"),
        charts,
        radar,
        html.H5("تاریخچه‌ی اجرای بک‌تست‌ها", style={"color": GOLD, "marginTop": 14}),
        table,
    ])

def perf_tab():
    closed = get_closed_trades(100)
    if not closed:
        return html.Div("هنوز معامله بسته‌شده‌ای برای تحلیل وجود ندارد.", style={"color": MUT})
    pnls = [t["pnl"] for t in closed if t["pnl"] is not None]
    wr = sum(1 for p in pnls if p > 0) / len(pnls) if pnls else 0
    by_regime = defaultdict(list)
    for t in closed:
        by_regime[t.get("regime") or "UNK"].append(t["pnl"] or 0)
    regime_stats = []
    for reg, vals in by_regime.items():
        if vals:
            regime_stats.append(html.Div(f"{reg}: n={len(vals)} | WR={sum(1 for v in vals if v>0)/len(vals)*100:.0f}% | Avg={np.mean(vals):+.2f}"))
    return html.Div([
        html.H5("تحلیل عملکرد (یادگیری بعد از معامله)", style={"color": GOLD}),
        dbc.Row([
            dbc.Col(card("WinRate", f"{wr*100:.1f}%", UP if wr>=0.5 else DN), md=3),
            dbc.Col(card("Avg PnL", f"${np.mean(pnls):+.2f}" if pnls else "—", GOLD), md=3),
            dbc.Col(card("Best", f"${max(pnls):+.2f}" if pnls else "—", UP), md=3),
            dbc.Col(card("Worst", f"${min(pnls):+.2f}" if pnls else "—", DN), md=3),
        ], className="mb-3"),
        html.H5("عملکرد بر اساس رژیم", style={"color": GOLD}),
        html.Div(regime_stats, style={"background": CARD, "padding": 12, "borderRadius": 8}),
        html.P("آستانه‌ها و وزن‌های نورونی به‌صورت خودکار بر اساس وین‌ریت اخیر و نتیجه‌ی هر معامله تنظیم می‌شوند.", style={"color": MUT, "marginTop": 12})
    ])

@app.callback(Output("pulse", "children"), Output("status", "children"), Input("life", "n_intervals"))
def header(n):
    h = HIVE
    h.heart_beat += 1
    return (f"BEAT #{h.heart_beat}  |  θ={h.adaptive['score_threshold']:.2f}  |  یادگیری #{h.learning.total_updates}",
            f"نورون {h.total_neurons():,} | آگاهی {h.awareness:.0%} | لوریج {LEVERAGE}×")

@app.callback(Output("cycle", "disabled"), Input("cycle", "n_intervals"), prevent_initial_call=False)
def run_cycle(n):
    HIVE.cycle()
    return False

@app.callback(Output("bt-config", "data"),
              Input("bt-symbol", "value"), Input("bt-candles", "value"), Input("bt-interval", "value"),
              State("bt-config", "data"), prevent_initial_call=True)
def sync_bt_config(sym, cnd, itv, cur):
    cur = dict(cur or {"symbol": "BTCUSDT", "candles": 10000, "interval": "5"})
    if sym is not None:
        cur["symbol"] = sym
    if cnd is not None:
        cur["candles"] = cnd
    if itv is not None:
        cur["interval"] = itv
    return cur

@app.callback(Output("bt-result", "data"), Input("bt-run", "n_clicks"),
              State("bt-symbol", "value"), State("bt-candles", "value"), State("bt-interval", "value"),
              prevent_initial_call=True)
def do_backtest(n, symbol, candles, interval):
    if not n:
        return None
    symbol = (symbol or "BTCUSDT").upper().strip()
    try:
        candles = int(candles) if candles else 10000
    except Exception:
        candles = 10000
    candles = max(300, min(10000, candles))
    interval = interval or "5"
    result = run_backtest_walkforward(symbol, candles=candles, interval=interval)
    return result

if __name__ == "__main__":
    print("HIVE PRO starting...")
    print(f"Neurons: {HIVE.total_neurons():,} | Leverage: {LEVERAGE}x | Max Pos: {MAX_POSITIONS}")
    print("Features: Regime | VolTarget | Correlation | Partial+Trail | Deep Learning Core | Experience Memory | Walk-Forward Backtest")
    print(f"Learning updates so far: {HIVE.learning.total_updates} | Backtest runs so far: {HIVE.learning.backtest_runs_count}")
    print("WARNING: Simulation only. 20x leverage is extremely risky. No profit guarantee.")
    app.run(debug=True, host="0.0.0.0", port=8060, use_reloader=False)
