# -*- coding: utf-8 -*-
"""
🪐 Chrono-Gravitas v3.0 — سیستم زمان‌سنج سیاره‌ای با نمودار مسیر قیمت
=============================================================================
{Morindok}

این سیستم:
  ۱. زمان را در تمام سیارات منظومه شمسی محاسبه می‌کند
  ۲. ساعت جهانی هر سیاره را بر اساس دوره چرخش و مدار می‌سازد
  ۳. زمان‌های نسبی سیاره‌ای را به زمان مطلق تبدیل می‌کند
  ۴. حمایت و مقاومت را بر اساس نیروی جاذبه سیارات محاسبه می‌کند
  ۵. قدرت جذب هر سطح را سنجیده و قدرتمندترین را نمایش می‌دهد
  ۶. Win Rate سیستم را با بک‌تست محاسبه می‌کند
  ۷. مسیر قیمت را بر اساس جاذبه‌ها در نمودار زمان-قیمت رسم می‌کند
  ۸. تاریخچه مسیر پیش‌بینی‌شده را نمایش می‌دهد
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
DEFAULT_INTERVAL = "15"
BACKTEST_CANDLES = 100
WIN_THRESHOLD_PCT = 0.5
FORECAST_HOURS = 12  # پیش‌بینی برای 12 ساعت آینده

FONT_FAMILY = "Vazirmatn, Tahoma, Arial, sans-serif"

# ==============================================================================
# 2) REST API پایدار بایبیت
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


def get_klines(symbol, interval, category="linear", limit=500):
    d = bybit_get("/v5/market/kline", {
        "category": category,
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    })
    if not d or "list" not in (d.get("result") or {}):
        return pd.DataFrame()

    lst = d["result"]["list"]
    if not lst:
        return pd.DataFrame()

    df = pd.DataFrame(
        lst,
        columns=["ts", "open", "high", "low", "close", "volume", "turnover"],
    )
    df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)


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

    max_force = max(forces.values())
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


def calculate_total_gravitational_pull(sr_data: Dict) -> Tuple[float, float]:
    total_support_pull = sum(level["strength"] for level in sr_data["support_levels"])
    total_resistance_pull = sum(level["strength"] for level in sr_data["resistance_levels"])
    return total_support_pull, total_resistance_pull


# ==============================================================================
# 5) پیش‌بینی مسیر قیمت بر اساس جاذبه‌ها
# ==============================================================================

def predict_price_path_gravitational(df: pd.DataFrame,
                                     current_time: datetime,
                                     interval_minutes: int,
                                     forecast_hours: int = 12) -> pd.DataFrame:
    """
    پیش‌بینی مسیر قیمت بر اساس نیروی جاذبه سیارات

    منطق:
    - برای هر زمان آینده، موقعیت سیارات محاسبه می‌شود
    - نیروی خالص گرانشی از تمام سیارات محاسبه می‌شود
    - قیمت بر اساس این نیرو حرکت می‌کند
    """
    current_price = float(df.iloc[-1]["close"])
    last_timestamp = pd.Timestamp(df.iloc[-1]["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)

    # تعداد کندل‌های پیش‌بینی
    forecast_candles = int(forecast_hours * 60 / interval_minutes)

    predictions = []

    for i in range(forecast_candles):
        future_time = last_timestamp + timedelta(minutes=interval_minutes * (i + 1))

        # محاسبه موقعیت سیارات در این زمان
        planet_times = calculate_all_planet_times(future_time)

        # محاسبه نیروی گرانشی هر سیاره
        forces = {}
        for p in planet_times:
            planet_data = PLANETS[p["planet_name"]]
            force = calculate_gravitational_force(
                planet_data["mass_kg"],
                planet_data["distance_from_sun_km"],
                current_price
            )
            forces[p["planet_name"]] = force

        max_force = max(forces.values())
        normalized_forces = {k: v / max_force for k, v in forces.items()}

        # محاسبه نیروی خالص و جهت حرکت
        net_force = 0

        for p in planet_times:
            planet_name = p["planet_name"]
            local_hour = p["local_hour"]
            force_weight = normalized_forces[planet_name]

            # سیارات در نیمه اول روز → فشار نزولی
            # سیارات در نیمه دوم روز → فشار صعودی
            if 0 <= local_hour < 12:
                # نزولی
                net_force -= force_weight * (1 - local_hour / 12)
            else:
                # صعودی
                net_force += force_weight * ((local_hour - 12) / 12)

        # تبدیل نیرو به تغییر قیمت (درصد)
        # حداکثر تغییر 0.5% در هر کندل
        price_change_pct = net_force * 0.5

        # محاسبه قیمت جدید
        current_price = current_price * (1 + price_change_pct / 100)

        predictions.append({
            "timestamp": future_time,
            "price": current_price,
            "net_force": net_force,
            "price_change_pct": price_change_pct,
        })

    return pd.DataFrame(predictions)


def build_price_path_chart(df: pd.DataFrame,
                           predicted_df: pd.DataFrame,
                           sr_data: Dict,
                           symbol: str) -> go.Figure:
    """
    ساخت نمودار قیمت-زمان با مسیر تاریخی و پیش‌بینی‌شده
    """
    fig = go.Figure()

    # 1. کندل‌استیک‌های تاریخی
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

    # 2. مسیر پیش‌بینی‌شده (خط طلایی)
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

        # 3. نقاط عطف پیش‌بینی (اوج و فرود)
        prices = predicted_df["price"].values
        for i in range(1, len(prices) - 1):
            if prices[i] > prices[i - 1] and prices[i] > prices[i + 1]:
                # اوج محلی
                fig.add_trace(go.Scatter(
                    x=[predicted_df.iloc[i]["timestamp"]],
                    y=[prices[i]],
                    mode="markers+text",
                    marker=dict(size=12, color=DN, symbol="triangle-down"),
                    text=[f"مقاومت: {prices[i]:,.0f}"],
                    textposition="top center",
                    textfont=dict(size=10, color=DN),
                    showlegend=False,
                    hovertemplate=f"مقاومت پیش‌بینی‌شده<br>قیمت: {prices[i]:,.2f}<extra></extra>",
                ))
            elif prices[i] < prices[i - 1] and prices[i] < prices[i + 1]:
                # فرود محلی
                fig.add_trace(go.Scatter(
                    x=[predicted_df.iloc[i]["timestamp"]],
                    y=[prices[i]],
                    mode="markers+text",
                    marker=dict(size=12, color=UP, symbol="triangle-up"),
                    text=[f"حمایت: {prices[i]:,.0f}"],
                    textposition="bottom center",
                    textfont=dict(size=10, color=UP),
                    showlegend=False,
                    hovertemplate=f"حمایت پیش‌بینی‌شده<br>قیمت: {prices[i]:,.2f}<extra></extra>",
                ))

    # 4. خطوط حمایت و مقاومت فعلی
    for level in sr_data["support_levels"][:3]:
        fig.add_hline(
            y=level["price"],
            line_dash="dot",
            line_color=UP,
            line_width=1,
            opacity=0.5,
        )
        fig.add_annotation(
            x=0,
            y=level["price"],
            xref="paper",
            yref="y",
            text=f"حمایت {level['planet_fa']}",
            showarrow=False,
            font=dict(size=9, color=UP),
            xanchor="left",
            yshift=-10,
        )

    for level in sr_data["resistance_levels"][:3]:
        fig.add_hline(
            y=level["price"],
            line_dash="dot",
            line_color=DN,
            line_width=1,
            opacity=0.5,
        )
        fig.add_annotation(
            x=0,
            y=level["price"],
            xref="paper",
            yref="y",
            text=f"مقاومت {level['planet_fa']}",
            showarrow=False,
            font=dict(size=9, color=DN),
            xanchor="left",
            yshift=10,
        )

    # 5. خط جداکننده گذشته و آینده (با add_shape به جای add_vline)
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

    # 6. ناحیه پیش‌بینی (shading)
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
            text=f"📈 نمودار مسیر قیمت — {symbol} | پیش‌بینی بر اساس جاذبه سیارات",
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

# ==============================================================================
# 6) سیستم بک‌تست و محاسبه Win Rate
# ==============================================================================

def backtest_system(df: pd.DataFrame, interval_minutes: int) -> Dict:
    n = len(df)
    if n < BACKTEST_CANDLES + 10:
        return {"win_rate": 0, "total_predictions": 0, "successful": 0, "details": []}

    start_idx = n - BACKTEST_CANDLES
    predictions = []

    for i in range(start_idx, n - 5):
        current_time = pd.Timestamp(df.iloc[i]["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)
        current_price = float(df.iloc[i]["close"])

        sr_data = calculate_gravitational_support_resistance(df, current_time, price_index=i)
        future_candles = df.iloc[i + 1:i + 6]

        for level in sr_data["support_levels"][:3]:
            predicted_price = level["price"]
            reached = False
            for _, future_row in future_candles.iterrows():
                future_low = float(future_row["low"])
                if future_low <= predicted_price * (1 + WIN_THRESHOLD_PCT / 100):
                    reached = True
                    break

            predictions.append({
                "type": "support",
                "planet": level["planet_fa"],
                "predicted_price": predicted_price,
                "actual_price": current_price,
                "reached": reached,
                "timestamp": current_time,
                "strength": level["strength"],
            })

        for level in sr_data["resistance_levels"][:3]:
            predicted_price = level["price"]
            reached = False
            for _, future_row in future_candles.iterrows():
                future_high = float(future_row["high"])
                if future_high >= predicted_price * (1 - WIN_THRESHOLD_PCT / 100):
                    reached = True
                    break

            predictions.append({
                "type": "resistance",
                "planet": level["planet_fa"],
                "predicted_price": predicted_price,
                "actual_price": current_price,
                "reached": reached,
                "timestamp": current_time,
                "strength": level["strength"],
            })

    total_predictions = len(predictions)
    successful = sum(1 for p in predictions if p["reached"])
    win_rate = (successful / total_predictions * 100) if total_predictions > 0 else 0

    support_predictions = [p for p in predictions if p["type"] == "support"]
    resistance_predictions = [p for p in predictions if p["type"] == "resistance"]

    support_win_rate = (sum(1 for p in support_predictions if p["reached"]) / len(support_predictions) * 100) if len(
        support_predictions) > 0 else 0
    resistance_win_rate = (
                sum(1 for p in resistance_predictions if p["reached"]) / len(resistance_predictions) * 100) if len(
        resistance_predictions) > 0 else 0

    return {
        "win_rate": win_rate,
        "support_win_rate": support_win_rate,
        "resistance_win_rate": resistance_win_rate,
        "total_predictions": total_predictions,
        "successful": successful,
        "support_count": len(support_predictions),
        "resistance_count": len(resistance_predictions),
        "details": predictions[-10:],
    }


# ==============================================================================
# 7) ساخت Figure ساعت سیاره‌ای
# ==============================================================================

def build_planet_clock_figure(sr_data: Dict, earth_utc: datetime, symbol: str):
    fig = go.Figure()
    R = 1.0
    live_price = sr_data["live_price"]

    for i, (rad, op) in enumerate([(1.0, 0.05), (0.75, 0.05), (0.5, 0.06), (0.25, 0.07)]):
        ang_full = np.linspace(0, 360, 121)
        fig.add_trace(go.Scatter(
            x=rad * R * np.cos(np.radians(ang_full)),
            y=rad * R * np.sin(np.radians(ang_full)),
            mode="lines", fill="toself", fillcolor=f"rgba(79,141,253,{op})",
            line=dict(color="rgba(0,0,0,0)"), hoverinfo="skip", showlegend=False,
        ))

    ang_full = np.linspace(0, 360, 361)
    fig.add_trace(go.Scatter(
        x=R * np.cos(np.radians(ang_full)),
        y=R * np.sin(np.radians(ang_full)),
        mode="lines", line=dict(color=LINE, width=2),
        showlegend=False, hoverinfo="skip",
    ))

    for p in sr_data["planet_times"]:
        local_hour = p["local_hour"]
        angle = (local_hour / 24) * 360
        x = 0.85 * R * np.cos(np.radians(angle))
        y = 0.85 * R * np.sin(np.radians(angle))
        size = 10 + p["rotation_fraction"] * 10

        fig.add_trace(go.Scatter(
            x=[x], y=[y],
            mode="markers+text",
            marker=dict(size=size, color=p["color"], symbol="circle",
                        line=dict(width=2, color="white")),
            text=[p["planet_name_fa"]],
            textposition="top center",
            textfont=dict(size=9, color=TXT),
            showlegend=True,
            name=f"{p['planet_name_fa']} ({p['planet_name']})",
            hovertemplate=f"{p['planet_name_fa']}<br>ساعت محلی: {local_hour:.2f}<br>جرم: {p['mass']:.2e} kg<extra></extra>",
        ))

    for level in sr_data["support_levels"][:3]:
        angle = (level["local_hour"] / 24) * 360
        x = 1.1 * R * np.cos(np.radians(angle))
        y = 1.1 * R * np.sin(np.radians(angle))

        fig.add_trace(go.Scatter(
            x=[x], y=[y],
            mode="markers+text",
            marker=dict(size=8, color=UP, symbol="triangle-up"),
            text=[f"حمایت: {level['price']:,.0f}"],
            textposition="bottom center",
            textfont=dict(size=8, color=UP),
            showlegend=False,
            hovertemplate=f"حمایت {level['planet_fa']}<br>قیمت: {level['price']:,.2f}<br>قدرت: {level['strength'] * 100:.1f}%<extra></extra>",
        ))

    for level in sr_data["resistance_levels"][:3]:
        angle = (level["local_hour"] / 24) * 360
        x = 1.1 * R * np.cos(np.radians(angle))
        y = 1.1 * R * np.sin(np.radians(angle))

        fig.add_trace(go.Scatter(
            x=[x], y=[y],
            mode="markers+text",
            marker=dict(size=8, color=DN, symbol="triangle-down"),
            text=[f"مقاومت: {level['price']:,.0f}"],
            textposition="top center",
            textfont=dict(size=8, color=DN),
            showlegend=False,
            hovertemplate=f"مقاومت {level['planet_fa']}<br>قیمت: {level['price']:,.2f}<br>قدرت: {level['strength'] * 100:.1f}%<extra></extra>",
        ))

    fig.add_annotation(
        x=0, y=0,
        text=f"قیمت لایو<br><b>{live_price:,.2f}</b>",
        showarrow=False,
        font=dict(size=14, color=GOLD, family=FONT_FAMILY),
        bgcolor="rgba(15,24,48,0.9)",
        bordercolor=GOLD,
        borderwidth=2,
        borderpad=10,
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        title=dict(
            text=f"🪐 ساعت سیاره‌ای — {symbol} | {earth_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC",
            x=0.5,
            font=dict(color=GOLD, size=18, family=FONT_FAMILY),
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
        margin=dict(l=10, r=10, t=80, b=10),
        font=dict(family=FONT_FAMILY),
        showlegend=True,
    )

    fig.update_xaxes(range=[-1.5, 1.5], visible=False)
    fig.update_yaxes(range=[-1.5, 1.5], visible=False, scaleanchor="x", scaleratio=1)

    return fig


def build_win_rate_gauge(win_rate: float, title: str) -> go.Figure:
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
# 8) اپلیکیشن Dash
# ==============================================================================

FONT_URL = "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;800&display=swap"

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG, FONT_URL])
app.title = "Chrono-Gravitas - مسیر قیمت جاذبه‌ای"
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
        html.H4("🪐 Chrono-Gravitas v3.0", style={"color": GOLD, "fontWeight": 800, "margin": 0}),
        html.Div("سیستم مسیر قیمت جاذبه‌ای — Morindok",
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
            html.Label("افق پیش‌بینی (ساعت)", style={"fontSize": 11, "color": MUT}),
            dcc.Input(id="forecast-hours", type="number", value=FORECAST_HOURS, min=1, max=48, step=1,
                      style={"width": "100%", "padding": 6, "borderRadius": 8,
                             "background": CARD2, "color": TXT, "border": f"1px solid {LINE}"}),
        ], md=2),
        dbc.Col(
            dbc.Button("🔄 به‌روزرسانی", id="refresh-btn", color="warning", className="mt-3",
                       style={"fontWeight": "bold", "color": BG, "width": "100%", "padding": "8px 6px"}),
            md=2,
        ),
    ])), className="glass-card", style={"maxWidth": 1600, "margin": "10px auto"}),

    # نمودار مسیر قیمت (جدید)
    dbc.Card(dbc.CardBody([
        html.H5("📈 نمودار مسیر قیمت — تاریخی و پیش‌بینی‌شده بر اساس جاذبه سیارات",
                style={"color": GOLD, "fontWeight": 800, "marginBottom": 12}),
        dcc.Graph(id="price-path-chart", style={"height": "70vh"},
                  config={"displaylogo": False, "responsive": True}),
    ]), className="glass-card", style={"maxWidth": 1600, "margin": "10px auto"}),

    # آمار کلی و Win Rate
    html.Div(dbc.Row([
        stat_card("live-price", "قیمت لایو", GOLD),
        stat_card("support-pull", "قدرت جذب حمایت", UP),
        stat_card("resistance-pull", "قدرت جذب مقاومت", DN),
        stat_card("universal-time", "زمان مطلق", BLUE),
        stat_card("win-rate", "Win Rate کل", GOLD),
        stat_card("predictions", "تعداد پیش‌بینی", MUT),
    ]), style={"maxWidth": 1600, "margin": "0 auto"}),

    # گیج‌های Win Rate
    dbc.Row([
        dbc.Col(
            dbc.Card(dbc.CardBody([
                dcc.Graph(id="win-rate-total-gauge", config={"displaylogo": False, "responsive": True}),
            ]), className="glass-card"),
            md=4,
        ),
        dbc.Col(
            dbc.Card(dbc.CardBody([
                dcc.Graph(id="win-rate-support-gauge", config={"displaylogo": False, "responsive": True}),
            ]), className="glass-card"),
            md=4,
        ),
        dbc.Col(
            dbc.Card(dbc.CardBody([
                dcc.Graph(id="win-rate-resistance-gauge", config={"displaylogo": False, "responsive": True}),
            ]), className="glass-card"),
            md=4,
        ),
    ], style={"maxWidth": 1600, "margin": "10px auto"}),

    # نمودار ساعت سیاره‌ای
    dbc.Row([
        dbc.Col(
            dbc.Card(dbc.CardBody([
                dcc.Graph(id="planet-clock-graph", style={"height": "60vh"},
                          config={"displaylogo": False, "responsive": True}),
            ]), className="glass-card"),
            md=8,
        ),
        dbc.Col(
            dbc.Card(dbc.CardBody([
                html.H5("⏰ زمان در سیارات", style={"color": GOLD, "fontWeight": 800, "marginBottom": 12}),
                dash_table.DataTable(
                    id="planet-time-table",
                    style_table={"overflowX": "auto"},
                    style_header={"backgroundColor": CARD2, "color": MUT, "fontWeight": 700,
                                  "fontSize": 10, "border": f"1px solid {LINE}", "textAlign": "center"},
                    style_cell={"backgroundColor": "rgba(0,0,0,0)", "color": TXT, "fontSize": 10,
                                "border": f"1px solid {LINE}", "textAlign": "center", "padding": "6px",
                                "fontFamily": FONT_FAMILY},
                ),
            ]), className="glass-card"),
            md=4,
        ),
    ], style={"maxWidth": 1600, "margin": "10px auto"}),

    # جدول حمایت و مقاومت
    dbc.Row([
        dbc.Col(
            dbc.Card(dbc.CardBody([
                html.H5("🟢 سطوح حمایت بر اساس جاذبه", style={"color": UP, "fontWeight": 800, "marginBottom": 12}),
                dash_table.DataTable(
                    id="support-table",
                    style_table={"overflowX": "auto"},
                    style_header={"backgroundColor": CARD2, "color": UP, "fontWeight": 700,
                                  "fontSize": 10, "border": f"1px solid {LINE}", "textAlign": "center"},
                    style_cell={"backgroundColor": "rgba(0,0,0,0)", "color": TXT, "fontSize": 10,
                                "border": f"1px solid {LINE}", "textAlign": "center", "padding": "6px",
                                "fontFamily": FONT_FAMILY},
                ),
            ]), className="glass-card"),
            md=6,
        ),
        dbc.Col(
            dbc.Card(dbc.CardBody([
                html.H5("🔴 سطوح مقاومت بر اساس جاذبه", style={"color": DN, "fontWeight": 800, "marginBottom": 12}),
                dash_table.DataTable(
                    id="resistance-table",
                    style_table={"overflowX": "auto"},
                    style_header={"backgroundColor": CARD2, "color": DN, "fontWeight": 700,
                                  "fontSize": 10, "border": f"1px solid {LINE}", "textAlign": "center"},
                    style_cell={"backgroundColor": "rgba(0,0,0,0)", "color": TXT, "fontSize": 10,
                                "border": f"1px solid {LINE}", "textAlign": "center", "padding": "6px",
                                "fontFamily": FONT_FAMILY},
                ),
            ]), className="glass-card"),
            md=6,
        ),
    ], style={"maxWidth": 1600, "margin": "10px auto"}),

    # جدول آخرین پیش‌بینی‌ها
    dbc.Row([
        dbc.Col(
            dbc.Card(dbc.CardBody([
                html.H5("📊 آخرین پیش‌بینی‌های بک‌تست", style={"color": GOLD, "fontWeight": 800, "marginBottom": 12}),
                dash_table.DataTable(
                    id="backtest-table",
                    style_table={"overflowX": "auto"},
                    style_header={"backgroundColor": CARD2, "color": GOLD, "fontWeight": 700,
                                  "fontSize": 10, "border": f"1px solid {LINE}", "textAlign": "center"},
                    style_cell={"backgroundColor": "rgba(0,0,0,0)", "color": TXT, "fontSize": 10,
                                "border": f"1px solid {LINE}", "textAlign": "center", "padding": "6px",
                                "fontFamily": FONT_FAMILY},
                ),
            ]), className="glass-card"),
            md=12,
        ),
    ], style={"maxWidth": 1600, "margin": "10px auto"}),

    # توضیحات
    html.Div(
        "💡 نمودار مسیر قیمت نشان می‌دهد که چگونه نیروی جاذبه سیارات می‌تواند بر قیمت تأثیر بگذارد. "
        "خط طلایی مسیر پیش‌بینی‌شده برای آینده است. نقاط اوج و فرود در مسیر پیش‌بینی به عنوان سطوح حمایت و مقاومت عمل می‌کنند.",
        style={"fontSize": 11, "color": MUT, "marginTop": 4, "direction": "rtl", "lineHeight": "1.7",
               "textAlign": "center", "maxWidth": 1600, "marginLeft": "auto", "marginRight": "auto",
               "padding": "0 12px 16px 12px"},
    ),

    dcc.Interval(id="tick", interval=30_000, n_intervals=0),
], style={"background": BG, "minHeight": "100vh", "padding": "10px", "fontFamily": FONT_FAMILY})


@callback(
    Output("price-path-chart", "figure"),
    Output("planet-clock-graph", "figure"),
    Output("planet-time-table", "data"),
    Output("planet-time-table", "columns"),
    Output("support-table", "data"),
    Output("support-table", "columns"),
    Output("resistance-table", "data"),
    Output("resistance-table", "columns"),
    Output("backtest-table", "data"),
    Output("backtest-table", "columns"),
    Output("win-rate-total-gauge", "figure"),
    Output("win-rate-support-gauge", "figure"),
    Output("win-rate-resistance-gauge", "figure"),
    Output("live-price-value", "children"),
    Output("support-pull-value", "children"),
    Output("resistance-pull-value", "children"),
    Output("universal-time-value", "children"),
    Output("win-rate-value", "children"),
    Output("predictions-value", "children"),
    Input("tick", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    State("symbol", "value"),
    State("category", "value"),
    State("interval", "value"),
    State("forecast-hours", "value"),
)
def update_all(_n, _click, symbol, category, interval, forecast_hours):
    symbol = (symbol or DEFAULT_SYMBOL).upper().strip()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL

    try:
        forecast_hours = float(forecast_hours or FORECAST_HOURS)
    except:
        forecast_hours = FORECAST_HOURS

    interval_map = {"1": 1, "5": 5, "15": 15, "30": 30, "60": 60, "240": 240}
    interval_minutes = interval_map.get(interval, 15)

    now_utc = get_server_time()
    df = get_klines(symbol, interval, category, limit=500)

    if df.empty:
        empty_fig = go.Figure()
        empty_fig.update_layout(
            template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
            xaxis=dict(visible=False), yaxis=dict(visible=False),
        )
        empty_fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text="خطا در دریافت داده", showarrow=False,
            font=dict(size=16, color=DN, family=FONT_FAMILY),
        )
        empty_gauge = go.Figure()
        empty_data = [{"msg": "خطا"}]
        empty_cols = [{"name": "پیام", "id": "msg"}]
        return (empty_fig, empty_fig, empty_data, empty_cols, empty_data, empty_cols,
                empty_data, empty_cols, empty_data, empty_cols,
                empty_gauge, empty_gauge, empty_gauge,
                "—", "—", "—", "—", "—", "—")

    # محاسبات گرانشی
    sr_data = calculate_gravitational_support_resistance(df, now_utc)

    # محاسبه قدرت جذب
    total_support_pull, total_resistance_pull = calculate_total_gravitational_pull(sr_data)

    # زمان مطلق
    universal_time = calculate_universal_time(sr_data["planet_times"])

    # بک‌تست و محاسبه Win Rate
    backtest_results = backtest_system(df, interval_minutes)

    # پیش‌بینی مسیر قیمت
    predicted_df = predict_price_path_gravitational(df, now_utc, interval_minutes, forecast_hours)

    # نمودار مسیر قیمت
    price_path_fig = build_price_path_chart(df, predicted_df, sr_data, symbol)

    # نمودار ساعت سیاره‌ای
    planet_fig = build_planet_clock_figure(sr_data, now_utc, symbol)

    # گیج‌های Win Rate
    win_rate_total_gauge = build_win_rate_gauge(backtest_results["win_rate"], "Win Rate کل")
    win_rate_support_gauge = build_win_rate_gauge(backtest_results["support_win_rate"], "Win Rate حمایت")
    win_rate_resistance_gauge = build_win_rate_gauge(backtest_results["resistance_win_rate"], "Win Rate مقاومت")

    # جدول زمان سیارات
    planet_data = []
    for p in sr_data["planet_times"]:
        planet_data.append({
            "سیاره": p["planet_name_fa"],
            "نام انگلیسی": p["planet_name"],
            "ساعت محلی": f"{p['local_hour']:.2f}",
            "جرم (kg)": f"{p['mass']:.2e}",
            "جاذبه (m/s²)": f"{p['gravity']:.2f}",
            "نیرو": f"{sr_data['forces'][p['planet_name']] * 100:.1f}%",
        })

    planet_cols = [
        {"name": "سیاره", "id": "سیاره"},
        {"name": "نام انگلیسی", "id": "نام انگلیسی"},
        {"name": "ساعت محلی", "id": "ساعت محلی"},
        {"name": "جرم (kg)", "id": "جرم (kg)"},
        {"name": "جاذبه (m/s²)", "id": "جاذبه (m/s²)"},
        {"name": "نیرو", "id": "نیرو"},
    ]

    # جدول حمایت
    support_data = []
    for level in sr_data["support_levels"]:
        support_data.append({
            "سیاره": level["planet_fa"],
            "قیمت": f"{level['price']:,.2f}",
            "فاصله (%)": f"{((sr_data['live_price'] - level['price']) / sr_data['live_price'] * 100):.2f}%",
            "قدرت جذب": f"{level['strength'] * 100:.1f}%",
            "ساعت محلی": f"{level['local_hour']:.2f}",
        })

    support_cols = [
        {"name": "سیاره", "id": "سیاره"},
        {"name": "قیمت", "id": "قیمت"},
        {"name": "فاصله (%)", "id": "فاصله (%)"},
        {"name": "قدرت جذب", "id": "قدرت جذب"},
        {"name": "ساعت محلی", "id": "ساعت محلی"},
    ]

    # جدول مقاومت
    resistance_data = []
    for level in sr_data["resistance_levels"]:
        resistance_data.append({
            "سیاره": level["planet_fa"],
            "قیمت": f"{level['price']:,.2f}",
            "فاصله (%)": f"{((level['price'] - sr_data['live_price']) / sr_data['live_price'] * 100):.2f}%",
            "قدرت جذب": f"{level['strength'] * 100:.1f}%",
            "ساعت محلی": f"{level['local_hour']:.2f}",
        })

    resistance_cols = [
        {"name": "سیاره", "id": "سیاره"},
        {"name": "قیمت", "id": "قیمت"},
        {"name": "فاصله (%)", "id": "فاصله (%)"},
        {"name": "قدرت جذب", "id": "قدرت جذب"},
        {"name": "ساعت محلی", "id": "ساعت محلی"},
    ]

    # جدول بک‌تست
    backtest_data = []
    for pred in backtest_results["details"]:
        status = "✅ موفق" if pred["reached"] else "❌ ناموفق"
        backtest_data.append({
            "نوع": "حمایت" if pred["type"] == "support" else "مقاومت",
            "سیاره": pred["planet"],
            "قیمت پیش‌بینی": f"{pred['predicted_price']:,.2f}",
            "قیمت واقعی": f"{pred['actual_price']:,.2f}",
            "وضعیت": status,
            "قدرت": f"{pred['strength'] * 100:.1f}%",
            "زمان": pred["timestamp"].strftime("%m-%d %H:%M"),
        })

    backtest_cols = [
        {"name": "نوع", "id": "نوع"},
        {"name": "سیاره", "id": "سیاره"},
        {"name": "قیمت پیش‌بینی", "id": "قیمت پیش‌بینی"},
        {"name": "قیمت واقعی", "id": "قیمت واقعی"},
        {"name": "وضعیت", "id": "وضعیت"},
        {"name": "قدرت", "id": "قدرت"},
        {"name": "زمان", "id": "زمان"},
    ]

    return (
        price_path_fig,
        planet_fig,
        planet_data, planet_cols,
        support_data, support_cols,
        resistance_data, resistance_cols,
        backtest_data, backtest_cols,
        win_rate_total_gauge,
        win_rate_support_gauge,
        win_rate_resistance_gauge,
        f"{sr_data['live_price']:,.2f}",
        f"{total_support_pull * 100:.1f}%",
        f"{total_resistance_pull * 100:.1f}%",
        f"{universal_time:.4f}",
        f"{backtest_results['win_rate']:.1f}%",
        f"{backtest_results['total_predictions']}",
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8060, use_reloader=False)