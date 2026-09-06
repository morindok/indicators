# -*- coding: utf-8 -*-
"""
داشبورد زنده مورین‌دوک - تحلیل شبکه تار عنکبوتی + شبکه عصبی عمیق LSTM
+ مسیریابی مونت‌کارلوی چند-مسیره روی داده زنده بایبیت.

اجرا:
    pip install -r requirements.txt
    python app.py
سپس مرورگر را روی http://127.0.0.1:8050 باز کنید.
"""

import pandas as pd
import plotly.graph_objects as go
import dash
from dash import html, dcc, Output, Input
import dash_bootstrap_components as dbc

from config import CONFIG
from engine import Engine

engine = Engine(CONFIG)

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])
app.title = "Morindok Quantum Neural Dashboard"

CARD_STYLE = {"backgroundColor": "#111318", "border": "1px solid #333", "borderRadius": "10px"}


def fmt_pct(x):
    return "—" if x is None else f"{x*100:.1f}%"


def fmt_num(x, digits=2):
    return "—" if x is None else f"{x:.{digits}f}"


def decision_color(label):
    if "صعودی قوی" in label:
        return "#00c853"
    if "صعودی" in label:
        return "#66bb6a"
    if "نزولی قوی" in label:
        return "#d50000"
    if "نزولی" in label:
        return "#ef5350"
    return "#9e9e9e"


def build_table(s):
    rows = [
        ("احتمال نهایی صعود", f"{fmt_num(s['final_probability'],1)}%", s["decision_label"]),
        ("خروجی شبکه عصبی LSTM", fmt_pct(s["neural_prob"]), "بالا" if s["neural_prob"] > 0.5 else "پایین"),
        ("احتمال مونت‌کارلو (چند-مسیره)", fmt_pct(s["montecarlo_prob"]), f"میانگین حرکت {fmt_num(s['expected_move_pct'],2)}%"),
        ("بایاس شبکه تار عنکبوتی", fmt_num(s["grid_bias"], 2), "حمایت" if s["grid_bias"] > 0 else "مقاومت"),
        ("سیگنال ترکیبی", fmt_num(s["combined_signal"], 2), "Neural+MC+Grid"),
        ("دقت واک-فوروارد (درصد برد)", fmt_pct(s["accuracy"]), f"{s['correct']}/{s['total']} نمونه"),
        ("ضریب اطمینان کالیبره", fmt_num(s["confidence_multiplier"], 2), "Calibration"),
        ("مراحل آموزش انجام‌شده", str(s["trained_steps"]), f"Loss={fmt_num(s['train_loss'],4)}"),
        ("کندل‌های موجود", f"{s['bars_available']}/{s['min_bars_required']}", "آماده" if s["enough_data"] else "در حال آموزش"),
    ]
    header = html.Tr([html.Th("شاخص"), html.Th("مقدار"), html.Th("وضعیت")])
    body = []
    for name, val, status in rows:
        body.append(html.Tr([
            html.Td(name, style={"color": "#ccc", "padding": "8px"}),
            html.Td(val, style={"color": "#00e5ff", "fontWeight": "bold", "padding": "8px", "textAlign": "center"}),
            html.Td(status, style={"color": "#aaa", "padding": "8px", "textAlign": "center", "fontSize": "12px"}),
        ]))
    return dbc.Table([html.Thead(header), html.Tbody(body)], bordered=True, color="dark", hover=True, size="sm")


def build_chart(df: pd.DataFrame, s):
    fig = go.Figure()
    if df is not None and len(df) > 0:
        recent = df.tail(150)
        fig.add_trace(go.Candlestick(
            x=recent["timestamp"], open=recent["open"], high=recent["high"],
            low=recent["low"], close=recent["close"], name="قیمت",
            increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        ))

        percentiles = s.get("path_percentiles")
        if percentiles is not None and len(recent) > 0:
            last_ts = recent["timestamp"].iloc[-1]
            step = (recent["timestamp"].iloc[-1] - recent["timestamp"].iloc[-2]) if len(recent) > 1 else pd.Timedelta(minutes=5)
            future_x = [last_ts + step * (i + 1) for i in range(len(percentiles["p50"]))]

            fig.add_trace(go.Scatter(x=future_x, y=percentiles["p90"], line=dict(color="rgba(0,229,255,0.25)"),
                                      name="سقف ۹۰٪ مسیرها", showlegend=False))
            fig.add_trace(go.Scatter(x=future_x, y=percentiles["p10"], line=dict(color="rgba(0,229,255,0.25)"),
                                      fill="tonexty", fillcolor="rgba(0,229,255,0.10)",
                                      name="کف ۱۰٪ مسیرها", showlegend=False))
            fig.add_trace(go.Scatter(x=future_x, y=percentiles["p50"], line=dict(color="#ffd600", dash="dot", width=2),
                                      name="مسیر میانه (Monte Carlo)"))

    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#111318", plot_bgcolor="#111318",
        margin=dict(l=10, r=10, t=30, b=10), height=520,
        xaxis_rangeslider_visible=False,
        title=f"{CONFIG['symbol']} — کندل زنده + مخروط پیش‌بینی چند-مسیره ({CONFIG['horizon']} کندل جلوتر)",
    )
    return fig


app.layout = html.Div(style={"backgroundColor": "#0a0b0e", "minHeight": "100vh", "padding": "20px", "direction": "rtl", "fontFamily": "Tahoma"}, children=[
    html.H2("🧠 داشبورد کوانتومی مورین‌دوک — تحلیل زنده", style={"color": "#00e5ff", "textAlign": "center"}),
    html.Div(id="status-bar", style={"textAlign": "center", "color": "#aaa", "marginBottom": "15px"}),
    dbc.Row([
        dbc.Col(dcc.Graph(id="price-chart"), width=8),
        dbc.Col(html.Div(id="live-table"), width=4),
    ]),
    dcc.Interval(id="refresh-interval", interval=CONFIG["dash_refresh_ms"], n_intervals=0),
])


@app.callback(
    Output("status-bar", "children"),
    Output("live-table", "children"),
    Output("price-chart", "figure"),
    Input("refresh-interval", "n_intervals"),
)
def refresh(_n):
    s = engine.state.snapshot()
    df = engine.feed.get_df()

    conn_dot = "🟢" if s["connected"] else "🔴"
    price_txt = f"{s['price']:,.1f}" if s["price"] else "—"
    last_update = s["last_update"].strftime("%H:%M:%S UTC") if s["last_update"] else "—"
    status_children = html.Span([
        f"{conn_dot}  {s['symbol'] or CONFIG['symbol']}   |   قیمت: {price_txt} USDT   |   ",
        html.Span(s["decision_label"], style={"color": decision_color(s["decision_label"]), "fontWeight": "bold"}),
        f"   |   آخرین به‌روزرسانی: {last_update}   |   وضعیت اتصال: {s['status']}",
    ])

    return status_children, build_table(s), build_chart(df, s)


if __name__ == "__main__":
    engine.start()
    app.run(debug=False, host="127.0.0.1", port=CONFIG["dash_port"])
