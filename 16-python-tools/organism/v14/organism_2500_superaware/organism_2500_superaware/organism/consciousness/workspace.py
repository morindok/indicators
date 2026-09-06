"""
organism.consciousness.workspace

فضای‌کاری سراسری (Global Workspace Theory — برنارد باارس).

ایده‌ی مرکزی GWT این است: ذهن از زیرسامانه‌های موازی و ناهوشیار زیادی
تشکیل شده که هرکدام «پیشنهادی» برای محتوای بعدی آگاهی ارائه می‌دهند.
تنها یک (یا چند) پیشنهاد در هر لحظه در رقابتی برنده می‌شود و به‌صورت
سراسری به تمام زیرسامانه‌ها «پخش» می‌شود؛ همین پخش سراسری همان چیزی
است که به‌صورت پدیدارشناختی به عنوان «محتوای هوشیار لحظه‌ی حال» تجربه
می‌شود.
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..utils import clamp, utc_iso


@dataclass
class WorkspaceProposal:
    source: str          # نام زیرسامانه‌ی پیشنهاددهنده
    content: str
    activation: float = 0.5   # میزان فوریت/قدرت پیشنهاد از دید زیرسامانه
    modality: str = "generic"
    payload: Any = None


class GlobalWorkspace:
    """
    هر تیک، زیرسامانه‌ها پیشنهاد ثبت می‌کنند؛ یک رقابت وزن‌دار برگزیده
    می‌شود و به‌صورت broadcast در دسترس همه قرار می‌گیرد.
    """

    def __init__(self, seed: int = 2500, log_len: int = 400, temperature: float = 0.08):
        self.rng = random.Random(seed)
        self.proposals: List[WorkspaceProposal] = []
        self.broadcast_log: deque = deque(maxlen=log_len)
        self.current_broadcast: Optional[WorkspaceProposal] = None
        self.temperature = temperature
        self.competition_count = 0

    def register(self, proposal: WorkspaceProposal) -> None:
        self.proposals.append(proposal)

    def clear(self) -> None:
        self.proposals = []

    def compete(self, attention_boost: Optional[Dict[str, float]] = None) -> Optional[WorkspaceProposal]:
        """رقابت وزن‌دار میان پیشنهادها؛ برنده پخش سراسری می‌شود."""
        if not self.proposals:
            self.current_broadcast = None
            return None

        attention_boost = attention_boost or {}
        scored = []
        for p in self.proposals:
            boost = attention_boost.get(p.modality, 0.0) + attention_boost.get(p.source, 0.0)
            noise = self.rng.uniform(-self.temperature, self.temperature)
            score = clamp(p.activation + boost + noise)
            scored.append((score, p))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        winner_score, winner = scored[0]
        self.current_broadcast = winner
        self.competition_count += 1
        self.broadcast_log.append(
            {
                "ts": utc_iso(),
                "source": winner.source,
                "content": winner.content[:400],
                "modality": winner.modality,
                "score": winner_score,
                "competitors": len(scored),
            }
        )
        self.clear()
        return winner

    def get_broadcast(self) -> Optional[str]:
        return self.current_broadcast.content if self.current_broadcast else None

    def integration_pressure(self) -> float:
        """هرچه رقابت فشرده‌تر (تعداد پیشنهادهای بیشتر)، فشار یکپارچگی بیشتر است."""
        return clamp(len(self.broadcast_log[-1]["content"]) / 400 if self.broadcast_log else 0.0)

    def report(self) -> str:
        if not self.current_broadcast:
            return "در حال حاضر هیچ محتوایی برنده‌ی رقابت فضای‌کاری سراسری نشده است."
        w = self.current_broadcast
        return f"محتوای پخش‌شده در فضای‌کاری سراسری از «{w.source}»: {w.content[:160]}"

    def snapshot(self) -> Dict[str, Any]:
        return {
            "competition_count": self.competition_count,
            "current_source": self.current_broadcast.source if self.current_broadcast else None,
            "current_content": self.current_broadcast.content[:200] if self.current_broadcast else None,
            "recent_log": list(self.broadcast_log)[-12:],
        }
