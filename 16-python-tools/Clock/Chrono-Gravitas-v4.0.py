# -*- coding: utf-8 -*-
"""
🪐 Chrono-Gravitas v5.0 — سیستم بک‌تست با ریسک به ریوارد 2 و مدیریت سرمایه
=============================================================================
{Morindok}

این سیستم:
  ۱. ریسک به ریوارد 1:2 (حد ضرر 1 واحد، حد سود 2 واحد)
  ۲. مدیریت سرمایه با ریسک ثابت درصدی
  ۳. Win Rate بر اساس ریسک به ریوارد 2
  ۴. محاسبه Expectancy و Kelly Criterion
  ۵. بک‌تست تاریخی چند ماهه
"""

import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash
from dash import dcc, html, Input, Output, State, dash_table, callback
import dash_bootstrap_components as dbc

# ==============================================================================
# 0) ثابت‌های علمی سیارات منظومه شمسی
# ==============================================================================

PLANETS = {
    "Mercury": {
        "name_fa": "عطارد",
        "color": "#A0522D",
        "rotation_period_hours": 1407.6,
        "orbital_period_days": 87.97,
        "mass_kg": 3.3011e23,
        "radius_km": 2439.7,
        "gravity_m_s2": 3.7,
        "distance_from_sun_km": 57.9e6,
    },
    "Venus": {
        "name_fa": "زهره",
        "color": "#FFD700",
        "rotation_period_hours": 5832.5,
        "orbital_period_days": 224.7,
        "mass_kg": 4.8675e24,
        "radius_km": 6051.8,
        "gravity_m_s2": 8.87,
        "distance_from_sun_km": 108.2e6,
    },
    "Earth": {
        "name_fa": "زمین",
        "color": "#1E90FF",
        "rotation_period_hours": 23.934,
        "orbital_period_days": 365.25,
        "mass_kg": 5.972e24,
        "radius_km": 6371.0,
        "gravity_m_s2": 9.81,
        "distance_from_sun_km": 149.6e6,
    },
    "Mars": {
        "name_fa": "مریخ",
        "color": "#DC143C",
        "rotation_period_hours": 24.623,
        "orbital_period_days": 687.0,
        "mass_kg": 6.4171e23,
        "radius_km": 3389.5,
        "gravity_m_s2": 3.72,
        "distance_from_sun_km": 227.9e6,
    },
    "Jupiter": {
        "name_fa": "مشتری",
        "color": "#FFA500",
        "rotation_period_hours": 9.925,
        "orbital_period_days": 4331.0,
        "mass_kg": 1.8982e27,
        "radius_km": 69911.0,
        "gravity_m_s2": 24.79,
        "distance_from_sun_km": 778.6e6,
    },
    "Saturn": {
        "name_fa": "زحل",
        "color": "#F0E68C",
        "rotation_period_hours": 10.656,
        "orbital_period_days": 10747.0,
        "mass_kg": 5.6834e26,
        "radius_km": 58232.0,
        "gravity_m_s2": 10.44,
        "distance_from_sun_km": 1433.5e6,
    },
    "Uranus": {
        "name_fa": "اورانوس",
        "color": "#40E0D0",
        "rotation_period_hours": 17.24,
        "orbital_period_days": 30589.0,
        "mass_kg": 8.6810e25,
        "radius_km": 25362.0,
        "gravity_m_s2": 8.69,
        "distance_from_sun_km": 2872.5e6,
    },
    "Neptune": {
        "name_fa": "نپتون",
        "color": "#4169E1",
        "rotation_period_hours": 16.11,
        "orbital_period_days": 59800.0,
        "mass_kg": 1.02413e26,
        "radius_km": 24622.0,
        "gravity_m_s2": 11.15,
        "distance_from_sun_km": 4495.1e6,
    },
}

G = 6.67430e-11

# ==============================================================================
# 1) پالت رنگی و تنظیمات
# ==============================================================================

BG = "#070b14"
CARD = "#0f1830"
CARD2 = "#101c38"
LINE = "#22304e"
TXT = "#eef2fb"
MUT = "#8ea0c4"
GOLD = "#f3ba2f"
UP = "#1fd7a6"
DN = "#ff5d6c"
BLUE = "#4f8dfd"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_CATEGORY = "linear"
DEFAULT_INTERVAL = "60"
FORECAST_HOURS = 12

# پارامترهای مدیریت سرمایه
INITIAL_CAPITAL = 10000  # سرمایه اولیه (دلار)
RISK_PER_TRADE = 1.0  # ریسک هر معامله به درصد از سرمایه
RISK_REWARD_RATIO = 2.0  # ریسک به ریوارد 1:2
STOP_LOSS_PCT = 1.5  # حد ضرر به درصد
TAKE_PROFIT_PCT = 3.0  # حد سود به درصد (2 برابر حد ضرر)

FONT_FAMILY = "Vazirmatn, Tahoma, Arial, sans-serif"

# ==============================================================================
# 2) REST API پایدار بایبیت با Pagination
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
})

_ACTIVE_REST_BASE = {"url": None}


def bybit_get(path, params, timeout=15):
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


def get_server_time():
    d = bybit_get("/v5/market/time", {})
    try:
        res = (d or {}).get("result") or {}
        nano = res.get("timeNano")
        if nano:
            return datetime.fromtimestamp(int(nano) / 1e9, tz=timezone.utc)
        sec = res.get("timeSecond")
        if sec:
            v = int(sec)
            s = str(v)
            if len(s) >= 19:
                sec_f = v / 1e9
            elif len(s) >= 16:
                sec_f = v / 1e6
            elif len(s) >= 13:
                sec_f = v / 1e3
            else:
                sec_f = float(v)
            return datetime.fromtimestamp(sec_f, tz=timezone.utc)
    except Exception:
        pass
    return datetime.now(timezone.utc)


