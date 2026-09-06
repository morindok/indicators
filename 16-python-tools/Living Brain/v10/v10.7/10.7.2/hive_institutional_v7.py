# -*- coding: utf-8 -*-
"""
HIVE INSTITUTIONAL v7

Single-file Dash trading cockpit with:
- Auto-created config and SQLite schema
- Eight advanced market-touching organisms
- Background scan / consensus / execution loop
- Simulation-first, live execution opt-in
- Dashboard tabs for trades, organisms, scan, hive mind, performance, control
- Robust error handling, logging, graceful shutdown

Safety defaults:
- Testnet mode on by default
- Execution disabled by default
- If live API credentials are missing, the engine stays in simulation mode
"""

from __future__ import annotations

import os
import sys
import json
import math
import time
import signal
import sqlite3
import threading
import traceback
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import deque, defaultdict

import numpy as np
import pandas as pd

try:
    import requests  # optional, used for live market data/execution
except Exception:
    requests = None

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except Exception as e:  # pragma: no cover
    raise RuntimeError("plotly is required for this application") from e

try:
    import dash
    from dash import dcc, html, Input, Output, State, ctx
except Exception as e:  # pragma: no cover
    raise RuntimeError("dash is required for this application") from e

try:
    import dash_bootstrap_components as dbc
except Exception:
    dbc = None

try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    def rtl_text(s: Any) -> str:
        try:
            return get_display(arabic_reshaper.reshape(str(s)))
        except Exception:
            return str(s)
except Exception:
    def rtl_text(s: Any) -> str:
        return str(s)


# =============================================================================
# Paths / constants
# =============================================================================
BASE_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
CONFIG_PATH = BASE_DIR / "hive_institutional_config.json"
DB_PATH = BASE_DIR / "hive_institutional_v7.db"
LOG_PATH = BASE_DIR / "hive_institutional_v7.log"
STATE_PATH = BASE_DIR / "hive_institutional_v7_state.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "app": {
        "title": "HIVE INSTITUTIONAL v7",
        "host": "0.0.0.0",
        "port": 8060,
        "debug": False,
        "rtl": True,
    },
    "mode": {
        "live_mode": False,
        "testnet": True,
        "execution_enabled": False,
        "replay_mode": False,
        "scan_interval_sec": 30,
        "manage_interval_sec": 10,
        "dashboard_tick_sec": 5,
    },
    "bybit": {
        "api_key": "",
        "api_secret": "",
        "recv_window": 5000,
        "category": "linear",
        "base_urls_live": ["https://api.bybit.com", "https://api.bytick.com"],
        "base_urls_testnet": ["https://api-testnet.bybit.com"],
    },
    "universe": {
        "max_symbols": 16,
        "symbols": [
            "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT",
            "BNBUSDT", "DOGEUSDT", "AVAXUSDT", "ADAUSDT",
            "LINKUSDT", "SUIUSDT", "TONUSDT", "LTCUSDT",
            "DOTUSDT", "TRXUSDT", "BCHUSDT", "NEARUSDT",
        ],
        "min_turnover_24h": 1200000,
        "max_spread_bps": 5.0,
    },
    "risk": {
        "initial_capital": 500.0,
        "base_leverage": 20,
        "min_leverage": 5,
        "max_leverage": 50,
        "max_positions": 5,
        "risk_per_trade": 0.011,
        "daily_loss_limit": 0.04,
        "consecutive_loss_limit": 4,
        "volatility_pause_pct": 0.03,
        "correlation_block": 0.92,
        "kelly_fraction": 0.35,
        "atr_stop_mult": 1.8,
        "partial_exit_1r": 0.25,
        "partial_exit_2r": 0.25,
    },
    "learning": {
        "score_threshold": 0.53,
        "conv_threshold": 0.42,
        "pattern_memory_size": 500,
        "recent_backtest_candles": 2000,
        "walk_forward_train": 1500,
        "walk_forward_test": 300,
        "memory_decay": 0.985,
    },
    "ui": {
        "theme": "cyborg",
        "update_ms": 5000,
    },
}

APP_TITLE = DEFAULT_CONFIG["app"]["title"]
TZ = timezone.utc

BG = "#08111f"
CARD = "rgba(12, 20, 36, 0.85)"
CARD_SOLID = "#0f1830"
TXT = "#ecf3ff"
MUTED = "#8ea2c7"
GREEN = "#19e3b1"
RED = "#ff5d7a"
CYAN = "#26d7ff"
GOLD = "#f2c14e"
NEON = "#8f5cff"
ORANGE = "#ff9f1c"


# =============================================================================
# Logging
# =============================================================================
def setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(fh)
    root.addHandler(sh)


log = logging.getLogger("hive_v7")


# =============================================================================
# Utility helpers
# =============================================================================
def utc_now() -> str:
    return datetime.now(TZ).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def safe_json_load(value: Optional[str], default: Any = None) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def safe_json_dump(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return json.dumps(str(value), ensure_ascii=False)


def fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def fmt_money(x: float) -> str:
    return f"${x:,.2f}"


def fmt_num(x: float) -> str:
    return f"{x:,.4f}"


def now_ts_ms() -> int:
    return int(time.time() * 1000)


def fig_style(fig: go.Figure, title: str = "", height: int = 360) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        height=height,
        title=dict(text=rtl_text(title), x=0.98, xanchor="right", font=dict(color=GOLD, size=15)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(8,17,31,0.9)",
        margin=dict(l=22, r=18, t=50, b=26),
        font=dict(color=TXT, family="Vazirmatn, IRANSans, Segoe UI, sans-serif"),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0.01),
    )
    fig.update_xaxes(gridcolor="#1d2a43", zeroline=False)
    fig.update_yaxes(gridcolor="#1d2a43", zeroline=False)
    return fig


def hex_to_rgba(hex_color: str, a: float = 0.15) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return f"rgba(255,255,255,{a})"
    r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{a})"


# =============================================================================
# Config
# =============================================================================
def load_or_create_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        ensure_parent(CONFIG_PATH)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        log.info("Created default config at %s", CONFIG_PATH)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # shallow merge with defaults for missing keys
        merged = json.loads(json.dumps(DEFAULT_CONFIG))
        for k, v in cfg.items():
            if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
                merged[k].update(v)
            else:
                merged[k] = v
        return merged
    except Exception as e:
        log.exception("Failed loading config, regenerating default: %s", e)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        return DEFAULT_CONFIG.copy()


CFG = load_or_create_config()


