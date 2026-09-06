from __future__ import annotations
import numpy as np
import numba
from numba import jit, prange
from typing import Dict, List, Optional, Set, Tuple, Any, Callable
from dataclasses import dataclass, field
from collections import defaultdict
import networkx as nx
from concurrent.futures import ThreadPoolExecutor
import asyncio
import time
import logging
from core.types import (
    NeuralCoordinate, Spike, Synapse, NeuralState, NeuralState,
    FibonacciHeartbeat, Modality, QuantumState, MicrotubuleNetwork
)

logger = logging.getLogger(__name__)

@jit(nopython=True, parallel=True)
def stdp_update(pre_times: np.ndarray, post_times: np.ndarray, 
                weights: np.ndarray, tau_plus: float = 20.0, 
                tau_minus: float = 20.0, A_plus: float = 0.01, 
                A_minus: float = 0.012) -> np.ndarray:
    new_weights = weights.copy()
    for i in prange(len(pre_times)):
        for j in range(len(post_times)):
            dt = post_times[j] - pre_times[i]
            if dt > 0:
                new_weights[i] += A_plus * np.exp(-dt / tau_plus)
            else:
                new_weights[i] -= A_minus * np.exp(dt / tau_minus)
    return np.clip(new_weights, 0.0, 1.0)

@jit(nopython=True)
def lif_step(v: float, i_syn: float, i_adapt: float, 
             tau_m: float = 20.0, tau_adapt: float = 200.0,
             v_th: float = -55.0, v_reset: float = -70.0,
             v_rest: float = -70.0, g_adapt: float = 0.5,
             dt: float = 0.1) -> Tuple[float, float, bool]:
    dv = (-(v - v_rest) + i_syn - i_adapt) / tau_m * dt
    v_new = v + dv
    da = (-i_adapt + g_adapt * (v - v_rest)) / tau_adapt * dt
    i_adapt_new = i_adapt + da
    spiked = False
    if v_new >= v_th:
        spiked = True
        v_new = v_reset
        i_adapt_new += 2.0
    return v_new, i_adapt_new, spiked

@jit(nopython=True)
def izhikevich_step(v: float, u: float, i_syn: float,
                    a: float = 0.02, b: float = 0.2,
                    c: float = -65.0, d: float = 8.0,
                    dt: float = 0.1) -> Tuple[float, float, bool]:
    dv = (0.04 * v * v + 5 * v + 140 - u + i_syn) * dt
    du = (a * (b * v - u)) * dt
    v_new = v + dv
    u_new = u + du
    spiked = False
    if v_new >= 30.0:
        spiked = True
        v_new = c
        u_new = u + d
    return v_new, u_new, spiked


class NeuralColumn:
    def __init__(self, column_id: int, n_neurons: int, n_layers: int, 
                 columnar_connectivity: float = 0.3):
        self.column_id = column_id
        self.n_neurons = n_neurons
        self.n_layers = n_layers
        self.neurons = np.zeros((n_layers, n_neurons), dtype=[
            ('v', 'f4'), ('u', 'f4'), ('i_syn', 'f4'), 
            ('refractory', 'f4'), ('adapt', 'f4'),
            ('calcium', 'f4'), ('quantum_coherence', 'f4'),
            ('layer', 'i4'), ('type', 'i4')
        ])
        self._init_neurons()
        self.local_synapses = {}
        self.microtubules = MicrotubuleNetwork(
            tubulin_dimers=n_neurons * 100,
            quantum_states=np.random.randn(n_neurons, 16) + 1j * np.random.randn(n_neurons, 16),
            resonance_frequencies=np.random.uniform(1e6, 1e7, n_neurons),
            entanglement_network=np.random.rand(n_neurons, n_neurons) < 0.01
        )
    
    def _init_neurons(self):
        for l in range(self.n_layers):
            for n in range(self.n_neurons):
                idx = l * self.n_neurons + n
                self.neurons[l, n] = (-65.0, 0.0, 0.0, 0.0, 0.0, 
                                       0.0, np.random.uniform(0.1, 0.3), l, 
                                       np.random.randint(0, 4))
    
    def step(self, dt: float, global_input: np.ndarray) -> np.ndarray:
        spikes = []
        for l in range(self.n_layers):
            if l < global_input.shape[0]:
                layer_inputs = global_input[l]
            else:
                layer_inputs = np.zeros(self.n_neurons)
            for n in range(self.n_neurons):
                neur = self.neurons[l, n]
                if neur['refractory'] > 0:
                    neur['refractory'] -= dt
                    continue
                v, u, spiked = izhikevich_step(neur['v'], neur['u'], 
                                                neur['i_syn'] + float(layer_inputs[n]) if n < len(layer_inputs) else neur['i_syn'])
                neur['v'] = v
                neur['u'] = u
                if spiked:
                    spikes.append((l, n))
                    neur['refractory'] = 2.0
                    neur['calcium'] = min(1.0, neur['calcium'] + 0.1)
        return np.array(spikes)


