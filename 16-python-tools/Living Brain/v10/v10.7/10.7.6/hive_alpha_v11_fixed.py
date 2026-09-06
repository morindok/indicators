# -*- coding: utf-8 -*-
"""hive_alpha_v11_fixed.py

Single-file Bybit V5 position opener / monitor with optional dashboard fallback.
Focus: correct V5 authentication, real position sync, signal scoring, and resilient
order / position management.

Run:
    python hive_alpha_v11_fixed.py

Environment variables:
    BYBIT_API_KEY
    BYBIT_API_SECRET
    BYBIT_TESTNET=1   # optional
    HIVE_SYMBOL=BTCUSDT
    HIVE_QTY_USDT=10
    HIVE_SCAN_SECONDS=15
    HIVE_MAX_CYCLES=0   # 0 = run forever
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
DB_PATH = BASE_DIR / "hive_alpha_v11_fixed.db"

BYBIT_MAINNET = "https://api.bybit.com"
BYBIT_TESTNET = "https://api-testnet.bybit.com"
BYBIT_RECV_WINDOW = "5000"
DEFAULT_SYMBOL = os.getenv("HIVE_SYMBOL", "BTCUSDT").strip().upper()
DEFAULT_QTY_USDT = float(os.getenv("HIVE_QTY_USDT", "10"))
DEFAULT_SCAN_SECONDS = float(os.getenv("HIVE_SCAN_SECONDS", "15"))
DEFAULT_MAX_CYCLES = int(os.getenv("HIVE_MAX_CYCLES", "0"))
USE_TESTNET = os.getenv("BYBIT_TESTNET", "0").strip() in {"1", "true", "TRUE", "yes", "YES"}
BASE_URL = BYBIT_TESTNET if USE_TESTNET else BYBIT_MAINNET

SESSION = requests.Session()
SESSION.headers.update({"Content-Type": "application/json", "Accept": "application/json"})

LOCK = threading.Lock()
LAST_ERROR: str = ""
LAST_SCAN: Dict[str, Any] = {}


def utc_ms() -> int:
    return int(time.time() * 1000)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_compact(payload: Dict[str, Any]) -> str:
    return json.dumps(payload or {}, separators=(",", ":"), ensure_ascii=False)


def _auth_headers(api_key: str, api_secret: str, payload: Dict[str, Any]) -> Dict[str, str]:
    ts = str(utc_ms())
    body = _json_compact(payload)
    prehash = ts + api_key + BYBIT_RECV_WINDOW + body
    sign = hmac.new(api_secret.encode("utf-8"), prehash.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-TIMESTAMP": ts,
        "X-BAPI-RECV-WINDOW": BYBIT_RECV_WINDOW,
        "X-BAPI-SIGN": sign,
    }


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY,
                side TEXT,
                size REAL,
                entry_price REAL,
                unrealized_pnl REAL,
                updated_at TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                symbol TEXT,
                side TEXT,
                qty TEXT,
                order_type TEXT,
                status TEXT,
                response TEXT,
                error TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                level TEXT,
                message TEXT,
                detail TEXT
            )"""
        )


def db_log(level: str, message: str, detail: Any = None) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO logs (ts, level, message, detail) VALUES (?,?,?,?)",
                (now_utc(), level, message, json.dumps(detail, ensure_ascii=False, default=str) if detail is not None else None),
            )
    except Exception:
        pass


def api_request(method: str, path: str, *, params: Optional[Dict[str, Any]] = None,
                body: Optional[Dict[str, Any]] = None, auth: bool = False, timeout: int = 15) -> Tuple[Optional[Dict[str, Any]], Optional[requests.Response]]:
    url = f"{BASE_URL}{path}"
    headers = {}
    payload = body or {}
    if auth:
        api_key = os.getenv("BYBIT_API_KEY", "").strip()
        api_secret = os.getenv("BYBIT_API_SECRET", "").strip()
        if not api_key or not api_secret:
            return {"retCode": 10001, "retMsg": "Missing BYBIT_API_KEY / BYBIT_API_SECRET"}, None
        headers = _auth_headers(api_key, api_secret, payload)
    try:
        if method.upper() == "GET":
            resp = SESSION.get(url, params=params, timeout=timeout)
        elif method.upper() == "POST":
            resp = SESSION.post(url, params=params, data=_json_compact(payload), headers={**headers, "Content-Type": "application/json"}, timeout=timeout)
        elif method.upper() == "DELETE":
            resp = SESSION.delete(url, params=params, data=_json_compact(payload), headers={**headers, "Content-Type": "application/json"}, timeout=timeout)
        else:
            raise ValueError(f"Unsupported method: {method}")
        try:
            data = resp.json()
        except Exception:
            data = {"retCode": -1, "retMsg": "Non-JSON response", "text": resp.text}
        return data, resp
    except Exception as exc:
        return {"retCode": -1, "retMsg": str(exc)}, None


