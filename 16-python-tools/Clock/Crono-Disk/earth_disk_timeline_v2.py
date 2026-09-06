# -*- coding: utf-8 -*-
"""
💿 Multi-Disk Timeline Predictor (Earth + Planetary Cycles) + Precision S/R Engine
سازگار با: Dash 2.x | Python 3.13 | Bybit REST API v5

تغییرات کلیدی نسبت به نسخه‌ی قبل:
  - چرخه‌ها (چه تجربی FFT، چه سیاره‌ای) فقط وقتی وارد پیش‌بینی می‌شوند که از
    تست معناداری آماری (Permutation Test) با تصحیح مقایسه‌های چندگانه عبور کنند.
  - «سی‌دی‌های» سیارات دیگر (ماه، عطارد، زهره، مریخ، مشتری، زحل) به‌عنوان
    فرکانس‌های ثابتِ فرضیه‌محور اضافه شده‌اند، نه فرضِ بی‌قیدوشرط.
  - دریافت تاریخچه‌ی عمیق (pagination) چون چرخه‌های بلندمدت با ۱۰۰۰ کندل قابل آزمون نیستند.
  - اعتبارسنجی Out-of-Sample (Walk-Forward) برای گزارش صادقانه‌ی دقت واقعی مدل.
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
# 0) پالت رنگی و تنظیمات پیش‌فرض
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
PURPLE = "#b57bf0"
ORANGE = "#ff9f43"
CYAN = "#38d9d9"
PINK = "#ff6bd6"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_INTERVAL = "15"
FONT_FAMILY = "Vazirmatn, Tahoma, Arial, sans-serif"

RING_PALETTE = [BLUE, PURPLE, ORANGE, CYAN, PINK, GOLD, UP]

# دوره‌های سینودیک سیارات (روز) — منبع فرضیه، نه واقعیتِ اثبات‌شده
PLANET_CYCLES = {
    "ماه (سینودیک ۲۹.۵ روز)": 29.53059,
    "عطارد (سینودیک)": 115.88,
    "زهره (سینودیک)": 583.92,
    "مریخ (سینودیک)": 779.94,
    "مشتری (سینودیک)": 398.88,
    "زحل (سینودیک)": 378.09,
}
MIN_CYCLES_REQUIRED = 3   # حداقل تعداد دور کامل لازم در داده برای آزمون یک چرخه
ALPHA = 0.05              # سطح معناداری پایه (قبل از تصحیح Bonferroni)
N_PERM = 150              # تعداد جایگشت در تست معناداری

# ==============================================================================
# 1) REST بایبیت (تک‌درخواستی + صفحه‌بندی برای تاریخچه‌ی عمیق)
# ==============================================================================
REST_CANDIDATES = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
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
            if r.status_code in (403, 451): continue
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
        if nano: return datetime.fromtimestamp(int(nano) / 1e9, tz=timezone.utc)
        sec = res.get("timeSecond")
        if sec:
            v = int(sec); s = str(v)
            sec_f = v / 1e9 if len(s) >= 19 else v / 1e6 if len(s) >= 16 else v / 1e3 if len(s) >= 13 else float(v)
            return datetime.fromtimestamp(sec_f, tz=timezone.utc)
    except Exception:
        pass
    return datetime.now(timezone.utc)


def get_interval_minutes(interval):
    s = str(interval).strip().lower()
    if s == "d": return 1440
    try:
        return int(s)
    except Exception:
        return 15


def get_klines_extended(symbol, interval, category="linear", total_bars=3000, batch=1000, max_batches=20):
    """دریافت تاریخچه‌ی عمیق با صفحه‌بندی رو به عقب (لازم برای آزمون چرخه‌های بلندمدت)."""
    frames = []
    end_ts = None
    remaining = total_bars
    for _ in range(max_batches):
        if remaining <= 0: break
        params = {"category": category, "symbol": symbol, "interval": interval, "limit": min(batch, remaining)}
        if end_ts is not None:
            params["end"] = end_ts
        d = bybit_get("/v5/market/kline", params)
        lst = ((d or {}).get("result") or {}).get("list") or []
        if not lst: break
        chunk = pd.DataFrame(lst, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
        chunk["ts"] = chunk["ts"].astype(np.int64)
        frames.append(chunk)
        end_ts = int(chunk["ts"].min()) - 1
        remaining -= len(chunk)
        if len(chunk) < batch: break
    if not frames: return pd.DataFrame()
    full = pd.concat(frames, ignore_index=True).drop_duplicates(subset="ts")
    full["ts"] = pd.to_datetime(full["ts"], unit="ms")
    for c in ["open", "high", "low", "close", "volume"]:
        full[c] = full[c].astype(float)
    return full.sort_values("ts").reset_index(drop=True)


# ==============================================================================
# 2) موتور چرخه‌های معتبرشده (Earth + Planetary Disks)
# ==============================================================================
def bars_for_days(days, interval_min):
    return (days * 1440.0) / interval_min


def fit_sinusoid(t, y, period_bars):
    if period_bars <= 1: return None
    w = 2 * np.pi / period_bars
    X = np.column_stack([np.cos(w * t), np.sin(w * t), np.ones_like(t, dtype=float)])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    a, b, _c = coef
    y_hat = X @ coef
    ss_res = np.sum((y - y_hat) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {"amp": math.hypot(a, b), "phase": math.atan2(b, a), "r2": float(r2), "w": w}


def permutation_pvalue(t, y, period_bars, n_perm=N_PERM, rng=None):
    rng = rng or np.random.default_rng(42)
    obs = fit_sinusoid(t, y, period_bars)
    if obs is None: return 1.0, None
    obs_r2 = obs["r2"]
    y_perm = y.copy()
    count = 0
    for _ in range(n_perm):
        rng.shuffle(y_perm)
        f = fit_sinusoid(t, y_perm, period_bars)
        if f and f["r2"] >= obs_r2:
            count += 1
    return (count + 1) / (n_perm + 1), obs


def detect_significant_cycles(df, interval_min, top_fft_k=5, alpha=ALPHA, n_perm=N_PERM):
    """
    بازمی‌گرداند: (لیست چرخه‌های معنادار, ضرایب روند خطی, بردار زمان, تعداد کندل, متادیتای تست)
    فقط چرخه‌هایی که از تست جایگشتی با آستانه‌ی تصحیح‌شده (Bonferroni) عبور کنند وارد می‌شوند.
    """
    closes = df["close"].values
    n = len(closes)
    t = np.arange(n, dtype=float)
    trend_coef = np.polyfit(t, closes, 1)
    y_detrend = closes - np.polyval(trend_coef, t)

    candidates = []  # (label, period_bars, source)

    # --- چرخه‌های تجربی (داده‌محور) از FFT ---
    win = np.hanning(n)
    fft = np.fft.fft(y_detrend * win)
    freqs = np.fft.fftfreq(n, d=1)
    mags = np.abs(fft)
    mags[0] = 0
    pos = np.where(freqs > 0)[0]
    if len(pos):
        top_idx = pos[np.argsort(mags[pos])[::-1][:top_fft_k]]
        for idx in top_idx:
            period_bars = 1.0 / freqs[idx]
            if 4 <= period_bars <= n:
                candidates.append((f"چرخه تجربی ~{period_bars:.1f} کندلی", period_bars, "fft"))

    # --- چرخه‌های سیاره‌ای (فرضیه‌محور، فقط اگر داده کافی باشد) ---
    tested_planets, skipped_planets = [], []
    for name, days in PLANET_CYCLES.items():
        period_bars = bars_for_days(days, interval_min)
        if n >= period_bars * MIN_CYCLES_REQUIRED and period_bars <= n / 2:
            candidates.append((name, period_bars, "planet"))
            tested_planets.append(name)
        else:
            skipped_planets.append(name)

    # --- تصحیح مقایسه‌های چندگانه: چون همزمان چند فرضیه تست می‌شود ---
    n_tested = max(len(candidates), 1)
    alpha_eff = alpha / n_tested

    significant = []
    for label, period_bars, source in candidates:
        p_val, fit = permutation_pvalue(t, y_detrend, period_bars, n_perm=n_perm)
        if fit and p_val <= alpha_eff:
            significant.append({
                "label": label, "period_bars": period_bars, "source": source,
                "amp": fit["amp"], "phase": fit["phase"], "w": fit["w"], "p_value": p_val,
            })

    meta = {
        "n_candidates": n_tested, "alpha_eff": alpha_eff,
        "tested_planets": tested_planets, "skipped_planets": skipped_planets,
    }
    return significant, trend_coef, t, n, meta


def forecast_from_cycles(cycles, trend_coef, n, steps):
    t_ext = np.arange(n, n + steps, dtype=float)
    path = np.polyval(trend_coef, t_ext)
    for c in cycles:
        path += c["amp"] * np.cos(c["w"] * t_ext - c["phase"])
    return path


def find_turning_points(expected_path, last_ts, interval_min):
    diffs = np.diff(expected_path)
    signs = np.sign(diffs)
    signs[signs == 0] = 1
    crossings = np.where(signs[:-1] != signs[1:])[0] + 1
    turning_points = []
    for idx in crossings:
        idx_int = int(idx)
        t_future = last_ts + timedelta(minutes=interval_min * idx_int)
        price = float(expected_path[idx_int])
        is_peak = False
        if 0 < idx_int < len(expected_path) - 1:
            is_peak = expected_path[idx_int] > expected_path[idx_int - 1] and expected_path[idx_int] > expected_path[idx_int + 1]
        elif idx_int > 0:
            is_peak = expected_path[idx_int] > expected_path[idx_int - 1]
        turning_points.append({"time": t_future, "price": price, "type": "قله (Peak)" if is_peak else "کف (Trough)"})
    return turning_points


def backtest_walkforward(df, interval_min, holdout=50, top_fft_k=5, alpha=ALPHA, n_perm=100):
    """اعتبارسنجی صادقانه: مدل را روی داده‌ی قدیمی fit می‌کند و روی داده‌ی جدید (ندیده) تست می‌کند."""
    n_total = len(df)
    if n_total < holdout + 60:
        return None
    train = df.iloc[:-holdout].reset_index(drop=True)
    test = df.iloc[-holdout:].reset_index(drop=True)

    cycles, trend_coef, t, n, meta = detect_significant_cycles(train, interval_min, top_fft_k, alpha, n_perm)
    forecast = forecast_from_cycles(cycles, trend_coef, n, holdout)
    actual = test["close"].values

    mae_pct = float(np.mean(np.abs(forecast - actual) / actual) * 100)
    pred_dir = np.sign(np.diff(forecast))
    actual_dir = np.sign(np.diff(actual))
    hit_rate = float(np.mean(pred_dir == actual_dir) * 100) if len(pred_dir) > 0 else 0.0

    return {"mae_pct": round(mae_pct, 2), "hit_rate": round(hit_rate, 1),
            "n_cycles_used": len(cycles), "holdout": holdout}


def calculate_cycle_strength(cycles):
    """معیار ساده: چند درصد کندل‌ها زیر تأثیر چرخه‌های معنادار قرار دارند (تقریبی، نه دقیق افزایشی)."""
    if not cycles: return 0.0, 1.0
    best_p = min(c["p_value"] for c in cycles)
    return float(len(cycles)), float(best_p)


# ==============================================================================
# 2.5) موتور دقیق حمایت / مقاومت (بدون تغییر نسبت به نسخه‌ی قبل)
# ==============================================================================
def compute_atr(df, period=14):
    high, low, close = df["high"].values, df["low"].values, df["close"].values
    n = len(df)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    return pd.Series(tr).rolling(period, min_periods=1).mean().values


def detect_fractal_pivots(df, left=3, right=3):
    highs, lows = df["high"].values, df["low"].values
    n = len(df)
    pivot_highs, pivot_lows = [], []
    for i in range(left, n - right):
        wh = highs[i - left:i + right + 1]
        if highs[i] == wh.max() and np.argmax(wh) == left:
            pivot_highs.append((i, highs[i]))
        wl = lows[i - left:i + right + 1]
        if lows[i] == wl.min() and np.argmin(wl) == left:
            pivot_lows.append((i, lows[i]))
    return pivot_highs, pivot_lows


def build_volume_profile(df, bins=50):
    prices, volumes = df["close"].values, df["volume"].values
    lo, hi = prices.min(), prices.max()
    if hi <= lo: return np.array([]), np.array([])
    edges = np.linspace(lo, hi, bins + 1)
    hist = np.zeros(bins)
    idx = np.clip(np.digitize(prices, edges) - 1, 0, bins - 1)
    for i, v in zip(idx, volumes):
        hist[i] += v
    return (edges[:-1] + edges[1:]) / 2, hist


def find_volume_nodes(centers, hist, top_k=8):
    if len(hist) == 0: return []
    order = np.argsort(hist)[::-1][:top_k]
    total = hist.sum()
    return [{"price": float(centers[i]), "volume_share": float(hist[i] / total * 100) if total > 0 else 0.0} for i in order]


def classic_pivot_levels(df, lookback=96):
    seg = df.tail(lookback)
    if seg.empty: return []
    H, L, C = seg["high"].max(), seg["low"].min(), seg["close"].iloc[-1]
    P = (H + L + C) / 3
    R1, S1 = 2 * P - L, 2 * P - H
    R2, S2 = P + (H - L), P - (H - L)
    R3, S3 = H + 2 * (P - L), L - 2 * (H - P)
    return [{"price": p, "weight": 0.8, "kind": "classic_pivot"} for p in [P, R1, R2, R3, S1, S2, S3]]


def cluster_levels(levels, tolerance):
    if not levels: return []
    levels_sorted = sorted(levels, key=lambda x: x["price"])
    clusters, current = [], [levels_sorted[0]]
    for lv in levels_sorted[1:]:
        if lv["price"] - current[-1]["price"] <= tolerance:
            current.append(lv)
        else:
            clusters.append(current); current = [lv]
    clusters.append(current)
    result = []
    for c in clusters:
        total_w = sum(x["weight"] for x in c)
        wavg = (sum(x["price"] * x["weight"] for x in c) / total_w) if total_w > 0 else np.mean([x["price"] for x in c])
        result.append({"price": float(wavg), "weight": float(total_w)})
    return result


def validate_level_reliability(df, level_price, tolerance):
    highs, lows, closes = df["high"].values, df["low"].values, df["close"].values
    n = len(df)
    touches = bounces = 0
    i = 0
    while i < n:
        if lows[i] - tolerance <= level_price <= highs[i] + tolerance:
            touches += 1
            future = closes[i + 1:i + 4]
            if len(future) > 0:
                if level_price >= closes[i]:
                    if future.min() < closes[i] - tolerance * 0.3: bounces += 1
                else:
                    if future.max() > closes[i] + tolerance * 0.3: bounces += 1
            i += 3
        else:
            i += 1
    reliability = (bounces / touches * 100) if touches > 0 else 0.0
    return touches, round(reliability, 1)


def find_support_resistance(df, num_levels=5):
    n = len(df)
    if n < 30: return [], []
    atr = compute_atr(df, 14)
    current_atr = atr[-1] if len(atr) and atr[-1] > 0 else (df["high"].max() - df["low"].min()) / 20
    current_price = float(df["close"].iloc[-1])
    tolerance = max(current_atr * 0.35, current_price * 0.0015)

    pivot_highs, pivot_lows = detect_fractal_pivots(df, 3, 3)
    avg_vol = df["volume"].mean() if df["volume"].mean() > 0 else 1.0
    now_idx = n - 1

    levels = []
    for i, price in pivot_highs + [(i, p) for i, p in pivot_lows]:
        pass  # placeholder removed below
    levels = []
    for i, price in pivot_highs:
        recency = math.exp(-(now_idx - i) / max(n * 0.5, 1))
        weight = (0.5 + recency) * (0.5 + min(df["volume"].iloc[i] / avg_vol, 3.0))
        levels.append({"price": float(price), "weight": weight, "kind": "pivot_high"})
    for i, price in pivot_lows:
        recency = math.exp(-(now_idx - i) / max(n * 0.5, 1))
        weight = (0.5 + recency) * (0.5 + min(df["volume"].iloc[i] / avg_vol, 3.0))
        levels.append({"price": float(price), "weight": weight, "kind": "pivot_low"})
    levels.extend(classic_pivot_levels(df))

    clustered = cluster_levels(levels, tolerance)

    centers, hist = build_volume_profile(df, bins=50)
    vol_nodes = find_volume_nodes(centers, hist, top_k=8)
    for cl in clustered:
        cl["confluence"] = False
        for node in vol_nodes:
            if abs(cl["price"] - node["price"]) <= tolerance * 1.5:
                cl["weight"] *= (1.0 + node["volume_share"] / 100.0 * 2.0)
                cl["confluence"] = True

    if not clustered: return [], []
    max_w = max(c["weight"] for c in clustered)

    for cl in clustered:
        weight_score = (cl["weight"] / max_w * 100) if max_w > 0 else 0.0
        touches, reliability = validate_level_reliability(df, cl["price"], tolerance)
        cl["touches"], cl["reliability"] = touches, reliability
        cl["score"] = round(0.55 * weight_score + 0.45 * reliability, 1) if touches > 0 else round(weight_score * 0.85, 1)
        cl["type"] = "support" if cl["price"] < current_price else "resistance"
        cl["distance_pct"] = round((cl["price"] - current_price) / current_price * 100, 2)

    supports = sorted([c for c in clustered if c["type"] == "support"], key=lambda x: -x["score"])[:num_levels]
    resistances = sorted([c for c in clustered if c["type"] == "resistance"], key=lambda x: -x["score"])[:num_levels]
    supports = sorted(supports, key=lambda x: -x["price"])
    resistances = sorted(resistances, key=lambda x: x["price"])
    return supports, resistances


# ==============================================================================
# 3) ترسیم دیسک‌ها: زمین + سیارات + S/R
# ==============================================================================
def build_cd_figure(df, expected_path, turning_points, supports, resistances, cycles, now_utc, symbol, interval):
    interval_min = get_interval_minutes(interval)
    steps = len(expected_path)
    last_ts = pd.Timestamp(df.iloc[-1]["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)
    n = len(df)

    def get_theta(dt):
        minutes = dt.hour * 60 + dt.minute
        return (minutes / 1440) * 360

    R0 = 1.0
    all_prices = list(expected_path) + [s["price"] for s in supports] + [r["price"] for r in resistances]
    min_p, max_p = float(np.min(all_prices)), float(np.max(all_prices))
    p_range = max_p - min_p if max_p > min_p else 1.0

    def price_to_r(price):
        return R0 + 0.2 * (price - (min_p + max_p) / 2) / (p_range / 2)

    r_groove = price_to_r(expected_path)
    thetas = [get_theta(last_ts + timedelta(minutes=interval_min * (s + 1))) for s in range(steps)]

    fig = go.Figure()

    for r in np.linspace(0.4, 1.6, 15):
        fig.add_trace(go.Scatterpolar(r=[r] * 361, theta=np.linspace(0, 360, 361), mode="lines",
                                       line=dict(color="#1a233a", width=1), opacity=0.4,
                                       hoverinfo="skip", showlegend=False))

    for s in supports:
        r_val = price_to_r(s["price"])
        fig.add_trace(go.Scatterpolar(r=[r_val] * 361, theta=np.linspace(0, 360, 361), mode="lines",
                                       line=dict(color=UP, width=1 + s["score"] / 100 * 3.5, dash="dot"),
                                       opacity=0.30 + s["score"] / 100 * 0.55,
                                       name=f"حمایت {s['price']:,.1f} ({s['score']:.0f}%)", hoverinfo="name"))
    for r_lvl in resistances:
        r_val = price_to_r(r_lvl["price"])
        fig.add_trace(go.Scatterpolar(r=[r_val] * 361, theta=np.linspace(0, 360, 361), mode="lines",
                                       line=dict(color=DN, width=1 + r_lvl["score"] / 100 * 3.5, dash="dot"),
                                       opacity=0.30 + r_lvl["score"] / 100 * 0.55,
                                       name=f"مقاومت {r_lvl['price']:,.1f} ({r_lvl['score']:.0f}%)", hoverinfo="name"))

    fig.add_trace(go.Scatterpolar(
        r=r_groove, theta=thetas, mode="lines", line=dict(color=GOLD, width=2.5),
        name="شیار خط زمانی امروز",
        hovertemplate="زمان: %{text}<br>قیمت: %{r:.2f}<extra></extra>",
        text=[(last_ts + timedelta(minutes=interval_min * (s + 1))).strftime("%H:%M") for s in range(steps)]
    ))

    if turning_points:
        tp_thetas = [get_theta(tp["time"]) for tp in turning_points]
        tp_r = [price_to_r(tp["price"]) for tp in turning_points]
        tp_colors = [UP if tp["type"] == "قله (Peak)" else DN for tp in turning_points]
        tp_symbols = ["diamond" if tp["type"] == "قله (Peak)" else "square" for tp in turning_points]
        fig.add_trace(go.Scatterpolar(
            r=tp_r, theta=tp_thetas, mode="markers+text",
            marker=dict(size=14, color=tp_colors, symbol=tp_symbols, line=dict(width=1.5, color="white")),
            text=[tp["type"] for tp in turning_points], textposition="top center",
            textfont=dict(size=10, color=TXT, family=FONT_FAMILY), name="نقاط چرخش قطعی",
            hovertemplate="%{text}<br>زمان: %{customdata}<br>قیمت: %{r:.2f}<extra></extra>",
            customdata=[tp["time"].strftime("%H:%M") for tp in turning_points]
        ))

    now_theta = get_theta(now_utc)
    fig.add_trace(go.Scatterpolar(r=[0, 1.6], theta=[now_theta, now_theta], mode="lines",
                                   line=dict(color=DN, width=3, dash="dash"), name="سوزن لیزر (اکنون)", opacity=0.8))
    fig.add_trace(go.Scatterpolar(r=[0.05], theta=[0], mode="markers", marker=dict(size=30, color=GOLD),
                                   opacity=0.3, showlegend=False))
    fig.add_trace(go.Scatterpolar(r=[0.02], theta=[0], mode="markers", marker=dict(size=15, color="white"),
                                   showlegend=False))

    # --- دیسک‌های سیارات دیگر: هر چرخه‌ی معنادار یک حلقه‌ی بیرونی مستقل با فاز فعلی خودش ---
    max_r = 1.6
    for i, c in enumerate(cycles):
        ring_r = 1.7 + i * 0.13
        max_r = max(max_r, ring_r)
        color = RING_PALETTE[i % len(RING_PALETTE)]
        phase_now_deg = ((c["w"] * (n - 1) - c["phase"]) % (2 * np.pi)) * 180 / np.pi
        fig.add_trace(go.Scatterpolar(
            r=[ring_r] * 361, theta=np.linspace(0, 360, 361), mode="lines",
            line=dict(color=color, width=1.2, dash="dashdot"), opacity=0.55, hoverinfo="skip", showlegend=False
        ))
        fig.add_trace(go.Scatterpolar(
            r=[ring_r], theta=[phase_now_deg], mode="markers+text",
            marker=dict(size=12, color=color, symbol="circle", line=dict(width=1, color="white")),
            text=[""], textposition="top center",
            name=f"{c['label']} | p={c['p_value']:.3f}",
            hovertemplate=f"{c['label']}<br>p-value: {c['p_value']:.4f}<br>دامنه: {c['amp']:.2f}<extra></extra>"
        ))

    fig.update_layout(
        polar=dict(bgcolor=BG, radialaxis=dict(visible=False, range=[0, max_r + 0.25]),
                   angularaxis=dict(visible=True, direction="clockwise", rotation=90, tickmode="array",
                                     tickvals=[0, 90, 180, 270], ticktext=["00:00", "06:00", "12:00", "18:00"],
                                     tickfont=dict(color=MUT, size=13, family=FONT_FAMILY))),
        paper_bgcolor=BG, plot_bgcolor=BG, font=dict(family=FONT_FAMILY, color=TXT), showlegend=True,
        legend=dict(bgcolor="rgba(15,24,48,0.8)", bordercolor=LINE, borderwidth=1, font=dict(size=10)),
        margin=dict(l=40, r=40, t=60, b=40),
        title=dict(text=f"💿 Multi-Disk Timeline: {symbol} | {interval}m", x=0.5,
                   font=dict(color=GOLD, size=18, family=FONT_FAMILY))
    )
    return fig


def empty_fig(msg):
    fig = go.Figure()
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG)
    fig.add_annotation(x=0.5, y=0.5, xref="paper", yref="paper", text=msg, showarrow=False,
                       font=dict(size=16, color=DN, family=FONT_FAMILY))
    return fig


# ==============================================================================
# 4) رابط کاربری Dash
# ==============================================================================
FONT_URL = "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;800&display=swap"
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG, FONT_URL], suppress_callback_exceptions=True)
app.title = "Multi-Disk Timeline"
server = app.server

app.index_string = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}<title>{%title%}</title>{%favicon%}{%css%}
        <style>
            body { background: #070b14; direction: rtl; }
            * { font-family: 'Vazirmatn', Tahoma, Arial, sans-serif !important; }
            .glass-card { background: linear-gradient(145deg, rgba(16,28,56,0.85), rgba(10,17,35,0.85));
                border: 1px solid #22304e; border-radius: 16px; box-shadow: 0 8px 32px rgba(0,0,0,0.35); backdrop-filter: blur(6px); }
            .stat-value { font-weight: 800; font-size: 18px; }
            .stat-label { font-size: 11px; color: #8ea0c4; }
            .Select-control, .dash-dropdown .Select-control { background-color: #101c38 !important; border-color: #22304e !important; color: #eef2fb !important; }
            .Select-value-label { color: #eef2fb !important; }
            table { border-collapse: separate; border-spacing: 0 8px; width: 100%; }
            th { padding: 10px; font-weight: 600; color: #8ea0c4; font-size: 12px; text-align: center; }
            td { padding: 10px; text-align: center; background: rgba(34, 48, 78, 0.3); border-top: 1px solid #22304e; border-bottom: 1px solid #22304e; }
            td:first-child { border-right: 1px solid #22304e; border-top-right-radius: 8px; border-bottom-right-radius: 8px; }
            td:last-child { border-left: 1px solid #22304e; border-top-left-radius: 8px; border-bottom-left-radius: 8px; }
        </style>
    </head>
    <body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body>
</html>"""

