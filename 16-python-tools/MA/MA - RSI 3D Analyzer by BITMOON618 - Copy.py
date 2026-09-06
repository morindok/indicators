# -*- coding: utf-8 -*-
"""
BITMOON 3D Analyzer — تحلیل جامع MA + RSI (دوره 1-200) با سیگنال هم‌گرایی
----------------------------------------------------------------------
ارتقاءها:
 ۱) موتور سیگنال دقیق: هم‌ترازی MA 1-200 + هم‌ترازی RSI 1-200 + واگرایی + فشردگی
    → سیگنال ۵سطحی با «درصد اطمینان» برای هر ۱۳ تایم‌فریم.
 ۲) نمودار 3D RSI: سطح RSI دوره 1-200 با خطوط 30/50/70، خطوط کلیدی و نشانگر واگرایی.
 ۳) حکم «روند کلی» ترکیبی MA+RSI با نوار اطمینان + اجماع مولتی‌تایم‌فریم.
 ۴) رابط کاربری تب‌دار و کاربرپسند (dbc) + بنر دعوت به کانال تلگرام BITMOON618.
 ۵) حفظ بهینه‌سازی‌ها: دانلود موازی، محاسبات برداری، کش، Down-sample.

pip install dash dash-bootstrap-components plotly pandas numpy requests
python bitmoon_analyzer.py
"""

import time
import requests
import numpy as np
import pandas as pd
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed

TELEGRAM_URL = "https://t.me/BITMOON618"
TELEGRAM_ID = "BITMOON618"

# ==============================================================================
# 1) اتصال پایدار بایبیت (الهام از کد مرجع)
# ==============================================================================
REST_CANDIDATES = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept": "application/json", "Referer": "https://www.bybit.com/"})
_ACTIVE_REST_BASE = {"url": None}

def bybit_get(path, params, timeout=10):
    candidates = ([_ACTIVE_REST_BASE["url"]] if _ACTIVE_REST_BASE["url"] else []) + \
                 [b for b in REST_CANDIDATES if b != _ACTIVE_REST_BASE["url"]]
    for base in candidates:
        try:
            r = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code in (403, 451): continue
            r.raise_for_status()
            d = r.json()
            if d.get("retCode") == 0:
                _ACTIVE_REST_BASE["url"] = base
                return d
        except Exception:
            continue
    return None

def get_klines(symbol, interval, limit=500):
    d = bybit_get("/v5/market/kline", {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit})
    if not d or "list" not in (d.get("result") or {}): return pd.DataFrame()
    lst = d["result"]["list"]
    if not lst: return pd.DataFrame()
    df = pd.DataFrame(lst, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
    for c in ["open", "high", "low", "close", "volume"]: df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)

# ==============================================================================
# 2) محاسبات برداری سریع (MA و RSI دوره 1-200)
# ==============================================================================
def fast_all_ma(prices, max_period=200):
    n = len(prices); z = np.zeros((max_period, n)); c = np.cumsum(prices)
    for p in range(1, max_period + 1):
        if p == 1: z[0, :] = prices
        elif p <= n:
            z[p-1, :p-1] = c[:p-1] / np.arange(1, p)
            z[p-1, p-1:] = (c[p-1:] - np.concatenate(([0], c[:-p]))) / p
        else: z[p-1, :] = c / np.arange(1, n + 1)
    return z

def fast_ma_last(prices, max_period=200):
    n = len(prices); c = np.cumsum(prices); total = c[-1]; out = np.empty(max_period)
    for p in range(1, max_period + 1):
        prev = c[n-p-1] if (n-p-1) >= 0 else 0.0
        out[p-1] = (total - prev) / p if p <= n else total / n
    return out

def _rsi_core(gain, loss, p):
    a = 1.0 / p
    ag = pd.Series(gain).ewm(alpha=a, adjust=False).mean().values
    al = pd.Series(loss).ewm(alpha=a, adjust=False).mean().values
    return 100 - 100 / (1 + ag / np.where(al == 0, 1e-10, al))

def fast_all_rsi(prices, max_period=200):
    delta = np.diff(prices, prepend=prices[0])
    g, l = np.clip(delta, 0, None), np.clip(-delta, 0, None)
    return np.vstack([_rsi_core(g, l, p) for p in range(1, max_period + 1)])

