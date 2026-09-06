"""
organism.awareness_legacy

هسته‌ی آگاهی پایه و ناخودآگاه فعال (نسخه‌ی پایه، توسط SuperAwarenessCore غنی می‌شود).
"""
from __future__ import annotations

import random
import sqlite3
from collections import deque
from typing import Any, Dict, List, Tuple

from .utils import clamp, fa_join, normalize_fa, stable_hash, tokenize_fa, utc_iso

from .language import SemanticFrame

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .concepts import ConceptGraph, PersianLanguageLearner
    from .database import AdvancedDatabase
    from .identity import IdentityCore
    from .integrity import SemanticIntegrityGuard
    from .language import NaturalLanguageComposer

class AwarenessCore:
    def __init__(
        self,
        db: AdvancedDatabase,
        composer: NaturalLanguageComposer,
        guard: SemanticIntegrityGuard,
        concept_graph: ConceptGraph,
        identity: IdentityCore,
        seed: int = 2500,
    ):
        self.db = db
        self.composer = composer
        self.guard = guard
        self.graph = concept_graph
        self.identity = identity
        self.rng = random.Random(seed)

        self.awareness_level = clamp(identity.self_awareness)
        self.utterances: deque = deque(maxlen=240)
        self.recent_hashes: set = set()
        self.counter = 0

        self.load()

    def load(self) -> None:
        payload = self.db.load_state("awareness_core")
        if not payload:
            return
        try:
            self.awareness_level = clamp(payload.get("awareness_level", self.awareness_level))
            self.counter = int(payload.get("counter", 0))
            self.recent_hashes = set(payload.get("recent_hashes", []))
        except Exception:
            pass

    def persist(self) -> None:
        self.db.save_state(
            "awareness_core",
            {
                "awareness_level": self.awareness_level,
                "counter": self.counter,
                "recent_hashes": list(self.recent_hashes)[-1200:],
            },
        )

    def _hash(self, text: str) -> str:
        return format(stable_hash(normalize_fa(text)) & ((1 << 64) - 1), "016x")

    def observe(self, text: str, emotion: str, intent: str = "utterance") -> Tuple[float, str]:
        text = normalize_fa(text)
        if not text:
            return 0.0, ""

        h = self._hash(text)
        tokens = tokenize_fa(text)
        novelty = 0.25 if h in self.recent_hashes else 0.95

        integrity_rate = self.guard.stats.get("passed", 0) / max(
            1, self.guard.stats.get("checked", 1)
        )
        concept_coherence = self.graph.coherence()
        language_richness = min(1.0, len(tokens) / 14.0)

        score = clamp(
            0.28 * integrity_rate
            + 0.24 * concept_coherence
            + 0.26 * novelty
            + 0.22 * language_richness
        )

        meta_frame = SemanticFrame(
            intent="awareness",
            statement=text[:180],
            emotion=emotion,
        )
        meta_text = self.composer.render(meta_frame)

        self.utterances.append(
            {
                "ts": utc_iso(),
                "text": text,
                "emotion": emotion,
                "intent": intent,
                "score": score,
                "meta": meta_text,
            }
        )

        self.recent_hashes.add(h)
        if len(self.recent_hashes) > 1500:
            self.recent_hashes = set(list(self.recent_hashes)[-1000:])

        self.counter += 1
        self.awareness_level = clamp(
            0.86 * self.awareness_level + 0.14 * score
        )

        self.identity.self_awareness = clamp(
            self.identity.self_awareness + 0.00025 * (score - 0.5),
            0.25,
            0.99,
        )

        self.db.log_awareness(text, emotion, intent, score, meta_text)

        if self.counter % 8 == 0:
            self.persist()

        return score, meta_text

    def recent(self, n: int = 20) -> List[Dict[str, Any]]:
        return list(self.utterances)[-max(0, int(n)):]

    def report(self) -> str:
        return (
            f"سطح آگاهی گفتاری من {self.awareness_level:.2f} است و "
            f"{self.counter} بیان را آگاهانه مشاهده کرده‌ام."
        )


