# -*- coding: utf-8 -*-
"""
🌙 ChronoGann Dynamic Square — مربع گن دینامیک کرونوگن
================================================================================
سیستم «کرونوگن»: بازآفرینی نوین از Square of Nine گن به‌صورت یک ماتریس لایه‌لایه‌ی
زنده که مرکزش (Seed) با جریان قیمت هم‌گام می‌شود و با هر تیکِ قیمت، کل لایه‌ها
بازمحاسبه و رنگ‌آمیزی می‌شوند.

ریاضیات پایه (Square of Nine پیوسته):
    θ(P)  = 180 × (√P − √S)            → زاویه‌ی قیمت P نسبت به Seed (درجه، علامت‌دار)
    P(θ)  = (√S + θ/180)²              → قیمت روی زاویه θ
    یک دور کامل (360°) = +2 در فضای رادیکال (قانون کلاسیک گن)

ماتریس لایه‌ای:
    سلول (i,j): شعاع شوراشفسکی m = max(|dx|,|dy|) → لایه‌ی m
    φ = زاویه‌ی هندسی پادساعتگرد از شرق → θ = 360·m + φ
    مقاومت‌ها: P(θ) رو به بیرون | حمایت‌ها: آینه‌ی رادیکالی P(−θ)

کشف حمایت/مقاومت استاتیک:
    همه‌ی سطوح ۸ پرتو اصلی (0/45/90/…/315) در L لایه ساخته می‌شوند؛ سپس با
    اسکن تاریخچه (تاچ، ریجکشن سایه، حجم وزنی و تازگی برخورد) امتیازدهی و
    قوی‌ترین سطوح بالای/پایین قیمت زنده استخراج می‌شوند.

نصب:
pip install dash dash-bootstrap-components plotly pandas numpy requests
اجرا:
python chronogann_square.py   →   http://127.0.0.1:8075
"""

import math
import numpy as np
import pandas as pd
import requests
import dash
from dash import dcc, html, Input, Output, State, ctx, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

# ==============================================================================
# 0) پالت رنگی تیره — هماهنگ با BITMOON
# ==============================================================================
BG      = "#0b1220"
CARD    = "#121c30"
LINE    = "#23314d"
TXT     = "#e8ecf4"
MUT     = "#8fa3c0"
GOLD    = "#f0b90b"
UP      = "#16a085"
DN      = "#e74c3c"
VIOLET  = "#9b59b6"

DEFAULT_SYMBOL    = "BTCUSDT"
DEFAULT_CATEGORY  = "linear"
DEFAULT_INTERVAL  = "15"
DEFAULT_LAYERS    = 4          # تعداد حلقه‌های ماتریس (هر لایه = یک دور کامل ۳۶۰°)
DEFAULT_TOP_N     = 8          # تعداد سطوح کلیدی در هر سمت
DEFAULT_TOL       = 0.35       # تلورانس تاچ (%) برای اعتبارسنجی تاریخی
MAX_WINDOW_PCT    = 12.0       # فقط سطوح داخل ±۱۲٪ قیمت زنده

MASTER_ANGLES = [              # (زاویه، کد، نام فارسی، کاردینال؟)
    (0,   "E",  "شرق",       True),
    (45,  "NE", "شمال‌شرق",  False),
    (90,  "N",  "شمال",      True),
    (135, "NW", "شمال‌غرب",  False),
    (180, "W",  "غرب",       True),
    (225, "SW", "جنوب‌غرب",  False),
    (270, "S",  "جنوب",      True),
    (315, "SE", "جنوب‌شرق",  False),
]
TIME_CYCLES = [30, 45, 60, 90, 120, 144, 180, 270, 360]   # چرخه‌های زمانی گن (تعداد کندل)

INTERVAL_MS = {"1": 60_000, "3": 180_000, "5": 300_000, "15": 900_000,
               "30": 1_800_000, "60": 3_600_000, "240": 14_400_000, "D": 86_400_000}