# =============================================================================
# Database
# =============================================================================
def init_db() -> None:
    ensure_parent(DB_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        cur = conn.cursor()

        cur.execute(
            """CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                size REAL NOT NULL,
                pnl REAL,
                status TEXT NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                organisms_voted TEXT,
                consensus_score REAL,
                reason TEXT,
                mode TEXT,
                leverage REAL,
                stop_price REAL,
                take_profit_price REAL,
                partials TEXT,
                live_order_id TEXT
            );"""
        )

        cur.execute(
            """CREATE TABLE IF NOT EXISTS organisms_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER,
                organism_name TEXT NOT NULL,
                signal TEXT NOT NULL,
                confidence REAL NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(trade_id) REFERENCES trades(id)
            );"""
        )

        cur.execute(
            """CREATE TABLE IF NOT EXISTS market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                price REAL NOT NULL,
                volume REAL,
                spread REAL,
                funding_rate REAL,
                liquidation_data TEXT,
                order_imbalance REAL,
                microtrend REAL,
                volatility REAL,
                regime TEXT
            );"""
        )

        cur.execute(
            """CREATE TABLE IF NOT EXISTS hive_consensus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                decision TEXT NOT NULL,
                avg_confidence REAL NOT NULL,
                votes_for INTEGER NOT NULL,
                votes_against INTEGER NOT NULL,
                reason TEXT
            );"""
        )

        cur.execute(
            """CREATE TABLE IF NOT EXISTS performance_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                total_pnl REAL,
                win_rate REAL,
                avg_trade_duration REAL,
                best_organism TEXT,
                trade_count INTEGER,
                open_count INTEGER,
                equity REAL
            );"""
        )

        cur.execute(
            """CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );"""
        )
        conn.commit()


init_db()


class DB:
    _lock = threading.RLock()

    @staticmethod
    def execute(sql: str, params: Tuple[Any, ...] = ()) -> None:
        with DB._lock, sqlite3.connect(DB_PATH, timeout=30) as conn:
            conn.execute(sql, params)
            conn.commit()

    @staticmethod
    def query(sql: str, params: Tuple[Any, ...] = ()) -> List[Tuple[Any, ...]]:
        with DB._lock, sqlite3.connect(DB_PATH, timeout=30) as conn:
            cur = conn.execute(sql, params)
            return cur.fetchall()

    @staticmethod
    def set_state(key: str, value: Any) -> None:
        DB.execute(
            "INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)",
            (key, safe_json_dump(value)),
        )

    @staticmethod
    def get_state(key: str, default: Any = None) -> Any:
        rows = DB.query("SELECT value FROM app_state WHERE key=?", (key,))
        if not rows:
            return default
        return safe_json_load(rows[0][0], default)


# =============================================================================
# Market data / live execution clients
# =============================================================================
class MarketClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.session = None
        self._last_req = 0.0
        self._rate_lock = threading.Lock()
        self.active_base = None
        self.offline_seed = abs(hash("hive_v7")) % (2**32)
        if requests is not None:
            try:
                self.session = requests.Session()
                self.session.headers.update({
                    "User-Agent": "Mozilla/5.0 HiveInstitutionalV7",
                    "Accept": "application/json",
                })
            except Exception:
                self.session = None

    def _base_urls(self) -> List[str]:
        mode = self.cfg.get("mode", {})
        bybit = self.cfg.get("bybit", {})
        if mode.get("live_mode"):
            return list(bybit.get("base_urls_live", []))
        return list(bybit.get("base_urls_testnet", [])) + list(bybit.get("base_urls_live", []))

    def get(self, path: str, params: Dict[str, Any], timeout: int = 8) -> Optional[Dict[str, Any]]:
        if self.session is None:
            return None
        with self._rate_lock:
            elapsed = time.time() - self._last_req
            if elapsed < 0.05:
                time.sleep(0.05 - elapsed)
            self._last_req = time.time()
        bases = [self.active_base] if self.active_base else []
        bases += [b for b in self._base_urls() if b != self.active_base]
        for base in bases:
            if not base:
                continue
            try:
                resp = self.session.get(f"{base}{path}", params=params, timeout=timeout)
                if resp.status_code in (403, 451):
                    continue
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict) and data.get("retCode", 0) == 0:
                    self.active_base = base
                    return data
            except Exception:
                continue
        return None

    def post(self, path: str, body: Dict[str, Any], timeout: int = 8) -> Optional[Dict[str, Any]]:
        # Placeholder live executor can be expanded with proper signing.
        if self.session is None:
            return None
        return None

    def synthetic_ohlcv(self, symbol: str, interval: str = "1", n: int = 240) -> pd.DataFrame:
        seed = (self.offline_seed + abs(hash((symbol, interval))) % (2**31)) % (2**32)
        rng = np.random.default_rng(seed)
        idx = pd.date_range(end=pd.Timestamp.now(tz=TZ), periods=n, freq="1min")
        base = 100 + np.cumsum(rng.normal(0, 0.18, n))
        cyc = np.sin(np.linspace(0, 14, n)) * rng.uniform(1.0, 2.5)
        trend = np.linspace(0, rng.normal(0, 5), n)
        close = base + cyc + trend
        open_ = np.r_[close[0], close[:-1]]
        high = np.maximum(open_, close) + np.abs(rng.normal(0.18, 0.07, n))
        low = np.minimum(open_, close) - np.abs(rng.normal(0.18, 0.07, n))
        volume = np.abs(rng.normal(800, 220, n)) * (1 + np.sin(np.linspace(0, 8, n)) * 0.25)
        turnover = volume * close
        return pd.DataFrame({"ts": idx, "open": open_, "high": high, "low": low, "close": close, "volume": volume, "turnover": turnover})

    def get_klines(self, symbol: str, interval: str = "1", limit: int = 240, category: str = "linear") -> pd.DataFrame:
        # Try real Bybit endpoint; otherwise fallback to synthetic but stable data.
        data = self.get("/v5/market/kline", {"category": category, "symbol": symbol, "interval": interval, "limit": limit})
        rows = (((data or {}).get("result") or {}).get("list") or []) if data else []
        if not rows:
            return self.synthetic_ohlcv(symbol, interval, limit)
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
        df["ts"] = pd.to_datetime(df["ts"].astype(np.int64), unit="ms", utc=True)
        for c in ["open", "high", "low", "close", "volume", "turnover"]:
            df[c] = df[c].astype(float)
        return df.sort_values("ts").reset_index(drop=True)

    def get_tickers(self, symbols: Optional[List[str]] = None) -> Dict[str, Dict[str, float]]:
        data = self.get("/v5/market/tickers", {"category": self.cfg.get("bybit", {}).get("category", "linear")})
        out: Dict[str, Dict[str, float]] = {}
        if data and data.get("result", {}).get("list"):
            for t in data["result"]["list"]:
                sym = t.get("symbol")
                if symbols and sym not in symbols:
                    continue
                try:
                    last = float(t.get("lastPrice") or 0)
                    bid = float(t.get("bid1Price") or last)
                    ask = float(t.get("ask1Price") or last)
                    out[sym] = {
                        "last": last,
                        "bid": bid,
                        "ask": ask,
                        "vol24": float(t.get("volume24h") or 0),
                        "turn24": float(t.get("turnover24h") or 0),
                        "chg": float(t.get("price24hPcnt") or 0),
                    }
                except Exception:
                    continue
        if out:
            return out
        # Offline synthetic tickers
        if symbols is None:
            symbols = self.cfg["universe"]["symbols"]
        rng = np.random.default_rng(self.offline_seed + 77)
        for i, sym in enumerate(symbols):
            last = 100 + i * 15 + rng.normal(0, 2.5)
            bid = last * (1 - 0.00018 - rng.uniform(0, 0.00012))
            ask = last * (1 + 0.00018 + rng.uniform(0, 0.00012))
            out[sym] = {
                "last": float(last),
                "bid": float(bid),
                "ask": float(ask),
                "vol24": float(2_000_000 + i * 170_000 + rng.normal(0, 120_000)),
                "turn24": float(5_500_000 + i * 520_000 + rng.normal(0, 300_000)),
                "chg": float(rng.normal(0, 0.025)),
            }
        return out


# =============================================================================
# Market intelligence / features
# =============================================================================
def compute_regime(df: pd.DataFrame) -> str:
    if df is None or len(df) < 50:
        return "RANGING"
    close = df["close"].astype(float).values
    high = df["high"].astype(float).values
    low = df["low"].astype(float).values
    prev = np.r_[close[0], close[:-1]]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))
    atr = pd.Series(tr).rolling(14).mean().iloc[-1]
    atr_pct = float(atr / (close[-1] + 1e-12))
    ema_fast = pd.Series(close).ewm(span=12, adjust=False).mean().iloc[-1]
    ema_slow = pd.Series(close).ewm(span=36, adjust=False).mean().iloc[-1]
    slope = float((close[-1] - close[-20]) / (close[-20] + 1e-12))
    if atr_pct > 0.018:
        return "HIGH_VOL"
    if ema_fast > ema_slow and slope > 0.004:
        return "TREND_UP"
    if ema_fast < ema_slow and slope < -0.004:
        return "TREND_DOWN"
    return "RANGING"


def atr(df: pd.DataFrame, n: int = 14) -> float:
    prev = df["close"].shift(1)
    tr = pd.concat([
        (df["high"] - df["low"]),
        (df["high"] - prev).abs(),
        (df["low"] - prev).abs(),
    ], axis=1).max(axis=1)
    return float(tr.rolling(n).mean().iloc[-1])


