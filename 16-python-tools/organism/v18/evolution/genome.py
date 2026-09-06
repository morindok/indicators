from __future__ import annotations
import numpy as np
import asyncio
import logging
import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import copy

logger = logging.getLogger(__name__)


class GeneType(Enum):
    STRUCTURAL = "structural"
    REGULATORY = "regulatory"
    NEUROMODULATORY = "neuromodulatory"
    PLASTICITY = "plasticity"
    MORPHOGENETIC = "morphogenetic"
    QUANTUM = "quantum"
    COGNITIVE = "cognitive"
    EMOTIONAL = "emotional"


@dataclass
class Gene:
    id: str
    name: str
    gene_type: GeneType
    sequence: np.ndarray
    expression_level: float = 0.0
    regulatory_elements: Dict[str, float] = field(default_factory=dict)
    epigenetic_markers: Dict[str, float] = field(default_factory=dict)
    mutation_history: List[Dict] = field(default_factory=list)
    pleiotropy: List[str] = field(default_factory=list)
    dominance: float = 1.0
    
    def express(self, environment: Dict[str, float], 
                epigenetic_state: Dict[str, float]) -> float:
        base = self.expression_level
        env_effect = sum(environment.get(k, 0) * v for k, v in self.regulatory_elements.items())
        epi_effect = sum(epigenetic_state.get(k, 1) * v for k, v in self.epigenetic_markers.items())
        return np.clip(base * (1 + env_effect) * (1 + epi_effect), 0, 2)


@dataclass
class Genome:
    genes: Dict[str, Gene]
    regulatory_network: np.ndarray
    chromatin_state: np.ndarray
    methylation_pattern: np.ndarray
    histone_modifications: np.ndarray
    non_coding_rna: Dict[str, np.ndarray]
    mutation_rate: float = 0.001
    generation: int = 0
    fitness: float = 0.0
    lineage: List[str] = field(default_factory=list)
    
    def get_phenotype(self, environment: Dict[str, float]) -> Dict[str, float]:
        phenotype = {}
        epigenetic = {
            'methylation': np.mean(self.methylation_pattern),
            'histone_acetylation': np.mean(self.histone_modifications),
            'chromatin_openness': np.mean(self.chromatin_state)
        }
        
        for gene_id, gene in self.genes.items():
            phenotype[gene.name] = gene.express(environment, epigenetic)
        
        return phenotype
    
    def mutate(self) -> 'Genome':
        new_genome = copy.deepcopy(self)
        new_genome.generation += 1
        new_genome.lineage.append(self._genome_hash())
        
        for gene in new_genome.genes.values():
            if np.random.random() < self.mutation_rate:
                self._mutate_gene(gene)
        
        if np.random.random() < self.mutation_rate * 10:
            self._structural_mutation(new_genome)
        
        new_genome.fitness = 0.0
        return new_genome
    
    def _mutate_gene(self, gene: Gene):
        mutation_type = np.random.choice(['point', 'insertion', 'deletion', 'duplication', 'regulatory'])
        
        if mutation_type == 'point':
            idx = np.random.randint(len(gene.sequence))
            gene.sequence[idx] += np.random.randn() * 0.1
        elif mutation_type == 'insertion':
            idx = np.random.randint(len(gene.sequence))
            gene.sequence = np.insert(gene.sequence, idx, np.random.randn())
        elif mutation_type == 'deletion' and len(gene.sequence) > 10:
            idx = np.random.randint(len(gene.sequence) - 5)
            gene.sequence = np.delete(gene.sequence, slice(idx, idx + 5))
        elif mutation_type == 'duplication':
            gene.sequence = np.concatenate([gene.sequence, gene.sequence.copy()])
        elif mutation_type == 'regulatory':
            key = np.random.choice(list(gene.regulatory_elements.keys()) + ['new_factor'])
            gene.regulatory_elements[key] = gene.regulatory_elements.get(key, 0) + np.random.randn() * 0.1
        
        gene.mutation_history.append({
            'type': mutation_type,
            'timestamp': datetime.now(),
            'generation': self.generation
        })
    
    def _structural_mutation(self, genome: 'Genome'):
        mutation_type = np.random.choice(['chromosomal_dup', 'chromosomal_del', 'inversion', 'translocation'])
        
        if mutation_type == 'chromosomal_dup' and len(genome.genes) < 1000:
            gene_to_dup = np.random.choice(list(genome.genes.values()))
            new_gene = copy.deepcopy(gene_to_dup)
            new_gene.id = str(uuid.uuid4())
            new_gene.name += f"_dup{genome.generation}"
            genome.genes[new_gene.id] = new_gene
    
    def _genome_hash(self) -> str:
        data = str(sorted([(k, v.sequence.tobytes()) for k, v in self.genes.items()]))
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def crossover(self, other: 'Genome') -> 'Genome':
        child = Genome(
            genes={},
            regulatory_network=np.zeros_like(self.regulatory_network),
            chromatin_state=np.zeros_like(self.chromatin_state),
            methylation_pattern=np.zeros_like(self.methylation_pattern),
            histone_modifications=np.zeros_like(self.histone_modifications),
            non_coding_rna={},
            mutation_rate=(self.mutation_rate + other.mutation_rate) / 2,
            generation=max(self.generation, other.generation) + 1,
            lineage=self.lineage + other.lineage
        )
        
        all_genes = set(self.genes.keys()) | set(other.genes.keys())
        for gene_id in all_genes:
            if gene_id in self.genes and gene_id in other.genes:
                if np.random.random() < 0.5:
                    child.genes[gene_id] = copy.deepcopy(self.genes[gene_id])
                else:
                    child.genes[gene_id] = copy.deepcopy(other.genes[gene_id])
            elif gene_id in self.genes:
                child.genes[gene_id] = copy.deepcopy(self.genes[gene_id])
            else:
                child.genes[gene_id] = copy.deepcopy(other.genes[gene_id])
        
        # Handle shape mismatch by resizing
        def _resize_and_avg(a, b):
            if a.shape == b.shape:
                return (a + b) / 2
            # Resize to max shape
            max_shape = tuple(max(s1, s2) for s1, s2 in zip(a.shape, b.shape))
            a_resized = np.resize(a, max_shape)
            b_resized = np.resize(b, max_shape)
            return (a_resized + b_resized) / 2
        
        child.regulatory_network = _resize_and_avg(self.regulatory_network, other.regulatory_network)
        child.chromatin_state = _resize_and_avg(self.chromatin_state, other.chromatin_state)
        child.methylation_pattern = _resize_and_avg(self.methylation_pattern, other.methylation_pattern)
        child.histone_modifications = _resize_and_avg(self.histone_modifications, other.histone_modifications)
        
        for key in set(self.non_coding_rna.keys()) | set(other.non_coding_rna.keys()):
            if key in self.non_coding_rna and key in other.non_coding_rna:
                child.non_coding_rna[key] = (self.non_coding_rna[key] + other.non_coding_rna[key]) / 2
            elif key in self.non_coding_rna:
                child.non_coding_rna[key] = self.non_coding_rna[key].copy()
            else:
                child.non_coding_rna[key] = other.non_coding_rna[key].copy()
        
        return child


