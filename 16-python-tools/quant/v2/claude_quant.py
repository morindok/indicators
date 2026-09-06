# -*- coding: utf-8 -*-
r"""
CLAUDE QUANT — Bybit Live Quant Trading System
================================================================
یک داشبورد کوانت زنده روی دیتای بایبیت (v5) با:
  - اتصال پایدار REST (چند دامنه جایگزین + هدر مرورگر) دقیقا مثل اسکریپت پایه
  - موتور سیگنال کوانت چندعاملی (مومنتوم + بازگشت به میانگین + شکست + فیلتر نوسان)
  - بک‌تست زنده روی کندل‌ها و نمایش «وین‌ریت واقعی اندازه‌گیری‌شده» (نه عدد جعلی)
  - پنل‌های ویدئو: چارت کندل + حجم، ماتریس همبستگی، طیف سیگنال (heatmap)،
    گراف نیرو (live force)، تطبیق‌گر آنالوگ (Analogue Matcher)، آمار پایین
  - تب «معاملات لایو» با حالت کاغذی (Paper) پیش‌فرض و امکان ثبت سفارش واقعی
    روی Bybit v5 با کلید API (Testnet/Mainnet) — امضای HMAC.

هشدار امنیتی: ثبت سفارش واقعی پول واقعی جابه‌جا می‌کند. حالت پیش‌فرض Paper است.
برای معامله واقعی باید کلید/سکرت را دستی وارد و تیک تایید را بزنید.

نصب:
    pip install dash dash-bootstrap-components plotly pandas numpy requests
اجرا:
    python claude_quant.py
    http://127.0.0.1:8060
"""

import time
import hmac
import hashlib
import json
import numpy as np
import pandas as pd
import requests
import dash
from dash import dcc, html, Input, Output, State, ctx, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

# ==============================================================================
# 0) پالت رنگی
# ==============================================================================
BG, CARD, LINE, TXT, MUT = "#0b1220", "#121c30", "#23314d", "#e8ecf4", "#8fa3c0"
GOLD, UP, DN = "#f0b90b", "#16a085", "#e74c3c"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_CATEGORY = "linear"
DEFAULT_INTERVAL = "15"
CORR_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]

# ==============================================================================
# 1) اتصال REST پایدار به بایبیت (روش اسکریپت پایه)
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
    df["ts"] = pd.to_datetime(df["ts"].astype(np.int64), unit="ms")
    for c in ["open", "high", "low", "close", "volume", "turnover"]:
        df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)


# ==============================================================================
# 2) موتور سیگنال کوانت چندعاملی
# ==============================================================================
def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0.0)
    dn = -d.clip(upper=0.0)
    rs = up.ewm(alpha=1 / n, adjust=False).mean() / (dn.ewm(alpha=1 / n, adjust=False).mean() + 1e-12)
    return 100 - 100 / (1 + rs)


def _atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def compute_features(df):
    """اندیکاتورهای پایه را به دیتافریم اضافه می‌کند."""
    out = df.copy()
    out["ema_fast"] = _ema(out["close"], 20)
    out["ema_slow"] = _ema(out["close"], 50)
    out["rsi"] = _rsi(out["close"], 14)
    out["atr"] = _atr(out, 14)
    out["ret"] = out["close"].pct_change()
    out["vol_z"] = (out["volume"] - out["volume"].rolling(30).mean()) / (out["volume"].rolling(30).std() + 1e-12)
    out["mom"] = out["close"].pct_change(10)
    # انحراف از میانگین (بازگشت به میانگین)
    ma = out["close"].rolling(20).mean()
    sd = out["close"].rolling(20).std() + 1e-12
    out["zscore"] = (out["close"] - ma) / sd
    # شکست کانال دوناچیان
    out["hh"] = out["high"].rolling(20).max()
    out["ll"] = out["low"].rolling(20).min()
    return out


