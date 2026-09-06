# -*- coding: utf-8 -*-
"""
HIVE SYNAPSE v10
Institutional-grade scalping organism with seven living organs,
Bybit REST connector, SQLite memory, and a 6-tab Dash dashboard.

This is a trading research and execution scaffold. Live trading requires
valid Bybit credentials and exchange-side permissions.
"""

from __future__ import annotations

import json
import math
import os
import random
import sqlite3
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import dash
from dash import dcc, html, Input, Output, State, ctx, no_update
import dash_bootstrap_components as dbc

try:
    import requests
except Exception:
    requests = None

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

# -----------------------------------------------------------------------------
# Paths / constants
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
DB_PATH = BASE_DIR / "hive_synapse_v10.db"
LOG_PATH = BASE_DIR / "hive_synapse_v10.log"

APP_TITLE = "HIVE SYNAPSE v10"
INITIAL_CAPITAL = 500.0
DEFAULT_LEVERAGE = 10
TRADE_SIZE_MIN = 5.0
TRADE_SIZE_MAX = 20.0
SCOUT_INTERVAL_MS = 2000
HUNT_INTERVAL_MS = 1000
MAX_ACTIVE_POSITIONS = 3

REST_CANDIDATES = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
SESSION = requests.Session() if requests is not None else None
if SESSION is not None:
    SESSION.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.bybit.com/",
    })
_ACTIVE_REST_BASE = {"url": None}
_SESSION_LOCK = threading.Lock()
_LAST_REQ = 0.0

BG = "#08111f"
CARD = "#10192b"
CARD2 = "#0d1626"
LINE = "#24334c"
TXT = "#e8eef9"
MUT = "#8da0bf"
GOLD = "#f0b90b"
UP = "#18c29c"
DN = "#ef5b77"
CYAN = "#40c9ff"
PURPLE = "#8d6cff"
ORANGE = "#ff9f1c"

SYMBOL_UNIVERSE = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "AVAXUSDT", "ADAUSDT"]
SCOUT_SYMBOLS = SYMBOL_UNIVERSE[:5]
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_CATEGORY = "linear"
DEFAULT_INTERVAL = "1"

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def money(x: float) -> str:
    return f"${x:,.2f}"


def pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def safe_json_load(s, default=None):
    try:
        return json.loads(s)
    except Exception:
        return default


def log_event(msg: str):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{now_utc()}] {msg}\n")
    except Exception:
        pass


def fig_theme(fig: go.Figure, title: str = "", height: int = 380):
    fig.update_layout(
        template="plotly_dark",
        height=height,
        paper_bgcolor=BG,
        plot_bgcolor=CARD,
        font=dict(color=TXT, family="Vazirmatn, IRANSans, Segoe UI, sans-serif"),
        title=dict(text=rtl_text(title), x=0.98, xanchor="right", font=dict(color=GOLD, size=15)),
        margin=dict(l=18, r=18, t=48, b=24),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0.01),
    )
    fig.update_xaxes(gridcolor=LINE, zeroline=False)
    fig.update_yaxes(gridcolor=LINE, zeroline=False)
    return fig


