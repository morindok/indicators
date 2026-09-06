#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ارگانیسم دیجیتال تریدر — Dash + Bybit v5 (Paper / Live) با REST پایدار."""

from __future__ import annotations

import ast
import hashlib
import hmac
import json
import math
import os
import sqlite3
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from dash import Dash, Input, Output, dash_table, dcc, html
import dash_bootstrap_components as dbc

# ---------------------------------------------------------------------------
# پیکربندی
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "organism_memory.sqlite3"

BYBIT_TESTNET = os.getenv("BYBIT_TESTNET", "0") == "1"
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "").strip()
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "").strip()
BYBIT_LIVE = os.getenv("BYBIT_LIVE", "0") == "1"

if BYBIT_TESTNET:
    REST_CANDIDATES = [
        os.getenv("BYBIT_BASE", "https://api-testnet.bybit.com").rstrip("/")
    ]
else:
    _defaults = [
        "https://api.bybit.com",
        "https://api.bytick.com",
        "https://api.bybit.kz",
    ]
    _env_base = (os.getenv("BYBIT_BASE") or "").strip().rstrip("/")
    REST_CANDIDATES = (
        ([_env_base] + [b for b in _defaults if b != _env_base])
        if _env_base
        else list(_defaults)
    )

MAX_SCAN = 100
MAX_OPEN_POSITIONS = 5
STARTING_EQUITY = 500.0
LEVERAGE = 20
QUALITY_FLOOR = 0.56
TAKER_FEE = 0.00055
SESSION_SLEEP = 1.2
KLINE_INTERVAL = "5"
KLINE_LIMIT = 80
KLINE_WORKERS = 12
PRIORITY_KLINES = 25
SCALP_TIME_STOP_SEC = 12 * 60
RECV_WINDOW = "5000"
MIN_SL_PCT = 0.0018
MAX_SL_PCT = 0.0035
HTTP_TIMEOUT = 12

FIB_BIN = [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377]

# ---------------------------------------------------------------------------
# وضعیت مشترک (thread-safe)
# ---------------------------------------------------------------------------
LOCK = threading.RLock()
STATE: dict[str, Any] = {
    "alive": True,
    "started_at": time.time(),
    "heartbeat": 0,
    "genome": "",
    "focused": "",
    "scan_n": 0,
    "universe_n": 0,
    "candidates_n": 0,
    "opened_cycle": 0,
    "connection": "قطع",
    "rest_base": "",
    "last_error": "",
    "ideas": [],
    "organs": {},
    "hormones": {},
    "awareness": 0.0,
    "sixth": 0.0,
    "number_sense": 0.0,
    "neurons": max(128, (os.cpu_count() or 1) * 128),
    "lessons": [],
    "market": {},
    "cycle": 0,
    "last_open_print": "",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def clamp(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def round_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    precision = max(0, int(round(-math.log10(step)))) if step < 1 else 0
    snapped = math.floor(value / step + 1e-12) * step
    return float(f"{snapped:.{precision}f}")


# ---------------------------------------------------------------------------
# ژنوم / کرونوکلاک
# ---------------------------------------------------------------------------
def fib_binary_stream(n: int, width: int = 96) -> str:
    seq = []
    a, b = 0, 1
    while len(seq) < n + 24:
        seq.append(a)
        a, b = b, a + b
    bits = "".join(f"{x:b}" for x in seq[2:])
    start = n % max(1, len(bits) - width)
    stream = bits[start : start + width]
    return stream.ljust(width, "0")


def heart_period(beat: int) -> float:
    return 0.35 + (FIB_BIN[beat % len(FIB_BIN)] % 8) * 0.04


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------
def db_connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    con = db_connect()
    try:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                entry REAL NOT NULL,
                sl REAL NOT NULL,
                tp REAL NOT NULL,
                qty REAL NOT NULL,
                margin REAL NOT NULL,
                leverage INTEGER NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                exit_price REAL,
                pnl REAL,
                status TEXT NOT NULL,
                route TEXT NOT NULL,
                reason TEXT,
                score REAL,
                fee REAL
            );
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT,
                text TEXT NOT NULL
            );
            """
        )
        con.commit()
    finally:
        con.close()


def add_lesson(symbol: str, text: str) -> None:
    con = db_connect()
    try:
        con.execute(
            "INSERT INTO lessons(created_at, symbol, text) VALUES (?, ?, ?)",
            (utc_now(), symbol, text),
        )
        con.commit()
    finally:
        con.close()
    with LOCK:
        STATE["lessons"] = load_lessons(8)


def load_lessons(limit: int = 8) -> list[dict[str, Any]]:
    con = db_connect()
    try:
        rows = con.execute(
            "SELECT created_at, symbol, text FROM lessons ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def load_trades(status: str | None = None) -> list[dict[str, Any]]:
    con = db_connect()
    try:
        if status:
            rows = con.execute(
                "SELECT * FROM trades WHERE status = ? ORDER BY id DESC", (status,)
            ).fetchall()
        else:
            rows = con.execute("SELECT * FROM trades ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def insert_trade(row: dict[str, Any]) -> int:
    con = db_connect()
    try:
        cur = con.execute(
            """
            INSERT INTO trades(
                symbol, side, entry, sl, tp, qty, margin, leverage,
                opened_at, closed_at, exit_price, pnl, status, route, reason, score, fee
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["symbol"],
                row["side"],
                row["entry"],
                row["sl"],
                row["tp"],
                row["qty"],
                row["margin"],
                row["leverage"],
                row["opened_at"],
                row.get("closed_at"),
                row.get("exit_price"),
                row.get("pnl"),
                row["status"],
                row["route"],
                row.get("reason"),
                row.get("score"),
                row.get("fee", 0.0),
            ),
        )
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()