def quant_signal(row_feats):
    """
    امتیاز کوانت در بازه [-1, +1] از ترکیب چند عامل.
    +  مومنتوم/ترند صعودی، شکست سقف، حجم بالا  => لانگ
    -  ترند نزولی، اشباع خرید افراطی، شکست کف   => شورت
    """
    score = 0.0
    # 1) ترند (EMA)
    if row_feats["ema_fast"] > row_feats["ema_slow"]:
        score += 0.35
    else:
        score -= 0.35
    # 2) مومنتوم
    score += float(np.tanh((row_feats["mom"] or 0.0) * 25)) * 0.30
    # 3) بازگشت به میانگین (zscore منفی = ارزان => امتیاز مثبت کوچک)
    z = row_feats["zscore"] if pd.notna(row_feats["zscore"]) else 0.0
    score += float(np.clip(-z, -1.5, 1.5)) * 0.12
    # 4) تایید حجم
    vz = row_feats["vol_z"] if pd.notna(row_feats["vol_z"]) else 0.0
    score += float(np.tanh(vz)) * 0.10
    # 5) شکست کانال
    if pd.notna(row_feats["hh"]) and row_feats["close"] >= row_feats["hh"]:
        score += 0.13
    if pd.notna(row_feats["ll"]) and row_feats["close"] <= row_feats["ll"]:
        score -= 0.13
    return float(np.clip(score, -1.0, 1.0))


def backtest_winrate(df, thr=0.15):
    """
    بک‌تست ساده: در هر کندل بسته سیگنال محاسبه می‌شود؛ اگر |score|>=thr
    یک معامله در جهت سیگنال باز و در کندل بعد بسته می‌شود.
    خروجی: وین‌ریت واقعی، تعداد معاملات، میانگین بازده هر معامله.
    """
    feats = compute_features(df).dropna().reset_index(drop=True)
    if len(feats) < 30:
        return {"winrate": None, "trades": 0, "avg_ret": 0.0, "signal": 0.0, "equity": []}
    wins = 0
    trades = 0
    rets = []
    equity = [1.0]
    for i in range(len(feats) - 1):
        s = quant_signal(feats.iloc[i])
        if abs(s) < thr:
            equity.append(equity[-1])
            continue
        direction = 1 if s > 0 else -1
        fwd = (feats["close"].iloc[i + 1] - feats["close"].iloc[i]) / feats["close"].iloc[i]
        pnl = direction * fwd
        trades += 1
        rets.append(pnl)
        if pnl > 0:
            wins += 1
        equity.append(equity[-1] * (1 + pnl))
    winrate = (wins / trades * 100.0) if trades else None
    live_signal = quant_signal(feats.iloc[-1])
    return {
        "winrate": winrate,
        "trades": trades,
        "avg_ret": float(np.mean(rets)) if rets else 0.0,
        "signal": live_signal,
        "equity": equity,
    }


# ==============================================================================
# 3) پنل‌های ویدئو
# ==============================================================================
def fig_candles(df, symbol, interval, category):
    if df.empty:
        return go.Figure(layout=dict(paper_bgcolor=BG, plot_bgcolor=CARD,
            annotations=[dict(text="داده‌ای دریافت نشد", x=0.5, y=0.5, showarrow=False,
                              font=dict(color=DN, size=14))]))
    feats = compute_features(df)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df["ts"], open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], increasing_line_color=UP,
        decreasing_line_color=DN, name=symbol))
    fig.add_trace(go.Scatter(x=feats["ts"], y=feats["ema_fast"], mode="lines",
        line=dict(color=GOLD, width=1), name="EMA20"))
    fig.add_trace(go.Scatter(x=feats["ts"], y=feats["ema_slow"], mode="lines",
        line=dict(color=MUT, width=1), name="EMA50"))
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
        font=dict(color=TXT), xaxis=dict(gridcolor=LINE, rangeslider_visible=False),
        yaxis=dict(gridcolor=LINE), margin=dict(l=10, r=10, t=36, b=10),
        legend=dict(orientation="h", y=1.02, x=0),
        title=dict(text=f"{symbol} — {category} — {interval}", x=0.5,
                   font=dict(color=GOLD, size=14)))
    return fig


def fig_correlation(category, interval):
    frames = {}
    for s in CORR_SYMBOLS:
        d = get_klines(s, interval, category, limit=200)
        if not d.empty:
            frames[s] = d.set_index("ts")["close"].pct_change()
    if len(frames) < 2:
        return go.Figure(layout=dict(paper_bgcolor=BG, plot_bgcolor=CARD))
    mat = pd.DataFrame(frames).dropna().corr()
    fig = go.Figure(data=go.Heatmap(z=mat.values, x=mat.columns, y=mat.index,
        colorscale="RdYlGn", zmid=0, zmin=-1, zmax=1,
        text=np.round(mat.values, 2), texttemplate="%{text}",
        textfont=dict(size=10)))
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
        font=dict(color=TXT), margin=dict(l=10, r=10, t=30, b=10),
        title=dict(text="ماتریس همبستگی", x=0.5, font=dict(color=GOLD, size=13)))
    return fig