INTERVAL_OPTS = [{"label": lbl, "value": val} for lbl, val in [
    ("1m", "1"), ("5m", "5"), ("15m", "15"), ("30m", "30"), ("1h", "60"), ("4h", "240"), ("1D", "D"),
]]


def stat_card(id_prefix, label, color=TXT):
    return dbc.Col(html.Div([
        html.Div(label, className="stat-label"),
        html.Div("—", id=f"{id_prefix}-value", className="stat-value", style={"color": color}),
    ], className="glass-card", style={"padding": "10px 14px", "textAlign": "center"}), md=True, xs=6,
        style={"marginBottom": 10})


def create_turning_points_table(turning_points):
    if not turning_points:
        return html.Div("نقطه چرخشی یافت نشد.", style={"color": MUT, "textAlign": "center", "padding": "20px"})
    rows = []
    for tp in turning_points[:8]:
        color = UP if tp["type"] == "قله (Peak)" else DN
        rows.append(html.Tr([html.Td(tp["time"].strftime("%H:%M")), html.Td(f"{tp['price']:,.2f}", style={"color": GOLD}),
                              html.Td(tp["type"], style={"color": color, "fontWeight": "bold"})]))
    return html.Table([html.Thead(html.Tr([html.Th("زمان (UTC)"), html.Th("قیمت هدف"), html.Th("نوع چرخش")])),
                        html.Tbody(rows)])


