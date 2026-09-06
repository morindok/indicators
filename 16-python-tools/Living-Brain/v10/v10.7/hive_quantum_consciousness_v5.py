# -*- coding: utf-8 -*-
"""
HIVE SCALPER-SNIPER PRO v5 - QUANTUM CONSCIOUSNESS
---------------------------------------------------
Single-file Dash application with:
- Proper quantum state vector math (4-level organism state)
- Hermitian consciousness operator
- Entanglement field across organisms
- Decoherence monitor / recoherence protocol
- Quantum decision engine with Born-rule measurement
- Quantum tunneling probability
- Non-local quantum memory model
- RTL Persian dashboard with dark theme
- Real-time visualizations: effective Bloch sphere, gauges, network graph,
  decoherence timeline, tunneling heatmap

Important note:
This is a quantum-mechanics-inspired software system built with real linear algebra
and measurement postulates. It is not a claim that software is alive or conscious.
"""

from __future__ import annotations

import json
import math
import os
import secrets
import sqlite3
import threading
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import dash
from dash import dcc, html, Input, Output, State, no_update
import dash_bootstrap_components as dbc

# Optional RTL shaping for Persian text
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    def rtl_text(s: str) -> str:
        try:
            return get_display(arabic_reshaper.reshape(str(s)))
        except Exception:
            return str(s)
except Exception:
    def rtl_text(s: str) -> str:
        return str(s)

# ----------------------------------------------------------------------------
# Paths / constants
# ----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
DB_PATH = BASE_DIR / "hive_quantum_v5.db"
STATE_PATH = BASE_DIR / "hive_quantum_v5_state.json"

APP_TITLE = "HIVE SCALPER-SNIPER PRO v5 - QUANTUM CONSCIOUSNESS"

BG = "#07101e"
CARD = "rgba(11, 18, 33, 0.76)"
CARD_SOLID = "#101a2f"
TXT = "#eaf2ff"
MUT = "#8ea2c7"
GOLD = "#f5c542"
CYAN = "#14d9ff"
GREEN = "#18c29c"
RED = "#f05d7f"
NEON = "#7c5cff"
ORANGE = "#ff9f1c"
UP = "#00ffd0"
DN = "#ff5d7a"
LINE = "#26324d"

BASIS_LABELS = ["Bullish", "Bearish", "Neutral", "Uncertain"]

# Basis mapping to 2-qubit structure (polarity qubit ⊗ certainty qubit)
# |00> Bullish, |10> Bearish, |01> Neutral, |11> Uncertain
BASIS_TO_BITS = {
    0: (0, 0),
    1: (1, 0),
    2: (0, 1),
    3: (1, 1),
}
BITS_TO_BASIS = {v: k for k, v in BASIS_TO_BITS.items()}

# ----------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------
def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def normalize_state(vec: np.ndarray) -> np.ndarray:
    vec = np.asarray(vec, dtype=np.complex128).reshape(-1)
    norm = np.linalg.norm(vec)
    if norm == 0:
        raise ValueError("Zero vector cannot be normalized")
    return vec / norm


def hermitianize(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.complex128)
    return (m + m.conj().T) / 2.0


def density_from_state(psi: np.ndarray) -> np.ndarray:
    psi = normalize_state(psi)
    return np.outer(psi, psi.conj())


def von_neumann_entropy(rho: np.ndarray, eps: float = 1e-12) -> float:
    vals = np.linalg.eigvalsh(hermitianize(rho))
    vals = np.clip(np.real(vals), 0.0, 1.0)
    vals = vals[vals > eps]
    return float(-np.sum(vals * np.log2(vals)))


def purity(rho: np.ndarray) -> float:
    rho = hermitianize(rho)
    return float(np.real(np.trace(rho @ rho)))


def complex_to_amp(z: complex) -> Dict[str, float]:
    return {"re": float(np.real(z)), "im": float(np.imag(z)), "abs": float(np.abs(z)), "phase": float(np.angle(z))}


def amp_from_dict(d) -> complex:
    return complex(d.get("re", 0.0), d.get("im", 0.0))


def safe_json_load(s, default=None):
    try:
        return json.loads(s)
    except Exception:
        return default