def close_trade_row(trade_id: int, exit_price: float, pnl: float, reason: str) -> None:
    con = db_connect()
    try:
        con.execute(
            """
            UPDATE trades
            SET status='closed', closed_at=?, exit_price=?, pnl=?, reason=?
            WHERE id=?
            """,
            (utc_now(), exit_price, pnl, reason, trade_id),
        )
        con.commit()
    finally:
        con.close()


# ---------------------------------------------------------------------------
# HTTP / Bybit — اتصال پایدار: چند دامنه + کش دامنه فعال + هدر مرورگر
# ---------------------------------------------------------------------------
SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.bybit.com/",
    }
)
_ACTIVE_REST_BASE: dict[str, str | None] = {"url": None}


def _rest_candidates() -> list[str]:
    active = _ACTIVE_REST_BASE.get("url")
    ordered = ([active] if active else []) + [b for b in REST_CANDIDATES if b != active]
    return [b for b in ordered if b]


def _mark_rest(base: str) -> None:
    _ACTIVE_REST_BASE["url"] = base
    with LOCK:
        STATE["rest_base"] = base
        STATE["connection"] = f"متصل · {base}"
        STATE["last_error"] = ""


def bybit_get(path: str, params: dict[str, Any] | None = None, timeout: int = HTTP_TIMEOUT) -> dict[str, Any] | None:
    """GET عمومی با failover بین دامنه‌ها؛ 403/451 را رد می‌کند."""
    params = params or {}
    for base in _rest_candidates():
        try:
            r = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code in (403, 451):
                continue
            r.raise_for_status()
            data = r.json()
            if data.get("retCode") == 0:
                _mark_rest(base)
                return data
        except Exception:
            continue
    return None