# ==============================================================================
# 1) اتصال REST پایدار به بایبیت — دقیقاً به روش اسکریپت اصلی
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
# 2) موتور ریاضی کرونوگن — ChronoGann Engine
# ==============================================================================
def angle_to_price(theta_deg, seed):
    """قیمت روی زاویه‌ی θ (علامت‌دار) نسبت به Seed — قانون +۲ رادیکال در هر ۳۶۰°."""
    root = math.sqrt(max(seed, 1e-12)) + theta_deg / 180.0
    if root <= 0:
        return float("nan")
    return root * root


def price_to_angle(price, seed):
    """زاویه‌ی علامت‌دار قیمت نسبت به Seed (درجه)."""
    return 180.0 * (math.sqrt(max(price, 1e-12)) - math.sqrt(max(seed, 1e-12)))


def cell_polar(row, col, center):
    """(لایه‌ی شوراشفسکی m ، زاویه‌ی هندسی φ پادساعتگرد از شرق) برای سلول گرید."""
    dx = col - center
    dy = center - row                      # محور y به بالا
    ring = max(abs(dx), abs(dy))
    phi = math.degrees(math.atan2(dy, dx)) % 360.0
    return ring, phi


def fmt_price(p):
    if not np.isfinite(p):
        return "—"
    ap = abs(p)
    if ap >= 10_000:
        s = f"{p:,.0f}"
    elif ap >= 100:
        s = f"{p:,.2f}"
    elif ap >= 1:
        s = f"{p:,.4f}".rstrip("0").rstrip(".")
    else:
        s = f"{p:.6f}".rstrip("0").rstrip(".")
    return s


def fmt_pct(v, signed=True):
    sign = "+" if (signed and v > 0) else ""
    return f"{sign}{v:.2f}%"


def build_square(seed, layers, direction, live_price):
    """
    ساخت ماتریس مربع گن لایه‌لایه.
    direction=+1 → ماتریس مقاومت (رشد به بیرون) | −1 → ماتریس حمایت (آینه)
    خروجی: z (فاصله‌ی لگاریتمی تا قیمت زنده برای رنگ)، text، hovertext، M
    """
    M = 2 * layers + 1
    c = layers
    Z = np.full((M, M), np.nan)
    TXT_LBL = [[""] * M for _ in range(M)]
    HOVER = [[""] * M for _ in range(M)]

    kind = "مقاومت" if direction > 0 else "حمایت"

    def nearest_master(phi):
        best = min(MASTER_ANGLES, key=lambda t: min(abs(phi - t[0]), 360 - abs(phi - t[0])))
        return best

    for i in range(M):
        for j in range(M):
            ring, phi = cell_polar(i, j, c)
            theta = 360.0 * ring + phi
            p = angle_to_price(theta if direction > 0 else -theta, seed)
            Z[i, j] = abs(math.log(p / live_price)) if (live_price and np.isfinite(p) and live_price > 0) else np.nan
            if ring == 0:
                TXT_LBL[i][j] = fmt_price(seed)
                HOVER[i][j] = f"🎯 Seed (مرکز ماتریس) | {fmt_price(seed)}"
                continue
            ang, code, fa, is_card = nearest_master(phi)
            TXT_LBL[i][j] = fmt_price(p)
            HOVER[i][j] = (f"{kind} | {fmt_price(p)}<br>"
                           f"زاویه: {ang}° ({fa}) {'• کاردینال' if is_card else '• قطری'}<br>"
                           f"لایه: {ring}")
    return {"M": M, "c": c, "Z": Z, "labels": TXT_LBL, "hover": HOVER}


def find_pivots(df, w=8):
    """پیوت‌های سوئینگ تأییدشده (فرکتالی با پنجره‌ی w)."""
    hi, lo = df["high"].values, df["low"].values
    n = len(df)
    ph = pl = None
    for i in range(n - w - 1, w - 1, -1):
        seg_h = hi[i - w:i + w + 1]
        if ph is None and hi[i] == seg_h.max():
            ph = float(hi[i])
        seg_l = lo[i - w:i + w + 1]
        if pl is None and lo[i] == seg_l.min():
            pl = float(lo[i])
        if ph is not None and pl is not None:
            break
    return ph, pl