def create_sr_table(levels, kind="support"):
    if not levels:
        return html.Div("سطحی یافت نشد.", style={"color": MUT, "textAlign": "center", "padding": "20px"})
    color = UP if kind == "support" else DN
    rows = []
    for lv in levels:
        rows.append(html.Tr([
            html.Td(f"{lv['price']:,.2f}", style={"color": color, "fontWeight": "bold"}),
            html.Td(f"{lv['score']:.0f}%", style={"color": GOLD}), html.Td(f"{lv['reliability']:.0f}%"),
            html.Td(f"{lv['touches']}"), html.Td(f"{lv['distance_pct']:+.2f}%"),
            html.Td("✅" if lv.get("confluence") else "—"),
        ]))
    return html.Table([html.Thead(html.Tr([html.Th("قیمت"), html.Th("امتیاز"), html.Th("اطمینان"),
                                            html.Th("برخورد"), html.Th("فاصله"), html.Th("هم‌راستا با حجم")])),
                        html.Tbody(rows)])


def create_cycles_table(cycles, meta):
    header = html.Div([
        html.Span(f"آستانه‌ی معناداری تصحیح‌شده (Bonferroni): α = {meta['alpha_eff']:.4f} روی {meta['n_candidates']} فرضیه",
                   style={"color": MUT, "fontSize": 11})
    ], style={"marginBottom": 8, "textAlign": "center"})

    if not cycles:
        body = html.Div("هیچ چرخه‌ی معناداری (زمینی یا سیاره‌ای) در این بازه یافت نشد — پیش‌بینی فقط بر اساس روند خطی است.",
                        style={"color": MUT, "textAlign": "center", "padding": "16px"})
        return html.Div([header, body])

    rows = []
    for c in cycles:
        days = c["period_bars"] * get_interval_minutes(DEFAULT_INTERVAL) / 1440  # نمایشی؛ دقیق در کالبک محاسبه می‌شود
        badge = "🪐 سیاره‌ای" if c["source"] == "planet" else "📊 تجربی"
        rows.append(html.Tr([
            html.Td(c["label"]), html.Td(badge),
            html.Td(f"{c['amp']:.2f}", style={"color": GOLD}),
            html.Td(f"{c['p_value']:.4f}", style={"color": UP if c['p_value'] < 0.01 else TXT}),
        ]))
    table = html.Table([html.Thead(html.Tr([html.Th("چرخه"), html.Th("منبع"), html.Th("دامنه"), html.Th("p-value")])),
                         html.Tbody(rows)])
    return html.Div([header, table])


