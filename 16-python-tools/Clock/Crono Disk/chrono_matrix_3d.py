# -*- coding: utf-8 -*-
"""
⏳ 3D Chrono-Matrix — اسکنر خطوط زمانی قطعی قیمت (اتصال پایدار بایبیت)
================================================================================
این اسکریپت با تبدیل زمان خطی به مختصات قطبی-استوانه‌ای (Cylindrical)، ایده
دیسک چرخان و خطوط زمانی را به صورت سه‌بعدی روی نمودارهای Plotly/Dash پیاده‌سازی می‌کند.
"""

import math
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
import requests
import plotly.graph_objects as go
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc

# ==============================================================================
# 0) تنظیمات و پالت رنگی
# ==============================================================================
BG = "#070b14"
CARD = "#0f1830"
LINE = "#22304e"
TXT = "#eef2fb"
MUT = "#8ea0c4"
GOLD = "#f3ba2f"
BLUE = "#4f8dfd"
FONT_FAMILY = "Vazirmatn, Tahoma, Arial, sans-serif"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_CATEGORY = "linear"
DEFAULT_INTERVAL = "15"
DEFAULT_LIMIT = 1000

# ==============================================================================
# 1) اتصال پایدار بایبیت (چند دامنه‌ی جایگزین + هدر مرورگر + سرور تایم)
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
    """
    تلاش روی دامنه‌ی فعال قبلی و در صورت شکست، چرخش بین دامنه‌های جایگزین.
    دامنه‌ای که موفق شود به‌عنوان دامنه‌ی فعال ذخیره می‌شود تا درخواست‌های بعدی
    سریع‌تر انجام شوند.
    """
    cands = ([_ACTIVE_REST_BASE["url"]] if _ACTIVE_REST_BASE["url"] else []) + \
            [b for b in REST_CANDIDATES if b != _ACTIVE_REST_BASE["url"]]
    last_err = None
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
            last_err = d.get("retMsg")
        except Exception as e:
            last_err = str(e)
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


def get_klines(symbol, interval, category=DEFAULT_CATEGORY, limit=1000):
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

    df = pd.DataFrame(lst, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)


def get_interval_minutes(interval):
    s = str(interval).strip().lower()
    if s == "d":
        return 1440
    try:
        return int(s)
    except Exception:
        return 15


# ==============================================================================
# 2) موتور محاسبات دیسک سه‌بعدی و استخراج خط زمانی
# ==============================================================================
def calculate_timeline_matrix(df):
    """
    تبدیل داده‌های خطی به ماتریس سه‌بعدی چرخشی.
    هر روز یک 'دور' روی دیسک است.
    """
    df = df.copy()
    df['minute_of_day'] = df['ts'].dt.hour * 60 + df['ts'].dt.minute
    df['angle'] = (df['minute_of_day'] / 1440.0) * 360.0

    # شعاع = گسترش دیسک در طول زمان (مانند شیارهای سی‌دی)، از R=1 تا R=2
    n = len(df)
    df['radius'] = np.linspace(1, 2, n)

    df['x'] = df['radius'] * np.cos(np.radians(df['angle']))
    df['y'] = df['radius'] * np.sin(np.radians(df['angle']))
    df['z'] = df['close']

    return df


def predict_turning_points(df):
    """
    بررسی شیارهای قبلی در زاویه فعلی برای استخراج قیمت در خط زمانی آینده.
    """
    last_angle = df['angle'].iloc[-1]
    last_radius = df['radius'].iloc[-1]

    tolerance = 2.0  # درجه
    historical_matches = df[(df['angle'] >= last_angle - tolerance) &
                             (df['angle'] <= last_angle + tolerance)].copy()

    if len(historical_matches) > 1:
        poly = np.polyfit(historical_matches['radius'], historical_matches['z'], 1)
        future_radius = last_radius + (last_radius - historical_matches['radius'].iloc[-2])
        future_price = np.polyval(poly, future_radius)
        return future_price
    return df['close'].iloc[-1]


# ==============================================================================
# 3) رابط کاربری و سرور Dash
# ==============================================================================
FONT_URL = "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;800&display=swap"
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG, FONT_URL])
app.title = "Timeline Disk"
server = app.server

CATEGORY_OPTS = [{"label": v, "value": v} for v in ["linear", "spot", "inverse"]]
INTERVAL_OPTS = [
    {"label": "15 دقیقه", "value": "15"},
    {"label": "1 ساعت", "value": "60"},
    {"label": "4 ساعت", "value": "240"},
    {"label": "1 روز", "value": "D"},
]