# -----------------------------------------------------------------------------
# SQLite persistence
# -----------------------------------------------------------------------------
def db_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT, side TEXT, entry REAL, qty REAL, notional REAL,
        leverage INTEGER, stop REAL, trail REAL, take_profit REAL,
        opened_at TEXT, status TEXT, reason TEXT, organs TEXT, metadata TEXT,
        exit_price REAL, pnl REAL, closed_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, symbol TEXT, side TEXT, consensus REAL,
        accepted INTEGER, reason TEXT, organs TEXT, metadata TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS organ_state (
        ts TEXT, organ TEXT, vitality REAL, arousal REAL, hormones TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS equity (
        ts TEXT, equity REAL, cash REAL, open_pnl REAL, open_n INTEGER
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS scan_cache (
        ts TEXT, symbol TEXT, score REAL, side TEXT, regime TEXT, price REAL, spread_bps REAL, features TEXT
    )""")
    conn.commit()
    conn.close()


def state_get(key, default=None):
    conn = db_conn()
    row = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    conn.close()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except Exception:
        return row[0]


def state_set(key, value):
    conn = db_conn()
    conn.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?,?)",
                 (key, json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value))
    conn.commit()
    conn.close()


def insert_decision(symbol, side, consensus, accepted, reason, organs, metadata):
    conn = db_conn()
    conn.execute("""INSERT INTO decisions (ts, symbol, side, consensus, accepted, reason, organs, metadata)
                    VALUES (?,?,?,?,?,?,?,?)""",
                 (now_utc(), symbol, side, float(consensus), int(bool(accepted)), reason,
                  json.dumps(organs, ensure_ascii=False), json.dumps(metadata, ensure_ascii=False)))
    conn.commit()
    conn.close()


def save_organ_snapshot(organs: Dict[str, dict]):
    conn = db_conn()
    rows = [(now_utc(), name, float(v["vitality"]), float(v["arousal"]), json.dumps(v.get("hormones", {}), ensure_ascii=False))
            for name, v in organs.items()]
    conn.executemany("INSERT INTO organ_state (ts, organ, vitality, arousal, hormones) VALUES (?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def save_scan_cache(rows: List[dict]):
    if not rows:
        return
    conn = db_conn()
    conn.executemany("""INSERT INTO scan_cache (ts, symbol, score, side, regime, price, spread_bps, features)
                       VALUES (?,?,?,?,?,?,?,?)""",
                     [(now_utc(), r["symbol"], float(r["score"]), r["side"], r["regime"], float(r["price"]),
                       float(r["spread_bps"]), json.dumps(r.get("features", {}), ensure_ascii=False)) for r in rows])
    conn.commit()
    conn.close()


def record_equity(equity: float, cash: float, open_pnl: float, open_n: int):
    conn = db_conn()
    conn.execute("INSERT INTO equity (ts, equity, cash, open_pnl, open_n) VALUES (?,?,?,?,?)",
                 (now_utc(), float(equity), float(cash), float(open_pnl), int(open_n)))
    conn.commit()
    conn.close()


def get_equity_history(limit=500):
    conn = db_conn()
    rows = conn.execute("SELECT ts, equity, cash, open_pnl, open_n FROM equity ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    if not rows:
        return pd.DataFrame(columns=["ts", "equity", "cash", "open_pnl", "open_n"])
    return pd.DataFrame(rows, columns=["ts", "equity", "cash", "open_pnl", "open_n"]).sort_values("ts")


def get_open_positions():
    conn = db_conn()
    rows = conn.execute("""SELECT id, symbol, side, entry, qty, notional, leverage, stop, trail, take_profit,
                                    opened_at, reason, organs, metadata
                             FROM positions WHERE status='open' ORDER BY id DESC""").fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append({
            "id": r[0], "symbol": r[1], "side": r[2], "entry": r[3], "qty": r[4], "notional": r[5],
            "leverage": r[6], "stop": r[7], "trail": r[8], "take_profit": r[9], "opened_at": r[10],
            "reason": r[11], "organs": safe_json_load(r[12], {}), "metadata": safe_json_load(r[13], {}),
        })
    return out


def get_closed_positions(limit=120):
    conn = db_conn()
    rows = conn.execute("""SELECT id, symbol, side, entry, exit_price, qty, notional, pnl, opened_at, closed_at, reason
                             FROM positions WHERE status='closed' ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
    conn.close()
    return [
        {"id": r[0], "symbol": r[1], "side": r[2], "entry": r[3], "exit": r[4], "qty": r[5],
         "notional": r[6], "pnl": r[7], "opened_at": r[8], "closed_at": r[9], "reason": r[10]}
        for r in rows
    ]


def save_position(pos: dict) -> int:
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""INSERT INTO positions
        (symbol, side, entry, qty, notional, leverage, stop, trail, take_profit, opened_at, status, reason, organs, metadata)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (pos["symbol"], pos["side"], pos["entry"], pos["qty"], pos["notional"], pos["leverage"], pos["stop"],
         pos["trail"], pos["take_profit"], pos["opened_at"], "open", pos["reason"],
         json.dumps(pos.get("organs", {}), ensure_ascii=False), json.dumps(pos.get("metadata", {}), ensure_ascii=False)))
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid


def close_position(pid: int, exit_price: float, pnl: float):
    conn = db_conn()
    conn.execute("""UPDATE positions SET status='closed', exit_price=?, pnl=?, closed_at=? WHERE id=?""",
                 (float(exit_price), float(pnl), now_utc(), int(pid)))
    conn.commit()
    conn.close()


def update_position(pid: int, **kwargs):
    if not kwargs:
        return
    conn = db_conn()
    cols = ", ".join(f"{k}=?" for k in kwargs.keys())
    conn.execute(f"UPDATE positions SET {cols} WHERE id=?", (*kwargs.values(), int(pid)))
    conn.commit()
    conn.close()


# -----------------------------------------------------------------------------
# Bybit connector and market data
# -----------------------------------------------------------------------------
def bybit_get(path, params, timeout=8):
    if SESSION is None:
        return None
    global _LAST_REQ
    with _SESSION_LOCK:
        elapsed = time.time() - _LAST_REQ
        if elapsed < 0.06:
            time.sleep(0.06 - elapsed)
        _LAST_REQ = time.time()
    cands = ([ _ACTIVE_REST_BASE["url"] ] if _ACTIVE_REST_BASE["url"] else []) + [u for u in REST_CANDIDATES if u != _ACTIVE_REST_BASE["url"]]
    for base in cands:
        try:
            r = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code in (403, 451):
                continue
            r.raise_for_status()
            d = r.json()
            if d.get("retCode") == 0:
                _ACTIVE_REST_BASE["url"] = base
                return d
        except Exception:
            continue
    return None


def synthetic_series(symbol="BTCUSDT", interval="1", n=240, seed=None):
    seed = seed if seed is not None else abs(hash((symbol, interval))) % (2**32)
    rng = np.random.default_rng(seed)
    freq = "15s" if str(interval) in {"1", "15s"} else "1min"
    t = pd.date_range(end=pd.Timestamp.utcnow(), periods=n, freq=freq)
    base = 100 + np.cumsum(rng.normal(0, 0.18, n))
    cycle = np.sin(np.linspace(0, 14, n)) * 1.5 + np.sin(np.linspace(0, 44, n)) * 0.35
    trend = np.linspace(0, rng.normal(0, 5), n)
    close = base + cycle + trend
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + np.abs(rng.normal(0.28, 0.08, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0.28, 0.08, n))
    vol = np.abs(rng.normal(900, 180, n)) * (1 + np.sin(np.linspace(0, 9, n)) * 0.25)
    return pd.DataFrame({"ts": t, "open": open_, "high": high, "low": low, "close": close, "volume": vol})


def get_klines(symbol: str, interval: str = "1", category: str = "linear", limit: int = 240) -> pd.DataFrame:
    d = bybit_get("/v5/market/kline", {"category": category, "symbol": symbol, "interval": interval, "limit": limit})
    rows = ((d or {}).get("result") or {}).get("list") or []
    if not rows:
        return synthetic_series(symbol, interval, n=limit)
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms")
    for c in ["open", "high", "low", "close", "volume", "turnover"]:
        df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)


def get_tickers(category="linear") -> Dict[str, dict]:
    d = bybit_get("/v5/market/tickers", {"category": category})
    rows = ((d or {}).get("result") or {}).get("list") or []
    if not rows:
        rng = np.random.default_rng(42)
        out = {}
        for i, s in enumerate(SYMBOL_UNIVERSE):
            last = 100 + i * 20 + rng.normal(0, 2)
            out[s] = {"last": float(last), "bid": float(last * 0.9998), "ask": float(last * 1.0002),
                      "vol24": float(1_500_000 + i * 240_000), "turn24": float(4_000_000 + i * 320_000),
                      "chg": float(rng.normal(0, 0.03))}
        return out
    out = {}
    for t in rows:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        try:
            out[sym] = {
                "last": float(t.get("lastPrice") or 0),
                "bid": float(t.get("bid1Price") or t.get("lastPrice") or 0),
                "ask": float(t.get("ask1Price") or t.get("lastPrice") or 0),
                "vol24": float(t.get("volume24h") or 0),
                "turn24": float(t.get("turnover24h") or 0),
                "chg": float(t.get("price24hPcnt") or 0),
            }
        except Exception:
            continue
    return out


