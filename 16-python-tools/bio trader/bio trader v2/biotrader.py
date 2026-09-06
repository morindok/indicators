"""BioTrader Ultimate: a resilient, public-data, demo trading organism.

The module deliberately keeps exchange access read-only.  It uses Bybit's
public V5 market endpoints for ticker and kline data and falls back to a
deterministic synthetic market when the public API is unreachable.  Orders are
never sent to an exchange: the portfolio is a local paper-trading simulator.

The "biological" language is an interaction model for the UI and the decision
engine.  It is implemented as explicit, inspectable signals, genes, state and
risk controls rather than a claim of sentience.
"""

from __future__ import annotations

import hashlib
import math
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import numpy as np
import pandas as pd
import requests

from bio_memory import BioMemory


REST_CANDIDATES = [
    os.getenv("BYBIT_BASE_URL", "https://api.bybit.com"),
    "https://api.bytick.com",
    "https://api.bybit.kz",
]
DEFAULT_CATEGORY = "linear"
DEFAULT_INTERVAL = "5"
DEFAULT_UNIVERSE = 28
DEFAULT_SLOTS = 5
DEFAULT_MARGIN = 500.0
DEFAULT_LEVERAGE = 15
TAKER_FEE_RATE = 0.00055


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if not math.isfinite(float(value)):
        return low
    return float(max(low, min(high, value)))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _normalise(value: float, scale: float) -> float:
    """Map a signed value to [-1, 1] with a smooth saturation."""
    if scale <= 0:
        return 0.0
    return float(np.tanh(safe_float(value) / scale))


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=1).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff().fillna(0.0)
    gain = delta.clip(lower=0.0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0.0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0.0, np.nan)
    result = 100.0 - (100.0 / (1.0 + rs))
    # A flat/up-only series should not produce NaN in a decision.
    result = result.replace([np.inf, -np.inf], np.nan).fillna(50.0)
    return result.clip(0.0, 100.0)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    previous_close = df["close"].shift(1)
    ranges = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return ranges.ewm(alpha=1 / period, adjust=False, min_periods=1).mean()


def adx(df: pd.DataFrame, period: int = 14) -> float:
    """Normalised trend strength in [0, 1] from Wilder's ADX."""
    if len(df) < period * 2 + 2:
        return 0.0
    high, low, close = df["high"], df["low"], df["close"]
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    previous_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    alpha = 1.0 / period
    atr_s = tr.ewm(alpha=alpha, adjust=False, min_periods=period).mean().replace(0, np.nan)
    plus_di = 100.0 * plus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr_s
    minus_di = 100.0 * minus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr_s
    sum_di = (plus_di + minus_di).replace(0.0, np.nan)
    dx = (100.0 * (plus_di - minus_di).abs() / sum_di).replace([np.inf, -np.inf], np.nan)
    value = dx.ewm(alpha=alpha, adjust=False, min_periods=1).mean().iloc[-1]
    return clamp(safe_float(value) / 50.0)


def bollinger_z(close: pd.Series, period: int = 20) -> float:
    """Signed position of price inside its Bollinger channel, in [-1, 1]."""
    if len(close) < period:
        return 0.0
    mean = close.rolling(period).mean().iloc[-1]
    std = close.rolling(period).std().iloc[-1]
    if not np.isfinite(std) or std <= 0:
        return 0.0
    z = safe_float((float(close.iloc[-1]) - float(mean)) / (2.0 * float(std)))
    return clamp(z, -1.0, 1.0)


def vwap_deviation(df: pd.DataFrame, window: int = 96) -> float:
    """Distance of the last price from rolling VWAP, expressed in ATR units."""
    frame = df.tail(max(window, 10))
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    volume = frame["volume"].clip(lower=1e-12)
    vwap = float((typical * volume).sum() / volume.sum())
    atr_value = float(atr(frame, 14).iloc[-1])
    if atr_value <= 0 or vwap <= 0:
        return 0.0
    return clamp(safe_float(float(frame["close"].iloc[-1]) - vwap) / atr_value, -3.0, 3.0) / 3.0


def ema_stack_score(close: pd.Series) -> float:
    """Structural alignment of the 9/21/50 EMA ribbon in [-1, 1]."""
    if len(close) < 50:
        return 0.0
    e9 = ema(close, 9).iloc[-1]
    e21 = ema(close, 21).iloc[-1]
    e50 = ema(close, 50).iloc[-1]
    last = float(close.iloc[-1])
    checks = (last > e9, e9 > e21, e21 > e50)
    bull = sum(checks)
    bear = 3 - bull
    return (bull - bear) / 3.0


def obv_slope(df: pd.DataFrame, lookback: int = 24) -> float:
    """On-balance-volume slope proxy: signed money flow of recent bars."""
    if len(df) < lookback + 2:
        return 0.0
    frame = df.tail(lookback + 1)
    direction = np.sign(frame["close"].diff().fillna(0.0))
    flow = (direction * frame["volume"]).cumsum()
    total_flow = float(flow.iloc[-1]) - float(flow.iloc[0])
    mean_volume = float(frame["volume"].mean()) or 1e-12
    return clamp(total_flow / (mean_volume * lookback), -1.0, 1.0)


def htf_trend(frame: pd.DataFrame, rule: str, fast: int = 8, slow: int = 21) -> float:
    """Aggregate 5-minute candles to a higher timeframe and score its trend.

    Returns a signed value in [-1, 1]: positive means the higher timeframe
    supports long exposure.
    """
    if frame.empty or len(frame) < 30:
        return 0.0
    try:
        agg = (
            frame.set_index("ts")
            .resample(rule)
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .dropna(subset=["close"])
        )
    except Exception:
        return 0.0
    if len(agg) < slow + 4:
        return 0.0
    close = agg["close"].astype(float)
    gap = float(ema(close, fast).iloc[-1] / max(float(ema(close, slow).iloc[-1]), 1e-12) - 1.0)
    slope = linear_slope(np.log(close.tail(slow + 6)), slow + 6)
    return clamp(_normalise(0.6 * gap + 0.4 * slope * 12.0, 0.010), -1.0, 1.0)


def linear_slope(values: Iterable[float], lookback: int = 24) -> float:
    arr = np.asarray(list(values), dtype=float)
    if arr.size < 3:
        return 0.0
    arr = arr[-lookback:]
    x = np.arange(arr.size, dtype=float)
    denom = float(np.sum((x - x.mean()) ** 2))
    if denom == 0:
        return 0.0
    return float(np.polyfit(x, arr, 1)[0])


def serialise_number(value: Any, digits: int = 8) -> float:
    value = safe_float(value)
    return round(value, digits)


class BybitPublicClient:
    """Small read-only adapter for Bybit V5 public market endpoints."""

    def __init__(self, timeout: float = 4.5) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "BioTrader-2500/1.0 (public-market-demo)",
                "Accept": "application/json",
                "Referer": "https://www.bybit.com/",
            }
        )
        self._active_base: str | None = None
        self._lock = threading.Lock()
        self.last_error: str = ""

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any] | None:
        bases: list[str] = []
        if self._active_base:
            bases.append(self._active_base)
        bases.extend(base for base in REST_CANDIDATES if base not in bases)
        for base in bases:
            try:
                response = self.session.get(
                    f"{base.rstrip('/')}{path}", params=params, timeout=self.timeout
                )
                if response.status_code in (403, 429, 451):
                    continue
                response.raise_for_status()
                payload = response.json()
                if payload.get("retCode") == 0:
                    with self._lock:
                        self._active_base = base
                    self.last_error = ""
                    return payload
                self.last_error = str(payload.get("retMsg", "unknown Bybit response"))
            except Exception as exc:  # network, JSON and transient API failures
                self.last_error = str(exc)
        return None

    def get_tickers(self, category: str = DEFAULT_CATEGORY) -> pd.DataFrame:
        payload = self._get("/v5/market/tickers", {"category": category})
        if not payload:
            return pd.DataFrame()
        rows = (payload.get("result") or {}).get("list") or []
        if not rows:
            return pd.DataFrame()
        records: list[dict[str, Any]] = []
        for row in rows:
            symbol = str(row.get("symbol", "")).upper()
            if not symbol.endswith("USDT"):
                continue
            last = safe_float(row.get("lastPrice"))
            bid = safe_float(row.get("bid1Price"), last)
            ask = safe_float(row.get("ask1Price"), last)
            if last <= 0:
                continue
            if bid <= 0:
                bid = last
            if ask <= 0:
                ask = last
            if ask < bid:
                bid, ask = ask, bid
            records.append(
                {
                    "symbol": symbol,
                    "last_price": last,
                    "bid": bid,
                    "ask": ask,
                    "volume_24h": safe_float(row.get("volume24h")),
                    "turnover_24h": safe_float(row.get("turnover24h")),
                    "change_24h": safe_float(row.get("price24hPcnt")) * 100.0,
                    "funding_rate": safe_float(row.get("fundingRate")) * 100.0,
                }
            )
        return pd.DataFrame.from_records(records)

    def get_klines(
        self, symbol: str, interval: str = DEFAULT_INTERVAL, limit: int = 180
    ) -> pd.DataFrame:
        payload = self._get(
            "/v5/market/kline",
            {
                "category": DEFAULT_CATEGORY,
                "symbol": symbol.upper(),
                "interval": str(interval),
                "limit": min(max(int(limit), 1), 1000),
            },
        )
        if not payload:
            return pd.DataFrame()
        rows = (payload.get("result") or {}).get("list") or []
        if not rows:
            return pd.DataFrame()
        records = []
        for row in rows:
            if len(row) < 7:
                continue
            records.append(
                {
                    "ts": pd.to_datetime(int(row[0]), unit="ms", utc=True),
                    "open": safe_float(row[1]),
                    "high": safe_float(row[2]),
                    "low": safe_float(row[3]),
                    "close": safe_float(row[4]),
                    "volume": safe_float(row[5]),
                    "turnover": safe_float(row[6]),
                }
            )
        frame = pd.DataFrame.from_records(records)
        if frame.empty:
            return frame
        frame = frame[(frame["close"] > 0) & (frame["high"] > 0)]
        return frame.sort_values("ts").reset_index(drop=True)

    def get_orderbook_imbalance(self, symbol: str, limit: int = 25) -> float:
        """Return a bounded bid/ask size imbalance for one symbol."""
        payload = self._get(
            "/v5/market/orderbook",
            {"category": DEFAULT_CATEGORY, "symbol": symbol.upper(), "limit": limit},
        )
        if not payload:
            return 0.0
        result = payload.get("result") or {}
        bids = result.get("b") or []
        asks = result.get("a") or []
        bid_size = sum(safe_float(item[1]) for item in bids if len(item) > 1)
        ask_size = sum(safe_float(item[1]) for item in asks if len(item) > 1)
        total = bid_size + ask_size
        return clamp((bid_size - ask_size) / total, -1.0, 1.0) if total else 0.0

    def scan_market(
        self, universe_limit: int = DEFAULT_UNIVERSE, interval: str = DEFAULT_INTERVAL
    ) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], str]:
        """Fetch a liquid universe and its candles.

        The method is intentionally defensive: a temporary API outage yields an
        empty frame so the organism can switch to the local synthetic market.
        """
        tickers = self.get_tickers(DEFAULT_CATEGORY)
        if tickers.empty:
            return pd.DataFrame(), {}, "offline"

        tickers = tickers[
            (tickers["turnover_24h"] > 0)
            & ~tickers["symbol"].str.contains("1000|USDC|USDE", regex=True)
        ].copy()
        if tickers.empty:
            return pd.DataFrame(), {}, "offline"
        tickers = tickers.sort_values("turnover_24h", ascending=False).head(universe_limit)
        candles: dict[str, pd.DataFrame] = {}

        # Parallel reads keep the UI responsive while remaining read-only.
        # Deep history (35h of 5m) lets the 1-hour confluence breathe.
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(tickers)))) as pool:
            jobs = {
                pool.submit(self.get_klines, symbol, interval, 420): symbol
                for symbol in tickers["symbol"].tolist()
            }
            for job in as_completed(jobs):
                symbol = jobs[job]
                try:
                    frame = job.result()
                except Exception:
                    frame = pd.DataFrame()
                if not frame.empty:
                    candles[symbol] = frame
        if len(candles) < 5:
            return pd.DataFrame(), {}, "offline"
        return tickers, candles, "live"


