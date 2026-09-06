# -*- coding: utf-8 -*-
"""
🚀 Advanced Bybit Chrono-Analyzer — Deep PathFinder + Capital Growth Engine
===========================================================================
این نسخه:
  ۱. مسیر آینده را فقط با فوریه خام نمی‌سازد؛ بلکه آن را با روند کلان ۱ ساعته و ۴ ساعته،
     قدرت چرخه‌ها، RSI، نوسان ATR و کیفیت مسیر ترکیب می‌کند.
  ۲. برای هر نقطه تاریخی، کل مسیر پیش‌بینی‌شده را با مسیر واقعی مقایسه می‌کند.
  ۳. یک امتیاز اعتماد (Confidence) می‌سازد و فقط مسیرهای با اعتماد بالا را وارد آمار می‌کند.
  ۴. سیستم رشد سرمایه با ۵۰۰ دلار اولیه، ریسک هر معامله، TP/SL مبتنی بر ATR و منحنی سرمایه دارد.
"""

import numpy as np
import pandas as pd
import requests
from datetime import datetime, timezone, timedelta
import plotly.graph_objects as go

import dash
from dash import dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc

# ==============================================================================
# 0) تنظیمات و پالت
# ==============================================================================
BG = "#050914"
CARD = "#0a1020"
LINE = "#1f2d4a"
TXT = "#e0e6ed"
MUT = "#6c7a9c"
NEON_CYAN = "#00f3ff"
NEON_PINK = "#ff00ea"
NEON_GOLD = "#ffd700"
NEON_RED = "#ff2a2a"
NEON_GREEN = "#2eff71"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_CATEGORY = "linear"
DEFAULT_INTERVAL = "15"
DEFAULT_FORECAST_HOURS = 4

N_BINS = 360
FIT_LOOKBACK = 120

# ==============================================================================
# 1) Bybit API
# ==============================================================================
REST_CANDIDATES = [
    "https://api.bybit.com",
    "https://api.bytick.com",
    "https://api.bybit.kz",
]
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
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
    except Exception:
        pass
    return datetime.now(timezone.utc)