app.layout = html.Div([
    html.Div([
        html.H2("💿 Multi-Disk Timeline Predictor", style={"color": GOLD, "fontWeight": 800, "margin": 0}),
        html.P("زمین + سیارات دیگر، هرکدام یک «سی‌دی» با چرخه‌ی خودشان — فقط چرخه‌هایی که از تست آماری رد شوند وارد پیش‌بینی می‌شوند.",
               style={"color": MUT, "fontSize": 13, "margin": "4px 0"})
    ], style={"textAlign": "center", "marginTop": 20}),

    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([html.Label("نماد", style={"color": MUT, "fontSize": 12}),
                 dcc.Input(id="symbol", value=DEFAULT_SYMBOL, type="text", className="form-control",
                           style={"backgroundColor": CARD2, "color": TXT, "borderColor": LINE})], md=2),
        dbc.Col([html.Label("تایم‌فریم", style={"color": MUT, "fontSize": 12}),
                 dcc.Dropdown(id="interval", options=INTERVAL_OPTS, value=DEFAULT_INTERVAL, clearable=False,
                              style={"backgroundColor": CARD2, "color": TXT})], md=2),
        dbc.Col([html.Label("افق پیش‌بینی (ساعت)", style={"color": MUT, "fontSize": 12}),
                 dcc.Input(id="forecast_hours", value=24, type="number", min=6, max=72, className="form-control",
                           style={"backgroundColor": CARD2, "color": TXT, "borderColor": LINE})], md=2),
        dbc.Col([html.Label("عمق تاریخچه (کندل)", style={"color": MUT, "fontSize": 12}),
                 dcc.Input(id="history_bars", value=3000, type="number", min=500, max=15000, step=500,
                           className="form-control",
                           style={"backgroundColor": CARD2, "color": TXT, "borderColor": LINE})], md=3),
        dbc.Col([html.Button("⚡ تحلیل چند-دیسکی", id="btn-update", n_clicks=0,
                             style={"marginTop": 24, "backgroundColor": GOLD, "color": BG, "border": "none",
                                    "borderRadius": 8, "padding": "8px 16px", "fontWeight": "bold", "width": "100%",
                                    "cursor": "pointer"})], md=3),
    ], align="center")), className="glass-card", style={"maxWidth": 1100, "margin": "20px auto"}),

    dbc.Row([
        dbc.Col([dcc.Graph(id="cd-graph", config={"displayModeBar": False}, style={"height": "620px"})], md=8),
        dbc.Col([html.Div([
            html.H5("⏳ نقاط چرخش قطعی", style={"color": GOLD, "textAlign": "center", "marginBottom": 15, "fontWeight": 800}),
            html.Div(id="turning-points-table"),
            html.Hr(style={"borderColor": LINE}),
            html.H5("🪐 چرخه‌های معنادار (تأییدشده)", style={"color": GOLD, "textAlign": "center", "marginBottom": 10, "fontWeight": 800}),
            html.Div(id="cycles-table"),
        ], className="glass-card", style={"padding": 20, "height": "100%"})], md=4)
    ], style={"maxWidth": 1300, "margin": "20px auto"}),

    dbc.Row([
        dbc.Col([html.Div([html.H5("🟢 دقیق‌ترین سطوح حمایت", style={"color": UP, "textAlign": "center", "marginBottom": 15, "fontWeight": 800}),
                           html.Div(id="support-table")], className="glass-card", style={"padding": 20})], md=6),
        dbc.Col([html.Div([html.H5("🔴 دقیق‌ترین سطوح مقاومت", style={"color": DN, "textAlign": "center", "marginBottom": 15, "fontWeight": 800}),
                           html.Div(id="resistance-table")], className="glass-card", style={"padding": 20})], md=6),
    ], style={"maxWidth": 1300, "margin": "10px auto"}),

    dbc.Row([
        stat_card("current-phase", "فاز فعلی شیار", BLUE),
        stat_card("next-tp", "نزدیک‌ترین نقطه چرخش", GOLD),
        stat_card("nearest-support", "نزدیک‌ترین حمایت", UP),
        stat_card("nearest-resistance", "نزدیک‌ترین مقاومت", DN),
        stat_card("oos-mae", "خطای Out-of-Sample (MAE%)", ORANGE),
        stat_card("oos-hit", "دقت جهت (Hit-Rate%)", CYAN),
    ], style={"maxWidth": 1300, "margin": "10px auto"}),

    dcc.Interval(id="interval-component", interval=90 * 1000, n_intervals=0)
], style={"backgroundColor": BG, "minHeight": "100vh", "paddingBottom": 50})


