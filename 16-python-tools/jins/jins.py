# -*- coding: utf-8 -*-
"""
Digital Syndicate 2500 Demo Trading Terminal
---------------------------------------------
ویژگی‌ها:
- دریافت کندل عمومی از Bybit V5
- معاملات کاملاً دمو و داخلی
- تشخیص رژیم بازار
- استراتژی چندلایه Trend / Breakout / Mean Reversion
- مدیریت ریسک ATR
- نمودار کندلی
- Regime Matrix
- Confidence Gauge
- Equity Curve
- Risk Radar
- Volume Delta Proxy

هشدار:
این پروژه سفارش واقعی ارسال نمی‌کند و برای معامله واقعی آماده نیست.
"""

import time
import threading
from datetime import datetime

import numpy as np
import pandas as pd
import requests

import dash
from dash import dcc, html, Input, Output, State, ctx
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ============================================================================
# 1) تنظیمات
# ============================================================================

BG = "#07111f"
CARD = "#101d31"
CARD2 = "#14243d"
LINE = "#263b5d"
TXT = "#e9f0fa"
MUTED = "#8ca3c2"
GOLD = "#f0b90b"
GREEN = "#19c37d"
RED = "#ef5350"
BLUE = "#42a5f5"
PURPLE = "#ab6cff"
ORANGE = "#ff9f43"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_INTERVAL = "15"
DEFAULT_CATEGORY = "linear"

STARTING_BALANCE = 10_000.0
RISK_PER_TRADE = 0.01
MAX_BARS = 500

REST_CANDIDATES = [
    "https://api.bybit.com",
    "https://api.bytick.com",
    "https://api.bybit.kz",
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 DigitalSyndicateDemo/1.0",
    "Accept": "application/json",
    "Referer": "https://www.bybit.com/",
})

_ACTIVE_REST_BASE = {"url": None}
_BASE_LOCK = threading.Lock()


# ============================================================================
# 2) اتصال مقاوم به Bybit
# ============================================================================

def bybit_get(path, params, timeout=10):
    active = _ACTIVE_REST_BASE["url"]

    candidates = []
    if active:
        candidates.append(active)

    candidates.extend([
        base for base in REST_CANDIDATES
        if base != active
    ])

    last_error = None

    for base in candidates:
        try:
            response = SESSION.get(
                f"{base}{path}",
                params=params,
                timeout=timeout
            )

            if response.status_code in (403, 408, 425, 429, 451):
                continue

            response.raise_for_status()
            payload = response.json()

            if payload.get("retCode") == 0:
                with _BASE_LOCK:
                    _ACTIVE_REST_BASE["url"] = base
                return payload

        except Exception as exc:
            last_error = exc
            continue

    return None


def get_klines(symbol, interval, category=DEFAULT_CATEGORY, limit=500):
    payload = bybit_get(
        "/v5/market/kline",
        {
            "category": category,
            "symbol": symbol.upper().strip(),
            "interval": str(interval),
            "limit": int(limit),
        }
    )

    if not payload:
        return pd.DataFrame()

    rows = (payload.get("result") or {}).get("list") or []

    if not rows:
        return pd.DataFrame()

    columns = [
        "ts",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover",
    ]

    df = pd.DataFrame(rows, columns=columns)

    df["ts"] = pd.to_datetime(
        pd.to_numeric(df["ts"]),
        unit="ms",
        utc=True
    ).dt.tz_convert(None)

    for col in ["open", "high", "low", "close", "volume", "turnover"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = (
        df.dropna()
          .sort_values("ts")
          .drop_duplicates("ts")
          .reset_index(drop=True)
    )

    return df


# ============================================================================
# 3) اندیکاتورها و ویژگی‌های بازار
# ============================================================================

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))

    return result.fillna(50)


def atr(df, period=14):
    prev_close = df["close"].shift(1)

    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)

    return tr.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()