def get_klines(symbol, interval, category="linear", limit=1000):
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

    df = pd.DataFrame(lst, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
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
        return 15


# ==============================================================================
# 2) اندیکاتورها
# ==============================================================================
def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['close'].shift(1)).abs()
    tr3 = (df['low'] - df['close'].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def add_base_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["atr"] = calculate_atr(df, 14)
    df["rsi"] = calculate_rsi(df["close"], 14)
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    return df


# ==============================================================================
# 3) داده‌های کلان برای فیلتر روند
# ==============================================================================
def prepare_macro_df(symbol: str, interval: str, limit: int = 500):
    dfm = get_klines(symbol, interval, category="linear", limit=limit)
    if dfm.empty or len(dfm) < 60:
        return None

    dfm["ema_fast"] = dfm["close"].ewm(span=20, adjust=False).mean()
    dfm["ema_slow"] = dfm["close"].ewm(span=50, adjust=False).mean()
    dfm["trend"] = dfm["ema_fast"] - dfm["ema_slow"]
    dfm["slope"] = dfm["trend"].diff(3) / 3.0

    dfm = dfm[["ts", "trend", "slope"]].dropna().reset_index(drop=True)
    if len(dfm) < 10:
        return None
    return dfm


# ==============================================================================
# 4) رادار اصلی — بدون تغییر اساسی
# ==============================================================================
def hour_frac_12(dt_utc):
    return (dt_utc.hour % 12) + dt_utc.minute / 60.0 + dt_utc.second / 3600.0


def hf_to_theta(hf, direction="cw"):
    return (90.0 - 30.0 * hf) % 360.0 if direction == "cw" else (90.0 + 30.0 * hf) % 360.0


def get_macro_trend_slope(symbol, category="linear"):
    df_macro = get_klines(symbol, interval="60", category=category, limit=50)
    if df_macro.empty or len(df_macro) < 10:
        return 0.0
    closes = df_macro["close"].values
    t = np.arange(len(closes))
    p = np.polyfit(t, closes, 1)
    return p[0]


def fourier_extrapolation_mtf(series, n_predict, macro_slope, interval_min, n_harmonics=6):
    n = len(series)
    if n < 10:
        return np.array([series[-1]] * n_predict)

    t = np.arange(n)
    p_local = np.polyfit(t, series, 1)
    scaled_macro_slope = macro_slope * (interval_min / 60.0)
    blended_slope = (p_local[0] * 0.5) + (scaled_macro_slope * 0.5)

    trend = p_local[1] + (blended_slope * t)
    detrended = series - trend

    freq_domain = np.fft.fft(detrended)
    freqs = np.fft.fftfreq(n)

    indexes = list(range(n))
    indexes.sort(key=lambda i: np.absolute(freq_domain[i]), reverse=True)

    t_fut = np.arange(n, n + n_predict)
    restored = np.zeros(n_predict)

    for i in indexes[1: 1 + n_harmonics * 2]:
        ampli = np.absolute(freq_domain[i]) / n
        phase = np.angle(freq_domain[i])
        restored += ampli * np.cos(2 * np.pi * freqs[i] * t_fut + phase)

    future_trend = p_local[1] + (blended_slope * t_fut)
    return restored + future_trend


def build_advanced_ring(df, now_utc, forecast_hours, interval_min, symbol):
    df['SMA'] = df['close'].rolling(window=20, min_periods=1).mean()
    df['STD'] = df['close'].rolling(window=20, min_periods=1).std().fillna(0)
    df['UB'] = df['SMA'] + (2 * df['STD'])
    df['LB'] = df['SMA'] - (2 * df['STD'])

    closes = df["close"].values
    min_p, max_p = df['close'].min(), df['close'].max()
    padding = (max_p - min_p) * 0.1 if max_p != min_p else 1
    abs_min, abs_max = min_p - padding, max_p + padding

    def p_to_r(p):
        return 0.6 + 0.8 * ((p - abs_min) / (abs_max - abs_min))

    bin_price = np.full(N_BINS, np.nan)
    bin_ub = np.full(N_BINS, np.nan)
    bin_lb = np.full(N_BINS, np.nan)
    bin_status = np.array(["past"] * N_BINS, dtype=object)

    for _, row in df.iterrows():
        ts = pd.Timestamp(row["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)
        hf = hour_frac_12(ts)
        idx = int(hf / 12.0 * N_BINS) % N_BINS
        bin_price[idx] = row["close"]
        bin_ub[idx] = row["UB"]
        bin_lb[idx] = row["LB"]

    steps = max(int((forecast_hours * 60.0) / max(interval_min, 1)), 1)

    macro_slope = get_macro_trend_slope(symbol)
    future_prices = fourier_extrapolation_mtf(closes[-FIT_LOOKBACK:], steps, macro_slope, interval_min)

    last_ts = pd.Timestamp(df.iloc[-1]["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)

    for s in range(1, steps + 1):
        t_future = last_ts + timedelta(minutes=interval_min * s)
        hf = hour_frac_12(t_future)
        idx = int(hf / 12.0 * N_BINS) % N_BINS
        bin_price[idx] = future_prices[s - 1]
        bin_status[idx] = "future"

    s_series = pd.Series(bin_price)
    s_series = s_series.interpolate(method='linear', limit_direction='both')
    bin_price = s_series.values

    hour_fracs = np.arange(N_BINS) / float(N_BINS) * 12.0
    thetas = np.array([hf_to_theta(hf, "cw") for hf in hour_fracs])

    rad_price = np.array([p_to_r(p) for p in bin_price])
    rad_ub = np.array([p_to_r(p) if not np.isnan(p) else rad_price[i] for i, p in enumerate(bin_ub)])
    rad_lb = np.array([p_to_r(p) if not np.isnan(p) else rad_price[i] for i, p in enumerate(bin_lb)])

    return thetas, hour_fracs, bin_price, rad_price, rad_ub, rad_lb, bin_status, p_to_r, future_prices[-1]


def empty_fig(msg):
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    fig.add_annotation(
        x=0.5, y=0.5, xref="paper", yref="paper",
        text=msg, showarrow=False,
        font=dict(size=18, color=NEON_RED),
    )
    return fig


def build_advanced_clock(df, now_utc, symbol, interval, forecast_hours):
    if df.empty or len(df) < 20:
        return empty_fig("در حال دریافت داده..."), {"live": 0, "mirror": 0, "trend": "---", "pred": 0}

    interval_min = get_interval_minutes(interval)
    thetas, hfs, prices, r_price, r_ub, r_lb, status, norm_func, last_pred_price = build_advanced_ring(
        df, now_utc, forecast_hours, interval_min, symbol
    )

    live_price = float(df.iloc[-1]["close"])
    hf_now = hour_frac_12(now_utc)
    th_cw = hf_to_theta(hf_now, "cw")
    th_ccw = hf_to_theta(hf_now, "ccw")

    fig = go.Figure()

    for r_level in [0.6, 1.0, 1.4]:
        fig.add_trace(go.Scatter(
            x=r_level * np.cos(np.radians(np.linspace(0, 360, 100))),
            y=r_level * np.sin(np.radians(np.linspace(0, 360, 100))),
            mode="lines", line=dict(color=LINE, width=1, dash="dot"), hoverinfo="skip"
        ))

    for h in range(1, 13):
        th = (90 - 30 * h) % 360
        c, s = np.cos(np.radians(th)), np.sin(np.radians(th))
        fig.add_trace(go.Scatter(x=[0, 1.45 * c], y=[0, 1.45 * s], mode="lines",
                                 line=dict(color=LINE, width=1), hoverinfo="skip"))
        fig.add_annotation(x=1.55 * c, y=1.55 * s, text=f"<b>{h}</b>", showarrow=False,
                           font=dict(size=14, color=MUT))

    sort_idx = np.argsort(-thetas)
    th_sorted = thetas[sort_idx]

    xs_ub = r_ub[sort_idx] * np.cos(np.radians(th_sorted))
    ys_ub = r_ub[sort_idx] * np.sin(np.radians(th_sorted))
    xs_lb = r_lb[sort_idx] * np.cos(np.radians(th_sorted))
    ys_lb = r_lb[sort_idx] * np.sin(np.radians(th_sorted))

    fig.add_trace(go.Scatter(
        x=np.concatenate([xs_ub, xs_lb[::-1]]),
        y=np.concatenate([ys_ub, ys_lb[::-1]]),
        fill='toself', fillcolor="rgba(0, 243, 255, 0.05)",
        line=dict(color="rgba(255,255,255,0)"), hoverinfo="skip", name="محدوده نوسان"
    ))

    past_mask = (status == "past")
    fut_mask = (status == "future")

    fig.add_trace(go.Scatter(
        x=r_price[past_mask] * np.cos(np.radians(thetas[past_mask])),
        y=r_price[past_mask] * np.sin(np.radians(thetas[past_mask])),
        mode="markers+lines",
        line=dict(color=NEON_CYAN, width=2, shape="spline"),
        marker=dict(size=4, color=NEON_CYAN),
        name="گذشته قیمت",
        customdata=prices[past_mask],
        hovertemplate="تاریخی: %{customdata:.4f}<extra></extra>"
    ))

    fig.add_trace(go.Scatter(
        x=r_price[fut_mask] * np.cos(np.radians(thetas[fut_mask])),
        y=r_price[fut_mask] * np.sin(np.radians(thetas[fut_mask])),
        mode="markers+lines",
        line=dict(color=NEON_PINK, width=3, dash="dash", shape="spline"),
        marker=dict(size=6, color=NEON_PINK, symbol="diamond"),
        name="پیش‌بینی هماهنگ‌شده (MTF)",
        customdata=prices[fut_mask],
        hovertemplate="پیش‌بینی: %{customdata:.4f}<extra></extra>"
    ))

    r_live = norm_func(live_price)
    lc, ls = np.cos(np.radians(th_cw)), np.sin(np.radians(th_cw))
    fig.add_trace(go.Scatter(
        x=[r_live * lc], y=[r_live * ls],
        mode="markers+text",
        marker=dict(size=20, symbol="star-diamond", color=NEON_GOLD, line=dict(width=2, color="#000")),
        text=[f"{live_price:.4g}"], textposition="top right",
        textfont=dict(color=NEON_GOLD, size=14, family="Arial Black"),
        name="قیمت زنده"
    ))

    ccw_idx = np.argmin(np.abs(thetas - th_ccw))
    mirror_price = prices[ccw_idx]
    r_mirror = norm_func(mirror_price)
    mc, ms = np.cos(np.radians(th_ccw)), np.sin(np.radians(th_ccw))

    fig.add_trace(go.Scatter(
        x=[r_live * lc, r_mirror * mc], y=[r_live * ls, r_mirror * ms],
        mode="lines", line=dict(color="rgba(255, 215, 0, 0.3)", width=1, dash="dot"),
        name="محور تقارن"
    ))

    fig.add_trace(go.Scatter(
        x=[0, 1.3 * lc], y=[0, 1.3 * ls], mode="lines",
        line=dict(color=TXT, width=4), name="عقربه زمان (CW)"
    ))

    fig.add_trace(go.Scatter(
        x=[0, 1.1 * mc], y=[0, 1.1 * ms], mode="lines",
        line=dict(color=NEON_RED, width=3, dash="dot"), name="زمان معکوس (CCW)"
    ))

    lim = 1.75
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        showlegend=True,
        legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center", font=dict(color=MUT)),
        margin=dict(l=10, r=10, t=40, b=10),
    )
    fig.update_xaxes(range=[-lim, lim], visible=False)
    fig.update_yaxes(range=[-lim, lim], visible=False, scaleanchor="x", scaleratio=1)

    stats = {
        "live": live_price,
        "mirror": mirror_price,
        "trend": "صعودی ↗" if last_pred_price > live_price else "نزولی ↘",
        "pred": last_pred_price
    }
    return fig, stats


# ==============================================================================
# 5) مسیر‌یابی عمیق و امتیاز اعتماد
# ==============================================================================
def enhanced_predict_path(
        closes,
        current_price,
        n_predict,
        interval_min,
        m1_slope,
        m4_slope,
        m1_trend,
        m4_trend,
        rsi_val,
        atr_val,
        atr_pct
):
    n = len(closes)
    if n < 30 or n_predict <= 0 or current_price <= 0:
        return None

    t = np.arange(n)
    try:
        p = np.polyfit(t, closes, 1)
    except Exception:
        return None

    local_slope = float(p[0])
    trend = p[1] + local_slope * t
    detrended = closes - trend

    # استخراج چرخه‌ها و انرژی طیفی
    energy_ratio = 0.0
    cycles = np.zeros(n_predict)

    if np.std(detrended) > 1e-12:
        fft_vals = np.fft.rfft(detrended)
        freqs = np.fft.rfftfreq(n, d=1)
        power = np.abs(fft_vals)
        total_power = float(np.sum(power[1:] ** 2))

        chosen = []
        if total_power > 1e-12:
            order = np.argsort(power[1:])[::-1] + 1
            cum = 0.0
            for idx in order:
                cum += float(power[idx] ** 2)
                chosen.append(int(idx))
                energy_ratio = cum / total_power
                if energy_ratio >= 0.85 or len(chosen) >= 8:
                    break

        t_fut = np.arange(n, n + n_predict)
        restored = np.zeros(n_predict)
        current_cycle = 0.0

        for idx in chosen:
            amp = float(np.abs(fft_vals[idx]) / n)
            phase = float(np.angle(fft_vals[idx]))
            freq = float(freqs[idx])
            restored += amp * np.cos(2 * np.pi * freq * t_fut + phase)
            current_cycle += amp * np.cos(2 * np.pi * freq * (n - 1) + phase)

        cycles = restored - current_cycle

    def safe_float(x, default=0.0):
        try:
            if x is None:
                return default
            if pd.isna(x):
                return default
            return float(x)
        except Exception:
            return default

    m1_slope = safe_float(m1_slope)
    m4_slope = safe_float(m4_slope)
    m1_trend = safe_float(m1_trend)
    m4_trend = safe_float(m4_trend)

    m1_scaled = m1_slope * (interval_min / 60.0)
    m4_scaled = m4_slope * (interval_min / 240.0)

    # ترکیب روند محلی با روندهای کلان
    blended_slope = (0.55 * local_slope) + (0.25 * m1_scaled) + (0.20 * m4_scaled)

    local_sign = int(np.sign(local_slope))
    m1_sign = int(np.sign(m1_trend))
    m4_sign = int(np.sign(m4_trend))

    # اگر روند محلی خلاف هر دو روند کلان بود، شدت حرکت کم می‌شود
    if local_sign != 0 and m1_sign != 0 and m4_sign != 0:
        if local_sign != m1_sign and local_sign != m4_sign:
            blended_slope *= 0.45

    base_path = current_price + blended_slope * np.arange(1, n_predict + 1)

    # وزن چرخه‌ها بر اساس قدرت طیفی و نوسان بازار
    cycle_weight = min(0.80, max(0.0, energy_ratio * 0.65))
    if atr_pct > 0.03:
        cycle_weight *= 0.50
    elif atr_pct > 0.015:
        cycle_weight *= 0.75

    raw_path = base_path + cycle_weight * cycles

    # نرم‌سازی مسیر برای کاهش نویز
    path = np.empty(n_predict, dtype=float)
    prev = float(current_price)
    alpha = 0.40
    for j, val in enumerate(raw_path):
        prev = alpha * float(val) + (1 - alpha) * prev
        path[j] = prev

    path = np.maximum(path, current_price * 0.01)

    direction = int(np.sign(path[-1] - current_price))
    if direction == 0:
        direction = int(np.sign(blended_slope))
    if direction == 0:
        direction = 1 if local_slope >= 0 else -1

    # ----------------- امتیاز اعتماد -----------------
    trend_score = 0
    if int(np.sign(local_slope)) == direction:
        trend_score += 12
    if m1_sign != 0 and m1_sign == direction:
        trend_score += 18
    if m4_sign != 0 and m4_sign == direction:
        trend_score += 10
    if m1_sign != 0 and m4_sign != 0 and m1_sign == m4_sign == direction:
        trend_score += 5
    trend_score = min(40, trend_score)

    spectral_score = min(25.0, energy_ratio * 30.0)

    rsi_val = safe_float(rsi_val, 50.0)
    if direction > 0:
        if 52 <= rsi_val <= 70:
            momentum_score = 15
        elif 45 <= rsi_val < 52:
            momentum_score = 8
        elif 70 < rsi_val <= 78:
            momentum_score = 5
        else:
            momentum_score = 2
    else:
        if 30 <= rsi_val <= 48:
            momentum_score = 15
        elif 48 < rsi_val <= 55:
            momentum_score = 8
        elif 22 <= rsi_val < 30:
            momentum_score = 5
        else:
            momentum_score = 2

    if 0.0015 <= atr_pct <= 0.025:
        volatility_score = 10
    elif atr_pct < 0.0015:
        volatility_score = 4
    elif atr_pct <= 0.04:
        volatility_score = 6
    else:
        volatility_score = 2

    steps = np.abs(np.diff(np.concatenate(([current_price], path))))
    roughness = float(np.mean(steps)) / max(float(atr_val), 1e-9)

    if roughness < 0.9:
        quality_score = 10
    elif roughness < 1.6:
        quality_score = 7
    elif roughness < 2.5:
        quality_score = 4
    else:
        quality_score = 1

    confidence = float(min(100.0, trend_score + spectral_score + momentum_score + volatility_score + quality_score))

    # اگر مسیر خلاف هر دو روند کلان بود، جریمه می‌شود
    if m1_sign != 0 and m4_sign != 0 and direction != m1_sign and direction != m4_sign:
        confidence = max(0.0, confidence - 20.0)

    return path, confidence, float(energy_ratio), direction


def adaptive_threshold_from_history(confidences, wins, min_trades=20, target_wr=52.0):
    """
    آستانه تطبیقی بر اساس تاریخچه قبلی — بدون نگاه به آینده.
    """
    if len(confidences) < min_trades:
        return 0.0

    pairs = sorted(zip(confidences, wins), key=lambda x: x[0], reverse=True)
    cum_win = 0
    total = 0
    threshold = 0.0

    for conf, win in pairs:
        total += 1
        cum_win += int(win)
        if total >= min_trades:
            wr = (cum_win / total) * 100.0
            if wr >= target_wr:
                threshold = float(conf)
            elif threshold > 0:
                break

    return threshold


# ==============================================================================
# 6) بک‌تست کامل مسیر + رشد سرمایه
# ==============================================================================
def run_full_analytics(
        df,
        macro1,
        macro4,
        interval,
        lookforward=12,
        min_confidence=50.0,
        auto_threshold=True,
        min_rr=0.70,
        initial_capital=500.0,
        risk_pct=2.0
):
    df = add_base_indicators(df)
    interval_min = get_interval_minutes(interval)
    n = len(df)
    start = max(FIT_LOOKBACK, 60)

    if n <= start + lookforward:
        return {
            "rows": [],
            "qualified_rows": [],
            "trades": [],
            "equity_curve": [],
            "total_paths": 0,
            "qualified_paths": 0,
            "path_wr_all": 0.0,
            "path_wr_qualified": 0.0,
            "trade_win_rate": 0.0,
            "avg_confidence_qualified": 0.0,
            "final_equity": initial_capital,
            "growth_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "profit_factor": 0.0,
            "effective_threshold_final": min_confidence,
        }

    # آرایه‌های کلان برای جستجوی سریع
    if macro1 is not None and len(macro1) > 0:
        m1_ts = macro1["ts"].values
        m1_trend_arr = macro1["trend"].values
        m1_slope_arr = macro1["slope"].values
    else:
        m1_ts = np.array([], dtype="datetime64[ns]")
        m1_trend_arr = np.array([])
        m1_slope_arr = np.array([])

    if macro4 is not None and len(macro4) > 0:
        m4_ts = macro4["ts"].values
        m4_trend_arr = macro4["trend"].values
        m4_slope_arr = macro4["slope"].values
    else:
        m4_ts = np.array([], dtype="datetime64[ns]")
        m4_trend_arr = np.array([])
        m4_slope_arr = np.array([])

    rows = []
    qualified_rows = []
    trades = []

    equity = float(initial_capital)
    peak = float(initial_capital)
    max_dd = 0.0
    gross_win = 0.0
    gross_loss = 0.0

    first_time = df["ts"].iloc[start] if start < n else df["ts"].iloc[-1]
    equity_curve = [{"time": first_time, "equity": equity}]

    history_conf = []
    history_win = []
    effective_threshold_final = float(min_confidence)

    closes_all = df["close"].values

    for i in range(start, n - lookforward):
        row = df.iloc[i]
        current_time = row["ts"]
        current_price = float(row["close"])

        atr_val = float(row["atr"]) if not pd.isna(row["atr"]) else current_price * 0.005
        if atr_val <= 0:
            atr_val = current_price * 0.005
        atr_pct = atr_val / current_price if current_price > 0 else 0.0

        rsi_val = float(row["rsi"]) if not pd.isna(row["rsi"]) else 50.0

        closes_local = closes_all[max(0, i - FIT_LOOKBACK + 1): i + 1]
        if len(closes_local) < 35:
            continue

        current_np = np.datetime64(current_time)

        # مقدارهای کلان ۱ ساعته
        m1_trend = 0.0
        m1_slope = 0.0
        if len(m1_ts) > 0:
            idx1 = int(np.searchsorted(m1_ts, current_np, side="right") - 1)
            if idx1 >= 0:
                m1_trend = float(m1_trend_arr[idx1]) if not pd.isna(m1_trend_arr[idx1]) else 0.0
                m1_slope = float(m1_slope_arr[idx1]) if not pd.isna(m1_slope_arr[idx1]) else 0.0

        # مقدارهای کلان ۴ ساعته
        m4_trend = 0.0
        m4_slope = 0.0
        if len(m4_ts) > 0:
            idx4 = int(np.searchsorted(m4_ts, current_np, side="right") - 1)
            if idx4 >= 0:
                m4_trend = float(m4_trend_arr[idx4]) if not pd.isna(m4_trend_arr[idx4]) else 0.0
                m4_slope = float(m4_slope_arr[idx4]) if not pd.isna(m4_slope_arr[idx4]) else 0.0

        pred = enhanced_predict_path(
            closes=closes_local,
            current_price=current_price,
            n_predict=lookforward,
            interval_min=interval_min,
            m1_slope=m1_slope,
            m4_slope=m4_slope,
            m1_trend=m1_trend,
            m4_trend=m4_trend,
            rsi_val=rsi_val,
            atr_val=atr_val,
            atr_pct=atr_pct,
        )

        if pred is None:
            continue

        path, confidence, energy_ratio, direction = pred

        actual_end = float(closes_all[i + lookforward])
        actual_sign = int(np.sign(actual_end - current_price))
        endpoint_win = 1 if actual_sign == direction else 0

        # آستانه تطبیقی فقط از تاریخچه گذشته
        adaptive_thr = 0.0
        if auto_threshold:
            adaptive_thr = adaptive_threshold_from_history(history_conf, history_win)

        effective_threshold = max(float(min_confidence), float(adaptive_thr))
        effective_threshold_final = effective_threshold

        qualified = bool(confidence >= effective_threshold)

        # ذخیره تاریخچه برای آستانه تطبیقی بعدی
        history_conf.append(float(confidence))
        history_win.append(int(endpoint_win))

        path_row = {
            "time": current_time,
            "index": i,
            "current_price": current_price,
            "pred_end": float(path[-1]),
            "actual_end": actual_end,
            "direction": int(direction),
            "endpoint_win": int(endpoint_win),
            "confidence": float(confidence),
            "energy_ratio": float(energy_ratio),
            "threshold": float(effective_threshold),
            "qualified": qualified,
            "atr": atr_val,
            "rsi": rsi_val,
        }

        rows.append(path_row)
        if qualified:
            qualified_rows.append(path_row)

        # ----------------- شبیه‌سازی سرمایه -----------------
        if qualified and equity > 0:
            stop_distance = max(1.20 * atr_val, current_price * 0.0015)
            pred_distance = abs(float(path[-1]) - current_price)

            # هدف کوچک/متوسط برای افزایش شانس برخورد TP، ولی هنوز منطقی
            target_distance = min(max(pred_distance, 0.90 * atr_val), 2.50 * atr_val)

            if target_distance <= 0 or stop_distance <= 0:
                continue

            tp_price = current_price + direction * target_distance
            sl_price = current_price - direction * stop_distance
            rr = target_distance / stop_distance

            if rr < min_rr:
                continue

            risk_amount = equity * (float(risk_pct) / 100.0)
            qty = risk_amount / stop_distance

            outcome = "Pending"
            reason = "Timeout"
            exit_price = current_price
            pnl = 0.0

            future = df.iloc[i + 1: i + 1 + lookforward]

            for _, f in future.iterrows():
                high = float(f["high"])
                low = float(f["low"])

                if direction > 0:
                    # اول SL برای محافظه‌کاری
                    if low <= sl_price:
                        outcome = "Loss"
                        reason = "SL"
                        exit_price = sl_price
                        pnl = -risk_amount
                        break
                    if high >= tp_price:
                        outcome = "Win"
                        reason = "TP"
                        exit_price = tp_price
                        pnl = qty * (tp_price - current_price)
                        break
                else:
                    if high >= sl_price:
                        outcome = "Loss"
                        reason = "SL"
                        exit_price = sl_price
                        pnl = -risk_amount
                        break
                    if low <= tp_price:
                        outcome = "Win"
                        reason = "TP"
                        exit_price = tp_price
                        pnl = qty * (current_price - tp_price)
                        break

            if outcome == "Pending":
                exit_price = actual_end
                pnl = qty * (exit_price - current_price) * direction
                outcome = "Win" if pnl > 0 else "Loss"
                reason = "Close"

            equity += pnl
            if equity < 0:
                equity = 0.0

            peak = max(peak, equity)
            dd = ((peak - equity) / peak * 100.0) if peak > 0 else 0.0
            max_dd = max(max_dd, dd)

            if pnl > 0:
                gross_win += pnl
            else:
                gross_loss += abs(pnl)

            trade_row = {
                "time": current_time,
                "direction": int(direction),
                "entry": current_price,
                "tp": tp_price,
                "sl": sl_price,
                "exit": exit_price,
                "pnl": pnl,
                "equity": equity,
                "confidence": confidence,
                "rr": rr,
                "reason": reason,
                "outcome": outcome,
            }
            trades.append(trade_row)
            equity_curve.append({"time": current_time, "equity": equity})

    total_paths = len(rows)
    qualified_paths = len(qualified_rows)

    path_wr_all = (sum(r["endpoint_win"] for r in rows) / total_paths * 100.0) if total_paths > 0 else 0.0
    path_wr_qualified = (sum(r["endpoint_win"] for r in qualified_rows) / qualified_paths * 100.0) if qualified_paths > 0 else 0.0

    trade_wins = sum(1 for t in trades if t["pnl"] > 0)
    trade_total = len(trades)
    trade_win_rate = (trade_wins / trade_total * 100.0) if trade_total > 0 else 0.0

    avg_conf_qualified = float(np.mean([r["confidence"] for r in qualified_rows])) if qualified_rows else 0.0

    final_equity = equity
    growth_pct = ((final_equity - initial_capital) / initial_capital * 100.0) if initial_capital > 0 else 0.0

    if gross_loss > 0:
        profit_factor = gross_win / gross_loss
    elif gross_win > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    return {
        "rows": rows,
        "qualified_rows": qualified_rows,
        "trades": trades,
        "equity_curve": equity_curve,
        "total_paths": total_paths,
        "qualified_paths": qualified_paths,
        "path_wr_all": path_wr_all,
        "path_wr_qualified": path_wr_qualified,
        "trade_win_rate": trade_win_rate,
        "avg_confidence_qualified": avg_conf_qualified,
        "final_equity": final_equity,
        "growth_pct": growth_pct,
        "max_drawdown_pct": max_dd,
        "profit_factor": profit_factor,
        "effective_threshold_final": effective_threshold_final,
    }


# ==============================================================================
# 7) نمودارهای آمار و سرمایه
# ==============================================================================
def build_gauge(value, title, color, suffix="%"):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=float(value),
        number={"suffix": suffix, "font": {"color": color, "size": 28}},
        title={"text": title, "font": {"color": MUT, "size": 13}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": MUT},
            "bar": {"color": color},
            "bgcolor": CARD,
            "steps": [
                {"range": [0, 40], "color": "rgba(255,42,42,0.10)"},
                {"range": [40, 60], "color": "rgba(255,215,0,0.10)"},
                {"range": [60, 100], "color": "rgba(0,243,255,0.10)"},
            ],
            "threshold": {
                "line": {"color": "white", "width": 3},
                "thickness": 0.75,
                "value": 50
            }
        }
    ))
    fig.update_layout(
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font=dict(family="Tahoma", color=TXT),
        margin=dict(l=25, r=25, t=55, b=10),
        height=250,
    )
    return fig


def build_equity_fig(equity_curve, initial_capital):
    fig = go.Figure()

    if not equity_curve:
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text="معامله‌ای ثبت نشده است", showarrow=False,
            font=dict(color=NEON_GOLD, size=16)
        )
    else:
        times = [p["time"] for p in equity_curve]
        eq = [p["equity"] for p in equity_curve]

        fig.add_trace(go.Scatter(
            x=times,
            y=eq,
            mode="lines+markers",
            line=dict(color=NEON_CYAN, width=3, shape="spline"),
            marker=dict(size=6, color=NEON_CYAN),
            name="سرمایه",
        ))

        fig.add_trace(go.Scatter(
            x=[times[0], times[-1]],
            y=[initial_capital, initial_capital],
            mode="lines",
            line=dict(color=NEON_GOLD, width=1.5, dash="dot"),
            name="سرمایه اولیه",
        ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        title=dict(text="📈 رشد سرمایه در طول مسیر بک‌تست", font=dict(color=NEON_CYAN, size=18)),
        xaxis=dict(gridcolor=LINE, color=MUT),
        yaxis=dict(gridcolor=LINE, color=MUT, title="USDT"),
        legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center", font=dict(color=MUT)),
        margin=dict(l=20, r=20, t=60, b=20),
        font=dict(family="Tahoma, Arial", color=TXT),
    )
    return fig


# ==============================================================================
# 8) Dash App
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY], suppress_callback_exceptions=True)
app.title = "Advanced Chrono-Analyzer — Deep PathFinder"
server = app.server