# -----------------------------------------------------------------------------
# Organ model
# -----------------------------------------------------------------------------
@dataclass
class Organ:
    name: str
    vitality: float
    arousal: float
    hormones: dict


ORGANS_ORDER = ["RETINA", "COCHLEA", "AMYGDALA", "HIPPOCAMPUS", "CEREBELLUM", "NEOCORTEX", "HEART"]


def init_organs() -> Dict[str, Organ]:
    organs = {}
    for n in ORGANS_ORDER:
        organs[n] = Organ(name=n, vitality=94.0, arousal=18.0, hormones={"dopamine": 0.25, "cortisol": 0.12, "serotonin": 0.2})
    return organs


ORGANS = init_organs()


def organ_mutate(org: Organ, delta_v=0.0, delta_a=0.0, hormones=None):
    org.vitality = clamp(org.vitality + delta_v, 0, 100)
    org.arousal = clamp(org.arousal + delta_a, 0, 100)
    if hormones:
        for k, v in hormones.items():
            org.hormones[k] = clamp(org.hormones.get(k, 0.0) + v, 0.0, 1.0)


# -----------------------------------------------------------------------------
# Market feature extraction / regime detection
# -----------------------------------------------------------------------------
def detect_regime(df: pd.DataFrame) -> str:
    if df is None or len(df) < 40:
        return "UNKNOWN"
    close = df["close"].astype(float)
    ret = close.pct_change().dropna()
    vol = float(ret.tail(20).std()) if len(ret) >= 20 else float(ret.std())
    trend = float((close.iloc[-1] - close.iloc[-20]) / close.iloc[-20]) if len(close) >= 20 else 0.0
    ma_fast = close.rolling(8).mean().iloc[-1]
    ma_slow = close.rolling(34).mean().iloc[-1]
    if vol > 0.018:
        return "HIGH_VOL"
    if trend > 0.004 and ma_fast > ma_slow:
        return "TREND_UP"
    if trend < -0.004 and ma_fast < ma_slow:
        return "TREND_DOWN"
    return "RANGING"


def extract_features(df: pd.DataFrame, ticker: dict) -> dict:
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)
    if len(df) < 20:
        return {"momentum": 0, "vol_surge": 0, "pressure": 0, "spread_q": 0.5, "rsi": 50, "atr_pct": 0}
    mom = float(np.clip((close.iloc[-1] - close.iloc[-7]) / close.iloc[-7], -0.03, 0.03))
    vol_surge = float(np.clip(volume.tail(4).mean() / (volume.tail(18).mean() + 1e-9) - 1, -1, 2))
    diffs = close.diff().tail(10)
    pressure = float(np.clip(diffs.mean() / (diffs.std() + 1e-9), -3, 3))
    mid = float(ticker.get("last") or close.iloc[-1])
    bid = float(ticker.get("bid") or mid)
    ask = float(ticker.get("ask") or mid)
    spread_bps = (ask - bid) / (mid + 1e-9) * 10000
    spread_q = float(np.clip(1.0 - spread_bps / 8.0, 0.0, 1.0))
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(10).mean()
    loss = (-delta.clip(upper=0)).rolling(10).mean()
    rs = gain / (loss + 1e-9)
    rsi = float((100 - (100 / (1 + rs))).iloc[-1])
    tr = np.maximum(high - low, np.maximum((high - close.shift(1)).abs(), (low - close.shift(1)).abs()))
    atr = float(tr.rolling(14).mean().iloc[-1])
    atr_pct = atr / (close.iloc[-1] + 1e-9)
    return {
        "momentum": mom,
        "vol_surge": vol_surge,
        "pressure": pressure,
        "spread_q": spread_q,
        "spread_bps": float(spread_bps),
        "rsi": rsi,
        "atr_pct": float(atr_pct),
        "last": float(close.iloc[-1]),
        "prev": float(close.iloc[-2]),
    }


# -----------------------------------------------------------------------------
# Organ scoring / chemistry
# -----------------------------------------------------------------------------
def score_organs(features: dict, regime: str) -> Dict[str, dict]:
    mom = features["momentum"]
    vs = features["vol_surge"]
    pr = features["pressure"]
    sq = features["spread_q"]
    rsi = features["rsi"]
    atr_pct = features["atr_pct"]

    retina = clamp(50 + mom * 180 + pr * 12, 0, 100)
    cochlea = clamp(50 + vs * 18 + sq * 12, 0, 100)
    amygdala = clamp(45 + abs(pr) * 10 + (65 if atr_pct > 0.012 else 15), 0, 100)
    hippocampus = clamp(40 + (abs(mom) * 300) + (20 if regime in {"TREND_UP", "TREND_DOWN"} else 8), 0, 100)
    cerebellum = clamp(55 + (100 - abs(rsi - 50) * 1.7) * 0.35 + sq * 12, 0, 100)
    neocortex = clamp(50 + (abs(mom) * 280) + (cochlea - 50) * 0.25 + hippocampus * 0.18, 0, 100)
    heart = clamp(60 + (cochlea - 50) * 0.15 + (neocortex - 50) * 0.2 - (amygdala - 50) * 0.12, 0, 100)

    hormones = {
        "dopamine": clamp(0.18 + max(0, mom) * 4.0 + max(0, vs) * 0.03, 0, 1),
        "cortisol": clamp(0.12 + max(0, atr_pct) * 8 + max(0, abs(pr)) * 0.05, 0, 1),
        "serotonin": clamp(0.15 + max(0, sq) * 0.4, 0, 1),
        "adrenaline": clamp(0.10 + max(0, abs(pr)) * 0.08, 0, 1),
    }

    scores = {
        "RETINA": {"vitality": retina, "arousal": clamp(25 + abs(mom) * 250 + pr * 5, 0, 100), "hormones": hormones},
        "COCHLEA": {"vitality": cochlea, "arousal": clamp(20 + vs * 24 + sq * 20, 0, 100), "hormones": hormones},
        "AMYGDALA": {"vitality": amygdala, "arousal": clamp(20 + abs(pr) * 12 + atr_pct * 300, 0, 100), "hormones": hormones},
        "HIPPOCAMPUS": {"vitality": hippocampus, "arousal": clamp(18 + abs(mom) * 220, 0, 100), "hormones": hormones},
        "CEREBELLUM": {"vitality": cerebellum, "arousal": clamp(18 + sq * 25 + (100 - abs(rsi - 50)) * 0.5, 0, 100), "hormones": hormones},
        "NEOCORTEX": {"vitality": neocortex, "arousal": clamp(25 + abs(mom) * 240 + abs(pr) * 6, 0, 100), "hormones": hormones},
        "HEART": {"vitality": heart, "arousal": clamp(35 + abs(mom) * 210 + (50 - abs(rsi - 50)) * 0.35, 0, 100), "hormones": hormones},
    }
    return scores


