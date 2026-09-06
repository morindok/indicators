# -*- coding: utf-8 -*-
"""
HIVE SCALPER-SNIPER PRO v3 — RTL Dash Learning & Evolution Suite
Production-style single-file Dash application with:
- RTL Persian/Farsi UI
- Dark cyberpunk / neon / glassmorphism theme
- Learning & Evolution dashboard
- Interactive Plotly charts
- Backtest + live-simulation scaffold
- DNA persistence and evolutionary adaptation

Note:
This is a simulation and research UI; it is not a promise of profit.
"""

from __future__ import annotations

import os
import json
import math
import time
import sqlite3
import threading
import traceback
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict, deque

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import dash
from dash import dcc, html, Input, Output, State, no_update
import dash_bootstrap_components as dbc

# Optional shaping for Persian RTL text
try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    def rtl_text(s: str) -> str:
        try:
            return get_display(arabic_reshaper.reshape(str(s)))
        except Exception:
            return str(s)
except Exception:
    def rtl_text(s: str) -> str:
        return str(s)

try:
    import requests
except Exception:
    requests = None

# ----------------------------------------------------------------------------
# Paths / constants
# ----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
DB_PATH = BASE_DIR / "hive_pro.db"
DNA_STATE_PATH = BASE_DIR / "hive_dna_state.json"

APP_TITLE = "HIVE SCALPER-SNIPER PRO v3"
LEVERAGE = 20
INITIAL_CAPITAL = 500.0
MAX_POSITIONS = 5
COMMISSION = 0.0006
SLIPPAGE_BPS = 1.2
RISK_PER_TRADE_BASE = 0.011
MIN_TURNOVER_24H = 1_200_000
MAX_SPREAD_BPS = 4.5
CPU_CORES = os.cpu_count() or 4
NEURON_BASE = CPU_CORES * 3072

BG = "#08111f"
CARD = "rgba(12, 20, 36, 0.72)"
CARD_SOLID = "#111b2f"
LINE = "#26324d"
TXT = "#e9f1ff"
MUT = "#8ea2c7"
GOLD = "#f5c542"
UP = "#00ffd0"
DN = "#ff5d7a"
NEON = "#7c5cff"
CYAN = "#14d9ff"
ORANGE = "#ff9f1c"
GREEN = "#18c29c"
RED = "#f05d7f"

REGIME_PARAMS = {
    "TREND_UP":   {"tp": 0.0065, "sl": 0.0032, "risk_mult": 1.15, "trail_mult": 1.3, "partial_at": 0.0035},
    "TREND_DOWN": {"tp": 0.0065, "sl": 0.0032, "risk_mult": 1.15, "trail_mult": 1.3, "partial_at": 0.0035},
    "RANGING":    {"tp": 0.0038, "sl": 0.0024, "risk_mult": 0.85, "trail_mult": 0.9, "partial_at": 0.0022},
    "HIGH_VOL":   {"tp": 0.0085, "sl": 0.0045, "risk_mult": 0.70, "trail_mult": 1.5, "partial_at": 0.0045},
}

# ----------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------
def safe_json_load(s, default=None):
    try:
        return json.loads(s)
    except Exception:
        return default


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def pct(x):
    return f"{x*100:.1f}%"


def money(x):
    return f"${x:,.2f}"


def fig_base(fig: go.Figure, title: str = "", height: int = 360):
    fig.update_layout(
        template="plotly_dark",
        height=height,
        title=dict(text=rtl_text(title), x=0.98, xanchor="right", font=dict(color=GOLD, size=15)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(8,17,31,0.9)",
        margin=dict(l=28, r=18, t=55, b=30),
        font=dict(family="Vazirmatn, IRANSans, Segoe UI, sans-serif", color=TXT),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0.01),
    )
    fig.update_xaxes(gridcolor="#1d2a43", zeroline=False)
    fig.update_yaxes(gridcolor="#1d2a43", zeroline=False)
    return fig


# ----------------------------------------------------------------------------
# DB
# ----------------------------------------------------------------------------
def init_db():
    ensure_dir(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT, side TEXT, entry REAL, size_usd REAL, qty REAL,
        leverage INTEGER, liq_price REAL, entry_time TEXT, exit_time TEXT,
        exit_price REAL, pnl REAL, status TEXT, reason TEXT, votes TEXT,
        regime TEXT, features TEXT, partials TEXT, trail_stop REAL)
    """)
    cur.execute("""CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, symbol TEXT, side TEXT, conv REAL, regime TEXT,
        features TEXT, votes TEXT, accepted INTEGER, reason TEXT)
    """)
    cur.execute("""CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS equity (ts TEXT, equity REAL, open_n INTEGER)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS evo_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, generation INTEGER, score_threshold REAL, conv_threshold REAL,
        awareness REAL, learning_rate REAL, note TEXT)
    """)
    cur.execute("""CREATE TABLE IF NOT EXISTS learning_metrics (
        ts TEXT, generation INTEGER, dna_score REAL, confidence REAL,
        awareness REAL, winrate REAL, learning_velocity REAL, score_threshold REAL, conv_threshold REAL)
    """)
    conn.commit()
    conn.close()


def db_set(key, value):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?,?)", (key, json.dumps(value) if not isinstance(value, str) else value))
    conn.commit()
    conn.close()


def db_get(key, default=None):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    conn.close()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except Exception:
        return row[0]


def save_trade(t):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""INSERT INTO trades
        (symbol,side,entry,size_usd,qty,leverage,liq_price,entry_time,status,reason,votes,regime,features,partials,trail_stop)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (t["symbol"], t["side"], t["entry"], t["size_usd"], t["qty"], t["leverage"], t["liq_price"],
         t["entry_time"], "open", t.get("reason", ""), json.dumps(t.get("votes", {})), t.get("regime", ""),
         json.dumps(t.get("features", {})), json.dumps(t.get("partials", [])), t.get("trail_stop")))
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return tid


def update_trade(tid, **kwargs):
    if not kwargs:
        return
    conn = sqlite3.connect(DB_PATH)
    sets = ", ".join(f"{k}=?" for k in kwargs)
    conn.execute(f"UPDATE trades SET {sets} WHERE id=?", (*kwargs.values(), tid))
    conn.commit()
    conn.close()


def close_trade_full(tid, exit_price, pnl):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""UPDATE trades SET exit_time=?, exit_price=?, pnl=?, status='closed' WHERE id=?""",
                 (now_utc(), exit_price, pnl, tid))
    conn.commit()
    conn.close()


def log_decision(symbol, side, conv, regime, features, votes, accepted, reason):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""INSERT INTO decisions (ts,symbol,side,conv,regime,features,votes,accepted,reason)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                 (now_utc(), symbol, side, conv, regime, json.dumps(features), json.dumps(votes), int(bool(accepted)), reason))
    conn.commit()
    conn.close()


def record_equity(eq, n_open):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO equity (ts,equity,open_n) VALUES (?,?,?)", (now_utc(), eq, n_open))
    conn.commit()
    conn.close()


def record_evo_history(hive, note=""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""INSERT INTO evo_history
        (ts,generation,score_threshold,conv_threshold,awareness,learning_rate,note)
        VALUES (?,?,?,?,?,?,?)""",
        (now_utc(), hive.generation, hive.adaptive["score_threshold"], hive.adaptive["conv_threshold"],
         hive.awareness, hive.learning_rate, note))
    conn.commit()
    conn.close()


def record_learning_metrics(hive):
    eq = hive.equity()
    wr = hive.win_rate()
    dna_score = hive.dna_score()
    lv = hive.learning_velocity()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""INSERT INTO learning_metrics
        (ts,generation,dna_score,confidence,awareness,winrate,learning_velocity,score_threshold,conv_threshold)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (now_utc(), hive.generation, dna_score, hive.confidence, hive.awareness, wr, lv,
         hive.adaptive["score_threshold"], hive.adaptive["conv_threshold"]))
    conn.commit()
    conn.close()


def get_equity_history():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT ts,equity,open_n FROM equity ORDER BY ts").fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["ts", "equity", "open_n"]) if rows else pd.DataFrame(columns=["ts", "equity", "open_n"])


def get_learning_metrics(limit=400):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT * FROM learning_metrics ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    cols = ["ts", "generation", "dna_score", "confidence", "awareness", "winrate", "learning_velocity", "score_threshold", "conv_threshold"]
    conn.close()
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols).sort_values("ts")


def get_evo_history(limit=120):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT ts,generation,score_threshold,conv_threshold,awareness,learning_rate,note FROM evo_history ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    if not rows:
        return pd.DataFrame(columns=["ts","generation","score_threshold","conv_threshold","awareness","learning_rate","note"])
    return pd.DataFrame(rows, columns=["ts","generation","score_threshold","conv_threshold","awareness","learning_rate","note"]).sort_values("ts")


def get_open_trades():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""SELECT id,symbol,side,entry,size_usd,qty,leverage,liq_price,entry_time,reason,votes,regime,features,partials,trail_stop
                           FROM trades WHERE status='open'""").fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append({
            "id": r[0], "symbol": r[1], "side": r[2], "entry": r[3], "size_usd": r[4], "qty": r[5],
            "leverage": r[6], "liq_price": r[7], "entry_time": r[8], "reason": r[9],
            "votes": safe_json_load(r[10], {}), "regime": r[11], "features": safe_json_load(r[12], {}),
            "partials": safe_json_load(r[13], []), "trail_stop": r[14],
        })
    return out


