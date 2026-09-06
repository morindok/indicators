# -*- coding: utf-8 -*-
"""
🌙 Quantum Gann Square Dynamic System v11
سیستم مربع گن نوین بر پایه Chrono-Gann — لایه‌لایه و دینامیک
"""

import time
import numpy as np
import pandas as pd
import requests
import dash
from dash import dcc, html, Input, Output, State, ctx
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

# ==============================================================================
# 0) پالت رنگی تیره
# ==============================================================================
BG, CARD, LINE, TXT, MUT = "#0b1220", "#121c30", "#23314d", "#e8ecf4", "#8fa3c0"
GOLD, UP, DN = "#f0b90b", "#16a085", "#e74c3c"
CYAN = "#00f5ff"
PURPLE = "#9d4edd"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_CATEGORY = "linear"
DEFAULT_INTERVAL = "15"

# ==============================================================================
# 1) اتصال به بایبیت (دقیقاً مثل کد اصلی)
# ==============================================================================
REST_CANDIDATES = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
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

def get_klines(symbol, interval, category="linear", limit=500):
    d = bybit_get("/v5/market/kline", {
        "category": category, "symbol": symbol, "interval": interval, "limit": limit
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

# ==============================================================================
# 2) سیستم مربع گن دینامیک لایه‌لایه (مرکز با قیمت تغییر می‌کند)
# ==============================================================================
def generate_gann_shapes(df, current_price, interval, layers=3):
    """ایجاد ماتریس Gann Square دینامیک — لایه‌لایه"""
    if df.empty or current_price <= 0:
        return []
    shapes = []
    now = df['ts'].iloc[-1]
    base_time_min = 8 * int(interval or DEFAULT_INTERVAL)  # واحد زمان

    for layer in range(1, layers + 1):
        base = layer * 8
        color = GOLD if layer == 1 else PURPLE if layer == 2 else CYAN
        opacity = 0.85 - (layer * 0.18)

        # خطوط عمودی (زمان)
        for i in range(1, 9):
            t = now - pd.Timedelta(minutes=i * base)
            y_max = current_price * 3.5
            shapes.append({
                'type': 'line',
                'x0': t, 'x1': now,
                'y0': 0, 'y1': y_max,
                'line': {'color': color, 'width': 1, 'dash': 'dot', 'opacity': opacity}
            })

        # خطوط افقی (قیمت - سطوح کلیدی حمایت/مقاومت)
        for k in range(1, 9):
            mult = k / 4.0
            y = current_price * (0.65 + (k - 4.5) * 0.3)   # ۸ سطح دور قیمت فعلی
            shapes.append({
                'type': 'line',
                'x0': df['ts'].iloc[0], 'x1': now,
                'y0': y, 'y1': y,
                'line': {'color': color, 'width': 2.5 if k == 5 else 1.8, 'dash': 'dash'}
            })

        # خطوط مورب (دیاگونال - تعادل قیمت و زمان)
        for slope in [0.4, 0.8, 1.6, 3.2]:
            dt = (now - df['ts'].iloc[0]).total_seconds()
            dy = slope * (dt / 3600) * (current_price / 25)
            y0 = current_price - dy / 2
            y1 = current_price + dy / 2
            shapes.append({
                'type': 'line',
                'x0': df['ts'].iloc[0], 'x1': now,
                'y0': y0, 'y1': y1,
                'line': {'color': color, 'width': 1.2, 'dash': 'dashdot', 'opacity': opacity}
            })

    return shapes

# ==============================================================================
# 3) اپ Dash - Quantum Gann Square Dynamic
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])
app.title = "Quantum Gann Square System v11"

server = app.server

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
        dbc.Col(dbc.Button("🔄 بروزرسانی", id="refresh-btn", color="warning", className="mt-3",
                           style={"fontWeight": "bold", "color": "#0b1220", "width": "100%"}), md=2),
        dbc.Col(html.Div(id="conn-status", style={"color": MUT, "fontSize": 11, "marginTop": 22, "textAlign": "center"}), md=2),
    ])), style={"maxWidth": 1200, "margin": "10px auto"}),

    dbc.Row([
        dbc.Col(dcc.Graph(id="gann-chart", style={"height": "75vh"},
                          config={"modeBarButtonsToAdd": ["drawline", "eraseshape"],
                                  "displaylogo": False}), width=8),
        dbc.Col([
            html.H5("📐 سطوح کلیدی حمایت و مقاومت (Gann Square)", style={"color": GOLD, "fontSize": 14, "margin": "8px 0"}),
            html.Div(id="gann-panel"),
        ], width=4),
    ], style={"maxWidth": 1200, "margin": "0 auto"}),

    dcc.Store(id="shapes-store", data=[]),
    dcc.Interval(id="refresh-interval", interval=15_000, n_intervals=0),
], style={"background": BG, "minHeight": "100vh", "padding": "10px"})

