# -*- coding: utf-8 -*-
"""HIVE PREDATOR v10.0

Updated trading bot with:
- explicit live trade entry analysis for the organism vote model
- spread and commission handled in execution and PnL
- realized vs unrealized PnL separation
- margin availability enforcement
- dedicated Journal tab
- backtest tab with 5000-candle live-style simulation and no look-ahead bias
"""

import json
import math
import os
import sqlite3
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import dash
from dash import Input, Output, State, dcc, html
import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests

# Optional Persian text shaping
try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    def rtl_text(value):
        try:
            return get_display(arabic_reshaper.reshape(str(value)))
        except Exception:
            return str(value)
except Exception:

    def rtl_text(value):
        return str(value)

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
BG = "#05080f"
PANEL = "rgba(8, 14, 26, 0.94)"
PANEL_SOLID = "#0a101f"
TXT = "#eaf2ff"
MUT = "#8ea2c7"
GOLD = "#f5c542"
CYAN = "#14d9ff"
UP = "#00ffd0"
DN = "#ff2a6d"
NEON = "#7c5cff"
LINE = "#1a253a"

LEVERAGE = 20
INITIAL_CAPITAL = 500.0
MAX_POSITIONS = 5
MAX_TOTAL_MARGIN_RATIO = 1.0
MAX_MARGIN_PER_TRADE_RATIO = 0.35
COMMISSION_RATE = 0.0006
SLIPPAGE_BPS = 1.0
MIN_TURNOVER_24H = 500_000
MAX_SPREAD_BPS = 5.0
RISK_PER_TRADE_BASE = 0.025
MIN_MARGIN_USD = 10.0
BACKTEST_START_CAPITAL = 500.0
BACKTEST_CANDLES = 5000
BACKTEST_SPREAD_BPS = 2.0
DEFAULT_BACKTEST_SYMBOL = "BTCUSDT"
DEFAULT_INTERVAL = "5"

REST_ENDPOINTS = ["https://api.bybit.com", "https://api.bytick.com"]
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "HivePredator/10.0", "Accept": "application/json"})
_rate_lock = threading.Lock()
_last_req = 0.0
_active_base = {"url": None}

DB_PATH = Path(__file__).resolve().with_name("hive_predator_v10.db")

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def now_utc():
    return datetime.now(timezone.utc).isoformat()


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def safe_json(value, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def pct_to_bps(value):
    return value * 10000.0


def commission_fee(notional_usd):
    return abs(notional_usd) * COMMISSION_RATE


def synth_quotes(mid_price, spread_bps=BACKTEST_SPREAD_BPS):
    half = (spread_bps / 10000.0) / 2.0
    return {
        "bid": mid_price * (1.0 - half),
        "ask": mid_price * (1.0 + half),
        "spread_bps": spread_bps,
    }


def round_price(value, digits=6):
    return round(float(value), digits)


def save_organism_state(orgs):
    db_set("organisms", [org.to_state() for org in orgs])


def load_organism_state(default_orgs):
    raw = db_get("organisms", None)
    if not raw:
        return default_orgs
    items = safe_json(raw, None)
    if not isinstance(items, list):
        return default_orgs
    loaded = []
    for item in items:
        try:
            loaded.append(PredatorOrganism.from_state(item))
        except Exception:
            continue
    return loaded or default_orgs


# ----------------------------------------------------------------------------
# Market data
# ----------------------------------------------------------------------------

def bybit_get(path, params, timeout=8):
    global _last_req
    with _rate_lock:
        elapsed = time.time() - _last_req
        if elapsed < 0.05:
            time.sleep(0.05 - elapsed)
        _last_req = time.time()

    bases = []
    if _active_base["url"]:
        bases.append(_active_base["url"])
    bases.extend([u for u in REST_ENDPOINTS if u != _active_base["url"]])

    for base in bases:
        try:
            resp = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if resp.status_code in (403, 451):
                continue
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("retCode") == 0:
                _active_base["url"] = base
                return payload
        except Exception:
            continue
    return None


def get_all_tickers():
    payload = bybit_get("/v5/market/tickers", {"category": "linear"})
    items = (payload or {}).get("result", {}).get("list") or []
    out = {}
    for item in items:
        symbol = item.get("symbol", "")
        if not symbol.endswith("USDT"):
            continue
        try:
            out[symbol] = {
                "last": float(item.get("lastPrice") or 0),
                "bid": float(item.get("bid1Price") or item.get("lastPrice") or 0),
                "ask": float(item.get("ask1Price") or item.get("lastPrice") or 0),
                "vol24": float(item.get("volume24h") or 0),
                "turn24": float(item.get("turnover24h") or 0),
                "chg": float(item.get("price24hPcnt") or 0),
            }
        except Exception:
            continue
    return out


def get_ticker(symbol):
    return get_all_tickers().get(symbol)


def get_klines(symbol, interval=DEFAULT_INTERVAL, limit=200, category="linear"):
    payload = bybit_get(
        "/v5/market/kline",
        {"category": category, "symbol": symbol, "interval": interval, "limit": limit},
    )
    rows = (payload or {}).get("result", {}).get("list") or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    for col in ["open", "high", "low", "close", "volume", "turnover"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["ts"] = pd.to_numeric(df["ts"], errors="coerce")
    df = df.dropna().sort_values("ts").reset_index(drop=True)
    return df


def fetch_klines_history(symbol, interval=DEFAULT_INTERVAL, total=BACKTEST_CANDLES, category="linear"):
    all_rows = []
    end_ts = int(time.time() * 1000)
    seen = set()

    while len(all_rows) < total:
        limit = min(1000, total - len(all_rows))
        payload = bybit_get(
            "/v5/market/kline",
            {
                "category": category,
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
                "end": end_ts,
            },
            timeout=10,
        )
        rows = (payload or {}).get("result", {}).get("list") or []
        if not rows:
            break
        rows = sorted(rows, key=lambda r: int(r[0]))

        batch = []
        for row in rows:
            ts = int(row[0])
            if ts in seen:
                continue
            seen.add(ts)
            batch.append(row)

        if not batch:
            break

        all_rows = batch + all_rows
        end_ts = int(batch[0][0]) - 1
        if len(batch) < limit:
            break

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    for col in ["open", "high", "low", "close", "volume", "turnover"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["ts"] = pd.to_numeric(df["ts"], errors="coerce")
    df = df.dropna().sort_values("ts").reset_index(drop=True)
    if len(df) > total:
        df = df.iloc[-total:].reset_index(drop=True)
    return df


# ----------------------------------------------------------------------------
# Analytics
# ----------------------------------------------------------------------------

def compute_rsi(close, length=5):
    delta = pd.Series(close).diff()
    gain = delta.clip(lower=0).rolling(length).mean()
    loss = (-delta.clip(upper=0)).rolling(length).mean()
    rs = gain / (loss + 1e-12)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def detect_regime(df):
    if df is None or len(df) < 20:
        return "RANGING"
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    prev_close = np.r_[close[0], close[:-1]]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = pd.Series(tr).rolling(14).mean().iloc[-1]
    atr_pct = float(atr / (close[-1] + 1e-12))

    if atr_pct > 0.012:
        return "HIGH_VOL"

    ma_fast = pd.Series(close).rolling(6).mean().iloc[-1]
    ma_slow = pd.Series(close).rolling(18).mean().iloc[-1]
    slope = float((close[-1] - close[-8]) / (close[-8] + 1e-12))

    if slope > 0.002 and ma_fast > ma_slow:
        return "TREND_UP"
    if slope < -0.002 and ma_fast < ma_slow:
        return "TREND_DOWN"
    return "RANGING"


REGIME_PARAMS = {
    "TREND_UP": {"tp": 0.0050, "sl": 0.0025, "risk_mult": 1.3, "trail_mult": 1.5, "partial_at": 0.0028},
    "TREND_DOWN": {"tp": 0.0050, "sl": 0.0025, "risk_mult": 1.3, "trail_mult": 1.5, "partial_at": 0.0028},
    "RANGING": {"tp": 0.0032, "sl": 0.0018, "risk_mult": 1.0, "trail_mult": 1.1, "partial_at": 0.0018},
    "HIGH_VOL": {"tp": 0.0070, "sl": 0.0038, "risk_mult": 0.9, "trail_mult": 1.8, "partial_at": 0.0038},
}


def extract_features(df, ticker):
    if df is None or len(df) < 20 or ticker is None:
        return None
    close = df["close"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)

    mom = float(np.clip((close[-1] - close[-2]) / (close[-2] + 1e-12) * 40.0, -1.0, 1.0))
    vol_surge = float(np.clip((vol[-1] / (vol[-8:].mean() + 1e-12) - 1.0) * 3.0, -1.0, 1.0))

    mid = float(ticker["last"])
    spread_bps = float((ticker["ask"] - ticker["bid"]) / (mid + 1e-12) * 10000.0)
    spread_q = float(np.clip(1.0 - spread_bps / MAX_SPREAD_BPS, 0.0, 1.0))

    rsi = compute_rsi(close, 5)
    if rsi < 30:
        rsi_ext = 1.5
    elif rsi > 70:
        rsi_ext = -1.5
    elif rsi < 40:
        rsi_ext = 0.8
    elif rsi > 60:
        rsi_ext = -0.8
    else:
        rsi_ext = 0.0

    prev_close = np.r_[close[0], close[:-1]]
    prev_close_series = pd.Series(prev_close)
    tr = np.maximum(df["high"].to_numpy(dtype=float) - df["low"].to_numpy(dtype=float), np.maximum(np.abs(df["high"].to_numpy(dtype=float) - prev_close), np.abs(df["low"].to_numpy(dtype=float) - prev_close)))
    atr = pd.Series(tr).rolling(14).mean().iloc[-1]
    atr_pct = float(atr / (close[-1] + 1e-12))

    return {
        "mom": mom,
        "vol_surge": vol_surge,
        "spread_q": spread_q,
        "spread_bps": spread_bps,
        "rsi_ext": rsi_ext,
        "atr_pct": atr_pct,
        "rsi": float(rsi),
    }


# ----------------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            side TEXT,
            status TEXT,
            entry_price REAL,
            exit_price REAL,
            margin_usd REAL,
            notional_usd REAL,
            leverage INTEGER,
            entry_fee REAL,
            exit_fee REAL,
            spread_bps REAL,
            realized_pnl REAL,
            unrealized_pnl REAL,
            gross_pnl REAL,
            entry_time TEXT,
            exit_time TEXT,
            reason TEXT,
            votes TEXT,
            regime TEXT,
            partials TEXT,
            trail_stop REAL,
            entry_bid REAL,
            entry_ask REAL,
            exit_bid REAL,
            exit_ask REAL,
            close_reason TEXT,
            remaining_margin_usd REAL DEFAULT 0,
            remaining_notional_usd REAL DEFAULT 0
        )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            level TEXT,
            kind TEXT,
            symbol TEXT,
            message TEXT,
            payload TEXT
        )"""
    )
    cur.execute("""CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)""")
    cur.execute(
        """CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            symbol TEXT,
            regime TEXT,
            side TEXT,
            outcome REAL,
            lesson TEXT
        )"""
    )

    # Backward-compatible column migration for existing databases.
    try:
        cur.execute("ALTER TABLE trades ADD COLUMN remaining_margin_usd REAL DEFAULT 0")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE trades ADD COLUMN remaining_notional_usd REAL DEFAULT 0")
    except Exception:
        pass

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


def db_set(key, value):
    conn = sqlite3.connect(DB_PATH)
    raw = json.dumps(value) if not isinstance(value, str) else value
    conn.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)", (key, raw))
    conn.commit()
    conn.close()


def write_journal(level, kind, symbol, message, payload=None):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO journal (ts, level, kind, symbol, message, payload) VALUES (?, ?, ?, ?, ?, ?)",
        (now_utc(), level, kind, symbol, message, json.dumps(payload or {})),
    )
    conn.commit()
    conn.close()


def get_recent_journal(limit=40):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT ts, level, kind, symbol, message, payload FROM journal ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return rows


def get_open_trades():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT id, symbol, side, status, entry_price, exit_price, margin_usd, notional_usd, leverage,
                  entry_fee, exit_fee, spread_bps, realized_pnl, unrealized_pnl, gross_pnl,
                  entry_time, exit_time, reason, votes, regime, partials, trail_stop,
                  entry_bid, entry_ask, exit_bid, exit_ask, close_reason
           FROM trades WHERE status='open' ORDER BY id ASC"""
    ).fetchall()
    conn.close()
    return [trade_from_row(r) for r in rows]