def ensure_dir(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def fig_base(fig: go.Figure, title: str = "", height: int = 360):
    fig.update_layout(
        template="plotly_dark",
        height=height,
        title=dict(text=rtl_text(title), x=0.98, xanchor="right", font=dict(color=GOLD, size=15)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(8,17,31,0.9)",
        margin=dict(l=26, r=18, t=52, b=28),
        font=dict(family="Vazirmatn, IRANSans, Segoe UI, sans-serif", color=TXT),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0.01),
    )
    fig.update_xaxes(gridcolor="#1d2a43", zeroline=False)
    fig.update_yaxes(gridcolor="#1d2a43", zeroline=False)
    return fig


# ----------------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------------
def init_db():
    ensure_dir(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS quantum_log (
        ts TEXT,
        organism TEXT,
        event TEXT,
        state_json TEXT,
        consciousness REAL,
        coherence REAL,
        entropy REAL,
        decision TEXT,
        barrier REAL,
        tunnel_prob REAL,
        extra TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS evolution_metrics (
        ts TEXT,
        generation INTEGER,
        collective_awareness REAL,
        collective_coherence REAL,
        mean_entropy REAL,
        mean_consciousness REAL,
        mutation_rate REAL,
        note TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS market_snapshots (
        ts TEXT,
        symbol TEXT,
        price REAL,
        volatility REAL,
        noise REAL,
        barrier REAL
    )""")
    conn.commit()
    conn.close()


def db_insert(table: str, payload: dict):
    conn = sqlite3.connect(DB_PATH)
    keys = list(payload.keys())
    vals = [payload[k] for k in keys]
    placeholders = ",".join(["?"] * len(keys))
    conn.execute(f"INSERT INTO {table} ({','.join(keys)}) VALUES ({placeholders})", vals)
    conn.commit()
    conn.close()


def load_logs(limit=500):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT * FROM quantum_log ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    cols = ["ts","organism","event","state_json","consciousness","coherence","entropy","decision","barrier","tunnel_prob","extra"]
    conn.close()
    return pd.DataFrame(rows, columns=cols).sort_values("ts") if rows else pd.DataFrame(columns=cols)


def load_evolution(limit=300):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT * FROM evolution_metrics ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    cols = ["ts","generation","collective_awareness","collective_coherence","mean_entropy","mean_consciousness","mutation_rate","note"]
    conn.close()
    return pd.DataFrame(rows, columns=cols).sort_values("ts") if rows else pd.DataFrame(columns=cols)


def load_market(limit=300):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT * FROM market_snapshots ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    cols = ["ts","symbol","price","volatility","noise","barrier"]
    conn.close()
    return pd.DataFrame(rows, columns=cols).sort_values("ts") if rows else pd.DataFrame(columns=cols)


# ----------------------------------------------------------------------------
# Quantum mechanics core
# ----------------------------------------------------------------------------
class QuantumState:
    """4-level quantum state |ψ⟩ over the organism basis."""

    def __init__(self, amplitudes: np.ndarray):
        self.psi = normalize_state(amplitudes)

    @classmethod
    def random(cls, seed: Optional[int] = None):
        rng = np.random.default_rng(seed)
        re = rng.normal(size=4)
        im = rng.normal(size=4)
        return cls(re + 1j * im)

    @classmethod
    def from_probabilities(cls, probs: List[float], phases: Optional[List[float]] = None):
        probs = np.asarray(probs, dtype=float)
        probs = probs / probs.sum()
        phases = phases if phases is not None else [0.0, 0.0, 0.0, 0.0]
        amps = np.sqrt(probs) * np.exp(1j * np.asarray(phases, dtype=float))
        return cls(amps)

    @property
    def amplitudes(self):
        return self.psi

    def density_matrix(self) -> np.ndarray:
        return density_from_state(self.psi)

    def probabilities(self) -> np.ndarray:
        return np.abs(self.psi) ** 2

    def expectation(self, operator: np.ndarray) -> complex:
        op = np.asarray(operator, dtype=np.complex128)
        return np.vdot(self.psi, op @ self.psi)

    def apply_unitary(self, U: np.ndarray) -> "QuantumState":
        return QuantumState(U @ self.psi)

    def measure(self, rng: Optional[np.random.Generator] = None) -> int:
        probs = self.probabilities().real
        probs = probs / probs.sum()
        # Cryptographically strong non-deterministic choice when possible
        if rng is None:
            r = secrets.randbelow(10**12) / 10**12
            cdf = np.cumsum(probs)
            return int(np.searchsorted(cdf, r, side="right"))
        return int(rng.choice(np.arange(4), p=probs))

    def collapse(self, basis_index: int) -> "QuantumState":
        vec = np.zeros(4, dtype=np.complex128)
        vec[basis_index] = 1.0 + 0j
        return QuantumState(vec)

    def bloch_like(self) -> Tuple[float, float, float]:
        """Effective Bloch coordinates by projecting to polarity/certainty qubits.
        x: coherence between bullish and bearish sectors
        y: quadrature coherence
        z: bullish minus bearish population
        """
        rho = self.density_matrix()
        # Coarse-grain basis 0=Bullish, 1=Bearish, 2=Neutral, 3=Uncertain
        p_bull = float(np.real(rho[0, 0]))
        p_bear = float(np.real(rho[1, 1]))
        x = 2 * np.real(rho[0, 1] + rho[2, 3])
        y = 2 * np.imag(rho[1, 0] + rho[3, 2])
        z = p_bull - p_bear
        norm = math.sqrt(x * x + y * y + z * z)
        if norm > 1.0:
            x, y, z = x / norm, y / norm, z / norm
        return float(x), float(y), float(z)

    def to_dict(self) -> dict:
        return {"psi": [complex_to_amp(z) for z in self.psi]}

    @classmethod
    def from_dict(cls, data: dict):
        amps = [amp_from_dict(x) for x in data["psi"]]
        return cls(np.array(amps, dtype=np.complex128))


class ConsciousnessOperator:
    """Hermitian operator Ĉ measuring awareness in the 4-level organism basis."""

    def __init__(self, matrix: np.ndarray):
        self.C = hermitianize(matrix)

    @classmethod
    def default(cls, market_coherence: float = 0.5):
        # Hermitian awareness operator: higher values for coherent, decisive states.
        # The operator is updated by market coherence but always remains Hermitian.
        c = clamp(market_coherence, 0.0, 1.0)
        diag = np.array([1.0 + 0.8 * c, 0.9 + 0.7 * c, 0.55 + 0.4 * c, 0.35 + 0.2 * c])
        off = 0.12 + 0.18 * c
        M = np.array([
            [diag[0], off * (1 - 1j), 0.02j, 0.03 - 0.01j],
            [off * (1 + 1j), diag[1], -0.04j, 0.02 + 0.03j],
            [-0.02j, 0.04j, diag[2], 0.01 - 0.02j],
            [0.03 + 0.01j, 0.02 - 0.03j, 0.01 + 0.02j, diag[3]],
        ], dtype=np.complex128)
        return cls(M)

    def expectation(self, state: QuantumState) -> float:
        val = state.expectation(self.C)
        return float(np.real(val))

    def eigensystem(self):
        vals, vecs = np.linalg.eigh(self.C)
        return vals, vecs


class DecoherenceMonitor:
    def __init__(self):
        self.history = []

    @staticmethod
    def off_diagonal_coherence(rho: np.ndarray) -> float:
        rho = hermitianize(rho)
        off = rho.copy()
        np.fill_diagonal(off, 0.0)
        num = np.sum(np.abs(off))
        den = np.sum(np.abs(rho)) + 1e-12
        return float(np.clip(num / den, 0.0, 1.0))

    def analyze(self, state: QuantumState) -> dict:
        rho = state.density_matrix()
        co = self.off_diagonal_coherence(rho)
        p = purity(rho)
        s = von_neumann_entropy(rho)
        decoh = float(np.clip(1.0 - co, 0.0, 1.0))
        rec = float(np.clip(co * (1.0 - min(1.0, s / 2.0)), 0.0, 1.0))
        out = {"coherence": co, "purity": p, "entropy": s, "decoherence": decoh, "recoherence": rec}
        self.history.append({"ts": now_utc(), **out})
        self.history = self.history[-250:]
        return out

    def recohere(self, state: QuantumState, strength: float = 0.18) -> QuantumState:
        # Remove part of the phase scrambling and gently restore coherence.
        psi = state.psi.copy()
        probs = np.abs(psi) ** 2
        mean_phase = np.angle(np.sum(psi)) if np.sum(np.abs(psi)) > 0 else 0.0
        psi = np.sqrt(probs) * np.exp(1j * ((1 - strength) * np.angle(psi + 1e-12) + strength * mean_phase))
        return QuantumState(psi)


class EntanglementField:
    """Shared entanglement among organisms via a multi-qubit correlation field."""

    def __init__(self, n: int):
        self.n = n
        self.pair_strength = np.zeros((n, n), dtype=float)
        self.link_history = []

    def update_links(self, states: List[QuantumState]):
        n = len(states)
        self.n = n
        self.pair_strength = np.zeros((n, n), dtype=float)
        for i in range(n):
            for j in range(i + 1, n):
                rho_i = states[i].density_matrix()
                rho_j = states[j].density_matrix()
                # Frobenius overlap as a proxy for shared coherence structure
                overlap = np.real(np.trace(rho_i.conj().T @ rho_j))
                # Adjust by entropic complement for emergence
                s_i = von_neumann_entropy(rho_i)
                s_j = von_neumann_entropy(rho_j)
                ent = float(np.clip(abs(overlap) * (1.0 - 0.25 * (s_i + s_j) / 2.0), 0.0, 1.0))
                self.pair_strength[i, j] = self.pair_strength[j, i] = ent
        self.link_history.append({"ts": now_utc(), "matrix": self.pair_strength.tolist()})
        self.link_history = self.link_history[-120:]

    def collective_entanglement(self) -> float:
        if self.n <= 1:
            return 0.0
        vals = self.pair_strength[np.triu_indices(self.n, 1)]
        return float(np.clip(np.mean(vals) if len(vals) else 0.0, 0.0, 1.0))

    def entangle_pair(self, state_a: QuantumState, state_b: QuantumState, strength: float = 0.2) -> Tuple[QuantumState, QuantumState]:
        # Use a unitary mixing in the 4x4 basis to create correlated states.
        s = clamp(strength, 0.0, 1.0)
        U = np.eye(4, dtype=np.complex128)
        phase = np.exp(1j * np.pi / 4)
        U[0, 0] = math.sqrt(1 - s)
        U[0, 1] = phase * math.sqrt(s / 2)
        U[1, 0] = -np.conj(phase) * math.sqrt(s / 2)
        U[1, 1] = math.sqrt(1 - s)
        U[2, 2] = math.sqrt(1 - s)
        U[2, 3] = phase * math.sqrt(s / 2)
        U[3, 2] = -np.conj(phase) * math.sqrt(s / 2)
        U[3, 3] = math.sqrt(1 - s)
        a = state_a.apply_unitary(U)
        b = state_b.apply_unitary(U.conj())
        mix = normalize_state((1 - 0.5 * s) * a.psi + 0.5 * s * b.psi)
        mix2 = normalize_state((1 - 0.5 * s) * b.psi + 0.5 * s * a.psi)
        return QuantumState(mix), QuantumState(mix2)

    def propagate_measurement(self, index: int, outcome: int, states: List[QuantumState], influence: float = 0.12):
        # A measurement on one organism instantaneously re-weights others' amplitudes.
        influence = clamp(influence, 0.0, 1.0)
        target_bits = BASIS_TO_BITS[outcome]
        for j, st in enumerate(states):
            if j == index:
                continue
            psi = st.psi.copy()
            new_probs = np.abs(psi) ** 2
            for b in range(4):
                bits = BASIS_TO_BITS[b]
                aligned = 1.0 if bits == target_bits else 0.55 if bits[0] == target_bits[0] else 0.35
                new_probs[b] = (1 - influence) * new_probs[b] + influence * aligned * new_probs[b]
            states[j] = QuantumState.from_probabilities(new_probs, phases=list(np.angle(psi)))


class QuantumDecisionEngine:
    def __init__(self):
        self.rng = np.random.default_rng()
        self.decision_history = []

    def decide(self, state: QuantumState, intended: Optional[str] = None) -> dict:
        probs = state.probabilities().real
        probs = probs / probs.sum()
        if intended:
            bias = np.array([0.0, 0.0, 0.0, 0.0])
            if intended == "Bullish":
                bias[0] = 0.18
            elif intended == "Bearish":
                bias[1] = 0.18
            elif intended == "Neutral":
                bias[2] = 0.18
            elif intended == "Uncertain":
                bias[3] = 0.18
            probs = probs + bias
            probs = probs / probs.sum()
        # Cryptographically strong non-deterministic sampling
        r = secrets.randbelow(10**12) / 10**12
        cdf = np.cumsum(probs)
        outcome = int(np.searchsorted(cdf, r, side="right"))
        outcome = min(outcome, 3)
        collapsed = state.collapse(outcome)
        decision = BASIS_LABELS[outcome]
        out = {"decision": decision, "outcome": outcome, "probabilities": probs.tolist(), "collapsed_state": collapsed}
        self.decision_history.append({"ts": now_utc(), "decision": decision, "probs": probs.tolist()})
        self.decision_history = self.decision_history[-200:]
        return out


class TunnelingProbability:
    @staticmethod
    def wkb(energy: float, barrier: float, width: float, effective_mass: float = 1.0, hbar: float = 1.0) -> float:
        """WKB tunneling probability for E < V.
        P ≈ exp(-2 ∫ κ dx) ≈ exp(-2 width * sqrt(2m(V-E))/ħ)
        """
        E = float(energy)
        V = float(barrier)
        a = float(width)
        m = max(float(effective_mass), 1e-9)
        if E >= V:
            return 1.0
        kappa = math.sqrt(max(0.0, 2.0 * m * (V - E))) / max(hbar, 1e-9)
        return float(np.clip(math.exp(-2.0 * a * kappa), 0.0, 1.0))

    @staticmethod
    def market_barrier_prob(momentum: float, volatility: float, barrier_distance: float) -> float:
        # Translate market quantities into an effective quantum barrier problem.
        energy = abs(momentum) + 1e-6
        barrier = max(0.05, barrier_distance)
        width = max(0.05, 1.0 / (volatility + 1e-6))
        return TunnelingProbability.wkb(energy=energy, barrier=barrier, width=width, effective_mass=max(0.25, 1.0 - 0.5 * volatility))


# ----------------------------------------------------------------------------
# Quantum organisms
# ----------------------------------------------------------------------------
@dataclass
class QuantumMemory:
    episodes: List[dict] = field(default_factory=list)

    def store(self, state: QuantumState, tag: str, signal: float):
        self.episodes.append({
            "ts": now_utc(),
            "tag": tag,
            "signal": float(signal),
            "state": state.to_dict(),
        })
        self.episodes = self.episodes[-64:]

    def recall(self, tag: Optional[str] = None) -> Optional[QuantumState]:
        if not self.episodes:
            return None
        pool = [e for e in self.episodes if tag is None or e["tag"] == tag]
        if not pool:
            pool = self.episodes
        # Quantum recall: a measurement-like weighted superposition of memories.
        weights = np.array([abs(e.get("signal", 0.0)) + 0.05 for e in pool], dtype=float)
        weights = weights / weights.sum()
        chosen_idx = int(np.searchsorted(np.cumsum(weights), secrets.randbelow(10**12) / 10**12, side="right"))
        chosen = pool[min(chosen_idx, len(pool) - 1)]
        return QuantumState.from_dict(chosen["state"])


@dataclass
class QuantumOrganism:
    name: str
    role: str
    state: QuantumState
    memory: QuantumMemory = field(default_factory=QuantumMemory)
    consciousness: float = 0.0
    coherence: float = 0.0
    entropy: float = 0.0
    qualia: str = ""
    intended_direction: Optional[str] = None
    last_decision: str = "None"
    last_tunnel_prob: float = 0.0
    last_barrier: float = 0.0

    def update_metrics(self, operator: ConsciousnessOperator, decoh: DecoherenceMonitor):
        self.consciousness = operator.expectation(self.state)
        metrics = decoh.analyze(self.state)
        self.coherence = metrics["coherence"]
        self.entropy = metrics["entropy"]
        self.qualia = self._generate_qualia()
        return metrics

    def _generate_qualia(self) -> str:
        probs = self.state.probabilities()
        top = int(np.argmax(probs))
        if top == 0:
            return "clarity"
        if top == 1:
            return "alarm"
        if top == 2:
            return "equilibrium"
        return "ambiguity"

    def intended_basis(self) -> Optional[str]:
        # Intentionality is a bias to collapse toward a target direction.
        if self.role == "SNIPER" and self.coherence > 0.45:
            return "Bullish" if np.real(self.state.psi[0]) >= np.real(self.state.psi[1]) else "Bearish"
        if self.role == "SCALPER":
            return "Neutral"
        if self.role == "FLOW":
            return "Bullish" if self.consciousness > 0.75 else "Uncertain"
        return self.intended_direction


class QuantumHive:
    def __init__(self):
        init_db()
        self.lock = threading.Lock()
        self.generation = 1
        self.operator = ConsciousnessOperator.default(0.5)
        self.decoh = DecoherenceMonitor()
        self.decider = QuantumDecisionEngine()
        self.entanglement = EntanglementField(4)
        self.symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
        self.market_state = {s: self._synthetic_market(s) for s in self.symbols}
        self.organisms: List[QuantumOrganism] = [
            QuantumOrganism("Aether", "SNIPER", QuantumState.random(1)),
            QuantumOrganism("Pulse", "SCALPER", QuantumState.random(2)),
            QuantumOrganism("Flux", "FLOW", QuantumState.random(3)),
            QuantumOrganism("Vector", "MEMORY", QuantumState.random(4)),
        ]
        self.timeline = []
        self.last_cycle = "initialized"
        self.collective_awareness = 0.0
        self.collective_coherence = 0.0
        self.mean_entropy = 0.0
        self.mean_consciousness = 0.0
        self.mutation_rate = 0.08
        self._load_state()
        self._bootstrap_logs()

    def _synthetic_market(self, symbol: str):
        # Stable offline series for dashboard use.
        seed = abs(hash(symbol)) % (2**32)
        rng = np.random.default_rng(seed)
        n = 96
        base = 100 + np.cumsum(rng.normal(0, 0.35, n)) + np.sin(np.linspace(0, 6, n)) * 2.2
        close = base + np.linspace(0, rng.normal(0, 3.0), n)
        high = close + np.abs(rng.normal(0.45, 0.15, n))
        low = close - np.abs(rng.normal(0.45, 0.15, n))
        open_ = np.r_[close[0], close[:-1]]
        vol = np.abs(rng.normal(900, 180, n))
        t = pd.date_range(end=pd.Timestamp.utcnow(), periods=n, freq="5min")
        return pd.DataFrame({"ts": t, "open": open_, "high": high, "low": low, "close": close, "volume": vol})

    def _bootstrap_logs(self):
        for sym in self.symbols:
            snap = self.market_state[sym].iloc[-1]
            db_insert("market_snapshots", {
                "ts": now_utc(), "symbol": sym, "price": float(snap["close"]),
                "volatility": float((self.market_state[sym]["close"].pct_change().rolling(12).std().iloc[-1] or 0.0)),
                "noise": float(np.std(self.market_state[sym]["close"].pct_change().fillna(0).tail(24))),
                "barrier": float(np.std(self.market_state[sym]["close"].tail(24)) + 0.5),
            })

    def _load_state(self):
        try:
            if STATE_PATH.exists():
                data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                self.generation = int(data.get("generation", self.generation))
                self.collective_awareness = float(data.get("collective_awareness", self.collective_awareness))
                self.collective_coherence = float(data.get("collective_coherence", self.collective_coherence))
                self.mean_entropy = float(data.get("mean_entropy", self.mean_entropy))
                self.mean_consciousness = float(data.get("mean_consciousness", self.mean_consciousness))
                self.mutation_rate = float(data.get("mutation_rate", self.mutation_rate))
                org_state = data.get("organisms", [])
                by_name = {o.name: o for o in self.organisms}
                for odata in org_state:
                    name = odata.get("name")
                    if name in by_name:
                        by_name[name].state = QuantumState.from_dict(odata["state"])
                        by_name[name].consciousness = float(odata.get("consciousness", by_name[name].consciousness))
                        by_name[name].coherence = float(odata.get("coherence", by_name[name].coherence))
                        by_name[name].entropy = float(odata.get("entropy", by_name[name].entropy))
                        by_name[name].qualia = odata.get("qualia", by_name[name].qualia)
        except Exception:
            pass

    def save_state(self):
        data = {
            "generation": self.generation,
            "collective_awareness": self.collective_awareness,
            "collective_coherence": self.collective_coherence,
            "mean_entropy": self.mean_entropy,
            "mean_consciousness": self.mean_consciousness,
            "mutation_rate": self.mutation_rate,
            "organisms": [
                {
                    "name": o.name,
                    "role": o.role,
                    "state": o.state.to_dict(),
                    "consciousness": o.consciousness,
                    "coherence": o.coherence,
                    "entropy": o.entropy,
                    "qualia": o.qualia,
                    "last_decision": o.last_decision,
                    "last_tunnel_prob": o.last_tunnel_prob,
                    "last_barrier": o.last_barrier,
                    "memory": o.memory.episodes,
                }
                for o in self.organisms
            ],
            "saved_at": now_utc(),
        }
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, STATE_PATH)

    def market_coherence(self) -> float:
        vals = []
        for sym, df in self.market_state.items():
            rets = df["close"].pct_change().dropna()
            if len(rets) < 6:
                continue
            # low realized noise => higher market coherence
            coh = 1.0 / (1.0 + float(rets.tail(18).std() * 80.0))
            vals.append(clamp(coh, 0.0, 1.0))
        return float(np.mean(vals) if vals else 0.5)

    def update_operator(self):
        self.operator = ConsciousnessOperator.default(self.market_coherence())

    def _market_barrier(self, symbol: str) -> Tuple[float, float, float]:
        df = self.market_state[symbol]
        close = df["close"]
        vol = float(close.pct_change().rolling(12).std().iloc[-1] or 0.01)
        noise = float(np.std(close.pct_change().fillna(0).tail(24)))
        barrier = float(abs(close.iloc[-1] - close.tail(24).mean()) / (close.tail(24).std() + 1e-9) + 0.5)
        return vol, noise, barrier

    def evolve_market(self):
        # Update synthetic market snapshots with mild stochastic drift.
        for sym in self.symbols:
            df = self.market_state[sym]
            last = float(df["close"].iloc[-1])
            drift = secrets.randbelow(10**6) / 10**6 - 0.5
            drift = drift * 0.25
            shock = np.random.default_rng().normal(0, 0.35)
            new = max(0.1, last + drift + shock)
            ts = pd.Timestamp.utcnow()
            row = pd.DataFrame({"ts": [ts], "open": [last], "high": [max(last, new) + abs(shock) * 0.3], "low": [min(last, new) - abs(shock) * 0.3], "close": [new], "volume": [max(1.0, np.random.default_rng().normal(1000, 100))]})
            self.market_state[sym] = pd.concat([df.iloc[-119:], row], ignore_index=True)
            vol, noise, barrier = self._market_barrier(sym)
            db_insert("market_snapshots", {
                "ts": now_utc(), "symbol": sym, "price": new, "volatility": vol, "noise": noise, "barrier": barrier,
            })

    def cycle(self):
        with self.lock:
            self.evolve_market()
            self.update_operator()
            states = [o.state for o in self.organisms]
            self.entanglement.update_links(states)
            ent_strength = self.entanglement.collective_entanglement()
            market_coh = self.market_coherence()
            results = []
            for idx, org in enumerate(self.organisms):
                symbol = self.symbols[idx % len(self.symbols)]
                df = self.market_state[symbol]
                close = df["close"].values
                momentum = float((close[-1] - close[-6]) / (close[-6] + 1e-12))
                barrier_distance = float(abs(close[-1] - close[-24:].mean()) / (close[-24:].std() + 1e-12) + 0.4)
                vol, noise, barrier = self._market_barrier(symbol)
                tunnel_prob = TunnelingProbability.market_barrier_prob(momentum=momentum, volatility=max(vol, 1e-4), barrier_distance=barrier_distance)
                org.last_tunnel_prob = tunnel_prob
                org.last_barrier = barrier_distance

                # Decoherence from market noise, recoherence from meditation-like activity
                if noise > 0.008:
                    org.state = self.decoh.recohere(org.state, strength=0.15)
                if market_coh > 0.65 and ent_strength > 0.15:
                    org.state = self.decoh.recohere(org.state, strength=0.24)

                # Intentionality biases measurement without making it deterministic
                intended = org.intended_basis()
                measured = self.decider.decide(org.state, intended=intended)
                org.last_decision = measured["decision"]
                org.state = measured["collapsed_state"]

                # Non-local memory store and recall interplay
                if org.last_decision in ("Bullish", "Bearish"):
                    org.memory.store(org.state, tag=org.last_decision, signal=momentum)
                recall = org.memory.recall(tag=org.last_decision)
                if recall is not None and org.coherence < 0.45:
                    # memory as non-local quantum influence
                    org.state = QuantumState(normalize_state(0.7 * org.state.psi + 0.3 * recall.psi))

                # Update consciousness / qualia / metrics
                m = org.update_metrics(self.operator, self.decoh)
                org.consciousness = clamp(org.consciousness, -2.0, 3.0)
                # Re-interference with entanglement field - measurement on one affects others
                self.entanglement.propagate_measurement(idx, measured["outcome"], [o.state for o in self.organisms], influence=0.08 + 0.08 * ent_strength)

                results.append({
                    "org": org.name,
                    "symbol": symbol,
                    "market_coh": market_coh,
                    "ent_strength": ent_strength,
                    "decision": org.last_decision,
                    "consciousness": org.consciousness,
                    "coherence": org.coherence,
                    "entropy": org.entropy,
                    "tunnel": tunnel_prob,
                    "barrier": barrier_distance,
                })

                db_insert("quantum_log", {
                    "ts": now_utc(),
                    "organism": org.name,
                    "event": "measurement",
                    "state_json": json.dumps(org.state.to_dict(), ensure_ascii=False),
                    "consciousness": org.consciousness,
                    "coherence": org.coherence,
                    "entropy": org.entropy,
                    "decision": org.last_decision,
                    "barrier": barrier_distance,
                    "tunnel_prob": tunnel_prob,
                    "extra": json.dumps({"symbol": symbol, "qualia": org.qualia, "entanglement": ent_strength}, ensure_ascii=False),
                })

            self.collective_awareness = float(np.mean([o.consciousness for o in self.organisms]))
            self.collective_coherence = float(np.mean([o.coherence for o in self.organisms]))
            self.mean_entropy = float(np.mean([o.entropy for o in self.organisms]))
            self.mean_consciousness = self.collective_awareness
            # Evolution-like mutation/re-coherence cycle
            self.generation += 1
            if self.collective_coherence < 0.35:
                self.mutation_rate = clamp(self.mutation_rate + 0.01, 0.02, 0.2)
            else:
                self.mutation_rate = clamp(self.mutation_rate * 0.995, 0.02, 0.2)
            self._maybe_mutate_states()
            self._record_evolution(note=f"ent={ent_strength:.3f};mc={market_coh:.3f}")
            self.save_state()
            self.last_cycle = f"cycle={self.generation} | awareness={self.collective_awareness:.3f} | coherence={self.collective_coherence:.3f} | ent={ent_strength:.3f}"
            self.timeline.append({"ts": now_utc(), "awareness": self.collective_awareness, "coherence": self.collective_coherence, "entropy": self.mean_entropy, "entanglement": ent_strength})
            self.timeline = self.timeline[-300:]
            return results

    def _maybe_mutate_states(self):
        # A gentle unitary perturbation: no deterministic formulas, but valid quantum evolution.
        for o in self.organisms:
            if secrets.randbelow(1000) / 1000.0 < self.mutation_rate:
                theta = np.random.default_rng().normal(0, 0.08)
                phi = np.random.default_rng().uniform(-np.pi, np.pi)
                U = np.eye(4, dtype=np.complex128)
                c, s = np.cos(theta), 1j * np.sin(theta) * np.exp(1j * phi)
                # Mix Bullish/Bearish and Neutral/Uncertain sectors with a unitary-like rotation
                U[0, 0] = c
                U[0, 1] = s
                U[1, 0] = np.conj(s)
                U[1, 1] = c
                U[2, 2] = c
                U[2, 3] = -s
                U[3, 2] = -np.conj(s)
                U[3, 3] = c
                o.state = o.state.apply_unitary(U)

    def _record_evolution(self, note=""):
        db_insert("evolution_metrics", {
            "ts": now_utc(),
            "generation": self.generation,
            "collective_awareness": self.collective_awareness,
            "collective_coherence": self.collective_coherence,
            "mean_entropy": self.mean_entropy,
            "mean_consciousness": self.mean_consciousness,
            "mutation_rate": self.mutation_rate,
            "note": note,
        })

    def organism_table(self):
        rows = []
        for o in self.organisms:
            rows.append({
                "name": o.name,
                "role": o.role,
                "consciousness": o.consciousness,
                "coherence": o.coherence,
                "entropy": o.entropy,
                "decision": o.last_decision,
                "qualia": o.qualia,
                "tunnel": o.last_tunnel_prob,
                "barrier": o.last_barrier,
                "amps": o.state.probabilities().tolist(),
            })
        return pd.DataFrame(rows)

    def bloch_points(self):
        pts = []
        for o in self.organisms:
            x, y, z = o.state.bloch_like()
            pts.append((o.name, x, y, z))
        return pts

    def network_edges(self):
        edges = []
        n = len(self.organisms)
        for i in range(n):
            for j in range(i + 1, n):
                w = float(self.entanglement.pair_strength[i, j])
                if w > 0:
                    edges.append((self.organisms[i].name, self.organisms[j].name, w))
        return edges


# ----------------------------------------------------------------------------
# Figure builders
# ----------------------------------------------------------------------------
def make_gauge(title, value, color):
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=float(value) * 100.0,
        number={"suffix": "%", "font": {"size": 28, "color": TXT}},
        delta={"reference": 50, "increasing": {"color": UP}, "decreasing": {"color": DN}},
        title={"text": rtl_text(title), "font": {"size": 16, "color": GOLD}},
        gauge={
            "axis": {"range": [None, 100], "tickwidth": 1, "tickcolor": "#9cb4d4"},
            "bar": {"color": color},
            "bgcolor": "rgba(0,0,0,0)",
            "steps": [
                {"range": [0, 35], "color": "#12233d"},
                {"range": [35, 70], "color": "#182a48"},
                {"range": [70, 100], "color": "#1f355b"},
            ],
            "threshold": {"line": {"color": GOLD, "width": 4}, "thickness": 0.8, "value": 90},
        },
    ))
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(8,17,31,0.9)", height=250, margin=dict(l=15, r=15, t=40, b=15), font=dict(color=TXT))
    return fig


def make_dashboard_figures(hive: QuantumHive):
    evo = load_evolution(220)
    logs = load_logs(200)
    market = load_market(200)
    timeline = pd.DataFrame(hive.timeline)
    if timeline.empty:
        timeline = pd.DataFrame({"ts": [now_utc()], "awareness": [0.5], "coherence": [0.5], "entropy": [1.0], "entanglement": [0.2]})

    # 1) Effective Bloch sphere / 3D state projections
    pts = hive.bloch_points()
    fig1 = go.Figure()
    for name, x, y, z in pts:
        fig1.add_trace(go.Scatter3d(x=[x], y=[y], z=[z], mode="markers+text", text=[rtl_text(name)], textposition="top center", marker=dict(size=9, color=GOLD, line=dict(color=CYAN, width=1.5))))
    # unit sphere wireframe
    u = np.linspace(0, 2*np.pi, 24)
    v = np.linspace(0, np.pi, 18)
    xs = np.outer(np.cos(u), np.sin(v))
    ys = np.outer(np.sin(u), np.sin(v))
    zs = np.outer(np.ones_like(u), np.cos(v))
    fig1.add_trace(go.Surface(x=xs, y=ys, z=zs, showscale=False, opacity=0.15, colorscale=[[0, "#123"], [1, "#468"]], hoverinfo="skip"))
    fig_base(fig1, "کرهٔ بلاخِ مؤثر — بردار حالت کوانتومی", height=500)
    
    # --- FIX APPLIED HERE: Changed 'bgcolor' to 'backgroundcolor' for 3D axes ---
    fig1.update_layout(scene=dict(
        xaxis=dict(title=rtl_text("X"), range=[-1.1, 1.1], backgroundcolor="rgba(0,0,0,0)"), 
        yaxis=dict(title=rtl_text("Y"), range=[-1.1, 1.1], backgroundcolor="rgba(0,0,0,0)"), 
        zaxis=dict(title=rtl_text("Z"), range=[-1.1, 1.1], backgroundcolor="rgba(0,0,0,0)"), 
        bgcolor="rgba(0,0,0,0)"
    ))

    # 2) Consciousness / coherence / entropy over time
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=timeline["ts"], y=timeline["awareness"], mode="lines+markers", name=rtl_text("آگاهی"), line=dict(color=UP, width=3)))
    fig2.add_trace(go.Scatter(x=timeline["ts"], y=timeline["coherence"], mode="lines", name=rtl_text("همدوسی"), line=dict(color=CYAN, width=2, dash="dot")))
    fig2.add_trace(go.Scatter(x=timeline["ts"], y=timeline["entropy"], mode="lines", name=rtl_text("آنتروپی"), line=dict(color=ORANGE, width=2)))
    fig_base(fig2, "تکامل آگاهی، همدوسی و آنتروپی")
    fig2.update_yaxes(range=[0, max(2.0, float(timeline[["awareness","coherence","entropy"]].max().max()) + 0.1)])

    # 3) Entanglement network graph
    edges = hive.network_edges()
    fig3 = go.Figure()
    pos = {
        "Aether": (-1.0, 0.9),
        "Pulse": (1.0, 0.9),
        "Flux": (-1.0, -0.9),
        "Vector": (1.0, -0.9),
    }
    for a, b, w in edges:
        x0, y0 = pos[a]
        x1, y1 = pos[b]
        fig3.add_trace(go.Scatter(x=[x0, x1], y=[y0, y1], mode="lines", line=dict(color=f"rgba(20,217,255,{0.2 + 0.75*w})", width=1 + 8*w), hoverinfo="skip", showlegend=False))
    for name, (x, y) in pos.items():
        org = next(o for o in hive.organisms if o.name == name)
        fig3.add_trace(go.Scatter(x=[x], y=[y], mode="markers+text", text=[f"{rtl_text(name)}<br>{org.qualia}"], textposition="top center", marker=dict(size=20, color=GOLD if org.consciousness >= 0 else DN, line=dict(color=CYAN, width=2)), name=rtl_text(name)))
    fig_base(fig3, "شبکهٔ درهم‌تنیدگی بین ارگانیسم‌ها", height=430)
    fig3.update_xaxes(visible=False)
    fig3.update_yaxes(visible=False)
    fig3.update_layout(plot_bgcolor="rgba(8,17,31,0.9)")

    # 4) Decoherence timeline (from logs if available)
    if not logs.empty:
        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(x=logs["ts"], y=logs["coherence"], mode="lines", name=rtl_text("coherence"), line=dict(color=UP, width=2.5)))
        fig4.add_trace(go.Scatter(x=logs["ts"], y=logs["entropy"], mode="lines", name=rtl_text("entropy"), line=dict(color=DN, width=2)))
        fig4.add_trace(go.Scatter(x=logs["ts"], y=logs["tunnel_prob"], mode="lines", name=rtl_text("tunnel"), line=dict(color=GOLD, width=2, dash="dash")))
    else:
        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(x=timeline["ts"], y=timeline["coherence"], mode="lines", name=rtl_text("همدوسی"), line=dict(color=UP, width=2.5)))
        fig4.add_trace(go.Scatter(x=timeline["ts"], y=timeline["entropy"], mode="lines", name=rtl_text("آنتروپی"), line=dict(color=DN, width=2)))
    fig_base(fig4, "نمودار زمان‌مند واهمدوسی / بازهمدوسی", height=360)
    fig4.update_yaxes(range=[0, max(2.0, float(timeline[["coherence","entropy"]].max().max()) + 0.1)])

    # 5) Tunneling probability heatmap
    momentum_grid = np.linspace(-0.05, 0.05, 40)
    barrier_grid = np.linspace(0.15, 2.2, 40)
    Z = np.zeros((len(barrier_grid), len(momentum_grid)))
    for i, b in enumerate(barrier_grid):
        for j, m in enumerate(momentum_grid):
            Z[i, j] = TunnelingProbability.market_barrier_prob(momentum=m, volatility=0.012, barrier_distance=b)
    fig5 = go.Figure(data=go.Heatmap(z=Z, x=momentum_grid, y=barrier_grid, colorscale=[[0, "#070c12"], [0.35, "#123b8a"], [0.7, "#14d9ff"], [1, "#f5c542"]], colorbar=dict(title=rtl_text("P"))))
    fig_base(fig5, "نقشهٔ حرارتی احتمال تونل‌زنی", height=360)
    fig5.update_xaxes(title_text=rtl_text("Momentum"))
    fig5.update_yaxes(title_text=rtl_text("Barrier"))

    # 6) Quantum state amplitudes
    org = hive.organisms[0]
    amps = org.state.amplitudes
    fig6 = go.Figure()
    fig6.add_trace(go.Bar(x=[rtl_text(x) for x in BASIS_LABELS], y=np.abs(amps), marker_color=[GOLD, DN, CYAN, NEON], name=rtl_text("|ψ|")))
    fig6.add_trace(go.Scatter(x=[rtl_text(x) for x in BASIS_LABELS], y=np.angle(amps), mode="lines+markers", name=rtl_text("phase"), line=dict(color=UP, width=2)))
    fig_base(fig6, f"دامنه‌های حالت — {org.name}", height=360)

    # 7) Market snapshots / noise
    fig7 = go.Figure()
    if not market.empty:
        for sym in market["symbol"].unique()[:4]:
            sdf = market[market["symbol"] == sym]
            fig7.add_trace(go.Scatter(x=sdf["ts"], y=sdf["price"], mode="lines", name=rtl_text(sym), line=dict(width=2)))
    else:
        fig7.add_trace(go.Scatter(x=timeline["ts"], y=timeline["awareness"], mode="lines", name=rtl_text("market"), line=dict(width=2)))
    fig_base(fig7, "ردیاب بازار و نویز", height=360)

    # 8) Evolution metrics table-like chart
    fig8 = go.Figure()
    if not evo.empty:
        fig8.add_trace(go.Scatter(x=evo["ts"], y=evo["collective_awareness"], mode="lines", name=rtl_text("collective awareness"), line=dict(color=GOLD, width=2.5)))
        fig8.add_trace(go.Scatter(x=evo["ts"], y=evo["collective_coherence"], mode="lines", name=rtl_text("collective coherence"), line=dict(color=UP, width=2)))
        fig8.add_trace(go.Scatter(x=evo["ts"], y=evo["mutation_rate"], mode="lines", name=rtl_text("mutation rate"), line=dict(color=NEON, width=2, dash="dot")))
    else:
        fig8.add_trace(go.Scatter(x=timeline["ts"], y=timeline["awareness"], mode="lines", name=rtl_text("awareness"), line=dict(color=GOLD, width=2.5)))
    fig_base(fig8, "تکامل جمعی و نرخ جهش", height=360)

    # 9) Heatmap of organism basis probabilities
    probs = np.array([o.state.probabilities() for o in hive.organisms])
    fig9 = go.Figure(data=go.Heatmap(z=probs, x=[rtl_text(x) for x in BASIS_LABELS], y=[rtl_text(o.name) for o in hive.organisms], colorscale="Viridis", zmin=0, zmax=1))
    fig_base(fig9, "نقشهٔ حرارتی حالت پایهٔ ارگانیسم‌ها", height=360)

    return {
        "fig1": fig1, "fig2": fig2, "fig3": fig3, "fig4": fig4, "fig5": fig5,
        "fig6": fig6, "fig7": fig7, "fig8": fig8, "fig9": fig9,
    }


# ----------------------------------------------------------------------------
# Dash app
# ----------------------------------------------------------------------------
HIVE = QuantumHive()
external_stylesheets = [dbc.themes.CYBORG, "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;700;900&display=swap"]
app = dash.Dash(__name__, external_stylesheets=external_stylesheets, suppress_callback_exceptions=True)
server = app.server
app.title = APP_TITLE

app.index_string = f"""
<!DOCTYPE html>
<html lang=\"fa\" dir=\"rtl\">
    <head>
        {{%metas%}}
        <title>{APP_TITLE}</title>
        {{%favicon%}}
        {{%css%}}
        <style>
        :root {{ color-scheme: dark; }}
        body {{
            margin:0; padding:0;
            background:
                radial-gradient(circle at 20% 20%, rgba(20,217,255,.12), transparent 25%),
                radial-gradient(circle at 80% 10%, rgba(124,92,255,.14), transparent 24%),
                radial-gradient(circle at 50% 90%, rgba(245,197,66,.10), transparent 20%),
                linear-gradient(135deg, #050b16 0%, #08111f 50%, #050b16 100%);
            font-family: Vazirmatn, IRANSans, Segoe UI, sans-serif;
            color: #e9f1ff;
            overflow-x: hidden;
        }}
        * {{ scrollbar-width: thin; scrollbar-color: #3d527a #091220; }}
        ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
        ::-webkit-scrollbar-track {{ background: #091220; }}
        ::-webkit-scrollbar-thumb {{ background: linear-gradient(180deg, #7c5cff, #14d9ff); border-radius: 10px; }}
        .glass-card {{
            backdrop-filter: blur(18px);
            background: rgba(13, 20, 38, 0.70) !important;
            border: 1px solid rgba(124, 92, 255, 0.35) !important;
            box-shadow: 0 0 0 1px rgba(20,217,255,0.08), 0 10px 30px rgba(0,0,0,0.35), inset 0 0 25px rgba(20,217,255,0.05);
            border-radius: 18px !important;
        }}
        .neon-border {{
            box-shadow: 0 0 12px rgba(20,217,255,0.25), 0 0 24px rgba(124,92,255,0.12);
            border: 1px solid rgba(20,217,255,0.35) !important;
        }}
        .glow-title {{ text-shadow: 0 0 12px rgba(20,217,255,0.45), 0 0 24px rgba(124,92,255,0.22); }}
        .dash-tabs .nav-link {{ border-radius: 14px !important; margin: 0 4px; }}
        .btn {{ border-radius: 14px !important; }}
        .fade-in {{ animation: fadeIn .5s ease both; }}
        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(4px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        </style>
    </head>
    <body>
        {{%app_entry%}}
        <footer>
            {{%config%}}
            {{%scripts%}}
            {{%renderer%}}
        </footer>
    </body>
</html>
"""


def stat_card(title, value, color=GOLD, sub=""):
    return dbc.Card(
        dbc.CardBody([
            html.Div(rtl_text(title), style={"color": MUT, "fontSize": 12, "marginBottom": 6}),
            html.Div(str(value), style={"color": color, "fontSize": 24, "fontWeight": 800, "lineHeight": 1.1, "textShadow": f"0 0 12px {color}55"}),
            html.Div(rtl_text(sub), style={"color": MUT, "fontSize": 11, "marginTop": 6}),
        ]),
        className="glass-card neon-border fade-in",
        style={"height": "100%"},
    )


def organism_cards(hive: QuantumHive):
    cards = []
    for o in hive.organisms:
        cards.append(dbc.Col(stat_card(
            f"{o.name} • {o.role}",
            f"{o.consciousness:.3f}",
            color=UP if o.consciousness >= 0 else DN,
            sub=f"{rtl_text('coherence')}={o.coherence:.3f} | {rtl_text('entropy')}={o.entropy:.3f} | {rtl_text('qualia')}={o.qualia}"
        ), md=3))
    return dbc.Row(cards, className="g-2")


app.layout = html.Div([
    dbc.Container(fluid=True, children=[
        dbc.Card(dbc.CardBody(dbc.Row([
            dbc.Col(html.Div([
                html.H2(rtl_text(APP_TITLE), className="glow-title", style={"margin": 0, "color": GOLD, "fontWeight": 900}),
                html.Div(rtl_text("سیستم کوانتومیِ چند-ارگانیسمی با حالت برداری، درهم‌تنیدگی، واهمدوسی و اندازه‌گیری واقعی بر پایهٔ مکانیک کوانتومی"), style={"color": MUT, "marginTop": 6}),
            ]), md=8),
            dbc.Col(html.Div(id="pulse", className="text-end", style={"color": NEON, "fontFamily": "monospace", "fontSize": 13}), md=4),
        ], align="center")), className="glass-card neon-border mb-3 mt-2"),

        dcc.Tabs(id="tabs", value="live", parent_className="dash-tabs", className="dash-tabs", children=[
            dcc.Tab(label=rtl_text("نمای زندهٔ ارگانیسم‌ها"), value="live", style={"background": CARD_SOLID, "color": TXT}, selected_style={"background": LINE, "color": GOLD, "fontWeight": 700}),
            dcc.Tab(label=rtl_text("آگاهی و آمار کوانتومی"), value="quantum", style={"background": CARD_SOLID, "color": TXT}, selected_style={"background": LINE, "color": GOLD, "fontWeight": 700}),
            dcc.Tab(label=rtl_text("درهم‌تنیدگی و شبکه"), value="network", style={"background": CARD_SOLID, "color": TXT}, selected_style={"background": LINE, "color": GOLD, "fontWeight": 700}),
            dcc.Tab(label=rtl_text("واهمدوسی و تونل‌زنی"), value="physics", style={"background": CARD_SOLID, "color": TXT}, selected_style={"background": LINE, "color": GOLD, "fontWeight": 700}),
            dcc.Tab(label=rtl_text("تاریخچه و تکامل"), value="evolution", style={"background": CARD_SOLID, "color": TXT}, selected_style={"background": LINE, "color": GOLD, "fontWeight": 700}),
        ]),
        html.Div(id="content", className="mt-3"),
        dcc.Interval(id="life", interval=12_000, n_intervals=0),
        html.Div(style={"height": "24px"}),
    ])
], style={"minHeight": "100vh"})


def render_live_tab():
    figs = make_dashboard_figures(HIVE)
    row1 = dbc.Row([
        dbc.Col(stat_card("آگاهی جمعی", f"{HIVE.collective_awareness:.3f}", color=GOLD, sub="میانگین انتظار اندازه‌گیری"), md=3),
        dbc.Col(stat_card("همدوسی جمعی", f"{HIVE.collective_coherence:.3f}", color=UP, sub="مؤلفه‌های غیردیagonal"), md=3),
        dbc.Col(stat_card("آنتروپی متوسط", f"{HIVE.mean_entropy:.3f}", color=ORANGE, sub="Von Neumann entropy"), md=3),
        dbc.Col(stat_card("نسل", f"{HIVE.generation}", color=CYAN, sub="تکامل در هر چرخه"), md=3),
    ], className="g-2")
    row2 = organism_cards(HIVE)
    row3 = dbc.Row([
        dbc.Col(dcc.Graph(figure=figs["fig1"]), md=6),
        dbc.Col(dcc.Graph(figure=figs["fig2"]), md=6),
    ], className="g-2 mt-1")
    row4 = dbc.Row([
        dbc.Col(dcc.Graph(figure=figs["fig3"]), md=6),
        dbc.Col(dcc.Graph(figure=figs["fig4"]), md=6),
    ], className="g-2 mt-1")
    return html.Div([row1, html.Div(className="mt-2"), row2, html.Div(className="mt-2"), row3, row4], className="fade-in")


def render_quantum_tab():
    figs = make_dashboard_figures(HIVE)
    gauges = dbc.Row([
        dbc.Col(dcc.Graph(figure=make_gauge("آگاهی جمعی", HIVE.collective_awareness, GOLD)), md=4),
        dbc.Col(dcc.Graph(figure=make_gauge("همدوسی", HIVE.collective_coherence, UP)), md=4),
        dbc.Col(dcc.Graph(figure=make_gauge("میانگین آنتروپی", min(HIVE.mean_entropy / 2.0, 1.0), CYAN)), md=4),
    ], className="g-2")
    return html.Div([
        gauges,
        dbc.Row([
            dbc.Col(dcc.Graph(figure=figs["fig6"]), md=6),
            dbc.Col(dcc.Graph(figure=figs["fig9"]), md=6),
        ], className="g-2 mt-1"),
    ], className="fade-in")


def render_network_tab():
    figs = make_dashboard_figures(HIVE)
    return html.Div([
        dbc.Row([
            dbc.Col(dcc.Graph(figure=figs["fig3"]), md=8),
            dbc.Col(html.Div([
                stat_card("درهم‌تنیدگی جمعی", f"{HIVE.entanglement.collective_entanglement():.3f}", color=CYAN, sub="میانگین strength جفتی"),
                html.Div(className="mt-2"),
                stat_card("میدان ارتباط", f"{len(HIVE.network_edges())} لینک", color=GOLD, sub="پیوندهای غیرصفر"),
            ]), md=4),
        ], className="g-2"),
        dbc.Row([
            dbc.Col(dcc.Graph(figure=figs["fig7"]), md=6),
            dbc.Col(dcc.Graph(figure=figs["fig8"]), md=6),
        ], className="g-2 mt-1"),
    ], className="fade-in")


def render_physics_tab():
    figs = make_dashboard_figures(HIVE)
    return html.Div([
        dbc.Row([
            dbc.Col(dcc.Graph(figure=figs["fig4"]), md=6),
            dbc.Col(dcc.Graph(figure=figs["fig5"]), md=6),
        ], className="g-2"),
        dbc.Row([
            dbc.Col(dcc.Graph(figure=figs["fig1"]), md=6),
            dbc.Col(dcc.Graph(figure=figs["fig2"]), md=6),
        ], className="g-2 mt-1"),
    ], className="fade-in")


def render_evolution_tab():
    figs = make_dashboard_figures(HIVE)
    return html.Div([
        dbc.Row([
            dbc.Col(dcc.Graph(figure=figs["fig8"]), md=6),
            dbc.Col(dcc.Graph(figure=figs["fig7"]), md=6),
        ], className="g-2"),
        html.Div(className="mt-2"),
        dbc.Row([
            dbc.Col(dcc.Graph(figure=figs["fig9"]), md=6),
            dbc.Col(dcc.Graph(figure=figs["fig6"]), md=6),
        ], className="g-2 mt-1"),
    ], className="fade-in")


@app.callback(Output("content", "children"), Output("pulse", "children"), Input("tabs", "value"), Input("life", "n_intervals"))
def update_content(tab, _):
    try:
        HIVE.cycle()
        if tab == "live":
            content = render_live_tab()
        elif tab == "quantum":
            content = render_quantum_tab()
        elif tab == "network":
            content = render_network_tab()
        elif tab == "physics":
            content = render_physics_tab()
        elif tab == "evolution":
            content = render_evolution_tab()
        else:
            content = render_live_tab()
        pulse = f"{HIVE.last_cycle} | {now_utc()}"
        return content, pulse
    except Exception as e:
        traceback.print_exc()
        return dbc.Alert(str(e), color="danger"), f"error: {e}"


# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------
def main():
    print(f"Launching {APP_TITLE}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8050")), debug=False)


if __name__ == "__main__":
    main()