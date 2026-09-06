# -*- coding: utf-8 -*-
"""
🌙 3D CHAIN REVERSAL TERMINAL — ادغام ساختار 3بعدی زنجیره‌ای + تاییدیه MA/RSI
----------------------------------------------------------------------
معماری:
  • موتور داده: اتصال REST پایدار به Bybit با fallback.
  • موتور 3بعدی: محاسبه Dominant Period برای HH/LL از دوره 1 تا 200.
  • موتور سیگنال: تلاقی شکست ساختار 3بعدی + فرمول‌های برداری MA و RSI.
  
⚠️ صداقت علمی: مدل «تلاقی 100%» یک هیوریستیک آماری بر اساس هم‌افزایی 3 لایه است.
در بازارهای مالی قطعیت مطلق وجود ندارد؛ مدیریت ریسک همواره الزامی است.
"""

import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import requests
import time
import warnings
warnings.filterwarnings('ignore')

# ==============================================================================
# 1) اتصال REST و دریافت داده (Bybit)
# ==============================================================================
REST_CANDIDATES = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

def bybit_get(path, params, timeout=10):
    for base in REST_CANDIDATES:
        try:
            r = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            r.raise_for_status()
            d = r.json()
            if d.get("retCode") == 0: return d
        except Exception: continue
    return None

def get_klines(symbol, interval, category="linear", limit=500):
    d = bybit_get("/v5/market/kline", {"category": category, "symbol": symbol, "interval": interval, "limit": limit})
    if not d or "list" not in (d.get("result") or {}): return pd.DataFrame()
    lst = d["result"]["list"]
    if not lst: return pd.DataFrame()
    df = pd.DataFrame(lst, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
    for c in ["open", "high", "low", "close", "volume"]: df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)

# ==============================================================================
# 2) موتورهای ریاضی (برگرفته از کد شما)
# ==============================================================================
def fast_all_ma(prices, P=200):
    n = len(prices); z = np.zeros((P, n)); c = np.cumsum(prices)
    for p in range(1, P + 1):
        if p == 1: z[0] = prices
        elif p <= n:
            z[p-1, :p-1] = c[:p-1] / np.arange(1, p)
            z[p-1, p-1:] = (c[p-1:] - np.concatenate(([0], c[:-p]))) / p
        else: z[p-1] = c / np.arange(1, n + 1)
    return z

def fast_all_rsi(prices, P=200):
    n = len(prices)
    diffs = np.diff(prices, prepend=prices[0])
    gains = np.clip(diffs, 0.0, None); losses = np.clip(-diffs, 0.0, None)
    alphas = 1.0 / np.arange(1, P + 1)
    avg_gain = np.full(P, gains[0], dtype=float); avg_loss = np.full(P, losses[0], dtype=float)
    out = np.empty((P, n), dtype=float)
    out[:, 0] = 100 - 100 / (1 + avg_gain / np.where(avg_loss == 0, 1e-10, avg_loss))
    for t in range(1, n):
        avg_gain += alphas * (gains[t] - avg_gain)
        avg_loss += alphas * (losses[t] - avg_loss)
        out[:, t] = 100 - 100 / (1 + avg_gain / np.where(avg_loss == 0, 1e-10, avg_loss))
    return out

