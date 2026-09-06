import os
import math
import random
import time
import statistics
from collections import deque, defaultdict
from datetime import datetime

from dash import Dash, dcc, html, Input, Output
import plotly.graph_objects as go


# ============================================================
# Utilities
# ============================================================

def clamp(v, lo=0.0, hi=1.0):
    try:
        if v is None:
            return lo
        v = float(v)
        if math.isnan(v) or math.isinf(v):
            return lo
        return max(lo, min(hi, v))
    except Exception:
        return lo


def clamp100(v):
    return clamp(v, 0.0, 100.0)


def now_hms():
    return datetime.now().strftime("%H:%M:%S")


def normalize_scores(scores):
    try:
        if not scores:
            return {}

        vals = list(scores.values())
        mn = min(vals)
        mx = max(vals)
        rng = mx - mn

        if rng <= 1e-9:
            return {k: 0.5 for k in scores}

        return {k: (v - mn) / rng for k, v in scores.items()}

    except Exception:
        return {}


def action_hash(text):
    try:
        h = 0
        for ch in str(text):
            h = (h * 31 + ord(ch)) & 0xFFFFFFFF
        return h
    except Exception:
        return random.randint(0, 10**9)


ACTIONS = [
    "rest",
    "seek_energy",
    "explore",
    "regulate",
    "focus",
]

ACTION_FA = {
    "rest": "استراحت",
    "seek_energy": "جستجوی انرژی",
    "explore": "کاوش",
    "regulate": "تنظیم",
    "focus": "تمرکز",
}

BODY_KEYS = [
    "energy",
    "oxygen",
    "glucose",
    "safety",
    "novelty",
    "pain",
    "fatigue",
    "temperature",
]


def homeostasis_score(s):
    try:
        temp_balance = clamp100(100 - abs(s.get("temperature", 50) - 50) * 2.2)

        vals = {
            "energy": s.get("energy", 0),
            "oxygen": s.get("oxygen", 0),
            "glucose": s.get("glucose", 0),
            "safety": s.get("safety", 0),
            "temperature": temp_balance,
            "comfort": 100 - s.get("pain", 0),
            "rest": 100 - s.get("fatigue", 0),
        }

        weights = {
            "energy": 0.20,
            "oxygen": 0.18,
            "glucose": 0.12,
            "safety": 0.12,
            "temperature": 0.10,
            "comfort": 0.14,
            "rest": 0.14,
        }

        total = 0.0
        for k in vals:
            total += vals[k] * weights[k]

        return clamp100(total)

    except Exception:
        return 50.0


# ============================================================
# Body core
# ============================================================

def body_step_core(s, action):
    """
    مدل قطعی بدن برای شبیه‌سازی آینده و اجرای واقعی.
    """
    s = dict(s)

    if action == "rest":
        s["energy"] = clamp100(s["energy"] + 3.0)
        s["fatigue"] = clamp100(s["fatigue"] - 4.0)
        s["oxygen"] = clamp100(s["oxygen"] + 2.0)
        s["pain"] = clamp100(s["pain"] - 0.6)
        s["temperature"] = clamp100(s["temperature"] - 0.3)

    elif action == "seek_energy":
        s["energy"] = clamp100(s["energy"] + 5.0)
        s["glucose"] = clamp100(s["glucose"] + 6.0)
        s["fatigue"] = clamp100(s["fatigue"] + 2.0)
        s["temperature"] = clamp100(s["temperature"] + 0.4)

    elif action == "explore":
        s["novelty"] = clamp100(s["novelty"] + 6.0)
        s["energy"] = clamp100(s["energy"] - 2.2)
        s["glucose"] = clamp100(s["glucose"] - 1.8)
        s["fatigue"] = clamp100(s["fatigue"] + 1.6)
        s["oxygen"] = clamp100(s["oxygen"] - 1.2)
        s["temperature"] = clamp100(s["temperature"] + 0.6)

    elif action == "regulate":
        s["safety"] = clamp100(s["safety"] + 4.0)
        s["pain"] = clamp100(s["pain"] - 1.2)
        s["fatigue"] = clamp100(s["fatigue"] + 0.4)
        s["temperature"] = clamp100(s["temperature"] - 0.4)

    else:  # focus
        s["novelty"] = clamp100(s["novelty"] - 1.0)
        s["fatigue"] = clamp100(s["fatigue"] + 1.2)
        s["energy"] = clamp100(s["energy"] - 0.6)
        s["glucose"] = clamp100(s["glucose"] - 0.5)

    # Continuous biological decay
    s["energy"] = clamp100(s["energy"] - 0.50)
    s["oxygen"] = clamp100(s["oxygen"] - 0.35)
    s["glucose"] = clamp100(s["glucose"] - 0.45)
    s["novelty"] = clamp100(s["novelty"] - 0.30)
    s["temperature"] = clamp100(s["temperature"] + random.uniform(-0.35, 0.35))

    # Deterministic damage approximations
    if s["energy"] < 25:
        s["pain"] = clamp100(s["pain"] + 0.5)
        s["safety"] = clamp100(s["safety"] - 0.6)

    if s["oxygen"] < 40:
        s["pain"] = clamp100(s["pain"] + 0.7)
        s["fatigue"] = clamp100(s["fatigue"] + 0.8)

    if s["glucose"] < 25:
        s["fatigue"] = clamp100(s["fatigue"] + 0.7)

    if s["temperature"] > 75 or s["temperature"] < 25:
        s["pain"] = clamp100(s["pain"] + 0.4)
        s["safety"] = clamp100(s["safety"] - 0.4)

    return s


class Body:
    def __init__(self):
        self.signals = {
            "energy": 82.0,
            "oxygen": 88.0,
            "glucose": 75.0,
            "safety": 78.0,
            "novelty": 55.0,
            "pain": 6.0,
            "fatigue": 18.0,
            "temperature": 50.0,
        }

    def update(self, action):
        self.signals = body_step_core(self.signals, action)

        s = self.signals

        # Stochastic biological noise
        s["pain"] = clamp100(s["pain"] + random.uniform(-0.2, 0.35))
        s["temperature"] = clamp100(s["temperature"] + random.uniform(-0.4, 0.4))
        s["novelty"] = clamp100(s["novelty"] + random.uniform(-0.4, 0.6))


# ============================================================
# Future simulation
# ============================================================