class SyntheticMarket:
    """Deterministic market generator used for demos and API outages."""

    SYMBOLS = [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "DOGEUSDT",
        "BNBUSDT",
        "LINKUSDT",
        "AVAXUSDT",
        "SUIUSDT",
        "ADAUSDT",
        "TONUSDT",
        "APTUSDT",
        "OPUSDT",
        "ARBUSDT",
        "NEARUSDT",
        "LTCUSDT",
        "DOTUSDT",
        "ATOMUSDT",
        "FILUSDT",
        "INJUSDT",
        "TIAUSDT",
        "SEIUSDT",
        "WIFUSDT",
        "PEPEUSDT",
    ]
    BASES = {
        "BTCUSDT": 108_000,
        "ETHUSDT": 3_850,
        "SOLUSDT": 205,
        "XRPUSDT": 2.85,
        "DOGEUSDT": 0.205,
        "BNBUSDT": 710,
        "LINKUSDT": 24,
        "AVAXUSDT": 38,
        "SUIUSDT": 3.45,
        "ADAUSDT": 0.94,
        "TONUSDT": 3.15,
        "APTUSDT": 5.8,
        "OPUSDT": 0.82,
        "ARBUSDT": 0.59,
        "NEARUSDT": 3.4,
        "LTCUSDT": 94,
        "DOTUSDT": 4.1,
        "ATOMUSDT": 4.7,
        "FILUSDT": 2.4,
        "INJUSDT": 13.5,
        "TIAUSDT": 1.8,
        "SEIUSDT": 0.31,
        "WIFUSDT": 0.74,
        "PEPEUSDT": 0.000009,
    }

    @staticmethod
    def _seed(symbol: str) -> int:
        digest = hashlib.sha256(symbol.encode("utf-8")).hexdigest()[:12]
        return int(digest, 16) % (2**32 - 1)

    def candles(self, symbol: str, limit: int = 180) -> pd.DataFrame:
        now_slot = int(time.time() // 15)
        rng = np.random.default_rng(self._seed(symbol))
        base = self.BASES.get(symbol, 1.0)
        idx = np.arange(limit, dtype=float)
        # Each asset has a slowly changing regime plus a short impulse.  The
        # current slot changes the phase without making the series discontinuous.
        phase = now_slot / 19.0 + (self._seed(symbol) % 100) / 17.0
        regime_bias = ((self._seed(symbol) % 21) - 10) * 0.00016
        drift = regime_bias + math.sin(phase) * 0.00062 + math.cos(phase / 2.7) * 0.00028
        wave = np.sin(idx / 8.5 + phase) * 0.004 + np.cos(idx / 23 + phase / 2) * 0.002
        noise = rng.normal(0, 0.0022, limit)
        returns = drift + wave + noise
        closes = base * np.exp(np.cumsum(returns))
        # Keep generated values in a believable range around the base.
        closes *= base / np.median(closes) * (1 + 0.015 * math.sin(phase))
        opens = np.r_[closes[0], closes[:-1]] * (1 + rng.normal(0, 0.0008, limit))
        high = np.maximum(opens, closes) * (1 + np.abs(rng.normal(0, 0.0018, limit)))
        low = np.minimum(opens, closes) * (1 - np.abs(rng.normal(0, 0.0018, limit)))
        volume = np.exp(rng.normal(10.4, 0.55, limit)) * (1 + np.abs(returns) * 80)
        ts = pd.date_range(
            end=pd.Timestamp.now(tz="UTC").floor("min"), periods=limit, freq="5min"
        )
        return pd.DataFrame(
            {
                "ts": ts,
                "open": opens,
                "high": high,
                "low": low,
                "close": closes,
                "volume": volume,
                "turnover": volume * closes,
            }
        )

    def tickers(self) -> pd.DataFrame:
        records: list[dict[str, float | str]] = []
        for rank, symbol in enumerate(self.SYMBOLS):
            frame = self.candles(symbol, 180)
            last = float(frame["close"].iloc[-1])
            previous = float(frame["close"].iloc[-7])
            spread_bps = 1.2 + (self._seed(symbol) % 90) / 35.0
            spread = last * spread_bps / 10_000
            turnover = float(frame["turnover"].tail(48).sum()) * (1.0 + rank / 90)
            records.append(
                {
                    "symbol": symbol,
                    "last_price": last,
                    "bid": last - spread / 2,
                    "ask": last + spread / 2,
                    "volume_24h": float(frame["volume"].tail(288).sum()),
                    "turnover_24h": turnover,
                    "change_24h": (last / previous - 1) * 100,
                    "funding_rate": math.sin(rank + time.time() / 1800) * 0.012,
                }
            )
        return pd.DataFrame.from_records(records)

    def scan_market(
        self, universe_limit: int = DEFAULT_UNIVERSE, interval: str = DEFAULT_INTERVAL
    ) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], str]:
        tickers = self.tickers().sort_values("turnover_24h", ascending=False).head(universe_limit)
        candles = {symbol: self.candles(symbol, 420) for symbol in tickers["symbol"]}
        return tickers.reset_index(drop=True), candles, "simulation"


def extract_features(
    frame: pd.DataFrame,
    ticker: dict[str, Any],
    book_imbalance: float = 0.0,
    htf: dict[str, float] | None = None,
    ranks: dict[str, float] | None = None,
) -> dict[str, float | str]:
    """Convert candles and a ticker into a compact multi-sensory observation."""
    if frame.empty or len(frame) < 20:
        return {}
    df = frame.copy()
    close = df["close"].astype(float)
    volume = df["volume"].astype(float)
    fast = ema(close, 9)
    slow = ema(close, 26)
    atr_series = atr(df, 14)
    rsi_series = rsi(close, 14)
    last = safe_float(ticker.get("last_price"), float(close.iloc[-1]))
    bid = safe_float(ticker.get("bid"), last)
    ask = safe_float(ticker.get("ask"), last)
    mid = max((bid + ask) / 2.0, 1e-12)
    spread_bps = abs(ask - bid) / mid * 10_000
    returns = close.pct_change().fillna(0.0)
    ret_3 = float(close.iloc[-1] / close.iloc[-4] - 1.0)
    ret_12 = float(close.iloc[-1] / close.iloc[-13] - 1.0)
    ret_36 = float(close.iloc[-1] / close.iloc[-37] - 1.0) if len(close) > 37 else ret_12
    trend_gap = float(fast.iloc[-1] / max(slow.iloc[-1], 1e-12) - 1.0)
    slope_pct = linear_slope(np.log(close.tail(36)), 36)
    vol_mean = volume.rolling(30, min_periods=5).mean()
    vol_std = volume.rolling(30, min_periods=5).std().replace(0, np.nan)
    volume_z = float(((volume.iloc[-1] - vol_mean.iloc[-1]) / vol_std.iloc[-1])) if pd.notna(vol_std.iloc[-1]) else 0.0
    range_high = float(close.rolling(48, min_periods=10).max().iloc[-1])
    range_low = float(close.rolling(48, min_periods=10).min().iloc[-1])
    range_width = max(range_high - range_low, last * 1e-8)
    breakout = float((last - (range_high + range_low) / 2) / (range_width / 2))
    atr_pct = float(atr_series.iloc[-1] / max(last, 1e-12))
    # Institutional senses -------------------------------------------------
    adx_value = adx(df, 14)
    bb_z = bollinger_z(close, 20)
    vwap_dev = vwap_deviation(df, 96)
    stack = ema_stack_score(close)
    flow = obv_slope(df, 24)
    funding = safe_float(ticker.get("funding_rate"))
    # Funding extremes mark crowded positioning; fade them slightly.
    funding_bias = _normalise(-funding, 0.045)
    htf = htf or {}
    ranks = ranks or {}
    # Signed senses in [-1, 1].
    momentum = _normalise(0.50 * ret_3 + 0.32 * ret_12 + 0.18 * ret_36, 0.025)
    trend = clamp(
        0.55 * _normalise(trend_gap, 0.012) + 0.25 * stack + 0.20 * clamp(slope_pct * 10.0, -1.0, 1.0),
        -1.0,
        1.0,
    )
    volume_impulse = clamp(0.62 * _normalise(volume_z, 2.5) + 0.38 * flow)
    volatility = clamp(atr_pct / 0.018)
    rsi_signal = _normalise(float(rsi_series.iloc[-1] - 50.0), 25.0)
    multi_tf_agreement = float(np.sign(ret_3) == np.sign(ret_12)) * 0.5 + float(np.sign(ret_12) == np.sign(ret_36)) * 0.5
    signed_agreement = (
        (np.sign(ret_3) + np.sign(ret_12) + np.sign(ret_36)) / 3.0
    ) * (0.45 + 0.55 * multi_tf_agreement)
    liquidity = clamp(math.log1p(max(safe_float(ticker.get("turnover_24h")), 0.0)) / 22.0)
    pressure = clamp(book_imbalance, -1.0, 1.0)
    change_24h = safe_float(ticker.get("change_24h"))
    htf_agree = clamp(
        0.5 * safe_float(htf.get("trend_15")) + 0.35 * safe_float(htf.get("trend_60")) + 0.15 * stack,
        -1.0,
        1.0,
    )
    regime = "TREND" if (adx_value > 0.42 and abs(htf_agree) > 0.25 and multi_tf_agreement > 0.5) else "RANGE"
    if volatility > 0.82 or spread_bps > 22.0:
        regime = "STRESS"
    return {
        "last_price": last,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread_bps": spread_bps,
        "ret_3": ret_3,
        "ret_12": ret_12,
        "ret_36": ret_36,
        "trend": trend,
        "momentum": momentum,
        "signed_agreement": float(np.clip(signed_agreement, -1.0, 1.0)),
        "volume_impulse": volume_impulse,
        "volatility": volatility,
        "atr": float(atr_series.iloc[-1]),
        "atr_pct": atr_pct,
        "rsi": float(rsi_series.iloc[-1]),
        "rsi_signal": rsi_signal,
        "breakout": clamp(breakout, -1.0, 1.0),
        "multi_tf_agreement": multi_tf_agreement,
        "liquidity": liquidity,
        "book_imbalance": pressure,
        "change_24h": change_24h,
        "regime": regime,
        "candle_high": float(df["high"].iloc[-1]),
        "candle_low": float(df["low"].iloc[-1]),
        # Institutional extensions ------------------------------------------
        "adx": adx_value,
        "bb_z": bb_z,
        "vwap_dev": vwap_dev,
        "ema_stack": stack,
        "flow": flow,
        "funding_rate": funding,
        "funding_bias": funding_bias,
        "htf_agree": htf_agree,
        "htf_trend_15": safe_float(htf.get("trend_15")),
        "htf_trend_60": safe_float(htf.get("trend_60")),
        "momentum_rank": clamp(safe_float(ranks.get("momentum_rank")), 0.0, 1.0),
        "vol_rank": clamp(safe_float(ranks.get("vol_rank")), 0.0, 1.0),
    }


