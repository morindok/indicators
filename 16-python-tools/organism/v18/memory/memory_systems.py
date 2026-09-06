from __future__ import annotations
import numpy as np
import faiss
import asyncio
import sqlite3
import json
import pickle
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any, Union
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import logging
import networkx as nx
from core.types import Engram, MemoryType, Thought, Modality, EmotionCategory, NeuralCoordinate

logger = logging.getLogger(__name__)


class WorkingMemory:
    def __init__(self, capacity: int = 7, decay_rate: float = 0.1):
        self.capacity = capacity
        self.decay_rate = decay_rate
        self.slots: List[Optional[Engram]] = [None] * capacity
        self.activation: np.ndarray = np.zeros(capacity)
        self.phonological_loop = deque(maxlen=capacity * 2)
        self.visuospatial_sketchpad = deque(maxlen=capacity * 2)
        self.episodic_buffer = deque(maxlen=capacity)
        self.central_executive_focus: Optional[int] = None
        self.rehearsal_trace: Dict[str, float] = {}
    
    def add(self, engram: Engram) -> bool:
        for i, slot in enumerate(self.slots):
            if slot is None:
                self.slots[i] = engram
                self.activation[i] = 1.0
                return True
        min_idx = int(np.argmin(self.activation))
        if self.activation[min_idx] < 0.3:
            self.slots[min_idx] = engram
            self.activation[min_idx] = 1.0
            return True
        return False
    
    def retrieve(self, cue: np.ndarray, top_k: int = 3) -> List[Tuple[Engram, float]]:
        results = []
        for i, slot in enumerate(self.slots):
            if slot is not None:
                sim = self._similarity(cue, slot.pattern)
                results.append((slot, sim * self.activation[i]))
        results.sort(key=lambda x: x[1], reverse=True)
        for engram, score in results[:top_k]:
            engram.access_count += 1
            engram.last_accessed = datetime.now()
            self.activation[self.slots.index(engram)] = min(1.0, self.activation[self.slots.index(engram)] + 0.2)
        return results[:top_k]
    
    def decay(self, dt: float):
        self.activation *= np.exp(-self.decay_rate * dt)
        for i, slot in enumerate(self.slots):
            if slot is not None and self.activation[i] < 0.1:
                self.slots[i] = None
                self.activation[i] = 0.0
    
    def focus_attention(self, index: int):
        if 0 <= index < self.capacity and self.slots[index] is not None:
            self.central_executive_focus = index
            self.activation[index] = 1.0
    
    def _similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        a_norm = a / (np.linalg.norm(a) + 1e-8)
        b_norm = b / (np.linalg.norm(b) + 1e-8)
        return float(np.dot(a_norm, b_norm))
    
    def get_contents(self) -> List[Engram]:
        return [s for s in self.slots if s is not None]