def build_features(df):
    x = df.copy()

    x["ema_fast"] = x["close"].ewm(span=21, adjust=False).mean()
    x["ema_slow"] = x["close"].ewm(span=55, adjust=False).mean()
    x["atr"] = atr(x, 14)
    x["rsi"] = rsi(x["close"], 14)

    x["atr_pct"] = (x["atr"] / x["close"]) * 100
    x["vol_ma"] = x["volume"].rolling(30).mean()
    x["relative_volume"] = x["volume"] / x["vol_ma"].replace(0, np.nan)

    x["high_20"] = x["high"].rolling(20).max().shift(1)
    x["low_20"] = x["low"].rolling(20).min().shift(1)

    x["ema_spread"] = (
        (x["ema_fast"] - x["ema_slow"]) / x["close"] * 100
    )

    # این دلتا، دلتا واقعی اردرفلو نیست؛ proxy جهت کندل است.
    x["volume_delta_proxy"] = np.where(
        x["close"] >= x["open"],
        x["volume"],
        -x["volume"]
    )

    x["delta_z"] = (
        x["volume_delta_proxy"]
        - x["volume_delta_proxy"].rolling(30).mean()
    ) / x["volume_delta_proxy"].rolling(30).std().replace(0, np.nan)

    x["ret"] = x["close"].pct_change()
    x["realized_vol"] = x["ret"].rolling(30).std() * 100

    return x.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)


# ============================================================================
# 4) موتور رژیم بازار
# ============================================================================

def classify_regime(row):
    spread = float(row["ema_spread"])
    atr_pct = float(row["atr_pct"])
    rv = float(row["realized_vol"])

    if atr_pct > 1.8 or rv > 1.2:
        return "HIGH_VOLATILITY"

    if spread > 0.25:
        return "TREND_UP"

    if spread < -0.25:
        return "TREND_DOWN"

    return "RANGE"


REGIME_COLORS = {
    "TREND_UP": GREEN,
    "TREND_DOWN": RED,
    "RANGE": BLUE,
    "HIGH_VOLATILITY": ORANGE,
    "UNKNOWN": MUTED,
}


# ============================================================================
# 5) استراتژی سندیکا
# ============================================================================

def calculate_signal(features):
    """
    سه جن مفهومی در این موتور همکاری می‌کنند:

    Trend Engine:
        هم‌جهتی EMA21 و EMA55

    Breakout Engine:
        شکست سقف یا کف 20 کندل اخیر

    Flow Proxy Engine:
        جهت حجم بر اساس رنگ کندل

    خروجی فقط سیگنال داخلی برای معاملات دمو است.
    """

    if len(features) < 50:
        return {
            "signal": "WAIT",
            "score": 0.0,
            "regime": "UNKNOWN",
            "reason": "insufficient_data",
        }

    row = features.iloc[-1]
    prev = features.iloc[-2]

    regime = classify_regime(row)

    long_score = 0.0
    short_score = 0.0
    reasons = []

    # روند
    if row["ema_fast"] > row["ema_slow"]:
        long_score += 0.35
        reasons.append("ema_bullish")
    elif row["ema_fast"] < row["ema_slow"]:
        short_score += 0.35
        reasons.append("ema_bearish")

    # شکست
    if row["close"] > row["high_20"] and prev["close"] <= prev["high_20"]:
        long_score += 0.35
        reasons.append("breakout_up")

    if row["close"] < row["low_20"] and prev["close"] >= prev["low_20"]:
        short_score += 0.35
        reasons.append("breakout_down")

    # حجم جهت‌دار
    if row["delta_z"] > 0.4:
        long_score += 0.20
        reasons.append("positive_volume_proxy")

    if row["delta_z"] < -0.4:
        short_score += 0.20
        reasons.append("negative_volume_proxy")

    # مومنتوم
    if 52 <= row["rsi"] <= 72:
        long_score += 0.10

    if 28 <= row["rsi"] <= 48:
        short_score += 0.10

    # در نوسان شدید، آستانه سخت‌تر می‌شود
    threshold = 0.70 if regime == "HIGH_VOLATILITY" else 0.60

    if long_score >= threshold and regime != "TREND_DOWN":
        final_signal = "LONG"
        final_score = long_score

    elif short_score >= threshold and regime != "TREND_UP":
        final_signal = "SHORT"
        final_score = short_score

    else:
        final_signal = "WAIT"
        final_score = max(long_score, short_score)

    return {
        "signal": final_signal,
        "score": round(float(final_score), 3),
        "regime": regime,
        "reason": ", ".join(reasons) if reasons else "no_confirmation",
        "atr": float(row["atr"]),
        "price": float(row["close"]),
        "rsi": float(row["rsi"]),
        "atr_pct": float(row["atr_pct"]),
        "delta_z": float(row["delta_z"]),
    }


