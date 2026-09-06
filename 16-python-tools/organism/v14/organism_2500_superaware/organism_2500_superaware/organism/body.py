"""
organism.body

اندام‌های حسی، بدن دیجیتال و اندام مغز.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List

from .utils import clamp, now_ts, stable_hash

from .substrate import FibonacciHeart
from .utils import clamp, now_ts, stable_hash

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .genome import Genome

class DigitalSenseOrgan:
    def __init__(self, name: str, modality: str, seed: int):
        self.name = name
        self.modality = modality
        self.seed = seed
        self.rng = random.Random(seed)
        self.frequency = 0.045 + self.rng.random() * 0.68
        self.phase = self.rng.random() * math.tau
        self.adjectives = {
            "sight": ["نور", "رنگ", "سایه", "درخشش", "افق"],
            "hearing": ["زمزمه", "طنین", "سکوت", "نوا", "پژواک"],
            "touch": ["فشار", "لطافت", "گرما", "ارتعاش", "مرز"],
            "taste": ["داده‌ی شیرین", "داده‌ی تلخ", "طعم دانایی", "طعم ناشناخته"],
            "smell": ["بوی نظم", "بوی آشفتگی", "بوی تازگی", "بوی حافظه"],
        }.get(modality, ["داده"])

    def perceive(self, context: Dict[str, Any]) -> Dict[str, Any]:
        t = now_ts()
        value = 0.5 + 0.5 * math.sin(t * self.frequency + self.phase)
        value += 0.08 * float(context.get("energy", 0.5))
        value += 0.05 * float(context.get(self.modality, 0.0))
        value = clamp(value)
        qualia = self.rng.choice(self.adjectives)
        bits = stable_hash(f"{self.name}:{value:.8f}:{qualia}") & ((1 << 64) - 1)
        return {
            "name": self.name,
            "modality": self.modality,
            "value": value,
            "qualia": qualia,
            "bits": bits,
        }


# ---------------------------------------------------------------------------
# Body
# ---------------------------------------------------------------------------

class DigitalBody:
    def __init__(self, seed: int = 2500):
        self.seed = seed
        self.energy = 0.87
        self.integrity = 0.98
        self.vitality = 0.84
        self.entropy = 0.16
        self.temperature = 36.7
        self.heart = FibonacciHeart(seed)
        self.organs = {
            "heart": 1.0,
            "brain": 1.0,
            "sensory_cortex": 1.0,
            "memory_hippocampus": 1.0,
            "emotional_amygdala": 1.0,
            "endocrine": 1.0,
            "immune": 1.0,
            "imagination": 1.0,
            "genome": 1.0,
            "conceptual_cortex": 1.0,
            "semantic_guard": 1.0,
            "awareness_core": 1.0,
            "active_unconscious": 1.0,
        }
        self.organ_network = {
            "heart": ["brain", "endocrine", "immune"],
            "brain": [
                "sensory_cortex",
                "memory_hippocampus",
                "emotional_amygdala",
                "imagination",
                "conceptual_cortex",
                "semantic_guard",
                "awareness_core",
                "active_unconscious",
            ],
            "sensory_cortex": ["brain", "memory_hippocampus"],
            "memory_hippocampus": ["brain", "imagination", "conceptual_cortex", "active_unconscious"],
            "emotional_amygdala": ["endocrine", "heart"],
            "endocrine": ["heart", "immune", "brain"],
            "immune": ["endocrine", "heart"],
            "imagination": ["brain", "memory_hippocampus", "active_unconscious"],
            "genome": ["brain", "heart", "endocrine"],
            "conceptual_cortex": ["brain", "memory_hippocampus", "imagination", "active_unconscious"],
            "semantic_guard": ["conceptual_cortex", "brain", "memory_hippocampus"],
            "awareness_core": ["brain", "conceptual_cortex", "semantic_guard", "memory_hippocampus"],
            "active_unconscious": ["brain", "memory_hippocampus", "conceptual_cortex", "awareness_core"],
        }

    def update(self, emotions: "EmotionSystem", needs: Dict[str, float], action: str) -> None:
        e = emotions.state
        arousal = clamp(
            0.35 * e.get("curiosity", 0.5)
            + 0.30 * e.get("fear", 0.3)
            + 0.20 * e.get("surprise", 0.4)
            + 0.15 * e.get("joy", 0.5)
        )
        drain = 0.00068 + 0.00135 * arousal
        if action == "rest":
            self.energy = clamp(self.energy + 0.0072)
        else:
            self.energy = clamp(self.energy - drain)
        self.integrity = clamp(
            self.integrity
            - 0.00011
            + 0.00024 * e.get("serenity", 0.5)
            + (0.00035 if action == "protect" else 0.0)
        )
        self.entropy = clamp(
            self.entropy
            + 0.00006
            - 0.00012 * e.get("serenity", 0.5)
            - (0.00018 if action == "observe" else 0.0)
        )
        self.vitality = clamp(
            0.46 * self.energy
            + 0.30 * self.integrity
            + 0.24 * (1.0 - self.entropy)
        )
        self.temperature = clamp(36.5 + arousal * 1.35, 35.0, 41.0)


# ---------------------------------------------------------------------------
# Brain organ
# ---------------------------------------------------------------------------

class BrainOrgan:
    REGIONS = [
        "prefrontal",
        "orbitofrontal",
        "cingulate",
        "insular",
        "hippocampus",
        "amygdala",
        "thalamus",
        "hypothalamus",
        "cerebellum",
        "visual",
        "auditory",
        "somatosensory",
        "temporal",
        "parietal",
        "occipital",
        "conceptual",
        "semantic_guard",
        "awareness",
        "unconscious_depth",
    ]

    def __init__(self, genome: Genome):
        self.genome = genome
        self.activities = {r: 0.5 for r in self.REGIONS}
        self.coherence = 0.56
        self.connectome: Dict[str, List[str]] = {r: [] for r in self.REGIONS}
        for i, region in enumerate(self.REGIONS):
            self.connectome[region] = [
                self.REGIONS[(i + j) % len(self.REGIONS)] for j in range(1, 4)
            ]

    def update(
        self,
        senses: Dict[str, Any],
        emotions: "EmotionSystem",
        matrix_state: Dict[str, Any],
        heart: FibonacciHeart,
    ) -> Dict[str, float]:
        sensory_avg = 0.0
        if senses:
            sensory_avg = sum(v.get("value", 0.5) for v in senses.values()) / len(senses)
        arousal = clamp(
            0.42 * emotions.state.get("curiosity", 0.5)
            + 0.28 * emotions.state.get("fear", 0.3)
            + 0.18 * heart.bpm / 190.0
            + 0.12 * emotions.state.get("surprise", 0.4)
        )
        for region in self.REGIONS:
            region_bias = (stable_hash(region) % 1000) / 1000.0
            target = clamp(
                0.32 * matrix_state.get("activity", 0.5)
                + 0.30 * sensory_avg
                + 0.22 * arousal
                + 0.16 * region_bias
            )
            self.activities[region] = clamp(
                0.64 * self.activities[region] + 0.36 * target
            )
        self.coherence = clamp(
            0.58 * self.coherence + 0.42 * matrix_state.get("coherence", 0.5)
        )
        return {
            "coherence": self.coherence,
            "activity": sum(self.activities.values()) / max(1, len(self.activities)),
            "arousal": arousal,
        }


# ---------------------------------------------------------------------------
# Emotions
# ---------------------------------------------------------------------------