def fast_rsi_last(prices, max_period=200):
    return fast_all_rsi(prices, max_period)[:, -1]

def rsi_series(prices, p=14):
    delta = np.diff(prices, prepend=prices[0])
    return _rsi_core(np.clip(delta, 0, None), np.clip(-delta, 0, None), p)

def detect_divergence(prices, rsi14, look=60):
    """واگرایی معمولی: کف/سقف قیمتی جدید بدون تأیید RSI."""
    if len(prices) < look: return None
    p, r = prices[-look:], rsi14[-look:]
    h = look // 2
    i1, i2 = np.argmin(p[:h]), np.argmin(p[h:])
    if p[h:][i2] < p[:h][i1] - 1e-9 and r[h:][i2] > r[:h][i1] + 1e-9: return "bull"
    j1, j2 = np.argmax(p[:h]), np.argmax(p[h:])
    if p[h:][j2] > p[:h][j1] + 1e-9 and r[h:][j2] < r[:h][j1] - 1e-9: return "bear"
    return None

# ==============================================================================
# 3) کش + دانلود موازی
# ==============================================================================
TIMEFRAMES = ['1', '3', '5', '15', '30', '60', '120', '240', '360', '720', 'D', 'W', 'M']
TF_NAMES = {'1': '1m', '3': '3m', '5': '5m', '15': '15m', '30': '30m', '60': '1H', '120': '2H',
            '240': '4H', '360': '6H', '720': '12H', 'D': '1D', 'W': '1W', 'M': '1M'}
CACHE = {"symbol": None, "ts": 0.0, "data": {}, "ms": 0}

def get_all_timeframes(symbol, force=False):
    now = time.time()
    if not force and CACHE["symbol"] == symbol and (now - CACHE["ts"]) < 45 and CACHE["data"]:
        return CACHE["data"], CACHE["ms"]
    t0 = time.time(); out = {}
    with ThreadPoolExecutor(max_workers=13) as ex:
        futs = {ex.submit(get_klines, symbol, tf): tf for tf in TIMEFRAMES}
        for f in as_completed(futs):
            df = f.result()
            if not df.empty: out[futs[f]] = df
    ms = int((time.time() - t0) * 1000)
    CACHE.update(symbol=symbol, ts=now, data=out, ms=ms)
    return out, ms

# ==============================================================================
# 4) موتور سیگنال دقیق (هم‌گرایی MA + RSI + واگرایی)
# ==============================================================================
def analyze_tf(df):
    prices = df["close"].values; cur = prices[-1]
    ma_last = fast_ma_last(prices, 200)
    ma20, ma50 = ma_last[19], ma_last[49]
    ma_align = float(np.mean(ma_last < cur) * 100)
    spread = float((ma_last.max() - ma_last.min()) / cur * 100)

    rsi_last = fast_rsi_last(prices, 200)
    rsi14 = float(rsi_last[13])
    rsi_align = float(np.mean(rsi_last > 50) * 100)
    div = detect_divergence(prices, rsi_series(prices, 14))

    if cur > ma20 and cur > ma50 and ma20 > ma50: trend, ts_ = "صعودی قوی", 2
    elif cur > ma20 and cur > ma50: trend, ts_ = "صعودی", 1
    elif cur < ma20 and cur < ma50 and ma20 < ma50: trend, ts_ = "نزولی قوی", -2
    elif cur < ma20 and cur < ma50: trend, ts_ = "نزولی", -1
    else: trend, ts_ = "خنثی", 0

    # --- امتیازدهی هم‌گرایی برای دقت بیشتر ---
    bull = bear = 0
    bull += 2 if ma_align >= 60 else 0;  bear += 2 if ma_align <= 40 else 0
    bull += 1 if ts_ > 0 else 0;         bear += 1 if ts_ < 0 else 0
    bull += 1 if rsi_align >= 55 else 0; bear += 1 if rsi_align <= 45 else 0
    bull += 1 if rsi14 < 32 else 0;      bear += 1 if rsi14 > 68 else 0
    bull += 2 if div == "bull" else 0;   bear += 2 if div == "bear" else 0

    if bull >= 4 and bull - bear >= 2:   sig, scol = "خرید قوی", "#155724"
    elif bull >= 3 and bull > bear:      sig, scol = "خرید", "#1a7a4c"
    elif bear >= 4 and bear - bull >= 2: sig, scol = "فروش قوی", "#721c24"
    elif bear >= 3 and bear > bull:      sig, scol = "فروش", "#c0392b"
    else:                                sig, scol = "انتظار", "#856404"
    conf = int(100 * max(bull, bear) / max(1, bull + bear)) if (bull + bear) else 50

    return dict(cur=cur, ma20=ma20, ma50=ma50, ma_align=ma_align, spread=spread,
                rsi14=rsi14, rsi_align=rsi_align, div=div, trend=trend, ts=ts_,
                sig=sig, scol=scol, conf=conf)