# ============================================================================
# 6) دفتر معاملات دمو
# ============================================================================

def empty_account():
    return {
        "balance": STARTING_BALANCE,
        "equity": STARTING_BALANCE,
        "position": None,
        "trades": [],
        "peak_equity": STARTING_BALANCE,
        "last_signal_key": None,
    }


def close_position(account, price, reason):
    pos = account.get("position")

    if not pos:
        return account

    direction = pos["side"]
    qty = pos["qty"]
    entry = pos["entry"]

    if direction == "LONG":
        pnl = (price - entry) * qty
    else:
        pnl = (entry - price) * qty

    account["balance"] += pnl

    trade = {
        "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "side": direction,
        "entry": entry,
        "exit": price,
        "qty": qty,
        "pnl": pnl,
        "reason": reason,
    }

    account["trades"].append(trade)
    account["position"] = None

    return account


def execute_demo_logic(account, signal, candle_key):
    if signal["signal"] == "WAIT":
        return account

    price = signal["price"]
    atr_value = max(signal["atr"], price * 0.001)

    # خروج در صورت وجود پوزیشن مخالف
    if account["position"]:
        current_side = account["position"]["side"]

        if current_side != signal["signal"]:
            account = close_position(
                account,
                price,
                "opposite_signal"
            )

    # جلوگیری از ورود تکراری روی همان کندل
    if account["position"]:
        return account

    if account.get("last_signal_key") == candle_key:
        return account

    # در نوسان شدید ریسک کاهش می‌یابد
    risk_fraction = RISK_PER_TRADE

    if signal["regime"] == "HIGH_VOLATILITY":
        risk_fraction *= 0.5

    risk_amount = account["balance"] * risk_fraction

    if signal["signal"] == "LONG":
        stop = price - 2.0 * atr_value
    else:
        stop = price + 2.0 * atr_value

    stop_distance = abs(price - stop)

    if stop_distance <= 0:
        return account

    qty = risk_amount / stop_distance

    account["position"] = {
        "side": signal["signal"],
        "entry": price,
        "qty": qty,
        "stop": stop,
        "opened_at": candle_key,
        "regime": signal["regime"],
        "score": signal["score"],
    }

    account["last_signal_key"] = candle_key

    return account


def mark_to_market(account, price):
    equity = account["balance"]
    pos = account.get("position")

    if pos:
        if pos["side"] == "LONG":
            unrealized = (price - pos["entry"]) * pos["qty"]
        else:
            unrealized = (pos["entry"] - price) * pos["qty"]

        equity += unrealized

    account["equity"] = equity
    account["peak_equity"] = max(
        account.get("peak_equity", STARTING_BALANCE),
        equity
    )

    return account


# ============================================================================
# 7) نمودارها
# ============================================================================

