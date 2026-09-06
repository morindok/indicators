# -*- coding: utf-8 -*-
"""
مسیریابی آینده با شبیه‌سازی مونت‌کارلوی چند-مسیره (Block Bootstrap).
به‌جای فرض ساده حرکت براونی هندسی (که خودهمبستگی نوسان بازار را نادیده می‌گیرد)،
از Block Bootstrap روی بازده‌های لگاریتمی واقعی گذشته استفاده می‌شود تا رفتار
خوشه‌ای نوسانات (Volatility Clustering) بازار کریپتو تا حد زیادی حفظ شود.

خروجی: از میان N مسیر شبیه‌سازی‌شده تا horizon کندل جلوتر، چند درصد به بالای
قیمت فعلی می‌رسند = تخمین احتمال صعود مبتنی بر آمار واقعی گذشته (نه فرضیات ساده).
"""

import numpy as np


def simulate_paths(close_prices: np.ndarray, horizon: int = 10, n_paths: int = 2000,
                    block_size: int = 5, lookback: int = 500, seed: int = None):
    """
    close_prices: آرایه قیمت‌های پایانی (از قدیم به جدید)
    horizon: چند کندل جلوتر شبیه‌سازی شود
    n_paths: تعداد مسیرهای مونت‌کارلو
    block_size: طول بلوک‌های بازده برای حفظ خودهمبستگی محلی
    lookback: چند کندل اخیر برای استخراج آمار بازده استفاده شود
    """
    rng = np.random.default_rng(seed)
    prices = close_prices[-lookback:] if len(close_prices) > lookback else close_prices
    if len(prices) < block_size * 2:
        return None

    log_returns = np.diff(np.log(np.clip(prices, 1e-9, None)))
    n_ret = len(log_returns)
    if n_ret < block_size:
        return None

    n_blocks_needed = int(np.ceil(horizon / block_size))
    current_price = close_prices[-1]

    paths = np.empty((n_paths, horizon))
    for p in range(n_paths):
        chunks = []
        for _ in range(n_blocks_needed):
            start = rng.integers(0, n_ret - block_size + 1)
            chunks.append(log_returns[start:start + block_size])
        sampled_returns = np.concatenate(chunks)[:horizon]
        cum_log_return = np.cumsum(sampled_returns)
        paths[p] = current_price * np.exp(cum_log_return)

    final_prices = paths[:, -1]
    prob_up = float(np.mean(final_prices > current_price))

    percentiles = {
        "p10": np.percentile(paths, 10, axis=0),
        "p50": np.percentile(paths, 50, axis=0),
        "p90": np.percentile(paths, 90, axis=0),
    }

    return {
        "prob_up": prob_up,
        "expected_move_pct": float((np.mean(final_prices) / current_price - 1.0) * 100.0),
        "percentiles": percentiles,
        "n_paths": n_paths,
        "horizon": horizon,
    }
