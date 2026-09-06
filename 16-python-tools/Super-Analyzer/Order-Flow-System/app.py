# -*- coding: utf-8 -*-
"""
Morindok Dashboard {Morindok}
================================
داشبورد حرفه‌ای آنالیز جریان سرمایه و قدرت خریدار/فروشنده - بایبیت
نویسنده: تولید شده برای برند Morindok

اجرا:
    pip install -r requirements.txt
    python app.py
سپس مرورگر را روی http://127.0.0.1:8050 باز کنید.
"""

import threading
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import dash
from dash import dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc

import bybit_engine as be
import signals_engine as se

# ----------------------------------------------------------------------------
# راه‌اندازی موتور داده (Polling معاملات ۳۰ ارز به‌صورت پس‌زمینه، بدون WebSocket)
# ----------------------------------------------------------------------------
STREAM = be.TradeStreamManager(be.TOP_30)
be.diagnose_connectivity()
STREAM.start()

SYMBOL_OPTIONS = [{"label": s.replace("USDT", " / USDT"), "value": s} for s in be.TOP_30]

FONT_FAMILY = "Vazirmatn, Tahoma, Arial, sans-serif"
DARK_BG = "#0e1117"
CARD_BG = "#161b22"
GREEN = "#26a69a"
RED = "#ef5350"
ACCENT = "#4fc3f7"

# ----------------------------------------------------------------------------
# App
# ----------------------------------------------------------------------------
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG],
    title="Morindok Dashboard",
)
server = app.server


def kpi_card(title, value, color=ACCENT, sub=None):
    return dbc.Card(
        dbc.CardBody([
            html.Div(title, style={"fontSize": "13px", "color": "#9aa4b2"}),
            html.Div(value, style={"fontSize": "26px", "fontWeight": "700", "color": color}),
            html.Div(sub or "", style={"fontSize": "12px", "color": "#6b7684"}),
        ]),
        style={"backgroundColor": CARD_BG, "border": "1px solid #262c36", "textAlign": "center"},
    )


def build_header():
    return dbc.Navbar(
        dbc.Container([
            dbc.Row([
                dbc.Col(html.Div([
                    html.Span("Morindok", style={"fontWeight": "800", "fontSize": "22px", "color": ACCENT}),
                    html.Span("  |  داشبورد آنالیز جریان سرمایه و قدرت بازار",
                               style={"fontSize": "14px", "color": "#9aa4b2"}),
                ]), width="auto"),
                dbc.Col(html.Div(id="connection-status-badge"), width="auto", className="ms-auto"),
            ], align="center", className="w-100 g-2"),
        ], fluid=True),
        color=CARD_BG, dark=True, style={"borderBottom": "1px solid #262c36", "marginBottom": "14px"},
    )


def connection_status_content():
    status = be.get_connection_status()
    connected = status.get("connected")
    color = GREEN if connected else RED
    text = f"متصل ({status.get('active_host', '—')})" if connected else "قطع از بایبیت"
    badge = dbc.Badge(
        [html.Span("● ", style={"color": color}), text],
        color="dark", style={"fontSize": "13px", "border": f"1px solid {color}"},
    )
    if not connected and status.get("last_error"):
        return html.Div([
            badge,
            html.Div(status["last_error"], style={"fontSize": "11px", "color": RED, "maxWidth": "420px",
                                                     "marginTop": "4px"}),
        ])
    return badge


def symbol_selector(dropdown_id):
    return dcc.Dropdown(
        id=dropdown_id, options=SYMBOL_OPTIONS, value="BTCUSDT",
        clearable=False, style={"direction": "ltr", "color": "#000"},
    )