def resolve_anchor(df, mode, manual_value=None):
    """تعیین Seed به روش هم‌گام (close)، پیوت سقف/کف یا دستی."""
    src = df.iloc[-2] if len(df) > 2 else df.iloc[-1]
    if mode == "manual" and manual_value:
        return float(manual_value), "دستی"
    if mode == "pivot_high":
        ph, _ = find_pivots(df)
        if ph:
            return ph, "پیوت سقف"
    if mode == "pivot_low":
        _, pl = find_pivots(df)
        if pl:
            return pl, "پیوت کف"
    return float(src["close"]), "کلوز آخرین کندل بسته"


def discover_static_levels(df, seed, live_price, layers, tol_pct, top_n):
    """
    کشف حمایت/مقاومت‌های کلیدی استاتیک:
      ساخت سطوح ۸ پرتو اصلی × لایه‌ها → اعتبارسنجی با اسکن تاریخچه:
      تاچ (تلورانس%)، ریجکشن سایه، نسبت حجم برخورد، وزن تازگی → امتیاز ۰..۱۰۰
    """
    hi, lo, cl, vol = (df["high"].values, df["low"].values,
                       df["close"].values, df["volume"].values)
    n = len(cl)
    vol_mu = float(np.mean(vol)) or 1.0
    recency_w = np.linspace(0.4, 1.0, n)          # برخوردهای جدیدتر سنگین‌تر
    out = []
    for L in range(0, int(layers) + 1):
        for ang, code, fa, is_card in MASTER_ANGLES:
            theta = 360.0 * L + ang
            for side, p in (("R", angle_to_price(theta, seed)),
                            ("S", angle_to_price(-theta, seed))):
                if not np.isfinite(p):
                    continue
                dist_pct = (p - live_price) / live_price * 100.0
                if abs(dist_pct) > MAX_WINDOW_PCT:
                    continue
                band = p * tol_pct / 100.0
                overlap = (hi >= p - band) & (lo <= p + band)
                touches = int(overlap.sum())
                if touches == 0:
                    continue
                rej = int(((hi >= p) & (cl < p)).sum()) if side == "R" \
                    else int(((lo <= p) & (cl > p)).sum())
                vol_ratio = float(vol[overlap].mean()) / vol_mu
                last_i = int(np.max(np.nonzero(overlap)[0]))
                score = touches * 8.0 + rej * 12.0 + max(vol_ratio - 1.0, 0.0) * 20.0 \
                        + recency_w[last_i] * 15.0 + (8.0 if is_card else 0.0)
                out.append({
                    "price": p, "side": side, "layer": L, "angle": ang,
                    "code": code, "fa": fa, "cardinal": is_card,
                    "touches": touches, "rejections": rej,
                    "vol_ratio": vol_ratio, "score": min(100.0, score),
                    "dist_pct": dist_pct,
                })
    res = sorted([x for x in out if x["side"] == "R"], key=lambda x: x["dist_pct"])[:top_n]
    sup = sorted([x for x in out if x["side"] == "S"], key=lambda x: -x["dist_pct"])[:top_n]
    return res, sup


def next_cardinals(live_price, seed):
    """نزدیک‌ترین مقاومت/حمایت کاردینال (۰/۹۰/۱۸۰/۲۷۰) بعد از قیمت زنده."""
    best_r = best_s = None
    base_theta = price_to_angle(live_price, seed)
    for rev in range(-30, 31):
        for ang in (0, 90, 180, 270):
            th = 360.0 * rev + ang
            p = angle_to_price(th, seed)
            if not np.isfinite(p):
                continue
            d = (p - live_price) / live_price * 100.0
            if d > 0 and (best_r is None or d < best_r[1]):
                best_r = (p, d, th % 360 or 360)
            if d < 0 and (best_s is None or -d < -best_s[1]):
                best_s = (p, d, th % 360 or 360)
    return base_theta, best_r, best_s


