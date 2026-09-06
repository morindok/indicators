# -*- coding: utf-8 -*-
"""
🌌⏰ Bybit Astro-Gann Pro
------------------------------------------------------------------
ساعت نجومی حرفه‌ای Bybit + موتور Confluence حمایت/مقاومت
------------------------------------------------------------------
منابع سطح (هر کدام یک "دسته" مستقل برای امتیاز Confluence):
  • پیووت‌های ساختاری (با فیلتر نویز مبتنی بر ATR)
  • عقربه‌ی واقعی ساعت UTC (تقاطع با اسپیرال قیمت-زمان)
  • ۷ عقربه‌ی نجومی واقعی: خورشید، ماه، عطارد، زهره، مریخ، مشتری، زحل
    (طول دایره‌البروجی زمین‌مرکز واقعی از کتابخانه ephem + پیش‌بینی
     آینده با درنظرگرفتن سرعت زاویه‌ای واقعی هر سیاره)
  • فیبوناچی ریتریسمنت/اکستنشن روی آخرین سوینگ معتبر
  • پیوت پوینت کلاسیک (روزانه)
  • پیوت پوینت کاماریلا (روزانه)
  • پروفایل حجم (POC + HVN/LVN)

⚠️ هشدار روش‌شناختی:
هیچ‌کدام از این روش‌ها (نجومی، گنی، فیبوناچی، پیوت، پروفایل حجم) دقت
تضمین‌شده یا اثبات‌شده‌ی آماری در بازارهای مالی ندارند. آنچه این ابزار
انجام می‌دهد صرفاً "هم‌پوشانی" (Confluence) چند روش تحلیل تکنیکال
مرسوم و غیرمرسوم است تا سطوحی که چند روش مستقل روی آن‌ها توافق دارند
برجسته‌تر نشان داده شوند؛ این به معنای تضمین حرکت قیمت در آن سطوح نیست.
"""

import math
import numpy as np
import pandas as pd
import requests
import ephem
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
CLOCK_HAND_CLR = "#ecf0f1"

DEFAULT_SYMBOL   = "BTCUSDT"
DEFAULT_CATEGORY = "linear"
DEFAULT_INTERVAL = "15"
DEFAULT_PIVOT    = 5
DEFAULT_TURNS    = 3
RATIO            = 4.0
DEG              = np.pi / 180.0
DEFAULT_FORECAST_HOURS = 24
ATR_PERIOD       = 14

# نام، کلاس ephem، رنگ نمایشی و وزن هر سیاره.
# وزن بالاتر = اهمیت بلندمدت‌تر (طبق نظریه‌ی گن، سیارات کندحرکت‌تر
# نشانگر سطوح ساختاری‌تر و پایدارتر هستند).
PLANETS = {
    "خورشید": {"cls": ephem.Sun,     "color": "#f39c12", "weight": 1.30},
    "ماه":    {"cls": ephem.Moon,    "color": "#bdc3c7", "weight": 0.90},
    "عطارد":  {"cls": ephem.Mercury, "color": "#9b59b6", "weight": 0.80},
    "زهره":   {"cls": ephem.Venus,   "color": "#2ecc71", "weight": 0.85},
    "مریخ":   {"cls": ephem.Mars,    "color": "#e67e22", "weight": 1.00},
    "مشتری":  {"cls": ephem.Jupiter, "color": "#3498db", "weight": 1.70},
    "زحل":    {"cls": ephem.Saturn,  "color": "#1abc9c", "weight": 2.00},
}

FIB_RETR = [0.236, 0.382, 0.5, 0.618, 0.786]
FIB_EXT  = [1.272, 1.618, 2.0, 2.618]

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
    """دریافت زمان دقیق UTC از سرور بایبیت (fallback به زمان سیستم)."""
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


def get_prev_daily_hlc(symbol, category):
    """H/L/C آخرین کندل روزانه‌ی *بسته‌شده* برای پیوت کلاسیک/کاماریلا."""
    d = get_klines(symbol, "D", category, limit=3)
    if len(d) < 2:
        return None
    row = d.iloc[-2]
    return float(row["high"]), float(row["low"]), float(row["close"])


# ==============================================================================
# 2) محاسبات نجومی واقعی (خورشید، ماه، سیارات تا زحل)
# ==============================================================================
def get_planet_longitudes(dt_utc):
    """
    طول دایره‌البروجی زمین‌مرکز واقعی هر سیاره در لحظه + سرعت زاویه‌ای
    روزانه (برای تشخیص رجعی/مستقیم و برای پروجکشن آینده دقیق‌تر).
    """
    d0 = ephem.Date(dt_utc)
    d_ref = ephem.Date(dt_utc - timedelta(hours=6))
    out = {}
    for name, info in PLANETS.items():
        try:
            b0 = info["cls"]()
            b0.compute(d0)
            lon0 = math.degrees(float(ephem.Ecliptic(b0, epoch=d0).lon)) % 360.0

            b1 = info["cls"]()
            b1.compute(d_ref)
            lon1 = math.degrees(float(ephem.Ecliptic(b1, epoch=d_ref).lon)) % 360.0

            delta6h = (lon0 - lon1 + 540.0) % 360.0 - 180.0
            speed_per_day = delta6h * 4.0

            out[name] = {
                "lon": lon0,
                "speed_deg_per_day": speed_per_day,
                "retrograde": speed_per_day < 0,
            }
        except Exception:
            out[name] = {"lon": 0.0, "speed_deg_per_day": 0.0, "retrograde": False}
    return out


# ==============================================================================
# 3) ATR + پیووت‌ها (با فیلتر نویز)
# ==============================================================================
def calc_atr(highs, lows, closes, period=ATR_PERIOD):
    highs = np.asarray(highs, dtype=float)
    lows = np.asarray(lows, dtype=float)
    closes = np.asarray(closes, dtype=float)
    if len(highs) < 2:
        return 0.0
    prev_close = np.roll(closes, 1)
    prev_close[0] = closes[0]
    tr = np.maximum(
        highs - lows,
        np.maximum(np.abs(highs - prev_close), np.abs(lows - prev_close)),
    )
    if len(tr) < period:
        return float(np.mean(tr)) if len(tr) else 0.0
    return float(pd.Series(tr).rolling(period).mean().iloc[-1])


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


