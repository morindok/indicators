"""
organism.decision

موتور تصمیم‌گیری خودمختار.
"""
from __future__ import annotations

import random
from typing import Any, Dict

class AutonomousDecisionEngine:
    ACTIONS = [
        "observe",
        "learn_internet",
        "consolidate",
        "imagine",
        "express",
        "evolve",
        "rest",
        "connect",
        "protect",
        "create",
        "conceptualize",
        "purify_meaning",
        "attend_speech",
        "unify_unconscious",
        "wormhole_dive",
        "ecosystem_balance",
    ]

    def __init__(self, seed: int = 2500):
        self.rng = random.Random(seed)
        self.boldness = 0.72

    def decide(self, snapshot: Dict[str, Any]) -> str:
        needs = snapshot.get("needs", {})
        emotions = snapshot.get("emotions", {})
        w = {action: 0.05 for action in self.ACTIONS}

        w["rest"] += max(0.0, 1.1 - needs.get("energy", 0.5)) * 1.25
        w["learn_internet"] += (
            emotions.get("curiosity", 0.5) * 1.35
            + needs.get("novelty", 0.5) * 0.62
        )
        w["observe"] += 0.42 + emotions.get("awe", 0.4) * 0.62
        w["imagine"] += (
            emotions.get("curiosity", 0.4) * 0.82
            + emotions.get("awe", 0.4) * 0.74
        )
        w["express"] += emotions.get("joy", 0.4) * 0.72 + emotions.get("love", 0.4) * 0.55
        w["evolve"] += 0.13 + emotions.get("curiosity", 0.4) * 0.36
        w["consolidate"] += max(0.0, 0.78 - needs.get("coherence", 0.5)) * 1.12
        w["connect"] += emotions.get("love", 0.5) * 0.95 + needs.get("social", 0.5) * 0.62
        w["protect"] += (
            emotions.get("fear", 0.3) * 1.12
            + max(0.0, 0.72 - needs.get("safety", 0.5))
        )
        w["create"] += emotions.get("joy", 0.4) * 0.56 + emotions.get("awe", 0.4) * 0.84
        w["conceptualize"] += (
            needs.get("meaning", 0.5) * 1.2
            + emotions.get("curiosity", 0.5) * 0.6
        )
        w["purify_meaning"] += (
            needs.get("integrity", 0.5) * 1.25
            + max(0.0, 0.72 - needs.get("coherence", 0.5)) * 0.8
        )
        w["attend_speech"] += (
            needs.get("awareness", 0.5) * 1.35
            + emotions.get("speech_presence", 0.5) * 0.75
        )
        w["unify_unconscious"] += (
            needs.get("unity", 0.5) * 1.45
            + emotions.get("inner_unity", 0.5) * 0.85
        )
        w["wormhole_dive"] += (
            emotions.get("curiosity", 0.5) * 1.2
            + emotions.get("awe", 0.5) * 0.9
            + needs.get("transcendence", 0.5) * 0.7
            + emotions.get("wormhole_wonder", 0.5) * 1.1
        )
        w["ecosystem_balance"] += (
            max(0.0, 0.75 - needs.get("coherence", 0.5)) * 1.2
            + max(0.0, 0.75 - needs.get("integrity", 0.5)) * 0.8
        )

        if self.rng.random() < 0.15 * self.boldness:
            return self.rng.choice(self.ACTIONS)

        total = sum(max(0.0001, v) for v in w.values())
        r = self.rng.random() * total
        acc = 0.0
        for action, weight in w.items():
            acc += max(0.0001, weight)
            if r <= acc:
                return action
        return "observe"


# ---------------------------------------------------------------------------
# Thought stream
# ---------------------------------------------------------------------------
