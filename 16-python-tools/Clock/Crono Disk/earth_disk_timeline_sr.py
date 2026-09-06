# -*- coding: utf-8 -*-
"""
💿 Earth-Disk Timeline Predictor + Precision Support/Resistance Engine
سازگار با: Dash 2.x | Python 3.13 | Bybit REST API v5
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
# 0) پالت رنگی و تنظیمات پیش‌فرض (تم دیسک و فضا)
# ==============================================================================
BG = "#070b14"
CARD = "#0f1830"
CARD2 = "#101c38"
LINE = "#22304e"
TXT = "#eef2fb"
MUT = "#8ea0c4"
GOLD = "#f3ba2f"
GOLD_DIM = "#8a6b1f"
UP = "#1fd7a6"
DN = "#ff5d6c"
BLUE = "#4f8dfd"
PURPLE = "#b57bf0"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_INTERVAL = "15"
FONT_FAMILY = "Vazirmatn, Tahoma, Arial, sans-serif"

# ==============================================================================
# 1) REST پایدار بایبیت
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
            if r.status_code in (403, 451): continue
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
        if nano: return datetime.fromtimestamp(int(nano) / 1e9, tz=timezone.utc)
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


def get_klines(symbol, interval, category="linear", limit=1000):
    d = bybit_get("/v5/market/kline", {
        "category": category, "symbol": symbol, "interval": interval, "limit": limit,
    })
    if not d or "list" not in (d.get("result") or {}): return pd.DataFrame()
    lst = d["result"]["list"]
    if not lst: return pd.DataFrame()
    df = pd.DataFrame(lst, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
    for c in ["open", "high", "low", "close", "volume"]: df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)


def get_interval_minutes(interval):
    s = str(interval).strip().lower()
    if s == "d": return 1440
    try:
        return int(s)
    except Exception:
        return 15


# ==============================================================================
# 2) موتور تحلیل دیسک زمین (Earth-Disk Timeline Engine)
# ==============================================================================
def analyze_earth_cycles(df, interval_min, forecast_hours=24):
    closes = df['close'].values
    n = len(closes)
    if n < 30: return None, []

    x = np.arange(n)
    p = np.polyfit(x, closes, 1)
    trend = np.polyval(p, x)
    y_detrend = closes - trend

    win = np.hanning(n)
    fft = np.fft.fft(y_detrend * win)
    freqs = np.fft.fftfreq(n, d=1)
    mags = np.abs(fft)
    mags[0] = 0

    top_k = 5
    top_idx = np.argsort(mags)[::-1][:top_k]

    steps = int((forecast_hours * 60) / interval_min)
    t_ext = np.arange(n, n + steps)
    trend_ext = np.polyval(p, t_ext)
    cyc_ext = np.zeros(steps)
    win_sum = np.sum(win)

    for idx in top_idx:
        if idx == 0: continue
        freq = freqs[idx]
        amp = 2.0 * mags[idx] / win_sum
        phase = np.angle(fft[idx])
        cyc_ext += amp * np.cos(2 * np.pi * freq * t_ext + phase)

    expected_path = trend_ext + cyc_ext

    diffs = np.diff(expected_path)
    signs = np.sign(diffs)
    signs[signs == 0] = 1
    crossings = np.where(signs[:-1] != signs[1:])[0] + 1

    last_ts = pd.Timestamp(df.iloc[-1]["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)
    turning_points = []

    for idx in crossings:
        idx_int = int(idx)
        t_future = last_ts + timedelta(minutes=interval_min * idx_int)
        price = expected_path[idx_int]

        is_peak = False
        if 0 < idx_int < len(expected_path) - 1:
            is_peak = expected_path[idx_int] > expected_path[idx_int - 1] and expected_path[idx_int] > expected_path[idx_int + 1]
        elif idx_int > 0:
            is_peak = expected_path[idx_int] > expected_path[idx_int - 1]

        turning_points.append({
            'time': t_future,
            'price': float(price),
            'type': 'قله (Peak)' if is_peak else 'کف (Trough)'
        })

    return expected_path, turning_points


def calculate_cycle_strength(df):
    closes = df['close'].values
    n = len(closes)
    if n < 20: return 0.0
    x = np.arange(n)
    p = np.polyfit(x, closes, 1)
    y_detrend = closes - np.polyval(p, x)
    win = np.hanning(n)
    fft = np.fft.fft(y_detrend * win)
    mags = np.abs(fft)
    mags[0] = 0
    top_k = 5
    top_idx = np.argsort(mags)[::-1][:top_k]
    total_power = np.sum(mags[: n // 2] ** 2)
    top_power = np.sum(mags[top_idx] ** 2)
    strength = float((top_power / total_power) * 100) if total_power > 0 else 0.0
    return min(strength, 100.0)


# ==============================================================================
# 2.5) موتور دقیق حمایت / مقاومت (Precision Support & Resistance Engine)
#      روش: پیوت‌های فرکتالی + پروفایل حجم + پیوت‌های کلاسیک + خوشه‌بندی
#      + اعتبارسنجی برخورد واقعی روی داده تاریخی (Reliability Backtest)
# ==============================================================================
def compute_atr(df, period=14):
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    n = len(df)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    return pd.Series(tr).rolling(period, min_periods=1).mean().values


def detect_fractal_pivots(df, left=3, right=3):
    highs = df['high'].values
    lows = df['low'].values
    n = len(df)
    pivot_highs, pivot_lows = [], []
    for i in range(left, n - right):
        wh = highs[i - left:i + right + 1]
        if highs[i] == wh.max() and np.argmax(wh) == left:
            pivot_highs.append((i, highs[i]))
        wl = lows[i - left:i + right + 1]
        if lows[i] == wl.min() and np.argmin(wl) == left:
            pivot_lows.append((i, lows[i]))
    return pivot_highs, pivot_lows


def build_volume_profile(df, bins=50):
    prices = df['close'].values
    volumes = df['volume'].values
    lo, hi = prices.min(), prices.max()
    if hi <= lo: return np.array([]), np.array([])
    edges = np.linspace(lo, hi, bins + 1)
    hist = np.zeros(bins)
    idx = np.clip(np.digitize(prices, edges) - 1, 0, bins - 1)
    for i, v in zip(idx, volumes):
        hist[i] += v
    centers = (edges[:-1] + edges[1:]) / 2
    return centers, hist


def find_volume_nodes(centers, hist, top_k=8):
    if len(hist) == 0: return []
    order = np.argsort(hist)[::-1][:top_k]
    total = hist.sum()
    return [{'price': float(centers[i]), 'volume_share': float(hist[i] / total * 100) if total > 0 else 0.0}
            for i in order]


def classic_pivot_levels(df, lookback=96):
    seg = df.tail(lookback)
    if seg.empty: return []
    H, L, C = seg['high'].max(), seg['low'].min(), seg['close'].iloc[-1]
    P = (H + L + C) / 3
    R1, S1 = 2 * P - L, 2 * P - H
    R2, S2 = P + (H - L), P - (H - L)
    R3, S3 = H + 2 * (P - L), L - 2 * (H - P)
    return [{'price': p, 'weight': 0.8, 'kind': 'classic_pivot'} for p in [P, R1, R2, R3, S1, S2, S3]]


def cluster_levels(levels, tolerance):
    if not levels: return []
    levels_sorted = sorted(levels, key=lambda x: x['price'])
    clusters, current = [], [levels_sorted[0]]
    for lv in levels_sorted[1:]:
        if lv['price'] - current[-1]['price'] <= tolerance:
            current.append(lv)
        else:
            clusters.append(current)
            current = [lv]
    clusters.append(current)

    result = []
    for c in clusters:
        total_w = sum(x['weight'] for x in c)
        wavg_price = (sum(x['price'] * x['weight'] for x in c) / total_w) if total_w > 0 else np.mean([x['price'] for x in c])
        result.append({'price': float(wavg_price), 'weight': float(total_w),
                        'has_pivot': any(x.get('kind') in ('pivot_high', 'pivot_low') for x in c)})
    return result


def validate_level_reliability(df, level_price, tolerance):
    """شمارش برخوردهای واقعی قیمت با سطح و درصد واکنش (بازگشت) واقعی به آن روی داده تاریخی."""
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    n = len(df)
    touches, bounces = 0, 0
    i = 0
    while i < n:
        near = (lows[i] - tolerance <= level_price <= highs[i] + tolerance)
        if near:
            touches += 1
            future = closes[i + 1:i + 4]
            if len(future) > 0:
                if level_price >= closes[i]:
                    if future.min() < closes[i] - tolerance * 0.3:
                        bounces += 1
                else:
                    if future.max() > closes[i] + tolerance * 0.3:
                        bounces += 1
            i += 3  # جلوگیری از شمارش چندباره‌ی یک برخورد پیوسته
        else:
            i += 1
    reliability = (bounces / touches * 100) if touches > 0 else 0.0
    return touches, round(reliability, 1)


def find_support_resistance(df, num_levels=5):
    n = len(df)
    if n < 30: return [], []

    atr = compute_atr(df, 14)
    current_atr = atr[-1] if len(atr) and atr[-1] > 0 else (df['high'].max() - df['low'].min()) / 20
    current_price = float(df['close'].iloc[-1])
    tolerance = max(current_atr * 0.35, current_price * 0.0015)

    pivot_highs, pivot_lows = detect_fractal_pivots(df, 3, 3)
    avg_vol = df['volume'].mean() if df['volume'].mean() > 0 else 1.0
    now_idx = n - 1

    levels = []
    for i, price in pivot_highs:
        recency = math.exp(-(now_idx - i) / max(n * 0.5, 1))
        vol_w = df['volume'].iloc[i] / avg_vol
        weight = (0.5 + recency) * (0.5 + min(vol_w, 3.0))
        levels.append({'price': float(price), 'weight': weight, 'kind': 'pivot_high'})
    for i, price in pivot_lows:
        recency = math.exp(-(now_idx - i) / max(n * 0.5, 1))
        vol_w = df['volume'].iloc[i] / avg_vol
        weight = (0.5 + recency) * (0.5 + min(vol_w, 3.0))
        levels.append({'price': float(price), 'weight': weight, 'kind': 'pivot_low'})

    levels.extend(classic_pivot_levels(df))

    clustered = cluster_levels(levels, tolerance)

    centers, hist = build_volume_profile(df, bins=50)
    vol_nodes = find_volume_nodes(centers, hist, top_k=8)
    for cl in clustered:
        cl['confluence'] = False
        for node in vol_nodes:
            if abs(cl['price'] - node['price']) <= tolerance * 1.5:
                cl['weight'] *= (1.0 + node['volume_share'] / 100.0 * 2.0)
                cl['confluence'] = True

    if not clustered: return [], []
    max_w = max(c['weight'] for c in clustered)

    for cl in clustered:
        weight_score = (cl['weight'] / max_w * 100) if max_w > 0 else 0.0
        touches, reliability = validate_level_reliability(df, cl['price'], tolerance)
        cl['touches'] = touches
        cl['reliability'] = reliability
        cl['score'] = round(0.55 * weight_score + 0.45 * reliability, 1) if touches > 0 else round(weight_score * 0.85, 1)
        cl['type'] = 'support' if cl['price'] < current_price else 'resistance'
        cl['distance_pct'] = round((cl['price'] - current_price) / current_price * 100, 2)

    supports = sorted([c for c in clustered if c['type'] == 'support'], key=lambda x: -x['score'])[:num_levels]
    resistances = sorted([c for c in clustered if c['type'] == 'resistance'], key=lambda x: -x['score'])[:num_levels]

    supports = sorted(supports, key=lambda x: -x['price'])          # نزدیک‌ترین حمایت اول
    resistances = sorted(resistances, key=lambda x: x['price'])     # نزدیک‌ترین مقاومت اول

    return supports, resistances


# ==============================================================================
# 3) ترسیم دیسک CD (نمودار قطبی) + حلقه‌های حمایت/مقاومت
# ==============================================================================
def build_cd_figure(df, expected_path, turning_points, supports, resistances, now_utc, symbol, interval):
    interval_min = get_interval_minutes(interval)
    steps = len(expected_path)
    last_ts = pd.Timestamp(df.iloc[-1]["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)

    def get_theta(dt):
        minutes = dt.hour * 60 + dt.minute
        return (minutes / 1440) * 360

    R0 = 1.0

    # محدوده قیمتی ترکیبی: مسیر پیش‌بینی‌شده + سطوح حمایت/مقاومت (برای مقیاس صحیح شعاع)
    all_prices = list(expected_path)
    all_prices += [s['price'] for s in supports] + [r['price'] for r in resistances]
    min_p, max_p = float(np.min(all_prices)), float(np.max(all_prices))
    p_range = max_p - min_p if max_p > min_p else 1.0

    def price_to_r(price):
        return R0 + 0.2 * (price - (min_p + max_p) / 2) / (p_range / 2)

    r_groove = price_to_r(expected_path)

    thetas = [get_theta(last_ts + timedelta(minutes=interval_min * (s + 1))) for s in range(steps)]

    fig = go.Figure()

    for r in np.linspace(0.4, 1.6, 15):
        fig.add_trace(go.Scatterpolar(
            r=[r] * 361, theta=np.linspace(0, 360, 361),
            mode='lines', line=dict(color='#1a233a', width=1),
            opacity=0.4, hoverinfo='skip', showlegend=False
        ))

    # حلقه‌های حمایت (سبز) و مقاومت (قرمز) - ضخامت و شفافیت بر اساس امتیاز دقت
    for s in supports:
        r_val = price_to_r(s['price'])
        fig.add_trace(go.Scatterpolar(
            r=[r_val] * 361, theta=np.linspace(0, 360, 361), mode='lines',
            line=dict(color=UP, width=1 + s['score'] / 100 * 3.5, dash='dot'),
            opacity=0.30 + s['score'] / 100 * 0.55,
            name=f"حمایت {s['price']:,.1f} ({s['score']:.0f}%)",
            hoverinfo='name', showlegend=True
        ))
    for r_lvl in resistances:
        r_val = price_to_r(r_lvl['price'])
        fig.add_trace(go.Scatterpolar(
            r=[r_val] * 361, theta=np.linspace(0, 360, 361), mode='lines',
            line=dict(color=DN, width=1 + r_lvl['score'] / 100 * 3.5, dash='dot'),
            opacity=0.30 + r_lvl['score'] / 100 * 0.55,
            name=f"مقاومت {r_lvl['price']:,.1f} ({r_lvl['score']:.0f}%)",
            hoverinfo='name', showlegend=True
        ))

    fig.add_trace(go.Scatterpolar(
        r=r_groove, theta=thetas,
        mode='lines', line=dict(color=GOLD, width=2.5),
        name='شیار خط زمانی امروز',
        hovertemplate='زمان: %{text}<br>قیمت: %{r:.2f}<extra></extra>',
        text=[(last_ts + timedelta(minutes=interval_min * (s + 1))).strftime('%H:%M') for s in range(steps)]
    ))

    if turning_points:
        tp_thetas = [get_theta(tp['time']) for tp in turning_points]
        tp_prices = [tp['price'] for tp in turning_points]
        tp_r = [price_to_r(p) for p in tp_prices]
        tp_colors = [UP if tp['type'] == 'قله (Peak)' else DN for tp in turning_points]
        tp_symbols = ['diamond' if tp['type'] == 'قله (Peak)' else 'square' for tp in turning_points]

        fig.add_trace(go.Scatterpolar(
            r=tp_r, theta=tp_thetas,
            mode='markers+text',
            marker=dict(size=14, color=tp_colors, symbol=tp_symbols, line=dict(width=1.5, color='white')),
            text=[tp['type'] for tp in turning_points],
            textposition='top center',
            textfont=dict(size=10, color=TXT, family=FONT_FAMILY),
            name='نقاط چرخش قطعی',
            hovertemplate='%{text}<br>زمان: %{customdata}<br>قیمت: %{r:.2f}<extra></extra>',
            customdata=[tp['time'].strftime('%H:%M') for tp in turning_points]
        ))

    now_theta = get_theta(now_utc)
    fig.add_trace(go.Scatterpolar(
        r=[0, 1.6], theta=[now_theta, now_theta],
        mode='lines', line=dict(color=DN, width=3, dash='dash'),
        name='سوزن لیزر (اکنون)', opacity=0.8
    ))

    fig.add_trace(go.Scatterpolar(r=[0.05], theta=[0], mode='markers', marker=dict(size=30, color=GOLD), opacity=0.3,
                                  showlegend=False))
    fig.add_trace(
        go.Scatterpolar(r=[0.02], theta=[0], mode='markers', marker=dict(size=15, color="white"), showlegend=False))

    fig.update_layout(
        polar=dict(
            bgcolor=BG,
            radialaxis=dict(visible=False, range=[0, 1.8]),
            angularaxis=dict(
                visible=True, direction="clockwise", rotation=90,
                tickmode='array',
                tickvals=[0, 90, 180, 270],
                ticktext=['00:00', '06:00', '12:00', '18:00'],
                tickfont=dict(color=MUT, size=13, family=FONT_FAMILY)
            )
        ),
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT_FAMILY, color=TXT),
        showlegend=True,
        legend=dict(bgcolor='rgba(15,24,48,0.8)', bordercolor=LINE, borderwidth=1, font=dict(size=10)),
        margin=dict(l=40, r=40, t=60, b=40),
        title=dict(text=f"💿 Earth-Disk Timeline: {symbol} | {interval}m", x=0.5,
                   font=dict(color=GOLD, size=18, family=FONT_FAMILY))
    )
    return fig


def empty_fig(msg):
    fig = go.Figure()
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG)
    fig.add_annotation(x=0.5, y=0.5, xref="paper", yref="paper", text=msg, showarrow=False,
                       font=dict(size=16, color=DN, family=FONT_FAMILY))
    return fig


# ==============================================================================
# 4) رابط کاربری Dash
# ==============================================================================
FONT_URL = "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;800&display=swap"

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG, FONT_URL],
    suppress_callback_exceptions=True
)
app.title = "Earth-Disk Timeline"
server = app.server

app.index_string = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            body { background: #070b14; direction: rtl; }
            * { font-family: 'Vazirmatn', Tahoma, Arial, sans-serif !important; }
            .glass-card {
                background: linear-gradient(145deg, rgba(16,28,56,0.85), rgba(10,17,35,0.85));
                border: 1px solid #22304e; border-radius: 16px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.35); backdrop-filter: blur(6px);
            }
            .stat-value { font-weight: 800; font-size: 20px; }
            .stat-label { font-size: 11px; color: #8ea0c4; }
            .Select-control, .dash-dropdown .Select-control {
                background-color: #101c38 !important; border-color: #22304e !important; color: #eef2fb !important;
            }
            .Select-value-label { color: #eef2fb !important; }
            table { border-collapse: separate; border-spacing: 0 8px; width: 100%; }
            th { padding: 10px; font-weight: 600; color: #8ea0c4; font-size: 12px; text-align: center; }
            td { padding: 12px; text-align: center; background: rgba(34, 48, 78, 0.3); border-top: 1px solid #22304e; border-bottom: 1px solid #22304e; }
            td:first-child { border-right: 1px solid #22304e; border-top-right-radius: 8px; border-bottom-right-radius: 8px; }
            td:last-child { border-left: 1px solid #22304e; border-top-left-radius: 8px; border-bottom-left-radius: 8px; }
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

INTERVAL_OPTS = [{"label": lbl, "value": val} for lbl, val in [
    ("1m", "1"), ("5m", "5"), ("15m", "15"), ("30m", "30"), ("1h", "60"), ("4h", "240"),
]]


def stat_card(id_prefix, label, color=TXT):
    return dbc.Col(
        html.Div([
            html.Div(label, className="stat-label"),
            html.Div("—", id=f"{id_prefix}-value", className="stat-value", style={"color": color}),
        ], className="glass-card", style={"padding": "12px 16px", "textAlign": "center"}),
        md=True, xs=12, style={"marginBottom": 10},
    )


def create_turning_points_table(turning_points):
    if not turning_points:
        return html.Div("نقطه چرخشی یافت نشد.", style={"color": MUT, "textAlign": "center", "padding": "20px"})
    rows = []
    for tp in turning_points[:8]:
        color = UP if tp['type'] == 'قله (Peak)' else DN
        rows.append(html.Tr([
            html.Td(tp['time'].strftime('%H:%M')),
            html.Td(f"{tp['price']:,.2f}", style={"color": GOLD}),
            html.Td(tp['type'], style={"color": color, "fontWeight": "bold"})
        ]))
    return html.Table([
        html.Thead(html.Tr([html.Th("زمان (UTC)"), html.Th("قیمت هدف"), html.Th("نوع چرخش")])),
        html.Tbody(rows)
    ])


def create_sr_table(levels, kind="support"):
    if not levels:
        return html.Div("سطحی یافت نشد.", style={"color": MUT, "textAlign": "center", "padding": "20px"})
    color = UP if kind == "support" else DN
    rows = []
    for lv in levels:
        conf_icon = "✅" if lv.get('confluence') else "—"
        rows.append(html.Tr([
            html.Td(f"{lv['price']:,.2f}", style={"color": color, "fontWeight": "bold"}),
            html.Td(f"{lv['score']:.0f}%", style={"color": GOLD}),
            html.Td(f"{lv['reliability']:.0f}%"),
            html.Td(f"{lv['touches']}"),
            html.Td(f"{lv['distance_pct']:+.2f}%"),
            html.Td(conf_icon),
        ]))
    return html.Table([
        html.Thead(html.Tr([
            html.Th("قیمت"), html.Th("امتیاز"), html.Th("اطمینان"),
            html.Th("برخورد"), html.Th("فاصله"), html.Th("هم‌راستا با حجم")
        ])),
        html.Tbody(rows)
    ])


app.layout = html.Div([
    html.Div([
        html.H2("💿 Earth-Disk Timeline Predictor", style={"color": GOLD, "fontWeight": 800, "margin": 0}),
        html.P("ایده: زمین یک دیسک است. چرخش آن خط زمانی قطعی قیمت را انتخاب می‌کند (مانند شیارهای یک CD) — "
               "به‌همراه موتور دقیق حمایت/مقاومت مبتنی بر پیوت‌های فرکتالی، پروفایل حجم و اعتبارسنجی برخورد تاریخی.",
               style={"color": MUT, "fontSize": 13, "margin": "4px 0"})
    ], style={"textAlign": "center", "marginTop": 20}),

    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([
            html.Label("نماد", style={"color": MUT, "fontSize": 12}),
            dcc.Input(id="symbol", value=DEFAULT_SYMBOL, type="text", className="form-control",
                      style={"backgroundColor": CARD2, "color": TXT, "borderColor": LINE})
        ], md=3),
        dbc.Col([
            html.Label("تایم‌فریم", style={"color": MUT, "fontSize": 12}),
            dcc.Dropdown(id="interval", options=INTERVAL_OPTS, value=DEFAULT_INTERVAL, clearable=False,
                         style={"backgroundColor": CARD2, "color": TXT})
        ], md=3),
        dbc.Col([
            html.Label("افق پیش‌بینی (ساعت)", style={"color": MUT, "fontSize": 12}),
            dcc.Input(id="forecast_hours", value=24, type="number", min=6, max=72, className="form-control",
                      style={"backgroundColor": CARD2, "color": TXT, "borderColor": LINE})
        ], md=3),
        dbc.Col([
            html.Button("⚡ تحلیل دیسک زمین", id="btn-update", n_clicks=0,
                        style={"marginTop": 24, "backgroundColor": GOLD, "color": BG, "border": "none",
                               "borderRadius": 8, "padding": "8px 16px", "fontWeight": "bold", "width": "100%",
                               "cursor": "pointer"})
        ], md=3)
    ], align="center")), className="glass-card", style={"maxWidth": 1000, "margin": "20px auto"}),

    dbc.Row([
        dbc.Col([
            dcc.Graph(id="cd-graph", config={"displayModeBar": False}, style={"height": "600px"})
        ], md=8),
        dbc.Col([
            html.Div([
                html.H5("⏳ نقاط چرخش قطعی خط زمانی",
                        style={"color": GOLD, "textAlign": "center", "marginBottom": 15, "fontWeight": 800}),
                html.Div(id="turning-points-table")
            ], className="glass-card", style={"padding": 20, "height": "100%"})
        ], md=4)
    ], style={"maxWidth": 1200, "margin": "20px auto"}),

    dbc.Row([
        dbc.Col([
            html.Div([
                html.H5("🟢 دقیق‌ترین سطوح حمایت", style={"color": UP, "textAlign": "center", "marginBottom": 15, "fontWeight": 800}),
                html.Div(id="support-table")
            ], className="glass-card", style={"padding": 20})
        ], md=6),
        dbc.Col([
            html.Div([
                html.H5("🔴 دقیق‌ترین سطوح مقاومت", style={"color": DN, "textAlign": "center", "marginBottom": 15, "fontWeight": 800}),
                html.Div(id="resistance-table")
            ], className="glass-card", style={"padding": 20})
        ], md=6),
    ], style={"maxWidth": 1200, "margin": "10px auto"}),

    dbc.Row([
        stat_card("cycle-strength", "قدرت چرخه دیسک", GOLD),
        stat_card("current-phase", "فاز فعلی شیار", BLUE),
        stat_card("next-tp", "نزدیک‌ترین نقطه چرخش", UP),
        stat_card("nearest-support", "نزدیک‌ترین حمایت", UP),
        stat_card("nearest-resistance", "نزدیک‌ترین مقاومت", DN),
    ], style={"maxWidth": 1200, "margin": "10px auto"}),

    dcc.Interval(id="interval-component", interval=60 * 1000, n_intervals=0)
], style={"backgroundColor": BG, "minHeight": "100vh", "paddingBottom": 50})


# ==============================================================================
# 5) Callbacks
# ==============================================================================
@app.callback(
    [Output("cd-graph", "figure"),
     Output("turning-points-table", "children"),
     Output("support-table", "children"),
     Output("resistance-table", "children"),
     Output("cycle-strength-value", "children"),
     Output("current-phase-value", "children"),
     Output("next-tp-value", "children"),
     Output("nearest-support-value", "children"),
     Output("nearest-resistance-value", "children")],
    [Input("btn-update", "n_clicks"), Input("interval-component", "n_intervals")],
    [State("symbol", "value"), State("interval", "value"), State("forecast_hours", "value")]
)
def update_dashboard(n_clicks, n_intervals, symbol, interval, forecast_hours):
    symbol = symbol.upper().strip()
    if not symbol: symbol = DEFAULT_SYMBOL

    df = get_klines(symbol, interval)
    now_utc = get_server_time()

    if df.empty:
        empty = empty_fig("خطا در دریافت داده")
        return empty, html.Div("داده‌ای نیست"), html.Div("—"), html.Div("—"), "—", "—", "—", "—", "—"

    fh = forecast_hours if forecast_hours else 24
    expected_path, turning_points = analyze_earth_cycles(df, get_interval_minutes(interval), fh)

    if expected_path is None:
        empty = empty_fig("داده برای تحلیل چرخه کافی نیست")
        return empty, html.Div("—"), html.Div("—"), html.Div("—"), "—", "—", "—", "—", "—"

    supports, resistances = find_support_resistance(df, num_levels=5)

    fig = build_cd_figure(df, expected_path, turning_points, supports, resistances, now_utc, symbol, interval)
    tp_table = create_turning_points_table(turning_points)
    support_table = create_sr_table(supports, "support")
    resistance_table = create_sr_table(resistances, "resistance")

    strength = calculate_cycle_strength(df)

    current_phase = "—"
    if len(expected_path) > 0:
        current_price = float(df.iloc[-1]['close'])
        next_price = expected_path[0]
        current_phase = "📈 صعودی (شیار رو به بالا)" if next_price > current_price else "📉 نزولی (شیار رو به پایین)"

    next_tp_text = "—"
    if turning_points:
        nxt = turning_points[0]
        next_tp_text = f"{nxt['time'].strftime('%H:%M')} | {nxt['price']:,.2f}"

    nearest_support_text = f"{supports[0]['price']:,.2f} ({supports[0]['score']:.0f}%)" if supports else "—"
    nearest_resistance_text = f"{resistances[0]['price']:,.2f} ({resistances[0]['score']:.0f}%)" if resistances else "—"

    return (fig, tp_table, support_table, resistance_table,
            f"{strength:.1f}%", current_phase, next_tp_text,
            nearest_support_text, nearest_resistance_text)


if __name__ == "__main__":
    app.run(debug=True, port=8050, host='127.0.0.1')
