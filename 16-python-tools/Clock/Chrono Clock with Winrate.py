# -*- coding: utf-8 -*-
"""
⏳ Chrono-Clock Pro — سیستم معاملاتی نهادی (Institutional Scale-Out Strategy)
--------------------------------------------------------------------------------
موتور معاملاتی: Harmonic Cycle Breakout با مدیریت ریسک مقیاس‌پذیر (Partial Close)
"""

import math
import warnings
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import requests
import plotly.graph_objects as go

import dash
from dash import dcc, html, Input, Output, State, dash_table, no_update
import dash_bootstrap_components as dbc

warnings.filterwarnings("ignore")

# ==============================================================================
# 0) پالت رنگی و تنظیمات پیش‌فرض
# ==============================================================================
BG, CARD, LINE, TXT, MUT = "#0b1220", "#121c30", "#23314d", "#e8ecf4", "#8fa3c0"
GOLD, UP, DN = "#f0b90b", "#16a085", "#e74c3c"
HAND_CW_CLR = "#ecf0f1"
HAND_CCW_CLR = "#e74c3c"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_CATEGORY = "linear"
DEFAULT_INTERVAL = "15"
DEFAULT_FORECAST_HOURS = 6
N_BINS = 288

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
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"),
    "Accept": "application/json", "Referer": "https://www.bybit.com/",
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
        except Exception: continue
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
            if len(s) >= 19: sec_f = v / 1e9
            elif len(s) >= 16: sec_f = v / 1e6
            elif len(s) >= 13: sec_f = v / 1e3
            else: sec_f = float(v)
            return datetime.fromtimestamp(sec_f, tz=timezone.utc)
    except Exception: pass
    return datetime.now(timezone.utc)

def get_klines(symbol, interval, category="linear", limit=1000):
    d = bybit_get("/v5/market/kline", {"category": category, "symbol": symbol, "interval": interval, "limit": limit})
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
    try: return int(s)
    except Exception: return 15

