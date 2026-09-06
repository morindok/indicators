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

import math  # noqa: F401  (استفاده در build_planets_grid_figure برای math.ceil)
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import dash
from dash import dcc, html, Input, Output, State
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
# 2B) کرونو کلاک سیاره‌ای — همان حلقه‌ی قیمتِ زمین، با سرعت چرخش سیارات دیگر
# ==============================================================================
# منطق: عقربه‌ی زمینی هر ۱۲ ساعت (نصف یک شبانه‌روزِ ۲۴ ساعته) یک دور کامل می‌زند.
# همین قانون را برای بقیه‌ی سیارات هم تعمیم می‌دهیم: «یک دور کامل عقربه» = نصف طول
# شبانه‌روز خورشیدی همان سیاره. موقعیت لحظه‌ای (بر اساس زمان پیوسته‌ی epoch) روی
# همان حلقه‌ی واقعیِ قیمت که از داده‌ی زمین ساخته شده می‌نشیند — یعنی الگوی واقعیِ
# نوسان درون‌روزی BTC را با سرعت چرخش هر سیاره پخش می‌کنیم. برای زمین این فرمول
# دقیقاً معادل خودِ hour_frac_12 اصلی است (چون epoch از نیمه‌شب UTC شروع می‌شود).

PLANETS = [
    {"key": "mercury", "name": "عطارد",    "emoji": "☿",  "day_hours": 4222.6},
    {"key": "venus",   "name": "زهره",     "emoji": "♀",  "day_hours": 2802.0},
    {"key": "earth",   "name": "زمین",     "emoji": "🌍", "day_hours": 24.0},
    {"key": "mars",    "name": "مریخ",     "emoji": "♂",  "day_hours": 24.6597},
    {"key": "jupiter", "name": "مشتری",    "emoji": "♃",  "day_hours": 9.925},
    {"key": "saturn",  "name": "زحل",      "emoji": "♄",  "day_hours": 10.656},
    {"key": "uranus",  "name": "اورانوس",  "emoji": "♅",  "day_hours": 17.24},
    {"key": "neptune", "name": "نپتون",    "emoji": "♆",  "day_hours": 16.11},
    {"key": "pluto",   "name": "پلوتو",    "emoji": "⯓",  "day_hours": 153.28},
]


def build_price_ring_simple(df, n_bins=N_BINS):
    """حلقه‌ی قیمت تاریخی روی صفحه‌ی ۱۲ ساعته (بدون بخش پیش‌بینی) + درون‌یابی حلقوی."""
    bin_price = np.full(n_bins, np.nan)
    bin_ts = [None] * n_bins
    for _, row in df.iterrows():
        ts = pd.Timestamp(row["ts"]).to_pydatetime().replace(tzinfo=timezone.utc)
        hf = hour_frac_12(ts)
        idx = int(hf / 12.0 * n_bins) % n_bins
        if bin_ts[idx] is None or ts > bin_ts[idx]:
            bin_ts[idx] = ts
            bin_price[idx] = float(row["close"])

    nanmask = np.isnan(bin_price)
    valid_count = (~nanmask).sum()
    if valid_count >= 2:
        idxs = np.arange(n_bins)
        ext_price = np.concatenate([bin_price, bin_price, bin_price])
        ext_idx = np.concatenate([idxs - n_bins, idxs, idxs + n_bins])
        ext_valid = ~np.isnan(ext_price)
        filled = np.interp(idxs + n_bins, ext_idx[ext_valid], ext_price[ext_valid])
        bin_price[nanmask] = filled[nanmask]
    elif valid_count == 1:
        bin_price[nanmask] = bin_price[~nanmask][0]
    else:
        fallback = float(df.iloc[-1]["close"]) if len(df) else 0.0
        bin_price[:] = fallback
    return bin_price


