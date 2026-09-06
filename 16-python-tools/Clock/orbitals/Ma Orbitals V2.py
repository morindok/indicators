# -*- coding: utf-8 -*-
"""
🌌 Fibonacci Orbital System — Bybit Edition
------------------------------------------------------------------
قیمت روی مدارهای فیبوناچی (MA با دوره‌های دنباله فیبوناچی) می‌چرخد.
هر مدار با مدار مجاور خود یک «حلقه زنجیر» تشکیل می‌دهد.
تحلیل زنجیروار نشان می‌دهد روند کلی و قدرت روند چگونه است.

نصب:
pip install dash dash-bootstrap-components plotly pandas numpy requests
"""

import time
import numpy as np
import pandas as pd
import requests
import dash
from dash import dcc, html, Input, Output, State, ctx
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==============================================================================
# 0) پالت رنگی تیره
# ==============================================================================
BG, CARD, LINE, TXT, MUT = "#0b1220", "#121c30", "#23314d", "#e8ecf4", "#8fa3c0"
GOLD, UP, DN = "#f0b90b", "#16a085", "#e74c3c"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_CATEGORY = "linear"
DEFAULT_INTERVAL = "15"

# دنباله فیبوناچی برای دوره‌های مدار
FIBONACCI_PERIODS = [5, 8, 13, 21, 34, 55, 89, 144, 233]

# رنگ هر مدار (از سریع‌ترین به کندترین)
ORBIT_COLORS = [
    "#e74c3c",  # MA5  - قرمز (سریع‌ترین)
    "#e67e22",  # MA8  - نارنجی
    "#f1c40f",  # MA13 - زرد
    "#2ecc71",  # MA21 - سبز
    "#1abc9c",  # MA34 - فیروزه‌ای
    "#3498db",  # MA55 - آبی
    "#9b59b6",  # MA89 - بنفش
    "#8e44ad",  # MA144 - بنفش تیره
    "#34495e",  # MA233 - خاکستری (کندترین)
]

# ==============================================================================
# 1) اتصال REST پایدار به بایبیت — چند دامنه + کش فعال + هدر مرورگر
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
    """درخواست GET با مکانیسم فالبک بین چند دامنه بایبیت."""
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
    """دریافت کندل‌های تاریخی از بایبیت."""
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
# 2) محاسبه مدارهای فیبوناچی و موقعیت قیمت
# ==============================================================================
def calculate_orbits(df, periods=None):
    """
    محاسبه مدارهای فیبوناچی:
    هر میانگین متحرک یک «مدار» است که قیمت دور آن می‌چرخد.

    خروجی برای هر مدار:
      - ma: مقدار میانگین متحرک در هر کندل
      - distance_pct: فاصله درصدی قیمت از مدار (مثبت = بالا، منفی = پایین)
      - velocity: نرخ تغییر خود مدار (سرعت چرخش مدار)
      - acceleration: شتاب مدار
      - above: آیا قیمت بالای مدار است؟
    """
    periods = periods or FIBONACCI_PERIODS
    orbits = {}
    for period in periods:
        ma = df["close"].rolling(window=period, min_periods=1).mean()
        distance_pct = (df["close"] - ma) / ma * 100
        velocity = ma.diff()
        acceleration = velocity.diff()
        orbits[period] = {
            "ma": ma,
            "distance_pct": distance_pct,
            "velocity": velocity,
            "acceleration": acceleration,
            "above": df["close"] > ma,
        }
    return orbits