class NeuralCortex:
    """A deterministic, inspectable Ultimate neural ensemble.

    The network is intentionally not advertised as a trained general-purpose
    AI model. It is a fast nonlinear feature mixer whose fixed synapses are
    combined with the organism's durable, evolving genome. The 3,072 neurons
    are split across sensory, pattern, context, decision and executive layers.
    """

    LAYERS = (512, 1024, 768, 512, 256)
    INPUT_NAMES = (
        "trend",
        "momentum",
        "volume_impulse",
        "volatility",
        "rsi_signal",
        "breakout",
        "signed_agreement",
        "liquidity",
        "book_imbalance",
        "spread_quality",
        "ret_3",
        "ret_12",
        "ret_36",
        "change_24h",
        "atr_pct",
        "sin_time",
        "adx",
        "bb_z",
        "vwap_dev",
        "ema_stack",
        "flow",
        "funding_bias",
        "htf_agree",
        "momentum_rank",
    )
    CROSS_COUNT = 20  # quadratic/cross-channel interactions appended to inputs

    def __init__(self, seed: int = 2500, plasticity_bias: float = 0.0) -> None:
        self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed)
        self.plasticity_bias = float(np.clip(plasticity_bias, -0.25, 0.25))
        self.weights: list[np.ndarray] = []
        self.biases: list[np.ndarray] = []
        previous = len(self.INPUT_NAMES) + self.CROSS_COUNT
        for width in self.LAYERS:
            scale = math.sqrt(2.0 / max(previous, 1))
            self.weights.append(
                self.rng.normal(0.0, scale * 0.22, (previous, width)).astype(np.float32)
            )
            self.biases.append(np.zeros(width, dtype=np.float32))
            previous = width
        self.readout_signal = self.rng.normal(0.0, 0.08, self.LAYERS[-1]).astype(np.float32)
        self.readout_confidence = self.rng.normal(0.0, 0.08, self.LAYERS[-1]).astype(np.float32)
        self.readout_novelty = self.rng.normal(0.0, 0.08, self.LAYERS[-1]).astype(np.float32)
        self.readout_risk = self.rng.normal(0.0, 0.08, self.LAYERS[-1]).astype(np.float32)

    @property
    def neuron_count(self) -> int:
        return int(sum(self.LAYERS))

    @property
    def layer_view(self) -> list[dict[str, Any]]:
        labels = ["حسی", "الگو", "زمینه", "تصمیم", "اجرایی"]
        return [
            {"name": labels[index], "neurons": int(width)}
            for index, width in enumerate(self.LAYERS)
        ]

    def _input_vector(self, features: dict[str, Any]) -> np.ndarray:
        values = []
        for name in self.INPUT_NAMES:
            if name == "spread_quality":
                value = 1.0 - clamp(safe_float(features.get("spread_bps")) / 18.0)
            elif name == "sin_time":
                value = math.sin(time.time() / 900.0)
            else:
                value = safe_float(features.get(name))
            values.append(float(np.clip(value, -1.0, 1.0)))
        base = np.asarray(values, dtype=np.float32)
        # Quadratic/cross-channel features give the pattern layer richer
        # interactions without an external ML dependency.
        cross = np.asarray(
            [
                base[0] * base[1],
                base[0] * base[5],
                base[1] * base[2],
                base[3] * base[8],
                base[6] * base[7],
                base[10] - base[11],
                base[11] - base[12],
                base[4] * base[5],
                math.sin(float(base[0]) * math.pi),
                math.cos(float(base[1]) * math.pi),
                math.sin(float(base[3]) * math.pi),
                math.cos(float(base[6]) * math.pi),
                float(np.mean(base[:8])),
                float(np.std(base[:8])),
                float(np.max(base[:8])),
                float(np.min(base[:8])),
                # Institutional interaction channels.
                base[22] * base[0],          # HTF agreement × trend
                base[16] * base[6],          # ADX strength × multi-TF consensus
                base[18] - base[17],         # VWAP deviation vs Bollinger position
                base[21] * base[23],         # funding fade × momentum rank
            ],
            dtype=np.float32,
        )
        return np.concatenate([base, cross]).astype(np.float32)

    def forward(self, features: dict[str, Any]) -> dict[str, float]:
        activation = self._input_vector(features)
        activities: list[float] = []
        for weights, bias in zip(self.weights, self.biases):
            activation = np.tanh(activation @ weights + bias)
            activities.append(float(np.mean(np.abs(activation))))
        signal = float(np.tanh(np.dot(activation, self.readout_signal) * 0.22 + self.plasticity_bias))
        confidence = float(1.0 / (1.0 + math.exp(-float(np.dot(activation, self.readout_confidence) * 0.18))))
        novelty = float(1.0 / (1.0 + math.exp(-float(np.dot(activation, self.readout_novelty) * 0.20))))
        risk = float(1.0 / (1.0 + math.exp(-float(np.dot(activation, self.readout_risk) * 0.20))))
        return {
            "signal": float(np.clip(signal, -1.0, 1.0)),
            "confidence": float(np.clip(confidence, 0.0, 1.0)),
            "novelty": float(np.clip(novelty, 0.0, 1.0)),
            "risk": float(np.clip(risk, 0.0, 1.0)),
            "activation": float(np.mean(activities)),
        }

    def adapt(self, reward: float) -> None:
        """Small persistent synaptic bias update from journal outcomes."""
        reward_signal = float(np.tanh(safe_float(reward) / 20.0))
        self.plasticity_bias = float(
            np.clip(self.plasticity_bias + 0.018 * reward_signal, -0.25, 0.25)
        )


@dataclass
class RiskConfig:
    """Capital-preservation parameters of the institutional risk desk.

    Every knob exists to answer one question: "what stops this book from
    bleeding?"  Sizing is volatility-targeted, entries must clear an
    expectancy-after-costs bar, and escalating loss states progressively
    disarm the trader instead of doubling down.
    """

    risk_per_trade_pct: float = 0.85       # % of equity risked between entry and SL
    max_margin_per_trade: float = 160.0    # hard per-trade margin ceiling
    min_margin_per_trade: float = 25.0     # below this the trade is noise
    daily_loss_limit_pct: float = 3.0      # halt new entries for the UTC day
    soft_drawdown_pct: float = 5.0         # half size beyond this drawdown
    hard_drawdown_pct: float = 9.0         # kill switch beyond this drawdown
    loss_streak_limit: int = 3             # cooldown trigger
    cooldown_minutes: float = 12.0         # sniper pause after a loss streak
    min_quality: float = 47.0              # sniper gate on composite quality
    min_confidence: float = 0.40           # sniper gate on calibrated confidence
    min_ev_r: float = 0.12                 # expected value net of costs, in R
    max_spread_bps: float = 16.0           # liquidity floor
    max_atr_pct: float = 0.030             # chaos ceiling
    min_atr_pct: float = 0.0012            # dead-market floor
    max_same_direction: int = 3            # one-way traffic cap
    partial_at_r: float = 1.0              # bank profits at +1R
    partial_fraction: float = 0.5          # share of the position banked
    breakeven_buffer_r: float = 0.12       # lock a hair of profit at BE
    chandelier_atr_mult: float = 1.9       # trailing stop distance in ATR
    max_hold_minutes: float = 240.0        # scalper's time stop
    stall_check_minutes: float = 55.0      # give-up threshold on dead trades
    stall_min_r: float = 0.20              # minimum progress expected by then
    rotation_hysteresis: float = 7.0       # anti-churn seat protection (pts)

    def as_dict(self) -> dict[str, float]:
        return {
            key: round(float(value), 4) if isinstance(value, (int, float)) else value
            for key, value in self.__dict__.items()
        }


def evaluate_entry_gate(
    decision: dict[str, Any],
    config: RiskConfig,
    *,
    market_allows: bool = True,
    direction_count: int = 0,
) -> dict[str, Any]:
    """The sniper's go/no-go checklist.

    Returns an auditable verdict with the estimated expectancy of the trade
    AFTER commissions and spread, expressed in R multiples.  Only setups whose
    modelled edge survives friction are allowed near the book.
    """
    side = str(decision.get("side", "LONG"))
    direction = 1.0 if side == "LONG" else -1.0
    quality = safe_float(decision.get("quality"))
    confidence = safe_float(decision.get("confidence"))
    consensus = safe_float(decision.get("consensus"))
    signal = abs(safe_float(decision.get("signal")))
    spread_bps = abs(safe_float(decision.get("spread_bps")))
    entry = max(safe_float(decision.get("entry"), decision.get("last_price")), 1e-9)
    stop_distance = max(safe_float(decision.get("stop_distance")), entry * 0.0008)
    reward_multiple = max(safe_float(decision.get("reward_multiple"), 1.5), 0.5)
    atr_pct = safe_float(decision.get("atr_pct"))
    htf_aligned = clamp(safe_float(decision.get("htf_agree")) * direction, -1.0, 1.0)

    reasons: list[str] = []
    if quality < config.min_quality:
        reasons.append(f"کیفیت {quality:.0f} < {config.min_quality:.0f}")
    if confidence < config.min_confidence:
        reasons.append(f"اعتماد {confidence:.2f} < {config.min_confidence:.2f}")
    if spread_bps > config.max_spread_bps:
        reasons.append(f"اسپرد {spread_bps:.1f}bp")
    if atr_pct > config.max_atr_pct:
        reasons.append("نوسان آشوبناک")
    elif atr_pct < config.min_atr_pct:
        reasons.append("بازار مرده")
    if not market_allows:
        reasons.append("رژیم BTC مخالف جهت")
    if direction_count >= config.max_same_direction:
        reasons.append("سقف هم‌جهتی پر است")

    # Win probability implied by calibrated conviction, confluence and the
    # higher-timeframe backdrop.  Deliberately conservative at the extremes.
    p_win = clamp(
        0.26 + 0.36 * confidence + 0.16 * consensus + 0.22 * max(htf_aligned, 0.0),
        0.04,
        0.86,
    )
    fee_bps = TAKER_FEE_RATE * 2.0 * 10_000.0
    cost_r = ((fee_bps + spread_bps) / 10_000.0 * entry) / stop_distance
    ev_r = p_win * reward_multiple - (1.0 - p_win) - cost_r
    if ev_r < config.min_ev_r:
        reasons.append(f"EV {ev_r:+.2f}R < {config.min_ev_r:+.2f}R")
    if signal < 0.08:
        reasons.append("سیگنال ضعیف")

    return {
        "allowed": not reasons,
        "reasons": reasons,
        "ev_r": float(ev_r),
        "cost_r": float(cost_r),
        "p_win": float(p_win),
        "edge_bps": float((ev_r * stop_distance / entry) * 10_000.0),
    }