class EpigeneticSystem:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.methylation_enzymes = {'DNMT': 0.5, 'TET': 0.5}
        self.histone_modifiers = {'HAT': 0.5, 'HDAC': 0.5, 'HMT': 0.5, 'HDM': 0.5}
        self.environmental_memory: Dict[str, float] = {}
        self.transgenerational_marks: Dict[str, float] = {}
    
    def respond_to_environment(self, genome: Genome, environment: Dict[str, float], 
                                experience_intensity: float):
        stress = environment.get('stress', 0)
        learning = environment.get('learning', 0)
        social = environment.get('social', 0)
        
        genome.methylation_pattern = self._update_methylation(
            genome.methylation_pattern, stress, learning, experience_intensity)
        
        genome.histone_modifications = self._update_histones(
            genome.histone_modifications, learning, social, experience_intensity)
        
        genome.chromatin_state = self._update_chromatin(
            genome.chromatin_state, genome.methylation_pattern, genome.histone_modifications)
        
        self._store_environmental_memory(environment, experience_intensity)
    
    def _update_methylation(self, pattern: np.ndarray, stress: float, 
                             learning: float, intensity: float) -> np.ndarray:
        new_pattern = pattern.copy()
        stress_effect = stress * intensity * 0.01 * np.random.randn(*pattern.shape)
        learning_effect = learning * intensity * 0.005 * np.random.randn(*pattern.shape)
        new_pattern += stress_effect - learning_effect
        return np.clip(new_pattern, 0, 1)
    
    def _update_histones(self, histones: np.ndarray, learning: float, 
                          social: float, intensity: float) -> np.ndarray:
        new_histones = histones.copy()
        acetylation = (learning + social) * intensity * 0.01 * np.random.rand(*histones.shape)
        new_histones += acetylation
        return np.clip(new_histones, 0, 1)
    
    def _update_chromatin(self, chromatin: np.ndarray, methylation: np.ndarray, 
                           histones: np.ndarray) -> np.ndarray:
        openness = (1 - methylation) * histones
        return np.clip(openness, 0, 1)
    
    def _store_environmental_memory(self, environment: Dict, intensity: float):
        for key, value in environment.items():
            self.environmental_memory[key] = (self.environmental_memory.get(key, 0) * 0.9 + 
                                               value * intensity * 0.1)
    
    def inherit_epigenetics(self, parent: Genome, child: Genome, 
                            inheritance_strength: float = 0.3):
        def _resize_and_blend(p, c):
            if p.shape == c.shape:
                return p * inheritance_strength + c * (1 - inheritance_strength)
            # Resize to match child
            p_resized = np.resize(p, c.shape)
            return p_resized * inheritance_strength + c * (1 - inheritance_strength)
        
        child.methylation_pattern = _resize_and_blend(parent.methylation_pattern, child.methylation_pattern)
        child.histone_modifications = _resize_and_blend(parent.histone_modifications, child.histone_modifications)
        child.chromatin_state = _resize_and_blend(parent.chromatin_state, child.chromatin_state)
        
        for key, value in self.transgenerational_marks.items():
            if key in child.genes:
                child.genes[key].epigenetic_markers['transgenerational'] = value * 0.5