def consensus_side(features: dict, regime: str, organs: Dict[str, dict]) -> Tuple[str, float, Dict[str, float]]:
    mom = features["momentum"]
    vs = features["vol_surge"]
    pr = features["pressure"]
    rsi = features["rsi"]
    atr_pct = features["atr_pct"]
    spread_q = features["spread_q"]

    buy_votes = {
        "RETINA": 0.65 * max(0, mom) + 0.12 * max(0, pr),
        "COCHLEA": 0.28 * max(0, vs) + 0.16 * spread_q,
        "AMYGDALA": 0.22 * max(0, 0.5 - atr_pct),
        "HIPPOCAMPUS": 0.22 if regime in {"TREND_UP", "RANGING"} else 0.06,
        "CEREBELLUM": 0.28 if rsi < 60 else 0.06,
        "NEOCORTEX": 0.42 * max(0, mom) + 0.18 * max(0, pr),
        "HEART": 0.24 * spread_q,
    }
    sell_votes = {
        "RETINA": 0.65 * max(0, -mom) + 0.12 * max(0, -pr),
        "COCHLEA": 0.28 * max(0, -vs) + 0.16 * spread_q,
        "AMYGDALA": 0.22 * max(0, atr_pct - 0.008),
        "HIPPOCAMPUS": 0.22 if regime in {"TREND_DOWN", "RANGING"} else 0.06,
        "CEREBELLUM": 0.28 if rsi > 40 else 0.06,
        "NEOCORTEX": 0.42 * max(0, -mom) + 0.18 * max(0, -pr),
        "HEART": 0.24 * spread_q,
    }

    organ_weight = 0.0
    for name, o in organs.items():
        organ_weight += (o["vitality"] / 100.0) * (o["arousal"] / 100.0)

    buy_score = sum(buy_votes.values()) * (0.75 + organ_weight / 10.0)
    sell_score = sum(sell_votes.values()) * (0.75 + organ_weight / 10.0)
    side = "BUY" if buy_score > sell_score else "SELL"
    raw = max(buy_score, sell_score)
    consensus = float(clamp(raw / 4.2, 0.0, 1.0))
    return side, consensus, {"buy": float(buy_score), "sell": float(sell_score)}


# -----------------------------------------------------------------------------
# Execution engine
# -----------------------------------------------------------------------------
@dataclass
class HiveState:
    cash: float = INITIAL_CAPITAL
    realized: float = 0.0
    equity_last: float = INITIAL_CAPITAL
    last_scan_ts: str = ""
    last_hunt_ts: str = ""
    generation: int = 10
    sequence: int = 0
    last_decision: dict = None
    logs: List[str] = None


HIVE = HiveState(last_decision={}, logs=[])


def open_positions_count() -> int:
    return len(get_open_positions())


def open_position(symbol: str, side: str, price: float, consensus: float, organs: Dict[str, dict], reason: str, metadata: dict) -> dict:
    notional = float(clamp(TRADE_SIZE_MIN + consensus * (TRADE_SIZE_MAX - TRADE_SIZE_MIN), TRADE_SIZE_MIN, TRADE_SIZE_MAX))
    qty = (notional * DEFAULT_LEVERAGE) / max(price, 1e-9)
    sl_dist = max(price * (0.0018 + metadata.get("atr_pct", 0) * 1.8), price * 0.0012)
    tp_dist = max(price * (0.0026 + metadata.get("atr_pct", 0) * 2.5), price * 0.0018)
    if side == "BUY":
        stop = price - sl_dist
        take_profit = price + tp_dist
        trail = price - sl_dist * 0.7
    else:
        stop = price + sl_dist
        take_profit = price - tp_dist
        trail = price + sl_dist * 0.7
    pos = {
        "symbol": symbol,
        "side": side,
        "entry": float(price),
        "qty": float(qty),
        "notional": float(notional),
        "leverage": DEFAULT_LEVERAGE,
        "stop": float(stop),
        "trail": float(trail),
        "take_profit": float(take_profit),
        "opened_at": now_utc(),
        "reason": reason,
        "organs": organs,
        "metadata": metadata,
    }
    pos["id"] = save_position(pos)
    log_event(f"OPEN {side} {symbol} @ {price:.4f} consensus={consensus:.2f}")
    return pos


def pnl_for_position(pos: dict, last_price: float) -> float:
    direction = 1.0 if pos["side"] == "BUY" else -1.0
    return (last_price - pos["entry"]) * pos["qty"] * direction


def manage_positions(price_map: Dict[str, float]) -> List[dict]:
    closed = []
    for pos in get_open_positions():
        last = price_map.get(pos["symbol"])
        if last is None:
            continue
        if pos["side"] == "BUY":
            if last > pos["entry"]:
                trail = max(pos["trail"], last * 0.9982)
                if trail > pos["trail"]:
                    update_position(pos["id"], trail=trail)
                    pos["trail"] = trail
            exit_hit = last <= pos["stop"] or last <= pos["trail"] or last >= pos["take_profit"]
        else:
            if last < pos["entry"]:
                trail = min(pos["trail"], last * 1.0018)
                if trail < pos["trail"]:
                    update_position(pos["id"], trail=trail)
                    pos["trail"] = trail
            exit_hit = last >= pos["stop"] or last >= pos["trail"] or last <= pos["take_profit"]
        if exit_hit:
            pnl = pnl_for_position(pos, last)
            close_position(pos["id"], last, pnl)
            HIVE.cash += pnl
            HIVE.realized += pnl
            closed.append({**pos, "exit_price": last, "pnl": pnl})
            log_event(f"CLOSE {pos['side']} {pos['symbol']} @ {last:.4f} pnl={pnl:.2f}")
    return closed