def find_all_pivots(highs, lows, period, atr_val=0.0, lookback=250, min_atr_mult=0.35):
    """پیووت‌های ساختاری، با فیلتر دامنه‌ی نوسان مبتنی بر ATR برای حذف نویز."""
    highs = np.asarray(highs, dtype=float)
    lows = np.asarray(lows, dtype=float)
    n = len(highs)
    if n < 2 * period + 1:
        return []

    start = max(period, n - lookback)
    end = n - period
    out = []
    min_amp = atr_val * min_atr_mult

    for i in range(start, end):
        w_low = lows[i - period:i + period + 1]
        if lows[i] <= w_low.min() + 1e-12:
            if atr_val <= 0 or (w_low.mean() - lows[i]) >= min_amp:
                out.append({"price": float(lows[i]), "source": "کف", "index": i})

        w_high = highs[i - period:i + period + 1]
        if highs[i] >= w_high.max() - 1e-12:
            if atr_val <= 0 or (highs[i] - w_high.mean()) >= min_amp:
                out.append({"price": float(highs[i]), "source": "سقف", "index": i})

    return out


# ==============================================================================
# 4) هندسه اسپیرال / تقاطع‌های زاویه‌ای
# ==============================================================================
def spiral_intersections(phi_deg, th_max):
    phi = (phi_deg % 360.0) * DEG
    kmax = int(np.floor((th_max - phi) / (2 * np.pi) + 1e-9))
    if kmax < 0:
        return np.empty(0)
    return phi + 2 * np.pi * np.arange(kmax + 1)


def future_theta_intersections(phi_deg, th_start, th_end):
    """تقاطع آینده با زاویه‌ی ثابت (برای عقربه‌ی واقعی ساعت UTC)."""
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


def future_astro_minutes(lon0_deg, speed_deg_per_day, th_max, th_step, interval_min, forecast_minutes):
    """
    تقاطع‌های آینده با زاویه‌ی *متحرک واقعی* یک سیاره (نه زاویه‌ی ثابت).
    w_s: سرعت زاویه‌ای اسپیرال (رادیان/دقیقه) — همیشه مثبت.
    w_p: سرعت زاویه‌ای واقعی سیاره (رادیان/دقیقه) — می‌تواند منفی باشد (رجعی).
    خروجی: آرایه‌ای از "دقیقه‌های آینده" که تقاطع در آن رخ می‌دهد.
    """
    w_s = th_step / max(interval_min, 1e-9)
    w_p = math.radians(speed_deg_per_day) / 1440.0
    rel_w = w_s - w_p
    if abs(rel_w) < 1e-12:
        return np.empty(0)

    phi0 = math.radians(lon0_deg % 360.0)
    base = (phi0 - th_max) % (2 * math.pi)
    step_m = abs(2 * math.pi / rel_w)

    m0 = base / rel_w if rel_w > 0 else (base - 2 * math.pi) / rel_w
    if m0 < 0:
        k = math.ceil(-m0 / step_m)
        m0 += k * step_m

    ms = []
    m = m0
    guard = 0
    while m <= forecast_minutes and guard < 5000:
        if m >= 0:
            ms.append(m)
        m += step_m
        guard += 1
    return np.array(ms)


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
# 5) برازش/پیش‌بینی قیمت روی زاویه (بدون scipy)
# ==============================================================================
def fit_predict_prices(th_hist, prices, th_future, th_max):
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
    lower = last - 5 * rng
    upper = last + 5 * rng
    pred = np.clip(pred, lower, upper)
    return pred


# ==============================================================================
# 6) روش‌های تکمیلی: فیبوناچی / پیوت کلاسیک / کاماریلا / پروفایل حجم
# ==============================================================================
def fibonacci_items(pivots, weight=1.6):
    highs = [p for p in pivots if p["source"] == "سقف"]
    lows = [p for p in pivots if p["source"] == "کف"]
    if not highs or not lows:
        return []

    last_high = max(highs, key=lambda p: p["index"])
    last_low = max(lows, key=lambda p: p["index"])
    hi, lo = last_high["price"], last_low["price"]
    if hi <= lo:
        return []

    diff = hi - lo
    out = []
    for r in FIB_RETR:
        out.append({
            "price": hi - diff * r, "weight": weight,
            "source": f"فیبو ریتریسمنت {r:.3f}", "category": "فیبوناچی",
        })
    for r in FIB_EXT:
        out.append({
            "price": hi + diff * (r - 1), "weight": weight * 0.85,
            "source": f"فیبو اکستنشن {r:.3f}", "category": "فیبوناچی",
        })
        out.append({
            "price": lo - diff * (r - 1), "weight": weight * 0.85,
            "source": f"فیبو اکستنشن {r:.3f}", "category": "فیبوناچی",
        })
    return out


def classic_pivot_items(prev_hlc, weight=1.8):
    if not prev_hlc:
        return []
    ph, pl, pc = prev_hlc
    pp = (ph + pl + pc) / 3.0
    levels = {
        "PP": pp,
        "R1": 2 * pp - pl, "S1": 2 * pp - ph,
        "R2": pp + (ph - pl), "S2": pp - (ph - pl),
        "R3": ph + 2 * (pp - pl), "S3": pl - 2 * (ph - pp),
    }
    return [
        {"price": price, "weight": weight, "source": f"پیوت کلاسیک {lbl}", "category": "پیوت کلاسیک"}
        for lbl, price in levels.items()
    ]


def camarilla_items(prev_hlc, weight=1.7):
    if not prev_hlc:
        return []
    ph, pl, pc = prev_hlc
    rng = ph - pl
    if rng <= 0:
        return []
    factors = {"R1": 1.1 / 12, "R2": 1.1 / 6, "R3": 1.1 / 4, "R4": 1.1 / 2,
               "S1": 1.1 / 12, "S2": 1.1 / 6, "S3": 1.1 / 4, "S4": 1.1 / 2}
    out = []
    for lbl, f in factors.items():
        price = pc + f * rng if lbl.startswith("R") else pc - f * rng
        out.append({"price": price, "weight": weight, "source": f"کاماریلا {lbl}", "category": "کاماریلا"})
    return out