# ----------------------------------------------------------------------------
# تب اول: تحلیل و آنالیز
# ----------------------------------------------------------------------------
tab1_layout = dbc.Container([
    dbc.Row([
        dbc.Col([html.Label("انتخاب ارز:"), symbol_selector("tab1-symbol")], width=3),
        dbc.Col([html.Label("بروزرسانی خودکار:"),
                 dcc.Interval(id="tab1-interval", interval=15000, n_intervals=0)], width=3),
    ], className="mb-3"),

    dbc.Row(id="tab1-kpi-row", className="mb-3"),

    dbc.Row([
        dbc.Col(dcc.Loading(dcc.Graph(id="price-chart", style={"height": "480px"})), width=12),
    ], className="mb-3"),

    dbc.Row([
        dbc.Col([
            html.H5("قدرت خریدار به فروشنده در هر تایم‌فریم (تاثیر از بالا به پایین)", style={"color": "#dfe6ee"}),
            dcc.Loading(dcc.Graph(id="power-cascade-chart", style={"height": "380px"})),
        ], width=7),
        dbc.Col([
            html.H5("چرخش سرمایه از ۳۰ ارز معتبر", style={"color": "#dfe6ee"}),
            dcc.Loading(dcc.Graph(id="money-flow-chart", style={"height": "380px"})),
        ], width=5),
    ], className="mb-3"),

    dbc.Row([
        dbc.Col([
            html.H5("آنالیز عمق حجم (تشخیص حجم مشکوک)", style={"color": "#dfe6ee"}),
            dcc.Loading(dcc.Graph(id="volume-analysis-chart", style={"height": "340px"})),
        ], width=12),
    ], className="mb-3"),
], fluid=True)


# ----------------------------------------------------------------------------
# تب دوم: سیگنال‌های معاملاتی
# ----------------------------------------------------------------------------
tab2_layout = dbc.Container([
    dbc.Row([
        dbc.Col([html.Label("انتخاب ارز از لیست:"), symbol_selector("tab2-symbol")], width=3),
        dbc.Col(dbc.Button("بررسی/تولید سیگنال جدید", id="gen-signal-btn", color="info", className="mt-4"), width=3),
        dbc.Col(dcc.Interval(id="tab2-interval", interval=20000, n_intervals=0), width=1),
    ], className="mb-3"),
    html.Div(id="signal-gen-msg", style={"color": ACCENT, "marginBottom": "10px"}),
    html.H5("سیگنال‌های باز", style={"color": "#dfe6ee"}),
    html.Div(id="open-signals-cards", className="mb-4"),
    html.H5("تاریخچه‌ی اخیر سیگنال‌های بسته‌شده", style={"color": "#dfe6ee"}),
    html.Div(id="closed-signals-table"),
], fluid=True)


# ----------------------------------------------------------------------------
# تب سوم: وین‌ریت و آمار
# ----------------------------------------------------------------------------
tab3_layout = dbc.Container([
    dbc.Row([
        dbc.Col([html.Label("انتخاب ارز:"), symbol_selector("tab3-symbol")], width=3),
        dbc.Col(dcc.Interval(id="tab3-interval", interval=30000, n_intervals=0), width=1),
    ], className="mb-3"),
    dbc.Row(id="tab3-kpi-row", className="mb-4"),
    dbc.Row([
        dbc.Col([
            html.H5("منحنی سرمایه (بر حسب R)", style={"color": "#dfe6ee"}),
            dcc.Loading(dcc.Graph(id="equity-curve-chart", style={"height": "360px"})),
        ], width=12),
    ], className="mb-3"),
    html.H5("تاریخچه‌ی کامل معاملات", style={"color": "#dfe6ee"}),
    html.Div(id="all-trades-table"),
], fluid=True)


app.layout = html.Div([
    build_header(),
    dcc.Interval(id="global-status-interval", interval=8000, n_intervals=0),
    dbc.Container([
        dbc.Tabs([
            dbc.Tab(tab1_layout, label="تحلیل و آنالیز", tab_id="tab-1"),
            dbc.Tab(tab2_layout, label="سیگنال‌های معاملاتی", tab_id="tab-2"),
            dbc.Tab(tab3_layout, label="وین‌ریت و آمار", tab_id="tab-3"),
        ], id="main-tabs", active_tab="tab-1"),
    ], fluid=True),
], dir="rtl", style={"backgroundColor": DARK_BG, "minHeight": "100vh",
                      "fontFamily": FONT_FAMILY, "paddingBottom": "40px"})


@app.callback(Output("connection-status-badge", "children"), Input("global-status-interval", "n_intervals"))
def update_connection_badge(_n):
    return connection_status_content()


