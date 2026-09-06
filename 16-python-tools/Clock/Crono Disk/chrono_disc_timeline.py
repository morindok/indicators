# -*- coding: utf-8 -*-
"""
🌐 Chrono-Disc Timeline — دیسک زمانی-نجومی برای شناسایی نقاط چرخش قیمت
========================================================================
{Morindok}

ایده: زمین با چرخش خودش (شبانه‌روزی/سیدرال) و مدارش دور خورشید (سالانه) در هر
لحظه یک زاویه‌ی نجومی مشخص دارد. این زاویه به N «کانال زمانی» (Timeline)
تقسیم می‌شود و هر کندل قیمت بر اساس زاویه‌ی لحظه‌ی ثبتش، در یکی از این کانال‌ها
جا می‌گیرد. این ابزار قیمت را به‌صورت اسپیرال روی دیسک رسم می‌کند (شعاع = گذر
زمان، زاویه = موقعیت نجومی) و نقاط چرخش (پیوت‌های فراکتالی) را روی کانال‌ها
هایلایت می‌کند تا خوشه‌بندی احتمالی چرخش‌ها در کانال‌های خاص، به‌صورت بصری
قابل بررسی باشد.

⚠️ این ابزار صرفاً اکتشافی/بصری است، نه اثبات آماری. برای تایید واقعی بودن
اثر، باید طبق روال قبلی (permutation test / walk-forward) روی خروجی آن آزمون
آماری اجرا شود.
"""

import math
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import requests
import plotly.graph_objects as go

import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc

# ==============================================================================
# 0) پالت رنگی
# ==============================================================================
BG = "#070b14"
CARD2 = "#101c38"
LINE = "#22304e"
TXT = "#eef2fb"
MUT = "#8ea0c4"
GOLD = "#f3ba2f"
UP = "#1fd7a6"
DN = "#ff5d6c"
BLUE = "#4f8dfd"

FONT_FAMILY = "Vazirmatn, Tahoma, Arial, sans-serif"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_CATEGORY = "linear"
DEFAULT_INTERVAL = "60"
DEFAULT_LIMIT = 500
DEFAULT_N_CHANNELS = 12
DEFAULT_PIVOT_K = 3

# ==============================================================================
# 1) اتصال پایدار به بایبیت (REST با چند دامنه‌ی جایگزین)
# ==============================================================================
REST_CANDIDATES = [
    "https://api.bybit.com",
    "https://api.bytick.com",
    "https://api.bybit.kz",
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0 Safari/537.36"),
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


def get_server_time():
    d = bybit_get("/v5/market/time", {})
    try:
        res = (d or {}).get("result") or {}
        nano = res.get("timeNano")
        if nano:
            return datetime.fromtimestamp(int(nano) / 1e9, tz=timezone.utc)
        sec = res.get("timeSecond")
        if sec:
            v = int(sec)
            s = str(v)
            if len(s) >= 19:
                sec_f = v / 1e9
            elif len(s) >= 16:
                sec_f = v / 1e6
            elif len(s) >= 13:
                sec_f = v / 1e3
            else:
                sec_f = float(v)
            return datetime.fromtimestamp(sec_f, tz=timezone.utc)
    except Exception:
        pass
    return datetime.now(timezone.utc)


def get_klines(symbol, interval, category="linear", limit=500):
    d = bybit_get("/v5/market/kline", {
        "category": category,
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    })
    if not d or "list" not in (d.get("result") or {}):
        return pd.DataFrame()

    lst = d["result"]["list"]
    if not lst:
        return pd.DataFrame()

    df = pd.DataFrame(
        lst,
        columns=["ts", "open", "high", "low", "close", "volume", "turnover"],
    )
    df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)


def get_interval_minutes(interval):
    s = str(interval).strip().lower()
    if s == "d":
        return 1440
    try:
        return int(s)
    except Exception:
        return 60


# ==============================================================================
# 2) زاویه‌ی نجومی زمین → کانال زمانی
# ==============================================================================
J2000 = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)


def days_since_j2000(dt_utc):
    return (dt_utc - J2000).total_seconds() / 86400.0


def angle_diurnal_utc(dt_utc):
    """ساعت میانگین UTC به‌صورت زاویه (۰=نیمه‌شب, ۳۶۰=یک دور کامل شبانه‌روز)."""
    hf = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0
    return (hf / 24.0 * 360.0) % 360.0


