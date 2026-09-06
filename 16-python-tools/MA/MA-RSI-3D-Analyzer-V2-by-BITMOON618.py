# -*- coding: utf-8 -*-
"""
🌙 BITMOON INSTITUTIONAL 3D TREND TERMINAL (نسخه اصلاح‌شده)
----------------------------------------------------------------------
اصلاحات این نسخه:
 - رفع کامل خطای `titlefont` در محورهای سه‌بعدی Plotly (استفاده از ساختار جدید title=dict)
 - حفظ تمام قابلیت‌های نهادی: بدون ریپینت، تحلیل زنجیره‌ای TII/RII/CTI، قفل سیگنال، RTL کامل.

pip install dash dash-bootstrap-components plotly pandas numpy requests
"""

import time, webbrowser
import requests
import numpy as np
import pandas as pd
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from threading import Timer
from concurrent.futures import ThreadPoolExecutor, as_completed

TELEGRAM_URL, TELEGRAM_ID = "https://t.me/BITMOON618", "BITMOON618"

# ── پالت نهادی تیره ────────────────────────────────────────────────
BG, CARD, LINE, TXT, MUT = "#0b1220", "#121c30", "#23314d", "#e8ecf4", "#8fa3c0"
GOLD, UP, DN = "#f0b90b", "#16a085", "#e74c3c"

# ==============================================================================
# 1) اتصال پایدار بایبیت
# ==============================================================================
REST_CANDIDATES = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept": "application/json", "Referer": "https://www.bybit.com/"})
_ACTIVE = {"url": None}

def bybit_get(path, params, timeout=10):
    cands = ([_ACTIVE["url"]] if _ACTIVE["url"] else []) + [b for b in REST_CANDIDATES if b != _ACTIVE["url"]]
    for base in cands:
        try:
            r = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code in (403, 451): continue
            r.raise_for_status(); d = r.json()
            if d.get("retCode") == 0:
                _ACTIVE["url"] = base; return d
        except Exception: continue
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
# 2) هسته محاسبات برداری + تحلیل زنجیره‌ای (بدون ریپینت)
# ==============================================================================
def closed_only(df):
    return df.iloc[:-1].reset_index(drop=True) if len(df) > 2 else df

def fast_all_ma(prices, P=200):
    n = len(prices); z = np.zeros((P, n)); c = np.cumsum(prices)
    for p in range(1, P + 1):
        if p == 1: z[0] = prices
        elif p <= n:
            z[p-1, :p-1] = c[:p-1] / np.arange(1, p)
            z[p-1, p-1:] = (c[p-1:] - np.concatenate(([0], c[:-p]))) / p
        else: z[p-1] = c / np.arange(1, n + 1)
    return z

def _rsi_core(g, l, p):
    a = 1.0 / p
    ag = pd.Series(g).ewm(alpha=a, adjust=False).mean().values
    al = pd.Series(l).ewm(alpha=a, adjust=False).mean().values
    return 100 - 100 / (1 + ag / np.where(al == 0, 1e-10, al))

def fast_all_rsi(prices, P=200):
    d = np.diff(prices, prepend=prices[0])
    return np.vstack([_rsi_core(np.clip(d, 0, None), np.clip(-d, 0, None), p) for p in range(1, P + 1)])

def chain_integrity(Z):
    return np.mean(Z[:-1] > Z[1:], axis=0) * 100.0

def locked_signal(cti):
    state, changes = 0, []
    for i, v in enumerate(cti):
        if v >= 70 and state != 1: state = 1; changes.append((i, 1))
        elif v <= 30 and state != -1: state = -1; changes.append((i, -1))
        elif state == 1 and v < 50: state = 0; changes.append((i, 0))
        elif state == -1 and v > 50: state = 0; changes.append((i, 0))
    return state, changes

def detect_divergence(p, r, look=60):
    if len(p) < look: return None
    p, r = p[-look:], r[-look:]; h = look // 2
    i1, i2 = np.argmin(p[:h]), np.argmin(p[h:])
    if p[h:][i2] < p[:h][i1] - 1e-9 and r[h:][i2] > r[:h][i1] + 1e-9: return "bull"
    j1, j2 = np.argmax(p[:h]), np.argmax(p[h:])
    if p[h:][j2] > p[:h][j1] + 1e-9 and r[h:][j2] < r[:h][j1] - 1e-9: return "bear"
    return None

