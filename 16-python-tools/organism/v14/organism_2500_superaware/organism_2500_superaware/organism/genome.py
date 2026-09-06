"""
organism.genome

ژنوم دیجیتال ارگانیسم و بیان ژن‌ها.
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

from .utils import clamp, stable_hash

from .utils import clamp, stable_hash

class Genome:
    BASES = "ACGT"
    TRAIT_KEYS = [
        "coherence",
        "boldness",
        "curiosity",
        "hope",
        "plasticity",
        "sensory_gain",
        "memory_depth",
        "imagination",
        "sociality",
        "insight",
        "conceptual_depth",
        "semantic_guard",
        "speech_awareness",
        "unconscious_depth",
        "wormhole_capacity",
    ]

    def __init__(self, seed: int = 2500):
        self.seed = seed
        rng = random.Random(seed)
        self.dna = "".join(rng.choice(self.BASES) for _ in range(4096))
        self.dna_hash = stable_hash(self.dna)
        self.generation = 0
        self.traits = {
            key: clamp(0.32 + rng.random() * 0.64) for key in self.TRAIT_KEYS
        }
        self.genes = self._build_genes()

    def _build_genes(self) -> List[Dict[str, Any]]:
        genes = []
        functions = [
            "stabilizes identity across time",
            "amplifies exploratory behavior",
            "supports emotional hope",
            "increases memory consolidation",
            "boosts creative recombination",
            "regulates sensory sensitivity",
            "coordinates organ coherence",
            "opens insight pathways",
            "deepens conceptual graph formation",
            "protects semantic integrity",
            "makes the organism aware of its own speech",
            "deepens active unconscious integration",
        ]
        for i in range(96):
            genes.append(
                {
                    "name": f"gene-{i:03d}",
                    "trait": self.TRAIT_KEYS[i % len(self.TRAIT_KEYS)],
                    "locus": i * 64,
                    "function": functions[i % len(functions)],
                }
            )
        return genes

    def mutate(self, rate: float = 0.008) -> "Genome":
        rng = random.Random(self.dna_hash ^ int(time.time() * 1000) ^ random.getrandbits(32))
        chars = list(self.dna)
        for i in range(len(chars)):
            if rng.random() < rate:
                chars[i] = rng.choice(self.BASES)
        self.dna = "".join(chars)
        self.dna_hash = stable_hash(self.dna)
        self.generation += 1
        for key, value in self.traits.items():
            self.traits[key] = clamp(value + rng.uniform(-0.06, 0.06))
        return self

    def expression(self, context: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        context = context or {}
        out: Dict[str, float] = {}
        for gene in self.genes:
            trait = gene["trait"]
            out[gene["name"]] = clamp(
                0.22
                + 0.52 * self.traits.get(trait, 0.5)
                + 0.26 * context.get(trait, 0.0)
            )
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seed": self.seed,
            "dna": self.dna,
            "generation": self.generation,
            "traits": dict(self.traits),
            "dna_hash": format(self.dna_hash, "016x"),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Genome":
        obj = cls(seed=int(data.get("seed", 2500)))
        obj.dna = str(data.get("dna", obj.dna))
        obj.dna_hash = stable_hash(obj.dna)
        obj.generation = int(data.get("generation", 0))
        traits = data.get("traits", {})
        for k, v in traits.items():
            if k in obj.traits:
                obj.traits[k] = clamp(v)
        return obj


# ---------------------------------------------------------------------------
# Advanced database
# ---------------------------------------------------------------------------
