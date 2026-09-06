from __future__ import annotations
import asyncio
import asyncpg
import redis.asyncio as redis
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, Float, Integer, LargeBinary, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
import numpy as np
import faiss
import pickle
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
import uuid

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class EngramModel(Base):
    __tablename__ = 'engrams'
    
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pattern: Mapped[bytes] = mapped_column(LargeBinary)
    memory_type: Mapped[str] = mapped_column(String(32))
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    emotional_valence: Mapped[float] = mapped_column(Float)
    arousal: Mapped[float] = mapped_column(Float)
    context: Mapped[dict] = mapped_column(JSON)
    associations: Mapped[dict] = mapped_column(JSON)
    consolidation_level: Mapped[float] = mapped_column(Float)
    access_count: Mapped[int] = mapped_column(Integer)
    last_accessed: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    quantum_signature: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)


class ThoughtModel(Base):
    __tablename__ = 'thoughts'
    
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[dict] = mapped_column(JSON)
    modality: Mapped[str] = mapped_column(String(32))
    consciousness_level: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    duration_ms: Mapped[float] = mapped_column(Float)
    parent_thoughts: Mapped[dict] = mapped_column(JSON)
    child_thoughts: Mapped[dict] = mapped_column(JSON)
    emotional_tone: Mapped[dict] = mapped_column(JSON)
    certainty: Mapped[float] = mapped_column(Float)
    novelty: Mapped[float] = mapped_column(Float)
    relevance: Mapped[float] = mapped_column(Float)
    quantum_entanglement: Mapped[dict] = mapped_column(JSON)


class ConceptModel(Base):
    __tablename__ = 'concepts'
    
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    embedding: Mapped[bytes] = mapped_column(LargeBinary)
    properties: Mapped[dict] = mapped_column(JSON)
    category: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    prototype: Mapped[bool] = mapped_column(Integer)
    created: Mapped[datetime] = mapped_column(DateTime)
    access_count: Mapped[int] = mapped_column(Integer)
    last_accessed: Mapped[datetime] = mapped_column(DateTime)


class SkillModel(Base):
    __tablename__ = 'skills'
    
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    steps: Mapped[dict] = mapped_column(JSON)
    proficiency: Mapped[float] = mapped_column(Float)
    context: Mapped[dict] = mapped_column(JSON)
    practice_count: Mapped[int] = mapped_column(Integer)
    last_practiced: Mapped[datetime] = mapped_column(DateTime)
    chunks: Mapped[dict] = mapped_column(JSON)


class GoalModel(Base):
    __tablename__ = 'goals'
    
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(Text)
    drive: Mapped[str] = mapped_column(String(32))
    priority: Mapped[float] = mapped_column(Float)
    subgoals: Mapped[dict] = mapped_column(JSON)
    preconditions: Mapped[dict] = mapped_column(JSON)
    effects: Mapped[dict] = mapped_column(JSON)
    progress: Mapped[float] = mapped_column(Float)
    created: Mapped[datetime] = mapped_column(DateTime)
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    intrinsic_value: Mapped[float] = mapped_column(Float)
    instrumental_value: Mapped[float] = mapped_column(Float)
    completed: Mapped[bool] = mapped_column(Integer)


class GenomeModel(Base):
    __tablename__ = 'genomes'
    
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    genes: Mapped[bytes] = mapped_column(LargeBinary)
    regulatory_network: Mapped[bytes] = mapped_column(LargeBinary)
    epigenetic_markers: Mapped[dict] = mapped_column(JSON)
    mutation_history: Mapped[dict] = mapped_column(JSON)
    fitness: Mapped[float] = mapped_column(Float)
    generation: Mapped[int] = mapped_column(Integer)
    lineage: Mapped[dict] = mapped_column(JSON)
    created: Mapped[datetime] = mapped_column(DateTime)


class ConversationModel(Base):
    __tablename__ = 'conversations'
    
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    turn: Mapped[int] = mapped_column(Integer)
    user_input: Mapped[str] = mapped_column(Text)
    understanding: Mapped[dict] = mapped_column(JSON)
    response: Mapped[str] = mapped_column(Text)
    monologue: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)


class InternetKnowledgeModel(Base):
    __tablename__ = 'internet_knowledge'
    
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    query: Mapped[str] = mapped_column(Text, index=True)
    results: Mapped[dict] = mapped_column(JSON)
    credibility_scores: Mapped[dict] = mapped_column(JSON)
    verified: Mapped[bool] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    access_count: Mapped[int] = mapped_column(Integer)


