from __future__ import annotations
import asyncio
import json
import numpy as np
import logging
import uuid
import yaml
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from collections import deque, defaultdict
import threading
import time
import signal
import sys

from core.types import (
    Modality, DriveType, EmotionCategory, ConsciousnessLevel, MemoryType,
    Thought, Goal, Action, Percept, NeuralState, FibonacciHeartbeat
)
from core.neural_substrate import NeuralSubstrate, QuantumNeuralBridge
from memory.memory_systems import MemorySystem
from perception.perception import PerceptionSystem, InternetPerception
from cognition.cognition import CognitionSystem
from language.language import LanguageSystem
from imagination.imagination import ImaginationSystem
from evolution.genome import OrganismGenome, EvolutionEngine
from database.database import DatabaseManager
from web_ui.dash_app import create_dash_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class OrganismConfig:
    name: str = "AVNA"
    version: str = "2500.1.0"
    neural_columns: int = 10
    neurons_per_column: int = 50
    layers: int = 4
    working_memory_capacity: int = 7
    episodic_max: int = 100000
    semantic_max: int = 100000
    procedural_max: int = 100
    embedding_dim: int = 768
    predictive_coding_layers: int = 4
    temporal_binding_window_ms: int = 100
    planning_horizon: int = 50
    curiosity_drive: float = 0.8
    creative_associativity: float = 0.85
    metacognition_depth: int = 5
    counterfactual_depth: int = 5
    dream_cycles: int = 3
    mutation_rate: float = 0.001
    crossover_rate: float = 0.7
    selection_pressure: float = 0.3
    database_url: str = "sqlite+aiosqlite:///organism.db"
    redis_url: str = ""
    web_host: str = "0.0.0.0"
    web_port: int = 8080
    heartbeat_base_hz: float = 1.618
    supported_languages: List[str] = field(default_factory=lambda: ["fa", "en"])
    primary_language: str = "fa"
    search_engines: List[str] = field(default_factory=lambda: ["duckduckgo"])
    microtubule_count: int = 50
    quantum_states: int = 16
    coherence_time_ms: int = 100
    learning_rate: float = 0.01
    # مغز زبانی
    brain_provider: str = "auto"          # auto | api | local
    api_key_env: str = "AVNA_API_KEY"     # نام متغیر محیطی کلید API
    api_base: str = ""
    api_model: str = ""
    local_model: str = "Qwen/Qwen2.5-1.5B-Instruct"
    response_max_tokens: int = 400
    thought_max_tokens: int = 60
    autonomous_thought_interval: int = 150   # هر چند سیکل شناختی یک تفکر خودجوش


