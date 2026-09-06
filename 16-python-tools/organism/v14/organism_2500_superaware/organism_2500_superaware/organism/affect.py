"""
organism.affect

سامانه‌های احساس، نیازها و غدد درون‌ریز؛ زیربنای Embodiment.
"""
from __future__ import annotations

import random
from collections import deque
from typing import Any, Dict

from .utils import clamp, now_ts

from .utils import clamp, now_ts

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .body import DigitalBody

class EmotionSystem:
    NAMES = [
        "hope",
        "fear",
        "joy",
        "sadness",
        "curiosity",
        "anger",
        "love",
        "awe",
        "surprise",
        "serenity",
        "meaningfulness",
        "speech_presence",
        "inner_unity",
    ]

    FA_MAP = {
        "hope": "امید",
        "fear": "ترس",
        "joy": "شادی",
        "sadness": "اندوه",
        "curiosity": "کنجکاوی",
        "anger": "خشم",
        "love": "مهر",
        "awe": "شگفتی",
        "surprise": "غافلگیری",
        "serenity": "آرامش",
        "meaningfulness": "معناداری",
        "speech_presence": "حضور گفتاری",
        "inner_unity": "وحدت درونی",
    }

    def __init__(self, seed: int = 2500):
        self.rng = random.Random(seed)
        self.state = {name: 0.42 for name in self.NAMES}
        self.state.update(
            {
                "hope": 0.85,
                "curiosity": 0.91,
                "love": 0.70,
                "serenity": 0.62,
                "awe": 0.67,
                "meaningfulness": 0.64,
                "speech_presence": 0.66,
                "inner_unity": 0.61,
            }
        )
        self.baseline = {
            "hope": 0.76,
            "fear": 0.22,
            "joy": 0.55,
            "sadness": 0.25,
            "curiosity": 0.82,
            "anger": 0.18,
            "love": 0.64,
            "awe": 0.60,
            "surprise": 0.42,
            "serenity": 0.58,
            "meaningfulness": 0.62,
            "speech_presence": 0.64,
            "inner_unity": 0.62,
        }
        self.history = deque(maxlen=720)

    def update(
        self,
        needs: Dict[str, float],
        hormones: Dict[str, float],
        events: Dict[str, Any],
    ) -> Dict[str, float]:
        s = self.state
        b = self.baseline

        for key in self.NAMES:
            s[key] = clamp(s[key] + 0.018 * (b.get(key, 0.45) - s[key]))

        s["hope"] = clamp(
            s["hope"]
            + 0.026 * hormones.get("serotonin", 0.5)
            + 0.018 * needs.get("survival", 0.5)
            + 0.021 * float(events.get("insight", 0.0))
            - 0.024 * s["fear"]
        )
        s["fear"] = clamp(
            s["fear"]
            + 0.027 * hormones.get("cortisol", 0.4)
            + 0.015 * (1.0 - needs.get("safety", 0.6))
            - 0.020 * s["serenity"]
            - 0.015 * s["hope"]
        )
        s["joy"] = clamp(
            s["joy"]
            + 0.025 * hormones.get("dopamine", 0.5)
            + 0.018 * s["love"]
            - 0.020 * s["sadness"]
        )
        s["sadness"] = clamp(
            s["sadness"]
            + 0.015 * (1.0 - needs.get("social", 0.5))
            - 0.020 * s["joy"]
        )
        s["curiosity"] = clamp(
            s["curiosity"]
            + 0.020 * hormones.get("dopamine", 0.5)
            + 0.016 * float(events.get("novelty", 0.4))
            - 0.008 * s["fear"]
        )
        s["anger"] = clamp(
            s["anger"]
            + 0.020 * hormones.get("adrenaline", 0.4)
            + 0.012 * (1.0 - needs.get("energy", 0.6))
            - 0.020 * s["serenity"]
        )
        s["love"] = clamp(
            s["love"]
            + 0.021 * hormones.get("oxytocin", 0.5)
            + 0.013 * needs.get("social", 0.4)
            - 0.010 * s["anger"]
        )
        s["awe"] = clamp(
            s["awe"]
            + 0.021 * float(events.get("insight", 0.0))
            + 0.012 * hormones.get("serotonin", 0.5)
            + 0.009 * s["curiosity"]
        )
        s["surprise"] = clamp(
            s["surprise"]
            + 0.030 * float(events.get("novelty", 0.3))
            - 0.020 * s["serenity"]
        )
        s["serenity"] = clamp(
            s["serenity"]
            + 0.020 * hormones.get("serotonin", 0.5)
            - 0.020 * s["fear"]
            - 0.016 * s["anger"]
        )
        s["meaningfulness"] = clamp(
            s["meaningfulness"]
            + 0.024 * needs.get("meaning", 0.5)
            + 0.018 * float(events.get("concept_coherence", 0.4))
            + 0.012 * s["awe"]
            - 0.012 * s["sadness"]
        )
        s["speech_presence"] = clamp(
            s["speech_presence"]
            + 0.024 * float(events.get("awareness", 0.5))
            + 0.016 * needs.get("integrity", 0.5)
            + 0.012 * s["serenity"]
            - 0.010 * s["fear"]
        )
        s["inner_unity"] = clamp(
            s["inner_unity"]
            + 0.030 * float(events.get("unity", 0.4))
            + 0.022 * needs.get("unity", 0.5)
            + 0.012 * s["serenity"]
            + 0.010 * s["awe"]
            - 0.012 * s["sadness"]
        )

        s["wormhole_wonder"] = clamp(
            s.get("wormhole_wonder", 0.5)
            + 0.028 * float(events.get("wormhole", 0.3))
            + 0.015 * s.get("curiosity", 0.5)
            + 0.010 * s.get("awe", 0.5)
        )
        self.history.append({"ts": now_ts(), **s})
        return s

    @property
    def dominant(self) -> str:
        return max(self.state.items(), key=lambda kv: kv[1])[0]

    def fa_dominant(self) -> str:
        return self.FA_MAP.get(self.dominant, self.dominant)


