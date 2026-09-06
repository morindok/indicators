# -*- coding: utf-8 -*-
"""
🌌 Temporal Resonance Engine v7
=========================================================
{Morindok}
"""

import math
import os
import time
import sqlite3
import webbrowser
import threading
from datetime import datetime, timezone, timedelta

import requests
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import dash
from dash import dcc, html, Input, Output, State, ALL, ctx
import dash_bootstrap_components as dbc

# ==============================================================================
# 0) تنظیمات
# ==============================================================================
BG = "#030308"
CARD = "#0a0a18"
CARD2 = "#101025"
LINE = "#252545"
TXT = "#e8e8ff"
MUT = "#7a7aa8"
GOLD = "#ffd700"
UP = "#00ffcc"
DN = "#ff2266"
BLUE = "#00aaff"
PURPLE = "#bb66ff"
CYAN = "#00ffff"

FONT_FAMILY = "Vazirmatn, Tahoma, Arial, sans-serif"
DB_PATH = "signals_database.db"

DEFAULT_BALANCE = 500.0

# ==============================================================================
# پروفایل حالت‌های معاملاتی
# ==============================================================================
TRADING_MODES = {
    "conservative": {
        "name": "🛡️ محافظه‌کار",
        "risk_pct": 0.01,
        "max_leverage": 10.0,
        "min_leverage": 2.0,
        "max_position_pct": 0.20,
        "max_margin_pct": 0.15,
        "sl_atr_mult": 2.0,
        "tp_atr_mult": 3.0,
        "min_sl_pct": 0.005,
        "min_tp_pct": 0.015,
    },
    "normal": {
        "name": "⚖️ معمولی",
        "risk_pct": 0.02,
        "max_leverage": 25.0,
        "min_leverage": 2.0,
        "max_position_pct": 0.40,
        "max_margin_pct": 0.25,
        "sl_atr_mult": 1.5,
        "tp_atr_mult": 4.0,
        "min_sl_pct": 0.008,
        "min_tp_pct": 0.025,
    },
    "aggressive": {
        "name": "🔥 اگرسیو",
        "risk_pct": 0.05,
        "max_leverage": 50.0,
        "min_leverage": 5.0,
        "max_position_pct": 0.50,
        "max_margin_pct": 0.30,
        "sl_atr_mult": 1.2,
        "tp_atr_mult": 6.0,
        "min_sl_pct": 0.008,
        "min_tp_pct": 0.03,
    },
}

TRADING_MODE_OPTIONS = [
    {"label": v["name"], "value": k}
    for k, v in TRADING_MODES.items()
]

SYMBOLS = {
    "BTCUSDT": {"name": "بیت‌کوین", "icon": "₿"},
    "ETHUSDT": {"name": "اتریوم", "icon": "Ξ"},
    "SOLUSDT": {"name": "سولانا", "icon": "◎"},
    "BNBUSDT": {"name": "بایننس کوین", "icon": "🔶"},
    "XRPUSDT": {"name": "ریپل", "icon": "✕"},
    "ADAUSDT": {"name": "کاردانو", "icon": "₳"},
    "DOGEUSDT": {"name": "دوج‌کوین", "icon": "Ð"},
    "AVAXUSDT": {"name": "آوالانچ", "icon": "🔺"},
    "DOTUSDT": {"name": "پولکادات", "icon": "●"},
    "LINKUSDT": {"name": "چین‌لینک", "icon": "⬡"},
    "MATICUSDT": {"name": "پالیگان", "icon": "🟣"},
    "LTCUSDT": {"name": "لایت‌کوین", "icon": "Ł"},
    "ATOMUSDT": {"name": "کاسماس", "icon": "⚛"},
    "UNIUSDT": {"name": "یونی‌سواپ", "icon": "🦄"},
    "APTUSDT": {"name": "آپتوس", "icon": "🅰"},
    "ARBUSDT": {"name": "آربیتروم", "icon": "🔵"},
    "OPUSDT": {"name": "آپتیمیسم", "icon": "🔴"},
    "NEARUSDT": {"name": "نیر", "icon": "Ⓝ"},
    "INJUSDT": {"name": "اینجکتیو", "icon": "💉"},
    "SUIUSDT": {"name": "سویی", "icon": "💧"},
    "XAUUSDT": {"name": "طلا", "icon": "🥇"},
}

SYMBOL_OPTIONS = [
    {"label": f"{v['icon']} {k.replace('USDT', '')} — {v['name']}", "value": k}
    for k, v in SYMBOLS.items()
]

TEMPORAL_CYCLES = [
    {"name": "روزانه", "period_hours": 24.0, "color": "#ffd700", "weight": 1.0},
    {"name": "نیم‌روز", "period_hours": 12.0, "color": "#00ffcc", "weight": 0.8},
    {"name": "شش‌ساعته", "period_hours": 6.0, "color": "#00aaff", "weight": 0.6},
    {"name": "سه‌ساعته", "period_hours": 3.0, "color": "#bb66ff", "weight": 0.5},
    {"name": "هفتگی", "period_hours": 168.0, "color": "#ff66aa", "weight": 1.2},
    {"name": "ماهانه", "period_hours": 720.0, "color": "#ffaa00", "weight": 1.0},
    {"name": "عطارد", "period_hours": 2111.3, "color": "#aaaaaa", "weight": 0.4},
    {"name": "زهره", "period_hours": 1401.0, "color": "#ffcc88", "weight": 0.5},
    {"name": "مریخ", "period_hours": 12.33, "color": "#ff6644", "weight": 0.7},
    {"name": "مشتری", "period_hours": 4.96, "color": "#ffaa66", "weight": 0.6},
    {"name": "زحل", "period_hours": 5.33, "color": "#ccaa66", "weight": 0.6},
]

BACKTEST_MIN_HISTORY = 200