def get_klines_with_pagination(symbol, interval, category="linear", months=3):
    """دریافت داده‌های تاریخی چند ماهه با pagination"""
    all_data = []
    interval_map = {"1": 1, "5": 5, "15": 15, "30": 30, "60": 60, "240": 240}
    interval_minutes = interval_map.get(interval, 60)

    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=months * 30)

    current_end = int(now.timestamp() * 1000)
    start_ts = int(start_time.timestamp() * 1000)

    max_iterations = 100

    for _ in range(max_iterations):
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": 1000,
            "end": current_end,
        }

        d = bybit_get("/v5/market/kline", params)
        if not d or "list" not in (d.get("result") or {}):
            break

        lst = d["result"]["list"]
        if not lst:
            break

        all_data.extend(lst)

        oldest_ts = int(lst[-1][0])
        if oldest_ts <= start_ts or len(lst) < 1000:
            break

        current_end = oldest_ts - 1

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(
        all_data,
        columns=["ts", "open", "high", "low", "close", "volume", "turnover"],
    )
    df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)

    df = df.sort_values("ts").reset_index(drop=True)
    df = df.drop_duplicates(subset=["ts"]).reset_index(drop=True)

    return df


def get_interval_minutes(interval):
    s = str(interval).strip().lower()
    if s == "d":
        return 1440
    try:
        return int(s)
    except Exception:
        return 60


# ==============================================================================
# 3) محاسبات زمانی سیاره‌ای
# ==============================================================================

def calculate_planet_time(planet_name: str, earth_utc: datetime) -> Dict:
    planet = PLANETS[planet_name]
    epoch = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    delta_seconds = (earth_utc - epoch).total_seconds()
    rotation_seconds = planet["rotation_period_hours"] * 3600
    rotation_fraction = (delta_seconds % rotation_seconds) / rotation_seconds
    planet_hour = rotation_fraction * 24
    rotation_count = delta_seconds / rotation_seconds
    orbital_seconds = planet["orbital_period_days"] * 24 * 3600
    orbital_fraction = (delta_seconds % orbital_seconds) / orbital_seconds
    orbital_count = delta_seconds / orbital_seconds

    return {
        "planet_name": planet_name,
        "planet_name_fa": planet["name_fa"],
        "color": planet["color"],
        "local_hour": planet_hour,
        "rotation_fraction": rotation_fraction,
        "day_number": rotation_count,
        "orbital_fraction": orbital_fraction,
        "year_number": orbital_count,
        "rotation_period_hours": planet["rotation_period_hours"],
        "gravity": planet["gravity_m_s2"],
        "mass": planet["mass_kg"],
    }


def calculate_all_planet_times(earth_utc: datetime) -> List[Dict]:
    return [calculate_planet_time(planet, earth_utc) for planet in PLANETS.keys()]


def calculate_universal_time(planet_times: List[Dict]) -> float:
    total_mass = sum(p["mass"] for p in planet_times)
    weighted_time = 0
    for p in planet_times:
        weight = p["mass"] / total_mass
        time_fraction = p["rotation_fraction"]
        weighted_time += weight * time_fraction
    return weighted_time


# ==============================================================================
# 4) محاسبات گرانشی و حمایت/مقاومت
# ==============================================================================

def calculate_gravitational_force(planet_mass: float, distance_km: float,
                                  btc_price: float) -> float:
    distance_m = distance_km * 1000
    btc_mass = btc_price * 1e10
    force = G * planet_mass * btc_mass / (distance_m ** 2)
    return force


def calculate_gravitational_support_resistance(df: pd.DataFrame,
                                               earth_utc: datetime,
                                               price_index: int = -1) -> Dict:
    if price_index == -1:
        price_index = len(df) - 1

    live_price = float(df.iloc[price_index]["close"])
    planet_times = calculate_all_planet_times(earth_utc)

    forces = {}
    for p in planet_times:
        planet_data = PLANETS[p["planet_name"]]
        force = calculate_gravitational_force(
            planet_data["mass_kg"],
            planet_data["distance_from_sun_km"],
            live_price
        )
        forces[p["planet_name"]] = force

    max_force = max(forces.values()) if forces else 1
    normalized_forces = {k: v / max_force for k, v in forces.items()}

    support_levels = []
    resistance_levels = []

    for p in planet_times:
        planet_name = p["planet_name"]
        local_hour = p["local_hour"]
        force_weight = normalized_forces[planet_name]

        time_angle = local_hour / 24 * 360
        price_impact_pct = force_weight * 5

        if 0 <= local_hour < 12:
            support_offset = price_impact_pct * (1 - local_hour / 12)
            support_price = live_price * (1 - support_offset / 100)
            support_levels.append({
                "planet": planet_name,
                "planet_fa": p["planet_name_fa"],
                "price": support_price,
                "strength": force_weight,
                "local_hour": local_hour,
                "color": p["color"],
                "timestamp": earth_utc,
            })
        else:
            resistance_offset = price_impact_pct * ((local_hour - 12) / 12)
            resistance_price = live_price * (1 + resistance_offset / 100)
            resistance_levels.append({
                "planet": planet_name,
                "planet_fa": p["planet_name_fa"],
                "price": resistance_price,
                "strength": force_weight,
                "local_hour": local_hour,
                "color": p["color"],
                "timestamp": earth_utc,
            })

    support_levels.sort(key=lambda x: x["strength"], reverse=True)
    resistance_levels.sort(key=lambda x: x["strength"], reverse=True)

    return {
        "live_price": live_price,
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "forces": normalized_forces,
        "planet_times": planet_times,
        "timestamp": earth_utc,
    }