def volume_profile_items(df, bins=48, lookback=300, weight=2.0):
    seg = df.tail(lookback)
    if len(seg) < 10:
        return []
    typical = (seg["high"] + seg["low"] + seg["close"]) / 3.0
    vols = seg["volume"].values
    pmin, pmax = float(seg["low"].min()), float(seg["high"].max())
    if pmax <= pmin:
        return []

    edges = np.linspace(pmin, pmax, bins + 1)
    hist = np.zeros(bins)
    idx = np.clip(np.digitize(typical.values, edges) - 1, 0, bins - 1)
    for i, v in zip(idx, vols):
        hist[i] += v
    centers = (edges[:-1] + edges[1:]) / 2.0

    out = []
    poc_i = int(np.argmax(hist))
    out.append({
        "price": float(centers[poc_i]), "weight": weight * 1.6,
        "source": "POC (نقطه کنترل حجم)", "category": "پروفایل حجم",
    })

    mean_h = float(hist.mean()) if hist.mean() > 0 else 1.0
    for i in range(1, bins - 1):
        if hist[i] > hist[i - 1] and hist[i] > hist[i + 1] and hist[i] > mean_h * 1.3:
            out.append({
                "price": float(centers[i]), "weight": weight,
                "source": "HVN (گره حجم بالا)", "category": "پروفایل حجم",
            })
        elif hist[i] < hist[i - 1] and hist[i] < hist[i + 1] and hist[i] < mean_h * 0.35:
            out.append({
                "price": float(centers[i]), "weight": weight * 0.6,
                "source": "LVN (گره حجم پایین)", "category": "پروفایل حجم",
            })
    return out


# ==============================================================================
# 7) خوشه‌بندی سطوح + امتیاز Confluence واقعی
# ==============================================================================
def merge_cluster_levels(items, live_price, tol_pct):
    valid = [
        it for it in items
        if np.isfinite(it.get("price", np.nan)) and it.get("price", 0) > 0
    ]

    if not valid:
        step = max(abs(live_price) * 0.0015, 1e-9)
        valid = [
            {"price": live_price - step, "weight": 1.0, "source": "Fallback", "category": "Fallback"},
            {"price": live_price + step, "weight": 1.0, "source": "Fallback", "category": "Fallback"},
        ]

    valid.sort(key=lambda x: x["price"])
    clusters = []

    for it in valid:
        price = float(it["price"])
        weight = float(it.get("weight", 1.0))
        source = str(it.get("source", "?"))
        category = str(it.get("category", source))

        if not clusters:
            clusters.append({
                "price": price, "weight": weight,
                "sources": {source}, "categories": {category},
            })
            continue

        last = clusters[-1]
        if abs(price - last["price"]) / max(last["price"], 1e-12) > tol_pct:
            clusters.append({
                "price": price, "weight": weight,
                "sources": {source}, "categories": {category},
            })
        else:
            new_w = last["weight"] + weight
            last["price"] = (last["price"] * last["weight"] + price * weight) / new_w
            last["weight"] = new_w
            last["sources"].add(source)
            last["categories"].add(category)

    for c in clusters:
        c["side"] = "support" if c["price"] < live_price else "resistance"
        c["distance_pct"] = (c["price"] - live_price) / live_price * 100.0
        n_cat = len(c["categories"])
        c["confluence"] = n_cat
        # امتیاز = وزن پایه × (۱ + پاداش هم‌پوشانی چند-روشی) / فاصله از قیمت زنده
        c["score"] = c["weight"] * (1.0 + 0.55 * (n_cat - 1)) / (abs(c["distance_pct"]) + 0.08)

    supports = sorted(
        [c for c in clusters if c["side"] == "support"],
        key=lambda x: abs(x["distance_pct"])
    )
    resistances = sorted(
        [c for c in clusters if c["side"] == "resistance"],
        key=lambda x: abs(x["distance_pct"])
    )

    top = sorted(clusters, key=lambda x: x["score"], reverse=True)[:14]

    if supports and not any(c is supports[0] for c in top):
        top.append(supports[0])
    if resistances and not any(c is resistances[0] for c in top):
        top.append(resistances[0])

    if not any(c["side"] == "support" for c in top):
        top.append({
            "price": live_price * (1 - 0.0015), "weight": 1.0,
            "sources": {"Fallback"}, "categories": {"Fallback"}, "confluence": 1,
            "side": "support", "distance_pct": -0.15, "score": 0.0,
        })
    if not any(c["side"] == "resistance" for c in top):
        top.append({
            "price": live_price * (1 + 0.0015), "weight": 1.0,
            "sources": {"Fallback"}, "categories": {"Fallback"}, "confluence": 1,
            "side": "resistance", "distance_pct": 0.15, "score": 0.0,
        })

    return sorted(top, key=lambda x: x["price"], reverse=True)