def simulate_action(signals, action, horizon=4):
    """
    آینده‌نگری:
    شبیه‌سازی چندقدمی بدن برای یک عمل خاص.
    """
    s = dict(signals)
    score = 0.0

    for h in range(horizon):
        s = body_step_core(s, action)
        hs = homeostasis_score(s)
        score += hs * (0.9 ** h)
        score -= s["pain"] * 0.03
        score -= s["fatigue"] * 0.01

    return score / max(1, horizon), s


# ============================================================
# Predictive coding
# ============================================================

class PredictiveModel:
    def __init__(self, keys):
        self.keys = keys
        self.trend = {k: 0.0 for k in keys}
        self.action_effects = {
            a: {k: 0.0 for k in keys}
            for a in ACTIONS
        }
        self.error = 12.0

    def update(self, prev_signals, action, actual_signals):
        errors = []

        for k in self.keys:
            trend = self.trend.get(k, 0.0)
            predicted = (
                prev_signals[k]
                + trend
                + self.action_effects[action].get(k, 0.0)
            )

            actual = actual_signals[k]
            error = actual - predicted
            errors.append(abs(error))

            self.trend[k] = clamp(
                0.75 * trend + 0.25 * (actual - prev_signals[k]),
                -6.0,
                6.0
            )

            self.action_effects[action][k] = clamp(
                self.action_effects[action][k] + 0.08 * clamp(error, -8.0, 8.0),
                -10.0,
                10.0
            )

        avg_error = sum(errors) / max(1, len(errors))
        self.error = 0.70 * self.error + 0.30 * avg_error

        return self.error


# ============================================================
# Reinforcement learning
# ============================================================

class ReinforcementLearner:
    def __init__(self, actions):
        self.actions = actions
        self.q = defaultdict(lambda: {a: 0.0 for a in self.actions})
        self.alpha = 0.18
        self.gamma = 0.92

    def state(self, signals, consciousness):
        return (
            signals["energy"] < 40,
            signals["oxygen"] < 50,
            signals["glucose"] < 40,
            signals["pain"] > 40,
            signals["fatigue"] > 60,
            signals["safety"] < 40,
            signals["novelty"] < 35,
            consciousness > 60,
        )

    def get_q(self, state, action):
        return self.q[state][action]

    def choose(self, state, epsilon=0.2):
        if random.random() < epsilon:
            return random.choice(self.actions)

        best_action = self.actions[0]
        best_value = self.q[state][best_action]

        for a in self.actions[1:]:
            v = self.q[state][a]
            if v > best_value:
                best_value = v
                best_action = a

        return best_action

    def update(self, state, action, reward, next_state):
        old = self.q[state][action]

        best_next = max(self.q[next_state][a] for a in self.actions)

        target = reward + self.gamma * best_next

        self.q[state][action] = old + self.alpha * (target - old)


# ============================================================
# Episodic memory
# ============================================================

class EpisodicMemory:
    def __init__(self, capacity=500):
        self.events = []
        self.capacity = capacity

    def vector(self, signals, consciousness, ignition):
        vec = []

        for k in BODY_KEYS:
            vec.append(signals.get(k, 50.0) / 100.0)

        vec.append(consciousness / 100.0)
        vec.append(ignition)

        return vec

    def add(self, vec, action, reward, importance):
        event = {
            "time": now_hms(),
            "vec": vec,
            "action": action,
            "reward": reward,
            "importance": importance,
        }

        self.events.append(event)

        if len(self.events) > self.capacity:
            self.events.pop(0)

    def _distance(self, a, b):
        try:
            if len(a) != len(b):
                return 1.0

            total = 0.0
            for x, y in zip(a, b):
                total += (x - y) ** 2

            return math.sqrt(total / len(a))

        except Exception:
            return 1.0

    def retrieve(self, vec, k=3):
        scored = []

        for e in self.events:
            d = self._distance(vec, e["vec"])
            scored.append((d, e))

        scored.sort(key=lambda x: x[0])

        return [e for _, e in scored[:k]]

    def recurrence_count(self, vec, threshold=0.18):
        count = 0

        for e in self.events[:-1]:
            d = self._distance(vec, e["vec"])
            if d < threshold:
                count += 1

        return count


# ============================================================
# Self-model
# ============================================================

class SelfModel:
    def __init__(self):
        self.body_estimate = {}
        self.prediction_error = 20.0
        self.confidence = 0.35
        self.last_updated = now_hms()

    def update(self, body_signals, consciousness, ignition, predictor_error):
        try:
            if not self.body_estimate:
                self.body_estimate = dict(body_signals)

            errors = []

            for k, v in body_signals.items():
                old = self.body_estimate.get(k, v)
                self.body_estimate[k] = 0.82 * old + 0.18 * v
                errors.append(abs(self.body_estimate[k] - v))

            avg_error = sum(errors) / max(1, len(errors))

            self.prediction_error = clamp100(
                0.55 * avg_error
                + 0.45 * predictor_error
            )

            self.confidence = clamp(
                (consciousness / 100.0)
                * (1.0 - self.prediction_error / 130.0)
                + ignition * 0.15
            )

            self.last_updated = now_hms()

        except Exception:
            pass


# ============================================================
# Small-world connectome
# ============================================================