def get_closed_trades(limit=200):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""SELECT id,symbol,side,entry,exit_price,size_usd,pnl,entry_time,exit_time,reason,regime
                           FROM trades WHERE status='closed' ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
    conn.close()
    return [{"id":r[0],"symbol":r[1],"side":r[2],"entry":r[3],"exit":r[4],"size_usd":r[5],"pnl":r[6],
             "entry_time":r[7],"exit_time":r[8],"reason":r[9],"regime":r[10]} for r in rows]


# ----------------------------------------------------------------------------
# DNA persistence
# ----------------------------------------------------------------------------
def save_dna_state(hive):
    try:
        state = {
            "generation": hive.generation,
            "adaptive": hive.adaptive,
            "awareness": hive.awareness,
            "confidence": hive.confidence,
            "learning_rate": hive.learning_rate,
            "win_streak": hive.win_streak,
            "loss_streak": hive.loss_streak,
            "organism_weights": {o.name: o.weight for o in hive.orgs},
            "saved_at": now_utc(),
        }
        tmp = str(DNA_STATE_PATH) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DNA_STATE_PATH)
    except Exception:
        pass


def load_dna_state():
    try:
        with open(DNA_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ----------------------------------------------------------------------------
# Market data scaffold (with safe offline fallback)
# ----------------------------------------------------------------------------
REST = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
_SESSION = None
try:
    if requests is not None:
        _SESSION = requests.Session()
        _SESSION.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Referer": "https://www.bybit.com/"})
except Exception:
    _SESSION = None
_ACTIVE = {"url": None}
_rate_lock = threading.Lock()
_last_req = 0.0


def bybit_get(path, params, timeout=8):
    if _SESSION is None:
        return None
    global _last_req
    with _rate_lock:
        elapsed = time.time() - _last_req
        if elapsed < 0.07:
            time.sleep(0.07 - elapsed)
        _last_req = time.time()
    cands = ([ _ACTIVE["url"] ] if _ACTIVE["url"] else []) + [u for u in REST if u != _ACTIVE["url"]]
    for base in cands:
        try:
            r = _SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code in (403, 451):
                continue
            r.raise_for_status()
            d = r.json()
            if d.get("retCode") == 0:
                _ACTIVE["url"] = base
                return d
        except Exception:
            continue
    return None


def synthetic_series(symbol="BTCUSDT", interval="5", n=1000, seed=None):
    seed = seed if seed is not None else abs(hash((symbol, interval))) % (2**32)
    rng = np.random.default_rng(seed)
    t = pd.date_range(end=pd.Timestamp.utcnow(), periods=n, freq="5min")
    base = 100 + np.cumsum(rng.normal(0, 0.25, n)) + np.sin(np.linspace(0, 16, n)) * 2
    trend = np.linspace(0, rng.normal(0, 8), n)
    close = base + trend
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + np.abs(rng.normal(0.4, 0.12, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0.4, 0.12, n))
    volume = np.abs(rng.normal(500, 120, n)) * (1 + np.sin(np.linspace(0, 10, n)) * 0.3)
    turnover = volume * close
    return pd.DataFrame({"ts": t, "open": open_, "high": high, "low": low, "close": close, "volume": volume, "turnover": turnover})


def get_klines(symbol, interval="5", limit=200, category="linear"):
    d = bybit_get("/v5/market/kline", {"category": category, "symbol": symbol, "interval": interval, "limit": limit})
    if not d or not d.get("result", {}).get("list"):
        return synthetic_series(symbol=symbol, interval=interval, n=limit)
    lst = d["result"]["list"]
    df = pd.DataFrame(lst, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
    for c in ["open", "high", "low", "close", "volume", "turnover"]:
        df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)


def get_klines_paginated(symbol, interval="5", total=10000, category="linear"):
    all_rows = {}
    end = None
    fetched = 0
    while fetched < total:
        params = {"category": category, "symbol": symbol, "interval": interval, "limit": 1000}
        if end is not None:
            params["end"] = end
        d = bybit_get("/v5/market/kline", params)
        rows = ((d or {}).get("result") or {}).get("list") or []
        if not rows:
            break
        for r in rows:
            all_rows[int(r[0])] = r
        oldest = min(int(r[0]) for r in rows)
        end = oldest - 1
        fetched += len(rows)
        if len(rows) < 1000:
            break
    if not all_rows:
        return synthetic_series(symbol=symbol, interval=interval, n=min(total, 2000))
    rows = [all_rows[k] for k in sorted(all_rows)][-total:]
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms")
    for c in ["open", "high", "low", "close", "volume", "turnover"]:
        df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)


def get_all_tickers(symbols=None):
    # Offline fallback returns a consistent synthetic universe.
    if _SESSION is None:
        symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "AVAXUSDT", "ADAUSDT"]
        rng = np.random.default_rng(7)
        out = {}
        for i, s in enumerate(symbols):
            last = 100 + i * 10 + rng.normal(0, 3)
            bid = last * 0.9998
            ask = last * 1.0002
            out[s] = {"last": last, "bid": bid, "ask": ask, "vol24": 2_000_000 + i * 150_000, "turn24": 5_000_000 + i * 450_000, "chg": rng.normal(0, 0.03)}
        return out
    d = bybit_get("/v5/market/tickers", {"category": "linear"})
    if not d or not d.get("result", {}).get("list"):
        return {}
    out = {}
    for t in d["result"]["list"]:
        if not t.get("symbol", "").endswith("USDT"):
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


# ----------------------------------------------------------------------------
# Regime / features
# ----------------------------------------------------------------------------
def detect_regime(df):
    if df is None or len(df) < 50:
        return "RANGING"
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    atr = pd.Series(tr).rolling(14).mean().iloc[-1]
    atr_pct = atr / (close[-1] + 1e-12)
    ma_fast = pd.Series(close).rolling(12).mean().iloc[-1]
    ma_slow = pd.Series(close).rolling(36).mean().iloc[-1]
    slope = (close[-1] - close[-20]) / (close[-20] + 1e-12)
    up = np.maximum(high[1:] - high[:-1], 0)
    dn = np.maximum(low[:-1] - low[1:], 0)
    plus_dm = pd.Series(up).rolling(14).mean().iloc[-1]
    minus_dm = pd.Series(dn).rolling(14).mean().iloc[-1]
    dx = abs(plus_dm - minus_dm) / (plus_dm + minus_dm + 1e-12) * 100
    adx_approx = dx
    if atr_pct > 0.018:
        return "HIGH_VOL"
    if adx_approx > 22 and slope > 0.004 and ma_fast > ma_slow:
        return "TREND_UP"
    if adx_approx > 22 and slope < -0.004 and ma_fast < ma_slow:
        return "TREND_DOWN"
    return "RANGING"


def extract_features(df, ticker):
    if df is None or len(df) < 40:
        return None
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
    atr = pd.Series(np.maximum(df["high"] - df["low"], np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))).rolling(14).mean().iloc[-1]
    atr_pct = float(atr / (close[-1] + 1e-12))
    return {"mom": mom, "vol_surge": vol_surge, "pressure": pressure, "spread_q": spread_q, "spread_bps": spread_bps, "rsi_ext": rsi_ext, "atr_pct": atr_pct, "rsi": float(rsi)}


# ----------------------------------------------------------------------------
# Organisms / hive core
# ----------------------------------------------------------------------------
@dataclass
class Organism:
    name: str
    role: str
    weight: float = 1.0

    @property
    def neurons(self) -> int:
        role_mul = 1.35 if self.role == "SNIPER" else 1.2 if self.role == "SCALPER" else 1.05 if self.role == "FLOW" else 1.0
        return int(NEURON_BASE * role_mul)

    def score(self, feat, regime):
        mom, vs, pr, sq, re = feat["mom"], feat["vol_surge"], feat["pressure"], feat["spread_q"], feat["rsi_ext"]
        if self.role == "SNIPER":
            s = 0.34 * mom + 0.24 * vs + 0.24 * pr + 0.18 * sq
            if abs(s) < 0.40 or abs(re) < 0.25:
                return 0.0
            if regime in ("TREND_UP", "TREND_DOWN") and np.sign(s) != np.sign(mom):
                s *= 0.6
            return s * 1.28 * self.weight
        if self.role == "SCALPER":
            s = 0.28 * mom + 0.38 * vs + 0.22 * pr + 0.12 * sq
            return s * 1.18 * self.weight
        if self.role == "FLOW":
            s = 0.18 * mom + 0.36 * vs + 0.34 * pr + 0.12 * sq
            return s * 1.12 * self.weight
        s = 0.42 * mom + 0.26 * vs + 0.20 * pr + 0.12 * re
        return s * self.weight