# ==============================================================================
# 2) نگاشت زمان → زاویه‌ی صفحه‌ی ساعت
# ==============================================================================
def hour_frac_12(dt_utc): return (dt_utc.hour % 12) + dt_utc.minute / 60.0 + dt_utc.second / 3600.0
def hour_frac_to_theta_cw(hf): return (90.0 - 30.0 * hf) % 360.0
def hour_frac_to_theta_ccw(hf): return (90.0 + 30.0 * hf) % 360.0
def hour_frac_to_clockstr(hf):
    total_min = hf * 60.0
    hh, mm = int(total_min // 60), int(round(total_min % 60))
    if mm == 60: mm, hh = 0, hh + 1
    hh = hh % 12
    if hh == 0: hh = 12
    return f"{hh:02d}:{mm:02d}"

# ==============================================================================
# 3) موتور پیش‌بینی فوریه (FFT)
# ==============================================================================
def build_price_ring_advanced(df, now_utc, forecast_hours, interval_min, model_type="fourier", n_harmonics=3, n_bins=N_BINS):
    bin_price_hist = np.full(n_bins, np.nan)
    bin_ts_hist = [None] * n_bins
    for _, row in df.iterrows():
        ts = pd.Timestamp(row["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)
        hf = hour_frac_12(ts)
        idx = int(hf / 12.0 * n_bins) % n_bins
        if bin_ts_hist[idx] is None or ts > bin_ts_hist[idx]:
            bin_ts_hist[idx] = ts
            bin_price_hist[idx] = float(row["close"])

    steps = max(int((forecast_hours * 60.0) / max(interval_min, 1)), 1)
    closes, highs, lows = df['close'].values, df['high'].values, df['low'].values
    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - np.roll(closes, 1)), np.abs(lows - np.roll(closes, 1))))
    tr[0] = highs[0] - lows[0]
    atr = pd.Series(tr).rolling(window=14, min_periods=1).mean().values
    current_atr = atr[-1]
    ci_width = current_atr * np.sqrt(np.arange(1, steps + 1)) * 1.5
    pred_prices, strength = np.zeros(steps), 0.0

    if model_type == "fourier" and len(closes) > 10:
        n = len(closes)
        x = np.arange(n)
        p = np.polyfit(x, closes, 1)
        y_detrend = closes - np.polyval(p, x)
        fft = np.fft.fft(y_detrend)
        mags = np.abs(fft); mags[0] = 0
        top_idx = np.argsort(mags)[::-1][:n_harmonics]
        total_power = np.sum(mags ** 2)
        strength = (np.sum(mags[top_idx] ** 2) / total_power) * 100 if total_power > 0 else 0
        x_ext = np.arange(n, n + steps)
        trend_ext = np.polyval(p, x_ext)
        cyc_ext = np.zeros(steps)
        freqs = np.fft.fftfreq(n, d=1)
        for idx in top_idx:
            if idx == 0: continue
            cyc_ext += 2 * (mags[idx]/n) * np.cos(2 * np.pi * freqs[idx] * x_ext + np.angle(fft[idx]))
        pred_prices = trend_ext + cyc_ext
    elif model_type == "momentum":
        ema = pd.Series(closes).ewm(span=20).mean().values
        slope = (ema[-1] - ema[-10]) / 10 if len(ema) >= 10 else 0
        pred_prices = closes[-1] + slope * np.arange(1, steps + 1)
    else:
        p = np.polyfit(np.arange(len(closes)), closes, 1)
        pred_prices = np.polyval(p, np.arange(len(closes), len(closes) + steps))

    bin_price_fut, bin_ci_upper, bin_ci_lower = np.full(n_bins, np.nan), np.full(n_bins, np.nan), np.full(n_bins, np.nan)
    fut_bins = set()
    last_ts = pd.Timestamp(df.iloc[-1]["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)
    for s in range(steps):
        t_future = last_ts + timedelta(minutes=interval_min * (s + 1))
        idx = int(hour_frac_12(t_future) / 12.0 * n_bins) % n_bins
        bin_price_fut[idx] = pred_prices[s]
        bin_ci_upper[idx] = pred_prices[s] + ci_width[s]
        bin_ci_lower[idx] = pred_prices[s] - ci_width[s]
        fut_bins.add(idx)

    final_price, status = bin_price_hist.copy(), np.array(["past"] * n_bins, dtype=object)
    for idx in fut_bins:
        final_price[idx], status[idx] = bin_price_fut[idx], "future"

    nanmask = np.isnan(final_price)
    if (~nanmask).sum() >= 2:
        idxs = np.arange(n_bins)
        ext_price = np.concatenate([final_price]*3)
        ext_idx = np.concatenate([idxs - n_bins, idxs, idxs + n_bins])
        ext_valid = ~np.isnan(ext_price)
        final_price[nanmask] = np.interp(idxs + n_bins, ext_idx[ext_valid], ext_price[ext_valid])[nanmask]
        status[nanmask & (status == "past")] = "interp"
    else: final_price[:] = float(df.iloc[-1]["close"]) if len(df) else 0.0

    hour_fracs = np.arange(n_bins) / n_bins * 12.0
    thetas = np.array([hour_frac_to_theta_cw(hf) for hf in hour_fracs])
    return thetas, hour_fracs, final_price, status, bin_ci_upper, bin_ci_lower, strength

# ==============================================================================
# 4) موتور بک‌تست نهادی (Institutional Scale-Out Backtester)
# ==============================================================================
def get_fft_metrics(closes, window=150, forecast_steps=15, n_harmonics=3):
    if len(closes) < window: return 0.0, 0.0
    y = closes[-window:]
    x = np.arange(window)
    p = np.polyfit(x, y, 1)
    y_detrend = y - np.polyval(p, x)
    fft = np.fft.fft(y_detrend)
    mags = np.abs(fft); mags[0] = 0
    top_idx = np.argsort(mags)[::-1][:n_harmonics]
    total_power = np.sum(mags**2)
    strength = (np.sum(mags[top_idx]**2) / total_power) * 100 if total_power > 0 else 0
    x_ext = np.arange(window, window + forecast_steps)
    trend_ext = np.polyval(p, x_ext)
    cyc_ext = np.zeros(forecast_steps)
    freqs = np.fft.fftfreq(window, d=1)
    for idx in top_idx:
        if idx == 0: continue
        cyc_ext += 2 * (mags[idx]/window) * np.cos(2 * np.pi * freqs[idx] * x_ext + np.angle(fft[idx]))
    pred_prices = trend_ext + cyc_ext
    return strength, pred_prices[-1] - y[-1]

def backtest_strategy_pro(df, initial_capital=500.0, risk_pct=0.015):
    if df.empty or len(df) < 300: return pd.DataFrame(), [initial_capital], {}
    closes, highs, lows = df['close'].values, df['high'].values, df['low'].values
    timestamps, hours = df['ts'].values, pd.to_datetime(df['ts']).dt.hour.values
    ema50 = pd.Series(closes).ewm(span=50).mean().values
    ema200 = pd.Series(closes).ewm(span=200).mean().values
    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - np.roll(closes, 1)), np.abs(lows - np.roll(closes, 1))))
    tr[0] = highs[0] - lows[0]
    atr = pd.Series(tr).rolling(window=14).mean().values
    atr_sma = pd.Series(atr).rolling(window=50).mean().values
    fee_pct = 0.0006 # کارمزد واقعی صرافی
    trades, equity, equity_curve = [], initial_capital, [initial_capital]
    in_position, warmup = False, 250

    for i in range(warmup, len(df) - 1):
        if in_position:
            if side == 1:
                if not tp1_hit and highs[i] >= tp1_price:
                    partial_size = pos_size / 2
                    pnl = partial_size * (tp1_price - entry_price) - (partial_size * (entry_price + tp1_price) * fee_pct)
                    equity += pnl
                    trades.append({'time': timestamps[i], 'side': 'BUY', 'entry': entry_price, 'exit': tp1_price, 'sl': sl_price, 'tp1': tp1_price, 'tp2': tp2_price, 'pnl': pnl, 'result': '✅ TP1 (50%)'})
                    equity_curve.append(equity)
                    pos_size /= 2; sl_price = entry_price; tp1_hit = True
                
                if highs[i] >= tp2_price:
                    pnl = pos_size * (tp2_price - entry_price) - (pos_size * (entry_price + tp2_price) * fee_pct)
                    equity += pnl
                    trades.append({'time': timestamps[i], 'side': 'BUY', 'entry': entry_price, 'exit': tp2_price, 'sl': sl_price, 'tp1': tp1_price, 'tp2': tp2_price, 'pnl': pnl, 'result': '🚀 TP2 (100%)'})
                    equity_curve.append(equity); in_position = False; continue
                    
                if lows[i] <= sl_price:
                    pnl = pos_size * (sl_price - entry_price) - (pos_size * (entry_price + sl_price) * fee_pct)
                    equity += pnl
                    res = '🛡️ BE' if abs(sl_price - entry_price) < 1e-6 else '❌ LOSS'
                    trades.append({'time': timestamps[i], 'side': 'BUY', 'entry': entry_price, 'exit': sl_price, 'sl': sl_price, 'tp1': tp1_price, 'tp2': tp2_price, 'pnl': pnl, 'result': res})
                    equity_curve.append(equity); in_position = False; continue
            else:
                if not tp1_hit and lows[i] <= tp1_price:
                    partial_size = pos_size / 2
                    pnl = partial_size * (entry_price - tp1_price) - (partial_size * (entry_price + tp1_price) * fee_pct)
                    equity += pnl
                    trades.append({'time': timestamps[i], 'side': 'SELL', 'entry': entry_price, 'exit': tp1_price, 'sl': sl_price, 'tp1': tp1_price, 'tp2': tp2_price, 'pnl': pnl, 'result': '✅ TP1 (50%)'})
                    equity_curve.append(equity)
                    pos_size /= 2; sl_price = entry_price; tp1_hit = True
                
                if lows[i] <= tp2_price:
                    pnl = pos_size * (entry_price - tp2_price) - (pos_size * (entry_price + tp2_price) * fee_pct)
                    equity += pnl
                    trades.append({'time': timestamps[i], 'side': 'SELL', 'entry': entry_price, 'exit': tp2_price, 'sl': sl_price, 'tp1': tp1_price, 'tp2': tp2_price, 'pnl': pnl, 'result': '🚀 TP2 (100%)'})
                    equity_curve.append(equity); in_position = False; continue
                    
                if highs[i] >= sl_price:
                    pnl = pos_size * (entry_price - sl_price) - (pos_size * (entry_price + sl_price) * fee_pct)
                    equity += pnl
                    res = '🛡️ BE' if abs(sl_price - entry_price) < 1e-6 else '❌ LOSS'
                    trades.append({'time': timestamps[i], 'side': 'SELL', 'entry': entry_price, 'exit': sl_price, 'sl': sl_price, 'tp1': tp1_price, 'tp2': tp2_price, 'pnl': pnl, 'result': res})
                    equity_curve.append(equity); in_position = False; continue

        if not in_position:
            if not (7 <= hours[i] <= 21) or np.isnan(atr_sma[i]): continue
            if atr[i] < atr_sma[i] * 0.8: continue # فیلتر بازار مرده
            
            strength, expected_move = get_fft_metrics(closes[:i+1])
            if strength < 45.0: continue # فیلتر تشدید چرخه زمانی
            
            risk_dist = 1.5 * atr[i]
            if closes[i] > ema50[i] and ema50[i] > ema200[i] and expected_move > (0.8 * atr[i]):
                side, entry_price, entry_atr = 1, closes[i], atr[i]
                sl_price = entry_price - risk_dist
                tp1_price = entry_price + (1.5 * risk_dist)
                tp2_price = entry_price + (3.0 * risk_dist)
                pos_size = (equity * risk_pct) / risk_dist
                in_position, tp1_hit, entry_idx = True, False, i
                
            elif closes[i] < ema50[i] and ema50[i] < ema200[i] and expected_move < (-0.8 * atr[i]):
                side, entry_price, entry_atr = -1, closes[i], atr[i]
                sl_price = entry_price + risk_dist
                tp1_price = entry_price - (1.5 * risk_dist)
                tp2_price = entry_price - (3.0 * risk_dist)
                pos_size = (equity * risk_pct) / risk_dist
                in_position, tp1_hit, entry_idx = True, False, i

    df_trades = pd.DataFrame(trades)
    stats = {}
    if not df_trades.empty:
        stats['total'] = len(df_trades)
        stats['win_rate'] = (df_trades['pnl'] > 0).mean() * 100
        stats['net_profit'] = equity - initial_capital
        stats['final_eq'] = equity
        stats['max_dd'] = np.max(np.maximum.accumulate(equity_curve) - equity_curve)
        gross_profit = df_trades[df_trades['pnl'] > 0]['pnl'].sum()
        gross_loss = abs(df_trades[df_trades['pnl'] < 0]['pnl'].sum())
        stats['pf'] = gross_profit / gross_loss if gross_loss > 0 else 99.9
    else:
        stats = {'total': 0, 'win_rate': 0, 'net_profit': 0, 'final_eq': initial_capital, 'max_dd': 0, 'pf': 0}
    return df_trades, equity_curve, stats