# ==============================================================================
# 3) سازنده‌های نمایش — Figures & Panels
# ==============================================================================
def square_figure(sq, live_price, title_fa, accent, direction, seed, show_labels=True):
    M, c, Z, labels, hover = sq["M"], sq["c"], sq["Z"], sq["labels"], sq["hover"]
    flat_txt = [labels[i][j] for i in range(M) for j in range(M)]
    flat_hov = [hover[i][j] for i in range(M) for j in range(M)]

    zmax = float(np.nanpercentile(Z, 92))
    fig = go.Figure(go.Heatmap(
        z=np.round(Z, 4), x=list(range(M)), y=list(range(M)),
        text=flat_txt, texttemplate="%{text}" if show_labels else "",
        textfont={"size": max(8, min(13, int(150 / M))), "color": TXT, "family": "Consolas"},
        customdata=flat_hov,
        hovertemplate="%{customdata}<extra></extra>",
        colorscale=[[0.0, GOLD], [0.18, "#7a5c08"], [0.55, CARD], [1.0, "#0a0f1a"]],
        zmin=-0.02, zmax=max(zmax, 0.05), showscale=False,
        xgap=1, ygap=1,
    ))

    # خطوط پرتوهای اصلی (کاردینال طلایی / قطری بنفش کم‌رنگ)
    half = M - 0.5
    for ang, code, fa, is_card in MASTER_ANGLES:
        rad = math.radians(ang)
        x2, y2 = c + half * math.cos(rad), c + half * math.sin(rad)
        fig.add_shape(type="line", x0=c, y0=c, x1=x2, y1=y2,
                      line=dict(color=GOLD if is_card else VIOLET,
                                width=1.6 if is_card else 1.0,
                                dash="solid" if is_card else "dot"),
                      layer="above")

    # قاب لایه‌ها (حلقه‌های متحدالمرکز)
    for k in range(1, c + 1):
        fig.add_shape(type="rect", x0=c - k - 0.5, y0=c - k - 0.5,
                      x1=c + k + 0.5, y1=c + k + 0.5,
                      line=dict(color=LINE, width=1), opacity=0.45,
                      layer="above")

    # نشانگر موقعیت زنده‌ی قیمت داخل مربع (شعاع پیوسته)
    th_live = direction * price_to_angle(live_price, seed)
    R_live = math.floor(th_live / 360.0)
    phi_live = th_live - 360.0 * R_live
    r_norm = (R_live + phi_live / 360.0) / max(c, 1)
    r_norm = min(max(r_norm, 0.0), 1.0)
    rad = math.radians(phi_live)
    mx, my = c + r_norm * half * math.cos(rad), c + r_norm * half * math.sin(rad)
    fig.add_trace(go.Scatter(
        x=[mx], y=[my], mode="markers",
        marker=dict(size=17, color="#ffffff", symbol="diamond",
                    line=dict(color=accent, width=3)),
        name=f"💰 {fmt_price(live_price)}",
        hovertemplate=f"💰 قیمت زنده: {fmt_price(live_price)}<extra></extra>",
        showlegend=False,
    ))

    fig.update_layout(
        title=dict(text=title_fa, x=0.5, font=dict(color=accent, size=13)),
        paper_bgcolor=CARD, plot_bgcolor="#0a0f1a",
        font=dict(color=MUT, family="Tahoma"),
        margin=dict(l=8, r=8, t=34, b=8),
        xaxis=dict(visible=False, constrain="domain"),
        yaxis=dict(visible=False, scaleanchor="x", scaleratio=1),
        height=None,
    )
    fig.update_xaxes(range=[-0.5, M - 0.5])
    fig.update_yaxes(range=[M - 0.5, -0.5])   # شمال (ردیف ۰) بالا
    return fig


