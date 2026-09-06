# -*- coding: utf-8 -*-
"""
🔮 Nostradamus Digital Organism — Backtest Edition
پیش‌بینی با قلب فیبوناچی + Backtest Walk-Forward بدون Lookahead
"""

import os
import math
import random
import time
import statistics
import threading
import requests
import pandas as pd
import numpy as np
from collections import deque, defaultdict
from datetime import datetime, timedelta

from dash import Dash, dcc, html, Input, Output, State, no_update, ctx
import dash_bootstrap_components as dbc
import plotly.graph_objects as go


# ============================================================
# Utilities
# ============================================================

def clamp(v, lo=0.0, hi=1.0):
    try:
        if v is None: return lo
        v = float(v)
        if math.isnan(v) or math.isinf(v): return lo
        return max(lo, min(hi, v))
    except Exception:
        return lo

def clamp100(v):
    return clamp(v, 0.0, 100.0)

def now_hms():
    return datetime.now().strftime("%H:%M:%S")


# ============================================================
# Bybit stable connection
# ============================================================

REST_CANDIDATES = [
    "https://api.bybit.com",
    "https://api.bytick.com",
    "https://api.bybit.kz",
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.bybit.com/",
})
_ACTIVE_REST_BASE = {"url": None}


def bybit_get(path, params, timeout=10):
    cands = ([_ACTIVE_REST_BASE["url"]] if _ACTIVE_REST_BASE["url"] else []) + \
            [b for b in REST_CANDIDATES if b != _ACTIVE_REST_BASE["url"]]
    for base in cands:
        try:
            r = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code in (403, 451, 429):
                continue
            r.raise_for_status()
            d = r.json()
            if d.get("retCode") == 0:
                _ACTIVE_REST_BASE["url"] = base
                return d
        except Exception:
            continue
    return None


def get_klines(symbol, interval, category="linear", limit=500):
    try:
        d = bybit_get("/v5/market/kline", {
            "category": category, "symbol": symbol,
            "interval": interval, "limit": limit,
        })
        if not d or "list" not in (d.get("result") or {}):
            return pd.DataFrame()
        lst = d["result"]["list"]
        if not lst:
            return pd.DataFrame()
        df = pd.DataFrame(lst, columns=[
            "ts", "open", "high", "low", "close", "volume", "turnover"
        ])
        df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
        for c in ["open", "high", "low", "close", "volume", "turnover"]:
            df[c] = df[c].astype(float)
        return df.sort_values("ts").reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


# ============================================================
# Market Perception
# ============================================================