# ==============================================================================
# Callbacks - تب اول
# ==============================================================================
@app.callback(
    Output("tab1-kpi-row", "children"),
    Output("price-chart", "figure"),
    Output("power-cascade-chart", "figure"),
    Output("money-flow-chart", "figure"),
    Output("volume-analysis-chart", "figure"),
    Input("tab1-symbol", "value"),
    Input("tab1-interval", "n_intervals"),
)
def update_tab1(symbol, _n):
    kdf = be.get_klines(symbol, "15", limit=200)
    last_price = float(kdf["close"].iloc[-1]) if not kdf.empty else 0.0
    chg = 0.0
    if len(kdf) > 1:
        chg = (kdf["close"].iloc[-1] / kdf["close"].iloc[-2] - 1) * 100

    composite, details = se.composite_power_score(STREAM, symbol)
    power_color = GREEN if composite > 0 else RED if composite < 0 else ACCENT
    span_min = STREAM.buffer_span_minutes(symbol)

    kpis = [
        dbc.Col(kpi_card("آخرین قیمت", f"{last_price:,.4f}", ACCENT), width=3),
        dbc.Col(kpi_card("تغییر کندل اخیر", f"{chg:+.2f}%", GREEN if chg >= 0 else RED), width=3),
        dbc.Col(kpi_card("نمره‌ی ترکیبی قدرت خرید/فروش", f"{composite:+.1f}", power_color,
                          "خرید غالب" if composite > 0 else "فروش غالب" if composite < 0 else "خنثی"), width=3),
        dbc.Col(kpi_card("عمق دیتای زنده", f"{span_min:.0f} دقیقه", ACCENT,
                          "هرچه بیشتر، محاسبه دقیق‌تر"), width=3),
    ]

    # نمودار قیمت
    price_fig = go.Figure()
    if not kdf.empty:
        price_fig.add_trace(go.Candlestick(
            x=kdf["time"], open=kdf["open"], high=kdf["high"], low=kdf["low"], close=kdf["close"],
            increasing_line_color=GREEN, decreasing_line_color=RED, name=symbol,
        ))
    price_fig.update_layout(
        template="plotly_dark", plot_bgcolor=DARK_BG, paper_bgcolor=DARK_BG,
        margin=dict(l=10, r=10, t=30, b=10), xaxis_rangeslider_visible=False,
        title=f"نمودار قیمت {symbol} (تایم‌فریم ۱۵ دقیقه)", font=dict(family=FONT_FAMILY),
    )

    # نمودار کاسکید قدرت روی تایم‌فریم‌ها (از بالا به پایین: روزانه در بالا)
    tf_order = list(reversed(be.TIMEFRAMES))
    labels = [d[1] for d in tf_order]
    values = [details.get(d[0], {}).get("power_pct", 0.0) for d in tf_order]
    sources = [details.get(d[0], {}).get("source", "") for d in tf_order]
    colors = [GREEN if v > 0 else RED if v < 0 else "#555" for v in values]
    cascade_fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", marker_color=colors,
        text=[f"{v:+.1f}  ({s})" for v, s in zip(values, sources)], textposition="outside",
    ))
    cascade_fig.update_layout(
        template="plotly_dark", plot_bgcolor=DARK_BG, paper_bgcolor=DARK_BG,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="قدرت خریدار(+) / فروشنده(-)", font=dict(family=FONT_FAMILY),
    )

    # نمودار چرخش سرمایه
    flow_df = be.money_flow_from_top30(STREAM, symbol)
    flow_fig = go.Figure()
    if not flow_df.empty:
        top = flow_df.head(12)
        flow_colors = [GREEN if v > 0 else RED for v in top["net_flow_usdt"]]
        flow_fig.add_trace(go.Bar(
            x=top["net_flow_usdt"], y=top["symbol"], orientation="h", marker_color=flow_colors,
            text=[f"lag={l} | corr={c}" for l, c in zip(top["lag_bars"], top["correlation"])],
            textposition="outside",
        ))
        flow_fig.update_layout(xaxis_title="جریان نقدی خالص (دلار، ۳ کندل اخیر)")
    else:
        flow_fig.add_annotation(text="داده‌ی کافی برای تحلیل چرخش سرمایه هنوز جمع نشده\n(نیاز به چند دقیقه استریم زنده)",
                                 showarrow=False, font=dict(color="#9aa4b2"))
    flow_fig.update_layout(
        template="plotly_dark", plot_bgcolor=DARK_BG, paper_bgcolor=DARK_BG,
        margin=dict(l=10, r=10, t=10, b=10), font=dict(family=FONT_FAMILY),
    )

    # آنالیز حجم
    vol_df = be.analyze_volume(kdf) if not kdf.empty else pd.DataFrame()
    vol_fig = make_subplots(specs=[[{"secondary_y": False}]])
    if not vol_df.empty:
        color_map = {"عادی": "#3d5a80", "قابل توجه": "#f4a300", "مشکوک": RED, "در حال محاسبه": "#555"}
        bar_colors = vol_df["vol_status"].map(color_map).fillna("#555")
        vol_fig.add_trace(go.Bar(x=vol_df["time"], y=vol_df["volume"], marker_color=bar_colors,
                                  name="حجم", text=vol_df["vol_status"], hovertemplate="%{text}<extra></extra>"))
    vol_fig.update_layout(
        template="plotly_dark", plot_bgcolor=DARK_BG, paper_bgcolor=DARK_BG,
        margin=dict(l=10, r=10, t=10, b=10), font=dict(family=FONT_FAMILY),
        title="زرد = قابل توجه | قرمز = مشکوک (احتمال دستکاری/شست‌وشوی حجم)",
    )

    return kpis, price_fig, cascade_fig, flow_fig, vol_fig