# ==============================================================================
# 5) Callback
# ==============================================================================
@app.callback(
    [Output("cd-graph", "figure"), Output("turning-points-table", "children"), Output("cycles-table", "children"),
     Output("support-table", "children"), Output("resistance-table", "children"),
     Output("current-phase-value", "children"), Output("next-tp-value", "children"),
     Output("nearest-support-value", "children"), Output("nearest-resistance-value", "children"),
     Output("oos-mae-value", "children"), Output("oos-hit-value", "children")],
    [Input("btn-update", "n_clicks"), Input("interval-component", "n_intervals")],
    [State("symbol", "value"), State("interval", "value"), State("forecast_hours", "value"), State("history_bars", "value")]
)
def update_dashboard(n_clicks, n_intervals, symbol, interval, forecast_hours, history_bars):
    symbol = (symbol or DEFAULT_SYMBOL).upper().strip()
    hb = int(history_bars) if history_bars else 3000
    interval_min = get_interval_minutes(interval)

    df = get_klines_extended(symbol, interval, total_bars=hb)
    now_utc = get_server_time()

    if df.empty or len(df) < 60:
        empty = empty_fig("داده کافی دریافت نشد")
        na = "—"
        return empty, html.Div("—"), html.Div("—"), html.Div("—"), html.Div("—"), na, na, na, na, na, na

    fh = forecast_hours if forecast_hours else 24
    steps = int((fh * 60) / interval_min)
    last_ts = pd.Timestamp(df.iloc[-1]["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)

    cycles, trend_coef, t, n, meta = detect_significant_cycles(df, interval_min, top_fft_k=5, alpha=ALPHA, n_perm=N_PERM)
    expected_path = forecast_from_cycles(cycles, trend_coef, n, steps)
    turning_points = find_turning_points(expected_path, last_ts, interval_min)

    supports, resistances = find_support_resistance(df, num_levels=5)
    fig = build_cd_figure(df, expected_path, turning_points, supports, resistances, cycles, now_utc, symbol, interval)

    tp_table = create_turning_points_table(turning_points)
    cycles_table = create_cycles_table(cycles, meta)
    support_table = create_sr_table(supports, "support")
    resistance_table = create_sr_table(resistances, "resistance")

    current_price = float(df.iloc[-1]["close"])
    current_phase = ("📈 صعودی (شیار رو به بالا)" if len(expected_path) and expected_path[0] > current_price
                      else "📉 نزولی (شیار رو به پایین)")

    next_tp_text = f"{turning_points[0]['time'].strftime('%H:%M')} | {turning_points[0]['price']:,.2f}" if turning_points else "—"
    nearest_support_text = f"{supports[0]['price']:,.2f} ({supports[0]['score']:.0f}%)" if supports else "—"
    nearest_resistance_text = f"{resistances[0]['price']:,.2f} ({resistances[0]['score']:.0f}%)" if resistances else "—"

    holdout = min(80, max(15, int(n * 0.08)))
    bt = backtest_walkforward(df, interval_min, holdout=holdout, top_fft_k=5, alpha=ALPHA, n_perm=100)
    mae_text = f"{bt['mae_pct']:.2f}%" if bt else "—"
    hit_text = f"{bt['hit_rate']:.1f}%" if bt else "—"

    return (fig, tp_table, cycles_table, support_table, resistance_table,
            current_phase, next_tp_text, nearest_support_text, nearest_resistance_text, mae_text, hit_text)


if __name__ == "__main__":
    app.run(debug=True, port=8050, host="127.0.0.1")