def get_closed_trades(limit=100):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT id, symbol, side, status, entry_price, exit_price, margin_usd, notional_usd, leverage,
                  entry_fee, exit_fee, spread_bps, realized_pnl, unrealized_pnl, gross_pnl,
                  entry_time, exit_time, reason, votes, regime, partials, trail_stop,
                  entry_bid, entry_ask, exit_bid, exit_ask, close_reason
           FROM trades WHERE status='closed' ORDER BY id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [trade_from_row(r) for r in rows]


def trade_from_row(row):
    return {
        "id": row[0],
        "symbol": row[1],
        "side": row[2],
        "status": row[3],
        "entry_price": row[4],
        "exit_price": row[5],
        "margin_usd": row[6],
        "notional_usd": row[7],
        "leverage": row[8],
        "entry_fee": row[9],
        "exit_fee": row[10],
        "spread_bps": row[11],
        "realized_pnl": row[12],
        "unrealized_pnl": row[13],
        "gross_pnl": row[14],
        "entry_time": row[15],
        "exit_time": row[16],
        "reason": row[17],
        "votes": safe_json(row[18], {}),
        "regime": row[19],
        "partials": safe_json(row[20], []),
        "trail_stop": row[21],
        "entry_bid": row[22],
        "entry_ask": row[23],
        "exit_bid": row[24],
        "exit_ask": row[25],
        "close_reason": row[26],
    }


def save_trade(trade):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO trades (
            symbol, side, status, entry_price, exit_price, margin_usd, notional_usd, leverage,
            entry_fee, exit_fee, spread_bps, realized_pnl, unrealized_pnl, gross_pnl,
            entry_time, exit_time, reason, votes, regime, partials, trail_stop,
            entry_bid, entry_ask, exit_bid, exit_ask, close_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            trade["symbol"],
            trade["side"],
            trade["status"],
            trade["entry_price"],
            trade.get("exit_price"),
            trade["margin_usd"],
            trade["notional_usd"],
            trade["leverage"],
            trade["entry_fee"],
            trade.get("exit_fee", 0.0),
            trade["spread_bps"],
            trade.get("realized_pnl", 0.0),
            trade.get("unrealized_pnl", 0.0),
            trade.get("gross_pnl", 0.0),
            trade["entry_time"],
            trade.get("exit_time"),
            trade["reason"],
            json.dumps(trade.get("votes", {})),
            trade["regime"],
            json.dumps(trade.get("partials", [])),
            trade.get("trail_stop"),
            trade.get("entry_bid"),
            trade.get("entry_ask"),
            trade.get("exit_bid"),
            trade.get("exit_ask"),
            trade.get("close_reason"),
        ),
    )
    conn.commit()
    trade_id = cur.lastrowid
    conn.close()
    return trade_id


def update_trade(trade_id, **fields):
    if not fields:
        return
    sets = []
    vals = []
    for key, value in fields.items():
        sets.append(f"{key}=?")
        if isinstance(value, (dict, list)):
            vals.append(json.dumps(value))
        else:
            vals.append(value)
    vals.append(trade_id)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(f"UPDATE trades SET {', '.join(sets)} WHERE id=?", vals)
    conn.commit()
    conn.close()


# ----------------------------------------------------------------------------
# Organisms
# ----------------------------------------------------------------------------

class PredatorOrganism:
    def __init__(self, name, role, base_weight=1.0):
        self.name = name
        self.role = role
        self.base_weight = base_weight
        self.last_vote = "LONG"
        self.conviction = 0.0
        self.regime_score = {"TREND_UP": 0.0, "TREND_DOWN": 0.0, "RANGING": 0.0, "HIGH_VOL": 0.0}
        self.regime_trades = {"TREND_UP": 1, "TREND_DOWN": 1, "RANGING": 1, "HIGH_VOL": 1}

    @property
    def weight(self):
        total_score = sum(self.regime_score.values())
        total_trades = sum(self.regime_trades.values())
        avg_accuracy = total_score / max(1, total_trades)
        return clamp(self.base_weight * (1.0 + avg_accuracy * 2.5), 0.6, 3.5)

    def learn(self, regime, reward):
        alpha = 0.25
        self.regime_score[regime] = (1 - alpha) * self.regime_score[regime] + alpha * reward
        self.regime_trades[regime] += 1

    def evaluate(self, feat, regime):
        if self.role == "ALPHA_SNIPER":
            force = (feat["rsi_ext"] * 2.5) + (feat["mom"] * 4.0)
        elif self.role == "HFT_SCALPER":
            force = (feat["vol_surge"] * 5.0) + (feat["mom"] * 3.0)
        elif self.role == "FLOW":
            force = (feat["vol_surge"] * 3.0) + (feat["mom"] * 2.5) + (feat["rsi_ext"] * 1.5)
        else:
            force = feat["mom"] * 5.0 + feat["vol_surge"] * 2.0

        if force >= 0:
            self.last_vote = "LONG"
            raw_score = abs(force) * self.weight
        else:
            self.last_vote = "SHORT"
            raw_score = -abs(force) * self.weight

        self.conviction = clamp(abs(force) / 6.0, 0.15, 1.0)
        regime_accuracy = self.regime_score[regime] / max(1, self.regime_trades[regime])
        regime_multiplier = clamp(1.0 + regime_accuracy, 0.7, 1.6)
        return raw_score * regime_multiplier

    def to_state(self):
        return {
            "name": self.name,
            "role": self.role,
            "base_weight": self.base_weight,
            "last_vote": self.last_vote,
            "conviction": self.conviction,
            "regime_score": self.regime_score,
            "regime_trades": self.regime_trades,
        }

    @classmethod
    def from_state(cls, data):
        org = cls(data.get("name", "Org"), data.get("role", "MOMENTUM"), base_weight=float(data.get("base_weight", 1.0)))
        org.last_vote = data.get("last_vote", "LONG")
        org.conviction = float(data.get("conviction", 0.0))
        org.regime_score = data.get("regime_score", org.regime_score)
        org.regime_trades = data.get("regime_trades", org.regime_trades)
        return org


