# -*- coding: utf-8 -*-
"""
🌀 ChronoGann Dynamic Square — سیستم مربع گن دینامیک لایه‌ای
------------------------------------------------------------------
ایده‌ی هسته‌ای این سیستم (نسخه‌ی نوینِ مربع گن، نه پیاده‌سازی کلاسیک ثابت):

۱) لنگر (Anchor) به‌صورت خودکار و پویا از روی آخرین «پیوت فرکتال معتبر»
   (سقف/کف چرخشی تأییدشده) روی چارت واقعی بایبیت انتخاب می‌شود — نه یک
   عدد دلخواه ثابت. یعنی مرکز مربع گن با ساختار واقعی قیمت هم‌گام است.

۲) «گام رشد مارپیچ» (increment) ثابت نیست؛ بر اساس نسبت ATR فعلی به
   میانه‌ی ATR اخیر (رژیم نوسان) تعدیل می‌شود. در نوسان بالا مربع باز
   می‌شود (لایه‌ها دورتر از هم)، در نوسان کم جمع می‌شود (لایه‌ها نزدیک‌تر).
   این همان «متغیر بودنِ هم‌گام با تغییرات قیمت» است.

۳) ماتریس کاملاً لایه‌ای (Ring-based) است: هر لایه یک دور کامل چرخش
   مربع ریشه‌ی گن (Square-Root spiral) را نمایندگی می‌کند و در هر لایه
   ۸ گرهِ زاویه‌ای (۴ محور اصلی کاردینال + ۴ محور مورب دیاگونال) در دو
   جهت صعودی (بالقوه مقاومت) و نزولی (بالقوه حمایت) نسبت به لنگر
   محاسبه می‌شود.

۴) «کشف حمایت/مقاومت کلیدی استاتیک»: هر سطح تولیدشده توسط ماتریس، در
   برابر دیتای واقعی تاریخی (برخورد high/low در بازه‌ی تلورانس) امتیاز
   می‌گیرد. فقط سطوحی که واقعاً چند بار قیمت را برگردانده‌اند به‌عنوان
   سطح «کلیدی» با ضخامت/درخشندگی بیشتر نمایش داده می‌شوند.

۵) به‌علاوه، بادبزن زمانی-قیمتی گن (Gann Fan) از همان لنگر، با واحد
   قیمت-به-کندل مبتنی بر ATR (نه یک واحد دلخواه) رسم می‌شود.

۶) یک پنل «چرخ ماتریس» (Polar Wheel) جداگانه، خودِ ساختار لایه‌ای مربع
   گن و موقعیت لحظه‌ای قیمت داخل مارپیچ را به‌صورت بصری دقیق نشان می‌دهد.

⚠️ نکته‌ی صادقانه: امتیاز «برخورد» (touches) یک پروکسیِ آماریِ ساده
(شمارش برخورد) است، نه یک تست معناداری آماری کامل (مثل پرموتیشن‌تست).
برای اثبات ادج واقعی، باید مثل روال همیشگی، روی دیتای بزرگ و با
پرموتیشن‌تست/واک‌فوروارد جداگانه اعتبارسنجی شود. این ابزار فقط سطوح
کاندید را کشف و رتبه‌بندی می‌کند.

اتصال به بایبیت دقیقاً به روش پایدار اسکریپت مرجع (چند دامنه + کش
دامنه‌ی فعال + هدر مرورگر) است.

نصب:
pip install dash dash-bootstrap-components plotly pandas numpy requests
"""

import numpy as np
import pandas as pd
import requests
import dash
from dash import dcc, html, Input, Output, State, ctx
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

# ==============================================================================
# 0) پالت رنگی تیره (هماهنگ با اسکریپت‌های خانواده‌ی Morindok / BITMOON)
# ==============================================================================
BG, CARD, LINE, TXT, MUT = "#0b1220", "#121c30", "#23314d", "#e8ecf4", "#8fa3c0"
GOLD, UP, DN = "#f0b90b", "#16a085", "#e74c3c"
CYAN, PURPLE, ORANGE = "#22d3ee", "#a78bfa", "#fb923c"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_CATEGORY = "linear"
DEFAULT_INTERVAL = "15"

