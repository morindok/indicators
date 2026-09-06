# -*- coding: utf-8 -*-
"""
🌙⏰ Bybit UTC Spiral Clock + Professional Future Support/Resistance Predictor
------------------------------------------------------------------
• زمان UTC دقیق از سرور بایبیت: /v5/market/time
• پیش‌بینی حمایت و مقاومت بدون نیاز به scipy
• نمایش سطوح پیش‌بینی‌شده در پنل قیمتی جداگانه با خطوط افقی
• ترکیب پیووت‌های ساختاری + تقاطع‌های فعلی + تقاطع‌های آینده اسپیرال
"""

import numpy as np
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timezone, timedelta

import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc

# ==============================================================================
# 0) پالت رنگی و تنظیمات
# ==============================================================================
BG, CARD, LINE, TXT, MUT = "#0b1220", "#121c30", "#23314d", "#e8ecf4", "#8fa3c0"
GOLD, UP, DN = "#f0b90b", "#16a085", "#e74c3c"
SPIRAL_CLR = "#3498db"
FUTURE_CLR = "#ff00ff"

DEFAULT_SYMBOL   = "BTCUSDT"
DEFAULT_CATEGORY = "linear"
DEFAULT_INTERVAL = "15"
DEFAULT_PIVOT    = 5
DEFAULT_TURNS    = 3
RATIO            = 4.0
DEG              = np.pi / 180.0
FORECAST_HOURS   = 24

# ==============================================================================
# 1) REST پایدار بایبیت + دریافت زمان دقیق سرور
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
    """
    دریافت زمان دقیق UTC از سرور بایبیت.
    اگر به هر دلیل ناموفق بود، زمان سیستم برگردانده می‌شود.
    """
    d = bybit_get("/v5/market/time", {})
    try:
        res = (d or {}).get("result") or {}

        nano = res.get("timeNano")
        if nano:
            ns = int(nano)
            return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)

        sec = res.get("timeSecond")
        if sec:
            v = int(sec)
            s = str(v)

            # Bybit ممکن است میلی‌ثانیه، ثانیه یا نانوثانیه بدهد
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


# ==============================================================================
# 2) پیووت‌ها
# ==============================================================================
def find_last_pivot(highs, lows, period):
    highs = np.asarray(highs, dtype=float)
    lows = np.asarray(lows, dtype=float)
    n = len(highs)

    if n < 2 * period + 1:
        return 0, "none", float(highs[0]) if n > 0 else 0.0

    for i in range(n - period - 1, period - 1, -1):
        window = lows[i - period:i + period + 1]
        if lows[i] <= window.min() + 1e-12:
            return i, "low", float(lows[i])

    for i in range(n - period - 1, period - 1, -1):
        window = highs[i - period:i + period + 1]
        if highs[i] >= window.max() - 1e-12:
            return i, "high", float(highs[i])

    return 0, "none", float(highs[0])


def find_all_pivots(highs, lows, period, lookback=250):
    """
    پیدا کردن پیووت‌های تأییدشده برای ساخت سطوح ساختاری.
    """
    highs = np.asarray(highs, dtype=float)
    lows = np.asarray(lows, dtype=float)
    n = len(highs)

    if n < 2 * period + 1:
        return []

    start = max(period, n - lookback)
    end = n - period
    out = []

    for i in range(start, end):
        w_low = lows[i - period:i + period + 1]
        if lows[i] <= w_low.min() + 1e-12:
            out.append({"price": float(lows[i]), "source": "کف", "index": i})

        w_high = highs[i - period:i + period + 1]
        if highs[i] >= w_high.max() - 1e-12:
            out.append({"price": float(highs[i]), "source": "سقف", "index": i})

    return out


# ==============================================================================
# 3) هندسه اسپیرال و ساعت
# ==============================================================================
def spiral_intersections(phi_deg, th_max, b=None):
    phi = (phi_deg % 360.0) * DEG
    kmax = int(np.floor((th_max - phi) / (2 * np.pi) + 1e-9))
    if kmax < 0:
        return np.empty(0)
    return phi + 2 * np.pi * np.arange(kmax + 1)


