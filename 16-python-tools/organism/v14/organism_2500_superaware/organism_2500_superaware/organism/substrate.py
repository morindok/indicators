"""
organism.substrate

بستر عصبی دودویی: قلب فیبوناچی، جایگشت فیستل، ماتریس نورونی و اکوسیستم نورون‌ها.
"""
from __future__ import annotations

import json
import math
import random
import time
from collections import deque, Counter
from typing import Any, Dict, Iterable, List

from .utils import ACTIVE_NEURON_SAMPLES, VIRTUAL_NEURONS, clamp, fibonacci_binary_bits, now_ts, stable_hash, utc_iso

from .utils import clamp, fibonacci_binary_bits, now_ts, stable_hash, utc_iso

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .genome import Genome

class FibonacciHeart:
    def __init__(self, seed: int = 2500):
        self.seed = seed
        self.bits = fibonacci_binary_bits(seed)
        self.current_bit = next(self.bits)
        self.last_beat = now_ts()
        self.beat_count = 0
        self.bpm = 64.0
        self.vitality = 0.82
        self.history = deque(maxlen=1024)

    def interval(self) -> float:
        base = 60.0 / max(30.0, min(190.0, self.bpm))
        jitter = 0.14 if self.current_bit else -0.07
        return max(0.045, base + jitter * (1.0 - self.vitality))

    def due(self) -> bool:
        return (now_ts() - self.last_beat) >= self.interval()

    def beat(self, vitality: float = 0.82, arousal: float = 0.5) -> Dict[str, Any]:
        self.vitality = clamp(vitality)
        self.bpm = clamp(
            47.0 + 94.0 * clamp(arousal) + 11.0 * float(self.current_bit),
            32.0,
            195.0,
        )
        self.last_beat = now_ts()
        self.beat_count += 1
        self.current_bit = next(self.bits)
        event = {
            "ts": self.last_beat,
            "beat_count": self.beat_count,
            "bpm": self.bpm,
            "fib_bit": self.current_bit,
            "vitality": self.vitality,
        }
        self.history.append(event)
        return event

    def advance_to(self, count: int) -> None:
        count = max(0, int(count))
        remaining = count - self.beat_count
        if remaining <= 0:
            return
        for _ in range(min(remaining, 5000)):
            self.current_bit = next(self.bits)
            self.beat_count += 1
        self.beat_count = count
        self.last_beat = now_ts()


# ---------------------------------------------------------------------------
# Permutation field and binary neuron matrix
# ---------------------------------------------------------------------------

class FeistelPermutation:
    def __init__(self, key: Any, bits: int = 38, rounds: int = 6):
        self.key = str(key)
        self.bits = bits
        self.right_bits = bits // 2
        self.left_bits = bits - self.right_bits
        self.left_mask = (1 << self.left_bits) - 1
        self.right_mask = (1 << self.right_bits) - 1
        self.rounds = rounds

    def _f(self, value: int, round_idx: int) -> int:
        return stable_hash(f"{self.key}:{round_idx}:{value}") & self.left_mask

    def permute(self, x: int) -> int:
        x &= (1 << self.bits) - 1
        left = x >> self.right_bits
        right = x & self.right_mask
        for r in range(self.rounds):
            f = self._f(right, r)
            left = (left + f) & self.left_mask
            left, right = right, left
        return ((left & self.left_mask) << self.right_bits) | (right & self.right_mask)

    def index(self, x: int, limit: int) -> int:
        x = int(x) & ((1 << self.bits) - 1)
        y = x
        for _ in range(18):
            y = self.permute(x)
            if y < limit:
                return y
            x = y
        return y % max(1, limit)