# ==============================================================================
# 1) اتصال REST پایدار به بایبیت — دقیقاً به روش اسکریپت مرجع
#    (چند دامنه جایگزین + کش دامنه فعال + هدر مرورگر برای عبور از فیلتر)
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
# 2) تشخیص پیوت فرکتال (لنگر پویا) + ATR
# ==============================================================================
def detect_pivots(df, left=5, right=5):
    """پیوت فرکتال تأییدشده: سقف/کفی که `right` کندل بعدش تأیید شده باشد."""
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)
    piv_high, piv_low = [], []
    for i in range(left, n - right):
        wh = highs[i - left:i + right + 1]
        wl = lows[i - left:i + right + 1]
        if highs[i] == wh.max() and np.argmax(wh) == left:
            piv_high.append(i)
        if lows[i] == wl.min() and np.argmin(wl) == left:
            piv_low.append(i)
    return piv_high, piv_low


def select_anchor(df, piv_high, piv_low):
    """
    انتخاب جدیدترین پیوت معتبر (سقف یا کف) به‌عنوان مرکز مربع گن.
    مرکز همیشه آخرین ساختار چرخشیِ تأییدشده‌ی قیمت است، نه عدد دلخواه.
    """
    cands = []
    if piv_high:
        i = piv_high[-1]
        cands.append((i, df["ts"].iloc[i], float(df["high"].iloc[i]), "high"))
    if piv_low:
        i = piv_low[-1]
        cands.append((i, df["ts"].iloc[i], float(df["low"].iloc[i]), "low"))
    if not cands:
        i = max(len(df) // 2, 0)
        return i, df["ts"].iloc[i], float(df["close"].iloc[i]), "mid"
    cands.sort(key=lambda c: c[0])
    return cands[-1]


def atr_series(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def compute_dynamic_increment(df, base=2.0, period=14, lookback=100, sensitivity=1.0):
    """
    گام رشد مارپیچ را بر اساس رژیم نوسان (ATR فعلی نسبت به میانه‌ی اخیر)
    تعدیل می‌کند. sensitivity ضریب دستیِ کاربر برای تشدید/تلطیف اثر است.
    """
    a = atr_series(df, period).dropna()
    if a.empty:
        return base * sensitivity
    current_atr = a.iloc[-2] if len(a) > 1 else a.iloc[-1]  # کندل بسته‌شده آخر
    ref = a.iloc[-lookback:] if len(a) >= lookback else a
    median_atr = ref.median()
    if not median_atr or np.isnan(median_atr) or median_atr == 0:
        return base * sensitivity
    ratio = float(np.clip(current_atr / median_atr, 0.5, 2.5))
    return base * ratio * sensitivity


# ==============================================================================
# 3) ماتریس لایه‌ای مربع گن (ChronoGann Spiral Matrix)
# ==============================================================================
ANGLE_LABELS = ["0°", "45°", "90°", "135°", "180°", "225°", "270°", "315°"]
CARDINAL_IDX = {0, 2, 4, 6}


def build_chronogann_matrix(anchor_price, increment, n_rings=8):
    """
    برای هر لایه (ring)، ۸ گره زاویه‌ای در دو جهت صعودی (up_price) و
    نزولی (down_price) نسبت به sqrt(anchor) محاسبه می‌شود — روش
    ریشه‌ی مربع گن، اما با گام (increment) پویا به‌جای عدد ثابت کلاسیک ۲.
    """
    root_anchor = np.sqrt(max(anchor_price, 1e-9))
    step = increment / 8.0
    levels = []
    for ring in range(1, n_rings + 1):
        for a_idx in range(8):
            offset = ring * increment + a_idx * step
            up_root = root_anchor + offset
            down_root = root_anchor - offset
            up_price = up_root ** 2
            down_price = (down_root ** 2) if down_root > 0 else None
            is_card = a_idx in CARDINAL_IDX
            if up_price is not None:
                levels.append({"ring": ring, "angle_idx": a_idx, "angle": ANGLE_LABELS[a_idx],
                                "direction": "up", "is_cardinal": is_card, "price": float(up_price)})
            if down_price is not None:
                levels.append({"ring": ring, "angle_idx": a_idx, "angle": ANGLE_LABELS[a_idx],
                                "direction": "down", "is_cardinal": is_card, "price": float(down_price)})
    return levels


def score_confluence(df, levels, tolerance_pct=0.15, lookback=400):
    """امتیازدهی برخورد تاریخی هر سطح با high/low واقعی (کشف سطوح کلیدی)."""
    sub = df.iloc[-lookback:] if len(df) > lookback else df
    highs = sub["high"].to_numpy()
    lows = sub["low"].to_numpy()
    out = []
    for lv in levels:
        p = lv["price"]
        if p is None or p <= 0 or np.isnan(p):
            continue
        tol = p * tolerance_pct / 100.0
        touches = int(np.sum((np.abs(highs - p) <= tol) | (np.abs(lows - p) <= tol)))
        out.append({**lv, "touches": touches})
    return out


def current_price_spiral_position(current_price, anchor_price, increment):
    """موقعیت لحظه‌ای قیمت داخل مارپیچ (برای نمایش روی چرخ ماتریس)."""
    root_anchor = np.sqrt(max(anchor_price, 1e-9))
    root_diff = np.sqrt(max(current_price, 1e-9)) - root_anchor
    ring_float = root_diff / increment if increment else 0.0
    direction = "up" if ring_float >= 0 else "down"
    frac = abs(ring_float) % 1.0
    angle_deg = frac * 360.0
    r = abs(ring_float)
    return r, angle_deg, direction


# ==============================================================================
# 4) بادبزن زمانی-قیمتی گن (Gann Fan) — واحد قیمت/کندل مبتنی بر ATR
# ==============================================================================
FAN_RATIOS = [(1, 8), (1, 4), (1, 2), (1, 1), (2, 1), (4, 1), (8, 1)]


def build_gann_fan(df, anchor_idx, anchor_price, anchor_type, atr_val, forward_bars=30):
    if not atr_val or np.isnan(atr_val) or atr_val <= 0:
        return []
    n = len(df)
    x_end = min(n - 1 + forward_bars, n - 1 + forward_bars)
    fans = []
    sign = 1.0 if anchor_type != "high" else -1.0
    for num, den in FAN_RATIOS:
        slope = (num / den) * atr_val * sign
        x0_idx, x1_idx = anchor_idx, n - 1 + forward_bars
        y0 = anchor_price
        y1 = anchor_price + slope * (x1_idx - anchor_idx)
        fans.append({
            "label": f"{num}x{den}",
            "x0_idx": x0_idx, "x1_idx": x1_idx,
            "y0": y0, "y1": y1,
            "is_1x1": (num == den),
        })
    return fans


def idx_to_ts(df, idx):
    """ایندکس کندل را به timestamp نگاشت می‌دهد؛ برای ایندکس‌های آینده برون‌یابی می‌کند."""
    n = len(df)
    if idx < n:
        return df["ts"].iloc[idx]
    step = df["ts"].iloc[-1] - df["ts"].iloc[-2]
    return df["ts"].iloc[-1] + step * (idx - (n - 1))


# ==============================================================================
# 5) اپ Dash
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])
app.title = "ChronoGann Dynamic Square"
server = app.server

