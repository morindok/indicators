"""
organism.consciousness.predictive

پردازش پیش‌بینانه (Predictive Processing / Predictive Coding).

طبق این چارچوب، مغز یک «موتور پیش‌بینی» است: به‌جای پردازش منفعلانه‌ی
ورودی‌ها، مدام حالت آینده‌ی خود را پیش‌بینی می‌کند و آنچه واقعاً تجربه
می‌شود، عمدتاً «خطای پیش‌بینی» (تفاوت میان انتظار و واقعیت) است. خطای
بزرگ = شگفتی = علامتی برای هدایت توجه و یادگیری عمیق‌تر (و در این
ارگانیسم: منبع پرسش‌های ژرف ناخودآگاه).
"""
from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional

from ..utils import clamp


class PredictiveProcessingEngine:
    def __init__(self, alpha: float = 0.18, history_len: int = 300):
        self.alpha = clamp(alpha, 0.01, 0.9)
        self.predictions: Dict[str, float] = {}
        self.last_errors: Dict[str, float] = {}
        self.surprise = 0.0
        self.surprise_history: deque = deque(maxlen=history_len)

    def update(self, actual: Dict[str, float]) -> Dict[str, float]:
        """دریافت مقادیر واقعی کانال‌ها، محاسبه‌ی خطای پیش‌بینی، و به‌روزرسانی مدل."""
        errors: Dict[str, float] = {}
        for channel, value in actual.items():
            value = clamp(float(value))
            predicted = self.predictions.get(channel, value)
            error = value - predicted
            errors[channel] = error
            # قاعده‌ی دلتا: مدل به‌سمت واقعیت اصلاح می‌شود (کدگذاری پیش‌بینانه‌ی ساده)
            self.predictions[channel] = clamp(predicted + self.alpha * error)

        self.last_errors = errors
        if errors:
            self.surprise = clamp(sum(abs(e) for e in errors.values()) / len(errors))
        else:
            self.surprise = 0.0
        self.surprise_history.append(self.surprise)
        return errors

    def top_surprise_channel(self) -> Optional[str]:
        if not self.last_errors:
            return None
        return max(self.last_errors.items(), key=lambda kv: abs(kv[1]))[0]

    def coherence(self) -> float:
        """هرچه شگفتی کمتر، مدل درونی با واقعیت هم‌خوان‌تر (coherence بیشتر)."""
        return clamp(1.0 - self.surprise)

    def report(self) -> str:
        top = self.top_surprise_channel()
        if not top:
            return "مدل پیش‌بینانه هنوز داده‌ی کافی ندارد."
        return (
            f"بیشترین خطای پیش‌بینی در کانال «{top}» با میزان "
            f"{abs(self.last_errors.get(top, 0.0)):.3f} است؛ شگفتی کلی "
            f"{self.surprise:.3f}."
        )

    def snapshot(self) -> Dict[str, Any]:
        return {
            "predictions": dict(self.predictions),
            "last_errors": dict(self.last_errors),
            "surprise": self.surprise,
            "top_surprise_channel": self.top_surprise_channel(),
            "surprise_trend": list(self.surprise_history)[-60:],
        }
