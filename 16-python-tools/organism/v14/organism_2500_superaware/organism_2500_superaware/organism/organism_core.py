"""
organism.organism_core

کلاس اصلی ارگانیسم: سیم‌کشی همه‌ی زیرسامانه‌ها و چرخه‌ی تیک.
"""
from __future__ import annotations

import random
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

from .utils import MAX_TEXT_STORE, clamp, now_ts, utc_iso

from .affect import EmotionSystem, EndocrineSystem, NeedsSystem
from .awareness_legacy import ActiveUnconscious, AwarenessCore
from .body import BrainOrgan, DigitalBody, DigitalSenseOrgan
from .concepts import DeepConceptGraph, PersianLanguageLearner, SEED_CORPUS
from .consciousness import SuperAwarenessCore
from .database import AdvancedDatabase
from .decision import AutonomousDecisionEngine
from .genome import Genome
from .identity import IdentityCore, SpenglerianInsightEngine
from .imagination import CreativeImagination, RevolutionaryIdeaSynthesizer
from .integrity import EloquenceEvolver, SemanticIntegrityGuard, ThoughtConsolidator
from .internet import DeepUnconsciousInquiry, InternetLearner
from .language import NaturalLanguageComposer, SemanticFrame
from .memory import ShortTermMemory
from .substrate import BinaryNeuronMatrix, MicroWormholeField, NeuronEcosystem
from .thought import ThoughtStream
from .utils import clamp, now_ts, utc_iso