CATEGORY_OPTS = [{"label": v, "value": v} for v in ["linear", "spot", "inverse"]]
INTERVAL_OPTS = [{"label": lbl, "value": val} for lbl, val in [
    ("1m", "1"), ("3m", "3"), ("5m", "5"), ("15m", "15"),
    ("30m", "30"), ("1h", "60"), ("4h", "240"), ("1D", "D"),
]]

control_style = {"fontSize": 12, "color": MUT}

app.layout = html.Div([
    dbc.Card(dbc.CardBody([
        dbc.Row([
            dbc.Col([html.Label("نماد:", style=control_style),
                     dcc.Input(id="symbol-input", value=DEFAULT_SYMBOL, type="text",
                               style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
            dbc.Col([html.Label("بازار:", style=control_style),
                     dcc.Dropdown(id="category-dropdown", value=DEFAULT_CATEGORY, clearable=False, options=CATEGORY_OPTS)], md=2),
            dbc.Col([html.Label("تایم‌فریم:", style=control_style),
                     dcc.Dropdown(id="interval-dropdown", value=DEFAULT_INTERVAL, clearable=False, options=INTERVAL_OPTS)], md=2),
            dbc.Col([html.Label("تعداد لایه‌ها:", style=control_style),
                     dcc.Slider(id="rings-slider", min=3, max=14, step=1, value=8,
                                marks=None, tooltip={"placement": "bottom", "always_visible": True})], md=2),
            dbc.Col([html.Label("قدرت پیوت (چپ/راست):", style=control_style),
                     dcc.Slider(id="pivot-strength-slider", min=2, max=15, step=1, value=5,
                                marks=None, tooltip={"placement": "bottom", "always_visible": True})], md=2),
            dbc.Col([html.Label("حساسیت گام مارپیچ:", style=control_style),
                     dcc.Slider(id="sensitivity-slider", min=0.5, max=2.0, step=0.1, value=1.0,
                                marks=None, tooltip={"placement": "bottom", "always_visible": True})], md=2),
        ], className="mb-2"),
        dbc.Row([
            dbc.Col([html.Label("تلورانس برخورد سطح (٪):", style=control_style),
                     dcc.Slider(id="tolerance-slider", min=0.05, max=0.6, step=0.05, value=0.15,
                                marks=None, tooltip={"placement": "bottom", "always_visible": True})], md=3),
            dbc.Col(dbc.Checklist(
                id="show-fan-check",
                options=[{"label": " نمایش بادبزن زمانی گن (Gann Fan)", "value": "on"}],
                value=["on"], switch=True, style={"marginTop": 28, "color": MUT}
            ), md=3),
            dbc.Col(dbc.Button("🔄 بروزرسانی", id="refresh-btn", color="warning", className="mt-3",
                               style={"fontWeight": "bold", "color": "#0b1220", "width": "100%"}), md=2),
            dbc.Col(html.Div(id="conn-status", style={"color": MUT, "fontSize": 11, "marginTop": 30, "textAlign": "center"}), md=4),
        ]),
    ]), style={"maxWidth": 1400, "margin": "10px auto"}),

    dbc.Row([
        dbc.Col(dcc.Graph(id="main-chart", style={"height": "70vh"},
                          config={"displaylogo": False}), width=7),
        dbc.Col(dcc.Graph(id="wheel-chart", style={"height": "70vh"},
                          config={"displaylogo": False}), width=5),
    ], style={"maxWidth": 1400, "margin": "0 auto"}),

    dbc.Row([
        dbc.Col([
            html.H5("🎯 سطوح کلیدی حمایت/مقاومت کشف‌شده (بر اساس برخورد تاریخی)",
                    style={"color": GOLD, "fontSize": 14, "margin": "8px 0"}),
            html.Div(id="levels-panel"),
        ], width=12),
    ], style={"maxWidth": 1400, "margin": "0 auto"}),

    dcc.Interval(id="refresh-interval", interval=15_000, n_intervals=0),
], style={"background": BG, "minHeight": "100vh", "padding": "10px"})


# ==============================================================================
# 6) کال‌بک اصلی
# ==============================================================================
@app.callback(
    Output("main-chart", "figure"),
    Output("wheel-chart", "figure"),
    Output("levels-panel", "children"),
    Output("conn-status", "children"),
    Input("refresh-interval", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    State("symbol-input", "value"),
    State("interval-dropdown", "value"),
    State("category-dropdown", "value"),
    State("rings-slider", "value"),
    State("pivot-strength-slider", "value"),
    State("sensitivity-slider", "value"),
    State("tolerance-slider", "value"),
    State("show-fan-check", "value"),
)
def update(n_int, n_refresh, symbol, interval, category, n_rings, pivot_strength, sensitivity, tolerance_pct, show_fan):
    symbol = (symbol or DEFAULT_SYMBOL).upper()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL
    n_rings = int(n_rings or 8)
    pivot_strength = int(pivot_strength or 5)
    sensitivity = float(sensitivity or 1.0)
    tolerance_pct = float(tolerance_pct or 0.15)
    fan_on = "on" in (show_fan or [])

    df = get_klines(symbol, interval, category, limit=500)
    if df.empty or len(df) < (2 * pivot_strength + 10):
        empty_fig = go.Figure(layout=dict(
            paper_bgcolor=BG, plot_bgcolor=CARD,
            annotations=[dict(text="❌ دیتای کافی از بایبیت دریافت نشد.", x=0.5, y=0.5, showarrow=False,
                               font=dict(color=DN, size=14))]))
        return empty_fig, empty_fig, dash.no_update, "🔴 قطع"

    # --- کندل بسته‌نشده را کنار می‌گذاریم تا محاسبات لحظه‌به‌لحظه با نوسان زنده تغییر نکند
    df_closed = df.iloc[:-1] if len(df) > 2 else df

    piv_high, piv_low = detect_pivots(df_closed, left=pivot_strength, right=pivot_strength)
    anchor_idx, anchor_ts, anchor_price, anchor_type = select_anchor(df_closed, piv_high, piv_low)

    a_series = atr_series(df_closed, period=14)
    atr_val = float(a_series.iloc[-1]) if not a_series.dropna().empty else None
    increment = compute_dynamic_increment(df_closed, base=2.0, period=14, lookback=100, sensitivity=sensitivity)

    raw_levels = build_chronogann_matrix(anchor_price, increment, n_rings=n_rings)
    scored_levels = score_confluence(df_closed, raw_levels, tolerance_pct=tolerance_pct, lookback=min(400, len(df_closed)))

    current_price = float(df_closed["close"].iloc[-1])
    price_band = current_price * 0.18  # فقط سطوح نزدیک به قیمت فعلی روی چارت رسم می‌شوند
    visible_levels = [lv for lv in scored_levels if abs(lv["price"] - current_price) <= price_band]
    visible_levels.sort(key=lambda l: -l["touches"])

    max_touch = max((lv["touches"] for lv in visible_levels), default=0)

    # ---------------- چارت اصلی ----------------
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df["ts"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color=UP, decreasing_line_color=DN, name=symbol,
    ))

    x_range_end = idx_to_ts(df_closed, len(df_closed) - 1 + 30)

    for lv in visible_levels:
        touch_ratio = (lv["touches"] / max_touch) if max_touch > 0 else 0.0
        width = 1 + 3 * touch_ratio
        opacity = 0.25 + 0.65 * touch_ratio
        color = GOLD if lv["is_cardinal"] else CYAN
        dash_style = "solid" if lv["is_cardinal"] else "dot"
        fig.add_shape(
            type="line", x0=df["ts"].iloc[0], x1=x_range_end,
            y0=lv["price"], y1=lv["price"],
            line=dict(color=color, width=width, dash=dash_style),
            opacity=opacity, layer="below",
        )

    # لنگر
    fig.add_trace(go.Scatter(
        x=[anchor_ts], y=[anchor_price], mode="markers+text",
        marker=dict(color=PURPLE, size=12, symbol="diamond"),
        text=["⚓ لنگر"], textposition="top center",
        textfont=dict(color=PURPLE, size=11),
        name="لنگر ChronoGann",
    ))

    # بادبزن زمانی گن
    if fan_on and atr_val:
        fans = build_gann_fan(df_closed, anchor_idx, anchor_price, anchor_type, atr_val, forward_bars=30)
        for f in fans:
            x0 = idx_to_ts(df_closed, f["x0_idx"])
            x1 = idx_to_ts(df_closed, f["x1_idx"])
            fig.add_shape(
                type="line", x0=x0, x1=x1, y0=f["y0"], y1=f["y1"],
                line=dict(color=ORANGE if f["is_1x1"] else MUT,
                          width=2.5 if f["is_1x1"] else 1, dash="solid" if f["is_1x1"] else "dash"),
                opacity=0.85 if f["is_1x1"] else 0.45, layer="below",
            )

    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
        font=dict(color=TXT),
        xaxis=dict(gridcolor=LINE, rangeslider_visible=False),
        yaxis=dict(gridcolor=LINE),
        margin=dict(l=10, r=10, t=40, b=10), showlegend=False,
        title=dict(text=f"{symbol} — {category} — {interval} | لنگر: {anchor_type} @ {anchor_price:.4g} | گام: {increment:.3f}",
                   x=0.5, font=dict(color=GOLD, size=13)),
    )

    # ---------------- چرخ ماتریس (Polar Wheel) ----------------
    wheel = go.Figure()
    ring_r = list(range(1, n_rings + 1))
    theta_full = [i * 45 for i in range(8)] + [0]

    for ring in ring_r:
        wheel.add_trace(go.Scatterpolar(
            r=[ring] * 9, theta=theta_full,
            mode="lines", line=dict(color=LINE, width=1), showlegend=False, hoverinfo="skip",
        ))
    for a_idx in range(8):
        wheel.add_trace(go.Scatterpolar(
            r=[0, n_rings], theta=[a_idx * 45, a_idx * 45],
            mode="lines",
            line=dict(color=GOLD if a_idx in CARDINAL_IDX else LINE,
                      width=1.5 if a_idx in CARDINAL_IDX else 1,
                      dash="solid" if a_idx in CARDINAL_IDX else "dot"),
            showlegend=False, hoverinfo="skip",
        ))

    up_nodes = [lv for lv in scored_levels if lv["direction"] == "up"]
    if up_nodes:
        touches_arr = [lv["touches"] for lv in up_nodes]
        max_t = max(touches_arr) if max(touches_arr) > 0 else 1
        wheel.add_trace(go.Scatterpolar(
            r=[lv["ring"] for lv in up_nodes],
            theta=[lv["angle_idx"] * 45 for lv in up_nodes],
            mode="markers",
            marker=dict(
                size=[6 + 10 * (lv["touches"] / max_t) for lv in up_nodes],
                color=[lv["touches"] for lv in up_nodes],
                colorscale=[[0, "#23314d"], [1, GOLD]],
                showscale=False,
                line=dict(color=UP, width=1),
            ),
            text=[f"{lv['price']:.4g} | برخورد: {lv['touches']}" for lv in up_nodes],
            hovertemplate="%{text}<extra></extra>",
            name="سطوح صعودی (مقاومت بالقوه)",
        ))

    r_now, theta_now, dir_now = current_price_spiral_position(current_price, anchor_price, increment)
    wheel.add_trace(go.Scatterpolar(
        r=[min(r_now, n_rings + 0.5)], theta=[theta_now], mode="markers+text",
        marker=dict(color=UP if dir_now == "up" else DN, size=16, symbol="star"),
        text=["💠 قیمت لحظه‌ای"], textposition="bottom center",
        textfont=dict(color=TXT, size=10),
        name="موقعیت قیمت در مارپیچ",
    ))

    wheel.update_layout(
        template="plotly_dark", paper_bgcolor=BG,
        polar=dict(
            bgcolor=CARD,
            radialaxis=dict(visible=True, range=[0, n_rings + 1], gridcolor=LINE, color=MUT),
            angularaxis=dict(gridcolor=LINE, color=MUT, direction="counterclockwise", rotation=90),
        ),
        margin=dict(l=20, r=20, t=40, b=20), showlegend=False,
        title=dict(text="🌀 چرخ ماتریسِ ChronoGann (لایه‌ها = رینگ، اسپوک‌ها = زوایای اصلی/مورب)",
                   x=0.5, font=dict(color=GOLD, size=13)),
    )

    # ---------------- پنل سطوح کلیدی ----------------
    top_levels = sorted(scored_levels, key=lambda l: -l["touches"])[:12]
    if not top_levels or all(lv["touches"] == 0 for lv in top_levels):
        panel = dbc.Alert("در بازه‌ی فعلی، برخورد تاریخی معناداری برای سطوح مارپیچ ثبت نشد.",
                          color="secondary", style={"fontSize": 13})
    else:
        rows = []
        for lv in top_levels:
            dist_pct = (lv["price"] - current_price) / current_price * 100
            dir_color = UP if dist_pct >= 0 else DN
            rows.append(html.Tr([
                html.Td(f"{lv['price']:.5g}", style={"color": TXT}),
                html.Td("کاردینال" if lv["is_cardinal"] else "دیاگونال",
                        style={"color": GOLD if lv["is_cardinal"] else CYAN}),
                html.Td(f"رینگ {lv['ring']} / {lv['angle']}", style={"color": MUT}),
                html.Td("صعودی" if lv["direction"] == "up" else "نزولی",
                        style={"color": UP if lv["direction"] == "up" else DN}),
                html.Td(f"{dist_pct:+.2f}٪", style={"color": dir_color}),
                html.Td(f"{lv['touches']}", style={"color": GOLD, "fontWeight": "bold"}),
            ]))
        panel = dbc.Table(
            [html.Thead(html.Tr([html.Th(c) for c in
                ["قیمت", "نوع محور", "رینگ/زاویه", "جهت", "فاصله از قیمت", "تعداد برخورد"]])),
             html.Tbody(rows)],
            bordered=False, dark=True, hover=True, size="sm",
            style={"background": CARD, "fontSize": 12},
        )

    status = f"🟢 متصل | {pd.Timestamp.now().strftime('%H:%M:%S')} | ATR: {atr_val:.4g}" if atr_val else "🟡 دیتای ناقص"
    return fig, wheel, panel, status


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8061, use_reloader=False)