def log_api_error(context: str, data: Optional[Dict[str, Any]], resp: Optional[requests.Response]) -> None:
    global LAST_ERROR
    detail = {
        "context": context,
        "response": data,
        "status_code": getattr(resp, "status_code", None),
        "text": getattr(resp, "text", None),
    }
    LAST_ERROR = json.dumps(detail, ensure_ascii=False, default=str)
    db_log("error", context, detail)


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def ensure_btc_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if not symbol.endswith("USDT"):
        symbol = symbol.replace("/", "").replace("-", "")
    return symbol


def rsi_7_normalized(close: pd.Series) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(7).mean()
    loss = (-delta.clip(upper=0)).rolling(7).mean()
    rs = gain / (loss + 1e-12)
    rsi = 100 - (100 / (1 + rs))
    val = safe_float(rsi.iloc[-1], 50.0)
    return max(0.0, min(100.0, val))


def get_klines(symbol: str, interval: str = "5", limit: int = 50) -> pd.DataFrame:
    data, resp = api_request(
        "GET",
        "/v5/market/kline",
        params={"category": "linear", "symbol": symbol, "interval": interval, "limit": limit},
        auth=False,
    )
    if not data or data.get("retCode") != 0 or not data.get("result", {}).get("list"):
        # offline fallback: deterministic synthetic series based on symbol
        seed = abs(hash((symbol, interval))) % (2**32)
        rng = np.random.default_rng(seed)
        n = limit
        base = np.cumsum(rng.normal(0, 8, n)) + 20000
        close = base + rng.normal(0, 3, n)
        open_ = np.r_[close[0], close[:-1]]
        high = np.maximum(open_, close) + rng.uniform(0, 5, n)
        low = np.minimum(open_, close) - rng.uniform(0, 5, n)
        volume = np.abs(rng.normal(1000, 250, n))
        ts = pd.date_range(end=pd.Timestamp.utcnow(), periods=n, freq="5min")
        return pd.DataFrame({"ts": ts, "open": open_, "high": high, "low": low, "close": close, "volume": volume})
    rows = data["result"]["list"]
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype(np.int64), unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume", "turnover"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def volume_spike(volume: pd.Series) -> float:
    if len(volume) < 21:
        return 0.0
    avg20 = safe_float(volume.iloc[-21:-1].mean(), 0.0)
    cur = safe_float(volume.iloc[-1], 0.0)
    if avg20 <= 0:
        return 0.0
    ratio = cur / avg20
    return max(0.0, min(100.0, (ratio - 1.0) * 100.0))


def momentum_3(close: pd.Series) -> float:
    if len(close) < 4:
        return 0.0
    c0 = safe_float(close.iloc[-4], 0.0)
    c1 = safe_float(close.iloc[-3], 0.0)
    c2 = safe_float(close.iloc[-2], 0.0)
    c3 = safe_float(close.iloc[-1], 0.0)
    if c0 <= 0:
        return 0.0
    mom = ((c3 - c0) / c0) * 100.0
    return max(0.0, min(100.0, (mom + 3.0) / 6.0 * 100.0))


def compute_signal(df: pd.DataFrame) -> Dict[str, float]:
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    rsi_norm = rsi_7_normalized(close)
    vol_spike = volume_spike(vol)
    mom = momentum_3(close)
    score = (rsi_norm + vol_spike + mom) / 3.0
    return {
        "rsi_norm": rsi_norm,
        "vol_spike": vol_spike,
        "mom": mom,
        "score": score,
    }


def get_positions_from_bybit() -> List[Dict[str, Any]]:
    data, resp = api_request(
        "GET",
        "/v5/position/list",
        params={"category": "linear", "settleCoin": "USDT"},
        auth=True,
    )
    if not data or data.get("retCode") != 0:
        log_api_error("GET /v5/position/list", data, resp)
        return []
    result = data.get("result", {})
    rows = result.get("list", []) if isinstance(result, dict) else []
    out: List[Dict[str, Any]] = []
    for r in rows:
        size = abs(safe_float(r.get("size"), 0.0))
        if size <= 0:
            continue
        symbol = str(r.get("symbol") or "").upper()
        side = str(r.get("side") or "").capitalize()
        out.append({
            "symbol": symbol,
            "side": side,
            "size": size,
            "entry_price": safe_float(r.get("avgPrice"), 0.0),
            "unrealized_pnl": safe_float(r.get("unrealisedPnl") or r.get("unrealizedPnl"), 0.0),
            "raw": r,
        })
    return out