class DreamModel(Base):
    __tablename__ = 'dreams'
    
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cycle: Mapped[int] = mapped_column(Integer)
    narrative: Mapped[dict] = mapped_column(JSON)
    lucidity: Mapped[float] = mapped_column(Float)
    consolidated_count: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime)


class SystemStateModel(Base):
    __tablename__ = 'system_states'
    
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    component: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[dict] = mapped_column(JSON)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)


class DatabaseManager:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.engine = None
        self.session_factory = None
        self.redis = None
        self.faiss_indices: Dict[str, faiss.Index] = {}
        self.embedding_dim = config.get('embedding_dim', 768)
        self._init_faiss()
    
    def _init_faiss(self):
        self.faiss_indices = {
            'engrams': faiss.IndexHNSWFlat(self.embedding_dim, 32),
            'concepts': faiss.IndexHNSWFlat(self.embedding_dim, 32),
            'thoughts': faiss.IndexHNSWFlat(self.embedding_dim, 16),
            'skills': faiss.IndexHNSWFlat(self.embedding_dim, 16)
        }
        for idx in self.faiss_indices.values():
            idx.hnsw.efConstruction = 200
            idx.hnsw.efSearch = 100
    
    async def initialize(self):
        db_url = self.config.get('database_url', 'sqlite+aiosqlite:///organism.db')
        self.engine = create_async_engine(db_url, echo=False, pool_size=5, max_overflow=5)
        self.session_factory = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        redis_url = self.config.get('redis_url', '')
        if redis_url:
            self.redis = redis.from_url(redis_url, encoding='utf-8', decode_responses=True)
        else:
            self.redis = None
        
        self._load_faiss_indices()
        logger.info("Database initialized")
    
    def _load_faiss_indices(self):
        import os
        for name in self.faiss_indices:
            path = f"faiss_{name}.index"
            if os.path.exists(path):
                self.faiss_indices[name] = faiss.read_index(path)
    
    async def close(self):
        if self.engine:
            await self.engine.dispose()
        if self.redis:
            await self.redis.close()
        self._save_faiss_indices()
    
    def _save_faiss_indices(self):
        for name, idx in self.faiss_indices.items():
            faiss.write_index(idx, f"faiss_{name}.index")
    
    @asynccontextmanager
    async def session(self):
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    async def store_engram(self, engram_data: Dict) -> str:
        engram_id = engram_data.get('id', hashlib.sha256(str(datetime.now()).encode()).hexdigest()[:16])
        
        async with self.session() as session:
            model = EngramModel(
                id=engram_id,
                pattern=pickle.dumps(engram_data['pattern']),
                memory_type=engram_data['memory_type'],
                timestamp=engram_data['timestamp'],
                emotional_valence=engram_data['emotional_valence'],
                arousal=engram_data['arousal'],
                context=engram_data['context'],
                associations=engram_data.get('associations', []),
                consolidation_level=engram_data.get('consolidation_level', 0),
                access_count=engram_data.get('access_count', 0),
                last_accessed=engram_data.get('last_accessed'),
                quantum_signature=pickle.dumps(engram_data['quantum_signature']) if engram_data.get('quantum_signature') is not None else None
            )
            session.add(model)
            
            pattern = engram_data['pattern'].astype(np.float32).flatten()
            if len(pattern) == self.embedding_dim:
                self.faiss_indices['engrams'].add(pattern.reshape(1, -1))
        
        if self.redis:
            await self.redis.setex(f"engram:{engram_id}", 3600, json.dumps(engram_data, default=str))
        return engram_id
    
    async def retrieve_engrams(self, query_vector: np.ndarray, top_k: int = 10, 
                                threshold: float = 0.7) -> List[Dict]:
        query = query_vector.astype(np.float32).flatten().reshape(1, -1)
        distances, indices = self.faiss_indices['engrams'].search(query, top_k)
        
        results = []
        async with self.session() as session:
            for dist, idx in zip(distances[0], indices[0]):
                if idx == -1:
                    continue
                similarity = 1.0 / (1.0 + dist)
                if similarity < threshold:
                    continue
                
                cached = None
                if self.redis:
                    cached = await self.redis.get(f"engram:{idx}")
                if cached:
                    results.append(json.loads(cached))
                else:
                    result = await session.get(EngramModel, str(idx))
                    if result:
                        data = {
                            'id': result.id,
                            'pattern': pickle.loads(result.pattern),
                            'memory_type': result.memory_type,
                            'timestamp': result.timestamp,
                            'emotional_valence': result.emotional_valence,
                            'arousal': result.arousal,
                            'context': result.context,
                            'associations': result.associations,
                            'consolidation_level': result.consolidation_level,
                            'access_count': result.access_count,
                            'last_accessed': result.last_accessed,
                            'quantum_signature': pickle.loads(result.quantum_signature) if result.quantum_signature else None
                        }
                        results.append(data)
        
        return results
    
    async def store_thought(self, thought_data: Dict) -> str:
        thought_id = thought_data.get('id', str(uuid.uuid4()))
        
        async with self.session() as session:
            model = ThoughtModel(
                id=thought_id,
                content=thought_data['content'],
                modality=thought_data['modality'],
                consciousness_level=thought_data['consciousness_level'],
                timestamp=thought_data['timestamp'],
                duration_ms=thought_data['duration_ms'],
                parent_thoughts=thought_data.get('parent_thoughts', []),
                child_thoughts=thought_data.get('child_thoughts', []),
                emotional_tone=thought_data.get('emotional_tone', {}),
                certainty=thought_data.get('certainty', 0.5),
                novelty=thought_data.get('novelty', 0),
                relevance=thought_data.get('relevance', 0),
                quantum_entanglement=thought_data.get('quantum_entanglement', [])
            )
            session.add(model)
            
            if 'embedding' in thought_data:
                emb = thought_data['embedding'].astype(np.float32).flatten()
                if len(emb) == self.embedding_dim:
                    self.faiss_indices['thoughts'].add(emb.reshape(1, -1))
        
        return thought_id
    
    async def store_concept(self, concept_id: str, embedding: np.ndarray, 
                             properties: Dict, category: Optional[str] = None):
        async with self.session() as session:
            model = ConceptModel(
                id=concept_id,
                embedding=pickle.dumps(embedding),
                properties=properties,
                category=category,
                prototype=1 if category else 0,
                created=datetime.now(),
                access_count=0,
                last_accessed=datetime.now()
            )
            session.add(model)
            
            emb = embedding.astype(np.float32).flatten()
            if len(emb) == self.embedding_dim:
                self.faiss_indices['concepts'].add(emb.reshape(1, -1))
    
    async def query_concepts(self, query_vector: np.ndarray, top_k: int = 10) -> List[Dict]:
        query = query_vector.astype(np.float32).flatten().reshape(1, -1)
        distances, indices = self.faiss_indices['concepts'].search(query, top_k)
        
        results = []
        async with self.session() as session:
            for dist, idx in zip(distances[0], indices[0]):
                if idx == -1:
                    continue
                result = await session.get(ConceptModel, str(idx))
                if result:
                    results.append({
                        'id': result.id,
                        'embedding': pickle.loads(result.embedding),
                        'properties': result.properties,
                        'category': result.category,
                        'similarity': 1.0 / (1.0 + dist)
                    })
        return results
    
    async def store_skill(self, skill_id: str, skill_data: Dict):
        async with self.session() as session:
            model = SkillModel(
                id=skill_id,
                steps=skill_data['steps'],
                proficiency=skill_data['proficiency'],
                context=skill_data['context'],
                practice_count=skill_data['practice_count'],
                last_practiced=skill_data['last_practiced'],
                chunks=skill_data.get('chunks', {})
            )
            session.add(model)
    
    async def store_goal(self, goal_data: Dict):
        async with self.session() as session:
            model = GoalModel(
                id=goal_data['id'],
                description=goal_data['description'],
                drive=goal_data['drive'],
                priority=goal_data['priority'],
                subgoals=goal_data.get('subgoals', []),
                preconditions=goal_data.get('preconditions', {}),
                effects=goal_data.get('effects', {}),
                progress=goal_data.get('progress', 0),
                created=goal_data['created'],
                deadline=goal_data.get('deadline'),
                intrinsic_value=goal_data.get('intrinsic_value', 0),
                instrumental_value=goal_data.get('instrumental_value', 0),
                completed=0
            )
            session.add(model)
    
    async def update_goal_progress(self, goal_id: str, progress: float):
        async with self.session() as session:
            model = await session.get(GoalModel, goal_id)
            if model:
                model.progress = progress
                if progress >= 1.0:
                    model.completed = 1
    
    async def store_genome(self, genome_data: Dict):
        genome_id = genome_data.get('id', hashlib.sha256(str(datetime.now()).encode()).hexdigest()[:16])
        
        async with self.session() as session:
            model = GenomeModel(
                id=genome_id,
                genes=pickle.dumps(genome_data['genes']),
                regulatory_network=pickle.dumps(genome_data['regulatory_network']),
                epigenetic_markers=genome_data.get('epigenetic_markers', {}),
                mutation_history=genome_data.get('mutation_history', {}),
                fitness=genome_data.get('fitness', 0),
                generation=genome_data.get('generation', 0),
                lineage=genome_data.get('lineage', []),
                created=datetime.now()
            )
            session.add(model)
    
    async def store_conversation(self, conv_data: Dict):
        async with self.session() as session:
            model = ConversationModel(
                id=str(uuid.uuid4()),
                turn=conv_data['turn'],
                user_input=conv_data['user_input'],
                understanding=conv_data['understanding'],
                response=conv_data['response'],
                monologue=conv_data.get('monologue', ''),
                timestamp=conv_data['timestamp']
            )
            session.add(model)
    
    async def store_internet_knowledge(self, query: str, results: List[Dict], 
                                        credibility: Dict, verified: bool):
        knowledge_id = hashlib.sha256(query.encode()).hexdigest()[:16]
        
        async with self.session() as session:
            model = InternetKnowledgeModel(
                id=knowledge_id,
                query=query,
                results={'results': results},
                credibility_scores=credibility,
                verified=1 if verified else 0,
                timestamp=datetime.now(),
                access_count=0
            )
            session.add(model)
    
    async def get_internet_knowledge(self, query: str) -> Optional[Dict]:
        knowledge_id = hashlib.sha256(query.encode()).hexdigest()[:16]
        
        cached = None
        if self.redis:
            cached = await self.redis.get(f"knowledge:{knowledge_id}")
        if cached:
            return json.loads(cached)
        
        async with self.session() as session:
            model = await session.get(InternetKnowledgeModel, knowledge_id)
            if model:
                data = {
                    'query': model.query,
                    'results': model.results,
                    'credibility': model.credibility_scores,
                    'verified': model.verified
                }
                if self.redis:
                    await self.redis.setex(f"knowledge:{knowledge_id}", 86400, json.dumps(data))
                return data
        return None
    
    async def store_dream(self, dream_data: Dict):
        async with self.session() as session:
            model = DreamModel(
                id=str(uuid.uuid4()),
                cycle=dream_data['cycle'],
                narrative=dream_data['narrative'],
                lucidity=dream_data['lucidity'],
                consolidated_count=dream_data['consolidated'],
                timestamp=dream_data['timestamp']
            )
            session.add(model)
    
    async def store_system_state(self, component: str, state: Dict):
        async with self.session() as session:
            model = SystemStateModel(
                id=str(uuid.uuid4()),
                component=component,
                state=state,
                timestamp=datetime.now()
            )
            session.add(model)
    
    async def get_latest_state(self, component: str) -> Optional[Dict]:
        async with self.session() as session:
            result = await session.execute(
                sa.select(SystemStateModel)
                .where(SystemStateModel.component == component)
                .order_by(SystemStateModel.timestamp.desc())
                .limit(1)
            )
            model = result.scalar_one_or_none()
            return model.state if model else None
    
    async def backup(self):
        logger.info("Database backup initiated")
    
    async def get_stats(self) -> Dict:
        async with self.session() as session:
            stats = {}
            for model_class, name in [
                (EngramModel, 'engrams'), (ThoughtModel, 'thoughts'),
                (ConceptModel, 'concepts'), (SkillModel, 'skills'),
                (GoalModel, 'goals'), (GenomeModel, 'genomes'),
                (ConversationModel, 'conversations'), (DreamModel, 'dreams')
            ]:
                result = await session.execute(sa.select(sa.func.count()).select_from(model_class))
                stats[name] = result.scalar()
            
            stats['faiss_engrams'] = self.faiss_indices['engrams'].ntotal
            stats['faiss_concepts'] = self.faiss_indices['concepts'].ntotal
            stats['faiss_thoughts'] = self.faiss_indices['thoughts'].ntotal
            
            return stats


class VectorCache:
    def __init__(self, redis_client, ttl: int = 3600):
        self.redis = redis_client
        self.ttl = ttl
    
    async def set(self, key: str, vector: np.ndarray):
        if self.redis:
            data = pickle.dumps(vector.astype(np.float32))
            await self.redis.setex(f"vec:{key}", self.ttl, data)
    
    async def get(self, key: str) -> Optional[np.ndarray]:
        if self.redis:
            data = await self.redis.get(f"vec:{key}")
            if data:
                return pickle.loads(data)
        return None
    
    async def delete(self, key: str):
        if self.redis:
            await self.redis.delete(f"vec:{key}")