# ==============================================================================
# 3) موتور ساختار 3بعدی و زنجیره اتصالات
# ==============================================================================
def get_dominant_extrema(highs, lows, max_period=200):
    """محاسبه دوره غالب (قدرت) برای هر نقطه اکستریمم"""
    n = len(highs)
    max_p = min(max_period, n // 2)
    dom_hh = np.zeros(n, dtype=int)
    dom_ll = np.zeros(n, dtype=int)
    
    s_high = pd.Series(highs)
    s_low = pd.Series(lows)
    
    for p in range(1, max_p + 1):
        win = 2 * p + 1
        roll_max = s_high.rolling(win, center=True, min_periods=1).max().values
        roll_min = s_low.rolling(win, center=True, min_periods=1).min().values
        
        dom_hh[np.isclose(highs, roll_max)] = p
        dom_ll[np.isclose(lows, roll_min)] = p
        
    return dom_hh, dom_ll

def extract_chains(dom_arr, price_arr, min_period=10):
    """استخراج گره‌های اصلی زنجیره (نقاطی که در آن‌ها دوره غالب ماکزیمم محلی است)"""
    points = []
    n = len(dom_arr)
    for i in range(1, n-1):
        if dom_arr[i] > dom_arr[i-1] and dom_arr[i] > dom_arr[i+1] and dom_arr[i] >= min_period:
            points.append({"idx": i, "price": price_arr[i], "period": dom_arr[i]})
    return points

def generate_signals(hh_chain, ll_chain, ma_fast, ma_slow, rsi, prices):
    """تولید سیگنال بازگشتی بر اساس تلاقی 3 لایه"""
    signals = []
    n = len(prices)
    
    last_hh, last_ll = None, None
    hh_ptr, ll_ptr = 0, 0
    
    for i in range(n):
        while hh_ptr < len(hh_chain) and hh_chain[hh_ptr]["idx"] <= i:
            last_hh = hh_chain[hh_ptr]
            hh_ptr += 1
        while ll_ptr < len(ll_chain) and ll_chain[ll_ptr]["idx"] <= i:
            last_ll = ll_chain[ll_ptr]
            ll_ptr += 1
            
        if i < 50 or last_hh is None or last_ll is None: continue
        
        prev_hh = hh_chain[hh_ptr-2] if hh_ptr >= 2 else None
        prev_ll = ll_chain[ll_ptr-2] if ll_ptr >= 2 else None
        
        # لایه 1: ساختار 3بعدی (شکست ساختار + افت مومنتوم در بعد Z)
        bearish_struct = False
        bullish_struct = False
        
        if prev_hh and last_hh:
            # Lower High یا Weak High (افت دوره غالب)
            if last_hh["price"] < prev_hh["price"] or last_hh["period"] < prev_hh["period"] * 0.8:
                if prices[i] < last_ll["price"]: bearish_struct = True
                
        if prev_ll and last_ll:
            # Higher Low یا Weak Low
            if last_ll["price"] > prev_ll["price"] or last_ll["period"] < prev_ll["period"] * 0.8:
                if prices[i] > last_hh["price"]: bullish_struct = True
                
        # لایه 2: تاییدیه MA
        bearish_ma = ma_fast[i] < ma_slow[i] and ma_fast[i] < ma_fast[i-1]
        bullish_ma = ma_fast[i] > ma_slow[i] and ma_fast[i] > ma_fast[i-1]
        
        # لایه 3: تاییدیه RSI
        bearish_rsi = rsi[i] < 45 and rsi[i] < rsi[i-1]
        bullish_rsi = rsi[i] > 55 and rsi[i] > rsi[i-1]
        
        # قانون تلاقی 100% (Cooldown 5 کندل برای جلوگیری از سیگنال‌های رگباری)
        if bearish_struct and bearish_ma and bearish_rsi:
            if not signals or (i - signals[-1]["idx"] > 5):
                signals.append({"idx": i, "type": "SELL", "price": prices[i]})
        elif bullish_struct and bullish_ma and bullish_rsi:
            if not signals or (i - signals[-1]["idx"] > 5):
                signals.append({"idx": i, "type": "BUY", "price": prices[i]})
                
    return signals

# ==============================================================================
# 4) رابط کاربری Dash
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])

app.layout = dbc.Container([
    dbc.Row(dbc.Col(html.H1("🌙 3D Chain Reversal System | Bybit Terminal", className="text-center my-3 text-warning"))),
    dbc.Row(dbc.Col(html.P("⚠️ صداقت علمی: مدل «تلاقی 100%» یک هیوریستیک آماری بر اساس شکست ساختار 3بعدی، مومنتوم و تاییدیه اندیکاتورها است. در بازارهای مالی قطعیت مطلق وجود ندارد؛ مدیریت ریسک الزامی است.", className="text-center text-info small"))),
    
    dbc.Row([
        dbc.Col(dbc.Input(id="symbol", value="BTCUSDT", placeholder="Symbol e.g. BTCUSDT")),
        dbc.Col(dbc.Select(id="interval", options=[
            {"label": "1m", "value": "1"}, {"label": "5m", "value": "5"},
            {"label": "15m", "value": "15"}, {"label": "1H", "value": "60"},
            {"label": "4H", "value": "240"}, {"label": "1D", "value": "D"}
        ], value="60")),
        dbc.Col(dbc.Button("Fetch & Analyze 3D", id="btn", color="primary", className="w-100"))
    ], className="mb-4"),
    
    dbc.Spinner(dbc.Row([
        dbc.Col(dcc.Graph(id="graph-3d"), width=12)
    ])),
    
    dbc.Spinner(dbc.Row([
        dbc.Col(dcc.Graph(id="graph-2d"), width=12)
    ]))
], fluid=True)

