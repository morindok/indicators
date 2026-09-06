"""BioTrader 2500: a resilient, public-data, demo trading organism.

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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

import numpy as np
import pandas as pd
import requests


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
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(tickers)))) as pool:
            jobs = {
                pool.submit(self.get_klines, symbol, interval, 180): symbol
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
        candles = {symbol: self.candles(symbol, 180) for symbol in tickers["symbol"]}
        return tickers.reset_index(drop=True), candles, "simulation"


def extract_features(
    frame: pd.DataFrame, ticker: dict[str, Any], book_imbalance: float = 0.0
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
    # Signed senses in [-1, 1].
    momentum = _normalise(0.50 * ret_3 + 0.32 * ret_12 + 0.18 * ret_36, 0.025)
    trend = _normalise(0.65 * trend_gap + 0.35 * slope_pct * 10, 0.012)
    volume_impulse = _normalise(volume_z, 2.5)
    volatility = clamp(atr_pct / 0.018)
    rsi_signal = _normalise(float(rsi_series.iloc[-1] - 50.0), 25.0)
    multi_tf_agreement = float(np.sign(ret_3) == np.sign(ret_12)) * 0.5 + float(np.sign(ret_12) == np.sign(ret_36)) * 0.5
    signed_agreement = (
        (np.sign(ret_3) + np.sign(ret_12) + np.sign(ret_36)) / 3.0
    ) * (0.45 + 0.55 * multi_tf_agreement)
    liquidity = clamp(math.log1p(max(safe_float(ticker.get("turnover_24h")), 0.0)) / 22.0)
    pressure = clamp(book_imbalance, -1.0, 1.0)
    change_24h = safe_float(ticker.get("change_24h"))
    regime = "TREND" if abs(trend) > 0.28 and multi_tf_agreement > 0.5 else "RANGE"
    if volatility > 0.82:
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

    @property
    def direction(self) -> int:
        return 1 if self.side == "LONG" else -1

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
            "pnl": serialise_number(self.net_unrealised(), 2),
            "pnl_pct_margin": serialise_number(self.net_unrealised() / max(self.margin, 1e-9) * 100, 2),
            "opened_at": self.opened_at,
            "heartbeat_at_open": self.heartbeat_at_open,
            "status": self.status,
            "last_reason": self.last_reason,
        }


class DemoPortfolio:
    """Five-slot isolated-margin paper portfolio with fee and spread accounting."""

    def __init__(
        self,
        initial_balance: float = DEFAULT_MARGIN,
        leverage: int = DEFAULT_LEVERAGE,
        slots: int = DEFAULT_SLOTS,
        fee_rate: float = TAKER_FEE_RATE,
    ) -> None:
        self.initial_balance = float(initial_balance)
        self.balance = float(initial_balance)
        self.leverage = int(leverage)
        self.slots = int(slots)
        self.margin_per_slot = self.initial_balance / self.slots
        self.fee_rate = float(fee_rate)
        self.positions: dict[str, Position] = {}
        self.closed: list[dict[str, Any]] = []
        self.equity_curve: list[dict[str, Any]] = []
        self.total_scans = 0
        self.total_entries = 0
        self.realized_gross = 0.0
        self.fees_paid = 0.0

    def reset(self) -> None:
        self.balance = self.initial_balance
        self.positions.clear()
        self.closed.clear()
        self.equity_curve.clear()
        self.total_scans = 0
        self.total_entries = 0
        self.realized_gross = 0.0
        self.fees_paid = 0.0

    def _effective_mark(self, decision: dict[str, Any], side: str) -> float:
        if side == "LONG":
            return safe_float(decision.get("bid"), decision.get("last_price"))
        return safe_float(decision.get("ask"), decision.get("last_price"))

    def _open(self, decision: dict[str, Any], heartbeat: int) -> None:
        side = str(decision["side"])
        entry = safe_float(decision["ask"] if side == "LONG" else decision["bid"], decision["entry"])
        mark = self._effective_mark(decision, side)
        notional = self.margin_per_slot * self.leverage
        qty = notional / max(entry, 1e-12)
        entry_fee = notional * self.fee_rate
        spread_cost = abs(entry - safe_float(decision["last_price"])) * qty
        self.balance -= entry_fee + spread_cost
        self.fees_paid += entry_fee + spread_cost
        position = Position(
            symbol=str(decision["symbol"]),
            side=side,
            margin=self.margin_per_slot,
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
        self.positions[position.symbol] = position
        self.total_entries += 1

    def _close(self, symbol: str, reason: str, mark: float | None = None) -> None:
        position = self.positions.get(symbol)
        if not position:
            return
        if mark is not None and mark > 0:
            position.mark = float(mark)
        exit_fee = abs(position.mark * position.qty) * self.fee_rate
        net = position.gross_pnl() - exit_fee
        self.balance += net
        self.realized_gross += position.gross_pnl()
        self.fees_paid += exit_fee
        position.status = "CLOSED"
        position.last_reason = reason
        record = position.to_dict()
        net_trade = position.gross_pnl() - exit_fee - position.entry_fee - position.entry_spread_cost
        record.update(
            {
                "exit_reason": reason,
                "realized_pnl": serialise_number(net_trade, 2),
                "closed_at": utc_now().isoformat(),
            }
        )
        self.closed.append(record)
        del self.positions[symbol]

    def _trail(self, position: Position, decision: dict[str, Any]) -> None:
        mark = self._effective_mark(decision, position.side)
        if mark <= 0:
            return
        position.mark = mark
        position.best_mark = (
            max(position.best_mark, mark) if position.side == "LONG" else min(position.best_mark or mark, mark)
        )
        # A one-R move buys a break-even stop, reducing catastrophic tail risk.
        move = (mark - position.entry) * position.direction
        if move >= position.stop_distance:
            if position.side == "LONG":
                position.sl = max(position.sl, position.entry + position.stop_distance * 0.10)
            else:
                position.sl = min(position.sl, position.entry - position.stop_distance * 0.10)

    def update(self, decisions: list[dict[str, Any]], heartbeat: int) -> None:
        self.total_scans += 1
        by_symbol = {str(item["symbol"]): item for item in decisions}
        # Mark existing positions and enforce TP/SL before rotating the book.
        for symbol in list(self.positions):
            decision = by_symbol.get(symbol)
            if not decision:
                continue
            self._trail(self.positions[symbol], decision)
            position = self.positions.get(symbol)
            if not position:
                continue
            # The last quote is the only executable mark. Historical candle
            # extremes can predate the position and must not trigger exits.
            mark = position.mark
            hit_stop = mark <= position.sl if position.side == "LONG" else mark >= position.sl
            hit_target = mark >= position.tp if position.side == "LONG" else mark <= position.tp
            if hit_stop:
                self._close(symbol, "حد ضرر / nociceptor", position.sl)
            elif hit_target:
                self._close(symbol, "حد سود / reward", position.tp)

        ranked = [item for item in decisions if item.get("quality", 0) > 0]
        selected = ranked[: self.slots]
        selected_symbols = {str(item["symbol"]) for item in selected}

        # Keep exactly the current top-five cohort; this makes the demo easy to
        # audit and ensures margin is always split equally among five symbols.
        for symbol in list(self.positions):
            if symbol not in selected_symbols:
                self._close(symbol, "چرخش اسکن / rotation")

        for decision in selected:
            symbol = str(decision["symbol"])
            existing = self.positions.get(symbol)
            if existing and existing.side == decision["side"]:
                existing.confidence = safe_float(decision["confidence"])
                existing.quality = safe_float(decision["quality"])
                existing.regime = str(decision["regime"])
                existing.tp = safe_float(decision["tp"], existing.tp)
                proposed_sl = safe_float(decision["sl"], existing.sl)
                # Never loosen a protective stop after it has trailed into
                # profit. A fresh signal may tighten risk, not widen it.
                if existing.side == "LONG":
                    existing.sl = max(existing.sl, proposed_sl)
                else:
                    existing.sl = min(existing.sl, proposed_sl)
                continue
            if existing:
                self._close(symbol, "تغییر ژن جهت / flip")
            if len(self.positions) < self.slots:
                self._open(decision, heartbeat)

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

    def summary(self) -> dict[str, Any]:
        unrealised = sum(position.net_unrealised() for position in self.positions.values())
        equity = self.balance + unrealised
        used_margin = sum(position.margin for position in self.positions.values())
        return {
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

    def _win_rate(self) -> float:
        if not self.closed:
            return 0.0
        wins = sum(1 for item in self.closed if safe_float(item.get("realized_pnl")) > 0)
        return wins / len(self.closed) * 100.0

    def positions_view(self) -> list[dict[str, Any]]:
        return [position.to_dict() for position in self.positions.values()]


class BioTradingEngine:
    """Orchestrates data, organism cognition and the demo portfolio."""

    def __init__(self) -> None:
        self.client = BybitPublicClient()
        self.synthetic = SyntheticMarket()
        self.organism = BioOrganism()
        self.portfolio = DemoPortfolio()
        self.candles: dict[str, pd.DataFrame] = {}
        self.candidates: list[dict[str, Any]] = []
        self.mode = "simulation"
        self.last_scan_at: datetime | None = None
        self.last_error = ""
        self.scan_id = 0
        self._lock = threading.RLock()
        self._snapshot_cache: dict[str, Any] | None = None
        # A synthetic first frame gives the UI an immediate, useful state before
        # the first network request completes.
        self.scan(force=True, prefer_live=False)

    def reset(self) -> None:
        with self._lock:
            self.organism = BioOrganism()
            self.portfolio.reset()
            self.candles.clear()
            self.candidates.clear()
            self.last_scan_at = None
            self.last_error = ""
            self.scan_id = 0
            self._snapshot_cache = None
            self.scan(force=True, prefer_live=False)

    def scan(self, force: bool = False, prefer_live: bool = True) -> dict[str, Any]:
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
                features = extract_features(frame, ticker, imbalance)
                if features:
                    observations.append((symbol, features))

            decisions = self.organism.scan(observations)
            # Ticker rows not present in candles are ignored by design.
            self.portfolio.update(decisions, int(self.organism.state["heartbeat"]))
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
        }
        return snapshot

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            if not self._snapshot_cache:
                return self.scan(force=True, prefer_live=False)
            return self._snapshot_cache

    def candles_for(self, symbol: str | None) -> pd.DataFrame:
        with self._lock:
            if symbol and symbol in self.candles:
                return self.candles[symbol]
            if self.candidates:
                return self.candles.get(str(self.candidates[0]["symbol"]), pd.DataFrame())
            return pd.DataFrame()


__all__ = [
    "BioTradingEngine",
    "BybitPublicClient",
    "DemoPortfolio",
    "BioOrganism",
    "extract_features",
    "TAKER_FEE_RATE",
]