class MarketPerception:
    @staticmethod
    def ema(values, period):
        try:
            if len(values) < period:
                return values[-1] if len(values) > 0 else 0.0
            k = 2.0 / (period + 1)
            ema = values[0]
            for v in values[1:]:
                ema = v * k + ema * (1 - k)
            return ema
        except Exception:
            return 0.0

    @staticmethod
    def rsi(closes, period=14):
        try:
            if len(closes) < period + 1: return 50.0
            deltas = np.diff(closes)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            avg_gain = np.mean(gains[-period:])
            avg_loss = np.mean(losses[-period:])
            if avg_loss == 0: return 100.0
            rs = avg_gain / avg_loss
            return 100.0 - (100.0 / (1.0 + rs))
        except Exception:
            return 50.0

    @staticmethod
    def atr(highs, lows, closes, period=14):
        try:
            if len(closes) < period + 1: return 0.0
            trs = []
            for i in range(1, len(closes)):
                tr = max(highs[i] - lows[i],
                         abs(highs[i] - closes[i-1]),
                         abs(lows[i] - closes[i-1]))
                trs.append(tr)
            return float(np.mean(trs[-period:])) if len(trs) >= period else (
                float(np.mean(trs)) if trs else 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def bollinger(closes, period=20, num_std=2):
        try:
            if len(closes) < period:
                return closes[-1], closes[-1], closes[-1]
            sma = float(np.mean(closes[-period:]))
            std = float(np.std(closes[-period:]))
            return sma, sma + num_std * std, sma - num_std * std
        except Exception:
            return closes[-1], closes[-1], closes[-1]

    @staticmethod
    def extract(df):
        try:
            if df.empty or len(df) < 30: return None

            closes = df["close"].values
            opens = df["open"].values
            highs = df["high"].values
            lows = df["low"].values
            volumes = df["volume"].values

            price = float(closes[-1])
            returns = np.diff(closes) / closes[:-1]
            last_return = float(returns[-1]) if len(returns) > 0 else 0.0

            ema20_vals = []
            for i in range(20, len(closes) + 1):
                ema20_vals.append(MarketPerception.ema(closes[:i], 20))
            trend_slope = (
                (ema20_vals[-1] - ema20_vals[-5]) / max(1e-9, ema20_vals[-5])
                if len(ema20_vals) >= 5 else 0.0
            )

            ema12 = MarketPerception.ema(closes, 12)
            ema26 = MarketPerception.ema(closes, 26)
            ma_bias = (ema12 - ema26) / max(1e-9, price)

            rsi = MarketPerception.rsi(closes, 14)
            atr = MarketPerception.atr(highs, lows, closes, 14)
            atr_pct = atr / max(1e-9, price)

            bb_mid, bb_upper, bb_lower = MarketPerception.bollinger(closes)
            bb_width = (bb_upper - bb_lower) / max(1e-9, bb_mid)
            bb_pos = clamp((price - bb_lower) / max(1e-9, (bb_upper - bb_lower)))

            vol_avg = float(np.mean(volumes[-20:])) if len(volumes) >= 20 else float(np.mean(volumes))
            vol_ratio = volumes[-1] / max(1e-9, vol_avg)

            mom5 = (price - closes[-5]) / max(1e-9, closes[-5]) if len(closes) >= 5 else 0.0
            mom20 = (price - closes[-20]) / max(1e-9, closes[-20]) if len(closes) >= 20 else 0.0
            vol_ret = float(np.std(returns[-30:])) if len(returns) >= 30 else 0.0

            body = abs(closes[-1] - opens[-1])
            wick = highs[-1] - lows[-1]
            body_ratio = body / max(1e-9, wick)
            is_bullish = 1.0 if closes[-1] > opens[-1] else 0.0
            last_3_bull = sum(1 for i in range(-3, 0) if closes[i] > opens[i])

            binary_seq = [1 if closes[i] > opens[i] else 0 for i in range(len(closes))]

            return {
                "price": price,
                "ema12": ema12, "ema26": ema26,
                "rsi": rsi, "atr": atr, "atr_pct": atr_pct,
                "trend_slope": trend_slope, "ma_bias": ma_bias,
                "bb_mid": bb_mid, "bb_upper": bb_upper, "bb_lower": bb_lower,
                "bb_width": bb_width, "bb_pos": bb_pos,
                "vol_ratio": vol_ratio, "mom5": mom5, "mom20": mom20,
                "vol_ret": vol_ret, "body_ratio": body_ratio,
                "is_bullish": is_bullish, "last_3_bull": last_3_bull,
                "last_return": last_return,
                "binary_seq": binary_seq,
            }
        except Exception:
            return None


# ============================================================
# Fibonacci Heart
# ============================================================

class FibonacciHeart:
    def __init__(self):
        self.a = 0
        self.b = 1
        self.mask = (1 << 64) - 1
        self.bit_queue = deque(maxlen=2048)
        self.beat_times = deque(maxlen=80)
        self.ecg = deque(maxlen=1200)
        self.ecg_x = deque(maxlen=1200)
        self.sample_i = 0
        self.bpm = 60.0
        self.coherence = 50.0

    def _next_word(self):
        self.a, self.b = self.b, (self.a + self.b) & self.mask
        return self.a

    def _refill(self, needed):
        while len(self.bit_queue) < needed:
            word = self._next_word()
            for shift in range(63, -1, -1):
                self.bit_queue.append((word >> shift) & 1)

    def _append_baseline(self, n):
        for _ in range(n):
            self.sample_i += 1
            self.ecg_x.append(self.sample_i)
            self.ecg.append(random.uniform(-0.03, 0.03))

    def _append_spike(self):
        wave = [0.08, 0.12, -0.10, 1.0, -0.55, 0.05, 0.16, 0.22, 0.12, 0.02, -0.02, 0.0]
        for amp in wave:
            self.sample_i += 1
            self.ecg_x.append(self.sample_i)
            self.ecg.append(amp + random.uniform(-0.02, 0.02))
        self._append_baseline(3)

    def ingest_binary_candles(self, binary_seq, last_n=64):
        try:
            recent = binary_seq[-last_n:] if len(binary_seq) > last_n else binary_seq
            for bit in recent:
                fib_bit = (self._next_word() & 1)
                intuition_bit = bit ^ fib_bit
                self.bit_queue.append(intuition_bit)
        except Exception:
            pass

    def consume(self, n_bits):
        try:
            self._refill(n_bits)
            consumed = []
            now = time.time()
            for _ in range(n_bits):
                bit = self.bit_queue.popleft()
                consumed.append(bit)
                if bit == 1:
                    self.beat_times.append(now)
                    self._append_spike()
                else:
                    self._append_baseline(5)
            self.bpm = self._compute_bpm()
            self.coherence = self._compute_coherence()
            return consumed
        except Exception:
            return []

    def _compute_bpm(self):
        try:
            now = time.time()
            recent = [t for t in self.beat_times if now - t <= 12]
            if len(recent) >= 3:
                intervals = [recent[i + 1] - recent[i] for i in range(len(recent) - 1)]
                avg = sum(intervals) / len(intervals)
                if avg > 0:
                    return clamp(60 / avg, 30, 220)
        except Exception:
            pass
        return 60.0

    def _compute_coherence(self):
        try:
            now = time.time()
            recent = [t for t in self.beat_times if now - t <= 12]
            if len(recent) < 4: return 50.0
            intervals = [recent[i + 1] - recent[i] for i in range(len(recent) - 1)]
            mean = sum(intervals) / len(intervals)
            if mean <= 0: return 50.0
            var = sum((x - mean) ** 2 for x in intervals) / len(intervals)
            cv = math.sqrt(var) / mean
            return clamp(1 - cv * 2, 0, 1) * 100
        except Exception:
            return 50.0

    def intuition_bits(self, n_bits=8):
        try:
            self._refill(n_bits)
            bits = []
            for _ in range(n_bits):
                bits.append(self.bit_queue.popleft())
            return bits
        except Exception:
            return [0] * n_bits


# ============================================================
# Binary Sequence Predictor
# ============================================================

class BinarySequencePredictor:
    def __init__(self, heart: FibonacciHeart):
        self.heart = heart
        self.markov_1 = defaultdict(lambda: [0, 0])
        self.markov_2 = defaultdict(lambda: [0, 0])
        self.markov_3 = defaultdict(lambda: [0, 0])
        self.markov_4 = defaultdict(lambda: [0, 0])
        self.pattern_history = defaultdict(lambda: {"bull": 0, "bear": 0})
        self.run_lengths = []

    def reset(self):
        """بازنشانی برای backtest مستقل."""
        self.markov_1 = defaultdict(lambda: [0, 0])
        self.markov_2 = defaultdict(lambda: [0, 0])
        self.markov_3 = defaultdict(lambda: [0, 0])
        self.markov_4 = defaultdict(lambda: [0, 0])
        self.pattern_history = defaultdict(lambda: {"bull": 0, "bear": 0})
        self.run_lengths = []

    def learn(self, binary_seq):
        try:
            if len(binary_seq) < 5: return
            for i in range(1, len(binary_seq)):
                prev = binary_seq[i-1]
                curr = binary_seq[i]
                self.markov_1[prev][curr] += 1
            for i in range(2, len(binary_seq)):
                ctx = (binary_seq[i-2], binary_seq[i-1])
                self.markov_2[ctx][binary_seq[i]] += 1
            for i in range(3, len(binary_seq)):
                ctx = (binary_seq[i-3], binary_seq[i-2], binary_seq[i-1])
                self.markov_3[ctx][binary_seq[i]] += 1
            for i in range(4, len(binary_seq)):
                ctx = tuple(binary_seq[i-4:i])
                self.markov_4[ctx][binary_seq[i]] += 1

            runs = []
            current = binary_seq[0]
            length = 1
            for i in range(1, len(binary_seq)):
                if binary_seq[i] == current:
                    length += 1
                else:
                    runs.append((current, length))
                    current = binary_seq[i]
                    length = 1
            runs.append((current, length))
            self.run_lengths = runs[-20:]

            for pat_len in [3, 4, 5]:
                for i in range(pat_len, len(binary_seq) - 2):
                    pattern = tuple(binary_seq[i-pat_len:i])
                    future_bits = binary_seq[i:i+2]
                    future_score = sum(future_bits) - 1
                    if future_score >= 1:
                        self.pattern_history[pattern]["bull"] += 1
                    elif future_score <= -1:
                        self.pattern_history[pattern]["bear"] += 1
        except Exception:
            pass

    def predict(self, binary_seq, heart_intuition_weight=0.35, use_heart=True):
        try:
            if len(binary_seq) < 5:
                return {
                    "bullish_prob": 0.5, "bearish_prob": 0.5,
                    "confidence": 0.0, "pattern_match": None,
                    "heart_bits": [], "reasoning": ["داده ناکافی"],
                }

            reasoning = []
            scores = {"bull": 0.0, "bear": 0.0}

            last_1 = binary_seq[-1]
            last_2 = tuple(binary_seq[-2:])
            last_3 = tuple(binary_seq[-3:])
            last_4 = tuple(binary_seq[-4:]) if len(binary_seq) >= 4 else None

            for ctx, weight in [
                (last_1, 1.0), (last_2, 1.5), (last_3, 2.0),
                (last_4, 2.5) if last_4 else (None, 0),
            ]:
                if ctx is None: continue
                if len(ctx) == 1: table = self.markov_1
                elif len(ctx) == 2: table = self.markov_2
                elif len(ctx) == 3: table = self.markov_3
                else: table = self.markov_4

                counts = table[ctx]
                total = counts[0] + counts[1]
                if total > 0:
                    p_bull = counts[1] / total
                    p_bear = counts[0] / total
                    scores["bull"] += p_bull * weight * total
                    scores["bear"] += p_bear * weight * total

            best_match = None
            best_score = 0
            for pat_len in [3, 4, 5]:
                if len(binary_seq) >= pat_len:
                    pattern = tuple(binary_seq[-pat_len:])
                    if pattern in self.pattern_history:
                        stats = self.pattern_history[pattern]
                        total = stats["bull"] + stats["bear"]
                        if total >= 2:
                            bull_ratio = stats["bull"] / total
                            bear_ratio = stats["bear"] / total
                            match_score = total * (pat_len / 3)
                            scores["bull"] += bull_ratio * match_score
                            scores["bear"] += bear_ratio * match_score
                            if total > best_score:
                                best_score = total
                                best_match = (pattern, stats)

            if self.run_lengths:
                last_run_bit, last_run_len = self.run_lengths[-1]
                if last_run_len >= 4:
                    if last_run_bit == 1:
                        scores["bear"] += last_run_len * 0.8
                    else:
                        scores["bull"] += last_run_len * 0.8

            heart_bits = []
            if use_heart and self.heart:
                heart_bits = self.heart.intuition_bits(n_bits=5)
                heart_bull = sum(heart_bits)
                heart_bear = len(heart_bits) - heart_bull
                heart_weight = heart_intuition_weight * (
                    (self.heart.coherence / 100.0) if self.heart else 0.5
                ) * len(heart_bits)
                scores["bull"] += heart_bull * heart_weight
                scores["bear"] += heart_bear * heart_weight

            total_score = scores["bull"] + scores["bear"] + 1e-9
            bull_prob = scores["bull"] / total_score
            bear_prob = scores["bear"] / total_score
            confidence = abs(bull_prob - bear_prob)

            pattern_match = None
            if best_match:
                pattern, stats = best_match
                pattern_str = "".join(str(b) for b in pattern)
                direction = "صعودی" if stats["bull"] > stats["bear"] else "نزولی"
                pattern_match = f"{pattern_str} → {direction} ({stats['bull']}:{stats['bear']})"

            return {
                "bullish_prob": bull_prob, "bearish_prob": bear_prob,
                "confidence": confidence, "pattern_match": pattern_match,
                "heart_bits": heart_bits, "reasoning": reasoning,
                "scores": scores,
            }
        except Exception as e:
            return {
                "bullish_prob": 0.5, "bearish_prob": 0.5,
                "confidence": 0.0, "pattern_match": None,
                "heart_bits": [], "reasoning": [f"Error: {str(e)}"],
            }


# ============================================================
# Backtester — Walk-Forward بدون Lookahead
# ============================================================

class Backtester:
    """
    Backtest Walk-Forward روی داده‌های گذشته:
    - در هر نقطه i، فقط از داده‌های [:i] استفاده می‌شود
    - پیش‌بینی 10 کندل بعد
    - Win Rate واقعی محاسبه می‌شود
    - بدون Lookahead
    """

    def __init__(self, window_size=10, min_history=30, step=2):
        self.window_size = window_size  # تعداد کندل برای سنجش پیش‌بینی
        self.min_history = min_history  # حداقل داده برای شروع backtest
        self.step = step  # هر چند کندل یکبار پیش‌بینی
        self.result = None
        self.lock = threading.Lock()

    def run(self, df):
        """
        backtest کامل روی df.
        خروجی: dict با آمار و مسیر پیش‌بینی‌ها
        """
        try:
            if df is None or len(df) < self.min_history + self.window_size + 5:
                return None

            # یک predictor و heart موقت برای backtest
            heart = FibonacciHeart()
            predictor = BinarySequencePredictor(heart)

            path = []
            wins = 0
            losses = 0
            neutral = 0

            # Walk-Forward: از min_history تا len(df) - window_size
            end_idx = len(df) - self.window_size
            for i in range(self.min_history, end_idx, self.step):
                # داده‌های تا نقطه i (شامل i) — بدون آینده
                df_slice = df.iloc[:i+1]
                features = MarketPerception.extract(df_slice)
                if not features or "binary_seq" not in features:
                    continue

                binary_seq = features["binary_seq"]

                # یادگیری از گذشته (فقط داده‌های تا i)
                predictor.learn(binary_seq)
                heart.ingest_binary_candles(binary_seq, last_n=32)
                heart.consume(2)

                # پیش‌بینی بدون نگاه به آینده
                pred = predictor.predict(binary_seq, heart_intuition_weight=0.3, use_heart=True)

                bull_prob = pred["bullish_prob"]
                bear_prob = pred["bearish_prob"]

                if bull_prob > bear_prob:
                    direction = "bull"
                elif bear_prob > bull_prob:
                    direction = "bear"
                else:
                    direction = "neutral"

                # قیمت در لحظه پیش‌بینی
                price_at_pred = float(df.iloc[i]["close"])
                time_at_pred = df.iloc[i]["ts"]

                # قیمت واقعی 10 کندل بعد
                future_idx = i + self.window_size
                if future_idx >= len(df):
                    break
                price_future = float(df.iloc[future_idx]["close"])
                time_future = df.iloc[future_idx]["ts"]

                actual_move = price_future - price_at_pred
                actual_pct = actual_move / max(1e-9, price_at_pred) * 100

                # سنجش نتیجه
                correct = False
                if direction == "bull" and actual_move > 0:
                    correct = True
                    wins += 1
                elif direction == "bear" and actual_move < 0:
                    correct = True
                    wins += 1
                elif direction == "neutral":
                    neutral += 1
                else:
                    losses += 1

                path.append({
                    "time_pred": time_at_pred,
                    "time_future": time_future,
                    "price_at_pred": price_at_pred,
                    "price_future": price_future,
                    "predicted_direction": direction,
                    "actual_move_pct": actual_pct,
                    "confidence": pred["confidence"],
                    "bull_prob": bull_prob,
                    "bear_prob": bear_prob,
                    "correct": correct,
                })

            total_decisive = wins + losses
            win_rate = (wins / total_decisive * 100) if total_decisive > 0 else 0.0

            # محاسبه P&L تجمعی (با ریسک یکسان)
            cumulative_pnl = []
            total_pnl = 0.0
            for p in path:
                if p["predicted_direction"] == "neutral":
                    pnl = 0
                elif p["correct"]:
                    pnl = abs(p["actual_move_pct"])
                else:
                    pnl = -abs(p["actual_move_pct"])
                total_pnl += pnl
                cumulative_pnl.append({
                    "time": p["time_future"],
                    "pnl": total_pnl,
                })

            result = {
                "wins": wins,
                "losses": losses,
                "neutral": neutral,
                "total": len(path),
                "total_decisive": total_decisive,
                "win_rate": win_rate,
                "path": path,
                "cumulative_pnl": cumulative_pnl,
                "final_pnl": total_pnl,
                "timestamp": datetime.now(),
            }

            with self.lock:
                self.result = result

            return result

        except Exception as e:
            return {"error": str(e), "path": [], "wins": 0, "losses": 0,
                    "win_rate": 0, "total": 0}

    def get_result(self):
        with self.lock:
            return self.result


class BacktesterThread(threading.Thread):
    """Thread جداگانه برای اجرای backtest بدون مسدود کردن UI."""

    def __init__(self, backtester: Backtester):
        super().__init__(daemon=True)
        self.backtester = backtester
        self.latest_df = None
        self.running = True
        self.last_run_hash = None

    def set_df(self, df):
        self.latest_df = df

    def run(self):
        while self.running:
            try:
                if self.latest_df is not None and not self.latest_df.empty:
                    # hash کردن آخرین کندل برای جلوگیری از اجرای تکراری
                    try:
                        last_ts = self.latest_df.iloc[-1]["ts"]
                        length = len(self.latest_df)
                        current_hash = (last_ts, length)
                    except Exception:
                        current_hash = None

                    if current_hash != self.last_run_hash:
                        self.backtester.run(self.latest_df)
                        self.last_run_hash = current_hash

                time.sleep(8)  # هر 8 ثانیه یکبار
            except Exception:
                time.sleep(5)


# ============================================================
# Body
# ============================================================

class Body:
    def __init__(self):
        self.signals = {
            "energy": 82.0, "oxygen": 88.0, "glucose": 75.0,
            "safety": 78.0, "novelty": 55.0, "pain": 6.0,
            "fatigue": 18.0, "temperature": 50.0,
        }

    def update(self, action, reward_signal=0.0):
        s = self.signals
        if action == "observe":
            s["energy"] = clamp100(s["energy"] - 0.4)
            s["novelty"] = clamp100(s["novelty"] + 1.5)
            s["fatigue"] = clamp100(s["fatigue"] + 0.3)
        elif action == "analyze_deep":
            s["energy"] = clamp100(s["energy"] - 1.2)
            s["glucose"] = clamp100(s["glucose"] - 0.8)
            s["fatigue"] = clamp100(s["fatigue"] + 0.8)
            s["novelty"] = clamp100(s["novelty"] + 3.0)
        elif action == "forecast":
            s["energy"] = clamp100(s["energy"] - 2.0)
            s["glucose"] = clamp100(s["glucose"] - 1.5)
            s["fatigue"] = clamp100(s["fatigue"] + 1.2)
        elif action == "rest":
            s["energy"] = clamp100(s["energy"] + 3.0)
            s["fatigue"] = clamp100(s["fatigue"] - 4.0)
            s["oxygen"] = clamp100(s["oxygen"] + 2.0)
            s["pain"] = clamp100(s["pain"] - 0.6)
        elif action == "regulate":
            s["safety"] = clamp100(s["safety"] + 3.5)
            s["pain"] = clamp100(s["pain"] - 1.0)

        if reward_signal > 0:
            s["safety"] = clamp100(s["safety"] + reward_signal * 2.0)
            s["pain"] = clamp100(s["pain"] - reward_signal * 0.5)
        elif reward_signal < 0:
            s["safety"] = clamp100(s["safety"] + reward_signal * 2.0)
            s["pain"] = clamp100(s["pain"] - reward_signal * 0.8)

        s["energy"] = clamp100(s["energy"] - 0.35)
        s["oxygen"] = clamp100(s["oxygen"] - 0.25)
        s["glucose"] = clamp100(s["glucose"] - 0.30)
        s["novelty"] = clamp100(s["novelty"] - 0.25)
        s["pain"] = clamp100(s["pain"] + random.uniform(-0.15, 0.25))
        s["temperature"] = clamp100(s["temperature"] + random.uniform(-0.3, 0.3))

        if s["energy"] < 25: s["pain"] = clamp100(s["pain"] + 0.5)
        if s["oxygen"] < 40: s["pain"] = clamp100(s["pain"] + 0.7)


# ============================================================
# Small-world connectome
# ============================================================

def build_small_world(n, k=10, p=0.14, rng=None):
    if rng is None: rng = random.Random()
    incoming = [[] for _ in range(n)]
    half = max(1, k // 2)
    for i in range(n):
        for d in range(-half, half + 1):
            if d == 0: continue
            j = (i + d) % n
            w = rng.uniform(0.08, 0.55) if rng.random() < 0.82 else rng.uniform(-0.35, 0.08)
            incoming[i].append([j, w])
    for i in range(n):
        for edge in incoming[i]:
            if rng.random() < p:
                edge[0] = rng.randrange(n)
                edge[1] = rng.uniform(-0.45, 0.65)
    hub_count = min(10, max(3, n // 70))
    hubs = rng.sample(range(n), hub_count)
    for hub in hubs:
        for _ in range(min(60, max(12, n // 12))):
            target = rng.randrange(n)
            if target != hub:
                incoming[target].append([hub, rng.uniform(0.18, 0.72)])
    return incoming


# ============================================================
# Neural Core
# ============================================================

class NeuralCore:
    def __init__(self, n=None, seed=None):
        cpu_count = os.cpu_count() or 4
        if n is None: n = min(896, max(320, cpu_count * 80))
        self.n = n
        self.rng = random.Random(seed if seed is not None else int(time.time() * 1000))
        self.potentials = [self.rng.uniform(-0.1, 0.1) for _ in range(n)]
        self.firing = [0] * n
        self.thresholds = [self.rng.uniform(0.38, 0.62) for _ in range(n)]
        self.incoming = build_small_world(n, k=10, p=0.14, rng=self.rng)
        self.modules = self._build_modules()
        self._add_architecture()
        self.history = deque(maxlen=180)
        self.module_history = deque(maxlen=40)
        self.ignition = 0.0
        self.integration = 0.0
        self.differentiation = 0.0
        self.phi = 0.0
        self.consciousness = 0.0
        self.synapse_count = sum(len(x) for x in self.incoming)

    def _build_modules(self):
        n = self.n
        parts = [
            ("sensory", n // 9), ("market", n // 7), ("interoceptive", n // 9),
            ("memory", n // 6), ("association", n // 6), ("forecast", n // 8),
            ("self", n // 12), ("motor", n // 14),
        ]
        start = 0
        modules = {}
        for name, size in parts:
            size = max(1, size)
            end = min(n, start + size)
            modules[name] = list(range(start, end))
            start = end
        modules["global"] = list(range(start, n))
        if not modules["global"]: modules["global"] = [n - 1]
        return modules

    def _add_module_connections(self, src, dst, count, wmin=0.10, wmax=0.55):
        try:
            src_n = self.modules.get(src, [])
            dst_n = self.modules.get(dst, [])
            if not src_n or not dst_n: return
            for _ in range(count):
                j = self.rng.choice(src_n)
                i = self.rng.choice(dst_n)
                self.incoming[i].append([j, self.rng.uniform(wmin, wmax)])
        except Exception:
            pass

    def _add_architecture(self):
        self._add_module_connections("market", "forecast", 80, 0.22, 0.70)
        self._add_module_connections("market", "association", 60, 0.18, 0.55)
        self._add_module_connections("market", "memory", 50, 0.15, 0.50)
        self._add_module_connections("forecast", "global", 90, 0.25, 0.75)
        self._add_module_connections("forecast", "self", 50, 0.20, 0.60)
        self._add_module_connections("sensory", "association", 50, 0.15, 0.55)
        self._add_module_connections("interoceptive", "self", 40, 0.18, 0.60)
        self._add_module_connections("interoceptive", "global", 25, 0.12, 0.45)
        self._add_module_connections("memory", "association", 60, 0.15, 0.55)
        self._add_module_connections("association", "memory", 50, 0.12, 0.50)
        self._add_module_connections("association", "self", 50, 0.16, 0.60)
        self._add_module_connections("association", "global", 70, 0.18, 0.65)
        self._add_module_connections("self", "global", 60, 0.22, 0.70)
        for gw in self.modules["global"]:
            for _ in range(22):
                target = self.rng.randrange(self.n)
                if target != gw:
                    self.incoming[target].append([gw, self.rng.uniform(0.15, 0.60)])
        self._add_module_connections("global", "motor", 50, 0.18, 0.60)
        self._add_module_connections("global", "forecast", 40, 0.15, 0.55)

    def step(self, body_signals, market_features, neuromodulators, action,
             prediction_error, hypercoherence, binary_pred=None):
        try:
            n = self.n
            external = [0.0] * n
            t = time.time()
            for idx, i in enumerate(self.modules["sensory"]):
                phase = idx * 0.37
                external[i] += (0.08 * math.sin(t * 1.7 + phase)
                               + 0.06 * math.cos(t * 0.9 + phase)
                               + self.rng.uniform(-0.02, 0.02))
            for idx, i in enumerate(self.modules["interoceptive"]):
                items = list(body_signals.items())
                key, value = items[idx % len(items)]
                normalized = value / 100.0 if key in ("pain", "fatigue") else 1.0 - value / 100.0
                external[i] += clamp(normalized * 0.48 + self.rng.uniform(-0.02, 0.02))
            if market_features:
                market_neurons = self.modules["market"]
                feature_list = [
                    clamp(market_features.get("rsi", 50) / 100),
                    clamp((market_features.get("trend_slope", 0) + 0.02) / 0.04, 0, 1),
                    clamp((market_features.get("ma_bias", 0) + 0.02) / 0.04, 0, 1),
                    clamp(market_features.get("atr_pct", 0) * 20, 0, 1),
                    clamp(market_features.get("bb_pos", 0.5)),
                    clamp(market_features.get("vol_ratio", 1) / 3, 0, 1),
                    clamp((market_features.get("mom5", 0) + 0.05) / 0.10, 0, 1),
                    clamp(market_features.get("vol_ret", 0) * 30, 0, 1),
                    clamp(market_features.get("body_ratio", 0.5)),
                    market_features.get("is_bullish", 0.5),
                ]
                for idx, i in enumerate(market_neurons):
                    external[i] += feature_list[idx % len(feature_list)] * 0.65
            if binary_pred:
                forecast_neurons = self.modules["forecast"]
                bull_prob = binary_pred.get("bullish_prob", 0.5)
                confidence = binary_pred.get("confidence", 0.0)
                heart_bits = binary_pred.get("heart_bits", [])
                for idx, i in enumerate(forecast_neurons):
                    if idx < len(heart_bits):
                        external[i] += heart_bits[idx] * 0.4 * (0.5 + confidence)
                    external[i] += bull_prob * 0.3 * confidence
            if action == "forecast":
                for i in self.modules["forecast"]:
                    external[i] += 0.25
            error_drive = clamp(prediction_error / 100.0)
            for i in self.modules["association"][:max(1, len(self.modules["association"]) // 3)]:
                external[i] += 0.12 * error_drive
            broadcast = 0.05 * self.ignition + 0.05 * hypercoherence
            new_firing = [0] * n
            norepi = neuromodulators.get("norepinephrine", 0.3)
            for i in range(n):
                s = 0.76 * self.potentials[i] + external[i]
                if broadcast > 0: s += broadcast
                for j, w in self.incoming[i]: s += w * self.firing[j]
                s += norepi * self.rng.uniform(-0.035, 0.035)
                self.potentials[i] = s
                new_firing[i] = 1 if s > self.thresholds[i] else 0
            self.firing = new_firing
            self._plasticity(neuromodulators, prediction_error)
            acts = {}
            for name, idxs in self.modules.items():
                acts[name] = sum(self.firing[i] for i in idxs) / max(1, len(idxs))
            gw_act = acts.get("global", 0.0)
            self_act = acts.get("self", 0.0)
            assoc_act = acts.get("association", 0.0)
            memory_act = acts.get("memory", 0.0)
            forecast_act = acts.get("forecast", 0.0)
            target_ignition = clamp(
                gw_act * 1.10 + self_act * 0.30 + assoc_act * 0.22
                + memory_act * 0.14 + forecast_act * 0.25
                + neuromodulators.get("acetylcholine", 0.3) * 0.08
                + hypercoherence * 0.10
            )
            self.ignition = 0.62 * self.ignition + 0.38 * target_ignition
            self._compute_phi(acts, hypercoherence)
            self.consciousness = clamp100(
                100.0 * (0.38 * self.phi + 0.24 * self.ignition
                        + 0.20 * self.integration + 0.18 * self.differentiation)
            )
            self.history.append({
                "t": time.time(), "consciousness": self.consciousness,
                "ignition": self.ignition, "integration": self.integration,
                "differentiation": self.differentiation, "phi": self.phi,
            })
            self.module_history.append(dict(acts))
            return acts
        except Exception:
            return {}

    def _plasticity(self, neuromodulators, prediction_error):
        try:
            dopamine = neuromodulators.get("dopamine", 0.4)
            acetylcholine = neuromodulators.get("acetylcholine", 0.3)
            active = [i for i, f in enumerate(self.firing) if f == 1]
            if not active: return
            sampled = self.rng.sample(active, min(40, len(active)))
            base_plasticity = (0.0016 + acetylcholine * 0.0032
                               + clamp(prediction_error / 100.0) * 0.0022)
            for i in sampled:
                for edge in self.incoming[i]:
                    j, w = edge
                    if self.firing[j] == 1:
                        edge[1] = clamp(w + base_plasticity * (0.35 + dopamine), -1.0, 1.0)
        except Exception:
            pass

    def _corr(self, x, y):
        try:
            n = len(x)
            if n < 3: return 0.0
            mx, my = sum(x) / n, sum(y) / n
            cov = sum((a - mx) * (b - my) for a, b in zip(x, y)) / (n - 1)
            vx = sum((a - mx) ** 2 for a in x) / (n - 1)
            vy = sum((b - my) ** 2 for b in y) / (n - 1)
            sx, sy = math.sqrt(max(0, vx)), math.sqrt(max(0, vy))
            return clamp(cov / (sx * sy), -1.0, 1.0) if sx * sy > 1e-9 else 0.0
        except Exception:
            return 0.0

    def _compute_phi(self, acts, hypercoherence):
        try:
            if len(self.module_history) < 8:
                self.integration = 0.25
                self.differentiation = 0.25
                self.phi = 0.2
                return
            window = list(self.module_history)[-30:]
            keys = list(acts.keys())
            series = {k: [h.get(k, 0) for h in window] for k in keys}
            corrs = []
            for i in range(len(keys)):
                for j in range(i + 1, len(keys)):
                    corrs.append(abs(self._corr(series[keys[i]], series[keys[j]])))
            self.integration = clamp(sum(corrs) / max(1, len(corrs)) * 1.6) if corrs else 0.25
            vals = list(acts.values())
            total = sum(vals) + 1e-9
            probs = [v / total for v in vals]
            ent = sum(-p * math.log(p) for p in probs if p > 1e-9)
            max_ent = math.log(max(1, len(probs)))
            self.differentiation = clamp(ent / max_ent if max_ent > 0 else 0.0)
            self.phi = clamp(
                (0.55 * self.integration + 0.45 * self.differentiation)
                * (0.45 + self.ignition * 0.55 + hypercoherence * 0.25)
            )
        except Exception:
            self.phi = 0.2


# ============================================================
# Price Oracle
# ============================================================

class PriceOracle:
    def __init__(self, rng, predictor: BinarySequencePredictor):
        self.rng = rng
        self.predictor = predictor
        self.history = deque(maxlen=100)
        self.last_prediction = None

    def forecast(self, features, org, horizon_candles=10, horizon_time_minutes=15):
        try:
            if not features or "binary_seq" not in features:
                return None

            binary_seq = features["binary_seq"]
            self.predictor.learn(binary_seq)
            org.heart.ingest_binary_candles(binary_seq, last_n=64)
            org.heart.consume(4)

            binary_pred = self.predictor.predict(binary_seq, heart_intuition_weight=0.35)

            bull_prob = binary_pred["bullish_prob"]
            bear_prob = binary_pred["bearish_prob"]
            base_prob = max(0.05, 1.0 - bull_prob - bear_prob)
            total = bull_prob + bear_prob + base_prob
            bull_prob /= total
            bear_prob /= total
            base_prob /= total

            confidence = binary_pred["confidence"]
            brain_weight = 0.5 + org.brain.phi * 0.3 + org.brain.consciousness / 300

            price = features["price"]
            atr = features["atr"]
            vol_ratio = features["vol_ratio"]
            base_magnitude = atr * (0.5 + 0.5 * min(2.0, vol_ratio))

            bull_target = price + base_magnitude * (1 + bull_prob)
            bear_target = price - base_magnitude * (1 + bear_prob)
            base_target = price + (self.rng.uniform(-0.3, 0.3) * base_magnitude)

            scenarios = {
                "bull": {"target": bull_target, "confidence": bull_prob * brain_weight,
                         "move_pct": (bull_target - price) / price * 100},
                "bear": {"target": bear_target, "confidence": bear_prob * brain_weight,
                         "move_pct": (bear_target - price) / price * 100},
                "base": {"target": base_target, "confidence": base_prob * brain_weight,
                         "move_pct": (base_target - price) / price * 100},
            }

            best = max(scenarios.items(), key=lambda x: x[1]["confidence"])
            expected_price = sum(s["target"] * s["confidence"] for s in scenarios.values()) / \
                             sum(s["confidence"] for s in scenarios.values())

            now = datetime.now()
            target_time = now + timedelta(minutes=horizon_time_minutes)

            result = {
                "timestamp": now, "target_time": target_time,
                "horizon_candles": horizon_candles, "current_price": price,
                "scenarios": scenarios, "best_scenario": best[0],
                "best_target": best[1]["target"], "best_confidence": best[1]["confidence"],
                "best_move_pct": best[1]["move_pct"], "expected_price": expected_price,
                "expected_move_pct": (expected_price - price) / price * 100,
                "binary_prediction": binary_pred,
                "heart_bpm": org.heart.bpm, "heart_coherence": org.heart.coherence,
            }

            self.last_prediction = result
            self.history.append(result)
            return result
        except Exception as e:
            return None


# ============================================================
# Tertium Organum Core
# ============================================================

class TertiumOrganumCore:
    def __init__(self):
        self.self_remembering = 0.2
        self.divided_attention = 0.2
        self.higher_coherence = 0.2
        self.hyperconsciousness = 5.0
        self.eternal_recurrence = 0
        self.market_dimensions = []
        self.insight = "هسته فرابعدی بازار در حال شکل‌گیری است."

    def update(self, org, features, prediction_result, backtest_result=None):
        try:
            body_axis = clamp(sum(org.body.signals.values()) / (100 * len(org.body.signals)))
            time_axis = clamp(1.0 - org.predictor.error / 80.0)

            if prediction_result:
                confs = [s["confidence"] for s in prediction_result["scenarios"].values()]
                possibility_axis = clamp(statistics.pstdev(confs) * 3)
                future_clarity = max(confs)
            else:
                possibility_axis = 0.1
                future_clarity = 0.1

            self_axis = org.self_model.confidence

            if features:
                market_axis = clamp(
                    features.get("atr_pct", 0.01) * 10
                    + min(2.0, features.get("vol_ratio", 1.0)) / 2
                    + abs(features.get("trend_slope", 0)) * 10
                ) / 3
            else:
                market_axis = 0.2

            dims = [body_axis, time_axis, possibility_axis, self_axis, market_axis]
            self.market_dimensions = dims
            dim_std = statistics.pstdev(dims) if len(dims) > 1 else 0.0
            self.higher_coherence = clamp(1.0 - dim_std * 1.6)

            module_acts = org.last_module_activity
            body_att = module_acts.get("interoceptive", 0.0)
            env_att = module_acts.get("sensory", 0.0)
            market_att = module_acts.get("market", 0.0)
            self_att = module_acts.get("self", 0.0)
            forecast_att = module_acts.get("forecast", 0.0)
            future_att = clamp(org.brain.ignition * 0.70 + future_clarity * 0.30)

            atts = [body_att, env_att, market_att, self_att, forecast_att, future_att]
            total_att = sum(atts) + 1e-9
            att_probs = [a / total_att for a in atts]
            ent = sum(-p * math.log(p) for p in att_probs if p > 1e-9)
            self.divided_attention = clamp(ent / math.log(max(2, len(atts))))

            self.self_remembering = clamp(
                0.35 * org.brain.consciousness / 100.0
                + 0.30 * self_axis
                + 0.20 * self.divided_attention
                + 0.15 * org.brain.phi
            )

            self.hyperconsciousness = clamp100(
                100.0 * (0.26 * org.brain.phi + 0.22 * self.self_remembering
                        + 0.18 * self.higher_coherence + 0.16 * future_clarity
                        + 0.18 * self.divided_attention)
            )

            backtest_info = ""
            if backtest_result and backtest_result.get("total_decisive", 0) > 0:
                wr = backtest_result["win_rate"]
                w = backtest_result["wins"]
                l = backtest_result["losses"]
                pnl = backtest_result["final_pnl"]
                backtest_info = (
                    f"\n📊 Backtest: {wr:.1f}٪ Win Rate | "
                    f"{w}W/{l}L | P&L تجمعی: {pnl:+.2f}٪"
                )

            if prediction_result:
                best = prediction_result["best_scenario"]
                move = prediction_result["best_move_pct"]
                conf = prediction_result["best_confidence"] * 100
                direction = "صعودی" if move > 0 else "نزولی" if move < 0 else "خنثی"
                target_time = prediction_result["target_time"].strftime("%H:%M")
                target_price = prediction_result["best_target"]

                bp = prediction_result.get("binary_prediction", {})
                pattern = bp.get("pattern_match", "نامشخص")
                heart_bits = bp.get("heart_bits", [])
                heart_str = "".join(str(b) for b in heart_bits[:8])

                self.insight = (
                    f"💓 قلب فیبوناچی: {org.heart.bpm:.0f} BPM "
                    f"(انسجام: {org.heart.coherence:.0f}٪)\n"
                    f"🔢 بیت‌های شهودی: {heart_str}\n"
                    f"🎯 پیش‌بینی فرابعدی: در {target_time}، "
                    f"احتمال حرکت {direction} به {target_price:.2f} "
                    f"({move:+.2f}٪) با اعتماد {conf:.0f}٪\n"
                    f"🧩 الگوی تطبیقی: {pattern}{backtest_info}\n"
                    f"🌌 خودبه‌خودی‌آگاهی: {self.self_remembering * 100:.0f}٪ | "
                    f"Φ: {org.brain.phi * 100:.0f}٪"
                )
            else:
                self.insight = f"در انتظار داده بازار.{backtest_info}"

        except Exception:
            pass


# ============================================================
# Predictive Coding & Self Model & Episodic Memory
# ============================================================

class PredictiveModel:
    def __init__(self):
        self.market_estimate = None
        self.error = 12.0
        self.trend = {}

    def update(self, features, brain_phi):
        try:
            if not features: return self.error
            keys = ["rsi", "trend_slope", "bb_pos", "vol_ratio"]
            if self.market_estimate is None:
                self.market_estimate = {k: features.get(k, 0) for k in keys}
            errors = []
            for k in keys:
                actual = features.get(k, 0)
                old = self.market_estimate.get(k, actual)
                predicted = old + self.trend.get(k, 0)
                errors.append(abs(actual - predicted) / max(1e-9, abs(actual) + 1.0))
                self.trend[k] = clamp(0.75 * self.trend.get(k, 0) + 0.25 * (actual - old), -5.0, 5.0)
                self.market_estimate[k] = 0.82 * old + 0.18 * actual
            self.error = 0.70 * self.error + 0.30 * (sum(errors) / max(1, len(errors)) * 100)
            return self.error
        except Exception:
            return self.error


class SelfModel:
    def __init__(self):
        self.body_estimate = {}
        self.prediction_error = 20.0
        self.confidence = 0.35

    def update(self, body_signals, consciousness, ignition, predictor_error):
        try:
            if not self.body_estimate:
                self.body_estimate = dict(body_signals)
            errors = []
            for k, v in body_signals.items():
                old = self.body_estimate.get(k, v)
                self.body_estimate[k] = 0.82 * old + 0.18 * v
                errors.append(abs(self.body_estimate[k] - v))
            avg_error = sum(errors) / max(1, len(errors))
            self.prediction_error = clamp100(0.55 * avg_error + 0.45 * predictor_error)
            self.confidence = clamp(
                (consciousness / 100.0) * (1.0 - self.prediction_error / 130.0)
                + ignition * 0.15
            )
        except Exception:
            pass


class EpisodicMemory:
    def __init__(self, capacity=500):
        self.events = []
        self.capacity = capacity

    def vector(self, features, consciousness, ignition):
        vec = []
        if features:
            for k in ["rsi", "trend_slope", "bb_pos", "vol_ratio", "mom5"]:
                vec.append(features.get(k, 0))
        vec.append(consciousness / 100.0)
        vec.append(ignition)
        return vec

    def add(self, vec, action, price, scenario, confidence, importance):
        self.events.append({
            "time": now_hms(), "vec": vec, "action": action,
            "price": price, "scenario": scenario,
            "confidence": confidence, "importance": importance,
        })
        if len(self.events) > self.capacity:
            self.events.pop(0)

    def recurrence_count(self, vec, threshold=0.30):
        count = 0
        for e in self.events[:-1]:
            try:
                if len(vec) != len(e["vec"]): continue
                d = math.sqrt(sum((a - b) ** 2 for a, b in zip(vec, e["vec"])) / len(vec))
                if d < threshold: count += 1
            except Exception:
                pass
        return count


# ============================================================
# Nostradamus Organism
# ============================================================

ACTIONS = ["observe", "analyze_deep", "forecast", "rest", "regulate"]
ACTION_FA = {
    "observe": "مشاهده بازار",
    "analyze_deep": "تحلیل عمیق",
    "forecast": "پیش‌بینی",
    "rest": "استراحت",
    "regulate": "تنظیم",
}


class NostradamusOrganism:
    def __init__(self):
        self.rng = random.Random(int(time.time() * 1000))
        self.body = Body()
        self.heart = FibonacciHeart()
        self.brain = NeuralCore()
        self.binary_predictor = BinarySequencePredictor(self.heart)
        self.oracle = PriceOracle(self.rng, self.binary_predictor)
        self.predictor = PredictiveModel()
        self.self_model = SelfModel()
        self.tertium = TertiumOrganumCore()
        self.episodic = EpisodicMemory(capacity=500)

        self.age = 0
        self.action = "observe"
        self.last_module_activity = {}
        self.last_features = None
        self.last_prediction = None
        self.backtest_result = None
        self.prediction_log = deque(maxlen=30)
        self.thoughts = deque(maxlen=70)
        self.logs = deque(maxlen=90)

        self.heart.consume(4)
        self.add_log("تولد", "نوستراداموس با Backtest Walk-Forward بیدار شد.")

    def add_log(self, kind, text):
        self.logs.append({"time": now_hms(), "kind": kind, "text": text})

    def add_thought(self, text):
        self.thoughts.append({"time": now_hms(), "text": text})

    def make_neuromodulators(self, reward_signal):
        s = self.body.signals
        return {
            "dopamine": clamp(0.34 + max(0, reward_signal) * 0.15 + (0.10 if self.action == "forecast" else 0)),
            "serotonin": clamp(0.35 + s["safety"] / 260.0 - s["pain"] / 260.0),
            "norepinephrine": clamp(0.24 + s["pain"] / 210.0 + max(0, 40 - s["energy"]) / 260.0 + self.predictor.error / 350.0),
            "acetylcholine": clamp(0.30 + self.brain.consciousness / 260.0 + self.self_model.confidence * 0.22 + self.tertium.divided_attention * 0.18),
        }

    def choose_action(self, features):
        try:
            if features is None: return "rest"
            s = self.body.signals
            scores = {
                "observe": 0.5,
                "analyze_deep": clamp(features.get("atr_pct", 0.01) * 20) * 0.4 + (1 - s["fatigue"] / 100) * 0.3 + 0.3,
                "forecast": self.brain.consciousness / 100 * 0.3 + self.tertium.hyperconsciousness / 100 * 0.4 + (1 - s["fatigue"] / 100) * 0.3,
                "rest": s["fatigue"] / 100 * 0.7 + s["pain"] / 100 * 0.2 + (100 - s["energy"]) / 100 * 0.1,
                "regulate": s["pain"] / 100 * 0.5 + (100 - s["safety"]) / 100 * 0.5,
            }
            actions = list(scores.keys())
            weights = [max(0.02, scores[a] + self.rng.uniform(0, 0.1)) for a in actions]
            total = sum(weights)
            r = self.rng.random() * total
            acc = 0
            for a, w in zip(actions, weights):
                acc += w
                if r <= acc: return a
            return actions[-1]
        except Exception:
            return "observe"

    def set_backtest_result(self, result):
        self.backtest_result = result

    def tick(self, market_features):
        try:
            self.age += 1
            self.last_features = market_features
            self.action = self.choose_action(market_features)
            self.body.update(self.action)
            prediction_error = self.predictor.update(market_features, self.brain.phi)

            reward_signal = 0.0
            if self.action in ("forecast", "analyze_deep") and market_features:
                pred = self.oracle.forecast(
                    market_features, self, horizon_candles=10, horizon_time_minutes=15
                )
                if pred:
                    self.last_prediction = pred
                    self.prediction_log.append(pred)
                    reward_signal = pred["best_confidence"] * 2.0 - 0.5
                    self.add_log(
                        "پیش‌بینی",
                        f"{ACTION_FA[pred['best_scenario']]} به {pred['best_target']:.2f} "
                        f"({pred['best_move_pct']:+.2f}٪) اعتماد {pred['best_confidence'] * 100:.0f}٪ | "
                        f"BPM {self.heart.bpm:.0f}"
                    )

            neuromodulators = self.make_neuromodulators(reward_signal)
            binary_pred = self.last_prediction.get("binary_prediction") if self.last_prediction else None

            self.last_module_activity = self.brain.step(
                self.body.signals, market_features, neuromodulators,
                self.action, prediction_error,
                self.tertium.hyperconsciousness / 100.0,
                binary_pred=binary_pred
            )

            self.self_model.update(
                self.body.signals, self.brain.consciousness,
                self.brain.ignition, prediction_error
            )
            self.tertium.update(self, market_features, self.last_prediction, self.backtest_result)

            if market_features:
                vec = self.episodic.vector(market_features, self.brain.consciousness, self.brain.ignition)
                recurrence = self.episodic.recurrence_count(vec, threshold=0.30)
                self.tertium.eternal_recurrence = recurrence

                importance = clamp(
                    abs(reward_signal) * 0.15 + self.brain.ignition * 0.40
                    + self.tertium.hyperconsciousness / 300.0
                )
                pred_scenario = self.last_prediction["best_scenario"] if self.last_prediction else "none"
                pred_conf = self.last_prediction["best_confidence"] if self.last_prediction else 0.0

                self.episodic.add(
                    vec, self.action, market_features["price"],
                    pred_scenario, pred_conf, importance
                )

                if recurrence > 2 and self.age % 10 == 0:
                    self.add_log("بازگشت ابدی", f"{recurrence} الگوی مشابه بازار.")

            if self.age % 3 == 0:
                self.add_thought(self.tertium.insight)

        except Exception as e:
            self.add_log("خطا", f"خطای سیستمی: {str(e)[:80]}")


# ============================================================
# Bybit Feed Thread
# ============================================================

class BybitFeed(threading.Thread):
    def __init__(self, organism, backtester_thread, symbol="BTCUSDT", interval="15", category="linear"):
        super().__init__(daemon=True)
        self.organism = organism
        self.backtester_thread = backtester_thread
        self.symbol = symbol
        self.interval = interval
        self.category = category
        self.latest_df = pd.DataFrame()
        self.latest_features = None
        self.status = "در حال اتصال..."
        self.last_price = 0.0
        self.last_update = None

    def run(self):
        time.sleep(2)
        while True:
            try:
                df = get_klines(self.symbol, self.interval, self.category, limit=500)
                if df.empty:
                    self.status = "❌ خطا در دریافت داده"
                    time.sleep(5)
                    continue

                self.latest_df = df
                self.last_price = float(df["close"].iloc[-1])
                self.last_update = datetime.now()

                features = MarketPerception.extract(df)
                self.latest_features = features
                self.status = f"🟢 متصل — {self.last_price:.2f}"

                # ارسال df به backtester thread
                self.backtester_thread.set_df(df)

                # دریافت نتیجه backtest و تزریق به organism
                bt_result = self.backtester_thread.backtester.get_result()
                if bt_result:
                    self.organism.set_backtest_result(bt_result)

                self.organism.tick(features)

                interval_minutes = {"1": 1, "3": 3, "5": 5, "15": 15, "30": 30,
                                    "60": 60, "240": 240, "D": 1440}.get(self.interval, 15)
                sleep_time = max(3, interval_minutes * 60 // 4)
                time.sleep(sleep_time)

            except Exception as e:
                self.status = f"⚠ خطا: {str(e)[:40]}"
                time.sleep(5)


# ============================================================
# Rendering
# ============================================================

BG, CARD, LINE, TXT, MUT = "#0b1220", "#121c30", "#23314d", "#e8ecf4", "#8fa3c0"
GOLD, UP, DN = "#f0b90b", "#16a085", "#e74c3c"

SCENARIO_COLORS = {"bull": UP, "bear": DN, "base": MUT}


def build_candle_chart(org, feed):
    """چارت کندل با مسیرهای backtest (به جای EMA)."""
    df = feed.latest_df
    if df.empty:
        fig = go.Figure(layout=dict(
            paper_bgcolor=BG, plot_bgcolor=CARD,
            annotations=[dict(text="در انتظار داده بازار...", x=0.5, y=0.5, showarrow=False,
                              font=dict(color=MUT, size=14))],
        ))
        return fig

    fig = go.Figure(data=[go.Candlestick(
        x=df["ts"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color=UP, decreasing_line_color=DN, name=feed.symbol,
    )])

    # === Backtest Path Overlays ===
    bt = org.backtest_result
    if bt and bt.get("path"):
        path = bt["path"]

        # مسیرهای درست (سبز) و نادرست (قرمز)
        correct_paths = [p for p in path if p["correct"]]
        wrong_paths = [p for p in path if not p["correct"]]

        # خطوط پیش‌بینی درست
        if correct_paths:
            for p in correct_paths[-30:]:  # آخرین 30 تا برای شلوغ نشدن
                fig.add_trace(go.Scatter(
                    x=[p["time_pred"], p["time_future"]],
                    y=[p["price_at_pred"], p["price_future"]],
                    mode="lines",
                    line=dict(color=UP, width=1, dash="dot"),
                    opacity=0.4,
                    showlegend=False,
                    hoverinfo="skip",
                ))

        # خطوط پیش‌بینی نادرست
        if wrong_paths:
            for p in wrong_paths[-30:]:
                fig.add_trace(go.Scatter(
                    x=[p["time_pred"], p["time_future"]],
                    y=[p["price_at_pred"], p["price_future"]],
                    mode="lines",
                    line=dict(color=DN, width=1, dash="dot"),
                    opacity=0.4,
                    showlegend=False,
                    hoverinfo="skip",
                ))

        # نقاط پیش‌بینی درست (سبز توپر)
        if correct_paths:
            fig.add_trace(go.Scatter(
                x=[p["time_pred"] for p in correct_paths],
                y=[p["price_at_pred"] for p in correct_paths],
                mode="markers",
                marker=dict(size=6, color=UP, symbol="triangle-up",
                           line=dict(color="#ffffff", width=1)),
                name=f"✓ پیش‌بینی درست ({len(correct_paths)})",
                hovertemplate=(
                    "پیش‌بینی درست ✓<br>"
                    "زمان: %{x}<br>"
                    "قیمت: %{y:.2f}<extra></extra>"
                ),
            ))

        # نقاط پیش‌بینی نادرست (قرمز)
        if wrong_paths:
            fig.add_trace(go.Scatter(
                x=[p["time_pred"] for p in wrong_paths],
                y=[p["price_at_pred"] for p in wrong_paths],
                mode="markers",
                marker=dict(size=6, color=DN, symbol="triangle-down",
                           line=dict(color="#ffffff", width=1)),
                name=f"✗ پیش‌بینی نادرست ({len(wrong_paths)})",
                hovertemplate=(
                    "پیش‌بینی نادرست ✗<br>"
                    "زمان: %{x}<br>"
                    "قیمت: %{y:.2f}<extra></extra>"
                ),
            ))

    # === Live prediction arrow ===
    pred = org.last_prediction
    if pred and org.last_features:
        current_time = df["ts"].iloc[-1]
        current_price = org.last_features["price"]
        target_time = pd.Timestamp(pred["target_time"])

        for scenario_name, scenario in pred["scenarios"].items():
            target_price = scenario["target"]
            confidence = scenario["confidence"]
            color = SCENARIO_COLORS.get(scenario_name, MUT)
            is_best = (scenario_name == pred["best_scenario"])

            fig.add_trace(go.Scatter(
                x=[current_time, target_time],
                y=[current_price, target_price],
                mode="lines+markers",
                line=dict(
                    color=color,
                    width=2 + confidence * 4 if is_best else 1 + confidence * 2,
                    dash="solid" if is_best else "dash",
                ),
                marker=dict(
                    symbol="arrow",
                    size=14 + confidence * 10 if is_best else 10 + confidence * 6,
                    color=color,
                ),
                name=f"🔮 {scenario_name}: {target_price:.2f} ({confidence * 100:.0f}٪)",
                hovertemplate=(
                    f"🔮 سناریو: {scenario_name}<br>"
                    f"قیمت هدف: {target_price:.2f}<br>"
                    f"زمان: {target_time.strftime('%H:%M')}<br>"
                    f"اعتماد: {confidence * 100:.0f}٪<extra></extra>"
                ),
            ))

            move_pct = (target_price - current_price) / current_price * 100
            fig.add_annotation(
                x=target_time, y=target_price,
                text=f"{scenario_name}<br>{target_price:.2f}<br>{move_pct:+.2f}٪",
                showarrow=True, arrowhead=2,
                ax=30 if scenario_name == "bull" else (-30 if scenario_name == "bear" else 0),
                ay=-40, bgcolor=CARD, bordercolor=color, borderwidth=2,
                font=dict(color=color, size=10),
            )

    wr_text = f"Win Rate: {bt['win_rate']:.1f}٪" if bt and bt.get("total_decisive", 0) > 0 else "Backtest در حال اجرا..."

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG, plot_bgcolor=CARD,
        font=dict(color=TXT, family="Tahoma"),
        xaxis=dict(gridcolor=LINE, rangeslider_visible=False),
        yaxis=dict(gridcolor=LINE),
        margin=dict(l=10, r=10, t=50, b=10),
        title=dict(
            text=f"🔮 {feed.symbol} | 💓 {org.heart.bpm:.0f} BPM | 📊 {wr_text}",
            x=0.5, font=dict(color=GOLD, size=15, family="Tahoma"),
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                   bgcolor="rgba(0,0,0,0.5)"),
    )
    return fig


def build_ecg_chart(org):
    fig = go.Figure()
    x = list(org.heart.ecg_x)[-400:]
    y = list(org.heart.ecg)[-400:]
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color="#ff5f7a", width=1.5)))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
        font=dict(color=TXT, size=10, family="Tahoma"), height=220,
        margin=dict(l=30, r=10, t=30, b=10),
        title=dict(text=f"💓 ECG | انسجام: {org.heart.coherence:.0f}٪", x=0.5, font=dict(color=GOLD, size=12)),
        xaxis=dict(visible=False), yaxis=dict(range=[-1, 1.3], showgrid=False, visible=False),
    )
    return fig


def build_backtest_stats_chart(org):
    """نمودار P&L تجمعی از backtest."""
    fig = go.Figure()
    bt = org.backtest_result

    if not bt or not bt.get("cumulative_pnl"):
        fig.add_annotation(text="Backtest در حال اجرا...", x=0.5, y=0.5,
                          showarrow=False, font=dict(color=MUT, size=12))
        fig.update_layout(
            template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
            font=dict(color=TXT, size=10, family="Tahoma"), height=220,
            margin=dict(l=30, r=10, t=30, b=10),
            xaxis=dict(visible=False), yaxis=dict(visible=False),
        )
        return fig

    pnl_data = bt["cumulative_pnl"]
    x = [p["time"] for p in pnl_data]
    y = [p["pnl"] for p in pnl_data]

    color = UP if y[-1] >= 0 else DN

    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines",
        line=dict(color=color, width=2),
        fill="tozeroy",
        fillcolor=color.replace(")", ", 0.2)").replace("rgb", "rgba") if "rgb" in color else color,
        name="P&L تجمعی",
    ))

    # خط صفر
    fig.add_hline(y=0, line_dash="dash", line_color=MUT, line_width=1)

    fig.update_layout(
        template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
        font=dict(color=TXT, size=10, family="Tahoma"), height=220,
        margin=dict(l=30, r=10, t=30, b=10),
        title=dict(
            text=f"📊 P&L تجمعی | {bt['win_rate']:.1f}٪ Win Rate | "
                 f"نهایی: {bt['final_pnl']:+.2f}٪",
            x=0.5, font=dict(color=GOLD, size=12)
        ),
        xaxis=dict(gridcolor=LINE, showgrid=False),
        yaxis=dict(gridcolor=LINE, title="P&L ٪"),
    )
    return fig


def build_binary_seq_chart(org, feed):
    fig = go.Figure()
    if org.last_features and "binary_seq" in org.last_features:
        seq = org.last_features["binary_seq"][-64:]
        x = list(range(len(seq)))
        colors = [UP if b == 1 else DN for b in seq]
        fig.add_trace(go.Bar(
            x=x, y=[1] * len(seq), marker_color=colors,
            name="کندل‌ها (1=سبز، 0=قرمز)", width=0.8,
        ))
        if org.last_prediction and "binary_prediction" in org.last_prediction:
            bp = org.last_prediction["binary_prediction"]
            heart_bits = bp.get("heart_bits", [])
            if heart_bits:
                fig.add_trace(go.Scatter(
                    x=list(range(len(heart_bits))),
                    y=[1.2] * len(heart_bits),
                    mode="markers",
                    marker=dict(size=12, color=[GOLD if b == 1 else MUT for b in heart_bits],
                               symbol="diamond"),
                    name="شهود قلبی",
                ))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
        font=dict(color=TXT, size=10, family="Tahoma"), height=220,
        margin=dict(l=30, r=10, t=30, b=10),
        title=dict(text="🔢 دنباله باینری کندل‌ها و شهود قلبی", x=0.5, font=dict(color=GOLD, size=12)),
        xaxis=dict(title="کندل", gridcolor=LINE),
        yaxis=dict(range=[0, 1.5], gridcolor=LINE),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def render_header(org, feed):
    brain = org.brain
    tertium = org.tertium
    return html.Div(style={"display": "flex", "gap": "16px", "flexWrap": "wrap", "fontSize": "12px"}, children=[
        html.Span("🔮 نوستراداموس", style={"color": GOLD, "fontWeight": "bold"}),
        html.Span(f"نماد: {feed.symbol}"),
        html.Span(f"قیمت: {feed.last_price:.2f}"),
        html.Span(f"💓 BPM: {org.heart.bpm:.0f}", style={"color": "#ff5f7a"}),
        html.Span(f"آگاهی: {brain.consciousness:.0f}٪"),
        html.Span(f"Φ: {brain.phi * 100:.0f}٪"),
        html.Span(f"فراآگاهی: {tertium.hyperconsciousness:.0f}٪"),
        html.Span(f"عمل: {ACTION_FA.get(org.action, org.action)}"),
        html.Span(f"وضعیت: {feed.status}"),
    ])


def render_vitals(org):
    """کارت‌های وضعیت حیاتی. با استفاده صحیح از 'tertium'."""
    s = org.body.signals
    brain = org.brain
    tertium = org.tertium  # <-- این خط مهم است!
    pred = org.last_prediction
    bt = org.backtest_result

    cards = [
        ("💓 قلب", f"{org.heart.bpm:.0f} BPM", f"انسجام: {org.heart.coherence:.0f}٪", "#ff5f7a"),
        ("آگاهی", f"{brain.consciousness:.0f}٪", f"Φ: {brain.phi * 100:.0f}٪", "#00e5ff"),
        ("فراآگاهی", f"{tertium.hyperconsciousness:.0f}٪",
         f"خودبه‌خودی: {tertium.self_remembering * 100:.0f}٪", "#b388ff"),
        ("انرژی", f"{s['energy']:.0f}٪", f"گلوکز: {s['glucose']:.0f}٪", "#ffd166"),
        ("امنیت", f"{s['safety']:.0f}٪", f"درد: {s['pain']:.0f}٪", "#00ff88"),
        ("خستگی", f"{s['fatigue']:.0f}٪", f"تازگی: {s['novelty']:.0f}٪", "#ff9f43"),
    ]

    if pred:
        direction = "📈" if pred["best_move_pct"] > 0 else "📉" if pred["best_move_pct"] < 0 else "➡️"
        cards.append((
            "پیش‌بینی",
            f"{direction} {pred['best_move_pct']:+.2f}٪",
            f"{ACTION_FA.get(pred['best_scenario'], pred['best_scenario'])} — {pred['best_confidence'] * 100:.0f}٪",
            SCENARIO_COLORS.get(pred["best_scenario"], MUT),
        ))

    if bt and bt.get("total_decisive", 0) > 0:
        wr = bt["win_rate"]
        w = bt["wins"]
        l = bt["losses"]
        wr_color = UP if wr > 55 else (GOLD if wr > 45 else DN)
        cards.append((
            "📊 Win Rate",
            f"{wr:.1f}٪",
            f"{w}W / {l}L | {bt['total']} کل",
            wr_color,
        ))

    return [
        html.Div(style={
            "backgroundColor": CARD, "border": f"1px solid {LINE}",
            "borderRadius": "10px", "padding": "10px", "minHeight": "80px",
        }, children=[
            html.Div(title, style={"color": MUT, "fontSize": "11px"}),
            html.Div(value, style={"color": color, "fontSize": "17px", "fontWeight": "bold"}),
            html.Div(sub, style={"color": MUT, "fontSize": "10px"}),
        ]) for title, value, sub, color in cards
    ]


def render_modules(org):
    fig = go.Figure()
    acts = org.last_module_activity
    if acts:
        names = list(acts.keys())
        values = list(acts.values())
        colors = [
            "#00e5ff" if n == "market" else
            "#b388ff" if n == "forecast" else
            "#ffd166" if n == "memory" else
            "#ff9f43" if n == "global" else MUT for n in names
        ]
        fig.add_trace(go.Bar(x=names, y=values, marker_color=colors))
        fig.update_yaxes(range=[0, 1])
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
        font=dict(color=TXT, size=10, family="Tahoma"), height=240,
        margin=dict(l=30, r=10, t=30, b=10),
        title=dict(text="ماژول‌های مغز", x=0.5, font=dict(color=GOLD, size=12)),
    )
    return fig


def render_predictions(org):
    pred = org.last_prediction
    children = [html.H5("🎯 سناریوهای پیش‌بینی", style={"color": GOLD, "fontSize": "14px", "margin": "8px 0"})]

    if not pred:
        children.append(html.Div("در انتظار اولین پیش‌بینی...", style={"color": MUT}))
        return html.Div(children)

    for name, scenario in pred["scenarios"].items():
        color = SCENARIO_COLORS.get(name, MUT)
        move_pct = scenario["move_pct"]
        target = scenario["target"]
        confidence = scenario["confidence"]
        direction = "📈" if move_pct > 0 else "📉" if move_pct < 0 else "➡️"
        is_best = (name == pred["best_scenario"])

        children.append(html.Div(style={
            "backgroundColor": BG,
            "border": f"2px solid {color}" if is_best else f"1px solid {LINE}",
            "borderRadius": "8px", "padding": "10px", "marginBottom": "8px",
        }, children=[
            html.Div(style={"display": "flex", "justifyContent": "space-between", "marginBottom": "6px"}, children=[
                html.Span(
                    f"{direction} {ACTION_FA.get(name, name)}" + (" ★" if is_best else ""),
                    style={"color": color, "fontWeight": "bold", "fontSize": "13px"}
                ),
                html.Span(f"{confidence * 100:.0f}٪ اعتماد", style={"color": MUT, "fontSize": "11px"}),
            ]),
            html.Div(f"قیمت هدف: {target:.2f}", style={"color": TXT, "fontSize": "12px"}),
            html.Div(f"حرکت: {move_pct:+.2f}٪", style={"color": color, "fontSize": "11px"}),
            html.Div(style={
                "marginTop": "6px", "height": "5px",
                "backgroundColor": BG, "borderRadius": "3px", "overflow": "hidden",
            }, children=[html.Div(style={
                "width": f"{confidence * 100:.0f}%", "height": "100%", "backgroundColor": color,
            })]),
        ]))

    bp = pred.get("binary_prediction")
    if bp:
        heart_bits = bp.get("heart_bits", [])
        heart_str = "".join(str(b) for b in heart_bits)
        pattern = bp.get("pattern_match", "نامشخص")

        children.append(html.Div(style={
            "padding": "10px", "backgroundColor": BG,
            "border": f"1px solid {GOLD}", "borderRadius": "8px", "marginTop": "8px",
        }, children=[
            html.Div("💓 تحلیل قلبی-مغزی", style={"color": GOLD, "fontSize": "12px",
                                                  "fontWeight": "bold", "marginBottom": "6px"}),
            html.Div(f"احتمال صعودی: {bp.get('bullish_prob', 0.5) * 100:.1f}٪", style={"color": UP, "fontSize": "11px"}),
            html.Div(f"احتمال نزولی: {bp.get('bearish_prob', 0.5) * 100:.1f}٪", style={"color": DN, "fontSize": "11px"}),
            html.Div(f"الگوی تطبیقی: {pattern or 'نامشخص'}", style={"color": TXT, "fontSize": "11px", "marginTop": "4px"}),
            html.Div(f"بیت‌های شهودی: {heart_str}", style={"color": MUT, "fontSize": "10px", "marginTop": "4px"}),
        ]))

    children.append(html.Div(style={
        "marginTop": "10px", "padding": "8px", "borderLeft": f"3px solid {GOLD}",
        "backgroundColor": BG, "borderRadius": "6px",
    }, children=[
        html.Div(f"قیمت انتظاری: {pred['expected_price']:.2f}", style={"color": GOLD, "fontSize": "12px"}),
        html.Div(f"حرکت انتظاری: {pred['expected_move_pct']:+.2f}٪", style={"color": TXT, "fontSize": "11px"}),
        html.Div(
            f"افق زمانی: {pred['target_time'].strftime('%H:%M')} ({pred['horizon_candles']} کندل)",
            style={"color": MUT, "fontSize": "10px"}
        ),
    ]))

    return html.Div(children)


def render_backtest_stats(org):
    """پنل آمار backtest."""
    bt = org.backtest_result
    children = [html.H5("📊 آمار Backtest Walk-Forward", style={"color": GOLD, "fontSize": "14px", "margin": "8px 0"})]

    if not bt:
        children.append(html.Div("⏳ Backtest در حال راه‌اندازی...", style={"color": MUT}))
        return html.Div(children)

    if bt.get("error"):
        children.append(html.Div(f"❌ خطا: {bt['error']}", style={"color": DN}))
        return html.Div(children)

    total = bt.get("total", 0)
    decisive = bt.get("total_decisive", 0)
    wins = bt.get("wins", 0)
    losses = bt.get("losses", 0)
    neutral = bt.get("neutral", 0)
    win_rate = bt.get("win_rate", 0)
    final_pnl = bt.get("final_pnl", 0)

    wr_color = UP if win_rate > 55 else (GOLD if win_rate > 45 else DN)
    pnl_color = UP if final_pnl > 0 else DN

    children.append(html.Div(style={
        "padding": "12px", "backgroundColor": BG,
        "border": f"2px solid {wr_color}", "borderRadius": "8px", "marginBottom": "10px",
    }, children=[
        html.Div(style={"display": "flex", "justifyContent": "space-between", "marginBottom": "8px"}, children=[
            html.Span("Win Rate", style={"color": MUT, "fontSize": "13px"}),
            html.Span(f"{win_rate:.1f}٪", style={"color": wr_color, "fontSize": "20px", "fontWeight": "bold"}),
        ]),
        html.Div(style={
            "height": "8px", "backgroundColor": CARD, "borderRadius": "4px", "overflow": "hidden",
        }, children=[html.Div(style={
            "width": f"{min(100, win_rate):.0f}%", "height": "100%", "backgroundColor": wr_color,
        })]),
    ]))

    stats_rows = [
        ("کل پیش‌بینی‌ها", str(total), TXT),
        ("تصمیم‌های قاطع", str(decisive), TXT),
        ("بردها", str(wins), UP),
        ("باخت‌ها", str(losses), DN),
        ("خنثی", str(neutral), MUT),
        ("P&L تجمعی", f"{final_pnl:+.2f}٪", pnl_color),
    ]

    for label, value, color in stats_rows:
        children.append(html.Div(style={
            "display": "flex", "justifyContent": "space-between",
            "padding": "4px 0", "borderBottom": f"1px solid {LINE}",
        }, children=[
            html.Span(label, style={"color": MUT, "fontSize": "11px"}),
            html.Span(value, style={"color": color, "fontSize": "12px", "fontWeight": "bold"}),
        ]))

    children.append(html.Div(style={
        "marginTop": "10px", "padding": "8px", "backgroundColor": CARD, "borderRadius": "6px",
        "fontSize": "10px", "color": MUT, "lineHeight": "1.5",
    }, children=[
        "ℹ️ این backtest ",
        html.Strong("Walk-Forward", style={"color": GOLD}),
        " است: در هر نقطه فقط از داده‌های ",
        html.Strong("گذشته", style={"color": UP}),
        " استفاده شده (بدون Lookahead). هر پیش‌بینی با 10 کندل بعد سنجیده می‌شود.",
    ]))

    return html.Div(children)


def render_insight(org):
    return html.Div([
        html.H5("🌌 بینش فرابعدی", style={"color": GOLD, "fontSize": "14px", "margin": "8px 0"}),
        html.Div(org.tertium.insight, style={
            "padding": "10px", "backgroundColor": BG,
            "border": f"1px solid {LINE}", "borderRadius": "8px",
            "color": TXT, "fontSize": "12px", "lineHeight": "1.7",
            "whiteSpace": "pre-line",
        }),
    ])


def render_thoughts(org):
    thoughts = list(org.thoughts)[-8:][::-1]
    children = [html.H5("💭 اندیشه‌ها", style={"color": "#00e5ff", "fontSize": "14px", "margin": "8px 0"})]
    if not thoughts:
        children.append(html.Div("...", style={"color": MUT}))
    else:
        for t in thoughts:
            children.append(html.Div(style={
                "padding": "6px 8px", "borderLeft": "2px solid #00e5ff",
                "backgroundColor": BG, "borderRadius": "4px", "marginBottom": "4px",
                "fontSize": "11px", "lineHeight": "1.6",
            }, children=[
                html.Span(t["time"], style={"color": MUT, "fontSize": "9px"}),
                html.Br(),
                html.Span(t["text"], style={"color": TXT, "whiteSpace": "pre-line"}),
            ]))
    return html.Div(children, style={"height": "300px", "overflowY": "auto"})


def render_logs(org):
    items = list(org.logs)[-12:][::-1]
    children = [html.H5("📜 رویدادها", style={"color": "#9fd0ff", "fontSize": "14px", "margin": "8px 0"})]
    if not items:
        children.append(html.Div("...", style={"color": MUT}))
    else:
        for item in items:
            children.append(html.Div(style={
                "padding": "4px 8px", "borderLeft": "2px solid #9fd0ff",
                "backgroundColor": BG, "borderRadius": "4px", "marginBottom": "3px", "fontSize": "10px",
            }, children=[
                html.Span(f"[{item['time']}] {item['kind']}: {item['text']}", style={"color": TXT}),
            ]))
    return html.Div(children, style={"height": "280px", "overflowY": "auto"})


# ============================================================
# Dash App
# ============================================================

app = Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])
app.title = "🔮 Nostradamus — Backtest Edition"
server = app.server

# Initialize backtester and organism
BACKTESTER = Backtester(window_size=10, min_history=30, step=2)
BACKTESTER_THREAD = BacktesterThread(BACKTESTER)
BACKTESTER_THREAD.start()

ORGANISM = NostradamusOrganism()

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_CATEGORY = "linear"
DEFAULT_INTERVAL = "15"

CATEGORY_OPTS = [{"label": v, "value": v} for v in ["linear", "spot", "inverse"]]
INTERVAL_OPTS = [{"label": lbl, "value": val} for lbl, val in [
    ("1m", "1"), ("3m", "3"), ("5m", "5"), ("15m", "15"),
    ("30m", "30"), ("1h", "60"), ("4h", "240"), ("1D", "D"),
]]

app.layout = html.Div([
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([html.Label("نماد:", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="symbol-input", value=DEFAULT_SYMBOL, type="text",
                           style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
        dbc.Col([html.Label("بازار:", style={"fontSize": 12, "color": MUT}),
                 dcc.Dropdown(id="category-dropdown", value=DEFAULT_CATEGORY, clearable=False, options=CATEGORY_OPTS)], md=2),
        dbc.Col([html.Label("تایم‌فریم:", style={"fontSize": 12, "color": MUT}),
                 dcc.Dropdown(id="interval-dropdown", value=DEFAULT_INTERVAL, clearable=False, options=INTERVAL_OPTS)], md=2),
        dbc.Col(dbc.Button("🔄 اعمال", id="apply-btn", color="warning", className="mt-3",
                           style={"fontWeight": "bold", "color": "#0b1220", "width": "100%"}), md=2),
        dbc.Col(dbc.Button("🔮 پیش‌بینی فوری", id="forecast-btn", color="success", className="mt-3",
                           style={"fontWeight": "bold", "width": "100%"}), md=2),
        dbc.Col(html.Div(id="conn-status", style={"color": MUT, "fontSize": 11, "marginTop": 22, "textAlign": "center"}), md=2),
    ])), style={"maxWidth": 1600, "margin": "10px auto"}),

    html.Div(id="header-info", style={
        "maxWidth": 1600, "margin": "0 auto 10px auto", "padding": "10px",
        "backgroundColor": CARD, "border": f"1px solid {LINE}", "borderRadius": "10px",
    }),

    html.Div(id="vital-cards", style={
        "display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(160px, 1fr))",
        "gap": "8px", "maxWidth": 1600, "margin": "0 auto 10px auto",
    }),

    # چارت اصلی با backtest overlays
    dbc.Row([
        dbc.Col(dcc.Graph(id="candle-chart", style={"height": "65vh"}, config={"displaylogo": False}), width=8),
        dbc.Col([
            html.Div(id="predictions-panel", style={"marginBottom": "10px"}),
            html.Div(id="insight-panel"),
        ], width=4),
    ], style={"maxWidth": 1600, "margin": "0 auto"}),

    # ردیف دوم: ECG، P&L تجمعی، ماژول‌ها
    dbc.Row([
        dbc.Col(dcc.Graph(id="ecg-graph", style={"height": "220px"}), width=4),
        dbc.Col(dcc.Graph(id="pnl-graph", style={"height": "220px"}), width=4),
        dbc.Col(dcc.Graph(id="modules-graph", style={"height": "220px"}), width=4),
    ], style={"maxWidth": 1600, "margin": "10px auto"}),

    # ردیف سوم: آمار backtest، دنباله باینری
    dbc.Row([
        dbc.Col(html.Div(id="backtest-stats-panel"), width=6),
        dbc.Col(dcc.Graph(id="binary-seq-graph", style={"height": "280px"}), width=6),
    ], style={"maxWidth": 1600, "margin": "10px auto"}),

    # ردیف چهارم: اندیشه‌ها و لاگ
    dbc.Row([
        dbc.Col(html.Div(id="thoughts-panel"), width=6),
        dbc.Col(html.Div(id="logs-panel"), width=6),
    ], style={"maxWidth": 1600, "margin": "10px auto"}),

    dcc.Store(id="config-store", data={
        "symbol": DEFAULT_SYMBOL, "category": DEFAULT_CATEGORY, "interval": DEFAULT_INTERVAL,
    }),
    dcc.Interval(id="update-interval", interval=3000, n_intervals=0),
], style={"background": BG, "minHeight": "100vh", "padding": "10px"})


FEED = BybitFeed(ORGANISM, BACKTESTER_THREAD, DEFAULT_SYMBOL, DEFAULT_INTERVAL, DEFAULT_CATEGORY)
FEED.start()


@app.callback(
    Output("config-store", "data"),
    Input("apply-btn", "n_clicks"),
    State("symbol-input", "value"),
    State("category-dropdown", "value"),
    State("interval-dropdown", "value"),
    prevent_initial_call=True,
)
def apply_config(n, symbol, category, interval):
    symbol = (symbol or DEFAULT_SYMBOL).upper()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL
    FEED.symbol = symbol
    FEED.category = category
    FEED.interval = interval
    ORGANISM.add_log("پیکربندی", f"{symbol} | {category} | {interval}m")
    return {"symbol": symbol, "category": category, "interval": interval}


@app.callback(
    Output("candle-chart", "figure"),
    Output("ecg-graph", "figure"),
    Output("pnl-graph", "figure"),
    Output("binary-seq-graph", "figure"),
    Output("conn-status", "children"),
    Input("update-interval", "n_intervals"),
    Input("forecast-btn", "n_clicks"),
    State("config-store", "data"),
)
def update_charts(n_int, n_forecast, config):
    if ctx.triggered_id == "forecast-btn" and FEED.latest_features:
        try:
            ORGANISM.action = "forecast"
            ORGANISM.body.update("forecast")
            pred = ORGANISM.oracle.forecast(FEED.latest_features, ORGANISM,
                                           horizon_candles=10, horizon_time_minutes=15)
            if pred:
                ORGANISM.last_prediction = pred
                ORGANISM.prediction_log.append(pred)
                ORGANISM.add_log(
                    "پیش‌بینی فوری",
                    f"{ACTION_FA[pred['best_scenario']]} به {pred['best_target']:.2f} "
                    f"({pred['best_move_pct']:+.2f}٪) اعتماد {pred['best_confidence'] * 100:.0f}٪"
                )
        except Exception:
            pass

    fig_candle = build_candle_chart(ORGANISM, FEED)
    fig_ecg = build_ecg_chart(ORGANISM)
    fig_pnl = build_backtest_stats_chart(ORGANISM)
    fig_binary = build_binary_seq_chart(ORGANISM, FEED)
    return fig_candle, fig_ecg, fig_pnl, fig_binary, FEED.status


@app.callback(
    Output("header-info", "children"),
    Output("vital-cards", "children"),
    Output("modules-graph", "figure"),
    Output("predictions-panel", "children"),
    Output("backtest-stats-panel", "children"),
    Output("insight-panel", "children"),
    Output("thoughts-panel", "children"),
    Output("logs-panel", "children"),
    Input("update-interval", "n_intervals"),
)
def update_panels(n):
    return (
        render_header(ORGANISM, FEED),
        render_vitals(ORGANISM),
        render_modules(ORGANISM),
        render_predictions(ORGANISM),
        render_backtest_stats(ORGANISM),
        render_insight(ORGANISM),
        render_thoughts(ORGANISM),
        render_logs(ORGANISM),
    )


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8060, use_reloader=False)