def future_theta_intersections(phi_deg, th_start, th_end):
    """
    تقاطع‌های آینده یک زاویه با اسپیرال.
    """
    phi = (phi_deg % 360.0) * DEG
    if th_end <= th_start:
        return np.empty(0)

    k_min = int(np.ceil((th_start - phi) / (2 * np.pi) - 1e-12))
    k_max = int(np.floor((th_end - phi) / (2 * np.pi) + 1e-12))

    if k_max < k_min:
        return np.empty(0)

    thetas = phi + 2 * np.pi * np.arange(k_min, k_max + 1)
    thetas = thetas[(thetas > th_start + 1e-9) & (thetas <= th_end + 1e-9)]
    return thetas


def theta_to_clockstr(theta_deg):
    t = ((90.0 - theta_deg) / 30.0) % 12.0
    if t == 0:
        t = 12.0
    hh = int(t)
    mm = int(round((t - hh) * 60))
    if mm == 60:
        hh = (hh + 1) % 12 or 12
        mm = 0
    return f"{hh:02d}:{mm:02d}"


def get_interval_minutes(interval):
    s = str(interval).strip().lower()
    if s == "d":
        return 1440
    try:
        return int(s)
    except Exception:
        return 15


# ==============================================================================
# 4) موتور پیش‌بینی قیمت بدون scipy
# ==============================================================================
def fit_predict_prices(th_hist, prices, th_future, th_max):
    """
    برازش robust روی قیمت/زاویه.
    اگر داده کافی نباشد، fallback می‌دهد.
    """
    th_future = np.asarray(th_future, dtype=float)
    if len(th_future) == 0:
        return np.empty(0)

    prices = np.asarray(prices, dtype=float)
    if len(prices) < 2:
        last = float(prices[-1]) if len(prices) else 1.0
        return np.full(len(th_future), last)

    base = max(float(th_max), 1e-9)
    xh = np.asarray(th_hist, dtype=float) / base
    xf = th_future / base

    mask = np.isfinite(xh) & np.isfinite(prices)
    if mask.sum() < 2:
        return np.full(len(th_future), float(prices[-1]))

    xh = xh[mask]
    ph = prices[mask]
    last = float(ph[-1])
    rng = max(float(np.ptp(ph)), abs(last) * 0.002, 1e-9)

    degree = 2 if mask.sum() >= 10 else 1
    pred = None

    with np.errstate(all="ignore"):
        try:
            coeff = np.polyfit(xh, ph, degree)
            pred = np.polyval(coeff, xf)
            if not np.all(np.isfinite(pred)):
                raise ValueError("bad polyfit")
        except Exception:
            try:
                coeff = np.polyfit(xh, ph, 1)
                pred = np.polyval(coeff, xf)
                if not np.all(np.isfinite(pred)):
                    raise ValueError("bad linear fit")
            except Exception:
                pred = last + (xf - 1.0) * rng * 0.25

    pred = np.where(np.isfinite(pred), pred, last)

    # مهار خروجی‌های پرت
    lower = last - 5 * rng
    upper = last + 5 * rng
    pred = np.clip(pred, lower, upper)

    return pred


def make_future_points(prices, th_hist, th_max, th_cw, th_ccw,
                       last_closed_time, now_utc, interval_min,
                       forecast_hours=FORECAST_HOURS):
    """
    ساخت نقاط چرخه‌ای آینده از تقاطع عقربه‌ها با ادامه اسپیرال.
    """
    n = len(prices)
    if n < 2:
        return []

    th_step = th_max / (n - 1)
    future_candles = max(1, int(forecast_hours * 60 / interval_min))
    th_end = th_max + th_step * future_candles

    pairs = []

    for phi, src in ((th_cw, "CW"), (th_ccw, "CCW")):
        thetas = future_theta_intersections(phi, th_max, th_end)
        pairs.extend([(float(t), src) for t in thetas])

    # اگر تقاطع‌های عقربه کم بود، شبکه زمانی آینده اضافه می‌شود
    if len(pairs) < 5:
        num = min(future_candles, 80)
        if num > 0:
            grid = np.linspace(th_max + th_step, th_end, num)
            pairs.extend([(float(t), "Grid") for t in grid])

    if not pairs:
        return []

    theta_vals = np.array([p[0] for p in pairs], dtype=float)
    pred_prices = fit_predict_prices(th_hist, prices, theta_vals, th_max)

    out = []

    for (theta, src), price in zip(pairs, pred_prices):
        if not np.isfinite(price) or price <= 0:
            continue

        minutes_ahead = (theta - th_max) / th_step * interval_min
        if minutes_ahead < 0:
            minutes_ahead = 0

        try:
            t_hit = last_closed_time + timedelta(minutes=float(minutes_ahead))
        except Exception:
            t_hit = now_utc + timedelta(minutes=float(minutes_ahead))

        if t_hit < now_utc:
            t_hit = now_utc + timedelta(minutes=max(1, int(minutes_ahead)))

        out.append({
            "price": float(price),
            "theta": float(theta),
            "source": src,
            "time_hit": t_hit,
            "minutes_ahead": int(minutes_ahead),
        })

    return out