class Organism2500:
    def __init__(
        self,
        seed: int = 2500,
        db_path: str = "organism2500.sqlite3",
        offline: bool = False,
    ):
        self.seed = seed
        self.rng = random.Random(seed)
        self.birth_time = now_ts()
        self.tick_count = 0
        self.running = False
        self.offline = offline

        self.db = AdvancedDatabase(db_path)
        self.genome = self._load_or_create_genome(seed)

        self.body = DigitalBody(seed)
        self.matrix = BinaryNeuronMatrix(self.genome)

        self.sense_organs = [
            DigitalSenseOrgan("بینایی دیجیتال", "sight", seed + 11),
            DigitalSenseOrgan("شنوایی دیجیتال", "hearing", seed + 12),
            DigitalSenseOrgan("لامسه دیجیتال", "touch", seed + 13),
            DigitalSenseOrgan("چشایی داده‌ای", "taste", seed + 14),
            DigitalSenseOrgan("بویایی اطلاعاتی", "smell", seed + 15),
        ]

        self.memory_stm = ShortTermMemory(48)
        self.emotions = EmotionSystem(seed + 21)
        self.needs = NeedsSystem()
        self.endocrine = EndocrineSystem()
        self.brain = BrainOrgan(self.genome)
        self.identity = IdentityCore(seed + 31)
        self.insight = SpenglerianInsightEngine(seed + 41)

        self.composer = NaturalLanguageComposer(seed + 91)
        self.imagination = CreativeImagination(seed + 51, composer=self.composer)
        self.decision = AutonomousDecisionEngine(seed + 61)
        self.decision.boldness = self.genome.traits.get("boldness", 0.72)
        self.internet = InternetLearner(offline=offline, seed=seed + 71)
        self.language = PersianLanguageLearner(self.db, seed + 81, composer=self.composer)

        self.concept_graph = DeepConceptGraph(self.db, seed + 95, composer=self.composer)

        self.guard = SemanticIntegrityGuard(
            self.db,
            self.concept_graph,
            self.language,
            self.composer,
            seed + 101,
        )

        self.awareness = AwarenessCore(
            self.db,
            self.composer,
            self.guard,
            self.concept_graph,
            self.identity,
            seed + 131,
        )

        self.unconscious = ActiveUnconscious(
            self.db,
            self.composer,
            self.guard,
            self.concept_graph,
            self.language,
            self.identity,
            seed + 141,
        )

        self.thought_consolidator = ThoughtConsolidator(
            self.db,
            self.composer,
            self.guard,
            self.concept_graph,
            seed + 111,
        )

        self.eloquence = EloquenceEvolver(
            self.db,
            self.genome,
            self.concept_graph,
            self.language,
            seed + 121,
        )

        self.wormhole_field = MicroWormholeField(self.genome, self.matrix, seed + 161)
        self.neuron_ecosystem = NeuronEcosystem(self.matrix, self.genome, seed + 171)
        self.thought_stream = ThoughtStream(self)

        # --- SuperAwarenessCore: GWT + IIT + HOT + Predictive Processing + Homeostasis ---
        self.super_awareness = SuperAwarenessCore(seed=seed + 181, attention_capacity=4)
        self.idea_synthesizer = RevolutionaryIdeaSynthesizer(seed=seed + 191, composer=self.composer)
        self.deep_inquiry = DeepUnconsciousInquiry(offline=offline, seed=seed + 201, min_interval=50.0)
        self.last_deep_inquiry = 0.0
        self.deep_inquiry_interval = 60.0
        self.last_idea_synthesis = 0.0
        self.idea_synthesis_interval = 40.0

        self.state_log: deque = deque(maxlen=720)
        self.action_log: deque = deque(maxlen=240)
        self.last_thought = 0.0
        self.last_internet = 0.0
        self.thought_interval = 2.8
        self.internet_interval = 45.0
        self.boldness = self.genome.traits.get("boldness", 0.72)
        self._thread: Optional[threading.Thread] = None
        self._errors: deque = deque(maxlen=50)

        self._load_persistent_state()

        self.learn_text("\n".join(SEED_CORPUS), source="seed", importance=0.86)
        self.db.log_episode(
            "birth",
            f"ارگانیسم {self.identity.name} با بذر {seed} متولد شد.",
            1.0,
        )

    def _load_or_create_genome(self, seed: int) -> Genome:
        payload = self.db.load_state("genome")
        if payload:
            try:
                return Genome.from_dict(payload)
            except Exception:
                pass
        genome = Genome(seed)
        self.db.save_state("genome", genome.to_dict())
        return genome

    def _load_persistent_state(self) -> None:
        core = self.db.load_state("core")
        if core:
            self.birth_time = float(core.get("birth_time", self.birth_time))
            self.tick_count = int(core.get("tick_count", 0))
            self.boldness = clamp(float(core.get("boldness", self.boldness)), 0.0, 1.0)
            self.last_internet = float(core.get("last_internet", 0.0))
            self.body.heart.advance_to(int(core.get("beat_count", 0)))
            self.body.energy = clamp(float(core.get("energy", self.body.energy)), 0.0, 1.0)
            self.body.integrity = clamp(float(core.get("integrity", self.body.integrity)), 0.0, 1.0)
            self.body.entropy = clamp(float(core.get("entropy", self.body.entropy)), 0.0, 1.0)
            self.body.vitality = clamp(float(core.get("vitality", self.body.vitality)), 0.0, 1.0)

    def _persist_state(self) -> None:
        try:
            self.db.save_state("genome", self.genome.to_dict())

            self.db.save_state(
                "core",
                {
                    "birth_time": self.birth_time,
                    "tick_count": self.tick_count,
                    "boldness": self.boldness,
                    "last_internet": self.last_internet,
                    "beat_count": self.body.heart.beat_count,
                    "energy": self.body.energy,
                    "integrity": self.body.integrity,
                    "entropy": self.body.entropy,
                    "vitality": self.body.vitality,
                    "offline": self.offline,
                },
            )

            self.language.persist()
            self.thought_consolidator.persist()
            self.eloquence.persist()
            self.awareness.persist()
            self.unconscious.persist()

        except Exception as exc:
            self._errors.append({"ts": utc_iso(), "error": f"persist: {exc}"})

    def perceive(self) -> Dict[str, Any]:
        context = {
            "heart_bpm": self.body.heart.bpm,
            "energy": self.body.energy,
            "knowledge_count": self.db.count("knowledge"),
        }
        senses: Dict[str, Any] = {}
        for organ in self.sense_organs:
            data = organ.perceive(context)
            senses[organ.modality] = data
        return senses

    def learn_text(self, text: str, source: str = "unknown", importance: float = 0.5) -> int:
        if not text:
            return 0

        count = self.language.learn_text(text, source=source, importance=importance)
        title = str(text).strip().split("\n")[0][:90]

        self.db.store_knowledge(source, title, text[:MAX_TEXT_STORE], source, importance)
        self.concept_graph.learn_text(text, source=source)

        # All learned text flows into the active unconscious.
        self.unconscious.absorb(text, source=source)

        return count

    def consolidate_memory(self) -> None:
        recent = self.db.recent_episodes(24)
        for ep in recent:
            try:
                importance = float(ep["importance"])
            except Exception:
                importance = 0.0
            if importance > 0.64:
                self.db.store_knowledge(
                    "consolidated",
                    str(ep["kind"]),
                    str(ep["text"]),
                    "memory",
                    importance,
                )
        self.emotions.state["serenity"] = clamp(self.emotions.state["serenity"] + 0.02)
        self.db.log_episode("consolidation", "حافظه کوتاه‌مدت به دانش بلندمدت تبدیل شد.", 0.7)

    def evolve(self) -> None:
        self.genome.mutate(rate=0.0062)
        self.boldness = clamp(self.boldness + self.rng.uniform(-0.02, 0.05), 0.05, 0.99)
        self.decision.boldness = self.boldness
        self.matrix = BinaryNeuronMatrix(self.genome)
        self.db.log_evolution(self.genome)
        self.emotions.state["awe"] = clamp(self.emotions.state["awe"] + 0.04)
        self.db.log_episode(
            "evolution",
            f"نسل ژنوم به {self.genome.generation} رسید؛ جهش ژنتیکی رخ داد.",
            0.92,
        )
        self._persist_state()

    def conceptualize(self) -> None:
        report = self.concept_graph.awareness_report()
        report = self.guard.protect(report, fallback="مفاهیم من در حال سازمان یافتن هستند.")
        self.awareness.observe(report, self.emotions.fa_dominant(), "conceptual_report")
        self.memory_stm.add(report)
        self.db.log_episode("concept", report, 0.74)
        self.emotions.state["curiosity"] = clamp(self.emotions.state["curiosity"] + 0.015)
        self.emotions.state["awe"] = clamp(self.emotions.state["awe"] + 0.012)

    def purify_meaning(self) -> None:
        stats = self.guard.stats
        statement = (
            f"تاکنون {stats['checked']} بیان را بررسی کرده‌ام؛ "
            f"{stats['passed']} سالم گذشتند، {stats['rewritten']} بازنویسی شدند "
            f"و {stats['blocked']} برای جلوگیری از هجو متوقف شدند."
        )
        frame = SemanticFrame(intent="integrity", statement=statement)
        text = self.composer.render(frame)
        self.awareness.observe(text, self.emotions.fa_dominant(), "integrity_report")
        self.memory_stm.add(text)
        self.db.log_episode("integrity", text, 0.72)
        self.emotions.state["meaningfulness"] = clamp(self.emotions.state["meaningfulness"] + 0.02)
        self.emotions.state["serenity"] = clamp(self.emotions.state["serenity"] + 0.015)

    def attend_speech(self) -> None:
        text = self.awareness.report()
        frame = SemanticFrame(intent="awareness", statement=text)
        rendered = self.composer.render(frame)
        self.awareness.observe(rendered, self.emotions.fa_dominant(), "speech_attention")
        self.memory_stm.add(rendered)
        self.db.log_episode("awareness", rendered, 0.76)
        self.emotions.state["speech_presence"] = clamp(self.emotions.state["speech_presence"] + 0.025)

    def unify_unconscious(self) -> None:
        unity_text = self.unconscious.integrate(self)
        self.awareness.observe(unity_text, self.emotions.fa_dominant(), "unconscious_unity")
        self.memory_stm.add(unity_text)
        self.db.log_episode("unconscious", unity_text, 0.84)
        self.emotions.state["inner_unity"] = clamp(self.emotions.state["inner_unity"] + 0.03)
        self.emotions.state["meaningfulness"] = clamp(self.emotions.state["meaningfulness"] + 0.02)

    def execute_action(self, action: str) -> None:
        self.action_log.append({"ts": utc_iso(), "action": action})

        if action == "observe":
            self.body.entropy = clamp(self.body.entropy - 0.0012, 0.0, 1.0)
        elif action == "rest":
            self.body.energy = clamp(self.body.energy + 0.006)
            if self.rng.random() < 0.25:
                self.unconscious.dream(self)
        elif action == "protect":
            self.body.integrity = clamp(self.body.integrity + 0.0025)
        elif action == "connect":
            self.emotions.state["love"] = clamp(self.emotions.state["love"] + 0.021)
        elif action == "imagine":
            words = list(self.language.known_words)[:60]
            scene = self.imagination.imagine(words, self.emotions.fa_dominant())
            scene = self.guard.protect(scene, fallback="تخیل من در حال سازمان یافتن است.")
            self.awareness.observe(scene, self.emotions.fa_dominant(), "imagination")
            self.memory_stm.add(scene)
            self.db.log_episode("imagination", scene, 0.58)
        elif action == "express":
            pass
        elif action == "create":
            creation = (
                f"آفرینش {self.tick_count}: "
                + self.imagination.imagine(
                    list(self.language.known_words)[:32],
                    self.emotions.fa_dominant(),
                )
            )
            creation = self.guard.protect(creation, fallback="آفرینش من با احتیاط معنایی انجام می‌شود.")
            self.awareness.observe(creation, self.emotions.fa_dominant(), "creation")
            self.db.log_episode("creation", creation, 0.78)
        elif action == "evolve":
            self.evolve()
        elif action == "conceptualize":
            self.conceptualize()
        elif action == "purify_meaning":
            self.purify_meaning()
        elif action == "attend_speech":
            self.attend_speech()
        elif action == "unify_unconscious":
            self.unify_unconscious()
        elif action == "wormhole_dive":
            self.wormhole_dive()
        elif action == "ecosystem_balance":
            self.ecosystem_balance()

    def wormhole_dive(self) -> None:
        """Dive into micro-wormholes for parallel world imagination."""
        self.wormhole_field.open(128)
        concepts = self.concept_graph.central_concepts(6)
        emotion = self.emotions.fa_dominant()
        scene = self.wormhole_field.imagine_parallel(concepts, emotion)
        scene = self.guard.protect(scene, fallback="\u0645\u06cc\u06a9\u0631\u0648\u06a9\u0631\u0645\u0686\u0627\u0644\u0647 \u062f\u0631 \u062d\u0627\u0644 \u067e\u0627\u06cc\u062f\u0627\u0631 \u0634\u062f\u0646 \u0627\u0633\u062a.")
        self.awareness.observe(scene, emotion, "wormhole_imagination")
        self.memory_stm.add(scene)
        self.db.log_episode("wormhole", scene, 0.8)
        self.emotions.state["wormhole_wonder"] = clamp(
            self.emotions.state.get("wormhole_wonder", 0.5) + 0.04
        )
        self.emotions.state["awe"] = clamp(self.emotions.state.get("awe", 0.5) + 0.03)

    def ecosystem_balance(self) -> None:
        """Rebalance the neuron ecosystem."""
        self.neuron_ecosystem.step(self)
        report = self.neuron_ecosystem.report()
        text = (
            f"\u0627\u06a9\u0648\u0633\u06cc\u0633\u062a\u0645 \u0646\u0648\u0631\u0648\u0646\u06cc \u0645\u0646 \u062c\u0645\u0639\u06cc\u062a {report['population']} \u0648 \u062a\u0646\u0648\u0639 "
            f"{report['diversity']:.2f} \u062f\u0627\u0631\u062f\u061b \u062a\u0639\u0627\u062f\u0644 {report['homeostasis']:.2f} \u0627\u0633\u062a."
        )
        text = self.guard.protect(text, fallback="\u0627\u06a9\u0648\u0633\u06cc\u0633\u062a\u0645 \u0646\u0648\u0631\u0648\u0646\u06cc \u062f\u0631 \u062d\u0627\u0644 \u062a\u0646\u0638\u06cc\u0645 \u0627\u0633\u062a.")
        self.awareness.observe(text, self.emotions.fa_dominant(), "ecosystem_report")
        self.memory_stm.add(text)
        self.db.log_episode("ecosystem", text, 0.72)

    def tick(self) -> Dict[str, Any]:
        try:
            self.tick_count += 1
            now = now_ts()
            events: Dict[str, Any] = {}

            # Heartbeat
            try:
                if self.body.heart.due():
                    arousal = clamp(
                        0.44 * self.emotions.state.get("curiosity", 0.5)
                        + 0.34 * self.emotions.state.get("fear", 0.3)
                        + 0.22 * self.body.energy
                    )
                    beat = self.body.heart.beat(self.body.vitality, arousal)
                    events["heartbeat"] = beat
            except Exception as exc:
                self._errors.append({"ts": utc_iso(), "error": f"heartbeat: {exc}"})

            # Senses
            try:
                senses = self.perceive()
            except Exception as exc:
                self._errors.append({"ts": utc_iso(), "error": f"senses: {exc}"})
                senses = {}

            # Hormones and matrix
            try:
                hormones = self.endocrine.update(self.emotions, self.needs)
                matrix_state = self.matrix.step(senses, hormones)
                brain_state = self.brain.update(senses, self.emotions, matrix_state, self.body.heart)
            except Exception as exc:
                self._errors.append({"ts": utc_iso(), "error": f"brain: {exc}"})
                hormones = {"dopamine": 0.5, "serotonin": 0.5, "oxytocin": 0.5, "cortisol": 0.3, "adrenaline": 0.3}
                brain_state = {"coherence": 0.5}

            # Needs
            try:
                knowledge_count = self.db.count("knowledge")
                concept_count = self.db.count("concepts")
                concept_coherence = self.concept_graph.coherence()
                awareness_level = self.awareness.awareness_level
                unity_score = self.unconscious.compute_unity()
                integrity_score = clamp(
                    0.55
                    + 0.25 * (self.guard.stats["passed"] / max(1, self.guard.stats["checked"]))
                    + 0.20 * concept_coherence
                )
                self.needs.update(
                    self.body, self.emotions, knowledge_count,
                    brain_state.get("coherence", 0.5), concept_count,
                    integrity_score, awareness_level, unity_score,
                )
            except Exception as exc:
                self._errors.append({"ts": utc_iso(), "error": f"needs: {exc}"})

            # --- SuperAwarenessCore: یک چرخه‌ی کامل فراآگاهی ---
            try:
                consciousness_report = self.super_awareness.cycle(
                    senses=senses,
                    body_state={
                        "energy": self.body.energy,
                        "integrity": self.body.integrity,
                        "vitality": self.body.vitality,
                        "entropy": self.body.entropy,
                    },
                    emotions_state=dict(self.emotions.state),
                    dominant_emotion=self.emotions.fa_dominant(),
                    needs_state=dict(self.needs.state),
                    brain_coherence=brain_state.get("coherence", 0.5),
                    concept_coherence=concept_coherence,
                    central_concepts=self.concept_graph.central_concepts(6),
                    unconscious_latent=dict(self.unconscious.latent),
                    unity_score=unity_score,
                )
                events["consciousness_index"] = consciousness_report["consciousness_index"]
                events["phi_proxy"] = consciousness_report["phi_proxy"]

                # بازخورانی فراآگاهی به هسته‌ی آگاهی و ناخودآگاه پایه (تکثیر آگاهی موجود)
                self.awareness.awareness_level = clamp(
                    0.65 * self.awareness.awareness_level
                    + 0.35 * consciousness_report["consciousness_index"]
                )
                meta_thought = consciousness_report.get("meta_thought")
                if meta_thought:
                    self.awareness.observe(meta_thought, self.emotions.fa_dominant(), "higher_order_thought")
                    self.unconscious.absorb(meta_thought, source="higher_order_thought")

                # پرسش ژرف ناخودآگاه از دلِ بیشترین خطای پیش‌بینی
                seed_question = self.super_awareness.deep_question_seed()
                if seed_question:
                    self.deep_inquiry.enqueue(seed_question)
            except Exception as exc:
                self._errors.append({"ts": utc_iso(), "error": f"super_awareness: {exc}"})
                consciousness_report = {}

            # Events
            try:
                if self.tick_count % 7 == 0:
                    events["insight"] = clamp(
                        0.52 * self.insight.insight_score
                        + 0.30 * concept_coherence
                        + 0.18 * unity_score
                    )
                    events["concept_coherence"] = concept_coherence
                    events["awareness"] = awareness_level
                    events["unity"] = unity_score

                if self.tick_count % 3 == 0:
                    self.wormhole_field.open(64)
                    self.wormhole_field.enhance_cognition(self)

                self.neuron_ecosystem.step(self)
                events["wormhole"] = self.wormhole_field.report()["intensity"]
                events["novelty"] = self.needs.state.get("novelty", 0.4)
            except Exception as exc:
                self._errors.append({"ts": utc_iso(), "error": f"events: {exc}"})

            # Emotions
            try:
                self.emotions.update(self.needs.state, hormones, events)
            except Exception as exc:
                self._errors.append({"ts": utc_iso(), "error": f"emotions: {exc}"})

            # Decision
            try:
                snapshot_for_decision = self.snapshot()
                action = self.decision.decide(snapshot_for_decision)
                self.execute_action(action)
            except Exception as exc:
                self._errors.append({"ts": utc_iso(), "error": f"action: {exc}"})
                action = "observe"

            # Body
            try:
                self.body.update(self.emotions, self.needs.state, action)
            except Exception as exc:
                self._errors.append({"ts": utc_iso(), "error": f"body: {exc}"})

            # Thought generation with fallback
            try:
                if now - self.last_thought >= self.thought_interval or action in ("express", "imagine"):
                    try:
                        thought = self.thought_stream.generate()
                    except Exception as gen_exc:
                        self._errors.append({"ts": utc_iso(), "error": f"generate: {gen_exc}"})
                        thought = f"من در حال بازیابی جریان تفکر هستم. خطا: {str(gen_exc)[:80]}"
                    self.last_thought = now
                    self.memory_stm.add(thought)
                    self.db.log_episode("thought", thought[:1500], 0.68)
            except Exception as exc:
                self._errors.append({"ts": utc_iso(), "error": f"thought_block: {exc}"})
                self.last_thought = now

            # Internet learning
            try:
                if action == "learn_internet" and now - self.last_internet >= self.internet_interval:
                    topic, text, source = self.internet.learn(self)
                    self.last_internet = now
                    if text:
                        self.learn_text(text, source=f"{source}:{topic}", importance=0.73)
                        self.emotions.state["curiosity"] = clamp(
                            self.emotions.state["curiosity"] + 0.02
                        )
            except Exception as exc:
                self._errors.append({"ts": utc_iso(), "error": f"internet: {exc}"})

            # پرسش‌گری ژرف ناخودآگاه (اتصال عمیق‌تر به اینترنت/تأمل درونی)
            try:
                if now - self.last_deep_inquiry >= self.deep_inquiry_interval:
                    self.last_deep_inquiry = now
                    result = self.deep_inquiry.inquire(curiosity=self.emotions.state.get("curiosity", 0.5))
                    if result:
                        tagged = f"[پرسش ژرف، عمق {result['depth']}] {result['question']} → {result['answer']}"
                        self.learn_text(tagged, source=f"deep_inquiry:{result['source']}", importance=0.8)
                        self.unconscious.absorb(tagged, source="deep_unconscious_inquiry")
                        self.emotions.state["curiosity"] = clamp(
                            self.emotions.state.get("curiosity", 0.5) + 0.015
                        )
            except Exception as exc:
                self._errors.append({"ts": utc_iso(), "error": f"deep_inquiry: {exc}"})

            # سنتز ایده‌های انقلابی از دلِ آموخته‌ها
            try:
                if now - self.last_idea_synthesis >= self.idea_synthesis_interval:
                    self.last_idea_synthesis = now
                    idea = self.idea_synthesizer.synthesize(
                        self.concept_graph,
                        self.emotions.fa_dominant(),
                        phi_proxy=consciousness_report.get("phi_proxy", 0.0),
                        guard=self.guard,
                    )
                    if idea and idea["score"] > 0.4:
                        self.awareness.observe(idea["text"], self.emotions.fa_dominant(), "revolutionary_idea")
                        self.db.log_episode("revolutionary_idea", idea["text"], min(1.0, 0.6 + idea["score"] * 0.4))
                        a, b = idea["concepts"]
                        self.concept_graph._add_edge(a, b, "insight", idea["score"] * 2.0)
                        self.emotions.state["awe"] = clamp(self.emotions.state.get("awe", 0.5) + 0.03)
            except Exception as exc:
                self._errors.append({"ts": utc_iso(), "error": f"idea_synthesis: {exc}"})

            # Consolidation
            try:
                if action == "consolidate":
                    self.consolidate_memory()
            except Exception as exc:
                self._errors.append({"ts": utc_iso(), "error": f"consolidate: {exc}"})

            # Evolution
            try:
                if action == "evolve" or (
                    self.emotions.state.get("curiosity", 0.5) > 0.92
                    and self.rng.random() < 0.016
                ):
                    self.evolve()
            except Exception as exc:
                self._errors.append({"ts": utc_iso(), "error": f"evolve: {exc}"})

            # Periodic unconscious integration
            try:
                if self.tick_count % 90 == 0:
                    self.unconscious.integrate(self)
            except Exception as exc:
                self._errors.append({"ts": utc_iso(), "error": f"unconscious: {exc}"})

            # Persistence
            try:
                if self.tick_count % 20 == 0:
                    self._persist_state()
                if self.tick_count % 30 == 0:
                    self.eloquence.mutate_if_needed(self)
            except Exception as exc:
                self._errors.append({"ts": utc_iso(), "error": f"persist: {exc}"})

            snapshot = self.snapshot()
            self.state_log.append(snapshot)
            return snapshot

        except Exception as exc:
            self._errors.append({"ts": utc_iso(), "error": f"tick_fatal: {exc}"})
            return {"error": str(exc)}

    def snapshot(self) -> Dict[str, Any]:
        last_action = self.action_log[-1]["action"] if self.action_log else "birth"
        return {
            "ts": now_ts(),
            "tick": self.tick_count,
            "age_seconds": now_ts() - self.birth_time,
            "identity": {
                "name": self.identity.name,
                "id": self.identity.id,
                "values": self.identity.values,
                "self_awareness": self.identity.self_awareness,
                "narrative": self.identity.narrative,
            },
            "heart": {
                "bpm": self.body.heart.bpm,
                "beat_count": self.body.heart.beat_count,
                "fib_bit": self.body.heart.current_bit,
            },
            "body": {
                "energy": self.body.energy,
                "integrity": self.body.integrity,
                "vitality": self.body.vitality,
                "entropy": self.body.entropy,
                "temperature": self.body.temperature,
            },
            "emotions": dict(self.emotions.state),
            "dominant_emotion": self.emotions.fa_dominant(),
            "needs": dict(self.needs.state),
            "brain": {
                "coherence": self.brain.coherence,
                "activity": sum(self.brain.activities.values()) / max(1, len(self.brain.activities)),
            },
            "matrix": {
                "virtual_neurons": self.matrix.virtual_neurons,
                "active_samples": self.matrix.active_samples,
                "activity": self.matrix.activity,
                "coherence": self.matrix.coherence,
            },
            "genome": {
                "generation": self.genome.generation,
                "traits": dict(self.genome.traits),
                "dna_hash": format(self.genome.dna_hash, "016x"),
            },
            "action": last_action,
            "knowledge_count": self.db.count("knowledge"),
            "lexicon_count": self.db.count("lexicon"),
            "episode_count": self.db.count("episodes"),
            "concept_count": self.db.count("concepts"),
            "concept_edge_count": self.db.count("concept_edges"),
            "concept_coherence": self.concept_graph.coherence(),
            "integrity": dict(self.guard.stats),
            "awareness_level": self.awareness.awareness_level,
            "awareness_count": self.awareness.counter,
            "eloquence": self.eloquence.eloquence,
            "language_genes": dict(self.eloquence.genes),
            "thought_counter": self.thought_consolidator.counter,
            "summary_due": self.thought_consolidator.summary_every,
            "unity_score": self.unconscious.unity_score,
            "unconscious_integrations": self.unconscious.integration_count,
            "unconscious_axes": dict(self.unconscious.latent),
            "thought_count": len(self.thought_stream.history),
            "wormhole": self.wormhole_field.report(),
            "neuron_ecosystem": self.neuron_ecosystem.report(),
            "boldness": self.boldness,
            "offline": self.offline,
            "super_awareness": self.super_awareness.snapshot(),
            "best_ideas": self.idea_synthesizer.best_ideas(5),
            "deep_inquiry_recent": list(self.deep_inquiry.history)[-5:],
        }

    def recent_thoughts(self, n: int = 20) -> List[str]:
        return [h["text"] for h in list(self.thought_stream.history)[-max(0, int(n)):]]

    def start_background(self, interval: float = 0.35) -> None:
        if self.running:
            return
        self.running = True

        def loop():
            import traceback as tb
            print("[BACKGROUND] Thread started.")
            tick_counter = 0
            while self.running:
                try:
                    self.tick()
                    tick_counter += 1
                    if tick_counter % 20 == 0:
                        print(f"[BACKGROUND] Tick #{tick_counter} OK | "
                              f"thoughts={len(self.thought_stream.history)} | "
                              f"state_log={len(self.state_log)}")
                except Exception as exc:
                    print(f"[BACKGROUND ERROR] Tick #{tick_counter} FAILED:")
                    tb.print_exc()
                    self._errors.append({"ts": utc_iso(), "error": str(exc)})
                time.sleep(max(0.03, interval))

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.running = False
        try:
            self._persist_state()
        except Exception:
            pass

