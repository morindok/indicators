# -*- coding: utf-8 -*-
"""
موتور اصلی داشبورد مورین‌دوک: هر چرخه این مراحل را انجام می‌دهد:
  1) دریافت جدیدترین داده از data_feed (که خودش پس‌زمینه به‌روز می‌شود)
  2) ساخت ویژگی‌های تکنیکال + شبکه تار عنکبوتی
  3) یادگیری مداوم شبکه عصبی LSTM روی داده‌های تازه (وقتی کندل جدیدی بسته شده)
  4) پیش‌بینی زنده + شبیه‌سازی مونت‌کارلوی چند-مسیره
  5) ادغام و کالیبراسیون سیگنال نهایی + نوشتن در AppState برای نمایش در Dash
"""

import time
import logging
import threading

import numpy as np

from data_feed import BybitDataFeed
from features import build_feature_matrix, N_FEATURES
from neural_net import ContinualTrainer
from path_simulator import simulate_paths
from app_state import AppState

logger = logging.getLogger("morindok.engine")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


class Engine:
    def __init__(self, config):
        self.cfg = config
        self.state = AppState()

        self.feed = BybitDataFeed(
            symbol=config["symbol"],
            category=config["category"],
            interval=config["interval"],
            history_len=config["history_len"],
            poll_seconds=config["poll_seconds"],
        )

        self.trainer = ContinualTrainer(
            n_features=N_FEATURES,
            seq_len=config["seq_len"],
            horizon=config["horizon"],
            hidden_size=config["hidden_size"],
            num_layers=config["num_layers"],
            lr=config["learning_rate"],
        )

        self.min_bars_required = (
            config["seq_len"] + config["horizon"] + 60
        )
        self.min_train_bars = config["min_train_bars"]
        self.min_samples = config["min_samples"]

        self._last_trained_timestamp = None
        self._cycle_count = 0
        self._stop_flag = threading.Event()
        self._thread = None

    # -----------------------------------------------------------------
    def _run_cycle(self):
        df = self.feed.get_df()
        status = self.feed.get_status()

        if len(df) < self.min_bars_required:
            self.state.update(
                status=f"در انتظار داده کافی ({len(df)}/{self.min_bars_required})",
                connected=status["connected"],
                symbol=self.cfg["symbol"],
                bars_available=len(df),
                min_bars_required=self.min_bars_required,
            )
            return

        feat_df = build_feature_matrix(
            df, grid_size=self.cfg["grid_size"], grid_lookback=self.cfg["grid_lookback"]
        )
        feature_cols = feat_df.attrs["feature_cols"]
        feat_matrix = feat_df[feature_cols].to_numpy(dtype=np.float32)
        closes = feat_df["close"].to_numpy()
        current_index = len(feat_df) - 1
        current_price = float(closes[-1])
        latest_timestamp = feat_df["timestamp"].iloc[-1]

        # --- آموزش مداوم فقط وقتی کندل جدیدی بسته شده و به‌اندازه کافی دیتا هست ---
        new_candle = latest_timestamp != self._last_trained_timestamp
        should_train = new_candle and (self._cycle_count % self.cfg["train_every_n_cycles"] == 0)
        if should_train and len(feat_matrix) > self.trainer.seq_len + self.trainer.horizon + 20:
            loss = self.trainer.train_step(
                feat_matrix, closes,
                epochs=self.cfg["train_epochs"],
                batch_size=self.cfg["train_batch_size"],
                max_samples=self.cfg["train_max_samples"],
            )
            self._last_trained_timestamp = latest_timestamp
            if loss is not None:
                logger.info("آموزش مداوم انجام شد - loss=%.4f - نمونه‌ها=%d", loss, self.trainer.trained_steps)

        # --- پیش‌بینی زنده ---
        neural_prob = self.trainer.predict_latest(feat_matrix, current_index)
        self.trainer.update_accuracy(closes, current_index)

        # --- شبیه‌سازی مونت‌کارلوی چند-مسیره ---
        mc_result = simulate_paths(
            closes, horizon=self.cfg["horizon"], n_paths=self.cfg["n_paths"],
            block_size=self.cfg["mc_block_size"], lookback=self.cfg["mc_lookback"],
        )
        mc_prob = mc_result["prob_up"] if mc_result else 0.5
        expected_move = mc_result["expected_move_pct"] if mc_result else 0.0
        percentiles = mc_result["percentiles"] if mc_result else None

        # --- شبکه تار عنکبوتی ---
        grid_bias_raw = float(feat_df["grid_bias_raw"].iloc[-1]) if not np.isnan(feat_df["grid_bias_raw"].iloc[-1]) else 0.0
        grid_signal = float(np.clip(grid_bias_raw / (self.cfg["grid_size"] / 2.0), -1.0, 1.0))

        # --- ادغام نهایی سه منبع سیگنال ---
        neural_signal = (neural_prob - 0.5) * 2.0
        mc_signal = (mc_prob - 0.5) * 2.0
        w_n, w_m, w_g = self.cfg["w_neural"], self.cfg["w_montecarlo"], self.cfg["w_grid"]
        wsum = max(w_n + w_m + w_g, 1e-6)
        combined_signal = (neural_signal * w_n + mc_signal * w_m + grid_signal * w_g) / wsum

        accuracy = self.trainer.accuracy
        edge = accuracy - 0.5
        confidence_multiplier = float(np.clip(1.0 + edge * 3.0, 0.2, 1.5))

        enough_data = (
            len(df) >= self.min_train_bars
            and self.trainer.total_predictions >= self.min_samples
            and self.trainer.trained_steps > 0
        )

        raw_probability = 50.0 + combined_signal * 50.0 * confidence_multiplier
        final_probability = float(np.clip(raw_probability, 5.0, 95.0))

        if not enough_data:
            decision = "🧠 در حال آموزش..."
        elif final_probability >= 70:
            decision = "🧠 صعودی قوی"
        elif final_probability >= 60:
            decision = "🧠 صعودی"
        elif final_probability < 30:
            decision = "🧠 نزولی قوی"
        elif final_probability < 40:
            decision = "🧠 نزولی"
        else:
            decision = "🧠 خنثی"

        self.state.update(
            status="زنده" if status["connected"] else "قطع اتصال - تلاش مجدد...",
            connected=status["connected"],
            symbol=self.cfg["symbol"],
            price=current_price,
            neural_prob=neural_prob,
            montecarlo_prob=mc_prob,
            grid_bias=grid_bias_raw,
            grid_signal=grid_signal,
            combined_signal=combined_signal,
            final_probability=final_probability,
            confidence_multiplier=confidence_multiplier,
            accuracy=accuracy,
            correct=self.trainer.correct_predictions,
            total=self.trainer.total_predictions,
            trained_steps=self.trainer.trained_steps,
            train_loss=self.trainer.last_train_loss,
            enough_data=enough_data,
            bars_available=len(df),
            min_bars_required=self.min_bars_required,
            path_percentiles=percentiles,
            expected_move_pct=expected_move,
            decision_label=decision,
        )
        self._cycle_count += 1

    # -----------------------------------------------------------------
    def _loop(self):
        while not self._stop_flag.is_set():
            try:
                self._run_cycle()
            except Exception:  # noqa: BLE001
                logger.exception("خطا در چرخه پردازش موتور")
            self._stop_flag.wait(self.cfg["engine_cycle_seconds"])

    def start(self):
        self.feed.start()
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("موتور مورین‌دوک استارت شد.")

    def stop(self):
        self._stop_flag.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.feed.stop()