# ----------------------------------------------------------------------------
# Hive engine
# ----------------------------------------------------------------------------

class PredatorHive:
    def __init__(self):
        init_db()
        self.balance = float(db_get("balance", INITIAL_CAPITAL))
        self.peak_equity = float(db_get("peak_equity", INITIAL_CAPITAL))
        self.generation = int(db_get("generation", 1))
        self.adaptive = db_get("adaptive", {"base_threshold": 0.3})
        self.orgs = [
            PredatorOrganism("Alpha", "ALPHA_SNIPER", base_weight=2.0),
            PredatorOrganism("Pulse", "HFT_SCALPER", base_weight=1.8),
            PredatorOrganism("Flux", "FLOW", base_weight=1.4),
            PredatorOrganism("Vector", "MOMENTUM", base_weight=1.2),
        ]
        self.orgs = load_organism_state(self.orgs)
        self._lock = threading.Lock()
        self.last_stats = {"scanned": 0, "cands": 0, "opened": 0, "regime_counts": {}, "last_cycle": now_utc()}
        self.heart_beat = 0
        self.latest_metrics = {
            "realized": 0.0,
            "unrealized": 0.0,
            "equity": self.balance,
            "margin_used": 0.0,
        }

    def margin_used(self):
        return sum(t["remaining_margin_usd"] for t in get_open_trades())

    def equity(self):
        open_trades = get_open_trades()
        unrealized = sum(self.unrealized_trade_pnl(t) for t in open_trades)
        margin_used = sum(t["remaining_margin_usd"] for t in open_trades)
        equity = self.balance + margin_used + unrealized
        self.peak_equity = max(self.peak_equity, equity)
        db_set("peak_equity", self.peak_equity)
        self.latest_metrics = {
            "realized": self.balance - INITIAL_CAPITAL + self.margin_used(),
            "unrealized": unrealized,
            "equity": equity,
            "margin_used": margin_used,
        }
        return equity

    def persist_learning_state(self):
        db_set("generation", self.generation)
        db_set("adaptive", self.adaptive)
        db_set("balance", self.balance)
        db_set("peak_equity", self.peak_equity)
        save_organism_state(self.orgs)

    def learn_from_outcome(self, trade, pnl, source="live"):
        reward = 1.0 if pnl > 0 else -1.0
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO memory (ts, symbol, regime, side, outcome, lesson) VALUES (?, ?, ?, ?, ?, ?)",
            (
                now_utc(),
                trade["symbol"],
                trade["regime"],
                trade["side"],
                pnl,
                f"{source.upper()}_{'WIN' if pnl > 0 else 'LOSS'}",
            ),
        )
        conn.commit()
        conn.close()

        for org in self.orgs:
            if org.name in trade.get("votes", {}):
                org.learn(trade["regime"], reward)

        if pnl > 0:
            self.adaptive["base_threshold"] = max(0.15, self.adaptive["base_threshold"] - 0.008)
        else:
            self.adaptive["base_threshold"] = min(0.40, self.adaptive["base_threshold"] + 0.012)
        self.generation += 1
        self.persist_learning_state()

    @staticmethod
    def side_sign(side):
        return 1.0 if side == "long" else -1.0

    def unrealized_trade_pnl(self, trade, market_price=None, spread_bps=None):
        if trade["status"] != "open":
            return float(trade.get("realized_pnl", 0.0))
        if market_price is None:
            ticker = get_ticker(trade["symbol"])
            if ticker is None:
                return 0.0
            market_price = float(ticker["last"])
            spread_bps = float((ticker["ask"] - ticker["bid"]) / (market_price + 1e-12) * 10000.0)
        if spread_bps is None:
            spread_bps = BACKTEST_SPREAD_BPS
        quotes = synth_quotes(market_price, spread_bps)
        if trade["side"] == "long":
            exit_price = quotes["bid"]
            gross = trade["notional_usd"] * (exit_price - trade["entry_price"]) / trade["entry_price"]
        else:
            exit_price = quotes["ask"]
            gross = trade["notional_usd"] * (trade["entry_price"] - exit_price) / trade["entry_price"]
        estimated_exit_fee = commission_fee(trade.get("remaining_notional_usd", trade.get("notional_usd", 0)))
        net_unrealized = gross - estimated_exit_fee
        return float(net_unrealized)

    def decide_predator(self, feat, regime):
        if feat is None:
            return None

        long_pool = 0.0
        short_pool = 0.0
        votes = {}
        for org in self.orgs:
            score = org.evaluate(feat, regime)
            side = "long" if org.last_vote == "LONG" else "short"
            if side == "long":
                long_pool += abs(score)
            else:
                short_pool += abs(score)
            votes[org.name] = {
                "org": org.name,
                "role": org.role,
                "side": side,
                "score": score,
                "vote": org.last_vote,
                "conviction": org.conviction,
                "weight": org.weight,
            }

        total_pool = long_pool + short_pool
        if total_pool <= 1e-12:
            return None
        dominance = abs(long_pool - short_pool) / total_pool
        if long_pool > short_pool:
            side = "long"
            final_pool = long_pool
        elif short_pool > long_pool:
            side = "short"
            final_pool = short_pool
        else:
            return None

        if final_pool <= self.adaptive["base_threshold"]:
            return None

        expected_edge_bps = dominance * 50.0
        return {
            "side": side,
            "conv": clamp(final_pool / 4.0, 0.0, 1.0),
            "dominance": dominance,
            "expected_edge_bps": expected_edge_bps,
            "votes": votes,
            "reason": " | ".join([f"{v['org']}:{v['vote']}({v['conviction']:.2f})" for v in votes.values() if v["side"] == side]),
            "regime": regime,
        }

    def current_capacity(self):
        return self.balance

    def can_open_margin(self, margin_usd, entry_fee_usd):
        if margin_usd < MIN_MARGIN_USD:
            return False
        if margin_usd + entry_fee_usd > self.balance:
            return False
        open_margin = self.margin_used()
        if open_margin + margin_usd > max(self.peak_equity, self.balance) * MAX_TOTAL_MARGIN_RATIO:
            return False
        return True

    def try_open(self, symbol, ticker, decision, feat):
        with self._lock:
            open_trades = get_open_trades()
            if len(open_trades) >= MAX_POSITIONS or any(t["symbol"] == symbol for t in open_trades):
                return False

            regime = decision["regime"]
            rp = REGIME_PARAMS.get(regime, REGIME_PARAMS["RANGING"])
            spread_bps = float((ticker["ask"] - ticker["bid"]) / (ticker["last"] + 1e-12) * 10000.0)
            cost_bps = spread_bps + (2.0 * COMMISSION_RATE * 10000.0) + SLIPPAGE_BPS
            if decision["expected_edge_bps"] <= cost_bps:
                return False
            if spread_bps > MAX_SPREAD_BPS:
                return False

            risk = RISK_PER_TRADE_BASE * rp["risk_mult"] * (0.75 + 0.25 * decision["conv"])
            stop_pct = rp["sl"]
            margin_by_risk = (self.balance * risk) / max(stop_pct * LEVERAGE, 1e-12)
            margin_cap = self.balance * MAX_MARGIN_PER_TRADE_RATIO
            margin_usd = min(margin_by_risk, margin_cap)
            notional_usd = margin_usd * LEVERAGE
            entry_fee = commission_fee(notional_usd)
            available_balance = self.balance
            required_margin = margin_usd + entry_fee
            if available_balance < required_margin:
                write_journal("WARN", "MARGIN_GUARD", symbol, "Margin Guard triggered", {"available_balance": available_balance, "required_margin": required_margin})
                return False
            if not self.can_open_margin(margin_usd, entry_fee):
                return False

            bid = float(ticker["bid"])
            ask = float(ticker["ask"])
            mid = float(ticker["last"])
            half_spread = (ask - bid) / 2.0
            slip = mid * (SLIPPAGE_BPS / 10000.0)
            if decision["side"] == "long":
                entry_price = ask + slip
                trail_stop = entry_price * (1.0 - rp["sl"] * 1.1)
            else:
                entry_price = bid - slip
                trail_stop = entry_price * (1.0 + rp["sl"] * 1.1)

            self.balance -= (margin_usd + entry_fee)
            db_set("balance", self.balance)

            trade = {
                "symbol": symbol,
                "side": decision["side"],
                "status": "open",
                "entry_price": round_price(entry_price),
                "exit_price": None,
                "margin_usd": float(margin_usd),
                "remaining_margin_usd": float(margin_usd),
                "notional_usd": float(notional_usd),
                "remaining_notional_usd": float(notional_usd),
                "leverage": LEVERAGE,
                "entry_fee": float(entry_fee),
                "exit_fee": 0.0,
                "spread_bps": float(spread_bps),
                "realized_pnl": float(-entry_fee),
                "unrealized_pnl": 0.0,
                "gross_pnl": 0.0,
                "entry_time": now_utc(),
                "exit_time": None,
                "reason": decision["reason"],
                "votes": decision["votes"],
                "regime": regime,
                "partials": [],
                "trail_stop": float(trail_stop),
                "entry_bid": bid,
                "entry_ask": ask,
                "exit_bid": None,
                "exit_ask": None,
                "close_reason": None,
            }
            trade_id = save_trade(trade)
            write_journal(
                "INFO",
                "OPEN",
                symbol,
                f"Opened {decision['side'].upper()} on {symbol}",
                {
                    "trade_id": trade_id,
                    "side": decision["side"],
                    "entry_price": trade["entry_price"],
                    "margin_usd": margin_usd,
                    "notional_usd": notional_usd,
                    "entry_fee": entry_fee,
                    "spread_bps": spread_bps,
                    "expected_edge_bps": decision["expected_edge_bps"],
                },
            )
            return True

    def close_trade(self, trade, exit_price, exit_bid=None, exit_ask=None, reason="manual"):
        close_notional = trade.get("remaining_notional_usd", trade.get("notional_usd", 0))
        close_margin = trade.get("remaining_margin_usd", trade.get("margin_usd", 0))
        exit_fee = commission_fee(close_notional)
        if trade["side"] == "long":
            gross = close_notional * (exit_price - trade["entry_price"]) / trade["entry_price"]
        else:
            gross = close_notional * (trade["entry_price"] - exit_price) / trade["entry_price"]
        realized_add = gross - exit_fee
        total_realized = float(trade["realized_pnl"] + realized_add)
        total_gross = float(trade["gross_pnl"] + gross)

        self.balance += close_margin + realized_add
        db_set("balance", self.balance)

        update_trade(
            trade["id"],
            status="closed",
            exit_price=round_price(exit_price),
            exit_fee=float(exit_fee),
            realized_pnl=total_realized,
            unrealized_pnl=0.0,
            gross_pnl=total_gross,
            exit_time=now_utc(),
            exit_bid=exit_bid,
            exit_ask=exit_ask,
            close_reason=reason,
            remaining_margin_usd=0.0,
            remaining_notional_usd=0.0,
        )
        write_journal(
            "INFO",
            "CLOSE",
            trade["symbol"],
            f"Closed {trade['side'].upper()} on {trade['symbol']} via {reason}",
            {
                "trade_id": trade["id"],
                "exit_price": exit_price,
                "exit_fee": exit_fee,
                "realized_pnl": total_realized,
                "gross_pnl": total_gross,
            },
        )
        self.learn_from_trade(trade, total_realized)

    def partial_close(self, trade, exit_price, fraction, reason):
        fraction = clamp(fraction, 0.0, 1.0)
        if fraction <= 0 or trade.get("remaining_notional_usd", trade.get("notional_usd", 0)) <= 0:
            return
        close_notional = trade.get("remaining_notional_usd", trade.get("notional_usd", 0)) * fraction
        close_margin = trade.get("remaining_margin_usd", trade.get("margin_usd", 0)) * fraction
        exit_fee = commission_fee(close_notional)
        if trade["side"] == "long":
            gross = close_notional * (exit_price - trade["entry_price"]) / trade["entry_price"]
        else:
            gross = close_notional * (trade["entry_price"] - exit_price) / trade["entry_price"]
        realized_add = gross - exit_fee

        trade.get("remaining_notional_usd", trade.get("notional_usd", 0)) -= close_notional
        trade.get("remaining_margin_usd", trade.get("margin_usd", 0)) -= close_margin
        trade["realized_pnl"] += realized_add
        trade["gross_pnl"] += gross
        trade["partials"].append(
            {
                "ts": now_utc(),
                "fraction": fraction,
                "price": exit_price,
                "realized": realized_add,
                "gross": gross,
                "fee": exit_fee,
                "reason": reason,
                "stage": "p1" if reason == "take_profit_partial" else reason,
            }
        )
        self.balance += close_margin + realized_add
        db_set("balance", self.balance)
        update_trade(
            trade["id"],
            realized_pnl=float(trade["realized_pnl"]),
            gross_pnl=float(trade["gross_pnl"]),
            remaining_margin_usd=float(trade.get("remaining_margin_usd", trade.get("margin_usd", 0))),
            remaining_notional_usd=float(trade.get("remaining_notional_usd", trade.get("notional_usd", 0))),
            partials=trade["partials"],
            trail_stop=float(trade["trail_stop"]),
        )
        write_journal(
            "INFO",
            "PARTIAL",
            trade["symbol"],
            f"Partial close on {trade['symbol']} ({reason})",
            {
                "trade_id": trade["id"],
                "fraction": fraction,
                "price": exit_price,
                "realized_add": realized_add,
                "exit_fee": exit_fee,
            },
        )

    def learn_from_trade(self, trade, pnl):
        self.learn_from_outcome(trade, pnl, source="live")

    def manage_positions(self):
        open_trades = get_open_trades()
        if not open_trades:
            return
        tickers = get_all_tickers()
        now = datetime.now(timezone.utc)

        for trade in open_trades:
            ticker = tickers.get(trade["symbol"])
            if ticker is None:
                continue
            last = float(ticker["last"])
            bid = float(ticker["bid"])
            ask = float(ticker["ask"])
            spread_bps = float((ask - bid) / (last + 1e-12) * 10000.0)
            rp = REGIME_PARAMS.get(trade["regime"], REGIME_PARAMS["RANGING"])

            if trade["side"] == "long":
                unrealized = trade.get("remaining_notional_usd", trade.get("notional_usd", 0)) * (bid - trade["entry_price"]) / trade["entry_price"]
                gross_on_mark = trade.get("remaining_notional_usd", trade.get("notional_usd", 0)) * (bid - trade["entry_price"]) / trade["entry_price"]
                trail_candidate = last * (1.0 - rp["sl"] * rp["trail_mult"] * 0.4)
                if trail_candidate > trade["trail_stop"]:
                    trade["trail_stop"] = trail_candidate
                    update_trade(trade["id"], trail_stop=float(trade["trail_stop"]))
                hit_trail = last <= trade["trail_stop"]
            else:
                unrealized = trade.get("remaining_notional_usd", trade.get("notional_usd", 0)) * (trade["entry_price"] - ask) / trade["entry_price"]
                gross_on_mark = trade.get("remaining_notional_usd", trade.get("notional_usd", 0)) * (trade["entry_price"] - ask) / trade["entry_price"]
                trail_candidate = last * (1.0 + rp["sl"] * rp["trail_mult"] * 0.4)
                if trail_candidate < trade["trail_stop"]:
                    trade["trail_stop"] = trail_candidate
                    update_trade(trade["id"], trail_stop=float(trade["trail_stop"]))
                hit_trail = last >= trade["trail_stop"]

            exit_fee_est = commission_fee(trade.get("remaining_notional_usd", trade.get("notional_usd", 0)))
            trade_unrealized = float(unrealized - exit_fee_est)
            update_trade(trade["id"], unrealized_pnl=trade_unrealized)

            pnl_pct = (last - trade["entry_price"]) / trade["entry_price"] if trade["side"] == "long" else (trade["entry_price"] - last) / trade["entry_price"]
            if pnl_pct >= rp["partial_at"] and not any(p.get("reason") == "take_profit_partial" for p in trade["partials"]):
                self.partial_close(trade, bid if trade["side"] == "long" else ask, 0.50, "take_profit_partial")

            full_close = False
            close_reason = None
            if pnl_pct >= rp["tp"]:
                full_close = True
                close_reason = "take_profit"
            elif pnl_pct <= -rp["sl"]:
                full_close = True
                close_reason = "stop_loss"
            elif hit_trail:
                full_close = True
                close_reason = "trailing_stop"
            elif (now - datetime.fromisoformat(trade["entry_time"])).total_seconds() / 60.0 >= 12:
                full_close = True
                close_reason = "time_exit"

            if full_close:
                exit_price = bid if trade["side"] == "long" else ask
                self.close_trade(trade, exit_price, bid, ask, close_reason)

        db_set("generation", self.generation)
        db_set("adaptive", self.adaptive)
        self.equity()

    def decide_cost_gate(self, decision, ticker):
        spread_bps = float((ticker["ask"] - ticker["bid"]) / (ticker["last"] + 1e-12) * 10000.0)
        cost_bps = spread_bps + (2.0 * COMMISSION_RATE * 10000.0) + SLIPPAGE_BPS
        return decision["expected_edge_bps"] > cost_bps and spread_bps <= MAX_SPREAD_BPS

    def cycle(self):
        self.manage_positions()
        tickers = get_all_tickers()
        if not tickers:
            return

        ranked = []
        for sym, t in tickers.items():
            if t["turn24"] < MIN_TURNOVER_24H:
                continue
            spread_bps = float((t["ask"] - t["bid"]) / (t["last"] + 1e-12) * 10000.0)
            if spread_bps > MAX_SPREAD_BPS:
                continue
            score = math.log10(t["turn24"] + 1.0) * 0.2 + abs(t["chg"]) * 150.0 * 0.8
            ranked.append((sym, score, t))
        ranked.sort(key=lambda x: -x[1])
        candidates = ranked[:15]

        regime_counts = defaultdict(int)
        opened = 0
        for sym, _, tk in candidates:
            try:
                df = get_klines(sym, DEFAULT_INTERVAL, 40)
                if df.empty:
                    continue
                regime = detect_regime(df)
                regime_counts[regime] += 1
                feat = extract_features(df, tk)
                if feat is None:
                    continue
                decision = self.decide_predator(feat, regime)
                if decision and self.decide_cost_gate(decision, tk):
                    if self.try_open(sym, tk, decision, feat):
                        opened += 1
            except Exception:
                continue

        self.last_stats = {
            "scanned": len(tickers),
            "cands": len(candidates),
            "opened": opened,
            "regime_counts": dict(regime_counts),
            "last_cycle": now_utc(),
        }
        self.heart_beat += 1
        db_set("generation", self.generation)
        db_set("adaptive", self.adaptive)
        db_set("balance", self.balance)
        save_organism_state(self.orgs)
        self.equity()