# ==============================================================================
# Callbacks - تب دوم (سیگنال‌ها)
# ==============================================================================
def _signal_card(row):
    side = row["side"]
    color = GREEN if side.startswith("خرید") else RED
    return dbc.Card(dbc.CardBody([
        html.Div([
            html.Span(row["symbol"], style={"fontWeight": "800", "fontSize": "18px"}),
            html.Span(f"  {side}", style={"color": color, "fontWeight": "700", "marginRight": "10px"}),
            html.Span(f"  اهرم پیشنهادی: {row['leverage']}x", style={"color": "#9aa4b2", "float": "left"}),
        ]),
        html.Hr(style={"borderColor": "#262c36"}),
        dbc.Row([
            dbc.Col(f"ورود: {row['entry']:.4f}", width=4),
            dbc.Col(f"حد ضرر: {row['sl']:.4f}", width=4, style={"color": RED}),
            dbc.Col(f"حد سود: {row['tp']:.4f}", width=4, style={"color": GREEN}),
        ]),
        html.Div(row["reasons"], style={"fontSize": "13px", "color": "#9aa4b2", "marginTop": "8px"}),
        html.Div(f"زمان صدور: {row['opened_at'][:19].replace('T',' ')}",
                  style={"fontSize": "11px", "color": "#5c6673", "marginTop": "6px"}),
    ]), style={"backgroundColor": CARD_BG, "border": f"1px solid {color}", "marginBottom": "10px"})


@app.callback(
    Output("signal-gen-msg", "children"),
    Input("gen-signal-btn", "n_clicks"),
    State("tab2-symbol", "value"),
    prevent_initial_call=True,
)
def on_generate_signal(n_clicks, symbol):
    result = se.generate_signal(STREAM, symbol)
    if result is None:
        if se.has_open_signal(symbol):
            return "یک سیگنال باز برای این نماد وجود دارد؛ تا رسیدن به حد سود/ضرر سیگنال جدیدی صادر نمی‌شود."
        return "شرایط ورود در حال حاضر برقرار نیست (قدرت/جریان پول/حجم تایید نمی‌کند)."
    return f"سیگنال جدید صادر شد: {result['symbol']} - {result['side']}"


