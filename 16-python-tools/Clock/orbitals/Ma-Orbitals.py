# -*- coding: utf-8 -*-
"""
🪐 Orbital Trend Engine + Backtest — نسخه نهایی پایدار
✓ تب Live: تشخیص روند زنده با سیستم اربیتالی فیبوناچی
✓ تب Backtest: وین‌ریت + منحنی سرمایه + جزئیات معاملات
✓ ضدخطا: fallback data در لحظه import + figure اولیه + try/except
✓ سازگار با pandas 2.x و numpy مدرن
"""

import threading
import time
import traceback
import math
import urllib3
import numpy as np
import pandas as pd
import requests
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==============================================================================
# 1) تنظیمات پایه
# ==============================================================================
SYMBOL = "BTCUSDT"
CATEGORY = "linear"
API_ENDPOINTS = ["https://api.bybit.com", "https://api.bytick.com"]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
})

APP_STATE = {"price": 97000.0, "connected": False, "endpoint": "None"}
MA_DATA = {}

FIB_PERIODS = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987]
PERIODS_DESC = sorted(FIB_PERIODS, reverse=True)
MAX_MOM = sum(
    (2 * np.pi / (p * 60)) * (1.0 + np.log10(p + 1) * 2.5)
    for p in PERIODS_DESC
)

COLORS = [
    '#FFD700', '#FFC300', '#FFB000', '#FF9D00', '#FF8A00',
    '#FF7700', '#FF6400', '#FF5100', '#FF3E00', '#FF2B00',
    '#FF1800', '#FF0500', '#E000FF', '#CC00FF', '#AA00FF',
]

MONO = {"fontFamily": "monospace"}


def get_base_radius(period):
    return 1.0 + np.log10(period + 1) * 2.5


def get_api_interval(period):
    if period <= 3: return "1"
    elif period <= 15: return "5"
    elif period <= 60: return "15"
    elif period <= 240: return "60"
    elif period <= 1440: return "D"
    else: return "W"


# ==============================================================================
# 2) Fallback Data — اجرای فوری در import (ضمانت داده اولیه)
# ==============================================================================
def generate_fallback_data():
    base_price = 97000.0
    rng = np.random.RandomState(42)
    for period in FIB_PERIODS:
        n = max(period, 30)
        closes = base_price + np.cumsum(rng.normal(0, base_price * 0.0005, n))
        MA_DATA[period] = {
            'ma': float(np.mean(closes[-period:])),
            'atr': float(max(np.std(closes) * 2, 1.0)),
            'price': base_price,
            'last_close': float(closes[-1]),
        }
    APP_STATE["price"] = base_price


generate_fallback_data()
print("✅ Fallback data initialized")