# ==============================================================================
# 5) رسم ساعت قیمت
# ==============================================================================
STATUS_FA = {"past": "داده تاریخی", "future": "پیش‌بینی چرخه‌ای", "interp": "درون‌یابی"}
STATUS_SYMBOL = {"past": "circle", "future": "diamond", "interp": "circle-open"}

def empty_fig(msg):
    fig = go.Figure()
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD, xaxis=dict(visible=False), yaxis=dict(visible=False))
    fig.add_annotation(x=0.5, y=0.5, xref="paper", yref="paper", text=msg, showarrow=False, font=dict(size=16, color=DN))
    return fig

def build_clock_figure(df, now_utc, symbol, interval, forecast_hours, model_type, n_harmonics, show_ci):
    if df.empty or len(df) < 8: return empty_fig("داده‌ی کافی نیست.")
    interval_min = get_interval_minutes(interval)
    thetas, hour_fracs, prices, status, bin_ci_upper, bin_ci_lower, strength = build_price_ring_advanced(df, now_utc, forecast_hours, interval_min, model_type, n_harmonics)
    R = 1.0
    live_price = float(df.iloc[-1]["close"])
    hf_now = hour_frac_12(now_utc)
    theta_cw, theta_ccw = hour_frac_to_theta_cw(hf_now), hour_frac_to_theta_ccw(hf_now)
    fig = go.Figure()
    ang_full = np.linspace(0, 360, 361)
    fig.add_trace(go.Scatter(x=R * np.cos(np.radians(ang_full)), y=R * np.sin(np.radians(ang_full)), mode="lines", line=dict(color=LINE, width=1.5), showlegend=False, hoverinfo="skip"))
    for h in range(1, 13):
        theta = (90 - 30 * h) % 360
        c, s = np.cos(np.radians(theta)), np.sin(np.radians(theta))
        fig.add_trace(go.Scatter(x=[0.92 * R * c, R * c], y=[0.92 * R * s, R * s], mode="lines", line=dict(color=GOLD, width=1.5), hoverinfo="skip", showlegend=False))
        fig.add_annotation(x=1.1 * R * c, y=1.1 * R * s, text=f"<b>{h}</b>", showarrow=False, font=dict(size=13, color=GOLD))
    xs, ys = R * np.cos(np.radians(thetas)), R * np.sin(np.radians(thetas))
    clock_labels = [hour_frac_to_clockstr(hf) for hf in hour_fracs]
    status_labels = [STATUS_FA[s] for s in status]
    symbols = [STATUS_SYMBOL[s] for s in status]
    customdata = np.column_stack([clock_labels, [f"{p:.6g}" for p in prices], status_labels])
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers", marker=dict(size=8, color=prices, colorscale="Turbo", symbol=symbols, showscale=True, colorbar=dict(title="قیمت", thickness=12, len=0.55, y=0.78, tickfont=dict(color=TXT, size=10)), line=dict(width=0.3, color="#000")), customdata=customdata, hovertemplate=("⏱ ساعت: %{customdata[0]}<br>💰 قیمت: %{customdata[1]}<br>📌 %{customdata[2]}<extra></extra>"), name="حلقه قیمت دور ساعت"))
    valid_fut = ~np.isnan(bin_ci_upper)
    if valid_fut.sum() > 1 and show_ci:
        thetas_fut, hf_fut = thetas[valid_fut], hour_fracs[valid_fut]
        order = np.argsort(hf_fut)
        xs_upper, ys_upper = 1.08 * R * np.cos(np.radians(thetas_fut[order])), 1.08 * R * np.sin(np.radians(thetas_fut[order]))
        xs_lower, ys_lower = 0.92 * R * np.cos(np.radians(thetas_fut[order])), 0.92 * R * np.sin(np.radians(thetas_fut[order]))
        fig.add_trace(go.Scatter(x=xs_upper, y=ys_upper, mode="lines", line=dict(color=UP, width=4, dash="dot"), opacity=0.3, showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=xs_lower, y=ys_lower, mode="lines", line=dict(color=DN, width=4, dash="dot"), opacity=0.3, showlegend=False, hoverinfo="skip"))
    session_opens = {"آسیا 🌏": 0, "لندن 🌍": 7, "نیویورک 🌎": 13}
    for name, h in session_opens.items():
        hf = h % 12
        theta = hour_frac_to_theta_cw(hf)
        c, s = np.cos(np.radians(theta)), np.sin(np.radians(theta))
        fig.add_trace(go.Scatter(x=[1.15 * R * c], y=[1.15 * R * s], mode="markers+text", marker=dict(size=9, color=GOLD, symbol="diamond", line=dict(width=1, color="black")), text=[name], textposition="top center", textfont=dict(size=10, color=MUT), showlegend=False, hoverinfo="name"))
    lc, ls = np.cos(np.radians(theta_cw)), np.sin(np.radians(theta_cw))
    fig.add_trace(go.Scatter(x=[R * lc], y=[R * ls], mode="markers+text", marker=dict(size=18, symbol="star", color=GOLD, line=dict(width=2, color="black")), text=[f"LIVE {live_price:.4g}"], textposition="top center", textfont=dict(color=GOLD, size=12, family="Arial Black")))
    fig.add_trace(go.Scatter(x=[0, 0.88 * R * lc], y=[0, 0.88 * R * ls], mode="lines", line=dict(color=HAND_CW_CLR, width=6)))
    mc, ms = np.cos(np.radians(theta_ccw)), np.sin(np.radians(theta_ccw))
    fig.add_trace(go.Scatter(x=[0, 0.72 * R * mc], y=[0, 0.72 * R * ms], mode="lines", line=dict(color=HAND_CCW_CLR, width=5, dash="dot")))
    fig.add_trace(go.Scatter(x=[0], y=[0], mode="markers", marker=dict(size=10, color=TXT, line=dict(width=1, color=GOLD))))
    fig.add_annotation(x=0.02, y=0.98, xref="paper", yref="paper", text=f"⚡ قدرت چرخه زمانی: {strength:.1f}%", showarrow=False, font=dict(size=12, color=GOLD, family="Arial Black"), bgcolor="rgba(11,18,32,0.8)", bordercolor=GOLD, borderwidth=1, borderpad=4, xanchor="left", yanchor="top")
    h_now = now_utc.hour
    sessions = []
    if 0 <= h_now < 9: sessions.append("آسیا 🌏")
    if 7 <= h_now < 16: sessions.append("لندن 🌍")
    if 13 <= h_now < 22: sessions.append("نیویورک 🌎")
    curr_sess = " | ".join(sessions) if sessions else "خارج از سشن 🌑"
    fig.add_annotation(x=0.98, y=0.98, xref="paper", yref="paper", text=f"⏱ سشن فعال: {curr_sess}", showarrow=False, font=dict(size=12, color=UP, family="Arial"), bgcolor="rgba(11,18,32,0.8)", bordercolor=UP, borderwidth=1, borderpad=4, xanchor="right", yanchor="top")
    lim = 1.35 * R
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD, legend=dict(bgcolor="rgba(11,18,32,0.8)", font=dict(size=10), orientation="h", y=-0.06, x=0.5, xanchor="center"), margin=dict(l=10, r=10, t=60, b=10), title=dict(text=(f"⏳ Chrono-Clock Pro — {symbol} | {interval}m | {now_utc.strftime('%H:%M:%S')} UTC"), x=0.5, font=dict(color=GOLD, size=16)))
    fig.update_xaxes(range=[-lim, lim], visible=False)
    fig.update_yaxes(range=[-lim, lim], visible=False, scaleanchor="x", scaleratio=1)
    return fig

