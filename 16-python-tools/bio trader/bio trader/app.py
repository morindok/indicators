"""Dash interface for the BioTrader 2500 demo organism."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import dash
import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, ctx, dcc, html
from plotly.subplots import make_subplots

from biotrader import BioTradingEngine, clamp, safe_float


BG = "#07111f"
PANEL = "#0d1a2d"
PANEL_2 = "#10233a"
LINE = "#1e3b58"
TEXT = "#e6f5ff"
MUTED = "#7c9ab5"
CYAN = "#48e7ff"
MINT = "#53f7b2"
GOLD = "#f5c451"
RED = "#ff647f"
PURPLE = "#b987ff"


def money(value: Any, digits: int = 2) -> str:
    return f"${safe_float(value):,.{digits}f}"


def number(value: Any, digits: int = 2) -> str:
    value = safe_float(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.{digits}f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.{digits}f}K"
    return f"{value:.{digits}f}"


def price(value: Any) -> str:
    value = safe_float(value)
    if value >= 1000:
        return f"{value:,.1f}"
    if value >= 1:
        return f"{value:,.3f}"
    if value >= 0.01:
        return f"{value:,.5f}"
    return f"{value:,.8f}"


def pct(value: Any, digits: int = 1) -> str:
    return f"{safe_float(value):+.{digits}f}%"


def color_for(value: float, neutral: str = MUTED) -> str:
    value = safe_float(value)
    return MINT if value > 0 else RED if value < 0 else neutral


def panel(children: Any, title: str | None = None, icon: str = "◌", class_name: str = "") -> html.Div:
    head = (
        html.Div(
            [
                html.Span(icon, className="panel-icon"),
                html.Span(title or "", className="panel-title"),
            ],
            className="panel-heading",
        )
        if title
        else None
    )
    return html.Div([head, children] if head else children, className=f"hud-panel {class_name}".strip())


def metric_card(label: str, value: Any, sub: str, icon: str, value_color: str = TEXT) -> html.Div:
    return html.Div(
        [
            html.Div([html.Span(icon, className="metric-icon"), html.Span(label)], className="metric-label"),
            html.Div(value, className="metric-value", style={"color": value_color}),
            html.Div(sub, className="metric-sub"),
        ],
        className="metric-card",
    )


def gauge(value: float, label: str = "", color: str = CYAN) -> html.Div:
    value = clamp(safe_float(value))
    return html.Div(
        [
            html.Div(
                html.Div(style={"width": f"{value * 100:.1f}%", "background": color}),
                className="gauge-track",
            ),
            html.Div(
                [html.Span(label), html.Span(f"{value * 100:.0f}%")],
                className="gauge-caption",
            ),
        ],
        className="mini-gauge",
    )


def render_bio_core(state: dict[str, Any]) -> html.Div:
    heartbeat = int(safe_float(state.get("heartbeat"), 72))
    awareness = clamp(safe_float(state.get("awareness"), 0.7))
    stress = clamp(safe_float(state.get("stress"), 0.2))
    mood = str(state.get("mood", "پایش"))
    return html.Div(
        [
            html.Div(className="pulse-ring ring-one"),
            html.Div(className="pulse-ring ring-two"),
            html.Div(className="pulse-ring ring-three"),
            html.Div(
                [
                    html.Div("BIO", className="core-kicker"),
                    html.Div(f"{heartbeat}", className="core-heart"),
                    html.Div("BPM", className="core-unit"),
                    html.Div(mood, className="core-mood"),
                ],
                className="bio-core-disc",
            ),
            html.Div(
                [
                    html.Span("آگاهی", className="core-stat-label"),
                    html.Span(f"{awareness * 100:.0f}%", className="core-stat-value"),
                ],
                className="core-stat core-stat-left",
            ),
            html.Div(
                [
                    html.Span("استرس", className="core-stat-label"),
                    html.Span(f"{stress * 100:.0f}%", className="core-stat-value"),
                ],
                className="core-stat core-stat-right",
            ),
        ],
        className="bio-core",
    )


def render_organs(organs: list[dict[str, Any]]) -> html.Div:
    cards = []
    for organ in organs:
        value = clamp(safe_float(organ.get("value")))
        color = RED if organ.get("name") == "سیستم درد" else CYAN
        cards.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(organ.get("icon", "◌"), className="organ-icon"),
                            html.Span(organ.get("name", ""), className="organ-name"),
                        ],
                        className="organ-head",
                    ),
                    html.Div(organ.get("detail", ""), className="organ-detail"),
                    gauge(value, color=color),
                ],
                className="organ-card",
            )
        )
    return html.Div(cards, className="organ-grid")


def render_genome(genome: list[dict[str, Any]]) -> html.Div:
    rows = []
    for gene in genome:
        mutation = safe_float(gene.get("mutation"))
        expression = safe_float(gene.get("expression"))
        rows.append(
            html.Tr(
                [
                    html.Td(gene.get("label", ""), className="gene-label"),
                    html.Td(gene.get("key", "").upper(), className="gene-key"),
                    html.Td(
                        [
                            html.Div(
                                html.Div(
                                    style={
                                        "width": f"{min(100, mutation * 100):.0f}%",
                                        "background": PURPLE,
                                    }
                                ),
                                className="gene-bar",
                            ),
                            html.Span(f"جهش {mutation * 100:.0f}%"),
                        ],
                        className="gene-mutation",
                    ),
                    html.Td(f"{expression:.2f}×", className="gene-expression"),
                ]
            )
        )
    return html.Table(
        [
            html.Thead(html.Tr([html.Th("ژن"), html.Th("کد"), html.Th("جهش"), html.Th("بیان")])),
            html.Tbody(rows),
        ],
        className="data-table genome-table",
    )


def render_candidates(candidates: list[dict[str, Any]]) -> html.Div:
    if not candidates:
        return html.Div("هنوز ادراکی ثبت نشده است.", className="empty-state")
    rows = []
    for rank, item in enumerate(candidates[:12], 1):
        side = str(item.get("side", ""))
        quality = safe_float(item.get("quality"))
        confidence = safe_float(item.get("confidence"))
        rows.append(
            html.Tr(
                [
                    html.Td(f"{rank:02d}", className="rank-cell"),
                    html.Td(item.get("symbol", ""), className="symbol-cell"),
                    html.Td(
                        html.Span(
                            "خرید" if side == "LONG" else "فروش",
                            className=f"side-pill {'long' if side == 'LONG' else 'short'}",
                        )
                    ),
                    html.Td(f"{quality:.0f}", className="score-cell"),
                    html.Td(f"{confidence * 100:.0f}%", className="confidence-cell"),
                    html.Td(item.get("regime", "—"), className="regime-cell"),
                    html.Td(price(item.get("entry")), className="price-cell"),
                ]
            )
        )
    return html.Table(
        [
            html.Thead(html.Tr([html.Th("#"), html.Th("نماد"), html.Th("جهت"), html.Th("امتیاز"), html.Th("اعتماد"), html.Th("رژیم"), html.Th("ورود")])),
            html.Tbody(rows),
        ],
        className="data-table",
    )


def render_positions(
    positions: list[dict[str, Any]], summary: dict[str, Any] | None = None
) -> html.Div:
    if not positions:
        return html.Div("در حال ساختن پنج اتصال عصبی به بازار…", className="empty-state")
    rows = []
    for item in positions:
        pnl = safe_float(item.get("pnl"))
        side = str(item.get("side", ""))
        rows.append(
            html.Tr(
                [
                    html.Td(item.get("symbol", ""), className="symbol-cell"),
                    html.Td(html.Span("L" if side == "LONG" else "S", className=f"side-mini {'long' if side == 'LONG' else 'short'}")),
                    html.Td(price(item.get("entry")), className="price-cell"),
                    html.Td(price(item.get("tp")), className="price-cell target-cell"),
                    html.Td(price(item.get("sl")), className="price-cell stop-cell"),
                    html.Td(money(pnl), style={"color": color_for(pnl)}, className="pnl-cell"),
                ]
            )
        )
    table = html.Table(
        [
            html.Thead(
                html.Tr(
                    [
                        html.Th("نماد"),
                        html.Th("جهت"),
                        html.Th("ورود"),
                        html.Th("TP"),
                        html.Th("SL"),
                        html.Th("PnL"),
                    ]
                )
            ),
            html.Tbody(rows),
        ],
        className="data-table",
    )
    if not summary:
        return table
    return html.Div(
        [
            html.Div(
                [
                    html.Span(f"مارجین {money(summary.get('used_margin'), 0)} / {money(summary.get('initial_balance'), 0)}"),
                    html.Span(f"هزینه‌ی ورود/خروج {money(summary.get('fees_paid'))}", className="trade-fee"),
                ],
                className="trade-meta",
            ),
            table,
        ]
    )


def render_event_stream(snapshot: dict[str, Any]) -> html.Div:
    events: list[html.Div] = []
    for item in snapshot.get("closed", [])[-5:][::-1]:
        realized = safe_float(item.get("realized_pnl"))
        events.append(
            html.Div(
                [
                    html.Span("●", className="event-dot", style={"color": color_for(realized)}),
                    html.Span(item.get("symbol", ""), className="event-symbol"),
                    html.Span(item.get("exit_reason", "چرخه"), className="event-text"),
                    html.Span(money(realized), className="event-pnl", style={"color": color_for(realized)}),
                ],
                className="event-row",
            )
        )
    if not events:
        events.append(
            html.Div(
                "سیستم آماده است؛ هر اسکن یک چرخه‌ی عصبی جدید را ثبت می‌کند.",
                className="event-empty",
            )
        )
    return html.Div(events, className="event-stream")


def dark_layout(fig: go.Figure, title: str = "") -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=PANEL,
        font={"family": "Vazirmatn, Segoe UI, sans-serif", "color": TEXT, "size": 11},
        margin={"l": 12, "r": 12, "t": 42 if title else 12, "b": 12},
        title={"text": title, "x": 0.02, "font": {"size": 13, "color": CYAN}} if title else None,
        legend={"orientation": "h", "y": 1.02, "x": 0, "font": {"size": 10}},
        hoverlabel={"bgcolor": PANEL_2, "font": {"color": TEXT}},
    )
    fig.update_xaxes(gridcolor=LINE, zerolinecolor=LINE, showgrid=True)
    fig.update_yaxes(gridcolor=LINE, zerolinecolor=LINE, showgrid=True)
    return fig


def make_candle_figure(
    frame: pd.DataFrame, symbol: str, positions: list[dict[str, Any]]
) -> go.Figure:
    if frame.empty:
        return dark_layout(go.Figure(), "داده‌ی کندلی در دسترس نیست")
    df = frame.tail(120).copy()
    fast = df["close"].ewm(span=9, adjust=False).mean()
    slow = df["close"].ewm(span=26, adjust=False).mean()
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.75, 0.25],
    )
    fig.add_trace(
        go.Candlestick(
            x=df["ts"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name=symbol,
            increasing_line_color=MINT,
            increasing_fillcolor="rgba(83,247,178,.42)",
            decreasing_line_color=RED,
            decreasing_fillcolor="rgba(255,100,127,.42)",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(go.Scatter(x=df["ts"], y=fast, name="EMA 9", line={"color": GOLD, "width": 1.4}), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["ts"], y=slow, name="EMA 26", line={"color": PURPLE, "width": 1.2}), row=1, col=1)
    volume_colors = [MINT if c >= o else RED for o, c in zip(df["open"], df["close"])]
    fig.add_trace(
        go.Bar(x=df["ts"], y=df["volume"], name="حجم", marker_color=volume_colors, opacity=0.6),
        row=2,
        col=1,
    )
    for position in positions:
        if position.get("symbol") != symbol:
            continue
        side_color = MINT if position.get("side") == "LONG" else RED
        fig.add_hline(y=safe_float(position.get("entry")), line_color=CYAN, line_dash="dot", row=1, col=1, annotation_text="ورود")
        fig.add_hline(y=safe_float(position.get("tp")), line_color=MINT, line_dash="dash", row=1, col=1, annotation_text="TP")
        fig.add_hline(y=safe_float(position.get("sl")), line_color=RED, line_dash="dash", row=1, col=1, annotation_text="SL")
        fig.add_annotation(
            x=df["ts"].iloc[-1],
            y=safe_float(position.get("mark")),
            text=f"{position.get('side')} / {money(position.get('pnl'))}",
            showarrow=True,
            arrowcolor=side_color,
            font={"color": side_color, "size": 10},
            row=1,
            col=1,
        )
    fig.update_layout(xaxis_rangeslider_visible=False, hovermode="x unified")
    fig.update_yaxes(title_text="قیمت", row=1, col=1)
    fig.update_yaxes(title_text="حجم", row=2, col=1, showticklabels=False)
    return dark_layout(fig, f"{symbol}  ·  ادراک شبکیه / 5m")


def make_radar_figure(candidates: list[dict[str, Any]]) -> go.Figure:
    categories = ["روند", "مومنتوم", "حجم", "همگرایی", "نقدشوندگی", "ایمنی"]
    fig = go.Figure()
    palette = [CYAN, MINT, GOLD, PURPLE, "#ff9f68"]
    for idx, item in enumerate(candidates[:5]):
        senses = item.get("senses", {}) or {}
        values = [
            abs(safe_float(senses.get("retina"))),
            abs(safe_float(senses.get("intuition"))),
            abs(safe_float(senses.get("cochlea"))),
            safe_float(item.get("consensus")),
            safe_float(item.get("liquidity")),
            1 - safe_float(item.get("volatility")),
        ]
        values = [max(0.04, min(1.0, value)) for value in values]
        fig.add_trace(
            go.Scatterpolar(
                r=values + [values[0]],
                theta=categories + [categories[0]],
                name=f"{item.get('symbol')} · {item.get('side')}",
                line={"color": palette[idx % len(palette)], "width": 1.7},
                fill="toself" if idx == 0 else None,
                opacity=0.72,
            )
        )
    fig.update_layout(
        polar={
            "bgcolor": "rgba(0,0,0,0)",
            "radialaxis": {"visible": True, "range": [0, 1], "gridcolor": LINE, "tickfont": {"color": MUTED, "size": 8}},
            "angularaxis": {"gridcolor": LINE, "tickfont": {"color": TEXT, "size": 10}},
        },
        showlegend=True,
    )
    return dark_layout(fig, "رادار حواس فرابشری")


def make_equity_figure(curve: list[dict[str, Any]]) -> go.Figure:
    fig = go.Figure()
    if curve:
        x = list(range(len(curve)))
        y = [safe_float(item.get("equity")) for item in curve]
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                name="Equity",
                line={"color": CYAN, "width": 2.4},
                fill="tozeroy",
                fillcolor="rgba(72,231,255,.08)",
            )
        )
    return dark_layout(fig, "هومئوستاز سرمایه / Equity")


def symbol_options(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    options = []
    seen: set[str] = set()
    for item in snapshot.get("candidates", []):
        symbol = str(item.get("symbol", ""))
        if symbol and symbol not in seen:
            options.append({"label": symbol, "value": symbol})
            seen.add(symbol)
    return options


engine = BioTradingEngine()
initial_snapshot = engine.snapshot()
initial_options = symbol_options(initial_snapshot)
initial_symbol = initial_options[0]["value"] if initial_options else "BTCUSDT"


app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG],
    suppress_callback_exceptions=True,
)
app.title = "BIO•TRADER 2500"
server = app.server


app.layout = html.Div(
    [
        dcc.Interval(id="market-interval", interval=15_000, n_intervals=0),
        html.Div(id="app-sentinel", style={"display": "none"}),
        html.Div(
            [
                html.Div(
                    [
                        html.Div("BIO•TRADER", className="brand-mark"),
                        html.Div("ارگانیسم معاملاتی جهش‌یافته / نسخه‌ی 2500", className="brand-sub"),
                    ],
                    className="brand-block",
                ),
                html.Div(
                    [
                        html.Div(id="status-pill", className="status-pill"),
                        html.Div(id="last-scan", className="last-scan"),
                    ],
                    className="status-block",
                ),
                html.Div(
                    [
                        dcc.Dropdown(
                            id="symbol-select",
                            options=initial_options,
                            value=initial_symbol,
                            clearable=False,
                            className="symbol-select",
                            searchable=True,
                        ),
                        dcc.Dropdown(
                            id="refresh-speed",
                            options=[
                                {"label": "۱۰ ثانیه", "value": 10_000},
                                {"label": "۱۵ ثانیه", "value": 15_000},
                                {"label": "۳۰ ثانیه", "value": 30_000},
                            ],
                            value=15_000,
                            clearable=False,
                            className="speed-select",
                        ),
                        dbc.Button("⟳ اسکن", id="manual-scan", className="neon-button"),
                        dbc.Button("↺ تولد دوباره", id="reset-organism", className="ghost-button"),
                    ],
                    className="control-strip",
                ),
            ],
            className="topbar",
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.Div("سامانه‌ی ادراک و اجرای دمو", className="hero-kicker"),
                        html.H1(
                            [
                                html.Span("ذهنی که بازار را "),
                                html.Span("حس می‌کند"),
                            ],
                            className="hero-title",
                        ),
                        html.P(
                            "هفت حس بازار، ژن‌های جهش‌یافته، کنترل درد و انضباط سرمایه؛ "
                            "تمام معاملات این پنل کاغذی و قابل ممیزی هستند.",
                            className="hero-copy",
                        ),
                        html.Div(
                            [
                                html.Span("● داده‌ی عمومی Bybit", className="hero-tag"),
                                html.Span("● اهرم شبیه‌سازی ۱۵×", className="hero-tag"),
                                html.Span("● سرمایه‌ی پایه $500", className="hero-tag"),
                            ],
                            className="hero-tags",
                        ),
                    ],
                    className="hero-copy-block",
                ),
                html.Div(id="organism-core", children=render_bio_core(initial_snapshot["organism"]["state"]), className="hero-core-block"),
            ],
            className="hero-section",
        ),
        html.Div(
            [
                html.Div(id="kpi-equity"),
                html.Div(id="kpi-pnl"),
                html.Div(id="kpi-heart"),
                html.Div(id="kpi-awareness"),
                html.Div(id="kpi-positions"),
                html.Div(id="kpi-mode"),
            ],
            className="metric-grid",
        ),
        html.Div(
            [
                panel(
                    dcc.Graph(
                        id="candle-chart",
                        figure=make_candle_figure(engine.candles_for(initial_symbol), initial_symbol, initial_snapshot["positions"]),
                        config={"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]},
                        style={"height": "480px"},
                    ),
                    "مرکز فرمان شبکیه",
                    "◒",
                    "chart-panel chart-large",
                ),
                panel(
                    dcc.Graph(
                        id="radar-chart",
                        figure=make_radar_figure(initial_snapshot["candidates"]),
                        config={"displaylogo": False},
                        style={"height": "480px"},
                    ),
                    "امضای حسی پنج کاندید",
                    "✧",
                    "chart-panel",
                ),
            ],
            className="main-chart-grid",
        ),
        html.Div(
            [
                panel(html.Div(id="organ-grid", children=render_organs(initial_snapshot["organism"]["organs"])), "اندام‌های زنده", "⟡"),
                panel(html.Div(id="candidate-table", children=render_candidates(initial_snapshot["candidates"])), "اسکنر فرصت‌ها / ۵ برش برتر", "⌁"),
                panel(
                    html.Div(
                        id="position-table",
                        children=render_positions(
                            initial_snapshot["positions"], initial_snapshot["summary"]
                        ),
                    ),
                    "اتاق معاملات دمو",
                    "⬡",
                ),
            ],
            className="three-panel-grid",
        ),
        html.Div(
            [
                panel(html.Div(id="genome-table", children=render_genome(initial_snapshot["organism"]["genome"])), "ژنوم جهش‌یافته", "🧬", "genome-panel"),
                panel(dcc.Graph(id="equity-chart", figure=make_equity_figure(initial_snapshot["equity_curve"]), config={"displaylogo": False}, style={"height": "340px"}), "هومئوستاز سرمایه", "⌇", "equity-panel"),
                panel(html.Div(id="event-stream", children=render_event_stream(initial_snapshot)), "حافظه‌ی رویدادها", "⚡", "event-panel"),
            ],
            className="bottom-grid",
        ),
        html.Div(
            [
                html.Span("اسکن ", className="footer-label"),
                html.Span(id="scan-counter", children=f"#{initial_snapshot['scan_id']}"),
                html.Span("  ·  این محیط فقط برای پژوهش و معاملات نمایشی است؛ هیچ سفارش واقعی ارسال نمی‌شود.", className="footer-note"),
            ],
            className="footer-bar",
        ),
    ],
    className="bio-shell",
    dir="rtl",
)


@app.callback(
    Output("market-interval", "interval"),
    Input("refresh-speed", "value"),
)
def update_interval(value: int | None) -> int:
    return int(value or 15_000)


@app.callback(
    Output("status-pill", "children"),
    Output("last-scan", "children"),
    Output("organism-core", "children"),
    Output("kpi-equity", "children"),
    Output("kpi-pnl", "children"),
    Output("kpi-heart", "children"),
    Output("kpi-awareness", "children"),
    Output("kpi-positions", "children"),
    Output("kpi-mode", "children"),
    Output("candle-chart", "figure"),
    Output("radar-chart", "figure"),
    Output("equity-chart", "figure"),
    Output("organ-grid", "children"),
    Output("candidate-table", "children"),
    Output("position-table", "children"),
    Output("genome-table", "children"),
    Output("event-stream", "children"),
    Output("symbol-select", "options"),
    Output("symbol-select", "value"),
    Output("scan-counter", "children"),
    Input("market-interval", "n_intervals"),
    Input("manual-scan", "n_clicks"),
    Input("reset-organism", "n_clicks"),
    Input("symbol-select", "value"),
    State("symbol-select", "options"),
    prevent_initial_call=False,
)
def refresh_dashboard(
    n_intervals: int,
    manual_clicks: int | None,
    reset_clicks: int | None,
    selected_symbol: str | None,
    existing_options: list[dict[str, str]] | None,
):
    trigger = ctx.triggered_id
    if trigger == "reset-organism":
        engine.reset()
    elif trigger in {"manual-scan", "market-interval"}:
        # The first render already has a seeded synthetic frame.  Subsequent
        # ticks attempt public Bybit data and automatically fall back if needed.
        if trigger == "manual-scan" or int(n_intervals or 0) > 0:
            engine.scan(force=trigger == "manual-scan", prefer_live=True)

    snapshot = engine.snapshot()
    options = symbol_options(snapshot)
    if not options:
        options = existing_options or [{"label": "BTCUSDT", "value": "BTCUSDT"}]
    available = {item["value"] for item in options}
    selected = selected_symbol if selected_symbol in available else options[0]["value"]
    state = snapshot["organism"]["state"]
    summary = snapshot["summary"]
    selected_frame = engine.candles_for(selected)

    status_color = MINT if snapshot["mode"] == "live" else GOLD
    status = html.Span(
        [
            html.Span("●", className="status-dot", style={"color": status_color}),
            html.Span("LIVE / Bybit" if snapshot["mode"] == "live" else "SIM / fallback"),
        ],
        className="status-inner",
    )
    last_scan = snapshot.get("last_scan") or ""
    try:
        stamp = datetime.fromisoformat(last_scan).astimezone().strftime("%H:%M:%S")
    except Exception:
        stamp = "--:--:--"

    equity = safe_float(summary["equity"])
    unrealised = safe_float(summary["unrealised"])
    return (
        status,
        f"چرخه‌ی آخر {stamp}",
        render_bio_core(state),
        metric_card("ارزش خالص", money(equity), f"موجودی {money(summary['balance'])}", "◈", CYAN),
        metric_card(
            "PnL شناور",
            money(unrealised),
            f"خالص بسته‌شده {money(summary.get('closed_net'))} · هزینه {money(summary.get('fees_paid'))}",
            "↗",
            color_for(unrealised),
        ),
        metric_card("ضربان ارگانیسم", f"{int(safe_float(state['heartbeat']))} BPM", str(state["mood"]), "♥", RED),
        metric_card("خودآگاهی", f"{safe_float(state['awareness']) * 100:.0f}%", f"تمرکز {safe_float(state['focus']) * 100:.0f}%", "◎", PURPLE),
        metric_card("اتصالات فعال", f"{summary['open_positions']} / {summary['slots']}", f"برد بسته‌شده {summary['win_rate']:.0f}%", "⬡", MINT),
        metric_card("سرمایه / اهرم", money(summary["initial_balance"], 0), f"{summary['leverage']}× · دمو", "₿", GOLD),
        make_candle_figure(selected_frame, selected, snapshot["positions"]),
        make_radar_figure(snapshot["candidates"]),
        make_equity_figure(snapshot["equity_curve"]),
        render_organs(snapshot["organism"]["organs"]),
        render_candidates(snapshot["candidates"]),
        render_positions(snapshot["positions"], summary),
        render_genome(snapshot["organism"]["genome"]),
        render_event_stream(snapshot),
        options,
        selected,
        f"#{snapshot['scan_id']} · {snapshot['mode']}",
    )


if __name__ == "__main__":
    app.run(
        debug=os.getenv("DASH_DEBUG", "0") == "1",
        host=os.getenv("DASH_HOST", "0.0.0.0"),
        port=int(os.getenv("DASH_PORT", "8060")),
        use_reloader=False,
    )