def candles_figure(df, symbol, interval, res_levels, sup_levels, seed,
                   cycles_on, bar_ms):
    fig = go.Figure(data=[go.Candlestick(
        x=df["ts"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color=UP, decreasing_line_color=DN, name=symbol,
    )])

    def add_level(lv, side):
        color = DN if side == "R" else UP
        dash = "solid" if lv["cardinal"] else "dash"
        width = 1.4 + lv["score"] / 100.0 * 1.6
        fig.add_shape(type="line", xref="paper", x0=0, x1=1, y0=lv["price"], y1=lv["price"],
                      line=dict(color=color, width=width, dash=dash),
                      opacity=0.35 + lv["score"] / 100.0 * 0.5)
        fig.add_annotation(xref="paper", x=0.01, y=lv["price"],
                           text=(f"{'◆' if lv['cardinal'] else '◇'} "
                                 f"{fmt_price(lv['price'])} | S{lv['score']:.0f} "
                                 f"| L{lv['layer']}·{lv['code']}"),
                           showarrow=False, font=dict(color=color, size=10),
                           bgcolor="rgba(11,18,32,.72)", xanchor="left")

    for lv in res_levels:
        add_level(lv, "R")
    for lv in sup_levels:
        add_level(lv, "S")

    fig.add_shape(type="line", xref="paper", x0=0, x1=1, y0=seed, y1=seed,
                  line=dict(color=GOLD, width=2, dash="dot"))
    fig.add_annotation(xref="paper", x=0.01, y=seed, text=f"🌱 Seed: {fmt_price(seed)}",
                       showarrow=False, font=dict(color=GOLD, size=11),
                       bgcolor="rgba(11,18,32,.85)", xanchor="left")

    if cycles_on and bar_ms:
        t_last = df["ts"].iloc[-1]
        for ncyc in TIME_CYCLES:
            t_fut = t_last + pd.Timedelta(milliseconds=bar_ms * ncyc)
            fig.add_vline(x=t_fut, line=dict(color=VIOLET, width=1, dash="dash"), opacity=0.5)
            fig.add_annotation(x=t_fut, y=1.04, yref="paper", text=f"T+{ncyc}",
                               showarrow=False, font=dict(color=VIOLET, size=9))

    fig.update_layout(
        template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor="#0a0f1a",
        font=dict(color=TXT),
        xaxis=dict(gridcolor=LINE, rangeslider_visible=False),
        yaxis=dict(gridcolor=LINE, side="right"),
        margin=dict(l=10, r=52, t=30, b=10),
        title=dict(text=f"{symbol} · {interval} — سطوح استاتیک کشف‌شده",
                   x=0.5, font=dict(color=GOLD, size=13)),
        showlegend=False,
    )
    return fig


def levels_panel(res_levels, sup_levels):
    def rows(levels, side):
        color = DN if side == "R" else UP
        icon = "🔴" if side == "R" else "🟢"
        out = []
        for lv in levels:
            bar_w = int(lv["score"])
            out.append(html.Div([
                html.Div([
                    html.Span(f"{icon} {fmt_price(lv['price'])}",
                              style={"fontWeight": "bold", "color": TXT}),
                    html.Span(f"{lv['dist_pct']:+.2f}%",
                              style={"color": MUT, "fontSize": 11}),
                ], style={"display": "flex", "justifyContent": "space-between"}),
                html.Div([
                    html.Span(f"L{lv['layer']} · {lv['code']} {'کاردینال' if lv['cardinal'] else 'قطری'}",
                              style={"fontSize": 10, "color": MUT}),
                    html.Span(f"تاچ {lv['touches']} | ریج {lv['rejections']}",
                              style={"fontSize": 10, "color": MUT}),
                ], style={"display": "flex", "justifyContent": "space-between", "marginTop": 2}),
                html.Div(style={"height": 4, "background": LINE, "borderRadius": 3,
                                "marginTop": 4, "overflow": "hidden"},
                         children=[html.Div(style={"height": 4, "width": f"{bar_w}%",
                                                   "background": color})]),
            ], style={"background": BG, "border": f"1px solid {LINE}", "borderRight":
                      f"3px solid {color}", "borderRadius": 6, "padding": "6px 8px",
                      "marginBottom": 6}))
        return out

    def block(title, items, accent):
        return html.Div([
            html.Div(title, style={"color": accent, "fontWeight": "bold",
                                   "fontSize": 12, "marginBottom": 6}),
            *(items if items else [html.Div("— سطح معتبری در بازه پیدا نشد —",
                                            style={"color": MUT, "fontSize": 11})]),
        ])

    return html.Div([
        block("🔴 مقاومت‌های کلیدی استاتیک", rows(res_levels, "R"), DN),
        html.Hr(style={"borderColor": LINE, "margin": "8px 0"}),
        block("🟢 حمایت‌های کلیدی استاتیک", rows(sup_levels, "S"), UP),
    ])


def stats_strip(live_price, prev_close, seed, seed_src, theta, nxt_r, nxt_s, layers_now):
    chg = (live_price - prev_close) / prev_close * 100.0 if prev_close else 0.0
    chg_col = UP if chg >= 0 else DN

    def cell(label, value, vcol=TXT, sub=""):
        return dbc.Col(html.Div([
            html.Div(label, style={"fontSize": 10, "color": MUT}),
            html.Div(value, style={"fontSize": 15, "fontWeight": "bold", "color": vcol}),
            html.Div(sub, style={"fontSize": 9, "color": MUT}),
        ], style={"textAlign": "center"}), width=2)

    nr_txt = f"{fmt_price(nxt_r[0])} ({nxt_r[1]:+.2f}%)" if nxt_r else "—"
    ns_txt = f"{fmt_price(nxt_s[0])} ({nxt_s[1]:+.2f}%)" if nxt_s else "—"
    return dbc.Row([
        cell("💰 قیمت زنده", fmt_price(live_price), chg_col, f"{fmt_pct(chg)} نسبت به کندل قبل"),
        cell("🌱 Seed فعال", fmt_price(seed), GOLD, f"حالت: {seed_src}"),
        cell("🧭 زاویه فعلی θ", f"{theta % 360:,.1f}°", TXT, f"لایه فعلی: {layers_now}"),
        cell("🔺 مقاومت کاردینال بعدی", nr_txt, DN),
        cell("🔻 حمایت کاردینال قبلی", ns_txt, UP),
    ], className="g-1")


# ==============================================================================
# 4) اپ Dash
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG],
                meta_tags=[{"name": "viewport",
                            "content": "width=device-width, initial-scale=1"}])