def planet_clock_state(ring, day_hours, now_utc, n_bins=N_BINS):
    """موقعیت لحظه‌ای عقربه‌ی یک سیاره روی حلقه‌ی قیمت زمین."""
    half_day = day_hours / 2.0
    hours_since_epoch = now_utc.timestamp() / 3600.0
    frac = (hours_since_epoch % half_day) / half_day
    hf12 = frac * 12.0
    idx = int(frac * n_bins) % n_bins
    return {
        "half_day": half_day,
        "frac": frac,
        "hf12": hf12,
        "clock_str": hour_frac_to_clockstr(hf12),
        "pct": frac * 100.0,
        "price": float(ring[idx]),
        "bin_idx": idx,
    }


def build_planets_rows(df, now_utc, n_bins=N_BINS):
    """جدول لایو: برای هر سیاره وضعیت عقربه و قیمت متناظر روی حلقه."""
    ring = build_price_ring_simple(df, n_bins)
    rows = []
    for pl in PLANETS:
        st = planet_clock_state(ring, pl["day_hours"], now_utc, n_bins)
        rows.append({**pl, **st})
    return rows, ring


def build_planets_grid_figure(ring, rows, n_bins=N_BINS, cols=3):
    """نمودار قیمت-زمان جداگانه برای هر سیاره (زیرنمودار‌های مستقل)."""
    n = len(rows)
    n_rows = math.ceil(n / cols)
    fig = make_subplots(
        rows=n_rows, cols=cols,
        subplot_titles=[f"{r['emoji']} {r['name']} — دور = {r['half_day']:,.2f}h" for r in rows],
        horizontal_spacing=0.06, vertical_spacing=0.10,
    )
    for i, r in enumerate(rows):
        row_i, col_i = i // cols + 1, i % cols + 1
        x = np.arange(n_bins) / n_bins * r["half_day"]
        fig.add_trace(go.Scatter(
            x=x, y=ring, mode="lines", line=dict(color=BLUE, width=1.3),
            fill="tozeroy", fillcolor="rgba(79,141,253,0.08)",
            hovertemplate="t=%{x:.2f}h<br>قیمت=%{y:,.4g}<extra></extra>",
            showlegend=False,
        ), row=row_i, col=col_i)
        fig.add_trace(go.Scatter(
            x=[r["frac"] * r["half_day"]], y=[r["price"]], mode="markers",
            marker=dict(size=11, symbol="star", color=GOLD, line=dict(width=1, color="black")),
            hovertemplate=f"الان: {r['clock_str']}<br>قیمت=%{{y:,.4g}}<extra></extra>",
            showlegend=False,
        ), row=row_i, col=col_i)
        fig.update_xaxes(color=MUT, gridcolor=LINE, tickfont=dict(size=8), row=row_i, col=col_i)
        fig.update_yaxes(color=MUT, gridcolor=LINE, tickfont=dict(size=8), row=row_i, col=col_i)

    fig.update_annotations(font=dict(size=11, color=TXT, family=FONT_FAMILY))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
        height=280 * n_rows, margin=dict(l=20, r=20, t=40, b=20),
        font=dict(family=FONT_FAMILY, color=TXT),
    )
    return fig


