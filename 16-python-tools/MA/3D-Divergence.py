# -*- coding: utf-8 -*-
"""
📐 TRENDLINE ANGLE ANALYZER (FIXED)
"""

import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import requests
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# اتصال به Bybit
# ============================================================
REST = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})

def fetch(symbol, interval, limit=300):
    for base in REST:
        try:
            r = S.get(f"{base}/v5/market/kline", params={
                "category": "linear", "symbol": symbol,
                "interval": interval, "limit": limit
            }, timeout=10)
            d = r.json()
            if d.get("retCode") == 0 and d["result"]["list"]:
                df = pd.DataFrame(d["result"]["list"],
                    columns=["ts","open","high","low","close","volume","turnover"])
                df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
                for c in ["open","high","low","close"]:
                    df[c] = df[c].astype(float)
                return df.sort_values("ts").reset_index(drop=True)
        except Exception:
            continue
    return pd.DataFrame()

# ============================================================
# تبدیل مختصات x به عدد
# ============================================================
def x_to_num(x):
    if isinstance(x, (int, float, np.number)):
        return float(x)
    try:
        return pd.to_datetime(x).timestamp() * 1000
    except Exception:
        return float(x)

# ============================================================
# محاسبه زاویه ترندلاین در فضای نرمال‌شده
# ============================================================
def trendline_angle(x0, y0, x1, y1, t_range, p_range):
    t_span = (t_range[1] - t_range[0]) or 1
    p_span = (p_range[1] - p_range[0]) or 1
    nx0 = (x0 - t_range[0]) / t_span
    ny0 = (y0 - p_range[0]) / p_span
    nx1 = (x1 - t_range[0]) / t_span
    ny1 = (y1 - p_range[0]) / p_span
    dx = nx1 - nx0
    dy = ny1 - ny0
    return np.degrees(np.arctan2(dy, dx))

# ============================================================
# چرخش قیمت حول نقطه شروع ترندلاین
# ============================================================
def rotate_price(times_ms, prices, angle_deg, pivot_t, pivot_p, t_range, p_range):
    t_span = (t_range[1] - t_range[0]) or 1
    p_span = (p_range[1] - p_range[0]) or 1

    tn = (times_ms - t_range[0]) / t_span
    pn = (prices   - p_range[0]) / p_span

    pt = (pivot_t - t_range[0]) / t_span
    pp = (pivot_p - p_range[0]) / p_span

    rad = np.radians(-angle_deg)
    c, s = np.cos(rad), np.sin(rad)

    dx = tn - pt
    dy = pn - pp
    t_rot = dx * c - dy * s + pt
    p_rot = dx * s + dy * c + pp

    return t_rot, p_rot

# ============================================================
# استخراج shapeها از relayoutData
# ============================================================
def parse_shapes(relayout_data, prev_shapes):
    shapes = [dict(s) for s in (prev_shapes or [])]
    if not relayout_data:
        return shapes

    if 'shapes' in relayout_data:
        return list(relayout_data['shapes'])

    updates = {}
    deletions = set()
    for key, val in relayout_data.items():
        if not key.startswith('shapes'):
            continue
        if key == 'shapes':
            return list(val)
        try:
            idx = int(key.split('[')[1].split(']')[0])
        except Exception:
            continue
        if '.' in key.split(']', 1)[1]:
            prop = key.split('].', 1)[1]
            updates.setdefault(idx, {})[prop] = val
        else:
            deletions.add(idx)

    max_idx = max(updates.keys()) if updates else -1
    while len(shapes) <= max_idx:
        shapes.append({})
    for idx, props in updates.items():
        shapes[idx].update(props)

    result = []
    for i, sh in enumerate(shapes):
        if i in deletions:
            continue
        if sh.get('type') == 'line' or 'x0' in sh:
            result.append(sh)
    return result

# ============================================================
# داش‌بورد
# ============================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])

app.layout = dbc.Container([

    # عنوان
    dbc.Row(
        dbc.Col(
            html.H1([
                "📐 Trendline Angle Analyzer",
                html.Br(),
                html.Small("ترندلاین بکشید → قیمت با زاویه آن رندر می‌شود",
                           className="text-info")
            ], className="text-center my-3 text-warning"),
            width=12
        )
    ),

    # کنترل‌ها
    dbc.Row([
        dbc.Col(dbc.Input(id="symbol", value="BTCUSDT"), md=2),
        dbc.Col(dbc.Select(id="interval", options=[
            {"label":"1m","value":"1"}, {"label":"5m","value":"5"},
            {"label":"15m","value":"15"}, {"label":"1H","value":"60"},
            {"label":"4H","value":"240"}, {"label":"1D","value":"D"}
        ], value="60"), md=2),
        dbc.Col(dbc.Button("📥 Load Data", id="btn-load",
                           color="warning", className="w-100"), md=2),
        dbc.Col(dbc.Button("🧹 Clear Lines", id="btn-clear",
                           color="secondary", className="w-100"), md=2),
        dbc.Col(html.Div(id="angle-info", className="pt-2"), md=4),
    ], className="mb-2"),

    # چارت اصلی برای رسم ترندلاین
    dbc.Row(
        dbc.Col(
            html.Div([
                html.P("✏️ با ماوس روی چارت ترندلاین بکشید (ابزار خط فعال است)",
                       className="text-success small mb-1"),
                dcc.Graph(id="main-chart", config={
                    'displaylogo': False,
                    'modeBarButtonsToAdd': ['drawline', 'eraseshape']
                }, style={"height": "450px"})
            ]),
            width=12
        )
    ),

    # نمودار چرخش‌یافته
    dbc.Row(
        dbc.Col(
            dcc.Graph(id="rotated-views", style={"height": "500px"}),
            width=12
        )
    ),

    dcc.Store(id='data-store'),
    dcc.Store(id='shapes-store'),

], fluid=True)