app.title = "ChronoGann Dynamic Square"
server = app.server

CATEGORY_OPTS = [{"label": v, "value": v} for v in ["linear", "spot", "inverse"]]
INTERVAL_OPTS = [{"label": lbl, "value": val} for lbl, val in [
    ("1m", "1"), ("3m", "3"), ("5m", "5"), ("15m", "15"),
    ("30m", "30"), ("1h", "60"), ("4h", "240"), ("1D", "D"),
]]
ANCHOR_OPTS = [
    {"label": "هم‌گام با کلوز (زنده)", "value": "close"},
    {"label": "پیوت سقف", "value": "pivot_high"},
    {"label": "پیوت کف", "value": "pivot_low"},
    {"label": "دستی", "value": "manual"},
]

ctrl_style = {"fontSize": 12, "color": MUT}

app.layout = html.Div(style={"background": BG, "minHeight": "100vh",
                             "padding": "10px", "direction": "rtl"}, children=[
    dbc.Card(dbc.CardBody([
        dbc.Row([
            dbc.Col([html.Label("نماد:", style=ctrl_style),
                     dcc.Input(id="symbol-input", value=DEFAULT_SYMBOL, type="text",
                               style={"width": "100%", "padding": 6, "borderRadius": 6,
                                      "background": BG, "color": TXT, "border": f"1px solid {LINE}"})],
                    md=2),
            dbc.Col([html.Label("بازار:", style=ctrl_style),
                     dcc.Dropdown(id="category-dropdown", value=DEFAULT_CATEGORY,
                                  clearable=False, options=CATEGORY_OPTS)], md=2),
            dbc.Col([html.Label("تایم‌فریم:", style=ctrl_style),
                     dcc.Dropdown(id="interval-dropdown", value=DEFAULT_INTERVAL,
                                  clearable=False, options=INTERVAL_OPTS)], md=2),
            dbc.Col([html.Label("حالت Seed:", style=ctrl_style),
                     dcc.Dropdown(id="anchor-dropdown", value="close",
                                  clearable=False, options=ANCHOR_OPTS)], md=3),
            dbc.Col([html.Label("Seed دستی:", style=ctrl_style),
                     dcc.Input(id="manual-seed", type="number", placeholder="مثلاً 60000",
                               style={"width": "100%", "padding": 6, "borderRadius": 6,
                                      "background": BG, "color": TXT, "border": f"1px solid {LINE}"})],
                    md=3),
        ], className="g-2"),
        dbc.Row([
            dbc.Col([html.Label("لایه‌ها (حلقه‌ها):", style=ctrl_style),
                     dcc.Slider(id="layers-slider", min=2, max=6, step=1, value=DEFAULT_LAYERS,
                                marks={i: str(i) for i in range(2, 7)},
                                tooltip={"placement": "bottom", "always_visible": True})], md=3),
            dbc.Col([html.Label("سطوح کلیدی هر سمت:", style=ctrl_style),
                     dcc.Slider(id="topn-slider", min=3, max=12, step=1, value=DEFAULT_TOP_N,
                                marks={i: str(i) for i in range(3, 13, 3)})], md=3),
            dbc.Col([html.Label("تلورانس تاچ %:", style=ctrl_style),
                     dcc.Slider(id="tol-slider", min=0.1, max=1.0, step=0.05, value=DEFAULT_TOL,
                                marks={0.1: "0.1", 0.5: "0.5", 1.0: "1"})], md=3),
            dbc.Col([dbc.Checklist(id="cycles-check",
                                   options=[{"label": " چرخه‌های زمانی گن (T+n)", "value": 1}],
                                   value=[], switch=True,
                                   style={"marginTop": 28, "fontSize": 12, "color": MUT}),
                     dbc.Checklist(id="labels-check",
                                   options=[{"label": " اعداد داخل سلول‌ها", "value": 1}],
                                   value=[1], switch=True,
                                   style={"marginTop": 8, "fontSize": 12, "color": MUT})], md=3),
        ], className="g-2 mt-2"),
        dbc.Row(dbc.Col(dbc.Button("🔄 بروزرسانی", id="refresh-btn", color="warning",
                                   style={"fontWeight": "bold", "color": "#0b1220",
                                          "width": "100%"}), md=12), className="mt-2"),
        html.Hr(style={"borderColor": LINE, "margin": "10px 0"}),
        html.Div(id="stats-strip"),
    ]), style={"maxWidth": 1400, "margin": "0 auto", "background": CARD,
               "border": f"1px solid {LINE}"}),

    dbc.Row([
        dbc.Col([
            html.H5("🌀 مربع گن دینامیک — مقاومت‌ها (رو به بیرون)",
                    style={"color": DN, "fontSize": 13, "margin": "8px 4px"}),
            dcc.Graph(id="res-square", config={"displayModeBar": False},
                      style={"height": "40vh"}),
            html.H5("🌀 مربع گن دینامیک — حمایت‌ها (آینه‌ی رادیکالی)",
                    style={"color": UP, "fontSize": 13, "margin": "8px 4px"}),
            dcc.Graph(id="sup-square", config={"displayModeBar": False},
                      style={"height": "40vh"}),
        ], width=5),
        dbc.Col([
            dcc.Graph(id="candle-chart", style={"height": "56vh"},
                      config={"displaylogo": False}),
            html.H5("🎯 سطوح کلیدی استاتیک کشف‌شده (امتیاز اعتبار تاریخی)",
                    style={"color": GOLD, "fontSize": 13, "margin": "10px 4px"}),
            html.Div(id="levels-panel", style={"maxHeight": "30vh", "overflowY": "auto"}),
        ], width=7),
    ], style={"maxWidth": 1400, "margin": "8px auto"}),

    html.Div(id="conn-status",
             style={"position": "fixed", "bottom": 8, "left": 12,
                    "color": MUT, "fontSize": 11, "direction": "ltr"}),

    dcc.Interval(id="refresh-interval", interval=10_000, n_intervals=0),
], )