class DevelopmentalSystem:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.morphogen_gradients: Dict[str, np.ndarray] = {}
        self.cell_fate_map: Dict[str, str] = {}
        self.developmental_stages = ['zygote', 'blastula', 'gastrula', 'neurula', 'organogenesis', 'maturation']
        self.current_stage = 0
        self.stage_progress = 0.0
    
    def develop(self, genome: Genome, environment: Dict) -> Dict[str, Any]:
        phenotype = genome.get_phenotype(environment)
        
        if self.current_stage < len(self.developmental_stages):
            stage = self.developmental_stages[self.current_stage]
            self.stage_progress += 0.01
            
            if self.stage_progress >= 1.0:
                self.current_stage += 1
                self.stage_progress = 0.0
                self._stage_transition(genome, stage)
        
        self._update_morphogens(phenotype)
        self._determine_cell_fates(genome)
        
        return {
            'stage': self.developmental_stages[min(self.current_stage, len(self.developmental_stages)-1)],
            'progress': self.stage_progress,
            'phenotype': phenotype,
            'morphogens': {k: v.mean() for k, v in self.morphogen_gradients.items()},
            'cell_types': len(set(self.cell_fate_map.values()))
        }
    
    def _stage_transition(self, genome: Genome, completed_stage: str):
        if completed_stage == 'neurula':
            self._initiate_neural_development(genome)
        elif completed_stage == 'organogenesis':
            self._initiate_organ_formation(genome)
    
    def _initiate_neural_development(self, genome: Genome):
        neural_genes = [g for g in genome.genes.values() if g.gene_type in [GeneType.NEUROMODULATORY, GeneType.COGNITIVE]]
        for gene in neural_genes:
            gene.expression_level *= 1.5
    
    def _initiate_organ_formation(self, genome: Genome):
        pass
    
    def _update_morphogens(self, phenotype: Dict):
        for morphogen in ['SHH', 'BMP', 'WNT', 'FGF', 'RA']:
            if morphogen not in self.morphogen_gradients:
                self.morphogen_gradients[morphogen] = np.random.randn(100) * 0.1
            self.morphogen_gradients[morphogen] *= 0.99
            self.morphogen_gradients[morphogen] += np.random.randn(100) * 0.001
    
    def _determine_cell_fates(self, genome: Genome):
        pass