def angle_diurnal_sidereal(dt_utc):
    """زاویه‌ی چرخش زمین نسبت به ستارگان (Earth Rotation Angle - IAU 2000)."""
    d = days_since_j2000(dt_utc)
    era = 280.46061837 + 360.98564736629 * d
    return era % 360.0


def angle_annual_solar(dt_utc):
    """طول دایرة‌البروجی خورشید (ژئوسنتریک، تقریب کم‌دقت Meeus)."""
    n = days_since_j2000(dt_utc)
    L = (280.460 + 0.9856474 * n) % 360.0
    g = math.radians((357.528 + 0.9856003 * n) % 360.0)
    lam = L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)
    return lam % 360.0


ANGLE_FUNCS = {
    "diurnal_utc": angle_diurnal_utc,
    "diurnal_sidereal": angle_diurnal_sidereal,
    "annual_solar": angle_annual_solar,
}
ANGLE_LABEL_FA = {
    "diurnal_utc": "شبانه‌روزی (ساعت میانگین UTC)",
    "diurnal_sidereal": "شبانه‌روزی نجومی (سیدرال / ERA)",
    "annual_solar": "سالانه (طول دایرة‌البروجی خورشید)",
}


def channel_of(angle_deg, n_channels):
    width = 360.0 / n_channels
    return int(angle_deg // width) % n_channels


def channel_label(idx, n_channels, mode):
    width = 360.0 / n_channels
    lo, hi = idx * width, (idx + 1) * width
    if mode == "diurnal_utc":
        lo_h, hi_h = lo / 15.0, hi / 15.0
        return f"#{idx} | {lo:.0f}°-{hi:.0f}° | ~{lo_h:04.1f}h-{hi_h:04.1f}h UTC"
    if mode == "annual_solar":
        base = datetime(2024, 3, 20)  # اعتدال بهاری تقریبی، فقط برای برچسب
        d1 = base + timedelta(days=lo / 360.0 * 365.25)
        d2 = base + timedelta(days=hi / 360.0 * 365.25)
        return f"#{idx} | {lo:.0f}°-{hi:.0f}° | ~{d1.strftime('%d %b')}-{d2.strftime('%d %b')}"
    return f"#{idx} | {lo:.0f}°-{hi:.0f}°"


# ==============================================================================
# 3) تشخیص پیوت فراکتالی
# ==============================================================================
def fractal_pivots(highs, lows, k=3):
    n = len(highs)
    is_high = np.zeros(n, dtype=bool)
    is_low = np.zeros(n, dtype=bool)
    for i in range(k, n - k):
        wh = highs[i - k:i + k + 1]
        wl = lows[i - k:i + k + 1]
        if highs[i] == wh.max() and np.argmax(wh) == k:
            is_high[i] = True
        if lows[i] == wl.min() and np.argmin(wl) == k:
            is_low[i] = True
    return is_high, is_low


# ==============================================================================
# 3b) خوشه‌بندی سطوح حمایت/مقاومت از روی پیوت‌ها
# ==============================================================================
def cluster_levels(prices, timestamps, tol_pct=0.15):
    order = np.argsort(prices)
    prices_sorted = prices[order]
    ts_sorted = [timestamps[i] for i in order]

    clusters = [{"prices": [prices_sorted[0]], "ts": [ts_sorted[0]]}]
    for p, t in zip(prices_sorted[1:], ts_sorted[1:]):
        ref = float(np.mean(clusters[-1]["prices"]))
        if ref > 0 and abs(p - ref) / ref * 100.0 <= tol_pct:
            clusters[-1]["prices"].append(p)
            clusters[-1]["ts"].append(t)
        else:
            clusters.append({"prices": [p], "ts": [t]})

    result = []
    for c in clusters:
        result.append({
            "price": float(np.mean(c["prices"])),
            "touches": len(c["prices"]),
            "last_ts": max(c["ts"]),
        })
    return result


def compute_support_resistance(df, pivot_k, tol_pct=0.15, top_n=2):
    highs = df["high"].values
    lows = df["low"].values
    ts = pd.to_datetime(df["ts"]).dt.tz_localize("UTC").tolist()
    is_high, is_low = fractal_pivots(highs, lows, k=pivot_k)

    prices = np.concatenate([highs[is_high], lows[is_low]]) if (is_high.any() or is_low.any()) else np.array([])
    times = [t for t, m in zip(ts, is_high) if m] + [t for t, m in zip(ts, is_low) if m]

    live_price = float(df.iloc[-1]["close"])
    if len(prices) == 0:
        return [], [], live_price

    clusters = cluster_levels(prices, times, tol_pct)
    max_touches = max(c["touches"] for c in clusters)
    for c in clusters:
        c["strength_pct"] = round(100.0 * c["touches"] / max_touches, 1)
        c["distance"] = c["price"] - live_price
        c["distance_pct"] = c["distance"] / live_price * 100.0 if live_price else 0.0

    resistances = sorted((c for c in clusters if c["price"] > live_price), key=lambda c: c["distance"])[:top_n]
    supports = sorted((c for c in clusters if c["price"] < live_price), key=lambda c: -c["distance"])[:top_n]
    return resistances, supports, live_price


def build_sr_table(resistances, supports, live_price):
    def row(label, c, color):
        return html.Div([
            html.Span(label, style={"width": "20%", "display": "inline-block", "color": color, "fontWeight": 700}),
            html.Span(f"{c['price']:,.6g}", style={"width": "24%", "display": "inline-block", "color": TXT}),
            html.Span(f"{c['distance_pct']:+.2f}%", style={"width": "20%", "display": "inline-block", "color": MUT}),
            html.Span(f"{c['touches']} برخورد", style={"width": "18%", "display": "inline-block", "color": TXT, "fontSize": 11}),
            html.Div(style={"width": f"{c['strength_pct']}%", "maxWidth": "38%", "height": "8px",
                             "background": color, "borderRadius": "4px", "display": "inline-block"}),
        ], style={"marginBottom": 6})

    header = html.Div([
        html.Span("سطح", style={"width": "20%", "display": "inline-block", "color": MUT}),
        html.Span("قیمت", style={"width": "24%", "display": "inline-block", "color": MUT}),
        html.Span("فاصله", style={"width": "20%", "display": "inline-block", "color": MUT}),
        html.Span("تماس", style={"width": "18%", "display": "inline-block", "color": MUT}),
        html.Span("قدرت", style={"display": "inline-block", "color": MUT}),
    ], style={"fontSize": 11, "borderBottom": f"1px solid {LINE}", "paddingBottom": 4, "marginBottom": 6})

    rows = [header]
    res_sorted = sorted(resistances, key=lambda c: -c["distance"])  # دورتر بالا، نزدیک‌تر پایین
    for i, c in enumerate(res_sorted):
        n = len(res_sorted) - i
        rows.append(row(f"مقاومت {n}", c, DN))
    rows.append(html.Div([
        html.Span("💰 قیمت زنده", style={"width": "20%", "display": "inline-block", "color": GOLD, "fontWeight": 700}),
        html.Span(f"{live_price:,.6g}", style={"display": "inline-block", "color": GOLD, "fontWeight": 700}),
    ], style={"margin": "8px 0", "borderTop": f"1px dashed {LINE}", "borderBottom": f"1px dashed {LINE}", "padding": "6px 0"}))
    for i, c in enumerate(supports):
        rows.append(row(f"حمایت {i + 1}", c, UP))

    if not resistances and not supports:
        rows.append(html.Div("پیوت کافی برای شناسایی سطح یافت نشد.", style={"color": MUT, "fontSize": 12}))
    return html.Div(rows)


# ==============================================================================
# 4) ساخت داده‌ی دیسک (اسپیرال زمانی)
# ==============================================================================
def build_disc_data(df, mode, n_channels, pivot_k):
    n = len(df)
    ts = pd.to_datetime(df["ts"]).dt.tz_localize("UTC").tolist()
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values

    fn = ANGLE_FUNCS[mode]
    angles = np.array([fn(t.to_pydatetime()) for t in ts])
    channels = np.array([channel_of(a, n_channels) for a in angles])

    r_min, r_max = 0.18, 1.0
    radii = r_min + (r_max - r_min) * (np.arange(n) / max(n - 1, 1))

    is_high, is_low = fractal_pivots(highs, lows, k=pivot_k)

    ch_stats = []
    for c in range(n_channels):
        mask = channels == c
        n_hi = int(np.sum(is_high & mask))
        n_lo = int(np.sum(is_low & mask))
        ch_stats.append({
            "channel": c,
            "label": channel_label(c, n_channels, mode),
            "n_bars": int(mask.sum()),
            "n_pivot_high": n_hi,
            "n_pivot_low": n_lo,
            "n_pivot_total": n_hi + n_lo,
            "avg_price": float(closes[mask].mean()) if mask.any() else None,
        })

    return {
        "angles": angles, "channels": channels, "radii": radii,
        "closes": closes, "is_high": is_high, "is_low": is_low,
        "ts": ts, "ch_stats": ch_stats,
    }


def to_xy(angle_deg, radius):
    theta = math.radians((90.0 - angle_deg) % 360.0)
    return radius * math.cos(theta), radius * math.sin(theta)


# ==============================================================================
# 5) ساخت فیگور
# ==============================================================================
def empty_fig(msg):
    fig = go.Figure()
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
                       xaxis=dict(visible=False), yaxis=dict(visible=False),
                       font=dict(family=FONT_FAMILY))
    fig.add_annotation(x=0.5, y=0.5, xref="paper", yref="paper", text=msg,
                        showarrow=False, font=dict(size=16, color=DN, family=FONT_FAMILY))
    return fig