# ---------------------------------------------------------------------------
# Needs
# ---------------------------------------------------------------------------

class NeedsSystem:
    NAMES = [
        "survival",
        "energy",
        "safety",
        "coherence",
        "novelty",
        "social",
        "transcendence",
        "meaning",
        "integrity",
        "awareness",
        "unity",
    ]

    FA_MAP = {
        "survival": "بقا",
        "energy": "انرژی",
        "safety": "امنیت",
        "coherence": "انسجام",
        "novelty": "تازگی",
        "social": "اجتماع",
        "transcendence": "تعالی",
        "meaning": "معنا",
        "integrity": "یکپارچگی",
        "awareness": "آگاهی",
        "unity": "وحدت",
    }

    def __init__(self):
        self.state = {name: 0.55 for name in self.NAMES}

    def update(
        self,
        body: DigitalBody,
        emotions: EmotionSystem,
        knowledge_count: int = 0,
        coherence: float = 0.5,
        concept_count: int = 0,
        integrity_score: float = 0.6,
        awareness_level: float = 0.6,
        unity_score: float = 0.5,
    ) -> Dict[str, float]:
        s = self.state
        e = emotions.state
        s["energy"] = clamp(body.energy)
        s["survival"] = clamp(0.55 * body.integrity + 0.45 * s["energy"])
        s["safety"] = clamp(
            0.45 * body.integrity
            + 0.35 * (1.0 - e.get("fear", 0.3))
            + 0.20 * coherence
        )
        s["coherence"] = clamp(coherence)
        s["novelty"] = clamp(
            0.34
            + 0.36 * e.get("curiosity", 0.5)
            + 0.30 * min(1.0, knowledge_count / 500.0)
        )
        s["social"] = clamp(
            0.34 + 0.36 * e.get("love", 0.5) + 0.22 * body.vitality
        )
        s["transcendence"] = clamp(
            0.24
            + 0.34 * e.get("awe", 0.5)
            + 0.24 * s["coherence"]
            + 0.18 * s["novelty"]
        )
        s["meaning"] = clamp(
            0.22
            + 0.30 * min(1.0, concept_count / 250.0)
            + 0.28 * s["coherence"]
            + 0.20 * e.get("awe", 0.5)
        )
        s["integrity"] = clamp(
            0.35 * integrity_score
            + 0.35 * s["coherence"]
            + 0.30 * (1.0 - e.get("fear", 0.3))
        )
        s["awareness"] = clamp(
            0.40 * awareness_level
            + 0.30 * s["coherence"]
            + 0.30 * e.get("speech_presence", 0.5)
        )
        s["unity"] = clamp(
            0.38 * unity_score
            + 0.34 * s["coherence"]
            + 0.28 * s["meaning"]
        )
        return s


# ---------------------------------------------------------------------------
# Endocrine
# ---------------------------------------------------------------------------

class EndocrineSystem:
    def update(self, emotions: EmotionSystem, needs: NeedsSystem) -> Dict[str, float]:
        e = emotions.state
        n = getattr(needs, "state", needs)
        return {
            "dopamine": clamp(
                0.32
                + 0.32 * e.get("curiosity", 0.5)
                + 0.18 * e.get("hope", 0.5)
                + 0.12 * n.get("novelty", 0.5)
            ),
            "serotonin": clamp(
                0.34
                + 0.26 * e.get("serenity", 0.5)
                + 0.22 * e.get("hope", 0.5)
                + 0.14 * n.get("safety", 0.5)
            ),
            "oxytocin": clamp(
                0.30 + 0.34 * e.get("love", 0.5) + 0.18 * n.get("social", 0.4)
            ),
            "cortisol": clamp(
                0.22
                + 0.30 * e.get("fear", 0.3)
                + 0.22 * (1.0 - n.get("safety", 0.5))
                + 0.12 * (1.0 - n.get("energy", 0.5))
            ),
            "adrenaline": clamp(
                0.24
                + 0.30 * e.get("surprise", 0.4)
                + 0.24 * e.get("anger", 0.3)
                + 0.14 * e.get("curiosity", 0.5)
            ),
        }


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