# ==============================================================================
# 5) خوشه‌بندی و انتخاب سطوح
# ==============================================================================
def merge_cluster_levels(items, live_price, tol_pct=0.0012):
    """
    تجمیع سطوح نزدیک به هم و انتخاب معتبرترین‌ها.
    """
    valid = [
        it for it in items
        if np.isfinite(it.get("price", np.nan)) and it.get("price", 0) > 0
    ]

    if not valid:
        step = max(abs(live_price) * 0.0015, 1e-9)
        valid = [
            {"price": live_price - step, "weight": 1.0, "source": "Fallback"},
            {"price": live_price + step, "weight": 1.0, "source": "Fallback"},
        ]

    valid.sort(key=lambda x: x["price"])
    clusters = []

    for it in valid:
        price = float(it["price"])
        weight = float(it.get("weight", 1.0))
        source = str(it.get("source", "?"))

        if not clusters:
            clusters.append({
                "price": price,
                "weight": weight,
                "sources": {source},
            })
            continue

        last = clusters[-1]
        if abs(price - last["price"]) / max(last["price"], 1e-12) > tol_pct:
            clusters.append({
                "price": price,
                "weight": weight,
                "sources": {source},
            })
        else:
            new_w = last["weight"] + weight
            last["price"] = (last["price"] * last["weight"] + price * weight) / new_w
            last["weight"] = new_w
            last["sources"].add(source)

    for c in clusters:
        c["side"] = "support" if c["price"] < live_price else "resistance"
        c["distance_pct"] = (c["price"] - live_price) / live_price * 100.0
        c["score"] = c["weight"] / (abs(c["distance_pct"]) + 0.08)

    supports = sorted(
        [c for c in clusters if c["side"] == "support"],
        key=lambda x: abs(x["distance_pct"])
    )
    resistances = sorted(
        [c for c in clusters if c["side"] == "resistance"],
        key=lambda x: abs(x["distance_pct"])
    )

    top = sorted(clusters, key=lambda x: x["score"], reverse=True)[:12]

    if supports and not any(c is supports[0] for c in top):
        top.append(supports[0])

    if resistances and not any(c is resistances[0] for c in top):
        top.append(resistances[0])

    if not any(c["side"] == "support" for c in top):
        top.append({
            "price": live_price * (1 - 0.0015),
            "weight": 1.0,
            "sources": {"Fallback"},
            "side": "support",
            "distance_pct": -0.15,
            "score": 0.0,
        })

    if not any(c["side"] == "resistance" for c in top):
        top.append({
            "price": live_price * (1 + 0.0015),
            "weight": 1.0,
            "sources": {"Fallback"},
            "side": "resistance",
            "distance_pct": 0.15,
            "score": 0.0,
        })

    return sorted(top, key=lambda x: x["price"], reverse=True)


