# -*- coding: utf-8 -*-
"""
شبکه عصبی عمیق (LSTM + لایه‌های تمام‌متصل) برای پیش‌بینی احتمال صعود/نزول.
- به‌جای وزن‌های تصادفیِ ثابت، با Backpropagation واقعی (PyTorch/Adam) آموزش می‌بیند.
- یادگیری مداوم (Continual Learning): هر چند دقیقه با داده تازه fine-tune می‌شود،
  نه اینکه فقط یک‌بار آموزش ببیند و ثابت بماند - به همین دلیل با بازار «زنده» تطبیق می‌یابد.
- دقت با روش Walk-Forward (بدون نگاه به آینده) سنجیده می‌شود.
"""

import threading
import logging

import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger("morindok.neural_net")


class LSTMForecaster(nn.Module):
    def __init__(self, n_features, hidden_size=32, num_layers=2, dropout=0.15):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=n_features,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.fc1 = nn.Linear(hidden_size, 16)
        self.act = nn.Tanh()
        self.fc2 = nn.Linear(16, 1)

    def forward(self, x):
        # x: (batch, seq_len, n_features)
        out, (h_n, _) = self.lstm(x)
        last = h_n[-1]                      # آخرین لایه پنهان -> (batch, hidden_size)
        z = self.act(self.fc1(last))
        z = self.fc2(z)
        return torch.sigmoid(z).squeeze(-1)  # (batch,)


class ContinualTrainer:
    """
    مسئول آموزش مداوم، پیش‌بینی زنده، و ردیابی دقت واقعی (walk-forward) شبکه.
    Thread-safe: می‌تواند از یک ترد پس‌زمینه فراخوانی شود بدون قفل‌کردن UI.
    """

    def __init__(self, n_features, seq_len=20, horizon=10, hidden_size=32,
                 num_layers=2, lr=1e-3, l2=1e-5, device=None):
        self.n_features = n_features
        self.seq_len = seq_len
        self.horizon = horizon
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        self.model = LSTMForecaster(n_features, hidden_size, num_layers).to(self.device)
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=lr, weight_decay=l2)
        self.criterion = nn.BCELoss()

        self._lock = threading.Lock()
        self.pred_history = {}          # index -> probability پیش‌بینی‌شده در همان لحظه
        self.correct_predictions = 0
        self.total_predictions = 0
        self.last_train_loss = None
        self.trained_steps = 0

    # -----------------------------------------------------------------
    def _make_sequences(self, feat_matrix: np.ndarray, closes: np.ndarray):
        """
        از ماتریس ویژگی (T, n_features) دنباله‌های (seq_len) و برچسب صعود/نزول
        بعد از horizon کندل می‌سازد. فقط نمونه‌هایی که برچسبشان معلوم است.
        """
        T = feat_matrix.shape[0]
        xs, ys, idxs = [], [], []
        last_labelable = T - self.horizon
        for t in range(self.seq_len - 1, last_labelable):
            window = feat_matrix[t - self.seq_len + 1: t + 1]
            if window.shape[0] != self.seq_len:
                continue
            label = 1.0 if closes[t + self.horizon] > closes[t] else 0.0
            xs.append(window)
            ys.append(label)
            idxs.append(t)
        if not xs:
            return None, None, None
        X = np.stack(xs).astype(np.float32)
        y = np.array(ys, dtype=np.float32)
        return X, y, idxs

    # -----------------------------------------------------------------
    def train_step(self, feat_matrix: np.ndarray, closes: np.ndarray,
                    epochs=2, batch_size=64, max_samples=1500):
        """
        یک دور fine-tune روی جدیدترین داده‌های برچسب‌دارشده (Continual Learning).
        max_samples: برای پایداری، فقط پنجره اخیر آموزش داده می‌شود نه کل تاریخچه.
        """
        X, y, _ = self._make_sequences(feat_matrix, closes)
        if X is None or len(X) < 10:
            return None

        if len(X) > max_samples:
            X = X[-max_samples:]
            y = y[-max_samples:]

        X_t = torch.from_numpy(np.nan_to_num(X)).to(self.device)
        y_t = torch.from_numpy(y).to(self.device)

        with self._lock:
            self.model.train()
            n = X_t.shape[0]
            last_loss = None
            for _ in range(epochs):
                perm = torch.randperm(n)
                epoch_loss = 0.0
                for i in range(0, n, batch_size):
                    idx = perm[i:i + batch_size]
                    xb, yb = X_t[idx], y_t[idx]
                    self.optimizer.zero_grad()
                    pred = self.model(xb)
                    loss = self.criterion(pred, yb)
                    if torch.isnan(loss):
                        continue
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                    self.optimizer.step()
                    epoch_loss += loss.item() * xb.shape[0]
                last_loss = epoch_loss / n
            self.last_train_loss = last_loss
            self.trained_steps += 1
        return last_loss

    # -----------------------------------------------------------------
    def predict_latest(self, feat_matrix: np.ndarray, current_index: int):
        """پیش‌بینی زنده برای آخرین کندل موجود (استفاده از seq_len ردیف آخر)."""
        if feat_matrix.shape[0] < self.seq_len:
            return 0.5
        window = feat_matrix[-self.seq_len:]
        x = torch.from_numpy(np.nan_to_num(window).astype(np.float32)).unsqueeze(0).to(self.device)
        with self._lock:
            self.model.eval()
            with torch.no_grad():
                prob = self.model(x).item()
        if np.isnan(prob):
            prob = 0.5
        self.pred_history[current_index] = prob
        return prob

    # -----------------------------------------------------------------
    def update_accuracy(self, closes: np.ndarray, current_index: int):
        """
        سنجش دقت Walk-Forward: پیش‌بینیِ ثبت‌شده در horizon کندل قبل را با
        نتیجه واقعیِ الان مقایسه می‌کند (بدون نگاه به آینده، چون آن پیش‌بینی
        همان لحظه‌ی خودش ذخیره شده بود، نه با وزن‌های امروز بازمحاسبه‌شده).
        """
        past_index = current_index - self.horizon
        if past_index in self.pred_history and past_index + self.horizon < len(closes):
            past_pred = self.pred_history.pop(past_index)
            predicted_up = past_pred > 0.5
            actual_up = closes[past_index + self.horizon] > closes[past_index]
            self.total_predictions += 1
            if predicted_up == actual_up:
                self.correct_predictions += 1
        # جلوگیری از رشد بی‌نهایت دیکشنری در اجرای طولانی‌مدت
        if len(self.pred_history) > 5000:
            oldest_keys = sorted(self.pred_history.keys())[:1000]
            for k in oldest_keys:
                self.pred_history.pop(k, None)

    @property
    def accuracy(self):
        if self.total_predictions == 0:
            return 0.5
        return self.correct_predictions / self.total_predictions