# ==============================================================================
# 3) تحلیل زنجیروار مدارها
# ==============================================================================
def analyze_chain(orbits, df):
    """
    تحلیل زنجیروار:
    هر جفت مدار مجاور (درونی/بیرونی) یک «حلقه» از زنجیر تشکیل می‌دهد.
    اگر همه حلقه‌ها هم‌جهت باشند => زنجیر هم‌راستا (روند قوی).
    اگر حلقه‌ها ضد جهت باشند => زنجیر پیچ‌خورده (خنثی یا بازگشت).

    خروجی:
      - chain_links: لیست حلقه‌ها با وضعیت هر کدام
      - alignment_score: امتیاز هم‌راستایی کل زنجیر
      - direction: جهت روند کلی
      - strength: قدرت روند
      - convergence: هم‌گرایی یا واگرایی مدارهای سریع و کند
    """
    latest_idx = df.index[-1]
    periods = sorted(orbits.keys())
    chain_links = []

    # ساخت حلقه‌های زنجیر از مدارهای مجاور
    for i in range(len(periods) - 1):
        inner_p = periods[i]      # مدار درونی (سریع‌تر)
        outer_p = periods[i + 1]  # مدار بیرونی (کندتر)
        inner_data = orbits[inner_p]
        outer_data = orbits[outer_p]

        inner_ma = inner_data["ma"].iloc[latest_idx]
        outer_ma = outer_data["ma"].iloc[latest_idx]
        price = df["close"].iloc[latest_idx]

        # فاصله بین دو مدار (Spread)
        orbit_spread = (inner_ma - outer_ma) / outer_ma * 100 if outer_ma != 0 else 0

        # موقعیت قیمت نسبت به هر دو مدار
        price_above_inner = price > inner_ma
        price_above_outer = price > outer_ma

        # وضعیت حلقه زنجیر
        if price_above_inner and price_above_outer:
            link_status = "صعودی کامل"
            link_value = 1
        elif not price_above_inner and not price_above_outer:
            link_status = "نزولی کامل"
            link_value = -1
        elif price_above_inner and not price_above_outer:
            link_status = "صعودی محلی / نزولی کلی"
            link_value = 0.5
        else:
            link_status = "نزولی محلی / صعودی کلی"
            link_value = -0.5

        # قدرت حلقه (بر اساس فاصله درصدی از مدارها)
        inner_dist = inner_data["distance_pct"].iloc[latest_idx]
        outer_dist = outer_data["distance_pct"].iloc[latest_idx]
        link_power = (abs(inner_dist) + abs(outer_dist)) / 2

        chain_links.append({
            "inner_period": inner_p,
            "outer_period": outer_p,
            "inner_ma": inner_ma,
            "outer_ma": outer_ma,
            "orbit_spread": orbit_spread,
            "link_status": link_status,
            "link_value": link_value,
            "link_power": link_power,
            "price": price,
        })

    # تحلیل کلی زنجیر
    if chain_links:
        total_value = sum(lk["link_value"] for lk in chain_links)
        avg_power = sum(lk["link_power"] for lk in chain_links) / len(chain_links)

        # امتیاز هم‌راستایی: از -n تا +n (n = تعداد حلقه‌ها)
        alignment_score = total_value

        # جهت روند
        if alignment_score > 1:
            direction = "🟢 صعودی"
        elif alignment_score < -1:
            direction = "🔴 نزولی"
        else:
            direction = "⚪ خنثی"

        # قدرت روند
        max_score = len(chain_links)
        score_ratio = abs(alignment_score) / max_score if max_score > 0 else 0
        if score_ratio >= 0.75:
            strength = "فوق‌العاده قوی"
            strength_color = UP
        elif score_ratio >= 0.5:
            strength = "قوی"
            strength_color = UP
        elif score_ratio >= 0.25:
            strength = "متوسط"
            strength_color = GOLD
        else:
            strength = "ضعیف"
            strength_color = MUT

        # هم‌گرایی: مقایسه حلقه داخلی‌ترین و خارجی‌ترین
        inner_link = chain_links[0]
        outer_link = chain_links[-1]
        if inner_link["link_value"] * outer_link["link_value"] > 0:
            convergence = "🔄 هم‌گرا"
        else:
            convergence = "⚡ واگرا"
    else:
        alignment_score = 0
        direction = "⚪ خنثی"
        strength = "ضعیف"
        strength_color = MUT
        convergence = "🔄 هم‌گرا"

    return {
        "chain_links": chain_links,
        "alignment_score": alignment_score,
        "direction": direction,
        "strength": strength,
        "strength_color": strength_color,
        "convergence": convergence,
        "avg_power": avg_power if chain_links else 0,
    }


# ==============================================================================
# 4) ساخت پنل نمایشی تحلیل زنجیروار
# ==============================================================================
def _fmt_price(v):
    if v is None or pd.isna(v):
        return "-"
    return f"{v:,.2f}"


def _fmt_pct(v):
    if v is None or pd.isna(v):
        return "-"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.2f}%"


def _link_color(v):
    if v > 0:
        return UP
    elif v < 0:
        return DN
    return MUT