def sign_headers(payload: str) -> dict[str, str]:
    ts = str(int(time.time() * 1000))
    raw = f"{ts}{BYBIT_API_KEY}{RECV_WINDOW}{payload}"
    sig = hmac.new(BYBIT_API_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return {
        "X-BAPI-API-KEY": BYBIT_API_KEY,
        "X-BAPI-TIMESTAMP": ts,
        "X-BAPI-RECV-WINDOW": RECV_WINDOW,
        "X-BAPI-SIGN": sig,
        "Content-Type": "application/json",
    }


def bybit_signed(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """REST امضاشده با همان failover دامنه؛ خطای منطقی API دامنه را عوض نمی‌کند."""
    body = body or {}
    last_err: Exception | None = None
    for base in _rest_candidates():
        try:
            url = f"{base}{path}"
            if method == "GET":
                qs = "&".join(f"{k}={body[k]}" for k in sorted(body))
                headers = sign_headers(qs)
                r = SESSION.get(url, params=body, headers=headers, timeout=HTTP_TIMEOUT)
            else:
                payload = json.dumps(body, separators=(",", ":"))
                headers = sign_headers(payload)
                r = SESSION.post(url, data=payload, headers=headers, timeout=HTTP_TIMEOUT)
            if r.status_code in (403, 451):
                continue
            r.raise_for_status()
            data = r.json()
            if str(data.get("retCode")) == "0":
                _mark_rest(base)
                return data
            raise RuntimeError(f"Bybit {method} {path}: {data.get('retMsg')}")
        except RuntimeError:
            raise
        except Exception as exc:
            last_err = exc
            continue
    raise RuntimeError(f"REST امضاشده ناموفق روی همه دامنه‌ها: {last_err}")


# ---------------------------------------------------------------------------
# بازار
# ---------------------------------------------------------------------------
INSTRUMENTS: dict[str, dict[str, Any]] = {}
KLINES: dict[str, pd.DataFrame] = {}
TICKERS: dict[str, dict[str, Any]] = {}
UNIVERSE: list[str] = []
KLINE_CURSOR = 0


def fetch_tickers_universe() -> list[str]:
    data = bybit_get("/v5/market/tickers", {"category": "linear"})
    if not data:
        with LOCK:
            STATE["connection"] = "قطع / تلاش دامنه‌های جایگزین"
            STATE["last_error"] = "هیچ دامنهٔ REST بایبیت پاسخ نداد"
        return list(UNIVERSE)

    rows = data.get("result", {}).get("list", []) or []
    parsed = []
    for row in rows:
        sym = str(row.get("symbol") or "")
        if not sym.endswith("USDT"):
            continue
        if not all(ch.isalnum() for ch in sym):
            continue
        last = safe_float(row.get("lastPrice"))
        bid = safe_float(row.get("bid1Price"))
        ask = safe_float(row.get("ask1Price"))
        turn = safe_float(row.get("turnover24h"))
        vol = safe_float(row.get("volume24h"))
        if last <= 0 or bid <= 0 or ask <= 0 or ask < bid or turn <= 0:
            continue
        item = {
            "symbol": sym,
            "last": last,
            "bid": bid,
            "ask": ask,
            "spread": (ask - bid) / last,
            "change24": safe_float(row.get("price24hPcnt")),
            "turnover24h": turn,
            "volume24h": vol,
            "bid_size": safe_float(row.get("bid1Size")),
            "ask_size": safe_float(row.get("ask1Size")),
            "high24": safe_float(row.get("highPrice24h")),
            "low24": safe_float(row.get("lowPrice24h")),
        }
        parsed.append(item)
    parsed.sort(key=lambda x: x["turnover24h"], reverse=True)
    top = parsed[:MAX_SCAN]
    with LOCK:
        TICKERS.clear()
        TICKERS.update({x["symbol"]: x for x in top})
        UNIVERSE[:] = [x["symbol"] for x in top]
        STATE["universe_n"] = len(UNIVERSE)
        STATE["market"] = {
            "n": len(top),
            "median_spread": float(np.median([x["spread"] for x in top])) if top else 0.0,
            "median_chg": float(np.median([abs(x["change24"]) for x in top])) if top else 0.0,
            "top_turn": top[0]["turnover24h"] if top else 0.0,
        }
    return [x["symbol"] for x in top]


def cache_instruments() -> None:
    if INSTRUMENTS:
        return
    cursor = ""
    collected: dict[str, dict[str, Any]] = {}
    for _ in range(8):
        params: dict[str, Any] = {"category": "linear", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        data = bybit_get("/v5/market/instruments-info", params)
        if not data:
            break
        result = data.get("result", {}) or {}
        for row in result.get("list", []) or []:
            if row.get("status") != "Trading":
                continue
            sym = row.get("symbol") or ""
            lot = row.get("lotSizeFilter") or {}
            price = row.get("priceFilter") or {}
            lev = row.get("leverageFilter") or {}
            collected[sym] = {
                "qtyStep": safe_float(lot.get("qtyStep"), 0.001),
                "minOrderQty": safe_float(lot.get("minOrderQty"), 0.001),
                "tickSize": safe_float(price.get("tickSize"), 0.01),
                "maxLeverage": safe_float(lev.get("maxLeverage"), LEVERAGE),
            }
        cursor = result.get("nextPageCursor") or ""
        if not cursor:
            break
    if collected:
        INSTRUMENTS.update(collected)


def fetch_klines(symbol: str) -> pd.DataFrame:
    data = bybit_get(
        "/v5/market/kline",
        {
            "category": "linear",
            "symbol": symbol,
            "interval": KLINE_INTERVAL,
            "limit": KLINE_LIMIT,
        },
    )
    if not data:
        return pd.DataFrame()
    rows = data.get("result", {}).get("list", []) or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(
        rows,
        columns=["ts", "open", "high", "low", "close", "volume", "turnover"],
    )
    for c in ("open", "high", "low", "close", "volume", "turnover"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["ts"] = pd.to_numeric(df["ts"], errors="coerce")
    df = df.dropna().sort_values("ts").reset_index(drop=True)
    return df


def refresh_klines_round_robin(symbols: list[str]) -> None:
    global KLINE_CURSOR
    if not symbols:
        return
    priority = symbols[:PRIORITY_KLINES]
    rest = symbols[PRIORITY_KLINES:]
    batch_n = 8
    start = KLINE_CURSOR % max(1, len(rest) or 1)
    batch = priority + rest[start : start + batch_n]
    if rest:
        KLINE_CURSOR = (start + batch_n) % len(rest)
    with ThreadPoolExecutor(max_workers=KLINE_WORKERS) as pool:
        futs = {pool.submit(fetch_klines, s): s for s in batch}
        for fut in as_completed(futs):
            sym = futs[fut]
            try:
                df = fut.result()
                if df is not None and not df.empty:
                    KLINES[sym] = df
            except Exception:
                continue


# ---------------------------------------------------------------------------
# تحلیل غیرتصادفی
# ---------------------------------------------------------------------------
def rsi(series: pd.Series, period: int = 14) -> float:
    if series is None or len(series) < period + 2:
        return 50.0
    delta = series.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    val = 100 - (100 / (1 + rs))
    out = float(val.iloc[-1])
    return 50.0 if math.isnan(out) else out


def atr_pct(df: pd.DataFrame, period: int = 14) -> float:
    if df is None or df.empty or len(df) < period + 1:
        return 0.0024
    high, low, close = df["high"], df["low"], df["close"]
    prev = close.shift(1)
    tr = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(period).mean().iloc[-1])
    last = float(close.iloc[-1])
    if last <= 0 or math.isnan(atr):
        return 0.0024
    return clamp(atr / last, 0.0008, 0.02)


def analyze_symbol(sym: str, ticker: dict[str, Any], kdf: pd.DataFrame | None) -> dict[str, Any]:
    last = ticker["last"]
    spread = ticker["spread"]
    chg = ticker["change24"]
    bid_s = ticker["bid_size"]
    ask_s = ticker["ask_size"]
    depth = bid_s + ask_s
    imbalance = ((bid_s - ask_s) / depth) if depth > 0 else 0.0
    rng = ticker["high24"] - ticker["low24"]
    loc = 0.5 if rng <= 0 else clamp((last - ticker["low24"]) / rng, 0.0, 1.0)

    have_kl = kdf is not None and not kdf.empty
    rsi_v = rsi(kdf["close"]) if have_kl else 50.0 + 80.0 * chg
    atrp = atr_pct(kdf) if have_kl else clamp(abs(chg) * 0.35 + spread * 4.0, 0.0015, 0.01)
    mom = 0.0
    if have_kl and len(kdf) >= 8:
        c = kdf["close"]
        mom = float((c.iloc[-1] - c.iloc[-8]) / c.iloc[-8])

    spread_score = clamp(1.0 - spread / 0.0012, 0.0, 1.0)
    liq_score = clamp(math.log10(max(ticker["turnover24h"], 1.0)) / 9.5, 0.0, 1.0)
    mom_score = clamp(0.5 + 8.0 * (mom if have_kl else chg), 0.0, 1.0)
    imb_score = clamp(0.5 + imbalance, 0.0, 1.0)
    rsi_edge = abs(rsi_v - 50.0) / 50.0
    ext_score = clamp(rsi_edge * 1.15, 0.0, 1.0)
    atr_score = clamp(1.0 - abs(atrp - 0.0026) / 0.004, 0.0, 1.0)

    raw = (
        0.22 * spread_score
        + 0.18 * liq_score
        + 0.22 * mom_score
        + 0.16 * imb_score
        + 0.14 * ext_score
        + 0.08 * atr_score
    )
    score = QUALITY_FLOOR + (0.95 - QUALITY_FLOOR) * clamp(raw, 0.0, 1.0)

    long_bias = imbalance + (0.0 if have_kl else chg) * 6.0 + (50.0 - rsi_v) / 80.0 + mom * 4.0
    side = "Buy" if long_bias >= 0 else "Sell"

    sl_pct = clamp(atrp * 0.85, MIN_SL_PCT, MAX_SL_PCT)
    tp_pct = clamp(sl_pct * 1.55, sl_pct * 1.2, 0.006)

    if side == "Buy":
        entry = ticker["ask"]
        sl = entry * (1.0 - sl_pct)
        tp = entry * (1.0 + tp_pct)
    else:
        entry = ticker["bid"]
        sl = entry * (1.0 + sl_pct)
        tp = entry * (1.0 - tp_pct)

    reason = (
        f"spread={spread:.5f} imb={imbalance:.2f} rsi={rsi_v:.1f} "
        f"mom={mom:.4f} atr={atrp:.4f} loc={loc:.2f}"
    )
    return {
        "symbol": sym,
        "score": float(score),
        "side": side,
        "entry": float(entry),
        "sl": float(sl),
        "tp": float(tp),
        "sl_pct": float(sl_pct),
        "tp_pct": float(tp_pct),
        "rsi": float(rsi_v),
        "atr": float(atrp),
        "spread": float(spread),
        "imbalance": float(imbalance),
        "reason": reason,
        "last": float(last),
        "bid": float(ticker["bid"]),
        "ask": float(ticker["ask"]),
        "change24": float(chg),
        "turnover": float(ticker["turnover24h"]),
    }


def hormone_state(focus: dict[str, Any] | None, market: dict[str, Any]) -> dict[str, float]:
    vol = float(market.get("median_chg") or 0.0)
    spr = float(market.get("median_spread") or 0.0)
    sc = float((focus or {}).get("score") or 0.5)
    cortisol = clamp(0.25 + vol * 8.0 + spr * 80.0, 0.05, 0.95)
    dopamine = clamp(0.20 + (sc - QUALITY_FLOOR) * 1.6, 0.05, 0.95)
    adrenaline = clamp(0.15 + abs(float((focus or {}).get("change24") or 0)) * 10.0, 0.05, 0.95)
    serotonin = clamp(1.0 - cortisol * 0.55 + dopamine * 0.25, 0.05, 0.95)
    return {
        "کورتیزول": cortisol,
        "دوپامین": dopamine,
        "آدرنالین": adrenaline,
        "سروتونین": serotonin,
    }


def organ_state(focus: dict[str, Any] | None, hormones: dict[str, float]) -> dict[str, float]:
    sc = float((focus or {}).get("score") or 0.5)
    return {
        "قلب": clamp(0.4 + sc * 0.5, 0.1, 1.0),
        "مغز": clamp(0.45 + hormones["دوپامین"] * 0.4, 0.1, 1.0),
        "چشم": clamp(0.35 + (1.0 - float((focus or {}).get("spread") or 0.001) * 200) * 0.4, 0.1, 1.0),
        "پوست": clamp(0.5 - hormones["کورتیزول"] * 0.25, 0.1, 1.0),
        "ریه": clamp(0.55 - hormones["آدرنالین"] * 0.2, 0.1, 1.0),
        "کبد": clamp(0.4 + hormones["سروتونین"] * 0.45, 0.1, 1.0),
    }


def night_size_factor() -> float:
    hour = datetime.now(timezone.utc).hour
    return 0.72 if hour < 6 or hour >= 22 else 1.0


def candidate_allocation(hormones: dict[str, float], n_open: int) -> float:
    slots = max(1, MAX_OPEN_POSITIONS - n_open)
    base = STARTING_EQUITY / MAX_OPEN_POSITIONS
    fear = clamp(1.0 - hormones["کورتیزول"] * 0.45, 0.35, 1.0)
    drive = clamp(0.65 + hormones["دوپامین"] * 0.4, 0.5, 1.15)
    size = base * fear * drive * night_size_factor()
    return max(12.0, min(size, STARTING_EQUITY / slots))


# ---------------------------------------------------------------------------
# سفارش / مدیریت پوزیشن
# ---------------------------------------------------------------------------
def live_enabled() -> bool:
    return BYBIT_LIVE and bool(BYBIT_API_KEY) and bool(BYBIT_API_SECRET)


def set_leverage(symbol: str) -> None:
    try:
        bybit_signed(
            "POST",
            "/v5/position/set-leverage",
            {
                "category": "linear",
                "symbol": symbol,
                "buyLeverage": str(LEVERAGE),
                "sellLeverage": str(LEVERAGE),
            },
        )
    except Exception:
        pass


def place_live_order(idea: dict[str, Any], qty: float) -> dict[str, Any]:
    set_leverage(idea["symbol"])
    spec = INSTRUMENTS.get(idea["symbol"], {})
    tick = spec.get("tickSize") or 0.01
    sl = round_step(idea["sl"], tick)
    tp = round_step(idea["tp"], tick)
    body = {
        "category": "linear",
        "symbol": idea["symbol"],
        "side": idea["side"],
        "orderType": "Market",
        "qty": str(qty),
        "timeInForce": "IOC",
        "takeProfit": str(tp),
        "stopLoss": str(sl),
        "tpTriggerBy": "LastPrice",
        "slTriggerBy": "LastPrice",
        "positionIdx": 0,
    }
    return bybit_signed("POST", "/v5/order/create", body)


def realized_pnl(side: str, entry: float, exit_price: float, qty: float) -> float:
    if side == "Buy":
        raw = (exit_price - entry) * qty
    else:
        raw = (entry - exit_price) * qty
    fee = (entry + exit_price) * qty * TAKER_FEE
    return raw - fee


def open_trade(idea: dict[str, Any], margin: float) -> dict[str, Any] | None:
    spec = INSTRUMENTS.get(
        idea["symbol"],
        {"qtyStep": 0.001, "minOrderQty": 0.001, "tickSize": 0.01},
    )
    entry = idea["entry"]
    if entry <= 0 or margin <= 0:
        return None
    notional = margin * LEVERAGE
    qty = round_step(notional / entry, spec.get("qtyStep") or 0.001)
    if qty < (spec.get("minOrderQty") or 0):
        return None
    route = "live" if live_enabled() else "paper"
    if route == "live":
        try:
            place_live_order(idea, qty)
        except Exception as exc:
            with LOCK:
                STATE["last_error"] = f"لایو رد شد، Paper: {exc}"
            route = "paper"
            add_lesson(idea["symbol"], f"سفارش لایو شکست؛ Paper باز شد: {exc}")

    fee = entry * qty * TAKER_FEE
    row = {
        "symbol": idea["symbol"],
        "side": idea["side"],
        "entry": entry,
        "sl": idea["sl"],
        "tp": idea["tp"],
        "qty": qty,
        "margin": margin,
        "leverage": LEVERAGE,
        "opened_at": utc_now(),
        "status": "open",
        "route": route,
        "reason": idea["reason"],
        "score": idea["score"],
        "fee": fee,
    }
    row["id"] = insert_trade(row)
    msg = (
        f"[OPEN] {row['id']} {route} {row['side']} {row['symbol']} "
        f"qty={qty} entry={entry} sl={row['sl']} tp={row['tp']} score={idea['score']:.3f}"
    )
    print(msg, flush=True)
    with LOCK:
        STATE["last_open_print"] = msg
        STATE["opened_cycle"] += 1
    add_lesson(row["symbol"], f"ورود {row['side']} امتیاز {idea['score']:.3f} مسیر {route}")
    return row


def mark_price(sym: str, side: str) -> float | None:
    t = TICKERS.get(sym)
    if not t:
        return None
    return t["bid"] if side == "Buy" else t["ask"]


def manage_open_trades() -> None:
    opens = load_trades("open")
    now = time.time()
    for tr in opens:
        px = mark_price(tr["symbol"], tr["side"])
        if px is None:
            continue
        hit = None
        if tr["side"] == "Buy":
            if px <= tr["sl"]:
                hit = ("sl", tr["sl"])
            elif px >= tr["tp"]:
                hit = ("tp", tr["tp"])
        else:
            if px >= tr["sl"]:
                hit = ("sl", tr["sl"])
            elif px <= tr["tp"]:
                hit = ("tp", tr["tp"])
        opened_ts = datetime.strptime(tr["opened_at"].replace(" UTC", ""), "%Y-%m-%d %H:%M:%S")
        opened_ts = opened_ts.replace(tzinfo=timezone.utc).timestamp()
        if hit is None and now - opened_ts >= SCALP_TIME_STOP_SEC:
            hit = ("time", px)
        if not hit:
            continue
        why, exit_px = hit
        pnl = realized_pnl(tr["side"], tr["entry"], exit_px, tr["qty"])
        close_trade_row(tr["id"], exit_px, pnl, why)
        add_lesson(tr["symbol"], f"خروج {why} pnl={pnl:.4f}")
        print(f"[CLOSE] {tr['id']} {tr['symbol']} {why} px={exit_px} pnl={pnl:.4f}", flush=True)


def recover_open_on_start() -> None:
    opens = load_trades("open")
    if opens:
        add_lesson("-", f"بازیابی {len(opens)} معامله باز بعد از ری‌استارت")
        manage_open_trades()


# ---------------------------------------------------------------------------
# حلقه مغز
# ---------------------------------------------------------------------------
def sync_organism(focus: dict[str, Any] | None, ideas: list[dict[str, Any]]) -> None:
    market = STATE.get("market") or {}
    hormones = hormone_state(focus, market)
    organs = organ_state(focus, hormones)
    awareness = clamp(
        0.35
        + 0.25 * (STATE.get("universe_n", 0) / MAX_SCAN)
        + 0.25 * float((focus or {}).get("score") or 0)
        + 0.15 * (1.0 if KLINES else 0.4),
        0.0,
        1.0,
    )
    sixth = clamp(
        0.2
        + abs(float((focus or {}).get("imbalance") or 0)) * 0.7
        + float(hormones["دوپامین"]) * 0.25,
        0.0,
        1.0,
    )
    number_sense = clamp(
        0.3 + (float((focus or {}).get("rsi") or 50) / 100.0) * 0.4 + awareness * 0.3,
        0.0,
        1.0,
    )
    with LOCK:
        STATE["hormones"] = hormones
        STATE["organs"] = organs
        STATE["awareness"] = awareness
        STATE["sixth"] = sixth
        STATE["number_sense"] = number_sense
        STATE["ideas"] = ideas[:20]
        STATE["focused"] = (focus or {}).get("symbol") or STATE.get("focused") or ""


def scan_and_trade_loop() -> None:
    beat = 0
    recover_open_on_start()
    while STATE["alive"]:
        t0 = time.time()
        try:
            beat += 1
            genome = fib_binary_stream(beat)
            with LOCK:
                STATE["heartbeat"] = beat
                STATE["genome"] = genome
                STATE["cycle"] += 1
                STATE["opened_cycle"] = 0

            symbols = fetch_tickers_universe()
            cache_instruments()
            refresh_klines_round_robin(symbols)

            ideas: list[dict[str, Any]] = []
            for i, sym in enumerate(symbols):
                ticker = TICKERS.get(sym)
                if not ticker:
                    continue
                idea = analyze_symbol(sym, ticker, KLINES.get(sym))
                ideas.append(idea)
                if i == beat % max(1, len(symbols)):
                    sync_organism(idea, ideas)

            ideas.sort(key=lambda x: x["score"], reverse=True)
            candidates = [x for x in ideas if x["score"] >= QUALITY_FLOOR]
            with LOCK:
                STATE["scan_n"] = len(ideas)
                STATE["candidates_n"] = len(candidates)
            if ideas:
                sync_organism(ideas[0], ideas)

            manage_open_trades()
            opens = load_trades("open")
            open_syms = {t["symbol"] for t in opens}
            hormones = STATE.get("hormones") or hormone_state(
                ideas[0] if ideas else None, STATE.get("market") or {}
            )
            for idea in candidates:
                if len(load_trades("open")) >= MAX_OPEN_POSITIONS:
                    break
                if idea["symbol"] in open_syms:
                    continue
                margin = candidate_allocation(hormones, len(open_syms))
                row = open_trade(idea, margin)
                if row:
                    open_syms.add(row["symbol"])
        except Exception as exc:
            with LOCK:
                STATE["connection"] = "خطا / تلاش مجدد"
                STATE["last_error"] = f"{exc}"
            traceback.print_exc()
            add_lesson("-", f"وقفه شبکه یا هسته: {exc}")

        elapsed = time.time() - t0
        time.sleep(max(0.25, SESSION_SLEEP - elapsed) + heart_period(beat) * 0.15)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def empty_bar(title: str, names: list[str], values: list[float]) -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=values,
            y=names,
            orientation="h",
            marker=dict(color=values, colorscale="Tealgrn", cmin=0, cmax=1),
        )
    )
    fig.update_layout(
        title=title,
        template="plotly_dark",
        height=260,
        margin=dict(l=80, r=20, t=40, b=30),
        xaxis=dict(range=[0, 1]),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def equity_figure(trades: list[dict[str, Any]]) -> go.Figure:
    eq = STARTING_EQUITY
    xs = [0]
    ys = [eq]
    closed = [t for t in trades if t["status"] == "closed" and t.get("pnl") is not None]
    closed.sort(key=lambda t: t.get("closed_at") or "")
    for i, t in enumerate(closed, start=1):
        eq += float(t["pnl"])
        xs.append(i)
        ys.append(eq)
    fig = go.Figure(go.Scatter(x=xs, y=ys, mode="lines+markers", line=dict(color="#2dd4bf", width=2)))
    fig.update_layout(
        title="رشد سرمایه از ۵۰۰ دلار",
        template="plotly_dark",
        height=280,
        margin=dict(l=40, r=20, t=40, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def kpi_card(title: str, value: Any, sub: str = "") -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(title, className="text-muted", style={"fontSize": "12px"}),
                html.H4(str(value), className="mb-0"),
                html.Small(sub, className="text-info"),
            ]
        ),
        className="mb-2",
    )


app = Dash(__name__, external_stylesheets=[dbc.themes.CYBORG], title="ارگانیسم زنده")
app.layout = dbc.Container(
    [
        html.H3("ارگانیسم دیجیتال تریدر · بایبیت", className="mt-3 mb-1"),
        html.Div(id="hdr", className="text-muted mb-3"),
        dcc.Interval(id="tick", interval=1000, n_intervals=0),
        dbc.Tabs(
            [
                dbc.Tab(
                    label="آمار",
                    children=[
                        dbc.Row(
                            [
                                dbc.Col(html.Div(id="stat-kpis"), md=4),
                                dbc.Col(dcc.Graph(id="organs-fig"), md=4),
                                dbc.Col(dcc.Graph(id="hormones-fig"), md=4),
                            ],
                            className="mt-3",
                        ),
                        dbc.Row(
                            [
                                dbc.Col(html.Div(id="dna-box"), md=6),
                                dbc.Col(html.Div(id="brain-box"), md=6),
                            ]
                        ),
                    ],
                ),
                dbc.Tab(
                    label="ترید",
                    children=[
                        dbc.Row(html.Div(id="trade-kpis"), className="mt-3"),
                        dcc.Graph(id="eq-fig"),
                        html.H5("معاملات باز"),
                        html.Div(id="open-table"),
                        html.H5("ایده‌های لحظه‌ای (۲۰ امتیاز برتر)"),
                        html.Div(id="idea-table"),
                    ],
                ),
            ]
        ),
    ],
    fluid=True,
)


@app.callback(
    Output("hdr", "children"),
    Output("stat-kpis", "children"),
    Output("organs-fig", "figure"),
    Output("hormones-fig", "figure"),
    Output("dna-box", "children"),
    Output("brain-box", "children"),
    Output("trade-kpis", "children"),
    Output("eq-fig", "figure"),
    Output("open-table", "children"),
    Output("idea-table", "children"),
    Input("tick", "n_intervals"),
)
def refresh(_n: int):
    with LOCK:
        st = dict(STATE)
        ideas = list(STATE.get("ideas") or [])
        organs = dict(STATE.get("organs") or {})
        hormones = dict(STATE.get("hormones") or {})
    trades = load_trades()
    opens = [t for t in trades if t["status"] == "open"]
    closed = [t for t in trades if t["status"] == "closed"]
    wins = [t for t in closed if (t.get("pnl") or 0) > 0]
    wr = (100.0 * len(wins) / len(closed)) if closed else 0.0
    eq = STARTING_EQUITY + sum(float(t.get("pnl") or 0) for t in closed)
    route = "LIVE" if live_enabled() else "PAPER"

    hdr = (
        f"{st.get('connection')} · مسیر {route} · ضربان {st.get('heartbeat')} · "
        f"تمرکز {st.get('focused') or '—'} · {utc_now()}"
    )
    if st.get("last_error"):
        hdr += f" · خطا: {st['last_error']}"

    stat = [
        kpi_card("آگاهی به مارکت", f"{st.get('awareness', 0):.2f}", "همگام با نماد تمرکز"),
        kpi_card("حس ششم", f"{st.get('sixth', 0):.2f}", "عدم‌تعادل دفتر سفارش"),
        kpi_card("حس عدد", f"{st.get('number_sense', 0):.2f}", f"نورون {st.get('neurons')}"),
        kpi_card("اسکن", f"{st.get('scan_n', 0)}/{MAX_SCAN}", f"کاندید {st.get('candidates_n', 0)}"),
    ]
    o_names, o_vals = (list(organs.keys()), list(organs.values())) if organs else (["—"], [0])
    h_names, h_vals = (list(hormones.keys()), list(hormones.values())) if hormones else (["—"], [0])

    genes = " ".join((st.get("genome") or "").join(" ").split())
    dna = dbc.Card(
        dbc.CardBody(
            [
                html.H5("نردبان DNA / ژنوم جاری"),
                html.Code(st.get("genome") or "—", style={"wordBreak": "break-all"}),
                html.Hr(),
                html.Div("درس‌های حافظه:"),
                html.Ul(
                    [
                        html.Li(f"{x['created_at']} [{x.get('symbol')}] {x['text']}")
                        for x in load_lessons(6)
                    ]
                ),
            ]
        )
    )
    brain = dbc.Card(
        dbc.CardBody(
            [
                html.H5("گزارش لحظه‌ای مغز"),
                html.P(f"چرخه {st.get('cycle')} · بازشده در چرخه {st.get('opened_cycle')}"),
                html.P(f"نماد تمرکز: {st.get('focused') or '—'}"),
                html.P(f"دامنه فعال: {st.get('rest_base') or 'هنوز انتخاب نشده'}"),
                html.P(st.get("last_open_print") or "هنوز پوزیشنی باز نشده."),
                html.P("گیت احساسی فقط سایز را کم می‌کند؛ ورود را قفل نمی‌کند."),
                html.Small(genes[:80]),
            ]
        )
    )
    tk = dbc.Row(
        [
            dbc.Col(kpi_card("وین‌ریت", f"{wr:.1f}%", f"{len(wins)}/{len(closed)}"), md=3),
            dbc.Col(kpi_card("اکوئیتی", f"{eq:.2f}$", f"شروع {STARTING_EQUITY}"), md=3),
            dbc.Col(kpi_card("باز", f"{len(opens)}/{MAX_OPEN_POSITIONS}", f"اهرم {LEVERAGE}"), md=3),
            dbc.Col(kpi_card("کف کیفیت", QUALITY_FLOOR, f"اسکن {st.get('scan_n', 0)}"), md=3),
        ]
    )

    def table(rows: list[dict[str, Any]], cols: list[str]):
        if not rows:
            return html.Div("خالی", className="text-muted mb-3")
        return dash_table.DataTable(
            data=[{k: r.get(k) for k in cols} for r in rows],
            columns=[{"name": c, "id": c} for c in cols],
            style_table={"overflowX": "auto"},
            style_cell={"backgroundColor": "#111", "color": "#eee", "fontSize": 12, "padding": "6px"},
            style_header={"backgroundColor": "#222", "fontWeight": "bold"},
            page_size=10,
        )

    open_cols = ["id", "symbol", "side", "entry", "sl", "tp", "qty", "margin", "score", "route", "opened_at"]
    idea_cols = ["symbol", "side", "score", "entry", "sl", "tp", "rsi", "spread", "change24"]
    return (
        hdr,
        stat,
        empty_bar("آتش ارگان‌ها", o_names, o_vals),
        empty_bar("هورمون‌ها", h_names, h_vals),
        dna,
        brain,
        tk,
        equity_figure(trades),
        table(opens, open_cols),
        table(ideas, idea_cols),
    )


def main() -> None:
    init_db()
    t = threading.Thread(target=scan_and_trade_loop, name="organism-brain", daemon=True)
    t.start()
    print("organism_live listening on http://127.0.0.1:8050", flush=True)
    print(
        f"route={'LIVE' if live_enabled() else 'PAPER'} "
        f"candidates={REST_CANDIDATES}",
        flush=True,
    )
    app.run(host="127.0.0.1", port=8050, debug=False)


if __name__ == "__main__":
    ast.parse(Path(__file__).read_text(encoding="utf-8"))
    main()