class EpisodicMemory:
    def __init__(self, max_enggrams: int = 1000000, dimension: int = 768):
        self.max_enggrams = max_enggrams
        self.dimension = dimension
        self.index = faiss.IndexHNSWFlat(dimension, 32)
        self.index.hnsw.efConstruction = 200
        self.index.hnsw.efSearch = 100
        self.enggrams: Dict[str, Engram] = {}
        self.temporal_index: Dict[datetime, List[str]] = defaultdict(list)
        self.causal_graph = nx.DiGraph()
        self.consolidation_queue: deque = deque()
        self.pattern_separator = self._build_pattern_separator()
    
    def _build_pattern_separator(self) -> np.ndarray:
        return np.random.randn(self.dimension, self.dimension) * 0.01
    
    def store(self, engram: Engram) -> str:
        if len(self.enggrams) >= self.max_enggrams:
            self._forget_oldest()
        separated = self._pattern_separate(engram.pattern)
        engram.pattern = separated
        self.index.add(separated.reshape(1, -1).astype(np.float32))
        self.enggrams[engram.id] = engram
        self.temporal_index[engram.timestamp].append(engram.id)
        self.consolidation_queue.append(engram.id)
        return engram.id
    
    def _pattern_separate(self, pattern: np.ndarray) -> np.ndarray:
        return np.tanh(pattern @ self.pattern_separator + pattern)
    
    def _forget_oldest(self):
        if not self.enggrams:
            return
        oldest_id = min(self.enggrams.keys(), key=lambda k: self.enggrams[k].timestamp)
        self._remove_enggram(oldest_id)
    
    def _remove_enggram(self, engram_id: str):
        if engram_id in self.enggrams:
            del self.enggrams[engram_id]
    
    def recall(self, cue: np.ndarray, context: Optional[Dict] = None, 
               top_k: int = 10, threshold: float = 0.7) -> List[Tuple[Engram, float]]:
        cue_sep = self._pattern_separate(cue)
        distances, indices = self.index.search(cue_sep.reshape(1, -1).astype(np.float32), top_k * 2)
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            engram_id = list(self.enggrams.keys())[idx]
            engram = self.enggrams[engram_id]
            similarity = 1.0 / (1.0 + dist)
            if similarity >= threshold:
                if context and not self._context_match(engram.context, context):
                    continue
                results.append((engram, similarity))
        results.sort(key=lambda x: x[1], reverse=True)
        for engram, _ in results:
            engram.access_count += 1
            engram.last_accessed = datetime.now()
        return results[:top_k]
    
    def _context_match(self, ctx1: Dict, ctx2: Dict) -> bool:
        common_keys = set(ctx1.keys()) & set(ctx2.keys())
        if not common_keys:
            return True
        matches = sum(1 for k in common_keys if ctx1[k] == ctx2[k])
        return matches / len(common_keys) > 0.5
    
    def link(self, cause_id: str, effect_id: str, strength: float = 1.0):
        if cause_id in self.enggrams and effect_id in self.enggrams:
            self.causal_graph.add_edge(cause_id, effect_id, weight=strength)
            self.enggrams[cause_id].associations.add(effect_id)
            self.enggrams[effect_id].associations.add(cause_id)
    
    def replay(self, engram_id: str, steps: int = 3) -> List[Engram]:
        if engram_id not in self.enggrams:
            return []
        path = [engram_id]
        current = engram_id
        for _ in range(steps):
            successors = list(self.causal_graph.successors(current))
            if not successors:
                break
            weights = [self.causal_graph[current][s]['weight'] for s in successors]
            current = np.random.choice(successors, p=np.array(weights)/sum(weights))
            path.append(current)
        return [self.enggrams[eid] for eid in path if eid in self.enggrams]
    
    async def consolidate(self, batch_size: int = 100):
        consolidated = 0
        while self.consolidation_queue and consolidated < batch_size:
            eid = self.consolidation_queue.popleft()
            if eid in self.enggrams:
                engram = self.enggrams[eid]
                engram.consolidation_level = min(1.0, engram.consolidation_level + 0.1)
                for assoc_id in engram.associations:
                    if assoc_id in self.enggrams:
                        assoc = self.enggrams[assoc_id]
                        assoc.consolidation_level = min(1.0, assoc.consolidation_level + 0.05)
                consolidated += 1
        return consolidated