def microstructure_features(df: pd.DataFrame, ticker: Dict[str, float], timeframe: str = "1") -> Dict[str, float]:
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    if len(df) < 40:
        return {
            "mom": 0.0, "vol_surge": 0.0, "pressure": 0.0, "spread_q": 0.0,
            "rsi": 50.0, "rsi_ext": 0.0, "atr_pct": 0.0, "imbalance": 0.0,
            "microtrend": 0.0, "volatility": 0.0, "flow": 0.0,
        }

    lr = np.log(close / close.shift(1)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    mom = float(np.clip((close.iloc[-1] - close.iloc[-8]) / (close.iloc[-8] + 1e-12) * 18, -1, 1))
    vol_surge = float(np.clip((vol.iloc[-4:].mean() / (vol.iloc[-18:].mean() + 1e-12) - 1) * 1.8, -1, 1))
    pressure = float(np.clip(lr.iloc[-8:].mean() / (lr.iloc[-8:].std() + 1e-12) * 0.45, -1, 1))
    spread_bps = (ticker["ask"] - ticker["bid"]) / (ticker["last"] + 1e-12) * 10000
    spread_q = float(np.clip(1.0 - spread_bps / float(CFG["universe"]["max_spread_bps"]), 0.0, 1.0))

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(10).mean()
    loss = (-delta.clip(upper=0)).rolling(10).mean()
    rs = gain / (loss + 1e-12)
    rsi_val = float(100 - (100 / (1 + rs)).iloc[-1])
    rsi_ext = 1.0 if rsi_val < 28 else -1.0 if rsi_val > 72 else 0.4 if rsi_val < 38 else -0.4 if rsi_val > 62 else 0.0

    _atr = atr(df)
    atr_pct = float(_atr / (close.iloc[-1] + 1e-12))
    imbalance = float(np.clip((ticker["bid"] - ticker["ask"]) / (ticker["last"] + 1e-12) * 10000, -1, 1))
    microtrend = float(np.clip((close.iloc[-1] - close.iloc[-3]) / (close.iloc[-3] + 1e-12) * 30, -1, 1))
    volatility = float(np.clip(atr_pct / 0.015, 0, 2))
    flow = float(np.clip(0.55 * mom + 0.25 * pressure + 0.2 * vol_surge, -1, 1))

    return {
        "mom": mom,
        "vol_surge": vol_surge,
        "pressure": pressure,
        "spread_q": spread_q,
        "spread_bps": float(spread_bps),
        "rsi": rsi_val,
        "rsi_ext": rsi_ext,
        "atr_pct": atr_pct,
        "imbalance": imbalance,
        "microtrend": microtrend,
        "volatility": volatility,
        "flow": flow,
    }


def liquidity_proxies(df: pd.DataFrame, ticker: Dict[str, float]) -> Dict[str, float]:
    # No fake randomness; derive from candle structure and quote data.
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    vol = df["volume"].astype(float)
    range_pct = ((high - low) / (close + 1e-12)).rolling(10).mean().iloc[-1]
    wick_up = ((high - np.maximum(df["open"], df["close"])) / (close + 1e-12)).rolling(10).mean().iloc[-1]
    wick_dn = ((np.minimum(df["open"], df["close"]) - low) / (close + 1e-12)).rolling(10).mean().iloc[-1]
    vol_z = (vol.iloc[-1] - vol.iloc[-20:-1].mean()) / (vol.iloc[-20:-1].std() + 1e-12)
    spread_bps = (ticker["ask"] - ticker["bid"]) / (ticker["last"] + 1e-12) * 10000
    hidden_liquidity = float(np.clip(0.5 * (1 - spread_bps / 10) + 0.3 * np.tanh(vol_z / 3) + 0.2 * np.tanh(wick_dn - wick_up), 0, 1))
    iceberg_pressure = float(np.clip(np.tanh(vol_z / 2) * 0.5 + np.tanh(range_pct * 120) * 0.5, 0, 1))
    fake_wall_risk = float(np.clip(np.tanh((wick_up + wick_dn) * 14) * 0.5 + (1 - hidden_liquidity) * 0.5, 0, 1))
    return {
        "hidden_liquidity": hidden_liquidity,
        "iceberg_pressure": iceberg_pressure,
        "fake_wall_risk": fake_wall_risk,
        "range_pct": float(range_pct),
    }


# =============================================================================
# Organisms
# =============================================================================
@dataclass
class OrganismSignal:
    name: str
    side: str
    confidence: float
    reason: str
    score: float
    precision: float
    position_size_bias: float
    entry_precision: float
    exit_precision: float


@dataclass
class Organism:
    name: str
    role: str
    base_weight: float = 1.0

    def analyze(self, df: pd.DataFrame, ticker: Dict[str, float], features: Dict[str, float], regime: str, tf_label: str) -> OrganismSignal:
        raise NotImplementedError


class Ghost_Sniper(Organism):
    def __init__(self):
        super().__init__("Ghost_Sniper", "SNIPER", 1.25)

    def analyze(self, df, ticker, features, regime, tf_label):
        liq = liquidity_proxies(df, ticker)
        score = 0.42 * liq["hidden_liquidity"] + 0.34 * features["flow"] + 0.16 * features["spread_q"] - 0.18 * liq["fake_wall_risk"]
        side = "long" if features["flow"] > 0 and features["microtrend"] > -0.05 else "short" if features["flow"] < 0 and features["microtrend"] < 0.05 else "flat"
        if side == "flat":
            score *= 0.55
        conf = clamp(abs(score) * 0.92 + 0.12 * liq["iceberg_pressure"], 0, 1)
        reason = f"hidden_liquidity={liq['hidden_liquidity']:.2f}, iceberg={liq['iceberg_pressure']:.2f}, fake_wall={liq['fake_wall_risk']:.2f}"
        return OrganismSignal(self.name, side, conf, reason, float(score), precision=clamp(conf * 0.97, 0, 1), position_size_bias=clamp(0.7 + conf * 0.5, 0.6, 1.35), entry_precision=clamp(0.86 + conf * 0.1, 0, 1), exit_precision=clamp(0.80 + conf * 0.12, 0, 1))


class Shadow_Sniper(Organism):
    def __init__(self):
        super().__init__("Shadow_Sniper", "SNIPER", 1.20)

    def analyze(self, df, ticker, features, regime, tf_label):
        # Tracks whale-ish pressure via momentum/volume anomalies and spread compression.
        zvol = (df["volume"].iloc[-1] - df["volume"].iloc[-20:-1].mean()) / (df["volume"].iloc[-20:-1].std() + 1e-12)
        anomaly = np.tanh(zvol / 2.5)
        exchange_flow = features["flow"]
        funding_proxy = np.tanh((features["mom"] - features["pressure"]) * 2.3)
        score = 0.36 * exchange_flow + 0.28 * anomaly + 0.22 * (1 - features["spread_q"]) + 0.14 * funding_proxy
        side = "long" if exchange_flow > 0.1 else "short" if exchange_flow < -0.1 else ("long" if features["microtrend"] > 0 else "short")
        conf = clamp(abs(score) * 0.95 + 0.08 * abs(funding_proxy), 0, 1)
        reason = f"whale_pressure={anomaly:.2f}, flow={exchange_flow:.2f}, funding_proxy={funding_proxy:.2f}"
        return OrganismSignal(self.name, side, conf, reason, float(score), precision=clamp(0.65 + conf * 0.3, 0, 1), position_size_bias=clamp(0.75 + conf * 0.55, 0.6, 1.4), entry_precision=clamp(0.84 + conf * 0.1, 0, 1), exit_precision=clamp(0.78 + conf * 0.14, 0, 1))


class Venom_Sniper(Organism):
    def __init__(self):
        super().__init__("Venom_Sniper", "SNIPER", 1.18)

    def analyze(self, df, ticker, features, regime, tf_label):
        # Microstructure breaks: breakout + volatility expansion + acceleration.
        close = df["close"].astype(float)
        fast = close.ewm(span=8, adjust=False).mean().iloc[-1]
        slow = close.ewm(span=21, adjust=False).mean().iloc[-1]
        breakout = np.tanh(((close.iloc[-1] - close.iloc[-12: ].max()) / (close.iloc[-1] + 1e-12)) * -12)
        accel = np.tanh((features["microtrend"] + features["mom"]) * 2.2)
        vol_exp = np.tanh((features["volatility"] - 0.8) * 2.0)
        score = 0.40 * accel + 0.28 * breakout + 0.18 * vol_exp + 0.14 * np.sign(fast - slow)
        side = "long" if (fast > slow and accel > -0.05) else "short" if (fast < slow and accel < 0.05) else ("long" if score > 0 else "short")
        conf = clamp(abs(score) * 0.98 + 0.05 * abs(vol_exp), 0, 1)
        reason = f"breakout={breakout:.2f}, accel={accel:.2f}, vol_exp={vol_exp:.2f}"
        return OrganismSignal(self.name, side, conf, reason, float(score), precision=clamp(0.72 + conf * 0.24, 0, 1), position_size_bias=clamp(0.65 + conf * 0.45, 0.55, 1.25), entry_precision=clamp(0.88 + conf * 0.08, 0, 1), exit_precision=clamp(0.82 + conf * 0.1, 0, 1))


class Flash_Scalper(Organism):
    def __init__(self):
        super().__init__("Flash_Scalper", "SCALPER", 1.15)

    def analyze(self, df, ticker, features, regime, tf_label):
        imbalance = features["imbalance"]
        momentum = features["microtrend"]
        pressure = features["pressure"]
        score = 0.38 * momentum + 0.33 * pressure + 0.18 * features["spread_q"] + 0.11 * np.tanh(imbalance * 4)
        side = "long" if score > 0.03 else "short" if score < -0.03 else "flat"
        conf = clamp(abs(score) * 1.05 + 0.06 * features["spread_q"], 0, 1)
        reason = f"imbalance={imbalance:.2f}, momentum={momentum:.2f}, pressure={pressure:.2f}"
        return OrganismSignal(self.name, side, conf, reason, float(score), precision=clamp(0.70 + conf * 0.26, 0, 1), position_size_bias=clamp(0.80 + conf * 0.35, 0.7, 1.3), entry_precision=clamp(0.89 + conf * 0.08, 0, 1), exit_precision=clamp(0.87 + conf * 0.08, 0, 1))


class Vortex_Scalper(Organism):
    def __init__(self):
        super().__init__("Vortex_Scalper", "SCALPER", 1.10)

    def analyze(self, df, ticker, features, regime, tf_label):
        close = df["close"].astype(float)
        bb_mid = close.rolling(20).mean().iloc[-1]
        bb_std = close.rolling(20).std().iloc[-1]
        contraction = np.clip(1 - (bb_std / (close.iloc[-1] + 1e-12)) * 400, -1, 1)
        expansion = np.clip(features["volatility"] - 0.75, -1, 1)
        mean_revert = np.tanh(((close.iloc[-1] - bb_mid) / (bb_std + 1e-12)) * -0.45)
        score = 0.35 * contraction + 0.33 * expansion + 0.18 * mean_revert + 0.14 * features["flow"]
        side = "long" if (score > 0.02 and features["microtrend"] >= 0) else "short" if (score < -0.02 and features["microtrend"] <= 0) else "flat"
        conf = clamp(abs(score) * 1.00 + 0.05 * abs(mean_revert), 0, 1)
        reason = f"contraction={contraction:.2f}, expansion={expansion:.2f}, mean_revert={mean_revert:.2f}"
        return OrganismSignal(self.name, side, conf, reason, float(score), precision=clamp(0.69 + conf * 0.28, 0, 1), position_size_bias=clamp(0.78 + conf * 0.4, 0.7, 1.25), entry_precision=clamp(0.84 + conf * 0.12, 0, 1), exit_precision=clamp(0.85 + conf * 0.10, 0, 1))


class Pulse_Scalper(Organism):
    def __init__(self):
        super().__init__("Pulse_Scalper", "SCALPER", 1.12)

    def analyze(self, df, ticker, features, regime, tf_label):
        close = df["close"].astype(float)
        lr = np.log(close / close.shift(1)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        beat = float(np.tanh(lr.iloc[-5:].mean() / (lr.iloc[-10:].std() + 1e-12) * 2.8))
        alignment = float(np.tanh((features["mom"] + features["pressure"]) * 1.8))
        score = 0.44 * beat + 0.34 * alignment + 0.12 * features["spread_q"] + 0.10 * features["flow"]
        side = "long" if score > 0.025 else "short" if score < -0.025 else "flat"
        conf = clamp(abs(score) * 1.04 + 0.05 * features["spread_q"], 0, 1)
        reason = f"beat={beat:.2f}, alignment={alignment:.2f}, spread_q={features['spread_q']:.2f}"
        return OrganismSignal(self.name, side, conf, reason, float(score), precision=clamp(0.72 + conf * 0.24, 0, 1), position_size_bias=clamp(0.74 + conf * 0.42, 0.6, 1.28), entry_precision=clamp(0.86 + conf * 0.1, 0, 1), exit_precision=clamp(0.88 + conf * 0.08, 0, 1))


class Oracle_Analyst(Organism):
    def __init__(self):
        super().__init__("Oracle_Analyst", "ANALYST", 1.05)

    def analyze(self, df, ticker, features, regime, tf_label):
        # Multi-timeframe confluence approximation using three EMAs and price structure.
        close = df["close"].astype(float)
        tf_fast = close.ewm(span=9, adjust=False).mean().iloc[-1]
        tf_mid = close.ewm(span=21, adjust=False).mean().iloc[-1]
        tf_slow = close.ewm(span=55, adjust=False).mean().iloc[-1]
        stack = np.tanh(((tf_fast - tf_mid) + (tf_mid - tf_slow)) / (close.iloc[-1] + 1e-12) * 260)
        trend = np.tanh(features["mom"] * 1.7 + features["microtrend"] * 1.4)
        regime_bias = 0.2 if regime == "TREND_UP" else -0.2 if regime == "TREND_DOWN" else 0.0
        score = 0.44 * stack + 0.34 * trend + 0.12 * features["flow"] + 0.10 * regime_bias
        side = "long" if score > 0.02 else "short" if score < -0.02 else "flat"
        conf = clamp(abs(score) * 0.95 + 0.1 * abs(regime_bias), 0, 1)
        reason = f"stack={stack:.2f}, trend={trend:.2f}, regime={regime}"
        return OrganismSignal(self.name, side, conf, reason, float(score), precision=clamp(0.78 + conf * 0.18, 0, 1), position_size_bias=clamp(0.82 + conf * 0.35, 0.7, 1.2), entry_precision=clamp(0.80 + conf * 0.15, 0, 1), exit_precision=clamp(0.82 + conf * 0.14, 0, 1))


class Cipher_Analyst(Organism):
    def __init__(self):
        super().__init__("Cipher_Analyst", "ANALYST", 1.00)

    def analyze(self, df, ticker, features, regime, tf_label):
        close = df["close"].astype(float)
        hi = df["high"].astype(float)
        lo = df["low"].astype(float)
        pivot_hi = hi.rolling(20).max().iloc[-1]
        pivot_lo = lo.rolling(20).min().iloc[-1]
        pos = (close.iloc[-1] - pivot_lo) / (pivot_hi - pivot_lo + 1e-12)
        sr_bias = np.tanh((0.5 - pos) * 2.4)
        pattern = np.tanh((features["rsi_ext"] + features["pressure"] + features["mom"]) * 0.9)
        score = 0.42 * sr_bias + 0.31 * pattern + 0.17 * features["spread_q"] + 0.10 * features["vol_surge"]
        side = "long" if score > 0.02 else "short" if score < -0.02 else "flat"
        conf = clamp(abs(score) * 0.98 + 0.05 * (1 - abs(features["rsi_ext"])), 0, 1)
        reason = f"sr_bias={sr_bias:.2f}, pattern={pattern:.2f}, pos={pos:.2f}"
        return OrganismSignal(self.name, side, conf, reason, float(score), precision=clamp(0.74 + conf * 0.22, 0, 1), position_size_bias=clamp(0.78 + conf * 0.3, 0.7, 1.18), entry_precision=clamp(0.79 + conf * 0.14, 0, 1), exit_precision=clamp(0.85 + conf * 0.1, 0, 1))


# =============================================================================
# Trades / execution / position management
# =============================================================================
@dataclass
class LivePosition:
    trade_id: int
    symbol: str
    side: str
    entry_price: float
    size: float
    qty: float
    leverage: float
    opened_at: str
    consensus_score: float
    organisms_voted: List[str]
    reason: str
    stop_price: float
    take_profit_price: float
    partials: List[Dict[str, Any]] = field(default_factory=list)
    live_order_id: Optional[str] = None
    mode: str = "simulation"

    def direction(self) -> int:
        return 1 if self.side == "long" else -1


class ExecutionClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.enabled = bool(cfg.get("mode", {}).get("execution_enabled", False))
        self.testnet = bool(cfg.get("mode", {}).get("testnet", True))
        self.api_key = cfg.get("bybit", {}).get("api_key", "")
        self.api_secret = cfg.get("bybit", {}).get("api_secret", "")
        self.session = requests.Session() if requests is not None else None

    def can_live(self) -> bool:
        return self.enabled and bool(self.api_key) and bool(self.api_secret) and self.session is not None

    def place_market_order(self, symbol: str, side: str, qty: float) -> Dict[str, Any]:
        # Safe placeholder. Real signing can be added; we keep simulation-first.
        return {"ok": False, "mode": "simulation", "order_id": f"SIM-{now_ts_ms()}", "reason": "live execution not wired with signature in this safe build"}


class HiveInstitutionalV7:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.lock = threading.RLock()
        self.running = False
        self.stop_event = threading.Event()
        self.market = MarketClient(cfg)
        self.exec = ExecutionClient(cfg)
        self.symbols = list(cfg.get("universe", {}).get("symbols", []))[: int(cfg.get("universe", {}).get("max_symbols", 16))]
        self.scan_interval_sec = int(cfg.get("mode", {}).get("scan_interval_sec", 30))
        self.manage_interval_sec = int(cfg.get("mode", {}).get("manage_interval_sec", 10))
        self.dashboard_tick_sec = int(cfg.get("mode", {}).get("dashboard_tick_sec", 5))
        self.risk = cfg.get("risk", {})
        self.learning = cfg.get("learning", {})
        self.initial_capital = float(self.risk.get("initial_capital", 500.0))
        self.equity_value = float(DB.get_state("equity_value", self.initial_capital))
        self.peak_equity = float(DB.get_state("peak_equity", self.initial_capital))
        self.consecutive_losses = int(DB.get_state("consecutive_losses", 0))
        self.daily_pnl = float(DB.get_state("daily_pnl", 0.0))
        self.last_scan_ts = 0.0
        self.last_manage_ts = 0.0
        self.last_dashboard_ts = 0.0
        self.scan_results: List[Dict[str, Any]] = []
        self.consensus_rows: List[Dict[str, Any]] = []
        self.snapshot_rows: Dict[str, Dict[str, Any]] = {}
        self.performance_cache: Dict[str, Any] = {}
        self.action_log: deque = deque(maxlen=200)
        self.position_map: Dict[int, LivePosition] = {}
        self._position_lock = threading.RLock()
        self._data_cache: Dict[Tuple[str, str], pd.DataFrame] = {}
        self._ticker_cache: Dict[str, Dict[str, float]] = {}
        self._organisms = [
            Ghost_Sniper(), Shadow_Sniper(), Venom_Sniper(),
            Flash_Scalper(), Vortex_Scalper(), Pulse_Scalper(),
            Oracle_Analyst(), Cipher_Analyst(),
        ]
        self.generation = int(DB.get_state("generation", 1))
        self.learning_memory = deque(maxlen=int(self.learning.get("pattern_memory_size", 500)))
        self._last_metrics_write = 0.0

    # ------------------------------- state -------------------------------
    def equity(self) -> float:
        return float(self.equity_value)

    def open_positions(self) -> List[LivePosition]:
        with self._position_lock:
            return list(self.position_map.values())

    def open_positions_count(self) -> int:
        return len(self.open_positions())

    def load_open_positions_from_db(self) -> None:
        rows = DB.query(
            """SELECT id, symbol, side, entry_price, size, leverage, opened_at, consensus_score,
                      organisms_voted, reason, stop_price, take_profit_price, partials, live_order_id, mode, qty
               FROM trades WHERE status='open'"""
        )
        with self._position_lock:
            self.position_map.clear()
            for r in rows:
                p = LivePosition(
                    trade_id=int(r[0]),
                    symbol=r[1],
                    side=r[2],
                    entry_price=float(r[3]),
                    size=float(r[4]),
                    qty=float(r[15]) if r[15] is not None else float(r[4]) / max(float(r[3]), 1e-12),
                    leverage=float(r[5]),
                    opened_at=r[6],
                    consensus_score=float(r[7] or 0),
                    organisms_voted=safe_json_load(r[8], []) or [],
                    reason=r[9] or "",
                    stop_price=float(r[10] or 0),
                    take_profit_price=float(r[11] or 0),
                    partials=safe_json_load(r[12], []) or [],
                    live_order_id=r[13],
                    mode=r[14] or "simulation",
                )
                self.position_map[p.trade_id] = p

    # ------------------------------- data -------------------------------
    def get_ticker_universe(self) -> Dict[str, Dict[str, float]]:
        tickers = self.market.get_tickers(self.symbols)
        self._ticker_cache = tickers
        return tickers

    def get_df(self, symbol: str, interval: str = "1", limit: int = 240) -> pd.DataFrame:
        key = (symbol, interval)
        df = self.market.get_klines(symbol, interval=interval, limit=limit, category=self.cfg.get("bybit", {}).get("category", "linear"))
        self._data_cache[key] = df
        return df

    def scan_symbol(self, symbol: str, ticker: Dict[str, float]) -> Optional[Dict[str, Any]]:
        try:
            df1 = self.get_df(symbol, "1", 240)
            df5 = self.get_df(symbol, "5", 240)
            df15 = self.get_df(symbol, "15", 240)
            reg1 = compute_regime(df1)
            reg5 = compute_regime(df5)
            reg15 = compute_regime(df15)
            regime = reg1 if reg1 == reg5 else reg5 if reg5 == reg15 else reg1
            feat1 = microstructure_features(df1, ticker, "1")
            feat5 = microstructure_features(df5, ticker, "5")
            feat15 = microstructure_features(df15, ticker, "15")
            features = {
                "mom": float(0.5 * feat1["mom"] + 0.3 * feat5["mom"] + 0.2 * feat15["mom"]),
                "vol_surge": float(0.55 * feat1["vol_surge"] + 0.3 * feat5["vol_surge"] + 0.15 * feat15["vol_surge"]),
                "pressure": float(0.5 * feat1["pressure"] + 0.3 * feat5["pressure"] + 0.2 * feat15["pressure"]),
                "spread_q": feat1["spread_q"],
                "spread_bps": feat1["spread_bps"],
                "rsi": float(0.5 * feat1["rsi"] + 0.3 * feat5["rsi"] + 0.2 * feat15["rsi"]),
                "rsi_ext": float(0.5 * feat1["rsi_ext"] + 0.3 * feat5["rsi_ext"] + 0.2 * feat15["rsi_ext"]),
                "atr_pct": float(0.5 * feat1["atr_pct"] + 0.3 * feat5["atr_pct"] + 0.2 * feat15["atr_pct"]),
                "imbalance": float(0.5 * feat1["imbalance"] + 0.3 * feat5["imbalance"] + 0.2 * feat15["imbalance"]),
                "microtrend": float(0.5 * feat1["microtrend"] + 0.3 * feat5["microtrend"] + 0.2 * feat15["microtrend"]),
                "volatility": float(0.5 * feat1["volatility"] + 0.3 * feat5["volatility"] + 0.2 * feat15["volatility"]),
                "flow": float(0.5 * feat1["flow"] + 0.3 * feat5["flow"] + 0.2 * feat15["flow"]),
            }

            rows = []
            for org in self._organisms:
                sig = org.analyze(df1, ticker, features, regime, "1m")
                rows.append(sig)

            consensus = self.calculate_consensus(symbol, ticker, df1, features, regime, rows)
            self._persist_snapshot(symbol, ticker, features, regime)
            return {
                "symbol": symbol,
                "ticker": ticker,
                "regime": regime,
                "features": features,
                "organisms": rows,
                "consensus": consensus,
            }
        except Exception as e:
            log.exception("scan_symbol error for %s: %s", symbol, e)
            return None

    def _persist_snapshot(self, symbol: str, ticker: Dict[str, float], features: Dict[str, float], regime: str) -> None:
        try:
            DB.execute(
                """INSERT INTO market_snapshots
                   (symbol, timestamp, price, volume, spread, funding_rate, liquidation_data, order_imbalance, microtrend, volatility, regime)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    symbol,
                    utc_now(),
                    float(ticker["last"]),
                    float(ticker.get("vol24", 0.0)),
                    float((ticker["ask"] - ticker["bid"]) / max(ticker["last"], 1e-12)),
                    float(features.get("flow", 0.0) * 0.002),
                    safe_json_dump({"hidden_liquidity": max(0.0, min(1.0, 0.5 + 0.5 * features.get("flow", 0.0)))}),
                    float(features.get("imbalance", 0.0)),
                    float(features.get("microtrend", 0.0)),
                    float(features.get("volatility", 0.0)),
                    regime,
                ),
            )
        except Exception:
            log.exception("Failed persisting market snapshot for %s", symbol)

    # ------------------------------- consensus -------------------------------
    def calculate_consensus(self, symbol: str, ticker: Dict[str, float], df: pd.DataFrame, features: Dict[str, float], regime: str, organism_signals: List[OrganismSignal]) -> Dict[str, Any]:
        valid = [s for s in organism_signals if s.side != "flat" and s.confidence > 0.15]
        votes_for = len([s for s in valid if s.side == "long"])
        votes_against = len([s for s in valid if s.side == "short"])
        long_score = sum(s.score * s.confidence for s in valid if s.side == "long")
        short_score = sum(abs(s.score) * s.confidence for s in valid if s.side == "short")
        chosen = "hold"
        avg_conf = float(np.mean([s.confidence for s in valid])) if valid else 0.0
        consensus_score = 0.0
        if long_score > short_score and long_score >= self.learning["score_threshold"]:
            chosen = "long"
            consensus_score = float(long_score)
        elif short_score > long_score and short_score >= self.learning["score_threshold"]:
            chosen = "short"
            consensus_score = float(short_score)

        # multi-timeframe alignment boost
        align_boost = 0.0
        if len(df) >= 55:
            close = df["close"].astype(float)
            e9 = close.ewm(span=9, adjust=False).mean().iloc[-1]
            e21 = close.ewm(span=21, adjust=False).mean().iloc[-1]
            e55 = close.ewm(span=55, adjust=False).mean().iloc[-1]
            if chosen == "long" and e9 > e21 > e55:
                align_boost = 0.10
            elif chosen == "short" and e9 < e21 < e55:
                align_boost = 0.10
        consensus_score = float(consensus_score + align_boost)

        reason = f"regime={regime}; long={long_score:.2f}; short={short_score:.2f}; align={align_boost:.2f}"
        DB.execute(
            """INSERT INTO hive_consensus (timestamp, symbol, decision, avg_confidence, votes_for, votes_against, reason)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (utc_now(), symbol, chosen, avg_conf, votes_for, votes_against, reason),
        )
        row = {
            "timestamp": utc_now(),
            "symbol": symbol,
            "decision": chosen,
            "avg_confidence": avg_conf,
            "votes_for": votes_for,
            "votes_against": votes_against,
            "consensus_score": consensus_score,
            "reason": reason,
            "organisms": organism_signals,
            "features": features,
            "regime": regime,
        }
        self.consensus_rows.append(row)
        self.consensus_rows = self.consensus_rows[-400:]
        return row

    def universe_rank(self) -> List[Dict[str, Any]]:
        tickers = self.get_ticker_universe()
        ranked = []
        for symbol in self.symbols:
            t = tickers.get(symbol)
            if not t:
                continue
            spread_bps = (t["ask"] - t["bid"]) / max(t["last"], 1e-12) * 10000
            if t.get("turn24", 0) < float(self.cfg["universe"]["min_turnover_24h"]):
                continue
            if spread_bps > float(self.cfg["universe"]["max_spread_bps"]):
                continue
            df = self._data_cache.get((symbol, "1")) or self.get_df(symbol, "1", 240)
            reg = compute_regime(df)
            feat = microstructure_features(df, t, "1")
            score = (
                0.25 * math.log10(max(t["turn24"], 1.0))
                + 0.28 * abs(t.get("chg", 0.0)) * 100
                + 0.18 * feat["volatility"]
                + 0.12 * feat["spread_q"]
                + 0.17 * abs(feat["flow"])
            )
            ranked.append({
                "symbol": symbol,
                "score": float(score),
                "regime": reg,
                "price": float(t["last"]),
                "spread_bps": float(spread_bps),
                "turn24": float(t.get("turn24", 0.0)),
                "flow": float(feat["flow"]),
                "volatility": float(feat["volatility"]),
                "chg": float(t.get("chg", 0.0)),
            })
        ranked.sort(key=lambda x: x["score"], reverse=True)
        return ranked

    def scan_all_symbols(self) -> None:
        tickers = self.get_ticker_universe()
        ranked = self.universe_rank()
        self.scan_results = []
        for item in ranked[: min(len(ranked), len(self.symbols))]:
            symbol = item["symbol"]
            t = tickers.get(symbol)
            if not t:
                continue
            res = self.scan_symbol(symbol, t)
            if not res:
                continue
            self.scan_results.append({
                "symbol": symbol,
                "rank_score": item["score"],
                "decision": res["consensus"]["decision"],
                "consensus_score": res["consensus"]["consensus_score"],
                "avg_confidence": res["consensus"]["avg_confidence"],
                "regime": res["regime"],
                "price": t["last"],
                "spread_bps": (t["ask"] - t["bid"]) / max(t["last"], 1e-12) * 10000,
                "organisms": res["organisms"],
                "features": res["features"],
            })
        self.scan_results.sort(key=lambda x: (x["consensus_score"], x["avg_confidence"], x["rank_score"]), reverse=True)
        self.last_scan_ts = time.time()

    # ------------------------------- execution -------------------------------
    def _risk_size(self, symbol: str, ticker: Dict[str, float], features: Dict[str, float], consensus_score: float) -> Tuple[float, float, float]:
        base_risk = float(self.risk.get("risk_per_trade", 0.011))
        atr_pct = max(features.get("atr_pct", 0.01), 0.003)
        leverage = float(self.risk.get("base_leverage", 20))
        leverage = clamp(leverage, float(self.risk.get("min_leverage", 5)), float(self.risk.get("max_leverage", 50)))
        risk_adj = clamp(base_risk * (0.8 + consensus_score), 0.002, 0.03)
        size_usd = self.equity() * risk_adj * 1.15 / max(atr_pct * leverage, 0.0001)
        size_usd = clamp(size_usd, 10.0, self.equity() * 0.35)
        return size_usd, leverage, atr_pct

    def _create_trade_row(self, symbol: str, side: str, entry_price: float, size: float, leverage: float, consensus_score: float, reason: str, organisms: List[OrganismSignal], features: Dict[str, float], mode: str) -> int:
        tp_mult = 1.8 * features.get("atr_pct", 0.01)
        sl_mult = float(self.risk.get("atr_stop_mult", 1.8)) * features.get("atr_pct", 0.01)
        stop = entry_price * (1 - sl_mult if side == "long" else 1 + sl_mult)
        take = entry_price * (1 + tp_mult if side == "long" else 1 - tp_mult)
        cur = sqlite3.connect(DB_PATH, timeout=30).cursor()
        cur.execute(
            """INSERT INTO trades
               (symbol, side, entry_price, exit_price, size, pnl, status, opened_at, closed_at,
                organisms_voted, consensus_score, reason, mode, leverage, stop_price, take_profit_price,
                partials, live_order_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                symbol, side, float(entry_price), None, float(size), None, "open", utc_now(), None,
                safe_json_dump([s.name for s in organisms]), float(consensus_score), reason, mode, float(leverage),
                float(stop), float(take), safe_json_dump([]), None,
            ),
        )
        trade_id = cur.lastrowid
        sqlite3.connect(DB_PATH, timeout=30).commit()
        return int(trade_id)

    def execute_trade(self, scan_row: Dict[str, Any]) -> Optional[int]:
        symbol = scan_row["symbol"]
        decision = scan_row["decision"]
        if decision not in ("long", "short"):
            return None
        if self.open_positions_count() >= int(self.risk.get("max_positions", 5)):
            return None
        if any(p.symbol == symbol for p in self.open_positions()):
            return None
        ticker = self._ticker_cache.get(symbol) or self.get_ticker_universe().get(symbol)
        if not ticker:
            return None
        features = scan_row["features"]
        size_usd, leverage, atr_pct = self._risk_size(symbol, ticker, features, scan_row["consensus_score"])
        side = decision
        entry = ticker["ask"] if side == "long" else ticker["bid"]
        mode = "simulation"
        live_order_id = None
        if self.exec.can_live():
            live = self.exec.place_market_order(symbol, side, size_usd)
            live_order_id = live.get("order_id")
            mode = "live" if live.get("ok") else "simulation"
        trade_id = self._create_trade_row(symbol, side, entry, size_usd, leverage, scan_row["consensus_score"], scan_row["organisms"][0].reason if scan_row["organisms"] else scan_row["regime"], scan_row["organisms"], features, mode)
        p = LivePosition(
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            entry_price=entry,
            size=size_usd,
            qty=(size_usd * leverage) / max(entry, 1e-12),
            leverage=leverage,
            opened_at=utc_now(),
            consensus_score=scan_row["consensus_score"],
            organisms_voted=[s.name for s in scan_row["organisms"]],
            reason=scan_row["regime"],
            stop_price=entry * (1 - 1.8 * atr_pct if side == "long" else 1 + 1.8 * atr_pct),
            take_profit_price=entry * (1 + 2.2 * atr_pct if side == "long" else 1 - 2.2 * atr_pct),
            live_order_id=live_order_id,
            mode=mode,
        )
        with self._position_lock:
            self.position_map[trade_id] = p
        DB.execute(
            "INSERT INTO organisms_decisions (trade_id, organism_name, signal, confidence, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (trade_id, "HIVE", side, float(scan_row["consensus_score"]), scan_row["reason"], utc_now()),
        )
        for s in scan_row["organisms"]:
            DB.execute(
                "INSERT INTO organisms_decisions (trade_id, organism_name, signal, confidence, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (trade_id, s.name, s.side, float(s.confidence), s.reason, utc_now()),
            )
        self.action_log.appendleft({"ts": utc_now(), "action": "open", "symbol": symbol, "side": side, "trade_id": trade_id})
        return trade_id

    def _close_trade(self, pos: LivePosition, exit_price: float, reason: str) -> None:
        pnl = (exit_price - pos.entry_price) * pos.qty if pos.side == "long" else (pos.entry_price - exit_price) * pos.qty
        pnl -= pos.size * 0.0006  # fees approximation
        DB.execute(
            """UPDATE trades
               SET exit_price=?, pnl=?, status='closed', closed_at=?, reason=?
               WHERE id=?""",
            (float(exit_price), float(pnl), utc_now(), reason, pos.trade_id),
        )
        with self._position_lock:
            self.position_map.pop(pos.trade_id, None)
        self.equity_value += pnl
        self.peak_equity = max(self.peak_equity, self.equity_value)
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        self.daily_pnl += pnl
        DB.set_state("equity_value", self.equity_value)
        DB.set_state("peak_equity", self.peak_equity)
        DB.set_state("consecutive_losses", self.consecutive_losses)
        DB.set_state("daily_pnl", self.daily_pnl)
        self.action_log.appendleft({"ts": utc_now(), "action": "close", "symbol": pos.symbol, "side": pos.side, "trade_id": pos.trade_id, "pnl": pnl, "reason": reason})

    def manage_open_positions(self) -> None:
        try:
            tickers = self.get_ticker_universe()
            with self._position_lock:
                positions = list(self.position_map.values())
            for pos in positions:
                t = tickers.get(pos.symbol)
                if not t:
                    continue
                mid = t["last"]
                if pos.side == "long":
                    # partial close on 1R and 2R, final close on stop/target.
                    r = max(pos.entry_price - pos.stop_price, pos.entry_price * 0.001)
                    gain = mid - pos.entry_price
                    if gain >= r and not any(p.get("tag") == "1R" for p in pos.partials):
                        pos.partials.append({"tag": "1R", "pct": float(self.risk.get("partial_exit_1r", 0.25)), "price": mid, "ts": utc_now()})
                    if gain >= 2 * r and not any(p.get("tag") == "2R" for p in pos.partials):
                        pos.partials.append({"tag": "2R", "pct": float(self.risk.get("partial_exit_2r", 0.25)), "price": mid, "ts": utc_now()})
                    if mid <= pos.stop_price:
                        self._close_trade(pos, mid, "stop_loss")
                        continue
                    if mid >= pos.take_profit_price:
                        self._close_trade(pos, mid, "take_profit")
                        continue
                    # trail
                    new_stop = mid - r * 0.85
                    if new_stop > pos.stop_price:
                        pos.stop_price = new_stop
                        DB.execute("UPDATE trades SET stop_price=?, partials=? WHERE id=?", (float(pos.stop_price), safe_json_dump(pos.partials), pos.trade_id))
                else:
                    r = max(pos.stop_price - pos.entry_price, pos.entry_price * 0.001)
                    gain = pos.entry_price - mid
                    if gain >= r and not any(p.get("tag") == "1R" for p in pos.partials):
                        pos.partials.append({"tag": "1R", "pct": float(self.risk.get("partial_exit_1r", 0.25)), "price": mid, "ts": utc_now()})
                    if gain >= 2 * r and not any(p.get("tag") == "2R" for p in pos.partials):
                        pos.partials.append({"tag": "2R", "pct": float(self.risk.get("partial_exit_2r", 0.25)), "price": mid, "ts": utc_now()})
                    if mid >= pos.stop_price:
                        self._close_trade(pos, mid, "stop_loss")
                        continue
                    if mid <= pos.take_profit_price:
                        self._close_trade(pos, mid, "take_profit")
                        continue
                    new_stop = mid + r * 0.85
                    if new_stop < pos.stop_price:
                        pos.stop_price = new_stop
                        DB.execute("UPDATE trades SET stop_price=?, partials=? WHERE id=?", (float(pos.stop_price), safe_json_dump(pos.partials), pos.trade_id))
        except Exception as e:
            log.exception("manage_open_positions failed: %s", e)

    # ------------------------------- learning / metrics -------------------------------
    def write_performance_metrics(self) -> None:
        try:
            closed = DB.query("SELECT pnl, opened_at, closed_at, reason FROM trades WHERE status='closed' ORDER BY id DESC LIMIT 500")
            trade_count = len(closed)
            wins = sum(1 for r in closed if r[0] is not None and float(r[0]) > 0)
            win_rate = wins / trade_count if trade_count else 0.0
            total_pnl = float(sum(float(r[0] or 0) for r in closed))
            durations = []
            for r in closed:
                try:
                    a = pd.Timestamp(r[1])
                    b = pd.Timestamp(r[2]) if r[2] else a
                    durations.append((b - a).total_seconds() / 60.0)
                except Exception:
                    pass
            avg_dur = float(np.mean(durations)) if durations else 0.0
            best_org = self.best_organism()
            DB.execute(
                """INSERT INTO performance_metrics (date, total_pnl, win_rate, avg_trade_duration, best_organism, trade_count, open_count, equity)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (datetime.now(TZ).date().isoformat(), total_pnl, win_rate, avg_dur, best_org, trade_count, self.open_positions_count(), self.equity()),
            )
        except Exception:
            log.exception("write_performance_metrics failed")

    def best_organism(self) -> str:
        rows = DB.query("SELECT organism_name, AVG(confidence) FROM organisms_decisions GROUP BY organism_name ORDER BY AVG(confidence) DESC LIMIT 1")
        if rows:
            return str(rows[0][0])
        return "HIVE"

    def maybe_update_learning(self) -> None:
        try:
            # Conservative adaptive tuning from recent outcomes.
            closed = DB.query("SELECT pnl, consensus_score FROM trades WHERE status='closed' ORDER BY id DESC LIMIT 60")
            if len(closed) < 8:
                return
            pnls = [float(r[0] or 0) for r in closed]
            avg_pnl = float(np.mean(pnls))
            win_rate = sum(1 for p in pnls if p > 0) / len(pnls)
            score_threshold = float(self.learning["score_threshold"])
            conv_threshold = float(self.learning["conv_threshold"])
            if win_rate < 0.4:
                score_threshold = clamp(score_threshold + 0.01, 0.45, 0.75)
                conv_threshold = clamp(conv_threshold + 0.01, 0.35, 0.70)
            elif win_rate > 0.55 and avg_pnl > 0:
                score_threshold = clamp(score_threshold - 0.005, 0.35, 0.70)
                conv_threshold = clamp(conv_threshold - 0.005, 0.25, 0.65)
            self.learning["score_threshold"] = float(score_threshold)
            self.learning["conv_threshold"] = float(conv_threshold)
            DB.set_state("learning", self.learning)
        except Exception:
            log.exception("maybe_update_learning failed")

    # ------------------------------- loop -------------------------------
    def should_scan(self) -> bool:
        return (time.time() - self.last_scan_ts) >= self.scan_interval_sec

    def should_manage(self) -> bool:
        return (time.time() - self.last_manage_ts) >= self.manage_interval_sec

    def decision_cycle(self) -> None:
        try:
            if self.should_scan():
                self.scan_all_symbols()
                self.last_scan_ts = time.time()
                # Immediately act on best opportunities
                for row in self.scan_results[:8]:
                    if row["decision"] in ("long", "short") and row["consensus_score"] >= self.learning["conv_threshold"]:
                        self.execute_trade(row)
                        # open at most one per scan burst per cycle if already strong
                        break
            if self.should_manage():
                self.manage_open_positions()
                self.last_manage_ts = time.time()
                self.maybe_update_learning()
                if time.time() - self._last_metrics_write > 60:
                    self.write_performance_metrics()
                    self._last_metrics_write = time.time()
            # keep state live even in simulation
            DB.set_state("equity_value", self.equity())
            DB.set_state("peak_equity", self.peak_equity)
        except Exception as e:
            log.exception("decision_cycle error: %s", e)

    def run_background(self) -> None:
        self.running = True
        self.stop_event.clear()
        self.load_open_positions_from_db()
        log.info("Background loop started")
        while not self.stop_event.is_set():
            start = time.time()
            self.decision_cycle()
            elapsed = time.time() - start
            # short wait to reduce CPU while remaining responsive
            self.stop_event.wait(max(0.25, min(1.0, 1.0 - elapsed)))
        log.info("Background loop stopped")

    def start(self) -> None:
        if self.running:
            return
        self.thread = threading.Thread(target=self.run_background, name="hive-v7-loop", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.running = False
        self.stop_event.set()
        try:
            self.thread.join(timeout=2.0)
        except Exception:
            pass


# =============================================================================
# Dash UI
# =============================================================================
def base_card(title: str, body: Any, accent: str = CYAN) -> html.Div:
    return html.Div(
        [
            html.Div(rtl_text(title), style={"color": accent, "fontWeight": "700", "fontSize": "1.05rem", "marginBottom": "0.5rem"}),
            body,
        ],
        style={
            "background": CARD,
            "border": f"1px solid {hex_to_rgba(accent, 0.35)}",
            "borderRadius": "16px",
            "padding": "14px 14px 10px 14px",
            "boxShadow": f"0 0 20px {hex_to_rgba(accent, 0.08)}",
            "marginBottom": "12px",
        },
    )


def make_badge(text: str, color: str) -> html.Span:
    return html.Span(
        rtl_text(text),
        style={
            "display": "inline-block",
            "padding": "4px 10px",
            "borderRadius": "999px",
            "background": hex_to_rgba(color, 0.18),
            "color": color,
            "border": f"1px solid {hex_to_rgba(color, 0.35)}",
            "marginInlineEnd": "8px",
            "fontSize": "0.78rem",
        },
    )


def build_layout(app: dash.Dash, hive: HiveInstitutionalV7) -> html.Div:
    return html.Div(
        [
            dcc.Interval(id="tick-main", interval=int(hive.dashboard_tick_sec * 1000), n_intervals=0),
            dcc.Store(id="store-state", data={"ready": True}),
            html.Div(
                [
                    html.Div(rtl_text(APP_TITLE), style={"fontSize": "1.6rem", "fontWeight": "800", "color": GOLD}),
                    html.Div(
                        [
                            make_badge("RTL", CYAN),
                            make_badge("Testnet" if CFG["mode"]["testnet"] else "Live", ORANGE if CFG["mode"]["testnet"] else RED),
                            make_badge("Execution OFF" if not CFG["mode"]["execution_enabled"] else "Execution ON", RED if not CFG["mode"]["execution_enabled"] else GREEN),
                        ],
                        style={"marginTop": "8px"},
                    ),
                ],
                style={"padding": "18px 18px 6px 18px"},
            ),
            dcc.Tabs(
                id="main-tabs",
                value="tab-trades",
                children=[
                    dcc.Tab(label="🎯 LIVE TRADES", value="tab-trades", style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
                    dcc.Tab(label="🔬 ORGANISM PULSE", value="tab-orgs", style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
                    dcc.Tab(label="📊 MARKET SCAN", value="tab-scan", style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
                    dcc.Tab(label="🧠 HIVE MIND", value="tab-hive", style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
                    dcc.Tab(label="📈 PERFORMANCE", value="tab-perf", style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
                    dcc.Tab(label="⚙️ CONTROL", value="tab-control", style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
                ],
                colors={"border": "#22314f", "primary": CYAN, "background": "#0a1220"},
            ),
            html.Div(id="tab-content", style={"padding": "14px 18px 20px 18px"}),
        ],
        style={
            "background": BG,
            "minHeight": "100vh",
            "color": TXT,
            "direction": "rtl" if CFG.get("app", {}).get("rtl", True) else "ltr",
            "fontFamily": "Vazirmatn, IRANSans, Segoe UI, sans-serif",
        },
    )


TAB_STYLE = {
    "background": "#0f1830",
    "color": TXT,
    "border": "1px solid #22314f",
    "padding": "10px 12px",
    "fontWeight": "700",
}
TAB_SELECTED_STYLE = {
    "background": "#182646",
    "color": GOLD,
    "border": "1px solid #3b4d77",
    "padding": "10px 12px",
    "fontWeight": "800",
}


def render_trades(hive: HiveInstitutionalV7) -> html.Div:
    positions = hive.open_positions()
    open_rows = []
    for p in positions:
        t = hive._ticker_cache.get(p.symbol, {"last": p.entry_price})
        cur = float(t["last"])
        pnl = (cur - p.entry_price) * p.qty if p.side == "long" else (p.entry_price - cur) * p.qty
        open_rows.append(html.Tr([
            html.Td(p.trade_id), html.Td(p.symbol), html.Td(p.side), html.Td(fmt_num(p.entry_price)), html.Td(fmt_num(cur)), html.Td(fmt_money(p.size)),
            html.Td(fmt_money(pnl)), html.Td(f"{p.consensus_score:.2f}"), html.Td(f"{p.stop_price:.4f}"), html.Td(f"{p.take_profit_price:.4f}"), html.Td(p.mode),
        ]))
    open_table = html.Table([
        html.Thead(html.Tr([html.Th(h) for h in ["ID", "Symbol", "Side", "Entry", "Mark", "Size", "PnL", "Consensus", "Stop", "TP", "Mode"]])),
        html.Tbody(open_rows or [html.Tr(html.Td("No open positions", colSpan=11, style={"textAlign": "center", "color": MUTED}))]),
    ], style=TABLE_STYLE)

    closed = DB.query("SELECT id, symbol, side, entry_price, exit_price, size, pnl, opened_at, closed_at, status FROM trades ORDER BY id DESC LIMIT 12")
    closed_table = html.Table([
        html.Thead(html.Tr([html.Th(h) for h in ["ID", "Symbol", "Side", "Entry", "Exit", "Size", "PnL", "Opened", "Closed", "Status"]])),
        html.Tbody([
            html.Tr([html.Td(c[0]), html.Td(c[1]), html.Td(c[2]), html.Td(fmt_num(c[3])), html.Td(fmt_num(c[4] or c[3])), html.Td(fmt_money(c[5])), html.Td(fmt_money(c[6] or 0)), html.Td(c[7][:19] if c[7] else ""), html.Td((c[8] or "")[:19]), html.Td(c[9])])
            for c in closed
        ] or [html.Tr(html.Td("No closed trades", colSpan=10, style={"textAlign": "center", "color": MUTED}))]),
    ], style=TABLE_STYLE)

    return html.Div([
        html.Div([html.Div([html.H4(rtl_text("Open Positions"), style={"margin": 0}), html.Div(f"Equity: {fmt_money(hive.equity())}", style={"color": MUTED})])], style={"marginBottom": "10px"}),
        base_card("Active Positions", open_table, CYAN),
        base_card("Recent Closed Trades", closed_table, GOLD),
    ])


TABLE_STYLE = {
    "width": "100%",
    "borderCollapse": "collapse",
    "fontSize": "0.88rem",
}


def render_orgs(hive: HiveInstitutionalV7) -> html.Div:
    rows = []
    latest = hive.scan_results[0] if hive.scan_results else None
    signals = {s.name: s for s in (latest["organisms"] if latest else [])}
    for org in hive._organisms:
        s = signals.get(org.name)
        rows.append(html.Tr([
            html.Td(org.name),
            html.Td(org.role),
            html.Td(s.side if s else "—"),
            html.Td(f"{(s.confidence if s else 0):.2f}"),
            html.Td(f"{(s.score if s else 0):.3f}"),
            html.Td((s.reason if s else "No signal")[:120]),
            html.Td(f"{(s.position_size_bias if s else 1.0):.2f}"),
            html.Td(f"{(s.entry_precision if s else 0):.2f}"),
            html.Td(f"{(s.exit_precision if s else 0):.2f}"),
        ]))
    table = html.Table([
        html.Thead(html.Tr([html.Th(h) for h in ["Organism", "Type", "Signal", "Conf", "Score", "Reason", "Size Bias", "Entry Px", "Exit Px"]])),
        html.Tbody(rows),
    ], style=TABLE_STYLE)
    return html.Div([
        base_card("Organism Pulse", table, NEON),
        html.Div(
            [
                html.Div("Each organism reads real market structure: order flow, microtrend, spread, volatility, regime, and multi-timeframe alignment.",
                         style={"color": MUTED, "lineHeight": 1.6}),
            ],
            style={"padding": "6px 4px"},
        ),
    ])


def render_scan(hive: HiveInstitutionalV7) -> html.Div:
    rows = []
    for r in hive.scan_results[:20]:
        rows.append(html.Tr([
            html.Td(r["symbol"]), html.Td(r["regime"]), html.Td(r["decision"]), html.Td(f'{r["consensus_score"]:.2f}'),
            html.Td(f'{r["avg_confidence"]:.2f}'), html.Td(fmt_num(r["price"])), html.Td(f'{r["spread_bps"]:.2f}'),
            html.Td(f'{r["rank_score"]:.2f}'), html.Td((r["organisms"][0].reason if r.get("organisms") else "")[:60]),
        ]))
    table = html.Table([
        html.Thead(html.Tr([html.Th(h) for h in ["Symbol", "Regime", "Decision", "Consensus", "Avg Conf", "Price", "Spread bps", "Rank", "Top Reason"]])),
        html.Tbody(rows or [html.Tr(html.Td("No scan results yet", colSpan=9, style={"textAlign": "center", "color": MUTED}))]),
    ], style=TABLE_STYLE)

    fig = go.Figure()
    if hive.scan_results:
        x = [r["symbol"] for r in hive.scan_results[:12]]
        y = [r["consensus_score"] for r in hive.scan_results[:12]]
        fig.add_bar(x=x, y=y, marker_color=[GREEN if v >= hive.learning["conv_threshold"] else CYAN for v in y])
    fig_style(fig, "Consensus Ranking", 340)
    return html.Div([
        base_card("Opportunity Scanner", table, CYAN),
        base_card("Top Consensus Rank", dcc.Graph(figure=fig, config={"displayModeBar": False}), ORANGE),
    ])


def render_hive(hive: HiveInstitutionalV7) -> html.Div:
    latest = hive.consensus_rows[-1] if hive.consensus_rows else None
    consensus_cards = []
    if latest:
        consensus_cards.append(html.Div([
            html.Div(f"{latest['symbol']} — {latest['decision']}", style={"fontWeight": 800, "fontSize": "1.1rem", "color": GOLD}),
            html.Div(f"Conf {latest['avg_confidence']:.2f} | Score {latest['consensus_score']:.2f}", style={"color": MUTED}),
            html.Div(latest["reason"], style={"marginTop": "6px", "color": TXT}),
        ], style={"padding": "10px 0"}))
    rows = []
    if latest:
        for s in latest["organisms"]:
            rows.append(html.Tr([html.Td(s.name), html.Td(s.side), html.Td(f"{s.confidence:.2f}"), html.Td(s.reason[:100])]))
    table = html.Table([
        html.Thead(html.Tr([html.Th(h) for h in ["Organism", "Vote", "Conf", "Reason"]])),
        html.Tbody(rows or [html.Tr(html.Td("No consensus yet", colSpan=4, style={"textAlign": "center", "color": MUTED}))]),
    ], style=TABLE_STYLE)

    return html.Div([
        base_card("Consensus Decision", consensus_cards if consensus_cards else html.Div("Waiting for live scan...", style={"color": MUTED}), GOLD),
        base_card("Hive Vote Breakdown", table, NEON),
        html.Div([
            html.Div(f"Score Threshold: {hive.learning['score_threshold']:.2f}", style={"marginBottom": "4px"}),
            html.Div(f"Conv Threshold: {hive.learning['conv_threshold']:.2f}"),
        ], style={"padding": "4px 6px", "color": TXT}),
    ])


def render_perf(hive: HiveInstitutionalV7) -> html.Div:
    eq = DB.query("SELECT ts, equity_value FROM app_state WHERE key='equity_value'")
    # Use trades-based reconstructed equity curve because app_state stores one row; safe fallback below.
    df_tr = pd.DataFrame(DB.query("SELECT opened_at, closed_at, pnl FROM trades WHERE status='closed' ORDER BY id"), columns=["opened_at", "closed_at", "pnl"])
    trade_count = len(df_tr)
    closed = df_tr[df_tr["pnl"].notna()] if trade_count else pd.DataFrame(columns=df_tr.columns)
    win_rate = float((closed["pnl"] > 0).mean()) if len(closed) else 0.0
    total_pnl = float(closed["pnl"].sum()) if len(closed) else 0.0

    metrics = DB.query("SELECT date, total_pnl, win_rate, avg_trade_duration, best_organism, trade_count, open_count, equity FROM performance_metrics ORDER BY id DESC LIMIT 8")
    perf_table = html.Table([
        html.Thead(html.Tr([html.Th(h) for h in ["Date", "PnL", "WinRate", "Avg Dur (m)", "Best Org", "Trades", "Open", "Equity"]])),
        html.Tbody([
            html.Tr([html.Td(m[0]), html.Td(fmt_money(m[1] or 0)), html.Td(fmt_pct(m[2] or 0)), html.Td(f"{(m[3] or 0):.1f}"), html.Td(m[4]), html.Td(m[5]), html.Td(m[6]), html.Td(fmt_money(m[7] or 0))])
            for m in metrics
        ] or [html.Tr(html.Td("No metrics yet", colSpan=8, style={"textAlign": "center", "color": MUTED}))]),
    ], style=TABLE_STYLE)

    fig = go.Figure()
    equity_rows = DB.query("SELECT opened_at, pnl FROM trades WHERE status='closed' ORDER BY id")
    if equity_rows:
        cum = np.cumsum([float(r[1] or 0) for r in equity_rows]) + hive.initial_capital
        fig.add_scatter(y=cum, mode="lines", line=dict(color=GREEN, width=2), name="Equity")
    else:
        fig.add_scatter(y=[hive.equity()], mode="lines", line=dict(color=CYAN, width=2), name="Equity")
    fig_style(fig, "Equity Curve", 320)

    return html.Div([
        base_card("Performance Summary", html.Div([
            html.Div(f"Trades: {trade_count}"),
            html.Div(f"Win Rate: {fmt_pct(win_rate)}"),
            html.Div(f"Total PnL: {fmt_money(total_pnl)}"),
            html.Div(f"Open Positions: {hive.open_positions_count()}"),
            html.Div(f"Best Organism: {hive.best_organism()}"),
        ], style={"display": "grid", "gridTemplateColumns": "repeat(2, minmax(0, 1fr))", "gap": "8px"}), CYAN),
        base_card("Equity Curve", dcc.Graph(figure=fig, config={"displayModeBar": False}), GREEN),
        base_card("Daily Metrics", perf_table, GOLD),
    ])


def render_control(hive: HiveInstitutionalV7) -> html.Div:
    cfg_pre = html.Pre(json.dumps(CFG, ensure_ascii=False, indent=2), style={"whiteSpace": "pre-wrap", "color": TXT, "background": CARD_SOLID, "padding": "12px", "borderRadius": "12px", "maxHeight": "420px", "overflow": "auto"})
    controls = html.Div([
        html.Button("Start Engine", id="btn-start", n_clicks=0, style=BUTTON_STYLE_GREEN),
        html.Button("Stop Engine", id="btn-stop", n_clicks=0, style=BUTTON_STYLE_RED),
        html.Button("Force Scan Now", id="btn-scan-now", n_clicks=0, style=BUTTON_STYLE_CYAN),
        html.Button("Refresh Config", id="btn-refresh-config", n_clicks=0, style=BUTTON_STYLE_ORANGE),
        html.Div(id="control-message", style={"marginTop": "10px", "color": MUTED}),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap"})
    return html.Div([
        base_card("Runtime Controls", controls, CYAN),
        base_card("Current Config", cfg_pre, GOLD),
    ])


BUTTON_STYLE_GREEN = {"background": "#103d2f", "color": "#e8fff8", "border": "1px solid #24b88d", "padding": "10px 14px", "borderRadius": "10px", "cursor": "pointer"}
BUTTON_STYLE_RED = {"background": "#3a1120", "color": "#ffe6ee", "border": "1px solid #ff5d7a", "padding": "10px 14px", "borderRadius": "10px", "cursor": "pointer"}
BUTTON_STYLE_CYAN = {"background": "#10283a", "color": "#e6f8ff", "border": "1px solid #26d7ff", "padding": "10px 14px", "borderRadius": "10px", "cursor": "pointer"}
BUTTON_STYLE_ORANGE = {"background": "#3a2910", "color": "#fff4e0", "border": "1px solid #ff9f1c", "padding": "10px 14px", "borderRadius": "10px", "cursor": "pointer"}


def tab_renderer(tab: str, hive: HiveInstitutionalV7) -> html.Div:
    if tab == "tab-trades":
        return render_trades(hive)
    if tab == "tab-orgs":
        return render_orgs(hive)
    if tab == "tab-scan":
        return render_scan(hive)
    if tab == "tab-hive":
        return render_hive(hive)
    if tab == "tab-perf":
        return render_perf(hive)
    if tab == "tab-control":
        return render_control(hive)
    return html.Div("Unknown tab")


# =============================================================================
# App creation
# =============================================================================
def create_app(hive: HiveInstitutionalV7) -> dash.Dash:
    ext_stylesheets = []
    if dbc is not None:
        try:
            ext_stylesheets = [getattr(dbc.themes, "CYBORG", None)] if getattr(dbc, "themes", None) else []
            ext_stylesheets = [x for x in ext_stylesheets if x]
        except Exception:
            ext_stylesheets = []
    app = dash.Dash(
        __name__,
        external_stylesheets=ext_stylesheets,
        suppress_callback_exceptions=True,
        title=APP_TITLE,
    )
    app.layout = build_layout(app, hive)

    @app.callback(Output("tab-content", "children"), Input("main-tabs", "value"), Input("tick-main", "n_intervals"))
    def _render_tab(tab_value, n):
        return tab_renderer(tab_value, hive)

    @app.callback(
        Output("control-message", "children"),
        Input("btn-start", "n_clicks"),
        Input("btn-stop", "n_clicks"),
        Input("btn-scan-now", "n_clicks"),
        Input("btn-refresh-config", "n_clicks"),
        prevent_initial_call=True,
    )
    def _control(start_clicks, stop_clicks, scan_clicks, refresh_clicks):
        trig = ctx.triggered_id
        if trig == "btn-start":
            hive.start()
            return rtl_text("Engine started.")
        if trig == "btn-stop":
            hive.stop()
            return rtl_text("Engine stopped.")
        if trig == "btn-scan-now":
            hive.scan_all_symbols()
            return rtl_text(f"Manual scan complete: {len(hive.scan_results)} setups.")
        if trig == "btn-refresh-config":
            global CFG
            CFG = load_or_create_config()
            hive.cfg = CFG
            hive.scan_interval_sec = int(CFG["mode"]["scan_interval_sec"])
            hive.manage_interval_sec = int(CFG["mode"]["manage_interval_sec"])
            hive.dashboard_tick_sec = int(CFG["mode"].get("dashboard_tick_sec", 5))
            hive.symbols = list(CFG["universe"]["symbols"][: int(CFG["universe"]["max_symbols"])])
            return rtl_text("Config reloaded.")
        return no_update

    return app


# =============================================================================
# Main
# =============================================================================
def save_state_on_exit(hive: HiveInstitutionalV7) -> None:
    try:
        DB.set_state("equity_value", hive.equity())
        DB.set_state("peak_equity", hive.peak_equity)
        DB.set_state("consecutive_losses", hive.consecutive_losses)
        DB.set_state("daily_pnl", hive.daily_pnl)
        DB.set_state("generation", hive.generation)
        DB.set_state("learning", hive.learning)
    except Exception:
        pass


def install_signal_handlers(hive: HiveInstitutionalV7) -> None:
    def _handler(signum, frame):
        log.info("Signal %s received, shutting down.", signum)
        hive.stop()
        save_state_on_exit(hive)
        raise SystemExit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except Exception:
            pass


def main() -> None:
    setup_logging()
    log.info("Starting %s", APP_TITLE)
    hive = HiveInstitutionalV7(CFG)
    install_signal_handlers(hive)
    hive.start()  # immediate decision loop in background
    app = create_app(hive)
    host = CFG.get("app", {}).get("host", "0.0.0.0")
    port = int(CFG.get("app", {}).get("port", 8060))
    debug = bool(CFG.get("app", {}).get("debug", False))
    try:
        app.run(host=host, port=port, debug=debug, use_reloader=False)
    finally:
        hive.stop()
        save_state_on_exit(hive)
        log.info("Shutdown complete")


if __name__ == "__main__":
    main()