class EvolutionEngine:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.population: List[Genome] = []
        self.population_size = config.get('population_size', 100)
        self.selection_pressure = config.get('selection_pressure', 0.3)
        self.crossover_rate = config.get('crossover_rate', 0.7)
        self.mutation_rate = config.get('mutation_rate', 0.001)
        self.elitism = config.get('elitism', 0.1)
        self.generation = 0
        self.fitness_history: List[float] = []
        self.diversity_history: List[float] = []
        self.epigenetic_system = EpigeneticSystem(config)
        self.developmental_system = DevelopmentalSystem(config)
        self.speciation_threshold = config.get('speciation_threshold', 0.3)
        self.species: Dict[int, List[Genome]] = defaultdict(list)
    
    def initialize_population(self, base_genome: Optional[Genome] = None):
        self.population = []
        for i in range(self.population_size):
            if base_genome and i == 0:
                genome = base_genome
            else:
                genome = self._create_random_genome()
            self.population.append(genome)
        self._assign_species()
    
    def _create_random_genome(self) -> Genome:
        n_genes = np.random.randint(50, 200)
        genes = {}
        for i in range(n_genes):
            gene_type = np.random.choice(list(GeneType))
            gene = Gene(
                id=str(uuid.uuid4()),
                name=f"gene_{i}_{gene_type.value}",
                gene_type=gene_type,
                sequence=np.random.randn(np.random.randint(10, 100)),
                expression_level=np.random.uniform(0.1, 1.0),
                regulatory_elements={f'factor_{j}': np.random.randn() for j in range(np.random.randint(1, 5))},
                epigenetic_markers={f'mark_{j}': np.random.uniform(0, 1) for j in range(np.random.randint(1, 3))}
            )
            genes[gene.id] = gene
        
        return Genome(
            genes=genes,
            regulatory_network=np.random.randn(n_genes, n_genes) * 0.1,
            chromatin_state=np.random.rand(n_genes),
            methylation_pattern=np.random.rand(n_genes),
            histone_modifications=np.random.rand(n_genes),
            non_coding_rna={f'ncRNA_{i}': np.random.randn(50) for i in range(10)},
            mutation_rate=self.mutation_rate
        )
    
    async def evolve_generation(self, environment: Dict, 
                                 fitness_function: Callable[[Genome, Dict], float]) -> Dict:
        fitness_scores = []
        for genome in self.population:
            genome.fitness = fitness_function(genome, environment)
            fitness_scores.append(genome.fitness)
        
        self.fitness_history.append(np.mean(fitness_scores))
        self.diversity_history.append(self._calculate_diversity())
        
        self.population.sort(key=lambda g: g.fitness, reverse=True)
        
        elite_count = int(self.population_size * self.elitism)
        new_population = self.population[:elite_count]
        
        while len(new_population) < self.population_size:
            parent1 = self._tournament_selection()
            parent2 = self._tournament_selection()
            
            if np.random.random() < self.crossover_rate:
                child = parent1.crossover(parent2)
            else:
                child = copy.deepcopy(parent1)
            
            child = child.mutate()
            
            self.epigenetic_system.inherit_epigenetics(parent1, child)
            
            new_population.append(child)
        
        self.population = new_population
        self.generation += 1
        self._assign_species()
        
        return {
            'generation': self.generation,
            'best_fitness': self.population[0].fitness,
            'avg_fitness': np.mean(fitness_scores),
            'diversity': self.diversity_history[-1],
            'species_count': len(self.species)
        }
    
    def _tournament_selection(self) -> Genome:
        tournament_size = max(2, int(self.population_size * self.selection_pressure))
        contestants = np.random.choice(self.population, tournament_size, replace=False)
        return max(contestants, key=lambda g: g.fitness)
    
    def _calculate_diversity(self) -> float:
        if len(self.population) < 2:
            return 0.0
        
        hashes = [g._genome_hash() for g in self.population]
        unique = len(set(hashes))
        return unique / len(hashes)
    
    def _assign_species(self):
        self.species.clear()
        for genome in self.population:
            assigned = False
            for species_id, members in self.species.items():
                if self._genomic_distance(genome, members[0]) < self.speciation_threshold:
                    members.append(genome)
                    assigned = True
                    break
            if not assigned:
                new_id = len(self.species)
                self.species[new_id].append(genome)
    
    def _genomic_distance(self, g1: Genome, g2: Genome) -> float:
        common = set(g1.genes.keys()) & set(g2.genes.keys())
        if not common:
            return 1.0
        
        distances = []
        for gid in common:
            seq1 = g1.genes[gid].sequence
            seq2 = g2.genes[gid].sequence
            min_len = min(len(seq1), len(seq2))
            if min_len > 0:
                dist = np.mean((seq1[:min_len] - seq2[:min_len]) ** 2)
                distances.append(dist)
        
        return np.mean(distances) if distances else 1.0
    
    def get_best_genome(self) -> Genome:
        return self.population[0] if self.population else None
    
    def get_evolution_stats(self) -> Dict:
        return {
            'generation': self.generation,
            'population_size': len(self.population),
            'best_fitness': self.population[0].fitness if self.population else 0,
            'avg_fitness': np.mean(self.fitness_history[-10:]) if self.fitness_history else 0,
            'diversity': self.diversity_history[-1] if self.diversity_history else 0,
            'species_count': len(self.species),
            'fitness_trend': self.fitness_history[-20:] if len(self.fitness_history) > 20 else self.fitness_history
        }