def fig_signal_spectrum(df):
    """طیف سیگنال: امتیاز کوانت در طول زمان به‌صورت heatmap تک‌ردیفه."""
    feats = compute_features(df).dropna().reset_index(drop=True)
    if feats.empty:
        return go.Figure(layout=dict(paper_bgcolor=BG, plot_bgcolor=CARD))
    scores = [quant_signal(feats.iloc[i]) for i in range(len(feats))]
    fig = go.Figure(data=go.Heatmap(z=[scores], x=feats["ts"], colorscale="RdYlGn",
        zmid=0, zmin=-1, zmax=1, showscale=True, colorbar=dict(title="score")))
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
        font=dict(color=TXT), margin=dict(l=10, r=10, t=30, b=10), height=160,
        yaxis=dict(showticklabels=False),
        title=dict(text="طیف سیگنال (Signal Spectrum)", x=0.5, font=dict(color=GOLD, size=13)))
    return fig


def fig_force_graph(df):
    """گراف نیرو: دلتای حجم جهت‌دار (خرید منهای فروش) به‌صورت خط پرشده."""
    if df.empty:
        return go.Figure(layout=dict(paper_bgcolor=BG, plot_bgcolor=CARD))
    d = df.copy()
    signed = np.where(d["close"] >= d["open"], d["volume"], -d["volume"])
    force = pd.Series(signed).rolling(5).mean()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["ts"], y=force, mode="lines", fill="tozeroy",
        line=dict(color=GOLD, width=1.5), name="Force"))
    fig.add_hline(y=0, line=dict(color=MUT, width=1))
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
        font=dict(color=TXT), margin=dict(l=10, r=10, t=30, b=10), height=200,
        title=dict(text="گراف نیرو (Live Force)", x=0.5, font=dict(color=GOLD, size=13)))
    return fig


def analogue_matcher(df, window=20):
    """
    تطبیق‌گر آنالوگ: الگوی نرمال‌شده‌ی آخرین N کندل را با تمام پنجره‌های
    گذشته مقایسه و شبیه‌ترین را پیدا می‌کند؛ سپس حرکت پس از آن الگو را
    به‌عنوان پیش‌بینی برمی‌گرداند.
    """
    close = df["close"].to_numpy()
    if len(close) < window * 3:
        return {"similarity": None, "forecast": 0.0, "match_idx": None}

    def norm(a):
        a = np.asarray(a, dtype=float)
        return (a - a.mean()) / (a.std() + 1e-12)

    cur = norm(close[-window:])
    best_i, best_d = None, 1e18
    for i in range(len(close) - 2 * window):
        seg = norm(close[i:i + window])
        dist = float(np.mean((seg - cur) ** 2))
        if dist < best_d:
            best_d, best_i = dist, i
    if best_i is None:
        return {"similarity": None, "forecast": 0.0, "match_idx": None}
    nxt_i = best_i + window
    fwd = 0.0
    if nxt_i + 1 < len(close):
        fwd = float((close[nxt_i + 1] - close[nxt_i]) / close[nxt_i] * 100.0)
    similarity = float(max(0.0, 100.0 - best_d * 100.0))
    return {"similarity": similarity, "forecast": fwd, "match_idx": int(best_i)}


# ==============================================================================
# 4) معاملات لایو — امضای Bybit v5 (Paper پیش‌فرض)
# ==============================================================================
def bybit_signed_post(path, body, api_key, api_secret, testnet=False, timeout=10):
    base = "https://api-testnet.bybit.com" if testnet else "https://api.bybit.com"
    ts = str(int(time.time() * 1000))
    recv = "5000"
    body_str = json.dumps(body, separators=(",", ":"))
    pre = ts + api_key + recv + body_str
    sign = hmac.new(api_secret.encode(), pre.encode(), hashlib.sha256).hexdigest()
    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-TIMESTAMP": ts,
        "X-BAPI-RECV-WINDOW": recv,
        "X-BAPI-SIGN": sign,
        "Content-Type": "application/json",
    }
    try:
        r = requests.post(base + path, data=body_str, headers=headers, timeout=timeout)
        return r.json()
    except Exception as e:
        return {"retCode": -1, "retMsg": str(e)}