def get_backtest_symbols(limit=100, focus_symbol=None):
    tickers = get_all_tickers()
    ranked = []
    for sym, t in tickers.items():
        if not sym.endswith("USDT"):
            continue
        if t["turn24"] < MIN_TURNOVER_24H:
            continue
        ranked.append((sym, float(t["turn24"]), float(abs(t["chg"]))))
    ranked.sort(key=lambda x: (-x[1], -x[2], x[0]))
    symbols = [sym for sym, _, _ in ranked[:limit]]
    if focus_symbol and focus_symbol in tickers and focus_symbol not in symbols:
        symbols = [focus_symbol] + symbols[:-1]
    return symbols


# ----------------------------------------------------------------------------
# Backtest engine
# ----------------------------------------------------------------------------

class BacktestTrade:
    def __init__(self, trade_id, symbol, side, entry_time, entry_price, margin_usd, notional_usd, leverage,
                 entry_fee, spread_bps, reason, votes, regime, trail_stop, entry_bid, entry_ask):
        self.id = trade_id
        self.symbol = symbol
        self.side = side
        self.entry_time = entry_time
        self.entry_price = entry_price
        self.margin_usd = margin_usd
        self.remaining_margin_usd = margin_usd
        self.notional_usd = notional_usd
        self.remaining_notional_usd = notional_usd
        self.leverage = leverage
        self.entry_fee = entry_fee
        self.spread_bps = spread_bps
        self.realized_pnl = -entry_fee
        self.unrealized_pnl = 0.0
        self.gross_pnl = 0.0
        self.reason = reason
        self.votes = votes
        self.regime = regime
        self.partials = []
        self.trail_stop = trail_stop
        self.entry_bid = entry_bid
        self.entry_ask = entry_ask
        self.exit_price = None
        self.close_reason = None
        self.exit_time = None