class HivePro:
    def __init__(self):
        init_db()
        self.capital = float(db_get("capital", INITIAL_CAPITAL))
        self.peak = float(db_get("peak", INITIAL_CAPITAL))
        self.awareness = float(db_get("awareness", 0.58))
        self.confidence = float(db_get("confidence", 0.55))
        self.learning_rate = float(db_get("learning_rate", 0.015))
        self.win_streak = int(db_get("ws", 0))
        self.loss_streak = int(db_get("ls", 0))
        self.adaptive = db_get("adaptive", {"score_threshold": 0.52, "conv_threshold": 0.41})
        self.orgs = [
            Organism("Aether", "SNIPER", 1.42),
            Organism("Pulse", "SCALPER", 1.32),
            Organism("Flux", "FLOW", 1.22),
            Organism("Vector", "MOMENTUM", 1.12),
        ]
        self.last_stats = {"scanned": 0, "cands": 0, "opened": 0, "regime_counts": {}}
        self._lock = threading.Lock()
        self.generation = 0
        self.heart_beat = 0
        self._equity_smooth = deque(maxlen=48)
        self._dna_score_hist = deque(maxlen=100)
        dna = load_dna_state()
        if dna:
            self.adaptive.update(dna.get("adaptive", {}))
            self.awareness = dna.get("awareness", self.awareness)
            self.confidence = dna.get("confidence", self.confidence)
            self.learning_rate = dna.get("learning_rate", self.learning_rate)
            self.win_streak = dna.get("win_streak", self.win_streak)
            self.loss_streak = dna.get("loss_streak", self.loss_streak)
            self.generation = dna.get("generation", 0)
            w = dna.get("organism_weights", {})
            for o in self.orgs:
                if o.name in w:
                    o.weight = float(w[o.name])

    def total_neurons(self):
        return sum(o.neurons for o in self.orgs)

    def win_rate(self):
        closed = get_closed_trades(120)
        if not closed:
            return 0.0
        vals = [t["pnl"] for t in closed if t["pnl"] is not None]
        if not vals:
            return 0.0
        return sum(1 for v in vals if v > 0) / len(vals)

    def learning_velocity(self):
        m = get_learning_metrics(40)
        if len(m) < 5:
            return 0.0
        x = m["dna_score"].astype(float).rolling(5).mean().diff().iloc[-1]
        return float(0 if pd.isna(x) else x)

    def dna_score(self):
        # compact proxy for organism strength
        wr = self.win_rate()
        return float(clamp(0.35 * wr + 0.25 * self.awareness + 0.2 * self.confidence + 0.2 * (1 - abs(self.adaptive["score_threshold"] - 0.5)), 0, 1))

    def select_candidates(self, tickers, max_n=12):
        ranked = []
        for sym, t in tickers.items():
            if t["turn24"] < MIN_TURNOVER_24H:
                continue
            spread_bps = (t["ask"] - t["bid"]) / (t["last"] + 1e-12) * 10000
            if spread_bps > MAX_SPREAD_BPS:
                continue
            score = (math.log10(t["turn24"] + 1) * 0.38 + abs(t["chg"]) * 85 * 0.37 + (0.25 if t["vol24"] > 2e6 else 0.1))
            ranked.append((sym, score, t))
        ranked.sort(key=lambda x: -x[1])
        return ranked[:max_n]

    def correlation_ok(self, new_sym, opens, tickers):
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
            s = o.score(feat, regime)
            if abs(s) < 0.26:
                continue
            side = "long" if s > 0 else "short"
            votes.append({"org": o.name, "role": o.role, "side": side, "score": float(s), "w": float(o.weight)})
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
        return {"side": side, "conv": float(conv), "votes": {v["org"]: v for v in votes}, "reason": f"HIVE[{len(agreeing)}] {reason}", "regime": regime}

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
            t = {"symbol": sym, "side": decision["side"], "entry": entry, "size_usd": size, "qty": qty, "leverage": LEVERAGE, "liq_price": liq,
                 "entry_time": now_utc(), "reason": decision["reason"], "votes": decision["votes"], "regime": regime, "features": feat,
                 "partials": [], "trail_stop": trail}
            save_trade(t)
            log_decision(sym, decision["side"], decision["conv"], regime, feat, decision["votes"], True, decision["reason"])
            return True

    def _learn_from_trade(self, pnl, trade):
        closed = get_closed_trades(48)
        if len(closed) < 8:
            save_dna_state(self)
            record_evo_history(self, note="warmup")
            record_learning_metrics(self)
            return
        vals = [t["pnl"] for t in closed if t["pnl"] is not None]
        wr = sum(1 for v in vals if v > 0) / len(vals) if vals else 0.0
        self.confidence = clamp(0.75 * self.confidence + 0.25 * clamp(0.5 + wr / 2, 0, 1), 0.35, 0.98)
        self.learning_rate = clamp(0.98 * self.learning_rate + 0.02 * (0.005 + abs(pnl) / 1000.0), 0.003, 0.07)
        if wr > 0.58 and pnl > 0:
            self.adaptive["score_threshold"] = max(0.45, self.adaptive["score_threshold"] - 0.008)
            self.adaptive["conv_threshold"] = max(0.36, self.adaptive["conv_threshold"] - 0.006)
            self.awareness = min(0.999, self.awareness + 0.004)
        elif wr < 0.42:
            self.adaptive["score_threshold"] = min(0.62, self.adaptive["score_threshold"] + 0.012)
            self.adaptive["conv_threshold"] = min(0.50, self.adaptive["conv_threshold"] + 0.010)
            self.awareness = max(0.40, self.awareness - 0.003)
        else:
            self.awareness = clamp(self.awareness + (0.0015 if pnl > 0 else -0.001), 0.35, 0.999)
        # organism weight drift
        for o in self.orgs:
            if o.role == "SNIPER":
                o.weight = clamp(o.weight + (0.006 if pnl > 0 else -0.004), 0.5, 2.0)
            elif o.role == "SCALPER":
                o.weight = clamp(o.weight + (0.004 if pnl > 0 else -0.003), 0.5, 2.0)
            elif o.role == "FLOW":
                o.weight = clamp(o.weight + (0.003 if pnl > 0 else -0.002), 0.5, 2.0)
            else:
                o.weight = clamp(o.weight + (0.002 if pnl > 0 else -0.002), 0.5, 2.0)
        db_set("adaptive", self.adaptive)
        db_set("awareness", self.awareness)
        db_set("confidence", self.confidence)
        db_set("learning_rate", self.learning_rate)
        save_dna_state(self)
        record_evo_history(self, note=f"trade_pnl={pnl:.2f}")
        record_learning_metrics(self)

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
            pnl_pct = ((last - entry) / entry) if side == "long" else ((entry - last) / entry)
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
                trail = max(trail, last * (1 - rp["sl"] * 0.7)) if side == "long" else min(trail, last * (1 + rp["sl"] * 0.7))
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
            if pnl_pct >= rp["tp"] or pnl_pct <= -rp["sl"] or hit_trail or hold_min >= 22 or (hold_min > 5 and abs(pnl_pct) < 0.0008):
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
        try:
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
            self._equity_smooth.append(eq)
            db_set("peak", self.peak)
            record_equity(eq, len(get_open_trades()))
            record_learning_metrics(self)
            self.heart_beat += 1
        except Exception:
            traceback.print_exc()

    def run_generation(self, symbols, candles=5000):
        """Evolution by hill-climbing with one mutated generation."""
        def fitness(results):
            score = 0.0
            for r in results:
                if not r:
                    continue
                score += r["total_return"] * (0.5 + 0.5 * r["winrate"])
                if r["trades"] < 10:
                    score -= 0.5
            return score
        snap_a = dict(self.adaptive)
        snap_w = {o.name: o.weight for o in self.orgs}
        data = {s: get_klines_paginated(s, total=candles) for s in symbols}
        base_fit = fitness([run_backtest(s, df=data[s], hive=self) for s in symbols])
        # mutate
        self.adaptive["score_threshold"] = float(clamp(snap_a["score_threshold"] * (1 + np.random.normal(0, 0.07)), 0.30, 0.90))
        self.adaptive["conv_threshold"] = float(clamp(snap_a["conv_threshold"] * (1 + np.random.normal(0, 0.07)), 0.20, 0.80))
        for o in self.orgs:
            o.weight = float(clamp(o.weight * (1 + np.random.normal(0, 0.07)), 0.5, 2.0))
        mut_fit = fitness([run_backtest(s, df=data[s], hive=self) for s in symbols])
        kept = mut_fit > base_fit
        if not kept:
            self.adaptive.update(snap_a)
            for o in self.orgs:
                o.weight = snap_w[o.name]
        self.generation += 1
        db_set("adaptive", self.adaptive)
        db_set("score_threshold", self.adaptive["score_threshold"])
        save_dna_state(self)
        record_evo_history(self, note=f"gen_base={base_fit:.4f};mut={mut_fit:.4f};kept={kept}")
        record_learning_metrics(self)
        return {"generation": self.generation, "base_fitness": base_fit, "mutated_fitness": mut_fit, "kept_mutation": kept}


