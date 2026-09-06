
# -*- coding: utf-8 -*-
"""
⏳ Chrono-Clock Pro v2 — ابزار فوق‌پیشرفته پیش‌بینی قیمت مبتنی بر چرخه‌های زمانی
================================================================================
{Morindok}

ارتقاهای این نسخه نسبت به نسخه قبل:
  ۱. موتور فوریه با پنجره‌ی Hann (کاهش نشت طیفی / Spectral Leakage) → تشخیص دقیق‌تر چرخه‌ها.
  ۲. مدل آنسمبل هوشمند: وزن‌دهی پویا به سه مدل (فوریه/مومنتوم/خطی) بر اساس خطای
     واک‌فوروارد (Walk-Forward Backtest) روی همان دیتای اخیر — دقیقاً همان فرهنگ
     اعتبارسنجی که مرتضی روی آن‌ها کار می‌کند.
  ۳. نمایش هم‌زمان حلقه‌ی هر مدل (اختیاری) برای مقایسه‌ی بصری مستقیم مدل‌ها.
  ۴. باند اطمینان دوگانه: ATR-based CI + پراکندگی تاریخی خطای چرخه (Cycle Residual Std).
  ۵. گیج «قدرت چرخه» و گیج «نوسان‌پذیری (ATR%)» به‌صورت Indicator های شیشه‌ای.
  ۶. پنل اطلاعاتی زنده: قیمت لایو، پیش‌بینی افق، دقت مدل غالب، سشن فعال.
  ۷. طراحی بصری: دایل شیشه‌ای با گرادیان شعاعی، خطوط دقیقه‌ای ریز، افکت درخشش (glow)
     روی عقربه‌ها و ستاره‌ی لایو، فونت Vazirmatn، کارت‌های گلس‌مورفیسم.
"""

import math
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import dash
from dash import dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc

# ==============================================================================
# 0) پالت رنگی و تنظیمات پیش‌فرض
# ==============================================================================
BG = "#070b14"
CARD = "#0f1830"
CARD2 = "#101c38"
LINE = "#22304e"
TXT = "#eef2fb"
MUT = "#8ea0c4"
GOLD = "#f3ba2f"
GOLD_DIM = "#8a6b1f"
UP = "#1fd7a6"
DN = "#ff5d6c"
BLUE = "#4f8dfd"
PURPLE = "#b57bf0"
HAND_CW_CLR = "#ffffff"
HAND_CCW_CLR = "#ff5d6c"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_CATEGORY = "linear"
DEFAULT_INTERVAL = "15"
DEFAULT_FORECAST_HOURS = 6
N_BINS = 288  # وضوح حلقه‌ی قیمت (هر بین ≈ ۲.۵ دقیقه از یک دور ۱۲ ساعته)
BACKTEST_STEPS = 24     # تعداد کندل‌های نگه‌داشته‌شده برای واک‌فوروارد
BACKTEST_MIN_HISTORY = 60

FONT_FAMILY = "Vazirmatn, Tahoma, Arial, sans-serif"

MODEL_COLORS = {
    "fourier": BLUE,
    "momentum": PURPLE,
    "linear": MUT,
    "ensemble": GOLD,
}
MODEL_LABEL_FA = {
    "fourier": "فوریه (چرخه‌ها)",
    "momentum": "مومنتوم (EMA)",
    "linear": "روند خطی",
    "ensemble": "آنسمبل هوشمند",
}

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
        return 15


# ==============================================================================
# 2) نگاشت زمان → زاویه‌ی صفحه‌ی ساعت (۱۲ ساعته)
# ==============================================================================
def hour_frac_12(dt_utc):
    return (dt_utc.hour % 12) + dt_utc.minute / 60.0 + dt_utc.second / 3600.0


def hour_frac_to_theta_cw(hf):
    return (90.0 - 30.0 * hf) % 360.0


def hour_frac_to_theta_ccw(hf):
    return (90.0 + 30.0 * hf) % 360.0