class LiveStyleBacktester:
    def __init__(self, symbol, interval=DEFAULT_INTERVAL, candles=BACKTEST_CANDLES, teacher=None):
        self.symbol = symbol
        self.interval = interval
        self.candles = candles
        self.cash = BACKTEST_START_CAPITAL
        self.trades = []
        self.closed = []
        self.teacher = teacher
        if teacher is not None:
            self.orgs = teacher.orgs
            self.adaptive = teacher.adaptive
        else:
            self.orgs = [
                PredatorOrganism("Alpha", "ALPHA_SNIPER", base_weight=2.0),
                PredatorOrganism("Pulse", "HFT_SCALPER", base_weight=1.8),
                PredatorOrganism("Flux", "FLOW", base_weight=1.4),
                PredatorOrganism("Vector", "MOMENTUM", base_weight=1.2),
            ]
            self.adaptive = {"base_threshold": 0.3}
        self.peak_equity = self.cash
        self.equity_curve = []
        self.timestamps = []
        self.win_count = 0
        self.loss_count = 0
        self.reason_counts = defaultdict(int)

    def equity(self, mark_price, spread_bps=BACKTEST_SPREAD_BPS):
        open_equity = 0.0
        for trade in self.trades:
            if trade.side == "long":
                exit_price = synth_quotes(mark_price, spread_bps)["bid"]
                gross = trade.remaining_notional_usd * (exit_price - trade.entry_price) / trade.entry_price
            else:
                exit_price = synth_quotes(mark_price, spread_bps)["ask"]
                gross = trade.remaining_notional_usd * (trade.entry_price - exit_price) / trade.entry_price
            open_equity += trade.remaining_margin_usd + (gross - commission_fee(trade.remaining_notional_usd))
        return self.cash + open_equity

    def decide_predator(self, feat, regime):
        long_pool = 0.0
        short_pool = 0.0
        votes = {}
        for org in self.orgs:
            score = org.evaluate(feat, regime)
            side = "long" if org.last_vote == "LONG" else "short"
            if side == "long":
                long_pool += abs(score)
            else:
                short_pool += abs(score)
            votes[org.name] = {
                "org": org.name,
                "role": org.role,
                "side": side,
                "score": score,
                "vote": org.last_vote,
                "conviction": org.conviction,
                "weight": org.weight,
            }
        total_pool = long_pool + short_pool
        if total_pool <= 1e-12:
            return None
        if long_pool == short_pool:
            return None
        side = "long" if long_pool > short_pool else "short"
        final_pool = max(long_pool, short_pool)
        dominance = abs(long_pool - short_pool) / total_pool
        if final_pool <= self.adaptive["base_threshold"]:
            return None
        return {
            "side": side,
            "conv": clamp(final_pool / 4.0, 0.0, 1.0),
            "dominance": dominance,
            "expected_edge_bps": dominance * 50.0,
            "votes": votes,
            "reason": " | ".join([f"{v['org']}:{v['vote']}({v['conviction']:.2f})" for v in votes.values() if v["side"] == side]),
            "regime": regime,
        }

    def can_open(self, balance, margin_usd, entry_fee):
        return margin_usd >= MIN_MARGIN_USD and (margin_usd + entry_fee) <= balance

    def open_trade(self, ts, bar_open, decision, feat, regime):
        rp = REGIME_PARAMS.get(regime, REGIME_PARAMS["RANGING"])
        margin_by_risk = (self.cash * RISK_PER_TRADE_BASE * rp["risk_mult"] * (0.75 + 0.25 * decision["conv"])) / max(rp["sl"] * LEVERAGE, 1e-12)
        margin_usd = min(margin_by_risk, self.cash * MAX_MARGIN_PER_TRADE_RATIO)
        notional_usd = margin_usd * LEVERAGE
        entry_fee = commission_fee(notional_usd)
        quotes = synth_quotes(bar_open, BACKTEST_SPREAD_BPS)
        if decision["side"] == "long":
            entry_price = quotes["ask"] + (bar_open * SLIPPAGE_BPS / 10000.0)
            trail_stop = entry_price * (1.0 - rp["sl"] * 1.1)
        else:
            entry_price = quotes["bid"] - (bar_open * SLIPPAGE_BPS / 10000.0)
            trail_stop = entry_price * (1.0 + rp["sl"] * 1.1)
        available_balance = self.cash
        required_margin = margin_usd + entry_fee
        if available_balance < required_margin:
            return None
        if not self.can_open(self.cash, margin_usd, entry_fee):
            return None
        self.cash -= (margin_usd + entry_fee)
        trade = BacktestTrade(
            trade_id=len(self.closed) + len(self.trades) + 1,
            symbol=self.symbol,
            side=decision["side"],
            entry_time=ts,
            entry_price=entry_price,
            margin_usd=margin_usd,
            notional_usd=notional_usd,
            leverage=LEVERAGE,
            entry_fee=entry_fee,
            spread_bps=BACKTEST_SPREAD_BPS,
            reason=decision["reason"],
            votes=decision["votes"],
            regime=regime,
            trail_stop=trail_stop,
            entry_bid=quotes["bid"],
            entry_ask=quotes["ask"],
        )
        self.trades.append(trade)
        return trade

    def close_trade(self, trade, exit_price, ts, close_reason, exit_bid=None, exit_ask=None):
        exit_fee = commission_fee(trade.remaining_notional_usd)
        if trade.side == "long":
            gross = trade.remaining_notional_usd * (exit_price - trade.entry_price) / trade.entry_price
        else:
            gross = trade.remaining_notional_usd * (trade.entry_price - exit_price) / trade.entry_price
        realized_add = gross - exit_fee
        trade.realized_pnl += realized_add
        trade.gross_pnl += gross
        trade.exit_price = exit_price
        trade.exit_time = ts
        trade.close_reason = close_reason
        self.cash += trade.remaining_margin_usd + realized_add
        trade.remaining_margin_usd = 0.0
        trade.remaining_notional_usd = 0.0
        self.trades.remove(trade)
        self.closed.append(trade)
        if trade.realized_pnl > 0:
            self.win_count += 1
        else:
            self.loss_count += 1
        self.reason_counts[close_reason] += 1
        if self.teacher is not None:
            self.teacher.learn_from_outcome(
                {
                    "symbol": trade.symbol,
                    "regime": trade.regime,
                    "side": trade.side,
                    "votes": trade.votes,
                },
                trade.realized_pnl,
                source="backtest",
            )
        return trade.realized_pnl

    def partial_close(self, trade, exit_price, fraction, ts, reason):
        fraction = clamp(fraction, 0.0, 1.0)
        if fraction <= 0 or trade.remaining_notional_usd <= 0:
            return
        close_notional = trade.remaining_notional_usd * fraction
        close_margin = trade.remaining_margin_usd * fraction
        exit_fee = commission_fee(close_notional)
        if trade.side == "long":
            gross = close_notional * (exit_price - trade.entry_price) / trade.entry_price
        else:
            gross = close_notional * (trade.entry_price - exit_price) / trade.entry_price
        realized_add = gross - exit_fee
        trade.realized_pnl += realized_add
        trade.gross_pnl += gross
        trade.remaining_notional_usd -= close_notional
        trade.remaining_margin_usd -= close_margin
        trade.partials.append({"ts": ts, "fraction": fraction, "price": exit_price, "reason": reason, "realized": realized_add})
        self.cash += close_margin + realized_add

    def run(self):
        df = fetch_klines_history(self.symbol, self.interval, self.candles)
        if df.empty or len(df) < 200:
            return None

        for i in range(50, len(df) - 1):
            hist = df.iloc[: i + 1].copy().reset_index(drop=True)
            current = hist.iloc[-1]
            next_bar = df.iloc[i + 1]
            regime = detect_regime(hist)
            ticker = synth_quotes(float(current["close"]), BACKTEST_SPREAD_BPS)
            feat = extract_features(hist, {"last": float(current["close"]), "bid": ticker["bid"], "ask": ticker["ask"], "turn24": 1, "chg": 0, "vol24": 1})

            # 1) execute pending signals on the next bar open through the open price of this bar
            if i >= 1:
                prev_hist = df.iloc[:i].copy().reset_index(drop=True)
                prev_regime = detect_regime(prev_hist)
                prev_feat = extract_features(prev_hist, {"last": float(df.iloc[i - 1]["close"]), "bid": float(df.iloc[i - 1]["close"]), "ask": float(df.iloc[i - 1]["close"]), "turn24": 1, "chg": 0, "vol24": 1})
                if prev_feat is not None:
                    prev_decision = self.decide_predator(prev_feat, prev_regime)
                    if prev_decision:
                        edge = prev_decision["expected_edge_bps"]
                        cost = BACKTEST_SPREAD_BPS + (2.0 * COMMISSION_RATE * 10000.0) + SLIPPAGE_BPS
                        if edge > cost:
                            self.open_trade(ts=float(next_bar["ts"]), bar_open=float(next_bar["open"]), decision=prev_decision, feat=prev_feat, regime=prev_regime)

            # 2) manage open positions on the current candle using high/low only
            open_snapshot = list(self.trades)
            for trade in open_snapshot:
                rp = REGIME_PARAMS.get(trade.regime, REGIME_PARAMS["RANGING"])
                bar_high = float(current["high"])
                bar_low = float(current["low"])
                bar_close = float(current["close"])
                quotes = synth_quotes(bar_close, BACKTEST_SPREAD_BPS)
                if trade.side == "long":
                    stop_hit = bar_low <= trade.trail_stop
                    tp_hit = ((bar_high - trade.entry_price) / trade.entry_price) >= rp["tp"]
                    if ((bar_high - trade.entry_price) / trade.entry_price) >= rp["partial_at"] and not any(p.get("reason") == "take_profit_partial" for p in trade.partials):
                        self.partial_close(trade, quotes["bid"], 0.50, current["ts"], "take_profit_partial")
                        if trade not in self.trades:
                            continue
                    if stop_hit and tp_hit:
                        close_reason = "stop_loss_conservative"
                    elif stop_hit:
                        close_reason = "trailing_stop"
                    elif tp_hit:
                        close_reason = "take_profit"
                    elif ((bar_close - trade.entry_price) / trade.entry_price) <= -rp["sl"]:
                        close_reason = "stop_loss"
                    elif ((bar_close - trade.entry_price) / trade.entry_price) >= rp["tp"]:
                        close_reason = "take_profit"
                    else:
                        close_reason = None
                    if close_reason:
                        self.close_trade(trade, quotes["bid"], current["ts"], close_reason, quotes["bid"], quotes["ask"])
                else:
                    stop_hit = bar_high >= trade.trail_stop
                    tp_hit = ((trade.entry_price - bar_low) / trade.entry_price) >= rp["tp"]
                    if ((trade.entry_price - bar_low) / trade.entry_price) >= rp["partial_at"] and not any(p.get("reason") == "take_profit_partial" for p in trade.partials):
                        self.partial_close(trade, quotes["ask"], 0.50, current["ts"], "take_profit_partial")
                        if trade not in self.trades:
                            continue
                    if stop_hit and tp_hit:
                        close_reason = "stop_loss_conservative"
                    elif stop_hit:
                        close_reason = "trailing_stop"
                    elif tp_hit:
                        close_reason = "take_profit"
                    elif ((trade.entry_price - bar_close) / trade.entry_price) <= -rp["sl"]:
                        close_reason = "stop_loss"
                    elif ((trade.entry_price - bar_close) / trade.entry_price) >= rp["tp"]:
                        close_reason = "take_profit"
                    else:
                        close_reason = None
                    if close_reason:
                        self.close_trade(trade, quotes["ask"], current["ts"], close_reason, quotes["bid"], quotes["ask"])

                if trade in self.trades:
                    if trade.side == "long":
                        trail_candidate = bar_close * (1.0 - rp["sl"] * rp["trail_mult"] * 0.4)
                        trade.trail_stop = max(trade.trail_stop, trail_candidate)
                    else:
                        trail_candidate = bar_close * (1.0 + rp["sl"] * rp["trail_mult"] * 0.4)
                        trade.trail_stop = min(trade.trail_stop, trail_candidate)

            equity = self.equity(bar_close, BACKTEST_SPREAD_BPS)
            self.peak_equity = max(self.peak_equity, equity)
            self.equity_curve.append(equity)
            self.timestamps.append(current["ts"])

        # close remaining positions at last close
        last = df.iloc[-1]
        final_quotes = synth_quotes(float(last["close"]), BACKTEST_SPREAD_BPS)
        for trade in list(self.trades):
            self.close_trade(trade, final_quotes["bid"] if trade.side == "long" else final_quotes["ask"], last["ts"], "eod")
        final_equity = self.equity(float(last["close"]), BACKTEST_SPREAD_BPS)
        self.equity_curve.append(final_equity)
        self.timestamps.append(last["ts"])

        closed_count = len(self.closed)
        win_rate = (self.win_count / closed_count * 100.0) if closed_count else 0.0
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "candles": len(df),
            "equity_curve": self.equity_curve,
            "timestamps": self.timestamps,
            "win_rate": win_rate,
            "closed_trades": closed_count,
            "final_equity": final_equity,
            "start_capital": BACKTEST_START_CAPITAL,
            "peak_equity": self.peak_equity,
            "wins": self.win_count,
            "losses": self.loss_count,
            "reason_counts": dict(self.reason_counts),
        }


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------

