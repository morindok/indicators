# -*- coding: utf-8 -*-
"""تنظیمات مرکزی - همه‌ی پارامترها اینجا قابل تغییرند."""

CONFIG = {
    # --- داده ---
    "symbol": "BTCUSDT",
    "category": "linear",      # "linear" (پرپچوال USDT) یا "spot"
    "interval": "5",           # دقیقه: "1","3","5","15","30","60","240","D" ...
    "history_len": 1000,       # تعداد کندل تاریخی نگه‌داشته‌شده
    "poll_seconds": 15,        # هر چند ثانیه یک‌بار داده از بایبیت رفرش شود

    # --- شبکه تار عنکبوتی ---
    "grid_size": 20,
    "grid_lookback": 50,

    # --- شبکه عصبی LSTM ---
    "seq_len": 20,              # طول دنباله ورودی به LSTM
    "horizon": 10,              # چند کندل جلوتر پیش‌بینی شود
    "hidden_size": 32,
    "num_layers": 2,
    "learning_rate": 1e-3,
    "train_every_n_cycles": 1,  # آموزش را هر چند چرخه (فقط وقتی کندل جدید بسته شد) انجام بده
    "train_epochs": 2,
    "train_batch_size": 64,
    "train_max_samples": 1500,  # حداکثر نمونه اخیر برای fine-tune (پایداری)

    # --- شبیه‌سازی مونت‌کارلوی چند-مسیره ---
    "n_paths": 2000,
    "mc_block_size": 5,
    "mc_lookback": 500,

    # --- ادغام نهایی سیگنال‌ها ---
    "w_neural": 0.5,
    "w_montecarlo": 0.3,
    "w_grid": 0.2,

    # --- آستانه‌های اعتبار سیگنال ---
    "min_train_bars": 300,
    "min_samples": 30,

    # --- چرخه موتور پردازش (پس‌زمینه) ---
    "engine_cycle_seconds": 20,

    # --- Dash ---
    "dash_refresh_ms": 5000,
    "dash_port": 8050,
}
