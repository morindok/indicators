# -*- coding: utf-8 -*-
"""
مهندسی ویژگی برای شبکه عصبی:
  - 12 ویژگی تکنیکال کلاسیک (هم‌خانواده با نسخه Pine Script)
  - 3 ویژگی «شبکه تار عنکبوتی» (تحلیل تراکم حجم در گرید قیمتی)
  - 3 ویژگی تعاملی غیرخطی
همه‌چیز با pandas/numpy به‌صورت برداری محاسبه می‌شود تا برای داده زنده سریع باشد.
تمام مقادیر نهایی با tanh به بازه [-1, 1] فشرده و در برابر NaN/Inf ایمن می‌شوند.
"""

import numpy as np
import pandas as pd

EPS = 1e-6
FEATURE_NAMES = [f"f{i}" for i in range(1, 13)] + ["g1", "g2", "g3"] + ["i13", "i14", "i15"]
N_FEATURES = len(FEATURE_NAMES)


def _safe_tanh(x):
    x = np.clip(np.nan_to_num(x.astype(float), nan=0.0, posinf=0.0, neginf=0.0), -10, 10)
    return np.tanh(x)


def _rsi_like_stoch(close, high, low, length=14):
    hh = high.rolling(length).max()
    ll = low.rolling(length).min()
    denom = (hh - ll).clip(lower=EPS)
    return (close - ll) / denom * 100.0


def _cci(tp, length=20):
    sma = tp.rolling(length).mean()
    mad = tp.rolling(length).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    return (tp - sma) / (0.015 * mad.clip(lower=EPS))


def _mfi(high, low, close, volume, length=14):
    tp = (high + low + close) / 3.0
    raw_flow = tp * volume
    direction = np.sign(tp.diff())
    pos_flow = raw_flow.where(direction > 0, 0.0).rolling(length).sum()
    neg_flow = raw_flow.where(direction < 0, 0.0).rolling(length).sum().clip(lower=EPS)
    mfr = pos_flow / neg_flow
    return 100.0 - (100.0 / (1.0 + mfr))


def _session_vwap(df, high, low, close, volume):
    tp = (high + low + close) / 3.0
    day = df["timestamp"].dt.date
    cum_pv = (tp * volume).groupby(day).cumsum()
    cum_v = volume.groupby(day).cumsum().clip(lower=EPS)
    return cum_pv / cum_v