# ==============================================================================
# 4) کال‌بک اصلی
# ==============================================================================
@app.callback(
    Output("gann-chart", "figure"),
    Output("shapes-store", "data"),
    Output("gann-panel", "children"),
    Output("conn-status", "children"),
    Input("refresh-interval", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    Input("gann-chart", "relayoutData"),
    State("symbol-input", "value"),
    State("interval-dropdown", "value"),
    State("category-dropdown", "value"),
    State("shapes-store", "data"),
)
def update_gann_chart(n_int, n_refresh, relayout, symbol, interval, category, stored_shapes):
    trigger = ctx.triggered_id
    stored_shapes = list(stored_shapes or [])

    # حفظ ترندلاین‌های کاربر
    if trigger == "gann-chart" and relayout:
        if "shapes" in relayout:
            stored_shapes = relayout["shapes"]
        else:
            # جابجایی نقطه خط (drag)
            for key, val in relayout.items():
                if key.startswith("shapes[") and "." in key:
                    try:
                        idx = int(key.split("[")[1].split("]")[0])
                        field = key.split(".", 1)[1]
                        if idx < len(stored_shapes):
                            stored_shapes[idx][field] = val
                    except:
                        pass

    symbol = (symbol or DEFAULT_SYMBOL).upper()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL

    df = get_klines(symbol, interval, category, limit=500)

    if df.empty:
        empty_fig = go.Figure(layout=dict(
            paper_bgcolor=BG, plot_bgcolor=CARD,
            annotations=[dict(text="❌ دریافت دیتا از بایبیت ناموفق بود.", x=0.5, y=0.5, showarrow=False,
                               font=dict(color=DN, size=14))]))
        return empty_fig, stored_shapes, dash.no_update, "🔴 قطع"

    current_price = df['close'].iloc[-1]

    # تولید ماتریس Gann Square دینامیک
    gann_shapes = generate_gann_shapes(df, current_price, interval, layers=3)

    all_shapes = gann_shapes + stored_shapes

    # چارت
    fig = go.Figure(data=[go.Candlestick(
        x=df["ts"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color=UP, decreasing_line_color=DN,
    )])

    fig.update_layout(
        shapes=all_shapes,
        dragmode="drawline",
        newshape=dict(line_color=GOLD, line_width=2.5),
        template="plotly_dark",
        paper_bgcolor=BG, plot_bgcolor=CARD,
        font=dict(color=TXT),
        xaxis=dict(gridcolor=LINE, rangeslider_visible=False),
        yaxis=dict(gridcolor=LINE),
        margin=dict(l=10, r=10, t=40, b=10),
        title=dict(text=f"{symbol} — {category} — {interval} | 🌙 Quantum Gann Square Dynamic v11", 
                   x=0.5, font=dict(color=GOLD, size=16)),
    )

    # پنل نمایش سطوح کلیدی
    panel = html.Div([
        html.H6(f"قیمت فعلی: {current_price:,.2f} USDT", style={"color": GOLD, "marginBottom": 15}),
        html.Div("سطوح کلیدی حمایت و مقاومت استاتیک:", style={"color": MUT, "fontSize": 12, "marginBottom": 8}),
        *[
            html.Div(f"🟡 سطح {k}: {y:,.2f}", style={"color": GOLD, "fontSize": 13, "marginBottom": 4})
            for k, y in enumerate([current_price * m for m in [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]], 1)
        ],
        html.Div("لایه‌های Gann (زمان + قیمت + دیاگونال)", style={"color": MUT, "fontSize": 12, "marginTop": 12}),
    ], style={"background": CARD, "padding": "15px", "borderRadius": "8px", "border": f"1px solid {LINE}"})

    status = f"🟢 متصل | {pd.Timestamp.now().strftime('%H:%M:%S')}"

    return fig, stored_shapes, panel, status

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8060, use_reloader=False)