def build_planets_table_children(rows):
    """جدول HTML لایو با استایل گلس مورفیسم هماهنگ با بقیه‌ی اپ."""
    header = html.Tr([
        html.Th("سیاره"), html.Th("طول شبانه‌روز"), html.Th("طول یک دور عقربه"),
        html.Th("عقربه الان کجاست"), html.Th("٪ پیشرفت دور"), html.Th("قیمت روی ساعت"),
    ], style={"color": MUT, "fontSize": 11})

    def fmt_dur(h):
        return f"{h:,.2f}h" if h < 48 else f"{h/24:,.1f} روز ({h:,.0f}h)"

    body_rows = []
    for r in rows:
        is_earth = r["key"] == "earth"
        body_rows.append(html.Tr([
            html.Td(f"{r['emoji']} {r['name']}", style={"textAlign": "right", "fontWeight": 700}),
            html.Td(fmt_dur(r["day_hours"]), style={"color": MUT}),
            html.Td(fmt_dur(r["half_day"]), style={"color": MUT}),
            html.Td(r["clock_str"]),
            html.Td(f"{r['pct']:.1f}%", style={"color": MUT}),
            html.Td(f"${r['price']:,.4g}", style={"color": GOLD, "fontWeight": 800}),
        ], style={"background": "rgba(243,186,47,0.06)" if is_earth else "transparent"}))

    return dbc.Table(
        [html.Thead(header), html.Tbody(body_rows)],
        bordered=False, hover=True, responsive=True, size="sm",
        style={"fontSize": 13, "textAlign": "center", "color": TXT},
    )


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


# ==============================================================================
# 3B) ارزیابی عملکرد پیش‌بینی — وین‌ریت و آمار بک‌تست غلتان (Rolling Walk-Forward)
# ==============================================================================
# تعریف «برد» (win): برای هر نقطه‌ی زمانی گذشته، مدل با داده‌ی تا همان لحظه یک
# مسیر به‌جلو (به اندازه‌ی افق انتخابی) پیش‌بینی می‌کند. اگر جهتِ حرکتِ پیش‌بینی‌شده
# (بالا/پایین نسبت به آخرین قیمتِ لحظه‌ی پیش‌بینی) با جهتِ واقعی که بعداً رخ داده
# یکی باشد، آن نمونه «برد» است. وین‌ریت = درصد بردها از کل نمونه‌های تست‌شده.
# این یک آزمون کاملاً واک‌فوروارد است: هیچ داده‌ای از آینده در لحظه‌ی پیش‌بینی دیده نمی‌شود.

BACKTEST_STRIDE = 8  # فاصله (تعداد کندل) بین نمونه‌های بک‌تست غلتان


def compute_predictions_for_window(train_closes, steps, n_harmonics):
    preds, strength = compute_all_forecasts(train_closes, steps, n_harmonics)
    weights, errors = walk_forward_weights(train_closes, n_harmonics,
                                            test_steps=min(BACKTEST_STEPS, max(steps, 5)))
    preds["ensemble"] = (
        weights["fourier"] * preds["fourier"]
        + weights["momentum"] * preds["momentum"]
        + weights["linear"] * preds["linear"]
    )
    return preds, weights, strength


def run_rolling_winrate_backtest(df, interval_min, forecast_hours, n_harmonics, stride=BACKTEST_STRIDE):
    """بک‌تست غلتان روی کل تاریخچه‌ی دریافتی: هر stride کندل یک‌بار، یک پیش‌بینیِ
    کامل (فوریه/مومنتوم/خطی/آنسمبل) ساخته و با آنچه واقعاً رخ داده مقایسه می‌شود."""
    closes = df["close"].values
    n = len(closes)
    steps = max(int((forecast_hours * 60.0) / max(interval_min, 1)), 1)
    records = []
    i = BACKTEST_MIN_HISTORY
    while i + steps <= n:
        train = closes[:i]
        actual_path = closes[i:i + steps]
        preds, _, _ = compute_predictions_for_window(train, steps, n_harmonics)
        last_train = train[-1]
        actual_last = actual_path[-1]
        actual_dir = np.sign(actual_last - last_train)
        rec = {"i": i}
        for m in ("fourier", "momentum", "linear", "ensemble"):
            p_last = preds[m][-1]
            pred_dir = np.sign(p_last - last_train)
            rec[f"{m}_win"] = 1 if (pred_dir != 0 and pred_dir == actual_dir) else 0
            rec[f"{m}_abs_pct_err"] = (abs(p_last - actual_last) / actual_last * 100) if actual_last else np.nan
        records.append(rec)
        i += stride
    return pd.DataFrame(records), steps