# ==============================================================================
# 5) سیستم مدیریت سرمایه
# ==============================================================================

class CapitalManager:
    """سیستم مدیریت سرمایه"""

    def __init__(self, initial_capital: float, risk_per_trade: float,
                 risk_reward_ratio: float):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.risk_per_trade = risk_per_trade  # درصد از سرمایه
        self.risk_reward_ratio = risk_reward_ratio
        self.trades_history = []
        self.equity_curve = []
        self.max_drawdown = 0
        self.peak_capital = initial_capital

    def calculate_position_size(self, entry_price: float, stop_loss_pct: float) -> float:
        """محاسبه اندازه پوزیشن بر اساس ریسک"""
        risk_amount = self.current_capital * (self.risk_per_trade / 100)
        stop_loss_price = entry_price * (stop_loss_pct / 100)
        position_size = risk_amount / stop_loss_price if stop_loss_price > 0 else 0
        return position_size

    def update_capital(self, pnl: float):
        """به‌روزرسانی سرمایه"""
        self.current_capital += pnl
        self.trades_history.append({
            "capital": self.current_capital,
            "pnl": pnl,
        })

        # به‌روزرسانی peak و drawdown
        if self.current_capital > self.peak_capital:
            self.peak_capital = self.current_capital

        current_drawdown = (self.peak_capital - self.current_capital) / self.peak_capital * 100
        if current_drawdown > self.max_drawdown:
            self.max_drawdown = current_drawdown

    def get_stats(self) -> Dict:
        """دریافت آمار مدیریت سرمایه"""
        total_return = ((self.current_capital - self.initial_capital) / self.initial_capital) * 100

        return {
            "initial_capital": self.initial_capital,
            "current_capital": self.current_capital,
            "total_return": total_return,
            "max_drawdown": self.max_drawdown,
            "total_trades": len(self.trades_history),
        }


# ==============================================================================
# 6) سیستم بک‌تست با ریسک به ریوارد 2
# ==============================================================================