# ==============================================================================
# 8) ساخت نمودار اصلی
# ==============================================================================
def build_figure(df, pivot_idx, pivot_type, pivot_price, pivot_period,
                  turns, now_utc, interval_min, prev_hlc,
                  forecast_hours, active_planets, active_methods):
    df_closed = df.iloc[:-1] if len(df) > 2 else df
    seg = df_closed.iloc[pivot_idx:]

    if len(seg) < 2:
        return empty_fig("دادهٔ پس از پیووت کافی نیست."), [], {}, {}

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
    th_step = th_max / (npts - 1)
    forecast_minutes = forecast_hours * 60.0
    th_end = th_max + th_step * (forecast_minutes / interval_min)

    # --- عقربه‌ی واقعی ساعت UTC ---
    hf = now_utc.hour + now_utc.minute / 60 + now_utc.second / 3600
    th_clock = (90 - 30 * hf) % 360

    # --- طول‌های نجومی واقعی لحظه ---
    astro_now = get_planet_longitudes(now_utc)

    try:
        last_closed_time = pd.Timestamp(df_closed.iloc[-1]["ts"]).to_pydatetime()
        last_closed_time = last_closed_time.replace(tzinfo=timezone.utc)
    except Exception:
        last_closed_time = now_utc

    def ths_to_prices(ths):
        if len(ths) == 0:
            return np.empty(0), np.empty(0)
        idxs = ths / th_max * (npts - 1)
        idxs_i = np.clip(np.round(idxs).astype(int), 0, npts - 1)
        return ths, prices[idxs_i]

    # --- تقاطع‌های عقربه‌ی ساعت واقعی ---
    clock_hist_th, clock_hist_p = ths_to_prices(spiral_intersections(th_clock, th_max))
    clock_fut_th = future_theta_intersections(th_clock, th_max, th_end)
    clock_fut_p = fit_predict_prices(th, prices, clock_fut_th, th_max) if len(clock_fut_th) else np.empty(0)

    # --- تقاطع‌های نجومی: تاریخی (زاویه‌ی لحظه) + آینده (با حرکت واقعی سیاره) ---
    astro_hist = {}   # name -> (x, y, theta, price)
    astro_fut = {}    # name -> list of dict(price, theta, time_hit, minutes_ahead)

    items = []

    # پیووت‌های ساختاری
    atr_val = calc_atr(df_closed["high"].values, df_closed["low"].values, df_closed["close"].values)
    structural_pivots = find_all_pivots(
        df_closed["high"].values, df_closed["low"].values, pivot_period,
        atr_val=atr_val, lookback=250,
    )
    if "ساختاری" in active_methods:
        for it in structural_pivots:
            items.append({"price": it["price"], "weight": 2.5, "source": it["source"], "category": "ساختاری"})

    # عقربه‌ی ساعت واقعی
    if "ساعت‌واقعی" in active_methods:
        for p in clock_hist_p:
            items.append({"price": float(p), "weight": 1.5, "source": "تقاطع ساعت UTC", "category": "ساعت‌واقعی"})
        for p in clock_fut_p:
            items.append({"price": float(p), "weight": 1.3, "source": "تقاطع آینده ساعت UTC", "category": "ساعت‌واقعی"})

    # عقربه‌های نجومی
    if "نجومی" in active_methods:
        for name in active_planets:
            info = PLANETS[name]
            lon_now = astro_now[name]["lon"]
            speed = astro_now[name]["speed_deg_per_day"]
            w = info["weight"]

            hist_th, hist_p = ths_to_prices(spiral_intersections(lon_now, th_max))
            hx = r[np.clip(np.round(hist_th / th_max * (npts - 1)).astype(int), 0, npts - 1)] * np.cos(hist_th) if len(hist_th) else np.empty(0)
            hy = r[np.clip(np.round(hist_th / th_max * (npts - 1)).astype(int), 0, npts - 1)] * np.sin(hist_th) if len(hist_th) else np.empty(0)
            astro_hist[name] = (hx, hy, hist_th, hist_p)

            for p in hist_p:
                items.append({"price": float(p), "weight": w * 1.4, "source": f"تقاطع {name}", "category": f"نجومی:{name}"})

            fut_minutes = future_astro_minutes(lon_now, speed, th_max, th_step, interval_min, forecast_minutes)
            fut_list = []
            if len(fut_minutes):
                fut_theta = th_max + (th_step / interval_min) * fut_minutes
                fut_prices = fit_predict_prices(th, prices, fut_theta, th_max)
                for m, th_v, pr in zip(fut_minutes, fut_theta, fut_prices):
                    if not np.isfinite(pr) or pr <= 0:
                        continue
                    t_hit = last_closed_time + timedelta(minutes=float(m))
                    fut_list.append({
                        "price": float(pr), "theta": float(th_v),
                        "time_hit": t_hit, "minutes_ahead": int(m),
                    })
                    items.append({"price": float(pr), "weight": w * 1.1, "source": f"پیش‌بینی {name}", "category": f"نجومی:{name}"})
            astro_fut[name] = fut_list

    # فیبوناچی
    if "فیبوناچی" in active_methods:
        items.extend(fibonacci_items(structural_pivots))

    # پیوت کلاسیک / کاماریلا
    if "پیوت کلاسیک" in active_methods:
        items.extend(classic_pivot_items(prev_hlc))
    if "کاماریلا" in active_methods:
        items.extend(camarilla_items(prev_hlc))

    # پروفایل حجم
    if "پروفایل حجم" in active_methods:
        items.extend(volume_profile_items(df))

    # اگر هیچ منبع آینده‌ای وجود نداشت، یک شبکه‌ی کمکی اضافه شود (fallback ایمنی)
    has_future_source = any(
        c in {"ساعت‌واقعی"} or c.startswith("نجومی:") for c in {it.get("category", "") for it in items}
    )
    if not has_future_source:
        num = min(int(forecast_minutes / interval_min), 80)
        if num > 0:
            grid_th = np.linspace(th_max + th_step, th_end, num)
            grid_p = fit_predict_prices(th, prices, grid_th, th_max)
            for p in grid_p:
                items.append({"price": float(p), "weight": 1.0, "source": "شبکه آینده", "category": "شبکه"})

    # فاصله‌ی خوشه‌بندی داینامیک بر اساس نوسان (ATR)
    tol_pct = float(np.clip((atr_val / max(live_price, 1e-9)) * 0.6, 0.0008, 0.006)) if atr_val > 0 else 0.0015

    levels = merge_cluster_levels(items, live_price, tol_pct=tol_pct)

    # ==========================================================================
    # ساخت Figure
    # ==========================================================================
    fig = make_subplots(rows=2, cols=1, row_heights=[0.68, 0.32], vertical_spacing=0.09)
    ang = np.linspace(0, 2 * np.pi, 360)

    for frac in (0.25, 0.5, 0.75):
        fig.add_trace(go.Scatter(
            x=frac * R * np.cos(ang), y=frac * R * np.sin(ang),
            mode="lines", line=dict(color=LINE, width=1),
            showlegend=False, hoverinfo="skip",
        ), row=1, col=1)

    for dd in range(0, 360, 30):
        fig.add_trace(go.Scatter(
            x=[0, R * np.cos(dd * DEG)], y=[0, R * np.sin(dd * DEG)],
            mode="lines", line=dict(color=LINE, width=1, dash="dot"),
            showlegend=False, hoverinfo="skip",
        ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=R * np.cos(ang), y=R * np.sin(ang),
        mode="lines", line=dict(color=GOLD, width=3), name="دایره ساعت",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=r * np.cos(th), y=r * np.sin(th),
        mode="lines", line=dict(color=SPIRAL_CLR, width=2, dash="dot"),
        showlegend=False, hoverinfo="skip",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=r * np.cos(th), y=r * np.sin(th),
        mode="markers",
        marker=dict(
            size=5, color=prices, colorscale="Viridis", showscale=True,
            colorbar=dict(title="قیمت", thickness=12, len=0.55, y=0.78,
                          tickfont=dict(color=TXT, size=10)),
            line=dict(width=0.4, color="#000"),
        ),
        customdata=np.column_stack([
            np.degrees(th), prices, pd.to_datetime(times).strftime("%m-%d %H:%M"),
        ]),
        hovertemplate="θ=%{customdata[0]:.1f}°<br>قیمت=%{customdata[1]:.6g}<br>%{customdata[2]}<extra>کندل</extra>",
        name="قیمت از پیووت تا لایو",
    ), row=1, col=1)

    live_x, live_y = R * np.cos(th_max), R * np.sin(th_max)
    fig.add_trace(go.Scatter(
        x=[live_x], y=[live_y], mode="markers+text",
        marker=dict(size=14, symbol="star", color=GOLD, line=dict(width=1.5, color="black")),
        text=[f"LIVE: {live_price:.4g}"], textposition="top right",
        textfont=dict(color=GOLD, size=11), name=f"کندل لایو = {live_price:.4g}",
    ), row=1, col=1)

    piv_x, piv_y = r[0] * np.cos(th[0]), r[0] * np.sin(th[0])
    fig.add_trace(go.Scatter(
        x=[piv_x], y=[piv_y], mode="markers+text",
        marker=dict(size=12, symbol="square", color=UP, line=dict(width=1.5, color="black")),
        text=[f"PIVOT ({pivot_type}): {pivot_price:.4g}"], textposition="bottom left",
        textfont=dict(color=UP, size=11), name="آخرین پیووت",
    ), row=1, col=1)

    for h in range(1, 13):
        phi = (90 - 30 * h) * DEG
        c, s = np.cos(phi), np.sin(phi)
        fig.add_trace(go.Scatter(
            x=[0.94 * R * c, R * c], y=[0.94 * R * s, R * s],
            mode="lines", line=dict(color=GOLD, width=2),
            showlegend=False, hoverinfo="skip",
        ), row=1, col=1)
        fig.add_annotation(
            x=1.08 * R * c, y=1.08 * R * s, text=f"<b>{h}</b>",
            showarrow=False, font=dict(size=14, color=GOLD), row=1, col=1,
        )

    # عقربه‌ی ساعت واقعی
    c, s = np.cos(th_clock * DEG), np.sin(th_clock * DEG)
    fig.add_trace(go.Scatter(
        x=[0, 0.97 * R * c], y=[0, 0.97 * R * s],
        mode="lines", line=dict(color=CLOCK_HAND_CLR, width=4), name="عقربه ساعت واقعی UTC",
    ), row=1, col=1)
    fig.add_annotation(
        x=0.78 * R * c, y=0.78 * R * s, text=f"UTC θ={th_clock:.1f}°",
        showarrow=False, font=dict(size=11, color=CLOCK_HAND_CLR),
        bgcolor="rgba(11,18,32,0.8)", bordercolor=CLOCK_HAND_CLR, borderwidth=1, borderpad=3,
        row=1, col=1,
    )

    # عقربه‌های نجومی
    if "نجومی" in active_methods:
        for name in active_planets:
            info = PLANETS[name]
            lon = astro_now[name]["lon"]
            retro = astro_now[name]["retrograde"]
            c, s = np.cos(lon * DEG), np.sin(lon * DEG)
            fig.add_trace(go.Scatter(
                x=[0, 0.9 * R * c], y=[0, 0.9 * R * s],
                mode="lines", line=dict(color=info["color"], width=2.5),
                name=f"{name}{' (رجعی)' if retro else ''}",
            ), row=1, col=1)
            fig.add_annotation(
                x=0.62 * R * c, y=0.62 * R * s, text=f"{name} {lon:.1f}°",
                showarrow=False, font=dict(size=9, color=info["color"]),
                bgcolor="rgba(11,18,32,0.75)", bordercolor=info["color"], borderwidth=1, borderpad=2,
                row=1, col=1,
            )

        # تقاطع‌های تاریخی نجومی (تجمیع‌شده، رنگ بر اساس سیاره)
        all_hx, all_hy, all_hp, all_hname = [], [], [], []
        for name, (hx, hy, hth, hp) in astro_hist.items():
            all_hx.extend(hx.tolist()); all_hy.extend(hy.tolist())
            all_hp.extend(hp.tolist()); all_hname.extend([name] * len(hp))

        if all_hx:
            colors = [PLANETS[n]["color"] for n in all_hname]
            fig.add_trace(go.Scatter(
                x=all_hx, y=all_hy, mode="markers",
                marker=dict(size=9, symbol="star", color=colors, line=dict(width=1, color="white")),
                customdata=np.column_stack([all_hname, [f"{p:.4g}" for p in all_hp]]),
                hovertemplate="سیاره: %{customdata[0]}<br>قیمت=%{customdata[1]}<extra>تقاطع نجومی</extra>",
                name="تقاطع نجومی (تاریخی)",
            ), row=1, col=1)

        # نمایش نزدیک‌ترین نقاط پیش‌بینی نجومی روی لبه‌ی دایره
        fut_markers = []
        for name, lst in astro_fut.items():
            for p in lst:
                fut_markers.append((name, p))
        fut_markers = sorted(fut_markers, key=lambda x: abs(x[1]["price"] - live_price))[:12]

        for name, p in fut_markers:
            ang_f = p["theta"] % (2 * np.pi)
            x_f, y_f = R * np.cos(ang_f), R * np.sin(ang_f)
            color = UP if p["price"] < live_price else DN
            fig.add_trace(go.Scatter(
                x=[x_f], y=[y_f], mode="markers+text",
                marker=dict(size=10, symbol="diamond", color=color, line=dict(width=1, color="white")),
                text=[f"{p['price']:.0f}"], textposition="top center",
                textfont=dict(color=color, size=8),
                hovertemplate=(
                    f"پیش‌بینی نجومی ({name})<br>قیمت={p['price']:.6g}<br>"
                    f"زمان={p['time_hit'].strftime('%m-%d %H:%M')} UTC<extra></extra>"
                ),
                name="پیش‌بینی نجومی", showlegend=False,
            ), row=1, col=1)

    # ==========================================================================
    # پنل پایین: چارت قیمت + خطوط Confluence
    # ==========================================================================
    df_plot = df.tail(180).reset_index(drop=True)
    x_end = max(1, len(df_plot) - 1)

    fig.add_trace(go.Scatter(
        x=list(range(len(df_plot))), y=df_plot["close"].values,
        mode="lines", line=dict(color=SPIRAL_CLR, width=2), name="قیمت",
    ), row=2, col=1)

    for lvl in levels:
        color = UP if lvl["side"] == "support" else DN
        tag = "S" if lvl["side"] == "support" else "R"
        width = 1.4 + min(lvl["confluence"], 5) * 0.5

        fig.add_shape(
            type="line", xref="x2", yref="y2",
            x0=0, x1=x_end, y0=lvl["price"], y1=lvl["price"],
            line=dict(color=color, width=width, dash="dash"), opacity=0.9,
        )
        fig.add_annotation(
            xref="x2", yref="y2", x=x_end, y=lvl["price"],
            text=f"{tag} {lvl['price']:.2f} (×{lvl['confluence']})",
            showarrow=False, xanchor="right", yanchor="bottom",
            font=dict(color=color, size=10),
            bgcolor="rgba(11,18,32,0.85)", bordercolor=color, borderwidth=1, borderpad=2,
        )

    plot_prices = list(df_plot["close"].values) + [lvl["price"] for lvl in levels]
    y_min, y_max = float(np.min(plot_prices)), float(np.max(plot_prices))
    y_pad = max((y_max - y_min) * 0.08, abs(live_price) * 0.0008)
    lim = 1.45 * R

    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
        legend=dict(bgcolor="rgba(11,18,32,0.8)", font=dict(size=9),
                    orientation="h", y=-0.12, x=0.5, xanchor="center"),
        margin=dict(l=10, r=10, t=70, b=10),
        title=dict(
            text=(f"🌌 ساعت نجومی حرفه‌ای + Confluence — "
                  f"{now_utc.strftime('%H:%M:%S')} UTC | افق: {forecast_hours:.0f}h"),
            x=0.5, font=dict(color=GOLD, size=15),
        ),
    )
    fig.update_xaxes(range=[-lim, lim], visible=False, row=1, col=1)
    fig.update_yaxes(range=[-lim, lim], visible=False, scaleanchor="x", scaleratio=1, row=1, col=1)
    fig.update_xaxes(range=[0, x_end], visible=False, row=2, col=1)
    fig.update_yaxes(range=[y_min - y_pad, y_max + y_pad], gridcolor=LINE,
                      tickfont=dict(size=10, color=MUT), title_text="قیمت", row=2, col=1)

    return fig, levels, astro_now, astro_fut