@app.callback(
    [Output("graph-3d", "figure"), Output("graph-2d", "figure")],
    Input("btn", "n_clicks"),
    State("symbol", "value"),
    State("interval", "value"),
    prevent_initial_call=False
)
def update(n, symbol, interval):
    df = get_klines(symbol, interval, limit=500)
    if df.empty:
        return go.Figure().update_layout(title="❌ Data Fetch Error"), go.Figure().update_layout(title="❌ Data Fetch Error")
        
    prices = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    times = df["ts"].dt.strftime("%Y-%m-%d %H:%M")
    
    # 1. استخراج ساختار 3بعدی
    dom_hh, dom_ll = get_dominant_extrema(highs, lows, max_period=100)
    hh_chain = extract_chains(dom_hh, highs, min_period=10)
    ll_chain = extract_chains(dom_ll, lows, min_period=10)
    
    # 2. محاسبه اندیکاتورها با فرمول‌های برداری
    P = min(100, len(prices))
    Z = fast_all_ma(prices, P)
    R = fast_all_rsi(prices, P)
    ma_fast = Z[min(19, P-1)] # MA 20
    ma_slow = Z[min(49, P-1)] # MA 50
    rsi = R[min(13, P-1)]     # RSI 14
    
    # 3. تولید سیگنال‌های تلاقی
    signals = generate_signals(hh_chain, ll_chain, ma_fast, ma_slow, rsi, prices)
    
    # --- رسم نمودار 3بعدی ---
    fig3d = go.Figure()
    if hh_chain:
        fig3d.add_trace(go.Scatter3d(
            x=[times[p["idx"]] for p in hh_chain], y=[p["price"] for p in hh_chain], z=[p["period"] for p in hh_chain],
            mode='markers+lines', marker=dict(size=6, color='lime', symbol='diamond'),
            line=dict(color='lime', width=4), name='HH Chain (3D)'
        ))
    if ll_chain:
        fig3d.add_trace(go.Scatter3d(
            x=[times[p["idx"]] for p in ll_chain], y=[p["price"] for p in ll_chain], z=[p["period"] for p in ll_chain],
            mode='markers+lines', marker=dict(size=6, color='red', symbol='diamond'),
            line=dict(color='red', width=4), name='LL Chain (3D)'
        ))
        
    fig3d.update_layout(
        title="🌌 3D Market Structure (X: Time, Y: Price, Z: Strength/Period)",
        scene=dict(xaxis_title='Time', yaxis_title='Price', zaxis_title='Strength (Period)'),
        template="plotly_dark", height=600
    )
    
    # --- رسم نمودار 2بعدی و سیگنال‌ها ---
    fig2d = go.Figure()
    fig2d.add_trace(go.Candlestick(
        x=times, open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="Price"
    ))
    fig2d.add_trace(go.Scatter(x=times, y=ma_fast, line=dict(color='cyan', width=1), name="MA 20"))
    fig2d.add_trace(go.Scatter(x=times, y=ma_slow, line=dict(color='magenta', width=1), name="MA 50"))
    
    buys = [s for s in signals if s["type"] == "BUY"]
    sells = [s for s in signals if s["type"] == "SELL"]
    
    if buys:
        fig2d.add_trace(go.Scatter(
            x=[times[s["idx"]] for s in buys], y=[s["price"] for s in buys], mode='markers',
            marker=dict(symbol='triangle-up', size=15, color='lime', line=dict(width=2, color='white')),
            name='✅ BUY (3D+MA+RSI Confluence)'
        ))
    if sells:
        fig2d.add_trace(go.Scatter(
            x=[times[s["idx"]] for s in sells], y=[s["price"] for s in sells], mode='markers',
            marker=dict(symbol='triangle-down', size=15, color='red', line=dict(width=2, color='white')),
            name='❌ SELL (3D+MA+RSI Confluence)'
        ))
        
    fig2d.update_layout(
        title=f"🎯 {symbol} {interval} - High Probability Reversal Signals",
        template="plotly_dark", xaxis_rangeslider_visible=False, height=600
    )
    
    return fig3d, fig2d

if __name__ == "__main__":
    app.run(debug=True, port=8050)