init_db()
HIVE = PredatorHive()
external_stylesheets = [dbc.themes.CYBORG, "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;700;900&display=swap"]
app = dash.Dash(__name__, external_stylesheets=external_stylesheets, suppress_callback_exceptions=True)
app.title = "HIVE PREDATOR v10.0"

app.index_string = f"""
<!DOCTYPE html>
<html lang=\"fa\" dir=\"rtl\">
    <head>
        {{%metas%}}
        <title>{app.title}</title>
        {{%favicon%}}
        {{%css%}}
        <style>
            :root {{ color-scheme: dark; }}
            body {{ margin: 0; background: {BG}; color: {TXT}; font-family: 'Vazirmatn', sans-serif; }}
            .panel {{
                background: {PANEL};
                border: 1px solid rgba(255, 42, 109, 0.18);
                border-radius: 8px;
                padding: 12px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.55);
            }}
            .predator-glow {{ text-shadow: 0 0 15px rgba(255, 42, 109, 0.85); }}
            .dash-tabs .nav-link {{ border-radius: 8px !important; margin: 0 4px; font-family: 'Vazirmatn'; font-weight: 700; }}
            .small-note {{ color: {MUT}; font-size: 11px; }}
            .table-dark td, .table-dark th {{ color: {TXT}; }}
        </style>
    </head>
    <body>{{%app_entry%}}<footer>{{%config%}}{{%scripts%}}{{%renderer%}}</footer></body>
</html>
"""


def stat_card(title, value, color=GOLD, sub=""):
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(rtl_text(title), style={"color": MUT, "fontSize": 11, "marginBottom": 4}),
                html.Div(str(value), style={"color": color, "fontSize": 20, "fontWeight": 900}),
                html.Div(rtl_text(sub), style={"color": MUT, "fontSize": 10, "marginTop": 4}),
            ]
        ),
        className="panel",
        style={"height": "100%"},
    )


def organism_table():
    rows = []
    for org in HIVE.orgs:
        rows.append(
            html.Tr(
                [
                    html.Td(rtl_text(org.name), style={"fontWeight": "bold"}),
                    html.Td(rtl_text(org.role), style={"color": MUT, "fontSize": 11}),
                    html.Td(org.last_vote, style={"color": UP if org.last_vote == "LONG" else DN, "fontWeight": 900}),
                    html.Td(f"{org.conviction:.0%}", style={"color": GOLD}),
                    html.Td(f"{org.weight:.2f}x", style={"color": NEON}),
                ]
            )
        )
    return dbc.Table(
        [
            html.Thead(html.Tr([html.Th(rtl_text(x)) for x in ["واحد", "نقش", "جهت", "قاطعیت", "وزن"]])),
            html.Tbody(rows),
        ],
        bordered=True,
        hover=True,
        size="sm",
        className="table-dark",
    )