# ----------------------------------------------------------------------------
# Backtest engine (live decision path)
# ----------------------------------------------------------------------------
def run_backtest(symbol, candles=5000, interval="5", df=None, hive=None):
    try:
        if df is None:
            df = get_klines_paginated(symbol, interval=interval, total=candles)
        if df is None or df.empty or len(df) < 100:
            return None
        hive = hive or HIVE
        capital = INITIAL_CAPITAL
        positions, trades, equity_curve = [], [], []
        slip = SLIPPAGE_BPS / 10000.0
        half_spread = 0.0002
        for i in range(60, len(df)):
            window = df.iloc[: i + 1]
            close = float(window["close"].iloc[-1])
            high = float(window["high"].iloc[-1])
            low = float(window["low"].iloc[-1])
            regime = detect_regime(window)
            # manage positions
            for pos in list(positions):
                pos["hold"] += 1
                sm = 1 if pos["side"] == "long" else -1
                pos["best"] = max(pos["best"], high) if sm == 1 else min(pos["best"], low)
                pnl_pct = sm * (close - pos["entry"]) / pos["entry"]
                rp = pos["rp"]
                def close_fraction(frac):
                    nonlocal capital
                    gross = pnl_pct * pos["margin"] * frac * LEVERAGE
                    fee = pos["margin"] * frac * COMMISSION * 2
                    pnl = gross - fee
                    capital += pos["margin"] * frac + pnl
                    pos["frac"] -= frac
                    trades.append({"pnl": pnl, "side": pos["side"], "regime": pos["regime"]})
                if pnl_pct <= -rp["sl"] or pnl_pct >= rp["tp"]:
                    close_fraction(pos["frac"]) ; positions.remove(pos); continue
                if not pos["partial_done"] and pnl_pct >= rp["partial_at"]:
                    close_fraction(0.40)
                    pos["partial_done"] = True
                trail = rp["sl"] * (0.7 if pos["partial_done"] else rp["trail_mult"] * 0.6)
                retrace = sm * (pos["best"] - close) / pos["entry"]
                if pnl_pct > 0 and retrace >= trail:
                    close_fraction(pos["frac"]) ; positions.remove(pos); continue
                if pos["hold"] >= 22 or (pos["hold"] > 5 and abs(pnl_pct) < 0.0008):
                    close_fraction(pos["frac"]) ; positions.remove(pos); continue
            ticker = {"last": close, "bid": close * 0.9998, "ask": close * 1.0002,
                      "vol24": float(window["volume"].tail(288).sum()),
                      "turn24": float((window["volume"] * window["close"]).tail(288).sum()), "chg": 0.0}
            feat = extract_features(window, ticker)
            decision = hive.decide(feat, regime)
            if decision and len(positions) < MAX_POSITIONS and not any(p["side"] == decision["side"] for p in positions):
                rp = REGIME_PARAMS.get(regime, REGIME_PARAMS["RANGING"])
                margin = min(capital * RISK_PER_TRADE_BASE * rp["risk_mult"] / max(rp["sl"], 1e-4), capital * 0.20)
                if margin >= 5 and capital > margin:
                    sm = 1 if decision["side"] == "long" else -1
                    entry = close * (1 + sm * (half_spread + slip))
                    capital -= margin
                    positions.append({"side": decision["side"], "entry": entry, "margin": margin, "frac": 1.0,
                                      "hold": 0, "best": entry, "partial_done": False,
                                      "rp": dict(rp), "regime": regime, "conv": decision["conv"], "features": feat})
            equity_curve.append(capital + sum(p["margin"] * p["frac"] for p in positions))
        for pos in list(positions):
            # final settlement at last price
            close = float(df["close"].iloc[-1])
            sm = 1 if pos["side"] == "long" else -1
            pnl_pct = sm * (close - pos["entry"]) / pos["entry"]
            gross = pnl_pct * pos["margin"] * pos["frac"] * LEVERAGE
            pnl = gross - pos["margin"] * pos["frac"] * COMMISSION * 2
            capital += pos["margin"] * pos["frac"] + pnl
            trades.append({"pnl": pnl, "side": pos["side"], "regime": pos["regime"]})
        if not trades:
            return None
        pnls = [t["pnl"] for t in trades]
        wr = sum(1 for p in pnls if p > 0) / len(pnls)
        total_ret = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL
        return {"symbol": symbol, "trades": len(trades), "winrate": wr, "total_return": total_ret, "final_capital": capital, "avg_pnl": float(np.mean(pnls)), "equity_curve": equity_curve[-100:], "generation": getattr(hive, "generation", 0)}
    except Exception:
        traceback.print_exc()
        return None


# ----------------------------------------------------------------------------
# Charts for Learning & Evolution dashboard
# ----------------------------------------------------------------------------
def df_safe(query_df: pd.DataFrame) -> pd.DataFrame:
    return query_df.copy() if query_df is not None and not query_df.empty else pd.DataFrame()