app.layout = dbc.Container([
    html.Br(),
    html.H3("استخراج‌گر خطوط زمانی قیمت (Time-Matrix)", style={"color": GOLD, "textAlign": "center"}),
    html.P("قیمت به عنوان ارتفاع در یک دیسک چرخشی زمان محاسبه می‌شود", style={"color": MUT, "textAlign": "center"}),

    dbc.Row([
        dbc.Col([
            html.Label("نماد:", style={"color": TXT}),
            dcc.Input(id="symbol-input", value=DEFAULT_SYMBOL, type="text", className="form-control",
                      style={"background": CARD, "color": GOLD}),
        ], width=2),
        dbc.Col([
            html.Label("بازار:", style={"color": TXT}),
            dcc.Dropdown(id="category-input", options=CATEGORY_OPTS, value=DEFAULT_CATEGORY,
                         clearable=False, style={"color": "black"}),
        ], width=2),
        dbc.Col([
            html.Label("تایم‌فریم:", style={"color": TXT}),
            dcc.Dropdown(id="interval-input", options=INTERVAL_OPTS, value=DEFAULT_INTERVAL,
                         clearable=False, style={"color": "black"}),
        ], width=2),
        dbc.Col([
            html.Br(),
            html.Button("محاسبه خط زمانی قطعی", id="run-btn", n_clicks=0,
                        className="btn btn-warning", style={"width": "100%"}),
        ], width=3),
    ], justify="center"),

    html.Br(),
    dbc.Row([
        dbc.Col([
            html.Div(id="prediction-output", style={
                "fontSize": "20px", "textAlign": "center", "color": BLUE, "fontWeight": "bold",
                "background": CARD, "padding": "15px", "borderRadius": "10px",
            }),
        ], width=6),
    ], justify="center"),

    html.Br(),
    html.Div(id="conn-status", style={"textAlign": "center", "color": MUT, "fontSize": 12}),
    html.Br(),
    dcc.Loading(dcc.Graph(id="3d-disk-graph", style={"height": "700px"})),

    dcc.Interval(id="tick", interval=30_000, n_intervals=0, disabled=True),
], fluid=True, style={"background": BG, "minHeight": "100vh"})


@app.callback(
    [Output("3d-disk-graph", "figure"),
     Output("prediction-output", "children"),
     Output("conn-status", "children")],
    [Input("run-btn", "n_clicks")],
    [State("symbol-input", "value"),
     State("category-input", "value"),
     State("interval-input", "value")]
)
def update_matrix(n_clicks, symbol, category, interval):
    symbol = (symbol or DEFAULT_SYMBOL).upper().strip()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL

    now_utc = get_server_time()
    df = get_klines(symbol, interval, category, limit=DEFAULT_LIMIT)

    if df.empty:
        return go.Figure(), "داده‌ای یافت نشد.", "🔴 قطع از بایبیت (هیچ‌کدام از دامنه‌ها پاسخ نداد)"

    df = calculate_timeline_matrix(df)
    future_price = predict_turning_points(df)
    live_price = df['close'].iloc[-1]

    fig = go.Figure()

    fig.add_trace(go.Scatter3d(
        x=df['x'], y=df['y'], z=df['z'],
        mode='lines',
        line=dict(color=df['z'], colorscale='Turbo', width=4),
        name="مسیر حرکت قیمت در دیسک",
    ))

    fig.add_trace(go.Scatter3d(
        x=[df['x'].iloc[-1]], y=[df['y'].iloc[-1]], z=[df['z'].iloc[-1]],
        mode='markers',
        marker=dict(size=8, color=GOLD, symbol='diamond'),
        name="نقطه اتصال فعلی (Live)",
    ))

    fig.update_layout(
        scene=dict(
            xaxis=dict(showbackground=False, visible=False),
            yaxis=dict(showbackground=False, visible=False),
            zaxis=dict(title="قیمت (خط زمانی)", backgroundcolor=BG, gridcolor=LINE, color=MUT),
            bgcolor=BG,
            camera=dict(eye=dict(x=1.5, y=1.5, z=0.5)),
        ),
        paper_bgcolor=BG, plot_bgcolor=BG,
        margin=dict(l=0, r=0, b=0, t=0),
        font=dict(family=FONT_FAMILY, color=TXT),
        showlegend=False,
    )

    prediction_text = f"قیمت فعلی: {live_price:,.2f} | استخراج خط زمانی برای زاویه فعلی در دور بعد: {future_price:,.2f}"
    status = f"🟢 متصل به {_ACTIVE_REST_BASE['url']} | {now_utc.strftime('%H:%M:%S')} UTC | {len(df)} کندل"

    return fig, prediction_text, status


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=8062, use_reloader=False)