def open_positions_table():
    open_trades = get_open_trades()
    if not open_trades:
        return dbc.Alert(rtl_text("موقعیت بازی وجود ندارد."), color="dark", className="panel")

    tickers = get_all_tickers()
    rows = []
    for trade in open_trades:
        ticker = tickers.get(trade["symbol"])
        last = float(ticker["last"]) if ticker else float(trade["entry_price"])
        bid = float(ticker["bid"]) if ticker else last
        ask = float(ticker["ask"]) if ticker else last
        spread_bps = float((ask - bid) / (last + 1e-12) * 10000.0)
        unrealized = HIVE.unrealized_trade_pnl(trade, last, spread_bps)
        total_realized = float(trade["realized_pnl"])
        color = UP if unrealized >= 0 else DN
        vote_preview = ", ".join([f"{v.get('org')}:{v.get('vote')}" for v in trade["votes"].values()])
        rows.append(
            html.Tr(
                [
                    html.Td(trade["symbol"], style={"fontWeight": "bold"}),
                    html.Td(trade["side"].upper(), style={"color": UP if trade["side"] == "long" else DN, "fontWeight": 900}),
                    html.Td(f"{trade['entry_price']:.4f}"),
                    html.Td(f"{last:.4f}"),
                    html.Td(f"{trade['margin_usd']:.2f}"),
                    html.Td(f"{trade['notional_usd']:.2f}"),
                    html.Td(f"{trade['entry_fee']:.2f}"),
                    html.Td(f"{total_realized:+.2f}", style={"color": UP if total_realized >= 0 else DN, "fontWeight": 900}),
                    html.Td(f"{unrealized:+.2f}", style={"color": color, "fontWeight": 900}),
                    html.Td(f"{trade['trail_stop']:.4f}" if trade["trail_stop"] else "-"),
                    html.Td(vote_preview, style={"fontSize": 10, "color": CYAN}),
                ]
            )
        )
    return dbc.Table(
        [
            html.Thead(
                html.Tr(
                    [
                        html.Th(rtl_text(x))
                        for x in [
                            "نماد",
                            "سمت",
                            "ورود",
                            "آخرین",
                            "مارجین",
                            "نوشن",
                            "کارمزد ورود",
                            "Realized",
                            "Unrealized",
                            "تریل",
                            "رأی‌ها",
                        ]
                    ]
                )
            ),
            html.Tbody(rows),
        ],
        bordered=True,
        hover=True,
        size="sm",
        className="table-dark",
    )


def journal_table():
    rows = get_recent_journal(50)
    if not rows:
        return dbc.Alert(rtl_text("ژورنالی ثبت نشده است."), color="dark", className="panel")
    table_rows = []
    for ts, level, kind, symbol, message, payload in rows:
        level_color = GOLD if level == "INFO" else DN
        table_rows.append(
            html.Tr(
                [
                    html.Td(ts, style={"fontSize": 11, "color": MUT}),
                    html.Td(level, style={"color": level_color, "fontWeight": 900}),
                    html.Td(kind, style={"color": CYAN}),
                    html.Td(symbol or "-"),
                    html.Td(message),
                    html.Td(payload, style={"fontSize": 10, "color": MUT}),
                ]
            )
        )
    return dbc.Table(
        [
            html.Thead(html.Tr([html.Th(rtl_text(x)) for x in ["زمان", "سطح", "نوع", "نماد", "پیام", "جزئیات"]])),
            html.Tbody(table_rows),
        ],
        bordered=True,
        hover=True,
        size="sm",
        className="table-dark",
    )


def closed_trades_table():
    rows = get_closed_trades(30)
    if not rows:
        return dbc.Alert(rtl_text("معامله بسته‌شده‌ای وجود ندارد."), color="dark", className="panel")
    table_rows = []
    for trade in rows:
        color = UP if trade["realized_pnl"] >= 0 else DN
        table_rows.append(
            html.Tr(
                [
                    html.Td(trade["symbol"], style={"fontWeight": "bold"}),
                    html.Td(trade["side"].upper(), style={"color": UP if trade["side"] == "long" else DN, "fontWeight": 900}),
                    html.Td(f"{trade['entry_price']:.4f}"),
                    html.Td(f"{trade['exit_price']:.4f}" if trade["exit_price"] else "-"),
                    html.Td(f"{trade['entry_fee']:.2f}"),
                    html.Td(f"{trade['exit_fee']:.2f}"),
                    html.Td(f"{trade['gross_pnl']:+.2f}"),
                    html.Td(f"{trade['realized_pnl']:+.2f}", style={"color": color, "fontWeight": 900}),
                    html.Td(trade["close_reason"] or "-"),
                ]
            )
        )
    return dbc.Table(
        [
            html.Thead(html.Tr([html.Th(rtl_text(x)) for x in ["نماد", "سمت", "ورود", "خروج", "Fee In", "Fee Out", "Gross", "Realized", "Reason"]])),
            html.Tbody(table_rows),
        ],
        bordered=True,
        hover=True,
        size="sm",
        className="table-dark",
    )


def backtest_figure(result):
    curve = [BACKTEST_START_CAPITAL]
    if result and result.get("equity_curve"):
        curve = [BACKTEST_START_CAPITAL] + [float(x) for x in result["equity_curve"]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=curve, mode="lines", line={"color": CYAN, "width": 2}, name="Equity"))
    fig.update_layout(
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font={"color": TXT},
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        height=420,
        xaxis_title="Bars",
        yaxis_title="Equity USD",
        showlegend=False,
    )
    return fig


app.layout = html.Div(
    [
        dbc.Container(
            fluid=True,
            children=[
                html.Div(
                    [
                        dbc.Row(
                            [
                                dbc.Col(
                                    html.H2(
                                        "HIVE PREDATOR v10.0",
                                        className="predator-glow",
                                        style={"margin": 0, "color": DN, "fontWeight": 900},
                                    ),
                                    md=6,
                                ),
                                dbc.Col(
                                    html.Div(id="pulse", style={"color": CYAN, "fontFamily": "monospace", "fontSize": 12, "textAlign": "left"}),
                                    md=6,
                                ),
                            ],
                            align="center",
                        )
                    ],
                    className="panel mt-2 mb-3",
                ),
                dbc.Row(
                    [
                        dbc.Col(stat_card("Balance", f"${HIVE.balance:.2f}", GOLD, "Available capital after locked margin and fees"), md=3),
                        dbc.Col(stat_card("Equity", f"${HIVE.equity():.2f}", CYAN, f"Peak: ${HIVE.peak_equity:.2f}"), md=3),
                        dbc.Col(stat_card("Realized / Unrealized", f"${HIVE.latest_metrics['realized']:+.2f} / ${HIVE.latest_metrics['unrealized']:+.2f}", UP, "Separated accounting"), md=3),
                        dbc.Col(stat_card("Margin Used", f"${HIVE.latest_metrics['margin_used']:.2f}", NEON, f"Open positions: {len(get_open_trades())}/{MAX_POSITIONS}"), md=3),
                    ],
                    className="g-3 mb-3",
                ),
                dcc.Tabs(
                    id="tabs",
                    value="live",
                    parent_className="dash-tabs",
                    children=[
                        dcc.Tab(label="Live Trading", value="live", style={"background": PANEL_SOLID, "color": TXT}, selected_style={"background": LINE, "color": DN}),
                        dcc.Tab(label="Learning Status", value="learning", style={"background": PANEL_SOLID, "color": TXT}, selected_style={"background": LINE, "color": DN}),
                        dcc.Tab(label="Journal", value="journal", style={"background": PANEL_SOLID, "color": TXT}, selected_style={"background": LINE, "color": DN}),
                        dcc.Tab(label="Backtest", value="backtest", style={"background": PANEL_SOLID, "color": TXT}, selected_style={"background": LINE, "color": DN}),
                    ],
                ),
                html.Div(id="content", className="mt-3"),
                html.Div(id="cycle-status", style={"display": "none"}),
                dcc.Store(id="backtest-store"),
                dcc.Interval(id="life", interval=4000, n_intervals=0),
                dcc.Interval(id="cycle", interval=12000, n_intervals=0),
            ],
        )
    ],
    style={"minHeight": "100vh", "paddingBottom": "40px"},
)


def learning_status_panel():
    rows = []
    for org in HIVE.orgs:
        rows.append(
            html.Tr(
                [
                    html.Td(rtl_text(org.name), style={"fontWeight": "bold"}),
                    html.Td(rtl_text(org.role), style={"color": MUT}),
                    html.Td(org.last_vote, style={"color": UP if org.last_vote == "LONG" else DN, "fontWeight": 900}),
                    html.Td(f"{org.conviction:.0%}"),
                    html.Td(f"{org.weight:.2f}x"),
                    html.Td(str(org.regime_trades.get("TREND_UP", 0) + org.regime_trades.get("TREND_DOWN", 0) + org.regime_trades.get("RANGING", 0) + org.regime_trades.get("HIGH_VOL", 0))),
                ]
            )
        )
    return html.Div(
        [
            html.Div(
                [
                    html.H4(rtl_text("Learning Status"), style={"color": GOLD, "fontWeight": 900}),
                    html.Div(
                        [
                            html.Div(f"Generation: {HIVE.generation}", className="small-note"),
                            html.Div(f"Base Threshold: {HIVE.adaptive.get('base_threshold', 0.0):.3f}", className="small-note"),
                            html.Div(f"Peak Equity: ${HIVE.peak_equity:.2f}", className="small-note"),
                            html.Div(f"Current Equity: ${HIVE.equity():.2f}", className="small-note"),
                        ]
                    ),
                ],
                className="panel mb-3",
            ),
            html.Div(
                [
                    dbc.Table(
                        [
                            html.Thead(html.Tr([html.Th(rtl_text(x)) for x in ["Organism", "Role", "Vote", "Conviction", "Weight", "Trades"]])),
                            html.Tbody(rows),
                        ],
                        bordered=True,
                        hover=True,
                        size="sm",
                        className="table-dark",
                    )
                ],
                className="panel",
            ),
        ]
    )