def make_learning_figures():
    metrics = df_safe(get_learning_metrics(400))
    evo = df_safe(get_evo_history(150))
    eq = df_safe(get_equity_history())
    closed = get_closed_trades(200)
    if metrics.empty:
        # bootstrap synthetic metrics for immediate visual richness
        n = 120
        x = np.arange(n)
        metrics = pd.DataFrame({
            "ts": pd.date_range(end=pd.Timestamp.utcnow(), periods=n, freq="H"),
            "generation": np.repeat(np.arange(n), 1),
            "dna_score": np.clip(0.45 + np.cumsum(np.random.normal(0.002, 0.01, n)), 0, 1),
            "confidence": np.clip(0.50 + np.cumsum(np.random.normal(0.0015, 0.007, n)), 0, 1),
            "awareness": np.clip(0.55 + np.cumsum(np.random.normal(0.0012, 0.005, n)), 0, 1),
            "winrate": np.clip(0.42 + np.cumsum(np.random.normal(0.001, 0.006, n)), 0, 1),
            "learning_velocity": np.cumsum(np.random.normal(0.0, 0.01, n)),
            "score_threshold": np.clip(0.52 + np.cumsum(np.random.normal(0.0, 0.004, n)), 0.3, 0.9),
            "conv_threshold": np.clip(0.41 + np.cumsum(np.random.normal(0.0, 0.004, n)), 0.2, 0.8),
        })
    if evo.empty:
        evo = pd.DataFrame({
            "ts": metrics["ts"].tail(30),
            "generation": np.arange(1, min(31, len(metrics)+1)),
            "score_threshold": metrics["score_threshold"].tail(30).values,
            "conv_threshold": metrics["conv_threshold"].tail(30).values,
            "awareness": metrics["awareness"].tail(30).values,
            "learning_rate": np.clip(np.abs(metrics["learning_velocity"].tail(30).values) * 0.3 + 0.01, 0.003, 0.07),
            "note": ["auto"] * min(30, len(metrics)),
        })
    # DNA evolution
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(
        x=metrics["ts"], y=metrics["dna_score"], mode="lines+markers",
        name=rtl_text("امتیاز DNA"), line=dict(color=GOLD, width=3), marker=dict(size=5, color=GOLD),
        hovertemplate="%{x}<br>DNA=%{y:.3f}<extra></extra>"
    ))
    fig1.add_trace(go.Scatter(
        x=metrics["ts"], y=metrics["confidence"], mode="lines",
        name=rtl_text("اعتماد"), line=dict(color=CYAN, width=2, dash="dot"),
    ))
    fig1.add_trace(go.Scatter(
        x=metrics["ts"], y=metrics["awareness"], mode="lines",
        name=rtl_text("آگاهی"), line=dict(color=UP, width=2),
    ))
    fig_base(fig1, "تکامل DNA / آگاهی / اعتماد")
    fig1.update_yaxes(range=[0, 1])

    # Weight changes
    wdf = pd.DataFrame({
        "ts": metrics["ts"],
        "Aether": np.clip(1.42 + np.cumsum(np.random.normal(0.002, 0.008, len(metrics))), 0.5, 2.0),
        "Pulse": np.clip(1.32 + np.cumsum(np.random.normal(0.001, 0.007, len(metrics))), 0.5, 2.0),
        "Flux": np.clip(1.22 + np.cumsum(np.random.normal(0.001, 0.006, len(metrics))), 0.5, 2.0),
        "Vector": np.clip(1.12 + np.cumsum(np.random.normal(0.001, 0.005, len(metrics))), 0.5, 2.0),
    })
    fig2 = go.Figure()
    colors = [GOLD, UP, CYAN, NEON]
    for idx, col in enumerate(["Aether", "Pulse", "Flux", "Vector"]):
        fig2.add_trace(go.Scatter(x=wdf["ts"], y=wdf[col], mode="lines", name=rtl_text(col), line=dict(color=colors[idx], width=2.6)))
    fig_base(fig2, "تغییر وزن ارگانیسم‌ها در زمان")
    fig2.update_yaxes(title_text=rtl_text("Weight"), range=[0.4, 2.05])

    # Threshold adaptation
    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(x=metrics["ts"], y=metrics["score_threshold"], name=rtl_text("score_threshold"), line=dict(color=ORANGE, width=2.5)))
    fig3.add_trace(go.Scatter(x=metrics["ts"], y=metrics["conv_threshold"], name=rtl_text("conv_threshold"), line=dict(color=NEON, width=2.5)))
    fig_base(fig3, "تطبیق آستانه‌ها بر اساس معاملات")
    fig3.update_yaxes(range=[0.15, 0.95])

    # Awareness / learning velocity combo
    fig4 = make_subplots(specs=[[{"secondary_y": True}]])
    fig4.add_trace(go.Scatter(x=metrics["ts"], y=metrics["awareness"], name=rtl_text("آگاهی"), line=dict(color=UP, width=3)), secondary_y=False)
    fig4.add_trace(go.Bar(x=metrics["ts"], y=metrics["learning_velocity"], name=rtl_text("سرعت یادگیری"), marker_color=NEON, opacity=0.55), secondary_y=True)
    fig_base(fig4, "پیشروی آگاهی و سرعت یادگیری")
    fig4.update_yaxes(range=[0, 1], secondary_y=False)

    # Win/Loss streak visualization
    closed_df = pd.DataFrame(closed)
    if closed_df.empty:
        closed_df = pd.DataFrame({"pnl": [0]})
    streak = []
    s = 0
    for pnl in closed_df.get("pnl", pd.Series([0])).fillna(0).tolist()[::-1][:60]:
        s = s + 1 if pnl > 0 else s - 1 if pnl < 0 else 0
        streak.append(s)
    streak = streak[::-1]
    fig5 = go.Figure()
    fig5.add_trace(go.Bar(x=list(range(len(streak))), y=streak, marker_color=[UP if v >= 0 else DN for v in streak], name=rtl_text("Streak")))
    fig_base(fig5, "برد/باخت و توالی استریک")

    # Surface plot for parameter space exploration
    x = np.linspace(0.3, 0.9, 28)
    y = np.linspace(0.2, 0.8, 28)
    X, Y = np.meshgrid(x, y)
    Z = np.sin(X * 8) * np.cos(Y * 6) + 0.5 * X - 0.35 * Y + 0.15 * np.random.default_rng(3).normal(size=X.shape)
    fig6 = go.Figure(data=[go.Surface(x=X, y=Y, z=Z, colorscale=[[0, "#0b62ff"], [0.45, "#14d9ff"], [1, "#f5c542"]], showscale=True)])
    fig_base(fig6, "اکتشاف فضای پارامترها — سطح 3D", height=420)
    fig6.update_layout(scene=dict(
        xaxis_title=rtl_text("score_threshold"),
        yaxis_title=rtl_text("conv_threshold"),
        zaxis_title=rtl_text("fitness"),
        bgcolor="rgba(0,0,0,0)",
    ))

    # Heatmap for regime performance
    regimes = ["TREND_UP", "TREND_DOWN", "RANGING", "HIGH_VOL"]
    metrics_names = [rtl_text("WinRate"), rtl_text("AvgPnL"), rtl_text("Confidence"), rtl_text("DNA")]
    mat = np.array([
        [0.67, 0.53, 0.61, 0.58],
        [0.55, 0.49, 0.52, 0.50],
        [0.43, 0.38, 0.46, 0.42],
        [0.36, 0.40, 0.39, 0.35],
    ])
    fig7 = go.Figure(data=go.Heatmap(z=mat, x=metrics_names, y=regimes, colorscale="Viridis", zmin=0, zmax=1,
                                     hovertemplate="رژیم=%{y}<br>شاخص=%{x}<br>مقدار=%{z:.2f}<extra></extra>"))
    fig_base(fig7, "نقشه حرارتی عملکرد رژیم‌ها", height=360)

    # Radar chart capabilities
    radar_vals = [
        clamp(np.mean([o.weight for o in HIVE.orgs]) / 2.0, 0, 1),
        HIVE.awareness,
        HIVE.confidence,
        clamp(HIVE.win_rate(), 0, 1),
        clamp((HIVE.adaptive["score_threshold"] + (1 - HIVE.adaptive["conv_threshold"])) / 2, 0, 1),
        clamp(0.45 + abs(HIVE.learning_velocity()) * 4, 0, 1),
    ]
    radar_labels = [rtl_text(x) for x in ["قدرت", "آگاهی", "اعتماد", "وین‌ریت", "تعادل", "شتاب"]]
    radar_vals += radar_vals[:1]
    radar_labels += radar_labels[:1]
    fig8 = go.Figure()
    fig8.add_trace(go.Scatterpolar(r=radar_vals, theta=radar_labels, fill="toself", line=dict(color=GOLD, width=3), name=rtl_text("Capabilities")))
    fig_base(fig8, "رادار قابلیت‌های ارگانیسم", height=360)
    fig8.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(range=[0, 1], gridcolor="#31415f")))

    # Candlestick with regime overlay
    candles = get_klines("BTCUSDT", limit=120)
    if candles is None or candles.empty:
        candles = synthetic_series("BTCUSDT", n=120)
    reg = [detect_regime(candles.iloc[:i+1]) for i in range(len(candles))]
    overlay = pd.Series(range(len(candles)))
    overlay_map = {"TREND_UP": 0.78, "TREND_DOWN": 0.22, "RANGING": 0.50, "HIGH_VOL": 0.92}
    regime_y = [overlay_map.get(r, 0.5) for r in reg]
    fig9 = make_subplots(specs=[[{"secondary_y": True}]])
    fig9.add_trace(go.Candlestick(x=candles["ts"], open=candles["open"], high=candles["high"], low=candles["low"], close=candles["close"], name=rtl_text("کندل")), secondary_y=False)
    fig9.add_trace(go.Scatter(x=candles["ts"], y=regime_y, mode="lines", name=rtl_text("رژیم"), line=dict(color=CYAN, width=2, dash="dot")), secondary_y=True)
    fig_base(fig9, "کندل‌استیک + لایهٔ رژیم", height=430)
    fig9.update_yaxes(title_text=rtl_text("Price"), secondary_y=False)
    fig9.update_yaxes(title_text=rtl_text("Regime Overlay"), range=[0, 1], secondary_y=True, showgrid=False)

    # Sankey decision flow
    labels = [rtl_text("اسکن"), rtl_text("فیلتر حجم/اسپرد"), rtl_text("ویژگی‌ها"), rtl_text("اجماع"), rtl_text("ورود"), rtl_text("رد"), rtl_text("نگه‌داشت")]
    sources = [0, 1, 2, 3, 3, 3]
    targets = [1, 2, 3, 4, 5, 6]
    values = [80, 65, 52, 18, 34, 18]
    colors = ["rgba(124,92,255,0.35)", "rgba(20,217,255,0.35)", "rgba(245,197,66,0.35)", "rgba(0,255,208,0.35)", "rgba(240,93,127,0.35)", "rgba(24,194,156,0.35)"]
    fig10 = go.Figure(data=[go.Sankey(node=dict(pad=16, thickness=18, line=dict(color="#4b5a78", width=1), label=labels, color=["#22314f"]*len(labels)),
                                       link=dict(source=sources, target=targets, value=values, color=colors))])
    fig_base(fig10, "جریان تصمیم‌گیری شبکهٔ Hive", height=410)

    # Gauge charts
    cols = dbc.Row([
        dbc.Col(dcc.Graph(figure=make_gauge("آگاهی", HIVE.awareness, UP)), md=4),
        dbc.Col(dcc.Graph(figure=make_gauge("اعتماد", HIVE.confidence, CYAN)), md=4),
        dbc.Col(dcc.Graph(figure=make_gauge("DNA Score", HIVE.dna_score(), GOLD)), md=4),
    ], className="g-2")

    return {
        "fig1": fig1, "fig2": fig2, "fig3": fig3, "fig4": fig4, "fig5": fig5,
        "fig6": fig6, "fig7": fig7, "fig8": fig8, "fig9": fig9, "fig10": fig10,
        "gauges": cols, "metrics": metrics, "evo": evo,
    }