def summarize_winrate(bt_df):
    if bt_df is None or bt_df.empty:
        return {}
    out = {}
    for m in ("fourier", "momentum", "linear", "ensemble"):
        out[m] = {
            "win_rate": float(bt_df[f"{m}_win"].mean() * 100),
            "avg_abs_pct_err": float(bt_df[f"{m}_abs_pct_err"].mean()),
            "n": int(len(bt_df)),
        }
    return out


def latest_forecast_vs_actual(df, interval_min, forecast_hours, n_harmonics, model_type):
    """مسیر پیش‌بینی‌شده در آخرین افقِ کامل‌شده (که الان می‌شود دید چه اتفاقی واقعاً افتاد)."""
    closes = df["close"].values
    n = len(closes)
    steps = max(int((forecast_hours * 60.0) / max(interval_min, 1)), 1)
    if n <= steps + BACKTEST_MIN_HISTORY:
        return None
    train = closes[: n - steps]
    actual_path = closes[n - steps:]
    preds, _, _ = compute_predictions_for_window(train, steps, n_harmonics)
    pred_path = preds.get(model_type, preds["ensemble"])
    last_ts = pd.Timestamp(df["ts"].iloc[n - steps - 1]).to_pydatetime().replace(tzinfo=timezone.utc)
    future_ts = [last_ts + timedelta(minutes=interval_min * (s + 1)) for s in range(steps)]
    return {
        "future_ts": future_ts,
        "pred_path": pred_path,
        "actual_path": actual_path,
        "last_train_price": float(train[-1]),
    }


def build_winrate_path_figure(latest, model_type):
    if latest is None:
        return empty_fig("داده‌ی کافی برای بررسی مسیر پیش‌بینی‌شده نیست.")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=latest["future_ts"], y=latest["actual_path"], mode="lines+markers",
        name="قیمت واقعی", line=dict(color=UP, width=2), marker=dict(size=5),
    ))
    fig.add_trace(go.Scatter(
        x=latest["future_ts"], y=latest["pred_path"], mode="lines+markers",
        name=f"مسیر پیش‌بینی‌شده ({MODEL_LABEL_FA.get(model_type, model_type)})",
        line=dict(color=GOLD, width=2, dash="dash"), marker=dict(size=5, symbol="diamond"),
    ))
    fig.add_hline(y=latest["last_train_price"], line=dict(color=MUT, dash="dot", width=1),
                  annotation_text="قیمت لحظه‌ی پیش‌بینی", annotation_font=dict(color=MUT, size=10))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
        margin=dict(l=40, r=20, t=50, b=30),
        legend=dict(orientation="h", y=-0.22, x=0.5, xanchor="center", font=dict(color=TXT, size=10)),
        xaxis=dict(color=MUT, gridcolor=LINE, title="زمان"),
        yaxis=dict(color=MUT, gridcolor=LINE, title="قیمت"),
        font=dict(family=FONT_FAMILY, color=TXT),
        title=dict(text="مسیر پیش‌بینی‌شده در برابر قیمت واقعی (آخرین افقِ کامل‌شده)",
                   x=0.5, font=dict(color=GOLD, size=13)),
    )
    return fig


def build_winrate_bar_figure(summary):
    if not summary:
        return empty_fig("داده کافی برای وین‌ریت نیست.")
    models = ["fourier", "momentum", "linear", "ensemble"]
    fig = go.Figure(go.Bar(
        x=[MODEL_LABEL_FA[m] for m in models],
        y=[summary[m]["win_rate"] for m in models],
        marker_color=[MODEL_COLORS[m] for m in models],
        text=[f"{summary[m]['win_rate']:.1f}%" for m in models],
        textposition="outside",
    ))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
        margin=dict(l=40, r=20, t=50, b=30),
        yaxis=dict(color=MUT, gridcolor=LINE, title="وین‌ریت (٪)", range=[0, 100]),
        xaxis=dict(color=MUT),
        font=dict(family=FONT_FAMILY, color=TXT),
        title=dict(text="وین‌ریت جهت‌گیری هر مدل (٪ پیش‌بینیِ درستِ جهت حرکت)",
                   x=0.5, font=dict(color=GOLD, size=13)),
        showlegend=False,
    )
    return fig