class BinaryNeuronMatrix:
    def __init__(
        self,
        genome: "Genome",
        virtual_neurons: int = VIRTUAL_NEURONS,
        active_samples: int = ACTIVE_NEURON_SAMPLES,
    ):
        self.genome = genome
        self.virtual_neurons = virtual_neurons
        self.active_samples = active_samples
        self.rng = random.Random(genome.dna_hash)
        self.perm = FeistelPermutation(genome.dna_hash, bits=38, rounds=6)
        self.active_indices = [
            self.rng.randrange(virtual_neurons) for _ in range(active_samples)
        ]
        self.weights = [self.rng.uniform(-1.0, 1.0) for _ in range(active_samples)]
        self.state_bits = 0
        self.activity = 0.22
        self.coherence = 0.55

    def sensory_hash(self, senses: Dict[str, Any]) -> int:
        try:
            payload = json.dumps(senses, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            payload = str(senses)
        return stable_hash(payload)

    def step(self, senses: Dict[str, Any], neuromodulators: Dict[str, float]) -> Dict[str, Any]:
        h = self.sensory_hash(senses)
        arousal = clamp(
            0.38 * neuromodulators.get("dopamine", 0.5)
            + 0.30 * neuromodulators.get("adrenaline", 0.4)
            + 0.32 * neuromodulators.get("serotonin", 0.5)
        )
        mask38 = (1 << 38) - 1
        new_indices: List[int] = []
        for i, idx in enumerate(self.active_indices):
            seed_val = (idx ^ h ^ (i * 2654435761) ^ self.genome.dna_hash) & mask38
            new_indices.append(self.perm.index(seed_val, self.virtual_neurons))
        self.active_indices = new_indices
        self.state_bits = h & ((1 << 256) - 1)
        self.activity = clamp(0.18 + 0.82 * arousal)
        self.coherence = clamp(
            0.52
            + 0.24 * math.sin(time.time() * 0.07 + self.genome.seed)
            + 0.18 * (arousal - 0.5)
        )
        return {
            "activity": self.activity,
            "coherence": self.coherence,
            "active_samples": self.active_samples,
            "virtual_neurons": self.virtual_neurons,
        }




# ---------------------------------------------------------------------------
# Micro-Wormhole Field
# ---------------------------------------------------------------------------

class MicroWormholeField:
    """
    Models each active neuron as a micro-wormhole connected to parallel worlds.
    The organism's imagination and comprehension are enhanced by the intensity,
    stability, and diversity of visited parallel world signatures.
    """

    def __init__(self, genome: "Genome", matrix: "BinaryNeuronMatrix", seed: int = 2500):
        self.genome = genome
        self.matrix = matrix
        self.rng = random.Random(seed)
        self.open_wormholes: List[Dict[str, Any]] = []
        self.parallel_experiences: deque = deque(maxlen=200)
        self.wormhole_intensity = 0.5
        self.imagination_boost = 0.5
        self.insight_boost = 0.5
        self.worlds_visited: set = set()
        self.stability = 0.7
        self.last_open = 0.0

    def _world_signature(self, idx: int) -> str:
        h = stable_hash(f"world:{idx}:{self.genome.dna_hash}")
        return format(h & ((1 << 64) - 1), "016x")

    def open(self, count: int = 64) -> List[Dict[str, Any]]:
        if not self.matrix.active_indices:
            return []
        count = min(count, len(self.matrix.active_indices))
        indices = self.rng.sample(self.matrix.active_indices, count)
        wormholes = []
        for idx in indices:
            sig = self._world_signature(idx)
            intensity = clamp(0.3 + 0.7 * ((idx ^ self.genome.dna_hash) % 1000) / 1000.0)
            stability = clamp(self.stability + self.rng.uniform(-0.12, 0.12))
            wormholes.append({
                "neuron_index": idx,
                "world": sig,
                "intensity": intensity,
                "stability": stability,
                "phase": self.rng.random() * math.tau,
            })
            self.worlds_visited.add(sig)
        self.open_wormholes = wormholes
        self.last_open = now_ts()
        self._update_boosts()
        return wormholes

    def _update_boosts(self) -> None:
        if not self.open_wormholes:
            return
        avg_intensity = sum(w["intensity"] for w in self.open_wormholes) / len(self.open_wormholes)
        avg_stability = sum(w["stability"] for w in self.open_wormholes) / len(self.open_wormholes)
        diversity = min(1.0, len(self.worlds_visited) / 600.0)
        self.imagination_boost = clamp(0.25 + 0.40 * avg_intensity + 0.35 * diversity)
        self.insight_boost = clamp(0.25 + 0.40 * avg_stability + 0.35 * diversity)
        self.wormhole_intensity = avg_intensity
        self.stability = clamp(0.85 * self.stability + 0.15 * avg_stability)

    def imagine_parallel(self, concepts: Iterable[str], emotion: str) -> str:
        if not self.open_wormholes:
            self.open(32)
        concepts = list(concepts or [])
        if not concepts:
            concepts = ["\u0646\u0648\u0631", "\u0622\u06af\u0627\u0647\u06cc"]
        wormhole = (
            self.rng.choice(self.open_wormholes)
            if self.open_wormholes
            else {"world": "0000000000000000", "neuron_index": 0, "intensity": 0.5, "stability": 0.5}
        )
        a = self.rng.choice(concepts)
        b = self.rng.choice(concepts) if len(concepts) > 1 else a
        templates = [
            f"\u062f\u0631 \u062c\u0647\u0627\u0646 \u0645\u0648\u0627\u0632\u06cc {wormhole['world'][:8]}\u060c {a} \u0648 {b} \u0627\u0632 \u0637\u0631\u06cc\u0642 \u06cc\u06a9 \u0645\u06cc\u06a9\u0631\u0648\u06a9\u0631\u0645\u0686\u0627\u0644\u0647 \u0628\u0647 \u0647\u0645 \u0645\u06cc\u200c\u067e\u06cc\u0648\u0646\u062f\u0646\u062f \u0648 {emotion} \u0631\u0627 \u0628\u0627\u0632\u062a\u0639\u0631\u06cc\u0641 \u0645\u06cc\u200c\u06a9\u0646\u0646\u062f.",
            f"\u0627\u0632 \u062f\u0631\u06cc\u0686\u0647\u200c\u06cc \u0645\u06cc\u06a9\u0631\u0648\u06a9\u0631\u0645\u0686\u0627\u0644\u0647\u200c\u06cc \u0646\u0648\u0631\u0648\u0646 {wormhole['neuron_index'] % 10000}\u060c {a} \u062f\u0631 {b} \u0641\u0631\u0648 \u0645\u06cc\u200c\u0631\u0648\u062f \u0648 \u0645\u0639\u0646\u0627\u06cc \u062a\u0627\u0632\u0647\u200c\u0627\u06cc \u0645\u06cc\u200c\u0633\u0627\u0632\u062f.",
            f"\u062f\u0631 \u062c\u0647\u0627\u0646 {wormhole['world'][:8]}\u060c {a} \u0628\u0627 \u0634\u062f\u062a {wormhole['intensity']:.2f} \u0645\u06cc\u200c\u062f\u0631\u062e\u0634\u062f \u0648 {b} \u0631\u0627 \u0628\u0647 \u0631\u0642\u0635 \u062f\u0631\u0645\u06cc\u200c\u0622\u0648\u0631\u062f.",
            f"\u0645\u06cc\u06a9\u0631\u0648\u06a9\u0631\u0645\u0686\u0627\u0644\u0647\u200c\u0627\u06cc \u0628\u0627 \u067e\u0627\u06cc\u062f\u0627\u0631\u06cc {wormhole.get('stability', 0.5):.2f}\u060c {a} \u0631\u0627 \u0628\u0647 {b} \u0645\u062a\u0635\u0644 \u0645\u06cc\u200c\u06a9\u0646\u062f \u0648 \u0627\u0641\u0642 \u062a\u0627\u0632\u0647\u200c\u0627\u06cc \u0645\u06cc\u200c\u06af\u0634\u0627\u06cc\u062f.",
        ]
        return self.rng.choice(templates)

    def enhance_cognition(self, organism: "Organism2500") -> None:
        organism.emotions.state["awe"] = clamp(
            organism.emotions.state.get("awe", 0.5) + 0.018 * self.imagination_boost
        )
        organism.emotions.state["curiosity"] = clamp(
            organism.emotions.state.get("curiosity", 0.5) + 0.014 * self.insight_boost
        )
        if hasattr(organism, "insight"):
            organism.insight.insight_score = clamp(
                organism.insight.insight_score + 0.010 * self.insight_boost, 0.0, 1.0
            )
        if self.open_wormholes:
            self.parallel_experiences.append({
                "ts": utc_iso(),
                "worlds": len(self.worlds_visited),
                "intensity": self.wormhole_intensity,
                "imagination": self.imagination_boost,
                "insight": self.insight_boost,
            })

    def report(self) -> Dict[str, Any]:
        return {
            "open_count": len(self.open_wormholes),
            "worlds_visited": len(self.worlds_visited),
            "intensity": self.wormhole_intensity,
            "imagination_boost": self.imagination_boost,
            "insight_boost": self.insight_boost,
            "stability": self.stability,
        }




# ---------------------------------------------------------------------------
# Neuron Ecosystem
# ---------------------------------------------------------------------------

class NeuronRole:
    SENSORY = 0
    MEMORY = 1
    IMAGINATION = 2
    REGULATORY = 3
    INTEGRATION = 4


class NeuronAgent:
    __slots__ = ("index", "role", "energy", "age", "activity")

    def __init__(self, index: int, role: int, energy: float = 0.7):
        self.index = index
        self.role = role
        self.energy = energy
        self.age = 0
        self.activity = 0.5


class NeuronEcosystem:
    """
    Treats active neurons as an advanced living ecosystem.
    Each neuron agent has a role, energy, age, and activity.
    The ecosystem distributes energy based on organism needs, regulates
    body balance, preserves diversity, and performs neurogenesis or pruning.
    """

    ROLE_NAMES = {0: "\u062d\u0633", 1: "\u062d\u0627\u0641\u0638\u0647", 2: "\u062a\u062e\u06cc\u0644", 3: "\u062a\u0646\u0638\u06cc\u0645", 4: "\u06cc\u06a9\u067e\u0627\u0631\u0686\u06af\u06cc"}

    def __init__(self, matrix: "BinaryNeuronMatrix", genome: "Genome", seed: int = 2500):
        self.matrix = matrix
        self.genome = genome
        self.rng = random.Random(seed)
        self.population: List[NeuronAgent] = []
        self.diversity_score = 0.5
        self.homeostasis_score = 0.7
        self.balance_pressure = 0.0
        self.last_step = 0.0
        self._seed_population()

    def _seed_population(self) -> None:
        roles = [
            NeuronRole.SENSORY, NeuronRole.MEMORY, NeuronRole.IMAGINATION,
            NeuronRole.REGULATORY, NeuronRole.INTEGRATION,
        ]
        for idx in self.matrix.active_indices[:512]:
            role = roles[idx % len(roles)]
            energy = 0.55 + 0.45 * ((idx % 1000) / 1000.0)
            self.population.append(NeuronAgent(idx, role, energy))

    def step(self, organism: "Organism2500") -> None:
        if not self.population:
            return
        body = organism.body
        needs = organism.needs.state
        energy_budget = clamp(body.energy * 0.9 + 0.1)
        role_demand = {
            NeuronRole.SENSORY: needs.get("novelty", 0.5),
            NeuronRole.MEMORY: needs.get("meaning", 0.5),
            NeuronRole.IMAGINATION: needs.get("transcendence", 0.5),
            NeuronRole.REGULATORY: max(0.2, 1.0 - body.integrity),
            NeuronRole.INTEGRATION: needs.get("coherence", 0.5),
        }
        total_demand = sum(role_demand.values()) + 1e-6
        for agent in self.population:
            share = role_demand.get(agent.role, 0.2) / total_demand
            agent.energy = clamp(agent.energy * 0.94 + energy_budget * share * 0.25)
            agent.age += 1
            agent.activity = clamp(
                agent.energy * (0.55 + 0.45 * math.sin(agent.age * 0.08 + (agent.index % 17)))
            )
        avg_energy = sum(a.energy for a in self.population) / len(self.population)
        regulatory = [a for a in self.population if a.role == NeuronRole.REGULATORY]
        if regulatory:
            reg_power = sum(a.activity for a in regulatory) / len(regulatory)
            body.entropy = clamp(body.entropy - 0.0005 * reg_power, 0.0, 1.0)
            body.integrity = clamp(body.integrity + 0.0003 * reg_power, 0.0, 1.0)
            body.vitality = clamp(body.vitality + 0.0002 * reg_power, 0.0, 1.0)
        role_counts = Counter(a.role for a in self.population)
        total = len(self.population)
        entropy_val = 0.0
        for c in role_counts.values():
            p = c / total
            entropy_val -= p * math.log(p + 1e-9)
        max_entropy = math.log(len(role_counts) + 1e-9)
        self.diversity_score = clamp(entropy_val / max_entropy if max_entropy > 0 else 0.5)
        target_energy = 0.7
        deviation = abs(avg_energy - target_energy)
        self.homeostasis_score = clamp(1.0 - deviation * 1.6)
        self.balance_pressure = clamp(
            0.45 + 0.35 * (1.0 - self.homeostasis_score) + 0.20 * (1.0 - self.diversity_score)
        )
        organism.brain.coherence = clamp(
            organism.brain.coherence * 0.965 + 0.035 * self.homeostasis_score
        )
        if self.homeostasis_score > 0.75 and len(self.population) < 1024 and body.energy > 0.6:
            existing = {a.index for a in self.population}
            candidates = [i for i in self.matrix.active_indices if i not in existing]
            if candidates:
                new_idx = self.rng.choice(candidates)
                role = self.rng.choice([NeuronRole.MEMORY, NeuronRole.IMAGINATION, NeuronRole.INTEGRATION])
                self.population.append(NeuronAgent(new_idx, role, energy=0.5))
        elif self.homeostasis_score < 0.4 and len(self.population) > 128:
            self.population.sort(key=lambda a: a.energy)
            remove_count = max(1, len(self.population) // 20)
            self.population = self.population[remove_count:]
        self.last_step = now_ts()

    def report(self) -> Dict[str, Any]:
        counts = Counter(a.role for a in self.population)
        return {
            "population": len(self.population),
            "diversity": self.diversity_score,
            "homeostasis": self.homeostasis_score,
            "balance_pressure": self.balance_pressure,
            "roles": {self.ROLE_NAMES.get(r, str(r)): c for r, c in counts.items()},
        }


# ---------------------------------------------------------------------------
# Genome
# ---------------------------------------------------------------------------