def regime_of(v):
    if v >= 75: return "صعودی قوی", 2
    if v >= 60: return "صعودی", 1
    if v > 40: return "رنج", 0
    if v > 25: return "نزولی", -1
    return "نزولی قوی", -2

def analyze_tf(df):
    cl = closed_only(df)
    pc = cl["close"].values
    cur = df["close"].values[-1]
    Z = fast_all_ma(pc); R = fast_all_rsi(pc)
    tii = chain_integrity(Z); rii = chain_integrity(R)
    cti = 0.6 * tii + 0.4 * rii
    tii_l, rii_l, cti_l = tii[-1], rii[-1], cti[-1]
    reg, rs = regime_of(cti_l)
    state, changes = locked_signal(cti)
    ma_last = Z[:, -1]
    spread = float((ma_last.max() - ma_last.min()) / pc[-1] * 100)
    div = detect_divergence(pc, _rsi_core(np.clip(np.diff(pc, prepend=pc[0]), 0, None),
                                          np.clip(-np.diff(pc, prepend=pc[0]), 0, None), 14))
    conf = int(min(99, abs(cti_l - 50) * 2 + (8 if (div == "bull" and state == 1) or (div == "bear" and state == -1) else 0)))
    lock_ts = cl["ts"].iloc[changes[-1][0]] if changes else cl["ts"].iloc[-1]
    sig = {1: "خرید", -1: "فروش", 0: "انتظار"}[state]
    if state == 1 and cti_l >= 75: sig = "خرید قوی"
    if state == -1 and cti_l <= 25: sig = "فروش قوی"
    return dict(cur=cur, cti=cti_l, tii=tii_l, rii=rii_l, reg=reg, rs=rs, state=state,
                sig=sig, conf=conf, div=div, spread=spread, lock_ts=lock_ts,
                rsi14=float(R[13, -1]), series=dict(tii=tii, rii=rii, cti=cti, ts=cl["ts"], changes=changes))

# ==============================================================================
# 3) کش + دانلود موازی
# ==============================================================================
TIMEFRAMES = ['1', '3', '5', '15', '30', '60', '120', '240', '360', '720', 'D', 'W', 'M']
TF_NAMES = {'1': '1m', '3': '3m', '5': '5m', '15': '15m', '30': '30m', '60': '1H', '120': '2H',
            '240': '4H', '360': '6H', '720': '12H', 'D': '1D', 'W': '1W', 'M': '1M'}
W = {'1': 1, '3': 1, '5': 2, '15': 2, '30': 3, '60': 4, '120': 4, '240': 5, '360': 5, '720': 6, 'D': 7, 'W': 8, 'M': 8}
CACHE = {"symbol": None, "ts": 0.0, "data": {}, "ms": 0}

def get_all(symbol, force=False):
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
# 4) نمودارهای 3D + پنل زنجیره (تم تیره) — اصلاح ساختار title
# ==============================================================================
def _axis(title_text=""):
    """ساختار صحیح تنظیمات محور در Plotly: title یک شیء دیکشنری با text و font است."""
    return dict(
        title=dict(text=title_text, font=dict(color=MUT, size=10, family="Tahoma")),
        gridcolor=LINE,
        tickfont=dict(color=MUT, size=9, family="Tahoma"),
        color=MUT
    )