def make_main_chart(features, account, symbol, interval):
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.025,
        row_heights=[0.58, 0.20, 0.22],
    )

    fig.add_trace(
        go.Candlestick(
            x=features["ts"],
            open=features["open"],
            high=features["high"],
            low=features["low"],
            close=features["close"],
            name="Price",
            increasing_line_color=GREEN,
            decreasing_line_color=RED,
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=features["ts"],
            y=features["ema_fast"],
            name="EMA 21",
            line=dict(color=GOLD, width=1.5),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=features["ts"],
            y=features["ema_slow"],
            name="EMA 55",
            line=dict(color=PURPLE, width=1.5),
        ),
        row=1,
        col=1,
    )

    colors = np.where(
        features["volume_delta_proxy"] >= 0,
        GREEN,
        RED
    )

    fig.add_trace(
        go.Bar(
            x=features["ts"],
            y=features["volume_delta_proxy"],
            marker_color=colors,
            name="Volume Delta Proxy",
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=features["ts"],
            y=features["rsi"],
            name="RSI",
            line=dict(color=BLUE, width=1.5),
        ),
        row=3,
        col=1,
    )

    fig.add_hline(
        y=70,
        line_dash="dot",
        line_color=RED,
        row=3,
        col=1,
    )

    fig.add_hline(
        y=30,
        line_dash="dot",
        line_color=GREEN,
        row=3,
        col=1,
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG,
        plot_bgcolor=CARD,
        font=dict(color=TXT),
        height=760,
        margin=dict(l=35, r=15, t=45, b=25),
        title=f"{symbol} | {interval} | Digital Syndicate Demo",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.02),
    )

    for axis in ["xaxis", "xaxis2", "xaxis3"]:
        fig.update_layout(**{
            axis: dict(
                gridcolor=LINE,
                showgrid=True,
            )
        })

    for axis in ["yaxis", "yaxis2", "yaxis3"]:
        fig.update_layout(**{
            axis: dict(
                gridcolor=LINE,
                showgrid=True,
            )
        })

    return fig


def make_regime_matrix(features):
    x = features.tail(100).copy()
    regimes = [classify_regime(row) for _, row in x.iterrows()]

    numeric = {
        "TREND_UP": 1,
        "RANGE": 2,
        "TREND_DOWN": 3,
        "HIGH_VOLATILITY": 4,
        "UNKNOWN": 0,
    }

    z = np.array([[numeric.get(r, 0) for r in regimes]])

    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=x["ts"],
            y=["Market Regime"],
            colorscale=[
                [0.00, "#384860"],
                [0.25, BLUE],
                [0.50, GREEN],
                [0.75, RED],
                [1.00, ORANGE],
            ],
            showscale=False,
            hovertext=regimes,
            hovertemplate="%{x}<br>%{hovertext}<extra></extra>",
        )
    )

    fig.update_layout(
        title="Regime Matrix",
        height=180,
        paper_bgcolor=BG,
        plot_bgcolor=CARD,
        font=dict(color=TXT),
        margin=dict(l=20, r=20, t=45, b=20),
    )

    return fig


def make_equity_chart(account):
    trades = account.get("trades", [])

    if not trades:
        equity = [STARTING_BALANCE]
        labels = ["Start"]
    else:
        equity = [STARTING_BALANCE]
        labels = ["Start"]

        current = STARTING_BALANCE

        for i, trade in enumerate(trades, start=1):
            current += trade["pnl"]
            equity.append(current)
            labels.append(str(i))

    fig = go.Figure(
        go.Scatter(
            x=labels,
            y=equity,
            mode="lines+markers",
            line=dict(color=GOLD, width=2),
            fill="tozeroy",
            fillcolor="rgba(240,185,11,0.12)",
            name="Equity",
        )
    )

    fig.update_layout(
        title="Demo Equity Curve",
        height=250,
        paper_bgcolor=BG,
        plot_bgcolor=CARD,
        font=dict(color=TXT),
        margin=dict(l=35, r=20, t=45, b=30),
        yaxis=dict(gridcolor=LINE),
        xaxis=dict(gridcolor=LINE),
    )

    return fig