def run_backtest_with_rr(df: pd.DataFrame,
                         interval_minutes: int,
                         initial_capital: float = 10000,
                         risk_per_trade: float = 1.0,
                         risk_reward_ratio: float = 2.0,
                         stop_loss_pct: float = 1.5,
                         take_profit_pct: float = 3.0) -> Dict:
    """
    بک‌تست با ریسک به ریوارد مشخص

    استراتژی:
    - حد ضرر: stop_loss_pct درصد
    - حد سود: take_profit_pct درصد (باید risk_reward_ratio برابر باشد)
    - ریسک هر معامله: risk_per_trade درصد از سرمایه
    """
    n = len(df)
    if n < 50:
        return {"error": "داده کافی نیست"}

    # مدیریت سرمایه
    capital_manager = CapitalManager(initial_capital, risk_per_trade, risk_reward_ratio)

    trades = []
    equity_curve = []
    position = None
    entry_price = 0
    entry_time = None
    stop_loss_price = 0
    take_profit_price = 0

    # پارامترهای استراتژی
    min_force_threshold = 0.3

    for i in range(50, n):
        current_time = pd.Timestamp(df.iloc[i]["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)
        current_price = float(df.iloc[i]["close"])
        current_high = float(df.iloc[i]["high"])
        current_low = float(df.iloc[i]["low"])

        # محاسبه نیروی گرانشی
        planet_times = calculate_all_planet_times(current_time)
        forces = {}
        for p in planet_times:
            planet_data = PLANETS[p["planet_name"]]
            force = calculate_gravitational_force(
                planet_data["mass_kg"],
                planet_data["distance_from_sun_km"],
                current_price
            )
            forces[p["planet_name"]] = force

        max_force = max(forces.values()) if forces else 1
        normalized_forces = {k: v / max_force for k, v in forces.items()}

        # محاسبه نیروی خالص
        net_force = 0
        for p in planet_times:
            planet_name = p["planet_name"]
            local_hour = p["local_hour"]
            force_weight = normalized_forces[planet_name]

            if 0 <= local_hour < 12:
                net_force -= force_weight * (1 - local_hour / 12)
            else:
                net_force += force_weight * ((local_hour - 12) / 12)

        # مدیریت معامله باز
        if position is not None:
            if position == "long":
                # بررسی حد ضرر
                if current_low <= stop_loss_price:
                    # حد ضرر
                    pnl_pct = -stop_loss_pct
                    risk_amount = capital_manager.current_capital * (risk_per_trade / 100)
                    pnl = -risk_amount

                    capital_manager.update_capital(pnl)

                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": current_time,
                        "entry_price": entry_price,
                        "exit_price": stop_loss_price,
                        "stop_loss": stop_loss_price,
                        "take_profit": take_profit_price,
                        "position": "long",
                        "pnl_pct": pnl_pct,
                        "pnl_usd": pnl,
                        "capital": capital_manager.current_capital,
                        "reason": "حد ضرر",
                        "risk_reward": risk_reward_ratio,
                    })
                    position = None

                # بررسی حد سود
                elif current_high >= take_profit_price:
                    # حد سود
                    pnl_pct = take_profit_pct
                    risk_amount = capital_manager.current_capital * (risk_per_trade / 100)
                    pnl = risk_amount * risk_reward_ratio

                    capital_manager.update_capital(pnl)

                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": current_time,
                        "entry_price": entry_price,
                        "exit_price": take_profit_price,
                        "stop_loss": stop_loss_price,
                        "take_profit": take_profit_price,
                        "position": "long",
                        "pnl_pct": pnl_pct,
                        "pnl_usd": pnl,
                        "capital": capital_manager.current_capital,
                        "reason": "حد سود",
                        "risk_reward": risk_reward_ratio,
                    })
                    position = None

            elif position == "short":
                # بررسی حد ضرر
                if current_high >= stop_loss_price:
                    # حد ضرر
                    pnl_pct = -stop_loss_pct
                    risk_amount = capital_manager.current_capital * (risk_per_trade / 100)
                    pnl = -risk_amount

                    capital_manager.update_capital(pnl)

                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": current_time,
                        "entry_price": entry_price,
                        "exit_price": stop_loss_price,
                        "stop_loss": stop_loss_price,
                        "take_profit": take_profit_price,
                        "position": "short",
                        "pnl_pct": pnl_pct,
                        "pnl_usd": pnl,
                        "capital": capital_manager.current_capital,
                        "reason": "حد ضرر",
                        "risk_reward": risk_reward_ratio,
                    })
                    position = None

                # بررسی حد سود
                elif current_low <= take_profit_price:
                    # حد سود
                    pnl_pct = take_profit_pct
                    risk_amount = capital_manager.current_capital * (risk_per_trade / 100)
                    pnl = risk_amount * risk_reward_ratio

                    capital_manager.update_capital(pnl)

                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": current_time,
                        "entry_price": entry_price,
                        "exit_price": take_profit_price,
                        "stop_loss": stop_loss_price,
                        "take_profit": take_profit_price,
                        "position": "short",
                        "pnl_pct": pnl_pct,
                        "pnl_usd": pnl,
                        "capital": capital_manager.current_capital,
                        "reason": "حد سود",
                        "risk_reward": risk_reward_ratio,
                    })
                    position = None

        # سیگنال‌های ورود
        if position is None:
            if net_force > min_force_threshold:
                # سیگنال خرید
                position = "long"
                entry_price = current_price
                entry_time = current_time

                # محاسبه حد ضرر و حد سود با ریسک به ریوارد
                stop_loss_price = entry_price * (1 - stop_loss_pct / 100)
                take_profit_price = entry_price * (1 + take_profit_pct / 100)

            elif net_force < -min_force_threshold:
                # سیگنال فروش
                position = "short"
                entry_price = current_price
                entry_time = current_time

                # محاسبه حد ضرر و حد سود با ریسک به ریوارد
                stop_loss_price = entry_price * (1 + stop_loss_pct / 100)
                take_profit_price = entry_price * (1 - take_profit_pct / 100)

        equity_curve.append({
            "timestamp": current_time,
            "equity": capital_manager.current_capital,
            "price": current_price,
        })

    # بستن معامله باز در انتها
    if position is not None:
        current_price = float(df.iloc[-1]["close"])
        current_time = pd.Timestamp(df.iloc[-1]["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)

        if position == "long":
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100

        risk_amount = capital_manager.current_capital * (risk_per_trade / 100)
        if pnl_pct > 0:
            pnl = risk_amount * (pnl_pct / stop_loss_pct)
        else:
            pnl = -risk_amount * (abs(pnl_pct) / stop_loss_pct)

        capital_manager.update_capital(pnl)

        trades.append({
            "entry_time": entry_time,
            "exit_time": current_time,
            "entry_price": entry_price,
            "exit_price": current_price,
            "stop_loss": stop_loss_price,
            "take_profit": take_profit_price,
            "position": position,
            "pnl_pct": pnl_pct,
            "pnl_usd": pnl,
            "capital": capital_manager.current_capital,
            "reason": "پایان بک‌تست",
            "risk_reward": risk_reward_ratio,
        })

    # محاسبه آمار
    stats = calculate_backtest_stats_rr(trades, equity_curve, initial_capital,
                                        risk_reward_ratio, risk_per_trade)

    return {
        "trades": trades,
        "equity_curve": equity_curve,
        "stats": stats,
        "capital_manager": capital_manager,
        "final_capital": capital_manager.current_capital,
    }


def calculate_backtest_stats_rr(trades: List[Dict], equity_curve: List[Dict],
                                initial_capital: float, risk_reward_ratio: float,
                                risk_per_trade: float) -> Dict:
    """محاسبه آمار کامل بک‌تست با ریسک به ریوارد"""
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0,
            "profit_factor": 0,
            "max_drawdown": 0,
            "sharpe_ratio": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "total_pnl": 0,
            "total_pnl_pct": 0,
            "expectancy": 0,
            "kelly_criterion": 0,
            "risk_reward_ratio": risk_reward_ratio,
            "risk_per_trade": risk_per_trade,
        }

    winning_trades = [t for t in trades if t["pnl_usd"] > 0]
    losing_trades = [t for t in trades if t["pnl_usd"] <= 0]

    total_trades = len(trades)
    win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0

    gross_profit = sum(t["pnl_usd"] for t in winning_trades)
    gross_loss = abs(sum(t["pnl_usd"] for t in losing_trades))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0

    avg_win = np.mean([t["pnl_pct"] for t in winning_trades]) if winning_trades else 0
    avg_loss = np.mean([t["pnl_pct"] for t in losing_trades]) if losing_trades else 0

    # محاسبه Drawdown
    equity_values = [e["equity"] for e in equity_curve]
    if equity_values:
        peak = equity_values[0]
        max_drawdown = 0
        for value in equity_values:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
    else:
        max_drawdown = 0

    # محاسبه Sharpe Ratio
    returns = []
    for i in range(1, len(equity_values)):
        ret = (equity_values[i] - equity_values[i - 1]) / equity_values[i - 1]
        returns.append(ret)

    if returns and np.std(returns) > 0:
        sharpe_ratio = (np.mean(returns) / np.std(returns)) * np.sqrt(252 * 24)
    else:
        sharpe_ratio = 0

    total_pnl = sum(t["pnl_usd"] for t in trades)
    total_pnl_pct = (total_pnl / initial_capital) * 100

    # محاسبه Expectancy
    # Expectancy = (Win Rate × Average Win) - (Loss Rate × Average Loss)
    win_rate_decimal = win_rate / 100
    loss_rate_decimal = 1 - win_rate_decimal

    if winning_trades and losing_trades:
        avg_win_usd = np.mean([t["pnl_usd"] for t in winning_trades])
        avg_loss_usd = abs(np.mean([t["pnl_usd"] for t in losing_trades]))
        expectancy = (win_rate_decimal * avg_win_usd) - (loss_rate_decimal * avg_loss_usd)
    else:
        expectancy = 0

    # محاسبه Kelly Criterion
    # Kelly = (Win Rate × Risk Reward - Loss Rate) / Risk Reward
    if risk_reward_ratio > 0:
        kelly = (win_rate_decimal * risk_reward_ratio - loss_rate_decimal) / risk_reward_ratio
        kelly = max(0, min(kelly, 1))  # محدود کردن بین 0 و 1
    else:
        kelly = 0

    return {
        "total_trades": total_trades,
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe_ratio,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "expectancy": expectancy,
        "kelly_criterion": kelly,
        "risk_reward_ratio": risk_reward_ratio,
        "risk_per_trade": risk_per_trade,
    }


def build_equity_curve_chart(equity_curve: List[Dict], trades: List[Dict]) -> go.Figure:
    """ساخت نمودار Equity Curve و Drawdown"""
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        row_heights=[0.7, 0.3],
        subplot_titles=("Equity Curve", "Drawdown (%)"),
    )

    if equity_curve:
        timestamps = [e["timestamp"] for e in equity_curve]
        equity_values = [e["equity"] for e in equity_curve]

        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=equity_values,
                mode="lines",
                name="Equity",
                line=dict(color=UP, width=2),
                fill="tozeroy",
                fillcolor="rgba(31,215,166,0.1)",
            ),
            row=1, col=1,
        )

        peak = equity_values[0]
        drawdowns = []
        for value in equity_values:
            if value > peak:
                peak = value
            dd = (peak - value) / peak * 100
            drawdowns.append(-dd)

        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=drawdowns,
                mode="lines",
                name="Drawdown",
                line=dict(color=DN, width=1),
                fill="tozeroy",
                fillcolor="rgba(255,93,108,0.2)",
            ),
            row=2, col=1,
        )

    if trades:
        buy_times = [t["entry_time"] for t in trades if t["position"] == "long"]
        buy_prices = [t["entry_price"] for t in trades if t["position"] == "long"]
        sell_times = [t["entry_time"] for t in trades if t["position"] == "short"]
        sell_prices = [t["entry_price"] for t in trades if t["position"] == "short"]

        if buy_times:
            fig.add_trace(
                go.Scatter(
                    x=buy_times,
                    y=buy_prices,
                    mode="markers",
                    name="خرید",
                    marker=dict(size=8, color=UP, symbol="triangle-up"),
                ),
                row=1, col=1,
            )

        if sell_times:
            fig.add_trace(
                go.Scatter(
                    x=sell_times,
                    y=sell_prices,
                    mode="markers",
                    name="فروش",
                    marker=dict(size=8, color=DN, symbol="triangle-down"),
                ),
                row=1, col=1,
            )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        title=dict(
            text="📊 نمودار Equity Curve و Drawdown",
            x=0.5,
            font=dict(color=GOLD, size=16, family=FONT_FAMILY),
        ),
        legend=dict(
            bgcolor="rgba(15,24,48,0.85)",
            bordercolor=LINE,
            borderwidth=1,
            font=dict(size=10, color=TXT, family=FONT_FAMILY),
            orientation="h",
            y=-0.15,
            x=0.5,
            xanchor="center",
        ),
        margin=dict(l=20, r=20, t=80, b=20),
        font=dict(family=FONT_FAMILY),
        height=500,
    )

    fig.update_xaxes(gridcolor=LINE, zerolinecolor=LINE)
    fig.update_yaxes(gridcolor=LINE, zerolinecolor=LINE)

    return fig