# ------------------------------------------------------------
# Callback 1: بارگذاری داده و رسم چارت اصلی
# ------------------------------------------------------------
@app.callback(
    Output('main-chart', 'figure'),
    Output('data-store', 'data'),
    Output('shapes-store', 'data'),
    Input('btn-load', 'n_clicks'),
    State('symbol', 'value'),
    State('interval', 'value'),
    prevent_initial_call=False
)
def load_data(n, symbol, interval):
    df = fetch(symbol, interval)
    if df.empty:
        empty = go.Figure().update_layout(title="❌ Data Error",
                                          template="plotly_dark")
        return empty, {}, []

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df["ts"], open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name="Price",
        increasing_line_color='#16a085',
        decreasing_line_color='#e74c3c'
    ))

    fig.update_layout(
        title=f"📈 {symbol} {interval} — ترندلاین بکشید",
        template="plotly_dark",
        dragmode='drawline',
        newshape=dict(line=dict(color='cyan', width=3)),
        xaxis_rangeslider_visible=False,
        yaxis=dict(title="Price"),
        xaxis=dict(title="Time"),
        margin=dict(l=40, r=20, t=60, b=30)
    )

    store = {
        "ts": df["ts"].astype(str).tolist(),
        "ts_ms": (df["ts"].astype(np.int64) // 10**6).tolist(),
        "open": df["open"].tolist(),
        "high": df["high"].tolist(),
        "low": df["low"].tolist(),
        "close": df["close"].tolist(),
    }
    return fig, store, []

# ------------------------------------------------------------
# Callback 2: پاک‌سازی ترندلاین‌ها
# ------------------------------------------------------------
@app.callback(
    Output('main-chart', 'figure'),
    Output('shapes-store', 'data'),
    Output('rotated-views', 'figure'),
    Output('angle-info', 'children'),
    Input('btn-clear', 'n_clicks'),
    State('main-chart', 'figure'),
    prevent_initial_call=True
)
def clear_lines(n, fig):
    if fig:
        fig['layout']['shapes'] = []
    empty_rot = go.Figure().update_layout(
        title="🌀 ترندلاین بکشید تا رندر زاویه‌ای نمایش داده شود",
        template="plotly_dark")
    return fig, [], empty_rot, ""

# ------------------------------------------------------------
# Callback 3: پردازش ترندلاین‌ها و رندر زاویه‌ای
# ------------------------------------------------------------
@app.callback(
    Output('rotated-views', 'figure'),
    Output('angle-info', 'children'),
    Output('shapes-store', 'data'),
    Input('main-chart', 'relayoutData'),
    State('data-store', 'data'),
    State('shapes-store', 'data'),
    prevent_initial_call=True
)
def on_draw(relayout_data, store, stored_shapes):
    if not store or not store.get("close"):
        return (go.Figure().update_layout(template="plotly_dark"),
                "", stored_shapes)

    shapes = parse_shapes(relayout_data, stored_shapes)
    lines = [s for s in shapes if s.get('type') == 'line'
             and all(k in s for k in ('x0','y0','x1','y1'))]

    if not lines:
        empty = go.Figure().update_layout(
            title="🌀 ترندلاین بکشید تا رندر زاویه‌ای نمایش داده شود",
            template="plotly_dark")
        return empty, "", shapes

    ts_ms = np.array(store["ts_ms"], dtype=float)
    prices = np.array(store["close"], dtype=float)
    t_range = [ts_ms.min(), ts_ms.max()]
    p_range = [prices.min(), prices.max()]

    n = len(lines)
    fig = make_subplots(
        rows=n, cols=1,
        subplot_titles=[f"ترندلاین #{i+1}" for i in range(n)],
        vertical_spacing=0.12
    )

    info_badges = []

    for i, ln in enumerate(lines):
        x0 = x_to_num(ln['x0']); y0 = float(ln['y0'])
        x1 = x_to_num(ln['x1']); y1 = float(ln['y1'])

        angle = trendline_angle(x0, y0, x1, y1, t_range, p_range)
        t_rot, p_rot = rotate_price(ts_ms, prices, angle,
                                    x0, y0, t_range, p_range)

        fig.add_trace(go.Scatter(
            x=t_rot, y=p_rot, mode='lines',
            line=dict(color='#f0b90b', width=1.5),
            name=f"Rotated {angle:.1f}°",
            showlegend=False
        ), row=i+1, col=1)

        p_span = (p_range[1]-p_range[0]) or 1
        pivot_pn = (y0 - p_range[0]) / p_span
        fig.add_hline(y=pivot_pn, line_dash="dash", line_color="cyan",
                      line_width=2, row=i+1, col=1)

        fig.update_xaxes(title_text="Rotated Time (norm)", row=i+1, col=1)
        fig.update_yaxes(title_text="Rotated Price (norm)", row=i+1, col=1)

        direction = "صعودی ⬆" if angle > 0 else "نزولی ⬇" if angle < 0 else "خنثی ➡"
        info_badges.append(
            dbc.Badge(f"#{i+1}: {angle:.1f}° ({direction})",
                      color="info", className="me-2")
        )

    fig.update_layout(
        title="🌀 رندر قیمت در زاویه هر ترندلاین (خط‌چین = ترندلاین مرجع افقی)",
        template="plotly_dark",
        height=250 * n + 100,
        margin=dict(l=50, r=20, t=80, b=30)
    )

    return fig, info_badges, shapes

if __name__ == "__main__":
    print("📐 http://127.0.0.1:8050")
    app.run(debug=True, port=8050, host="127.0.0.1")