def build_chain_panel(chain_result, orbits):
    """ساخت پنل نمایش وضعیت زنجیر مدارهای فیبوناچی."""
    if not chain_result["chain_links"]:
        return dbc.Alert("دیتا کافی برای تحلیل زنجیروار وجود ندارد.",
                         color="secondary", style={"fontSize": 13})

    # کارت خلاصه کلی
    summary_card = dbc.Card(dbc.CardBody([
        html.Div("🌌 وضعیت کلی سیستم اربیتال",
                 style={"color": GOLD, "fontWeight": "bold", "fontSize": 14, "marginBottom": 10}),
        dbc.Row([
            dbc.Col([
                html.Div("جهت روند:", style={"color": MUT, "fontSize": 12}),
                html.Div(chain_result["direction"],
                         style={"fontSize": 16, "fontWeight": "bold", "color": TXT}),
            ], width=6),
            dbc.Col([
                html.Div("قدرت روند:", style={"color": MUT, "fontSize": 12}),
                html.Div(chain_result["strength"],
                         style={"fontSize": 16, "fontWeight": "bold",
                                "color": chain_result["strength_color"]}),
            ], width=6),
        ]),
        dbc.Row([
            dbc.Col([
                html.Div("هم‌راستایی:", style={"color": MUT, "fontSize": 12, "marginTop": 8}),
                html.Div(f"{chain_result['alignment_score']:.1f} / {len(chain_result['chain_links'])}",
                         style={"fontSize": 14, "color": TXT}),
            ], width=6),
            dbc.Col([
                html.Div("وضعیت:", style={"color": MUT, "fontSize": 12, "marginTop": 8}),
                html.Div(chain_result["convergence"],
                         style={"fontSize": 14, "color": TXT}),
            ], width=6),
        ]),
    ]), style={"background": CARD, "border": f"1px solid {LINE}", "marginBottom": 12})

    # کارت حلقه‌های زنجیر
    link_cards = []
    for lk in chain_result["chain_links"]:
        inner_color = ORBIT_COLORS[FIBONACCI_PERIODS.index(lk["inner_period"])]
        outer_color = ORBIT_COLORS[FIBONACCI_PERIODS.index(lk["outer_period"])]

        link_cards.append(
            dbc.Card(dbc.CardBody([
                html.Div([
                    html.Span(f"🔗 MA{lk['inner_period']}",
                              style={"color": inner_color, "fontWeight": "bold", "marginRight": 8}),
                    html.Span("→", style={"color": MUT, "marginRight": 8}),
                    html.Span(f"MA{lk['outer_period']}",
                              style={"color": outer_color, "fontWeight": "bold"}),
                ], style={"marginBottom": 6}),
                dbc.Row([
                    dbc.Col([
                        html.Div(f"درونی: {_fmt_price(lk['inner_ma'])}",
                                 style={"color": inner_color, "fontSize": 12}),
                    ], width=6),
                    dbc.Col([
                        html.Div(f"بیرونی: {_fmt_price(lk['outer_ma'])}",
                                 style={"color": outer_color, "fontSize": 12}),
                    ], width=6),
                ]),
                dbc.Row([
                    dbc.Col([
                        html.Div(f"Spread: {_fmt_pct(lk['orbit_spread'])}",
                                 style={"color": _link_color(lk['orbit_spread']), "fontSize": 12}),
                    ], width=6),
                    dbc.Col([
                        html.Div(lk["link_status"],
                                 style={"color": _link_color(lk["link_value"]),
                                        "fontSize": 12, "fontWeight": "bold"}),
                    ], width=6),
                ], style={"marginTop": 4}),
            ]), style={"background": CARD, "border": f"1px solid {LINE}",
                       "marginBottom": 6, "padding": "8px"})
        )

    # کارت موقعیت قیمت روی هر مدار
    orbit_cards = []
    for period in FIBONACCI_PERIODS:
        if period not in orbits:
            continue
        data = orbits[period]
        ma_val = data["ma"].iloc[-1]
        dist = data["distance_pct"].iloc[-1]
        color = ORBIT_COLORS[FIBONACCI_PERIODS.index(period)]

        orbit_cards.append(
            dbc.Card(dbc.CardBody([
                html.Div(f"مدار {period}", style={"color": color, "fontWeight": "bold", "fontSize": 12}),
                html.Div(f"قیمت: {_fmt_price(ma_val)}", style={"color": MUT, "fontSize": 11}),
                html.Div(f"انحراف: {_fmt_pct(dist)}",
                         style={"color": _link_color(dist), "fontSize": 12, "fontWeight": "bold"}),
            ]), style={"background": CARD, "border": f"1px solid {LINE}",
                       "display": "inline-block", "margin": "2px", "padding": "6px 10px",
                       "minWidth": "90px"})
        )

    return html.Div([
        summary_card,
        html.Div("📍 موقعیت قیمت روی هر مدار:",
                 style={"color": GOLD, "fontSize": 13, "marginBottom": 6}),
        html.Div(orbit_cards, style={"marginBottom": 12}),
        html.Div("🔗 حلقه‌های زنجیر:",
                 style={"color": GOLD, "fontSize": 13, "marginBottom": 6}),
        html.Div(link_cards),
    ])