def make_risk_radar(account, signal):
    pos = account.get("position")

    if pos:
        exposure = abs(pos["qty"] * pos["entry"]) / max(account["equity"], 1)
        stop_distance = abs(pos["entry"] - pos["stop"]) / pos["entry"]
    else:
        exposure = 0
        stop_distance = 0

    values = [
        min(signal.get("score", 0), 1),
        min(abs(signal.get("delta_z", 0)) / 3, 1),
        min(signal.get("atr_pct", 0) / 3, 1),
        min(exposure, 1),
        min(stop_distance * 20, 1),
    ]

    categories = [
        "Signal",
        "Flow",
        "Volatility",
        "Exposure",
        "Stop Distance",
    ]

    fig = go.Figure(
        go.Scatterpolar(
            r=values + [values[0]],
            theta=categories + [categories[0]],
            fill="toself",
            line=dict(color=PURPLE),
            fillcolor="rgba(171,108,255,0.25)",
        )
    )

    fig.update_layout(
        title="Risk / Signal Radar",
        height=300,
        paper_bgcolor=BG,
        font=dict(color=TXT),
        polar=dict(
            bgcolor=CARD,
            radialaxis=dict(
                visible=True,
                range=[0, 1],
                gridcolor=LINE,
            ),
            angularaxis=dict(gridcolor=LINE),
        ),
        margin=dict(l=35, r=35, t=50, b=25),
    )

    return fig


# ============================================================================
# 8) رابط کاربری Dash
# ============================================================================

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG]
)

server = app.server
app.title = "Digital Syndicate 2500 Demo"

INTERVAL_OPTIONS = [
    {"label": "1m", "value": "1"},
    {"label": "3m", "value": "3"},
    {"label": "5m", "value": "5"},
    {"label": "15m", "value": "15"},
    {"label": "30m", "value": "30"},
    {"label": "1h", "value": "60"},
    {"label": "4h", "value": "240"},
    {"label": "1D", "value": "D"},
]

CATEGORY_OPTIONS = [
    {"label": "Linear", "value": "linear"},
    {"label": "Spot", "value": "spot"},
    {"label": "Inverse", "value": "inverse"},
]


def metric_card(title, value, color=TXT):
    return dbc.Card(
        dbc.CardBody([
            html.Div(title, style={
                "color": MUTED,
                "fontSize": "11px",
                "marginBottom": "5px",
            }),
            html.Div(value, style={
                "color": color,
                "fontSize": "20px",
                "fontWeight": "bold",
            }),
        ]),
        style={
            "background": CARD,
            "border": f"1px solid {LINE}",
            "minHeight": "92px",
        }
    )


app.layout = html.Div([
    dcc.Store(id="account-store", data=empty_account()),
    dcc.Store(id="last-candle-store", data=None),
    dcc.Interval(id="timer", interval=15_000, n_intervals=0),

    dbc.Container([
        html.H2(
            "◈ DIGITAL SYNDICATE / DEMO TRADING TERMINAL",
            style={
                "color": GOLD,
                "letterSpacing": "2px",
                "marginTop": "18px",
                "marginBottom": "15px",
            }
        ),

        dbc.Card(
            dbc.CardBody(
                dbc.Row([
                    dbc.Col([
                        html.Label("Symbol", style={"color": MUTED}),
                        dcc.Input(
                            id="symbol",
                            value=DEFAULT_SYMBOL,
                            type="text",
                            style={"width": "100%"},
                        ),
                    ], md=3),

                    dbc.Col([
                        html.Label("Category", style={"color": MUTED}),
                        dcc.Dropdown(
                            id="category",
                            value=DEFAULT_CATEGORY,
                            options=CATEGORY_OPTIONS,
                            clearable=False,
                        ),
                    ], md=2),

                    dbc.Col([
                        html.Label("Interval", style={"color": MUTED}),
                        dcc.Dropdown(
                            id="interval",
                            value=DEFAULT_INTERVAL,
                            options=INTERVAL_OPTIONS,
                            clearable=False,
                        ),
                    ], md=2),

                    dbc.Col(
                        dbc.Button(
                            "RESET DEMO ACCOUNT",
                            id="reset",
                            color="danger",
                            className="mt-4",
                            style={"width": "100%"},
                        ),
                        md=2,
                    ),

                    dbc.Col(
                        html.Div(
                            id="status",
                            style={
                                "color": MUTED,
                                "fontSize": "12px",
                                "marginTop": "28px",
                            }
                        ),
                        md=3,
                    ),
                ])
            ),
            style={
                "background": CARD,
                "border": f"1px solid {LINE}",
                "marginBottom": "12px",
            }
        ),

        dbc.Row(id="metrics-row", className="g-2"),

        dbc.Row([
            dbc.Col(
                dcc.Graph(id="main-chart"),
                md=8,
            ),
            dbc.Col([
                dcc.Graph(id="regime-chart"),
                dcc.Graph(id="radar-chart"),
            ], md=4),
        ]),

        dbc.Row([
            dbc.Col(
                dcc.Graph(id="equity-chart"),
                md=7,
            ),
            dbc.Col(
                html.Div(id="trade-log"),
                md=5,
            ),
        ]),

        html.Div(
            "PUBLIC DATA ONLY • PAPER TRADING • VOLUME DELTA IS A CANDLE-DIRECTION PROXY",
            style={
                "color": MUTED,
                "fontSize": "11px",
                "textAlign": "center",
                "padding": "15px",
            }
        ),

    ], fluid=True)

], style={
    "background": BG,
    "minHeight": "100vh",
    "padding": "10px",
})