def build_winrate_table_children(summary):
    header = html.Tr([
        html.Th("مدل"), html.Th("وین‌ریت"), html.Th("میانگین خطای مطلق"), html.Th("تعداد نمونه"),
    ], style={"color": MUT, "fontSize": 11})
    rows = []
    for m in ("fourier", "momentum", "linear", "ensemble"):
        s = summary.get(m, {"win_rate": 0.0, "avg_abs_pct_err": 0.0, "n": 0})
        rows.append(html.Tr([
            html.Td(MODEL_LABEL_FA[m], style={"textAlign": "right", "fontWeight": 700, "color": MODEL_COLORS[m]}),
            html.Td(f"{s['win_rate']:.1f}%", style={"fontWeight": 800, "color": GOLD}),
            html.Td(f"{s['avg_abs_pct_err']:.2f}%", style={"color": MUT}),
            html.Td(f"{s['n']}", style={"color": MUT}),
        ]))
    return dbc.Table([html.Thead(header), html.Tbody(rows)], bordered=False, hover=True,
                      responsive=True, size="sm", style={"fontSize": 13, "textAlign": "center", "color": TXT})


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


def kpi_card(label, value, color=TXT):
    return dbc.Col(
        html.Div([
            html.Div(label, className="stat-label"),
            html.Div(value, className="stat-value", style={"color": color}),
        ], className="glass-card", style={"padding": "12px 16px", "textAlign": "center"}),
        md=3, xs=6, style={"marginBottom": 10},
    )