def empty_fig(msg):
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    fig.add_annotation(x=0.5, y=0.5, xref="paper", yref="paper", text=msg,
                        showarrow=False, font=dict(size=18, color=DN))
    return fig


# ==============================================================================
# 9) کمک‌توابع نمایش کارتی سطوح (رابط کاربری خوانا برای S/R)
# ==============================================================================
_METHOD_COLORS = {
    "ساختاری": GOLD,
    "ساعت‌واقعی": CLOCK_HAND_CLR,
    "فیبوناچی": "#9b59b6",
    "پیوت کلاسیک": "#3498db",
    "کاماریلا": "#e67e22",
    "پروفایل حجم": "#2ecc71",
    "شبکه": MUT,
    "Fallback": MUT,
}


def category_color(cat):
    if cat.startswith("نجومی:"):
        name = cat.split(":", 1)[1]
        return PLANETS.get(name, {}).get("color", GOLD)
    return _METHOD_COLORS.get(cat, MUT)


def category_label(cat):
    return cat.split(":", 1)[1] if cat.startswith("نجومی:") else cat


def confluence_tier(n):
    """سطح‌بندی قدرت هم‌پوشانی برای نمایش رنگی/برچسبی."""
    if n >= 7:
        return "بسیار قوی 🔥", "#f1c40f"
    if n >= 4:
        return "قوی", "#3498db"
    if n >= 2:
        return "متوسط", "#7f8c9a"
    return "ضعیف", "#4a5568"