app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            body { background-color: #050914; color: #e0e6ed; font-family: Tahoma, Arial, sans-serif; }
            .custom-tab {
                background-color: #0a1020 !important;
                color: #6c7a9c !important;
                border: 1px solid #1f2d4a !important;
                border-bottom: none !important;
                border-top-left-radius: 10px !important;
                border-top-right-radius: 10px !important;
                margin-right: 5px !important;
                font-weight: bold !important;
            }
            .custom-tab--selected {
                background-color: #050914 !important;
                color: #00f3ff !important;
                border: 1px solid #00f3ff !important;
                border-bottom: 1px solid #050914 !important;
            }
            .custom-tabs {
                border-bottom: 1px solid #1f2d4a !important;
                margin-bottom: 20px !important;
            }
            .card-neon {
                background: #0a1020;
                border: 1px solid #1f2d4a;
                border-radius: 12px;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""

INTERVAL_OPTS = [{"label": l, "value": v} for l, v in [("5m", "5"), ("15m", "15"), ("1h", "60"), ("4h", "240")]]

app.layout = html.Div([
    dbc.Container([
        html.H2(
            "⚡ رادار تقارن زمانی + مسیر‌یابی عمیق و رشد سرمایه",
            style={"color": NEON_CYAN, "textAlign": "center", "fontWeight": "bold", "marginBottom": "20px"}
        ),

        dbc.Row([
            dbc.Col([
                html.Div("نماد", className="text-muted small"),
                dbc.Input(id="symbol", value=DEFAULT_SYMBOL, type="text", className="text-center",
                          style={"background": CARD, "color": NEON_GOLD, "border": f"1px solid {LINE}"})
            ], md=3),
            dbc.Col([
                html.Div("تایم‌فریم", className="text-muted small"),
                dcc.Dropdown(id="interval", value=DEFAULT_INTERVAL, options=INTERVAL_OPTS, clearable=False,
                             style={"color": "black"})
            ], md=2),
            dbc.Col([
                html.Div("افق رادار (ساعت)", className="text-muted small"),
                dbc.Input(id="forecast-hours", type="number", value=DEFAULT_FORECAST_HOURS, min=1, max=24,
                          style={"background": CARD, "color": TXT, "border": f"1px solid {LINE}"})
            ], md=3),
            dbc.Col([
                html.Div("اسکن", className="text-muted small"),
                dbc.Button("اسکن مجدد 📡", id="refresh-btn", color="info", className="w-100",
                           style={"fontWeight": "bold"})
            ], md=4),
        ], className="mb-3"),

        dcc.Tabs(id="main-tabs", value="tab-radar", className="custom-tabs", children=[

            # ==================== TAB 1: RADAR ====================
            dcc.Tab(label="📡 رادار زمانی", value="tab-radar", className="custom-tab", children=[
                dbc.Row([
                    dbc.Col(dbc.Card([
                        html.Div("قیمت لایو", className="text-muted small"),
                        html.H4(id="stat-live", style={"color": NEON_GOLD})
                    ], body=True, style={"background": CARD, "borderLeft": f"4px solid {NEON_GOLD}"})),
                    dbc.Col(dbc.Card([
                        html.Div("تارگت پیش‌بینی MTF", className="text-muted small"),
                        html.H4(id="stat-pred", style={"color": NEON_PINK})
                    ], body=True, style={"background": CARD, "borderLeft": f"4px solid {NEON_PINK}"})),
                    dbc.Col(dbc.Card([
                        html.Div("پیوت تقارن", className="text-muted small"),
                        html.H4(id="stat-mirror", style={"color": NEON_RED})
                    ], body=True, style={"background": CARD, "borderLeft": f"4px solid {NEON_RED}"})),
                ], className="mb-3 text-center"),

                dbc.Card(dcc.Graph(id="radar-graph", style={"height": "75vh"}),
                         style={"background": BG, "border": f"1px solid {LINE}"}),
            ]),

            # ==================== TAB 2: PATH WINRATE ====================
            dcc.Tab(label="📈 وین‌ریت مسیر عمیق", value="tab-path", className="custom-tab", children=[
                dbc.Row([
                    dbc.Col([
                        html.Div("افق مسیر (کندل)", className="text-muted small"),
                        dbc.Input(id="path-lookforward", type="number", value=12, min=5, max=60, step=1,
                                  style={"background": CARD, "color": TXT, "border": f"1px solid {LINE}"})
                    ], md=3),
                    dbc.Col([
                        html.Div("حداقل اعتماد", className="text-muted small"),
                        dbc.Input(id="min-confidence", type="number", value=50, min=0, max=100, step=1,
                                  style={"background": CARD, "color": TXT, "border": f"1px solid {LINE}"})
                    ], md=3),
                    dbc.Col([
                        html.Div("آستانه تطبیقی", className="text-muted small"),
                        dcc.Dropdown(id="auto-threshold", value="yes", clearable=False,
                                     options=[
                                         {"label": "فعال", "value": "yes"},
                                         {"label": "غیرفعال", "value": "no"},
                                     ], style={"color": "black"})
                    ], md=3),
                ], className="mb-4"),

                dbc.Row([
                    dbc.Col(dbc.Card([
                        html.Div("کل مسیرهای بررسی‌شده", className="text-muted small"),
                        html.H4(id="path-total-value", style={"color": NEON_CYAN})
                    ], body=True, className="card-neon text-center")),
                    dbc.Col(dbc.Card([
                        html.Div("مسیرهای واجد شرایط", className="text-muted small"),
                        html.H4(id="path-qualified-value", style={"color": NEON_GOLD})
                    ], body=True, className="card-neon text-center")),
                    dbc.Col(dbc.Card([
                        html.Div("وین‌ریت مسیر واجد شرایط", className="text-muted small"),
                        html.H4(id="path-wr-value", style={"color": NEON_PINK})
                    ], body=True, className="card-neon text-center")),
                    dbc.Col(dbc.Card([
                        html.Div("وین‌ریت معاملات", className="text-muted small"),
                        html.H4(id="trade-wr-value", style={"color": NEON_GREEN})
                    ], body=True, className="card-neon text-center")),
                ], className="mb-4"),

                dbc.Row([
                    dbc.Col(dcc.Graph(id="gauge-path-wr"), md=4),
                    dbc.Col(dcc.Graph(id="gauge-trade-wr"), md=4),
                    dbc.Col(dcc.Graph(id="gauge-confidence"), md=4),
                ], className="mb-4"),

                dbc.Card([
                    html.H5("🧭 تاریخچه ارزیابی مسیرها", className="text-center p-2",
                            style={"color": NEON_CYAN, "fontWeight": "bold"}),
                    dash_table.DataTable(
                        id="path-table",
                        page_size=15,
                        columns=[
                            {"name": "زمان", "id": "زمان"},
                            {"name": "قیمت", "id": "قیمت"},
                            {"name": "جهت", "id": "جهت"},
                            {"name": "پایان پیش‌بینی", "id": "پایان پیش‌بینی"},
                            {"name": "پایان واقعی", "id": "پایان واقعی"},
                            {"name": "نتیجه مسیر", "id": "نتیجه مسیر"},
                            {"name": "اعتماد", "id": "اعتماد"},
                            {"name": "آستانه", "id": "آستانه"},
                            {"name": "وضعیت", "id": "وضعیت"},
                        ],
                        style_table={"overflowX": "auto", "backgroundColor": BG},
                        style_header={"backgroundColor": CARD, "color": NEON_CYAN, "fontWeight": "bold",
                                      "border": f"1px solid {LINE}", "textAlign": "center"},
                        style_cell={"backgroundColor": BG, "color": TXT, "border": f"1px solid {LINE}",
                                    "textAlign": "center", "fontFamily": "Tahoma, Arial"},
                    )
                ], style={"background": BG, "border": f"1px solid {LINE}"}),
            ]),

            # ==================== TAB 3: CAPITAL GROWTH ====================
            dcc.Tab(label="💰 رشد سرمایه", value="tab-capital", className="custom-tab", children=[
                dbc.Row([
                    dbc.Col([
                        html.Div("سرمایه اولیه (USDT)", className="text-muted small"),
                        dbc.Input(id="initial-capital", type="number", value=500, min=10, step=10,
                                  style={"background": CARD, "color": TXT, "border": f"1px solid {LINE}"})
                    ], md=3),
                    dbc.Col([
                        html.Div("ریسک هر معامله (%)", className="text-muted small"),
                        dbc.Input(id="risk-per-trade", type="number", value=2, min=0.1, max=10, step=0.1,
                                  style={"background": CARD, "color": TXT, "border": f"1px solid {LINE}"})
                    ], md=3),
                    dbc.Col([
                        html.Div("حداقل R:R", className="text-muted small"),
                        dbc.Input(id="min-rr", type="number", value=0.7, min=0.1, max=5, step=0.1,
                                  style={"background": CARD, "color": TXT, "border": f"1px solid {LINE}"})
                    ], md=3),
                ], className="mb-4"),

                dbc.Row([
                    dbc.Col(dbc.Card([
                        html.Div("سرمایه نهایی", className="text-muted small"),
                        html.H4(id="cap-final-value", style={"color": NEON_CYAN})
                    ], body=True, className="card-neon text-center")),
                    dbc.Col(dbc.Card([
                        html.Div("درصد رشد / ضرر", className="text-muted small"),
                        html.H4(id="cap-growth-value", style={"color": NEON_GOLD})
                    ], body=True, className="card-neon text-center")),
                    dbc.Col(dbc.Card([
                        html.Div("بیشترین Drawdown", className="text-muted small"),
                        html.H4(id="cap-maxdd-value", style={"color": NEON_RED})
                    ], body=True, className="card-neon text-center")),
                    dbc.Col(dbc.Card([
                        html.Div("Profit Factor", className="text-muted small"),
                        html.H4(id="cap-pf-value", style={"color": NEON_PINK})
                    ], body=True, className="card-neon text-center")),
                    dbc.Col(dbc.Card([
                        html.Div("تعداد معاملات", className="text-muted small"),
                        html.H4(id="cap-trades-value", style={"color": NEON_GREEN})
                    ], body=True, className="card-neon text-center")),
                ], className="mb-4"),

                dbc.Card(dcc.Graph(id="equity-graph", style={"height": "45vh"}),
                         className="card-neon mb-4"),

                dbc.Card([
                    html.H5("📊 ریز معاملات انجام‌شده", className="text-center p-2",
                            style={"color": NEON_CYAN, "fontWeight": "bold"}),
                    dash_table.DataTable(
                        id="trades-table",
                        page_size=15,
                        columns=[
                            {"name": "زمان", "id": "زمان"},
                            {"name": "جهت", "id": "جهت"},
                            {"name": "ورود", "id": "ورود"},
                            {"name": "TP", "id": "TP"},
                            {"name": "SL", "id": "SL"},
                            {"name": "خروج", "id": "خروج"},
                            {"name": "PnL", "id": "PnL"},
                            {"name": "سرمایه", "id": "سرمایه"},
                            {"name": "دلیل", "id": "دلیل"},
                        ],
                        style_table={"overflowX": "auto", "backgroundColor": BG},
                        style_header={"backgroundColor": CARD, "color": NEON_CYAN, "fontWeight": "bold",
                                      "border": f"1px solid {LINE}", "textAlign": "center"},
                        style_cell={"backgroundColor": BG, "color": TXT, "border": f"1px solid {LINE}",
                                    "textAlign": "center", "fontFamily": "Tahoma, Arial"},
                    )
                ], style={"background": BG, "border": f"1px solid {LINE}"}),
            ]),
        ]),

        dcc.Interval(id="tick", interval=60_000, n_intervals=0),

    ], fluid=True, style={"maxWidth": "1300px"})
], style={"background": BG, "minHeight": "100vh", "padding": "20px", "fontFamily": "Tahoma, Arial"})


# ==============================================================================
# 9) Callbacks
# ==============================================================================
@app.callback(
    Output("radar-graph", "figure"),
    Output("stat-live", "children"),
    Output("stat-pred", "children"),
    Output("stat-mirror", "children"),
    Input("tick", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    State("symbol", "value"),
    State("interval", "value"),
    State("forecast-hours", "value"),
)
def update_dashboard(_n, _click, symbol, interval, forecast_hours):
    symbol = (symbol or DEFAULT_SYMBOL).upper().strip()
    interval = interval or DEFAULT_INTERVAL
    forecast_hours = float(forecast_hours or DEFAULT_FORECAST_HOURS)

    now_utc = get_server_time()
    df = get_klines(symbol, interval, limit=1000)

    if df.empty:
        return empty_fig("دریافت داده ناموفق بود..."), "---", "---", "---"

    fig, stats = build_advanced_clock(df, now_utc, symbol, interval, forecast_hours)

    stat_live = f"${stats['live']:.2f}"
    stat_pred = f"${stats['pred']:.2f} ({stats['trend']})"
    stat_mirror = f"${stats['mirror']:.2f}"

    return fig, stat_live, stat_pred, stat_mirror


@app.callback(
    # Path tab
    Output("path-total-value", "children"),
    Output("path-qualified-value", "children"),
    Output("path-wr-value", "children"),
    Output("trade-wr-value", "children"),
    Output("gauge-path-wr", "figure"),
    Output("gauge-trade-wr", "figure"),
    Output("gauge-confidence", "figure"),
    Output("path-table", "data"),

    # Capital tab
    Output("cap-final-value", "children"),
    Output("cap-growth-value", "children"),
    Output("cap-maxdd-value", "children"),
    Output("cap-pf-value", "children"),
    Output("cap-trades-value", "children"),
    Output("equity-graph", "figure"),
    Output("trades-table", "data"),

    Input("tick", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    State("symbol", "value"),
    State("interval", "value"),
    State("path-lookforward", "value"),
    State("min-confidence", "value"),
    State("auto-threshold", "value"),
    State("min-rr", "value"),
    State("initial-capital", "value"),
    State("risk-per-trade", "value"),
)
def update_analytics(
        _n,
        _click,
        symbol,
        interval,
        lookforward,
        min_confidence,
        auto_threshold,
        min_rr,
        initial_capital,
        risk_per_trade
):
    symbol = (symbol or DEFAULT_SYMBOL).upper().strip()
    interval = interval or DEFAULT_INTERVAL

    try:
        lookforward = int(lookforward or 12)
        min_confidence = float(min_confidence or 50)
        min_rr = float(min_rr or 0.7)
        initial_capital = float(initial_capital or 500)
        risk_per_trade = float(risk_per_trade or 2)
    except Exception:
        lookforward, min_confidence, min_rr, initial_capital, risk_per_trade = 12, 50, 0.7, 500, 2

    auto_thr = (auto_threshold == "yes")

    df = get_klines(symbol, interval, limit=1000)
    macro1 = prepare_macro_df(symbol, "60", 500)
    macro4 = prepare_macro_df(symbol, "240", 500)

    empty_g = build_gauge(0, "داده کافی نیست", NEON_RED)
    empty_equity = empty_fig("داده کافی برای رشد سرمایه نیست")

    if df.empty or len(df) < FIT_LOOKBACK + lookforward + 10:
        return (
            "—", "—", "—", "—",
            empty_g, empty_g, empty_g, [],
            "—", "—", "—", "—", "—",
            empty_equity, []
        )

    res = run_full_analytics(
        df=df,
        macro1=macro1,
        macro4=macro4,
        interval=interval,
        lookforward=lookforward,
        min_confidence=min_confidence,
        auto_threshold=auto_thr,
        min_rr=min_rr,
        initial_capital=initial_capital,
        risk_pct=risk_per_trade,
    )

    # Path table
    path_data = []
    for r in res["rows"][-120:][::-1]:
        path_data.append({
            "زمان": r["time"].strftime("%m-%d %H:%M"),
            "قیمت": f"{r['current_price']:.2f}",
            "جهت": "⬆️ صعودی" if r["direction"] > 0 else "⬇️ نزولی",
            "پایان پیش‌بینی": f"{r['pred_end']:.2f}",
            "پایان واقعی": f"{r['actual_end']:.2f}",
            "نتیجه مسیر": "✅ درست" if r["endpoint_win"] == 1 else "❌ غلط",
            "اعتماد": f"{r['confidence']:.1f}",
            "آستانه": f"{r['threshold']:.1f}",
            "وضعیت": "⭐ واجد شرایط" if r["qualified"] else "—",
        })

    # Capital stats
    final_equity = res["final_equity"]
    growth_pct = res["growth_pct"]
    max_dd = res["max_drawdown_pct"]
    pf = res["profit_factor"]
    pf_text = "∞" if pf == float("inf") else f"{pf:.2f}"

    growth_color = NEON_GREEN if growth_pct >= 0 else NEON_RED

    # Trades table
    trade_data = []
    for t in res["trades"][-120:][::-1]:
        trade_data.append({
            "زمان": t["time"].strftime("%m-%d %H:%M"),
            "جهت": "🟢 Long" if t["direction"] > 0 else "🔴 Short",
            "ورود": f"{t['entry']:.2f}",
            "TP": f"{t['tp']:.2f}",
            "SL": f"{t['sl']:.2f}",
            "خروج": f"{t['exit']:.2f}",
            "PnL": f"{t['pnl']:+.2f}",
            "سرمایه": f"{t['equity']:.2f}",
            "دلیل": t["reason"],
        })

    equity_fig = build_equity_fig(res["equity_curve"], initial_capital)

    return (
        str(res["total_paths"]),
        str(res["qualified_paths"]),
        f"{res['path_wr_qualified']:.1f}%",
        f"{res['trade_win_rate']:.1f}%",

        build_gauge(res["path_wr_qualified"], "وین‌ریت مسیر واجد شرایط",
                    NEON_CYAN if res["path_wr_qualified"] >= 50 else NEON_RED),
        build_gauge(res["trade_win_rate"], "وین‌ریت معاملات",
                    NEON_GREEN if res["trade_win_rate"] >= 50 else NEON_RED),
        build_gauge(res["avg_confidence_qualified"], "میانگین اعتماد سیگنال‌ها",
                    NEON_GOLD if res["avg_confidence_qualified"] >= 50 else NEON_RED),

        path_data,

        f"${final_equity:.2f}",
        f"{growth_pct:+.2f}%",
        f"{max_dd:.1f}%",
        pf_text,
        str(len(res["trades"])),

        equity_fig,
        trade_data,
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8060, use_reloader=False)