@app.callback(
    Output("stats-strip", "children"),
    Output("res-square", "figure"),
    Output("sup-square", "figure"),
    Output("candle-chart", "figure"),
    Output("levels-panel", "children"),
    Output("conn-status", "children"),
    Input("refresh-interval", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    State("symbol-input", "value"),
    State("category-dropdown", "value"),
    State("interval-dropdown", "value"),
    State("anchor-dropdown", "value"),
    State("manual-seed", "value"),
    State("layers-slider", "value"),
    State("topn-slider", "value"),
    State("tol-slider", "value"),
    State("cycles-check", "value"),
    State("labels-check", "value"),
)
def update_all(_n_int, _n_ref, symbol, category, interval, anchor_mode,
               manual_seed, layers, top_n, tol, cycles_val, labels_val):
    symbol = (symbol or DEFAULT_SYMBOL).upper()
    interval = interval or DEFAULT_INTERVAL
    category = category or DEFAULT_CATEGORY

    df = get_klines(symbol, interval, category, limit=500)

    def empty_fig(msg):
        return go.Figure(layout=dict(
            paper_bgcolor=BG, plot_bgcolor=CARD,
            annotations=[dict(text=msg, x=0.5, y=0.5, showarrow=False,
                              font=dict(color=DN, size=14))]))

    if df.empty or len(df) < 20:
        err = empty_fig("❌ دریافت دیتا از بایبیت ناموفق بود.")
        return no_update, err, err, err, no_update, "🔴 قطع"

    live_price = float(df["close"].iloc[-1])
    prev_close = float(df["close"].iloc[-2]) if len(df) > 1 else live_price
    seed, seed_src = resolve_anchor(df, anchor_mode, manual_seed)

    res_sq = build_square(seed, layers, +1, live_price)
    sup_sq = build_square(seed, layers, -1, live_price)

    res_levels, sup_levels = discover_static_levels(df, seed, live_price,
                                                    layers + 1, tol, top_n)
    theta_live, nxt_r, nxt_s = next_cardinals(live_price, seed)
    layer_now = int(math.floor(price_to_angle(live_price, seed) / 360.0))

    stats = stats_strip(live_price, prev_close, seed, seed_src, theta_live,
                        nxt_r, nxt_s, layer_now)
    fig_res = square_figure(res_sq, live_price,
                            f"🌀 Resistance Matrix — Seed {fmt_price(seed)}",
                            DN, +1, seed, show_labels=bool(labels_val))
    fig_sup = square_figure(sup_sq, live_price,
                            f"🌀 Support Matrix — Seed {fmt_price(seed)}",
                            UP, -1, seed, show_labels=bool(labels_val))
    fig_cdl = candles_figure(df, symbol, interval, res_levels, sup_levels, seed,
                             bool(cycles_val), INTERVAL_MS.get(interval))
    panel = levels_panel(res_levels, sup_levels)
    status = (f"🟢 ChronoGann synced @ {pd.Timestamp.now().strftime('%H:%M:%S')} | "
              f"seed={fmt_price(seed)} | θ={theta_live % 360:,.0f}° | layer {layer_now}")

    return stats, fig_res, fig_sup, fig_cdl, panel, status


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8075, use_reloader=False)