def place_order(symbol, side, qty, category, paper, api_key, api_secret, testnet):
    """side: 'Buy'|'Sell'. در حالت paper فقط شبیه‌سازی می‌کند."""
    if paper or not api_key or not api_secret:
        px = None
        d = get_klines(symbol, "1", category, limit=1)
        if not d.empty:
            px = float(d["close"].iloc[-1])
        return {"paper": True, "symbol": symbol, "side": side, "qty": qty,
                "price": px, "ts": pd.Timestamp.now().strftime("%H:%M:%S")}
    body = {"category": category, "symbol": symbol, "side": side,
            "orderType": "Market", "qty": str(qty)}
    resp = bybit_signed_post("/v5/order/create", body, api_key, api_secret, testnet)
    return {"paper": False, "resp": resp, "ts": pd.Timestamp.now().strftime("%H:%M:%S")}


# ==============================================================================
# 5) اپ Dash
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG],
                suppress_callback_exceptions=True)
app.title = "CLAUDE QUANT"
server = app.server

CATEGORY_OPTS = [{"label": v, "value": v} for v in ["linear", "spot", "inverse"]]
INTERVAL_OPTS = [{"label": lbl, "value": val} for lbl, val in [
    ("1m", "1"), ("3m", "3"), ("5m", "5"), ("15m", "15"),
    ("30m", "30"), ("1h", "60"), ("4h", "240"), ("1D", "D")]]


def stat_card(title, value_id, sub=""):
    return dbc.Card(dbc.CardBody([
        html.Div(title, style={"color": MUT, "fontSize": 11}),
        html.Div(id=value_id, style={"color": GOLD, "fontSize": 20, "fontWeight": "bold"}),
        html.Div(sub, style={"color": MUT, "fontSize": 10}),
    ]), style={"background": CARD, "border": f"1px solid {LINE}"})


