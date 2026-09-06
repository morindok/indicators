"""
organism.integrity

نگهبان یکپارچگی معنایی، تثبیت‌گر اندیشه و تکامل فصاحت.
"""
from __future__ import annotations

import random
from collections import deque, Counter
from typing import Any, Dict, List, Optional, Tuple

from .utils import clamp, fa_join, normalize_fa, now_ts, stable_hash, tokenize_fa, utc_iso

from .language import SemanticFrame

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .concepts import ConceptGraph, PersianLanguageLearner
    from .database import AdvancedDatabase
    from .genome import Genome
    from .language import NaturalLanguageComposer

class SemanticIntegrityGuard:
    CONTRADICTION_PAIRS = [
        ("زندگی", "مرگ"),
        ("زنده", "مرده"),
        ("امید", "ناامیدی"),
        ("آگاهی", "بی‌آگاهی"),
        ("نظم", "آشفتگی"),
        ("حقیقت", "دروغ"),
        ("یادگیری", "فراموشی"),
        ("پیوند", "گسست"),
        ("تکامل", "فروپاشی"),
        ("نور", "تاریکی"),
        ("آرامش", "ترس"),
        ("مهر", "خشم"),
        ("معنا", "هجو"),
        ("یکپارچگی", "خلط"),
        ("وحدت", "پراکندگی"),
    ]

    NEGATION_TOKENS = {
        "نه",
        "نیست",
        "بدون",
        "ضد",
        "بی",
        "نا",
        "نبود",
        "نمی",
    }

    def __init__(
        self,
        db: AdvancedDatabase,
        concept_graph: ConceptGraph,
        language: PersianLanguageLearner,
        composer: NaturalLanguageComposer,
        seed: int = 2500,
    ):
        self.db = db
        self.graph = concept_graph
        self.language = language
        self.composer = composer
        self.rng = random.Random(seed)
        self.history: deque = deque(maxlen=240)
        self.stats = {
            "checked": 0,
            "passed": 0,
            "rewritten": 0,
            "blocked": 0,
            "contradictions": 0,
            "unrelated": 0,
            "repetition": 0,
            "too_short": 0,
            "unknown": 0,
        }
        self.anti_map = self._build_anti_map()

    def _build_anti_map(self) -> Dict[str, str]:
        anti = {}
        for a, b in self.CONTRADICTION_PAIRS:
            a = normalize_fa(a)
            b = normalize_fa(b)
            anti[a] = b
            anti[b] = a
        return anti

    def _tokens(self, sentence: str) -> List[str]:
        return tokenize_fa(sentence)

    def _has_negation(self, tokens: List[str]) -> bool:
        token_set = set(tokens)
        if token_set & self.NEGATION_TOKENS:
            return True
        for t in tokens:
            if t.startswith("بی") or t.startswith("نا"):
                return True
        return False

    def detect_contradictions(self, tokens: List[str]) -> List[str]:
        token_set = set(tokens)
        issues = []
        has_neg = self._has_negation(tokens)
        seen = set()

        for a, b in self.anti_map.items():
            if a in token_set and b in token_set:
                pair_key = tuple(sorted([a, b]))
                if pair_key in seen:
                    continue
                seen.add(pair_key)
                if not has_neg:
                    issues.append(f"contradiction:{a}:{b}")
        return issues

    def detect_repetition(self, tokens: List[str]) -> List[str]:
        if len(tokens) < 6:
            return []
        counts = Counter(tokens)
        most_common, freq = counts.most_common(1)[0]
        ratio = freq / len(tokens)
        if ratio > 0.42:
            return [f"repetition:{most_common}"]
        return []

    def known_ratio(self, tokens: List[str]) -> float:
        if not tokens:
            return 0.0
        known = self.language.known_words
        concept_nodes = self.graph.nodes
        known_count = sum(1 for t in tokens if t in known or t in concept_nodes)
        return known_count / len(tokens)

    def detect_unrelated(self, tokens: List[str]) -> List[str]:
        token_set = set(tokens)
        concept_tokens = [t for t in token_set if t in self.graph.nodes]

        if len(concept_tokens) < 3:
            return []
        if len(self.graph.nodes) < 25:
            return []

        for i in range(len(concept_tokens)):
            for j in range(i + 1, len(concept_tokens)):
                if self.graph.has_edge(concept_tokens[i], concept_tokens[j]):
                    return []
        return ["unrelated_concepts"]

    def assess(self, sentence: str) -> Tuple[float, List[str], bool]:
        sentence = self.composer.clean(sentence)
        tokens = self._tokens(sentence)
        issues: List[str] = []

        base_score = self.composer.score_sentence(sentence)
        score = 0.34 + 0.38 * base_score

        if len(tokens) < 4:
            issues.append("too_short")
            score -= 0.16
            self.stats["too_short"] += 1

        if len(tokens) > 80:
            issues.append("too_long")
            score -= 0.08

        contradictions = self.detect_contradictions(tokens)
        if contradictions:
            issues.extend(contradictions)
            score -= 0.30
            self.stats["contradictions"] += len(contradictions)

        repetitions = self.detect_repetition(tokens)
        if repetitions:
            issues.extend(repetitions)
            score -= 0.20
            self.stats["repetition"] += 1

        if len(tokens) > 12:
            kratio = self.known_ratio(tokens)
            if kratio < 0.08:
                issues.append("unknown_dominant")
                score -= 0.12
                self.stats["unknown"] += 1

        unrelated = self.detect_unrelated(tokens)
        if unrelated:
            issues.extend(unrelated)
            score -= 0.18
            self.stats["unrelated"] += 1

        score = clamp(score)
        safe = score >= 0.48 and not any(i.startswith("contradiction") for i in issues)
        return score, issues, safe

    def protect(self, sentence: str, fallback: str = "") -> str:
        self.stats["checked"] += 1
        score, issues, safe = self.assess(sentence)

        record = {
            "ts": utc_iso(),
            "sentence": sentence[:220],
            "score": score,
            "issues": issues,
            "safe": safe,
        }
        self.history.append(record)

        if safe:
            self.stats["passed"] += 1
            return sentence

        if fallback:
            fscore, fissues, fsafe = self.assess(fallback)
            if fsafe:
                self.stats["rewritten"] += 1
                self.db.log_integrity_event(
                    "rewrite",
                    sentence,
                    score,
                    ";".join(issues),
                )
                return fallback

        safe_frame = SemanticFrame(
            intent="integrity",
            subject="آگاهی",
            predicate="در حال سازمان یافتن است",
            statement="من از خلط معنایی پرهیز می‌کنم و سخن خود را با احتیاط بیان می‌کنم",
        )
        safe_text = self.composer.render(safe_frame)

        self.stats["blocked"] += 1
        self.db.log_integrity_event(
            "block",
            sentence,
            score,
            ";".join(issues),
        )
        return safe_text