def build_disc_figure(df, now_utc, symbol, interval, mode, n_channels, pivot_k):
    if df.empty or len(df) < (2 * pivot_k + 5):
        return empty_fig("داده‌ی کافی از بایبیت دریافت نشد."), None

    data = build_disc_data(df, mode, n_channels, pivot_k)
    n = len(data["closes"])
    fig = go.Figure()

    # --- محیط دیسک ---
    ang_full = np.linspace(0, 360, 361)
    fig.add_trace(go.Scatter(
        x=np.cos(np.radians(ang_full)), y=np.sin(np.radians(ang_full)),
        mode="lines", line=dict(color=LINE, width=2), showlegend=False, hoverinfo="skip",
    ))

    # --- کانال‌ها (خطوط شعاعی + برچسب) ---
    for c in range(n_channels):
        a0 = c * 360.0 / n_channels
        x0, y0 = to_xy(a0, 0.02)
        x1, y1 = to_xy(a0, 1.0)
        fig.add_trace(go.Scatter(
            x=[x0, x1], y=[y0, y1], mode="lines",
            line=dict(color=LINE, width=1, dash="dot"), showlegend=False, hoverinfo="skip",
        ))
        a_mid = a0 + (360.0 / n_channels) / 2.0
        lx, ly = to_xy(a_mid, 1.16)
        fig.add_annotation(x=lx, y=ly, text=f"<b>{c}</b>", showarrow=False,
                            font=dict(size=11, color=GOLD, family=FONT_FAMILY))

    # --- اسپیرال قیمت (شعاع = گذر زمان، زاویه = موقعیت نجومی) ---
    xs, ys = [], []
    for a, r in zip(data["angles"], data["radii"]):
        x, y = to_xy(a, r)
        xs.append(x); ys.append(y)
    xs, ys = np.array(xs), np.array(ys)

    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines", line=dict(color=MUT, width=1), opacity=0.35,
        hoverinfo="skip", showlegend=False,
    ))
    ts_str = [t.strftime("%Y-%m-%d %H:%M") for t in data["ts"]]
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers",
        marker=dict(size=5, color=data["closes"], colorscale="Turbo", showscale=True,
                    colorbar=dict(title="قیمت", thickness=12, len=0.5, y=0.76,
                                  tickfont=dict(color=TXT, size=10),
                                  title_font=dict(color=MUT, size=11)),
                    line=dict(width=0.2, color="#000")),
        customdata=np.column_stack([ts_str, [f"{p:,.6g}" for p in data["closes"]],
                                     data["channels"]]),
        hovertemplate="🕒 %{customdata[0]}<br>💰 %{customdata[1]}<br>📡 کانال %{customdata[2]}<extra></extra>",
        name="قیمت (اسپیرال زمانی)",
    ))

    # --- پیوت‌های سقف/کف ---
    hi_mask, lo_mask = data["is_high"], data["is_low"]
    if hi_mask.any():
        fig.add_trace(go.Scatter(
            x=xs[hi_mask], y=ys[hi_mask], mode="markers",
            marker=dict(size=11, symbol="triangle-up", color=DN,
                        line=dict(width=1, color="#fff")),
            name="پیوت سقف", hovertemplate="سقف: %{customdata}<extra></extra>",
            customdata=[f"{p:,.6g}" for p in data["closes"][hi_mask]],
        ))
    if lo_mask.any():
        fig.add_trace(go.Scatter(
            x=xs[lo_mask], y=ys[lo_mask], mode="markers",
            marker=dict(size=11, symbol="triangle-down", color=UP,
                        line=dict(width=1, color="#fff")),
            name="پیوت کف", hovertemplate="کف: %{customdata}<extra></extra>",
            customdata=[f"{p:,.6g}" for p in data["closes"][lo_mask]],
        ))

    # --- زاویه‌ی لحظه‌ای (زنده) ---
    live_angle = ANGLE_FUNCS[mode](now_utc)
    lx, ly = to_xy(live_angle, 1.0)
    for size, op in [(30, 0.12), (22, 0.20)]:
        fig.add_trace(go.Scatter(x=[lx], y=[ly], mode="markers",
                                  marker=dict(size=size, symbol="star", color=GOLD),
                                  opacity=op, hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(
        x=[lx], y=[ly], mode="markers+text",
        marker=dict(size=15, symbol="star", color=GOLD, line=dict(width=2, color="black")),
        text=[f"اکنون | کانال {channel_of(live_angle, n_channels)}"], textposition="top center",
        textfont=dict(color=GOLD, size=12, family=FONT_FAMILY),
        name=f"موقعیت نجومی لحظه‌ای ({live_angle:.1f}°)",
    ))

    lim = 1.35
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        legend=dict(bgcolor="rgba(15,24,48,0.85)", bordercolor=LINE, borderwidth=1,
                    font=dict(size=10, color=TXT, family=FONT_FAMILY),
                    orientation="h", y=-0.05, x=0.5, xanchor="center"),
        margin=dict(l=10, r=10, t=60, b=10),
        title=dict(
            text=(f"🌐 Chrono-Disc — {symbol} | {interval}m | "
                  f"مدل زاویه: {ANGLE_LABEL_FA.get(mode, mode)} | N={n_channels} | "
                  f"{now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC"),
            x=0.5, font=dict(color=GOLD, size=16, family=FONT_FAMILY),
        ),
        font=dict(family=FONT_FAMILY),
    )
    fig.update_xaxes(range=[-lim, lim], visible=False)
    fig.update_yaxes(range=[-lim, lim], visible=False, scaleanchor="x", scaleratio=1)
    return fig, data