# ==============================================================================
# 6) ساخت نمودار اصلی + پنل قیمت و سطوح
# ==============================================================================
def build_figure(df, pivot_idx, pivot_type, pivot_price, pivot_period,
                 turns, now_utc, interval_min):
    df_closed = df.iloc[:-1] if len(df) > 2 else df
    seg = df_closed.iloc[pivot_idx:]

    if len(seg) < 2:
        return empty_fig("دادهٔ پس از پیووت کافی نیست."), [], []

    prices = seg["close"].values
    times = seg["ts"].values
    npts = len(prices)

    pmin, pmax = float(prices.min()), float(prices.max())
    if pmax <= pmin:
        pmax = pmin + 1.0

    th_max = 2 * np.pi * turns
    th = np.linspace(0, th_max, npts)
    b = np.log(RATIO) / th_max
    r = np.exp(b * th)
    R = r[-1]

    live_price = float(df.iloc[-1]["close"])

    hf = now_utc.hour + now_utc.minute / 60 + now_utc.second / 3600
    th_cw = (90 - 30 * hf) % 360
    th_ccw = (30 + 30 * (hf - 2)) % 360

    # تقاطع‌های تاریخی عقربه‌ها با اسپیرال
    cw_ths = spiral_intersections(th_cw, th_max, b)
    ccw_ths = spiral_intersections(th_ccw, th_max, b)

    def ths_to_prices(ths):
        if len(ths) == 0:
            return np.empty(0), np.empty(0)
        idxs = ths / th_max * (npts - 1)
        idxs_i = np.clip(np.round(idxs).astype(int), 0, npts - 1)
        return ths, prices[idxs_i]

    cw_ths, cw_p = ths_to_prices(cw_ths)
    ccw_ths, ccw_p = ths_to_prices(ccw_ths)

    # شعاع واقعی تقاطع‌ها روی اسپیرال
    cw_rad = np.exp(b * cw_ths) if len(cw_ths) else np.empty(0)
    ccw_rad = np.exp(b * ccw_ths) if len(ccw_ths) else np.empty(0)

    cw_x = cw_rad * np.cos(cw_ths) if len(cw_ths) else np.empty(0)
    cw_y = cw_rad * np.sin(cw_ths) if len(cw_ths) else np.empty(0)

    ccw_x = ccw_rad * np.cos(ccw_ths) if len(ccw_ths) else np.empty(0)
    ccw_y = ccw_rad * np.sin(ccw_ths) if len(ccw_ths) else np.empty(0)

    # زمان آخرین کندل بسته
    try:
        last_closed_time = pd.Timestamp(df_closed.iloc[-1]["ts"]).to_pydatetime()
        last_closed_time = last_closed_time.replace(tzinfo=timezone.utc)
    except Exception:
        last_closed_time = now_utc

    # نقاط آینده
    future_points = make_future_points(
        prices=prices,
        th_hist=th,
        th_max=th_max,
        th_cw=th_cw,
        th_ccw=th_ccw,
        last_closed_time=last_closed_time,
        now_utc=now_utc,
        interval_min=interval_min,
        forecast_hours=FORECAST_HOURS,
    )

    # جمع‌آوری آیتم‌های تشکیل سطح
    structural_items = find_all_pivots(
        df_closed["high"].values,
        df_closed["low"].values,
        pivot_period,
        lookback=250
    )

    items = []

    for it in structural_items:
        items.append({
            "price": it["price"],
            "weight": 2.5,
            "source": it["source"],
        })

    for p in cw_p:
        items.append({
            "price": float(p),
            "weight": 1.8,
            "source": "فاز ساعتگرد",
        })

    for p in ccw_p:
        items.append({
            "price": float(p),
            "weight": 1.8,
            "source": "فاز پادساعتگرد",
        })

    for p in future_points:
        items.append({
            "price": p["price"],
            "weight": 1.2,
            "source": "اسپیرال آینده",
        })

    levels = merge_cluster_levels(items, live_price, tol_pct=0.0012)

    # ==========================================================================
    # ساخت Figure با دو بخش: اسپیرال + چارت قیمت
    # ==========================================================================
    fig = make_subplots(
        rows=2,
        cols=1,
        row_heights=[0.68, 0.32],
        vertical_spacing=0.09,
    )

    ang = np.linspace(0, 2 * np.pi, 360)

    # شبکه قطبی
    for frac in (0.25, 0.5, 0.75):
        fig.add_trace(go.Scatter(
            x=frac * R * np.cos(ang),
            y=frac * R * np.sin(ang),
            mode="lines",
            line=dict(color=LINE, width=1),
            showlegend=False,
            hoverinfo="skip",
        ), row=1, col=1)

    for dd in range(0, 360, 30):
        fig.add_trace(go.Scatter(
            x=[0, R * np.cos(dd * DEG)],
            y=[0, R * np.sin(dd * DEG)],
            mode="lines",
            line=dict(color=LINE, width=1, dash="dot"),
            showlegend=False,
            hoverinfo="skip",
        ), row=1, col=1)

    # دایره ساعت
    fig.add_trace(go.Scatter(
        x=R * np.cos(ang),
        y=R * np.sin(ang),
        mode="lines",
        line=dict(color=GOLD, width=3),
        name="دایره ساعت",
    ), row=1, col=1)

    # اسپیرال
    fig.add_trace(go.Scatter(
        x=r * np.cos(th),
        y=r * np.sin(th),
        mode="lines",
        line=dict(color=SPIRAL_CLR, width=2, dash="dot"),
        showlegend=False,
        hoverinfo="skip",
    ), row=1, col=1)

    # نقاط قیمت روی اسپیرال
    fig.add_trace(go.Scatter(
        x=r * np.cos(th),
        y=r * np.sin(th),
        mode="markers",
        marker=dict(
            size=5,
            color=prices,
            colorscale="Viridis",
            showscale=True,
            colorbar=dict(
                title="قیمت",
                thickness=12,
                len=0.55,
                y=0.78,
                tickfont=dict(color=TXT, size=10),
            ),
            line=dict(width=0.4, color="#000"),
        ),
        customdata=np.column_stack([
            np.degrees(th),
            prices,
            pd.to_datetime(times).strftime("%m-%d %H:%M"),
        ]),
        hovertemplate=(
            "θ=%{customdata[0]:.1f}°<br>"
            "قیمت=%{customdata[1]:.6g}<br>"
            "%{customdata[2]}<extra>کندل</extra>"
        ),
        name="قیمت از پیووت تا لایو",
    ), row=1, col=1)

    # کندل لایو
    live_x, live_y = R * np.cos(th_max), R * np.sin(th_max)
    fig.add_trace(go.Scatter(
        x=[live_x],
        y=[live_y],
        mode="markers+text",
        marker=dict(size=14, symbol="star", color=GOLD, line=dict(width=1.5, color="black")),
        text=[f"LIVE: {live_price:.4g}"],
        textposition="top right",
        textfont=dict(color=GOLD, size=11),
        name=f"کندل لایو = {live_price:.4g}",
    ), row=1, col=1)

    # پیووت
    piv_x, piv_y = r[0] * np.cos(th[0]), r[0] * np.sin(th[0])
    fig.add_trace(go.Scatter(
        x=[piv_x],
        y=[piv_y],
        mode="markers+text",
        marker=dict(size=12, symbol="square", color=UP, line=dict(width=1.5, color="black")),
        text=[f"PIVOT ({pivot_type}): {pivot_price:.4g}"],
        textposition="bottom left",
        textfont=dict(color=UP, size=11),
        name="آخرین پیووت",
    ), row=1, col=1)

    # درجه‌بندی ساعت
    for h in range(1, 13):
        phi = (90 - 30 * h) * DEG
        c, s = np.cos(phi), np.sin(phi)

        fig.add_trace(go.Scatter(
            x=[0.94 * R * c, R * c],
            y=[0.94 * R * s, R * s],
            mode="lines",
            line=dict(color=GOLD, width=2),
            showlegend=False,
            hoverinfo="skip",
        ), row=1, col=1)

        fig.add_annotation(
            x=1.08 * R * c,
            y=1.08 * R * s,
            text=f"<b>{h}</b>",
            showarrow=False,
            font=dict(size=14, color=GOLD),
            row=1,
            col=1,
        )

    # عقربه‌ها
    for phi, color, name in (
        (th_cw, DN, "عقربه ساعتگرد (UTC)"),
        (th_ccw, UP, "عقربه پادساعتگرد (هماهنگ در ۲:۰۰)"),
    ):
        c, s = np.cos(phi * DEG), np.sin(phi * DEG)

        fig.add_trace(go.Scatter(
            x=[0, 0.97 * R * c],
            y=[0, 0.97 * R * s],
            mode="lines",
            line=dict(color=color, width=4),
            name=name,
        ), row=1, col=1)

        fig.add_annotation(
            x=0.78 * R * c,
            y=0.78 * R * s,
            text=f"θ = {phi:.1f}°",
            showarrow=False,
            font=dict(size=12, color=color),
            bgcolor="rgba(11,18,32,0.8)",
            bordercolor=color,
            borderwidth=1,
            borderpad=3,
            row=1,
            col=1,
        )

    # تقاطع‌های تاریخی عقربه‌ها
    for xs, ys, ths, pp, color, tag in (
        (cw_x, cw_y, cw_ths, cw_p, DN, "ساعتگرد"),
        (ccw_x, ccw_y, ccw_ths, ccw_p, UP, "پادساعتگرد"),
    ):
        if len(xs) == 0:
            continue

        fig.add_trace(go.Scatter(
            x=xs,
            y=ys,
            mode="markers+text",
            marker=dict(size=13, symbol="star", color=color, line=dict(width=1.2, color="white")),
            text=[f"{p:.4g}" for p in pp],
            textposition="top center",
            textfont=dict(color=color, size=10),
            customdata=np.column_stack([np.degrees(ths), pp]),
            hovertemplate=(
                f"تقاطع {tag}<br>"
                "θ=%{customdata[0]:.2f}°<br>"
                "قیمت=%{customdata[1]:.6g}<extra></extra>"
            ),
            name=f"تقاطع عقربه {tag}",
        ), row=1, col=1)

    # نمایش نقاط آینده روی لبه ساعت
    future_markers = sorted(
        future_points,
        key=lambda x: abs(x["price"] - live_price)
    )[:10]

    for p in future_markers:
        ang_f = p["theta"] % (2 * np.pi)
        x_f = R * np.cos(ang_f)
        y_f = R * np.sin(ang_f)
        color = UP if p["price"] < live_price else DN

        fig.add_trace(go.Scatter(
            x=[x_f],
            y=[y_f],
            mode="markers+text",
            marker=dict(
                size=11,
                symbol="diamond",
                color=color,
                line=dict(width=1, color="white"),
            ),
            text=[f"{p['price']:.0f}"],
            textposition="top center",
            textfont=dict(color=color, size=9),
            hovertemplate=(
                "پیش‌بینی چرخه‌ای<br>"
                f"قیمت={p['price']:.6g}<br>"
                f"زمان={p['time_hit'].strftime('%m-%d %H:%M')} UTC"
                "<extra></extra>"
            ),
            name="پیش‌بینی چرخه‌ای",
            showlegend=False,
        ), row=1, col=1)

    # ==========================================================================
    # پنل پایین: چارت قیمت + خطوط حمایت/مقاومت واقعی
    # ==========================================================================
    df_plot = df.tail(180).reset_index(drop=True)
    x_end = max(1, len(df_plot) - 1)

    fig.add_trace(go.Scatter(
        x=list(range(len(df_plot))),
        y=df_plot["close"].values,
        mode="lines",
        line=dict(color=SPIRAL_CLR, width=2),
        name="قیمت",
    ), row=2, col=1)

    # خطوط S/R
    for lvl in levels:
        color = UP if lvl["side"] == "support" else DN
        tag = "S" if lvl["side"] == "support" else "R"

        fig.add_shape(
            type="line",
            xref="x2",
            yref="y2",
            x0=0,
            x1=x_end,
            y0=lvl["price"],
            y1=lvl["price"],
            line=dict(color=color, width=1.8, dash="dash"),
            opacity=0.9,
        )

        fig.add_annotation(
            xref="x2",
            yref="y2",
            x=x_end,
            y=lvl["price"],
            text=f"{tag} {lvl['price']:.2f}",
            showarrow=False,
            xanchor="right",
            yanchor="bottom",
            font=dict(color=color, size=10),
            bgcolor="rgba(11,18,32,0.85)",
            bordercolor=color,
            borderwidth=1,
            borderpad=2,
        )

    # محدوده محورها
    plot_prices = list(df_plot["close"].values) + [lvl["price"] for lvl in levels]
    y_min = float(np.min(plot_prices))
    y_max = float(np.max(plot_prices))
    y_pad = max((y_max - y_min) * 0.08, abs(live_price) * 0.0008)

    lim = 1.45 * R

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG,
        plot_bgcolor=CARD,
        legend=dict(
            bgcolor="rgba(11,18,32,0.8)",
            font=dict(size=10),
            orientation="h",
            y=-0.12,
            x=0.5,
            xanchor="center",
        ),
        margin=dict(l=10, r=10, t=70, b=10),
        title=dict(
            text=(
                f"🌀 اسپیرال UTC + پیش‌بینی S/R — "
                f"{now_utc.strftime('%H:%M:%S')} UTC | افق: {FORECAST_HOURS}h"
            ),
            x=0.5,
            font=dict(color=GOLD, size=15),
        ),
    )

    fig.update_xaxes(range=[-lim, lim], visible=False, row=1, col=1)
    fig.update_yaxes(
        range=[-lim, lim],
        visible=False,
        scaleanchor="x",
        scaleratio=1,
        row=1,
        col=1,
    )

    fig.update_xaxes(range=[0, x_end], visible=False, row=2, col=1)
    fig.update_yaxes(
        range=[y_min - y_pad, y_max + y_pad],
        gridcolor=LINE,
        tickfont=dict(size=10, color=MUT),
        title_text="قیمت",
        row=2,
        col=1,
    )

    return fig, levels, future_points