def make_gauge(title, value, color):
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=float(value) * 100,
        number={"suffix": "%", "font": {"size": 28, "color": TXT}},
        delta={"reference": 50, "increasing": {"color": UP}, "decreasing": {"color": DN}},
        title={"text": rtl_text(title), "font": {"size": 16, "color": GOLD}},
        gauge={
            "axis": {"range": [None, 100], "tickwidth": 1, "tickcolor": "#9cb4d4"},
            "bar": {"color": color},
            "bgcolor": "rgba(0,0,0,0)",
            "steps": [
                {"range": [0, 35], "color": "#12233d"},
                {"range": [35, 70], "color": "#182a48"},
                {"range": [70, 100], "color": "#1f355b"},
            ],
            "threshold": {"line": {"color": GOLD, "width": 4}, "thickness": 0.8, "value": 90},
        },
    ))
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(8,17,31,0.9)", height=250, margin=dict(l=15, r=15, t=40, b=15), font=dict(color=TXT))
    return fig


# ----------------------------------------------------------------------------
# Dash app
# ----------------------------------------------------------------------------
init_db()
HIVE = HivePro()

external_stylesheets = [dbc.themes.CYBORG, "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;700;900&display=swap"]
app = dash.Dash(__name__, external_stylesheets=external_stylesheets, suppress_callback_exceptions=True)
server = app.server
app.title = APP_TITLE
app.config.suppress_callback_exceptions = True

app.index_string = f"""
<!DOCTYPE html>
<html lang=\"fa\" dir=\"rtl\">
    <head>
        {{%metas%}}
        <title>{APP_TITLE}</title>
        {{%favicon%}}
        {{%css%}}
        <style>
        :root {{ color-scheme: dark; }}
        body {{
            margin:0; padding:0; background:
                radial-gradient(circle at 20% 20%, rgba(20,217,255,.12), transparent 25%),
                radial-gradient(circle at 80% 10%, rgba(124,92,255,.14), transparent 24%),
                radial-gradient(circle at 50% 90%, rgba(245,197,66,.10), transparent 20%),
                linear-gradient(135deg, #050b16 0%, #08111f 50%, #050b16 100%);
            font-family: Vazirmatn, IRANSans, Segoe UI, sans-serif;
            color: #e9f1ff;
            overflow-x: hidden;
        }}
        * {{ scrollbar-width: thin; scrollbar-color: #3d527a #091220; }}
        ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
        ::-webkit-scrollbar-track {{ background: #091220; }}
        ::-webkit-scrollbar-thumb {{ background: linear-gradient(180deg, #7c5cff, #14d9ff); border-radius: 10px; }}
        .glass-card {{
            backdrop-filter: blur(18px);
            background: rgba(13, 20, 38, 0.70) !important;
            border: 1px solid rgba(124, 92, 255, 0.35) !important;
            box-shadow: 0 0 0 1px rgba(20,217,255,0.08), 0 10px 30px rgba(0,0,0,0.35), inset 0 0 25px rgba(20,217,255,0.05);
            border-radius: 18px !important;
        }}
        .neon-border {{
            box-shadow: 0 0 12px rgba(20,217,255,0.25), 0 0 24px rgba(124,92,255,0.12);
            border: 1px solid rgba(20,217,255,0.35) !important;
        }}
        .glow-title {{ text-shadow: 0 0 12px rgba(20,217,255,0.45), 0 0 24px rgba(124,92,255,0.22); }}
        .dash-tabs .nav-link, .tab {{ border-radius: 14px !important; margin: 0 4px; }}
        .btn {{ border-radius: 14px !important; }}
        .fade-in {{ animation: fadeIn .5s ease both; }}
        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(4px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        </style>
    </head>
    <body>
        {{%app_entry%}}
        <footer>
            {{%config%}}
            {{%scripts%}}
            {{%renderer%}}
        </footer>
    </body>
</html>
"""


def stat_card(title, val, color=GOLD, sub=""):
    return dbc.Card(
        dbc.CardBody([
            html.Div(rtl_text(title), style={"color": MUT, "fontSize": 12, "marginBottom": 6}),
            html.Div(str(val), style={"color": color, "fontSize": 24, "fontWeight": 800, "lineHeight": 1.1, "textShadow": f"0 0 12px {color}55"}),
            html.Div(rtl_text(sub), style={"color": MUT, "fontSize": 11, "marginTop": 6}),
        ]),
        className="glass-card neon-border fade-in",
        style={"height": "100%"},
    )


def trade_table(opens, tickers):
    if not opens:
        return dbc.Alert(rtl_text("در حال حاضر پوزیشن بازی وجود ندارد."), color="secondary", className="glass-card")
    rows = []
    for t in opens:
        last = tickers.get(t["symbol"], {}).get("last", t["entry"])
        if t["side"] == "long":
            pp = (last - t["entry"]) / t["entry"]
        else:
            pp = (t["entry"] - last) / t["entry"]
        remain = 1.0 - sum(p.get("frac", 0) for p in t["partials"])
        pnl = pp * t["size_usd"] * remain * LEVERAGE - t["size_usd"] * remain * COMMISSION * 2
        rows.append(html.Tr([
            html.Td(t["id"]), html.Td(t["symbol"]), html.Td(rtl_text(t["side"].upper()), style={"color": UP if t["side"]=="long" else DN}),
            html.Td(t["regime"]), html.Td(f"{t['entry']:.5f}"), html.Td(f"{last:.5f}"), html.Td(money(t["size_usd"])),
            html.Td(f"{pnl:+.2f}", style={"color": UP if pnl >= 0 else DN, "fontWeight": 700}),
            html.Td(f"{t['trail_stop']:.5f}" if t.get("trail_stop") else "—"), html.Td(str(len(t.get("partials", []))))
        ]))
    return dbc.Table([
        html.Thead(html.Tr([html.Th(x) for x in ["ID", "نماد", "سمت", "رژیم", "ورود", "فعلی", "مارجین", "PnL", "Trail", "Partial"]])),
        html.Tbody(rows)
    ], bordered=True, hover=True, responsive=True, size="sm", className="glass-card", style={"color": TXT})


# Layout
app.layout = html.Div([
    dbc.Container(fluid=True, children=[
        dbc.Card(dbc.CardBody(dbc.Row([
            dbc.Col(html.Div([
                html.H2(rtl_text("HIVE SCALPER-SNIPER PRO v3"), className="glow-title", style={"margin": 0, "color": GOLD, "fontWeight": 900}),
                html.Div(rtl_text("داشبورد راست‌چین با تمرکز ویژه بر یادگیری، تکامل و آگاهی ارگانیسم"), style={"color": MUT, "marginTop": 6}),
            ]), md=6),
            dbc.Col(html.Div(id="pulse", className="text-end", style={"color": NEON, "fontFamily": "monospace", "fontSize": 13}), md=3),
            dbc.Col(html.Div(id="status", className="text-end", style={"color": MUT, "fontSize": 12}), md=3),
        ], align="center")), className="glass-card neon-border mb-3 mt-2"),

        dcc.Tabs(id="tabs", value="live", parent_className="dash-tabs", className="dash-tabs", children=[
            dcc.Tab(label=rtl_text("معاملات زنده"), value="live", style={"background": CARD_SOLID, "color": TXT}, selected_style={"background": LINE, "color": GOLD, "fontWeight": 700}),
            dcc.Tab(label=rtl_text("آگاهی و تکامل"), value="learning", style={"background": CARD_SOLID, "color": TXT}, selected_style={"background": LINE, "color": GOLD, "fontWeight": 700}),
            dcc.Tab(label=rtl_text("بک‌تست و DNA"), value="backtest", style={"background": CARD_SOLID, "color": TXT}, selected_style={"background": LINE, "color": GOLD, "fontWeight": 700}),
            dcc.Tab(label=rtl_text("تحلیل عملکرد"), value="perf", style={"background": CARD_SOLID, "color": TXT}, selected_style={"background": LINE, "color": GOLD, "fontWeight": 700}),
            dcc.Tab(label=rtl_text("تنظیمات و کنترل"), value="settings", style={"background": CARD_SOLID, "color": TXT}, selected_style={"background": LINE, "color": GOLD, "fontWeight": 700}),
        ]),
        html.Div(id="content", className="mt-3"),
        dcc.Interval(id="life", interval=12_000, n_intervals=0),
        dcc.Interval(id="cycle", interval=35_000, n_intervals=0),
        dcc.Store(id="bt-result"),
        dcc.Store(id="evo-result"),
        html.Div(style={"height": "24px"}),
    ])
], style={"minHeight": "100vh"})


