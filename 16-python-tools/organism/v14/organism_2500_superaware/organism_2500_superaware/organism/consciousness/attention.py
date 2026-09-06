"""
organism.consciousness.attention

قوه‌ی توجه و تمرکز — «نورافکن توجه» با ظرفیت محدود.

این ماژول پیاده‌سازی می‌کند که چگونه از میان ده‌ها محرک هم‌زمان (حسی،
هیجانی، مفهومی، ناخودآگاه) تنها چند مورد به «کانون توجه» راه می‌یابند.
این گلوگاه ظرفیت‌محدود همان چیزی است که در نظریه‌ی فضای‌کاری سراسری
(Global Workspace Theory) به عنوان «دروازه‌بان ورود به آگاهی» شناخته
می‌شود: هر چیزی که وارد کارگاه سراسری می‌شود، پیش از آن باید از صافی
توجه عبور کرده باشد.
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..utils import clamp


@dataclass
class AttentionCandidate:
    """یک محرک بالقوه برای ورود به کانون توجه."""

    key: str
    content: str
    modality: str = "generic"       # sight/hearing/emotion/need/concept/unconscious/...
    novelty: float = 0.5
    intensity: float = 0.5
    relevance: float = 0.5           # ارتباط با نیازها/اهداف جاری
    surprise: float = 0.0            # خطای پیش‌بینی مرتبط (از موتور پردازش پیش‌بینانه)
    payload: Any = None

    def salience(self, weights: Optional[Dict[str, float]] = None) -> float:
        w = weights or {"novelty": 0.30, "intensity": 0.25, "relevance": 0.25, "surprise": 0.20}
        return clamp(
            w.get("novelty", 0.30) * self.novelty
            + w.get("intensity", 0.25) * self.intensity
            + w.get("relevance", 0.25) * self.relevance
            + w.get("surprise", 0.20) * self.surprise
        )


class AttentionSystem:
    """
    نورافکن توجه با ظرفیت محدود (پیش‌فرض ۴ خانه، الهام از حافظه‌ی کاری انسانی)
    به‌همراه بازداری از بازگشت (inhibition of return) تا محرک‌های تازه‌دیده‌شده
    موقتاً کم‌اهمیت‌تر جلوه کنند و توجه یکنواخت روی یک محرک قفل نشود.
    """

    def __init__(self, capacity: int = 4, seed: int = 2500, history_len: int = 240):
        self.capacity = max(1, int(capacity))
        self.rng = random.Random(seed)
        self.recent_keys: deque = deque(maxlen=32)
        self.focus_history: deque = deque(maxlen=history_len)
        self.current_focus: List[AttentionCandidate] = []
        self.fatigue: Dict[str, float] = {}
        self.temperature = 0.06  # مقدار کوچک تصادفی‌بودن برای گریز از قفل‌شدگی توجه

    def _inhibition_penalty(self, key: str) -> float:
        return self.fatigue.get(key, 0.0)

    def select(
        self,
        candidates: List[AttentionCandidate],
        extra_bias: Optional[Dict[str, float]] = None,
    ) -> List[AttentionCandidate]:
        """از میان نامزدها، برترین‌ها را تا سقف ظرفیت انتخاب می‌کند."""
        if not candidates:
            self.current_focus = []
            return []

        extra_bias = extra_bias or {}
        scored = []
        for cand in candidates:
            base = cand.salience()
            bias = extra_bias.get(cand.modality, 0.0) + extra_bias.get(cand.key, 0.0)
            penalty = self._inhibition_penalty(cand.key)
            noise = self.rng.uniform(-self.temperature, self.temperature)
            final = clamp(base + bias - penalty + noise)
            scored.append((final, cand))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        chosen = scored[: self.capacity]
        self.current_focus = [c for _, c in chosen]

        # به‌روزرسانی بازداری از بازگشت: هرچه بیشتر دیده شود، موقتاً کم‌رنگ‌تر می‌شود
        for key in list(self.fatigue.keys()):
            self.fatigue[key] = max(0.0, self.fatigue[key] - 0.05)
        for score, cand in chosen:
            self.fatigue[cand.key] = clamp(self.fatigue.get(cand.key, 0.0) + 0.22, 0.0, 0.85)
            self.recent_keys.append(cand.key)

        self.focus_history.append(
            {
                "keys": [c.key for c in self.current_focus],
                "modalities": [c.modality for c in self.current_focus],
                "top_salience": chosen[0][0] if chosen else 0.0,
            }
        )
        return self.current_focus

    def focus_strength(self) -> float:
        if not self.current_focus:
            return 0.0
        return clamp(sum(c.salience() for c in self.current_focus) / len(self.current_focus))

    def report(self) -> str:
        if not self.current_focus:
            return "کانون توجه در حال حاضر خالی است."
        items = "، ".join(f"{c.modality}:{c.key}" for c in self.current_focus)
        return f"توجه من اکنون بر {len(self.current_focus)} محرک متمرکز است: {items}."

    def snapshot(self) -> Dict[str, Any]:
        return {
            "capacity": self.capacity,
            "focus_strength": self.focus_strength(),
            "current_focus": [
                {"key": c.key, "modality": c.modality, "salience": c.salience()}
                for c in self.current_focus
            ],
            "fatigue": dict(self.fatigue),
        }