class RiskManager:
    """The preservation desk: halts, cooldowns, budgets and sizing power.

    State survives restarts through SQLite so a drawdown cannot be forgotten
    by relaunching the app.
    """

    def __init__(
        self,
        config: RiskConfig | None = None,
        memory: BioMemory | None = None,
        starting_equity: float = DEFAULT_MARGIN,
    ) -> None:
        self.config = config or RiskConfig()
        self.memory = memory
        now = utc_now()
        self.day_key = now.strftime("%Y-%m-%d")
        self.day_start_equity = float(starting_equity)
        self.peak_equity = float(starting_equity)
        self.realized_today = 0.0
        self.loss_streak = 0
        self.win_streak = 0
        self.cooldown_until: datetime | None = None
        self.halt_reason = ""
        self.events: deque[dict[str, str]] = deque(maxlen=40)
        self._last_equity = float(starting_equity)
        self._daily_halt_logged = False
        self._hard_halt_logged = False
        if memory:
            self._restore(memory.load_risk_state())

    # -- persistence -------------------------------------------------------
    def _restore(self, state: dict[str, Any]) -> None:
        if not state:
            return
        self.day_key = str(state.get("day_key", self.day_key))
        self.day_start_equity = safe_float(state.get("day_start_equity"), self.day_start_equity)
        self.peak_equity = safe_float(state.get("peak_equity"), self.peak_equity)
        self.realized_today = safe_float(state.get("realized_today"))
        self.loss_streak = int(safe_float(state.get("loss_streak")))
        self.win_streak = int(safe_float(state.get("win_streak")))
        cooldown = state.get("cooldown_until")
        if cooldown:
            try:
                parsed = datetime.fromisoformat(str(cooldown))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                if parsed > utc_now():
                    self.cooldown_until = parsed
            except ValueError:
                pass

    def _persist(self) -> None:
        if not self.memory:
            return
        self.memory.save_risk_state(
            {
                "day_key": self.day_key,
                "day_start_equity": self.day_start_equity,
                "peak_equity": self.peak_equity,
                "realized_today": self.realized_today,
                "loss_streak": self.loss_streak,
                "win_streak": self.win_streak,
                "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else "",
            }
        )

    def log(self, kind: str, text: str) -> None:
        self.events.appendleft({"time": utc_now().isoformat(), "kind": kind, "text": text})
        if self.memory:
            self.memory.record_risk_event(kind, text)

    # -- lifecycle ---------------------------------------------------------
    def reset_session(self, equity: float) -> None:
        """Restart-of-session: streaks and cooldowns clear, budgets re-anchor."""
        self.day_start_equity = float(equity)
        self.peak_equity = max(self.peak_equity, float(equity))
        self.realized_today = 0.0
        self.loss_streak = 0
        self.win_streak = 0
        self.cooldown_until = None
        self.halt_reason = ""
        self._daily_halt_logged = False
        self._hard_halt_logged = False
        self.log("reset", "میز ریسک برای جلسه‌ی جدید بازنشانی شد")
        self._persist()

    def begin_scan(self, equity: float) -> None:
        today = utc_now().strftime("%Y-%m-%d")
        if today != self.day_key:
            self.day_key = today
            self.day_start_equity = float(equity)
            self.realized_today = 0.0
            self._daily_halt_logged = False
            if self.halt_reason.startswith("سقف ضرر روزانه"):
                self.halt_reason = ""
            self.log("day", f"بودجه‌ی روز {today} باز شد؛ مبنا ${self.day_start_equity:,.0f}")
        self.peak_equity = max(self.peak_equity, float(equity))

    # -- derived state -----------------------------------------------------
    @property
    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self._last_equity) / self.peak_equity * 100.0)

    def update_equity(self, equity: float) -> None:
        self._last_equity = float(equity)

    @property
    def daily_limit_used_pct(self) -> float:
        base = max(self.day_start_equity, 1e-9)
        return -self.realized_today / base * 100.0

    def sizing_multiplier(self) -> float:
        multiplier = 1.0
        if self.drawdown_pct >= self.config.soft_drawdown_pct:
            multiplier *= 0.5
        if self.loss_streak >= self.config.loss_streak_limit:
            multiplier *= 0.6
        if self.win_streak >= 4:
            multiplier *= 1.15
        return clamp(multiplier, 0.25, 1.15)

    def trade_allowed(self) -> tuple[bool, str]:
        if self.drawdown_pct >= self.config.hard_drawdown_pct:
            return False, f"کیل‌سویی افت سرمایه {self.drawdown_pct:.1f}%"
        if self.daily_limit_used_pct >= self.config.daily_loss_limit_pct:
            return False, f"سقف ضرر روزانه ({self.config.daily_loss_limit_pct:.0f}%) مصرف شد"
        if self.cooldown_until and utc_now() < self.cooldown_until:
            remaining = (self.cooldown_until - utc_now()).total_seconds() / 60.0
            return False, f"خنک‌شدن اسنایپر {remaining:.0f} دقیقه"
        return True, ""

    # -- feedback ----------------------------------------------------------
    def on_trade_closed(self, pnl: float) -> None:
        pnl = safe_float(pnl)
        self.realized_today += pnl
        if pnl < 0:
            self.loss_streak += 1
            self.win_streak = 0
            if self.loss_streak == self.config.loss_streak_limit:
                self.cooldown_until = utc_now() + timedelta(minutes=self.config.cooldown_minutes)
                self.log(
                    "cooldown",
                    f"{self.loss_streak} باخت متوالی؛ توقف ورود تا "
                    f"{self.cooldown_until.strftime('%H:%M')} UTC",
                )
        elif pnl > 0:
            self.win_streak += 1
            self.loss_streak = 0
        if (
            not self._daily_halt_logged
            and self.daily_limit_used_pct >= self.config.daily_loss_limit_pct
        ):
            self._daily_halt_logged = True
            self.halt_reason = "سقف ضرر روزانه"
            self.log("halt-day", "ورودهای جدید تا فردای UTC بسته شد")
        if not self._hard_halt_logged and self.drawdown_pct >= self.config.hard_drawdown_pct:
            self._hard_halt_logged = True
            self.halt_reason = f"کیل‌سویی {self.drawdown_pct:.1f}%"
            self.log("halt-dd", "کیل‌سویی افت سرمایه فعال شد؛ فقط مدیریت خروج")
        self._persist()

    def snapshot_view(self) -> dict[str, Any]:
        allowed, reason = self.trade_allowed()
        cooldown_left = 0.0
        if self.cooldown_until:
            cooldown_left = max(0.0, (self.cooldown_until - utc_now()).total_seconds() / 60.0)
        return {
            "config": self.config.as_dict(),
            "day_key": self.day_key,
            "day_start_equity": serialise_number(self.day_start_equity, 2),
            "peak_equity": serialise_number(self.peak_equity, 2),
            "realized_today": serialise_number(self.realized_today, 2),
            "daily_budget_used_pct": serialise_number(self.daily_limit_used_pct, 2),
            "drawdown_pct": serialise_number(self.drawdown_pct, 2),
            "loss_streak": self.loss_streak,
            "win_streak": self.win_streak,
            "cooldown_remaining_min": serialise_number(cooldown_left, 1),
            "trading_allowed": allowed,
            "halt_reason": reason if not allowed else "",
            "sizing_multiplier": serialise_number(self.sizing_multiplier(), 3),
            "events": list(self.events)[:8],
        }


@dataclass
class Gene:
    key: str
    label: str
    base_weight: float
    mutation: float
    expression: float = 1.0

    def expressed_weight(self) -> float:
        return max(0.01, self.base_weight * (1.0 + self.mutation) * self.expression)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "base_weight": round(self.base_weight, 4),
            "mutation": round(self.mutation, 4),
            "expression": round(self.expression, 4),
            "expressed_weight": round(self.expressed_weight(), 4),
        }