def build_price_path_chart(df: pd.DataFrame,
                           predicted_df: pd.DataFrame,
                           sr_data: Dict,
                           symbol: str) -> go.Figure:
    """ساخت نمودار قیمت-زمان"""
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df["ts"],
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="قیمت تاریخی",
        increasing_line_color=UP,
        decreasing_line_color=DN,
        increasing_fillcolor=UP,
        decreasing_fillcolor=DN,
        opacity=0.8,
    ))

    if not predicted_df.empty:
        fig.add_trace(go.Scatter(
            x=predicted_df["timestamp"],
            y=predicted_df["price"],
            mode="lines+markers",
            name="مسیر پیش‌بینی‌شده (جاذبه)",
            line=dict(color=GOLD, width=3, dash="dash"),
            marker=dict(size=4, color=GOLD),
            opacity=0.9,
        ))

    for level in sr_data["support_levels"][:3]:
        fig.add_hline(
            y=level["price"],
            line_dash="dot",
            line_color=UP,
            line_width=1,
            opacity=0.5,
        )

    for level in sr_data["resistance_levels"][:3]:
        fig.add_hline(
            y=level["price"],
            line_dash="dot",
            line_color=DN,
            line_width=1,
            opacity=0.5,
        )

    last_time = pd.Timestamp(df.iloc[-1]["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)

    fig.add_shape(
        type="line",
        x0=last_time,
        x1=last_time,
        y0=0,
        y1=1,
        yref="paper",
        line=dict(color=GOLD, width=2, dash="solid"),
        opacity=0.7,
    )

    fig.add_annotation(
        x=last_time,
        y=1.02,
        yref="paper",
        text="زمان فعلی",
        showarrow=False,
        font=dict(size=11, color=GOLD),
        xanchor="center",
    )

    if not predicted_df.empty:
        fig.add_shape(
            type="rect",
            x0=last_time,
            x1=predicted_df.iloc[-1]["timestamp"],
            y0=0,
            y1=1,
            yref="paper",
            fillcolor="rgba(243, 186, 47, 0.05)",
            line_width=0,
            layer="below",
        )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        title=dict(
            text=f"📈 نمودار مسیر قیمت — {symbol}",
            x=0.5,
            font=dict(color=GOLD, size=18, family=FONT_FAMILY),
        ),
        xaxis_title="زمان",
        yaxis_title="قیمت (USDT)",
        xaxis=dict(
            rangeslider=dict(visible=False),
            gridcolor=LINE,
            zerolinecolor=LINE,
        ),
        yaxis=dict(
            gridcolor=LINE,
            zerolinecolor=LINE,
        ),
        legend=dict(
            bgcolor="rgba(15,24,48,0.85)",
            bordercolor=LINE,
            borderwidth=1,
            font=dict(size=11, color=TXT, family=FONT_FAMILY),
            orientation="h",
            y=-0.2,
            x=0.5,
            xanchor="center",
        ),
        margin=dict(l=20, r=20, t=80, b=20),
        font=dict(family=FONT_FAMILY),
        hovermode="x unified",
    )

    return fig


def predict_price_path_gravitational(df: pd.DataFrame,
                                     current_time: datetime,
                                     interval_minutes: int,
                                     forecast_hours: int = 12) -> pd.DataFrame:
    """پیش‌بینی مسیر قیمت بر اساس نیروی جاذبه سیارات"""
    current_price = float(df.iloc[-1]["close"])
    last_timestamp = pd.Timestamp(df.iloc[-1]["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)

    forecast_candles = int(forecast_hours * 60 / interval_minutes)

    predictions = []

    for i in range(forecast_candles):
        future_time = last_timestamp + timedelta(minutes=interval_minutes * (i + 1))

        planet_times = calculate_all_planet_times(future_time)

        forces = {}
        for p in planet_times:
            planet_data = PLANETS[p["planet_name"]]
            force = calculate_gravitational_force(
                planet_data["mass_kg"],
                planet_data["distance_from_sun_km"],
                current_price
            )
            forces[p["planet_name"]] = force

        max_force = max(forces.values()) if forces else 1
        normalized_forces = {k: v / max_force for k, v in forces.items()}

        net_force = 0
        for p in planet_times:
            planet_name = p["planet_name"]
            local_hour = p["local_hour"]
            force_weight = normalized_forces[planet_name]

            if 0 <= local_hour < 12:
                net_force -= force_weight * (1 - local_hour / 12)
            else:
                net_force += force_weight * ((local_hour - 12) / 12)

        price_change_pct = net_force * 0.5
        current_price = current_price * (1 + price_change_pct / 100)

        predictions.append({
            "timestamp": future_time,
            "price": current_price,
            "net_force": net_force,
            "price_change_pct": price_change_pct,
        })

    return pd.DataFrame(predictions)


def build_win_rate_gauge(win_rate: float, title: str) -> go.Figure:
    """ساخت گیج Win Rate"""
    fig = go.Figure()
    color = UP if win_rate >= 60 else (GOLD if win_rate >= 45 else DN)

    fig.add_trace(go.Indicator(
        mode="gauge+number+delta",
        value=win_rate,
        number={"suffix": "%", "font": {"color": color, "size": 32, "family": FONT_FAMILY}},
        title={"text": title, "font": {"color": MUT, "size": 14, "family": FONT_FAMILY}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": MUT, "tickfont": {"color": MUT, "size": 10}},
            "bar": {"color": color},
            "bgcolor": CARD2,
            "borderwidth": 0,
            "steps": [
                {"range": [0, 40], "color": "rgba(255,93,108,0.18)"},
                {"range": [40, 60], "color": "rgba(243,186,47,0.18)"},
                {"range": [60, 100], "color": "rgba(31,215,166,0.18)"},
            ],
            "threshold": {
                "line": {"color": "white", "width": 4},
                "thickness": 0.75,
                "value": 50
            }
        }
    ))

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_FAMILY, color=TXT),
        margin=dict(l=20, r=20, t=50, b=10),
        height=250,
    )

    return fig


# ==============================================================================
# 7) اپلیکیشن Dash
# ==============================================================================

FONT_URL = "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;800&display=swap"

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG, FONT_URL])
app.title = "Chrono-Gravitas - بک‌تست با مدیریت سرمایه"
server = app.server