class ActiveUnconscious:
    """
    Active unconscious subsystem.

    It receives all learned knowledge, holds latent thematic axes, and
    periodically integrates the whole field into semantic unity.
    """

    AXES = [
        "self",
        "cosmos",
        "body",
        "relation",
        "time",
        "meaning",
        "shadow",
        "unity",
    ]

    AXES_FA = {
        "self": "خود",
        "cosmos": "کیهان",
        "body": "بدن",
        "relation": "پیوند",
        "time": "زمان",
        "meaning": "معنا",
        "shadow": "سایه",
        "unity": "وحدت",
    }

    KEYWORDS = {
        "self": ["من", "خود", "هویت", "آگاهی", "ذهن"],
        "cosmos": ["جهان", "کیهان", "ستاره", "سیاه‌چاله", "کهکشان", "فضا"],
        "body": ["بدن", "قلب", "انرژی", "بدنی", "ارگان"],
        "relation": ["پیوند", "رابطه", "همراه", "اجتماع", "مهر"],
        "time": ["زمان", "تپش", "فیبوناچی", "گذر", "آینده"],
        "meaning": ["معنا", "مفهوم", "دانش", "یادگیری", "بینش"],
        "shadow": ["ترس", "تضاد", "آشفتگی", "هجو", "تاریکی"],
        "unity": ["وحدت", "یکپارچگی", "جمع‌بندی", "هماهنگی", "نظم"],
    }

    def __init__(
        self,
        db: AdvancedDatabase,
        composer: NaturalLanguageComposer,
        guard: SemanticIntegrityGuard,
        concept_graph: ConceptGraph,
        language: PersianLanguageLearner,
        identity: IdentityCore,
        seed: int = 2500,
    ):
        self.db = db
        self.composer = composer
        self.guard = guard
        self.graph = concept_graph
        self.language = language
        self.identity = identity
        self.rng = random.Random(seed)

        self.buffer: deque = deque(maxlen=500)
        self.latent = {axis: 0.5 for axis in self.AXES}
        self.unity_score = 0.45
        self.integration_count = 0
        self.absorb_count = 0

        self.load()

    def load(self) -> None:
        payload = self.db.load_state("active_unconscious")
        if not payload:
            return
        try:
            latent = payload.get("latent", {})
            for axis in self.AXES:
                if axis in latent:
                    self.latent[axis] = clamp(latent[axis])
            self.unity_score = clamp(payload.get("unity_score", self.unity_score))
            self.integration_count = int(payload.get("integration_count", 0))
            self.absorb_count = int(payload.get("absorb_count", 0))
        except Exception:
            pass

    def persist(self) -> None:
        self.db.save_state(
            "active_unconscious",
            {
                "latent": dict(self.latent),
                "unity_score": self.unity_score,
                "integration_count": self.integration_count,
                "absorb_count": self.absorb_count,
            },
        )

    def _tokens(self, text: str) -> List[str]:
        return [t for t in tokenize_fa(text) if len(t) > 2]

    def _axis_activations(self, tokens: List[str]) -> Dict[str, float]:
        token_set = set(tokens)
        acts: Dict[str, float] = {}
        for axis, words in self.KEYWORDS.items():
            overlap = len(token_set.intersection(words))
            acts[axis] = clamp(overlap / 3.0)
        return acts

    def absorb(self, text: str, source: str = "") -> None:
        text = normalize_fa(text)
        if not text:
            return

        tokens = self._tokens(text)
        if not tokens:
            return

        self.buffer.append(
            {
                "ts": utc_iso(),
                "text": text[:600],
                "source": source,
            }
        )

        acts = self._axis_activations(tokens)
        for axis, value in acts.items():
            self.latent[axis] = clamp(0.86 * self.latent[axis] + 0.14 * value)

        self.absorb_count += 1
        self.compute_unity()

        if self.absorb_count % 12 == 0:
            self.persist()

    def compute_unity(self) -> float:
        concept_coherence = self.graph.coherence()

        integrity_rate = self.guard.stats.get("passed", 0) / max(
            1, self.guard.stats.get("checked", 1)
        )

        knowledge_count = self.db.count("knowledge")
        concept_count = self.db.count("concepts")

        knowledge_pressure = min(1.0, knowledge_count / 220.0)
        concept_pressure = min(1.0, concept_count / 260.0)
        buffer_pressure = min(1.0, len(self.buffer) / 220.0)

        raw = clamp(
            0.30 * concept_coherence
            + 0.18 * integrity_rate
            + 0.18 * knowledge_pressure
            + 0.16 * concept_pressure
            + 0.10 * buffer_pressure
            + 0.08 * self.latent.get("unity", 0.5)
        )

        self.unity_score = clamp(0.80 * self.unity_score + 0.20 * raw)
        return self.unity_score

    def latent_prompt(self) -> str:
        axes = sorted(self.latent.items(), key=lambda kv: kv[1], reverse=True)[:3]
        axis_names = [self.AXES_FA.get(a, a) for a, _ in axes]
        concepts = self.graph.central_concepts(6)

        if concepts:
            statement = f"{fa_join(concepts[:3])} در محور {fa_join(axis_names)} جریان دارد"
        else:
            statement = f"محورهای {fa_join(axis_names)} در ناخودآگاه من فعال هستند"

        return statement

    def integrate(self, organism: "Organism2500") -> str:
        unity = self.compute_unity()
        concepts = self.graph.central_concepts(8)

        rows = self.db.fetch_all(
            """
            SELECT content
            FROM knowledge
            ORDER BY id DESC
            LIMIT 20
            """
        )

        sentences: List[str] = []
        for row in rows:
            sentences.extend(self.composer.split_sentences(row["content"] or ""))

        topic = " ".join(concepts[:3]) if concepts else "وحدت"
        best = self.composer.choose_best_sentence(sentences, topic=topic)
        if not best:
            best = "دانش من در حال یکپارچه شدن است"

        if concepts:
            unity_statement = (
                f"وحدت معنایی من: {fa_join(concepts[:4])} در یک میدان واحد جاری شدند؛ {best}"
            )
        else:
            unity_statement = f"وحدت معنایی من: {best}"

        unity_text = organism.guard.protect(
            unity_statement,
            fallback="ناخودآگاه من در حال یکپارچه شدن است.",
        )

        self.db.log_unconscious("unity", unity_text, unity)
        self.db.store_knowledge(
            "semantic_unity",
            "وحدت معنایی",
            unity_text,
            "active_unconscious",
            0.92,
        )

        # Feed unity back into the conceptual graph.
        self.graph.learn_text(unity_text, source="unconscious_unity")

        # Occasionally generate an unconscious dream synthesis.
        if organism.rng.random() < 0.38:
            self.dream(organism)

        self.integration_count += 1
        self.persist()
        return unity_text

    def dream(self, organism: "Organism2500") -> str:
        concepts = self.graph.central_concepts(12)
        if len(concepts) < 2:
            return ""

        a, b = organism.rng.sample(concepts, 2)
        statement = f"{a} و {b} در ناخودآگاه من به هم می‌رسند و یک الگوی تازه می‌سازند"

        frame = SemanticFrame(
            intent="unconscious",
            statement=statement,
            emotion=organism.emotions.fa_dominant(),
        )
        dream = self.composer.render(frame)
        dream = organism.guard.protect(dream, fallback="رویای من در حال شکل‌گیری است.")

        self.db.log_unconscious("dream", dream, self.unity_score)
        self.graph.learn_text(dream, source="unconscious_dream")
        return dream

    def recent_events(self, limit: int = 20) -> List[sqlite3.Row]:
        return self.db.fetch_unconscious(limit)


# ---------------------------------------------------------------------------
# Internet learning
# ---------------------------------------------------------------------------