# -----------------------------------------------------------------------------
# Scanning / hunt
# -----------------------------------------------------------------------------
def scan_symbol(symbol: str, ticker: dict, category: str = "linear", interval: str = "1") -> dict:
    df = get_klines(symbol, interval=interval, category=category, limit=240)
    if df.empty:
        return {"symbol": symbol, "score": 0.0, "side": "NONE", "regime": "UNKNOWN", "price": 0.0, "spread_bps": 0.0, "features": {}}
    regime = detect_regime(df)
    features = extract_features(df, ticker)
    organs = score_organs(features, regime)
    side, consensus, votes = consensus_side(features, regime, organs)
    score = consensus * (1.25 if side == "BUY" else 1.18)
    price = float(features["last"])
    row = {
        "symbol": symbol,
        "score": float(score),
        "side": side if consensus > 0.5 else "NONE",
        "regime": regime,
        "price": price,
        "spread_bps": float(features["spread_bps"]),
        "features": features,
        "organs": organs,
        "consensus": float(consensus),
        "votes": votes,
    }
    return row


def update_organs_from_scan(row: dict):
    if not row:
        return
    organs = row.get("organs") or {}
    for name, data in organs.items():
        org = ORGANS[name]
        org.vitality = clamp(0.92 * org.vitality + 0.08 * data["vitality"], 0, 100)
        org.arousal = clamp(0.82 * org.arousal + 0.18 * data["arousal"], 0, 100)
        for hk, hv in (data.get("hormones") or {}).items():
            org.hormones[hk] = clamp(0.88 * org.hormones.get(hk, 0.0) + 0.12 * hv, 0.0, 1.0)


def scout_pack(category="linear", interval="1") -> Tuple[List[dict], Dict[str, float]]:
    tickers = get_tickers(category=category)
    rows = []
    price_map = {}
    for sym in SCOUT_SYMBOLS:
        ticker = tickers.get(sym) or {"last": 0, "bid": 0, "ask": 0, "vol24": 0, "turn24": 0, "chg": 0}
        row = scan_symbol(sym, ticker, category=category, interval=interval)
        rows.append(row)
        price_map[sym] = row["price"]
    rows = sorted(rows, key=lambda r: r["score"], reverse=True)
    save_scan_cache(rows)
    if rows:
        update_organs_from_scan(rows[0])
        HIVE.last_scan_ts = now_utc()
    return rows, price_map


def hunt(rows: List[dict]) -> Optional[dict]:
    if not rows:
        return None
    candidates = [r for r in rows if r["side"] in {"BUY", "SELL"} and r["consensus"] >= 0.70]
    candidates = sorted(candidates, key=lambda r: (r["consensus"], r["score"]), reverse=True)
    if not candidates:
        return None
    top = candidates[0]
    active = get_open_positions()
    if len(active) >= MAX_ACTIVE_POSITIONS:
        return None
    if any(p["symbol"] == top["symbol"] for p in active):
        return None
    if sum(1 for o in ORGANS.values() if o.arousal >= 70) < 5:
        return None
    return top


# -----------------------------------------------------------------------------
# Dashboard builders
# -----------------------------------------------------------------------------
def organ_card(name: str, organ: Organ):
    v = organ.vitality
    a = organ.arousal
    h = organ.hormones
    return dbc.Card(
        dbc.CardBody([
            html.Div(name, style={"color": GOLD, "fontWeight": 700, "fontSize": 13}),
            dbc.Progress(value=v, color="success" if v > 70 else "warning" if v > 45 else "danger", style={"height": 8, "marginTop": 8}),
            html.Div(f"Vitality {v:.0f}%", style={"color": TXT, "fontSize": 12, "marginTop": 6}),
            dbc.Progress(value=a, color="info" if a > 70 else "primary" if a > 40 else "secondary", style={"height": 8, "marginTop": 8}),
            html.Div(f"Arousal {a:.0f}%", style={"color": MUT, "fontSize": 12, "marginTop": 6}),
            html.Div(f"Dopamine {h.get('dopamine',0):.2f} | Cortisol {h.get('cortisol',0):.2f} | Serotonin {h.get('serotonin',0):.2f}",
                     style={"color": MUT, "fontSize": 11, "marginTop": 8, "lineHeight": 1.35}),
        ]),
        style={"background": CARD, "border": f"1px solid {LINE}", "borderRadius": 6},
    )


def build_live_tab():
    open_pos = get_open_positions()
    closed = get_closed_positions(limit=12)
    rows = []
    for p in open_pos:
        rows.append(html.Tr([
            html.Td(p["symbol"]), html.Td(p["side"]), html.Td(money(p["entry"])), html.Td(f'{p["qty"]:.4f}'),
            html.Td(money(p["notional"])), html.Td(str(p["leverage"])), html.Td(money(p["stop"])), html.Td(money(p["trail"])),
            html.Td(money(p["take_profit"])), html.Td(p["opened_at"][:19].replace("T", " ")),
        ]))
    table = dbc.Table([
        html.Thead(html.Tr([html.Th(x) for x in ["Symbol", "Side", "Entry", "Qty", "Notional", "Lev", "Stop", "Trail", "TP", "Opened"]])),
        html.Tbody(rows or [html.Tr(html.Td("No active positions", colSpan=10, style={"color": MUT}))])
    ], bordered=False, hover=True, responsive=True, size="sm", style={"color": TXT, "fontSize": 12})

    history_rows = []
    for p in closed:
        pnl_color = UP if (p["pnl"] or 0) >= 0 else DN
        history_rows.append(html.Tr([
            html.Td(p["symbol"]), html.Td(p["side"]), html.Td(money(p["entry"])), html.Td(money(p["exit"] or 0)),
            html.Td(html.Span(money(p["pnl"] or 0), style={"color": pnl_color})),
            html.Td(p["opened_at"][:19].replace("T", " ")), html.Td((p["closed_at"] or "")[:19].replace("T", " ")),
        ]))
    history = dbc.Table([
        html.Thead(html.Tr([html.Th(x) for x in ["Symbol", "Side", "Entry", "Exit", "PnL", "Opened", "Closed"]])),
        html.Tbody(history_rows or [html.Tr(html.Td("No closed trades yet", colSpan=7, style={"color": MUT}))])
    ], bordered=False, hover=True, responsive=True, size="sm", style={"color": TXT, "fontSize": 12})

    return html.Div([
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Active Positions", style={"color": GOLD, "fontWeight": 700}), table
            ]), style={"background": CARD, "border": f"1px solid {LINE}"}), md=8),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Capital Pulse", style={"color": GOLD, "fontWeight": 700}),
                html.Div(id="capital-summary", style={"color": TXT, "marginTop": 10, "lineHeight": 1.7}),
            ]), style={"background": CARD, "border": f"1px solid {LINE}"}), md=4),
        ], className="g-2"),
        html.Div(style={"height": 10}),
        dbc.Card(dbc.CardBody([
            html.Div("Recent Closed Trades", style={"color": GOLD, "fontWeight": 700, "marginBottom": 6}), history
        ]), style={"background": CARD, "border": f"1px solid {LINE}"}),
    ])