# ============================================================================
# 9) کال‌بک اصلی
# ============================================================================

@app.callback(
    Output("main-chart", "figure"),
    Output("regime-chart", "figure"),
    Output("radar-chart", "figure"),
    Output("equity-chart", "figure"),
    Output("metrics-row", "children"),
    Output("trade-log", "children"),
    Output("status", "children"),
    Output("account-store", "data"),
    Output("last-candle-store", "data"),

    Input("timer", "n_intervals"),
    Input("reset", "n_clicks"),

    State("symbol", "value"),
    State("category", "value"),
    State("interval", "value"),
    State("account-store", "data"),
    State("last-candle-store", "data"),
)
def update_terminal(
    n_intervals,
    reset_clicks,
    symbol,
    category,
    interval,
    account,
    last_candle,
):
    triggered = ctx.triggered_id

    if triggered == "reset":
        account = empty_account()
        last_candle = None

    account = account or empty_account()

    symbol = (symbol or DEFAULT_SYMBOL).upper().strip()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL

    df = get_klines(
        symbol=symbol,
        interval=interval,
        category=category,
        limit=MAX_BARS,
    )

    if df.empty:
        blank = go.Figure()
        blank.update_layout(
            template="plotly_dark",
            paper_bgcolor=BG,
            plot_bgcolor=CARD,
            annotations=[{
                "text": "Bybit data unavailable",
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"color": RED, "size": 18},
            }]
        )

        return (
            blank,
            blank,
            blank,
            blank,
            [],
            html.Div("No trades yet", style={"color": MUTED}),
            "🔴 Connection failed",
            account,
            last_candle,
        )

    features = build_features(df)

    if features.empty:
        blank = go.Figure()
        return (
            blank,
            blank,
            blank,
            blank,
            [],
            html.Div("Insufficient data", style={"color": MUTED}),
            "🟠 Insufficient data",
            account,
            last_candle,
        )

    signal = calculate_signal(features)
    latest = features.iloc[-1]
    candle_key = str(latest["ts"])

    # فقط یک بار برای هر کندل بسته‌شده منطق ورود اجرا می‌شود.
    # کندل نهایی Bybit ممکن است هنوز بسته نشده باشد.
    closed_features = features.iloc[:-1] if len(features) > 2 else features
    closed_signal = calculate_signal(closed_features)

    if len(closed_features) > 0:
        closed_price = float(closed_features.iloc[-1]["close"])

        if (
            closed_signal["signal"] in ("LONG", "SHORT")
            and last_candle != str(closed_features.iloc[-1]["ts"])
        ):
            account = execute_demo_logic(
                account,
                closed_signal,
                str(closed_features.iloc[-1]["ts"])
            )
            last_candle = str(closed_features.iloc[-1]["ts"])

    account = mark_to_market(account, float(latest["close"]))

    main_chart = make_main_chart(
        features,
        account,
        symbol,
        interval
    )

    regime_chart = make_regime_matrix(features)
    radar_chart = make_risk_radar(account, signal)
    equity_chart = make_equity_chart(account)

    position = account.get("position")
    pnl = account["equity"] - STARTING_BALANCE

    if pnl > 0:
        pnl_color = GREEN
    elif pnl < 0:
        pnl_color = RED
    else:
        pnl_color = TXT

    position_text = "FLAT"

    if position:
        position_text = (
            f"{position['side']} | "
            f"Entry: {position['entry']:.2f} | "
            f"Stop: {position['stop']:.2f}"
        )

    metrics = [
        dbc.Col(
            metric_card(
                "REGIME",
                signal["regime"],
                REGIME_COLORS.get(signal["regime"], MUTED)
            ),
            md=2
        ),
        dbc.Col(
            metric_card(
                "SIGNAL",
                f"{signal['signal']} / {signal['score']:.2f}",
                GREEN if signal["signal"] == "LONG"
                else RED if signal["signal"] == "SHORT"
                else MUTED
            ),
            md=2
        ),
        dbc.Col(
            metric_card(
                "EQUITY",
                f"${account['equity']:,.2f}",
                pnl_color
            ),
            md=2
        ),
        dbc.Col(
            metric_card(
                "P&L",
                f"${pnl:,.2f}",
                pnl_color
            ),
            md=2
        ),
        dbc.Col(
            metric_card(
                "RSI / ATR%",
                f"{signal['rsi']:.1f} / {signal['atr_pct']:.2f}",
                BLUE
            ),
            md=2
        ),
        dbc.Col(
            metric_card(
                "POSITION",
                position_text,
                ORANGE if position else MUTED
            ),
            md=2
        ),
    ]

    trades = account.get("trades", [])

    if trades:
        rows = []

        for trade in reversed(trades[-10:]):
            trade_color = GREEN if trade["pnl"] >= 0 else RED

            rows.append(
                html.Tr([
                    html.Td(trade["side"]),
                    html.Td(f"{trade['entry']:.2f}"),
                    html.Td(f"{trade['exit']:.2f}"),
                    html.Td(
                        f"{trade['pnl']:.2f}",
                        style={"color": trade_color}
                    ),
                    html.Td(trade["reason"]),
                ])
            )

        trade_log = dbc.Card([
            dbc.CardHeader(
                "آخرین معاملات دمو",
                style={"color": GOLD}
            ),
            dbc.CardBody(
                dbc.Table(
                    [
                        html.Thead(
                            html.Tr([
                                html.Th("Side"),
                                html.Th("Entry"),
                                html.Th("Exit"),
                                html.Th("PnL"),
                                html.Th("Reason"),
                            ])
                        ),
                        html.Tbody(rows),
                    ],
                    bordered=True,
                    hover=True,
                    responsive=True,
                    size="sm",
                    style={"fontSize": "11px"},
                )
            )
        ], style={"background": CARD, "border": f"1px solid {LINE}"})
    else:
        trade_log = dbc.Card(
            dbc.CardBody(
                html.Div(
                    "هنوز معامله‌ی دمو ایجاد نشده است.",
                    style={"color": MUTED}
                )
            ),
            style={"background": CARD, "border": f"1px solid {LINE}"}
        )

    status = (
        f"🟢 Bybit public REST | "
        f"{datetime.utcnow().strftime('%H:%M:%S')} UTC | "
        f"last price: {latest['close']:.2f}"
    )

    return (
        main_chart,
        regime_chart,
        radar_chart,
        equity_chart,
        metrics,
        trade_log,
        status,
        account,
        last_candle,
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8060,
        debug=False,
        use_reloader=False,
    )