# ==============================================================================
# 3) اتصال API (Thread)
# ==============================================================================
def api_request(path, params, timeout=10):
    for endpoint in API_ENDPOINTS:
        try:
            resp = SESSION.get(
                f"{endpoint}{path}", params=params, timeout=timeout, verify=False
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("retCode") == 0:
                    APP_STATE["endpoint"] = endpoint
                    APP_STATE["connected"] = True
                    return data
        except Exception:
            continue
    APP_STATE["connected"] = False
    return None


def data_loop(stop_flag):
    while not stop_flag.is_set():
        try:
            data = api_request(
                "/v5/market/tickers", {"category": CATEGORY, "symbol": SYMBOL}
            )
            if data and data.get("result") and data["result"].get("list"):
                APP_STATE["price"] = float(
                    data["result"]["list"][0].get("lastPrice", 0)
                )
            for period in FIB_PERIODS:
                try:
                    kdata = api_request("/v5/market/kline", {
                        "category": CATEGORY, "symbol": SYMBOL,
                        "interval": get_api_interval(period),
                        "limit": min(200, max(50, period * 2)),
                    })
                    if not (kdata and kdata.get("result") and kdata["result"].get("list")):
                        continue
                    klist = kdata["result"]["list"]
                    closes = np.array([float(k[4]) for k in reversed(klist)])
                    highs = np.array([float(k[2]) for k in reversed(klist)])
                    lows = np.array([float(k[3]) for k in reversed(klist)])
                    if len(closes) < period:
                        continue
                    tr = np.maximum(
                        highs - lows,
                        np.maximum(
                            np.abs(highs[1:] - closes[:-1]),
                            np.abs(lows[1:] - closes[:-1])
                        )
                    )
                    MA_DATA[period] = {
                        'ma': float(np.mean(closes[-period:])),
                        'atr': float(max(np.mean(tr[-min(14, len(tr)):]), 1.0)),
                        'price': APP_STATE["price"],
                        'last_close': float(closes[-1]),
                    }
                except Exception:
                    continue
        except Exception:
            pass
        time.sleep(3)


threading.Thread(target=data_loop, args=(threading.Event(),), daemon=True).start()


# ==============================================================================
# 4) موتور امتیاز اربیتالی (مشترک Live/Backtest)
# ==============================================================================
def orbital_score_at(t_sec, price, ma_get, atr_get):
    cx = cy = 0.0
    acc = 0.0
    angles, radii = [], []

    for period in PERIODS_DESC:
        base = get_base_radius(period)
        ma = ma_get(period)
        radius = base
        if ma is not None and not np.isnan(ma) and ma > 0 and price > 0:
            radius = base * (1 + min(abs(price - ma) / ma * 10, 2.0))
        T = period * 60
        progress = min((t_sec % T) / T, 1.0)
        angle = 2 * np.pi * progress + acc
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        cx, cy = x, y
        acc = angle
        angles.append(angle % (2 * np.pi))
        radii.append(radius)

    tip_angle = math.atan2(cy, cx)
    chain = math.sin(tip_angle)

    n_sec = 12
    sw = 2 * np.pi / n_sec
    counts = [0] * n_sec
    for a in angles:
        counts[int(a / sw) % n_sec] += 1
    mx = max(counts)
    dom = counts.index(mx)
    align = ((mx / len(angles)) * 2 - 1) * math.sin((dom + 0.5) * sw)

    mom = sum(
        (2 * np.pi / (p * 60)) * r for p, r in zip(PERIODS_DESC, radii)
    ) / MAX_MOM

    wsum = wtot = 0.0
    for p in FIB_PERIODS:
        ma = ma_get(p)
        if ma is None or (isinstance(ma, float) and np.isnan(ma)):
            continue
        w = np.log10(p + 1)
        wsum += w if price > ma else -w
        wtot += w
    mapos = wsum / wtot if wtot > 0 else 0.0

    ss = sum(math.sin(a) for a in angles)
    cs = sum(math.cos(a) for a in angles)
    res = np.sqrt(ss ** 2 + cs ** 2) / len(angles)
    coh = res * math.sin(math.atan2(ss, cs))

    tipv = chain * 0.5
    return float(
        0.25 * chain + 0.20 * align + 0.10 * mom +
        0.25 * mapos + 0.10 * coh + 0.10 * tipv
    )


# ==============================================================================
# 5) محاسبه روند زنده
# ==============================================================================
def compute_epicycle_positions(t_now):
    positions = []
    cx, cy, acc = 0.0, 0.0, 0.0
    price = APP_STATE["price"]
    for i, period in enumerate(PERIODS_DESC):
        base = get_base_radius(period)
        radius = base
        if period in MA_DATA:
            ma = MA_DATA[period]['ma']
            if price > 0 and ma > 0:
                radius = base * (1 + min(abs(price - ma) / ma * 10, 2.0))
        T = period * 60
        progress = min((t_now - (t_now // T) * T) / T, 1.0)
        angle = 2 * np.pi * progress + acc
        x = cx + radius * np.cos(angle)
        y = cy + radius * np.sin(angle)
        positions.append({
            'x': float(x), 'y': float(y),
            'cx': float(cx), 'cy': float(cy),
            'radius': float(radius), 'period': period,
            'color': COLORS[i % len(COLORS)],
            'progress': float(progress),
            'angle': float(angle % (2 * np.pi))
        })
        cx, cy = x, y
        acc = angle
    return positions


def compute_trend_factors(t_now):
    positions = compute_epicycle_positions(t_now)
    price = APP_STATE["price"]
    factors = {}

    tip = positions[-1]
    chain = float(np.sin(np.arctan2(tip['y'], tip['x'])))
    factors['chain_vector'] = {'score': chain, 'label': '🔗 بردار زنجیره'}

    n_sec, sw = 12, 2 * np.pi / 12
    counts = [0] * n_sec
    for p in positions:
        counts[int(p['angle'] / sw) % n_sec] += 1
    mx = max(counts)
    dom = int(np.argmax(counts))
    factors['orbital_alignment'] = {
        'score': float(((mx / len(positions)) * 2 - 1) * np.sin((dom + 0.5) * sw)),
        'label': '🎯 هم‌راستایی مداری'
    }

    mom = sum(
        (2 * np.pi / (p['period'] * 60)) * p['radius'] for p in positions
    ) / MAX_MOM
    factors['angular_momentum'] = {'score': float(mom), 'label': '🌀 مومنتوم زاویه‌ای'}

    above = below = wsum = wtot = 0
    for period in FIB_PERIODS:
        if period in MA_DATA:
            w = np.log10(period + 1)
            if price > MA_DATA[period]['ma']:
                above += 1; wsum += w
            else:
                below += 1; wsum -= w
            wtot += w
    factors['ma_position'] = {
        'score': float(wsum / wtot) if wtot else 0.0,
        'above': above, 'below': below, 'total': above + below,
        'label': '📊 موقعیت قیمت/MA'
    }

    an = np.array([p['angle'] for p in positions])
    ss = float(np.sum(np.sin(an)))
    cs = float(np.sum(np.cos(an)))
    res = np.sqrt(ss ** 2 + cs ** 2) / max(len(an), 1)
    factors['phase_coherence'] = {
        'score': float(res * np.sin(np.arctan2(ss, cs))),
        'label': '🔄 انسجام فاز'
    }
    factors['tip_velocity'] = {'score': chain * 0.5, 'label': '⚡ سرعت نوک'}

    weights = {
        'chain_vector': 0.25, 'orbital_alignment': 0.20, 'angular_momentum': 0.10,
        'ma_position': 0.25, 'phase_coherence': 0.10, 'tip_velocity': 0.10,
    }
    total = float(sum(factors[k]['score'] * weights[k] for k in weights))

    if total > 0.15:
        trend, color = "🟢 صعودی", "#00FF88"
    elif total < -0.15:
        trend, color = "🔴 نزولی", "#FF6B6B"
    else:
        trend, color = "🟡 خنثی", "#FFD700"

    factors['final'] = {
        'score': total, 'trend': trend, 'color': color,
        'strength': min(abs(total) / 0.5, 1.0), 'weights': weights
    }
    return factors, positions


# ==============================================================================
# 6) موتور بک‌تست (اصلاح‌شده)
# ==============================================================================
def fetch_klines_1m(limit=3000):
    dfs, end, fetched = [], None, 0
    while fetched < limit:
        params = {"category": CATEGORY, "symbol": SYMBOL, "interval": "1", "limit": 1000}
        if end:
            params["end"] = str(int(end * 1000))
        d = api_request("/v5/market/kline", params)
        if not (d and d.get("result", {}).get("list")):
            break
        lst = d["result"]["list"]
        arr = np.array([[
            int(k[0]) / 1000, float(k[1]), float(k[2]),
            float(k[3]), float(k[4])
        ] for k in lst])
        df = pd.DataFrame(arr, columns=["ts", "open", "high", "low", "close"])
        dfs.append(df)
        fetched += len(df)
        end = df["ts"].min() - 60
        time.sleep(0.08)
    if not dfs:
        return None
    return pd.concat(dfs).sort_values("ts").drop_duplicates("ts").reset_index(drop=True)


def generate_synthetic_candles(n=3000):
    rng = np.random.RandomState(7)
    t0 = time.time() - n * 60
    ts = t0 + np.arange(n) * 60
    close = 97000 + np.cumsum(rng.normal(0, 15, n))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) + abs(rng.normal(0, 5, n))
    low = np.minimum(open_, close) - abs(rng.normal(0, 5, n))
    return pd.DataFrame({
        "ts": ts, "open": open_, "high": high, "low": low, "close": close
    })


def run_backtest(df, hold=10, threshold=0.15):
    """اجرای بک‌تست با اصلاحات کامل"""
    closes = df["close"].values.astype(float)
    ts = df["ts"].values.astype(float)
    N = len(df)
    close_s = pd.Series(closes)

    # True Range
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    prev_close = np.roll(closes, 1)
    prev_close[0] = closes[0]
    tr = np.maximum(
        highs - lows,
        np.maximum(np.abs(highs - prev_close), np.abs(lows - prev_close))
    )
    tr_s = pd.Series(tr)

    # پیش‌محاسبه MA و ATR (min_periods=1 + bfill برای سازگاری با pandas 2.x)
    ma_arr, atr_arr = {}, {}
    for p in FIB_PERIODS:
        ma_arr[p] = close_s.rolling(p, min_periods=1).mean().bfill().values
        atr_arr[p] = tr_s.rolling(p, min_periods=1).mean().bfill().values

    warmup = max(FIB_PERIODS) + 5
    trades = []
    i = warmup
    while i < N - hold - 1:
        price = closes[i]
        if np.isnan(price) or price <= 0:
            i += 1
            continue

        t_sec = ts[i]
        try:
            score = orbital_score_at(
                t_sec, price,
                lambda p, _i=i: float(ma_arr[p][_i]),
                lambda p, _i=i: float(atr_arr[p][_i])
            )
        except Exception:
            i += 1
            continue

        if np.isnan(score):
            i += 1
            continue

        if abs(score) > threshold:
            direction = 1 if score > 0 else -1
            entry = closes[i]
            exit_ = closes[i + hold]
            if np.isnan(exit_) or entry == 0:
                i += 1
                continue
            pnl = (exit_ - entry) / entry * 100 * direction
            trades.append({
                'entry_time': pd.to_datetime(int(ts[i] * 1000), unit='ms'),
                'exit_time': pd.to_datetime(int(ts[i + hold] * 1000), unit='ms'),
                'direction': direction, 'score': float(score),
                'entry': float(entry), 'exit': float(exit_),
                'pnl': float(pnl), 'win': pnl > 0,
            })
            i += hold
        else:
            i += 1

    if not trades:
        return {'trades': [], 'stats': None}

    pnls = np.array([t['pnl'] for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    gross_win = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(abs(losses.sum())) if len(losses) else 0.0

    max_ws = cur = 0
    for t in trades:
        cur = cur + 1 if t['win'] else 0
        max_ws = max(max_ws, cur)
    max_ls = cur = 0
    for t in trades:
        cur = cur + 1 if not t['win'] else 0
        max_ls = max(max_ls, cur)

    stats = {
        'total': len(trades),
        'wins': int(len(wins)), 'losses': int(len(losses)),
        'win_rate': float(len(wins) / len(trades) * 100),
        'avg_pnl': float(pnls.mean()),
        'avg_win': float(wins.mean()) if len(wins) else 0.0,
        'avg_loss': float(losses.mean()) if len(losses) else 0.0,
        'profit_factor': float(gross_win / gross_loss) if gross_loss > 0 else float('inf'),
        'total_pnl': float(pnls.sum()),
        'best': float(pnls.max()), 'worst': float(pnls.min()),
        'max_win_streak': int(max_ws), 'max_loss_streak': int(max_ls),
        'equity': np.cumsum(pnls),
    }
    return {'trades': trades, 'stats': stats}


# ==============================================================================
# 7) Figure ها
# ==============================================================================
def placeholder_figure(text):
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark", plot_bgcolor='#0a0a12', paper_bgcolor='#0a0a12',
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        annotations=[dict(
            text=text, x=0.5, y=0.5, xref="paper", yref="paper",
            showarrow=False, font=dict(color="#FFD700", size=16)
        )]
    )
    return fig


def error_figure(msg):
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark", plot_bgcolor='#0a0a12', paper_bgcolor='#0a0a12',
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        annotations=[dict(
            text=str(msg)[:1500], x=0.02, y=0.98, xref="paper",
            yref="paper", xanchor='left', yanchor='top', align='left',
            showarrow=False,
            font=dict(color="#FF6B6B", size=9, family="monospace")
        )]
    )
    return fig


def build_epicycle_figure(positions):
    traces = []
    ax = [p['x'] for p in positions] + [p['cx'] for p in positions]
    ay = [p['y'] for p in positions] + [p['cy'] for p in positions]
    mr = max(max(abs(v) for v in ax), max(abs(v) for v in ay)) * 1.3

    for pos in positions:
        th = np.linspace(0, 2 * np.pi, 100)
        traces.append(go.Scatter(
            x=pos['cx'] + pos['radius'] * np.cos(th),
            y=pos['cy'] + pos['radius'] * np.sin(th),
            mode='lines', line=dict(color=pos['color'], width=1, dash='dot'),
            opacity=0.3, showlegend=False, hoverinfo='skip'
        ))
        np_ = max(int(100 * pos['progress']), 3)
        tp = np.linspace(0, 2 * np.pi * pos['progress'], np_)
        traces.append(go.Scatter(
            x=pos['cx'] + pos['radius'] * np.cos(tp),
            y=pos['cy'] + pos['radius'] * np.sin(tp),
            mode='lines', line=dict(color=pos['color'], width=2.5),
            showlegend=True, name=f"MA {pos['period']}m"
        ))
        traces.append(go.Scatter(
            x=[pos['x']], y=[pos['y']], mode='markers',
            marker=dict(color='#FFF', size=7, line=dict(color=pos['color'], width=2)),
            showlegend=False, hoverinfo='skip'
        ))

    traces.append(go.Scatter(
        x=[0] + [p['x'] for p in positions],
        y=[0] + [p['y'] for p in positions],
        mode='lines', line=dict(color='#FFF', width=1.5, dash='dash'),
        opacity=0.5, showlegend=False, hoverinfo='skip'
    ))
    traces.append(go.Scatter(
        x=[0], y=[0], mode='markers',
        marker=dict(color='#FFD700', size=14, line=dict(color='#000', width=2)),
        showlegend=False, hoverinfo='skip'
    ))
    tip = positions[-1]
    traces.append(go.Scatter(
        x=[tip['x']], y=[tip['y']], mode='markers',
        marker=dict(color='#FFD700', size=16, symbol='star',
                    line=dict(color='#000', width=2)),
        showlegend=False
    ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        template="plotly_dark", plot_bgcolor='#0a0a12', paper_bgcolor='#0a0a12',
        font=dict(color='#f5efe0', family='monospace'), showlegend=True,
        legend=dict(
            yanchor="top", y=0.99, xanchor="left", x=0.01,
            bgcolor="rgba(10,10,18,0.7)", font=dict(size=7)
        ),
        shapes=[
            dict(type="circle", xref="x", yref="y", x0=-r, y0=-r, x1=r, y1=r,
                 line=dict(color="#1a1a2e", width=1, dash="dot"))
            for r in [5, 10, 15, 20, 25]
        ],
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1, range=[-mr, mr]),
        yaxis=dict(visible=False, scaleanchor="x", scaleratio=1, range=[-mr, mr]),
        margin=dict(l=0, r=0, t=10, b=0), uirevision='constant'
    )
    return fig


def build_trend_dashboard(factors):
    final = factors['final']
    fig = make_subplots(
        rows=2, cols=3,
        specs=[[{"type": "indicator"}, {"type": "indicator"}, {"type": "indicator"}],
               [{"type": "xy", "colspan": 3}, None, None]],
        vertical_spacing=0.18, horizontal_spacing=0.1
    )

    fig.add_trace(go.Indicator(
        mode="gauge+number", value=final['score'] * 100,
        title={'text': "🎯 امتیاز روند", 'font': {'size': 12, 'color': '#FFD700'}},
        number={'font': {'size': 24, 'color': final['color']}},
        gauge={
            'axis': {'range': [-100, 100]},
            'bar': {'color': final['color']},
            'bgcolor': '#0a0a12',
            'steps': [
                {'range': [-100, -15], 'color': 'rgba(255,107,107,0.2)'},
                {'range': [-15, 15], 'color': 'rgba(255,215,0,0.2)'},
                {'range': [15, 100], 'color': 'rgba(0,255,136,0.2)'}
            ]
        }
    ), row=1, col=1)

    fig.add_trace(go.Indicator(
        mode="gauge+number", value=final['strength'] * 100,
        title={'text': "💪 قدرت", 'font': {'size': 12, 'color': '#FFD700'}},
        number={'suffix': '%', 'font': {'size': 20, 'color': final['color']}},
        gauge={
            'axis': {'range': [0, 100]},
            'bar': {'color': final['color']},
            'bgcolor': '#0a0a12'
        }
    ), row=1, col=2)

    mp = factors['ma_position']
    fig.add_trace(go.Indicator(
        mode="gauge+number", value=mp['above'],
        title={
            'text': f"📊 MA بالا ({mp['above']}/{mp['total']})",
            'font': {'size': 11, 'color': '#FFD700'}
        },
        number={
            'font': {
                'size': 20,
                'color': '#00FF88' if mp['above'] > mp['below'] else '#FF6B6B'
            }
        },
        gauge={
            'axis': {'range': [0, mp['total'] or 1]},
            'bar': {'color': '#00FF88' if mp['above'] > mp['below'] else '#FF6B6B'},
            'bgcolor': '#0a0a12'
        }
    ), row=1, col=3)

    names, scores, cols = [], [], []
    for k in ['chain_vector', 'orbital_alignment', 'angular_momentum',
              'ma_position', 'phase_coherence', 'tip_velocity']:
        s = factors[k]['score']
        names.append(factors[k]['label'])
        scores.append(s * 100)
        cols.append('#00FF88' if s > 0.05 else ('#FF6B6B' if s < -0.05 else '#FFD700'))

    fig.add_trace(go.Bar(
        x=scores, y=names, orientation='h',
        marker=dict(color=cols, opacity=0.8),
        text=[f"{s:+.1f}" for s in scores], textposition='auto',
        textfont=dict(color='white', size=9), showlegend=False
    ), row=2, col=1)

    fig.update_layout(
        template="plotly_dark", plot_bgcolor='#0a0a12', paper_bgcolor='#0a0a12',
        font=dict(color='#f5efe0', family='monospace'), height=320,
        margin=dict(l=10, r=10, t=30, b=20), showlegend=False
    )
    fig.update_xaxes(range=[-100, 100], gridcolor='#1a1a2e', row=2, col=1)
    fig.update_yaxes(gridcolor='#1a1a2e', row=2, col=1)
    return fig


def build_backtest_figures(result):
    stats = result['stats']
    trades = result['trades']

    fig_eq = go.Figure()
    if stats is not None and stats:
        eq = stats['equity']
        fig_eq.add_trace(go.Scatter(
            y=eq, mode='lines', name='Equity',
            line=dict(color='#FFD700', width=2)
        ))
        fig_eq.add_trace(go.Scatter(
            y=np.maximum.accumulate(eq), mode='lines', name='Peak',
            line=dict(color='#00FF88', width=1, dash='dot'), opacity=0.5
        ))
        fig_eq.add_hline(y=0, line_color='#666', line_dash='dash')
        fig_eq.update_layout(
            template="plotly_dark", plot_bgcolor='#0a0a12', paper_bgcolor='#0a0a12',
            font=dict(color='#f5efe0', family='monospace'),
            title={'text': '📈 منحنی سرمایه (Cumulative PnL %)',
                   'font': {'size': 13, 'color': '#FFD700'}},
            margin=dict(l=40, r=10, t=40, b=30),
            xaxis=dict(gridcolor='#1a1a2e', title='Trade #'),
            yaxis=dict(gridcolor='#1a1a2e', title='PnL %'),
            legend=dict(bgcolor='rgba(10,10,18,0.7)', font=dict(size=9))
        )
    else:
        fig_eq = placeholder_figure("❌ سیگنالی تولید نشد")

    fig_dist = go.Figure()
    if trades:
        pnls = [t['pnl'] for t in trades]
        colors = ['#00FF88' if p > 0 else '#FF6B6B' for p in pnls]
        fig_dist.add_trace(go.Bar(
            y=pnls, marker=dict(color=colors),
            hovertemplate='Trade %{x}: %{y:.3f}%<extra></extra>'
        ))
        fig_dist.add_hline(y=0, line_color='#666', line_dash='dash')
        fig_dist.update_layout(
            template="plotly_dark", plot_bgcolor='#0a0a12', paper_bgcolor='#0a0a12',
            font=dict(color='#f5efe0', family='monospace'),
            title={'text': '📊 PnL هر معامله',
                   'font': {'size': 13, 'color': '#FFD700'}},
            margin=dict(l=40, r=10, t=40, b=30),
            xaxis=dict(gridcolor='#1a1a2e', title='Trade #'),
            yaxis=dict(gridcolor='#1a1a2e', title='PnL %'),
            showlegend=False
        )
    else:
        fig_dist = placeholder_figure("❌ داده‌ای نیست")

    return fig_eq, fig_dist


def build_trades_table(result):
    trades = result['trades']
    if not trades:
        return html.P("❌ هیچ معامله‌ای ثبت نشد", style={
            "color": "#FF6B6B", "textAlign": "center", "padding": "20px"
        })

    rows = []
    for i, t in enumerate(trades[-100:][::-1], 1):
        d_txt = "🟢 LONG" if t['direction'] > 0 else "🔴 SHORT"
        d_col = "#00FF88" if t['direction'] > 0 else "#FF6B6B"
        p_col = "#00FF88" if t['pnl'] > 0 else "#FF6B6B"
        rows.append(html.Tr([
            html.Td(str(i), style={"color": "#888", "fontSize": "10px", "padding": "3px 6px"}),
            html.Td(t['entry_time'].strftime('%m-%d %H:%M'),
                    style={"color": "#f5efe0", "fontSize": "10px", "padding": "3px 6px",
                           "fontFamily": "monospace"}),
            html.Td(d_txt, style={"color": d_col, "fontSize": "10px", "padding": "3px 6px",
                                  "fontWeight": "bold"}),
            html.Td(f"{t['score']:+.3f}", style={"color": "#FFD700", "fontSize": "10px",
                                                  "padding": "3px 6px", "fontFamily": "monospace"}),
            html.Td(f"${t['entry']:,.1f}", style={"color": "#aaa", "fontSize": "10px",
                                                  "padding": "3px 6px", "fontFamily": "monospace"}),
            html.Td(f"${t['exit']:,.1f}", style={"color": "#aaa", "fontSize": "10px",
                                                 "padding": "3px 6px", "fontFamily": "monospace"}),
            html.Td(f"{t['pnl']:+.3f}%", style={"color": p_col, "fontSize": "10px",
                                                "padding": "3px 6px", "fontWeight": "bold",
                                                "fontFamily": "monospace"}),
            html.Td("✅" if t['win'] else "❌", style={"fontSize": "11px", "padding": "3px 6px"}),
        ], style={
            "borderBottom": "1px solid #1a1a2e",
            "backgroundColor": "rgba(0,255,136,0.05)" if t['win'] else "rgba(255,107,107,0.05)"
        }))

    return html.Table([
        html.Thead([html.Tr([
            html.Th("#", style={"color": "#FFD700", "fontSize": "10px", "padding": "4px"}),
            html.Th("🕐 Entry", style={"color": "#FFD700", "fontSize": "10px", "padding": "4px"}),
            html.Th("🧭 Dir", style={"color": "#FFD700", "fontSize": "10px", "padding": "4px"}),
            html.Th("🎯 Score", style={"color": "#FFD700", "fontSize": "10px", "padding": "4px"}),
            html.Th("💰 Entry", style={"color": "#FFD700", "fontSize": "10px", "padding": "4px"}),
            html.Th("💰 Exit", style={"color": "#FFD700", "fontSize": "10px", "padding": "4px"}),
            html.Th("📊 PnL", style={"color": "#FFD700", "fontSize": "10px", "padding": "4px"}),
            html.Th("✅", style={"color": "#FFD700", "fontSize": "10px", "padding": "4px"}),
        ])]),
        html.Tbody(rows),
    ], style={"width": "100%", "borderCollapse": "collapse"})


# ==============================================================================
# 8) Dash App با Tabs
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
app.title = "🪐 Orbital Trend Engine"


def stat_card(cid, label, color):
    return dbc.Col(html.Div([
        html.Div(label, style={"fontSize": "10px", "color": "#888"}),
        html.Div("—", id=cid, style={
            "fontSize": "18px", "fontWeight": "bold", "color": color, **MONO
        }),
    ], style={
        "backgroundColor": "rgba(16,16,30,0.9)",
        "border": "1px solid #333", "borderRadius": "8px",
        "padding": "8px", "textAlign": "center"
    }), md=2, xs=6, style={"padding": "4px"})


app.layout = html.Div([
    # Header
    html.Div([
        html.H2("🪐 Orbital Trend Engine", style={
            "textShadow": "0 0 10px #FFD700", "fontSize": "18px", "margin": "0",
            "color": "#f5efe0", "display": "inline-block", **MONO
        }),
        html.Span(id="price-display", style={
            "fontSize": "16px", "color": "#FFD700", "marginLeft": "20px", **MONO
        }),
        html.Div(id="trend-announcement", style={
            "fontSize": "18px", "fontWeight": "bold", "marginTop": "5px", **MONO
        }),
        html.Div(id="status-bar", style={
            "fontSize": "10px", "color": "#888", "marginTop": "4px", **MONO
        }),
    ], style={
        "textAlign": "center", "padding": "8px 0",
        "backgroundColor": "rgba(10,10,18,0.9)", "borderBottom": "1px solid #333"
    }),

    # Tabs
    dbc.Tabs([
        # ===================== تب ۱: Live =====================
        dbc.Tab(label="🌀 Live Trend", children=[
            dbc.Row([
                dbc.Col(dcc.Graph(
                    id="epicycle-graph", config={'displayModeBar': False},
                    figure=placeholder_figure("🌀 Initializing..."),
                    style={'height': '48vh'}
                ), md=6, style={"padding": "5px"}),
                dbc.Col(dcc.Graph(
                    id="trend-dashboard", config={'displayModeBar': False},
                    figure=placeholder_figure("📊 Initializing..."),
                    style={'height': '48vh'}
                ), md=6, style={"padding": "5px"}),
            ]),
            html.Div(id="factors-table", style={
                "padding": "0 10px", "maxHeight": "26vh", "overflowY": "auto"
            }),
        ], style={"padding": "5px"}, label_style=MONO),

        # ===================== تب ۲: Backtest =====================
        dbc.Tab(label="📊 Backtest", children=[
            dbc.Card(dbc.CardBody(dbc.Row([
                dbc.Col([
                    html.Label("تعداد کندل ۱m", style={"fontSize": "10px", "color": "#888"}),
                    dcc.Dropdown(id="bt-candles", value=3000, clearable=False, options=[
                        {"label": "۲,۰۰۰ (~۱.۴ روز)", "value": 2000},
                        {"label": "۳,۰۰۰ (~۲ روز)", "value": 3000},
                        {"label": "۵,۰۰۰ (~۳.۵ روز)", "value": 5000},
                    ]),
                ], md=3),
                dbc.Col([
                    html.Label("مدت نگهداری (کندل)", style={"fontSize": "10px", "color": "#888"}),
                    dcc.Input(id="bt-hold", type="number", value=10, min=2, max=120,
                              style={"width": "100%", "padding": "6px", "background": "#1a1a2e",
                                     "color": "#f5efe0", "border": "1px solid #333", **MONO}),
                ], md=2),
                dbc.Col([
                    html.Label("آستانه سیگنال", style={"fontSize": "10px", "color": "#888"}),
                    dcc.Input(id="bt-threshold", type="number", value=0.15, min=0.05,
                              max=0.5, step=0.05,
                              style={"width": "100%", "padding": "6px", "background": "#1a1a2e",
                                     "color": "#f5efe0", "border": "1px solid #333", **MONO}),
                ], md=2),
                dbc.Col(dbc.Button("🚀 اجرای بک‌تست", id="bt-run", color="warning",
                                   style={"width": "100%", "fontWeight": "bold",
                                          "color": "#0a0a12"}), md=2),
                dbc.Col(html.Div(id="bt-status", style={
                    "fontSize": "10px", "color": "#888", "marginTop": "22px", **MONO
                }), md=3),
            ])), className="mb-2",
                style={"backgroundColor": "rgba(10,10,18,0.9)", "border": "1px solid #333"}),

            dbc.Row([
                stat_card("bt-winrate", "🏆 Win Rate", "#00FF88"),
                stat_card("bt-total", "🔢 تعداد معاملات", "#FFD700"),
                stat_card("bt-pf", "⚖️ Profit Factor", "#4ECDC4"),
                stat_card("bt-avgpnl", "📊 میانگین PnL", "#FFD700"),
                stat_card("bt-streak", "🔥 بیشترین برد/باخت", "#00FF88"),
                stat_card("bt-totalpnl", "💰 مجموع PnL", "#FFD700"),
            ], className="mb-2"),

            dbc.Row([
                dbc.Col(dcc.Graph(
                    id="bt-equity", config={'displayModeBar': False},
                    figure=placeholder_figure("🚀 بک‌تست را اجرا کنید"),
                    style={'height': '36vh'}
                ), md=7),
                dbc.Col(dcc.Graph(
                    id="bt-dist", config={'displayModeBar': False},
                    figure=placeholder_figure("📊 توزیع معاملات"),
                    style={'height': '36vh'}
                ), md=5),
            ]),

            html.Div(id="bt-trades", style={
                "maxHeight": "28vh", "overflowY": "auto", "padding": "0 10px"
            }),
        ], style={"padding": "5px"}, label_style=MONO),
    ], style={"backgroundColor": "rgba(10,10,18,0.9)"}, className="mb-2"),

    dcc.Interval(id="interval", interval=2000, n_intervals=0),
], style={"minHeight": "100vh", "backgroundColor": "#0a0a12", "padding": "0 0 20px 0"})


# ==============================================================================
# 9) Callback ها
# ==============================================================================
@app.callback(
    [Output("epicycle-graph", "figure"),
     Output("trend-dashboard", "figure"),
     Output("price-display", "children"),
     Output("trend-announcement", "children"),
     Output("status-bar", "children"),
     Output("factors-table", "children")],
    [Input("interval", "n_intervals")],
)
def update_live(n):
    try:
        t_now = time.time()
        factors, positions = compute_trend_factors(t_now)
        final = factors['final']

        rows = []
        for k in ['chain_vector', 'orbital_alignment', 'angular_momentum',
                  'ma_position', 'phase_coherence', 'tip_velocity']:
            f = factors[k]
            s = f['score']
            c = "#00FF88" if s > 0.05 else ("#FF6B6B" if s < -0.05 else "#FFD700")
            bar = "█" * min(int(abs(s) * 10) + 1, 10) if abs(s) > 0.05 else "░░░"
            rows.append(html.Tr([
                html.Td(f['label'], style={"color": "#f5efe0", "fontSize": "11px",
                                           "padding": "3px 8px", **MONO}),
                html.Td(f"{s:+.3f}", style={"color": c, "fontSize": "11px",
                                            "fontWeight": "bold", "padding": "3px 8px", **MONO}),
                html.Td(bar, style={"color": c, "fontSize": "10px",
                                    "padding": "3px 8px", **MONO}),
                html.Td(f"{final['weights'][k]*100:.0f}%", style={
                    "color": "#888", "fontSize": "10px", "padding": "3px 8px", **MONO
                }),
            ], style={"borderBottom": "1px solid #1a1a2e"}))

        table = html.Table([
            html.Thead([html.Tr([
                html.Th("🔍 Factor", style={"color": "#FFD700", "fontSize": "10px", "padding": "4px"}),
                html.Th("📊 Score", style={"color": "#FFD700", "fontSize": "10px", "padding": "4px"}),
                html.Th("📈", style={"color": "#FFD700", "fontSize": "10px", "padding": "4px"}),
                html.Th("⚖️", style={"color": "#FFD700", "fontSize": "10px", "padding": "4px"}),
            ])]),
            html.Tbody(rows),
        ], style={"width": "100%", "borderCollapse": "collapse"})

        return (
            build_epicycle_figure(positions),
            build_trend_dashboard(factors),
            f"💰 ${APP_STATE['price']:,.2f}",
            html.Span(
                f"{final['trend']} | قدرت: {final['strength']*100:.0f}%",
                style={"color": final['color'], "textShadow": f"0 0 15px {final['color']}"}
            ),
            f"{'🟢' if APP_STATE['connected'] else '🟡(نمونه)'} "
            f"{len(MA_DATA)}/{len(FIB_PERIODS)} MAs | Score: {final['score']:+.3f}",
            table
        )
    except Exception as e:
        tb = traceback.format_exc()
        print("❌ LIVE ERROR:\n", tb)
        return (
            error_figure(tb), error_figure(tb), "💰 Error",
            html.Span(f"❌ {e}", style={"color": "#FF6B6B"}),
            "❌ error",
            html.Pre(tb, style={"color": "#FF6B6B", "fontSize": "9px", **MONO})
        )


@app.callback(
    [Output("bt-winrate", "children"),
     Output("bt-total", "children"),
     Output("bt-pf", "children"),
     Output("bt-avgpnl", "children"),
     Output("bt-streak", "children"),
     Output("bt-totalpnl", "children"),
     Output("bt-equity", "figure"),
     Output("bt-dist", "figure"),
     Output("bt-trades", "children"),
     Output("bt-status", "children")],
    [Input("bt-run", "n_clicks")],
    [State("bt-candles", "value"),
     State("bt-hold", "value"),
     State("bt-threshold", "value")],
    prevent_initial_call=True,
)
def run_bt(_n, n_candles, hold, threshold):
    try:
        t0 = time.time()
        hold = int(hold or 10)
        threshold = float(threshold or 0.15)
        n_candles = int(n_candles or 3000)

        df = fetch_klines_1m(limit=n_candles)
        src = "🟢 Bybit"
        if df is None or len(df) < 1200:
            df = generate_synthetic_candles(n_candles)
            src = "🟡 Synthetic"

        result = run_backtest(df, hold=hold, threshold=threshold)
        stats = result['stats']
        fig_eq, fig_dist = build_backtest_figures(result)
        table = build_trades_table(result)

        if not stats:
            return (
                "—", "0", "—", "—", "—", "—",
                fig_eq, fig_dist, table,
                f"⚠️ {src} | {len(df)} کندل | سیگنالی تولید نشد"
            )

        elapsed = time.time() - t0
        return (
            f"{stats['win_rate']:.1f}%",
            f"{stats['total']}",
            f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "∞",
            f"{stats['avg_pnl']:+.3f}%",
            f"{stats['max_win_streak']}W / {stats['max_loss_streak']}L",
            f"{stats['total_pnl']:+.2f}%",
            fig_eq, fig_dist, table,
            f"✅ {src} | {len(df)} کندل | Hold={hold} | Thr={threshold} | ⏱ {elapsed:.1f}s"
        )
    except Exception as e:
        tb = traceback.format_exc()
        print("❌ BACKTEST ERROR:\n", tb)
        return (
            "—", "—", "—", "—", "—", "—",
            error_figure(tb), error_figure(tb),
            html.Pre(tb, style={"color": "#FF6B6B", "fontSize": "9px", **MONO}),
            f"❌ {e}"
        )


# ==============================================================================
# 10) اجرا
# ==============================================================================
if __name__ == '__main__':
    print("=" * 70)
    print("🪐 Orbital Trend Engine + Backtest")
    print("=" * 70)
    print("✓ Live Trend Detection")
    print("✓ Backtest with Win Rate + Equity Curve")
    print("=" * 70)
    print("Server: http://localhost:8050")
    print("=" * 70)
    app.run(debug=False, port=8050, host='0.0.0.0', use_reloader=False)