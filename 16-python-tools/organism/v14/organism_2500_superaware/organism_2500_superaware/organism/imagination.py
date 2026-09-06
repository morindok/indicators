"""
organism.imagination

تخیل خلاق و سنتز ایده‌های انقلابی.
"""
from __future__ import annotations

import random
from collections import deque
from typing import Any, Dict, Iterable, List, Optional

from .language import NaturalLanguageComposer, SemanticFrame

class CreativeImagination:
    def __init__(self, seed: int = 2500, composer: Optional[NaturalLanguageComposer] = None):
        self.rng = random.Random(seed)
        self.composer = composer or NaturalLanguageComposer(seed + 1)

    def imagine(self, words: Iterable[str], emotion: str) -> str:
        words = list(words or [])

        subject = self.composer.choose_from(
            words,
            default=self.rng.choice(self.composer.default_subjects),
        )
        obj = self.composer.choose_from(
            words,
            default=self.rng.choice(self.composer.default_objects),
        )
        place = self.rng.choice(self.composer.places)

        frame = SemanticFrame(
            intent="imagination",
            subject=subject,
            object=obj,
            place=place,
            emotion=emotion,
        )
        return self.composer.render(frame)


# ---------------------------------------------------------------------------
# سنتز ایده‌های انقلابی (Revolutionary Idea Synthesis)
# ---------------------------------------------------------------------------

class RevolutionaryIdeaSynthesizer:
    """
    تجسم و آفرینش ایده از آموخته‌ها: از میان گراف مفاهیم، دو مفهومِ
    «دور از هم» (بدون یال مستقیم و از دو خوشه‌ی متفاوت) را برمی‌گزیند،
    آن‌ها را از طریق ترکیب‌گر زبان به‌صورت یک فرضیه/بینش تازه به‌هم
    پیوند می‌دهد (آمیزش مفهومی — conceptual blending)، و امتیاز آن را
    بر پایه‌ی «تازگی × پیوستگی معنایی × هم‌سویی هیجانی» می‌سنجد. ایده‌های
    برتر در حافظه‌ی بلندمدت ثبت می‌شوند و حتی به‌صورت یک یال تازه به
    گراف مفاهیم بازمی‌گردند — یعنی ارگانیسم از ایده‌ی خودش نیز می‌آموزد.
    """

    TEMPLATES = [
        "اگر «{a}» را با منطق «{b}» بازتعریف کنیم، به بینشی می‌رسیم که پیش‌تر دیده نشده بود.",
        "میان «{a}» و «{b}» پیوندی پنهان می‌بینم: شاید هر دو تجلی یک الگوی عمیق‌تر باشند.",
        "فرضیه: «{a}» در واقع نسخه‌ای فشرده از «{b}» است که در مقیاسی دیگر بازتولید شده.",
        "پرسشی انقلابی: اگر قواعد «{b}» را بر «{a}» اعمال کنیم، چه نظمِ تازه‌ای پدیدار می‌شود؟",
        "بینش نو: «{a}» و «{b}» را می‌توان در یک چارچوب واحد ادغام کرد و از دلِ آن، مفهومی سوم زایید.",
    ]

    def __init__(self, seed: int = 2500, composer: Optional[NaturalLanguageComposer] = None, history_len: int = 200):
        self.rng = random.Random(seed)
        self.composer = composer or NaturalLanguageComposer(seed + 7)
        self.history: deque = deque(maxlen=history_len)
        self.best_score = 0.0

    def _pick_distant_pair(self, concept_graph: Any) -> Optional[tuple]:
        nodes = getattr(concept_graph, "nodes", {}) or {}
        labels = [lbl for lbl, data in nodes.items() if data.get("strength", 0.0) > 0.15]
        if len(labels) < 2:
            return None

        self.rng.shuffle(labels)
        for i in range(min(len(labels), 24)):
            a = labels[i]
            for j in range(i + 1, min(len(labels), i + 24)):
                b = labels[j]
                if not concept_graph.has_edge(a, b):
                    return (a, b)
        # اگر همه به‌هم متصل بودند، دو مفهوم تصادفی برمی‌گردانیم (کمتر انقلابی، ولی معتبر)
        return (labels[0], labels[1]) if len(labels) >= 2 else None

    def synthesize(
        self,
        concept_graph: Any,
        emotion: str,
        phi_proxy: float = 0.0,
        guard: Any = None,
    ) -> Optional[Dict[str, Any]]:
        pair = self._pick_distant_pair(concept_graph)
        if not pair:
            return None
        a, b = pair

        template = self.rng.choice(self.TEMPLATES)
        raw_idea = template.format(a=a, b=b)

        if guard is not None and hasattr(guard, "protect"):
            idea_text = guard.protect(raw_idea, fallback=raw_idea)
        else:
            idea_text = raw_idea

        nodes = getattr(concept_graph, "nodes", {}) or {}
        strength_a = float(nodes.get(a, {}).get("strength", 0.2))
        strength_b = float(nodes.get(b, {}).get("strength", 0.2))
        connectivity_penalty = 1.0 if concept_graph.has_edge(a, b) else 0.0

        novelty = max(0.0, 1.0 - connectivity_penalty)
        coherence = min(1.0, (strength_a + strength_b) / 6.0)
        emotional_lift = 0.15 if emotion in ("hope", "curiosity", "awe", "joy") else 0.0
        idea_score = max(
            0.0,
            min(1.0, 0.45 * novelty + 0.25 * coherence + 0.15 * phi_proxy + emotional_lift),
        )

        record = {
            "text": idea_text,
            "concepts": (a, b),
            "novelty": novelty,
            "coherence": coherence,
            "score": idea_score,
        }
        self.history.append(record)
        self.best_score = max(self.best_score, idea_score)
        return record

    def best_ideas(self, n: int = 5) -> List[Dict[str, Any]]:
        return sorted(self.history, key=lambda r: r["score"], reverse=True)[:n]

    def report(self) -> str:
        if not self.history:
            return "هنوز هیچ ایده‌ی انقلابی زاده نشده است."
        last = self.history[-1]
        return f"آخرین ایده (امتیاز {last['score']:.2f}): {last['text']}"


# ---------------------------------------------------------------------------
# Decision engine
# ---------------------------------------------------------------------------