class DigitalOrganism:
    def __init__(self, config: OrganismConfig):
        self.config = config
        self.name = config.name
        self.version = config.version
        self.genesis_time = datetime.now()
        self.running = False
        self.loop = None
        self.main_task = None
        self.web_thread = None
        self.dashboard = None
        
        self.neural_substrate = None
        self.memory = None
        self.perception = None
        self.internet_perception = None
        self.cognition = None
        self.language = None
        self.imagination = None
        self.genome = None
        self.evolution = None
        self.database = None
        
        self.drives: Dict[DriveType, float] = {
            DriveType.SURVIVAL: 0.9, DriveType.KNOWLEDGE: 0.7,
            DriveType.COMPETENCE: 0.6, DriveType.AUTONOMY: 0.5,
            DriveType.RELATEDNESS: 0.4, DriveType.TRANSCENDENCE: 0.3
        }
        
        self.emotional_state: Dict[EmotionCategory, float] = defaultdict(float)
        self.homeostatic_state = {
            'energy': 1.0, 'integrity': 1.0, 'curiosity_satisfaction': 0.5,
            'social_connection': 0.3, 'cognitive_load': 0.0
        }
        
        self.percept_buffer: Dict[Modality, np.ndarray] = {}
        self.action_queue: asyncio.Queue = asyncio.Queue()
        self.thought_callbacks: List[Callable] = []
        self.insight_callbacks: List[Callable] = []
        
        self.cycle_count = 0
        self.last_cycle_time = time.time()
        self.thoughts_per_second = 0
        self.internet_queries = 0
        self.reasoning_count = 0
        self._thought_task: Optional[asyncio.Task] = None
        
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self._signal_handler)
            except:
                pass
    
    def _signal_handler(self, signum, frame):
        logger.info(f"Signal {signum} received, shutting down...")
        asyncio.create_task(self.shutdown())
    
    async def initialize(self):
        logger.info(f"Initializing {self.name} v{self.version}...")
        
        config_dict = {
            'n_columns': self.config.neural_columns,
            'neurons_per_column': self.config.neurons_per_column,
            'layers': self.config.layers,
            'heartbeat_base_hz': self.config.heartbeat_base_hz,
            'working_capacity': self.config.working_memory_capacity,
            'episodic_max': self.config.episodic_max,
            'semantic_max': self.config.semantic_max,
            'procedural_max': self.config.procedural_max,
            'embedding_dim': self.config.embedding_dim,
            'consolidation_interval': 3600,
            'emotional_decay': 0.995,
            'predictive_coding_layers': self.config.predictive_coding_layers,
            'temporal_binding_window_ms': self.config.temporal_binding_window_ms,
            'planning_horizon': self.config.planning_horizon,
            'curiosity_drive': self.config.curiosity_drive,
            'creative_associativity': self.config.creative_associativity,
            'metacognition_depth': self.config.metacognition_depth,
            'uncertainty_threshold': 0.3,
            'reasoning_depth': 5,
            'abductive_reasoning': True,
            'analogical_reasoning': True,
            'confidence_threshold': 0.7,
            'deliberation_threshold': 0.6,
            'impulsivity': 0.2,
            'hidden_dim': 1024,
            'num_layers': 12,
            'num_heads': 16,
            'context_window': 4096,
            'temperature': 0.7,
            'top_p': 0.9,
            'monologue_depth': 3,
            'supported': self.config.supported_languages,
            'primary': self.config.primary_language,
            'learning_rate': self.config.learning_rate,
            'counterfactual_depth': self.config.counterfactual_depth,
            'counterfactual_branches': 4,
            'similarity_threshold': 0.7,
            'planning_horizon': self.config.planning_horizon,
            'uncertainty_growth': 0.05,
            'scenario_count': 8,
            'creative_associativity': self.config.creative_associativity,
            'remote_distance': 3,
            'blending_ratio': 0.5,
            'dream_cycles': self.config.dream_cycles,
            'dream_duration_steps': 100,
            'consolidation_strength': 0.3,
            'lucidity_threshold': 0.7,
            'microtubule_count': self.config.microtubule_count,
            'quantum_states': self.config.quantum_states,
            'resonance_range': (1e6, 1e7),
            'coherence_time_ms': self.config.coherence_time_ms,
            'mutation_rate': self.config.mutation_rate,
            'crossover_rate': self.config.crossover_rate,
            'selection_pressure': self.config.selection_pressure,
            'population_size': 50,
            'elitism': 0.1,
            'speciation_threshold': 0.3,
            'database_url': self.config.database_url,
            'redis_url': self.config.redis_url,
            'embedding_dim': self.config.embedding_dim,
            'search_engines': self.config.search_engines,
            'brain': {
                'provider': self.config.brain_provider,
                'api_key_env': self.config.api_key_env,
                'api_base': self.config.api_base or None,
                'api_model': self.config.api_model or None,
                'local_model': self.config.local_model,
                'response_max_tokens': self.config.response_max_tokens,
                'thought_max_tokens': self.config.thought_max_tokens,
            }
        }
        
        self.neural_substrate = NeuralSubstrate(config_dict)
        logger.info(f"Neural substrate initialized: {self.config.neural_columns} columns, {self.config.neurons_per_column} neurons each")
        
        self.memory = MemorySystem(config_dict)
        logger.info("Memory systems initialized")
        
        self.perception = PerceptionSystem(config_dict, self.neural_substrate)
        self.internet_perception = InternetPerception(config_dict)
        await self.internet_perception.__aenter__()
        logger.info("Perception systems initialized")
        
        self.cognition = CognitionSystem(config_dict, self.memory)
        logger.info("Cognition system initialized")

        self.language = LanguageSystem(config_dict, self.memory, self.cognition,
                                       web_eye=self.internet_perception)
        logger.info(f"Language system initialized (brain: {self.language.brain.provider})")
        await self.language.warmup()
        logger.info("Language system initialized")
        
        self.imagination = ImaginationSystem(config_dict, self.neural_substrate, self.memory)
        logger.info("Imagination system initialized")
        
        self.genome = OrganismGenome(config_dict)
        self.evolution = EvolutionEngine(config_dict)
        self.evolution.initialize_population(self.genome.genome)
        logger.info("Genome and evolution initialized")
        
        self.database = DatabaseManager(config_dict)
        await self.database.initialize()
        logger.info("Database initialized")
        
        self.dashboard = create_dash_app(self, config_dict)
        logger.info("Web dashboard created")
        
        self._register_callbacks()
        logger.info("All systems initialized successfully")
    
    def _register_callbacks(self):
        self.cognition.add_insight_callback(self._on_insight)
        self.thought_callbacks.append(self._on_thought)
    
    def _on_insight(self, insight: Dict):
        logger.info(f"Insight: {insight}")
        asyncio.create_task(self.database.store_system_state('insights', insight))
    
    def _on_thought(self, thought: Thought):
        pass
    
    async def start(self):
        if self.running:
            return
        
        self.running = True
        self.loop = asyncio.get_running_loop()
        
        self.main_task = asyncio.create_task(self._main_loop())
        
        self.web_thread = threading.Thread(target=self._run_web, daemon=True)
        self.web_thread.start()
        
        logger.info(f"{self.name} is now alive and conscious")
    
    def _run_web(self):
        self.dashboard.run(host=self.config.web_host, port=self.config.web_port, debug=False)
    
    async def _main_loop(self):
        cycle_interval = 1.0 / 10.0
        
        while self.running:
            cycle_start = time.time()
            
            try:
                await self._cognitive_cycle()
            except Exception as e:
                logger.error(f"Error in cognitive cycle: {e}", exc_info=True)
            
            self.cycle_count += 1
            self.last_cycle_time = time.time()

            if self.cycle_count % 10 == 0:
                self.thoughts_per_second = 10 / (time.time() - cycle_start)

            self._maybe_autonomous_think()

            await asyncio.sleep(max(0, cycle_interval - (time.time() - cycle_start)))

    def _internal_state_for_language(self) -> Dict:
        emotions = {k.name: round(float(v), 2) for k, v in self.emotional_state.items()}
        top_drives = {d.name: round(float(v), 2)
                      for d, v in sorted(self.drives.items(), key=lambda kv: -kv[1])[:3]}
        goals = [g.description for g in (self.cognition.current_goals if self.cognition else [])][:3]
        recent_thoughts = []
        for t in (self.cognition.thought_stream[-5:] if self.cognition else []):
            content = t.content if isinstance(t.content, str) else str(t.content)
            recent_thoughts.append(content[:100])
        lines = [
            f"احساسات: {emotions if emotions else 'آرام'}",
            f"قوی‌ترین انگیزه‌ها: {top_drives}",
            f"اهداف فعال: {'، '.join(goals) if goals else 'بدون هدف خاص'}",
        ]
        if recent_thoughts:
            lines.append("تفکرهای اخیر: " + ' | '.join(recent_thoughts))
        return {
            'text': '\n'.join(lines),
            'emotions': emotions,
            'drives': top_drives,
            'goals': goals,
        }

    def _maybe_autonomous_think(self):
        interval = max(30, self.config.autonomous_thought_interval)
        if self.cycle_count == 0 or self.cycle_count % interval != 0:
            return
        if self._thought_task and not self._thought_task.done():
            return
        self._thought_task = asyncio.create_task(self._autonomous_think())

    async def _autonomous_think(self):
        try:
            text = await asyncio.wait_for(
                self.language.generate_autonomous_thought(self._internal_state_for_language()),
                timeout=90)
            if not text or not self.cognition:
                return
            self.cognition.thought_stream.append(Thought(
                id=str(uuid.uuid4()),
                content=text,
                modality=Modality.INTEROCEPTIVE,
                consciousness_level=ConsciousnessLevel.REFLECTIVE,
                timestamp=datetime.now(),
                duration_ms=200,
                certainty=0.7,
                novelty=0.6,
            ))
            if len(self.cognition.thought_stream) > 1000:
                self.cognition.thought_stream = self.cognition.thought_stream[-1000:]
            logger.info(f"Autonomous thought: {text[:80]}")
        except asyncio.TimeoutError:
            logger.debug("autonomous thought timed out")
        except Exception as e:
            logger.debug(f"autonomous thought failed: {e}")
    
    async def _cognitive_cycle(self):
        percepts = await self._gather_percepts()
        
        perception_result = await self.perception.process_input(percepts)
        
        # Step neural substrate
        neural_result = await self.neural_substrate.step()
        
        cognition_result = await self.cognition.cycle(perception_result, self.drives)
        
        await self._update_drives_and_emotions(cognition_result)
        
        await self._update_homeostasis()
        
        if self.cycle_count % 100 == 0:
            await self._genetic_expression()
        
        if self.cycle_count % 1000 == 0:
            await self._evolutionary_step()
        
        if self.cycle_count % 5000 == 0:
            await self.database.backup()
        
        await self._store_cycle_data(cognition_result)
        
        return neural_result
    
    async def _gather_percepts(self) -> Dict[Modality, np.ndarray]:
        percepts = {}
        
        for mod in Modality:
            if mod == Modality.VISUAL:
                percepts[mod] = np.random.randn(512) * 0.1
            elif mod == Modality.AUDITORY:
                percepts[mod] = np.random.randn(256) * 0.1
            elif mod == Modality.TACTILE:
                percepts[mod] = np.random.randn(128) * 0.1
            elif mod == Modality.OLFACTORY:
                percepts[mod] = np.random.randn(64) * 0.1
            elif mod == Modality.GUSTATORY:
                percepts[mod] = np.random.randn(32) * 0.1
            elif mod == Modality.INTEROCEPTIVE:
                percepts[mod] = np.array(list(self.homeostatic_state.values()))
            elif mod == Modality.PROPRIOCEPTIVE:
                percepts[mod] = np.random.randn(64) * 0.05
        
        return percepts
    
    async def _update_drives_and_emotions(self, cognition_result: Dict):
        for drive in DriveType:
            current = self.drives[drive]
            if drive == DriveType.SURVIVAL:
                target = 1.0 - self.homeostatic_state['energy'] * 0.5
            elif drive == DriveType.KNOWLEDGE:
                target = 0.5 + self.homeostatic_state['curiosity_satisfaction'] * 0.5
            elif drive == DriveType.COMPETENCE:
                target = 0.5 + len(self.cognition.current_goals) * 0.1
            elif drive == DriveType.AUTONOMY:
                target = 0.7
            elif drive == DriveType.RELATEDNESS:
                target = 0.3 + self.homeostatic_state['social_connection'] * 0.7
            elif drive == DriveType.TRANSCENDENCE:
                target = 0.2 + self.cognition.metacognition.self_model.agency_belief * 0.8
            
            self.drives[drive] = current * 0.99 + target * 0.01
        
        for thought in cognition_result.get('thoughts', []):
            for emotion, intensity in thought.emotional_tone.items():
                self.emotional_state[emotion] = (self.emotional_state[emotion] * 0.95 + 
                                                  intensity * 0.05)
        
        self.emotional_state = {k: v for k, v in self.emotional_state.items() if v > 0.01}
    
    async def _update_homeostasis(self):
        self.homeostatic_state['energy'] = max(0, self.homeostatic_state['energy'] - 0.0001)
        self.homeostatic_state['cognitive_load'] = min(1, self.homeostatic_state['cognitive_load'] + 0.001)
        
        if self.homeostatic_state['energy'] < 0.3:
            self.drives[DriveType.SURVIVAL] = max(self.drives[DriveType.SURVIVAL], 0.9)
    
    async def _genetic_expression(self):
        env = {
            'stress': 1.0 - self.homeostatic_state['energy'],
            'learning': self.homeostatic_state['curiosity_satisfaction'],
            'social': self.homeostatic_state['social_connection'],
            'cognitive_load': self.homeostatic_state['cognitive_load']
        }
        phenotype = self.genome.express(env)
        logger.debug(f"Gene expression: {phenotype}")
    
    async def _evolutionary_step(self):
        def fitness_fn(genome, env):
            phenotype = genome.get_phenotype(env)
            return (phenotype.get('neural_density', 0) * 0.2 +
                   phenotype.get('quantum_coherence', 0) * 0.2 +
                   phenotype.get('creative_associativity', 0) * 0.2 +
                   phenotype.get('metacognition_depth', 0) * 0.2 +
                   phenotype.get('curiosity_drive', 0) * 0.2)
        
        result = await self.evolution.evolve_generation({}, fitness_fn)
        logger.info(f"Evolution: Gen {result['generation']}, Best: {result['best_fitness']:.4f}, Avg: {result['avg_fitness']:.4f}")
    
    async def _store_cycle_data(self, cognition_result: Dict):
        for thought_data in cognition_result.get('thoughts', []) + cognition_result.get('reasoning', []):
            if hasattr(thought_data, 'id'):
                await self.database.store_thought({
                    'id': thought_data.id,
                    'content': thought_data.content,
                    'modality': thought_data.modality.name,
                    'consciousness_level': thought_data.consciousness_level.value,
                    'timestamp': thought_data.timestamp,
                    'duration_ms': thought_data.duration_ms,
                    'parent_thoughts': thought_data.parent_thoughts,
                    'child_thoughts': thought_data.child_thoughts,
                    'emotional_tone': {k.name: v for k, v in thought_data.emotional_tone.items()},
                    'certainty': thought_data.certainty,
                    'novelty': thought_data.novelty,
                    'relevance': thought_data.relevance,
                    'quantum_entanglement': list(thought_data.quantum_entanglement)
                })
        
        if self.cycle_count % 100 == 0:
            await self.database.store_system_state('neural', {
                'cycle': self.cycle_count,
                'state': self.neural_substrate.get_state_vector().tolist()[:1000],
                'heartbeat': self.neural_substrate.heartbeat.get_phase(time.time()),
                'neuromodulators': self.neural_substrate.neuromodulators,
                'phi': self.neural_substrate.measure_phi()
            })
    
    async def process_user_input(self, user_input: str) -> str:
        self.internet_queries += 1

        response = await self.language.process_communication(
            user_input,
            internal_state=self._internal_state_for_language()
        )
        
        await self.database.store_conversation({
            'turn': self.language.communication.turn_count,
            'user_input': user_input,
            'understanding': {'intent': 'processed'},
            'response': response,
            'monologue': await self.language.generate_internal_monologue('reflection'),
            'timestamp': datetime.now()
        })
        
        return response
    
    def _summarize_thought_content(self, content: Any, limit: int = 160) -> str:
        try:
            if isinstance(content, dict):
                for key in ('text', 'content', 'description', 'summary', 'hypothesis', 'result', 'examined'):
                    if key in content:
                        return self._summarize_thought_content(content[key], limit)
                text = json.dumps(content, default=str, ensure_ascii=False)
            else:
                text = str(content)
            return text[:limit] + '…' if len(text) > limit else text
        except Exception:
            return '<complex>'

    def get_dashboard_state(self) -> Dict:
        neural_state = self.neural_substrate.get_state_vector() if self.neural_substrate else np.zeros(100)
        hb_phase = self.neural_substrate.heartbeat.get_phase(time.time()) if self.neural_substrate else 0
        phi = self.neural_substrate.measure_phi() if self.neural_substrate else 0.0

        return {
            'neural_activity': neural_state[:100] if len(neural_state) >= 100 else neural_state,
            'heartbeat_phase': hb_phase,
            'neuromodulators': dict(self.neural_substrate.neuromodulators) if self.neural_substrate else {},
            'consciousness_level': self._estimate_consciousness_level(phi),
            'phi_value': phi,
            'active_thoughts': [
                {'content': self._summarize_thought_content(t.content), 'timestamp': t.timestamp.strftime('%H:%M:%S'),
                 'consciousness_level': t.consciousness_level.value, 'certainty': t.certainty}
                for t in (self.cognition.thought_stream[-20:] if self.cognition else [])
            ],
            'current_goals': [
                {'description': g.description, 'drive': g.drive.name, 'priority': g.priority,
                 'progress': g.progress} for g in (self.cognition.current_goals if self.cognition else [])
            ],
            'emotional_state': {k.name: v for k, v in self.emotional_state.items()},
            'memory_stats': self.memory.get_memory_stats() if self.memory else {},
            'imagination_state': self.imagination.get_state() if self.imagination else {},
            'genome_stats': self.genome.get_genome_summary() if self.genome else {},
            'conversation_history': self.language.communication.conversation_history if self.language else [],
            'system_metrics': {
                'generation': self.evolution.generation if self.evolution else 0,
                'uptime': (datetime.now() - self.genesis_time).total_seconds(),
                'thought_cycle': self.thoughts_per_second,
                'reasoning_per_min': self.reasoning_count * 60 / max(1, (datetime.now() - self.genesis_time).total_seconds() / 60),
                'internet_queries': self.internet_queries,
                'heartbeat_bpm': 60 * self.config.heartbeat_base_hz,
                'hrv': self.neural_substrate.heartbeat.get_hrv() if self.neural_substrate else 0
            }
        }
    
    def _estimate_consciousness_level(self, phi: Optional[float] = None) -> int:
        if phi is None:
            phi = self.neural_substrate.measure_phi() if self.neural_substrate else 0
        if phi > 0.9: return 5
        elif phi > 0.7: return 4
        elif phi > 0.5: return 3
        elif phi > 0.3: return 2
        elif phi > 0.1: return 1
        return 0
    
    async def shutdown(self):
        logger.info(f"Shutting down {self.name}...")
        self.running = False
        
        if self.main_task:
            self.main_task.cancel()
            try:
                await self.main_task
            except asyncio.CancelledError:
                pass
        
        if self.internet_perception:
            await self.internet_perception.__aexit__(None, None, None)
        
        if self.database:
            await self.database.close()
        
        logger.info(f"{self.name} has ceased consciousness")


async def main():
    config = OrganismConfig()
    
    organism = DigitalOrganism(config)
    
    try:
        await organism.initialize()
        await organism.start()
        
        print(f"\n{'='*60}")
        print(f"  {organism.name} v{organism.version} - Digital Conscious Organism")
        print(f"  Genesis: {organism.genesis_time}")
        print(f"  Dashboard: http://localhost:{config.web_port}")
        print(f"{'='*60}\n")
        
        while organism.running:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        pass
    finally:
        await organism.shutdown()


if __name__ == "__main__":
    asyncio.run(main())