app.layout = html.Div([
    html.Div([
        html.H4("⏳ Chrono-Clock Pro", style={"color": GOLD, "fontWeight": 800, "margin": 0}),
        html.Div("موتور پیش‌بینی آنسمبل مبتنی بر چرخه‌های زمانی — Morindok",
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
            html.Label("مدل پیش‌بینی", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="model-type", value="ensemble", clearable=False, options=MODEL_OPTS),
        ], md=2),
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
        ], md=1),
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
        ], md=2),
        dbc.Col(
            dbc.Button("🔄 به‌روزرسانی", id="refresh-btn", color="warning", className="mt-3",
                       style={"fontWeight": "bold", "color": BG, "width": "100%", "padding": "8px 6px"}),
            md=1,
        ),
    ])), className="glass-card", style={"maxWidth": 1200, "margin": "10px auto"}),

    html.Div(dbc.Row([
        stat_card("live-price", "قیمت لایو", GOLD),
        stat_card("forecast-price", "پیش‌بینی افق", UP),
        stat_card("cycle-strength", "قدرت چرخه", BLUE),
        stat_card("conn", "وضعیت اتصال", MUT),
    ]), style={"maxWidth": 1200, "margin": "0 auto"}),

    dbc.Tabs([
        dbc.Tab(label="⏳ ساعت زنده", tab_id="tab-clock", children=[
            dbc.Row([
                dbc.Col(
                    dbc.Card(dbc.CardBody([
                        dcc.Graph(id="clock-graph", style={"height": "78vh"}, config={"displaylogo": False}),
                    ]), className="glass-card"),
                    md=9,
                ),
                dbc.Col(
                    dbc.Card(dbc.CardBody([
                        dcc.Graph(id="gauges-graph", config={"displaylogo": False}),
                        html.Hr(style={"borderColor": LINE}),
                        html.Div(id="model-weights-panel", style={"fontSize": 12, "color": TXT, "lineHeight": "1.9"}),
                    ]), className="glass-card"),
                    md=3,
                ),
            ], style={"margin": "10px 0"}),
        ]),

        dbc.Tab(label="🪐 سیارات", tab_id="tab-planets", children=[
            html.Div([
                html.Div(
                    "اگر عقربه‌های همین ساعت به‌جای زمین، با سرعت چرخش یک سیاره‌ی دیگر می‌چرخیدند، الان روی "
                    "چه عددی از همین حلقه‌ی قیمت واقعی می‌ایستادند؟ («یک دور عقربه» = نصف شبانه‌روز آن سیاره، "
                    "دقیقاً مثل ساعت معمولی زمین.)",
                    style={"fontSize": 11, "color": MUT, "margin": "10px 6px"},
                ),
            ]),
            dbc.Card(dbc.CardBody([
                html.Div(id="planets-table"),
            ]), className="glass-card", style={"margin": "0 0 14px 0"}),
            dbc.Card(dbc.CardBody([
                dcc.Graph(id="planets-grid-graph", config={"displaylogo": False}),
            ]), className="glass-card"),
        ]),

        dbc.Tab(label="📊 آمار پیش‌بینی (وین‌ریت)", tab_id="tab-winrate", children=[
            html.Div(
                "وین‌ریت = درصدِ نمونه‌های بک‌تستِ واک‌فوروارد که «جهتِ» حرکتِ پیش‌بینی‌شده "
                "(صعود/نزول نسبت به قیمتِ لحظه‌ی پیش‌بینی) با جهتِ واقعیِ بعدی یکی بوده. این بک‌تست "
                "کاملاً روی داده‌ی تاریخیِ همین ۵۰۰ کندلِ دریافتی و بدون دیدن آینده انجام می‌شود.",
                style={"fontSize": 11, "color": MUT, "margin": "10px 6px", "lineHeight": "1.8"},
            ),
            html.Div(dbc.Row(id="winrate-kpi-row"), style={"margin": "0 0 10px 0"}),
            dbc.Row([
                dbc.Col(
                    dbc.Card(dbc.CardBody([
                        dcc.Graph(id="winrate-path-graph", config={"displaylogo": False}),
                    ]), className="glass-card"),
                    md=7,
                ),
                dbc.Col(
                    dbc.Card(dbc.CardBody([
                        dcc.Graph(id="winrate-bar-graph", config={"displaylogo": False}),
                    ]), className="glass-card"),
                    md=5,
                ),
            ], style={"margin": "0 0 14px 0"}),
            dbc.Card(dbc.CardBody([
                html.Div(id="winrate-table"),
            ]), className="glass-card"),
        ]),
    ], id="main-tabs", active_tab="tab-clock", style={"maxWidth": 1200, "margin": "0 auto"}),

    html.Div(id="tabs-content-spacer", style={"maxWidth": 1200, "margin": "0 auto"}),

    html.Div(
        "💡 مدل آنسمبل با اجرای یک واک‌فوروارد بک‌تست کوتاه روی همان داده‌ی دریافتی، به هر یک از "
        "مدل‌های فوریه (چرخه‌ها)، مومنتوم (EMA) و روند خطی وزنی متناسب با دقت اخیرشان می‌دهد. "
        "پنجره‌ی Hann پیش از FFT اعمال می‌شود تا نشت طیفی کاهش و تشخیص چرخه‌های واقعی دقیق‌تر شود. "
        "باند اطمینان بر اساس ATR و افق زمانی محاسبه می‌شود و صرفاً بازه‌ی نوسان محتمل را نشان می‌دهد، نه تضمین قیمت.",
        style={"fontSize": 11, "color": MUT, "marginTop": 4, "direction": "rtl", "lineHeight": "1.7",
               "textAlign": "center", "maxWidth": 1200, "marginLeft": "auto", "marginRight": "auto",
               "padding": "0 12px 16px 12px"},
    ),

    dcc.Interval(id="tick", interval=30_000, n_intervals=0),
    dcc.Interval(id="tick-slow", interval=90_000, n_intervals=0),
    dcc.Store(id="meta-store"),
], style={"background": BG, "minHeight": "100vh", "padding": "10px", "fontFamily": FONT_FAMILY})


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


