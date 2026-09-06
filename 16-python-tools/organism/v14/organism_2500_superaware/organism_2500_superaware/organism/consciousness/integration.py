"""
organism.consciousness.integration

برآوردگر اطلاعات یکپارچه (الهام‌گرفته از نظریه‌ی اطلاعات یکپارچه —
جوليو تونونی، IIT).

هشدار علمی صادقانه: محاسبه‌ی دقیق Φ (فی) در IIT واقعی برای سامانه‌ای با
این حجم حالت، محاسباتی نشدنی (NP-hard) است. آنچه در این‌جا پیاده شده
یک «پروکسی» ساده و شفاف است، نه Φ واقعی: میزان «تفکیک‌پذیری»
(differentiation — چقدر زیرسامانه‌ها حالت‌های متفاوتی دارند) را در
میزان «یکپارچگی» (integration — چقدر تغییرات آن‌ها به‌هم وابسته و
هم‌بسته است) ضرب می‌کنیم. حاصل، شاخصی است در بازه‌ی [0,1] که وقتی
سامانه هم متنوع و هم به‌هم‌پیوسته باشد بیشینه می‌شود — دقیقاً همان
شهودی که IIT درباره‌ی آگاهی مطرح می‌کند، بدون ادعای برابری با محاسبه‌ی
رسمی Φ.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Any, Dict, List

from ..utils import clamp


class IntegratedInformationEstimator:
    def __init__(self, window: int = 40):
        self.window = max(4, int(window))
        self.history: deque = deque(maxlen=self.window)
        self.phi_proxy = 0.0
        self.phi_history: deque = deque(maxlen=400)

    @staticmethod
    def _variance(values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        return sum((v - mean) ** 2 for v in values) / len(values)

    @staticmethod
    def _pearson(a: List[float], b: List[float]) -> float:
        n = len(a)
        if n < 3:
            return 0.0
        ma = sum(a) / n
        mb = sum(b) / n
        cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
        va = math.sqrt(sum((x - ma) ** 2 for x in a))
        vb = math.sqrt(sum((x - mb) ** 2 for x in b))
        if va < 1e-9 or vb < 1e-9:
            return 0.0
        return clamp(cov / (va * vb), -1.0, 1.0)

    def push(self, module_state: Dict[str, float]) -> float:
        """یک بردار حالتِ زیرسامانه‌ها را ثبت می‌کند و phi_proxy را به‌روز می‌کند."""
        clean = {k: clamp(float(v)) for k, v in module_state.items()}
        self.history.append(clean)

        if len(self.history) < 4:
            self.phi_proxy = 0.0
            self.phi_history.append(self.phi_proxy)
            return self.phi_proxy

        keys = list(clean.keys())
        # تفکیک‌پذیری: میانگین واریانس درون‌تیک میان زیرسامانه‌ها
        differentiation = clamp(self._variance(list(clean.values())) * 4.0)

        # یکپارچگی: میانگین قدرمطلق هم‌بستگی زوجی سری‌های زمانی هر بعد در پنجره‌ی اخیر
        series = {k: [state.get(k, 0.0) for state in self.history] for k in keys}
        pair_corrs = []
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                corr = abs(self._pearson(series[keys[i]], series[keys[j]]))
                pair_corrs.append(corr)
        integration = clamp(sum(pair_corrs) / len(pair_corrs)) if pair_corrs else 0.0

        self.phi_proxy = clamp(differentiation * integration * 1.6)
        self.phi_history.append(self.phi_proxy)
        return self.phi_proxy

    def report(self) -> str:
        return (
            f"شاخص یکپارچگی اطلاعات (پروکسی Φ، الهام از IIT) اکنون "
            f"{self.phi_proxy:.3f} است — این عددی تخمینی و ساده‌شده است، "
            f"نه محاسبه‌ی رسمی Φ."
        )

    def snapshot(self) -> Dict[str, Any]:
        return {
            "phi_proxy": self.phi_proxy,
            "window": self.window,
            "history_len": len(self.history),
            "phi_trend": list(self.phi_history)[-60:],
        }