app.index_string = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            body { background: #070b14; }
            * { font-family: 'Vazirmatn', Tahoma, Arial, sans-serif !important; }
            .glass-card {
                background: linear-gradient(145deg, rgba(16,28,56,0.85), rgba(10,17,35,0.85));
                border: 1px solid #22304e;
                border-radius: 16px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.35);
                backdrop-filter: blur(6px);
            }
            .stat-value { font-weight: 800; font-size: 20px; }
            .stat-label { font-size: 11px; color: #8ea0c4; }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""


def stat_card(id_prefix, label, color=TXT):
    return dbc.Col(
        html.Div([
            html.Div(label, className="stat-label"),
            html.Div("—", id=f"{id_prefix}-value", className="stat-value", style={"color": color}),
        ], className="glass-card", style={"padding": "12px 16px", "textAlign": "center"}),
        md=2, xs=6, style={"marginBottom": 10},
    )


app.layout = html.Div([
    html.Div([
        html.H4("🪐 Chrono-Gravitas v5.0", style={"color": GOLD, "fontWeight": 800, "margin": 0}),
        html.Div("سیستم بک‌تست با ریسک به ریوارد 2 و مدیریت سرمایه — Morindok",
                 style={"color": MUT, "fontSize": 12}),
    ], style={"maxWidth": 1600, "margin": "10px auto 4px auto", "padding": "0 6px"}),

    # کنترل‌ها
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([
            html.Label("نماد", style={"fontSize": 11, "color": MUT}),
            dcc.Input(id="symbol", value=DEFAULT_SYMBOL, type="text",
                      style={"width": "100%", "padding": 6, "borderRadius": 8,
                             "background": CARD2, "color": TXT, "border": f"1px solid {LINE}"}),
        ], md=2),
        dbc.Col([
            html.Label("بازار", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="category", value=DEFAULT_CATEGORY, clearable=False,
                         options=[{"label": v, "value": v} for v in ["linear", "spot", "inverse"]]),
        ], md=2),
        dbc.Col([
            html.Label("تایم‌فریم", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="interval", value=DEFAULT_INTERVAL, clearable=False,
                         options=[{"label": lbl, "value": val} for lbl, val in [
                             ("1m", "1"), ("5m", "5"), ("15m", "15"), ("30m", "30"),
                             ("1h", "60"), ("4h", "240"),
                         ]]),
        ], md=2),
        dbc.Col([
            html.Label("مدت بک‌تست (ماه)", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="backtest-months", value=3, clearable=False,
                         options=[{"label": f"{m} ماه", "value": m} for m in [1, 3, 6, 12]]),
        ], md=2),
        dbc.Col(
            dbc.Button("🚀 اجرای بک‌تست", id="backtest-btn", color="warning", className="mt-3",
                       style={"fontWeight": "bold", "color": BG, "width": "100%", "padding": "8px 6px"}),
            md=2,
        ),
    ])), className="glass-card", style={"maxWidth": 1600, "margin": "10px auto"}),

    # آمار بک‌تست
    html.Div(dbc.Row([
        stat_card("total-trades", "تعداد معاملات", GOLD),
        stat_card("win-rate", "Win Rate (RR=2)", UP),
        stat_card("profit-factor", "Profit Factor", BLUE),
        stat_card("max-drawdown", "Max Drawdown", DN),
        stat_card("sharpe-ratio", "Sharpe Ratio", GOLD),
        stat_card("total-pnl", "سود/ضرر کل (%)", UP),
    ]), style={"maxWidth": 1600, "margin": "0 auto"}),

    # آمار مدیریت سرمایه
    html.Div(dbc.Row([
        stat_card("initial-capital", "سرمایه اولیه", MUT),
        stat_card("final-capital", "سرمایه نهایی", UP),
        stat_card("risk-per-trade", "ریسک هر معامله", GOLD),
        stat_card("risk-reward", "ریسک به ریوارد", BLUE),
        stat_card("expectancy", "Expectancy", UP),
        stat_card("kelly", "Kelly Criterion", DN),
    ]), style={"maxWidth": 1600, "margin": "0 auto"}),

    # نمودار Equity Curve
    dbc.Card(dbc.CardBody([
        dcc.Graph(id="equity-chart", style={"height": "50vh"},
                  config={"displaylogo": False, "responsive": True}),
    ]), className="glass-card", style={"maxWidth": 1600, "margin": "10px auto"}),

    # جدول معاملات
    dbc.Card(dbc.CardBody([
        html.H5("📋 لیست معاملات", style={"color": GOLD, "fontWeight": 800, "marginBottom": 12}),
        dash_table.DataTable(
            id="trades-table",
            style_table={"overflowX": "auto"},
            style_header={"backgroundColor": CARD2, "color": MUT, "fontWeight": 700,
                          "fontSize": 10, "border": f"1px solid {LINE}", "textAlign": "center"},
            style_cell={"backgroundColor": "rgba(0,0,0,0)", "color": TXT, "fontSize": 10,
                        "border": f"1px solid {LINE}", "textAlign": "center", "padding": "6px",
                        "fontFamily": FONT_FAMILY},
        ),
    ]), className="glass-card", style={"maxWidth": 1600, "margin": "10px auto"}),

    # نمودار مسیر قیمت
    dbc.Card(dbc.CardBody([
        dcc.Graph(id="price-path-chart", style={"height": "60vh"},
                  config={"displaylogo": False, "responsive": True}),
    ]), className="glass-card", style={"maxWidth": 1600, "margin": "10px auto"}),

    dcc.Interval(id="tick", interval=60_000, n_intervals=0),
    dcc.Store(id="backtest-data"),
], style={"background": BG, "minHeight": "100vh", "padding": "10px", "fontFamily": FONT_FAMILY})