class SemanticMemory:
    def __init__(self, max_nodes: int = 10000000, embedding_dim: int = 768):
        self.max_nodes = max_nodes
        self.embedding_dim = embedding_dim
        self.concept_graph = nx.DiGraph()
        self.concept_embeddings: Dict[str, np.ndarray] = {}
        self.concept_properties: Dict[str, Dict] = {}
        self.category_hierarchy = nx.DiGraph()
        self.property_index: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
        self.prototype_vectors: Dict[str, np.ndarray] = {}
    
    def add_concept(self, concept: str, embedding: np.ndarray, 
                    properties: Dict[str, Any], category: Optional[str] = None):
        if len(self.concept_graph) >= self.max_nodes:
            return
        self.concept_graph.add_node(concept)
        self.concept_embeddings[concept] = embedding
        self.concept_properties[concept] = properties
        if category:
            self.category_hierarchy.add_edge(category, concept)
            for prop, val in properties.items():
                self.property_index[category][prop].add(concept)
        self._update_prototype(category)
    
    def _update_prototype(self, category: Optional[str]):
        if not category:
            return
        members = list(self.category_hierarchy.successors(category))
        if members:
            embeddings = [self.concept_embeddings[m] for m in members if m in self.concept_embeddings]
            if embeddings:
                self.prototype_vectors[category] = np.mean(embeddings, axis=0)
    
    def query(self, embedding: np.ndarray, top_k: int = 10) -> List[Tuple[str, float]]:
        results = []
        for concept, emb in self.concept_embeddings.items():
            sim = np.dot(embedding, emb) / (np.linalg.norm(embedding) * np.linalg.norm(emb) + 1e-8)
            results.append((concept, float(sim)))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
    
    def infer(self, premise1: str, premise2: str, relation: str) -> Optional[str]:
        if premise1 not in self.concept_graph or premise2 not in self.concept_graph:
            return None
        path = nx.shortest_path(self.concept_graph, premise1, premise2)
        if path and len(path) > 2:
            return path[len(path)//2]
        return None
    
    def analogical_reasoning(self, a: str, b: str, c: str) -> Optional[str]:
        if not all(x in self.concept_embeddings for x in [a, b, c]):
            return None
        vec_a = self.concept_embeddings[a]
        vec_b = self.concept_embeddings[b]
        vec_c = self.concept_embeddings[c]
        target_vec = vec_b - vec_a + vec_c
        target_vec = target_vec / (np.linalg.norm(target_vec) + 1e-8)
        results = self.query(target_vec, top_k=5)
        for concept, sim in results:
            if concept not in [a, b, c] and sim > 0.7:
                return concept
        return None


class ProceduralMemory:
    def __init__(self, max_skills: int = 1000):
        self.max_skills = max_skills
        self.skills: Dict[str, Dict] = {}
        self.skill_sequences: Dict[str, List[Dict]] = {}
        self.compilation_cache: Dict[str, Callable] = {}
        self.chunking_threshold = 0.8
    
    def learn_skill(self, name: str, steps: List[Dict], 
                    reward_history: List[float], context: Dict):
        if len(self.skills) >= self.max_skills:
            return
        proficiency = np.mean(reward_history[-10:]) if reward_history else 0.0
        self.skills[name] = {
            'steps': steps,
            'proficiency': proficiency,
            'context': context,
            'practice_count': len(reward_history),
            'last_practiced': datetime.now(),
            'chunks': self._identify_chunks(steps)
        }
        self.skill_sequences[name] = steps
    
    def _identify_chunks(self, steps: List[Dict]) -> List[List[int]]:
        chunks = []
        current_chunk = []
        for i, step in enumerate(steps):
            current_chunk.append(i)
            if i > 0 and step.get('type') != steps[i-1].get('type'):
                if len(current_chunk) > 1:
                    chunks.append(current_chunk)
                current_chunk = [i]
        if current_chunk:
            chunks.append(current_chunk)
        return chunks
    
    def execute(self, name: str, context: Dict) -> Optional[List[Dict]]:
        if name not in self.skills:
            return None
        skill = self.skills[name]
        skill['practice_count'] += 1
        skill['last_practiced'] = datetime.now()
        return skill['steps']
    
    def compile(self, name: str) -> Optional[Callable]:
        if name in self.compilation_cache:
            return self.compilation_cache[name]
        if name not in self.skills:
            return None
        steps = self.skills[name]['steps']
        def compiled_skill(ctx):
            results = []
            for step in steps:
                results.append(step.get('action', lambda c: None)(ctx))
            return results
        self.compilation_cache[name] = compiled_skill
        return compiled_skill


class EmotionalMemory:
    def __init__(self, decay: float = 0.995):
        self.decay = decay
        self.emotional_traces: Dict[EmotionCategory, List[Engram]] = defaultdict(list)
        self.mood_state: Dict[EmotionCategory, float] = defaultdict(float)
        self.flashbulb_memories: List[Engram] = []
        self.somatic_markers: Dict[str, float] = {}
    
    def store(self, engram: Engram):
        dominant_emotion = max(engram.emotional_tone.items(), key=lambda x: x[1])[0] if engram.emotional_tone else EmotionCategory.TRUST
        self.emotional_traces[dominant_emotion].append(engram)
        if engram.arousal > 0.9 and abs(engram.emotional_valence) > 0.8:
            self.flashbulb_memories.append(engram)
            if len(self.flashbulb_memories) > 100:
                self.flashbulb_memories.pop(0)
        self._update_mood(engram)
    
    def _update_mood(self, engram: Engram):
        for emotion, intensity in engram.emotional_tone.items():
            self.mood_state[emotion] = (self.mood_state[emotion] * self.decay + 
                                         intensity * (1 - self.decay))
    
    def get_mood(self) -> Dict[EmotionCategory, float]:
        return dict(self.mood_state)
    
    def recall_by_emotion(self, emotion: EmotionCategory, valence: float, 
                          top_k: int = 5) -> List[Engram]:
        traces = self.emotional_traces.get(emotion, [])
        if not traces:
            return []
        scored = [(e, abs(e.emotional_valence - valence) * e.arousal) for e in traces]
        scored.sort(key=lambda x: x[1])
        return [e for e, _ in scored[:top_k]]
    
    def somatic_mark(self, situation: str, value: float):
        self.somatic_markers[situation] = value
    
    def get_somatic_signal(self, situation: str) -> float:
        return self.somatic_markers.get(situation, 0.0)


class MemorySystem:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.working = WorkingMemory(config.get('working_capacity', 7))
        self.episodic = EpisodicMemory(
            config.get('episodic_max', 1000000),
            config.get('embedding_dim', 768)
        )
        self.semantic = SemanticMemory(
            config.get('semantic_max', 10000000),
            config.get('embedding_dim', 768)
        )
        self.procedural = ProceduralMemory(config.get('procedural_max', 1000))
        self.emotional = EmotionalMemory(config.get('emotional_decay', 0.995))
        self.consolidation_interval = config.get('consolidation_interval', 3600)
        self.last_consolidation = datetime.now()
    
    async def store_experience(self, percept: np.ndarray, modality: Modality,
                               emotional_tone: Dict[EmotionCategory, float],
                               context: Dict, engram_type: MemoryType = MemoryType.EPISODIC) -> Engram:
        engram = Engram(
            id=hashlib.sha256(f"{datetime.now()}{percept.tobytes()}".encode()).hexdigest()[:16],
            pattern=percept,
            memory_type=engram_type,
            timestamp=datetime.now(),
            emotional_valence=sum(emotional_tone.values()) / len(emotional_tone) if emotional_tone else 0,
            arousal=max(emotional_tone.values()) if emotional_tone else 0,
            context=context,
            emotional_tone=emotional_tone
        )
        
        if engram_type == MemoryType.WORKING:
            self.working.add(engram)
        elif engram_type == MemoryType.EPISODIC:
            self.episodic.store(engram)
            self.emotional.store(engram)
        elif engram_type == MemoryType.SEMANTIC:
            concept = context.get('concept', 'unknown')
            self.semantic.add_concept(concept, percept, context)
        elif engram_type == MemoryType.PROCEDURAL:
            skill_name = context.get('skill', 'unknown')
            self.procedural.learn_skill(skill_name, context.get('steps', []), 
                                       context.get('rewards', []), context)
        elif engram_type == MemoryType.EMOTIONAL:
            self.emotional.store(engram)
        
        return engram
    
    async def retrieve(self, cue: np.ndarray, modality: Modality,
                       memory_types: List[MemoryType] = None,
                       context: Optional[Dict] = None) -> List[Engram]:
        if memory_types is None:
            memory_types = [MemoryType.WORKING, MemoryType.EPISODIC, MemoryType.SEMANTIC]
        
        results = []
        if MemoryType.WORKING in memory_types:
            wm_results = self.working.retrieve(cue)
            results.extend([e for e, _ in wm_results])
        if MemoryType.EPISODIC in memory_types:
            ep_results = self.episodic.recall(cue, context)
            results.extend([e for e, _ in ep_results])
        if MemoryType.SEMANTIC in memory_types:
            sem_results = self.semantic.query(cue)
            for concept, sim in sem_results:
                if concept in self.semantic.concept_embeddings:
                    eng = Engram(
                        id=f"sem_{concept}",
                        pattern=self.semantic.concept_embeddings[concept],
                        memory_type=MemoryType.SEMANTIC,
                        timestamp=datetime.now(),
                        emotional_valence=0,
                        arousal=0,
                        context={'concept': concept, 'similarity': sim}
                    )
                    results.append(eng)
        return results
    
    async def consolidate(self):
        now = datetime.now()
        if (now - self.last_consolidation).total_seconds() >= self.consolidation_interval:
            await self.episodic.consolidate()
            self._systems_consolidation()
            self.last_consolidation = now
    
    def _systems_consolidation(self):
        for eid, engram in list(self.episodic.enggrams.items()):
            if engram.consolidation_level > 0.8 and engram.access_count > 5:
                concept = engram.context.get('concept')
                if concept and concept not in self.semantic.concept_embeddings:
                    self.semantic.add_concept(concept, engram.pattern, engram.context)
    
    def get_memory_stats(self) -> Dict:
        return {
            'working': len(self.working.get_contents()),
            'episodic': len(self.episodic.enggrams),
            'semantic': len(self.semantic.concept_graph),
            'procedural': len(self.procedural.skills),
            'emotional_traces': sum(len(v) for v in self.emotional.emotional_traces.values()),
            'flashbulb': len(self.emotional.flashbulb_memories),
            'mood': dict(self.emotional.get_mood())
        }