def hour_frac_to_clockstr(hf):
    total_min = hf * 60.0
    hh = int(total_min // 60)
    mm = int(round(total_min % 60))
    if mm == 60:
        mm = 0
        hh += 1
    hh = hh % 12
    if hh == 0:
        hh = 12
    return f"{hh:02d}:{mm:02d}"


# ==============================================================================
# 2.b) موتور ساده و آبستره حمایت/مقاومت (یک سطح حمایت + یک سطح مقاومت)
# ==============================================================================
def find_swing_points(highs, lows, order=5):
    """سویینگ‌های ساختاری (Fractal Pivots): یک های/لو که از order کندل قبل و بعدش بالاتر/پایین‌تره."""
    n = len(highs)
    swing_highs, swing_lows = [], []
    for i in range(order, n - order):
        window_h = highs[i - order:i + order + 1]
        if highs[i] == window_h.max():
            swing_highs.append(highs[i])
        window_l = lows[i - order:i + order + 1]
        if lows[i] == window_l.min():
            swing_lows.append(lows[i])
    return swing_highs, swing_lows


def compute_support_resistance(df, live_price, lookback=200, order=5):
    """
    خروجی آبستره و ساده: فقط یک سطح حمایت و یک سطح مقاومت.
    منطق: نزدیک‌ترین سویینگ ساختاری (Fractal Pivot) بالای قیمت لایو = مقاومت،
    نزدیک‌ترین سویینگ پایین قیمت لایو = حمایت. اگر سویینگی یافت نشد، از سقف/کف
    بازه‌ی اخیر استفاده می‌شود.
    """
    d = df.tail(lookback).reset_index(drop=True)
    highs = d["high"].values
    lows = d["low"].values

    swing_highs, swing_lows = find_swing_points(highs, lows, order=order)

    res_candidates = [p for p in swing_highs if p > live_price]
    sup_candidates = [p for p in swing_lows if p < live_price]

    resistance = min(res_candidates) if res_candidates else float(highs.max())
    support = max(sup_candidates) if sup_candidates else float(lows.min())

    # اطمینان از منطقی بودن سطوح نسبت به قیمت لایو
    if resistance <= live_price:
        resistance = float(highs.max())
        if resistance <= live_price:
            resistance = live_price * 1.01
    if support >= live_price:
        support = float(lows.min())
        if support >= live_price:
            support = live_price * 0.99

    res_dist_pct = (resistance - live_price) / live_price * 100 if live_price else 0.0
    sup_dist_pct = (live_price - support) / live_price * 100 if live_price else 0.0
    range_pct = (resistance - support) / live_price * 100 if live_price else 0.0

    return {
        "support": support,
        "resistance": resistance,
        "live": live_price,
        "res_dist_pct": res_dist_pct,
        "sup_dist_pct": sup_dist_pct,
        "range_pct": range_pct,
    }


# ==============================================================================
# 2.c) موتور علمی زمان‌سنج چندمنظوره
#      الف) حمایت/مقاومت زمانی (خوشه‌بندی ساعتی سویینگ‌ها + تست جایگشتی واقعی)
#      ب)  چرخ‌دنده‌های زمانی چندگانه (چند-هارمونیک فوریه + تست معناداری آماری)
# ==============================================================================
def find_swing_idx(highs, lows, order=3):
    """مثل find_swing_points ولی به‌جای مقدار، ایندکس سویینگ‌ها را برمی‌گرداند."""
    n = len(highs)
    sh, sl = [], []
    for i in range(order, n - order):
        wh = highs[i - order:i + order + 1]
        if highs[i] == wh.max():
            sh.append(i)
        wl = lows[i - order:i + order + 1]
        if lows[i] == wl.min():
            sl.append(i)
    return sh, sl


def next_occurrence_of_hour(target_hour_frac_24, now_utc):
    """نزدیک‌ترین زمان آینده (امروز یا فردا) که ساعت UTC آن برابر target_hour_frac_24 باشد."""
    hh = int(target_hour_frac_24)
    mm = int(round((target_hour_frac_24 - hh) * 60))
    if mm == 60:
        mm = 0
        hh = (hh + 1) % 24
    candidate = now_utc.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if candidate <= now_utc:
        candidate += timedelta(days=1)
    return candidate


def compute_time_based_sr(df, now_utc, order=3, n_bins=24, n_perm=400, random_state=42,
                           min_swings=5):
    """
    حمایت/مقاومت زمانی: برای هر سویینگ ساختاری (فرکتال) ساعت وقوعش (UTC) ثبت می‌شود.
    ساعتی که بیشترین تراکم کف‌ها را دارد → «حمایت زمانی»، بیشترین تراکم سقف‌ها → «مقاومت زمانی».
    معناداری آماری با تست جایگشتی (Permutation Test) سنجیده می‌شود: ساعت‌های سویینگ‌ها هزاران
    بار به‌صورت تصادفی بازچینش می‌شوند تا توزیع تهی (Null Distribution) بیشینه‌ی تراکم ساخته شود؛
    p-value = نسبت جایگشت‌هایی که تراکم تصادفی‌شان به تراکم واقعی می‌رسد یا از آن بیشتر است.
    """
    d = df.reset_index(drop=True).copy()
    n = len(d)
    if n < order * 2 + 20:
        return None

    highs = d["high"].values
    lows = d["low"].values
    opens = d["open"].values
    ts = pd.to_datetime(d["ts"])
    hours = (ts.dt.hour + ts.dt.minute / 60.0).values
    d["_date"] = ts.dt.date
    day_open = d.groupby("_date")["open"].transform("first").values

    sh_idx, sl_idx = find_swing_idx(highs, lows, order=order)
    if len(sh_idx) < min_swings or len(sl_idx) < min_swings:
        return None

    def bin_of(h):
        return int(h / 24.0 * n_bins) % n_bins

    high_bins = np.array([bin_of(hours[i]) for i in sh_idx])
    low_bins = np.array([bin_of(hours[i]) for i in sl_idx])

    high_counts = np.bincount(high_bins, minlength=n_bins)
    low_counts = np.bincount(low_bins, minlength=n_bins)

    res_bin = int(np.argmax(high_counts))
    sup_bin = int(np.argmax(low_counts))
    obs_high_max = int(high_counts[res_bin])
    obs_low_max = int(low_counts[sup_bin])

    rng = np.random.default_rng(random_state)
    n_high, n_low = len(sh_idx), len(sl_idx)
    null_high_max = np.empty(n_perm)
    null_low_max = np.empty(n_perm)
    for i in range(n_perm):
        null_high_max[i] = np.bincount(rng.integers(0, n_bins, n_high), minlength=n_bins).max()
        null_low_max[i] = np.bincount(rng.integers(0, n_bins, n_low), minlength=n_bins).max()

    p_high = float((null_high_max >= obs_high_max).mean())
    p_low = float((null_low_max >= obs_low_max).mean())

    dev_high = (highs[sh_idx] - day_open[sh_idx]) / day_open[sh_idx] * 100.0
    dev_low = (lows[sl_idx] - day_open[sl_idx]) / day_open[sl_idx] * 100.0

    res_dev = float(np.median(dev_high[high_bins == res_bin]))
    sup_dev = float(np.median(dev_low[low_bins == sup_bin]))

    today_open = float(day_open[-1])
    resistance_price = today_open * (1 + res_dev / 100.0)
    support_price = today_open * (1 + sup_dev / 100.0)

    res_hour24 = res_bin / n_bins * 24.0
    sup_hour24 = sup_bin / n_bins * 24.0

    return {
        "resistance": {
            "hour_utc": res_hour24,
            "clock12": hour_frac_to_clockstr(res_hour24 % 12),
            "count": obs_high_max,
            "total": n_high,
            "p_value": p_high,
            "significant": p_high < 0.05,
            "price": resistance_price,
            "next_time": next_occurrence_of_hour(res_hour24, now_utc),
        },
        "support": {
            "hour_utc": sup_hour24,
            "clock12": hour_frac_to_clockstr(sup_hour24 % 12),
            "count": obs_low_max,
            "total": n_low,
            "p_value": p_low,
            "significant": p_low < 0.05,
            "price": support_price,
            "next_time": next_occurrence_of_hour(sup_hour24, now_utc),
        },
    }


def multi_cycle_table(df, interval_min, now_utc, n_harmonics=5, n_perm=300, random_state=7):
    """
    چرخ‌دنده‌های زمانی چندگانه: تجزیه‌ی فوریه (با پنجره Hann) به چند هارمونیک برتر.
    برای هر هارمونیک: دوره‌ی تناوب، درصد قدرت از کل طیف، و p-value با تست جایگشتی
    (بازچینش تصادفی سری زمانی و مقایسه‌ی بیشینه‌ی طیف حاصل با طیف واقعی — کنترل خطای
    چندگانه به‌صورت ذاتی چون بیشینه روی کل طیف گرفته می‌شود، نه فقط فرکانس هدف).
    """
    closes = df["close"].values
    n = len(closes)
    if n < 30:
        return []

    x = np.arange(n)
    p = np.polyfit(x, closes, 1)
    trend = np.polyval(p, x)
    y_detrend = closes - trend

    win = np.hanning(n)
    win_sum = win.sum() if win.sum() > 0 else n

    fft = np.fft.fft(y_detrend * win)
    freqs = np.fft.fftfreq(n, d=1)
    mags = np.abs(fft)
    mags[0] = 0.0
    half = n // 2
    pos_idx = np.arange(1, half)
    mags_pos = mags[pos_idx]

    n_harmonics = max(1, int(n_harmonics))
    order_sorted = np.argsort(mags_pos)[::-1][:n_harmonics]
    top_indices = pos_idx[order_sorted]

    total_power = float(np.sum(mags[1:half] ** 2))

    rng = np.random.default_rng(random_state)
    null_max = np.empty(n_perm)
    for i in range(n_perm):
        shuffled = rng.permutation(y_detrend)
        f2 = np.fft.fft(shuffled * win)
        null_max[i] = np.abs(f2)[pos_idx].max()

    last_ts = pd.Timestamp(df.iloc[-1]["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)
    rows = []
    for idx in top_indices:
        freq = freqs[idx]
        if freq == 0:
            continue
        period_bars = 1.0 / abs(freq)
        period_hours = period_bars * interval_min / 60.0
        amp = 2.0 * mags[idx] / win_sum
        phase = np.angle(fft[idx])
        power_pct = float(mags[idx] ** 2 / total_power * 100.0) if total_power > 0 else 0.0
        p_val = float((null_max >= mags[idx]).mean())

        theta_now = 2 * np.pi * freq * n + phase
        theta_prev = 2 * np.pi * freq * (n - 1) + phase
        rising = bool(np.cos(theta_now) > np.cos(theta_prev))

        search_bars = max(period_bars, 4.0)
        xs = np.arange(n, n + search_bars + 1, max(search_bars / 300.0, 0.05))
        vals = np.cos(2 * np.pi * freq * xs + phase)
        peak_x = xs[int(np.argmax(vals))]
        trough_x = xs[int(np.argmin(vals))]
        peak_time = last_ts + timedelta(minutes=interval_min * float(peak_x - n))
        trough_time = last_ts + timedelta(minutes=interval_min * float(trough_x - n))

        rows.append({
            "period_hours": period_hours,
            "amplitude": amp,
            "power_pct": power_pct,
            "p_value": p_val,
            "significant": p_val < 0.05,
            "rising": rising,
            "next_peak": peak_time,
            "next_trough": trough_time,
        })

    rows.sort(key=lambda r: r["power_pct"], reverse=True)
    return rows


# ==============================================================================
# 3) موتور پیش‌بینی فوق‌پیشرفته (FFT با پنجره Hann + Ensemble پویا)
# ==============================================================================
def fourier_forecast(closes, steps, n_harmonics=3, window=True):
    """پیش‌بینی مبتنی بر برون‌یابی چرخه‌های غالب فوریه، با پنجره‌ی Hann برای دقت طیفی بالاتر."""
    n = len(closes)
    if n < 10:
        return np.full(steps, closes[-1] if n else 0.0), 0.0

    x = np.arange(n)
    p = np.polyfit(x, closes, 1)
    trend = np.polyval(p, x)
    y_detrend = closes - trend

    win = np.hanning(n) if window else np.ones(n)
    win_sum = np.sum(win) if np.sum(win) > 0 else n

    fft = np.fft.fft(y_detrend * win)
    freqs = np.fft.fftfreq(n, d=1)
    magnitudes = np.abs(fft)
    magnitudes[0] = 0.0  # حذف مولفه DC

    n_harmonics = max(1, int(n_harmonics))
    top_indices = np.argsort(magnitudes)[::-1][:n_harmonics]
    total_power = np.sum(magnitudes[: n // 2] ** 2)
    top_power = np.sum(magnitudes[top_indices] ** 2)
    strength = float((top_power / total_power) * 100) if total_power > 0 else 0.0
    strength = min(strength, 100.0)

    x_ext = np.arange(n, n + steps)
    trend_ext = np.polyval(p, x_ext)
    cyc_ext = np.zeros(steps)

    for idx in top_indices:
        if idx == 0:
            continue
        freq = freqs[idx]
        amp = 2.0 * magnitudes[idx] / win_sum
        phase = np.angle(fft[idx])
        cyc_ext += amp * np.cos(2 * np.pi * freq * x_ext + phase)

    return trend_ext + cyc_ext, strength


def momentum_forecast(closes, steps):
    ema = pd.Series(closes).ewm(span=20, adjust=False).mean().values
    slope = (ema[-1] - ema[-10]) / 10 if len(ema) >= 10 else 0.0
    return closes[-1] + slope * np.arange(1, steps + 1)


def linear_forecast(closes, steps):
    n = len(closes)
    x = np.arange(n)
    p = np.polyfit(x, closes, 1)
    x_ext = np.arange(n, n + steps)
    return np.polyval(p, x_ext)


def compute_all_forecasts(closes, steps, n_harmonics):
    """خروجی: دیکشنری {model_name: pred_array}, و قدرت چرخه فوریه."""
    fourier_pred, strength = fourier_forecast(closes, steps, n_harmonics)
    preds = {
        "fourier": fourier_pred,
        "momentum": momentum_forecast(closes, steps),
        "linear": linear_forecast(closes, steps),
    }
    return preds, strength


def walk_forward_weights(closes, n_harmonics, test_steps=BACKTEST_STEPS):
    """
    اعتبارسنجی واک‌فوروارد ساده: آخرین test_steps کندل کنار گذاشته می‌شود،
    هر مدل روی داده‌ی قبل از آن آموزش (فیت) و به جلو پیش‌بینی می‌شود، سپس با
    مقادیر واقعی مقایسه می‌شود. وزن نهایی هر مدل متناسب با معکوس خطا (MAE) است.
    """
    n = len(closes)
    if n < BACKTEST_MIN_HISTORY + test_steps:
        # داده کافی برای بک‌تست نیست → وزن مساوی
        return {"fourier": 1 / 3, "momentum": 1 / 3, "linear": 1 / 3}, None

    train = closes[: n - test_steps]
    actual = closes[n - test_steps:]

    fpred, _ = fourier_forecast(train, test_steps, n_harmonics)
    mpred = momentum_forecast(train, test_steps)
    lpred = linear_forecast(train, test_steps)

    errors = {
        "fourier": float(np.mean(np.abs(fpred - actual))),
        "momentum": float(np.mean(np.abs(mpred - actual))),
        "linear": float(np.mean(np.abs(lpred - actual))),
    }
    # جلوگیری از تقسیم بر صفر
    inv = {k: 1.0 / max(v, 1e-9) for k, v in errors.items()}
    total = sum(inv.values())
    weights = {k: v / total for k, v in inv.items()}
    return weights, errors


def build_price_ring_advanced(df, now_utc, forecast_hours, interval_min,
                               model_type="ensemble", n_harmonics=3, n_bins=N_BINS):
    bin_price_hist = np.full(n_bins, np.nan)
    bin_ts_hist = [None] * n_bins

    # --- تاریخی: نگاشت قیمت‌های گذشته روی حلقه ساعت ---
    for _, row in df.iterrows():
        ts = pd.Timestamp(row["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)
        hf = hour_frac_12(ts)
        idx = int(hf / 12.0 * n_bins) % n_bins
        if bin_ts_hist[idx] is None or ts > bin_ts_hist[idx]:
            bin_ts_hist[idx] = ts
            bin_price_hist[idx] = float(row["close"])

    steps = max(int((forecast_hours * 60.0) / max(interval_min, 1)), 1)
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values

    # --- ATR برای بازه اطمینان (Confidence Interval) ---
    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - np.roll(closes, 1)),
                                              np.abs(lows - np.roll(closes, 1))))
    tr[0] = highs[0] - lows[0]
    atr = pd.Series(tr).rolling(window=14, min_periods=1).mean().values
    current_atr = atr[-1]
    time_multipliers = np.sqrt(np.arange(1, steps + 1))
    ci_width = current_atr * time_multipliers * 1.5  # پوشش تقریبی ۹۰٪ نوسانات

    # --- تمام مدل‌ها + وزن‌های آنسمبل بر اساس واک‌فوروارد ---
    all_preds, strength = compute_all_forecasts(closes, steps, n_harmonics)
    weights, backtest_errors = walk_forward_weights(closes, n_harmonics)

    ensemble_pred = (
        weights["fourier"] * all_preds["fourier"]
        + weights["momentum"] * all_preds["momentum"]
        + weights["linear"] * all_preds["linear"]
    )
    all_preds["ensemble"] = ensemble_pred

    pred_prices = all_preds.get(model_type, ensemble_pred)

    # --- نگاشت پیش‌بینی‌ها روی بین‌های ساعت (برای هر مدل، برای اورلی مقایسه‌ای) ---
    last_ts = pd.Timestamp(df.iloc[-1]["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)

    def map_to_bins(pred_arr):
        bp = np.full(n_bins, np.nan)
        used = set()
        for s in range(steps):
            t_future = last_ts + timedelta(minutes=interval_min * (s + 1))
            hf = hour_frac_12(t_future)
            idx = int(hf / 12.0 * n_bins) % n_bins
            bp[idx] = pred_arr[s]
            used.add(idx)
        return bp, used

    bin_price_fut, fut_bins = map_to_bins(pred_prices)
    bin_ci_upper = np.full(n_bins, np.nan)
    bin_ci_lower = np.full(n_bins, np.nan)
    for s in range(steps):
        t_future = last_ts + timedelta(minutes=interval_min * (s + 1))
        hf = hour_frac_12(t_future)
        idx = int(hf / 12.0 * n_bins) % n_bins
        bin_ci_upper[idx] = pred_prices[s] + ci_width[s]
        bin_ci_lower[idx] = pred_prices[s] - ci_width[s]

    other_model_bins = {}
    for m_name, m_pred in all_preds.items():
        if m_name == model_type:
            continue
        bp, _ = map_to_bins(m_pred)
        other_model_bins[m_name] = bp

    final_price = bin_price_hist.copy()
    status = np.array(["past"] * n_bins, dtype=object)
    for idx in fut_bins:
        final_price[idx] = bin_price_fut[idx]
        status[idx] = "future"

    # --- درون‌یابی شکاف‌های خالی (حلقوی) ---
    nanmask = np.isnan(final_price)
    valid_count = (~nanmask).sum()
    if valid_count >= 2:
        idxs = np.arange(n_bins)
        ext_price = np.concatenate([final_price, final_price, final_price])
        ext_idx = np.concatenate([idxs - n_bins, idxs, idxs + n_bins])
        ext_valid = ~np.isnan(ext_price)
        filled = np.interp(idxs + n_bins, ext_idx[ext_valid], ext_price[ext_valid])
        final_price[nanmask] = filled[nanmask]
        status[nanmask & (status == "past")] = "interp"
    elif valid_count == 1:
        only_val = final_price[~nanmask][0]
        final_price[nanmask] = only_val
        status[nanmask] = "interp"
    else:
        fallback = float(df.iloc[-1]["close"]) if len(df) else 0.0
        final_price[:] = fallback
        status[:] = "interp"

    hour_fracs = np.arange(n_bins) / n_bins * 12.0
    thetas = np.array([hour_frac_to_theta_cw(hf) for hf in hour_fracs])

    meta = {
        "weights": weights,
        "backtest_errors": backtest_errors,
        "pred_prices": pred_prices,
        "ci_width": ci_width,
        "current_atr": current_atr,
        "other_model_bins": other_model_bins,
        "hour_fracs": hour_fracs,
        "thetas": thetas,
        "steps": steps,
    }
    return thetas, hour_fracs, final_price, status, bin_ci_upper, bin_ci_lower, strength, meta


# ==============================================================================
# 4) ساخت شکل (Figure) ساعت قیمت
# ==============================================================================
STATUS_FA = {"past": "داده تاریخی", "future": "پیش‌بینی", "interp": "درون‌یابی"}
STATUS_SYMBOL = {"past": "circle", "future": "diamond", "interp": "circle-open"}


def empty_fig(msg):
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        font=dict(family=FONT_FAMILY),
    )
    fig.add_annotation(x=0.5, y=0.5, xref="paper", yref="paper", text=msg,
                        showarrow=False, font=dict(size=16, color=DN, family=FONT_FAMILY))
    return fig


def _glow_line(fig, x, y, color, width, dash=None, name=None, opacity_core=1.0):
    """شبیه‌سازی افکت درخشش (glow) با چند لایه‌ی نیمه‌شفاف پشت خط اصلی."""
    for w, op in [(width + 10, 0.05), (width + 5, 0.10)]:
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="lines",
            line=dict(color=color, width=w, dash=dash),
            opacity=op, hoverinfo="skip", showlegend=False,
        ))
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines",
        line=dict(color=color, width=width, dash=dash),
        opacity=opacity_core, hoverinfo="skip" if name is None else None,
        showlegend=name is not None, name=name,
    ))


def build_clock_figure(df, now_utc, symbol, interval, forecast_hours, model_type,
                        n_harmonics, show_ci, show_all_models):
    if df.empty or len(df) < 8:
        return empty_fig("داده‌ی کافی از بایبیت دریافت نشد."), {}

    interval_min = get_interval_minutes(interval)
    thetas, hour_fracs, prices, status, bin_ci_upper, bin_ci_lower, strength, meta = \
        build_price_ring_advanced(df, now_utc, forecast_hours, interval_min, model_type, n_harmonics)

    R = 1.0
    live_price = float(df.iloc[-1]["close"])
    hf_now = hour_frac_12(now_utc)
    theta_cw = hour_frac_to_theta_cw(hf_now)
    theta_ccw = hour_frac_to_theta_ccw(hf_now)

    fig = go.Figure()

    # --- گرادیان شعاعی شبیه‌سازی‌شده برای پس‌زمینه‌ی دایل شیشه‌ای ---
    for i, (rad, op) in enumerate([(1.0, 0.05), (0.75, 0.05), (0.5, 0.06), (0.25, 0.07)]):
        ang_full = np.linspace(0, 360, 121)
        fig.add_trace(go.Scatter(
            x=rad * R * np.cos(np.radians(ang_full)), y=rad * R * np.sin(np.radians(ang_full)),
            mode="lines", fill="toself", fillcolor=f"rgba(79,141,253,{op})",
            line=dict(color="rgba(0,0,0,0)"), hoverinfo="skip", showlegend=False,
        ))

    # --- محیط دایره‌ی ساعت ---
    ang_full = np.linspace(0, 360, 361)
    fig.add_trace(go.Scatter(
        x=R * np.cos(np.radians(ang_full)), y=R * np.sin(np.radians(ang_full)),
        mode="lines", line=dict(color=LINE, width=2),
        showlegend=False, hoverinfo="skip",
    ))

    # --- خطوط دقیقه‌ای ریز (هر ۱۵ دقیقه از هر ساعت) ---
    for h in range(12):
        for m in (15, 30, 45):
            hf_tick = h + m / 60.0
            theta = hour_frac_to_theta_cw(hf_tick)
            c, s = np.cos(np.radians(theta)), np.sin(np.radians(theta))
            fig.add_trace(go.Scatter(
                x=[0.965 * R * c, R * c], y=[0.965 * R * s, R * s],
                mode="lines", line=dict(color=LINE, width=1),
                hoverinfo="skip", showlegend=False,
            ))

    # --- خطوط شعاعی و اعداد ۱ تا ۱۲ ---
    for h in range(1, 13):
        theta = (90 - 30 * h) % 360
        c, s = np.cos(np.radians(theta)), np.sin(np.radians(theta))
        fig.add_trace(go.Scatter(
            x=[0.90 * R * c, R * c], y=[0.90 * R * s, R * s],
            mode="lines", line=dict(color=GOLD, width=2),
            hoverinfo="skip", showlegend=False,
        ))
        fig.add_annotation(x=1.11 * R * c, y=1.11 * R * s, text=f"<b>{h}</b>",
                            showarrow=False, font=dict(size=14, color=GOLD, family=FONT_FAMILY))

    # --- اورلی مقایسه‌ای سایر مدل‌ها (اختیاری) ---
    if show_all_models:
        for m_name, bp in meta["other_model_bins"].items():
            valid = ~np.isnan(bp)
            if valid.sum() < 2:
                continue
            hf_v = meta["hour_fracs"][valid]
            order = np.argsort(hf_v)
            th_v = meta["thetas"][valid][order]
            xs_m = 1.0 * R * np.cos(np.radians(th_v))
            ys_m = 1.0 * R * np.sin(np.radians(th_v))
            fig.add_trace(go.Scatter(
                x=xs_m, y=ys_m, mode="lines+markers",
                line=dict(color=MODEL_COLORS.get(m_name, MUT), width=1.5, dash="dash"),
                marker=dict(size=4, color=MODEL_COLORS.get(m_name, MUT)),
                opacity=0.55, name=f"مدل {MODEL_LABEL_FA.get(m_name, m_name)}",
                hovertemplate=f"{MODEL_LABEL_FA.get(m_name, m_name)}: %{{y:.4g}}<extra></extra>",
            ))

    # --- باندهای اطمینان (Confidence Intervals) ---
    valid_fut = ~np.isnan(bin_ci_upper)
    if valid_fut.sum() > 1 and show_ci:
        thetas_fut = thetas[valid_fut]
        hf_fut = hour_fracs[valid_fut]
        order = np.argsort(hf_fut)

        xs_upper = 1.08 * R * np.cos(np.radians(thetas_fut[order]))
        ys_upper = 1.08 * R * np.sin(np.radians(thetas_fut[order]))
        xs_lower = 0.92 * R * np.cos(np.radians(thetas_fut[order]))
        ys_lower = 0.92 * R * np.sin(np.radians(thetas_fut[order]))

        fig.add_trace(go.Scatter(
            x=xs_upper, y=ys_upper, mode="lines",
            line=dict(color=UP, width=4, dash="dot"),
            opacity=0.35, showlegend=True, name="حد بالای اطمینان (CI)", hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=xs_lower, y=ys_lower, mode="lines",
            line=dict(color=DN, width=4, dash="dot"),
            opacity=0.35, showlegend=True, name="حد پایین اطمینان (CI)", hoverinfo="skip",
        ))

    # --- نشانگرهای سشن‌های جهانی ---
    session_opens = {"آسیا 🌏": 0, "لندن 🌍": 7, "نیویورک 🌎": 13}
    for name, h in session_opens.items():
        hf = h % 12
        theta = hour_frac_to_theta_cw(hf)
        c, s = np.cos(np.radians(theta)), np.sin(np.radians(theta))
        fig.add_trace(go.Scatter(
            x=[1.16 * R * c], y=[1.16 * R * s], mode="markers+text",
            marker=dict(size=10, color=GOLD, symbol="diamond", line=dict(width=1, color="black")),
            text=[name], textposition="top center",
            textfont=dict(size=10, color=MUT, family=FONT_FAMILY),
            showlegend=False, hoverinfo="name", name=f"سشن {name}",
        ))

    # --- حلقه‌ی قیمت اصلی (رنگ = قیمت، شکل نشانگر = وضعیت) ---
    xs = R * np.cos(np.radians(thetas))
    ys = R * np.sin(np.radians(thetas))
    clock_labels = [hour_frac_to_clockstr(hf) for hf in hour_fracs]
    status_labels = [STATUS_FA[s] for s in status]
    symbols = [STATUS_SYMBOL[s] for s in status]

    customdata = np.column_stack([clock_labels, [f"{p:,.6g}" for p in prices], status_labels])

    order = np.argsort(-thetas)
    fig.add_trace(go.Scatter(
        x=np.append(xs[order], xs[order][0]), y=np.append(ys[order], ys[order][0]),
        mode="lines", line=dict(color=MUT, width=1), opacity=0.3,
        hoverinfo="skip", showlegend=False,
    ))

    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers",
        marker=dict(
            size=8.5, color=prices, colorscale="Turbo", symbol=symbols,
            showscale=True,
            colorbar=dict(title="قیمت", thickness=12, len=0.5, y=0.76,
                           tickfont=dict(color=TXT, size=10), title_font=dict(color=MUT, size=11)),
            line=dict(width=0.4, color="#000"),
        ),
        customdata=customdata,
        hovertemplate=(
            "⏱ ساعت: %{customdata[0]}<br>"
            "💰 قیمت: %{customdata[1]}<br>"
            "📌 %{customdata[2]}<extra></extra>"
        ),
        name="حلقه قیمت دور ساعت",
    ))

    # --- قیمت لایو (با افکت درخشش) ---
    lc, ls = np.cos(np.radians(theta_cw)), np.sin(np.radians(theta_cw))
    for size, op in [(34, 0.10), (26, 0.18)]:
        fig.add_trace(go.Scatter(
            x=[R * lc], y=[R * ls], mode="markers",
            marker=dict(size=size, symbol="star", color=GOLD),
            opacity=op, hoverinfo="skip", showlegend=False,
        ))
    fig.add_trace(go.Scatter(
        x=[R * lc], y=[R * ls], mode="markers+text",
        marker=dict(size=17, symbol="star", color=GOLD, line=dict(width=2, color="black")),
        text=[f"LIVE {live_price:,.4g}"], textposition="top center",
        textfont=dict(color=GOLD, size=13, family=FONT_FAMILY),
        name=f"قیمت لایو = {live_price:,.4g}",
    ))

    # --- عقربه‌ها (با افکت درخشش) ---
    _glow_line(fig, [0, 0.88 * R * lc], [0, 0.88 * R * ls], HAND_CW_CLR, 5,
               name="عقربه زمان واقعی (ساعت‌گرد)")
    mc, ms = np.cos(np.radians(theta_ccw)), np.sin(np.radians(theta_ccw))
    _glow_line(fig, [0, 0.72 * R * mc], [0, 0.72 * R * ms], HAND_CCW_CLR, 4, dash="dot",
               name="عقربه آینه‌ای (معکوس)")

    fig.add_trace(go.Scatter(
        x=[0], y=[0], mode="markers",
        marker=dict(size=13, color=TXT, line=dict(width=2, color=GOLD)),
        showlegend=False, hoverinfo="skip",
    ))

    # --- annotation قدرت چرخه ---
    fig.add_annotation(
        x=0.02, y=0.98, xref="paper", yref="paper",
        text=f"⚡ قدرت چرخه زمانی (فوریه): {strength:.1f}%",
        showarrow=False, font=dict(size=12, color=GOLD, family=FONT_FAMILY),
        bgcolor="rgba(15,24,48,0.85)", bordercolor=GOLD, borderwidth=1, borderpad=5,
        xanchor="left", yanchor="top",
    )

    h_now = now_utc.hour
    sessions = []
    if 0 <= h_now < 9:
        sessions.append("آسیا 🌏")
    if 7 <= h_now < 16:
        sessions.append("لندن 🌍")
    if 13 <= h_now < 22:
        sessions.append("نیویورک 🌎")
    curr_sess = " | ".join(sessions) if sessions else "خارج از سشن 🌑"

    fig.add_annotation(
        x=0.98, y=0.98, xref="paper", yref="paper",
        text=f"⏱ سشن فعال: {curr_sess}",
        showarrow=False, font=dict(size=12, color=UP, family=FONT_FAMILY),
        bgcolor="rgba(15,24,48,0.85)", bordercolor=UP, borderwidth=1, borderpad=5,
        xanchor="right", yanchor="top",
    )

    if model_type == "ensemble" and meta.get("weights"):
        w = meta["weights"]
        w_txt = (f"🧠 وزن مدل‌ها → فوریه {w['fourier']*100:.0f}% | "
                 f"مومنتوم {w['momentum']*100:.0f}% | خطی {w['linear']*100:.0f}%")
        fig.add_annotation(
            x=0.5, y=0.02, xref="paper", yref="paper",
            text=w_txt, showarrow=False,
            font=dict(size=11, color=TXT, family=FONT_FAMILY),
            bgcolor="rgba(15,24,48,0.85)", bordercolor=GOLD_DIM, borderwidth=1, borderpad=5,
            xanchor="center", yanchor="bottom",
        )

    lim = 1.38 * R
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        legend=dict(bgcolor="rgba(15,24,48,0.85)", bordercolor=LINE, borderwidth=1,
                    font=dict(size=10, color=TXT, family=FONT_FAMILY),
                    orientation="h", y=-0.05, x=0.5, xanchor="center"),
        margin=dict(l=10, r=10, t=60, b=10),
        title=dict(
            text=(f"⏳ Chrono-Clock Pro — {symbol} | {interval}m | "
                  f"مدل: {MODEL_LABEL_FA.get(model_type, model_type)} | "
                  f"{now_utc.strftime('%H:%M:%S')} UTC"),
            x=0.5, font=dict(color=GOLD, size=17, family=FONT_FAMILY),
        ),
        font=dict(family=FONT_FAMILY),
    )
    fig.update_xaxes(range=[-lim, lim], visible=False)
    fig.update_yaxes(range=[-lim, lim], visible=False, scaleanchor="x", scaleratio=1)
    return fig, meta


