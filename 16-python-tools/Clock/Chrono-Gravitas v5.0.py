# -*- coding: utf-8 -*-
"""
🪐 Chrono-Gravitas v3.1 — سیستم زمان‌سنج سیاره‌ای با بک‌تست حرفه‌ای (ضد اسکلپ)
=============================================================================
{Morindok}

تغییرات نسخه 3.1:
  - محاسبه ATR برای سنجش نوسان بازار
  - تعیین حد ضرر (SL) معقول بر اساس نوسان (2 * ATR)
  - فیلتر کردن معاملات اسکلپ و بی‌ارزش (حداقل فاصله 0.5%)
  - بررسی R:R واقعی قبل از ورود به معامله
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
    "Mercury": {"name_fa": "عطارد", "color": "#A0522D", "rotation_period_hours": 1407.6, "orbital_period_days": 87.97, "mass_kg": 3.3011e23, "radius_km": 2439.7, "gravity_m_s2": 3.7, "distance_from_sun_km": 57.9e6},
    "Venus": {"name_fa": "زهره", "color": "#FFD700", "rotation_period_hours": 5832.5, "orbital_period_days": 224.7, "mass_kg": 4.8675e24, "radius_km": 6051.8, "gravity_m_s2": 8.87, "distance_from_sun_km": 108.2e6},
    "Earth": {"name_fa": "زمین", "color": "#1E90FF", "rotation_period_hours": 23.934, "orbital_period_days": 365.25, "mass_kg": 5.972e24, "radius_km": 6371.0, "gravity_m_s2": 9.81, "distance_from_sun_km": 149.6e6},
    "Mars": {"name_fa": "مریخ", "color": "#DC143C", "rotation_period_hours": 24.623, "orbital_period_days": 687.0, "mass_kg": 6.4171e23, "radius_km": 3389.5, "gravity_m_s2": 3.72, "distance_from_sun_km": 227.9e6},
    "Jupiter": {"name_fa": "مشتری", "color": "#FFA500", "rotation_period_hours": 9.925, "orbital_period_days": 4331.0, "mass_kg": 1.8982e27, "radius_km": 69911.0, "gravity_m_s2": 24.79, "distance_from_sun_km": 778.6e6},
    "Saturn": {"name_fa": "زحل", "color": "#F0E68C", "rotation_period_hours": 10.656, "orbital_period_days": 10747.0, "mass_kg": 5.6834e26, "radius_km": 58232.0, "gravity_m_s2": 10.44, "distance_from_sun_km": 1433.5e6},
    "Uranus": {"name_fa": "اورانوس", "color": "#40E0D0", "rotation_period_hours": 17.24, "orbital_period_days": 30589.0, "mass_kg": 8.6810e25, "radius_km": 25362.0, "gravity_m_s2": 8.69, "distance_from_sun_km": 2872.5e6},
    "Neptune": {"name_fa": "نپتون", "color": "#4169E1", "rotation_period_hours": 16.11, "orbital_period_days": 59800.0, "mass_kg": 1.02413e26, "radius_km": 24622.0, "gravity_m_s2": 11.15, "distance_from_sun_km": 4495.1e6},
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
BACKTEST_CANDLES = 200
FORECAST_HOURS = 12
RR_RATIO_DEFAULT = 2.0

FONT_FAMILY = "Vazirmatn, Tahoma, Arial, sans-serif"

# ==============================================================================
# 2) REST API پایدار بایبیت
# ==============================================================================

REST_CANDIDATES = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json",
})
_ACTIVE_REST_BASE = {"url": None}

def bybit_get(path, params, timeout=10):
    cands = ([_ACTIVE_REST_BASE["url"]] if _ACTIVE_REST_BASE["url"] else []) + \
            [b for b in REST_CANDIDATES if b != _ACTIVE_REST_BASE["url"]]
    for base in cands:
        try:
            r = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code in (403, 451): continue
            r.raise_for_status()
            d = r.json()
            if d.get("retCode") == 0:
                _ACTIVE_REST_BASE["url"] = base
                return d
        except Exception: continue
    return None

def get_server_time():
    d = bybit_get("/v5/market/time", {})
    try:
        res = (d or {}).get("result") or {}
        nano = res.get("timeNano")
        if nano: return datetime.fromtimestamp(int(nano) / 1e9, tz=timezone.utc)
        sec = res.get("timeSecond")
        if sec: return datetime.fromtimestamp(int(sec) / 1e3, tz=timezone.utc)
    except Exception: pass
    return datetime.now(timezone.utc)

def get_klines(symbol, interval, category="linear", limit=1000):
    d = bybit_get("/v5/market/kline", {"category": category, "symbol": symbol, "interval": interval, "limit": limit})
    if not d or "list" not in (d.get("result") or {}): return pd.DataFrame()
    lst = d["result"]["list"]
    if not lst: return pd.DataFrame()
    df = pd.DataFrame(lst, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
    for c in ["open", "high", "low", "close", "volume"]: df[c] = df[c].astype(float)
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
    orbital_seconds = planet["orbital_period_days"] * 24 * 3600
    return {
        "planet_name": planet_name, "planet_name_fa": planet["name_fa"], "color": planet["color"],
        "local_hour": planet_hour, "rotation_fraction": rotation_fraction, "day_number": delta_seconds / rotation_seconds,
        "orbital_fraction": (delta_seconds % orbital_seconds) / orbital_seconds, "year_number": delta_seconds / orbital_seconds,
        "rotation_period_hours": planet["rotation_period_hours"], "gravity": planet["gravity_m_s2"], "mass": planet["mass_kg"],
    }

def calculate_all_planet_times(earth_utc: datetime) -> List[Dict]:
    return [calculate_planet_time(planet, earth_utc) for planet in PLANETS.keys()]

def calculate_universal_time(planet_times: List[Dict]) -> float:
    total_mass = sum(p["mass"] for p in planet_times)
    return sum((p["mass"] / total_mass) * p["rotation_fraction"] for p in planet_times)

# ==============================================================================
# 4) محاسبات گرانشی و حمایت/مقاومت
# ==============================================================================

def calculate_gravitational_force(planet_mass: float, distance_km: float, btc_price: float) -> float:
    return G * planet_mass * (btc_price * 1e10) / ((distance_km * 1000) ** 2)

def calculate_gravitational_support_resistance(df: pd.DataFrame, earth_utc: datetime, price_index: int = -1) -> Dict:
    if price_index == -1: price_index = len(df) - 1
    live_price = float(df.iloc[price_index]["close"])
    planet_times = calculate_all_planet_times(earth_utc)
    forces = {p["planet_name"]: calculate_gravitational_force(PLANETS[p["planet_name"]]["mass_kg"], PLANETS[p["planet_name"]]["distance_from_sun_km"], live_price) for p in planet_times}
    max_force = max(forces.values())
    normalized_forces = {k: v / max_force for k, v in forces.items()}

    support_levels, resistance_levels = [], []
    for p in planet_times:
        force_weight = normalized_forces[p["planet_name"]]
        price_impact_pct = force_weight * 5
        if 0 <= p["local_hour"] < 12:
            support_price = live_price * (1 - (price_impact_pct * (1 - p["local_hour"] / 12)) / 100)
            support_levels.append({"planet": p["planet_name"], "planet_fa": p["planet_name_fa"], "price": support_price, "strength": force_weight, "local_hour": p["local_hour"], "color": p["color"]})
        else:
            resistance_price = live_price * (1 + (price_impact_pct * ((p["local_hour"] - 12) / 12)) / 100)
            resistance_levels.append({"planet": p["planet_name"], "planet_fa": p["planet_name_fa"], "price": resistance_price, "strength": force_weight, "local_hour": p["local_hour"], "color": p["color"]})

    return {"live_price": live_price, "support_levels": sorted(support_levels, key=lambda x: x["strength"], reverse=True),
            "resistance_levels": sorted(resistance_levels, key=lambda x: x["strength"], reverse=True),
            "forces": normalized_forces, "planet_times": planet_times, "timestamp": earth_utc}

def calculate_total_gravitational_pull(sr_data: Dict) -> Tuple[float, float]:
    return sum(l["strength"] for l in sr_data["support_levels"]), sum(l["strength"] for l in sr_data["resistance_levels"])

# ==============================================================================
# 5) پیش‌بینی مسیر قیمت
# ==============================================================================

def predict_price_path_gravitational(df: pd.DataFrame, current_time: datetime, interval_minutes: int, forecast_hours: int = 12) -> pd.DataFrame:
    current_price = float(df.iloc[-1]["close"])
    last_timestamp = pd.Timestamp(df.iloc[-1]["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)
    predictions = []
    for i in range(int(forecast_hours * 60 / interval_minutes)):
        future_time = last_timestamp + timedelta(minutes=interval_minutes * (i + 1))
        planet_times = calculate_all_planet_times(future_time)
        forces = {p["planet_name"]: calculate_gravitational_force(PLANETS[p["planet_name"]]["mass_kg"], PLANETS[p["planet_name"]]["distance_from_sun_km"], current_price) for p in planet_times}
        max_force = max(forces.values())
        normalized_forces = {k: v / max_force for k, v in forces.items()}
        net_force = sum([normalized_forces[p["planet_name"]] * ((p["local_hour"] - 12) / 12 if p["local_hour"] >= 12 else -(1 - p["local_hour"] / 12)) for p in planet_times])
        current_price *= (1 + (net_force * 0.5) / 100)
        predictions.append({"timestamp": future_time, "price": current_price, "net_force": net_force})
    return pd.DataFrame(predictions)

def build_price_path_chart(df: pd.DataFrame, predicted_df: pd.DataFrame, sr_data: Dict, symbol: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df["ts"], open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="قیمت تاریخی", increasing_line_color=UP, decreasing_line_color=DN, opacity=0.8))
    if not predicted_df.empty:
        fig.add_trace(go.Scatter(x=predicted_df["timestamp"], y=predicted_df["price"], mode="lines+markers", name="مسیر پیش‌بینی‌شده", line=dict(color=GOLD, width=3, dash="dash")))
    for level in sr_data["support_levels"][:3]:
        fig.add_hline(y=level["price"], line_dash="dot", line_color=UP, opacity=0.5)
    for level in sr_data["resistance_levels"][:3]:
        fig.add_hline(y=level["price"], line_dash="dot", line_color=DN, opacity=0.5)
    last_time = pd.Timestamp(df.iloc[-1]["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)
    fig.add_shape(type="line", x0=last_time, x1=last_time, y0=0, y1=1, yref="paper", line=dict(color=GOLD, width=2))
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, title=f"📈 مسیر قیمت — {symbol}", xaxis=dict(rangeslider=dict(visible=False)), margin=dict(l=20, r=20, t=80, b=20), font=dict(family=FONT_FAMILY))
    return fig

# ==============================================================================
# 6) سیستم بک‌تست حرفه‌ای (با فیلتر ضد اسکلپ و SL بر اساس ATR)
# ==============================================================================

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """محاسبه ATR برای تعیین حد ضرر معقول بر اساس نوسان بازار"""
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['close'].shift(1)).abs()
    tr3 = (df['low'] - df['close'].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def backtest_system(df: pd.DataFrame, interval_minutes: int, rr_ratio: float = 2.0, lookforward: int = 20) -> Dict:
    n = len(df)
    if n < BACKTEST_CANDLES + lookforward + 5:
        return {"win_rate": 0, "support_win_rate": 0, "resistance_win_rate": 0, "total_predictions": 0, "wins": 0, "losses": 0, "pending": 0, "successful": 0, "details": [], "planet_stats": [], "rr_ratio": rr_ratio}

    atr_series = calculate_atr(df, period=14)
    MIN_TRADE_PCT = 0.005  # حداقل فاصله 0.5% برای جلوگیری از معاملات اسکلپ و نویز
    
    start_idx = n - BACKTEST_CANDLES
    predictions = []

    for i in range(start_idx, n - lookforward):
        current_time = pd.Timestamp(df.iloc[i]["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)
        current_price = float(df.iloc[i]["close"])
        
        atr_val = float(atr_series.iloc[i])
        if pd.isna(atr_val) or atr_val <= 0:
            atr_val = current_price * MIN_TRADE_PCT
            
        # حد ضرر معقول = 2 برابر ATR (استاندارد بازار) یا حداقل 0.5% قیمت
        sl_distance = max(atr_val * 2.0, current_price * MIN_TRADE_PCT)

        sr_data = calculate_gravitational_support_resistance(df, current_time, price_index=i)
        future_candles = df.iloc[i + 1 : i + 1 + lookforward]

        # بررسی سطوح حمایت (پوزیشن Short)
        for level in sr_data["support_levels"][:3]:
            predicted_price = level["price"]
            tp_distance = current_price - predicted_price
            
            # فیلتر اسکلپ: اگر هدف خیلی نزدیک است رد کن
            if tp_distance <= current_price * MIN_TRADE_PCT: continue
                
            # محاسبه R:R واقعی این ستاپ
            actual_rr = tp_distance / sl_distance
            if actual_rr < rr_ratio: continue  # فقط ستاپ‌های با R:R معقول
                
            tp = predicted_price
            sl = current_price + sl_distance
            outcome, mfe, mae = "Pending", 0.0, 0.0

            for _, future_row in future_candles.iterrows():
                high, low = float(future_row["high"]), float(future_row["low"])
                mae = max(mae, high - current_price)
                mfe = max(mfe, current_price - low)
                if high >= sl: outcome = "Loss"; break
                if low <= tp: outcome = "Win"; break

            predictions.append({
                "type": "support", "planet": level["planet_fa"], "planet_en": level["planet"],
                "entry_price": current_price, "target_price": tp, "stop_loss": sl,
                "sl_distance_pct": (sl_distance / current_price) * 100,
                "tp_distance_pct": (tp_distance / current_price) * 100,
                "atr": atr_val, "actual_rr": actual_rr,
                "outcome": outcome, "rr_ratio": rr_ratio, "mfe": mfe, "mae": mae,
                "timestamp": current_time, "strength": level["strength"],
            })

        # بررسی سطوح مقاومت (پوزیشن Long)
        for level in sr_data["resistance_levels"][:3]:
            predicted_price = level["price"]
            tp_distance = predicted_price - current_price
            
            if tp_distance <= current_price * MIN_TRADE_PCT: continue
                
            actual_rr = tp_distance / sl_distance
            if actual_rr < rr_ratio: continue
                
            tp = predicted_price
            sl = current_price - sl_distance
            outcome, mfe, mae = "Pending", 0.0, 0.0

            for _, future_row in future_candles.iterrows():
                high, low = float(future_row["high"]), float(future_row["low"])
                mae = max(mae, current_price - low)
                mfe = max(mfe, high - current_price)
                if low <= sl: outcome = "Loss"; break
                if high >= tp: outcome = "Win"; break

            predictions.append({
                "type": "resistance", "planet": level["planet_fa"], "planet_en": level["planet"],
                "entry_price": current_price, "target_price": tp, "stop_loss": sl,
                "sl_distance_pct": (sl_distance / current_price) * 100,
                "tp_distance_pct": (tp_distance / current_price) * 100,
                "atr": atr_val, "actual_rr": actual_rr,
                "outcome": outcome, "rr_ratio": rr_ratio, "mfe": mfe, "mae": mae,
                "timestamp": current_time, "strength": level["strength"],
            })

    total = len(predictions)
    wins = sum(1 for p in predictions if p["outcome"] == "Win")
    losses = sum(1 for p in predictions if p["outcome"] == "Loss")
    pending = total - wins - losses
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

    support_preds = [p for p in predictions if p["type"] == "support"]
    resistance_preds = [p for p in predictions if p["type"] == "resistance"]
    
    def calc_wr(preds):
        w = sum(1 for p in preds if p["outcome"] == "Win")
        l = sum(1 for p in preds if p["outcome"] == "Loss")
        return (w / (w + l) * 100) if (w + l) > 0 else 0

    planets = list(set(p["planet_en"] for p in predictions))
    planet_stats = []
    for pl_en in planets:
        pl_preds = [p for p in predictions if p["planet_en"] == pl_en]
        planet_stats.append({"planet": pl_preds[0]["planet"], "planet_en": pl_en, "total": len(pl_preds), "wins": sum(1 for p in pl_preds if p["outcome"] == "Win"), "losses": sum(1 for p in pl_preds if p["outcome"] == "Loss"), "win_rate": calc_wr(pl_preds)})

    return {
        "win_rate": win_rate, "support_win_rate": calc_wr(support_preds), "resistance_win_rate": calc_wr(resistance_preds),
        "total_predictions": total, "wins": wins, "losses": losses, "pending": pending, "successful": wins,
        "details": predictions[-50:], "planet_stats": planet_stats, "rr_ratio": rr_ratio
    }

# ==============================================================================
# 7) Figure ساعت سیاره‌ای و گیج‌ها
# ==============================================================================

def build_planet_clock_figure(sr_data: Dict, earth_utc: datetime, symbol: str):
    fig = go.Figure()
    R = 1.0
    ang_full = np.linspace(0, 360, 361)
    fig.add_trace(go.Scatter(x=R * np.cos(np.radians(ang_full)), y=R * np.sin(np.radians(ang_full)), mode="lines", line=dict(color=LINE, width=2), showlegend=False))
    for p in sr_data["planet_times"]:
        angle = (p["local_hour"] / 24) * 360
        fig.add_trace(go.Scatter(x=[0.85*R*np.cos(np.radians(angle))], y=[0.85*R*np.sin(np.radians(angle))], mode="markers+text", marker=dict(size=12, color=p["color"]), text=[p["planet_name_fa"]], textposition="top center", name=p["planet_name_fa"]))
    fig.add_annotation(x=0, y=0, text=f"<b>{sr_data['live_price']:,.2f}</b>", showarrow=False, font=dict(size=14, color=GOLD), bgcolor=CARD, bordercolor=GOLD, borderwidth=2)
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, title=f"🪐 ساعت سیاره‌ای — {symbol}", showlegend=True)
    fig.update_xaxes(visible=False); fig.update_yaxes(visible=False, scaleanchor="x")
    return fig

def build_win_rate_gauge(win_rate: float, title: str) -> go.Figure:
    fig = go.Figure()
    color = UP if win_rate >= 60 else (GOLD if win_rate >= 45 else DN)
    fig.add_trace(go.Indicator(mode="gauge+number", value=win_rate, number={"suffix": "%", "font": {"color": color, "size": 32}}, title={"text": title, "font": {"color": MUT, "size": 14}},
        gauge={"axis": {"range": [0, 100], "tickcolor": MUT}, "bar": {"color": color}, "bgcolor": CARD2, "steps": [{"range": [0, 40], "color": "rgba(255,93,108,0.18)"}, {"range": [40, 60], "color": "rgba(243,186,47,0.18)"}, {"range": [60, 100], "color": "rgba(31,215,166,0.18)"}]}))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family=FONT_FAMILY, color=TXT), margin=dict(l=20, r=20, t=50, b=10), height=250)
    return fig

# ==============================================================================
# 8) اپلیکیشن Dash
# ==============================================================================

FONT_URL = "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;800&display=swap"
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG, FONT_URL])
app.title = "Chrono-Gravitas v3.1"
server = app.server

app.index_string = """<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>body{background:#070b14;}*{font-family:'Vazirmatn',Tahoma,Arial,sans-serif !important;}
.glass-card{background:linear-gradient(145deg,rgba(16,28,56,0.85),rgba(10,17,35,0.85));border:1px solid #22304e;border-radius:16px;box-shadow:0 8px 32px rgba(0,0,0,0.35);}
.stat-value{font-weight:800;font-size:20px;}.stat-label{font-size:11px;color:#8ea0c4;}
.custom-tabs .tab{background-color:#0f1830 !important;color:#8ea0c4 !important;border:1px solid #22304e !important;border-bottom:none !important;border-top-left-radius:8px !important;border-top-right-radius:8px !important;margin-right:4px !important;padding:12px 24px !important;font-weight:bold !important;}
.custom-tabs .tab--selected{background-color:#101c38 !important;color:#f3ba2f !important;border:1px solid #f3ba2f !important;border-bottom:1px solid #101c38 !important;}.custom-tabs{border-bottom:1px solid #22304e !important;}</style>
</head><body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>"""

def stat_card(id_prefix, label, color=TXT):
    return dbc.Col(html.Div([html.Div(label, className="stat-label"), html.Div("—", id=f"{id_prefix}-value", className="stat-value", style={"color": color})], className="glass-card", style={"padding": "12px 16px", "textAlign": "center"}), md=2, xs=6, style={"marginBottom": 10})

app.layout = html.Div([
    html.Div([html.H4("🪐 Chrono-Gravitas v3.1", style={"color": GOLD, "fontWeight": 800, "margin": 0}), html.Div("سیستم بک‌تست حرفه‌ای با ATR و R:R معقول", style={"color": MUT, "fontSize": 12})], style={"maxWidth": 1600, "margin": "10px auto 4px auto", "padding": "0 6px"}),

    dcc.Tabs(id="main-tabs", value="tab-main", className="custom-tabs", children=[
        dcc.Tab(label="📊 داشبورد اصلی", value="tab-main", children=[
            dbc.Card(dbc.CardBody(dbc.Row([
                dbc.Col([html.Label("نماد"), dcc.Input(id="symbol", value=DEFAULT_SYMBOL, type="text", style={"width": "100%", "padding": 6, "borderRadius": 8, "background": CARD2, "color": TXT, "border": f"1px solid {LINE}"})], md=2),
                dbc.Col([html.Label("بازار"), dcc.Dropdown(id="category", value=DEFAULT_CATEGORY, clearable=False, options=[{"label": v, "value": v} for v in ["linear", "spot", "inverse"]])], md=2),
                dbc.Col([html.Label("تایم‌فریم"), dcc.Dropdown(id="interval", value=DEFAULT_INTERVAL, clearable=False, options=[{"label": lbl, "value": val} for lbl, val in [("1m", "1"), ("5m", "5"), ("15m", "15"), ("30m", "30"), ("1h", "60"), ("4h", "240")]])], md=2),
                dbc.Col([html.Label("افق پیش‌بینی"), dcc.Input(id="forecast-hours", type="number", value=FORECAST_HOURS, min=1, max=48, step=1, style={"width": "100%", "padding": 6, "borderRadius": 8, "background": CARD2, "color": TXT, "border": f"1px solid {LINE}"})], md=2),
                dbc.Col(dbc.Button("🔄 به‌روزرسانی", id="refresh-btn", color="warning", className="mt-3", style={"fontWeight": "bold", "color": BG, "width": "100%"}), md=2),
            ])), className="glass-card", style={"maxWidth": 1600, "margin": "10px auto"}),

            dbc.Card(dbc.CardBody([dcc.Graph(id="price-path-chart", style={"height": "70vh"}, config={"displaylogo": False})]), className="glass-card", style={"maxWidth": 1600, "margin": "10px auto"}),
            html.Div(dbc.Row([stat_card("live-price", "قیمت لایو", GOLD), stat_card("support-pull", "جذب حمایت", UP), stat_card("resistance-pull", "جذب مقاومت", DN), stat_card("universal-time", "زمان مطلق", BLUE), stat_card("win-rate", "Win Rate کل", GOLD), stat_card("predictions", "تعداد ستاپ", MUT)]), style={"maxWidth": 1600, "margin": "0 auto"}),
            dbc.Row([dbc.Col(dbc.Card(dbc.CardBody([dcc.Graph(id="win-rate-total-gauge")])), className="glass-card", md=4), dbc.Col(dbc.Card(dbc.CardBody([dcc.Graph(id="win-rate-support-gauge")])), className="glass-card", md=4), dbc.Col(dbc.Card(dbc.CardBody([dcc.Graph(id="win-rate-resistance-gauge")])), className="glass-card", md=4)], style={"maxWidth": 1600, "margin": "10px auto"}),
            dbc.Row([dbc.Col(dbc.Card(dbc.CardBody([dcc.Graph(id="planet-clock-graph", style={"height": "60vh"})])), className="glass-card", md=8), dbc.Col(dbc.Card(dbc.CardBody([html.H5("⏰ زمان در سیارات"), dash_table.DataTable(id="planet-time-table")])), className="glass-card", md=4)], style={"maxWidth": 1600, "margin": "10px auto"}),
            dbc.Row([dbc.Col(dbc.Card(dbc.CardBody([html.H5("🟢 سطوح حمایت"), dash_table.DataTable(id="support-table")])), className="glass-card", md=6), dbc.Col(dbc.Card(dbc.CardBody([html.H5("🔴 سطوح مقاومت"), dash_table.DataTable(id="resistance-table")])), className="glass-card", md=6)], style={"maxWidth": 1600, "margin": "10px auto"}),
        ]),
        dcc.Tab(label="📈 آمار دقیق و R:R (ضد اسکلپ)", value="tab-stats", children=[
            dbc.Card(dbc.CardBody(dbc.Row([dbc.Col([html.Label("حداقل R:R برای ثبت معامله (مثلا 2.0)"), dcc.Input(id="rr-ratio", type="number", value=RR_RATIO_DEFAULT, min=0.5, max=10.0, step=0.1, style={"width": "100%", "padding": 6, "borderRadius": 8, "background": CARD2, "color": TXT, "border": f"1px solid {LINE}"})], md=3)])), className="glass-card", style={"maxWidth": 1600, "margin": "10px auto"}),
            html.Div(dbc.Row([stat_card("rr-total-trades", "کل معاملات", MUT), stat_card("rr-wins", "معاملات برنده", UP), stat_card("rr-losses", "معاملات بازنده", DN), stat_card("rr-winrate", "وین‌ریت واقعی", GOLD), stat_card("rr-avg-mfe", "میانگین MFE", BLUE), stat_card("rr-avg-mae", "میانگین MAE", DN)]), style={"maxWidth": 1600, "margin": "0 auto"}),
            dbc.Row([dbc.Col(dbc.Card(dbc.CardBody([dcc.Graph(id="rr-gauge-total")])), className="glass-card", md=4), dbc.Col(dbc.Card(dbc.CardBody([dcc.Graph(id="rr-gauge-support")])), className="glass-card", md=4), dbc.Col(dbc.Card(dbc.CardBody([dcc.Graph(id="rr-gauge-resistance")])), className="glass-card", md=4)], style={"maxWidth": 1600, "margin": "10px auto"}),
            dbc.Row([dbc.Col(dbc.Card(dbc.CardBody([html.H5("وین‌ریت بر اساس سیارات"), dcc.Graph(id="planet-wr-chart")])), className="glass-card", md=6), dbc.Col(dbc.Card(dbc.CardBody([html.H5("جدول آمار سیارات"), dash_table.DataTable(id="planet-stats-table")])), className="glass-card", md=6)], style={"maxWidth": 1600, "margin": "10px auto"}),
            dbc.Row([dbc.Col(dbc.Card(dbc.CardBody([html.H5("جزئیات معاملات بک‌تست (حد ضرر بر اساس ATR)"), dash_table.DataTable(id="rr-details-table", page_size=15)])), className="glass-card", md=12)], style={"maxWidth": 1600, "margin": "10px auto"}),
        ])
    ], style={"maxWidth": 1600, "margin": "10px auto", "backgroundColor": BG}),
    dcc.Interval(id="tick", interval=30_000, n_intervals=0),
], style={"background": BG, "minHeight": "100vh", "padding": "10px", "fontFamily": FONT_FAMILY, "direction": "rtl"})

@callback(
    Output("price-path-chart", "figure"), Output("planet-clock-graph", "figure"),
    Output("planet-time-table", "data"), Output("planet-time-table", "columns"),
    Output("support-table", "data"), Output("support-table", "columns"),
    Output("resistance-table", "data"), Output("resistance-table", "columns"),
    Output("win-rate-total-gauge", "figure"), Output("win-rate-support-gauge", "figure"), Output("win-rate-resistance-gauge", "figure"),
    Output("live-price-value", "children"), Output("support-pull-value", "children"), Output("resistance-pull-value", "children"),
    Output("universal-time-value", "children"), Output("win-rate-value", "children"), Output("predictions-value", "children"),
    Output("rr-total-trades-value", "children"), Output("rr-wins-value", "children"), Output("rr-losses-value", "children"),
    Output("rr-winrate-value", "children"), Output("rr-avg-mfe-value", "children"), Output("rr-avg-mae-value", "children"),
    Output("rr-gauge-total", "figure"), Output("rr-gauge-support", "figure"), Output("rr-gauge-resistance", "figure"),
    Output("planet-wr-chart", "figure"), Output("planet-stats-table", "data"), Output("planet-stats-table", "columns"),
    Output("rr-details-table", "data"), Output("rr-details-table", "columns"),
    Input("tick", "n_intervals"), Input("refresh-btn", "n_clicks"),
    State("symbol", "value"), State("category", "value"), State("interval", "value"), State("forecast-hours", "value"), State("rr-ratio", "value")
)
def update_all(_n, _click, symbol, category, interval, forecast_hours, rr_ratio):
    symbol = (symbol or DEFAULT_SYMBOL).upper().strip()
    interval_map = {"1": 1, "5": 5, "15": 15, "30": 30, "60": 60, "240": 240}
    interval_minutes = interval_map.get(interval, 15)
    rr_ratio = float(rr_ratio or RR_RATIO_DEFAULT)
    
    now_utc = get_server_time()
    df = get_klines(symbol, interval, category, limit=1000)
    if df.empty: return tuple([go.Figure()] * 8) + tuple([[]] * 2) + tuple([go.Figure()] * 3) + tuple(["—"] * 6) + tuple([go.Figure()] * 3) + tuple([[]] * 2) + tuple([go.Figure()] * 1) + tuple([[]] * 2)

    sr_data = calculate_gravitational_support_resistance(df, now_utc)
    total_support_pull, total_resistance_pull = calculate_total_gravitational_pull(sr_data)
    universal_time = calculate_universal_time(sr_data["planet_times"])
    backtest_results = backtest_system(df, interval_minutes, rr_ratio=rr_ratio, lookforward=20)
    predicted_df = predict_price_path_gravitational(df, now_utc, interval_minutes, float(forecast_hours or FORECAST_HOURS))
    
    price_path_fig = build_price_path_chart(df, predicted_df, sr_data, symbol)
    planet_fig = build_planet_clock_figure(sr_data, now_utc, symbol)
    
    p_data = [{"سیاره": p["planet_name_fa"], "ساعت محلی": f"{p['local_hour']:.2f}", "نیرو": f"{sr_data['forces'][p['planet_name']] * 100:.1f}%"} for p in sr_data["planet_times"]]
    p_cols = [{"name": c, "id": c} for c in ["سیاره", "ساعت محلی", "نیرو"]]
    s_data = [{"سیاره": l["planet_fa"], "قیمت": f"{l['price']:,.2f}", "فاصله (%)": f"{((sr_data['live_price'] - l['price']) / sr_data['live_price'] * 100):.2f}%"} for l in sr_data["support_levels"]]
    s_cols = [{"name": c, "id": c} for c in ["سیاره", "قیمت", "فاصله (%)"]]
    r_data = [{"سیاره": l["planet_fa"], "قیمت": f"{l['price']:,.2f}", "فاصله (%)": f"{((l['price'] - sr_data['live_price']) / sr_data['live_price'] * 100):.2f}%"} for l in sr_data["resistance_levels"]]
    r_cols = [{"name": c, "id": c} for c in ["سیاره", "قیمت", "فاصله (%)"]]

    rr_total = backtest_results["total_predictions"]
    rr_wins = backtest_results["wins"]
    rr_losses = backtest_results["losses"]
    details = backtest_results["details"]
    avg_mfe = sum(d["mfe"] for d in details) / len(details) if details else 0
    avg_mae = sum(d["mae"] for d in details) / len(details) if details else 0

    planet_wr_fig = go.Figure()
    if backtest_results["planet_stats"]:
        planets = [p["planet"] for p in backtest_results["planet_stats"]]
        wrs = [p["win_rate"] for p in backtest_results["planet_stats"]]
        planet_wr_fig.add_trace(go.Bar(x=planets, y=wrs, text=[f"{w:.1f}%" for w in wrs], textposition="outside"))
        planet_wr_fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=20, r=20, t=40, b=20))

    pl_stats_data = [{"سیاره": ps["planet"], "تعداد": ps["total"], "برد": ps["wins"], "باخت": ps["losses"], "وین‌ریت": f"{ps['win_rate']:.1f}%"} for ps in backtest_results["planet_stats"]]
    pl_stats_cols = [{"name": c, "id": c} for c in ["سیاره", "تعداد", "برد", "باخت", "وین‌ریت"]]

    rr_details_data = []
    for d in details:
        status = "✅ برد" if d["outcome"] == "Win" else ("❌ باخت" if d["outcome"] == "Loss" else "⏳ در انتظار")
        type_str = "🟢 Short" if d["type"] == "support" else "🔴 Long"
        rr_details_data.append({
            "زمان": d["timestamp"].strftime("%m-%d %H:%M"), "نوع": type_str, "سیاره": d["planet"], "قیمت ورود": f"{d['entry_price']:,.2f}", 
            "هدف (TP)": f"{d['target_price']:,.2f}", "حد ضرر (SL)": f"{d['stop_loss']:,.2f}", 
            "فاصله هدف": f"{d['tp_distance_pct']:.2f}%", "حد ضرر (ATR)": f"{d['sl_distance_pct']:.2f}%",
            "R:R واقعی": f"1:{d['actual_rr']:.1f}", "نتیجه": status
        })
    rr_details_cols = [{"name": c, "id": c} for c in ["زمان", "نوع", "سیاره", "قیمت ورود", "هدف (TP)", "حد ضرر (SL)", "فاصله هدف", "حد ضرر (ATR)", "R:R واقعی", "نتیجه"]]

    return (
        price_path_fig, planet_fig, p_data, p_cols, s_data, s_cols, r_data, r_cols,
        build_win_rate_gauge(backtest_results["win_rate"], "Win Rate کل"), build_win_rate_gauge(backtest_results["support_win_rate"], "Win Rate حمایت"), build_win_rate_gauge(backtest_results["resistance_win_rate"], "Win Rate مقاومت"),
        f"{sr_data['live_price']:,.2f}", f"{total_support_pull * 100:.1f}%", f"{total_resistance_pull * 100:.1f}%", f"{universal_time:.4f}", f"{backtest_results['win_rate']:.1f}%", f"{backtest_results['total_predictions']}",
        f"{rr_total}", f"{rr_wins}", f"{rr_losses}", f"{backtest_results['win_rate']:.1f}%", f"{avg_mfe:,.2f}", f"{avg_mae:,.2f}",
        build_win_rate_gauge(backtest_results["win_rate"], f"وین‌ریت کل (R:R ≥ {rr_ratio})"), build_win_rate_gauge(backtest_results["support_win_rate"], "حمایت"), build_win_rate_gauge(backtest_results["resistance_win_rate"], "مقاومت"),
        planet_wr_fig, pl_stats_data, pl_stats_cols, rr_details_data, rr_details_cols
    )

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8060, use_reloader=False)