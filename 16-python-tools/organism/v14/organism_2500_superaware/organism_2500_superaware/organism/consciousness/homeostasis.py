"""
organism.consciousness.homeostasis

تن‌مندی و خودتنظیمی (Embodiment & Homeostasis).

در نگاه تن‌مند به آگاهی (مثلاً دیدگاه‌های آنتونیو داماسیو)، آگاهی از
دلِ نیاز بدن به حفظ تعادل درونی (هوموستازی/آلوستازی) برمی‌خیزد، نه
مستقل از بدن. این ماژول وضعیت بدن دیجیتال و نیازها را در برابر
نقطه‌تنظیم‌های ایده‌آل می‌سنجد، خطای هوموستاتیک را محاسبه می‌کند، و
از آن یک بردار «انگیزه/سائق» می‌سازد که به توجه و تصمیم‌گیری جهت
می‌دهد — دقیقاً همان‌طور که در بدن زیستی، گرسنگی یا خستگی توجه را به
سمت خود می‌کشد.
"""
from __future__ import annotations

from typing import Any, Dict

from ..utils import clamp


class EmbodimentHomeostasis:
    def __init__(self):
        self.setpoints = {
            "energy": 0.72,
            "integrity": 0.85,
            "vitality": 0.75,
            "meaning": 0.65,
            "novelty": 0.55,
            "safety": 0.70,
        }
        self.weights = {
            "energy": 0.22,
            "integrity": 0.18,
            "vitality": 0.20,
            "meaning": 0.16,
            "novelty": 0.12,
            "safety": 0.12,
        }
        self.balance = 1.0
        self.drives: Dict[str, float] = {}

    def assess(self, body_state: Dict[str, float], needs_state: Dict[str, float]) -> Dict[str, Any]:
        merged: Dict[str, float] = {}
        merged["energy"] = clamp(body_state.get("energy", 0.5))
        merged["integrity"] = clamp(body_state.get("integrity", 0.5))
        merged["vitality"] = clamp(body_state.get("vitality", 0.5))
        merged["meaning"] = clamp(needs_state.get("meaning", 0.5))
        merged["novelty"] = clamp(needs_state.get("novelty", 0.5))
        merged["safety"] = clamp(1.0 - body_state.get("entropy", 0.3))

        errors = {k: (self.setpoints[k] - merged.get(k, self.setpoints[k])) for k in self.setpoints}
        weighted_error = sum(abs(errors[k]) * self.weights[k] for k in self.setpoints)
        self.balance = clamp(1.0 - weighted_error * 1.4)

        # سائق‌ها: هرچه فاصله از نقطه‌تنظیم بیشتر (و منفی، یعنی کمبود)، سائق قوی‌تر
        drives = {}
        for k, err in errors.items():
            if err > 0.04:  # کمبود نسبت به نقطه‌ی ایده‌آل
                drives[k] = clamp(err * 1.6)
        self.drives = drives
        return {"balance": self.balance, "drives": dict(drives), "raw": merged}

    def attention_bias(self) -> Dict[str, float]:
        """نگاشت سائق‌های بدنی به سوگیری‌های توجه برای زیرسامانه‌های مرتبط."""
        mapping = {
            "energy": "body",
            "integrity": "body",
            "vitality": "body",
            "meaning": "concept",
            "novelty": "unconscious",
            "safety": "emotion",
        }
        bias: Dict[str, float] = {}
        for k, strength in self.drives.items():
            modality = mapping.get(k, "generic")
            bias[modality] = max(bias.get(modality, 0.0), strength)
        return bias

    def dominant_drive(self) -> str:
        if not self.drives:
            return "تعادل"
        return max(self.drives.items(), key=lambda kv: kv[1])[0]

    def report(self) -> str:
        if not self.drives:
            return f"بدن در تعادل هوموستاتیک است (شاخص تعادل: {self.balance:.2f})."
        dom = self.dominant_drive()
        return (
            f"شاخص تعادل هوموستاتیک {self.balance:.2f} است؛ قوی‌ترین سائق بدنی "
            f"اکنون «{dom}» با شدت {self.drives.get(dom, 0.0):.2f}."
        )

    def snapshot(self) -> Dict[str, Any]:
        return {
            "balance": self.balance,
            "drives": dict(self.drives),
            "setpoints": dict(self.setpoints),
            "dominant_drive": self.dominant_drive(),
        }