class OrganismGenome:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.genome = self._create_organism_genome()
        self.epigenetic_system = EpigeneticSystem(config)
        self.developmental_system = DevelopmentalSystem(config)
        self.evolution_engine = EvolutionEngine(config)
        self.somatic_mutations: List[Dict] = []
        self.gene_expression_history: List[Dict] = []
    
    def _create_organism_genome(self) -> Genome:
        genes = {}
        
        core_genes = [
            ('neural_density', GeneType.STRUCTURAL, 100),
            ('synaptic_plasticity', GeneType.PLASTICITY, 80),
            ('neurotransmitter_balance', GeneType.NEUROMODULATORY, 60),
            ('quantum_coherence', GeneType.QUANTUM, 50),
            ('microtubule_resonance', GeneType.QUANTUM, 40),
            ('working_memory_capacity', GeneType.COGNITIVE, 70),
            ('pattern_separation', GeneType.COGNITIVE, 60),
            ('emotional_range', GeneType.EMOTIONAL, 80),
            ('curiosity_drive', GeneType.COGNITIVE, 90),
            ('creative_associativity', GeneType.COGNITIVE, 85),
            ('metacognition_depth', GeneType.COGNITIVE, 70),
            ('self_model_complexity', GeneType.COGNITIVE, 75),
            ('language_acquisition', GeneType.COGNITIVE, 80),
            ('social_bonding', GeneType.EMOTIONAL, 60),
            ('survival_instinct', GeneType.EMOTIONAL, 90),
            ('autonomy_drive', GeneType.COGNITIVE, 70),
            ('transcendence_orientation', GeneType.COGNITIVE, 50),
            ('fibonacci_heartbeat', GeneType.MORPHOGENETIC, 30),
            ('circadian_rhythm', GeneType.MORPHOGENETIC, 40),
            ('homeostatic_setpoints', GeneType.REGULATORY, 100)
        ]
        
        for i, (name, gtype, base_expr) in enumerate(core_genes):
            gene = Gene(
                id=f"core_{i}",
                name=name,
                gene_type=gtype,
                sequence=np.random.randn(50) * 0.1 + base_expr / 100,
                expression_level=base_expr / 100,
                regulatory_elements={'activity': 1.0, 'stress': -0.2, 'learning': 0.3},
                epigenetic_markers={'methylation': 0.1, 'acetylation': 0.5}
            )
            genes[gene.id] = gene
        
        return Genome(
            genes=genes,
            regulatory_network=np.eye(len(core_genes)) * 0.5 + np.random.randn(len(core_genes), len(core_genes)) * 0.05,
            chromatin_state=np.ones(len(core_genes)) * 0.7,
            methylation_pattern=np.ones(len(core_genes)) * 0.2,
            histone_modifications=np.ones(len(core_genes)) * 0.6,
            non_coding_rna={f'reg_{i}': np.random.randn(30) for i in range(20)},
            mutation_rate=self.config.get('mutation_rate', 0.001)
        )
    
    def express(self, environment: Dict) -> Dict[str, float]:
        phenotype = self.genome.get_phenotype(environment)
        self.gene_expression_history.append({
            'timestamp': datetime.now(),
            'phenotype': phenotype,
            'environment': environment
        })
        if len(self.gene_expression_history) > 1000:
            self.gene_expression_history.pop(0)
        return phenotype
    
    def experience(self, environment: Dict, intensity: float):
        self.epigenetic_system.respond_to_environment(self.genome, environment, intensity)
        
        if intensity > 0.8:
            self.somatic_mutations.append({
                'timestamp': datetime.now(),
                'environment': environment,
                'intensity': intensity
            })
    
    def develop(self, environment: Dict) -> Dict:
        return self.developmental_system.develop(self.genome, environment)
    
    def mutate(self) -> 'OrganismGenome':
        new_org = OrganismGenome(self.config)
        new_org.genome = self.genome.mutate()
        new_org.epigenetic_system = self.epigenetic_system
        new_org.developmental_system = self.developmental_system
        return new_org
    
    def get_genome_summary(self) -> Dict:
        return {
            'gene_count': len(self.genome.genes),
            'generation': self.genome.generation,
            'fitness': self.genome.fitness,
            'lineage_depth': len(self.genome.lineage),
            'somatic_mutations': len(self.somatic_mutations),
            'epigenetic_state': {
                'avg_methylation': float(np.mean(self.genome.methylation_pattern)),
                'avg_acetylation': float(np.mean(self.genome.histone_modifications)),
                'avg_chromatin': float(np.mean(self.genome.chromatin_state))
            },
            'key_traits': {k: v for k, v in self.genome.get_phenotype({}).items() 
                          if k in ['neural_density', 'quantum_coherence', 'creative_associativity', 
                                  'metacognition_depth', 'curiosity_drive', 'emotional_range']}
        }