controls = dbc.Card(dbc.CardBody(dbc.Row([
    dbc.Col([html.Label("نماد", style={"fontSize": 12, "color": MUT}),
             dcc.Input(id="symbol-input", value=DEFAULT_SYMBOL, type="text",
                       style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
    dbc.Col([html.Label("بازار", style={"fontSize": 12, "color": MUT}),
             dcc.Dropdown(id="category-dropdown", value=DEFAULT_CATEGORY, clearable=False,
                          options=CATEGORY_OPTS)], md=2),
    dbc.Col([html.Label("تایم‌فریم", style={"fontSize": 12, "color": MUT}),
             dcc.Dropdown(id="interval-dropdown", value=DEFAULT_INTERVAL, clearable=False,
                          options=INTERVAL_OPTS)], md=2),
    dbc.Col([html.Label("آستانه سیگنال", style={"fontSize": 12, "color": MUT}),
             dcc.Slider(id="thr-slider", min=0.05, max=0.6, step=0.05, value=0.15,
                        marks=None, tooltip={"placement": "bottom"})], md=3),
    dbc.Col(dbc.Button("بروزرسانی", id="refresh-btn", color="warning", className="mt-3",
                       style={"fontWeight": "bold", "color": BG, "width": "100%"}), md=1),
    dbc.Col(html.Div(id="conn-status", style={"color": MUT, "fontSize": 11,
            "marginTop": 22, "textAlign": "center"}), md=2),
])), style={"maxWidth": 1400, "margin": "8px auto"})


dashboard_tab = html.Div([
    dbc.Row([
        dbc.Col(stat_card("موجودی (Equity بک‌تست)", "kpi-equity"), md=3),
        dbc.Col(stat_card("وین‌ریت واقعی", "kpi-winrate", "اندازه‌گیری‌شده روی دیتای زنده"), md=3),
        dbc.Col(stat_card("سیگنال زنده", "kpi-signal"), md=3),
        dbc.Col(stat_card("تعداد معاملات بک‌تست", "kpi-trades"), md=3),
    ], style={"maxWidth": 1400, "margin": "6px auto"}),
    dbc.Row([
        dbc.Col(dcc.Graph(id="candle-chart", style={"height": "48vh"},
                          config={"displaylogo": False}), md=8),
        dbc.Col(dcc.Graph(id="corr-heatmap", style={"height": "48vh"},
                          config={"displaylogo": False}), md=4),
    ], style={"maxWidth": 1400, "margin": "0 auto"}),
    dbc.Row([
        dbc.Col(dcc.Graph(id="signal-spectrum", config={"displaylogo": False}), md=6),
        dbc.Col(dcc.Graph(id="force-graph", config={"displaylogo": False}), md=6),
    ], style={"maxWidth": 1400, "margin": "0 auto"}),
    dbc.Row([
        dbc.Col(html.Div(id="analogue-panel"), md=6),
        dbc.Col(html.Div(id="bottom-stats"), md=6),
    ], style={"maxWidth": 1400, "margin": "0 auto"}),
])


live_tab = html.Div([
    dbc.Card(dbc.CardBody([
        html.H5("معاملات لایو", style={"color": GOLD}),
        dbc.Alert("حالت پیش‌فرض «کاغذی (Paper)» است و هیچ سفارش واقعی ثبت نمی‌کند. "
                  "برای معامله واقعی باید کلید API را وارد و تیک «تایید معامله واقعی» را بزنید. "
                  "توصیه: ابتدا روی Testnet آزمایش کنید.",
                  color="warning", style={"fontSize": 12}),
        dbc.Row([
            dbc.Col([html.Label("API Key", style={"color": MUT, "fontSize": 12}),
                     dcc.Input(id="api-key", type="password", placeholder="اختیاری (فقط برای معامله واقعی)",
                               style={"width": "100%", "padding": 6})], md=4),
            dbc.Col([html.Label("API Secret", style={"color": MUT, "fontSize": 12}),
                     dcc.Input(id="api-secret", type="password", placeholder="اختیاری",
                               style={"width": "100%", "padding": 6})], md=4),
            dbc.Col([html.Label("محیط", style={"color": MUT, "fontSize": 12}),
                     dcc.Dropdown(id="net-dropdown", clearable=False, value="testnet",
                                  options=[{"label": "Testnet", "value": "testnet"},
                                           {"label": "Mainnet (واقعی)", "value": "mainnet"}])], md=4),
        ]),
        html.Hr(style={"borderColor": LINE}),
        dbc.Row([
            dbc.Col([html.Label("حجم (qty)", style={"color": MUT, "fontSize": 12}),
                     dcc.Input(id="order-qty", type="number", value=0.001, min=0,
                               style={"width": "100%", "padding": 6})], md=3),
            dbc.Col(dbc.Checklist(id="paper-toggle", switch=True,
                    options=[{"label": " حالت کاغذی (Paper)", "value": "paper"}],
                    value=["paper"], style={"color": TXT, "marginTop": 26}), md=3),
            dbc.Col(dbc.Checklist(id="confirm-live", switch=True,
                    options=[{"label": " تایید معامله واقعی", "value": "yes"}],
                    value=[], style={"color": DN, "marginTop": 26}), md=3),
            dbc.Col(html.Div(id="live-signal-badge", style={"marginTop": 26,
                    "textAlign": "center"}), md=3),
        ]),
        html.Br(),
        dbc.Row([
            dbc.Col(dbc.Button("خرید / LONG", id="buy-btn", color="success",
                    style={"width": "100%", "fontWeight": "bold"}), md=6),
            dbc.Col(dbc.Button("فروش / SHORT", id="sell-btn", color="danger",
                    style={"width": "100%", "fontWeight": "bold"}), md=6),
        ]),
        html.Hr(style={"borderColor": LINE}),
        html.H6("گزارش سفارش‌ها", style={"color": MUT}),
        html.Div(id="order-log"),
    ]), style={"background": CARD, "border": f"1px solid {LINE}",
               "maxWidth": 1000, "margin": "10px auto"}),
])


app.layout = html.Div([
    html.Div([
        html.Span("CLAUDE QUANT", style={"color": GOLD, "fontSize": 22, "fontWeight": "bold"}),
        html.Span(id="header-clock", style={"color": MUT, "fontSize": 12, "marginRight": 16, "float": "left"}),
    ], style={"maxWidth": 1400, "margin": "8px auto", "padding": "4px 12px"}),
    controls,
    dcc.Tabs(id="tabs", value="dash", children=[
        dcc.Tab(label="داشبورد کوانت", value="dash",
                style={"background": CARD, "color": TXT, "border": f"1px solid {LINE}"},
                selected_style={"background": BG, "color": GOLD, "border": f"1px solid {GOLD}"}),
        dcc.Tab(label="معاملات لایو", value="live",
                style={"background": CARD, "color": TXT, "border": f"1px solid {LINE}"},
                selected_style={"background": BG, "color": GOLD, "border": f"1px solid {GOLD}"}),
    ]),
    html.Div(id="tab-content"),
    dcc.Store(id="order-store", data=[]),
    dcc.Interval(id="tick", interval=15_000, n_intervals=0),
], style={"background": BG, "minHeight": "100vh", "padding": "6px"})


@app.callback(Output("tab-content", "children"), Input("tabs", "value"))
def render_tab(tab):
    return live_tab if tab == "live" else dashboard_tab


# --- کال‌بک اصلی داشبورد ---
@app.callback(
    Output("candle-chart", "figure"),
    Output("corr-heatmap", "figure"),
    Output("signal-spectrum", "figure"),
    Output("force-graph", "figure"),
    Output("analogue-panel", "children"),
    Output("bottom-stats", "children"),
    Output("kpi-equity", "children"),
    Output("kpi-winrate", "children"),
    Output("kpi-signal", "children"),
    Output("kpi-trades", "children"),
    Output("conn-status", "children"),
    Output("header-clock", "children"),
    Input("tick", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    Input("tabs", "value"),
    State("symbol-input", "value"),
    State("interval-dropdown", "value"),
    State("category-dropdown", "value"),
    State("thr-slider", "value"),
)
def update_dashboard(n, nr, tab, symbol, interval, category, thr):
    if tab != "dash":
        return (no_update,) * 12
    symbol = (symbol or DEFAULT_SYMBOL).upper()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL
    thr = thr or 0.15
    clock = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

    df = get_klines(symbol, interval, category, limit=500)
    if df.empty:
        empty = go.Figure(layout=dict(paper_bgcolor=BG, plot_bgcolor=CARD,
            annotations=[dict(text="اتصال به بایبیت ناموفق بود", x=0.5, y=0.5,
                              showarrow=False, font=dict(color=DN, size=14))]))
        return (empty, empty, empty, empty, no_update, no_update,
                "-", "-", "-", "-", "قطع", clock)

    bt = backtest_winrate(df, thr=thr)
    ana = analogue_matcher(df)

    # پنل آنالوگ
    if ana["similarity"] is None:
        analogue = dbc.Alert("داده کافی برای تطبیق آنالوگ نیست.", color="secondary", style={"fontSize": 12})
    else:
        fc = ana["forecast"]
        analogue = dbc.Card(dbc.CardBody([
            html.Div("تطبیق‌گر آنالوگ", style={"color": GOLD, "fontWeight": "bold"}),
            html.Div(f"شباهت به الگوی تاریخی: {ana['similarity']:.1f}%", style={"color": TXT, "fontSize": 13}),
            html.Div(f"پیش‌بینی حرکت بعدی: {fc:+.2f}%",
                     style={"color": UP if fc >= 0 else DN, "fontSize": 15, "fontWeight": "bold"}),
        ]), style={"background": CARD, "border": f"1px solid {LINE}"})

    sig = bt["signal"]
    strength = abs(sig) * 100.0
    pulse = float(compute_features(df)["rsi"].iloc[-1]) if len(df) > 15 else 50.0
    bottom = dbc.Card(dbc.CardBody([
        html.Div("آمار پایین", style={"color": GOLD, "fontWeight": "bold"}),
        dbc.Row([
            dbc.Col(html.Div([html.Div("قدرت سیگنال", style={"color": MUT, "fontSize": 11}),
                     html.Div(f"{strength:.0f}%", style={"color": GOLD, "fontSize": 16})]), md=4),
            dbc.Col(html.Div([html.Div("پالس (RSI)", style={"color": MUT, "fontSize": 11}),
                     html.Div(f"{pulse:.0f}", style={"color": GOLD, "fontSize": 16})]), md=4),
            dbc.Col(html.Div([html.Div("امتیاز تطبیق", style={"color": MUT, "fontSize": 11}),
                     html.Div(f"{(ana['similarity'] or 0):.0f}", style={"color": GOLD, "fontSize": 16})]), md=4),
        ]),
    ]), style={"background": CARD, "border": f"1px solid {LINE}"})

    eq = bt["equity"][-1] if bt["equity"] else 1.0
    equity_txt = f"{eq * 100:.1f} (پایه 100)"
    winrate_txt = f"{bt['winrate']:.1f}%" if bt["winrate"] is not None else "—"
    sig_dir = "LONG" if sig > thr else ("SHORT" if sig < -thr else "خنثی")
    signal_txt = f"{sig:+.2f} ({sig_dir})"
    trades_txt = str(bt["trades"])

    return (
        fig_candles(df, symbol, interval, category),
        fig_correlation(category, interval),
        fig_signal_spectrum(df),
        fig_force_graph(df),
        analogue, bottom,
        equity_txt, winrate_txt, signal_txt, trades_txt,
        "متصل", clock,
    )


# --- بج سیگنال زنده در تب معاملات ---
@app.callback(
    Output("live-signal-badge", "children"),
    Input("tick", "n_intervals"),
    Input("tabs", "value"),
    State("symbol-input", "value"),
    State("interval-dropdown", "value"),
    State("category-dropdown", "value"),
    State("thr-slider", "value"),
)
def live_signal_badge(n, tab, symbol, interval, category, thr):
    if tab != "live":
        return no_update
    symbol = (symbol or DEFAULT_SYMBOL).upper()
    df = get_klines(symbol, interval or "15", category or "linear", limit=300)
    if df.empty:
        return html.Span("سیگنال: —", style={"color": MUT})
    bt = backtest_winrate(df, thr=thr or 0.15)
    s = bt["signal"]
    thr = thr or 0.15
    color = UP if s > thr else (DN if s < -thr else MUT)
    label = "LONG" if s > thr else ("SHORT" if s < -thr else "خنثی")
    return html.Span(f"سیگنال زنده: {label} ({s:+.2f})",
                     style={"color": color, "fontWeight": "bold"})


# --- ثبت سفارش ---
@app.callback(
    Output("order-log", "children"),
    Output("order-store", "data"),
    Input("buy-btn", "n_clicks"),
    Input("sell-btn", "n_clicks"),
    State("symbol-input", "value"),
    State("category-dropdown", "value"),
    State("order-qty", "value"),
    State("paper-toggle", "value"),
    State("confirm-live", "value"),
    State("api-key", "value"),
    State("api-secret", "value"),
    State("net-dropdown", "value"),
    State("order-store", "data"),
    prevent_initial_call=True,
)
def submit_order(nb, ns, symbol, category, qty, paper_val, confirm_val, api_key,
                 api_secret, net, store):
    trig = ctx.triggered_id
    if trig not in ("buy-btn", "sell-btn"):
        return no_update, no_update
    store = list(store or [])
    symbol = (symbol or DEFAULT_SYMBOL).upper()
    category = category or DEFAULT_CATEGORY
    qty = qty or 0.001
    side = "Buy" if trig == "buy-btn" else "Sell"
    paper = ("paper" in (paper_val or [])) or not (api_key and api_secret) or ("yes" not in (confirm_val or []))
    testnet = (net or "testnet") == "testnet"

    res = place_order(symbol, side, qty, category, paper, api_key, api_secret, testnet)
    if res.get("paper"):
        line = f"[{res['ts']}] PAPER {side} {qty} {symbol} @ {res.get('price')}"
        color = UP if side == "Buy" else DN
    else:
        rc = res.get("resp", {}).get("retCode")
        msg = res.get("resp", {}).get("retMsg", "")
        env = "TESTNET" if testnet else "MAINNET"
        line = f"[{res['ts']}] REAL/{env} {side} {qty} {symbol} -> retCode={rc} {msg}"
        color = UP if rc == 0 else DN
    store.insert(0, {"line": line, "color": color})
    store = store[:30]
    log = [html.Div(item["line"], style={"color": item["color"], "fontSize": 12,
           "fontFamily": "monospace"}) for item in store]
    return html.Div(log), store


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8060, use_reloader=False)