@callback(
    Output("equity-chart", "figure"),
    Output("trades-table", "data"),
    Output("trades-table", "columns"),
    Output("price-path-chart", "figure"),
    Output("total-trades-value", "children"),
    Output("win-rate-value", "children"),
    Output("profit-factor-value", "children"),
    Output("max-drawdown-value", "children"),
    Output("sharpe-ratio-value", "children"),
    Output("total-pnl-value", "children"),
    Output("initial-capital-value", "children"),
    Output("final-capital-value", "children"),
    Output("risk-per-trade-value", "children"),
    Output("risk-reward-value", "children"),
    Output("expectancy-value", "children"),
    Output("kelly-value", "children"),
    Input("backtest-btn", "n_clicks"),
    Input("tick", "n_intervals"),
    State("symbol", "value"),
    State("category", "value"),
    State("interval", "value"),
    State("backtest-months", "value"),
)
def run_backtest(_click, _tick, symbol, category, interval, backtest_months):
    symbol = (symbol or DEFAULT_SYMBOL).upper().strip()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL
    backtest_months = backtest_months or 3

    interval_minutes = get_interval_minutes(interval)

    # دریافت داده‌های تاریخی
    df = get_klines_with_pagination(symbol, interval, category, months=backtest_months)

    if df.empty or len(df) < 50:
        empty_fig = go.Figure()
        empty_fig.update_layout(
            template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
            xaxis=dict(visible=False), yaxis=dict(visible=False),
        )
        empty_fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text="خطا در دریافت داده یا داده کافی نیست", showarrow=False,
            font=dict(size=16, color=DN, family=FONT_FAMILY),
        )
        empty_data = [{"msg": "خطا"}]
        empty_cols = [{"name": "پیام", "id": "msg"}]
        return (empty_fig, empty_data, empty_cols, empty_fig,
                "—", "—", "—", "—", "—", "—",
                "—", "—", "—", "—", "—", "—")

    # اجرای بک‌تست با ریسک به ریوارد 2
    backtest_result = run_backtest_with_rr(
        df, interval_minutes,
        initial_capital=INITIAL_CAPITAL,
        risk_per_trade=RISK_PER_TRADE,
        risk_reward_ratio=RISK_REWARD_RATIO,
        stop_loss_pct=STOP_LOSS_PCT,
        take_profit_pct=TAKE_PROFIT_PCT,
    )

    if "error" in backtest_result:
        empty_fig = go.Figure()
        empty_data = [{"msg": backtest_result["error"]}]
        empty_cols = [{"name": "پیام", "id": "msg"}]
        return (empty_fig, empty_data, empty_cols, empty_fig,
                "—", "—", "—", "—", "—", "—",
                "—", "—", "—", "—", "—", "—")

    trades = backtest_result["trades"]
    equity_curve = backtest_result["equity_curve"]
    stats = backtest_result["stats"]
    capital_manager = backtest_result["capital_manager"]

    # نمودار Equity Curve
    equity_fig = build_equity_curve_chart(equity_curve, trades)

    # جدول معاملات
    trades_data = []
    for t in trades[-50:]:
        trades_data.append({
            "زمان ورود": t["entry_time"].strftime("%Y-%m-%d %H:%M"),
            "زمان خروج": t["exit_time"].strftime("%Y-%m-%d %H:%M"),
            "قیمت ورود": f"{t['entry_price']:,.2f}",
            "حد ضرر": f"{t['stop_loss']:,.2f}",
            "حد سود": f"{t['take_profit']:,.2f}",
            "قیمت خروج": f"{t['exit_price']:,.2f}",
            "نوع": "خرید" if t["position"] == "long" else "فروش",
            "سود/ضرر (%)": f"{t['pnl_pct']:.2f}%",
            "سود/ضرر ($)": f"{t['pnl_usd']:.2f}",
            "دلیل خروج": t["reason"],
        })

    trades_cols = [
        {"name": "زمان ورود", "id": "زمان ورود"},
        {"name": "زمان خروج", "id": "زمان خروج"},
        {"name": "قیمت ورود", "id": "قیمت ورود"},
        {"name": "حد ضرر", "id": "حد ضرر"},
        {"name": "حد سود", "id": "حد سود"},
        {"name": "قیمت خروج", "id": "قیمت خروج"},
        {"name": "نوع", "id": "نوع"},
        {"name": "سود/ضرر (%)", "id": "سود/ضرر (%)"},
        {"name": "سود/ضرر ($)", "id": "سود/ضرر ($)"},
        {"name": "دلیل خروج", "id": "دلیل خروج"},
    ]

    # نمودار مسیر قیمت
    now_utc = get_server_time()
    sr_data = calculate_gravitational_support_resistance(df, now_utc)
    predicted_df = predict_price_path_gravitational(df, now_utc, interval_minutes, 12)
    price_path_fig = build_price_path_chart(df.tail(200), predicted_df, sr_data, symbol)

    return (
        equity_fig,
        trades_data, trades_cols,
        price_path_fig,
        f"{stats['total_trades']}",
        f"{stats['win_rate']:.1f}%",
        f"{stats['profit_factor']:.2f}",
        f"{stats['max_drawdown']:.2f}%",
        f"{stats['sharpe_ratio']:.2f}",
        f"{stats['total_pnl_pct']:.2f}%",
        f"${INITIAL_CAPITAL:,.0f}",
        f"${backtest_result['final_capital']:,.2f}",
        f"{RISK_PER_TRADE}%",
        f"1:{RISK_REWARD_RATIO:.0f}",
        f"${stats['expectancy']:.2f}",
        f"{stats['kelly_criterion'] * 100:.1f}%",
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8060, use_reloader=False)