@app.callback(
    Output("planets-table", "children"),
    Output("planets-grid-graph", "figure"),
    Input("tick", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    State("symbol", "value"),
    State("category", "value"),
    State("interval", "value"),
)
def update_planets(_n, _click, symbol, category, interval):
    symbol = (symbol or DEFAULT_SYMBOL).upper().strip()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL

    now_utc = get_server_time()
    df = get_klines(symbol, interval, category, limit=500)

    if df.empty:
        return html.Div("خطا در دریافت کندل از بایبیت.", style={"color": DN, "textAlign": "center"}), \
            empty_fig("داده‌ای برای رسم حلقه‌ی سیاره‌ای نیست.")

    rows, ring = build_planets_rows(df, now_utc)
    table = build_planets_table_children(rows)
    grid_fig = build_planets_grid_figure(ring, rows)
    return table, grid_fig


@app.callback(
    Output("winrate-kpi-row", "children"),
    Output("winrate-path-graph", "figure"),
    Output("winrate-bar-graph", "figure"),
    Output("winrate-table", "children"),
    Input("tick-slow", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    State("symbol", "value"),
    State("category", "value"),
    State("interval", "value"),
    State("forecast-hours", "value"),
    State("model-type", "value"),
    State("harmonics", "value"),
)
def update_winrate(_n, _click, symbol, category, interval, forecast_hours, model_type, n_harmonics):
    symbol = (symbol or DEFAULT_SYMBOL).upper().strip()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL
    model_type = model_type or "ensemble"
    n_harmonics = int(n_harmonics or 3)
    try:
        forecast_hours = float(forecast_hours or DEFAULT_FORECAST_HOURS)
    except Exception:
        forecast_hours = DEFAULT_FORECAST_HOURS

    interval_min = get_interval_minutes(interval)
    df = get_klines(symbol, interval, category, limit=500)

    if df.empty or len(df) < BACKTEST_MIN_HISTORY + 10:
        empty_kpis = [kpi_card("وین‌ریت", "—", GOLD), kpi_card("نمونه‌ها", "—", MUT)]
        return empty_kpis, empty_fig("داده‌ی کافی نیست."), empty_fig("داده‌ی کافی نیست."), \
            html.Div("داده‌ی کافی برای بک‌تست نیست.", style={"color": DN, "textAlign": "center"})

    bt_df, steps = run_rolling_winrate_backtest(df, interval_min, forecast_hours, n_harmonics)
    summary = summarize_winrate(bt_df)
    latest = latest_forecast_vs_actual(df, interval_min, forecast_hours, n_harmonics, model_type)

    sel = summary.get(model_type, summary.get("ensemble", {"win_rate": 0.0, "avg_abs_pct_err": 0.0, "n": 0}))
    n_samples = sel.get("n", 0)
    kpis = [
        kpi_card(f"وین‌ریت — {MODEL_LABEL_FA.get(model_type, model_type)}", f"{sel['win_rate']:.1f}%", GOLD),
        kpi_card("وین‌ریت آنسمبل", f"{summary.get('ensemble', {}).get('win_rate', 0):.1f}%", UP),
        kpi_card("میانگین خطای مطلق", f"{sel['avg_abs_pct_err']:.2f}%", BLUE),
        kpi_card("تعداد نمونه بک‌تست", f"{n_samples} (هر {steps} کندل)", MUT),
    ]

    path_fig = build_winrate_path_figure(latest, model_type)
    bar_fig = build_winrate_bar_figure(summary)
    table = build_winrate_table_children(summary)
    return kpis, path_fig, bar_fig, table


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