def overall_verdict(a, data):
    """روند کلی ترکیبی + اجماع مولتی‌تایم‌فریم."""
    score = 0.45 * a["ma_align"] + 0.35 * a["rsi_align"] + 0.20 * a["rsi14"]
    if score >= 68: label, emoji, col = "روند کلی: صعودی قوی", "🟢", "#1a7a4c"
    elif score >= 55: label, emoji, col = "روند کلی: صعودی", "🟢", "#27ae60"
    elif score > 45: label, emoji, col = "روند کلی: رنج / بدون جهت", "⚖️", "#f39c12"
    elif score > 32: label, emoji, col = "روند کلی: نزولی", "🔴", "#e67e22"
    else: label, emoji, col = "روند کلی: نزولی قوی", "🔴", "#c0392b"
    bulls = sum(1 for df in data.values() if not df.empty and analyze_tf(df)["ts"] > 0)
    bears = sum(1 for df in data.values() if not df.empty and analyze_tf(df)["ts"] < 0)
    return label, emoji, col, score, bulls, bears

# ==============================================================================
# 5) نمودارهای 3D (MA و RSI) — استفاده کامل از پتانسیل سه‌بعدی
# ==============================================================================
def _ds(df, max_pts=220):
    n = len(df); step = max(1, n // max_pts)
    x = np.arange(0, n, step)
    return x, step

def build_ma_3d(df, symbol, interval, mode):
    prices = df["close"].values.astype(float); vols = df["volume"].values.astype(float)
    x, step = _ds(df); m = len(x)
    p_ds, v_ds = prices[x], vols[x]
    t_lbl = df["ts"].iloc[x].dt.strftime("%m-%d %H:%M").values
    Zf = fast_all_ma(prices, 200); Z = Zf[:, x]; y = np.arange(1, 201); cur = prices[-1]

    if mode == "discount":
        SZ = (cur - Z) / Z * 100; cs, ct = "RdYlGn", "فاصله از قیمت %"
        lim = float(np.nanpercentile(np.abs(SZ), 98)) + 1e-6; cmin, cmax = -lim, lim
    elif mode == "momentum":
        look = max(2, m // 12)
        prev = np.empty_like(Z); prev[:, look:] = Z[:, :-look]; prev[:, :look] = Z[:, :look]
        SZ = (Z - prev) / np.where(prev == 0, 1e-9, prev) * 100; cs, ct = "RdYlGn", "شیب MA %"
        lim = float(np.nanpercentile(np.abs(SZ), 98)) + 1e-6; cmin, cmax = -lim, lim
    else:
        SZ, cs, ct, cmin, cmax = Z, "Plasma", "قیمت", None, None

    fig = go.Figure()
    fig.add_trace(go.Surface(x=x, y=y, z=Z, surfacecolor=SZ, colorscale=cs, cmin=cmin, cmax=cmax,
                             opacity=0.95, colorbar=dict(title=ct, thickness=14, len=0.75), name="MA 1-200"))
    fig.add_trace(go.Scatter3d(x=x, y=np.ones(m), z=p_ds, mode="lines", line=dict(color="white", width=9), name="قیمت"))
    fig.add_trace(go.Scatter3d(x=x, y=np.ones(m), z=p_ds, mode="lines", line=dict(color="#1b3a63", width=4), showlegend=False))
    for p, colr in [(20, "#f1c40f"), (50, "#e67e22"), (100, "#00d2ff"), (200, "#ff2d55")]:
        fig.add_trace(go.Scatter3d(x=x, y=np.full(m, p), z=Z[p-1], mode="lines", line=dict(color=colr, width=5), name=f"MA {p}"))
    zmin, zmax = float(Z.min()), float(Z.max()); span = (zmax - zmin) or 1.0; vmax = v_ds.max() or 1.0
    vx, vy, vz = [], [], []
    for i in range(m):
        h = 0.18 * span * (v_ds[i] / vmax)
        vx += [x[i], x[i], None]; vy += [205, 205, None]; vz += [zmin - .07*span, zmin - .07*span + h, None]
    fig.add_trace(go.Scatter3d(x=vx, y=vy, z=vz, mode="lines", hoverinfo="skip", line=dict(color="rgba(110,110,140,.5)", width=2), name="حجم"))
    d = Zf[19] - Zf[49]; cross = np.where(np.diff(np.sign(d)) != 0)[0] + 1
    if len(cross):
        gx, gy, gz, gc, gt = [], [], [], [], []
        for ci in cross[-6:]:
            gold = d[ci] > 0
            gx.append(int(ci // step)); gy.append(50); gz.append(float(Zf[49, ci]))
            gc.append("#16a085" if gold else "#c0392b"); gt.append("کراس طلایی" if gold else "کراس مرگ")
        fig.add_trace(go.Scatter3d(x=gx, y=gy, z=gz, mode="markers+text", text=gt, textposition="top center",
                                   textfont=dict(size=9), marker=dict(size=6, color=gc, symbol="diamond"), name="کراس 20/50"))
    ma_last = Zf[:, -1]
    for vals, colr, tag in [(ma_last[ma_last < cur], "#16a085", "حمایت هم‌گرایی"), (ma_last[ma_last >= cur], "#c0392b", "مقاومت هم‌گرایی")]:
        if len(vals) == 0: continue
        hist, edges = np.histogram(vals, bins=15); i = int(np.argmax(hist))
        lvl = float((edges[i] + edges[i+1]) / 2)
        fig.add_trace(go.Scatter3d(x=[x[0], x[-1]], y=[100, 100], z=[lvl, lvl], mode="lines+text",
                                   text=["", f"{tag} {lvl:,.0f}"], textfont=dict(size=10, color=colr),
                                   line=dict(color=colr, width=3, dash="dash"), name=tag))
    st = max(1, m // 6)
    fig.update_layout(scene=dict(xaxis=dict(title="زمان", tickvals=x[::st].tolist(), ticktext=t_lbl[::st].tolist(),
                                            gridcolor="rgba(190,190,190,.3)"),
                                 yaxis=dict(title="دوره MA", gridcolor="rgba(190,190,190,.3)"),
                                 zaxis=dict(title="قیمت", gridcolor="rgba(190,190,190,.3)"),
                                 camera=dict(eye=dict(x=1.7, y=1.7, z=0.9)), bgcolor="rgba(0,0,0,0)"),
                      legend=dict(orientation="h", y=0.01, font=dict(size=10)),
                      margin=dict(l=25, r=25, b=25, t=45), plot_bgcolor="#f7f1e2", paper_bgcolor="#f7f1e2",
                      title=dict(text=f"تحلیل 3D سیستم MA 1-200 | {symbol} {interval}", font=dict(size=16, family="Tahoma")),
                      uirevision=f"ma-{symbol}-{interval}")
    return fig

def build_rsi_3d(df, symbol, interval, mode):
    prices = df["close"].values.astype(float)
    x, step = _ds(df); m = len(x)
    t_lbl = df["ts"].iloc[x].dt.strftime("%m-%d %H:%M").values
    Rf = fast_all_rsi(prices, 200); R = Rf[:, x]; y = np.arange(1, 201)

    if mode == "dev":
        SZ = R - 50; ct = "انحراف از 50"
        cmin, cmax = -35, 35
    else:
        SZ = R; ct = "RSI"; cmin, cmax = 0, 100

    fig = go.Figure()
    fig.add_trace(go.Surface(x=x, y=y, z=R, surfacecolor=SZ, colorscale="RdYlGn", cmin=cmin, cmax=cmax,
                             opacity=0.95, colorbar=dict(title=ct, thickness=14, len=0.75), name="RSI 1-200"))
    # خطوط مرجع 30/50/70 در فضای سه‌بعدی
    for lvl, colr, tag in [(70, "#c0392b", "اشباع خرید 70"), (50, "#7f8c8d", "خط میانی 50"), (30, "#16a085", "اشباع فروش 30")]:
        fig.add_trace(go.Scatter3d(x=[x[0], x[-1]], y=[100, 100], z=[lvl, lvl], mode="lines+text",
                                   text=["", tag], textfont=dict(size=10, color=colr),
                                   line=dict(color=colr, width=3, dash="dash"), name=tag))
    # خطوط کلیدی RSI
    for p, colr, w in [(14, "#1b3a63", 7), (50, "#f1c40f", 4), (100, "#00d2ff", 4), (200, "#ff2d55", 4)]:
        fig.add_trace(go.Scatter3d(x=x, y=np.full(m, p), z=R[p-1], mode="lines", line=dict(color=colr, width=w), name=f"RSI {p}"))
    # نشانگر واگرایی فعلی
    div = detect_divergence(prices, rsi_series(prices, 14))
    if div:
        txt = "⚠️ واگرایی مثبت (سیگنال خرید)" if div == "bull" else "⚠️ واگرایی منفی (سیگنال فروش)"
        colr = "#16a085" if div == "bull" else "#c0392b"
        fig.add_trace(go.Scatter3d(x=[x[-1]], y=[14], z=[R[13, -1]], mode="markers+text", text=[txt],
                                   textposition="top center", textfont=dict(size=11, color=colr),
                                   marker=dict(size=9, color=colr, symbol="star"), name="واگرایی"))
    st = max(1, m // 6)
    fig.update_layout(scene=dict(xaxis=dict(title="زمان", tickvals=x[::st].tolist(), ticktext=t_lbl[::st].tolist(),
                                            gridcolor="rgba(190,190,190,.3)"),
                                 yaxis=dict(title="دوره RSI", gridcolor="rgba(190,190,190,.3)"),
                                 zaxis=dict(title="RSI", range=[0, 100], gridcolor="rgba(190,190,190,.3)"),
                                 camera=dict(eye=dict(x=1.7, y=1.7, z=0.9)), bgcolor="rgba(0,0,0,0)"),
                      legend=dict(orientation="h", y=0.01, font=dict(size=10)),
                      margin=dict(l=25, r=25, b=25, t=45), plot_bgcolor="#f7f1e2", paper_bgcolor="#f7f1e2",
                      title=dict(text=f"تحلیل 3D سیستم RSI 1-200 | {symbol} {interval}", font=dict(size=16, family="Tahoma")),
                      uirevision=f"rsi-{symbol}-{interval}")
    return fig

# ==============================================================================
# 6) اجزای رابط کاربری
# ==============================================================================
def telegram_banner():
    return html.A(html.Div([
        html.Span("🌙", style={"fontSize": 32}),
        html.Div([html.Div(f"کانال حرفه‌ای ترید {TELEGRAM_ID}", style={"fontWeight": "bold", "fontSize": 16}),
                  html.Div("سیگنال‌های VIP | تحلیل سه‌بعدی | آموزش اردرفلو — همین حالا رایگان عضو شوید", style={"fontSize": 12})],
                 style={"flex": "1", "textAlign": "right"}),
        html.Div("عضویت در کانال ✈", style={"background": "#fff", "color": "#229ED9", "borderRadius": 8,
                                            "padding": "8px 16px", "fontWeight": "bold", "whiteSpace": "nowrap"}),
    ], style={"display": "flex", "alignItems": "center", "gap": 14, "padding": "12px 18px", "direction": "rtl",
              "background": "linear-gradient(90deg,#229ED9 0%,#1b3a63 100%)", "color": "#fff", "borderRadius": 12,
              "margin": "12px auto", "maxWidth": 1150, "boxShadow": "0 4px 14px rgba(34,158,217,.4)", "cursor": "pointer"}),
        href=TELEGRAM_URL, target="_blank", style={"textDecoration": "none", "display": "block", "padding": "0 16px"})

def kpi_cards(a):
    rsi_col = "#1a7a4c" if a["rsi14"] > 55 else ("#c0392b" if a["rsi14"] < 45 else "#f39c12")
    div_txt = {"bull": "مثبت 🟢", "bear": "منفی 🔴", None: "ندارد ⚪"}[a["div"]]
    cards = [("قیمت لحظه‌ای", f"{a['cur']:,.2f}", "#1b3a63"),
             ("هم‌ترازی MA 1-200", f"{a['ma_align']:.0f}%", "#1a7a4c" if a["ma_align"] >= 50 else "#c0392b"),
             ("RSI (14)", f"{a['rsi14']:.1f}", rsi_col),
             ("هم‌ترازی RSI 1-200", f"{a['rsi_align']:.0f}%", "#1a7a4c" if a["rsi_align"] >= 50 else "#c0392b"),
             ("فشردگی MA", f"{a['spread']:.2f}%", "#8e44ad" if a["spread"] < 3 else "#f39c12"),
             ("واگرایی", div_txt, "#16a085" if a["div"] == "bull" else ("#c0392b" if a["div"] == "bear" else "#7f8c8d"))]
    return html.Div([html.Div([
        html.Div(t, style={"fontSize": 11, "color": "#6b6355", "fontFamily": "Tahoma"}),
        html.Div(v, style={"fontSize": 18, "fontWeight": "bold", "color": c, "fontFamily": "Tahoma"})],
        style={"flex": "1", "minWidth": 150, "background": "#fff", "borderRadius": 10, "padding": "10px",
               "textAlign": "center", "boxShadow": "0 2px 5px rgba(0,0,0,.08)", "borderTop": f"4px solid {c}"})
        for t, v, c in cards], style={"display": "flex", "gap": 10, "justifyContent": "center", "flexWrap": "wrap", "padding": "0 16px"})

def verdict_banner(label, emoji, col, score, bulls, bears):
    conf = int(abs(score - 50) * 2)
    return html.Div([
        html.Div([html.Span(emoji, style={"fontSize": 34, "marginLeft": 12}),
                  html.Div([html.Div(label, style={"fontSize": 20, "fontWeight": "bold", "color": col}),
                            html.Div(f"اطمینان: {conf}% | اجماع تایم‌فریم‌ها: {bulls} صعودی / {bears} نزولی",
                                     style={"fontSize": 12, "color": "#6b6355"})], style={"textAlign": "right"})],
                 style={"display": "flex", "alignItems": "center", "justifyContent": "center", "direction": "rtl"}),
        html.Div([html.Div(style={"width": f"{score:.0f}%", "background": "linear-gradient(90deg,#c0392b,#f39c12,#1a7a4c)",
                                  "height": 8, "borderRadius": 4})],
                 style={"background": "#eee", "height": 8, "borderRadius": 4, "marginTop": 10}),
    ], style={"background": "#fff", "borderRadius": 12, "padding": "16px 20px", "maxWidth": 1150,
              "margin": "12px auto", "boxShadow": "0 3px 10px rgba(0,0,0,.1)", "borderRight": f"6px solid {col}"})

ROW_BG = {2: "#d4edda", 1: "#e8f8f5", 0: "#fff8e6", -1: "#fdf0f0", -2: "#f8d7da"}

def build_table(data):
    th = lambda t, w: html.Th(t, style={"width": w, "padding": "8px 3px", "fontSize": 12, "background": "#1b3a63", "color": "#fff", "fontFamily": "Tahoma"})
    rows = []
    for tf in TIMEFRAMES:
        df = data.get(tf)
        if df is None or df.empty: continue
        a = analyze_tf(df)
        td = lambda ch, b=False: html.Td(ch, style={"padding": "5px 3px", "fontSize": 11, "textAlign": "center",
                                                    "fontFamily": "Tahoma", "borderBottom": "1px solid #e5e0d2",
                                                    "fontWeight": "bold" if b else "normal"})
        rows.append(html.Tr([
            td(TF_NAMES[tf], True), td(f"{a['cur']:,.1f}"),
            td(html.Span(a["trend"], style={"color": "#155724" if a["ts"] > 0 else ("#721c24" if a["ts"] < 0 else "#856404")})),
            td(f"{a['rsi14']:.0f}"),
            td(html.Div([html.Div(style={"width": f"{a['ma_align']:.0f}%", "background": "#1a7a4c" if a['ma_align'] >= 50 else "#c0392b", "height": 5, "borderRadius": 3})],
                        style={"background": "#eee", "height": 5, "borderRadius": 3, "width": "88%", "margin": "auto"})),
            td({"bull": "🟢", "bear": "🔴", None: "⚪"}[a["div"]]),
            td(html.Div([html.Span(f"{a['sig']} ", style={"color": a["scol"], "fontWeight": "bold"}),
                         html.Span(f"{a['conf']}%", style={"fontSize": 10, "color": "#888"})])),
        ], style={"background": ROW_BG[a["ts"]]}))
    return html.Table([html.Thead(html.Tr([th("TF", "8%"), th("قیمت", "16%"), th("روند MA", "16%"), th("RSI14", "9%"),
                                           th("هم‌ترازی MA1-200", "20%"), th("واگ.", "8%"), th("سیگنال+اطمینان", "23%")])),
                       html.Tbody(rows)],
                      style={"width": "100%", "tableLayout": "fixed", "borderCollapse": "collapse", "background": "#fff",
                             "borderRadius": 10, "overflow": "hidden", "boxShadow": "0 3px 8px rgba(0,0,0,.1)"})

# ==============================================================================
# 7) اپ Dash با رابط تب‌دار
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY], title="BITMOON 3D Analyzer")
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY], title="BITMOON 3D Analyzer")

# ================= چینش کاملاً راست‌به‌چپ (RTL) در سطح سند =================
app.index_string = '''<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
{%metas%}
<title>{%title%}</title>
{%favicon%}
{%css%}
<style>
  html, body { direction: rtl !important; text-align: right !important; }
  body, button, input, select, textarea,
  .dash-dropdown, .Select-control, .Select-menu-outer, .Select-value,
  .navbar-brand, th, td, label, div {
     font-family: Tahoma, "Segoe UI", Arial, sans-serif !important;
  }
  /* چیدمان فلکس/گرید بوت‌استرپ طبق جهت rtl راست‌به‌چپ می‌شود */
  .row, .navbar, .card-body, .dash-cell { direction: rtl !important; }
  /* نمودارهای Plotly باید داخلی LTR بمانند تا محورها به‌هم نریزند */
  .js-plotly-plot, .svg-container, .gl-container, .plot-container { direction: ltr !important; }
  /* منوی کشویی راست‌چین */
  .Select-menu-outer { text-align: right; }
</style>
</head>
<body dir="rtl">
{%app_entry%}
<footer>
{%config%}
{%scripts%}
{%renderer%}
</footer>
</body>
</html>'''
app.layout = html.Div([
    dbc.Navbar(color="dark", dark=True, children=dbc.Container(fluid=True, children=[
        dbc.NavbarBrand("🌙 BITMOON 3D Analyzer", style={"fontFamily": "Tahoma", "fontWeight": "bold"}),
        dbc.Button("✈ تلگرام BITMOON618", href=TELEGRAM_URL, target="_blank", color="info", size="sm",
                   style={"fontFamily": "Tahoma", "fontWeight": "bold"})])),
    telegram_banner(),
    dbc.Card(dbc.CardBody([
        dbc.Row([
            dbc.Col([html.Label("نماد:", style={"fontFamily": "Tahoma", "fontSize": 13}),
                     dcc.Input(id="symbol-input", value="BTCUSDT", style={"width": "100%", "padding": 6, "borderRadius": 6, "border": "1px solid #ccc"})], md=2),
            dbc.Col([html.Label("تایم‌فریم 3D:", style={"fontFamily": "Tahoma", "fontSize": 13}),
                     dcc.Dropdown(id="interval-dropdown", value="15", clearable=False,
                                  options=[{"label": TF_NAMES[t], "value": t} for t in ["1", "5", "15", "60", "240", "D"]])], md=2),
            dbc.Col([html.Label("مود رنگ MA:", style={"fontFamily": "Tahoma", "fontSize": 13}),
                     dcc.RadioItems(id="ma-mode-radio", value="price", inline=True, style={"fontSize": 12},
                                    options=[{"label": "قیمت", "value": "price"}, {"label": "پریمیوم", "value": "discount"}, {"label": "مومنتوم", "value": "momentum"}])], md=4),
            dbc.Col([html.Label("مود رنگ RSI:", style={"fontFamily": "Tahoma", "fontSize": 13}),
                     dcc.RadioItems(id="rsi-mode-radio", value="value", inline=True, style={"fontSize": 12},
                                    options=[{"label": "مقدار RSI", "value": "value"}, {"label": "انحراف از 50", "value": "dev"}])], md=2),
            dbc.Col(dbc.Button("🔄 تحلیل مجدد", id="refresh-btn", color="primary", className="mt-3",
                               style={"fontFamily": "Tahoma", "fontWeight": "bold", "width": "100%"}), md=2),
        ])]), style={"maxWidth": 1180, "margin": "0 auto"}),
    html.Div(id="verdict-wrap"),
    html.Div(id="kpi-row"),
    dbc.Card(dbc.CardBody(dbc.Tabs(id="tabs", active_tab="tab-ma", children=[
        dbc.Tab(label="📈 تحلیل 3D مووینگ‌ها", tab_id="tab-ma", children=dcc.Graph(id="ma-3d-chart", style={"height": "68vh"})),
        dbc.Tab(label="📉 تحلیل 3D RSI", tab_id="tab-rsi", children=dcc.Graph(id="rsi-3d-chart", style={"height": "68vh"})),
    ])), style={"maxWidth": 1180, "margin": "12px auto"}),
    html.H4("📊 سیگنال هم‌گرایی در همه تایم‌فریم‌ها", style={"textAlign": "center", "fontFamily": "Tahoma", "color": "#1b3a63", "margin": "16px 0 8px"}),
    html.Div(id="table-wrap", style={"maxWidth": 1150, "margin": "0 auto", "padding": "0 16px"}),
    telegram_banner(),
    html.Div(id="status-msg", style={"textAlign": "center", "color": "#1a7a4c", "fontFamily": "Tahoma", "fontWeight": "bold", "padding": "12px 0 22px"}),
    dcc.Interval(id="interval-component", interval=60_000, n_intervals=0),
], style={"background": "#f7f1e2", "minHeight": "100vh"})

@app.callback(Output("ma-3d-chart", "figure"), Output("rsi-3d-chart", "figure"),
              Output("kpi-row", "children"), Output("verdict-wrap", "children"),
              Output("table-wrap", "children"), Output("status-msg", "children"),
              Input("refresh-btn", "n_clicks"), Input("interval-component", "n_intervals"),
              Input("tabs", "active_tab"), Input("ma-mode-radio", "value"), Input("rsi-mode-radio", "value"),
              State("symbol-input", "value"), State("interval-dropdown", "value"))
def update(n_clicks, n_int, active_tab, ma_mode, rsi_mode, symbol, interval_3d):
    symbol = (symbol or "BTCUSDT").upper()
    ctx = dash.callback_context
    force = bool(ctx.triggered and ctx.triggered[0]["prop_id"].startswith("refresh-btn"))
    data, ms = get_all_timeframes(symbol, force=force)
    if not data:
        return (go.Figure(), go.Figure(), html.Div(), html.Div(), html.Div(), "❌ اتصال به بایبیت برقرار نشد.")

    df_3d = data.get(interval_3d)
    if df_3d is None or df_3d.empty: df_3d = data.get("15")
    if df_3d is None or df_3d.empty: df_3d = next(iter(data.values()))
    a = analyze_tf(df_3d)
    label, emoji, col, score, bulls, bears = overall_verdict(a, data)

    fig_ma = build_ma_3d(df_3d, symbol, interval_3d, ma_mode) if active_tab == "tab-ma" else dash.no_update
    fig_rsi = build_rsi_3d(df_3d, symbol, interval_3d, rsi_mode) if active_tab == "tab-rsi" else dash.no_update

    return (fig_ma, fig_rsi, kpi_cards(a), verdict_banner(label, emoji, col, score, bulls, bears),
            build_table(data),
            f"✅ {len(data)} تایم‌فریم در {ms}ms | بروزرسانی: {pd.Timestamp.now().strftime('%H:%M:%S')}")
if __name__ == "__main__":
    import webbrowser
    from threading import Timer

    # باز کردن خودکار مرورگر ۱.۲ ثانیه بعد از شروع سرور
    Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:8050/")).start()

    # use_reloader=False باعث می‌شود اسکریپت فقط یک‌بار اجرا شود
    # (وگرنه با debug=True مرورگر دو بار باز می‌شود)
    app.run(debug=True, port=8050, use_reloader=False)