def level_to_dict(c):
    """تبدیل خوشه‌ی سطح به دیکشنری قابل ذخیره در dcc.Store (JSON-safe)."""
    return {
        "price": round(float(c["price"]), 6),
        "side": c["side"],
        "distance_pct": round(float(c["distance_pct"]), 4),
        "confluence": int(c["confluence"]),
        "categories": sorted(c["categories"]),
        "score": round(float(c["score"]), 4),
    }


def build_level_card(c):
    """یک کارت رنگی و خوانا برای یک سطح حمایت/مقاومت."""
    side_color = UP if c["side"] == "support" else DN
    tier_label, tier_color = confluence_tier(c["confluence"])

    badges = [
        dbc.Badge(
            category_label(cat),
            style={
                "backgroundColor": category_color(cat),
                "color": "#0b1220",
                "marginLeft": "4px",
                "marginBottom": "4px",
                "fontSize": "10px",
                "fontWeight": "600",
            },
        )
        for cat in c["categories"]
    ]

    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.Div([
                    html.Span(f"{c['price']:.2f}", style={
                        "fontSize": "19px", "fontWeight": "bold", "color": side_color,
                    }),
                    html.Span(f"  ({c['distance_pct']:+.2f}%)", style={
                        "fontSize": "12px", "color": MUT, "marginRight": "6px",
                    }),
                ]),
                dbc.Badge(f"همگرایی ×{c['confluence']} — {tier_label}", style={
                    "backgroundColor": tier_color, "color": "#0b1220",
                    "fontSize": "10px", "fontWeight": "700", "padding": "5px 8px",
                }),
            ], style={
                "display": "flex", "justifyContent": "space-between",
                "alignItems": "center", "flexWrap": "wrap", "gap": "6px",
            }),
            html.Div(badges, style={
                "marginTop": "9px", "display": "flex", "flexWrap": "wrap",
                "gap": "2px", "direction": "rtl",
            }),
        ]),
        style={
            "backgroundColor": CARD, "border": f"1px solid {LINE}",
            "borderRight": f"4px solid {side_color}",
            "marginBottom": "9px", "borderRadius": "8px",
        },
    )


def render_level_cards(levels_data, side, sort_mode, min_conf):
    items = [c for c in levels_data if c["side"] == side and c["confluence"] >= (min_conf or 1)]
    if sort_mode == "distance":
        items.sort(key=lambda x: abs(x["distance_pct"]))
    elif sort_mode == "price":
        items.sort(key=lambda x: x["price"], reverse=True)
    else:
        items.sort(key=lambda x: -x["score"])

    if not items:
        return [html.Div(
            "هیچ سطحی با این فیلتر پیدا نشد؛ حداقل همگرایی را کم کنید.",
            style={"color": MUT, "textAlign": "center", "padding": "24px", "fontSize": 12},
        )]
    return [build_level_card(c) for c in items]


# ==============================================================================
# 10) اپ Dash
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])
app.title = "Bybit Astro-Gann Pro"
server = app.server

CATEGORY_OPTS = [{"label": v, "value": v} for v in ["linear", "spot", "inverse"]]
INTERVAL_OPTS = [{"label": lbl, "value": val} for lbl, val in [
    ("1m", "1"), ("3m", "3"), ("5m", "5"), ("15m", "15"),
    ("30m", "30"), ("1h", "60"), ("4h", "240"), ("1D", "D"),
]]
PLANET_OPTS = [{"label": name, "value": name} for name in PLANETS.keys()]
METHOD_OPTS = [{"label": m, "value": m} for m in
               ["ساختاری", "ساعت‌واقعی", "نجومی", "فیبوناچی", "پیوت کلاسیک", "کاماریلا", "پروفایل حجم"]]