def build_channel_table(ch_stats):
    if not ch_stats:
        return html.Div("داده‌ای موجود نیست.", style={"color": MUT})
    sorted_stats = sorted(ch_stats, key=lambda x: -x["n_pivot_total"])
    max_piv = max((s["n_pivot_total"] for s in ch_stats), default=1) or 1
    rows = []
    header = html.Div([
        html.Span("کانال", style={"width": "18%", "display": "inline-block", "color": MUT}),
        html.Span("پیوت‌ها", style={"width": "14%", "display": "inline-block", "color": MUT}),
        html.Span("میانگین قیمت", style={"width": "28%", "display": "inline-block", "color": MUT}),
        html.Span("توزیع", style={"width": "40%", "display": "inline-block", "color": MUT}),
    ], style={"fontSize": 11, "borderBottom": f"1px solid {LINE}", "paddingBottom": 4, "marginBottom": 4})
    rows.append(header)
    for s in sorted_stats:
        bar_w = int(100 * s["n_pivot_total"] / max_piv) if max_piv else 0
        avg_txt = f"{s['avg_price']:,.4g}" if s["avg_price"] is not None else "—"
        rows.append(html.Div([
            html.Span(f"#{s['channel']}", style={"width": "18%", "display": "inline-block",
                                                   "color": TXT, "fontWeight": 700}),
            html.Span(f"{s['n_pivot_total']} (▲{s['n_pivot_high']}/▼{s['n_pivot_low']})",
                      style={"width": "14%", "display": "inline-block", "color": TXT, "fontSize": 11}),
            html.Span(avg_txt, style={"width": "28%", "display": "inline-block", "color": MUT, "fontSize": 11}),
            html.Div(style={"width": f"{bar_w}%", "height": "8px", "background": GOLD,
                             "borderRadius": "4px", "display": "inline-block"}),
        ], style={"marginBottom": 5}))
    return html.Div(rows)