def build_organs_tab():
    grid = dbc.Row([dbc.Col(organ_card(name, ORGANS[name]), md=4, lg=3, className="mb-2") for name in ORGANS_ORDER], className="g-2")
    return html.Div([
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Organ Vital Signals", style={"color": GOLD, "fontWeight": 700}),
                html.Div("Seven organs share state through hormones and arousal.", style={"color": MUT, "fontSize": 12, "marginTop": 4}),
            ]), style={"background": CARD, "border": f"1px solid {LINE}"}), md=12),
        ]),
        html.Div(style={"height": 10}),
        grid,
    ])


def build_pack_tab(rows: List[dict]):
    if not rows:
        return html.Div("No scan data.", style={"color": MUT})
    cards = []
    for r in rows:
        consensus = float(r.get("consensus", 0))
        color = UP if r["side"] == "BUY" else DN if r["side"] == "SELL" else MUT
        cards.append(dbc.Card(dbc.CardBody([
            html.Div(f"{r['symbol']}  {r['side']}  {r['regime']}", style={"color": color, "fontWeight": 700}),
            html.Div(f"Score {r['score']:.3f} | Consensus {consensus:.2f} | Price {r['price']:.4f}", style={"color": TXT, "fontSize": 12, "marginTop": 6}),
            dbc.Progress(value=consensus * 100, color="success" if consensus >= 0.75 else "warning", style={"height": 8, "marginTop": 8}),
            html.Div(f"Spread {r['spread_bps']:.2f} bps | Momentum {r['features'].get('momentum',0):.4f} | Volume surge {r['features'].get('vol_surge',0):.2f}",
                     style={"color": MUT, "fontSize": 11, "marginTop": 6}),
        ]), style={"background": CARD, "border": f"1px solid {LINE}"}))
    return html.Div([dbc.Row([dbc.Col(c, md=6, className="mb-2") for c in cards], className="g-2")])


def build_prey_tab(rows: List[dict]):
    if not rows:
        return html.Div("No prey detected.", style={"color": MUT})
    fig = go.Figure()
    syms = [r["symbol"] for r in rows]
    scores = [r["score"] for r in rows]
    colors = [UP if r["side"] == "BUY" else DN for r in rows]
    fig.add_bar(x=syms, y=scores, marker_color=colors)
    fig_theme(fig, "Prey Scan Score")
    fig.update_yaxes(title_text="score")
    fig.update_xaxes(title_text="symbol")

    rows_html = []
    for r in rows:
        rows_html.append(html.Tr([
            html.Td(r["symbol"]), html.Td(r["side"]), html.Td(r["regime"]), html.Td(f'{r["consensus"]:.2f}'),
            html.Td(f'{r["score"]:.3f}'), html.Td(money(r["price"])), html.Td(f'{r["spread_bps"]:.2f}'),
        ]))
    table = dbc.Table([
        html.Thead(html.Tr([html.Th(x) for x in ["Symbol", "Side", "Regime", "Consensus", "Score", "Price", "Spread bps"]])),
        html.Tbody(rows_html)
    ], bordered=False, hover=True, responsive=True, size="sm", style={"color": TXT, "fontSize": 12})

    return html.Div([
        dbc.Row([
            dbc.Col(dcc.Graph(figure=fig, config={"displaylogo": False}), md=6),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Top Opportunities", style={"color": GOLD, "fontWeight": 700, "marginBottom": 8}), table
            ]), style={"background": CARD, "border": f"1px solid {LINE}"}), md=6),
        ], className="g-2")
    ])


def build_evolution_tab():
    df = get_equity_history(limit=700)
    if df.empty:
        df = pd.DataFrame({"ts": [now_utc()], "equity": [INITIAL_CAPITAL], "cash": [INITIAL_CAPITAL], "open_pnl": [0.0], "open_n": [0]})
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["ts"], y=df["equity"], mode="lines", name="Equity", line=dict(color=GOLD, width=2)))
    fig.add_trace(go.Scatter(x=df["ts"], y=df["cash"], mode="lines", name="Cash", line=dict(color=CYAN, width=1.5)))
    fig.add_trace(go.Scatter(x=df["ts"], y=df["open_pnl"], mode="lines", name="Open PnL", line=dict(color=UP, width=1.5)))
    fig_theme(fig, "Equity Curve from $500", height=420)
    fig.update_yaxes(title_text="USD")

    return html.Div([
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Equity Evolution", style={"color": GOLD, "fontWeight": 700}),
                html.Div(f"Start {money(INITIAL_CAPITAL)} | Current {money(HIVE.equity_last)} | Realized {money(HIVE.realized)}", style={"color": TXT, "marginTop": 8}),
            ]), style={"background": CARD, "border": f"1px solid {LINE}"}), md=12),
        ]),
        html.Div(style={"height": 10}),
        dcc.Graph(figure=fig, config={"displaylogo": False}),
    ])


def build_nervous_tab():
    conn = db_conn()
    rows = conn.execute("SELECT ts, symbol, side, consensus, accepted, reason FROM decisions ORDER BY id DESC LIMIT 120").fetchall()
    conn.close()
    if not rows:
        log_table = html.Div("No decisions logged yet.", style={"color": MUT})
    else:
        log_table = dbc.Table([
            html.Thead(html.Tr([html.Th(x) for x in ["Time", "Symbol", "Side", "Consensus", "Accepted", "Reason"]])),
            html.Tbody([html.Tr([
                html.Td(r[0][:19].replace("T", " ")), html.Td(r[1]), html.Td(r[2]), html.Td(f"{float(r[3]):.2f}"),
                html.Td("YES" if r[4] else "NO"), html.Td(r[5]),
            ]) for r in rows])
        ], bordered=False, hover=True, responsive=True, size="sm", style={"color": TXT, "fontSize": 12})
    return html.Div([
        dbc.Card(dbc.CardBody([
            html.Div("Nervous System Logs", style={"color": GOLD, "fontWeight": 700, "marginBottom": 8}),
            log_table,
        ]), style={"background": CARD, "border": f"1px solid {LINE}"})
    ])