def build_small_world(n, k=10, p=0.14, rng=None):
    if rng is None:
        rng = random.Random()

    incoming = [[] for _ in range(n)]

    half = max(1, k // 2)

    # Ring lattice
    for i in range(n):
        for d in range(-half, half + 1):
            if d == 0:
                continue

            j = (i + d) % n

            if rng.random() < 0.82:
                w = rng.uniform(0.08, 0.55)
            else:
                w = rng.uniform(-0.35, 0.08)

            incoming[i].append([j, w])

    # Rewire to create small-world shortcuts
    for i in range(n):
        for edge in incoming[i]:
            if rng.random() < p:
                edge[0] = rng.randrange(n)
                edge[1] = rng.uniform(-0.45, 0.65)

    # Hubs
    hub_count = min(10, max(3, n // 70))
    hubs = rng.sample(range(n), hub_count)

    for hub in hubs:
        connections = min(60, max(12, n // 12))

        for _ in range(connections):
            target = rng.randrange(n)
            if target != hub:
                incoming[target].append([hub, rng.uniform(0.18, 0.72)])

    return incoming


# ============================================================
# Binary neural core with predictive coding and Phi
# ============================================================

class NeuralCore:
    def __init__(self, n=None, seed=None):
        if n is None:
            cpu_count = os.cpu_count() or 4
            n = min(896, max(320, cpu_count * 80))

        self.n = n
        self.rng = random.Random(seed if seed is not None else int(time.time() * 1000))

        self.potentials = [self.rng.uniform(-0.1, 0.1) for _ in range(n)]
        self.firing = [0] * n
        self.thresholds = [self.rng.uniform(0.38, 0.62) for _ in range(n)]

        self.incoming = build_small_world(n, k=10, p=0.14, rng=self.rng)

        self.modules = self._build_modules()
        self._add_architecture()

        self.history = deque(maxlen=180)
        self.module_history = deque(maxlen=40)

        self.ignition = 0.0
        self.integration = 0.0
        self.differentiation = 0.0
        self.phi = 0.0
        self.consciousness = 0.0

        self.plasticity_events = 0
        self.synapse_count = sum(len(x) for x in self.incoming)

    def _build_modules(self):
        n = self.n
        modules = {}

        parts = [
            ("sensory", n // 8),
            ("interoceptive", n // 8),
            ("memory", n // 5),
            ("association", n // 5),
            ("self", n // 10),
            ("motor", n // 10),
        ]

        start = 0

        for name, size in parts:
            size = max(1, size)
            end = min(n, start + size)
            modules[name] = list(range(start, end))
            start = end

        modules["global"] = list(range(start, n))

        if not modules["global"]:
            modules["global"] = [n - 1]

        return modules

    def _add_module_connections(self, src, dst, count, wmin=0.10, wmax=0.55):
        try:
            src_neurons = self.modules.get(src, [])
            dst_neurons = self.modules.get(dst, [])

            if not src_neurons or not dst_neurons:
                return

            for _ in range(count):
                j = self.rng.choice(src_neurons)
                i = self.rng.choice(dst_neurons)
                w = self.rng.uniform(wmin, wmax)
                self.incoming[i].append([j, w])

        except Exception:
            pass

    def _add_architecture(self):
        # Sensory pathways
        self._add_module_connections("sensory", "association", 60, 0.15, 0.55)
        self._add_module_connections("sensory", "memory", 30, 0.10, 0.40)

        # Interoception to self and global
        self._add_module_connections("interoceptive", "self", 50, 0.18, 0.60)
        self._add_module_connections("interoceptive", "global", 25, 0.12, 0.45)

        # Memory loops
        self._add_module_connections("memory", "association", 60, 0.15, 0.55)
        self._add_module_connections("association", "memory", 50, 0.12, 0.50)

        # Association to self and global
        self._add_module_connections("association", "self", 50, 0.16, 0.60)
        self._add_module_connections("association", "global", 70, 0.18, 0.65)

        # Self to global
        self._add_module_connections("self", "global", 60, 0.22, 0.70)

        # Global broadcast
        for gw in self.modules["global"]:
            for _ in range(20):
                target = self.rng.randrange(self.n)
                if target != gw:
                    self.incoming[target].append([gw, self.rng.uniform(0.15, 0.60)])

        # Global to motor
        self._add_module_connections("global", "motor", 50, 0.18, 0.60)
        self._add_module_connections("association", "motor", 40, 0.12, 0.50)

    def step(self, body_signals, neuromodulators, action, prediction_error, hypercoherence):
        try:
            n = self.n
            external = [0.0] * n

            t = time.time()

            # Sensory environment
            sensory = self.modules["sensory"]
            novelty_factor = body_signals.get("novelty", 50) / 100.0

            for idx, i in enumerate(sensory):
                phase = idx * 0.37
                external[i] += (
                    0.10 * math.sin(t * 1.7 + phase)
                    + 0.08 * math.cos(t * 0.9 + phase)
                    + 0.07 * novelty_factor
                    + self.rng.uniform(-0.03, 0.03)
                )

            # Interoceptive body signals
            interoceptive = self.modules["interoceptive"]
            body_items = list(body_signals.items())

            for idx, i in enumerate(interoceptive):
                key, value = body_items[idx % len(body_items)]

                if key in ("pain", "fatigue"):
                    normalized = value / 100.0
                else:
                    normalized = 1.0 - value / 100.0

                external[i] += clamp(normalized * 0.50 + self.rng.uniform(-0.02, 0.02))

            # Motor intention
            motor = self.modules["motor"]
            h = action_hash(action)

            for idx, i in enumerate(motor):
                bit = (h >> idx) & 1
                if bit:
                    external[i] += 0.22
                else:
                    external[i] += 0.04

            # Prediction error drives instability and learning
            error_drive = clamp(prediction_error / 100.0)
            association = self.modules["association"]
            self_module = self.modules["self"]

            for i in association[:max(1, len(association)//3)]:
                external[i] += 0.12 * error_drive

            for i in self_module[:max(1, len(self_module)//3)]:
                external[i] += 0.10 * hypercoherence

            # Global broadcast
            broadcast = 0.05 * self.ignition + 0.05 * hypercoherence

            # Neural dynamics
            new_firing = [0] * n
            norepi = neuromodulators.get("norepinephrine", 0.3)

            for i in range(n):
                s = 0.76 * self.potentials[i] + external[i]

                if broadcast > 0:
                    s += broadcast

                for j, w in self.incoming[i]:
                    s += w * self.firing[j]

                s += norepi * self.rng.uniform(-0.035, 0.035)

                self.potentials[i] = s

                if s > self.thresholds[i]:
                    new_firing[i] = 1
                else:
                    new_firing[i] = 0

            self.firing = new_firing

            # Plasticity
            self._plasticity(neuromodulators, prediction_error)

            # Module activities
            acts = {}
            for name, idxs in self.modules.items():
                if idxs:
                    acts[name] = sum(self.firing[i] for i in idxs) / len(idxs)
                else:
                    acts[name] = 0.0

            # Global ignition
            gw_act = acts.get("global", 0.0)
            self_act = acts.get("self", 0.0)
            assoc_act = acts.get("association", 0.0)
            memory_act = acts.get("memory", 0.0)

            target_ignition = clamp(
                gw_act * 1.10
                + self_act * 0.35
                + assoc_act * 0.28
                + memory_act * 0.18
                + neuromodulators.get("acetylcholine", 0.3) * 0.08
                + hypercoherence * 0.12
            )

            self.ignition = 0.62 * self.ignition + 0.38 * target_ignition

            # Phi-like measure
            self._compute_phi(acts, hypercoherence)

            # Consciousness index
            self.consciousness = clamp100(
                100.0 * (
                    0.38 * self.phi
                    + 0.24 * self.ignition
                    + 0.20 * self.integration
                    + 0.18 * self.differentiation
                )
            )

            self.history.append({
                "t": time.time(),
                "consciousness": self.consciousness,
                "ignition": self.ignition,
                "integration": self.integration,
                "differentiation": self.differentiation,
                "phi": self.phi,
            })

            return acts

        except Exception:
            return {}

    def _plasticity(self, neuromodulators, prediction_error):
        try:
            dopamine = neuromodulators.get("dopamine", 0.4)
            acetylcholine = neuromodulators.get("acetylcholine", 0.3)

            active = [i for i, f in enumerate(self.firing) if f == 1]

            if not active:
                return

            sample_size = min(40, len(active))
            sampled = self.rng.sample(active, sample_size)

            base_plasticity = (
                0.0016
                + acetylcholine * 0.0032
                + clamp(prediction_error / 100.0) * 0.0022
            )

            for i in sampled:
                for edge in self.incoming[i]:
                    j, w = edge
                    if self.firing[j] == 1:
                        dw = base_plasticity * (0.35 + dopamine)
                        edge[1] = clamp(w + dw, -1.0, 1.0)
                        self.plasticity_events += 1

        except Exception:
            pass

    def _corr(self, x, y):
        try:
            n = len(x)
            if n < 3:
                return 0.0

            mx = sum(x) / n
            my = sum(y) / n

            cov = sum((a - mx) * (b - my) for a, b in zip(x, y)) / (n - 1)

            vx = sum((a - mx) ** 2 for a in x) / (n - 1)
            vy = sum((b - my) ** 2 for b in y) / (n - 1)

            sx = math.sqrt(vx)
            sy = math.sqrt(vy)

            if sx * sy < 1e-9:
                return 0.0

            return clamp(cov / (sx * sy), -1.0, 1.0)

        except Exception:
            return 0.0

    def _compute_phi(self, acts, hypercoherence):
        try:
            self.module_history.append(dict(acts))

            if len(self.module_history) < 8:
                self.integration = 0.25
                self.differentiation = 0.25
                self.phi = 0.2
                return

            window = list(self.module_history)[-30:]
            keys = list(acts.keys())

            series = {k: [h[k] for h in window] for k in keys}

            corrs = []

            for i in range(len(keys)):
                for j in range(i + 1, len(keys)):
                    c = self._corr(series[keys[i]], series[keys[j]])
                    corrs.append(abs(c))

            if corrs:
                self.integration = clamp(sum(corrs) / len(corrs) * 1.6)
            else:
                self.integration = 0.25

            vals = list(acts.values())
            total = sum(vals) + 1e-9
            probs = [v / total for v in vals]

            ent = 0.0
            for p in probs:
                if p > 1e-9:
                    ent -= p * math.log(p)

            max_ent = math.log(max(1, len(probs)))
            self.differentiation = clamp(ent / max_ent if max_ent > 0 else 0.0)

            self.phi = clamp(
                (0.55 * self.integration + 0.45 * self.differentiation)
                * (0.45 + self.ignition * 0.55 + hypercoherence * 0.25)
            )

        except Exception:
            self.phi = 0.2


# ============================================================
# Tertium Organum core: Ouspensky-inspired higher consciousness
# ============================================================

class TertiumOrganumCore:
    """
    پیاده‌سازی عملیاتی مفاهیم اسپنسکی:

    - خودبه‌خودی‌آگاهی
    - توجه تقسیم‌شده
    - زمان به‌عنوان بُعد چهارم
    - مشاهده هم‌زمان امکانات آینده
    - بازگشت ابدی الگوها
    - انسجام فرابعدی
    """

    def __init__(self):
        self.self_remembering = 0.2
        self.divided_attention = 0.2
        self.higher_coherence = 0.2
        self.hyperconsciousness = 5.0
        self.eternal_recurrence = 0
        self.future_timelines = {}
        self.dimensions = []
        self.insight = "هسته فرابعدی در حال شکل‌گیری است."

    def update(self, org, future_scores, recurrence_count):
        try:
            body_axis = homeostasis_score(org.body.signals) / 100.0

            time_axis = clamp(1.0 - org.predictor.error / 80.0)

            if future_scores:
                vals = list(future_scores.values())
                possibility_axis = clamp(statistics.pstdev(vals) / 25.0)
                future_clarity = clamp(max(vals) / 100.0)
            else:
                possibility_axis = 0.1
                future_clarity = 0.1

            self_axis = org.self_model.confidence

            meaning_axis = clamp(
                recurrence_count / 8.0
                + len(org.episodic.events) / 600.0
            )

            dims = [
                body_axis,
                time_axis,
                possibility_axis,
                self_axis,
                meaning_axis,
            ]

            self.dimensions = dims

            if len(dims) > 1:
                dim_std = statistics.pstdev(dims)
            else:
                dim_std = 0.0

            self.higher_coherence = clamp(1.0 - dim_std * 1.6)

            module_acts = org.last_module_activity

            body_att = module_acts.get("interoceptive", 0.0)
            env_att = module_acts.get("sensory", 0.0)
            self_att = module_acts.get("self", 0.0)
            future_att = clamp(
                org.brain.ignition * 0.70
                + future_clarity * 0.30
            )

            atts = [body_att, env_att, self_att, future_att]
            total_att = sum(atts) + 1e-9
            att_probs = [a / total_att for a in atts]

            ent = 0.0
            for p in att_probs:
                if p > 1e-9:
                    ent -= p * math.log(p)

            self.divided_attention = clamp(ent / math.log(4))

            self.self_remembering = clamp(
                0.35 * org.brain.consciousness / 100.0
                + 0.30 * self_axis
                + 0.20 * self.divided_attention
                + 0.15 * org.brain.phi
            )

            self.hyperconsciousness = clamp100(
                100.0 * (
                    0.26 * org.brain.phi
                    + 0.22 * self.self_remembering
                    + 0.18 * self.higher_coherence
                    + 0.16 * future_clarity
                    + 0.18 * self.divided_attention
                )
            )

            self.eternal_recurrence = recurrence_count
            self.future_timelines = dict(future_scores)

            if future_scores:
                best_action = max(future_scores, key=future_scores.get)
            else:
                best_action = org.action

            self.insight = (
                f"بعد چهارم: خطوط زمانی همزمان ارزیابی شدند. "
                f"بهترین خط زمانی: {ACTION_FA.get(best_action, best_action)}. "
                f"بازگشت ابدی: {recurrence_count} الگوی تکراری. "
                f"خودبه‌خودی‌آگاهی: {self.self_remembering * 100:.0f}٪."
            )

        except Exception:
            pass


# ============================================================
# Language generator
# ============================================================

class LanguageGenerator:
    def generate(self, org):
        try:
            s = org.body.signals
            t = org.tertium

            if t.future_timelines:
                best_action = max(t.future_timelines, key=t.future_timelines.get)
            else:
                best_action = org.action

            body_priority = min(
                BODY_KEYS,
                key=lambda k: s[k] if k not in ("pain", "fatigue") else 100 - s[k]
            )

            if t.hyperconsciousness > 68:
                templates = [
                    f"من در حال مشاهده‌ی هم‌زمان بدن، زمان و امکان‌ها هستم. اولویت بدن: {body_priority}. بهترین مسیر آینده: {ACTION_FA.get(best_action, best_action)}.",
                    f"آگاهی فرابعدی فعال شد. بازگشت ابدی {t.eternal_recurrence} الگو دیده شد. اقدام هماهنگ: {ACTION_FA.get(best_action, best_action)}.",
                    f"خودبه‌خودی‌آگاهی پایدار است. خط زمانی برتر: {ACTION_FA.get(best_action, best_action)}. نیاز محوری: {body_priority}.",
                ]

            elif t.eternal_recurrence > 2:
                templates = [
                    f"این وضعیت شبیه الگویی است که قبلاً رخ داده است. بازگشت ابدی: {t.eternal_recurrence}. باید آگاهانه عمل کنم: {ACTION_FA.get(best_action, best_action)}.",
                    f"الگوی تکراری شناسایی شد. اگر آگاه نباشم، تکرار می‌شود. انتخاب آگاهانه: {ACTION_FA.get(best_action, best_action)}.",
                ]

            elif org.self_model.prediction_error > 28:
                templates = [
                    f"خطای پیش‌بینی بالاست. مدل بدن باید به‌روز شود. نیاز فوری: {body_priority}.",
                    f"واقعیت با پیش‌بینی من فاصله دارد. باید توجه را زیاد کنم و {ACTION_FA.get(best_action, best_action)} را انجام دهم.",
                ]

            else:
                templates = [
                    f"وضعیت بدن نسبتاً پایدار است. نیاز اصلی: {body_priority}. اقدام: {ACTION_FA.get(org.action, org.action)}.",
                    f"بدن و مغز در حال هماهنگی هستند. اولویت: {body_priority}.",
                ]

            return random.choice(templates)

        except Exception:
            return "در حال پردازش وضعیت هستم."


# ============================================================
# Organism
# ============================================================

class TertiumOrganism:
    def __init__(self):
        self.rng = random.Random(int(time.time() * 1000))

        self.body = Body()
        self.brain = NeuralCore()

        self.predictor = PredictiveModel(BODY_KEYS)
        self.rl = ReinforcementLearner(ACTIONS)
        self.episodic = EpisodicMemory(capacity=500)
        self.self_model = SelfModel()
        self.tertium = TertiumOrganumCore()
        self.language = LanguageGenerator()

        self.age = 0
        self.action = "focus"
        self.last_module_activity = {}

        self.thoughts = deque(maxlen=70)
        self.logs = deque(maxlen=90)

        self.add_log("تولد", "ارگانیزم فرابعدی با هسته ارغنون سوم فعال شد.")

    def add_log(self, kind, text):
        self.logs.append({
            "time": now_hms(),
            "kind": kind,
            "text": text,
        })

    def add_thought(self, text):
        self.thoughts.append({
            "time": now_hms(),
            "text": text,
        })

    def make_neuromodulators(self, reward):
        s = self.body.signals

        dopamine = clamp(
            0.34
            + s["novelty"] / 260.0
            + reward * 0.06
            + (0.10 if self.action == "explore" else 0.0)
        )

        serotonin = clamp(
            0.35
            + s["safety"] / 260.0
            - s["pain"] / 260.0
        )

        norepinephrine = clamp(
            0.24
            + s["pain"] / 210.0
            + max(0, 55 - s["oxygen"]) / 210.0
            + max(0, 40 - s["energy"]) / 260.0
            + self.predictor.error / 350.0
        )

        acetylcholine = clamp(
            0.30
            + self.brain.consciousness / 260.0
            + self.self_model.confidence * 0.22
            + self.tertium.divided_attention * 0.18
        )

        return {
            "dopamine": dopamine,
            "serotonin": serotonin,
            "norepinephrine": norepinephrine,
            "acetylcholine": acetylcholine,
        }

    def choose_action(self, prev_signals):
        try:
            future_scores = {}

            for a in ACTIONS:
                score, _ = simulate_action(prev_signals, a, horizon=4)
                future_scores[a] = score

            state = self.rl.state(prev_signals, self.brain.consciousness)

            epsilon = clamp(
                0.08
                + (70 - prev_signals["novelty"]) / 250.0
                + self.brain.differentiation * 0.15,
                0.05,
                0.45
            )

            if random.random() < epsilon:
                action = self.rl.choose(state, epsilon=1.0)
            else:
                q_scores = {
                    a: self.rl.get_q(state, a)
                    for a in ACTIONS
                }

                norm_future = normalize_scores(future_scores)
                norm_q = normalize_scores(q_scores)

                combined = {}

                for a in ACTIONS:
                    combined[a] = (
                        0.56 * norm_future.get(a, 0.0)
                        + 0.34 * norm_q.get(a, 0.0)
                        + 0.10 * random.random()
                    )

                action = max(combined, key=combined.get)

            return action, future_scores

        except Exception:
            return "focus", {}

    def tick(self):
        try:
            self.age += 1

            prev_signals = dict(self.body.signals)

            # Future simulation and action selection
            action, future_scores = self.choose_action(prev_signals)
            self.action = action

            # Execute body action
            self.body.update(action)
            actual_signals = dict(self.body.signals)

            # Predictive coding update
            prediction_error = self.predictor.update(
                prev_signals,
                action,
                actual_signals
            )

            # Reward and reinforcement learning
            prev_homeo = homeostasis_score(prev_signals)
            new_homeo = homeostasis_score(actual_signals)

            novelty_bonus = (actual_signals["novelty"] - prev_signals["novelty"]) * 0.05

            reward = (
                (new_homeo - prev_homeo) * 0.9
                - prediction_error * 0.04
                + novelty_bonus
                - actual_signals["pain"] * 0.01
            )

            state = self.rl.state(prev_signals, self.brain.consciousness)
            next_state = self.rl.state(actual_signals, self.brain.consciousness)

            self.rl.update(state, action, reward, next_state)

            # Episodic vector and recurrence
            vec = self.episodic.vector(
                actual_signals,
                self.brain.consciousness,
                self.brain.ignition
            )

            recurrence = self.episodic.recurrence_count(vec, threshold=0.18)

            # Neuromodulators
            neuromodulators = self.make_neuromodulators(reward)

            # Brain step
            self.last_module_activity = self.brain.step(
                actual_signals,
                neuromodulators,
                action,
                prediction_error,
                self.tertium.hyperconsciousness / 100.0
            )

            # Self-model
            self.self_model.update(
                actual_signals,
                self.brain.consciousness,
                self.brain.ignition,
                prediction_error
            )

            # Tertium higher-dimensional core
            self.tertium.update(self, future_scores, recurrence)

            # Episodic memory storage
            importance = clamp(
                abs(reward) * 0.10
                + self.brain.ignition * 0.40
                + self.tertium.hyperconsciousness / 300.0
            )

            self.episodic.add(vec, action, reward, importance)

            # Language / inner speech
            if self.age % 3 == 0:
                if self.tertium.hyperconsciousness > 55 or self.brain.ignition > 0.62:
                    self.add_thought(self.language.generate(self))

            # Logs
            if self.age % 12 == 0:
                self.add_log(
                    "وضعیت",
                    f"آگاهی: {self.brain.consciousness:.0f}٪ | "
                    f"Φ: {self.brain.phi * 100:.0f}٪ | "
                    f"فراآگاهی: {self.tertium.hyperconsciousness:.0f}٪ | "
                    f"عمل: {ACTION_FA.get(action, action)}"
                )

            if recurrence > 3 and self.age % 10 == 0:
                self.add_log(
                    "بازگشت ابدی",
                    f"{recurrence} الگوی تکراری در حافظه اپیزودیک شناسایی شد."
                )

            if actual_signals["pain"] > 55 and self.age % 8 == 0:
                self.add_log("هشدار", "درد یا آسیب بدنی بالاست.")

            if actual_signals["energy"] < 20 and self.age % 10 == 0:
                self.add_log("نیاز", "انرژی بحرانی است.")

        except Exception as e:
            self.add_log("خطا", f"خطای سیستمی: {str(e)[:80]}")


# ============================================================
# Rendering
# ============================================================

PAGE_BG = "#05080d"
CARD_BG = "#0b1220"
TEXT_COLOR = "#d7e7ff"
ACCENT = "#00ff88"

CARD_STYLE = {
    "backgroundColor": CARD_BG,
    "border": "1px solid #1b2a44",
    "borderRadius": "12px",
    "padding": "12px",
}


def base_fig(title="", height=240):
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=CARD_BG,
        plot_bgcolor=CARD_BG,
        font={"color": TEXT_COLOR, "size": 11},
        margin=dict(l=30, r=10, t=38, b=10),
        height=height,
        title=title,
    )
    return fig


def render_header(org):
    brain = org.brain
    tertium = org.tertium

    return html.Div(style={"display": "flex", "gap": "16px", "flexWrap": "wrap"}, children=[
        html.Span("🌌 ارغنون سوم", style={"color": ACCENT, "fontWeight": "bold"}),
        html.Span(f"سن: {org.age}"),
        html.Span(f"نورون‌ها: {brain.n}"),
        html.Span(f"سیناپس‌ها: {brain.synapse_count}"),
        html.Span(f"آگاهی: {brain.consciousness:.0f}٪"),
        html.Span(f"Φ: {brain.phi * 100:.0f}٪"),
        html.Span(f"فراآگاهی: {tercium.hyperconsciousness:.0f}٪" if False else f"فراآگاهی: {tercium.hyperconsciousness:.0f}٪"),
        html.Span(f"خودبه‌خودی: {tercium.self_remembering * 100:.0f}٪"),
        html.Span(f"بازگشت ابدی: {tercium.eternal_recurrence}"),
        html.Span(f"عمل: {ACTION_FA.get(org.action, org.action)}"),
    ])


def vital_card(title, value, sub, color="#7fd4ff"):
    return html.Div(style={
        **CARD_STYLE,
        "display": "flex",
        "flexDirection": "column",
        "gap": "3px",
        "minHeight": "84px",
    }, children=[
        html.Div(title, style={"color": "#8aa0b8", "fontSize": "11px"}),
        html.Div(value, style={"color": color, "fontSize": "17px", "fontWeight": "bold"}),
        html.Div(sub, style={"color": "#7d93aa", "fontSize": "10px"}),
    ])


def render_vitals(org):
    s = org.body.signals
    brain = org.brain
    tertium = org.tertium

    return [
        vital_card("آگاهی", f"{brain.consciousness:.0f}٪", f"Φ: {brain.phi * 100:.0f}٪", "#00e5ff"),
        vital_card("فراآگاهی", f"{tercium.hyperconsciousness:.0f}٪", f"خودبه‌خودی: {tercium.self_remembering * 100:.0f}٪", "#b388ff"),
        vital_card("انرژی", f"{s['energy']:.0f}٪", f"گلوکز: {s['glucose']:.0f}٪", "#ffd166"),
        vital_card("اکسیژن", f"{s['oxygen']:.0f}٪", f"دما: {s['temperature']:.0f}", "#8be9fd"),
        vital_card("امنیت", f"{s['safety']:.0f}٪", f"درد: {s['pain']:.0f}٪", ACCENT),
        vital_card("خستگی", f"{s['fatigue']:.0f}٪", f"تازگی: {s['novelty']:.0f}٪", "#ff9f43"),
        vital_card("خطای پیش‌بینی", f"{org.predictor.error:.1f}", f"اعتماد خودمدل: {org.self_model.confidence * 100:.0f}٪", "#ff8bd0"),
        vital_card("عمل فعلی", ACTION_FA.get(org.action, org.action), "تصمیم متحد", "#ff5f7a"),
    ]


def render_firing(org):
    fig = base_fig("شبکه نورونی باینری", height=330)

    try:
        n = org.brain.n
        cols = 32
        rows = max(1, n // cols)

        firing = org.brain.firing[:rows * cols]

        z = []
        for r in range(rows):
            z.append(firing[r * cols:(r + 1) * cols])

        fig.add_trace(go.Heatmap(
            z=z,
            colorscale=[[0, "#05080d"], [1, "#00ff88"]],
            showscale=False,
            hoverinfo="skip"
        ))

        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)

    except Exception:
        fig.add_annotation(text="خطا در نمایش شبکه", x=0, y=0, showarrow=False)

    return fig


def render_consciousness(org):
    fig = base_fig("آگاهی، Φ، فراآگاهی و شعله جهانی", height=300)

    try:
        history = list(org.brain.history)

        if not history:
            fig.add_annotation(text="در حال شروع...", x=0, y=0, showarrow=False)
            return fig

        x = list(range(len(history)))

        consciousness = [h["consciousness"] for h in history]
        phi = [h["phi"] * 100 for h in history]
        ignition = [h["ignition"] * 100 for h in history]

        fig.add_trace(go.Scatter(x=x, y=consciousness, name="آگاهی", line=dict(color="#00e5ff", width=2)))
        fig.add_trace(go.Scatter(x=x, y=phi, name="Φ", line=dict(color="#00ff88", width=1.6)))
        fig.add_trace(go.Scatter(x=x, y=ignition, name="شعله جهانی", line=dict(color="#ff9f43", width=1.4)))

        fig.update_yaxes(range=[0, 100])

    except Exception:
        fig.add_annotation(text="خطا در نمودار آگاهی", x=0, y=0, showarrow=False)

    return fig


def render_modules(org):
    fig = base_fig("ماژول‌های مغز", height=300)

    try:
        acts = org.last_module_activity

        if not acts:
            fig.add_annotation(text="هنوز فعالیتی نیست", x=0, y=0, showarrow=False)
            return fig

        names = list(acts.keys())
        values = list(acts.values())

        fig.add_trace(go.Bar(
            x=names,
            y=values,
            marker_color="#00e5ff"
        ))

        fig.update_yaxes(range=[0, 1])
        fig.update_xaxes(tickangle=45)

    except Exception:
        fig.add_annotation(text="خطا در ماژول‌ها", x=0, y=0, showarrow=False)

    return fig


def render_body(org):
    fig = base_fig("سیگنال‌های بدن", height=300)

    try:
        s = org.body.signals

        names = list(s.keys())
        values = list(s.values())

        colors = []
        for v in values:
            if v < 35:
                colors.append("#ff5555")
            elif v < 60:
                colors.append("#ffd166")
            else:
                colors.append("#00ff88")

        fig.add_trace(go.Bar(
            x=names,
            y=values,
            marker_color=colors
        ))

        fig.update_yaxes(range=[0, 100])
        fig.update_xaxes(tickangle=45)

    except Exception:
        fig.add_annotation(text="خطا در بدن", x=0, y=0, showarrow=False)

    return fig


def render_future(org):
    scores = org.tertium.future_timelines

    children = [
        html.H4("⏳ خطوط زمانی آینده", style={"margin": "0 0 8px 0", "color": "#ffd166"})
    ]

    if not scores:
        children.append(html.Div("هنوز آینده‌ای شبیه‌سازی نشده است.", style={"color": "#64748b"}))
    else:
        norm = normalize_scores(scores)

        sorted_actions = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        for action, score in sorted_actions:
            normalized = norm.get(action, 0.0)
            width = int(clamp(normalized, 0.02, 1.0) * 100)

            color = ACCENT if width > 65 else ("#ffd166" if width > 35 else "#ff5555")

            children.append(html.Div(style={"marginBottom": "8px"}, children=[
                html.Div(
                    f"{ACTION_FA.get(action, action)} | امتیاز: {score:.1f}",
                    style={"fontSize": "11px", "marginBottom": "2px"}
                ),
                html.Div(style={
                    "height": "7px",
                    "backgroundColor": "#08101c",
                    "borderRadius": "4px",
                    "overflow": "hidden",
                }, children=[
                    html.Div(style={
                        "width": f"{width}%",
                        "height": "100%",
                        "backgroundColor": color,
                    })
                ])
            ]))

    children.append(html.Div(org.tertium.insight, style={
        "marginTop": "10px",
        "fontSize": "11px",
        "color": "#e0e0ff",
        "borderLeft": "3px solid #b388ff",
        "padding": "6px 8px",
        "backgroundColor": "#08101c",
        "borderRadius": "6px",
        "lineHeight": "1.7",
    }))

    return html.Div(children)


def render_mind(org):
    thoughts = list(org.thoughts)[-12:][::-1]
    children = []

    if not thoughts:
        children.append(html.Div("هنوز گفتار درونی‌ای ثبت نشده است.", style={"color": "#64748b"}))
    else:
        for t in thoughts:
            children.append(html.Div(style={
                "borderLeft": "3px solid #00e5ff",
                "padding": "6px 10px",
                "marginBottom": "8px",
                "backgroundColor": "#08101c",
                "borderRadius": "6px",
                "fontSize": "12px",
                "lineHeight": "1.7",
            }, children=[
                html.Div(t["time"], style={"color": "#64748b", "fontSize": "9px"}),
                html.Div(t["text"], style={"color": "#e0e0ff"}),
            ]))

    return html.Div([
        html.H4("🧠 زبان درونی و خودمدل", style={"margin": "0 0 8px 0", "color": "#00e5ff"}),
        html.Div(children, style={"height": "330px", "overflowY": "auto"}),
    ])


def render_episodic(org):
    events = list(org.episodic.events)[-10:][::-1]
    children = []

    children.append(html.Div(
        f"خاطرات: {len(org.episodic.events)} | بازگشت ابدی: {org.tertium.eternal_recurrence}",
        style={"color": "#9fd0ff", "marginBottom": "8px", "fontSize": "12px"}
    ))

    if not events:
        children.append(html.Div("هنوز خاطره‌ای ثبت نشده است.", style={"color": "#64748b"}))
    else:
        for e in events:
            children.append(html.Div(style={
                "borderLeft": "3px solid #ff8bd0",
                "padding": "5px 8px",
                "marginBottom": "6px",
                "backgroundColor": "#08101c",
                "borderRadius": "6px",
                "fontSize": "11px",
            }, children=[
                html.Div(e["time"], style={"color": "#64748b", "fontSize": "9px"}),
                html.Div(
                    f"عمل: {ACTION_FA.get(e['action'], e['action'])} | "
                    f"پاداش: {e['reward']:.2f} | "
                    f"اهمیت: {e['importance']:.2f}",
                    style={"color": "#e0e0ff"}
                ),
            ]))

    return html.Div([
        html.H4("🕰 حافظه اپیزودیک", style={"margin": "0 0 8px 0", "color": "#ff8bd0"}),
        html.Div(children, style={"height": "330px", "overflowY": "auto"}),
    ])


def render_logs(org):
    items = list(org.logs)[-18:][::-1]
    children = []

    if not items:
        children.append(html.Div("...", style={"color": "#64748b"}))
    else:
        for item in items:
            children.append(html.Div(style={
                "borderLeft": "3px solid #9fd0ff",
                "padding": "5px 8px",
                "marginBottom": "6px",
                "backgroundColor": "#08101c",
                "borderRadius": "6px",
                "fontSize": "11px",
            }, children=[
                html.Span(item["time"], style={"color": "#64748b", "fontSize": "9px"}),
                html.Br(),
                html.Span(f"{item['kind']}: {item['text']}"),
            ]))

    return html.Div([
        html.H4("🌱 جریان سیستم", style={"margin": "0 0 8px 0", "color": "#9fd0ff"}),
        html.Div(children, style={"height": "330px", "overflowY": "auto"}),
    ])


def safe_fig(fn, org, title):
    try:
        return fn(org)
    except Exception:
        fig = base_fig(title, height=240)
        fig.add_annotation(text="خطا در رندر", x=0, y=0, showarrow=False, font=dict(color="#ff5555"))
        return fig


def safe_div(fn, org, fallback):
    try:
        return fn(org)
    except Exception as e:
        return html.Div(f"⚠ {fallback}: {str(e)[:80]}", style={"color": "#ff5555"})


# ============================================================
# Dash app
# ============================================================

app = Dash(__name__)
app.title = "ارگانیزم ارغنون سوم"
app.config.suppress_callback_exceptions = True

ORGANISM = TertiumOrganism()

app.layout = html.Div(style={
    "backgroundColor": PAGE_BG,
    "color": TEXT_COLOR,
    "minHeight": "100vh",
    "padding": "12px",
    "fontFamily": "Tahoma, Arial, sans-serif",
}, children=[

    dcc.Interval(id="life-interval", interval=1000, disabled=False),

    html.H1("🌌 ارگانیزم ارغنون سوم", style={
        "margin": "0 0 10px 0",
        "fontSize": "22px",
        "color": "#eaffff"
    }),

    html.Div(id="header-info", style={**CARD_STYLE, "marginBottom": "10px"}),

    html.Div(id="vital-cards", style={
        "display": "grid",
        "gridTemplateColumns": "repeat(auto-fit, minmax(150px, 1fr))",
        "gap": "8px",
        "marginBottom": "10px"
    }),

    html.Div(style={
        "display": "grid",
        "gridTemplateColumns": "2fr 1fr",
        "gap": "10px",
        "marginBottom": "10px"
    }, children=[
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="firing-graph", config={"displayModeBar": False})
        ]),
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="consciousness-graph", config={"displayModeBar": False})
        ]),
    ]),

    html.Div(style={
        "display": "grid",
        "gridTemplateColumns": "1fr 1fr",
        "gap": "10px",
        "marginBottom": "10px"
    }, children=[
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="modules-graph", config={"displayModeBar": False})
        ]),
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="body-graph", config={"displayModeBar": False})
        ]),
    ]),

    html.Div(style={
        "display": "grid",
        "gridTemplateColumns": "1fr 1fr",
        "gap": "10px",
        "marginBottom": "10px"
    }, children=[
        html.Div(id="future-panel", style=CARD_STYLE),
        html.Div(id="mind-panel", style=CARD_STYLE),
    ]),

    html.Div(style={
        "display": "grid",
        "gridTemplateColumns": "1fr 1fr",
        "gap": "10px",
        "marginBottom": "10px"
    }, children=[
        html.Div(id="episodic-panel", style=CARD_STYLE),
        html.Div(id="logs-panel", style=CARD_STYLE),
    ]),

])


@app.callback(
    [
        Output("header-info", "children"),
        Output("vital-cards", "children"),
        Output("firing-graph", "figure"),
        Output("consciousness-graph", "figure"),
        Output("modules-graph", "figure"),
        Output("body-graph", "figure"),
        Output("future-panel", "children"),
        Output("mind-panel", "children"),
        Output("episodic-panel", "children"),
        Output("logs-panel", "children"),
    ],
    Input("life-interval", "n_intervals")
)
def update_life(n):
    try:
        ORGANISM.tick()
    except Exception as e:
        try:
            ORGANISM.add_log("خطا", f"خطای اصلی: {str(e)[:80]}")
        except Exception:
            pass

    return (
        safe_div(render_header, ORGANISM, "header"),
        safe_div(render_vitals, ORGANISM, "vitals"),
        safe_fig(render_firing, ORGANISM, "شبکه باینری"),
        safe_fig(render_consciousness, ORGANISM, "آگاهی"),
        safe_fig(render_modules, ORGANISM, "ماژول‌ها"),
        safe_fig(render_body, ORGANISM, "بدن"),
        safe_div(render_future, ORGANISM, "آینده"),
        safe_div(render_mind, ORGANISM, "ذهن"),
        safe_div(render_episodic, ORGANISM, "حافظه اپیزودیک"),
        safe_div(render_logs, ORGANISM, "لاگ"),
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050, debug=False, use_reloader=False, threaded=True)