def compute_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    ورودی: دیتافریم با ستون‌های timestamp, open, high, low, close, volume
    خروجی: همان دیتافریم + ستون‌های f1..f12 (خام، قبل از tanh)
    از close/high/low/volume شیفت‌خورده (کندل بسته‌شده قبلی) استفاده می‌شود تا ریپینت نداشته باشیم.
    """
    out = df.copy()
    c = out["close"].shift(1)
    h = out["high"].shift(1)
    l = out["low"].shift(1)
    v = out["volume"].shift(1)

    atr14 = (out["high"] - out["low"]).rolling(14).mean().shift(1).clip(lower=EPS)
    stdev_v20 = v.rolling(20).std().clip(lower=EPS)
    sma_c10 = c.rolling(10).mean()
    sma_c20 = c.rolling(20).mean().clip(lower=EPS)
    sma_c5 = c.rolling(5).mean()
    sma_v20 = v.rolling(20).mean()
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    hh14 = out["high"].rolling(14).max()
    ll14 = out["low"].rolling(14).min()
    hh_ll_diff = (hh14 - ll14).clip(lower=EPS)
    tp = (h + l + c) / 3.0

    out["f1"] = (c - sma_c10) / atr14
    out["f2"] = (h - l) / atr14
    out["f3"] = (v - sma_v20) / stdev_v20
    out["f4"] = _mfi(h, l, c, v, 14) / 100.0
    out["f5"] = (ema12 - ema26) / atr14
    out["f6"] = _rsi_like_stoch(c, h, l, 14) / 100.0
    willr = (hh14 - c) / hh_ll_diff * -100.0
    out["f7"] = willr / -100.0
    out["f8"] = _cci(tp, 20) / 200.0
    out["f9"] = c.pct_change(10) * 10.0
    vwap = _session_vwap(out, h, l, c, v)
    out["f10"] = (c - vwap.fillna(c)) / atr14
    out["f11"] = sma_c5 / sma_c20 - 1.0
    out["f12"] = (h + l + c) / 3.0 / c.clip(lower=EPS) - 1.0
    return out


def compute_grid_features(df: pd.DataFrame, grid_size=20, grid_lookback=50) -> pd.DataFrame:
    """
    ویژگی‌های «شبکه تار عنکبوتی»: تراکم حجم معامله‌شده در سطوح مختلف قیمتی
    اطراف قیمت فعلی، و بایاس کلی آن به سمت حمایت یا مقاومت.
    برای پرفورمنس، فقط با یک حلقه ساده numpy روی طول تاریخچه محاسبه می‌شود
    (برای چند صد تا چند هزار کندل در حد میلی‌ثانیه است).
    """
    n = len(df)
    close = df["close"].to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    volume = df["volume"].to_numpy()
    atr14 = pd.Series(high - low).rolling(14).mean().to_numpy()

    grid_bias = np.full(n, np.nan)
    density_anomaly = np.full(n, np.nan)
    position_in_grid = np.full(n, np.nan)

    half = grid_size // 2
    for t in range(grid_lookback + 1, n):
        atr_val = atr14[t] if not np.isnan(atr14[t]) and atr14[t] > 0 else 1.0
        grid_step = max(atr_val * 0.5, EPS)
        center = np.mean(close[max(0, t - 50):t]) if t >= 1 else close[t]

        window_close = close[t - grid_lookback:t]
        window_vol = volume[t - grid_lookback:t]

        activities = np.zeros(grid_size + 1)
        for gi, i in enumerate(range(-half, half + 1)):
            level = center + i * grid_step
            mask = np.abs(window_close - level) < grid_step * 0.3
            activities[gi] = window_vol[mask].sum() / 1000.0

        total_act = activities.sum()
        if total_act > 0:
            idxs = np.arange(len(activities)) - half
            grid_bias[t] = float(np.sum(activities * idxs) / total_act)
        else:
            grid_bias[t] = 0.0

        local_density = activities[half]
        avg_density = activities.mean() if len(activities) else 0.0
        density_anomaly[t] = (local_density - avg_density) / max(avg_density, EPS)
        position_in_grid[t] = (close[t] - center) / (grid_step * max(half, 1))

    out = df.copy()
    out["grid_bias_raw"] = grid_bias
    out["g1"] = grid_bias / (grid_size / 2.0)
    out["g2"] = density_anomaly
    out["g3"] = position_in_grid
    return out


def build_feature_matrix(df: pd.DataFrame, grid_size=20, grid_lookback=50) -> pd.DataFrame:
    """
    تابع اصلی: از دیتافریم خام OHLCV، ماتریس ویژگی نهایی (18 ستون) می‌سازد.
    خروجی شامل ستون‌های خام f1..f12, g1..g3 و نسخه فشرده‌شده با tanh (پیشوند t_)
    به‌علاوه 3 ویژگی تعاملی (i13, i14, i15) است.
    """
    out = compute_technical_features(df)
    out = compute_grid_features(out, grid_size=grid_size, grid_lookback=grid_lookback)

    raw_cols = [f"f{i}" for i in range(1, 13)] + ["g1", "g2", "g3"]
    for col in raw_cols:
        out[f"t_{col}"] = _safe_tanh(out[col])

    out["i13"] = _safe_tanh((out["f5"] * out["f9"]).to_numpy())
    out["i14"] = _safe_tanh((out["f4"] * out["g1"]).to_numpy())
    out["i15"] = _safe_tanh((out["f8"] * out["f7"]).to_numpy())

    feature_cols = [f"t_{c}" for c in raw_cols] + ["i13", "i14", "i15"]
    out[feature_cols] = out[feature_cols].apply(
        lambda s: pd.to_numeric(s, errors="coerce")
    ).fillna(0.0).replace([np.inf, -np.inf], 0.0)

    out.attrs["feature_cols"] = feature_cols
    return out