def build_vitals_summary() -> str:
    vals = [o.vitality for o in ORGANS.values()]
    ars = [o.arousal for o in ORGANS.values()]
    return f"Vitals {np.mean(vals):.0f}% | Arousal {np.mean(ars):.0f}% | Active positions {open_positions_count()} | Capital {money(HIVE.equity_last)}"


def build_equity_small_fig():
    df = get_equity_history(limit=150)
    fig = go.Figure()
    if not df.empty:
        fig.add_trace(go.Scatter(x=df["ts"], y=df["equity"], mode="lines", line=dict(color=GOLD, width=2), name="Equity"))
    else:
        fig.add_trace(go.Scatter(x=[0, 1], y=[INITIAL_CAPITAL, INITIAL_CAPITAL], mode="lines", line=dict(color=GOLD, width=2), name="Equity"))
    fig_theme(fig, "", height=280)
    fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
    return fig


# -----------------------------------------------------------------------------
# Dash app
# -----------------------------------------------------------------------------
init_db()
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])
app.title = APP_TITLE
server = app.server

app.layout = html.Div([
    dcc.Interval(id="scout-interval", interval=SCOUT_INTERVAL_MS, n_intervals=0),
    dcc.Interval(id="hunt-interval", interval=HUNT_INTERVAL_MS, n_intervals=0),
    dcc.Store(id="scan-store", data={"rows": [], "prices": {}}),
    dcc.Store(id="ui-store", data={}),
    dbc.Container([
        dbc.Row([
            dbc.Col(html.Div([
                html.Div(APP_TITLE, style={"color": GOLD, "fontWeight": 800, "fontSize": 24, "letterSpacing": 0}),
                html.Div("Year 2500 institutional scalp organism with biological perception", style={"color": MUT, "fontSize": 12, "marginTop": 4}),
            ]), md=5),
            dbc.Col(html.Div(id="top-status", style={"color": TXT, "textAlign": "right", "fontSize": 12, "lineHeight": 1.6}), md=7),
        ], align="center", className="g-2", style={"paddingTop": 12, "paddingBottom": 10}),
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Control Surface", style={"color": GOLD, "fontWeight": 700, "marginBottom": 8}),
                dbc.Row([
                    dbc.Col(dbc.Input(id="symbol-input", value=DEFAULT_SYMBOL, type="text"), md=3),
                    dbc.Col(dbc.Select(id="category-dropdown", value=DEFAULT_CATEGORY, options=[{"label": "linear", "value": "linear"}, {"label": "spot", "value": "spot"}]), md=3),
                    dbc.Col(dbc.Select(id="interval-dropdown", value=DEFAULT_INTERVAL, options=[{"label": "15s", "value": "1"}, {"label": "1m", "value": "1m"}, {"label": "5m", "value": "5"}]), md=2),
                    dbc.Col(dbc.Button([html.I(className="bi bi-lightning-charge"), html.Span(" Hunt")], id="manual-hunt-btn", color="warning", className="w-100"), md=2),
                    dbc.Col(dbc.Button([html.I(className="bi bi-trash"), html.Span(" Clear")], id="reset-btn", color="danger", className="w-100"), md=2),
                ], className="g-2"),
                html.Div(id="control-note", style={"color": MUT, "fontSize": 11, "marginTop": 8}),
            ]), style={"background": CARD, "border": f"1px solid {LINE}"}), md=12),
        ], className="g-2"),
        html.Div(style={"height": 10}),
        dbc.Tabs(id="main-tabs", active_tab="tab-live", children=[
            dbc.Tab(label="LIVE HUNT", tab_id="tab-live", children=[html.Div(id="tab-live-body", style={"paddingTop": 12})]),
            dbc.Tab(label="ORGAN VITALS", tab_id="tab-organs", children=[html.Div(id="tab-organs-body", style={"paddingTop": 12})]),
            dbc.Tab(label="PACK MIND", tab_id="tab-pack", children=[html.Div(id="tab-pack-body", style={"paddingTop": 12})]),
            dbc.Tab(label="PREY SCAN", tab_id="tab-prey", children=[html.Div(id="tab-prey-body", style={"paddingTop": 12})]),
            dbc.Tab(label="EVOLUTION", tab_id="tab-evo", children=[html.Div(id="tab-evo-body", style={"paddingTop": 12})]),
            dbc.Tab(label="NERVOUS SYSTEM", tab_id="tab-neural", children=[html.Div(id="tab-neural-body", style={"paddingTop": 12})]),
        ]),
        html.Div(style={"height": 10}),
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Organ field", style={"color": GOLD, "fontWeight": 700}),
                dcc.Graph(id="mini-equity", config={"displaylogo": False}, style={"height": 280}),
            ]), style={"background": CARD, "border": f"1px solid {LINE}"}), md=4),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Scalp engine", style={"color": GOLD, "fontWeight": 700}),
                html.Div(id="engine-status", style={"color": TXT, "marginTop": 10, "lineHeight": 1.8, "fontSize": 13}),
            ]), style={"background": CARD, "border": f"1px solid {LINE}"}), md=8),
        ], className="g-2"),
        html.Div(style={"height": 12}),
    ], fluid=True, style={"background": BG, "minHeight": "100vh", "paddingBottom": 18}),
], style={"background": BG})