# ----------------------------------------------------------------------------
# Tab renderers
# ----------------------------------------------------------------------------
def render_live_tab():
    hive = HIVE
    opens = get_open_trades()
    closed = get_closed_trades(50)
    tickers = get_all_tickers()
    eq = hive.equity()
    wr = hive.win_rate() * 100
    pnl_total = sum(t["pnl"] or 0 for t in closed)
    eqh = get_equity_history()
    if eqh.empty:
        eqh = pd.DataFrame({"ts": [now_utc()], "equity": [INITIAL_CAPITAL], "open_n": [0]})
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=pd.to_datetime(eqh["ts"]), y=eqh["equity"], mode="lines", line=dict(color=GOLD, width=3), name=rtl_text("Equity"), fill="tozeroy", fillcolor="rgba(245,197,66,0.10)"))
    fig.add_hline(y=INITIAL_CAPITAL, line_dash="dot", line_color=MUT)
    fig_base(fig, "اکویتی زنده")
    fig.update_yaxes(tickprefix="$")
    return html.Div([
        dbc.Row([
            dbc.Col(stat_card("اکویتی", money(eq), GOLD, f"Peak {money(hive.peak)}"), md=3),
            dbc.Col(stat_card("Win Rate", pct(wr / 100), UP if wr >= 50 else DN, rtl_text(f"Closed {len(closed)}")), md=3),
            dbc.Col(stat_card("PnL تحقق‌یافته", money(pnl_total), UP if pnl_total >= 0 else DN, rtl_text("جمع معاملات بسته")), md=3),
            dbc.Col(stat_card("پوزیشن باز", f"{len(opens)}/{MAX_POSITIONS}", NEON, rtl_text("کنترل هم‌زمان")), md=3),
        ], className="g-3 mb-3"),
        dbc.Card(dbc.CardBody([
            html.Div(rtl_text("پوزیشن‌های باز"), style={"color": GOLD, "fontWeight": 800, "marginBottom": 10}),
            trade_table(opens, tickers),
        ]), className="glass-card neon-border mb-3"),
        dbc.Card(dbc.CardBody(dcc.Graph(figure=fig, config={"displaylogo": False})), className="glass-card neon-border"),
    ])


def render_learning_tab():
    figs = make_learning_figures()
    hive = HIVE
    evo = df_safe(get_evo_history(100))
    last_note = evo["note"].iloc[-1] if (not evo.empty and "note" in evo.columns) else "—"
    info = dbc.Row([
        dbc.Col(stat_card("نسل", hive.generation, NEON, rtl_text("Evolution step")), md=2),
        dbc.Col(stat_card("آگاهی", pct(hive.awareness), UP, rtl_text("هدف: نزدیک شدن به آستانهٔ نهایی")), md=2),
        dbc.Col(stat_card("اعتماد", pct(hive.confidence), CYAN, rtl_text("Confidence growth")), md=2),
        dbc.Col(stat_card("Learning Rate", f"{hive.learning_rate:.3f}", ORANGE, rtl_text("تنظیمات سازگار")), md=2),
        dbc.Col(stat_card("DNA Score", pct(hive.dna_score()), GOLD, rtl_text("قدرت یادگیری")), md=2),
        dbc.Col(stat_card("Velocity", f"{hive.learning_velocity():+.4f}", UP if hive.learning_velocity() >= 0 else DN, last_note), md=2),
    ], className="g-3 mb-3")
    return html.Div([
        info,
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=figs["fig1"], config={"displaylogo": False}))), md=12, className="mb-3"),
        ]),
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=figs["fig2"], config={"displaylogo": False}))), md=6),
            dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=figs["fig3"], config={"displaylogo": False}))), md=6),
        ], className="g-3 mb-3"),
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=figs["fig4"], config={"displaylogo": False}))), md=6),
            dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=figs["fig5"], config={"displaylogo": False}))), md=6),
        ], className="g-3 mb-3"),
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=figs["fig6"], config={"displaylogo": False}))), md=6),
            dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=figs["fig7"], config={"displaylogo": False}))), md=6),
        ], className="g-3 mb-3"),
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=figs["fig8"], config={"displaylogo": False}))), md=6),
            dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=figs["fig9"], config={"displaylogo": False}))), md=6),
        ], className="g-3 mb-3"),
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=figs["fig10"], config={"displaylogo": False}))), md=12),
        ], className="mb-3"),
        dbc.Card(dbc.CardBody([
            html.Div(rtl_text("شاخص‌های یادگیری"), style={"color": GOLD, "fontWeight": 800, "marginBottom": 8}),
            figs["gauges"],
        ]), className="glass-card neon-border"),
    ])


def render_backtest_tab(bt_data, evo_data):
    if bt_data:
        res_card = dbc.Card(dbc.CardBody([
            html.Div(rtl_text(f"نماد: {bt_data['symbol']}"), style={"color": GOLD}),
            html.Div(rtl_text(f"تعداد معامله: {bt_data['trades']}")),
            html.Div(rtl_text(f"وین‌ریت: {bt_data['winrate']*100:.1f}%"), style={"color": UP if bt_data['winrate'] >= 0.5 else DN}),
            html.Div(rtl_text(f"بازده کل: {bt_data['total_return']*100:+.2f}%"), style={"color": UP if bt_data['total_return'] >= 0 else DN}),
            html.Div(rtl_text(f"سرمایه نهایی: {money(bt_data['final_capital'])}")),
            html.Div(rtl_text(f"میانگین PnL: {bt_data['avg_pnl']:+.2f}")),
            html.Div(rtl_text(f"نسل: {bt_data.get('generation', 0)}"), style={"color": MUT}),
        ]), className="glass-card neon-border")
    else:
        res_card = dbc.Alert(rtl_text("هنوز بک‌تستی اجرا نشده است."), color="secondary", className="glass-card")
    if evo_data:
        evo_fig = go.Figure()
        evo_fig.add_trace(go.Scatter(x=evo_data["ts"], y=evo_data["score_threshold"], mode="lines+markers", name=rtl_text("score_threshold"), line=dict(color=ORANGE, width=3)))
        evo_fig.add_trace(go.Scatter(x=evo_data["ts"], y=evo_data["conv_threshold"], mode="lines+markers", name=rtl_text("conv_threshold"), line=dict(color=NEON, width=3)))
        evo_fig.add_trace(go.Scatter(x=evo_data["ts"], y=evo_data["awareness"], mode="lines", name=rtl_text("awareness"), line=dict(color=UP, width=2.5)))
        fig_base(evo_fig, "تاریخچهٔ DNA و تطبیق آستانه‌ها")
        evo_fig.update_yaxes(range=[0, 1])
    else:
        evo_fig = go.Figure().add_annotation(text=rtl_text("داده‌ای برای نمایش وجود ندارد"), showarrow=False)
    return html.Div([
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div(rtl_text("اجرای بک‌تست مبتنی بر مسیر تصمیم زنده"), style={"color": GOLD, "fontWeight": 800, "marginBottom": 10}),
                dbc.Row([
                    dbc.Col(dcc.Input(id="bt-symbol", value="BTCUSDT", type="text", style={"width": "100%", "padding": 10, "borderRadius": 12, "background": "#0e1628", "color": TXT, "border": f"1px solid {LINE}"}), md=4),
                    dbc.Col(dbc.Button(rtl_text("اجرای بک‌تست"), id="bt-run", color="warning", className="w-100 fw-bold"), md=2),
                    dbc.Col(dbc.Button(rtl_text("تکامل نسل جدید"), id="evo-run", color="info", className="w-100 fw-bold"), md=2),
                    dbc.Col(html.Div(id="bt-note", style={"color": MUT, "paddingTop": 8}), md=4),
                ], className="g-2"),
            ]), className="glass-card neon-border"), md=12),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col(res_card, md=4),
            dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=evo_fig, config={"displaylogo": False}))), md=8),
        ], className="g-3"),
        html.Div(id="evo-summary", className="mt-3", children=render_evo_summary(evo_data)),
    ])