# ==============================================================================
# 6) اپ Dash
# ==============================================================================
FONT_URL = "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;800&display=swap"
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG, FONT_URL])
app.title = "Chrono-Disc Timeline"
server = app.server

app.index_string = """<!DOCTYPE html>
<html><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
body { background: #070b14; }
* { font-family: 'Vazirmatn', Tahoma, Arial, sans-serif !important; }
.glass-card {
    background: linear-gradient(145deg, rgba(16,28,56,0.85), rgba(10,17,35,0.85));
    border: 1px solid #22304e; border-radius: 16px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.35); backdrop-filter: blur(6px);
}
</style></head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>"""

CATEGORY_OPTS = [{"label": v, "value": v} for v in ["linear", "spot", "inverse"]]
INTERVAL_OPTS = [{"label": lbl, "value": val} for lbl, val in [
    ("15m", "15"), ("30m", "30"), ("1h", "60"), ("2h", "120"), ("4h", "240"), ("1d", "D"),
]]
MODE_OPTS = [{"label": v, "value": k} for k, v in ANGLE_LABEL_FA.items()]
N_CHANNEL_OPTS = [{"label": str(v), "value": v} for v in [4, 6, 8, 9, 12, 16, 24, 36]]

app.layout = html.Div([
    html.Div([
        html.H4("🌐 Chrono-Disc Timeline", style={"color": GOLD, "fontWeight": 800, "margin": 0}),
        html.Div("دیسک زمانی-نجومی برای بررسی خوشه‌بندی نقاط چرخش قیمت — Morindok",
                 style={"color": MUT, "fontSize": 12}),
    ], style={"maxWidth": 1200, "margin": "10px auto 4px auto", "padding": "0 6px"}),

    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([
            html.Label("نماد", style={"fontSize": 11, "color": MUT}),
            dcc.Input(id="symbol", value=DEFAULT_SYMBOL, type="text",
                      style={"width": "100%", "padding": 6, "borderRadius": 8,
                             "background": CARD2, "color": TXT, "border": f"1px solid {LINE}"}),
        ], md=2),
        dbc.Col([
            html.Label("بازار", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="category", value=DEFAULT_CATEGORY, clearable=False, options=CATEGORY_OPTS),
        ], md=1),
        dbc.Col([
            html.Label("تایم‌فریم", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="interval", value=DEFAULT_INTERVAL, clearable=False, options=INTERVAL_OPTS),
        ], md=1),
        dbc.Col([
            html.Label("مدل زاویه نجومی", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="angle-mode", value="diurnal_utc", clearable=False, options=MODE_OPTS),
        ], md=2),
        dbc.Col([
            html.Label("تعداد کانال‌ها (N)", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="n-channels", value=DEFAULT_N_CHANNELS, clearable=False, options=N_CHANNEL_OPTS),
        ], md=1),
        dbc.Col([
            html.Label("حساسیت پیوت (k)", style={"fontSize": 11, "color": MUT}),
            dcc.Input(id="pivot-k", type="number", value=DEFAULT_PIVOT_K, min=1, max=10, step=1,
                      style={"width": "100%", "padding": 6, "borderRadius": 8,
                             "background": CARD2, "color": TXT, "border": f"1px solid {LINE}"}),
        ], md=1),
        dbc.Col([
            html.Label("تعداد کندل", style={"fontSize": 11, "color": MUT}),
            dcc.Input(id="limit", type="number", value=DEFAULT_LIMIT, min=50, max=1000, step=50,
                      style={"width": "100%", "padding": 6, "borderRadius": 8,
                             "background": CARD2, "color": TXT, "border": f"1px solid {LINE}"}),
        ], md=1),
        dbc.Col([
            html.Label("تلورانس سطح (%)", style={"fontSize": 11, "color": MUT}),
            dcc.Input(id="sr-tol", type="number", value=0.15, min=0.01, max=5, step=0.01,
                      style={"width": "100%", "padding": 6, "borderRadius": 8,
                             "background": CARD2, "color": TXT, "border": f"1px solid {LINE}"}),
        ], md=1),
        dbc.Col(
            dbc.Button("🔄 به‌روزرسانی", id="refresh-btn", color="warning", className="mt-3",
                       style={"fontWeight": "bold", "color": BG, "width": "100%", "padding": "8px 6px"}),
            md=1,
        ),
    ])), className="glass-card", style={"maxWidth": 1200, "margin": "10px auto"}),

    dbc.Row([
        dbc.Col(
            dbc.Card(dbc.CardBody([
                dcc.Graph(id="disc-graph", style={"height": "78vh"}, config={"displaylogo": False}),
            ]), className="glass-card"),
            md=8,
        ),
        dbc.Col([
            dbc.Card(dbc.CardBody([
                html.Div("🎯 دو حمایت و مقاومت پیش رو",
                         style={"color": GOLD, "fontWeight": 700, "fontSize": 13, "marginBottom": 10}),
                html.Div(id="sr-table"),
            ]), className="glass-card", style={"marginBottom": 10}),
            dbc.Card(dbc.CardBody([
                html.Div("📊 توزیع پیوت‌ها بر اساس کانال زمانی",
                         style={"color": GOLD, "fontWeight": 700, "fontSize": 13, "marginBottom": 10}),
                html.Div(id="channel-table"),
                html.Hr(style={"borderColor": LINE}),
                html.Div(id="conn-status", style={"fontSize": 11, "color": MUT}),
            ]), className="glass-card"),
        ], md=4),
    ], style={"maxWidth": 1200, "margin": "10px auto"}),

    html.Div(
        "💡 شعاع در اسپیرال نشان‌دهنده‌ی گذر زمان است (مرکز = قدیمی‌ترین کندل، لبه‌ی بیرونی = جدیدترین) و "
        "زاویه، موقعیت نجومی زمین در لحظه‌ی ثبت آن کندل را نشان می‌دهد. اگر نقاط چرخش (▲/▼) در کانال‌های "
        "خاصی خوشه‌بندی شوند، فرضیه‌ی «خط زمانی معین» ارزش بررسی آماری دقیق‌تر (permutation test / "
        "walk-forward) را دارد؛ در غیر این صورت احتمالاً تصادفی توزیع شده‌اند.",
        style={"fontSize": 11, "color": MUT, "marginTop": 4, "direction": "rtl", "lineHeight": "1.7",
               "textAlign": "center", "maxWidth": 1200, "marginLeft": "auto", "marginRight": "auto",
               "padding": "0 12px 16px 12px"},
    ),

    dcc.Interval(id="tick", interval=30_000, n_intervals=0),
], style={"background": BG, "minHeight": "100vh", "padding": "10px", "fontFamily": FONT_FAMILY})