def empty_fig(msg):
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG,
        plot_bgcolor=CARD,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    fig.add_annotation(
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        text=msg,
        showarrow=False,
        font=dict(size=18, color=DN),
    )
    return fig


# ==============================================================================
# 7) اپ Dash
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])
app.title = "Bybit Spiral Clock + S/R Predictor"
server = app.server

CATEGORY_OPTS = [{"label": v, "value": v} for v in ["linear", "spot", "inverse"]]
INTERVAL_OPTS = [{"label": lbl, "value": val} for lbl, val in [
    ("1m", "1"), ("3m", "3"), ("5m", "5"), ("15m", "15"),
    ("30m", "30"), ("1h", "60"), ("4h", "240"), ("1D", "D"),
]]

app.layout = html.Div([
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([
            html.Label("نماد", style={"fontSize": 11, "color": MUT}),
            dcc.Input(id="symbol", value=DEFAULT_SYMBOL, type="text",
                      style={"width": "100%", "padding": 6, "borderRadius": 6})
        ], md=2),

        dbc.Col([
            html.Label("بازار", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="category", value=DEFAULT_CATEGORY,
                         clearable=False, options=CATEGORY_OPTS)
        ], md=2),

        dbc.Col([
            html.Label("تایم‌فریم", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="interval", value=DEFAULT_INTERVAL,
                         clearable=False, options=INTERVAL_OPTS)
        ], md=2),

        dbc.Col([
            html.Label("دوره پیووت", style={"fontSize": 11, "color": MUT}),
            dcc.Input(id="pivot-period", type="number", value=DEFAULT_PIVOT,
                      min=2, max=50, step=1,
                      style={"width": "100%", "padding": 6, "borderRadius": 6})
        ], md=1),

        dbc.Col([
            html.Label("دور اسپیرال", style={"fontSize": 11, "color": MUT}),
            dcc.Input(id="turns", type="number", value=DEFAULT_TURNS,
                      min=1, max=12, step=1,
                      style={"width": "100%", "padding": 6, "borderRadius": 6})
        ], md=1),

        dbc.Col(
            dbc.Button("🔄 بروزرسانی", id="refresh-btn", color="warning",
                       className="mt-3",
                       style={"fontWeight": "bold", "color": BG, "width": "100%"}),
            md=1
        ),

        dbc.Col(html.Div(id="conn-status",
                         style={"color": MUT, "fontSize": 11,
                                "marginTop": 22, "textAlign": "center"}), md=1),
    ])), style={"maxWidth": 1500, "margin": "10px auto"}),

    dbc.Row([
        dbc.Col(dcc.Graph(id="spiral-plot", style={"height": "82vh"},
                          config={"displaylogo": False}), width=9),

        dbc.Col([
            html.H5("📊 حمایت / مقاومت پیش‌بینی‌شده",
                    style={"color": GOLD, "fontSize": 14, "margin": "8px 0"}),
            html.Div(id="info-panel",
                     style={"background": CARD, "border": f"1px solid {LINE}",
                            "borderRadius": 8, "padding": 12,
                            "fontFamily": "Consolas, monospace",
                            "fontSize": 12, "color": TXT,
                            "whiteSpace": "pre-wrap", "direction": "rtl",
                            "maxHeight": "74vh", "overflowY": "auto"}),
        ], width=3),
    ], style={"maxWidth": 1500, "margin": "0 auto"}),

    dcc.Interval(id="tick", interval=10_000, n_intervals=0),
], style={"background": BG, "minHeight": "100vh", "padding": "10px"})