app.layout = html.Div([
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([
            html.Label("نماد", style={"fontSize": 11, "color": MUT}),
            dcc.Input(id="symbol", value=DEFAULT_SYMBOL, type="text",
                      style={"width": "100%", "padding": 6, "borderRadius": 6})
        ], md=2),
        dbc.Col([
            html.Label("بازار", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="category", value=DEFAULT_CATEGORY, clearable=False, options=CATEGORY_OPTS)
        ], md=2),
        dbc.Col([
            html.Label("تایم‌فریم", style={"fontSize": 11, "color": MUT}),
            dcc.Dropdown(id="interval", value=DEFAULT_INTERVAL, clearable=False, options=INTERVAL_OPTS)
        ], md=2),
        dbc.Col([
            html.Label("دوره پیووت", style={"fontSize": 11, "color": MUT}),
            dcc.Input(id="pivot-period", type="number", value=DEFAULT_PIVOT, min=2, max=50, step=1,
                      style={"width": "100%", "padding": 6, "borderRadius": 6})
        ], md=1),
        dbc.Col([
            html.Label("دور اسپیرال", style={"fontSize": 11, "color": MUT}),
            dcc.Input(id="turns", type="number", value=DEFAULT_TURNS, min=1, max=12, step=1,
                      style={"width": "100%", "padding": 6, "borderRadius": 6})
        ], md=1),
        dbc.Col([
            html.Label("افق (ساعت)", style={"fontSize": 11, "color": MUT}),
            dcc.Input(id="forecast-hours", type="number", value=DEFAULT_FORECAST_HOURS, min=1, max=240, step=1,
                      style={"width": "100%", "padding": 6, "borderRadius": 6})
        ], md=1),
        dbc.Col(
            dbc.Button("🔄 بروزرسانی", id="refresh-btn", color="warning", className="mt-3",
                       style={"fontWeight": "bold", "color": BG, "width": "100%"}),
            md=1
        ),
        dbc.Col(html.Div(id="conn-status",
                         style={"color": MUT, "fontSize": 11, "marginTop": 22, "textAlign": "center"}), md=1),
    ])), style={"maxWidth": 1500, "margin": "10px auto"}),

    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([
            html.Label("سیارات فعال", style={"fontSize": 11, "color": MUT}),
            dcc.Checklist(id="planets-checklist", options=PLANET_OPTS,
                          value=list(PLANETS.keys()), inline=True,
                          inputStyle={"marginLeft": "5px", "marginRight": "3px"},
                          style={"color": TXT, "fontSize": 12}),
        ], md=6),
        dbc.Col([
            html.Label("روش‌های تحلیلی فعال", style={"fontSize": 11, "color": MUT}),
            dcc.Checklist(id="methods-checklist", options=METHOD_OPTS,
                          value=[m["value"] for m in METHOD_OPTS], inline=True,
                          inputStyle={"marginLeft": "5px", "marginRight": "3px"},
                          style={"color": TXT, "fontSize": 12}),
        ], md=6),
    ])), style={"maxWidth": 1500, "margin": "0px auto 10px auto"}),

    dbc.Row([
        dbc.Col(dcc.Graph(id="spiral-plot", style={"height": "80vh"}, config={"displaylogo": False}), width=9),

        dbc.Col([
            # --- کارت کوچک وضعیت بازار/پیووت ---
            dbc.Card([
                dbc.CardHeader("💹 بازار و پیووت", style={"fontSize": 12, "color": GOLD, "fontWeight": "bold"}),
                dbc.CardBody(html.Div(id="market-info", style={"fontSize": 12, "color": TXT, "direction": "rtl"})),
            ], style={"marginBottom": 10, "backgroundColor": CARD, "border": f"1px solid {LINE}"}),

            # --- کارت موقعیت نجومی ---
            dbc.Card([
                dbc.CardHeader("🪐 موقعیت نجومی لحظه", style={"fontSize": 12, "color": GOLD, "fontWeight": "bold"}),
                dbc.CardBody(html.Div(id="astro-info", style={"direction": "rtl"})),
            ], style={"marginBottom": 10, "backgroundColor": CARD, "border": f"1px solid {LINE}"}),

            # --- کارت اصلی: سطوح Confluence با تب/فیلتر/مرتب‌سازی ---
            dbc.Card([
                dbc.CardHeader("📊 حمایت / مقاومت — سیستم Confluence",
                               style={"fontSize": 13, "color": GOLD, "fontWeight": "bold"}),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            html.Label("مرتب‌سازی", style={"fontSize": 10, "color": MUT}),
                            dcc.Dropdown(
                                id="sort-mode",
                                options=[
                                    {"label": "قدرت Confluence (پیشنهادی)", "value": "score"},
                                    {"label": "نزدیک‌ترین به قیمت زنده", "value": "distance"},
                                    {"label": "قیمت (نزولی)", "value": "price"},
                                ],
                                value="score", clearable=False,
                                style={"fontSize": 11, "color": "#000"},
                            ),
                        ], md=7),
                        dbc.Col([
                            html.Label(id="min-confluence-label",
                                       children="حداقل همگرایی: ۱", style={"fontSize": 10, "color": MUT}),
                            dcc.Slider(id="min-confluence", min=1, max=10, step=1, value=1,
                                       marks=None, tooltip={"placement": "bottom", "always_visible": False}),
                        ], md=5),
                    ], className="mb-2"),

                    dbc.Tabs([
                        dbc.Tab(
                            html.Div(id="support-cards", style={
                                "maxHeight": "48vh", "overflowY": "auto", "paddingTop": 8,
                            }),
                            label="🟢 حمایت‌ها", tab_id="tab-support",
                            label_style={"color": UP, "fontSize": 12},
                        ),
                        dbc.Tab(
                            html.Div(id="resistance-cards", style={
                                "maxHeight": "48vh", "overflowY": "auto", "paddingTop": 8,
                            }),
                            label="🔴 مقاومت‌ها", tab_id="tab-resistance",
                            label_style={"color": DN, "fontSize": 12},
                        ),
                    ], id="sr-tabs", active_tab="tab-resistance"),

                    html.Div(
                        "⚠️ این سطوح بر پایه‌ی هم‌پوشانی چند روش تحلیل تکنیکال/نجومی هستند "
                        "(بدون اعتبار آماری اثبات‌شده) — نه پیش‌بینی قطعی قیمت.",
                        style={"fontSize": 10, "color": MUT, "marginTop": 10, "direction": "rtl",
                               "borderTop": f"1px solid {LINE}", "paddingTop": 8},
                    ),
                ]),
            ], style={"backgroundColor": CARD, "border": f"1px solid {LINE}"}),
        ], width=3),
    ], style={"maxWidth": 1500, "margin": "0 auto"}),

    dcc.Store(id="levels-store"),
    dcc.Interval(id="tick", interval=20_000, n_intervals=0),
], style={"background": BG, "minHeight": "100vh", "padding": "10px"})