class BioOrganism:
    """A transparent multi-sense scoring model with adaptive internal state."""

    def __init__(self, seed: int = 2500) -> None:
        rng = np.random.default_rng(seed)
        specs = [
            ("retina", "بینایی روند", 0.22),
            ("cochlea", "شنوایی حجم", 0.16),
            ("vestibular", "تعادل چندبازه", 0.16),
            ("baroreceptor", "فشار نقدشوندگی", 0.12),
            ("nociceptor", "درد و ریسک", 0.13),
            ("thermoreceptor", "دماسنج نوسان", 0.10),
            ("intuition", "شهود جهش", 0.11),
        ]
        self.genome: dict[str, Gene] = {
            key: Gene(key, label, weight, float(rng.uniform(0.08, 0.42)))
            for key, label, weight in specs
        }
        self.state: dict[str, Any] = {
            "heartbeat": 72,
            "awareness": 0.74,
            "focus": 0.78,
            "stress": 0.18,
            "energy": 0.91,
            "coherence": 0.72,
            "mood": "جست‌وجوی فرصت",
            "last_intent": "پایش میدان بازار",
            "updated_at": utc_now().isoformat(),
        }
        self.scan_count = 0
        self.last_decisions: list[dict[str, Any]] = []

    def _weights(self) -> dict[str, float]:
        raw = {key: gene.expressed_weight() for key, gene in self.genome.items()}
        total = sum(raw.values()) or 1.0
        return {key: value / total for key, value in raw.items()}

    def evaluate(self, symbol: str, features: dict[str, Any]) -> dict[str, Any]:
        if not features:
            return {}
        volatility = clamp(safe_float(features["volatility"]))
        spread_quality = 1.0 - clamp(safe_float(features["spread_bps"]) / 18.0)
        senses = {
            "retina": safe_float(features["trend"]),
            "cochlea": 0.62 * safe_float(features["volume_impulse"]) + 0.38 * safe_float(features["book_imbalance"]),
            "vestibular": safe_float(features["signed_agreement"])
            * (0.55 + 0.45 * abs(safe_float(features["momentum"]))),
            "baroreceptor": 0.62 * safe_float(features["book_imbalance"])
            + 0.38 * (2.0 * safe_float(features["liquidity"]) - 1.0),
            "nociceptor": -(0.70 * volatility + 0.30 * clamp(safe_float(features["spread_bps"]) / 30.0)),
            "thermoreceptor": float(np.sign(safe_float(features["momentum"])))
            * max(0.0, 0.58 - abs(volatility - 0.42)),
            "intuition": 0.55 * safe_float(features["breakout"]) + 0.45 * safe_float(features["rsi_signal"]),
        }
        senses = {key: float(np.clip(value, -1.0, 1.0)) for key, value in senses.items()}
        weights = self._weights()
        risk_penalty = 0.70 * volatility + 0.30 * clamp(safe_float(features["spread_bps"]) / 30.0)
        directional_keys = [key for key in weights if key != "nociceptor"]
        directional_total = sum(weights[key] for key in directional_keys) or 1.0
        raw_direction = sum(weights[key] * senses[key] for key in directional_keys) / directional_total
        raw_signal = raw_direction * (1.0 - 0.28 * clamp(risk_penalty))
        # Consensus raises confidence; disagreement makes the organism cautious.
        signed = np.array([senses[key] for key in weights], dtype=float)
        consensus = clamp(1.0 - float(np.std(signed)) / 0.85)
        opportunity = clamp(
            0.42 * abs(raw_signal)
            + 0.22 * abs(safe_float(features["momentum"]))
            + 0.16 * safe_float(features["liquidity"])
            + 0.20 * spread_quality
        )
        confidence = clamp(0.58 * opportunity + 0.30 * consensus + 0.12 * (1.0 - volatility))
        # A low-volatility neutral signal is still ranked, but will receive a
        # smaller quality score than a coherent directional impulse.
        quality = clamp(0.54 * confidence + 0.32 * abs(raw_signal) + 0.14 * spread_quality) * 100.0
        side = "LONG" if raw_signal >= 0 else "SHORT"
        entry = safe_float(features["ask"] if side == "LONG" else features["bid"], features["last_price"])
        atr_value = max(safe_float(features["atr"]), entry * 0.0012)
        stop_distance = max(entry * (0.0026 + 0.0035 * volatility), atr_value * (1.20 + 0.55 * (1.0 - confidence)))
        stop_distance = min(stop_distance, entry * 0.035)
        reward_multiple = 1.55 + 1.25 * confidence + 0.35 * max(raw_signal, 0.0)
        target_distance = stop_distance * reward_multiple
        tp = entry + target_distance if side == "LONG" else entry - target_distance
        sl = entry - stop_distance if side == "LONG" else entry + stop_distance
        return {
            "symbol": symbol,
            "side": side,
            "signal": float(raw_signal),
            "confidence": float(confidence),
            "quality": float(quality),
            "consensus": float(consensus),
            "entry": float(entry),
            "tp": float(tp),
            "sl": float(sl),
            "stop_distance": float(stop_distance),
            "reward_multiple": float(reward_multiple),
            "senses": senses,
            "regime": str(features["regime"]),
            "spread_bps": float(features["spread_bps"]),
            "volatility": volatility,
            "atr_pct": float(features["atr_pct"]),
            "rsi": float(features["rsi"]),
            "momentum": float(features["momentum"]),
            "liquidity": float(features["liquidity"]),
            "last_price": float(features["last_price"]),
            "bid": float(features["bid"]),
            "ask": float(features["ask"]),
            "candle_high": float(features["candle_high"]),
            "candle_low": float(features["candle_low"]),
        }

    def scan(self, observations: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        decisions = [self.evaluate(symbol, features) for symbol, features in observations]
        decisions = [item for item in decisions if item]
        decisions.sort(key=lambda item: (item["quality"], item["confidence"]), reverse=True)
        self.last_decisions = decisions
        self.scan_count += 1
        if decisions:
            mean_signal = float(np.mean([abs(item["signal"]) for item in decisions]))
            mean_vol = float(np.mean([item["volatility"] for item in decisions]))
            top = decisions[0]
            self.state["heartbeat"] = int(
                round(61 + 48 * mean_signal + 30 * mean_vol + 14 * top["confidence"])
            )
            self.state["stress"] = clamp(0.12 + 0.76 * mean_vol + 0.18 * (1 - top["consensus"]))
            self.state["focus"] = clamp(0.52 + 0.42 * top["confidence"] + 0.08 * top["consensus"])
            self.state["awareness"] = clamp(0.60 + 0.28 * top["consensus"] + 0.12 * (1 - self.state["stress"]))
            self.state["energy"] = clamp(0.96 - 0.35 * self.state["stress"] + 0.08 * top["confidence"])
            self.state["coherence"] = clamp(0.35 + 0.50 * top["consensus"] + 0.15 * (1 - mean_vol))
            if self.state["stress"] > 0.72:
                mood = "حالت دفاعی / نوسان شدید"
            elif top["confidence"] > 0.78:
                mood = "شکار اسنایپر"
            else:
                mood = "جست‌وجوی فرصت"
            self.state["mood"] = mood
            self.state["last_intent"] = f"{top['side']} روی {top['symbol']} با همگرایی {top['consensus'] * 100:.0f}%"
        self.state["updated_at"] = utc_now().isoformat()
        return decisions

    def organs(self) -> list[dict[str, Any]]:
        s = self.state
        return [
            {"name": "قشر پیش‌بینی", "icon": "◈", "value": s["awareness"], "detail": "مدل‌سازی سناریو"},
            {"name": "شبکیه‌ی روند", "icon": "◎", "value": s["focus"], "detail": "EMA / مومنتوم"},
            {"name": "حلزون حجم", "icon": "◉", "value": s["coherence"], "detail": "نبض نقدینگی"},
            {"name": "گیرنده‌ی فشار", "icon": "◇", "value": 1 - s["stress"], "detail": "اسپرد / ریسک"},
            {"name": "غده‌ی شهود", "icon": "✦", "value": s["energy"], "detail": "جهش‌های نوظهور"},
            {"name": "سیستم درد", "icon": "△", "value": s["stress"], "detail": "ترمز حفاظتی"},
        ]

    def genome_view(self) -> list[dict[str, Any]]:
        return [gene.as_dict() for gene in self.genome.values()]


class UltimateBioOrganism(BioOrganism):
    """Persistent Ultimate organism with a 3,072-neuron neural cortex."""

    GENE_SPECS = [
        ("retina", "بینایی روند", 0.14),
        ("cochlea", "شنوایی حجم", 0.10),
        ("vestibular", "تعادل چندبازه", 0.10),
        ("baroreceptor", "فشار نقدشوندگی", 0.08),
        ("nociceptor", "درد و ریسک", 0.09),
        ("thermoreceptor", "دماسنج نوسان", 0.07),
        ("intuition", "شهود جهش", 0.09),
        ("microstructure", "ریزساختار", 0.07),
        ("regime", "تشخیص رژیم", 0.07),
        ("memory", "حافظه تجربی", 0.06),
        ("adrenaline", "آدرنالین فرصت", 0.05),
        ("inhibition", "مهار تکانه", 0.05),
        ("temporal", "حس زمان", 0.04),
        ("synchrony", "هم‌زمانی", 0.04),
        ("metacognition", "فراشناخت", 0.05),
    ]

    def __init__(self, seed: int = 2500, memory: BioMemory | None = None) -> None:
        self.memory = memory
        rng = np.random.default_rng(seed)
        defaults = [
            {
                "key": key,
                "label": label,
                "base_weight": weight,
                "mutation": float(rng.uniform(0.08, 0.42)),
                "expression": 1.0,
            }
            for key, label, weight in self.GENE_SPECS
        ]
        if memory:
            memory.ensure_genes(defaults)
            saved_genes = memory.load_genes()
            meta = memory.load_meta() or {}
        else:
            saved_genes = {}
            meta = {}
        self.genome: dict[str, Gene] = {}
        for default in defaults:
            saved = saved_genes.get(default["key"], {})
            self.genome[default["key"]] = Gene(
                default["key"],
                str(saved.get("label", default["label"])),
                safe_float(saved.get("base_weight"), default["base_weight"]),
                safe_float(saved.get("mutation"), default["mutation"]),
                safe_float(saved.get("expression"), 1.0),
            )
        saved_state = meta.get("state", {}) or {}
        self.generation = int(meta.get("generation", 0))
        self.scan_count = int(meta.get("scan_count", 0))
        self.memory_signal = safe_float(saved_state.get("memory_signal"))
        self.plasticity_bias = safe_float(saved_state.get("plasticity_bias"))
        # Confidence calibration: realised hit-rate vs promised conviction.
        self.calibration = clamp(safe_float(saved_state.get("calibration"), 1.0), 0.55, 1.30)
        self.regime_stats: dict[str, dict[str, float]] = {}
        self.cortex = NeuralCortex(seed=seed, plasticity_bias=self.plasticity_bias)
        self.state: dict[str, Any] = {
            "heartbeat": 72,
            "awareness": 0.74,
            "focus": 0.78,
            "stress": 0.18,
            "energy": 0.91,
            "coherence": 0.72,
            "mood": "جست‌وجوی فرصت",
            "last_intent": "پایش میدان بازار",
            "updated_at": utc_now().isoformat(),
        }
        self.state.update(
            {
                key: value
                for key, value in saved_state.items()
                if key
                in {
                    "heartbeat",
                    "awareness",
                    "focus",
                    "stress",
                    "energy",
                    "coherence",
                    "mood",
                    "last_intent",
                }
            }
        )
        self.last_decisions: list[dict[str, Any]] = []
        self._last_gene_contributions: dict[str, float] = {}
        self._persist()

    def _persist(self) -> None:
        self.state["generation"] = self.generation
        self.state["neuron_count"] = self.cortex.neuron_count
        self.state["plasticity_bias"] = self.cortex.plasticity_bias
        self.state["memory_signal"] = self.memory_signal
        self.state["calibration"] = self.calibration
        self.state["updated_at"] = utc_now().isoformat()
        if self.memory:
            self.memory.save_meta(
                generation=self.generation,
                scan_count=self.scan_count,
                neuron_count=self.cortex.neuron_count,
                state=self.state,
            )

    def _regime_factor(self, regime: str) -> float:
        """Discount conviction in regimes where the book keeps losing."""
        stats = self.regime_stats.get(regime)
        if not stats or stats.get("n", 0.0) < 8:
            return 1.0
        win_rate = stats["wins"] / max(stats["n"], 1.0)
        if win_rate < 0.35:
            return 0.72
        if win_rate < 0.45:
            return 0.88
        return 1.0

    def learn_stats(self, trades: list[dict[str, Any]]) -> None:
        """Update confidence calibration and per-regime reliability tables.

        Calibration multiplies promised confidence by realised accuracy, so a
        model that says "70%" but wins 45% of the time is gradually talked
        down before it can over-size into losses.
        """
        if not trades:
            return
        for trade in trades:
            pnl = safe_float(trade.get("realized_pnl"))
            regime = str(trade.get("regime", "RANGE")) or "RANGE"
            bucket = self.regime_stats.setdefault(regime, {"wins": 0.0, "n": 0.0})
            bucket["n"] += 1.0
            if pnl > 0:
                bucket["wins"] += 1.0
        recent = self.memory.journal(40) if self.memory else []
        recent = [item for item in recent if item.get("status") == "CLOSED"]
        if len(recent) >= 12:
            wins = sum(1 for item in recent if safe_float(item.get("net_pnl")) > 0)
            hit_rate = wins / len(recent)
            avg_promised = np.mean(
                [clamp(safe_float(item.get("confidence"), 0.5), 0.05, 0.95) for item in recent]
            )
            target = clamp(hit_rate / max(float(avg_promised), 0.30), 0.55, 1.30)
            self.calibration = float(np.clip(0.80 * self.calibration + 0.20 * target, 0.55, 1.30))
        self._persist()

    def evaluate(self, symbol: str, features: dict[str, Any]) -> dict[str, Any]:
        if not features:
            return {}
        volatility = clamp(safe_float(features.get("volatility")))
        spread_quality = 1.0 - clamp(safe_float(features.get("spread_bps")) / 18.0)
        neural = self.cortex.forward(features)
        risk = 0.70 * volatility + 0.30 * clamp(safe_float(features.get("spread_bps")) / 30.0)
        momentum = safe_float(features.get("momentum"))
        signed_agreement = safe_float(features.get("signed_agreement"))
        trend = safe_float(features.get("trend"))
        pressure = safe_float(features.get("book_imbalance"))
        agreement = safe_float(features.get("multi_tf_agreement"))
        htf_agree = safe_float(features.get("htf_agree"))
        adx_value = clamp(safe_float(features.get("adx")))
        vwap_dev = safe_float(features.get("vwap_dev"))
        bb_z = safe_float(features.get("bb_z"))
        flow = safe_float(features.get("flow"))
        funding_bias = safe_float(features.get("funding_bias"))
        senses = {
            "retina": trend,
            "cochlea": 0.62 * safe_float(features.get("volume_impulse")) + 0.38 * pressure,
            "vestibular": signed_agreement * (0.55 + 0.45 * abs(momentum)),
            "baroreceptor": 0.62 * pressure + 0.38 * (2.0 * safe_float(features.get("liquidity")) - 1.0),
            "nociceptor": -risk,
            "thermoreceptor": float(np.sign(momentum)) * max(0.0, 0.58 - abs(volatility - 0.42)),
            "intuition": 0.38 * safe_float(features.get("breakout"))
            + 0.32 * safe_float(features.get("rsi_signal"))
            + 0.30 * funding_bias,
            "microstructure": 0.50 * pressure + 0.28 * neural["signal"] + 0.22 * vwap_dev,
            "regime": (trend * (0.35 + 0.45 * agreement) + 0.25 * htf_agree) * (0.55 + 0.45 * adx_value),
            "memory": self.memory_signal,
            "adrenaline": float(np.sign(momentum)) * clamp(abs(momentum) + volatility * 0.35),
            "inhibition": -risk * (0.65 + 0.35 * neural["risk"]),
            "temporal": math.sin(time.time() / 900.0) * 0.25,
            "synchrony": signed_agreement * neural["activation"],
            "metacognition": 0.70 * neural["signal"] + 0.30 * (vwap_dev - bb_z),
        }
        senses = {key: float(np.clip(value, -1.0, 1.0)) for key, value in senses.items()}
        weights = self._weights()
        directional_keys = [key for key in weights if key not in {"nociceptor", "inhibition"}]
        directional_total = sum(weights[key] for key in directional_keys) or 1.0
        contributions = {
            key: weights[key] * senses[key] / directional_total for key in directional_keys
        }
        self._last_gene_contributions = contributions
        gene_signal = float(sum(contributions.values()))
        raw_signal = float(np.clip(0.58 * gene_signal + 0.42 * neural["signal"], -1.0, 1.0))
        # A counter-HTF signal must be materially stronger to survive.
        direction = 1.0 if raw_signal >= 0 else -1.0
        htf_penalty = 1.0 - 0.22 * max(0.0, -htf_agree * direction)
        raw_signal = float(np.clip(raw_signal * htf_penalty, -1.0, 1.0))
        signed = np.array(list(senses.values()), dtype=float)
        consensus = clamp(1.0 - float(np.std(signed)) / 0.90)
        opportunity = clamp(
            0.30 * abs(raw_signal)
            + 0.16 * abs(momentum)
            + 0.12 * safe_float(features.get("liquidity"))
            + 0.14 * spread_quality
            + 0.16 * neural["confidence"]
            + 0.12 * neural["novelty"]
        )
        confidence = clamp(
            0.38 * opportunity
            + 0.22 * consensus
            + 0.18 * neural["confidence"]
            + 0.12 * (1.0 - volatility)
            + 0.10 * (1.0 - neural["risk"])
        )
        # Institutional calibration: realised accuracy disciplines promise.
        regime = str(features.get("regime", "RANGE"))
        confidence = clamp(confidence * self.calibration * self._regime_factor(regime))
        quality = clamp(
            0.42 * confidence
            + 0.25 * abs(raw_signal)
            + 0.13 * spread_quality
            + 0.10 * neural["novelty"]
            + 0.10 * neural["activation"]
        ) * 100.0
        side = "LONG" if raw_signal >= 0 else "SHORT"
        entry = safe_float(
            features.get("ask") if side == "LONG" else features.get("bid"),
            features.get("last_price"),
        )
        atr_value = max(safe_float(features.get("atr")), entry * 0.0012)
        stop_distance = max(
            entry * (0.0026 + 0.0035 * volatility),
            atr_value * (1.20 + 0.55 * (1.0 - confidence)),
        )
        stop_distance = min(stop_distance, entry * 0.035)
        reward_multiple = 1.55 + 1.25 * confidence + 0.35 * max(raw_signal, 0.0)
        target_distance = stop_distance * reward_multiple
        tp = entry + target_distance if side == "LONG" else entry - target_distance
        sl = entry - stop_distance if side == "LONG" else entry + stop_distance
        return {
            "symbol": symbol,
            "side": side,
            "signal": raw_signal,
            "confidence": confidence,
            "quality": quality,
            "consensus": consensus,
            "entry": entry,
            "tp": float(tp),
            "sl": float(sl),
            "stop_distance": float(stop_distance),
            "reward_multiple": float(reward_multiple),
            "senses": senses,
            "neural": neural,
            "regime": regime,
            "spread_bps": safe_float(features.get("spread_bps")),
            "volatility": volatility,
            "atr": float(atr_value),
            "atr_pct": safe_float(features.get("atr_pct")),
            "rsi": safe_float(features.get("rsi")),
            "adx": adx_value,
            "bb_z": bb_z,
            "vwap_dev": vwap_dev,
            "ema_stack": safe_float(features.get("ema_stack")),
            "flow": flow,
            "funding_bias": funding_bias,
            "htf_agree": htf_agree,
            "htf_trend_15": safe_float(features.get("htf_trend_15")),
            "htf_trend_60": safe_float(features.get("htf_trend_60")),
            "momentum_rank": clamp(safe_float(features.get("momentum_rank")), 0.0, 1.0),
            "vol_rank": clamp(safe_float(features.get("vol_rank")), 0.0, 1.0),
            "momentum": momentum,
            "liquidity": safe_float(features.get("liquidity")),
            "last_price": safe_float(features.get("last_price")),
            "bid": safe_float(features.get("bid")),
            "ask": safe_float(features.get("ask")),
            "candle_high": safe_float(features.get("candle_high")),
            "candle_low": safe_float(features.get("candle_low")),
        }

    def scan(self, observations: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        decisions = [self.evaluate(symbol, features) for symbol, features in observations]
        decisions = [item for item in decisions if item]
        decisions.sort(key=lambda item: (item["quality"], item["confidence"]), reverse=True)
        self.last_decisions = decisions
        self.scan_count += 1
        if decisions:
            mean_signal = float(np.mean([abs(item["signal"]) for item in decisions]))
            mean_vol = float(np.mean([item["volatility"] for item in decisions]))
            top = decisions[0]
            neural_conf = float(np.mean([item["neural"]["confidence"] for item in decisions]))
            self.state["heartbeat"] = int(
                round(61 + 48 * mean_signal + 30 * mean_vol + 14 * top["confidence"] + 8 * neural_conf)
            )
            self.state["stress"] = clamp(
                0.10 + 0.68 * mean_vol + 0.16 * (1 - top["consensus"]) + 0.06 * top["neural"]["risk"]
            )
            self.state["focus"] = clamp(0.50 + 0.34 * top["confidence"] + 0.10 * top["neural"]["activation"] + 0.06 * top["consensus"])
            self.state["awareness"] = clamp(0.57 + 0.22 * top["consensus"] + 0.14 * neural_conf + 0.07 * (1 - self.state["stress"]))
            self.state["energy"] = clamp(0.96 - 0.34 * self.state["stress"] + 0.10 * top["confidence"])
            self.state["coherence"] = clamp(0.32 + 0.42 * top["consensus"] + 0.16 * neural_conf + 0.10 * (1 - mean_vol))
            if self.state["stress"] > 0.72:
                mood = "حالت دفاعی / نوسان شدید"
            elif top["confidence"] > 0.78:
                mood = "شکار اسنایپر Ultimate"
            else:
                mood = "جست‌وجوی فرصت"
            self.state["mood"] = mood
            self.state["last_intent"] = f"{top['side']} روی {top['symbol']} با شبکه‌ی {self.cortex.neuron_count:,} نورونی"
        self._persist()
        return decisions

    def learn(self, reward: float, trigger: str = "trade_outcome") -> None:
        reward_signal = float(np.tanh(safe_float(reward) / 20.0))
        self.cortex.adapt(reward)
        self.plasticity_bias = self.cortex.plasticity_bias
        self.memory_signal = float(np.clip(0.82 * self.memory_signal + 0.18 * reward_signal, -1.0, 1.0))
        self.generation += 1
        for key, gene in self.genome.items():
            old_mutation = gene.mutation
            contribution = safe_float(self._last_gene_contributions.get(key))
            direction = 1.0 if contribution >= 0 else -1.0
            delta = 0.012 * reward_signal * (0.55 + 0.45 * abs(contribution) + 0.15 * direction)
            gene.mutation = float(np.clip(gene.mutation + delta, 0.01, 0.95))
            gene.expression = float(np.clip(gene.expression + 0.006 * reward_signal * direction, 0.65, 1.65))
            if self.memory:
                self.memory.save_gene(
                    {
                        "key": gene.key,
                        "label": gene.label,
                        "base_weight": gene.base_weight,
                        "mutation": gene.mutation,
                        "expression": gene.expression,
                    },
                    old_mutation=old_mutation,
                    reward=reward,
                    trigger=trigger,
                )
        self._persist()

    def organs(self) -> list[dict[str, Any]]:
        organs = super().organs()
        organs.extend(
            [
                {"name": "قشر Ultimate", "icon": "Ψ", "value": self.state["awareness"], "detail": f"{self.cortex.neuron_count:,} نورون"},
                {"name": "حافظه SQLite", "icon": "⌬", "value": 1.0 if self.memory else 0.0, "detail": f"نسل {self.generation}"},
            ]
        )
        return organs

    def genome_view(self) -> list[dict[str, Any]]:
        return [gene.as_dict() for gene in self.genome.values()]

    def cortex_view(self) -> dict[str, Any]:
        return {
            "neuron_count": self.cortex.neuron_count,
            "layers": self.cortex.layer_view,
            "generation": self.generation,
            "plasticity_bias": round(self.cortex.plasticity_bias, 5),
            "memory_signal": round(self.memory_signal, 5),
            "calibration": round(self.calibration, 3),
        }


@dataclass
class Position:
    symbol: str
    side: str
    margin: float
    leverage: int
    notional: float
    qty: float
    entry: float
    mark: float
    tp: float
    sl: float
    stop_distance: float
    confidence: float
    quality: float
    regime: str
    spread_bps: float
    entry_fee: float
    entry_spread_cost: float
    opened_at: str
    heartbeat_at_open: int
    best_mark: float = 0.0
    status: str = "OPEN"
    last_reason: str = "signal"
    journal_id: int | None = None
    initial_qty: float = 0.0
    initial_stop_distance: float = 0.0
    risk_usd: float = 0.0
    realized_partial: float = 0.0
    partial_taken: bool = False
    max_r: float = 0.0

    def __post_init__(self) -> None:
        if self.initial_qty <= 0:
            self.initial_qty = self.qty
        if self.initial_stop_distance <= 0:
            self.initial_stop_distance = self.stop_distance
        if self.risk_usd <= 0:
            self.risk_usd = self.initial_qty * self.initial_stop_distance
        try:
            self.opened_dt = datetime.fromisoformat(self.opened_at)
        except (ValueError, TypeError):
            self.opened_dt = utc_now()

    @property
    def direction(self) -> int:
        return 1 if self.side == "LONG" else -1

    @property
    def move_r(self) -> float:
        stop = max(self.initial_stop_distance, 1e-12)
        return (self.mark - self.entry) * self.direction / stop

    @property
    def holding_minutes(self) -> float:
        return max(0.0, (utc_now() - self.opened_dt).total_seconds() / 60.0)

    def gross_pnl(self) -> float:
        return (self.mark - self.entry) * self.qty * self.direction

    def estimated_exit_fee(self) -> float:
        return abs(self.mark * self.qty) * TAKER_FEE_RATE

    def net_unrealised(self) -> float:
        return self.gross_pnl() - self.estimated_exit_fee()

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "margin": serialise_number(self.margin, 2),
            "leverage": self.leverage,
            "notional": serialise_number(self.notional, 2),
            "qty": serialise_number(self.qty, 8),
            "entry": serialise_number(self.entry),
            "mark": serialise_number(self.mark),
            "tp": serialise_number(self.tp),
            "sl": serialise_number(self.sl),
            "confidence": serialise_number(self.confidence, 4),
            "quality": serialise_number(self.quality, 2),
            "regime": self.regime,
            "spread_bps": serialise_number(self.spread_bps, 2),
            "pnl": serialise_number(self.net_unrealised() + self.realized_partial, 2),
            "pnl_pct_margin": serialise_number(
                (self.net_unrealised() + self.realized_partial) / max(self.margin, 1e-9) * 100, 2
            ),
            "r_multiple": serialise_number(self.move_r, 3),
            "risk_usd": serialise_number(self.risk_usd, 2),
            "partial_taken": self.partial_taken,
            "realized_partial": serialise_number(self.realized_partial, 2),
            "holding_min": serialise_number(self.holding_minutes, 1),
            "opened_at": self.opened_at,
            "heartbeat_at_open": self.heartbeat_at_open,
            "status": self.status,
            "last_reason": self.last_reason,
            "journal_id": self.journal_id,
        }


class DemoPortfolio:
    """Isolated-margin paper portfolio run by an institutional risk desk.

    Execution doctrine:
    * size is volatility-targeted, never fixed;
    * entries must clear the sniper gate (expectancy after costs);
    * +1R banks half the position and walks the stop to break-even;
    * a chandelier trail, stall guard and time stop retire tired trades;
    * seat changes require a challenger to beat the incumbent by a hysteresis
      margin, so fees are not burned on churn.
    """

    def __init__(
        self,
        initial_balance: float = DEFAULT_MARGIN,
        leverage: int = DEFAULT_LEVERAGE,
        slots: int = DEFAULT_SLOTS,
        fee_rate: float = TAKER_FEE_RATE,
        memory: BioMemory | None = None,
        risk_manager: RiskManager | None = None,
    ) -> None:
        self.initial_balance = float(initial_balance)
        self.balance = float(initial_balance)
        self.leverage = int(leverage)
        self.slots = int(slots)
        self.margin_per_slot = self.initial_balance / self.slots
        self.fee_rate = float(fee_rate)
        self.memory = memory
        self.risk = risk_manager or RiskManager(memory=memory, starting_equity=initial_balance)
        self.positions: dict[str, Position] = {}
        self.closed: list[dict[str, Any]] = []
        self.equity_curve: list[dict[str, Any]] = []
        self.total_scans = 0
        self.total_entries = 0
        self.realized_gross = 0.0
        self.fees_paid = 0.0

    @property
    def cfg(self) -> RiskConfig:
        return self.risk.config

    def reset(self) -> None:
        self.balance = self.initial_balance
        self.positions.clear()
        self.closed.clear()
        self.equity_curve.clear()
        self.total_scans = 0
        self.total_entries = 0
        self.realized_gross = 0.0
        self.fees_paid = 0.0
        self.risk.reset_session(self.initial_balance)

    # -- accounting helpers -------------------------------------------------
    def _equity_now(self) -> float:
        return self.balance + sum(p.net_unrealised() for p in self.positions.values())

    def _used_margin(self) -> float:
        return sum(p.margin for p in self.positions.values())

    def _effective_mark(self, decision: dict[str, Any], side: str) -> float:
        if side == "LONG":
            return safe_float(decision.get("bid"), decision.get("last_price"))
        return safe_float(decision.get("ask"), decision.get("last_price"))

    def _size_margin(self, decision: dict[str, Any]) -> float:
        """Volatility-targeted margin: risk a fixed slice of equity at the SL."""
        entry = max(safe_float(decision.get("entry"), decision.get("last_price")), 1e-9)
        stop_distance = max(safe_float(decision.get("stop_distance")), entry * 0.0008)
        stop_pct = stop_distance / entry
        equity = max(self._equity_now(), self.initial_balance * 0.2)
        risk_amount = equity * (self.cfg.risk_per_trade_pct / 100.0) * self.risk.sizing_multiplier()
        margin = risk_amount / (self.leverage * max(stop_pct, 1e-6))
        gross_cap = self.balance * 0.85 - self._used_margin()
        cap = min(self.cfg.max_margin_per_trade, max(gross_cap, 0.0))
        floor = min(self.cfg.min_margin_per_trade, max(cap, 1.0))
        return round(clamp(margin, floor, max(cap, floor)), 2)

    def _open(
        self,
        decision: dict[str, Any],
        heartbeat: int,
        *,
        persist_journal: bool = True,
        bootstrap: bool = False,
        margin_override: float | None = None,
    ) -> bool:
        side = str(decision["side"])
        gate = decision.get("gate")
        if not bootstrap and isinstance(gate, dict) and not gate.get("allowed"):
            return False
        margin = (
            float(margin_override)
            if margin_override
            else self._size_margin(decision)
        )
        available = self.balance - self._used_margin()
        if margin > available:
            if not bootstrap:
                return False
            margin = max(min(margin, available), 1.0)
        entry = safe_float(decision["ask"] if side == "LONG" else decision["bid"], decision["entry"])
        mark = self._effective_mark(decision, side)
        notional = margin * self.leverage
        qty = notional / max(entry, 1e-12)
        entry_fee = notional * self.fee_rate
        spread_cost = abs(entry - safe_float(decision["last_price"])) * qty
        self.balance -= entry_fee + spread_cost
        self.fees_paid += entry_fee + spread_cost
        position = Position(
            symbol=str(decision["symbol"]),
            side=side,
            margin=margin,
            leverage=self.leverage,
            notional=notional,
            qty=qty,
            entry=entry,
            mark=mark,
            tp=safe_float(decision["tp"]),
            sl=safe_float(decision["sl"]),
            stop_distance=safe_float(decision["stop_distance"]),
            confidence=safe_float(decision["confidence"]),
            quality=safe_float(decision["quality"]),
            regime=str(decision["regime"]),
            spread_bps=safe_float(decision["spread_bps"]),
            entry_fee=entry_fee,
            entry_spread_cost=spread_cost,
            opened_at=utc_now().isoformat(),
            heartbeat_at_open=int(heartbeat),
            best_mark=mark,
        )
        if self.memory and persist_journal:
            position.journal_id = self.memory.record_open(position, decision)
        self.positions[position.symbol] = position
        self.total_entries += 1
        return True

    def _close(
        self,
        symbol: str,
        reason: str,
        mark: float | None = None,
        *,
        persist_journal: bool = True,
    ) -> None:
        position = self.positions.get(symbol)
        if not position:
            return
        if mark is not None and mark > 0:
            position.mark = float(mark)
        exit_fee = abs(position.mark * position.qty) * self.fee_rate
        net_remaining = position.gross_pnl() - exit_fee
        self.balance += net_remaining
        self.realized_gross += position.gross_pnl()
        self.fees_paid += exit_fee
        position.status = "CLOSED"
        position.last_reason = reason
        record = position.to_dict()
        net_trade = (
            position.gross_pnl()
            - exit_fee
            - position.entry_fee
            - position.entry_spread_cost
            + position.realized_partial
        )
        record.update(
            {
                "exit_reason": reason,
                "realized_pnl": serialise_number(net_trade, 2),
                "risk_usd": serialise_number(position.risk_usd, 2),
                "closed_at": utc_now().isoformat(),
            }
        )
        self.closed.append(record)
        if self.memory and persist_journal:
            self.memory.record_close(
                position.journal_id,
                position,
                gross_pnl=position.gross_pnl(),
                exit_fee=exit_fee,
                net_pnl=net_trade,
                reason=reason,
            )
        del self.positions[symbol]

    def _bank_partial(self, position: Position, trigger: str = "+1R") -> None:
        """Take profits on part of the book and walk the stop to safety."""
        fraction = clamp(self.cfg.partial_fraction, 0.1, 0.9)
        close_qty = position.qty * fraction
        if close_qty <= 0:
            return
        gross = (position.mark - position.entry) * close_qty * position.direction
        fee = abs(position.mark * close_qty) * self.fee_rate
        net = gross - fee
        self.balance += net
        self.realized_gross += gross
        self.fees_paid += fee
        position.qty -= close_qty
        position.notional *= (1.0 - fraction)
        position.realized_partial += net
        position.partial_taken = True
        buffer = position.initial_stop_distance * self.cfg.breakeven_buffer_r
        be = position.entry + buffer * position.direction
        if position.side == "LONG":
            position.sl = max(position.sl, be)
        else:
            position.sl = min(position.sl, be)
        self.risk.log(
            "partial",
            f"{position.symbol}: رسیدن به {trigger} → واریز {fraction * 100:.0f}٪ سود "
            f"(${net:+.2f}) و انتقال SL به سربه‌سر+",
        )

    def _manage(self, symbol: str, decision: dict[str, Any]) -> str | None:
        """Mark-to-market plus scalper exit doctrine. Returns exit reason."""
        position = self.positions.get(symbol)
        if not position:
            return None
        mark = self._effective_mark(decision, position.side)
        if mark <= 0:
            return None
        position.mark = mark
        position.best_mark = (
            max(position.best_mark, mark)
            if position.side == "LONG"
            else min(position.best_mark or mark, mark)
        )
        initial_stop = max(position.initial_stop_distance, 1e-12)
        move_r = (mark - position.entry) * position.direction / initial_stop
        position.max_r = max(position.max_r, move_r)

        if not position.partial_taken and move_r >= self.cfg.partial_at_r:
            self._bank_partial(position, f"+{move_r:.1f}R")

        atr_value = max(safe_float(decision.get("atr"), initial_stop), initial_stop * 0.8)
        if position.partial_taken:
            # Chandelier trail on the runner once risk is off the table.
            distance = self.cfg.chandelier_atr_mult * atr_value
            if position.side == "LONG":
                candidate = position.best_mark - distance
                if candidate > position.sl:
                    position.sl = candidate
            else:
                candidate = position.best_mark + distance
                if candidate < position.sl:
                    position.sl = candidate

        age_min = position.holding_minutes
        if age_min > self.cfg.max_hold_minutes:
            return "پایان مهلت اسکالپ / زمان"
        if age_min > self.cfg.stall_check_minutes and position.max_r < self.cfg.stall_min_r:
            return "رکود مومنتوم / stall"
        return None

    def update(
        self,
        decisions: list[dict[str, Any]],
        heartbeat: int,
        *,
        persist_journal: bool = True,
        bootstrap: bool = False,
    ) -> None:
        cfg = self.cfg
        self.total_scans += 1
        by_symbol = {str(item["symbol"]): item for item in decisions}

        equity = self._equity_now()
        self.risk.update_equity(equity)
        self.risk.begin_scan(equity)

        # Phase A — manage survivors and enforce hard exits.
        for symbol in list(self.positions):
            decision = by_symbol.get(symbol)
            if decision is None:
                self._close(symbol, "خروج از پوشش اسکن", persist_journal=persist_journal)
                continue
            reason = self._manage(symbol, decision)
            if reason:
                self._close(
                    symbol, reason, self.positions[symbol].mark, persist_journal=persist_journal
                )
                continue
            position = self.positions.get(symbol)
            if not position:
                continue
            # The last quote is the only executable mark. Historical candle
            # extremes can predate the position and must not trigger exits.
            mark = position.mark
            hit_stop = mark <= position.sl if position.side == "LONG" else mark >= position.sl
            hit_target = mark >= position.tp if position.side == "LONG" else mark <= position.tp
            if hit_stop:
                self._close(
                    symbol,
                    "حد ضرر / nociceptor",
                    position.sl,
                    persist_journal=persist_journal,
                )
            elif hit_target:
                self._close(
                    symbol,
                    "حد سود / reward",
                    position.tp,
                    persist_journal=persist_journal,
                )

        # Phase B — build the target book with anti-churn hysteresis.
        ranked = [
            item
            for item in decisions
            if safe_float(item.get("quality")) > 0 and str(item.get("symbol"))
        ]
        ranked.sort(
            key=lambda item: (safe_float(item.get("quality")), safe_float(item.get("confidence"))),
            reverse=True,
        )
        selected_symbols = {str(item["symbol"]) for item in ranked[: self.slots]}
        threshold_quality = (
            safe_float(ranked[min(self.slots, len(ranked)) - 1].get("quality"))
            if len(ranked) >= self.slots
            else (safe_float(ranked[-1].get("quality")) if ranked else 0.0)
        )

        kept_symbols: list[str] = []
        for symbol in list(self.positions):
            decision = by_symbol.get(symbol)
            position = self.positions.get(symbol)
            if decision is None or position is None:
                continue
            if position.side != str(decision["side"]):
                self._close(symbol, "تغییر ژن جهت / flip", persist_journal=persist_journal)
                continue
            protected = (
                symbol in selected_symbols
                or position.quality + cfg.rotation_hysteresis >= threshold_quality
            )
            if not protected:
                self._close(symbol, "چرخش هوشمند / hysteresis", persist_journal=persist_journal)
                continue
            kept_symbols.append(symbol)
            # Refresh conviction; stops may only tighten, never loosen.
            position.confidence = safe_float(decision["confidence"], position.confidence)
            position.quality = safe_float(decision["quality"], position.quality)
            position.regime = str(decision["regime"])
            new_tp = safe_float(decision["tp"], position.tp)
            distance_tp = abs(new_tp - position.entry)
            old_distance = abs(position.tp - position.entry)
            if distance_tp < old_distance:
                position.tp = new_tp
            proposed_sl = safe_float(decision["sl"], position.sl)
            if position.side == "LONG":
                position.sl = max(position.sl, proposed_sl)
            else:
                position.sl = min(position.sl, proposed_sl)

        trading_allowed, _halt_reason = (True, "") if bootstrap else self.risk.trade_allowed()
        direction_counts = {"LONG": 0, "SHORT": 0}
        for symbol in kept_symbols:
            direction_counts[self.positions[symbol].side] += 1

        opened_symbols: set[str] = set()
        for decision in ranked:
            symbol = str(decision["symbol"])
            if len(kept_symbols) + len(opened_symbols) >= self.slots:
                break
            if symbol in kept_symbols or symbol in opened_symbols:
                continue
            side = str(decision["side"])
            market_ok = bool(
                decision.get("market_long_ok", True)
                if side == "LONG"
                else decision.get("market_short_ok", True)
            )
            gate = evaluate_entry_gate(
                decision,
                cfg,
                market_allows=market_ok,
                direction_count=direction_counts[side],
            )
            decision["gate"] = gate
            if not trading_allowed:
                continue
            if not bootstrap and not gate["allowed"]:
                continue
            if self._open(
                decision, heartbeat, persist_journal=persist_journal, bootstrap=bootstrap
            ):
                opened_symbols.add(symbol)
                direction_counts[side] += 1

        # Attach verdicts to the remaining candidates so the UI can audit why
        # the sniper did not shoot.
        for decision in decisions:
            if "gate" not in decision:
                side = str(decision["side"])
                market_ok = bool(
                    decision.get("market_long_ok", True)
                    if side == "LONG"
                    else decision.get("market_short_ok", True)
                )
                decision["gate"] = evaluate_entry_gate(
                    decision,
                    cfg,
                    market_allows=market_ok,
                    direction_count=direction_counts.get(side, 0),
                )

        self._record_equity()

    def _record_equity(self) -> None:
        unrealised = sum(position.net_unrealised() for position in self.positions.values())
        equity = self.balance + unrealised
        self.equity_curve.append(
            {
                "ts": utc_now().isoformat(),
                "equity": serialise_number(equity, 4),
                "balance": serialise_number(self.balance, 4),
                "unrealised": serialise_number(unrealised, 4),
            }
        )
        self.equity_curve = self.equity_curve[-180:]

    # -- analytics ----------------------------------------------------------
    def analytics(self) -> dict[str, Any]:
        pnls = [safe_float(item.get("realized_pnl")) for item in self.closed]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_win / gross_loss if gross_loss > 0 else (99.0 if gross_win else 0.0)
        expectancy = float(np.mean(pnls)) if pnls else 0.0
        total_risk = sum(safe_float(item.get("risk_usd")) for item in self.closed)
        expectancy_r = sum(pnls) / total_risk if total_risk > 0 else 0.0
        curve = [safe_float(item.get("equity")) for item in self.equity_curve]
        peak, max_dd = 0.0, 0.0
        for value in curve:
            peak = max(peak, value)
            if peak > 0:
                max_dd = max(max_dd, (peak - value) / peak * 100.0)
        rets = np.diff(curve) / np.array(curve[:-1]) if len(curve) > 2 else np.array([])
        sharpe = 0.0
        if rets.size > 4 and float(np.std(rets)) > 0:
            sharpe = float(np.mean(rets) / np.std(rets) * math.sqrt(len(rets)))
        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0
        payoff = abs(avg_win / avg_loss) if avg_loss else 0.0
        streak, worst_streak = 0, 0
        for pnl in pnls[::-1]:
            if pnl < 0:
                streak += 1
                worst_streak = max(worst_streak, streak)
            else:
                break
        return {
            "profit_factor": serialise_number(min(profit_factor, 99.0), 2),
            "expectancy_usd": serialise_number(expectancy, 3),
            "expectancy_r": serialise_number(expectancy_r, 3),
            "max_drawdown_pct": serialise_number(max_dd, 2),
            "sharpe": serialise_number(sharpe, 2),
            "avg_win": serialise_number(avg_win, 2),
            "avg_loss": serialise_number(avg_loss, 2),
            "payoff_ratio": serialise_number(payoff, 2),
            "current_loss_streak": streak,
            "worst_loss_streak": worst_streak,
        }

    def summary(self) -> dict[str, Any]:
        unrealised = sum(position.net_unrealised() for position in self.positions.values())
        equity = self.balance + unrealised
        used_margin = sum(position.margin for position in self.positions.values())
        result = {
            "initial_balance": self.initial_balance,
            "balance": serialise_number(self.balance, 2),
            "equity": serialise_number(equity, 2),
            "unrealised": serialise_number(unrealised, 2),
            "realized": serialise_number(self.balance - self.initial_balance, 2),
            "closed_net": serialise_number(self.realized_gross - self.fees_paid, 2),
            "fees_paid": serialise_number(self.fees_paid, 2),
            "free_margin": serialise_number(max(self.balance - used_margin, 0.0), 2),
            "used_margin": serialise_number(used_margin, 2),
            "slots": self.slots,
            "leverage": self.leverage,
            "open_positions": len(self.positions),
            "closed_trades": len(self.closed),
            "entries": self.total_entries,
            "win_rate": self._win_rate(),
        }
        result.update({f"stat_{key}": value for key, value in self.analytics().items()})
        return result

    def _win_rate(self) -> float:
        if not self.closed:
            return 0.0
        wins = sum(1 for item in self.closed if safe_float(item.get("realized_pnl")) > 0)
        return wins / len(self.closed) * 100.0

    def positions_view(self) -> list[dict[str, Any]]:
        return [position.to_dict() for position in self.positions.values()]


class BioTradingEngine:
    """Orchestrates data, cognition, durable memory and the demo portfolio."""

    def __init__(self, db_path: str | os.PathLike[str] | None = None) -> None:
        self.client = BybitPublicClient()
        self.synthetic = SyntheticMarket()
        self.memory = BioMemory(db_path)
        self.organism = UltimateBioOrganism(memory=self.memory)
        self.portfolio = DemoPortfolio(memory=self.memory)
        self.candles: dict[str, pd.DataFrame] = {}
        self.candidates: list[dict[str, Any]] = []
        self.mode = "simulation"
        self.last_scan_at: datetime | None = None
        self.last_error = ""
        self.scan_id = 0
        self._lock = threading.RLock()
        self._snapshot_cache: dict[str, Any] | None = None
        self._last_learned_closed = 0
        # A synthetic first frame gives the UI an immediate, useful state before
        # the first network request completes.
        self.scan(force=True, prefer_live=False, persist_journal=False)

    def reset(self) -> None:
        with self._lock:
            # Reset the active session while deliberately preserving the
            # durable genome and its mutation history.
            self.organism = UltimateBioOrganism(memory=self.memory)
            self.portfolio.reset()
            self.candles.clear()
            self.candidates.clear()
            self.last_scan_at = None
            self.last_error = ""
            self.scan_id = 0
            self._snapshot_cache = None
            self._last_learned_closed = 0
            self.scan(force=True, prefer_live=False, persist_journal=False)

    def scan(
        self,
        force: bool = False,
        prefer_live: bool = True,
        *,
        persist_journal: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            # Dash can trigger on both an interval and a button.  A short cache
            # avoids duplicate public API calls if two browser events coincide.
            if (
                not force
                and self.last_scan_at is not None
                and (utc_now() - self.last_scan_at).total_seconds() < 8
                and self._snapshot_cache
            ):
                return self._snapshot_cache

            previous_mode = self.mode
            tickers: pd.DataFrame
            candles: dict[str, pd.DataFrame]
            mode = "simulation"
            if prefer_live and os.getenv("BIO_TRADER_OFFLINE", "0").lower() not in {"1", "true", "yes"}:
                tickers, candles, mode = self.client.scan_market(DEFAULT_UNIVERSE, DEFAULT_INTERVAL)
            else:
                tickers, candles, mode = pd.DataFrame(), {}, "offline"
            if tickers.empty or len(candles) < 5:
                tickers, candles, mode = self.synthetic.scan_market(DEFAULT_UNIVERSE, DEFAULT_INTERVAL)
                self.last_error = self.client.last_error
            else:
                self.last_error = ""
            # The constructor seeds the UI with synthetic positions. When the
            # first real public snapshot arrives, those positions must not be
            # force-closed against unrelated exchange prices.
            if self.scan_id == 1 and previous_mode == "simulation" and mode == "live":
                self.portfolio.reset()
            self.mode = mode
            self.candles = candles

            ticker_records = {
                str(row["symbol"]): row.to_dict() for _, row in tickers.iterrows()
            }

            # Cross-sectional context: higher-timeframe confluence plus
            # momentum/volatility percentile ranks across the universe.
            htf_map: dict[str, dict[str, float]] = {}
            momentum_raw: dict[str, float] = {}
            vol_raw: dict[str, float] = {}
            for symbol, frame in candles.items():
                htf_map[symbol] = {
                    "trend_15": htf_trend(frame, "15min"),
                    "trend_60": htf_trend(frame, "1h"),
                }
                close = frame["close"].astype(float)
                momentum_raw[symbol] = safe_float(
                    close.iloc[-1] / max(close.iloc[-13], 1e-12) - 1.0
                )
                atr_value = safe_float(atr(frame, 14).iloc[-1])
                vol_raw[symbol] = atr_value / max(safe_float(close.iloc[-1]), 1e-12)

            def _percentile_ranks(raw: dict[str, float]) -> dict[str, float]:
                if not raw:
                    return {}
                ordered = sorted(raw.items(), key=lambda kv: kv[1])
                count = max(len(ordered) - 1, 1)
                return {symbol: index / count for index, (symbol, _) in enumerate(ordered)}

            momentum_rank_map = _percentile_ranks(momentum_raw)
            vol_rank_map = _percentile_ranks(vol_raw)

            observations: list[tuple[str, dict[str, Any]]] = []
            for symbol, frame in candles.items():
                ticker = ticker_records.get(symbol, {})
                # Public orderbook calls are reserved for the liquid front of
                # the cohort; synthetic data uses a momentum proxy.
                imbalance = 0.0
                if mode == "live" and len(observations) < 5:
                    imbalance = self.client.get_orderbook_imbalance(symbol)
                else:
                    imbalance = _normalise(linear_slope(frame["close"].tail(12), 12), frame["close"].iloc[-1] * 0.0015)
                features = extract_features(
                    frame,
                    ticker,
                    imbalance,
                    htf=htf_map.get(symbol),
                    ranks={
                        "momentum_rank": momentum_rank_map.get(symbol, 0.5),
                        "vol_rank": vol_rank_map.get(symbol, 0.5),
                    },
                )
                if features:
                    observations.append((symbol, features))

            decisions = self.organism.scan(observations)

            # Market regime filter from the bellwether: when BTC is in stress
            # or trending hard against a direction, altcoin exposure in that
            # direction is blocked. This kills the classic correlation trap.
            btc_features = next(
                (features for symbol, features in observations if symbol == "BTCUSDT"), None
            )
            market_long_ok = True
            market_short_ok = True
            if btc_features is not None:
                btc_trend = safe_float(btc_features.get("trend"))
                btc_stress = str(btc_features.get("regime")) == "STRESS"
                market_long_ok = (not btc_stress) and btc_trend > -0.30
                market_short_ok = (not btc_stress) and btc_trend < 0.30
            for decision in decisions:
                decision["market_long_ok"] = market_long_ok
                decision["market_short_ok"] = market_short_ok

            bootstrap = self._last_learned_closed == 0 and self.scan_id <= 1
            # Ticker rows not present in candles are ignored by design.
            self.portfolio.update(
                decisions,
                int(self.organism.state["heartbeat"]),
                persist_journal=persist_journal,
                bootstrap=bootstrap,
            )
            new_closed = self.portfolio.closed[self._last_learned_closed :]
            for trade in new_closed:
                pnl = safe_float(trade.get("realized_pnl"))
                self.organism.learn(
                    pnl,
                    trigger=f"{trade.get('symbol', 'UNKNOWN')}:{trade.get('exit_reason', 'close')}",
                )
                if persist_journal:
                    self.portfolio.risk.on_trade_closed(pnl)
            if new_closed and persist_journal:
                self.organism.learn_stats(new_closed)
            self._last_learned_closed = len(self.portfolio.closed)
            self.candidates = decisions
            self.last_scan_at = utc_now()
            self.scan_id += 1
            self._snapshot_cache = self._build_snapshot()
            return self._snapshot_cache

    def _build_snapshot(self) -> dict[str, Any]:
        summary = self.portfolio.summary()
        snapshot = {
            "scan_id": self.scan_id,
            "mode": self.mode,
            "status": "متصل به بازار عمومی" if self.mode == "live" else "حالت شبیه‌سازی خودکار",
            "last_error": self.last_error,
            "last_scan": self.last_scan_at.isoformat() if self.last_scan_at else None,
            "summary": summary,
            "organism": {
                "state": dict(self.organism.state),
                "organs": self.organism.organs(),
                "genome": self.organism.genome_view(),
                "cortex": self.organism.cortex_view(),
            },
            "candidates": [
                {
                    key: (
                        serialise_number(value, 8)
                        if isinstance(value, (int, float, np.floating))
                        else value
                    )
                    for key, value in item.items()
                    if key not in {"senses"}
                }
                | {"senses": {k: serialise_number(v, 4) for k, v in item.get("senses", {}).items()}}
                for item in self.candidates
            ],
            "positions": self.portfolio.positions_view(),
            "closed": self.portfolio.closed[-20:],
            "equity_curve": self.portfolio.equity_curve[-90:],
            "risk": self.portfolio.risk.snapshot_view(),
            "journal": self.memory.journal(60),
            "mutation_history": self.memory.mutation_history(30),
            "memory": self.memory.memory_summary(),
        }
        return snapshot

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            if not self._snapshot_cache:
                return self.scan(force=True, prefer_live=False, persist_journal=False)
            return self._snapshot_cache

    def candles_for(self, symbol: str | None) -> pd.DataFrame:
        with self._lock:
            if symbol and symbol in self.candles:
                return self.candles[symbol]
            if self.candidates:
                return self.candles.get(str(self.candidates[0]["symbol"]), pd.DataFrame())
            return pd.DataFrame()

    def journal(self, limit: int = 60) -> list[dict[str, Any]]:
        return self.memory.journal(limit)

    def mutation_history(self, limit: int = 30) -> list[dict[str, Any]]:
        return self.memory.mutation_history(limit)


__all__ = [
    "BioTradingEngine",
    "BybitPublicClient",
    "DemoPortfolio",
    "BioOrganism",
    "UltimateBioOrganism",
    "NeuralCortex",
    "RiskConfig",
    "RiskManager",
    "evaluate_entry_gate",
    "extract_features",
    "TAKER_FEE_RATE",
]