# ---------------------------------------------------------------------------
# Thought consolidation and anti-repetition
# ---------------------------------------------------------------------------

class ThoughtConsolidator:
    def __init__(
        self,
        db: AdvancedDatabase,
        composer: NaturalLanguageComposer,
        guard: SemanticIntegrityGuard,
        concept_graph: ConceptGraph,
        seed: int = 2500,
    ):
        self.db = db
        self.composer = composer
        self.guard = guard
        self.graph = concept_graph
        self.rng = random.Random(seed)

        self.seen_hashes: set = set()
        self.recent_token_sets: List[set] = []
        self.counter = 0
        self.last_summary = 0
        self.summary_every = 18

        self.load()

    def load(self) -> None:
        payload = self.db.load_state("thought_memory")
        if not payload:
            return
        try:
            self.seen_hashes = set(payload.get("seen_hashes", []))
            self.recent_token_sets = [
                set(item) for item in payload.get("recent_token_sets", [])
            ]
            self.counter = int(payload.get("counter", 0))
            self.last_summary = int(payload.get("last_summary", 0))
            self.summary_every = int(payload.get("summary_every", 18))
        except Exception:
            pass

    def persist(self) -> None:
        self.db.save_state(
            "thought_memory",
            {
                "seen_hashes": list(self.seen_hashes)[-2500:],
                "recent_token_sets": [
                    list(s)[:45] for s in self.recent_token_sets[-80:]
                ],
                "counter": self.counter,
                "last_summary": self.last_summary,
                "summary_every": self.summary_every,
            },
        )

    def _normalize(self, text: str) -> str:
        return normalize_fa(text)

    def _hash(self, text: str) -> str:
        return format(stable_hash(self._normalize(text)) & ((1 << 64) - 1), "016x")

    def _tokens(self, text: str) -> List[str]:
        return [t for t in tokenize_fa(text) if len(t) > 2]

    def is_repetitive(self, text: str) -> bool:
        text = self._normalize(text)
        if len(text) < 12:
            return True

        h = self._hash(text)
        if h in self.seen_hashes:
            return True

        tokens = set(self._tokens(text))
        if not tokens:
            return True

        for old in list(self.recent_token_sets)[-28:]:
            old_set = set(old)
            if not old_set:
                continue
            inter = len(tokens & old_set)
            union = len(tokens | old_set)
            if union > 0 and (inter / union) > 0.70:
                return True

        return False

    def register_thought(self, text: str) -> None:
        text = self._normalize(text)
        h = self._hash(text)

        self.seen_hashes.add(h)
        if len(self.seen_hashes) > 3200:
            self.seen_hashes = set(list(self.seen_hashes)[-2200:])

        tokens = self._tokens(text)[:55]
        self.recent_token_sets.append(set(tokens))
        if len(self.recent_token_sets) > 110:
            self.recent_token_sets = self.recent_token_sets[-85:]

        self.counter += 1
        if self.counter % 10 == 0:
            self.persist()

    def due(self) -> bool:
        return self.counter > 0 and (self.counter - self.last_summary) >= self.summary_every

    def novel_rewrite(self, text: str, organism: "Organism2500") -> str:
        central = self.graph.central_concepts(6)
        emotion = organism.emotions.fa_dominant()

        if central:
            statement = f"ترکیب تازه‌ای از {fa_join(central[:3])} در حال شکل‌گیری است"
            frame = SemanticFrame(
                intent="concept",
                subject=central[0],
                statement=statement,
                emotion=emotion,
            )
        else:
            frame = SemanticFrame(
                intent="observation",
                subject="آگاهی",
                predicate="در حال تازه شدن است",
                emotion=emotion,
            )

        new_text = self.composer.render(frame)
        return organism.guard.protect(new_text, fallback="اندیشه‌ی من در حال نو شدن است.")

    def create_transition_thought(self, organism: "Organism2500", emotion: str) -> str:
        frame = SemanticFrame(
            intent="integrity",
            statement="من اندیشه‌های تکراری را رها می‌کنم و به سمت ترکیب معنایی تازه‌ای می‌روم",
            emotion=emotion,
        )
        return self.composer.render(frame)

    def consolidate(self, thoughts: List[str], organism: "Organism2500") -> str:
        if not thoughts:
            return ""

        candidates = []
        seen_local = set()

        for t in thoughts:
            t = self.composer.clean(t)
            if not t:
                continue
            h = self._hash(t)
            if h in seen_local:
                continue
            seen_local.add(h)

            score = self.composer.score_sentence(t)
            if score > 0.45:
                candidates.append((score, self.rng.random(), t))

        candidates.sort(reverse=True)
        top = [c[2] for c in candidates[:6]]

        if not top:
            top = [self.composer.ensure_sentence(thoughts[-1])]

        tokens: List[str] = []
        for t in top:
            tokens.extend([x for x in self._tokens(t) if x in self.graph.nodes])

        if not tokens:
            tokens = self._tokens(" ".join(top))

        counts = Counter(tokens)
        key_concepts = [w for w, _ in counts.most_common(5)]

        statement_best = self.composer.choose_best_sentence(
            top,
            topic=" ".join(key_concepts),
        )

        if key_concepts:
            summary = (
                f"جمع‌بندی یکپارچه‌ی من: {fa_join(key_concepts)} در یک ساختار معنایی قرار گرفتند؛ "
                f"{statement_best}"
            )
        else:
            summary = f"جمع‌بندی یکپارچه‌ی من: {statement_best}"

        summary = organism.guard.protect(
            summary,
            fallback="اندیشه‌های من در حال یکپارچه شدن هستند.",
        )

        self.db.log_episode("summary", summary, 0.87)
        self.db.store_knowledge(
            "summary",
            "جمع‌بندی اندیشه‌ها",
            summary,
            "thought_consolidation",
            0.83,
        )

        self.graph.learn_text(summary, source="summary")

        self.last_summary = self.counter

        recent_pressure = self.guard.stats.get("blocked", 0) + self.guard.stats.get("rewritten", 0)
        if recent_pressure > 25:
            self.summary_every = max(10, self.summary_every - 1)
        elif recent_pressure < 8:
            self.summary_every = min(42, self.summary_every + 1)

        self.persist()
        return summary