def build_gauges_figure(strength, current_atr, live_price, model_type, meta):
    atr_pct = (current_atr / live_price * 100) if live_price else 0.0

    if model_type == "ensemble" and meta.get("backtest_errors"):
        errs = meta["backtest_errors"]
        best_model = min(errs, key=errs.get)
        conf_label = f"مدل غالب: {MODEL_LABEL_FA.get(best_model, best_model)}"
    else:
        conf_label = MODEL_LABEL_FA.get(model_type, model_type)

    fig = make_subplots(
        rows=1, cols=2,
        specs=[[{"type": "indicator"}, {"type": "indicator"}]],
        horizontal_spacing=0.15,
    )
    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=strength,
        number={"suffix": "%", "font": {"color": GOLD, "size": 26, "family": FONT_FAMILY}},
        title={"text": "قدرت چرخه زمانی", "font": {"color": MUT, "size": 12, "family": FONT_FAMILY}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": MUT, "tickfont": {"color": MUT, "size": 9}},
            "bar": {"color": GOLD},
            "bgcolor": CARD2,
            "borderwidth": 0,
            "steps": [
                {"range": [0, 33], "color": "rgba(255,93,108,0.18)"},
                {"range": [33, 66], "color": "rgba(243,186,47,0.18)"},
                {"range": [66, 100], "color": "rgba(31,215,166,0.18)"},
            ],
        },
    ), row=1, col=1)

    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=atr_pct,
        number={"suffix": "%", "font": {"color": BLUE, "size": 26, "family": FONT_FAMILY}},
        title={"text": "نوسان‌پذیری لحظه‌ای (ATR%)", "font": {"color": MUT, "size": 12, "family": FONT_FAMILY}},
        gauge={
            "axis": {"range": [0, max(2.5, atr_pct * 1.6)], "tickcolor": MUT, "tickfont": {"color": MUT, "size": 9}},
            "bar": {"color": BLUE},
            "bgcolor": CARD2,
            "borderwidth": 0,
            "steps": [
                {"range": [0, max(2.5, atr_pct * 1.6) * 0.33], "color": "rgba(31,215,166,0.18)"},
                {"range": [max(2.5, atr_pct * 1.6) * 0.33, max(2.5, atr_pct * 1.6) * 0.66],
                 "color": "rgba(243,186,47,0.18)"},
                {"range": [max(2.5, atr_pct * 1.6) * 0.66, max(2.5, atr_pct * 1.6)],
                 "color": "rgba(255,93,108,0.18)"},
            ],
        },
    ), row=1, col=2)

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_FAMILY, color=TXT),
        margin=dict(l=20, r=20, t=40, b=10), height=210,
        annotations=[dict(
            text=conf_label, x=0.5, y=-0.18, xref="paper", yref="paper",
            showarrow=False, font=dict(size=11, color=MUT, family=FONT_FAMILY),
        )],
    )
    return fig