def build_ma_3d(df, symbol, interval, mode):
    prices = df["close"].values.astype(float); vols = df["volume"].values.astype(float)
    n = len(prices); step = max(1, n // 220); x = np.arange(0, n, step); m = len(x)
    p_ds, v_ds = prices[x], vols[x]
    t_lbl = df["ts"].iloc[x].dt.strftime("%m-%d %H:%M").values
    Zf = fast_all_ma(prices); Z = Zf[:, x]; y = np.arange(1, 201); cur = prices[-1]
    if mode == "discount":
        SZ = (cur - Z) / Z * 100; cs, ct = "RdYlGn", "فاصله %"
        lim = float(np.nanpercentile(np.abs(SZ), 98)) + 1e-6; cmin, cmax = -lim, lim
    elif mode == "momentum":
        lk = max(2, m // 12); pv = np.empty_like(Z); pv[:, lk:] = Z[:, :-lk]; pv[:, :lk] = Z[:, :lk]
        SZ = (Z - pv) / np.where(pv == 0, 1e-9, pv) * 100; cs, ct = "RdYlGn", "شیب %"
        lim = float(np.nanpercentile(np.abs(SZ), 98)) + 1e-6; cmin, cmax = -lim, lim
    else: SZ, cs, ct, cmin, cmax = Z, "Plasma", "قیمت", None, None
    fig = go.Figure()
    fig.add_trace(go.Surface(x=x, y=y, z=Z, surfacecolor=SZ, colorscale=cs, cmin=cmin, cmax=cmax, opacity=0.95,
                             colorbar=dict(title=ct, thickness=12, len=0.75, tickfont=dict(color=MUT, family="Tahoma")), name="MA 1-200"))
    fig.add_trace(go.Scatter3d(x=x, y=np.ones(m), z=p_ds, mode="lines", line=dict(color="white", width=9), name="قیمت"))
    fig.add_trace(go.Scatter3d(x=x, y=np.ones(m), z=p_ds, mode="lines", line=dict(color=GOLD, width=3), showlegend=False))
    for p, c2 in [(20, "#f1c40f"), (50, "#e67e22"), (100, "#00d2ff"), (200, "#ff2d55")]:
        fig.add_trace(go.Scatter3d(x=x, y=np.full(m, p), z=Z[p-1], mode="lines", line=dict(color=c2, width=5), name=f"MA {p}"))
    zmin, zmax = float(Z.min()), float(Z.max()); span = (zmax - zmin) or 1; vmax = v_ds.max() or 1
    vx, vy, vz = [], [], []
    for i in range(m):
        h = 0.18 * span * (v_ds[i] / vmax)
        vx += [x[i], x[i], None]; vy += [205, 205, None]; vz += [zmin - .07*span, zmin - .07*span + h, None]
    fig.add_trace(go.Scatter3d(x=vx, y=vy, z=vz, mode="lines", hoverinfo="skip", line=dict(color="rgba(143,163,192,.4)", width=2), name="حجم"))
    d = Zf[19] - Zf[49]; cross = np.where(np.diff(np.sign(d)) != 0)[0] + 1
    if len(cross):
        gx, gz, gc, gt = [], [], [], []
        for ci in cross[-6:]:
            g = d[ci] > 0
            gx.append(int(ci // step)); gz.append(float(Zf[49, ci]))
            gc.append(UP if g else DN); gt.append("کراس طلایی" if g else "کراس مرگ")
        fig.add_trace(go.Scatter3d(x=gx, y=[50]*len(gx), z=gz, mode="markers+text", text=gt, textposition="top center",
                                   textfont=dict(size=9, color=TXT, family="Tahoma"), marker=dict(size=6, color=gc, symbol="diamond"), name="کراس 20/50"))
    ma_last = Zf[:, -1]
    for vals, c2, tag in [(ma_last[ma_last < cur], UP, "حمایت هم‌گرایی"), (ma_last[ma_last >= cur], DN, "مقاومت هم‌گرایی")]:
        if len(vals) == 0: continue
        hst, ed = np.histogram(vals, bins=15); i = int(np.argmax(hst)); lvl = float((ed[i] + ed[i+1]) / 2)
        fig.add_trace(go.Scatter3d(x=[x[0], x[-1]], y=[100, 100], z=[lvl, lvl], mode="lines+text", text=["", f"{tag} {lvl:,.0f}"],
                                   textfont=dict(size=10, color=c2, family="Tahoma"), line=dict(color=c2, width=3, dash="dash"), name=tag))
    st = max(1, m // 6)
    fig.update_layout(scene=dict(xaxis=dict(**_axis("زمان"), tickvals=x[::st].tolist(), ticktext=t_lbl[::st].tolist()),
                                 yaxis=dict(**_axis("دوره MA")), zaxis=dict(**_axis("قیمت")),
                                 camera=dict(eye=dict(x=1.7, y=1.7, z=0.9)), bgcolor="rgba(0,0,0,0)"),
                      legend=dict(orientation="h", y=0.01, font=dict(size=10, color=MUT, family="Tahoma")),
                      margin=dict(l=25, r=25, b=25, t=45), paper_bgcolor=BG,
                      title=dict(text=f"سطح 3D سیستم MA 1-200 | {symbol} {interval}", font=dict(size=15, color=GOLD, family="Tahoma")),
                      uirevision=f"ma-{symbol}-{interval}")
    return fig

def build_rsi_3d(df, symbol, interval, mode):
    prices = df["close"].values.astype(float)
    n = len(prices); step = max(1, n // 220); x = np.arange(0, n, step); m = len(x)
    t_lbl = df["ts"].iloc[x].dt.strftime("%m-%d %H:%M").values
    Rf = fast_all_rsi(prices); R = Rf[:, x]; y = np.arange(1, 201)
    SZ = R - 50 if mode == "dev" else R
    ct = "انحراف از 50" if mode == "dev" else "RSI"
    cmin, cmax = (-35, 35) if mode == "dev" else (0, 100)
    fig = go.Figure()
    fig.add_trace(go.Surface(x=x, y=y, z=R, surfacecolor=SZ, colorscale="RdYlGn", cmin=cmin, cmax=cmax, opacity=0.95,
                             colorbar=dict(title=ct, thickness=12, len=0.75, tickfont=dict(color=MUT, family="Tahoma")), name="RSI 1-200"))
    for lvl, c2, tag in [(70, DN, "اشباع خرید 70"), (50, MUT, "خط میانی 50"), (30, UP, "اشباع فروش 30")]:
        fig.add_trace(go.Scatter3d(x=[x[0], x[-1]], y=[100, 100], z=[lvl, lvl], mode="lines+text", text=["", tag],
                                   textfont=dict(size=10, color=c2, family="Tahoma"), line=dict(color=c2, width=3, dash="dash"), name=tag))
    for p, c2, w in [(14, GOLD, 7), (50, "#f1c40f", 4), (100, "#00d2ff", 4), (200, "#ff2d55", 4)]:
        fig.add_trace(go.Scatter3d(x=x, y=np.full(m, p), z=R[p-1], mode="lines", line=dict(color=c2, width=w), name=f"RSI {p}"))
    cl = closed_only(df); pc = cl["close"].values
    div = detect_divergence(pc, _rsi_core(np.clip(np.diff(pc, prepend=pc[0]), 0, None), np.clip(-np.diff(pc, prepend=pc[0]), 0, None), 14))
    if div:
        txt = "واگرایی مثبت (خرید)" if div == "bull" else "واگرایی منفی (فروش)"
        c2 = UP if div == "bull" else DN
        fig.add_trace(go.Scatter3d(x=[x[-1]], y=[14], z=[R[13, -1]], mode="markers+text", text=[txt], textposition="top center",
                                   textfont=dict(size=11, color=c2, family="Tahoma"), marker=dict(size=9, color=c2, symbol="diamond-open"), name="واگرایی"))
    st = max(1, m // 6)
    fig.update_layout(scene=dict(xaxis=dict(**_axis("زمان"), tickvals=x[::st].tolist(), ticktext=t_lbl[::st].tolist()),
                                 yaxis=dict(**_axis("دوره RSI")), zaxis=dict(**_axis("RSI"), range=[0, 100]),
                                 camera=dict(eye=dict(x=1.7, y=1.7, z=0.9)), bgcolor="rgba(0,0,0,0)"),
                      legend=dict(orientation="h", y=0.01, font=dict(size=10, color=MUT, family="Tahoma")),
                      margin=dict(l=25, r=25, b=25, t=45), paper_bgcolor=BG,
                      title=dict(text=f"سطح 3D سیستم RSI 1-200 | {symbol} {interval}", font=dict(size=15, color=GOLD, family="Tahoma")),
                      uirevision=f"rsi-{symbol}-{interval}")
    return fig

def build_integrity(a, symbol, interval):
    s = a["series"]
    n = len(s["cti"]); step = max(1, n // 300); x = np.arange(n)[::step]
    tl = s["ts"].iloc[::step].dt.strftime("%m-%d %H:%M").values
    fig = go.Figure()
    fig.add_hrect(y0=70, y1=100, fillcolor="rgba(22,160,133,.12)", line_width=0)
    fig.add_hrect(y0=0, y1=30, fillcolor="rgba(231,76,60,.12)", line_width=0)
    for lvl, c2 in [(70, UP), (30, DN), (50, MUT)]:
        fig.add_hline(y=lvl, line=dict(color=c2, width=1, dash="dot"))
    fig.add_trace(go.Scatter(x=x, y=s["cti"][::step], name="CTI ترکیبی", line=dict(color=GOLD, width=2.6)))
    fig.add_trace(go.Scatter(x=x, y=s["tii"][::step], name="TII زنجیره MA", line=dict(color="#00d2ff", width=1.2)))
    fig.add_trace(go.Scatter(x=x, y=s["rii"][::step], name="RII زنجیره RSI", line=dict(color="#e05fd0", width=1.2)))
    if s["changes"]:
        ci = [c[0] for c in s["changes"]]; cv = [s["cti"][i] for i in ci]
        cc = [UP if c[1] == 1 else (DN if c[1] == -1 else MUT) for c in s["changes"]]
        fig.add_trace(go.Scatter(x=ci, y=cv, mode="markers", name="تغییر قفل سیگنال",
                                 marker=dict(size=8, color=cc, symbol="diamond")))
    fig.update_layout(plot_bgcolor=CARD, paper_bgcolor=BG, height=260, margin=dict(l=40, r=20, t=35, b=30),
                      xaxis=dict(gridcolor=LINE, tickfont=dict(color=MUT, size=9, family="Tahoma"), tickvals=x[::max(1, len(x)//6)].tolist(),
                                 ticktext=tl[::max(1, len(tl)//6)].tolist(), title=dict(text="", font=dict(size=1))),
                      yaxis=dict(gridcolor=LINE, range=[0, 100], tickfont=dict(color=MUT, size=9, family="Tahoma"), title=dict(text="", font=dict(size=1))),
                      legend=dict(orientation="h", y=1.12, font=dict(size=10, color=MUT, family="Tahoma")),
                      title=dict(text=f"🔗 یکپارچگی زنجیره روند (بدون ریپینت) | {symbol} {interval}", font=dict(size=13, color=GOLD, family="Tahoma")))
    return fig

# ==============================================================================
# 5) اجزای UI (تم تیره + RTL)
# ==============================================================================
def telegram_banner():
    return html.A(html.Div([
        html.Span("🌙", style={"fontSize": 30}),
        html.Div([html.Div([html.Span("کانال نهادی ترید ", style={"fontWeight": "bold"}),
                            html.Span(TELEGRAM_ID, dir="ltr", style={"fontWeight": "bold", "color": "#ffd75e"})]),
                  html.Div("سیگنال‌های قفل‌شده بدون ریپینت | تحلیل 3D | اردرفلو — عضویت رایگان", style={"fontSize": 11})],
                 style={"flex": "1", "textAlign": "right"}),
        html.Div("عضویت ✈", style={"background": GOLD, "color": "#0b1220", "borderRadius": 8, "padding": "8px 18px",
                                   "fontWeight": "bold", "whiteSpace": "nowrap"}),
    ], style={"display": "flex", "alignItems": "center", "gap": 14, "padding": "12px 18px", "direction": "rtl",
              "background": "linear-gradient(90deg,#121c30 0%,#1a2b4a 60%,#229ED9 130%)", "color": TXT, "borderRadius": 12,
              "margin": "12px auto", "maxWidth": 1150, "border": f"1px solid {LINE}", "boxShadow": "0 4px 16px rgba(240,185,11,.15)"}),
        href=TELEGRAM_URL, target="_blank", style={"textDecoration": "none", "display": "block", "padding": "0 16px"})

def kpi_cards(a):
    sc = UP if a["state"] == 1 else (DN if a["state"] == -1 else MUT)
    cards = [("قیمت", f"{a['cur']:,.2f}", GOLD), ("سیگنال قفل‌شده 🔒", a["sig"], sc),
             ("CTI ترکیبی", f"{a['cti']:.0f}", sc), ("TII زنجیره MA", f"{a['tii']:.0f}", UP if a["tii"] >= 50 else DN),
             ("RII زنجیره RSI", f"{a['rii']:.0f}", UP if a["rii"] >= 50 else DN),
             ("واگرایی", {"bull": "مثبت 🟢", "bear": "منفی 🔴", None: "—"}[a["div"]], UP if a["div"] == "bull" else (DN if a["div"] == "bear" else MUT)),
             ("رژیم", a["reg"], sc)]
    return html.Div([html.Div([
        html.Div(t, style={"fontSize": 10, "color": MUT}),
        html.Div(v, style={"fontSize": 16, "fontWeight": "bold", "color": c})],
        style={"flex": "1", "minWidth": 130, "background": CARD, "borderRadius": 10, "padding": "10px", "textAlign": "center",
               "border": f"1px solid {LINE}", "borderTop": f"3px solid {c}"}) for t, v, c in cards],
        style={"display": "flex", "gap": 8, "justifyContent": "center", "flexWrap": "wrap", "padding": "0 16px"})

def verdict_banner(overall, bulls, bears, lock_ts):
    reg, rs = regime_of(overall)
    col = UP if rs > 0 else (DN if rs < 0 else "#f39c12")
    emoji = "🟢" if rs > 0 else ("🔴" if rs < 0 else "⚖️")
    conf = int(abs(overall - 50) * 2)
    return html.Div([
        html.Div([html.Span(emoji, style={"fontSize": 32, "marginLeft": 12}),
                  html.Div([html.Div(f"روند کلی بازار: {reg}", style={"fontSize": 19, "fontWeight": "bold", "color": col}),
                            html.Div([html.Span(f"اطمینان {conf}% | اجماع: {bulls} صعودی / {bears} نزولی | "),
                                      html.Span("🔒 قفل روی کندل بسته: ", style={"color": MUT}),
                                      html.Span(lock_ts.strftime("%m-%d %H:%M"), dir="ltr", style={"color": GOLD})],
                                     style={"fontSize": 11, "color": MUT})], style={"textAlign": "right"})],
                 style={"display": "flex", "alignItems": "center", "justifyContent": "center", "direction": "rtl"}),
        html.Div([html.Div(style={"width": f"{overall:.0f}%", "background": f"linear-gradient(90deg,{DN},#f39c12,{UP})",
                                  "height": 8, "borderRadius": 4})],
                 style={"background": LINE, "height": 8, "borderRadius": 4, "marginTop": 10})],
        style={"background": CARD, "borderRadius": 12, "padding": "14px 20px", "maxWidth": 1150, "margin": "12px auto",
               "border": f"1px solid {LINE}", "borderRight": f"6px solid {col}"})

ROW_BG = {2: "#0f2b1f", 1: "#0d241c", 0: "#241f10", -1: "#2b1515", -2: "#331010"}

def build_table(rows):
    th = lambda t, w: html.Th(t, style={"width": w, "padding": "8px 3px", "fontSize": 11, "background": GOLD, "color": "#0b1220"})
    trs = []
    for tf in TIMEFRAMES:
        a = rows.get(tf)
        if a is None: continue
        td = lambda ch, b=False: html.Td(ch, style={"padding": "5px 3px", "fontSize": 11, "textAlign": "center", "color": TXT,
                                                    "borderBottom": f"1px solid {LINE}", "fontWeight": "bold" if b else "normal"})
        sc = UP if a["rs"] > 0 else (DN if a["rs"] < 0 else "#f39c12")
        trs.append(html.Tr([
            td(TF_NAMES[tf], True), td(f"{a['cur']:,.1f}"), td(f"{a['cti']:.0f}"), td(f"{a['tii']:.0f}"), td(f"{a['rii']:.0f}"),
            td(html.Span(a["reg"], style={"color": sc})), td({"bull": "🟢", "bear": "🔴", None: "—"}[a["div"]]),
            td(html.Div([html.Span(f"🔒 {a['sig']} ", style={"color": UP if a['state'] == 1 else (DN if a['state'] == -1 else MUT), "fontWeight": "bold"}),
                         html.Span(f"{a['conf']}%", style={"fontSize": 9, "color": MUT})]))],
            style={"background": ROW_BG[a["rs"]]}))
    return html.Table([html.Thead(html.Tr([th("TF", "8%"), th("قیمت", "15%"), th("CTI", "9%"), th("TII", "9%"), th("RII", "9%"),
                                           th("رژیم", "15%"), th("واگ.", "8%"), th("سیگنال قفل‌شده", "27%")])), html.Tbody(trs)],
                      style={"width": "100%", "tableLayout": "fixed", "borderCollapse": "collapse", "background": CARD,
                             "borderRadius": 10, "overflow": "hidden", "border": f"1px solid {LINE}"})

# ==============================================================================
# 6) اپ Dash — RTL کامل + تم تیره
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY], title="BITMOON Terminal")
app.index_string = '''<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
  html, body { direction: rtl !important; text-align: right !important; background: #0b1220 !important; }
  body, button, input, select, label, div, th, td, .navbar-brand,
  .dash-dropdown, .Select-control, .Select-value-label, .Select-option, .Select-placeholder {
     font-family: Tahoma, "Segoe UI", Arial, sans-serif !important; }
  .js-plotly-plot, .svg-container, .gl-container, .plot-container { direction: ltr !important; }
  .Select-control { background: #121c30 !important; border-color: #23314d !important; }
  .Select-menu-outer { background: #121c30 !important; border-color: #23314d !important; text-align: right; }
  .Select-option, .Select-value-label { color: #e8ecf4 !important; }
  .nav-tabs { border-color: #23314d; }
  .nav-link { color: #8fa3c0 !important; font-family: Tahoma !important; }
  .nav-link.active { color: #f0b90b !important; background: #121c30 !important; border-color: #23314d !important; font-weight: bold; }
  .card { background: #121c30 !important; border-color: #23314d !important; }
</style>
</head>
<body dir="rtl">
{%app_entry%}
<footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>'''

app.layout = html.Div([
    dbc.Navbar(color="dark", dark=True, style={"background": CARD, "borderBottom": f"2px solid {GOLD}"},
               children=dbc.Container(fluid=True, children=[
        dbc.NavbarBrand("🌙 BITMOON INSTITUTIONAL TERMINAL", style={"fontWeight": "bold", "color": GOLD}),
        dbc.Button("✈ BITMOON618", href=TELEGRAM_URL, target="_blank", color="warning", size="sm",
                   style={"fontWeight": "bold", "color": "#0b1220"})])),
    telegram_banner(),
    dbc.Card(dbc.CardBody([dbc.Row([
        dbc.Col([html.Label("نماد:", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="symbol-input", value="BTCUSDT", style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
        dbc.Col([html.Label("تایم‌فریم:", style={"fontSize": 12, "color": MUT}),
                 dcc.Dropdown(id="interval-dropdown", value="15", clearable=False,
                              options=[{"label": TF_NAMES[t], "value": t} for t in ["1", "5", "15", "60", "240", "D"]])], md=2),
        dbc.Col([html.Label("مود رنگ MA:", style={"fontSize": 12, "color": MUT}),
                 dcc.RadioItems(id="ma-mode-radio", value="price", inline=True, style={"fontSize": 11, "color": TXT},
                                options=[{"label": "قیمت", "value": "price"}, {"label": "پریمیوم", "value": "discount"}, {"label": "مومنتوم", "value": "momentum"}])], md=3),
        dbc.Col([html.Label("مود رنگ RSI:", style={"fontSize": 12, "color": MUT}),
                 dcc.RadioItems(id="rsi-mode-radio", value="value", inline=True, style={"fontSize": 11, "color": TXT},
                                options=[{"label": "RSI", "value": "value"}, {"label": "انحراف", "value": "dev"}])], md=3),
        dbc.Col(dbc.Button("🔄 تحلیل", id="refresh-btn", color="warning", className="mt-3",
                           style={"fontWeight": "bold", "color": "#0b1220", "width": "100%"}), md=2)]
    )]), style={"maxWidth": 1180, "margin": "10px auto"}),
    html.Div(id="verdict-wrap"),
    html.Div(id="kpi-row"),
    dbc.Card(dbc.CardBody(dbc.Tabs(id="tabs", active_tab="tab-ma", children=[
        dbc.Tab(label="📈 سطح 3D مووینگ‌ها", tab_id="tab-ma", children=dcc.Graph(id="ma-3d-chart", style={"height": "62vh"})),
        dbc.Tab(label="📉 سطح 3D RSI", tab_id="tab-rsi", children=dcc.Graph(id="rsi-3d-chart", style={"height": "62vh"}))])),
        style={"maxWidth": 1180, "margin": "12px auto"}),
    html.Div(dcc.Graph(id="integrity-chart"), style={"maxWidth": 1180, "margin": "0 auto"}),
    html.H4("📊 ماتریس نهادی سیگنال — همه تایم‌فریم‌ها", style={"textAlign": "center", "color": GOLD, "margin": "16px 0 8px"}),
    html.Div(id="table-wrap", style={"maxWidth": 1150, "margin": "0 auto", "padding": "0 16px"}),
    telegram_banner(),
    html.Div(id="status-msg", style={"textAlign": "center", "color": UP, "fontWeight": "bold", "padding": "12px 0 22px"}),
    dcc.Interval(id="interval-component", interval=60_000, n_intervals=0),
], style={"background": BG, "minHeight": "100vh"})

@app.callback(Output("ma-3d-chart", "figure"), Output("rsi-3d-chart", "figure"),
              Output("integrity-chart", "figure"), Output("kpi-row", "children"),
              Output("verdict-wrap", "children"), Output("table-wrap", "children"),
              Output("status-msg", "children"),
              Input("refresh-btn", "n_clicks"), Input("interval-component", "n_intervals"),
              Input("tabs", "active_tab"), Input("ma-mode-radio", "value"), Input("rsi-mode-radio", "value"),
              State("symbol-input", "value"), State("interval-dropdown", "value"))
def update(n_clicks, n_int, active, ma_mode, rsi_mode, symbol, interval_3d):
    symbol = (symbol or "BTCUSDT").upper()
    ctx = dash.callback_context
    force = bool(ctx.triggered and ctx.triggered[0]["prop_id"].startswith("refresh-btn"))
    data, ms = get_all(symbol, force=force)
    if not data:
        return (go.Figure(), go.Figure(), go.Figure(), html.Div(), html.Div(), html.Div(), "❌ اتصال برقرار نشد.")
    df_3d = data.get(interval_3d)
    if df_3d is None or df_3d.empty: df_3d = data.get("15")
    if df_3d is None or df_3d.empty: df_3d = next(iter(data.values()))
    rows = {tf: analyze_tf(df) for tf, df in data.items()}
    a = rows.get(interval_3d) or rows.get("15") or next(iter(rows.values()))
    tot_w = sum(W.get(t, 1) for t in rows)
    overall = sum(W.get(t, 1) * r["cti"] for t, r in rows.items()) / tot_w
    bulls = sum(1 for r in rows.values() if r["rs"] > 0); bears = sum(1 for r in rows.values() if r["rs"] < 0)
    fig_ma = build_ma_3d(df_3d, symbol, interval_3d, ma_mode) if active == "tab-ma" else dash.no_update
    fig_rsi = build_rsi_3d(df_3d, symbol, interval_3d, rsi_mode) if active == "tab-rsi" else dash.no_update
    return (fig_ma, fig_rsi, build_integrity(a, symbol, interval_3d), kpi_cards(a),
            verdict_banner(overall, bulls, bears, a["lock_ts"]), build_table(rows),
            f"✅ {len(data)} تایم‌فریم در {ms}ms | 🔒 بدون ریپینت | {pd.Timestamp.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:8050/")).start()
    app.run(debug=True, port=8050, use_reloader=False)