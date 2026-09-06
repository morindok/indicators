# -*- coding: utf-8 -*-
"""یک ظرف ساده و Thread-safe برای اشتراک‌گذاری آخرین نتایج بین موتور پردازش (ترد پس‌زمینه) و Dash."""

import threading
from datetime import datetime, timezone


class AppState:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {
            "status": "در حال راه‌اندازی...",
            "connected": False,
            "symbol": None,
            "price": None,
            "neural_prob": 0.5,
            "montecarlo_prob": 0.5,
            "grid_bias": 0.0,
            "grid_signal": 0.0,
            "combined_signal": 0.0,
            "final_probability": 50.0,
            "confidence_multiplier": 1.0,
            "accuracy": 0.5,
            "correct": 0,
            "total": 0,
            "trained_steps": 0,
            "train_loss": None,
            "enough_data": False,
            "bars_available": 0,
            "min_bars_required": 0,
            "path_percentiles": None,
            "expected_move_pct": 0.0,
            "last_update": None,
            "decision_label": "در حال آموزش...",
        }

    def update(self, **kwargs):
        with self._lock:
            self._data.update(kwargs)
            self._data["last_update"] = datetime.now(timezone.utc)

    def snapshot(self):
        with self._lock:
            return dict(self._data)