# ==============================================================================
# 10) کال‌بک اصلی
# ==============================================================================
@app.callback(
    Output("spiral-plot", "figure"),
    Output("levels-store", "data"),
    Output("market-info", "children"),
    Output("astro-info", "children"),
    Output("conn-status", "children"),
    Output("min-confluence", "max"),
    Input("tick", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    State("symbol", "value"),
    State("interval", "value"),
    State("category", "value"),
    State("pivot-period", "value"),
    State("turns", "value"),
    State("forecast-hours", "value"),
    State("planets-checklist", "value"),
    State("methods-checklist", "value"),
)
def update(_n, _click, symbol, interval, category, pivot_period, turns,
           forecast_hours, active_planets, active_methods):
    try:
        pivot_period = int(pivot_period or DEFAULT_PIVOT)
        turns = int(turns or DEFAULT_TURNS)
        forecast_hours = float(forecast_hours or DEFAULT_FORECAST_HOURS)
    except Exception:
        pivot_period, turns, forecast_hours = DEFAULT_PIVOT, DEFAULT_TURNS, DEFAULT_FORECAST_HOURS

    active_planets = active_planets or list(PLANETS.keys())
    active_methods = active_methods or [m["value"] for m in METHOD_OPTS]

    symbol = (symbol or DEFAULT_SYMBOL).upper().strip()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL

    now_utc = get_server_time()
    df = get_klines(symbol, interval, category, limit=500)

    if df.empty:
        status = "🔴 قطع از بایبیت"
        err = html.Div("خطا در دریافت کندل از بایبیت.", style={"color": DN, "fontSize": 12})
        return empty_fig("دریافت دیتا از بایبیت ناموفق بود."), [], err, "", status, 10

    prev_hlc = get_prev_daily_hlc(symbol, category)

    pivot_idx, pivot_type, pivot_price = find_last_pivot(
        df["high"].values, df["low"].values, pivot_period
    )
    interval_min = get_interval_minutes(interval)

    fig, levels, astro_now, astro_fut = build_figure(
        df=df, pivot_idx=pivot_idx, pivot_type=pivot_type, pivot_price=pivot_price,
        pivot_period=pivot_period, turns=turns, now_utc=now_utc, interval_min=interval_min,
        prev_hlc=prev_hlc, forecast_hours=forecast_hours,
        active_planets=active_planets, active_methods=active_methods,
    )

    live_price = float(df.iloc[-1]["close"])
    pivot_time = df.iloc[pivot_idx]["ts"].strftime("%Y-%m-%d %H:%M")
    pivot_label = {"low": "کف", "high": "سقف", "none": "نامشخص"}.get(pivot_type, "—")

    # --- کارت بازار/پیووت ---
    market_info = html.Div([
        html.Div(f"⏰ {now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC", style={"marginBottom": 4}),
        html.Div([html.Span("نماد: ", style={"color": MUT}), html.Span(f"{symbol} | {category} | {interval}")],
                 style={"marginBottom": 4}),
        html.Div([html.Span("قیمت لایو: ", style={"color": MUT}),
                  html.Span(f"{live_price:.6g}", style={"color": GOLD, "fontWeight": "bold"})],
                 style={"marginBottom": 6}),
        html.Div([html.Span("پیووت: ", style={"color": MUT}),
                  html.Span(f"{pivot_label} {pivot_price:.6g}"),
                  html.Span(f"  ({pivot_time} UTC)", style={"color": MUT, "fontSize": 10})]),
    ])

    # --- کارت موقعیت نجومی (ردیف‌های رنگی) ---
    astro_rows = []
    for name in active_planets:
        a = astro_now.get(name, {})
        color = PLANETS.get(name, {}).get("color", MUT)
        row = [
            html.Span("● ", style={"color": color}),
            html.Span(f"{name}: ", style={"fontWeight": "bold"}),
            html.Span(f"{a.get('lon', 0):.2f}°", style={"color": MUT}),
        ]
        if a.get("retrograde"):
            row.append(dbc.Badge("رجعی ⟲", style={
                "backgroundColor": DN, "color": "#fff", "fontSize": "9px", "marginRight": "6px",
            }))
        astro_rows.append(html.Div(row, style={"fontSize": 12, "marginBottom": 4}))
    astro_info = html.Div(astro_rows) if astro_rows else html.Div(
        "هیچ سیاره‌ای فعال نیست.", style={"color": MUT, "fontSize": 12})

    # --- سطوح Confluence به‌صورت JSON-safe برای ذخیره و رندر جدا (بدون نیاز به fetch مجدد) ---
    levels_data = [level_to_dict(c) for c in levels]
    max_conf = max([c["confluence"] for c in levels_data], default=1)

    status = f"🟢 متصل به سرور | {now_utc.strftime('%H:%M:%S')} UTC"
    return fig, levels_data, market_info, astro_info, status, max(int(max_conf), 1)


@app.callback(
    Output("support-cards", "children"),
    Output("resistance-cards", "children"),
    Output("min-confluence-label", "children"),
    Input("levels-store", "data"),
    Input("sort-mode", "value"),
    Input("min-confluence", "value"),
)
def render_level_panels(levels_data, sort_mode, min_conf):
    """
    رندر کارت‌های حمایت/مقاومت مستقیماً از داده‌ی ذخیره‌شده — با تغییر
    مرتب‌سازی یا فیلتر، دوباره از بایبیت داده نمی‌گیرد، فقط بازچینی می‌شود.
    """
    levels_data = levels_data or []
    min_conf = min_conf or 1
    label = f"حداقل همگرایی: ×{min_conf}"

    support_children = render_level_cards(levels_data, "support", sort_mode, min_conf)
    resistance_children = render_level_cards(levels_data, "resistance", sort_mode, min_conf)
    return support_children, resistance_children, label


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8070, use_reloader=False)