@app.callback(Output("content", "children"), Input("tabs", "value"), Input("life", "n_intervals"), State("backtest-store", "data"))
def render(tab, _, backtest_data):
    if tab == "live":
        return html.Div(
            [
                html.Div(
                    [
                        html.H4(rtl_text("وضعیت واحدهای شکارچی"), style={"color": DN, "fontWeight": 900}),
                        organism_table(),
                    ],
                    className="panel mb-3",
                ),
                html.Div(
                    [
                        html.H4(rtl_text("پوزیشن‌های باز"), style={"color": GOLD, "fontWeight": 900}),
                        open_positions_table(),
                    ],
                    className="panel",
                ),
            ]
        )

    if tab == "learning":
        return learning_status_panel()

    if tab == "journal":
        return html.Div(
            [
                html.Div(
                    [
                        html.H4(rtl_text("ژورنال معاملاتی"), style={"color": DN, "fontWeight": 900}),
                        html.Div(rtl_text("ثبت ورود، خروج، بخشی از خروج، و پیام‌های عملیاتی در همین تب انجام می‌شود."), className="small-note", style={"marginBottom": "10px"}),
                        journal_table(),
                    ],
                    className="panel mb-3",
                ),
                html.Div(
                    [
                        html.H4(rtl_text("معاملات بسته‌شده"), style={"color": GOLD, "fontWeight": 900}),
                        closed_trades_table(),
                    ],
                    className="panel",
                ),
            ]
        )

    result = backtest_data or {}
    fig = backtest_figure(result)
    if result:
        win_rate = result.get("win_rate", 0.0)
        closed_trades = result.get("closed_trades", 0)
        final_equity = result.get("final_equity", 0.0)
        return html.Div(
            [
                html.Div(
                    [
                        dbc.Row(
                            [
                                dbc.Col(dbc.Input(id="backtest-symbol", value=result.get("focus_symbol", DEFAULT_BACKTEST_SYMBOL), type="text"), md=3),
                                dbc.Col(dbc.Input(id="backtest-interval", value=result.get("interval", DEFAULT_INTERVAL), type="text"), md=2),
                                dbc.Col(dbc.Input(id="backtest-bars", value=str(result.get("candles", BACKTEST_CANDLES)), type="number", min=500, max=5000, step=100), md=2),
                                dbc.Col(dbc.Button([html.I(className="bi bi-play-fill"), html.Span(" اجرای بک‌تست", style={"marginRight": "6px"})], id="run-backtest", color="danger", n_clicks=0), md=2),
                                dbc.Col(dbc.Alert(f"Symbols: {result.get('symbols_tested', 0)} | Win Rate: {win_rate:.1f}% | Closed: {closed_trades} | Final Equity: ${final_equity:.2f}", color="dark", className="mb-0"), md=3),
                            ],
                            className="g-2",
                        ),
                    ],
                    className="panel mb-3",
                ),
                html.Div(dcc.Graph(figure=fig, config={"displayModeBar": False}), className="panel mb-3"),
                html.Div(
                    [
                        html.H4(rtl_text("خلاصه بک‌تست"), style={"color": GOLD, "fontWeight": 900}),
                        html.Div(
                            [
                                html.Div(f"Start: ${result.get('start_capital', BACKTEST_START_CAPITAL):.2f}", className="small-note"),
                                html.Div(f"Peak Equity: ${result.get('peak_equity', 0.0):.2f}", className="small-note"),
                                html.Div(f"Wins: {result.get('wins', 0)} / Losses: {result.get('losses', 0)}", className="small-note"),
                            ]
                        ),
                    ],
                    className="panel",
                ),
            ]
        )

    return html.Div(
        [
            html.Div(
                [
                    dbc.Row(
                        [
                            dbc.Col(dbc.Input(id="backtest-symbol", value=DEFAULT_BACKTEST_SYMBOL, type="text"), md=3),
                            dbc.Col(dbc.Input(id="backtest-interval", value=DEFAULT_INTERVAL, type="text"), md=2),
                            dbc.Col(dbc.Input(id="backtest-bars", value=str(BACKTEST_CANDLES), type="number", min=500, max=5000, step=100), md=2),
                            dbc.Col(dbc.Button([html.I(className="bi bi-play-fill"), html.Span(" اجرای بک‌تست", style={"marginRight": "6px"})], id="run-backtest", color="danger", n_clicks=0), md=2),
                            dbc.Col(dbc.Alert(rtl_text("بک‌تست روی 100 ارز برتر انجام می‌شود و ژنوم را به‌روزرسانی می‌کند."), color="dark", className="mb-0"), md=3),
                        ],
                        className="g-2",
                    ),
                ],
                className="panel mb-3",
            ),
            html.Div(dcc.Graph(figure=fig, config={"displayModeBar": False}), className="panel"),
        ]
    )


@app.callback(Output("pulse", "children"), Input("life", "n_intervals"))
def update_pulse(_):
    open_count = len(get_open_trades())
    return f"BEAT #{HIVE.heart_beat} | GEN {HIVE.generation} | OPEN {open_count} | THRESH {HIVE.adaptive['base_threshold']:.3f} | {now_utc().split('T')[1][:8]}"


@app.callback(Output("cycle-status", "children"), Input("cycle", "n_intervals"))
def run_cycle(_):
    HIVE.cycle()
    return HIVE.last_stats.get("last_cycle", now_utc())


@app.callback(
    Output("backtest-store", "data"),
    Input("run-backtest", "n_clicks"),
    State("backtest-symbol", "value"),
    State("backtest-interval", "value"),
    State("backtest-bars", "value"),
    prevent_initial_call=True,
)
def run_backtest(n_clicks, symbol, interval, bars):
    if not n_clicks:
        return dash.no_update
    focus_symbol = (symbol or DEFAULT_BACKTEST_SYMBOL).strip().upper()
    interval = str(interval or DEFAULT_INTERVAL).strip()
    try:
        bars = int(bars or BACKTEST_CANDLES)
    except Exception:
        bars = BACKTEST_CANDLES
    bars = int(clamp(bars, 500, 5000))

    symbols = get_backtest_symbols(100, focus_symbol=focus_symbol)
    if not symbols:
        return {
            "focus_symbol": focus_symbol,
            "symbols_tested": 0,
            "interval": interval,
            "candles": bars,
            "equity_curve": [BACKTEST_START_CAPITAL],
            "timestamps": [],
            "win_rate": 0.0,
            "closed_trades": 0,
            "final_equity": BACKTEST_START_CAPITAL,
            "start_capital": BACKTEST_START_CAPITAL,
            "peak_equity": BACKTEST_START_CAPITAL,
            "wins": 0,
            "losses": 0,
            "reason_counts": {},
            "per_symbol": [],
        }

    per_symbol = []
    growth_curve = []
    labels = []
    total_closed = 0
    total_wins = 0
    total_losses = 0
    total_peak = HIVE.peak_equity
    for sym in symbols:
        backtester = LiveStyleBacktester(sym, interval=interval, candles=bars, teacher=HIVE)
        result = backtester.run()
        labels.append(sym)
        if result is None:
            growth_curve.append(BACKTEST_START_CAPITAL)
            per_symbol.append({"symbol": sym, "closed_trades": 0, "win_rate": 0.0, "final_equity": BACKTEST_START_CAPITAL})
            continue
        total_closed += result.get("closed_trades", 0)
        total_wins += result.get("wins", 0)
        total_losses += result.get("losses", 0)
        total_peak = max(total_peak, float(result.get("peak_equity", BACKTEST_START_CAPITAL)))
        growth_curve.append(float(result.get("final_equity", BACKTEST_START_CAPITAL)))
        per_symbol.append({
            "symbol": sym,
            "closed_trades": result.get("closed_trades", 0),
            "win_rate": result.get("win_rate", 0.0),
            "final_equity": result.get("final_equity", BACKTEST_START_CAPITAL),
            "wins": result.get("wins", 0),
            "losses": result.get("losses", 0),
        })

    total_trades = total_wins + total_losses
    win_rate = (total_wins / total_trades * 100.0) if total_trades else 0.0
    final_equity = growth_curve[-1] if growth_curve else BACKTEST_START_CAPITAL
    return {
        "focus_symbol": focus_symbol,
        "symbols_tested": len(symbols),
        "symbols": labels,
        "interval": interval,
        "candles": bars,
        "equity_curve": growth_curve,
        "timestamps": labels,
        "win_rate": win_rate,
        "closed_trades": total_closed,
        "final_equity": final_equity,
        "start_capital": BACKTEST_START_CAPITAL,
        "peak_equity": total_peak,
        "wins": total_wins,
        "losses": total_losses,
        "reason_counts": {},
        "per_symbol": per_symbol,
    }


if __name__ == "__main__":
    print("Launching HIVE PREDATOR v10.0")
    print(f"Database: {DB_PATH}")
    app.run(debug=False, host="0.0.0.0", port=8051, use_reloader=False)