# ==============================================================================
# 6) اپ Dash
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG], suppress_callback_exceptions=True)
app.title = "Chrono-Clock Pro Institutional"
server = app.server

CATEGORY_OPTS = [{"label": v, "value": v} for v in ["linear", "spot", "inverse"]]
INTERVAL_OPTS = [{"label": lbl, "value": val} for lbl, val in [("1m", "1"), ("3m", "3"), ("5m", "5"), ("15m", "15"), ("30m", "30"), ("1h", "60"), ("4h", "240")]]

def get_clock_layout():
    return html.Div([
        dbc.Card(dbc.CardBody(dbc.Row([
            dbc.Col([html.Label("نماد", style={"fontSize": 11, "color": MUT}), dcc.Input(id="symbol", value=DEFAULT_SYMBOL, type="text", style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
            dbc.Col([html.Label("بازار", style={"fontSize": 11, "color": MUT}), dcc.Dropdown(id="category", value=DEFAULT_CATEGORY, clearable=False, options=CATEGORY_OPTS)], md=1),
            dbc.Col([html.Label("تایم‌فریم", style={"fontSize": 11, "color": MUT}), dcc.Dropdown(id="interval", value=DEFAULT_INTERVAL, clearable=False, options=INTERVAL_OPTS)], md=1),
            dbc.Col([html.Label("مدل پیش‌بینی", style={"fontSize": 11, "color": MUT}), dcc.Dropdown(id="model-type", value="fourier", clearable=False, options=[{"label": "🌊 فوریه", "value": "fourier"}, {"label": "📈 خطی", "value": "linear"}, {"label": "🚀 مومنتوم", "value": "momentum"}])], md=2),
            dbc.Col([html.Label("عمق چرخه", style={"fontSize": 11, "color": MUT}), dcc.Dropdown(id="harmonics", value=3, clearable=False, options=[{"label": "۱", "value": 1}, {"label": "۲", "value": 2}, {"label": "۳", "value": 3}, {"label": "۵", "value": 5}])], md=2),
            dbc.Col([html.Label("افق (ساعت)", style={"fontSize": 11, "color": MUT}), dcc.Input(id="forecast-hours", type="number", value=DEFAULT_FORECAST_HOURS, min=1, max=12, step=1, style={"width": "100%", "padding": 6})], md=1),
            dbc.Col([dbc.Checklist(id="show-ci", options=[{"label": "نمایش CI", "value": "show"}], value=["show"], style={"marginTop": 22, "fontSize": 11, "color": MUT})], md=1),
            dbc.Col([dbc.Button("🔄", id="refresh-btn", color="warning", className="mt-3", style={"fontWeight": "bold", "color": BG, "width": "100%"})], md=1),
            dbc.Col(html.Div(id="conn-status", style={"color": MUT, "fontSize": 10, "marginTop": 26, "textAlign": "center"}), md=1),
        ])), style={"maxWidth": 1200, "margin": "10px auto"}),
        dbc.Card(dbc.CardBody([dcc.Graph(id="clock-graph", style={"height": "80vh"}, config={"displaylogo": False}), html.Div("💡 موتور نهادی: ترکیب تشدید چرخه فوریه (FFT) + فیلتر روند EMA + مدیریت ریسک مقیاس‌پذیر (Scale-Out)", style={"fontSize": 11, "color": MUT, "marginTop": 8, "direction": "rtl", "textAlign": "center"})]), style={"maxWidth": 1200, "margin": "0 auto", "backgroundColor": CARD, "border": f"1px solid {LINE}"}),
        dcc.Interval(id="tick", interval=30_000, n_intervals=0),
    ])

def get_stats_layout():
    return html.Div([
        dbc.Card(dbc.CardBody(dbc.Row([
            dbc.Col([html.Label("نماد", style={"fontSize": 11, "color": MUT}), dcc.Input(id="bt-symbol", value=DEFAULT_SYMBOL, type="text", style={"width": "100%", "padding": 6})], md=2),
            dbc.Col([html.Label("بازار", style={"fontSize": 11, "color": MUT}), dcc.Dropdown(id="bt-category", value=DEFAULT_CATEGORY, clearable=False, options=CATEGORY_OPTS)], md=1),
            dbc.Col([html.Label("تایم‌فریم", style={"fontSize": 11, "color": MUT}), dcc.Dropdown(id="bt-interval", value="15", clearable=False, options=INTERVAL_OPTS)], md=2),
            dbc.Col([html.Label("سرمایه ($)", style={"fontSize": 11, "color": MUT}), dcc.Input(id="bt-capital", type="number", value=500, style={"width": "100%", "padding": 6})], md=2),
            dbc.Col([html.Label("ریسک (%)", style={"fontSize": 11, "color": MUT}), dcc.Input(id="bt-risk", type="number", value=1.5, min=0.5, max=5, step=0.5, style={"width": "100%", "padding": 6})], md=1),
            dbc.Col([dbc.Button("🚀 اجرای بک‌تست نهادی", id="run-backtest-btn", color="success", className="mt-3", style={"fontWeight": "bold", "width": "100%"})], md=4),
        ])), style={"maxWidth": 1200, "margin": "10px auto"}),
        dcc.Loading(id="loading-backtest", type="default", color=GOLD, children=html.Div(id="stats-cards", style={"maxWidth": 1200, "margin": "10px auto"})),
        dbc.Card(dbc.CardBody([dcc.Graph(id="equity-graph", style={"height": "40vh"}, config={"displaylogo": False})]), style={"maxWidth": 1200, "margin": "10px auto", "backgroundColor": CARD}),
        dbc.Card(dbc.CardBody([html.H4("📜 تاریخچه معاملات (سیستم Scale-Out)", style={"color": TXT, "textAlign": "center", "direction": "rtl"}), dcc.Loading(id="loading-table", type="default", color=GOLD, children=dash_table.DataTable(id='trades-table', columns=[{"name": "زمان", "id": "time"}, {"name": "نوع", "id": "side"}, {"name": "ورود", "id": "entry"}, {"name": "خروج", "id": "exit"}, {"name": "SL", "id": "sl"}, {"name": "TP1", "id": "tp1"}, {"name": "TP2", "id": "tp2"}, {"name": "سود ($)", "id": "pnl"}, {"name": "نتیجه", "id": "result"}], data=[], style_table={'overflowX': 'auto'}, style_cell={'backgroundColor': '#121c30', 'color': '#e8ecf4', 'border': '1px solid #23314d', 'textAlign': 'center', 'fontFamily': 'Tahoma, Arial'}, style_header={'backgroundColor': '#0b1220', 'fontWeight': 'bold', 'color': '#f0b90b'}, page_size=15)))], style={"maxWidth": 1200, "margin": "10px auto", "backgroundColor": CARD}),
    ])

app.layout = html.Div([
    html.H1("⏳ Chrono-Clock Pro — سیستم معاملاتی نهادی (Institutional)", style={'textAlign': 'center', 'color': GOLD, 'fontFamily': 'Arial', 'margin': '20px 0'}),
    dcc.Tabs(id="tabs", value='tab-clock', children=[
        dcc.Tab(label='⏳ ساعت زمانی و پیش‌بینی قیمت', value='tab-clock'),
        dcc.Tab(label='📊 عملکرد سیستم و بک‌تست (سرمایه ۵۰۰$)', value='tab-stats'),
    ]),
    html.Div(id='tabs-content')
], style={"background": BG, "minHeight": "100vh", "padding": "10px", "fontFamily": "Tahoma, Arial, sans-serif", "direction": "rtl"})

@app.callback(Output('tabs-content', 'children'), Input('tabs', 'value'))
def render_tab(tab):
    if tab == 'tab-clock': return get_clock_layout()
    elif tab == 'tab-stats': return get_stats_layout()
    return html.Div()

@app.callback(Output("clock-graph", "figure"), Output("conn-status", "children"), Input("tick", "n_intervals"), Input("refresh-btn", "n_clicks"), State("symbol", "value"), State("category", "value"), State("interval", "value"), State("forecast-hours", "value"), State("model-type", "value"), State("harmonics", "value"), State("show-ci", "value"), prevent_initial_call=False)
def update_clock(_n, _click, symbol, category, interval, forecast_hours, model_type, n_harmonics, show_ci):
    symbol, category, interval, model_type = (symbol or DEFAULT_SYMBOL).upper().strip(), category or DEFAULT_CATEGORY, interval or DEFAULT_INTERVAL, model_type or "fourier"
    n_harmonics = int(n_harmonics or 3)
    show_ci_bool = "show" in (show_ci or [])
    try: forecast_hours = float(forecast_hours or DEFAULT_FORECAST_HOURS)
    except Exception: forecast_hours = DEFAULT_FORECAST_HOURS
    now_utc = get_server_time()
    df = get_klines(symbol, interval, category, limit=500)
    if df.empty: return empty_fig("خطا در دریافت کندل."), "🔴 قطع"
    fig = build_clock_figure(df, now_utc, symbol, interval, forecast_hours, model_type, n_harmonics, show_ci_bool)
    return fig, f"🟢 متصل | {now_utc.strftime('%H:%M:%S')} UTC"

@app.callback(Output("stats-cards", "children"), Output("equity-graph", "figure"), Output("trades-table", "data"), Input("run-backtest-btn", "n_clicks"), State("bt-capital", "value"), State("bt-risk", "value"), State("bt-symbol", "value"), State("bt-category", "value"), State("bt-interval", "value"), prevent_initial_call=True)
def run_backtest(n_clicks, capital, risk, symbol, category, interval):
    if not n_clicks: return no_update, no_update, no_update
    symbol, interval, category = (symbol or DEFAULT_SYMBOL).upper().strip(), interval or DEFAULT_INTERVAL, category or DEFAULT_CATEGORY
    capital, risk_dec = float(capital or 500), float(risk or 1.5) / 100.0
    df = get_klines(symbol, interval, category, limit=1000) 
    if df.empty or len(df) < 300: return html.Div("❌ داده کافی نیست.", style={"color": DN, "textAlign": "center", "padding": "20px"}), empty_fig("داده کافی نیست."), []
    
    df_trades, equity_curve, stats = backtest_strategy_pro(df, initial_capital=capital, risk_pct=risk_dec)
    cards = dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("تعداد معاملات", style={"color": MUT}), html.H3(f"{stats['total']}", style={"color": TXT})])), md=2, style={"textAlign": "center"}),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("وین‌ریت کل", style={"color": MUT}), html.H3(f"{stats['win_rate']:.1f}%", style={"color": UP if stats['win_rate'] > 50 else DN})])), md=2, style={"textAlign": "center"}),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("سود/ضرر خالص", style={"color": MUT}), html.H3(f"${stats['net_profit']:.2f}", style={"color": UP if stats['net_profit'] > 0 else DN})])), md=2, style={"textAlign": "center"}),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("سرمایه نهایی", style={"color": MUT}), html.H3(f"${stats['final_eq']:.2f}", style={"color": GOLD})])), md=2, style={"textAlign": "center"}),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("پرافیت فاکتور", style={"color": MUT}), html.H3(f"{stats['pf']:.2f}", style={"color": TXT})])), md=2, style={"textAlign": "center"}),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("حداکثر افت (DD)", style={"color": MUT}), html.H3(f"${stats['max_dd']:.2f}", style={"color": DN})])), md=2, style={"textAlign": "center"}),
    ], style={"margin": "10px 0"})

    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(x=list(range(len(equity_curve))), y=equity_curve, mode='lines', line=dict(color=GOLD, width=3), fill='tozeroy', fillcolor='rgba(240, 185, 11, 0.15)', name="Equity Curve"))
    fig_eq.add_hline(y=capital, line_dash="dash", line_color=MUT, annotation_text="سرمایه اولیه")
    fig_eq.update_layout(template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD, title=f"📈 نمودار رشد سرمایه نهادی | شروع با {capital}$", xaxis_title="تعداد معاملات", yaxis_title="سرمایه ($)", font=dict(color=TXT), margin=dict(l=20, r=20, t=40, b=20), hovermode="x unified")

    table_data = []
    if not df_trades.empty:
        df_trades['time'] = pd.to_datetime(df_trades['time']).dt.strftime('%m-%d %H:%M')
        df_trades = df_trades.sort_values('time', ascending=False)
        for _, row in df_trades.iterrows():
            table_data.append({"time": str(row['time']), "side": "📈 BUY" if row['side'] == 1 else "📉 SELL", "entry": f"{row['entry']:.2f}", "exit": f"{row['exit']:.2f}", "sl": f"{row['sl']:.2f}", "tp1": f"{row['tp1']:.2f}", "tp2": f"{row['tp2']:.2f}", "pnl": f"${row['pnl']:.2f}", "result": str(row['result'])})
    return cards, fig_eq, table_data

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8060, use_reloader=False)