# ==============================================================================
# 1) دیتابیس SQLite
# ==============================================================================
class SignalDatabase:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                direction INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                sl_price REAL NOT NULL,
                tp_price REAL NOT NULL,
                dollar_amount REAL NOT NULL,
                confidence REAL NOT NULL,
                score REAL NOT NULL,
                rr_ratio REAL NOT NULL,
                status TEXT DEFAULT 'open',
                exit_price REAL,
                exit_time TEXT,
                pnl REAL,
                pnl_pct REAL,
                exit_reason TEXT,
                interval TEXT,
                threshold REAL,
                leverage REAL DEFAULT 1.0,
                margin_used REAL DEFAULT 0.0,
                trading_mode TEXT DEFAULT 'normal'
            )
        """)
        conn.commit()
        for col in ["leverage", "margin_used", "trading_mode"]:
            try:
                default = "1.0" if col == "leverage" else ("0.0" if col == "margin_used" else "'normal'")
                cursor.execute(f"ALTER TABLE signals ADD COLUMN {col} {'REAL DEFAULT ' + default if col != 'trading_mode' else 'TEXT DEFAULT ' + default}")
            except sqlite3.OperationalError:
                pass
        conn.commit()
        conn.close()

    def save_signal(self, signal_data, interval, threshold):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO signals (created_at, symbol, direction, entry_price, sl_price, tp_price,
                                dollar_amount, confidence, score, rr_ratio, status, interval, threshold,
                                leverage, margin_used, trading_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)
        """, (
            signal_data["timestamp"],
            signal_data["symbol"],
            signal_data["signal"],
            signal_data["entry_price"],
            signal_data["sl_price"],
            signal_data["tp_price"],
            signal_data["dollar_amount"],
            signal_data["confidence"],
            signal_data["final_score"],
            signal_data["rr_ratio"],
            interval,
            threshold,
            signal_data.get("leverage", 1.0),
            signal_data.get("margin_used", 0.0),
            signal_data.get("trading_mode", "normal"),
        ))
        conn.commit()
        conn.close()

    def has_open_signal(self, symbol):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM signals WHERE symbol = ? AND status = 'open'", (symbol,))
        row = cursor.fetchone()
        conn.close()
        return row["cnt"] > 0

    def get_open_signals(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM signals WHERE status = 'open' ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_signal_by_id(self, signal_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM signals WHERE id = ?", (signal_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def close_signal(self, signal_id, exit_price, exit_time, pnl, pnl_pct, reason):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE signals SET status = 'closed_manual', exit_price = ?, exit_time = ?,
                pnl = ?, pnl_pct = ?, exit_reason = ? WHERE id = ?
        """, (exit_price, exit_time, pnl, pnl_pct, reason, signal_id))
        conn.commit()
        conn.close()

    def update_signal_result(self, signal_id, exit_price, exit_time, pnl, pnl_pct, status, reason):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE signals SET exit_price = ?, exit_time = ?, pnl = ?, pnl_pct = ?, status = ?, exit_reason = ?
            WHERE id = ?
        """, (exit_price, exit_time, pnl, pnl_pct, status, reason, signal_id))
        conn.commit()
        conn.close()

    def get_all_signals(self, limit=200):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_total_pnl(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(pnl), 0) as total FROM signals WHERE pnl IS NOT NULL AND status != 'open'")
        row = cursor.fetchone()
        conn.close()
        return row["total"] if row["total"] else 0.0

    def get_symbol_signals(self, symbol, limit=100):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM signals WHERE symbol = ? ORDER BY created_at DESC LIMIT ?", (symbol, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_symbol_stats(self, symbol):
        signals = self.get_symbol_signals(symbol, limit=1000)
        if not signals:
            return None

        total = len(signals)
        closed = [s for s in signals if s["status"] != "open"]
        open_count = total - len(closed)

        tp_count = sum(1 for s in closed if s["status"] == "tp_hit")
        sl_count = sum(1 for s in closed if s["status"] == "sl_hit")
        expired_count = sum(1 for s in closed if s["status"] == "expired")
        manual_count = sum(1 for s in closed if s["status"] == "closed_manual")

        pnls = [s["pnl"] for s in closed if s["pnl"] is not None]
        pnl_pcts = [s["pnl_pct"] for s in closed if s["pnl_pct"] is not None]
        total_pnl = sum(pnls) if pnls else 0.0

        wins = sum(1 for p in pnls if p > 0)
        losses = sum(1 for p in pnls if p <= 0)
        win_rate = (wins / len(pnls) * 100) if pnls else 0.0

        avg_pnl = total_pnl / len(pnls) if pnls else 0.0
        avg_pnl_pct = sum(pnl_pcts) / len(pnl_pcts) if pnl_pcts else 0.0
        best_trade = max(pnls) if pnls else 0.0
        worst_trade = min(pnls) if pnls else 0.0

        confidences = [s["confidence"] for s in signals if s["confidence"]]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        leverages = [s["leverage"] for s in signals if s.get("leverage")]
        avg_leverage = sum(leverages) / len(leverages) if leverages else 0.0

        cumulative_pnl = []
        running = 0.0
        for s in reversed(closed):
            if s["pnl"] is not None:
                running += s["pnl"]
                cumulative_pnl.append(running)

        long_count = sum(1 for s in signals if s["direction"] == 1)
        short_count = sum(1 for s in signals if s["direction"] == -1)

        long_closed = [s for s in closed if s["direction"] == 1 and s["pnl"] is not None]
        short_closed = [s for s in closed if s["direction"] == -1 and s["pnl"] is not None]
        long_wins = sum(1 for s in long_closed if s["pnl"] > 0)
        short_wins = sum(1 for s in short_closed if s["pnl"] > 0)
        long_win_rate = (long_wins / len(long_closed) * 100) if long_closed else 0.0
        short_win_rate = (short_wins / len(short_closed) * 100) if short_closed else 0.0

        return {
            "symbol": symbol, "total": total, "closed": len(closed), "open": open_count,
            "tp_count": tp_count, "sl_count": sl_count, "expired_count": expired_count,
            "manual_count": manual_count, "total_pnl": total_pnl,
            "wins": wins, "losses": losses, "win_rate": win_rate,
            "avg_pnl": avg_pnl, "avg_pnl_pct": avg_pnl_pct,
            "best_trade": best_trade, "worst_trade": worst_trade,
            "avg_confidence": avg_confidence, "avg_leverage": avg_leverage,
            "cumulative_pnl": cumulative_pnl,
            "long_count": long_count, "short_count": short_count,
            "long_win_rate": long_win_rate, "short_win_rate": short_win_rate,
        }

    def get_signal_stats(self, initial_balance=DEFAULT_BALANCE):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as total FROM signals")
        total = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as cnt FROM signals WHERE status = 'open'")
        open_count = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM signals WHERE status = 'tp_hit'")
        tp_count = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM signals WHERE status = 'sl_hit'")
        sl_count = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM signals WHERE status = 'expired'")
        expired_count = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM signals WHERE status = 'closed_manual'")
        manual_count = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COALESCE(SUM(pnl), 0) as total_pnl FROM signals WHERE pnl IS NOT NULL AND status != 'open'")
        row = cursor.fetchone()
        total_pnl = row["total_pnl"] if row["total_pnl"] else 0.0

        cursor.execute("SELECT COUNT(*) as cnt FROM signals WHERE pnl > 0 AND status != 'open'")
        wins = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM signals WHERE pnl <= 0 AND pnl IS NOT NULL AND status != 'open'")
        losses = cursor.fetchone()["cnt"]

        closed_with_result = wins + losses
        win_rate = (wins / closed_with_result * 100) if closed_with_result > 0 else 0.0

        cursor.execute("SELECT AVG(leverage) as avg_lev FROM signals WHERE leverage IS NOT NULL")
        row = cursor.fetchone()
        avg_leverage = row["avg_lev"] if row["avg_lev"] else 0.0

        conn.close()

        current_balance = initial_balance + total_pnl

        return {
            "total": total, "open": open_count, "tp_count": tp_count,
            "sl_count": sl_count, "expired_count": expired_count,
            "manual_count": manual_count, "total_pnl": total_pnl,
            "wins": wins, "losses": losses, "win_rate": win_rate,
            "avg_leverage": avg_leverage,
            "initial_balance": initial_balance, "current_balance": current_balance,
        }


# ==============================================================================
# ★ تابع جدید: محاسبه مجموع مارجین‌های معاملات باز
# ==============================================================================
def get_total_open_margin(db):
    """محاسبه مجموع مارجین‌های تمام معاملات باز."""
    open_signals = db.get_open_signals()
    total_margin = sum(sig.get("margin_used", 0) for sig in open_signals)
    return total_margin


def get_available_margin(balance, db):
    """محاسبه مارجین آزاد (سرمایه - مجموع مارجین‌های باز)."""
    total_open_margin = get_total_open_margin(db)
    return max(0, balance - total_open_margin)


def can_open_new_position(balance, db, required_margin, max_margin_pct):
    """
    بررسی اینکه آیا می‌توان معامله جدید باز کرد.
    
    شرایط:
    1. مارجین مورد نیاز <= مارجین آزاد
    2. مارجین مورد نیاز <= حداکثر درصد مجاز از سرمایه
    """
    available_margin = get_available_margin(balance, db)
    max_allowed_margin = balance * max_margin_pct
    
    # مارجین مورد نیاز نباید از مارجین آزاد بیشتر باشد
    if required_margin > available_margin:
        return False, available_margin, max_allowed_margin
    
    # مارجین مورد نیاز نباید از حداکثر مجاز بیشتر باشد
    if required_margin > max_allowed_margin:
        return False, available_margin, max_allowed_margin
    
    return True, available_margin, max_allowed_margin


# ==============================================================================
# 2) ارتباط پایدار با Bybit
# ==============================================================================
REST_CANDIDATES = [
    "https://api.bybit.com",
    "https://api.bytick.com",
    "https://api.bybit.kz",
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0 Safari/537.36"),
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


def get_klines(symbol, interval, limit=1000):
    if symbol == "XAUUSDT":
        categories = ["linear", "spot"]
    else:
        categories = ["linear"]

    for category in categories:
        d = bybit_get("/v5/market/kline", {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        })
        if d and "list" in (d.get("result") or {}):
            lst = d["result"]["list"]
            if lst:
                df = pd.DataFrame(lst, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
                df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
                for c in ["open", "high", "low", "close", "volume"]:
                    df[c] = df[c].astype(float)
                return df.sort_values("ts").reset_index(drop=True)

    return pd.DataFrame()


def get_interval_minutes(interval):
    s = str(interval).strip().lower()
    if s == "d": return 1440
    if s == "w": return 10080
    if s == "m": return 43200
    try: return int(s)
    except Exception: return 15


# ==============================================================================
# 3) موتور چرخه‌ها
# ==============================================================================
class CycleEngine:
    def __init__(self, cycles=TEMPORAL_CYCLES, n_phase_bins=48, forecast_horizon_hours=4):
        self.cycles = cycles
        self.n_phase_bins = n_phase_bins
        self.forecast_horizon_hours = forecast_horizon_hours
        self.phase_maps = {}

    def build_phase_return_maps(self, df, interval_min):
        closes = df["close"].values
        ts = df["ts"].values
        n = len(closes)

        horizon_candles = max(1, int(self.forecast_horizon_hours * 60 / interval_min))
        future_returns = np.full(n, np.nan)
        if n > horizon_candles:
            future_returns[:n - horizon_candles] = (
                closes[horizon_candles:] - closes[:n - horizon_candles]
            ) / closes[:n - horizon_candles]

        ts_hours = pd.to_datetime(ts).astype(np.int64) / 1e9 / 3600.0

        for cycle in self.cycles:
            name = cycle["name"]
            period_h = cycle["period_hours"]
            phases = (ts_hours % period_h) / period_h

            phase_returns = np.full(self.n_phase_bins, np.nan)
            phase_stds = np.full(self.n_phase_bins, np.nan)

            for b in range(self.n_phase_bins):
                b_start = b / self.n_phase_bins
                b_end = (b + 1) / self.n_phase_bins
                mask = (phases >= b_start) & (phases < b_end) & ~np.isnan(future_returns)
                if mask.sum() >= 3:
                    vals = future_returns[mask]
                    phase_returns[b] = vals.mean()
                    phase_stds[b] = vals.std() if len(vals) > 1 else np.abs(vals.mean())

            valid = ~np.isnan(phase_returns)
            if valid.sum() >= 2:
                idxs = np.arange(self.n_phase_bins)
                ext_ret = np.concatenate([phase_returns, phase_returns, phase_returns])
                ext_idx = np.concatenate([idxs - self.n_phase_bins, idxs, idxs + self.n_phase_bins])
                ext_valid = np.concatenate([valid, valid, valid])
                filled = np.interp(idxs + self.n_phase_bins, ext_idx[ext_valid], ext_ret[ext_valid])
                phase_returns[~valid] = filled[~valid]

                ext_std = np.concatenate([phase_stds, phase_stds, phase_stds])
                filled_std = np.interp(idxs + self.n_phase_bins, ext_idx[ext_valid], ext_std[ext_valid])
                phase_stds[~valid] = filled_std[~valid]
            elif valid.sum() == 1:
                phase_returns[:] = phase_returns[valid][0]
                phase_stds[:] = phase_stds[valid][0] if not np.isnan(phase_stds[valid][0]) else 0.001
            else:
                phase_returns[:] = 0.0
                phase_stds[:] = 0.001

            if valid.sum() >= 2:
                signal_range = np.nanmax(phase_returns) - np.nanmin(phase_returns)
                noise_level = np.nanmean(phase_stds)
                strength = min(1.0, signal_range / (noise_level + 1e-9)) if noise_level > 0 else 0.5
            else:
                strength = 0.0

            strength *= cycle["weight"]

            self.phase_maps[name] = {
                "phase_return": phase_returns,
                "phase_std": phase_stds,
                "strength": strength,
                "period_hours": period_h,
                "color": cycle["color"],
            }

    def get_phase(self, dt_utc, period_hours):
        t_hours = dt_utc.timestamp() / 3600.0
        return (t_hours % period_hours) / period_hours

    def get_cycle_signal(self, dt_utc, cycle_name):
        if cycle_name not in self.phase_maps:
            return 0.0, 0.0, 0.0
        m = self.phase_maps[cycle_name]
        phase = self.get_phase(dt_utc, m["period_hours"])
        bin_idx = int(phase * self.n_phase_bins) % self.n_phase_bins
        exp_return = m["phase_return"][bin_idx]
        strength = m["strength"]
        return exp_return, strength, phase

    def compute_resonance(self, dt_utc):
        total_weight = 0.0
        weighted_signal = 0.0
        cycle_details = []

        for cycle in self.cycles:
            name = cycle["name"]
            exp_ret, strength, phase = self.get_cycle_signal(dt_utc, name)
            direction = np.sign(exp_ret)
            magnitude = min(abs(exp_ret) / 0.005, 1.0)
            final_weight = strength * cycle["weight"] * (0.5 + 0.5 * magnitude)

            weighted_signal += final_weight * direction
            total_weight += final_weight

            cycle_details.append({
                "name": name, "exp_return": exp_ret, "strength": strength,
                "phase": phase, "direction": direction, "weight": final_weight,
            })

        resonance_score = weighted_signal / total_weight if total_weight > 0 else 0.0

        return {
            "score": resonance_score,
            "total_weight": total_weight,
            "cycles": cycle_details,
        }


# ==============================================================================
# 4) موتور سیگنال‌دهی
# ==============================================================================
class TemporalSignalEngine:
    def __init__(self, cycle_engine, entry_threshold=0.35, min_cycles_agree=5):
        self.cycle_engine = cycle_engine
        self.entry_threshold = entry_threshold
        self.min_cycles_agree = min_cycles_agree

    def generate_signal(self, dt_utc):
        resonance = self.cycle_engine.compute_resonance(dt_utc)
        score = resonance["score"]

        positive_cycles = sum(1 for c in resonance["cycles"] if c["direction"] > 0)
        negative_cycles = sum(1 for c in resonance["cycles"] if c["direction"] < 0)
        dominant_count = max(positive_cycles, negative_cycles)
        total_cycles = len(resonance["cycles"])

        signal = 0
        reason = "No Signal"

        if score > self.entry_threshold and dominant_count >= self.min_cycles_agree:
            signal = 1
            reason = f"رزونانس صعودی ({positive_cycles} چرخه)"
        elif score < -self.entry_threshold and dominant_count >= self.min_cycles_agree:
            signal = -1
            reason = f"رزونانس نزولی ({negative_cycles} چرخه)"

        confidence = self._calculate_confidence(resonance, dominant_count, total_cycles)

        return {
            "signal": signal, "score": score, "reason": reason,
            "resonance": resonance, "dominant_count": dominant_count,
            "total_cycles": total_cycles, "confidence": confidence,
        }

    def _calculate_confidence(self, resonance, dominant_count, total_cycles):
        score_factor = min(abs(resonance["score"]) / 0.7, 1.0) * 40
        alignment_factor = (dominant_count / total_cycles) * 35 if total_cycles > 0 else 0

        if resonance["cycles"]:
            dominant_dir = np.sign(resonance["score"]) if resonance["score"] != 0 else 0
            aligned = [c for c in resonance["cycles"] if c["direction"] == dominant_dir]
            if aligned:
                avg_strength = np.mean([c["strength"] for c in aligned])
                strength_factor = avg_strength * 25
            else:
                strength_factor = 0
        else:
            strength_factor = 0

        confidence = score_factor + alignment_factor + strength_factor
        return min(100.0, max(0.0, confidence))


# ==============================================================================
# 5) موتور ریسک با کنترل مارجین
# ==============================================================================
class RiskEngine:
    def __init__(self, trading_mode="normal", atr_period=14):
        self.profile = TRADING_MODES.get(trading_mode, TRADING_MODES["normal"])
        self.trading_mode = trading_mode
        self.atr_period = atr_period

    def calculate_atr(self, df):
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        n = len(closes)
        tr = np.maximum(
            highs - lows,
            np.maximum(np.abs(highs - np.roll(closes, 1)), np.abs(lows - np.roll(closes, 1))),
        )
        tr[0] = highs[0] - lows[0]
        atr = pd.Series(tr).ewm(span=self.atr_period, adjust=False).mean().values
        return atr

    def calculate_tp_sl(self, entry_price, signal, atr_value, confidence):
        profile = self.profile

        sl_atr = atr_value * profile["sl_atr_mult"]
        tp_atr = atr_value * profile["tp_atr_mult"]

        sl_pct = entry_price * profile["min_sl_pct"]
        tp_pct = entry_price * profile["min_tp_pct"]

        sl_distance = max(sl_atr, sl_pct)
        tp_distance = max(tp_atr, tp_pct)

        confidence_factor = confidence / 100.0
        tp_distance *= (1.0 + confidence_factor * 0.5)

        if signal == 1:
            sl_price = entry_price - sl_distance
            tp_price = entry_price + tp_distance
        else:
            sl_price = entry_price + sl_distance
            tp_price = entry_price - tp_distance

        rr_ratio = tp_distance / sl_distance if sl_distance > 0 else 0

        return {
            "sl_price": sl_price, "tp_price": tp_price,
            "rr_ratio": rr_ratio, "sl_distance": sl_distance,
            "tp_distance": tp_distance,
        }

    def calculate_leverage(self, entry_price, sl_distance, confidence):
        if entry_price <= 0 or sl_distance <= 0:
            return self.profile["min_leverage"]

        sl_pct = sl_distance / entry_price

        base_leverage = 0.02 / max(sl_pct, 0.005)

        confidence_mult = 0.7 + (confidence / 100.0) * 0.6

        leverage = base_leverage * confidence_mult

        leverage = max(self.profile["min_leverage"], min(self.profile["max_leverage"], leverage))

        return round(leverage, 1)

    def calculate_position(self, balance, entry_price, sl_distance, confidence, available_margin=None):
        """
        محاسبه کامل پوزیشن با کنترل مارجین.
        
        پارامتر جدید:
        - available_margin: مارجین آزاد (اختیاری)
        """
        if sl_distance <= 0 or entry_price <= 0:
            return {"dollar_amount": 0.0, "leverage": self.profile["min_leverage"], "margin_used": 0.0}

        profile = self.profile

        # 1. محاسبه حجم بر اساس ریسک
        risk_amount = balance * profile["risk_pct"]
        confidence_multiplier = 0.5 + (confidence / 100.0) * 0.5
        adjusted_risk = risk_amount * confidence_multiplier

        sl_pct = sl_distance / entry_price
        position_size_usd = adjusted_risk / sl_pct if sl_pct > 0 else 0

        # 2. محاسبه لوریج
        leverage = self.calculate_leverage(entry_price, sl_distance, confidence)

        # 3. محاسبه مارجین مورد نیاز
        margin_needed = position_size_usd / leverage

        # 4. محدودیت بر اساس حداکثر مارجین (درصدی از سرمایه)
        max_margin = balance * profile["max_margin_pct"]
        if margin_needed > max_margin:
            margin_needed = max_margin
            position_size_usd = margin_needed * leverage

        # 5. محدودیت بر اساس حداکثر حجم
        max_position = balance * profile["max_position_pct"]
        if position_size_usd > max_position:
            position_size_usd = max_position
            margin_needed = position_size_usd / leverage

        # ★ 6. محدودیت بر اساس مارجین آزاد (جدید)
        if available_margin is not None and margin_needed > available_margin:
            margin_needed = available_margin
            position_size_usd = margin_needed * leverage

        # 7. حداقل حجم
        if position_size_usd < 5.0:
            position_size_usd = 5.0
            margin_needed = position_size_usd / leverage

        return {
            "dollar_amount": round(position_size_usd, 2),
            "leverage": leverage,
            "margin_used": round(margin_needed, 2),
        }


# ==============================================================================
# 6) اسکنر با کنترل مارجین
# ==============================================================================
def scan_all_symbols(interval="15", balance=DEFAULT_BALANCE, risk_pct=0.01, threshold=0.35, trading_mode="normal", db=None):
    interval_min = get_interval_minutes(interval)
    results = []
    skipped_no_margin = []

    profile = TRADING_MODES.get(trading_mode, TRADING_MODES["normal"])

    for symbol in SYMBOLS.keys():
        try:
            df = get_klines(symbol, interval, limit=1000)
            if df.empty or len(df) < BACKTEST_MIN_HISTORY:
                continue

            cycle_engine = CycleEngine(forecast_horizon_hours=4)
            cycle_engine.build_phase_return_maps(df, interval_min)

            current_time = pd.to_datetime(df["ts"].iloc[-1]).to_pydatetime().replace(tzinfo=timezone.utc)

            signal_engine = TemporalSignalEngine(cycle_engine, entry_threshold=threshold)
            sig_data = signal_engine.generate_signal(current_time)

            # فقط سیگنال‌های فعال (Long/Short)
            if sig_data["signal"] == 0:
                continue

            # ★ بررسی مارجین آزاد قبل از محاسبه
            if db is not None:
                available_margin = get_available_margin(balance, db)
                max_allowed_margin = balance * profile["max_margin_pct"]
                
                # اگر مارجین آزاد کمتر از حداقل است، رد شو
                if available_margin < 5.0:  # حداقل $5 برای باز کردن معامله
                    skipped_no_margin.append(symbol)
                    continue
            else:
                available_margin = balance * profile["max_margin_pct"]
                max_allowed_margin = balance * profile["max_margin_pct"]

            risk_engine = RiskEngine(trading_mode=trading_mode)
            atr = risk_engine.calculate_atr(df)
            current_atr = atr[-1]
            current_price = df["close"].iloc[-1]

            tp_sl = risk_engine.calculate_tp_sl(
                current_price, sig_data["signal"], current_atr, sig_data["confidence"]
            )

            position = risk_engine.calculate_position(
                balance, current_price, tp_sl["sl_distance"], sig_data["confidence"],
                available_margin=available_margin
            )

            # بررسی نهایی: مارجین مورد نیاز نباید از مارجین آزاد بیشتر باشد
            if position["margin_used"] > available_margin:
                skipped_no_margin.append(symbol)
                continue

            final_score = abs(sig_data["score"]) * (sig_data["confidence"] / 100.0) * 100

            results.append({
                "symbol": symbol,
                "name": SYMBOLS[symbol]["name"],
                "icon": SYMBOLS[symbol]["icon"],
                "signal": sig_data["signal"],
                "score": sig_data["score"],
                "confidence": sig_data["confidence"],
                "final_score": final_score,
                "dominant_count": sig_data["dominant_count"],
                "total_cycles": sig_data["total_cycles"],
                "current_price": current_price,
                "entry_price": current_price,
                "atr": current_atr,
                "dollar_amount": position["dollar_amount"],
                "leverage": position["leverage"],
                "margin_used": position["margin_used"],
                "reason": sig_data["reason"],
                "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "sl_price": tp_sl["sl_price"],
                "tp_price": tp_sl["tp_price"],
                "rr_ratio": tp_sl["rr_ratio"],
                "sl_distance": tp_sl["sl_distance"],
                "tp_distance": tp_sl["tp_distance"],
                "trading_mode": trading_mode,
            })

            time.sleep(0.05)

        except Exception:
            continue

    results.sort(key=lambda x: x["final_score"], reverse=True)
    return results, skipped_no_margin


# ==============================================================================
# 7) آپدیت نتایج و PnL زنده
# ==============================================================================
def update_open_signals_results(db):
    open_signals = db.get_open_signals()
    if not open_signals:
        return 0

    updated_count = 0

    for sig in open_signals:
        try:
            symbol = sig["symbol"]
            direction = sig["direction"]
            entry_price = sig["entry_price"]
            sl_price = sig["sl_price"]
            tp_price = sig["tp_price"]
            dollar_amount = sig["dollar_amount"]

            df = get_klines(symbol, "1", limit=1)
            if df.empty:
                continue

            current_price = df["close"].iloc[-1]
            current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            size = dollar_amount / entry_price if entry_price > 0 else 0

            status = None
            exit_price = None
            reason = None

            if direction == 1:
                if current_price <= sl_price:
                    status = "sl_hit"
                    exit_price = sl_price
                    reason = "SL"
                elif current_price >= tp_price:
                    status = "tp_hit"
                    exit_price = tp_price
                    reason = "TP"
            else:
                if current_price >= sl_price:
                    status = "sl_hit"
                    exit_price = sl_price
                    reason = "SL"
                elif current_price <= tp_price:
                    status = "tp_hit"
                    exit_price = tp_price
                    reason = "TP"

            if status is None:
                try:
                    created_dt = datetime.strptime(sig["created_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    hours_passed = (datetime.now(timezone.utc) - created_dt).total_seconds() / 3600
                    if hours_passed > 24:
                        status = "expired"
                        exit_price = current_price
                        reason = "Expired (24h)"
                except Exception:
                    pass

            if status:
                if direction == 1:
                    pnl = (exit_price - entry_price) * size
                else:
                    pnl = (entry_price - exit_price) * size

                pnl_pct = (pnl / dollar_amount * 100) if dollar_amount > 0 else 0

                db.update_signal_result(
                    sig["id"], exit_price, current_time, pnl, pnl_pct, status, reason
                )
                updated_count += 1

        except Exception:
            continue

    return updated_count


def calculate_open_pnls_live(db):
    open_signals = db.get_open_signals()
    live_pnls = {}

    for sig in open_signals:
        try:
            df = get_klines(sig["symbol"], "1", limit=1)
            if df.empty:
                continue

            current_price = df["close"].iloc[-1]
            entry_price = sig["entry_price"]
            dollar_amount = sig["dollar_amount"]
            direction = sig["direction"]

            size = dollar_amount / entry_price if entry_price > 0 else 0

            if direction == 1:
                pnl = (current_price - entry_price) * size
            else:
                pnl = (entry_price - current_price) * size

            pnl_pct = (pnl / dollar_amount * 100) if dollar_amount > 0 else 0

            live_pnls[sig["id"]] = {
                "current_price": current_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
            }

        except Exception:
            continue

    return live_pnls


def get_open_pnl_estimate(db):
    live_pnls = calculate_open_pnls_live(db)
    return sum(p["pnl"] for p in live_pnls.values())


# ==============================================================================
# 8) توابع UI
# ==============================================================================
def empty_fig(msg):
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        font=dict(family=FONT_FAMILY),
    )
    fig.add_annotation(
        x=0.5, y=0.5, xref="paper", yref="paper", text=msg,
        showarrow=False, font=dict(size=16, color=DN, family=FONT_FAMILY),
    )
    return fig


def get_mode_badge(mode_key):
    if mode_key == "aggressive":
        return "🔥 اگرسیو", DN
    elif mode_key == "conservative":
        return "🛡️ محافظه‌کار", UP
    else:
        return "⚖️ معمولی", GOLD


def build_open_positions_table(open_signals, live_pnls):
    if not open_signals:
        return html.Div(
            "📭 معامله بازی وجود ندارد. روی «🔍 اسکن» بزنید تا سیگنال‌ها شناسایی و ذخیره شوند.",
            style={"color": MUT, "textAlign": "center", "padding": "30px", "fontSize": "13px"}
        )

    header = html.Tr([
        html.Th("ID", style={"width": "3%"}),
        html.Th("نماد", style={"width": "7%"}),
        html.Th("جهت", style={"width": "6%"}),
        html.Th("حالت", style={"width": "6%"}),
        html.Th("ورود", style={"width": "8%"}),
        html.Th("🛑 SL", style={"width": "8%"}),
        html.Th("🎯 TP", style={"width": "8%"}),
        html.Th("حجم ($)", style={"width": "8%"}),
        html.Th("⚡ لوریج", style={"width": "5%"}),
        html.Th("مارجین", style={"width": "7%"}),
        html.Th("قیمت فعلی", style={"width": "8%"}),
        html.Th("PnL ($)", style={"width": "8%"}),
        html.Th("PnL (٪)", style={"width": "7%"}),
        html.Th("عملیات", style={"width": "7%"}),
    ], style={"color": MUT, "fontSize": 9, "textAlign": "center"})

    rows = []
    for sig in open_signals:
        sig_id = sig["id"]
        symbol = sig["symbol"]
        direction = sig["direction"]

        if direction == 1:
            dir_text = "🟢 LONG"
            dir_color = UP
            row_bg = "rgba(0,255,204,0.04)"
        else:
            dir_text = "🔴 SHORT"
            dir_color = DN
            row_bg = "rgba(255,34,102,0.04)"

        entry_price = sig["entry_price"]
        sl_price = sig["sl_price"]
        tp_price = sig["tp_price"]
        dollar_amount = sig["dollar_amount"]
        leverage = sig.get("leverage", 1.0) or 1.0
        margin_used = sig.get("margin_used", 0.0) or 0.0
        trading_mode = sig.get("trading_mode", "normal")

        mode_text, mode_color = get_mode_badge(trading_mode)

        if sig_id in live_pnls:
            live = live_pnls[sig_id]
            current_price = live["current_price"]
            pnl = live["pnl"]
            pnl_pct = live["pnl_pct"]
        else:
            current_price = entry_price
            pnl = 0.0
            pnl_pct = 0.0

        pnl_color = UP if pnl > 0 else (DN if pnl < 0 else MUT)

        if leverage >= 50:
            lev_color = DN
        elif leverage >= 20:
            lev_color = GOLD
        else:
            lev_color = UP

        symbol_info = SYMBOLS.get(symbol, {"icon": "•", "name": symbol})

        rows.append(html.Tr([
            html.Td(f"#{sig_id}", style={"color": MUT, "fontSize": "10px"}),
            html.Td([
                html.Span(symbol_info["icon"], style={"marginRight": "2px"}),
                html.Span(symbol.replace("USDT", ""), style={"fontWeight": "bold", "fontSize": "10px"}),
            ], style={"color": TXT}),
            html.Td(dir_text, style={"color": dir_color, "fontWeight": "bold", "fontSize": "10px"}),
            html.Td(mode_text, style={"color": mode_color, "fontSize": "9px"}),
            html.Td(f"${entry_price:,.4g}", style={"color": TXT, "fontSize": "10px"}),
            html.Td(f"${sl_price:,.4g}", style={"color": DN, "fontSize": "10px"}),
            html.Td(f"${tp_price:,.4g}", style={"color": UP, "fontSize": "10px"}),
            html.Td(f"${dollar_amount:,.2f}", style={"color": BLUE, "fontWeight": "bold", "fontSize": "10px"}),
            html.Td(f"{leverage:.1f}x", style={"color": lev_color, "fontWeight": "bold", "fontSize": "10px"}),
            html.Td(f"${margin_used:,.2f}", style={"color": MUT, "fontSize": "10px"}),
            html.Td(f"${current_price:,.4g}", style={"color": CYAN, "fontWeight": "bold", "fontSize": "10px"}),
            html.Td(f"${pnl:+,.2f}", style={"color": pnl_color, "fontWeight": "bold", "fontSize": "11px"}),
            html.Td(f"{pnl_pct:+.2f}%", style={"color": pnl_color, "fontWeight": "bold", "fontSize": "10px"}),
            html.Td(
                dbc.Button(
                    "❌ بستن",
                    id={"type": "close-btn", "index": sig_id},
                    color="danger",
                    size="sm",
                    style={"fontSize": "9px", "padding": "2px 6px"},
                ),
                style={"textAlign": "center"}
            ),
        ], style={"textAlign": "center", "background": row_bg}))

    return dbc.Table(
        [html.Thead(header), html.Tbody(rows)],
        bordered=False, hover=True, responsive=True, size="sm",
        style={"color": TXT},
    )


def build_scan_results_table(signals_data):
    if not signals_data:
        return html.Div("هنوز اسکنی انجام نشده.", style={"color": MUT, "textAlign": "center", "padding": "20px"})

    header = html.Tr([
        html.Th("#", style={"width": "3%"}),
        html.Th("نماد", style={"width": "7%"}),
        html.Th("سیگنال", style={"width": "6%"}),
        html.Th("امتیاز", style={"width": "5%"}),
        html.Th("اطمینان", style={"width": "6%"}),
        html.Th("حجم ($)", style={"width": "8%"}),
        html.Th("⚡ لوریج", style={"width": "5%"}),
        html.Th("ورود", style={"width": "8%"}),
        html.Th("🛑 SL", style={"width": "8%"}),
        html.Th("🎯 TP", style={"width": "8%"}),
        html.Th("R:R", style={"width": "5%"}),
        html.Th("وضعیت", style={"width": "9%"}),
    ], style={"color": MUT, "fontSize": 9, "textAlign": "center"})

    rows = []
    for rank, s in enumerate(signals_data, 1):
        if s["signal"] == 1:
            dir_text = "🟢 LONG"
            dir_color = UP
            row_bg = "rgba(0,255,204,0.04)"
        elif s["signal"] == -1:
            dir_text = "🔴 SHORT"
            dir_color = DN
            row_bg = "rgba(255,34,102,0.04)"
        else:
            dir_text = "⏸ خنثی"
            dir_color = MUT
            row_bg = "transparent"

        has_open = db.has_open_signal(s["symbol"])
        if has_open:
            status_text = "✅ معامله باز دارد"
            status_color = BLUE
        elif s["signal"] != 0:
            status_text = "🆕 آماده ذخیره"
            status_color = GOLD
        else:
            status_text = "—"
            status_color = MUT

        conf = s["confidence"]
        conf_color = UP if conf >= 70 else (GOLD if conf >= 50 else DN)
        score_color = UP if s["final_score"] > 50 else (GOLD if s["final_score"] > 25 else MUT)
        leverage = s.get("leverage", 1.0)

        if leverage >= 50:
            lev_color = DN
        elif leverage >= 20:
            lev_color = GOLD
        else:
            lev_color = UP

        if s["signal"] != 0:
            sl_text = f"${s['sl_price']:,.4g}"
            tp_text = f"${s['tp_price']:,.4g}"
            rr_text = f"1:{s['rr_ratio']:.1f}"
        else:
            sl_text = "—"
            tp_text = "—"
            rr_text = "—"

        rows.append(html.Tr([
            html.Td(f"#{rank}", style={"color": GOLD, "fontWeight": "bold", "fontSize": "9px"}),
            html.Td([
                html.Span(s["icon"], style={"marginRight": "2px"}),
                html.Span(s["symbol"].replace("USDT", ""), style={"fontWeight": "bold", "fontSize": "9px"}),
            ], style={"color": TXT}),
            html.Td(dir_text, style={"color": dir_color, "fontWeight": "bold", "fontSize": "9px"}),
            html.Td(f"{s['final_score']:.1f}", style={"color": score_color, "fontWeight": "bold", "fontSize": "9px"}),
            html.Td(f"{conf:.0f}%", style={"color": conf_color, "fontSize": "9px"}),
            html.Td(f"${s['dollar_amount']:,.2f}", style={"color": BLUE, "fontSize": "9px"}),
            html.Td(f"{leverage:.1f}x", style={"color": lev_color, "fontWeight": "bold", "fontSize": "9px"}),
            html.Td(f"${s['entry_price']:,.4g}", style={"color": TXT, "fontSize": "9px"}),
            html.Td(sl_text, style={"color": DN, "fontSize": "9px"}),
            html.Td(tp_text, style={"color": UP, "fontSize": "9px"}),
            html.Td(rr_text, style={"color": GOLD, "fontWeight": "bold", "fontSize": "9px"}),
            html.Td(status_text, style={"color": status_color, "fontSize": "9px"}),
        ], style={"textAlign": "center", "background": row_bg}))

    return dbc.Table(
        [html.Thead(header), html.Tbody(rows)],
        bordered=False, hover=True, responsive=True, size="sm",
        style={"color": TXT},
    )


def build_signals_summary(signals_data, total_pnl=0.0, current_balance=DEFAULT_BALANCE, open_pnl=0.0, trading_mode="normal", margin_info=None):
    total = len(signals_data)
    longs = sum(1 for s in signals_data if s["signal"] == 1)
    shorts = sum(1 for s in signals_data if s["signal"] == -1)
    total_dollar = sum(s["dollar_amount"] for s in signals_data if s["signal"] != 0)
    total_margin = sum(s.get("margin_used", 0) for s in signals_data if s["signal"] != 0)

    total_pnl_with_open = total_pnl + open_pnl
    pnl_color = UP if total_pnl_with_open >= 0 else DN
    balance_color = UP if current_balance >= DEFAULT_BALANCE else DN

    mode_text, mode_color = get_mode_badge(trading_mode)

    # اطلاعات مارجین
    if margin_info:
        available_margin = margin_info.get("available", 0)
        used_margin = margin_info.get("used", 0)
        margin_color = UP if available_margin > 50 else (GOLD if available_margin > 20 else DN)
    else:
        available_margin = current_balance
        used_margin = 0
        margin_color = UP

    return dbc.Row([
        dbc.Col(html.Div([
            html.Div("حالت معاملاتی", className="stat-label"),
            html.Div(mode_text, className="stat-value", style={"color": mode_color, "fontSize": "14px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center", "border": f"1px solid {mode_color}"}), md=2),
        dbc.Col(html.Div([
            html.Div("🟢 خرید", className="stat-label"),
            html.Div(f"{longs}", className="stat-value", style={"color": UP, "fontSize": "16px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center"}), md=2),
        dbc.Col(html.Div([
            html.Div("🔴 فروش", className="stat-label"),
            html.Div(f"{shorts}", className="stat-value", style={"color": DN, "fontSize": "16px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center"}), md=2),
        dbc.Col(html.Div([
            html.Div("💰 مارجین آزاد", className="stat-label"),
            html.Div(f"${available_margin:,.2f}", className="stat-value", style={"color": margin_color, "fontSize": "16px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center", "border": f"1px solid {margin_color}"}), md=2),
        dbc.Col(html.Div([
            html.Div("💰 سود دلاری کل", className="stat-label"),
            html.Div(f"${total_pnl_with_open:+,.2f}", className="stat-value", style={"color": pnl_color, "fontSize": "16px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center", "border": f"1px solid {pnl_color}"}), md=2),
        dbc.Col(html.Div([
            html.Div("📊 سرمایه فعلی", className="stat-label"),
            html.Div(f"${current_balance:,.2f}", className="stat-value", style={"color": balance_color, "fontSize": "16px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center", "border": f"1px solid {balance_color}"}), md=2),
    ])


def build_mode_info_panel(trading_mode, balance=None, db=None):
    profile = TRADING_MODES.get(trading_mode, TRADING_MODES["normal"])
    mode_text, mode_color = get_mode_badge(trading_mode)

    # اطلاعات مارجین
    margin_html = ""
    if balance is not None and db is not None:
        available_margin = get_available_margin(balance, db)
        used_margin = get_total_open_margin(db)
        margin_pct = (used_margin / balance * 100) if balance > 0 else 0
        
        margin_color = UP if margin_pct < 50 else (GOLD if margin_pct < 80 else DN)
        
        margin_html = html.Div([
            html.Div("📊 وضعیت مارجین", style={"color": TXT, "fontWeight": "bold", "marginBottom": "10px"}),
            dbc.Row([
                dbc.Col(html.Div([
                    html.Div("مارجین استفاده‌شده", className="stat-label"),
                    html.Div(f"${used_margin:,.2f}", className="stat-value", style={"color": margin_color, "fontSize": "14px"}),
                ], style={"textAlign": "center"}), md=4),
                dbc.Col(html.Div([
                    html.Div("مارجین آزاد", className="stat-label"),
                    html.Div(f"${available_margin:,.2f}", className="stat-value", style={"color": UP, "fontSize": "14px"}),
                ], style={"textAlign": "center"}), md=4),
                dbc.Col(html.Div([
                    html.Div("درصد استفاده", className="stat-label"),
                    html.Div(f"{margin_pct:.1f}%", className="stat-value", style={"color": margin_color, "fontSize": "14px"}),
                ], style={"textAlign": "center"}), md=4),
            ]),
        ], style={"marginTop": "15px", "paddingTop": "15px", "borderTop": f"1px solid {LINE}"})

    return dbc.Card(dbc.CardBody([
        html.Div([
            html.Span(f"حالت فعال: {mode_text}", style={
                "color": mode_color, "fontWeight": "bold", "fontSize": "14px",
            }),
        ], style={"textAlign": "center", "marginBottom": "10px"}),
        dbc.Row([
            dbc.Col(html.Div([
                html.Div("ریسک هر معامله", className="stat-label"),
                html.Div(f"{profile['risk_pct']*100:.1f}%", className="stat-value", style={"color": GOLD, "fontSize": "14px"}),
            ], style={"textAlign": "center"}), md=2),
            dbc.Col(html.Div([
                html.Div("لوریج", className="stat-label"),
                html.Div(f"{profile['min_leverage']:.0f}x - {profile['max_leverage']:.0f}x", className="stat-value", style={"color": CYAN, "fontSize": "14px"}),
            ], style={"textAlign": "center"}), md=2),
            dbc.Col(html.Div([
                html.Div("حداکثر حجم", className="stat-label"),
                html.Div(f"{profile['max_position_pct']*100:.0f}%", className="stat-value", style={"color": BLUE, "fontSize": "14px"}),
            ], style={"textAlign": "center"}), md=2),
            dbc.Col(html.Div([
                html.Div("حداکثر مارجین", className="stat-label"),
                html.Div(f"{profile['max_margin_pct']*100:.0f}%", className="stat-value", style={"color": PURPLE, "fontSize": "14px"}),
            ], style={"textAlign": "center"}), md=2),
            dbc.Col(html.Div([
                html.Div("SL (ATR)", className="stat-label"),
                html.Div(f"{profile['sl_atr_mult']:.1f}x", className="stat-value", style={"color": DN, "fontSize": "14px"}),
            ], style={"textAlign": "center"}), md=2),
            dbc.Col(html.Div([
                html.Div("TP (ATR)", className="stat-label"),
                html.Div(f"{profile['tp_atr_mult']:.1f}x", className="stat-value", style={"color": UP, "fontSize": "14px"}),
            ], style={"textAlign": "center"}), md=2),
        ]),
        margin_html,
    ], style={"padding": "10px"}), className="glass-card", style={"margin": "10px 0"})


# ... (بقیه توابع build_history_table, build_history_stats, build_symbol_* مثل v15)

def build_history_table(signals_from_db, live_pnls=None):
    if not signals_from_db:
        return html.Div("هنوز سیگنالی در دیتابیس ثبت نشده است.", style={"color": MUT, "textAlign": "center", "padding": "20px"})

    header = html.Tr([
        html.Th("ID", style={"width": "3%"}),
        html.Th("زمان", style={"width": "8%"}),
        html.Th("نماد", style={"width": "6%"}),
        html.Th("جهت", style={"width": "6%"}),
        html.Th("حالت", style={"width": "5%"}),
        html.Th("ورود", style={"width": "7%"}),
        html.Th("🛑 SL", style={"width": "7%"}),
        html.Th("🎯 TP", style={"width": "7%"}),
        html.Th("حجم ($)", style={"width": "7%"}),
        html.Th("⚡ لوریج", style={"width": "5%"}),
        html.Th("مارجین", style={"width": "6%"}),
        html.Th("وضعیت", style={"width": "7%"}),
        html.Th("قیمت فعلی", style={"width": "7%"}),
        html.Th("PnL ($)", style={"width": "7%"}),
        html.Th("PnL (٪)", style={"width": "6%"}),
        html.Th("عملیات", style={"width": "7%"}),
    ], style={"color": MUT, "fontSize": 9, "textAlign": "center"})

    rows = []
    for s in signals_from_db:
        if s["direction"] == 1:
            dir_text = "🟢 LONG"
            dir_color = UP
        elif s["direction"] == -1:
            dir_text = "🔴 SHORT"
            dir_color = DN
        else:
            dir_text = "⏸"
            dir_color = MUT

        status = s["status"]
        if status == "tp_hit":
            status_text = "🎯 TP"
            status_color = UP
            row_bg = "rgba(0,255,204,0.06)"
        elif status == "sl_hit":
            status_text = "🛑 SL"
            status_color = DN
            row_bg = "rgba(255,34,102,0.06)"
        elif status == "expired":
            status_text = "⏰ منقضی"
            status_color = MUT
            row_bg = "rgba(122,122,168,0.06)"
        elif status == "closed_manual":
            status_text = "✋ بسته شد"
            status_color = GOLD
            row_bg = "rgba(255,215,0,0.06)"
        else:
            status_text = "🔵 باز"
            status_color = BLUE
            row_bg = "rgba(0,170,255,0.04)"

        trading_mode = s.get("trading_mode", "normal")
        mode_text, mode_color = get_mode_badge(trading_mode)

        if status == "open" and live_pnls and s["id"] in live_pnls:
            live = live_pnls[s["id"]]
            pnl = live["pnl"]
            pnl_pct = live["pnl_pct"]
            current_price = live["current_price"]
            pnl_color = UP if pnl > 0 else (DN if pnl < 0 else MUT)
            pnl_text = f"${pnl:+,.2f}"
            pnl_pct_text = f"{pnl_pct:+.2f}%"
            current_price_text = f"${current_price:,.4g}"
        elif s["pnl"] is not None:
            pnl = s["pnl"]
            pnl_pct = s["pnl_pct"]
            pnl_color = UP if pnl > 0 else DN
            pnl_text = f"${pnl:+,.2f}"
            pnl_pct_text = f"{pnl_pct:+.2f}%"
            current_price_text = f"${s['exit_price']:,.4g}" if s["exit_price"] else "—"
        else:
            pnl_color = MUT
            pnl_text = "—"
            pnl_pct_text = "—"
            current_price_text = "—"

        leverage = s.get("leverage", 1.0) or 1.0
        margin_used = s.get("margin_used", 0.0) or 0.0

        if leverage >= 50:
            lev_color = DN
        elif leverage >= 20:
            lev_color = GOLD
        else:
            lev_color = UP

        symbol_info = SYMBOLS.get(s["symbol"], {"icon": "•", "name": s["symbol"]})

        if status == "open":
            action_cell = html.Td(
                dbc.Button(
                    "❌ بستن",
                    id={"type": "close-btn", "index": s["id"]},
                    color="danger",
                    size="sm",
                    style={"fontSize": "9px", "padding": "2px 6px"},
                ),
                style={"textAlign": "center"}
            )
        else:
            action_cell = html.Td(
                html.Span(s["exit_reason"] or "—", style={"color": MUT, "fontSize": "9px"}),
                style={"textAlign": "center"}
            )

        rows.append(html.Tr([
            html.Td(f"#{s['id']}", style={"color": MUT, "fontSize": "9px"}),
            html.Td(s["created_at"][-14:], style={"color": MUT, "fontSize": "9px"}),
            html.Td([
                html.Span(symbol_info["icon"], style={"marginRight": "2px"}),
                html.Span(s["symbol"].replace("USDT", ""), style={"fontWeight": "bold", "fontSize": "10px"}),
            ], style={"color": TXT}),
            html.Td(dir_text, style={"color": dir_color, "fontWeight": "bold", "fontSize": "10px"}),
            html.Td(mode_text, style={"color": mode_color, "fontSize": "9px"}),
            html.Td(f"${s['entry_price']:,.4g}", style={"color": TXT, "fontSize": "10px"}),
            html.Td(f"${s['sl_price']:,.4g}", style={"color": DN, "fontSize": "10px"}),
            html.Td(f"${s['tp_price']:,.4g}", style={"color": UP, "fontSize": "10px"}),
            html.Td(f"${s['dollar_amount']:,.2f}", style={"color": BLUE, "fontSize": "10px"}),
            html.Td(f"{leverage:.1f}x", style={"color": lev_color, "fontWeight": "bold", "fontSize": "10px"}),
            html.Td(f"${margin_used:,.2f}", style={"color": MUT, "fontSize": "10px"}),
            html.Td(status_text, style={"color": status_color, "fontWeight": "bold", "fontSize": "10px"}),
            html.Td(current_price_text, style={"color": TXT, "fontSize": "10px"}),
            html.Td(pnl_text, style={"color": pnl_color, "fontWeight": "bold", "fontSize": "10px"}),
            html.Td(pnl_pct_text, style={"color": pnl_color, "fontSize": "10px"}),
            action_cell,
        ], style={"textAlign": "center", "background": row_bg}))

    return dbc.Table(
        [html.Thead(header), html.Tbody(rows)],
        bordered=False, hover=True, responsive=True, size="sm",
        style={"color": TXT},
    )


def build_history_stats(stats, open_pnl_estimate=0.0):
    total_pnl_with_open = stats["total_pnl"] + open_pnl_estimate
    current_balance_with_open = stats["initial_balance"] + total_pnl_with_open

    balance_color = UP if current_balance_with_open >= stats["initial_balance"] else DN
    pnl_color = UP if total_pnl_with_open >= 0 else DN
    closed_pnl_color = UP if stats["total_pnl"] >= 0 else DN

    return dbc.Row([
        dbc.Col(html.Div([
            html.Div("سرمایه اولیه", className="stat-label"),
            html.Div(f"${stats['initial_balance']:,.2f}", className="stat-value", style={"color": TXT, "fontSize": "15px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center"}), md=2),
        dbc.Col(html.Div([
            html.Div("💰 سرمایه فعلی", className="stat-label"),
            html.Div(f"${current_balance_with_open:,.2f}", className="stat-value", style={"color": balance_color, "fontSize": "15px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center", "border": f"1px solid {balance_color}"}), md=2),
        dbc.Col(html.Div([
            html.Div("📊 سود کل (قطعی+شناور)", className="stat-label"),
            html.Div(f"${total_pnl_with_open:+,.2f}", className="stat-value", style={"color": pnl_color, "fontSize": "15px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center", "border": f"1px solid {pnl_color}"}), md=2),
        dbc.Col(html.Div([
            html.Div("سود قطعی (بسته‌شده)", className="stat-label"),
            html.Div(f"${stats['total_pnl']:+,.2f}", className="stat-value", style={"color": closed_pnl_color, "fontSize": "15px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center"}), md=2),
        dbc.Col(html.Div([
            html.Div("⚡ میانگین لوریج", className="stat-label"),
            html.Div(f"{stats['avg_leverage']:.1f}x", className="stat-value", style={"color": CYAN, "fontSize": "15px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center"}), md=2),
        dbc.Col(html.Div([
            html.Div("Win Rate", className="stat-label"),
            html.Div(f"{stats['win_rate']:.1f}%", className="stat-value", style={"color": GOLD, "fontSize": "15px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center"}), md=2),
    ])


# ... (بقیه توابع build_symbol_*, build_resonance_*, build_price_figure, build_signal_panel مثل v15)


def build_symbol_stats_kpis(stats):
    if not stats:
        return html.Div("داده‌ای برای این نماد نیست.", style={"color": MUT, "textAlign": "center"})

    symbol_info = SYMBOLS.get(stats["symbol"], {"icon": "•", "name": stats["symbol"]})
    pnl_color = UP if stats["total_pnl"] >= 0 else DN
    win_color = UP if stats["win_rate"] >= 50 else (GOLD if stats["win_rate"] >= 35 else DN)

    return dbc.Row([
        dbc.Col(html.Div([
            html.Div(f"{symbol_info['icon']} {stats['symbol'].replace('USDT', '')}", className="stat-label"),
            html.Div(f"{stats['total']} سیگنال", className="stat-value", style={"color": TXT, "fontSize": "16px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center"}), md=2),
        dbc.Col(html.Div([
            html.Div("🏆 وین‌ریت", className="stat-label"),
            html.Div(f"{stats['win_rate']:.1f}%", className="stat-value", style={"color": win_color, "fontSize": "16px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center", "border": f"1px solid {win_color}"}), md=2),
        dbc.Col(html.Div([
            html.Div("💰 سود کل", className="stat-label"),
            html.Div(f"${stats['total_pnl']:+,.2f}", className="stat-value", style={"color": pnl_color, "fontSize": "16px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center", "border": f"1px solid {pnl_color}"}), md=2),
        dbc.Col(html.Div([
            html.Div("🎯 TP / 🛑 SL", className="stat-label"),
            html.Div(f"{stats['tp_count']} / {stats['sl_count']}", className="stat-value", style={"color": TXT, "fontSize": "16px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center"}), md=2),
        dbc.Col(html.Div([
            html.Div("📈 بهترین", className="stat-label"),
            html.Div(f"${stats['best_trade']:+,.2f}", className="stat-value", style={"color": UP, "fontSize": "16px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center"}), md=2),
        dbc.Col(html.Div([
            html.Div("📉 بدترین", className="stat-label"),
            html.Div(f"${stats['worst_trade']:+,.2f}", className="stat-value", style={"color": DN, "fontSize": "16px"}),
        ], className="glass-card", style={"padding": "10px", "textAlign": "center"}), md=2),
    ])


def build_symbol_stats_detail(stats):
    if not stats:
        return html.Div()

    return dbc.Row([
        dbc.Col(html.Div([
            html.Div("میانگین PnL", className="stat-label"),
            html.Div(f"${stats['avg_pnl']:+,.2f}", className="stat-value", style={"color": TXT, "fontSize": "14px"}),
        ], className="glass-card", style={"padding": "8px", "textAlign": "center"}), md=2),
        dbc.Col(html.Div([
            html.Div("میانگین PnL٪", className="stat-label"),
            html.Div(f"{stats['avg_pnl_pct']:+.2f}%", className="stat-value", style={"color": TXT, "fontSize": "14px"}),
        ], className="glass-card", style={"padding": "8px", "textAlign": "center"}), md=2),
        dbc.Col(html.Div([
            html.Div("🟢 وین‌ریت Long", className="stat-label"),
            html.Div(f"{stats['long_win_rate']:.1f}%", className="stat-value", style={"color": UP, "fontSize": "14px"}),
        ], className="glass-card", style={"padding": "8px", "textAlign": "center"}), md=2),
        dbc.Col(html.Div([
            html.Div("🔴 وین‌ریت Short", className="stat-label"),
            html.Div(f"{stats['short_win_rate']:.1f}%", className="stat-value", style={"color": DN, "fontSize": "14px"}),
        ], className="glass-card", style={"padding": "8px", "textAlign": "center"}), md=2),
        dbc.Col(html.Div([
            html.Div("⚡ میانگین لوریج", className="stat-label"),
            html.Div(f"{stats['avg_leverage']:.1f}x", className="stat-value", style={"color": CYAN, "fontSize": "14px"}),
        ], className="glass-card", style={"padding": "8px", "textAlign": "center"}), md=2),
        dbc.Col(html.Div([
            html.Div("🎯 میانگین اطمینان", className="stat-label"),
            html.Div(f"{stats['avg_confidence']:.0f}%", className="stat-value", style={"color": GOLD, "fontSize": "14px"}),
        ], className="glass-card", style={"padding": "8px", "textAlign": "center"}), md=2),
    ])


def build_symbol_cumulative_pnl_chart(stats):
    if not stats or not stats["cumulative_pnl"]:
        return empty_fig("داده‌ای برای نمودار نیست.")

    cumulative = stats["cumulative_pnl"]
    x = list(range(1, len(cumulative) + 1))

    fig = go.Figure()

    line_color = UP if cumulative[-1] >= 0 else DN

    fig.add_trace(go.Scatter(
        x=x, y=cumulative, mode="lines",
        name="PnL تجمعی",
        line=dict(color=line_color, width=3),
        fill="tozeroy",
        fillcolor="rgba(0,255,204,0.1)" if cumulative[-1] >= 0 else "rgba(255,34,102,0.1)",
    ))

    fig.add_hline(y=0, line=dict(color=MUT, dash="dot", width=1))

    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
        margin=dict(l=50, r=20, t=50, b=40),
        xaxis=dict(color=MUT, gridcolor=LINE, title="تعداد معامله"),
        yaxis=dict(color=MUT, gridcolor=LINE, title="PnL تجمعی ($)"),
        font=dict(family=FONT_FAMILY, color=TXT),
        title=dict(text=f"📈 PnL تجمعی — {stats['symbol']}", x=0.5,
                   font=dict(color=GOLD, size=14, family=FONT_FAMILY)),
        showlegend=False, height=300,
    )
    return fig


def build_symbol_status_chart(stats):
    if not stats:
        return empty_fig("داده‌ای نیست.")

    labels = ["🎯 TP", "🛑 SL", "⏰ منقضی", "✋ دستی", "🔵 باز"]
    values = [stats["tp_count"], stats["sl_count"], stats["expired_count"],
              stats["manual_count"], stats["open"]]
    colors = [UP, DN, MUT, GOLD, BLUE]

    filtered = [(l, v, c) for l, v, c in zip(labels, values, colors) if v > 0]
    if not filtered:
        return empty_fig("داده‌ای نیست.")

    labels, values, colors = zip(*filtered)

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.5,
        marker=dict(colors=colors),
        textinfo="label+percent",
        textfont=dict(size=11, color=TXT),
    )])

    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
        margin=dict(l=20, r=20, t=50, b=20),
        font=dict(family=FONT_FAMILY, color=TXT),
        title=dict(text=f"وضعیت سیگنال‌ها — {stats['symbol']}", x=0.5,
                   font=dict(color=GOLD, size=14, family=FONT_FAMILY)),
        showlegend=True,
        legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center", font=dict(size=10)),
        height=300,
    )
    return fig


def build_symbol_signals_table(signals):
    if not signals:
        return html.Div("سیگنالی برای این نماد ثبت نشده است.", style={"color": MUT, "textAlign": "center", "padding": "20px"})

    header = html.Tr([
        html.Th("ID", style={"width": "4%"}),
        html.Th("زمان", style={"width": "10%"}),
        html.Th("جهت", style={"width": "7%"}),
        html.Th("حالت", style={"width": "6%"}),
        html.Th("ورود", style={"width": "9%"}),
        html.Th("🛑 SL", style={"width": "9%"}),
        html.Th("🎯 TP", style={"width": "9%"}),
        html.Th("حجم ($)", style={"width": "8%"}),
        html.Th("⚡ لوریج", style={"width": "6%"}),
        html.Th("اطمینان", style={"width": "6%"}),
        html.Th("وضعیت", style={"width": "8%"}),
        html.Th("PnL ($)", style={"width": "8%"}),
        html.Th("PnL (٪)", style={"width": "7%"}),
    ], style={"color": MUT, "fontSize": 9, "textAlign": "center"})

    rows = []
    for s in signals:
        if s["direction"] == 1:
            dir_text = "🟢 LONG"
            dir_color = UP
        elif s["direction"] == -1:
            dir_text = "🔴 SHORT"
            dir_color = DN
        else:
            dir_text = "⏸"
            dir_color = MUT

        status = s["status"]
        if status == "tp_hit":
            status_text = "🎯 TP"
            status_color = UP
            row_bg = "rgba(0,255,204,0.04)"
        elif status == "sl_hit":
            status_text = "🛑 SL"
            status_color = DN
            row_bg = "rgba(255,34,102,0.04)"
        elif status == "expired":
            status_text = "⏰ منقضی"
            status_color = MUT
            row_bg = "rgba(122,122,168,0.04)"
        elif status == "closed_manual":
            status_text = "✋ دستی"
            status_color = GOLD
            row_bg = "rgba(255,215,0,0.04)"
        else:
            status_text = "🔵 باز"
            status_color = BLUE
            row_bg = "rgba(0,170,255,0.04)"

        trading_mode = s.get("trading_mode", "normal")
        mode_text, mode_color = get_mode_badge(trading_mode)

        pnl = s["pnl"]
        pnl_pct = s["pnl_pct"]

        if pnl is not None:
            pnl_color = UP if pnl > 0 else DN
            pnl_text = f"${pnl:+,.2f}"
            pnl_pct_text = f"{pnl_pct:+.2f}%"
        else:
            pnl_color = MUT
            pnl_text = "—"
            pnl_pct_text = "—"

        leverage = s.get("leverage", 1.0) or 1.0
        if leverage >= 50:
            lev_color = DN
        elif leverage >= 20:
            lev_color = GOLD
        else:
            lev_color = UP

        conf = s["confidence"]
        conf_color = UP if conf >= 70 else (GOLD if conf >= 50 else DN)

        rows.append(html.Tr([
            html.Td(f"#{s['id']}", style={"color": MUT, "fontSize": "9px"}),
            html.Td(s["created_at"][-14:], style={"color": MUT, "fontSize": "9px"}),
            html.Td(dir_text, style={"color": dir_color, "fontWeight": "bold", "fontSize": "10px"}),
            html.Td(mode_text, style={"color": mode_color, "fontSize": "9px"}),
            html.Td(f"${s['entry_price']:,.4g}", style={"color": TXT, "fontSize": "10px"}),
            html.Td(f"${s['sl_price']:,.4g}", style={"color": DN, "fontSize": "10px"}),
            html.Td(f"${s['tp_price']:,.4g}", style={"color": UP, "fontSize": "10px"}),
            html.Td(f"${s['dollar_amount']:,.2f}", style={"color": BLUE, "fontSize": "10px"}),
            html.Td(f"{leverage:.1f}x", style={"color": lev_color, "fontWeight": "bold", "fontSize": "10px"}),
            html.Td(f"{conf:.0f}%", style={"color": conf_color, "fontSize": "10px"}),
            html.Td(status_text, style={"color": status_color, "fontWeight": "bold", "fontSize": "10px"}),
            html.Td(pnl_text, style={"color": pnl_color, "fontWeight": "bold", "fontSize": "10px"}),
            html.Td(pnl_pct_text, style={"color": pnl_color, "fontSize": "10px"}),
        ], style={"textAlign": "center", "background": row_bg}))

    return dbc.Table(
        [html.Thead(header), html.Tbody(rows)],
        bordered=False, hover=True, responsive=True, size="sm",
        style={"color": TXT},
    )


def build_resonance_gauge(resonance_data, symbol):
    score = resonance_data["score"]
    gauge_value = (score + 1) * 50

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=gauge_value,
        number={"font": {"color": GOLD, "size": 40, "family": FONT_FAMILY}},
        title={"text": f"رزونانس {symbol}", "font": {"color": TXT, "size": 14, "family": FONT_FAMILY}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": MUT, "tickfont": {"color": MUT, "size": 9}},
            "bar": {"color": UP if score > 0 else DN},
            "bgcolor": CARD2,
            "borderwidth": 0,
            "steps": [
                {"range": [0, 35], "color": "rgba(255,34,102,0.3)"},
                {"range": [35, 65], "color": "rgba(255,215,0,0.2)"},
                {"range": [65, 100], "color": "rgba(0,255,204,0.3)"},
            ],
            "threshold": {"line": {"color": GOLD, "width": 4}, "thickness": 0.75, "value": 50},
        },
    ))

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_FAMILY, color=TXT),
        margin=dict(l=30, r=30, t=60, b=30), height=250,
    )
    return fig


def build_cycle_alignment_figure(resonance_data, symbol):
    cycles = resonance_data["cycles"]
    fig = go.Figure()

    n_cycles = len(cycles)
    angles = np.linspace(0, 2 * np.pi, n_cycles, endpoint=False)

    for i, c in enumerate(cycles):
        angle = angles[i]
        direction = c["direction"]
        strength = c["strength"]

        x = np.cos(angle)
        y = np.sin(angle)
        color = UP if direction > 0 else (DN if direction < 0 else MUT)
        size = 10 + strength * 20

        fig.add_trace(go.Scatter(
            x=[x], y=[y], mode="markers+text",
            marker=dict(size=size, color=color, symbol="circle", opacity=0.8,
                        line=dict(width=2, color=BG)),
            text=[c["name"]], textposition="top center",
            textfont=dict(size=9, color=TXT, family=FONT_FAMILY),
            showlegend=False,
        ))

    theta = np.linspace(0, 2 * np.pi, 100)
    fig.add_trace(go.Scatter(
        x=np.cos(theta), y=np.sin(theta), mode="lines",
        line=dict(color=LINE, width=2), showlegend=False, hoverinfo="skip",
    ))

    score = resonance_data["score"]
    resonance_angle = np.pi / 2 if score > 0 else -np.pi / 2
    arrow_length = abs(score)

    fig.add_trace(go.Scatter(
        x=[0, arrow_length * np.cos(resonance_angle)],
        y=[0, arrow_length * np.sin(resonance_angle)],
        mode="lines", line=dict(color=GOLD, width=6),
        showlegend=False, hoverinfo="skip",
    ))

    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        title=dict(text=f"🌀 هم‌راستایی چرخه‌ها — {symbol}", x=0.5,
                   font=dict(color=CYAN, size=15, family=FONT_FAMILY)),
        xaxis=dict(visible=False, range=[-1.5, 1.5]),
        yaxis=dict(visible=False, range=[-1.5, 1.5], scaleanchor="x", scaleratio=1),
        margin=dict(l=20, r=20, t=60, b=20), height=400,
        font=dict(family=FONT_FAMILY, color=TXT),
    )
    return fig


def build_price_figure(df, symbol):
    if df.empty:
        return empty_fig("داده‌ای نیست.")

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df["ts"], open=df["open"], high=df["high"],
        low=df["low"], close=df["close"],
        name=f"{symbol}",
        increasing_line_color=UP, decreasing_line_color=DN,
    ))

    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
        margin=dict(l=50, r=20, t=50, b=40),
        xaxis=dict(color=MUT, gridcolor=LINE, rangeslider=dict(visible=False)),
        yaxis=dict(color=MUT, gridcolor=LINE, title="قیمت ($)"),
        font=dict(family=FONT_FAMILY, color=TXT),
        title=dict(text=f"📊 {symbol} — داده واقعی Bybit ({len(df)} کندل)",
                   x=0.5, font=dict(color=GOLD, size=14, family=FONT_FAMILY)),
        showlegend=False, height=400,
    )
    return fig


def build_signal_panel(signal_data, symbol):
    if signal_data["signal"] == 0:
        return html.Div([
            html.Div(f"⏸ در انتظار رزونانس برای {symbol}...", style={
                "textAlign": "center", "color": MUT, "padding": "20px", "fontSize": "14px",
            }),
            html.Div(f"امتیاز رزونانس فعلی: {signal_data['score']:+.3f}", style={
                "textAlign": "center", "color": MUT, "fontSize": "12px",
            }),
        ], className="glass-card", style={"padding": "15px"})

    dir_color = UP if signal_data["signal"] == 1 else DN
    dir_icon = "🟢 LONG" if signal_data["signal"] == 1 else "🔴 SHORT"

    aligned_cycles = [
        c for c in signal_data["resonance"]["cycles"]
        if c["direction"] == signal_data["signal"]
    ]
    aligned_cycles.sort(key=lambda x: x["weight"], reverse=True)

    cycle_chips = []
    for c in aligned_cycles[:5]:
        cycle_chips.append(html.Span(
            f"{c['name']} ({c['exp_return']*100:+.2f}%)",
            style={
                "display": "inline-block", "margin": "3px", "padding": "4px 8px",
                "background": "rgba(0,255,204,0.1)" if signal_data["signal"] == 1 else "rgba(255,34,102,0.1)",
                "border": f"1px solid {dir_color}", "borderRadius": "12px",
                "fontSize": "11px", "color": dir_color,
            },
        ))

    conf = signal_data["confidence"]
    conf_color = UP if conf >= 70 else (GOLD if conf >= 50 else DN)

    return html.Div([
        html.H4(f"سیگنال فعال {symbol}: {dir_icon}", style={
            "color": dir_color, "textAlign": "center", "fontWeight": 800,
            "textShadow": f"0 0 15px {dir_color}", "marginBottom": "15px",
        }),
        html.Div(f"امتیاز رزونانس: {signal_data['score']:+.3f}", style={
            "textAlign": "center", "color": GOLD, "fontSize": "18px", "fontWeight": "bold",
        }),
        html.Div(f"دلیل: {signal_data['reason']}", style={
            "textAlign": "center", "color": TXT, "fontSize": "13px", "marginTop": "10px",
        }),
        html.Div([
            html.Div(f"درجه اطمینان: {conf:.0f}%", style={
                "textAlign": "center", "color": conf_color, "fontSize": "14px",
                "fontWeight": "bold", "marginTop": "15px",
            }),
            html.Div(style={
                "width": "80%", "height": "10px", "background": LINE,
                "borderRadius": "5px", "overflow": "hidden", "margin": "10px auto",
            }, children=[
                html.Div(style={
                    "width": f"{conf}%", "height": "100%",
                    "background": conf_color, "borderRadius": "5px",
                })
            ]),
        ]),
        html.Div([
            html.Div("چرخه‌های هم‌راستا:", style={"color": MUT, "fontSize": "12px", "marginBottom": "5px"}),
            html.Div(cycle_chips, style={"textAlign": "center"}),
        ], style={"marginTop": "15px"}),
    ], className="glass-card", style={"padding": "20px", "border": f"1px solid {dir_color}"})


# ==============================================================================
# 9) اپ Dash
# ==============================================================================
FONT_URL = "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;800&display=swap"
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG, FONT_URL])
app.title = "Temporal Resonance Engine"
server = app.server

db = SignalDatabase(DB_PATH)

app.index_string = """<!DOCTYPE html>
<html dir="rtl" lang="fa">
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            body { 
                background: #030308; 
                direction: rtl;
                text-align: right;
            }
            
            * { 
                font-family: 'Vazirmatn', Tahoma, Arial, sans-serif !important; 
            }
            
            .glass-card {
                background: linear-gradient(145deg, rgba(16,16,37,0.9), rgba(5,5,15,0.95));
                border: 1px solid #252545;
                border-radius: 16px;
                box-shadow: 0 0 25px rgba(0,255,255,0.08);
                backdrop-filter: blur(10px);
                direction: rtl;
                text-align: right;
            }
            
            .stat-value { 
                font-weight: 800; 
                font-size: 22px; 
                text-shadow: 0 0 10px currentColor; 
            }
            
            .stat-label { 
                font-size: 11px; 
                color: #7a7aa8; 
                text-transform: uppercase; 
                letter-spacing: 1px; 
            }
            
            .Select-control,
            .Select-menu-outer,
            .Select-menu,
            .VirtualizedSelectMenu,
            .dash-dropdown,
            .dash-dropdown .Select-control {
                background-color: #101025 !important;
                border-color: #252545 !important;
                color: #e8e8ff !important;
                z-index: 9999 !important;
                position: relative;
            }
            
            .Select-menu-outer {
                z-index: 99999 !important;
                position: absolute !important;
                background-color: #0a0a18 !important;
                border: 1px solid #252545 !important;
                border-radius: 8px !important;
                max-height: 300px !important;
                overflow-y: auto !important;
                box-shadow: 0 10px 40px rgba(0,0,0,0.8) !important;
            }
            
            .Select-menu {
                max-height: 298px !important;
                overflow-y: auto !important;
            }
            
            .Select-option {
                background-color: #0a0a18 !important;
                color: #e8e8ff !important;
                padding: 8px 12px !important;
                cursor: pointer;
            }
            
            .Select-option:hover,
            .Select-option.is-focused {
                background-color: #1a1a35 !important;
                color: #00ffcc !important;
            }
            
            .Select-option.is-selected {
                background-color: #1a2a4a !important;
                color: #ffd700 !important;
            }
            
            table {
                direction: rtl;
                text-align: right;
            }
            
            table th,
            table td {
                text-align: right !important;
                padding: 6px 8px !important;
            }
            
            .nav-tabs {
                direction: rtl;
            }
            
            .nav-tabs .nav-item {
                margin-left: 0 !important;
                margin-right: 4px;
            }
            
            .btn {
                direction: rtl;
            }
            
            input[type="text"],
            input[type="number"],
            input[type="email"],
            input[type="password"] {
                direction: rtl;
                text-align: right;
                background-color: #101025 !important;
                border-color: #252545 !important;
                color: #e8e8ff !important;
            }
            
            .rc-slider {
                direction: ltr;
            }
            
            label {
                direction: rtl;
                text-align: right;
            }
            
            ::-webkit-scrollbar {
                width: 8px;
                height: 8px;
            }
            
            ::-webkit-scrollbar-track {
                background: #0a0a18;
            }
            
            ::-webkit-scrollbar-thumb {
                background: #252545;
                border-radius: 4px;
            }
            
            ::-webkit-scrollbar-thumb:hover {
                background: #353560;
            }
            
            .dash-table-container {
                direction: rtl;
            }
            
            .dash-modal,
            .dash-popup {
                z-index: 100000 !important;
            }
            
            .tooltip,
            .dash-tooltip {
                z-index: 99999 !important;
            }
        </style>
    </head>
    <body dir="rtl">
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""


def stat_card(id_prefix, label, color=TXT):
    return dbc.Col(html.Div([
        html.Div(label, className="stat-label"),
        html.Div("—", id=f"{id_prefix}-value", className="stat-value", style={"color": color}),
    ], className="glass-card", style={"padding": "15px", "textAlign": "center"}), md=3, xs=6)


app.layout = html.Div([
    html.Div([
        html.H3("🌌 Temporal Resonance Engine", style={
            "color": CYAN, "fontWeight": 800, "margin": 0,
            "textShadow": "0 0 20px rgba(0,255,255,0.5)",
        }),
        html.Div("موتور معاملاتی رزونانس چرخه‌های زمانی — کنترل مارجین — Morindok", style={
            "color": MUT, "fontSize": 13,
        }),
    ], style={"maxWidth": 1200, "margin": "15px auto 10px auto", "padding": "0 15px"}),

    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([
            html.Label("🪙 نماد / ارز", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="symbol", value="BTCUSDT", clearable=False, options=SYMBOL_OPTIONS),
        ], md=2),
        dbc.Col([
            html.Label("تایم‌فریم", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="interval", value="15", clearable=False, options=[
                {"label": "5m", "value": "5"},
                {"label": "15m", "value": "15"},
                {"label": "30m", "value": "30"},
                {"label": "1h", "value": "60"},
                {"label": "4h", "value": "240"},
            ]),
        ], md=1),
        dbc.Col([
            html.Label("⚡ حالت معاملاتی", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="trading-mode", value="aggressive", clearable=False, options=TRADING_MODE_OPTIONS),
        ], md=2),
        dbc.Col([
            html.Label("موجودی اولیه ($)", style={"fontSize": 11, "color": MUT}),
            dcc.Input(id="initial-balance", type="number", value=DEFAULT_BALANCE, min=10, step=50,
                      style={"width": "100%", "padding": 6, "borderRadius": 8,
                             "background": CARD2, "color": TXT, "border": f"1px solid {LINE}"}),
        ], md=2),
        dbc.Col([
            html.Label("آستانه رزونانس", style={"fontSize": 11, "color": MUT}),
            dcc.Slider(id="threshold", min=0.2, max=0.6, step=0.05, value=0.35,
                       marks={0.2: "0.2", 0.35: "0.35", 0.5: "0.5", 0.6: "0.6"}),
        ], md=3),
        dbc.Col(
            dbc.Button("🔄", id="refresh-btn", color="primary", className="mt-4",
                       style={"width": "100%", "fontWeight": "bold"}),
            md=1,
        ),
    ])), className="glass-card", style={"maxWidth": 1200, "margin": "10px auto"}),

    html.Div(id="mode-info-panel", style={"maxWidth": 1200, "margin": "10px auto"}),

    html.Div(dbc.Row([
        stat_card("live-price", "قیمت فعلی", GOLD),
        stat_card("resonance-score", "امتیاز رزونانس", CYAN),
        stat_card("signal", "سیگنال", UP),
        stat_card("data-status", "وضعیت داده", MUT),
    ]), style={"maxWidth": 1200, "margin": "10px auto"}),

    html.Div(id="signal-panel", style={"maxWidth": 1200, "margin": "15px auto"}),

    dbc.Tabs([
        dbc.Tab(label="🌀 رزونانس", tab_id="tab-resonance", children=[
            dbc.Row([
                dbc.Col(dbc.Card(dbc.CardBody([
                    dcc.Graph(id="resonance-gauge", config={"displaylogo": False}),
                ]), className="glass-card"), md=4),
                dbc.Col(dbc.Card(dbc.CardBody([
                    dcc.Graph(id="cycle-alignment-graph", config={"displaylogo": False}),
                ]), className="glass-card"), md=8),
            ], style={"margin": "15px 0"}),
            dbc.Row([
                dbc.Col(dbc.Card(dbc.CardBody([
                    dcc.Graph(id="price-graph", config={"displaylogo": False}),
                ]), className="glass-card"), md=12),
            ]),
        ]),

        dbc.Tab(label="📡 سیگنال‌ها", tab_id="tab-signals", children=[
            html.Div([
                html.Div("📌 معاملات باز واقعی با PnL زنده | کنترل مارجین فعال",
                         style={"fontSize": 12, "color": MUT, "margin": "15px 5px"}),
                dbc.Button("🔍 اسکن همه ارزها + طلا", id="scan-btn", color="info",
                           style={"margin": "10px 5px", "fontWeight": "bold"}),
            ]),
            html.Div(id="signals-summary", style={"margin": "15px 0"}),
            dbc.Card(dbc.CardBody([
                html.H5("💼 معاملات باز — PnL زنده", style={
                    "color": CYAN, "fontSize": "14px", "marginBottom": "10px",
                    "textShadow": "0 0 10px rgba(0,255,255,0.3)",
                }),
                html.Div(id="open-positions-table"),
            ]), className="glass-card", style={"margin": "10px 0"}),
            dbc.Card(dbc.CardBody([
                html.H5("🔍 نتایج اسکن (پیش‌بینی — بدون PnL)", style={
                    "color": MUT, "fontSize": "13px", "marginBottom": "10px",
                }),
                html.Div(id="scan-results-table"),
            ]), className="glass-card"),
        ]),

        dbc.Tab(label="📈 آمار سیگنال‌ها", tab_id="tab-symbol-stats", children=[
            html.Div([
                html.Div("آمار جزئی وین‌ریت و عملکرد سیگنال‌های گذشته برای ارز انتخاب‌شده",
                         style={"fontSize": 12, "color": MUT, "margin": "15px 5px"}),
                dbc.Button("🔄 به‌روزرسانی آمار", id="refresh-stats-btn", color="info",
                           style={"margin": "10px 5px", "fontWeight": "bold"}),
            ]),
            html.Div(id="symbol-stats-kpis", style={"margin": "15px 0"}),
            html.Div(id="symbol-stats-detail", style={"margin": "10px 0"}),
            dbc.Row([
                dbc.Col(dbc.Card(dbc.CardBody([
                    dcc.Graph(id="symbol-pnl-chart", config={"displaylogo": False}),
                ]), className="glass-card"), md=7),
                dbc.Col(dbc.Card(dbc.CardBody([
                    dcc.Graph(id="symbol-status-chart", config={"displaylogo": False}),
                ]), className="glass-card"), md=5),
            ], style={"margin": "15px 0"}),
            dbc.Card(dbc.CardBody([
                html.H5("📋 سیگنال‌های گذشته این نماد", style={
                    "color": GOLD, "fontSize": "14px", "marginBottom": "10px", "textAlign": "center",
                }),
                html.Div(id="symbol-signals-table"),
            ]), className="glass-card"),
        ]),

        dbc.Tab(label="📋 تاریخچه سیگنال‌ها", tab_id="tab-history", children=[
            html.Div([
                html.Div("PnL معاملات باز به‌صورت زنده آپدیت می‌شود — سود کل = قطعی + شناور",
                         style={"fontSize": 12, "color": MUT, "margin": "15px 5px"}),
                dbc.Button("🔄 به‌روزرسانی تاریخچه", id="history-refresh-btn", color="warning",
                           style={"margin": "10px 5px", "fontWeight": "bold"}),
            ]),
            html.Div(id="history-stats", style={"margin": "15px 0"}),
            dbc.Card(dbc.CardBody([
                html.Div(id="history-table"),
            ]), className="glass-card"),
        ]),
    ], id="main-tabs", active_tab="tab-resonance", style={"maxWidth": 1200, "margin": "0 auto"}),

    html.Div(
        "💡 کنترل مارجین فعال: مجموع مارجین‌های معاملات باز هیچوقت از سرمایه بیشتر نمی‌شود. "
        "قبل از هر معامله جدید، مارجین آزاد بررسی می‌شود.",
        style={"fontSize": 11, "color": MUT, "marginTop": 20, "direction": "rtl", "lineHeight": "1.8",
               "textAlign": "center", "maxWidth": 1200, "margin": "20px auto", "padding": "0 15px 20px 15px"},
    ),

    dcc.Interval(id="tick", interval=60_000, n_intervals=0),
    dcc.Interval(id="positions-pnl-tick", interval=10_000, n_intervals=0),
    dcc.Interval(id="db-update-tick", interval=30_000, n_intervals=0),
    dcc.Interval(id="history-pnl-tick", interval=10_000, n_intervals=0),
    dcc.Store(id="scan-results-store"),
], style={"background": BG, "minHeight": "100vh", "padding": "10px", "fontFamily": FONT_FAMILY})


# ==============================================================================
# 10) Callbacks
# ==============================================================================
@app.callback(
    Output("live-price-value", "children"),
    Output("resonance-score-value", "children"),
    Output("signal-value", "children"),
    Output("data-status-value", "children"),
    Output("signal-panel", "children"),
    Output("resonance-gauge", "figure"),
    Output("cycle-alignment-graph", "figure"),
    Output("price-graph", "figure"),
    Input("tick", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    State("symbol", "value"),
    State("interval", "value"),
    State("threshold", "value"),
)
def update_main(_n, _click, symbol, interval, threshold):
    symbol = symbol or "BTCUSDT"
    interval = interval or "15"
    interval_min = get_interval_minutes(interval)

    df = get_klines(symbol, interval, limit=1000)

    if df.empty or len(df) < BACKTEST_MIN_HISTORY:
        return "—", "—", "—", "🔴 خطا در اتصال", html.Div(), \
               empty_fig("داده کافی نیست."), empty_fig("داده کافی نیست."), empty_fig("داده کافی نیست.")

    cycle_engine = CycleEngine(forecast_horizon_hours=4)
    cycle_engine.build_phase_return_maps(df, interval_min)

    current_time = pd.to_datetime(df["ts"].iloc[-1]).to_pydatetime().replace(tzinfo=timezone.utc)

    signal_engine = TemporalSignalEngine(cycle_engine, entry_threshold=threshold)
    signal_data = signal_engine.generate_signal(current_time)

    live_price = df["close"].iloc[-1]
    score = signal_data["score"]

    if signal_data["signal"] == 1:
        signal_text = "🟢 LONG"
    elif signal_data["signal"] == -1:
        signal_text = "🔴 SHORT"
    else:
        signal_text = "⏸ خنثی"

    gauge_fig = build_resonance_gauge(signal_data["resonance"], symbol)
    alignment_fig = build_cycle_alignment_figure(signal_data["resonance"], symbol)
    price_fig = build_price_figure(df, symbol)

    signal_panel = build_signal_panel(signal_data, symbol)

    data_status = f"🟢 Bybit | {len(df)} کندل"

    return (
        f"${live_price:,.4g}",
        f"{score:+.3f}",
        signal_text,
        data_status,
        signal_panel,
        gauge_fig,
        alignment_fig,
        price_fig,
    )


@app.callback(
    Output("mode-info-panel", "children"),
    Input("trading-mode", "value"),
    State("initial-balance", "value"),
)
def update_mode_info(trading_mode, balance):
    try:
        balance = float(balance or DEFAULT_BALANCE)
    except Exception:
        balance = DEFAULT_BALANCE
    return build_mode_info_panel(trading_mode or "normal", balance, db)


@app.callback(
    Output("scan-results-store", "data"),
    Output("signals-summary", "children"),
    Output("open-positions-table", "children"),
    Output("scan-results-table", "children"),
    Input("scan-btn", "n_clicks"),
    State("interval", "value"),
    State("initial-balance", "value"),
    State("threshold", "value"),
    State("trading-mode", "value"),
)
def scan_signals(_click, interval, balance, threshold, trading_mode):
    interval = interval or "15"
    trading_mode = trading_mode or "normal"

    try:
        balance = float(balance or DEFAULT_BALANCE)
        risk_pct_val = TRADING_MODES.get(trading_mode, TRADING_MODES["normal"])["risk_pct"]
        threshold_val = float(threshold or 0.35)
    except Exception:
        balance = DEFAULT_BALANCE
        risk_pct_val = TRADING_MODES["normal"]["risk_pct"]
        threshold_val = 0.35

    # آپدیت نتایج سیگنال‌های باز قبلی
    update_open_signals_results(db)

    # ★ اسکن با کنترل مارجین
    signals_data, skipped_no_margin = scan_all_symbols(
        interval, balance, risk_pct_val, threshold_val, trading_mode, db
    )

    if not signals_data and not skipped_no_margin:
        return [], html.Div("خطا در اسکن یا سیگنالی یافت نشد.", style={"color": DN}), \
               html.Div("خطا در دریافت داده.", style={"color": DN}), html.Div()

    # ذخیره سیگنال‌ها با بررسی نهایی مارجین
    saved_count = 0
    for sig in signals_data:
        if sig["signal"] != 0:
            # بررسی نهایی مارجین قبل از ذخیره
            available_margin = get_available_margin(balance, db)
            if sig["margin_used"] <= available_margin and not db.has_open_signal(sig["symbol"]):
                db.save_signal(sig, interval, threshold_val)
                saved_count += 1

    # خواندن معاملات باز
    open_signals = db.get_open_signals()
    live_pnls = calculate_open_pnls_live(db)

    total_pnl_closed = db.get_total_pnl()
    open_pnl_estimate = sum(p["pnl"] for p in live_pnls.values())
    current_balance = balance + total_pnl_closed + open_pnl_estimate

    # اطلاعات مارجین
    used_margin = get_total_open_margin(db)
    available_margin = balance - used_margin
    margin_info = {
        "used": used_margin,
        "available": available_margin,
        "total": balance,
    }

    summary = build_signals_summary(
        signals_data, total_pnl_closed, current_balance, 
        open_pnl_estimate, trading_mode, margin_info
    )
    positions_table = build_open_positions_table(open_signals, live_pnls)
    scan_table = build_scan_results_table(signals_data)

    return signals_data, summary, positions_table, scan_table


@app.callback(
    Output("open-positions-table", "children", allow_duplicate=True),
    Output("signals-summary", "children", allow_duplicate=True),
    Input("positions-pnl-tick", "n_intervals"),
    State("initial-balance", "value"),
    State("main-tabs", "active_tab"),
    State("scan-results-store", "data"),
    State("trading-mode", "value"),
    prevent_initial_call=True,
)
def update_positions_pnl_live(_tick, balance, active_tab, scan_data, trading_mode):
    if active_tab != "tab-signals":
        return dash.no_update, dash.no_update

    try:
        balance = float(balance or DEFAULT_BALANCE)
    except Exception:
        balance = DEFAULT_BALANCE

    trading_mode = trading_mode or "normal"

    update_open_signals_results(db)

    open_signals = db.get_open_signals()
    live_pnls = calculate_open_pnls_live(db)

    total_pnl_closed = db.get_total_pnl()
    open_pnl_estimate = sum(p["pnl"] for p in live_pnls.values())
    current_balance = balance + total_pnl_closed + open_pnl_estimate

    # اطلاعات مارجین
    used_margin = get_total_open_margin(db)
    available_margin = balance - used_margin
    margin_info = {
        "used": used_margin,
        "available": available_margin,
        "total": balance,
    }

    positions_table = build_open_positions_table(open_signals, live_pnls)

    scan_data = scan_data or []
    summary = build_signals_summary(
        scan_data, total_pnl_closed, current_balance, 
        open_pnl_estimate, trading_mode, margin_info
    )

    return positions_table, summary


@app.callback(
    Output("symbol-stats-kpis", "children"),
    Output("symbol-stats-detail", "children"),
    Output("symbol-pnl-chart", "figure"),
    Output("symbol-status-chart", "figure"),
    Output("symbol-signals-table", "children"),
    Input("symbol", "value"),
    Input("refresh-stats-btn", "n_clicks"),
    Input("db-update-tick", "n_intervals"),
)
def update_symbol_stats(symbol, _click, _tick):
    symbol = symbol or "BTCUSDT"

    update_open_signals_results(db)

    stats = db.get_symbol_stats(symbol)
    signals = db.get_symbol_signals(symbol, limit=50)

    if not stats:
        symbol_info = SYMBOLS.get(symbol, {"icon": "•", "name": symbol})
        no_data_msg = html.Div(
            f"📭 هنوز سیگنالی برای {symbol_info['icon']} {symbol} ثبت نشده است. "
            f"ابتدا اسکن کنید تا سیگنال‌ها ذخیره شوند.",
            style={"color": MUT, "textAlign": "center", "padding": "30px", "fontSize": "13px"}
        )
        return no_data_msg, html.Div(), empty_fig("داده‌ای نیست."), empty_fig("داده‌ای نیست."), html.Div()

    kpis = build_symbol_stats_kpis(stats)
    detail = build_symbol_stats_detail(stats)
    pnl_chart = build_symbol_cumulative_pnl_chart(stats)
    status_chart = build_symbol_status_chart(stats)
    signals_table = build_symbol_signals_table(signals)

    return kpis, detail, pnl_chart, status_chart, signals_table


@app.callback(
    Output("history-stats", "children"),
    Output("history-table", "children"),
    Input("history-refresh-btn", "n_clicks"),
    Input("db-update-tick", "n_intervals"),
    Input("main-tabs", "active_tab"),
    State("initial-balance", "value"),
)
def update_history(_click, _tick, active_tab, balance):
    try:
        balance = float(balance or DEFAULT_BALANCE)
    except Exception:
        balance = DEFAULT_BALANCE

    update_open_signals_results(db)

    live_pnls = calculate_open_pnls_live(db)
    open_pnl_estimate = sum(p["pnl"] for p in live_pnls.values())

    stats = db.get_signal_stats(balance)
    signals_from_db = db.get_all_signals(limit=200)

    stats_ui = build_history_stats(stats, open_pnl_estimate)
    table_ui = build_history_table(signals_from_db, live_pnls)

    return stats_ui, table_ui


@app.callback(
    Output("history-table", "children", allow_duplicate=True),
    Output("history-stats", "children", allow_duplicate=True),
    Input("history-pnl-tick", "n_intervals"),
    State("initial-balance", "value"),
    State("main-tabs", "active_tab"),
    prevent_initial_call=True,
)
def update_history_pnl_live(_tick, balance, active_tab):
    if active_tab != "tab-history":
        return dash.no_update, dash.no_update

    try:
        balance = float(balance or DEFAULT_BALANCE)
    except Exception:
        balance = DEFAULT_BALANCE

    live_pnls = calculate_open_pnls_live(db)
    open_pnl_estimate = sum(p["pnl"] for p in live_pnls.values())

    stats = db.get_signal_stats(balance)
    signals_from_db = db.get_all_signals(limit=200)

    stats_ui = build_history_stats(stats, open_pnl_estimate)
    table_ui = build_history_table(signals_from_db, live_pnls)

    return table_ui, stats_ui


@app.callback(
    Output("open-positions-table", "children", allow_duplicate=True),
    Output("history-table", "children", allow_duplicate=True),
    Output("history-stats", "children", allow_duplicate=True),
    Input({"type": "close-btn", "index": ALL}, "n_clicks"),
    State("initial-balance", "value"),
    State("main-tabs", "active_tab"),
    prevent_initial_call=True,
)
def close_signal_callback(n_clicks_list, balance, active_tab):
    if not any(n_clicks_list):
        return dash.no_update, dash.no_update, dash.no_update

    triggered = ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return dash.no_update, dash.no_update, dash.no_update

    signal_id = triggered.get("index")
    if signal_id is None:
        return dash.no_update, dash.no_update, dash.no_update

    sig = db.get_signal_by_id(signal_id)
    if not sig or sig["status"] != "open":
        return dash.no_update, dash.no_update, dash.no_update

    df = get_klines(sig["symbol"], "1", limit=1)
    if df.empty:
        return dash.no_update, dash.no_update, dash.no_update

    current_price = df["close"].iloc[-1]
    current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    entry_price = sig["entry_price"]
    direction = sig["direction"]
    dollar_amount = sig["dollar_amount"]
    size = dollar_amount / entry_price if entry_price > 0 else 0

    if direction == 1:
        pnl = (current_price - entry_price) * size
    else:
        pnl = (entry_price - current_price) * size

    pnl_pct = (pnl / dollar_amount * 100) if dollar_amount > 0 else 0

    db.close_signal(signal_id, current_price, current_time, pnl, pnl_pct, "Manual Close ✋")

    try:
        balance = float(balance or DEFAULT_BALANCE)
    except Exception:
        balance = DEFAULT_BALANCE

    open_signals = db.get_open_signals()
    live_pnls = calculate_open_pnls_live(db)
    open_pnl_estimate = sum(p["pnl"] for p in live_pnls.values())

    positions_table = build_open_positions_table(open_signals, live_pnls)

    stats = db.get_signal_stats(balance)
    signals_from_db = db.get_all_signals(limit=200)
    stats_ui = build_history_stats(stats, open_pnl_estimate)
    history_table = build_history_table(signals_from_db, live_pnls)

    return positions_table, history_table, stats_ui


# ==============================================================================
# 11) اجرا با باز شدن خودکار مرورگر
# ==============================================================================
def open_browser():
    webbrowser.open("http://127.0.0.1:8050")


if __name__ == "__main__":
    threading.Timer(2, open_browser).start()

    print("=" * 60)
    print("🌌 Temporal Resonance Engine v16")
    print("   ✅ کنترل مارجین فعال")
    print("   🥇 طلا (XAUUSDT)")
    print("   🌐 آدرس: http://127.0.0.1:8050")
    print("=" * 60)

    app.run(debug=True, host="0.0.0.0", port=8050, use_reloader=False)