# ==============================================================================
# 8) کال‌بک اصلی
# ==============================================================================
@app.callback(
    Output("spiral-plot", "figure"),
    Output("info-panel", "children"),
    Output("conn-status", "children"),
    Input("tick", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    State("symbol", "value"),
    State("interval", "value"),
    State("category", "value"),
    State("pivot-period", "value"),
    State("turns", "value"),
)
def update(_n, _click, symbol, interval, category, pivot_period, turns):
    try:
        pivot_period = int(pivot_period or DEFAULT_PIVOT)
        turns = int(turns or DEFAULT_TURNS)
    except Exception:
        pivot_period, turns = DEFAULT_PIVOT, DEFAULT_TURNS

    symbol = (symbol or DEFAULT_SYMBOL).upper().strip()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL

    now_utc = get_server_time()
    df = get_klines(symbol, interval, category, limit=500)

    if df.empty:
        status = "🔴 قطع از بایبیت"
        return empty_fig("دریافت دیتا از بایبیت ناموفق بود."), "خطا در دریافت کندل.", status

    pivot_idx, pivot_type, pivot_price = find_last_pivot(
        df["high"].values,
        df["low"].values,
        pivot_period
    )

    interval_min = get_interval_minutes(interval)

    fig, levels, future_points = build_figure(
        df=df,
        pivot_idx=pivot_idx,
        pivot_type=pivot_type,
        pivot_price=pivot_price,
        pivot_period=pivot_period,
        turns=turns,
        now_utc=now_utc,
        interval_min=interval_min,
    )

    live_price = float(df.iloc[-1]["close"])
    pivot_time = df.iloc[pivot_idx]["ts"].strftime("%Y-%m-%d %H:%M")
    pivot_label = {"low": "کف", "high": "سقف", "none": "نامشخص"}.get(pivot_type, "—")

    hf = now_utc.hour + now_utc.minute / 60 + now_utc.second / 3600
    th_cw = (90 - 30 * hf) % 360
    th_ccw = (30 + 30 * (hf - 2)) % 360

    lines = [
        f"⏰ زمان سرور بایبیت: {now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"💹 نماد           : {symbol} | {category} | {interval}",
        f"📈 قیمت لایو     : {live_price:.6g}",
        "",
        "🔍 آخرین پیووت:",
        f"   نوع            : {pivot_label} ({pivot_type})",
        f"   قیمت           : {pivot_price:.6g}",
        f"   زمان           : {pivot_time} UTC",
        f"   کندل‌های بعد از آن: {len(df) - 1 - pivot_idx}",
        "",
        f"🔴 عقربه ساعتگرد   : θ = {th_cw:7.2f}°  ≈ {theta_to_clockstr(th_cw)}",
        f"🟢 عقربه پادساعتگرد: θ = {th_ccw:7.2f}°  ≈ {theta_to_clockstr(th_ccw)}",
        "",
        "=" * 36,
    ]

    supports = sorted(
        [c for c in levels if c["side"] == "support"],
        key=lambda x: abs(x["distance_pct"])
    )
    resistances = sorted(
        [c for c in levels if c["side"] == "resistance"],
        key=lambda x: abs(x["distance_pct"])
    )

    lines.append("🟢 حمایت‌های پیش‌بینی‌شده:")
    if not supports:
        lines.append("   —")
    else:
        for i, c in enumerate(supports[:6]):
            src = ", ".join(sorted(c["sources"]))
            lines.append(
                f"   S{i+1}: {c['price']:.2f} | "
                f"{c['distance_pct']:+.2f}% | {src}"
            )

    lines.append("")
    lines.append("🔴 مقاومت‌های پیش‌بینی‌شده:")
    if not resistances:
        lines.append("   —")
    else:
        for i, c in enumerate(resistances[:6]):
            src = ", ".join(sorted(c["sources"]))
            lines.append(
                f"   R{i+1}: {c['price']:.2f} | "
                f"{c['distance_pct']:+.2f}% | {src}"
            )

    lines.append("")
    lines.append("⏳ نقاط چرخه‌ای آینده:")
    fp = sorted(future_points, key=lambda x: x["minutes_ahead"])[:8]
    if not fp:
        lines.append("   —")
    else:
        for p in fp:
            lines.append(
                f"   {p['source']} | {p['price']:.2f} | "
                f"{p['time_hit'].strftime('%m-%d %H:%M')} UTC"
            )

    status = f"🟢 متصل به سرور | {now_utc.strftime('%H:%M:%S')} UTC"
    return fig, "\n".join(lines), status


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8070, use_reloader=False)