@app.callback(
    Output("open-signals-cards", "children"),
    Output("closed-signals-table", "children"),
    Input("tab2-symbol", "value"),
    Input("tab2-interval", "n_intervals"),
)
def update_tab2(symbol, _n):
    se.check_and_close_open_signals()  # بررسی برخورد قیمت با SL/TP

    open_df = se.get_open_signals(symbol)
    if open_df.empty:
        open_cards = dbc.Alert("سیگنال باز فعالی برای این نماد وجود ندارد.", color="secondary")
    else:
        open_cards = [_signal_card(r) for _, r in open_df.iterrows()]

    closed_df = se.get_closed_signals(symbol).sort_values("closed_at", ascending=False).head(20)
    if closed_df.empty:
        closed_table = dbc.Alert("تاریخچه‌ای برای این نماد ثبت نشده است.", color="secondary")
    else:
        show = closed_df[["symbol", "side", "entry", "sl", "tp", "result", "pnl_r", "closed_at"]].copy()
        show.columns = ["نماد", "جهت", "ورود", "حد ضرر", "حد سود", "نتیجه", "R", "زمان بستن"]
        closed_table = dash_table.DataTable(
            data=show.to_dict("records"), columns=[{"name": c, "id": c} for c in show.columns],
            style_header={"backgroundColor": CARD_BG, "color": ACCENT, "fontWeight": "bold"},
            style_cell={"backgroundColor": DARK_BG, "color": "#dfe6ee", "textAlign": "center",
                        "fontFamily": FONT_FAMILY, "border": "1px solid #262c36"},
            style_data_conditional=[
                {"if": {"filter_query": "{نتیجه} = WIN"}, "color": GREEN},
                {"if": {"filter_query": "{نتیجه} = LOSS"}, "color": RED},
            ],
        )
    return open_cards, closed_table


# ==============================================================================
# Callbacks - تب سوم (وین‌ریت)
# ==============================================================================
@app.callback(
    Output("tab3-kpi-row", "children"),
    Output("equity-curve-chart", "figure"),
    Output("all-trades-table", "children"),
    Input("tab3-symbol", "value"),
    Input("tab3-interval", "n_intervals"),
)
def update_tab3(symbol, _n):
    stats = se.winrate_stats(symbol)
    kpis = [
        dbc.Col(kpi_card("تعداد کل معاملات", stats["total"], ACCENT), width=2),
        dbc.Col(kpi_card("برد", stats["wins"], GREEN), width=2),
        dbc.Col(kpi_card("باخت", stats["losses"], RED), width=2),
        dbc.Col(kpi_card("وین‌ریت", f"{stats['winrate']}%", GREEN if stats["winrate"] >= 50 else RED), width=2),
        dbc.Col(kpi_card("میانگین R برد", stats["avg_rr"], ACCENT), width=2),
        dbc.Col(kpi_card("فاکتور سود", stats["profit_factor"], ACCENT, f"اکسپکتنسی: {stats['expectancy']}R"), width=2),
    ]

    closed_df = se.get_closed_signals(symbol).sort_values("closed_at")
    eq_fig = go.Figure()
    if not closed_df.empty:
        cum = closed_df["pnl_r"].cumsum()
        eq_fig.add_trace(go.Scatter(x=list(range(1, len(cum) + 1)), y=cum,
                                     mode="lines+markers", line=dict(color=ACCENT)))
    eq_fig.update_layout(
        template="plotly_dark", plot_bgcolor=DARK_BG, paper_bgcolor=DARK_BG,
        margin=dict(l=10, r=10, t=10, b=10), xaxis_title="شماره معامله", yaxis_title="سود/زیان تجمعی (R)",
        font=dict(family=FONT_FAMILY),
    )

    if closed_df.empty:
        table = dbc.Alert("هنوز معامله‌ی بسته‌شده‌ای برای این نماد ثبت نشده است.", color="secondary")
    else:
        show = closed_df[["symbol", "side", "entry", "close_price", "result", "pnl_r",
                           "leverage", "opened_at", "closed_at"]].copy()
        show.columns = ["نماد", "جهت", "ورود", "خروج", "نتیجه", "R", "اهرم", "زمان باز شدن", "زمان بسته شدن"]
        table = dash_table.DataTable(
            data=show.to_dict("records"), columns=[{"name": c, "id": c} for c in show.columns],
            page_size=15,
            style_header={"backgroundColor": CARD_BG, "color": ACCENT, "fontWeight": "bold"},
            style_cell={"backgroundColor": DARK_BG, "color": "#dfe6ee", "textAlign": "center",
                        "fontFamily": FONT_FAMILY, "border": "1px solid #262c36"},
            style_data_conditional=[
                {"if": {"filter_query": "{نتیجه} = WIN"}, "color": GREEN},
                {"if": {"filter_query": "{نتیجه} = LOSS"}, "color": RED},
            ],
        )
    return kpis, eq_fig, table


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=8050)