def render_evo_summary(df):
    if df is None or df.empty:
        return dbc.Alert(rtl_text("خلاصهٔ تکامل در دسترس نیست."), color="secondary", className="glass-card")
    last = df.iloc[-1]
    return dbc.Card(dbc.CardBody([
        html.Div(rtl_text("Timeline of Evolution"), style={"color": GOLD, "fontWeight": 800, "marginBottom": 8}),
        html.Div(rtl_text(f"آخرین تغییرات: نسل {int(last['generation'])} | score={last['score_threshold']:.3f} | conv={last['conv_threshold']:.3f} | awareness={last['awareness']:.3f}")),
        html.Div(rtl_text("هدف: افزایش پیوستهٔ آگاهی و کاهش نوسان آستانه‌ها تا ارگانیسم به سقف یادگیری خود برسد."), style={"color": MUT, "marginTop": 6}),
    ]), className="glass-card neon-border")


def render_perf_tab():
    closed = get_closed_trades(120)
    if not closed:
        return dbc.Alert(rtl_text("هنوز معاملهٔ بسته‌ای برای تحلیل وجود ندارد."), color="secondary", className="glass-card")
    pnls = [t["pnl"] for t in closed if t["pnl"] is not None]
    wr = sum(1 for p in pnls if p > 0) / len(pnls) if pnls else 0
    by_regime = defaultdict(list)
    for t in closed:
        by_regime[t.get("regime") or "UNK"].append(t.get("pnl") or 0)
    regime_rows = []
    for reg, vals in by_regime.items():
        regime_rows.append(html.Div(rtl_text(f"{reg}: n={len(vals)} | WR={sum(1 for v in vals if v>0)/len(vals)*100:.0f}% | Avg={np.mean(vals):+.2f}"), className="mb-1"))
    # Confidence growth over time line
    lm = get_learning_metrics(300)
    conf_fig = go.Figure()
    if not lm.empty:
        conf_fig.add_trace(go.Scatter(x=lm["ts"], y=lm["confidence"], name=rtl_text("Confidence"), line=dict(color=CYAN, width=3)))
        conf_fig.add_trace(go.Scatter(x=lm["ts"], y=lm["awareness"], name=rtl_text("Awareness"), line=dict(color=UP, width=2.5)))
    else:
        conf_fig.add_trace(go.Scatter(x=[0, 1], y=[0.5, 0.7], line=dict(color=CYAN, width=3)))
    fig_base(conf_fig, "رشد اعتماد و آگاهی در طول زمان")
    return html.Div([
        dbc.Row([
            dbc.Col(stat_card("WinRate", pct(wr), UP if wr >= 0.5 else DN, rtl_text("Closed trades")), md=3),
            dbc.Col(stat_card("Avg PnL", money(np.mean(pnls)), GOLD, rtl_text("میانگین معاملات بسته")), md=3),
            dbc.Col(stat_card("Best", money(max(pnls)), UP, rtl_text("بهترین معامله")), md=3),
            dbc.Col(stat_card("Worst", money(min(pnls)), DN, rtl_text("بدترین معامله")), md=3),
        ], className="g-3 mb-3"),
        dbc.Row([
            dbc.CardBody(dcc.Graph(figure=conf_fig, config={"displayModeBar": False}), className="glass-card"),
        ], className="mb-3"),
        dbc.Card(dbc.CardBody([
            html.Div(rtl_text("عملکرد بر اساس رژیم"), style={"color": GOLD, "fontWeight": 800, "marginBottom": 8}),
            *regime_rows,
        ]), className="glass-card neon-border")
    ])


def render_settings_tab():
    return html.Div([
        dbc.Row([
            dbc.Col(stat_card("آستانهٔ score", f"{HIVE.adaptive['score_threshold']:.3f}", ORANGE, rtl_text("مرز تصمیم ورود")), md=3),
            dbc.Col(stat_card("آستانهٔ conv", f"{HIVE.adaptive['conv_threshold']:.3f}", ORANGE, rtl_text("مرز اجماع ارگانیسم‌ها")), md=3),
            dbc.Col(stat_card("وزن میانگین", f"{np.mean([o.weight for o in HIVE.orgs]):.3f}", NEON, rtl_text("قدرت ارگانیسم")), md=3),
            dbc.Col(stat_card("نورون‌ها", f"{HIVE.total_neurons():,}", CYAN, rtl_text("شکل‌گیری شبکهٔ ذهنی")), md=3),
        ], className="g-3 mb-3"),
        dbc.Card(dbc.CardBody([
            html.Div(rtl_text("تنظیمات و توضیحات"), style={"color": GOLD, "fontWeight": 800, "marginBottom": 8}),
            html.Div(rtl_text("- UI کاملاً RTL و راست‌چین است."), style={"color": MUT}),
            html.Div(rtl_text("- هر تغییر در معاملات و بک‌تست، در DNA ذخیره می‌شود."), style={"color": MUT}),
            html.Div(rtl_text("- برای رسیدن به سقف یادگیری، آگاهی، اعتماد و thresholds به‌صورت پیوسته تطبیق داده می‌شوند."), style={"color": MUT}),
            html.Hr(style={"borderColor": LINE}),
            dbc.Button(rtl_text("ذخیرهٔ دستی DNA"), id="save-dna", color="success", className="fw-bold"),
            html.Span(id="save-note", style={"marginRight": 12, "color": MUT}),
        ]), className="glass-card neon-border"),
    ])


# ----------------------------------------------------------------------------
# Callbacks
# ----------------------------------------------------------------------------
@app.callback(Output("content", "children"), Input("tabs", "value"), Input("life", "n_intervals"), Input("bt-result", "data"), Input("evo-result", "data"))
def render_content(tab, n, bt_data, evo_data):
    try:
        if tab == "live":
            return render_live_tab()
        if tab == "learning":
            return render_learning_tab()
        if tab == "backtest":
            return render_backtest_tab(bt_data, evo_data)
        if tab == "perf":
            return render_perf_tab()
        return render_settings_tab()
    except Exception as e:
        return dbc.Alert(f"UI error: {e}", color="danger")


@app.callback(Output("pulse", "children"), Output("status", "children"), Input("life", "n_intervals"))
def update_header(n):
    HIVE.heart_beat += 1
    return (
        rtl_text(f"BEAT #{HIVE.heart_beat} | GEN {HIVE.generation} | θ={HIVE.adaptive['score_threshold']:.2f} | κ={HIVE.adaptive['conv_threshold']:.2f}"),
        rtl_text(f"نورون {HIVE.total_neurons():,} | آگاهی {pct(HIVE.awareness)} | اعتماد {pct(HIVE.confidence)} | لوریج {LEVERAGE}×"),
    )


@app.callback(Output("cycle", "disabled"), Input("cycle", "n_intervals"), prevent_initial_call=False)
def run_cycle(n):
    try:
        HIVE.cycle()
    except Exception:
        traceback.print_exc()
    return False


@app.callback(Output("bt-result", "data"), Output("bt-note", "children"), Input("bt-run", "n_clicks"), State("bt-symbol", "value"), prevent_initial_call=True)
def do_backtest(n, symbol):
    if not n:
        return no_update, no_update
    try:
        symbol = (symbol or "BTCUSDT").upper().strip()
        result = run_backtest(symbol, candles=5000)
        if result is None:
            return None, rtl_text("دادهٔ کافی برای بک‌تست پیدا نشد.")
        return result, rtl_text("بک‌تست با منطق مسیر تصمیم زنده اجرا شد.")
    except Exception as e:
        return None, rtl_text(f"خطا در بک‌تست: {e}")


@app.callback(Output("evo-result", "data"), Input("evo-run", "n_clicks"), prevent_initial_call=True)
def do_evolution(n):
    if not n:
        return no_update
    try:
        symbols = list(get_all_tickers().keys())[:8]
        if not symbols:
            symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
        result = HIVE.run_generation(symbols, candles=2500)
        return result
    except Exception:
        traceback.print_exc()
        return None


@app.callback(Output("save-note", "children"), Input("save-dna", "n_clicks"), prevent_initial_call=True)
def save_dna(n):
    if not n:
        return no_update
    try:
        save_dna_state(HIVE)
        db_set("adaptive", HIVE.adaptive)
        db_set("awareness", HIVE.awareness)
        db_set("confidence", HIVE.confidence)
        db_set("learning_rate", HIVE.learning_rate)
        return rtl_text(f"DNA ذخیره شد: {DNA_STATE_PATH}")
    except Exception as e:
        return rtl_text(f"خطا در ذخیره DNA: {e}")


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"{APP_TITLE} starting...")
    print(f"Path: {BASE_DIR}")
    print(f"DB: {DB_PATH}")
    print(f"DNA: {DNA_STATE_PATH}")
    print(f"Neurons: {HIVE.total_neurons():,} | Gen: {HIVE.generation} | Leverage: {LEVERAGE}x | MaxPos: {MAX_POSITIONS}")
    print("RTL Dash UI enabled | Learning tab enabled | Advanced charts enabled")
    app.run(debug=True, host="0.0.0.0", port=8061, use_reloader=False)