# ==============================================================================
# 5) اپ Dash
# ==============================================================================
FONT_URL = "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;800&display=swap"

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG, FONT_URL])
app.title = "Chrono-Clock Pro"
server = app.server

app.index_string = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            body { background: #070b14; }
            * { font-family: 'Vazirmatn', Tahoma, Arial, sans-serif !important; }
            .glass-card {
                background: linear-gradient(145deg, rgba(16,28,56,0.85), rgba(10,17,35,0.85));
                border: 1px solid #22304e;
                border-radius: 16px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.35);
                backdrop-filter: blur(6px);
            }
            .stat-value { font-weight: 800; font-size: 20px; }
            .stat-label { font-size: 11px; color: #8ea0c4; }
            .Select-control, .dash-dropdown .Select-control {
                background-color: #101c38 !important;
                border-color: #22304e !important;
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
</html>"""

CATEGORY_OPTS = [{"label": v, "value": v} for v in ["linear", "spot", "inverse"]]
INTERVAL_OPTS = [{"label": lbl, "value": val} for lbl, val in [
    ("1m", "1"), ("3m", "3"), ("5m", "5"), ("15m", "15"),
    ("30m", "30"), ("1h", "60"), ("4h", "240"),
]]
MODEL_OPTS = [
    {"label": "🧠 آنسمبل هوشمند (پیشنهادی)", "value": "ensemble"},
    {"label": "🌊 فوریه (چرخه‌ها)", "value": "fourier"},
    {"label": "🚀 مومنتوم (EMA)", "value": "momentum"},
    {"label": "📈 روند خطی", "value": "linear"},
]


def stat_card(id_prefix, label, color=TXT):
    return dbc.Col(
        html.Div([
            html.Div(label, className="stat-label"),
            html.Div("—", id=f"{id_prefix}-value", className="stat-value", style={"color": color}),
        ], className="glass-card", style={"padding": "12px 16px", "textAlign": "center"}),
        md=3, xs=6, style={"marginBottom": 10},
    )


def sr_row(label, price_id, dist_id, color):
    return html.Tr([
        html.Td(label, style={"color": MUT, "fontSize": 13, "padding": "10px 14px"}),
        html.Td(id=price_id, style={"color": color, "fontWeight": 800, "fontSize": 18,
                                     "padding": "10px 14px", "textAlign": "center"}),
        html.Td(id=dist_id, style={"color": MUT, "fontSize": 12,
                                    "padding": "10px 14px", "textAlign": "center"}),
    ])


SIMPLE_TAB_CONTENT = dbc.Card(dbc.CardBody([
    html.Div("📊 حمایت و مقاومت", style={"color": GOLD, "fontWeight": 800, "fontSize": 16, "marginBottom": 4}),
    html.Div("نزدیک‌ترین سطح ساختاری بالا و پایین قیمت فعلی — ساده و بدون پارامتر اضافه",
             style={"color": MUT, "fontSize": 12, "marginBottom": 16}),

    html.Table([
        html.Thead(html.Tr([
            html.Th("سطح", style={"color": MUT, "fontSize": 11, "padding": "8px 14px", "borderBottom": f"1px solid {LINE}"}),
            html.Th("قیمت", style={"color": MUT, "fontSize": 11, "padding": "8px 14px", "borderBottom": f"1px solid {LINE}", "textAlign": "center"}),
            html.Th("فاصله از قیمت لایو", style={"color": MUT, "fontSize": 11, "padding": "8px 14px", "borderBottom": f"1px solid {LINE}", "textAlign": "center"}),
        ])),
        html.Tbody([
            sr_row("🔴 مقاومت (Resistance)", "sr-resistance-price", "sr-resistance-dist", DN),
            html.Tr([
                html.Td("🟡 قیمت لایو (Live)", style={"color": MUT, "fontSize": 13, "padding": "10px 14px"}),
                html.Td(id="sr-live-price", style={"color": GOLD, "fontWeight": 800, "fontSize": 18,
                                                    "padding": "10px 14px", "textAlign": "center"}),
                html.Td("—", style={"color": MUT, "fontSize": 12, "padding": "10px 14px", "textAlign": "center"}),
            ]),
            sr_row("🟢 حمایت (Support)", "sr-support-price", "sr-support-dist", UP),
        ]),
    ], style={"width": "100%", "borderCollapse": "collapse"}),

    html.Div(id="sr-range-note", style={"color": MUT, "fontSize": 12, "marginTop": 16, "textAlign": "center"}),

    html.Div(
        "💡 محاسبه بر اساس نزدیک‌ترین سویینگ ساختاری (Fractal Pivot) در ۲۰۰ کندل اخیر انجام می‌شود؛ "
        "اگر سویینگی یافت نشود، سقف/کف بازه به‌عنوان جایگزین استفاده می‌گردد. این یک برآورد ساختاری از "
        "قیمت است، نه سیگنال معاملاتی.",
        style={"fontSize": 11, "color": MUT, "marginTop": 18, "direction": "rtl", "lineHeight": "1.7",
               "textAlign": "center"},
    ),
]), className="glass-card", style={"maxWidth": 700, "margin": "16px auto"})


DATA_TABLE_STYLE = dict(
    style_table={"overflowX": "auto"},
    style_header={"backgroundColor": CARD2, "color": MUT, "fontWeight": 700,
                   "fontSize": 11, "border": f"1px solid {LINE}", "textAlign": "center"},
    style_cell={"backgroundColor": "rgba(0,0,0,0)", "color": TXT, "fontSize": 12,
                "border": f"1px solid {LINE}", "textAlign": "center", "padding": "8px",
                "fontFamily": FONT_FAMILY},
    style_data_conditional=[
        {"if": {"filter_query": "{معنادار آماری؟} contains '✅'"}, "backgroundColor": "rgba(31,215,166,0.08)"},
        {"if": {"filter_query": "{معنادار آماری؟} contains '❌'"}, "backgroundColor": "rgba(255,93,108,0.05)"},
    ],
)

TIME_TAB_CONTENT = dbc.Card(dbc.CardBody([
    html.Div("⏰ زمان‌سنج چندمنظوره — مبتنی بر صفحه‌ی ساعت Chrono-Clock",
             style={"color": GOLD, "fontWeight": 800, "fontSize": 16, "marginBottom": 4}),
    html.Div("هر دو جدول زیر از همان موتور ساعت استخراج می‌شوند و با تست جایگشتی (Permutation Test) "
             "واقعی سنجیده می‌شوند — نه حدس بصری.",
             style={"color": MUT, "fontSize": 12, "marginBottom": 16}),

    dbc.Row([
        dbc.Col([
            html.Label("حساسیت سویینگ (Order)", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="time-order", value=3, clearable=False, options=[
                {"label": f"{v} کندل", "value": v} for v in [2, 3, 5, 8]
            ]),
        ], md=3),
        dbc.Col([
            html.Label("تعداد هارمونیک‌های فوریه", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="time-harmonics", value=5, clearable=False, options=[
                {"label": f"{v}", "value": v} for v in [3, 5, 8]
            ]),
        ], md=3),
    ], style={"marginBottom": 14}),

    html.Div("① حمایت و مقاومت زمانی (خوشه‌بندی ساعتی سویینگ‌های ساختاری)",
             style={"color": TXT, "fontWeight": 700, "fontSize": 13, "marginBottom": 8}),
    dash_table.DataTable(id="time-sr-table", **DATA_TABLE_STYLE),

    html.Div(id="time-sr-note", style={"color": MUT, "fontSize": 11, "marginTop": 8, "marginBottom": 22}),

    html.Div("② چرخ‌دنده‌های زمانی چندگانه (هارمونیک‌های فوریه با تست معناداری)",
             style={"color": TXT, "fontWeight": 700, "fontSize": 13, "marginBottom": 8}),
    dash_table.DataTable(id="multi-cycle-table", **DATA_TABLE_STYLE),

    html.Div(
        "💡 روش علمی: هر عدد در این دو جدول از یک تست جایگشتی (Permutation Test) واقعی عبور کرده — "
        "یعنی داده به‌صورت تصادفی هزاران بار بازچینش شده تا مشخص شود آیا الگوی مشاهده‌شده واقعاً از "
        "تصادف قوی‌تر است یا نه. p-value کمتر از ۰.۰۵ یعنی احتمال تصادفی بودن این الگو کمتر از ۵٪ است؛ "
        "p-value بالا یعنی الگو از نویز قابل تفکیک نیست و نباید به آن اعتماد کرد. این سیستم صرفاً "
        "زمان‌های محتمل و آماری را نشان می‌دهد، نه پیش‌بینی قطعی قیمت.",
        style={"fontSize": 11, "color": MUT, "marginTop": 20, "direction": "rtl", "lineHeight": "1.7",
               "textAlign": "center"},
    ),
]), className="glass-card", style={"maxWidth": 1000, "margin": "16px auto"})


ADVANCED_TAB_CONTENT = html.Div([
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([
            html.Label("مدل پیش‌بینی", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="model-type", value="ensemble", clearable=False, options=MODEL_OPTS),
        ], md=3),
        dbc.Col([
            html.Label("عمق چرخه", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="harmonics", value=3, clearable=False, options=[
                {"label": "۱ (اصلی)", "value": 1},
                {"label": "۲ (فرعی)", "value": 2},
                {"label": "۳ (پیشرفته)", "value": 3},
                {"label": "۵ (فوق‌پیشرفته)", "value": 5},
            ]),
        ], md=2),
        dbc.Col([
            html.Label("افق (ساعت)", style={"fontSize": 11, "color": MUT}),
            dcc.Input(id="forecast-hours", type="number", value=DEFAULT_FORECAST_HOURS,
                      min=1, max=12, step=1,
                      style={"width": "100%", "padding": 6, "borderRadius": 8,
                             "background": CARD2, "color": TXT, "border": f"1px solid {LINE}"}),
        ], md=2),
        dbc.Col([
            dbc.Checklist(
                id="toggles",
                options=[
                    {"label": "نمایش CI", "value": "ci"},
                    {"label": "مقایسه مدل‌ها", "value": "all_models"},
                ],
                value=["ci"],
                style={"marginTop": 20, "fontSize": 11, "color": MUT},
                switch=True,
            ),
        ], md=3),
    ])), className="glass-card", style={"maxWidth": 1200, "margin": "10px auto"}),

    html.Div(dbc.Row([
        stat_card("live-price", "قیمت لایو", GOLD),
        stat_card("forecast-price", "پیش‌بینی افق", UP),
        stat_card("cycle-strength", "قدرت چرخه", BLUE),
        stat_card("conn", "وضعیت اتصال", MUT),
    ]), style={"maxWidth": 1200, "margin": "0 auto"}),

    dbc.Row([
        dbc.Col(
            dbc.Card(dbc.CardBody([
                dcc.Graph(id="clock-graph", style={"height": "78vh"}, config={"displaylogo": False, "responsive": True}),
            ]), className="glass-card"),
            md=9,
        ),
        dbc.Col(
            dbc.Card(dbc.CardBody([
                dcc.Graph(id="gauges-graph", config={"displaylogo": False, "responsive": True}),
                html.Hr(style={"borderColor": LINE}),
                html.Div(id="model-weights-panel", style={"fontSize": 12, "color": TXT, "lineHeight": "1.9"}),
            ]), className="glass-card"),
            md=3,
        ),
    ], style={"maxWidth": 1200, "margin": "10px auto"}),

    html.Div(
        "💡 مدل آنسمبل با اجرای یک واک‌فوروارد بک‌تست کوتاه روی همان داده‌ی دریافتی، به هر یک از "
        "مدل‌های فوریه (چرخه‌ها)، مومنتوم (EMA) و روند خطی وزنی متناسب با دقت اخیرشان می‌دهد. "
        "پنجره‌ی Hann پیش از FFT اعمال می‌شود تا نشت طیفی کاهش و تشخیص چرخه‌های واقعی دقیق‌تر شود. "
        "باند اطمینان بر اساس ATR و افق زمانی محاسبه می‌شود و صرفاً بازه‌ی نوسان محتمل را نشان می‌دهد، نه تضمین قیمت.",
        style={"fontSize": 11, "color": MUT, "marginTop": 4, "direction": "rtl", "lineHeight": "1.7",
               "textAlign": "center", "maxWidth": 1200, "marginLeft": "auto", "marginRight": "auto",
               "padding": "0 12px 16px 12px"},
    ),
])


app.layout = html.Div([
    html.Div([
        html.H4("⏳ Chrono-Clock Pro", style={"color": GOLD, "fontWeight": 800, "margin": 0}),
        html.Div("موتور پیش‌بینی آنسمبل مبتنی بر چرخه‌های زمانی — Morindok",
                 style={"color": MUT, "fontSize": 12}),
    ], style={"maxWidth": 1200, "margin": "10px auto 4px auto", "padding": "0 6px"}),

    # --- کنترل‌های مشترک بین هر دو تب ---
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([
            html.Label("نماد", style={"fontSize": 11, "color": MUT}),
            dcc.Input(id="symbol", value=DEFAULT_SYMBOL, type="text",
                      style={"width": "100%", "padding": 6, "borderRadius": 8,
                             "background": CARD2, "color": TXT, "border": f"1px solid {LINE}"}),
        ], md=3),
        dbc.Col([
            html.Label("بازار", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="category", value=DEFAULT_CATEGORY, clearable=False, options=CATEGORY_OPTS),
        ], md=2),
        dbc.Col([
            html.Label("تایم‌فریم", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="interval", value=DEFAULT_INTERVAL, clearable=False, options=INTERVAL_OPTS),
        ], md=2),
        dbc.Col(
            dbc.Button("🔄 به‌روزرسانی", id="refresh-btn", color="warning", className="mt-3",
                       style={"fontWeight": "bold", "color": BG, "width": "100%", "padding": "8px 6px"}),
            md=2,
        ),
    ])), className="glass-card", style={"maxWidth": 1200, "margin": "10px auto"}),

    dcc.Tabs(id="main-tabs", value="tab-sr", children=[
        dcc.Tab(label="📊 حمایت و مقاومت", value="tab-sr"),
        dcc.Tab(label="⏰ زمان‌سنج چندمنظوره", value="tab-time"),
        dcc.Tab(label="🧪 سیستم آماری (پیشرفته)", value="tab-adv"),
    ], style={"maxWidth": 1200, "margin": "0 auto"}),

    html.Div(SIMPLE_TAB_CONTENT, id="tab-sr-content"),
    html.Div(TIME_TAB_CONTENT, id="tab-time-content"),
    html.Div(ADVANCED_TAB_CONTENT, id="tab-adv-content"),

    dcc.Interval(id="tick", interval=30_000, n_intervals=0),
    dcc.Store(id="meta-store"),
], style={"background": BG, "minHeight": "100vh", "padding": "10px", "fontFamily": FONT_FAMILY})


@app.callback(
    Output("tab-sr-content", "style"),
    Output("tab-time-content", "style"),
    Output("tab-adv-content", "style"),
    Input("main-tabs", "value"),
)
def switch_tabs(tab_value):
    styles = {"tab-sr": {"display": "none"}, "tab-time": {"display": "none"}, "tab-adv": {"display": "none"}}
    styles[tab_value] = {"display": "block"}
    return styles["tab-sr"], styles["tab-time"], styles["tab-adv"]


@app.callback(
    Output("sr-live-price", "children"),
    Output("sr-resistance-price", "children"),
    Output("sr-resistance-dist", "children"),
    Output("sr-support-price", "children"),
    Output("sr-support-dist", "children"),
    Output("sr-range-note", "children"),
    Input("tick", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    State("symbol", "value"),
    State("category", "value"),
    State("interval", "value"),
)
def update_sr_table(_n, _click, symbol, category, interval):
    symbol = (symbol or DEFAULT_SYMBOL).upper().strip()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL

    df = get_klines(symbol, interval, category, limit=500)
    if df.empty:
        return "—", "—", "—", "—", "—", "🔴 خطا در دریافت داده از بایبیت."

    live_price = float(df.iloc[-1]["close"])
    sr = compute_support_resistance(df, live_price)

    note = (f"عرض کانال بین حمایت و مقاومت ≈ {sr['range_pct']:.2f}٪ از قیمت لایو | "
            f"{symbol} | {interval}m")

    return (
        f"{sr['live']:,.4g}",
        f"{sr['resistance']:,.4g}",
        f"↑ {sr['res_dist_pct']:.2f}٪",
        f"{sr['support']:,.4g}",
        f"↓ {sr['sup_dist_pct']:.2f}٪",
        note,
    )


@app.callback(
    Output("time-sr-table", "data"),
    Output("time-sr-table", "columns"),
    Output("time-sr-note", "children"),
    Output("multi-cycle-table", "data"),
    Output("multi-cycle-table", "columns"),
    Input("tick", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    State("symbol", "value"),
    State("category", "value"),
    State("interval", "value"),
    State("time-order", "value"),
    State("time-harmonics", "value"),
)
def update_time_tables(_n, _click, symbol, category, interval, order, n_harmonics):
    symbol = (symbol or DEFAULT_SYMBOL).upper().strip()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL
    order = int(order or 3)
    n_harmonics = int(n_harmonics or 5)

    now_utc = get_server_time()
    df = get_klines(symbol, interval, category, limit=500)
    interval_min = get_interval_minutes(interval)

    empty_cols = [{"name": "پیام", "id": "msg"}]
    if df.empty:
        msg = [{"msg": "خطا در دریافت داده از بایبیت."}]
        return msg, empty_cols, "", [], empty_cols

    # --- جدول ۱: حمایت/مقاومت زمانی ---
    sr_time = compute_time_based_sr(df, now_utc, order=order, n_perm=400)
    sr_cols = [
        {"name": "نوع", "id": "نوع"},
        {"name": "ساعت UTC", "id": "ساعت UTC"},
        {"name": "معادل صفحه‌ساعت", "id": "معادل صفحه‌ساعت"},
        {"name": "تراکم تاریخی", "id": "تراکم تاریخی"},
        {"name": "p-value", "id": "p-value"},
        {"name": "معنادار آماری؟", "id": "معنادار آماری؟"},
        {"name": "قیمت پیش‌بینی امروز", "id": "قیمت پیش‌بینی امروز"},
        {"name": "وقوع بعدی (UTC)", "id": "وقوع بعدی (UTC)"},
    ]
    if sr_time is None:
        sr_data = []
        sr_note = "داده‌ی کافی برای تحلیل ساختاری وجود ندارد (به کندل بیشتر یا حساسیت کمتر نیاز است)."
    else:
        rows = []
        for label, key in [("🔴 مقاومت زمانی", "resistance"), ("🟢 حمایت زمانی", "support")]:
            item = sr_time[key]
            rows.append({
                "نوع": label,
                "ساعت UTC": f"{int(item['hour_utc']):02d}:{int(round((item['hour_utc']%1)*60)):02d}",
                "معادل صفحه‌ساعت": item["clock12"],
                "تراکم تاریخی": f"{item['count']}/{item['total']}",
                "p-value": f"{item['p_value']:.3f}",
                "معنادار آماری؟": "✅ بله (p<0.05)" if item["significant"] else "❌ خیر",
                "قیمت پیش‌بینی امروز": f"{item['price']:,.4g}",
                "وقوع بعدی (UTC)": item["next_time"].strftime("%Y-%m-%d %H:%M"),
            })
        sr_data = rows
        sr_note = ("توضیح: p-value از تست جایگشتی روی ۴۰۰ بازچینش تصادفی به دست آمده. اگر هر دو ردیف "
                   "«❌ خیر» باشند، یعنی الگوی ساعتی این نماد در بازه‌ی فعلی از نویز تصادفی قابل تفکیک نیست.")

    # --- جدول ۲: چرخ‌دنده‌های زمانی چندگانه ---
    cyc_rows = multi_cycle_table(df, interval_min, now_utc, n_harmonics=n_harmonics, n_perm=300)
    cyc_cols = [
        {"name": "دوره تناوب", "id": "دوره تناوب"},
        {"name": "قدرت (% از کل طیف)", "id": "قدرت"},
        {"name": "p-value", "id": "p-value"},
        {"name": "معنادار آماری؟", "id": "معنادار آماری؟"},
        {"name": "فاز فعلی", "id": "فاز فعلی"},
        {"name": "اوج بعدی (مقاومت زمانی)", "id": "اوج بعدی"},
        {"name": "کف بعدی (حمایت زمانی)", "id": "کف بعدی"},
    ]
    cyc_data = []
    for r in cyc_rows:
        period_txt = f"{r['period_hours']:.2f} ساعت" if r["period_hours"] < 48 else f"{r['period_hours']/24:.1f} روز"
        cyc_data.append({
            "دوره تناوب": period_txt,
            "قدرت": f"{r['power_pct']:.1f}٪",
            "p-value": f"{r['p_value']:.3f}",
            "معنادار آماری؟": "✅ بله (p<0.05)" if r["significant"] else "❌ خیر",
            "فاز فعلی": "📈 در حال صعود" if r["rising"] else "📉 در حال نزول",
            "اوج بعدی": r["next_peak"].strftime("%m-%d %H:%M UTC"),
            "کف بعدی": r["next_trough"].strftime("%m-%d %H:%M UTC"),
        })

    return sr_data, sr_cols, sr_note, cyc_data, cyc_cols


@app.callback(
    Output("clock-graph", "figure"),
    Output("gauges-graph", "figure"),
    Output("live-price-value", "children"),
    Output("forecast-price-value", "children"),
    Output("cycle-strength-value", "children"),
    Output("conn-value", "children"),
    Output("model-weights-panel", "children"),
    Input("tick", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    State("symbol", "value"),
    State("category", "value"),
    State("interval", "value"),
    State("forecast-hours", "value"),
    State("model-type", "value"),
    State("harmonics", "value"),
    State("toggles", "value"),
)
def update(_n, _click, symbol, category, interval, forecast_hours, model_type, n_harmonics, toggles):
    symbol = (symbol or DEFAULT_SYMBOL).upper().strip()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL
    model_type = model_type or "ensemble"
    n_harmonics = int(n_harmonics or 3)
    toggles = toggles or []
    show_ci = "ci" in toggles
    show_all_models = "all_models" in toggles

    try:
        forecast_hours = float(forecast_hours or DEFAULT_FORECAST_HOURS)
    except Exception:
        forecast_hours = DEFAULT_FORECAST_HOURS

    now_utc = get_server_time()
    df = get_klines(symbol, interval, category, limit=500)

    if df.empty:
        empty = empty_fig("خطا در دریافت کندل از بایبیت.")
        return empty, go.Figure(), "—", "—", "—", "🔴 قطع از بایبیت", ""

    fig, meta = build_clock_figure(df, now_utc, symbol, interval, forecast_hours,
                                    model_type, n_harmonics, show_ci, show_all_models)

    live_price = float(df.iloc[-1]["close"])
    strength = 0.0
    if meta:
        # قدرت چرخه از فوریه محاسبه شده و در annotation قرار گرفته؛ اینجا از پیش‌بینی مدل انتخابی می‌خوانیم
        pred_arr = meta.get("pred_prices")
        forecast_at_horizon = pred_arr[-1] if pred_arr is not None and len(pred_arr) else live_price
    else:
        forecast_at_horizon = live_price

    gauges_fig = build_gauges_figure(
        strength=_extract_strength(fig), current_atr=meta.get("current_atr", 0.0) if meta else 0.0,
        live_price=live_price, model_type=model_type, meta=meta or {},
    )

    pct_change = ((forecast_at_horizon - live_price) / live_price * 100) if live_price else 0.0
    forecast_txt = f"{forecast_at_horizon:,.4g} ({pct_change:+.2f}%)"

    weights_panel = ""
    if meta and meta.get("weights"):
        w = meta["weights"]
        rows = []
        for k in ("fourier", "momentum", "linear"):
            rows.append(html.Div([
                html.Span(MODEL_LABEL_FA[k] + ": ", style={"color": MUT}),
                html.Span(f"{w[k]*100:.1f}%", style={"color": MODEL_COLORS[k], "fontWeight": 700}),
            ]))
        weights_panel = html.Div(rows)

    status = f"🟢 متصل | {now_utc.strftime('%H:%M:%S')} UTC"
    return (
        fig, gauges_fig,
        f"{live_price:,.4g}",
        forecast_txt,
        f"{_extract_strength(fig):.1f}%",
        status,
        weights_panel,
    )


def _extract_strength(fig):
    """قدرت چرخه را از annotation متنی روی فیگور استخراج می‌کند تا محاسبه دوباره لازم نباشد."""
    for ann in fig.layout.annotations or []:
        if ann.text and "قدرت چرخه زمانی" in ann.text:
            try:
                return float(ann.text.split(":")[-1].replace("%", "").strip())
            except Exception:
                return 0.0
    return 0.0


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050, use_reloader=False)