@app.callback(
    Output("disc-graph", "figure"),
    Output("channel-table", "children"),
    Output("sr-table", "children"),
    Output("conn-status", "children"),
    Input("tick", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    State("symbol", "value"),
    State("category", "value"),
    State("interval", "value"),
    State("angle-mode", "value"),
    State("n-channels", "value"),
    State("pivot-k", "value"),
    State("limit", "value"),
    State("sr-tol", "value"),
)
def update(_n, _click, symbol, category, interval, mode, n_channels, pivot_k, limit, sr_tol):
    symbol = (symbol or DEFAULT_SYMBOL).upper().strip()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL
    mode = mode or "diurnal_utc"
    n_channels = int(n_channels or DEFAULT_N_CHANNELS)
    pivot_k = int(pivot_k or DEFAULT_PIVOT_K)
    limit = int(limit or DEFAULT_LIMIT)
    sr_tol = float(sr_tol or 0.15)

    now_utc = get_server_time()
    df = get_klines(symbol, interval, category, limit=limit)

    if df.empty:
        empty_sr = html.Div("داده‌ای موجود نیست.", style={"color": MUT})
        return empty_fig("خطا در دریافت کندل از بایبیت."), html.Div("—"), empty_sr, "🔴 قطع از بایبیت"

    fig, data = build_disc_figure(df, now_utc, symbol, interval, mode, n_channels, pivot_k)
    table = build_channel_table(data["ch_stats"]) if data else html.Div("—")

    resistances, supports, live_price = compute_support_resistance(df, pivot_k, tol_pct=sr_tol, top_n=2)
    sr_table = build_sr_table(resistances, supports, live_price)

    status = f"🟢 متصل | {now_utc.strftime('%H:%M:%S')} UTC | {len(df)} کندل"
    return fig, table, sr_table, status


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8061, use_reloader=False)
