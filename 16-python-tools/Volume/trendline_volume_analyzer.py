# -*- coding: utf-8 -*-
"""
🌙 Bybit Trendline Volume Analyzer
------------------------------------------------------------------
کاربر روی چارت کندل‌استیک، ترندلاین (یا چند ترندلاین) رسم می‌کند.
برای هر خط، اسکریپت حجم معاملات کندل‌های «بالای خط» و «پایین خط» را
محاسبه کرده و آن را به تفکیک خرید (کندل سبز) و فروش (کندل قرمز) نمایش می‌دهد.
یک دکمه هم برای پاک‌کردن همه خطوط رسم‌شده وجود دارد.

⚠️ نکته صادقانه: دیتای کندل بایبیت (endpoint کلاین) حجم خرید/فروش واقعی
(Taker Buy/Sell) را جدا نمی‌دهد. به همین دلیل «خرید» و «فروش» بر اساس
جهت کندل (close >= open = خرید، در غیر این‌صورت = فروش) تفکیک شده که
یک پروکسی رایج و معتبر است، نه دیتای اردر فلو خام.

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

# ==============================================================================
# 0) پالت رنگی تیره (هماهنگ با اسکریپت اصلی BITMOON)
# ==============================================================================
BG, CARD, LINE, TXT, MUT = "#0b1220", "#121c30", "#23314d", "#e8ecf4", "#8fa3c0"
GOLD, UP, DN = "#f0b90b", "#16a085", "#e74c3c"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_CATEGORY = "linear"
DEFAULT_INTERVAL = "15"

# ==============================================================================
# 1) اتصال REST پایدار به بایبیت — دقیقاً به روش اسکریپت اصلی
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
# 2) محاسبه حجم خرید/فروش بالا و پایین هر ترندلاین
# ==============================================================================
def _line_y_at_x(x0, y0, x1, y1, x):
    """مقدار y روی خط راست (x0,y0)-(x1,y1) به ازای x دلخواه؛ x بر حسب epoch میلی‌ثانیه."""
    if x1 == x0:
        return y0
    t = (x - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


def analyze_trendlines(df, shapes):
    """
    برای هر خط رسم‌شده (shape از نوع line) روی چارت:
      - فقط کندل‌های داخل بازه‌ی افقی خودِ خط (بین x0 و x1) در نظر گرفته می‌شوند
        (نه اکستراپوله تا بی‌نهایت) تا با گذشت زمان عدد به‌طور نامحدود عوض نشود.
      - کندل آخر که هنوز بسته نشده از محاسبه حذف می‌شود تا مقدار فقط با
        close‌شدن کندل جدید تغییر کند، نه لحظه‌به‌لحظه با نوسان قیمت زنده.
      - کندل‌هایی که close آن‌ها بالای خط است => گروه «بالا»
      - کندل‌هایی که close آن‌ها پایین خط است => گروه «پایین»
      - در هر گروه، حجم به خرید (close>=open) و فروش (close<open) تفکیک و دلتا حساب می‌شود.
    خروجی: لیستی از دیکشنری، یکی برای هر خط.
    """
    if df.empty or not shapes:
        return []

    # کندل آخر (بسته‌نشده) را کنار می‌گذاریم تا محاسبه لحظه‌به‌لحظه تغییر نکند
    df_closed = df.iloc[:-1] if len(df) > 2 else df

    x_ms_all = (df_closed["ts"].astype("int64") // 10**6).to_numpy(dtype=float)
    is_buy = (df_closed["close"] >= df_closed["open"]).to_numpy()
    is_sell = ~is_buy
    volume = df_closed["volume"].to_numpy()
    close = df_closed["close"].to_numpy()

    results = []
    line_no = 0
    for sh in shapes:
        if sh.get("type") != "line":
            continue
        try:
            x0 = pd.Timestamp(sh["x0"]).value // 10**6
            x1 = pd.Timestamp(sh["x1"]).value // 10**6
            y0, y1 = float(sh["y0"]), float(sh["y1"])
        except Exception:
            continue

        line_no += 1
        x_lo, x_hi = (x0, x1) if x0 <= x1 else (x1, x0)

        # فقط کندل‌های داخل بازه‌ی افقی خودِ خط (نه فراتر از آن)
        in_range = (x_ms_all >= x_lo) & (x_ms_all <= x_hi)
        if not in_range.any():
            results.append({
                "line_no": line_no,
                "above_buy": 0.0, "above_sell": 0.0, "below_buy": 0.0, "below_sell": 0.0,
                "above_delta": 0.0, "below_delta": 0.0, "net_delta": 0.0,
            })
            continue

        line_y = _line_y_at_x(x0, y0, x1, y1, x_ms_all[in_range])
        seg_close = close[in_range]
        seg_buy = is_buy[in_range]
        seg_sell = is_sell[in_range]
        seg_vol = volume[in_range]

        above = seg_close > line_y
        below = ~above

        above_buy = float(seg_vol[above & seg_buy].sum())
        above_sell = float(seg_vol[above & seg_sell].sum())
        below_buy = float(seg_vol[below & seg_buy].sum())
        below_sell = float(seg_vol[below & seg_sell].sum())

        above_delta = above_buy - above_sell      # دلتای بالای خط: خریدار منهای فروشنده
        below_delta = below_buy - below_sell       # دلتای پایین خط: خریدار منهای فروشنده
        net_delta = above_delta - below_delta       # دلتای حاصل: تفاوت دلتای بالا و پایین از هم

        results.append({
            "line_no": line_no,
            "above_buy": above_buy, "above_sell": above_sell,
            "below_buy": below_buy, "below_sell": below_sell,
            "above_delta": above_delta, "below_delta": below_delta,
            "net_delta": net_delta,
        })
    return results


def _fmt(v):
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1_000_000:
        return f"{sign}{v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"{sign}{v/1_000:.2f}K"
    return f"{sign}{v:.2f}"


def _delta_color(v):
    return UP if v > 0 else (DN if v < 0 else MUT)


def build_volume_panel(results):
    if not results:
        return dbc.Alert("برای مشاهده تحلیل حجم، یک ترندلاین روی چارت رسم کنید (از ابزار ✏️ در نوار بالای چارت).",
                          color="secondary", style={"fontSize": 13})

    cards = []
    for r in results:
        cards.append(
            dbc.Card(dbc.CardBody([
                html.Div(f"📏 ترندلاین #{r['line_no']}", style={"color": GOLD, "fontWeight": "bold", "marginBottom": 8}),
                dbc.Row([
                    dbc.Col([
                        html.Div("بالای خط", style={"color": MUT, "fontSize": 12, "marginBottom": 4}),
                        html.Div(f"🟢 خرید: {_fmt(r['above_buy'])}", style={"color": UP, "fontSize": 13}),
                        html.Div(f"🔴 فروش: {_fmt(r['above_sell'])}", style={"color": DN, "fontSize": 13}),
                        html.Div(f"Δ دلتا: {_fmt(r['above_delta'])}",
                                 style={"color": _delta_color(r['above_delta']), "fontSize": 13, "fontWeight": "bold", "marginTop": 4}),
                    ], width=6),
                    dbc.Col([
                        html.Div("پایین خط", style={"color": MUT, "fontSize": 12, "marginBottom": 4}),
                        html.Div(f"🟢 خرید: {_fmt(r['below_buy'])}", style={"color": UP, "fontSize": 13}),
                        html.Div(f"🔴 فروش: {_fmt(r['below_sell'])}", style={"color": DN, "fontSize": 13}),
                        html.Div(f"Δ دلتا: {_fmt(r['below_delta'])}",
                                 style={"color": _delta_color(r['below_delta']), "fontSize": 13, "fontWeight": "bold", "marginTop": 4}),
                    ], width=6),
                ]),
                html.Hr(style={"borderColor": LINE, "margin": "8px 0"}),
                html.Div([
                    html.Span("دلتای حاصل (بالا − پایین): ", style={"color": MUT, "fontSize": 12}),
                    html.Span(_fmt(r['net_delta']),
                              style={"color": _delta_color(r['net_delta']), "fontSize": 14, "fontWeight": "bold"}),
                ]),
            ]), style={"background": CARD, "border": f"1px solid {LINE}", "marginBottom": 10})
        )
    return html.Div(cards)


# ==============================================================================
# 3) اپ Dash
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])
app.title = "Trendline Volume Analyzer"
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
        dbc.Col(dbc.Button("🗑 حذف همه ترندلاین‌ها", id="clear-btn", color="danger", className="mt-3",
                           style={"fontWeight": "bold", "width": "100%"}), md=2),
        dbc.Col(html.Div(id="conn-status", style={"color": MUT, "fontSize": 11, "marginTop": 22, "textAlign": "center"}), md=2),
    ])), style={"maxWidth": 1200, "margin": "10px auto"}),

    dbc.Row([
        dbc.Col(dcc.Graph(id="candle-chart", style={"height": "72vh"},
                          config={"modeBarButtonsToAdd": ["drawline", "eraseshape"],
                                  "displaylogo": False}), width=8),
        dbc.Col([
            html.H5("📊 حجم خرید/فروش بالا و پایین ترندلاین‌ها", style={"color": GOLD, "fontSize": 14, "margin": "8px 0"}),
            html.Div(id="volume-panel"),
        ], width=4),
    ], style={"maxWidth": 1200, "margin": "0 auto"}),

    # ذخیره‌سازی خطوط رسم‌شده تا بین رفرش‌های خودکار قیمت از بین نروند
    dcc.Store(id="shapes-store", data=[]),
    dcc.Interval(id="refresh-interval", interval=15_000, n_intervals=0),
], style={"background": BG, "minHeight": "100vh", "padding": "10px"})


# ==============================================================================
# 4) کال‌بک اصلی: دریافت کندل، مدیریت رسم/حذف خط، محاسبه حجم
# ==============================================================================
@app.callback(
    Output("candle-chart", "figure"),
    Output("shapes-store", "data"),
    Output("volume-panel", "children"),
    Output("conn-status", "children"),
    Input("refresh-interval", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    Input("clear-btn", "n_clicks"),
    Input("candle-chart", "relayoutData"),
    State("symbol-input", "value"),
    State("interval-dropdown", "value"),
    State("category-dropdown", "value"),
    State("shapes-store", "data"),
)
def update_chart(n_int, n_refresh, n_clear, relayout, symbol, interval, category, stored_shapes):
    stored_shapes = list(stored_shapes or [])
    trigger = ctx.triggered_id

    if trigger == "clear-btn":
        stored_shapes = []

    elif trigger == "candle-chart" and relayout:
        if "shapes" in relayout:
            # خط جدید اضافه شد یا با ابزار eraseshape حذف شد -> کل آرایه شکل‌ها آمده
            stored_shapes = relayout["shapes"]
        else:
            # جابجایی (درگ) یک نقطه از یک خط موجود -> کلیدهایی مثل shapes[0].x0 می‌آید
            for key, val in relayout.items():
                if key.startswith("shapes[") and "." in key:
                    try:
                        idx = int(key.split("[")[1].split("]")[0])
                        field = key.split(".", 1)[1]
                        if idx < len(stored_shapes):
                            stored_shapes[idx][field] = val
                    except Exception:
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

    fig = go.Figure(data=[go.Candlestick(
        x=df["ts"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color=UP, decreasing_line_color=DN, name=symbol,
    )])
    fig.update_layout(
        shapes=stored_shapes,
        dragmode="drawline",
        newshape=dict(line_color=GOLD, line_width=2),
        template="plotly_dark",
        paper_bgcolor=BG, plot_bgcolor=CARD,
        font=dict(color=TXT),
        xaxis=dict(gridcolor=LINE, rangeslider_visible=False),
        yaxis=dict(gridcolor=LINE),
        margin=dict(l=10, r=10, t=40, b=10),
        title=dict(text=f"{symbol} — {category} — {interval}", x=0.5, font=dict(color=GOLD, size=14)),
    )

    results = analyze_trendlines(df, stored_shapes)
    panel = build_volume_panel(results)
    status = f"🟢 متصل | {pd.Timestamp.now().strftime('%H:%M:%S')}"

    return fig, stored_shapes, panel, status


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8060, use_reloader=False)