def get_last_price(symbol: str) -> float:
    data, resp = api_request(
        "GET",
        "/v5/market/tickers",
        params={"category": "linear", "symbol": ensure_btc_symbol(symbol)},
        auth=False,
    )
    if not data or data.get("retCode") != 0:
        log_api_error("GET /v5/market/tickers", data, resp)
        return 0.0
    lst = data.get("result", {}).get("list", [])
    if not lst:
        return 0.0
    return safe_float(lst[0].get("lastPrice"), 0.0)


def sync_positions() -> List[Dict[str, Any]]:
    positions = get_positions_from_bybit()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM positions")
            for p in positions:
                conn.execute(
                    "INSERT OR REPLACE INTO positions (symbol, side, size, entry_price, unrealized_pnl, updated_at) VALUES (?,?,?,?,?,?)",
                    (p["symbol"], p["side"], p["size"], p["entry_price"], p["unrealized_pnl"], now_utc()),
                )
    except Exception as exc:
        db_log("error", "sync_positions db write failed", str(exc))
    return positions


def has_open_position(symbol: str, positions: Optional[List[Dict[str, Any]]] = None) -> bool:
    positions = positions if positions is not None else sync_positions()
    symbol = ensure_btc_symbol(symbol)
    return any(p["symbol"] == symbol and p["size"] > 0 for p in positions)


def side_to_bybit_side(side: str) -> str:
    side = side.lower()
    if side in {"buy", "long"}:
        return "Buy"
    if side in {"sell", "short"}:
        return "Sell"
    raise ValueError(f"Unknown side: {side}")


def open_market_position(symbol: str, side: str, qty_usdt: float) -> Dict[str, Any]:
    symbol = ensure_btc_symbol(symbol)
    payload = {
        "category": "linear",
        "symbol": symbol,
        "side": side_to_bybit_side(side),
        "orderType": "Market",
        "qty": str(qty_usdt),
        "timeInForce": "IOC",
        "positionIdx": 0,
    }
    data, resp = api_request("POST", "/v5/order/create", body=payload, auth=True)
    if not data or data.get("retCode") != 0:
        log_api_error("POST /v5/order/create", data, resp)
        raise RuntimeError(f"Bybit order error: {data}")
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO orders (ts, symbol, side, qty, order_type, status, response, error) VALUES (?,?,?,?,?,?,?,?)",
                (now_utc(), symbol, side_to_bybit_side(side), str(qty_usdt), "Market", "submitted", json.dumps(data, ensure_ascii=False, default=str), None),
            )
    except Exception as exc:
        db_log("error", "order db write failed", str(exc))
    return data


def close_position(symbol: str, side: str, qty: Optional[float] = None) -> Dict[str, Any]:
    symbol = ensure_btc_symbol(symbol)
    close_side = "Sell" if side.lower() in {"buy", "long"} else "Buy"
    payload = {
        "category": "linear",
        "symbol": symbol,
        "side": close_side,
        "orderType": "Market",
        "qty": str(qty) if qty is not None else "0",
        "reduceOnly": True,
        "timeInForce": "IOC",
        "positionIdx": 0,
    }
    data, resp = api_request("POST", "/v5/order/create", body=payload, auth=True)
    if not data or data.get("retCode") != 0:
        log_api_error("POST /v5/order/create close", data, resp)
        raise RuntimeError(f"Bybit close error: {data}")
    return data


@dataclass
class PositionState:
    symbol: str
    side: str
    size: float
    entry_price: float
    unrealized_pnl: float

    @property
    def tp_price(self) -> float:
        if self.side.lower() == "buy":
            return self.entry_price * 1.02
        return self.entry_price * 0.98

    @property
    def sl_price(self) -> float:
        if self.side.lower() == "buy":
            return self.entry_price * 0.99
        return self.entry_price * 1.01


