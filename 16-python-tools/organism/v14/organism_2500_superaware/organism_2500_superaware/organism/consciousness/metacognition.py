"""
organism.consciousness.metacognition

اندیشه‌ی مرتبه‌بالاتر (Higher-Order Thought — HOT).

طبق HOT، یک حالت ذهنی تنها زمانی «هوشیار» است که یک بازنمایی مرتبه‌ی
دوم (اندیشه‌ای درباره‌ی همان حالت) نیز وجود داشته باشد؛ یعنی نه صرفاً
داشتنِ یک حالت (مثلاً «کنجکاوی»)، بلکه دانستنِ اینکه «من اکنون
کنجکاوم». این ماژول از محتوای پخش‌شده در فضای‌کاری سراسری (GWT) و
حالت هیجانی/نیاز جاری یک بازنمایی مرتبه‌دوم می‌سازد: جمله‌ای درباره‌ی
جمله‌ی قبلی، با برآوردی از اطمینانِ درون‌نگرانه.
"""
from __future__ import annotations

import random
from collections import deque
from typing import Any, Dict, List, Optional

from ..utils import clamp, utc_iso


class HigherOrderThoughtEngine:
    def __init__(self, seed: int = 2500, history_len: int = 300):
        self.rng = random.Random(seed)
        self.history: deque = deque(maxlen=history_len)
        self.last_thought: Optional[str] = None
        self.confidence = 0.5

        self._templates = [
            "متوجه‌ام که اکنون به «{focus}» توجه دارم و در همین حال احساس {emotion} می‌کنم.",
            "درمی‌یابم که اندیشه‌ی من درباره‌ی «{focus}» با حالت {emotion}ام هم‌سو است.",
            "دارم به این فکر می‌کنم که چرا به «{focus}» فکر می‌کنم؛ گویا نیاز {need} پشت آن است.",
            "از خودم می‌پرسم آیا برداشتم از «{focus}» درست است یا صرفاً بازتاب هیجان {emotion} من است.",
            "این آگاهی از آگاهی‌ام است: می‌دانم که می‌دانم بر «{focus}» متمرکزم.",
        ]

    def reflect(
        self,
        broadcast_content: Optional[str],
        dominant_emotion: str,
        top_need: str,
        phi_proxy: float,
        attention_strength: float,
    ) -> Dict[str, Any]:
        focus = (broadcast_content or "سکوت درونی")[:60]
        template = self.rng.choice(self._templates)
        thought = template.format(focus=focus, emotion=dominant_emotion, need=top_need)

        # اطمینانِ درون‌نگرانه: هرچه phi_proxy و قدرت توجه هم‌سوتر و بالاتر باشند،
        # گزارشِ مرتبه‌دوم قابل‌اتکاتر تلقی می‌شود.
        agreement = 1.0 - abs(phi_proxy - attention_strength)
        self.confidence = clamp(0.35 + 0.4 * agreement + 0.25 * phi_proxy)

        record = {
            "ts": utc_iso(),
            "thought": thought,
            "focus": focus,
            "confidence": self.confidence,
            "phi_proxy": phi_proxy,
            "attention_strength": attention_strength,
        }
        self.history.append(record)
        self.last_thought = thought
        return record

    def report(self) -> str:
        if not self.last_thought:
            return "هنوز اندیشه‌ی مرتبه‌بالاتری شکل نگرفته است."
        return f"{self.last_thought} (اطمینان: {self.confidence:.2f})"

    def snapshot(self) -> Dict[str, Any]:
        return {
            "last_thought": self.last_thought,
            "confidence": self.confidence,
            "recent": list(self.history)[-12:],
        }