# ==============================================================================
# 5) رسم چارت با مدارهای فیبوناچی
# ==============================================================================
def build_orbital_chart(df, orbits):
    """رسم چارت کندل‌استیک با مدارهای فیبوناچی."""
    fig = go.Figure()

    # کندل‌استیک
    fig.add_trace(go.Candlestick(
        x=df["ts"], open=df["open"], high=df["high"],
        low=df["low"], close=df["close"],
        increasing_line_color=UP, decreasing_line_color=DN,
        name="Price",
    ))

    # اضافه کردن هر مدار به عنوان یک خط
    for period in FIBONACCI_PERIODS:
        if period not in orbits:
            continue
        data = orbits[period]
        color = ORBIT_COLORS[FIBONACCI_PERIODS.index(period)]

        fig.add_trace(go.Scatter(
            x=df["ts"], y=data["ma"],
            mode="lines",
            line=dict(color=color, width=1.5),
            name=f"Orbit {period}",
        ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG, plot_bgcolor=CARD,
        font=dict(color=TXT),
        xaxis=dict(gridcolor=LINE, rangeslider_visible=False),
        yaxis=dict(gridcolor=LINE),
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", y=1.15, x=0.5, xanchor="center"),
        showlegend=True,
    )
    return fig


# ==============================================================================
# 6) اپ Dash
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])
app.title = "Fibonacci Orbital System"
server = app.server

CATEGORY_OPTS = [{"label": v, "value": v} for v in ["linear", "spot", "inverse"]]
INTERVAL_OPTS = [{"label": lbl, "value": val} for lbl, val in [
    ("1m", "1"), ("3m", "3"), ("5m", "5"), ("15m", "15"),
    ("30m", "30"), ("1h", "60"), ("4h", "240"), ("1D", "D"),
]]

app.layout = html.Div([
    # نوار بالایی
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([html.Label("نماد:", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="symbol-input", value=DEFAULT_SYMBOL, type="text",
                           style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
        dbc.Col([html.Label("بازار:", style={"fontSize": 12, "color": MUT}),
                 dcc.Dropdown(id="category-dropdown", value=DEFAULT_CATEGORY,
                              clearable=False, options=CATEGORY_OPTS)], md=2),
        dbc.Col([html.Label("تایم‌فریم:", style={"fontSize": 12, "color": MUT}),
                 dcc.Dropdown(id="interval-dropdown", value=DEFAULT_INTERVAL,
                              clearable=False, options=INTERVAL_OPTS)], md=2),
        dbc.Col(dbc.Button("🔄 بروزرسانی", id="refresh-btn", color="warning", className="mt-3",
                           style={"fontWeight": "bold", "color": "#0b1220", "width": "100%"}), md=2),
        dbc.Col(html.Div(id="conn-status", style={"color": MUT, "fontSize": 11,
                                                   "marginTop": 22, "textAlign": "center"}), md=2),
    ])), style={"maxWidth": 1200, "margin": "10px auto"}),

    # بدنه اصلی
    dbc.Row([
        dbc.Col(dcc.Graph(id="orbital-chart", style={"height": "72vh"},
                          config={"displaylogo": False}), width=8),
        dbc.Col([
            html.H5("🌌 تحلیل زنجیروار مدارهای فیبوناچی",
                    style={"color": GOLD, "fontSize": 14, "margin": "8px 0"}),
            html.Div(id="chain-panel"),
        ], width=4),
    ], style={"maxWidth": 1200, "margin": "0 auto"}),

    # رفرش خودکار
    dcc.Interval(id="refresh-interval", interval=15_000, n_intervals=0),
], style={"background": BG, "minHeight": "100vh", "padding": "10px"})


# ==============================================================================
# 7) کال‌بک اصلی
# ==============================================================================
@app.callback(
    Output("orbital-chart", "figure"),
    Output("chain-panel", "children"),
    Output("conn-status", "children"),
    Input("refresh-interval", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    State("symbol-input", "value"),
    State("interval-dropdown", "value"),
    State("category-dropdown", "value"),
)
def update_orbital_system(n_int, n_refresh, symbol, interval, category):
    symbol = (symbol or DEFAULT_SYMBOL).upper()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL

    # دریافت دیتا از بایبیت
    df = get_klines(symbol, interval, category, limit=500)

    if df.empty:
        empty_fig = go.Figure(layout=dict(
            paper_bgcolor=BG, plot_bgcolor=CARD,
            annotations=[dict(text="❌ دریافت دیتا از بایبیت ناموفق بود.",
                              x=0.5, y=0.5, showarrow=False,
                              font=dict(color=DN, size=14))]))
        return empty_fig, dash.no_update, "🔴 قطع"

    # محاسبه مدارها
    orbits = calculate_orbits(df)

    # تحلیل زنجیروار
    chain_result = analyze_chain(orbits, df)

    # رسم چارت
    fig = build_orbital_chart(df, orbits)
    fig.update_layout(
        title=dict(text=f"🌌 {symbol} — {interval} — Fibonacci Orbital System",
                   x=0.5, font=dict(color=GOLD, size=14)),
    )

    # ساخت پنل
    panel = build_chain_panel(chain_result, orbits)
    status = f"🟢 متصل | {pd.Timestamp.now().strftime('%H:%M:%S')}"

    return fig, panel, status


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8061, use_reloader=False)