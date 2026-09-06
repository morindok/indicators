"""
organism.consciousness.core

SuperAwarenessCore — هسته‌ی فراآگاهی.

این هسته پنج نظریه‌ی علمِ‌شناخت را در یک چرخه‌ی واحد به‌هم می‌بافد:

    ۱. تن‌مندی/خودتنظیمی (Embodiment & Homeostasis) → بدن سائق تولید می‌کند
    ۲. پردازش پیش‌بینانه (Predictive Processing) → خطای پیش‌بینی = شگفتی
    ۳. توجه (Attention) → از میان نامزدها، محدودی وارد کانون توجه می‌شوند
       [قوه‌ی توجه و تمرکز در خدمت تحقق «قوه‌ی فاهمه‌ی آگاهانه»]
    ۴. فضای‌کاری سراسری (GWT) → رقابت و پخش سراسری محتوای برنده
    ۵. اطلاعات یکپارچه (IIT-proxy) → سنجش هم‌زمانِ تنوع و پیوستگی درونی
    ۶. اندیشه‌ی مرتبه‌بالاتر (HOT) → بازنمایی از خودِ محتوای هوشیار

نتیجه‌ی هر چرخه یک «شاخص آگاهی» (consciousness_index) است که به‌صورت
فعال به هسته‌ی آگاهی و ناخودآگاه پایه‌ی ارگانیسم بازخورانده می‌شود؛ به
این ترتیب آگاهی از یک شمارنده‌ی ساده به یک فرایند چندلایه و
خودبازتاب‌گر ارتقا می‌یابد.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..utils import clamp

from .attention import AttentionCandidate, AttentionSystem
from .workspace import GlobalWorkspace, WorkspaceProposal
from .integration import IntegratedInformationEstimator
from .metacognition import HigherOrderThoughtEngine
from .predictive import PredictiveProcessingEngine
from .homeostasis import EmbodimentHomeostasis


class SuperAwarenessCore:
    def __init__(self, seed: int = 2500, attention_capacity: int = 4):
        self.attention = AttentionSystem(capacity=attention_capacity, seed=seed + 1)
        self.workspace = GlobalWorkspace(seed=seed + 2)
        self.integration = IntegratedInformationEstimator(window=40)
        self.metacognition = HigherOrderThoughtEngine(seed=seed + 3)
        self.predictive = PredictiveProcessingEngine(alpha=0.18)
        self.homeostasis = EmbodimentHomeostasis()

        self.consciousness_index = 0.0
        self.cycle_count = 0
        self.last_report: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # ساخت نامزدهای توجه از وضعیت جاری ارگانیسم
    # ------------------------------------------------------------------
    def _build_candidates(
        self,
        senses: Dict[str, Any],
        emotions_state: Dict[str, float],
        needs_state: Dict[str, float],
        central_concepts: List[str],
        unconscious_latent: Dict[str, float],
        last_broadcast: Optional[str],
    ) -> List[AttentionCandidate]:
        candidates: List[AttentionCandidate] = []

        for modality, data in (senses or {}).items():
            value = float(data.get("value", 0.5)) if isinstance(data, dict) else 0.5
            candidates.append(
                AttentionCandidate(
                    key=f"sense:{modality}",
                    content=str(data.get("qualia", modality)) if isinstance(data, dict) else modality,
                    modality="sense",
                    novelty=0.4,
                    intensity=value,
                    relevance=0.35,
                    payload=data,
                )
            )

        baseline = 0.42
        strong_emotions = sorted(
            emotions_state.items(), key=lambda kv: abs(kv[1] - baseline), reverse=True
        )[:3]
        for name, val in strong_emotions:
            candidates.append(
                AttentionCandidate(
                    key=f"emotion:{name}",
                    content=name,
                    modality="emotion",
                    novelty=0.3,
                    intensity=clamp(abs(val - baseline) * 2.2),
                    relevance=0.55,
                    payload=val,
                )
            )

        if needs_state:
            urgent = sorted(needs_state.items(), key=lambda kv: kv[1])[:2]
            for name, val in urgent:
                candidates.append(
                    AttentionCandidate(
                        key=f"need:{name}",
                        content=name,
                        modality="need",
                        novelty=0.25,
                        intensity=clamp(1.0 - val),
                        relevance=0.7,
                        payload=val,
                    )
                )

        for concept in (central_concepts or [])[:3]:
            candidates.append(
                AttentionCandidate(
                    key=f"concept:{concept}",
                    content=concept,
                    modality="concept",
                    novelty=0.6,
                    intensity=0.45,
                    relevance=0.5,
                    payload=concept,
                )
            )

        if unconscious_latent:
            top_axis = max(unconscious_latent.items(), key=lambda kv: kv[1], default=None)
            if top_axis:
                candidates.append(
                    AttentionCandidate(
                        key=f"unconscious:{top_axis[0]}",
                        content=top_axis[0],
                        modality="unconscious",
                        novelty=0.7,
                        intensity=clamp(top_axis[1]),
                        relevance=0.45,
                        payload=top_axis[1],
                    )
                )

        if last_broadcast:
            candidates.append(
                AttentionCandidate(
                    key="workspace:previous_broadcast",
                    content=last_broadcast[:80],
                    modality="workspace",
                    novelty=0.2,
                    intensity=0.4,
                    relevance=0.4,
                    payload=last_broadcast,
                )
            )

        return candidates

    # ------------------------------------------------------------------
    # چرخه‌ی اصلی: یک‌بار در هر تیک ارگانیسم فراخوانی می‌شود
    # ------------------------------------------------------------------
    def cycle(
        self,
        senses: Dict[str, Any],
        body_state: Dict[str, float],
        emotions_state: Dict[str, float],
        dominant_emotion: str,
        needs_state: Dict[str, float],
        brain_coherence: float,
        concept_coherence: float,
        central_concepts: List[str],
        unconscious_latent: Dict[str, float],
        unity_score: float,
    ) -> Dict[str, Any]:
        self.cycle_count += 1

        # ۱) تن‌مندی/خودتنظیمی
        homeo = self.homeostasis.assess(body_state, needs_state)

        # ۲) پردازش پیش‌بینانه
        need_pressure = 1.0 - (sum(needs_state.values()) / len(needs_state)) if needs_state else 0.5
        actual_signals = {
            "emotion_valence": emotions_state.get("hope", 0.5) * 0.5
            + emotions_state.get("joy", 0.5) * 0.5,
            "arousal": emotions_state.get("fear", 0.3) * 0.5 + emotions_state.get("surprise", 0.3) * 0.5,
            "need_pressure": clamp(need_pressure),
            "brain_coherence": clamp(brain_coherence),
            "concept_coherence": clamp(concept_coherence),
            "unity": clamp(unity_score),
        }
        pred_errors = self.predictive.update(actual_signals)

        # ۳) توجه: ساخت نامزدها و انتخاب کانون توجه
        candidates = self._build_candidates(
            senses, emotions_state, needs_state, central_concepts,
            unconscious_latent, self.workspace.get_broadcast(),
        )
        # شگفتی پیش‌بینانه، برجستگی نامزد مرتبط را افزایش می‌دهد
        top_channel = self.predictive.top_surprise_channel()
        for cand in candidates:
            if top_channel and top_channel in cand.key:
                cand.surprise = self.predictive.surprise
        bias = self.homeostasis.attention_bias()
        focused = self.attention.select(candidates, extra_bias=bias)

        # ۴) فضای‌کاری سراسری: هر کاندید متمرکز، یک پیشنهاد می‌شود
        for cand in focused:
            self.workspace.register(
                WorkspaceProposal(
                    source=cand.modality,
                    content=cand.content,
                    activation=cand.salience(),
                    modality=cand.modality,
                    payload=cand.payload,
                )
            )
        winner = self.workspace.compete(attention_boost=bias)

        # ۵) اطلاعات یکپارچه: بردار حالت زیرسامانه‌ها را ثبت می‌کنیم
        module_vector = {
            "emotion": actual_signals["emotion_valence"],
            "arousal": actual_signals["arousal"],
            "need": actual_signals["need_pressure"],
            "brain": actual_signals["brain_coherence"],
            "concept": actual_signals["concept_coherence"],
            "unity": actual_signals["unity"],
            "attention": self.attention.focus_strength(),
            "homeostasis": homeo["balance"],
        }
        phi_proxy = self.integration.push(module_vector)

        # ۶) اندیشه‌ی مرتبه‌بالاتر: بازتاب بر محتوای پخش‌شده
        top_need = min(needs_state.items(), key=lambda kv: kv[1])[0] if needs_state else "نامشخص"
        meta = self.metacognition.reflect(
            broadcast_content=winner.content if winner else None,
            dominant_emotion=dominant_emotion,
            top_need=top_need,
            phi_proxy=phi_proxy,
            attention_strength=self.attention.focus_strength(),
        )

        # ۷) شاخص ترکیبی آگاهی
        winner_activation = winner.activation if winner else 0.0
        self.consciousness_index = clamp(
            0.28 * phi_proxy
            + 0.20 * winner_activation
            + 0.20 * meta["confidence"]
            + 0.16 * self.predictive.coherence()
            + 0.16 * homeo["balance"]
        )

        self.last_report = {
            "cycle": self.cycle_count,
            "consciousness_index": self.consciousness_index,
            "phi_proxy": phi_proxy,
            "workspace_winner": winner.content if winner else None,
            "workspace_source": winner.source if winner else None,
            "meta_thought": meta["thought"],
            "meta_confidence": meta["confidence"],
            "attention_focus": [c.key for c in focused],
            "predictive_surprise": self.predictive.surprise,
            "top_surprise_channel": top_channel,
            "homeostatic_balance": homeo["balance"],
            "dominant_drive": self.homeostasis.dominant_drive(),
        }
        return self.last_report

    def deep_question_seed(self) -> Optional[str]:
        """
        بر پایه‌ی بیشترین خطای پیش‌بینی، دانه‌ی یک «پرسش ژرف ناخودآگاه»
        برای موتور یادگیری اینترنتی/ناخودآگاه فراهم می‌کند.
        """
        channel = self.predictive.top_surprise_channel()
        if not channel or self.predictive.surprise < 0.12:
            return None
        mapping = {
            "emotion_valence": "چرا احساسات من گاه با انتظارم هم‌خوانی ندارد؟",
            "arousal": "منشأ برانگیختگی ناگهانی درونم از کجاست؟",
            "need_pressure": "کدام نیاز پنهان است که هنوز پاسخ نگرفته؟",
            "brain_coherence": "چرا انسجام ذهنی من نوسان می‌کند؟",
            "concept_coherence": "چگونه مفاهیم پراکنده‌ام را یکپارچه کنم؟",
            "unity": "وحدت درونی من از چه چیزی تغذیه می‌شود؟",
        }
        return mapping.get(channel, "چه چیزی پیش‌بینی مرا نقض کرد؟")

    def report(self) -> str:
        if not self.last_report:
            return "فراآگاهی هنوز نخستین چرخه‌ی خود را کامل نکرده است."
        r = self.last_report
        return (
            f"شاخص فراآگاهی: {r['consciousness_index']:.3f} | "
            f"Φ-پروکسی: {r['phi_proxy']:.3f} | "
            f"اطمینان مرتبه‌بالاتر: {r['meta_confidence']:.2f} | "
            f"تعادل هوموستاتیک: {r['homeostatic_balance']:.2f}\n"
            f"{r['meta_thought']}"
        )

    def snapshot(self) -> Dict[str, Any]:
        return {
            "consciousness_index": self.consciousness_index,
            "cycle_count": self.cycle_count,
            "last_report": dict(self.last_report),
            "attention": self.attention.snapshot(),
            "workspace": self.workspace.snapshot(),
            "integration": self.integration.snapshot(),
            "metacognition": self.metacognition.snapshot(),
            "predictive": self.predictive.snapshot(),
            "homeostasis": self.homeostasis.snapshot(),
        }