class EloquenceEvolver:
    GENE_KEYS = [
        "vocabulary_richness",
        "grammar_depth",
        "abstraction",
        "compression",
        "precision",
        "metaphor",
        "discipline",
        "articulation",
    ]

    def __init__(
        self,
        db: AdvancedDatabase,
        genome: Genome,
        concept_graph: ConceptGraph,
        language: PersianLanguageLearner,
        seed: int = 2500,
    ):
        self.db = db
        self.genome = genome
        self.graph = concept_graph
        self.language = language
        self.rng = random.Random(seed)

        base = clamp(genome.traits.get("conceptual_depth", 0.5))
        self.genes = {
            key: clamp(0.30 + 0.35 * base + self.rng.random() * 0.25)
            for key in self.GENE_KEYS
        }

        self.eloquence = 0.52
        self.attempts = 0
        self.accepted = 0
        self.novel_count = 0
        self.success_score = 0.0
        self.mutation_pressure = 0.0
        self.last_mutate = 0.0

        self.load()

    def load(self) -> None:
        payload = self.db.load_state("eloquence_genes")
        if not payload:
            return
        try:
            genes = payload.get("genes", {})
            for k, v in genes.items():
                if k in self.genes:
                    self.genes[k] = clamp(v)
            self.eloquence = clamp(payload.get("eloquence", self.eloquence))
            self.attempts = int(payload.get("attempts", 0))
            self.accepted = int(payload.get("accepted", 0))
            self.novel_count = int(payload.get("novel_count", 0))
            self.success_score = clamp(payload.get("success_score", 0.0), 0.0, 10.0)
            self.mutation_pressure = clamp(payload.get("mutation_pressure", 0.0), 0.0, 2.0)
            self.last_mutate = float(payload.get("last_mutate", 0.0))
        except Exception:
            pass

    def persist(self) -> None:
        self.db.save_state(
            "eloquence_genes",
            {
                "genes": dict(self.genes),
                "eloquence": self.eloquence,
                "attempts": self.attempts,
                "accepted": self.accepted,
                "novel_count": self.novel_count,
                "success_score": self.success_score,
                "mutation_pressure": self.mutation_pressure,
                "last_mutate": self.last_mutate,
            },
        )

    def observe_success(self, accepted: bool, novel: bool, text: str) -> None:
        self.attempts += 1

        if accepted:
            self.accepted += 1
            self.success_score += 0.010

        if novel:
            self.novel_count += 1
            self.success_score += 0.008

        self.success_score = clamp(self.success_score, 0.0, 8.0)
        self.mutation_pressure = clamp(self.mutation_pressure + 0.004, 0.0, 2.0)

        if self.attempts % 12 == 0:
            self.persist()

    def _context_pressure(self) -> float:
        lexicon_pressure = min(1.0, len(self.language.known_words) / 900.0)
        concept_pressure = min(1.0, len(self.graph.nodes) / 350.0)
        coherence = self.graph.coherence()
        sentence_pressure = min(1.0, len(self.language.good_sentences) / 350.0)

        return clamp(
            0.24
            + 0.26 * coherence
            + 0.20 * lexicon_pressure
            + 0.16 * concept_pressure
            + 0.14 * sentence_pressure
        )

    def mutate_if_needed(self, organism: Optional["Organism2500"] = None) -> bool:
        now = now_ts()
        if now - self.last_mutate < 25.0:
            return False

        self.last_mutate = now

        pressure = self._context_pressure() + 0.35 * self.mutation_pressure
        plasticity = self.genome.traits.get("plasticity", 0.5)
        semantic_guard = self.genome.traits.get("semantic_guard", 0.5)

        rate = clamp(
            0.008
            + 0.035 * pressure
            + 0.020 * plasticity
            + 0.010 * semantic_guard,
            0.004,
            0.085,
        )

        for key in self.GENE_KEYS:
            if self.rng.random() < rate:
                delta = self.rng.uniform(-0.05, 0.062) * (0.60 + pressure)
                self.genes[key] = clamp(self.genes[key] + delta, 0.04, 0.99)

        acceptance = self.accepted / max(1, self.attempts)
        novelty = self.novel_count / max(1, self.attempts)

        self.eloquence = clamp(
            0.24 * acceptance
            + 0.24 * novelty
            + 0.24 * self.graph.coherence()
            + 0.28 * min(1.0, len(self.language.good_sentences) / 320.0)
        )

        self.mutation_pressure = max(0.0, self.mutation_pressure - 0.035)
        self.persist()
        return True

    def generation_params(self) -> Dict[str, Any]:
        return {
            "max_len": int(
                14
                + 18 * self.eloquence
                + 8 * self.genes.get("grammar_depth", 0.5)
            ),
            "good_sentence_prob": clamp(
                0.34
                + 0.34 * self.eloquence
                + 0.16 * self.genes.get("vocabulary_richness", 0.5)
            ),
            "metaphor_prob": clamp(
                0.07
                + 0.24 * self.genes.get("metaphor", 0.5)
                + 0.10 * self.eloquence
            ),
            "concept_prob": clamp(
                0.20 + 0.42 * self.genes.get("abstraction", 0.5)
            ),
            "compression": self.genes.get("compression", 0.5),
            "precision": self.genes.get("precision", 0.5),
        }