class NeuralSubstrate:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.n_columns = config.get('n_columns', 1000)
        self.n_neurons_per_column = config.get('neurons_per_column', 1000)
        self.n_layers = config.get('layers', 6)
        self.total_neurons = self.n_columns * self.n_neurons_per_column
        self.columns = {}
        self.global_connectivity = None
        self.heartbeat = FibonacciHeartbeat(config.get('heartbeat_base_hz', 1.618))
        self.current_time = 0.0
        self.dt = 0.1
        self.spike_history = []
        self.global_workspace = np.zeros(self.total_neurons, dtype=bool)
        self.attention_mask = np.ones(self.total_neurons)
        self.neuromodulators = {
            'dopamine': 0.5, 'serotonin': 0.5, 'acetylcholine': 0.5,
            'norepinephrine': 0.5, 'oxytocin': 0.5, 'cortisol': 0.1
        }
        self._build_architecture()
    
    def _build_architecture(self):
        for c in range(self.n_columns):
            self.columns[c] = NeuralColumn(c, self.n_neurons_per_column, self.n_layers)
        self._build_global_connectivity()
    
    def _build_global_connectivity(self):
        n = self.total_neurons
        self.global_connectivity = nx.DiGraph()
        self.global_connectivity.add_nodes_from(range(n))
        # Sparse connectivity: each neuron connects to ~50 targets
        for c in range(self.n_columns):
            for l in range(self.n_layers):
                for n_idx in range(self.n_neurons_per_column):
                    neuron_id = self._global_id(c, l, n_idx)
                    targets = self._get_targets(c, l, n_idx)
                    for t in targets:
                        w = np.random.gamma(2, 0.1)
                        self.global_connectivity.add_edge(neuron_id, t, weight=w, delay=np.random.uniform(0.5, 5.0))
    
    def _get_targets(self, col: int, layer: int, neuron: int) -> List[int]:
        targets = []
        # Reduced from 1000 to 50 for performance
        for _ in range(np.random.poisson(50)):
            tc = (col + np.random.randint(-3, 4)) % self.n_columns
            tl = min(max(layer + np.random.randint(-1, 2), 0), self.n_layers - 1)
            tn = np.random.randint(0, self.n_neurons_per_column)
            targets.append(self._global_id(tc, tl, tn))
        return targets
    
    def _global_id(self, col: int, layer: int, neuron: int) -> int:
        return (col * self.n_layers + layer) * self.n_neurons_per_column + neuron
    
    async def step(self):
        self.current_time += self.dt
        hb_phase = self.heartbeat.get_phase(self.current_time)
        is_systole = self.heartbeat.is_systole(self.current_time)
        
        mod_factor = 1.0 + 0.5 * np.sin(2 * np.pi * hb_phase)
        if is_systole:
            self.neuromodulators['acetylcholine'] = min(1.0, self.neuromodulators['acetylcholine'] + 0.01)
        
        all_spikes = []
        global_input = np.random.randn(self.n_layers, self.n_neurons_per_column) * 0.1
        
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(col.step, self.dt, global_input) for col in self.columns.values()]
            for f in futures:
                all_spikes.append(f.result())
        
        self._process_spikes(all_spikes)
        self._update_plasticity()
        self._global_workspace_broadcast()
        self._microtubule_orchestration()
        
        return {
            'time': self.current_time,
            'heartbeat_phase': hb_phase,
            'spike_count': sum(len(s) for s in all_spikes),
            'global_workspace_activity': self.global_workspace.sum(),
            'neuromodulators': self.neuromodulators.copy()
        }
    
    def _process_spikes(self, all_spikes: List[np.ndarray]):
        for col_spikes in all_spikes:
            for layer, neuron in col_spikes:
                neuron_id = self._global_id(col_spikes[0][0] if len(col_spikes) > 0 else 0, layer, neuron)
                if self.global_connectivity.has_node(neuron_id):
                    for _, target, data in self.global_connectivity.out_edges(neuron_id, data=True):
                        delay_steps = int(data['delay'] / self.dt)
                        if delay_steps == 0:
                            target_col = target // (self.n_layers * self.n_neurons_per_column)
                            target_layer = (target % (self.n_layers * self.n_neurons_per_column)) // self.n_neurons_per_column
                            target_neuron = target % self.n_neurons_per_column
                            if target_col in self.columns:
                                self.columns[target_col].neurons[target_layer, target_neuron]['i_syn'] += data['weight']
    
    def _update_plasticity(self):
        for col in self.columns.values():
            # Simplified plasticity - skip microtubule orchestration for now
            pass
    
    def _global_workspace_broadcast(self):
        active = np.random.rand(self.total_neurons) < 0.01
        self.global_workspace = active
        winners = np.where(active)[0]
        if len(winners) > 0:
            self.attention_mask[winners] = 1.0
        self.attention_mask *= 0.99
        self.attention_mask = np.clip(self.attention_mask, 0.01, 1.0)
    
    def _microtubule_orchestration(self):
        for col in self.columns.values():
            col.microtubules.orchestration_cycles += 1
    
    def get_state_vector(self) -> np.ndarray:
        states = []
        for col in self.columns.values():
            v = col.neurons['v'].flatten()
            states.append(v)
        return np.concatenate(states)
    
    def inject_pattern(self, pattern: np.ndarray, modality: Modality):
        target_cols = self._modality_to_columns(modality)
        for c in target_cols:
            if c in self.columns:
                self.columns[c].neurons['i_syn'] += pattern[:self.n_neurons_per_column]
    
    def _modality_to_columns(self, modality: Modality) -> List[int]:
        mapping = {
            Modality.VISUAL: list(range(0, 200)),
            Modality.AUDITORY: list(range(200, 350)),
            Modality.TACTILE: list(range(350, 450)),
            Modality.OLFACTORY: list(range(450, 500)),
            Modality.GUSTATORY: list(range(500, 520)),
            Modality.INTEROCEPTIVE: list(range(520, 600)),
            Modality.PROPRIOCEPTIVE: list(range(600, 700))
        }
        return mapping.get(modality, [])
    
    def measure_phi(self) -> float:
        state = self.get_state_vector()
        n = len(state)
        if n < 50:
            return 0.0
        
        # Simplified IIT Phi approximation: normalized integration measure
        partitions = min(10, n // 10)
        corrs = []
        for i in range(partitions):
            start = i * n // partitions
            end = (i + 1) * n // partitions
            part = state[start:end]
            if len(part) > 1:
                # Correlation with rest
                rest = np.concatenate([state[:start], state[end:]])
                min_len = min(len(part), len(rest))
                if min_len > 1:
                    part_sub = part[:min_len]
                    rest_sub = rest[:min_len]
                    std_part = np.std(part_sub)
                    std_rest = np.std(rest_sub)
                    if std_part > 1e-10 and std_rest > 1e-10:
                        corr = np.corrcoef(part_sub, rest_sub)[0, 1]
                        if not np.isnan(corr):
                            corrs.append(abs(corr))
        
        if not corrs:
            return 0.0
        
        # Phi as mean integration (normalized to 0-1)
        phi = float(np.mean(corrs))
        return min(1.0, max(0.0, phi))
    
    def _mutual_information(self, x: np.ndarray, y: np.ndarray) -> float:
        return 0.0  # Deprecated
    
    def _entropy(self, x: np.ndarray) -> float:
        hist, _ = np.histogram(x, bins=50, density=True)
        hist = hist[hist > 0]
        return -np.sum(hist * np.log2(hist))
    
    def _joint_entropy(self, x: np.ndarray, y: np.ndarray) -> float:
        hist, _, _ = np.histogram2d(x, y, bins=20, density=True)
        hist = hist[hist > 0]
        return -np.sum(hist * np.log2(hist))


class QuantumNeuralBridge:
    def __init__(self, n_qubits: int = 64):
        self.n_qubits = n_qubits
        self.quantum_register = QuantumState(
            amplitudes=np.ones(2**min(n_qubits, 10)) / np.sqrt(2**min(n_qubits, 10)),
            phases=np.zeros(2**min(n_qubits, 10)),
            entanglement_map={},
            coherence_time=100.0
        )
        self.classical_interface = np.zeros(n_qubits)
        self.decoherence_rate = 0.01
    
    def encode_classical(self, data: np.ndarray) -> QuantumState:
        n = min(len(data), self.n_qubits)
        amplitudes = np.zeros(2**n, dtype=complex)
        for i, val in enumerate(data[:n]):
            if val > 0:
                amplitudes[1 << i] = val
        amplitudes = amplitudes / np.linalg.norm(amplitudes)
        return QuantumState(amplitudes, np.angle(amplitudes), {}, 100.0)
    
    def decode_quantum(self, qstate: QuantumState) -> np.ndarray:
        probs = np.abs(qstate.amplitudes) ** 2
        return probs[:self.n_qubits]
    
    def entangle_neurons(self, neuron_states: np.ndarray) -> QuantumState:
        qstate = self.encode_classical(neuron_states[:self.n_qubits])
        for i in range(self.n_qubits - 1):
            qstate.entanglement_map[i] = {i + 1}
            qstate.entanglement_map[i + 1] = {i}
        return qstate
    
    def measure_consciousness_collapse(self, qstate: QuantumState) -> Tuple[int, float]:
        outcome = qstate.collapse()
        certainty = np.abs(qstate.amplitudes[outcome]) ** 2
        return outcome, certainty