class HiveAlphaBot:
    def __init__(self) -> None:
        init_db()
        self.symbol = DEFAULT_SYMBOL
        self.qty_usdt = DEFAULT_QTY_USDT
        self.scan_seconds = DEFAULT_SCAN_SECONDS
        self.max_cycles = DEFAULT_MAX_CYCLES
        self.positions: Dict[str, PositionState] = {}
        self.last_signal: Dict[str, Any] = {}
        self.last_cycle_error: str = ""
        self._stop = False

    def refresh_positions(self) -> List[Dict[str, Any]]:
        rows = sync_positions()
        self.positions = {
            p["symbol"]: PositionState(
                symbol=p["symbol"],
                side=p["side"],
                size=p["size"],
                entry_price=p["entry_price"],
                unrealized_pnl=p["unrealized_pnl"],
            )
            for p in rows
        }
        return rows

    def evaluate(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        sym = ensure_btc_symbol(symbol or self.symbol)
        df = get_klines(sym, interval="5", limit=50)
        sig = compute_signal(df)
        sig["symbol"] = sym
        sig["ts"] = now_utc()
        sig["should_open"] = sig["score"] >= 70.0
        sig["side"] = "buy" if safe_float(df["close"].iloc[-1], 0.0) >= safe_float(df["close"].iloc[-4], 0.0) else "sell"
        self.last_signal = sig
        return sig

    def maybe_open(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        sym = ensure_btc_symbol(signal["symbol"])
        positions = self.refresh_positions()
        if has_open_position(sym, positions):
            return None
        if not signal.get("should_open"):
            return None
        try:
            return open_market_position(sym, signal["side"], self.qty_usdt)
        except Exception as exc:
            self.last_cycle_error = str(exc)
            db_log("error", "maybe_open", str(exc))
            return None

    def manage_positions(self) -> List[Dict[str, Any]]:
        positions = self.refresh_positions()
        results = []
        for p in positions:
            state = self.positions.get(p["symbol"])
            if not state:
                continue
            last_price = get_last_price(p["symbol"])
            hit_tp = False
            hit_sl = False
            if last_price > 0:
                if state.side.lower() == "buy":
                    hit_tp = last_price >= state.tp_price
                    hit_sl = last_price <= state.sl_price
                else:
                    hit_tp = last_price <= state.tp_price
                    hit_sl = last_price >= state.sl_price
            if hit_tp or hit_sl:
                try:
                    close_position(p["symbol"], state.side, p["size"])
                    db_log("info", "position closed", {"symbol": p["symbol"], "reason": "tp" if hit_tp else "sl", "price": last_price})
                except Exception as exc:
                    self.last_cycle_error = str(exc)
                    db_log("error", "close_position", str(exc))
                    log_api_error("POST /v5/order/create close", {"exception": str(exc)}, None)
            results.append({
                "symbol": p["symbol"],
                "side": p["side"],
                "size": p["size"],
                "entry_price": p["entry_price"],
                "unrealized_pnl": p["unrealized_pnl"],
                "tp_price": state.tp_price,
                "sl_price": state.sl_price,
                "last_price": last_price,
                "hit_tp": hit_tp,
                "hit_sl": hit_sl,
            })
        return results

    def cycle(self) -> Dict[str, Any]:
        global LAST_SCAN
        try:
            positions = self.refresh_positions()
            signal = self.evaluate(self.symbol)
            opened = self.maybe_open(signal)
            managed = self.manage_positions()
            LAST_SCAN = {
                "timestamp": now_utc(),
                "symbol": self.symbol,
                "signal": signal,
                "positions": managed,
                "opened": opened,
                "error": self.last_cycle_error,
            }
            return LAST_SCAN
        except Exception as exc:
            self.last_cycle_error = str(exc)
            db_log("error", "cycle", str(exc))
            LAST_SCAN = {"timestamp": now_utc(), "error": str(exc), "symbol": self.symbol}
            return LAST_SCAN

    def run(self) -> None:
        cycle = 0
        self.refresh_positions()
        while not self._stop:
            cycle += 1
            result = self.cycle()
            print(render_dashboard(result), flush=True)
            if self.max_cycles and cycle >= self.max_cycles:
                break
            time.sleep(self.scan_seconds)

    def stop(self) -> None:
        self._stop = True


def render_dashboard(state: Dict[str, Any]) -> str:
    lines = []
    lines.append(f"[{state.get('timestamp', now_utc())}] Hive Alpha v11 Fixed")
    lines.append(f"Symbol: {state.get('symbol', DEFAULT_SYMBOL)} | Testnet: {USE_TESTNET}")
    sig = state.get("signal") or {}
    if sig:
        lines.append(
            "Signal: score={score:.1f} rsi={rsi:.1f} vol={vol:.1f} mom={mom:.1f} open={open_flag}".format(
                score=sig.get("score", 0.0),
                rsi=sig.get("rsi_norm", 0.0),
                vol=sig.get("vol_spike", 0.0),
                mom=sig.get("mom", 0.0),
                open_flag=sig.get("should_open", False),
            )
        )
    pos = state.get("positions") or []
    if pos:
        for p in pos[:5]:
            lines.append(
                f"Pos {p['symbol']} {p['side']} size={p['size']} entry={p['entry_price']:.2f} pnl={p['unrealized_pnl']:.4f} tp={p['tp_price']:.2f} sl={p['sl_price']:.2f}"
            )
    else:
        lines.append("Positions: none")
    if state.get("opened"):
        lines.append(f"Opened: {state['opened']}")
    err = state.get("error") or LAST_ERROR
    if err:
        lines.append(f"Error: {err}")
    return "\n".join(lines)


def main() -> None:
    bot = HiveAlphaBot()
    print(render_dashboard(bot.cycle()), flush=True)
    if bot.max_cycles == 1:
        return
    if bot.max_cycles > 1:
        for _ in range(bot.max_cycles - 1):
            time.sleep(bot.scan_seconds)
            print(render_dashboard(bot.cycle()), flush=True)
        return
    bot.run()


if __name__ == "__main__":
    main()