# -----------------------------------------------------------------------------
# Callbacks
# -----------------------------------------------------------------------------
@app.callback(
    Output("scan-store", "data"),
    Output("control-note", "children"),
    Input("scout-interval", "n_intervals"),
    Input("manual-hunt-btn", "n_clicks"),
    Input("reset-btn", "n_clicks"),
    State("category-dropdown", "value"),
    State("interval-dropdown", "value"),
    State("scan-store", "data"),
)
def update_scan(n_int, manual_hunt, reset_btn, category, interval, scan_store):
    trigger = ctx.triggered_id
    scan_store = scan_store or {"rows": [], "prices": {}}
    if trigger == "reset-btn":
        state_set("manual_note", "reset")
        return {"rows": [], "prices": {}}, "Memory cleared for current session."

    rows, prices = scout_pack(category=category or DEFAULT_CATEGORY, interval=interval or DEFAULT_INTERVAL)
    note = f"Scanned {len(rows)} symbols every {SCOUT_INTERVAL_MS//1000}s. Best prey: {rows[0]['symbol']} {rows[0]['side']} {rows[0]['score']:.3f}" if rows else "No prey found."
    return {"rows": rows, "prices": prices}, note


@app.callback(
    Output("tab-live-body", "children"),
    Output("tab-organs-body", "children"),
    Output("tab-pack-body", "children"),
    Output("tab-prey-body", "children"),
    Output("tab-evo-body", "children"),
    Output("tab-neural-body", "children"),
    Output("top-status", "children"),
    Output("mini-equity", "figure"),
    Output("engine-status", "children"),
    Input("scan-store", "data"),
    Input("hunt-interval", "n_intervals"),
    Input("main-tabs", "active_tab"),
    State("symbol-input", "value"),
)
def refresh_views(scan_store, n_hunt, active_tab, symbol_input):
    scan_store = scan_store or {"rows": [], "prices": {}}
    rows = scan_store.get("rows") or []
    prices = scan_store.get("prices") or {}

    # Keep the equity line alive with a lightweight mark-to-market snapshot.
    open_positions = get_open_positions()
    open_pnl = 0.0
    for pos in open_positions:
        last = prices.get(pos["symbol"])
        if last is None:
            continue
        direction = 1.0 if pos["side"] == "BUY" else -1.0
        open_pnl += (last - pos["entry"]) * pos["qty"] * direction
    HIVE.equity_last = HIVE.cash + open_pnl
    record_equity(HIVE.equity_last, HIVE.cash, open_pnl, len(open_positions))

    # Manage open trades first.
    closed = manage_positions(prices)

    # Decide and open immediately if consensus is strong.
    top = hunt(rows)
    if top is not None:
        available = MAX_ACTIVE_POSITIONS - len(get_open_positions())
        if available > 0:
            price = top["price"]
            pos = open_position(
                symbol=top["symbol"],
                side=top["side"],
                price=price,
                consensus=top.get("consensus", 0.0),
                organs=top.get("organs", {}),
                reason=f"{top['regime']} consensus={top['consensus']:.2f}",
                metadata=top.get("features", {}),
            )
            insert_decision(top["symbol"], top["side"], top.get("consensus", 0.0), True,
                            "Hunter pack accepted prey", top.get("organs", {}), top.get("features", {}))
            HIVE.logs.append(f"Opened {pos['side']} {pos['symbol']} @ {pos['entry']:.4f}")
        else:
            insert_decision(top["symbol"], top["side"], top.get("consensus", 0.0), False,
                            "Capacity reached", top.get("organs", {}), top.get("features", {}))
    elif rows:
        insert_decision(rows[0]["symbol"], rows[0]["side"], rows[0].get("consensus", 0.0), False,
                        "Consensus below threshold", rows[0].get("organs", {}), rows[0].get("features", {}))

    save_organ_snapshot({k: asdict(v) for k, v in ORGANS.items()})
    save_scan_cache(rows[:5])

    top_status = html.Div([
        html.Div(f"Live {now_utc()[:19].replace('T', ' ')} UTC", style={"fontWeight": 700}),
        html.Div(build_vitals_summary()),
    ])

    engine_status = [
        html.Div(f"Scout pack: {len(rows)} symbols / {SCOUT_INTERVAL_MS//1000}s", style={"marginBottom": 4}),
        html.Div(f"Active positions: {open_positions_count()} | Closed this pass: {len(closed)}", style={"marginBottom": 4}),
        html.Div(f"Capital: {money(HIVE.cash)} | Equity: {money(HIVE.equity_last)} | Realized: {money(HIVE.realized)}", style={"marginBottom": 4}),
        html.Div(f"Decision latency target: <500ms from consensus to order placement scaffold", style={"marginBottom": 4}),
        html.Div(f"Universe: {' ,'.join(SCOUT_SYMBOLS)}", style={"color": MUT, "fontSize": 12}),
    ]

    return (
        build_live_tab(),
        build_organs_tab(),
        build_pack_tab(rows),
        build_prey_tab(rows),
        build_evolution_tab(),
        build_nervous_tab(),
        top_status,
        build_equity_small_fig(),
        engine_status,
    )


@app.callback(
    Output("symbol-input", "value"),
    Input("manual-hunt-btn", "n_clicks"),
    State("symbol-input", "value"),
    prevent_initial_call=True,
)
def noop_symbol(btn, value):
    return value or DEFAULT_SYMBOL


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def bootstrap_state():
    cash = state_get("cash", INITIAL_CAPITAL)
    HIVE.cash = float(cash)
    HIVE.realized = float(state_get("realized", 0.0))
    HIVE.equity_last = float(state_get("equity_last", INITIAL_CAPITAL))
    hist = state_get("logs", [])
    HIVE.logs = hist if isinstance(hist, list) else []
    saved_organs = state_get("organs", None)
    if isinstance(saved_organs, dict):
        for name, payload in saved_organs.items():
            if name in ORGANS and isinstance(payload, dict):
                ORGANS[name].vitality = float(payload.get("vitality", ORGANS[name].vitality))
                ORGANS[name].arousal = float(payload.get("arousal", ORGANS[name].arousal))
                ORGANS[name].hormones.update(payload.get("hormones", {}))


def persist_state():
    state_set("cash", HIVE.cash)
    state_set("realized", HIVE.realized)
    state_set("equity_last", HIVE.equity_last)
    state_set("logs", HIVE.logs[-200:])
    state_set("organs", {k: asdict(v) for k, v in ORGANS.items()})


bootstrap_state()

if __name__ == "__main__":
    try:
        log_event("Hive Synapse v10 boot")
        persist_state()
        app.run(debug=True, host="0.0.0.0", port=8060, use_reloader=False)
    finally:
        persist_state()
