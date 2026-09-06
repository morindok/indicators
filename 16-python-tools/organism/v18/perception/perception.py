from __future__ import annotations
import numpy as np
import asyncio
import aiohttp
import hashlib
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import logging
import networkx as nx
from core.types import Percept, Modality, NeuralCoordinate
from core.neural_substrate import NeuralSubstrate

logger = logging.getLogger(__name__)


class PredictiveCodingLayer:
    def __init__(self, input_dim: int, hidden_dim: int, level: int):
        self.level = level
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.W_pred = np.random.randn(hidden_dim, input_dim) * 0.1
        self.W_error = np.random.randn(hidden_dim, input_dim) * 0.1
        self.prediction = np.zeros(input_dim)
        self.error = np.zeros(input_dim)
        self.hidden_state = np.zeros(hidden_dim)
        self.lr = 0.01
    
    def forward(self, input_data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        self.prediction = self.W_pred.T @ self.hidden_state
        self.error = input_data - self.prediction
        hidden_update = self.W_error @ self.error
        self.hidden_state = np.tanh(self.hidden_state + self.lr * hidden_update)
        self.W_pred += self.lr * np.outer(self.hidden_state, self.error)
        self.W_error += self.lr * np.outer(self.hidden_state, self.error)
        return self.prediction, self.error
    
    def get_features(self) -> np.ndarray:
        return self.hidden_state.copy()


class SensoryProcessor:
    def __init__(self, modality: Modality, config: Dict[str, Any]):
        self.modality = modality
        self.config = config
        input_dim = config.get(f'{modality.name.lower()}_input_dim', 512)
        hidden_dim = config.get(f'{modality.name.lower()}_hidden_dim', 256)
        self.predictive_layers = [
            PredictiveCodingLayer(input_dim, hidden_dim, i)
            for i in range(config.get('predictive_coding_layers', 4))
        ]
        self.attention_weights = np.ones(input_dim)
        self.adaptation_state = np.zeros(input_dim)
        self.feature_extractors: Dict[str, Callable] = {}
        self._register_extractors()
    
    def _register_extractors(self):
        pass
    
    def process(self, raw_data: np.ndarray, attention: Optional[np.ndarray] = None) -> Percept:
        # Resize if input dimension changed
        if len(self.attention_weights) != len(raw_data):
            input_dim = len(raw_data)
            hidden_dim = self.config.get(f'{self.modality.name.lower()}_hidden_dim', 256)
            self.predictive_layers = [
                PredictiveCodingLayer(input_dim, hidden_dim, i)
                for i in range(self.config.get('predictive_coding_layers', 4))
            ]
            self.attention_weights = np.ones(input_dim)
            self.adaptation_state = np.zeros(input_dim)
        
        attended = raw_data * (attention if attention is not None else self.attention_weights)
        adapted = attended - self.adaptation_state * 0.1
        self.adaptation_state = 0.99 * self.adaptation_state + 0.01 * attended
        
        current_input = adapted
        features = {}
        total_error = 0.0
        for layer in self.predictive_layers:
            pred, error = layer.forward(current_input)
            features[f'level_{layer.level}'] = layer.get_features()
            total_error += np.mean(error ** 2)
            current_input = error
        
        return Percept(
            modality=self.modality,
            raw_data=raw_data,
            processed_features=features,
            timestamp=datetime.now(),
            attention_weight=float(np.mean(self.attention_weights)),
            predictive_error=total_error
        )
    
    def set_attention(self, weights: np.ndarray):
        self.attention_weights = weights


class VisualProcessor(SensoryProcessor):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(Modality.VISUAL, config)
        self.object_detector = None
        self.scene_understanding = None
        self.motion_detector = None
    
    def _register_extractors(self):
        self.feature_extractors = {
            'edges': lambda x: self._extract_edges(x),
            'colors': lambda x: self._extract_colors(x),
            'shapes': lambda x: self._extract_shapes(x),
            'motion': lambda x: self._extract_motion(x),
            'depth': lambda x: self._estimate_depth(x)
        }
    
    def _extract_edges(self, img: np.ndarray) -> np.ndarray:
        if img.ndim == 3:
            gray = np.mean(img, axis=2)
        else:
            gray = img
        sobel_x = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]])
        sobel_y = np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]])
        from scipy.signal import convolve2d
        gx = convolve2d(gray, sobel_x, mode='same', boundary='symm')
        gy = convolve2d(gray, sobel_y, mode='same', boundary='symm')
        return np.sqrt(gx**2 + gy**2)
    
    def _extract_colors(self, img: np.ndarray) -> np.ndarray:
        if img.ndim == 3:
            return np.mean(img, axis=(0, 1))
        return np.array([0.0, 0.0, 0.0])
    
    def _extract_shapes(self, img: np.ndarray) -> np.ndarray:
        return np.array([0.0] * 64)
    
    def _extract_motion(self, img: np.ndarray) -> np.ndarray:
        return np.array([0.0] * 32)
    
    def _estimate_depth(self, img: np.ndarray) -> np.ndarray:
        return np.array([0.0] * 16)


class AuditoryProcessor(SensoryProcessor):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(Modality.AUDITORY, config)
        self.phoneme_recognizer = None
        self.prosody_analyzer = None
        self.source_separator = None
    
    def _register_extractors(self):
        self.feature_extractors = {
            'mfcc': lambda x: self._extract_mfcc(x),
            'spectral': lambda x: self._extract_spectral(x),
            'prosody': lambda x: self._extract_prosody(x),
            'phonemes': lambda x: self._extract_phonemes(x),
            'rhythm': lambda x: self._extract_rhythm(x)
        }
    
    def _extract_mfcc(self, audio: np.ndarray) -> np.ndarray:
        return np.random.randn(40)
    
    def _extract_spectral(self, audio: np.ndarray) -> np.ndarray:
        return np.abs(np.fft.rfft(audio))[:128]
    
    def _extract_prosody(self, audio: np.ndarray) -> np.ndarray:
        return np.array([0.0] * 16)
    
    def _extract_phonemes(self, audio: np.ndarray) -> np.ndarray:
        return np.random.rand(50)
    
    def _extract_rhythm(self, audio: np.ndarray) -> np.ndarray:
        return np.array([0.0] * 8)


class TactileProcessor(SensoryProcessor):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(Modality.TACTILE, config)
        self.texture_analyzer = None
        self.temperature_sensor = None
        self.pressure_mapper = None
    
    def _register_extractors(self):
        self.feature_extractors = {
            'pressure': lambda x: np.mean(x),
            'texture': lambda x: np.std(x),
            'temperature': lambda x: np.mean(x),
            'vibration': lambda x: np.fft.fft(x).real[:16],
            'slip': lambda x: np.gradient(x).max()
        }


class OlfactoryProcessor(SensoryProcessor):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(Modality.OLFACTORY, config)
        self.receptor_array = np.random.randn(400, 10)
    
    def _register_extractors(self):
        self.feature_extractors = {
            'receptor_activation': lambda x: x @ self.receptor_array,
            'intensity': lambda x: np.sum(x),
            'quality': lambda x: np.argmax(x @ self.receptor_array, axis=1),
            'mixture_components': lambda x: np.linalg.svd(x @ self.receptor_array)[0][:10]
        }


class GustatoryProcessor(SensoryProcessor):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(Modality.GUSTATORY, config)
        self.taste_receptors = {'sweet': 0, 'sour': 0, 'salty': 0, 'bitter': 0, 'umami': 0}
    
    def _register_extractors(self):
        self.feature_extractors = {
            'taste_profile': lambda x: np.array(list(self.taste_receptors.values())),
            'intensity': lambda x: np.sum(list(self.taste_receptors.values())),
            'palatability': lambda x: self.taste_receptors['sweet'] + self.taste_receptors['umami'] - self.taste_receptors['bitter']
        }


class InteroceptiveProcessor(SensoryProcessor):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(Modality.INTEROCEPTIVE, config)
        self.homeostatic_variables = {
            'energy': 0.8, 'hydration': 0.7, 'temperature': 0.98,
            'integrity': 1.0, 'social_need': 0.5, 'cognitive_load': 0.3
        }
    
    def _register_extractors(self):
        self.feature_extractors = {
            'homeostasis': lambda x: np.array(list(self.homeostatic_variables.values())),
            'deviation': lambda x: np.array([abs(v - 0.8) for v in self.homeostatic_variables.values()]),
            'urgency': lambda x: max(abs(v - 0.8) for v in self.homeostatic_variables.values())
        }
    
    def update_homeostasis(self, variable: str, value: float):
        if variable in self.homeostatic_variables:
            self.homeostatic_variables[variable] = np.clip(value, 0, 1)


class ProprioceptiveProcessor(SensoryProcessor):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(Modality.PROPRIOCEPTIVE, config)
        self.body_schema = np.zeros(100)
        self.joint_angles = np.zeros(50)
        self.muscle_tensions = np.zeros(50)
    
    def _register_extractors(self):
        self.feature_extractors = {
            'body_configuration': lambda x: self.body_schema.copy(),
            'joint_state': lambda x: np.concatenate([self.joint_angles, self.muscle_tensions]),
            'movement_intention': lambda x: np.gradient(self.joint_angles) if len(self.joint_angles) > 1 else np.zeros(50)
        }


class MultimodalIntegration:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.binding_window = config.get('temporal_binding_window_ms', 100)
        self.pending_percepts: Dict[Modality, List[Percept]] = defaultdict(list)
        self.integrated_representation = np.zeros(config.get('integration_dim', 1024))
        self.attention_controller = AttentionController(config)
        self.cross_modal_associations = nx.DiGraph()
    
    def integrate(self, percepts: List[Percept]) -> np.ndarray:
        for p in percepts:
            self.pending_percepts[p.modality].append(p)
        
        now = datetime.now()
        synchronized = {}
        for mod, per_list in self.pending_percepts.items():
            per_list[:] = [p for p in per_list 
                          if (now - p.timestamp).total_seconds() * 1000 < self.binding_window]
            if per_list:
                synchronized[mod] = per_list[-1]
        
        if not synchronized:
            return self.integrated_representation
        
        features = []
        for mod, percept in synchronized.items():
            for level_name, feat in percept.processed_features.items():
                features.append(feat.flatten())
        
        if features:
            combined = np.concatenate(features)
            if len(combined) != len(self.integrated_representation):
                self.integrated_representation = np.resize(self.integrated_representation, len(combined))
            self.integrated_representation = 0.9 * self.integrated_representation + 0.1 * combined
            self._update_cross_modal(synchronized)
        
        return self.integrated_representation
    
    def _update_cross_modal(self, percepts: Dict[Modality, Percept]):
        mods = list(percepts.keys())
        for i, m1 in enumerate(mods):
            for m2 in mods[i+1:]:
                if not self.cross_modal_associations.has_edge(m1, m2):
                    self.cross_modal_associations.add_edge(m1, m2, weight=0.1)
                else:
                    w = self.cross_modal_associations[m1][m2]['weight']
                    self.cross_modal_associations[m1][m2]['weight'] = min(1.0, w + 0.01)
    
    def get_cross_modal_prediction(self, source_mod: Modality, target_mod: Modality) -> Optional[np.ndarray]:
        if self.cross_modal_associations.has_edge(source_mod, target_mod):
            weight = self.cross_modal_associations[source_mod][target_mod]['weight']
            return np.random.randn(256) * weight
        return None


class AttentionController:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.salience_map = np.zeros(config.get('salience_dim', 512))
        self.top_down_bias = np.zeros(config.get('salience_dim', 512))
        self.inhibition_of_return = np.zeros(config.get('salience_dim', 512))
        self.attention_history = deque(maxlen=100)
        self.current_focus: Optional[Tuple[Modality, int]] = None
    
    def compute_salience(self, percepts: Dict[Modality, Percept]) -> np.ndarray:
        salience = np.zeros_like(self.salience_map)
        for mod, percept in percepts.items():
            error_salience = percept.predictive_error
            novelty = 1.0 - percept.attention_weight
            mod_salience = error_salience * 0.5 + novelty * 0.5
            idx = hash(mod.name) % len(salience)
            salience[idx] = mod_salience
        salience += self.top_down_bias
        salience -= self.inhibition_of_return
        return np.maximum(salience, 0)
    
    def select_focus(self, salience: np.ndarray) -> Tuple[Modality, int]:
        if np.max(salience) > 0.1:
            idx = int(np.argmax(salience))
            mod_idx = idx % len(Modality)
            mod = list(Modality)[mod_idx]
            self.current_focus = (mod, idx)
            self.inhibition_of_return[idx] = 1.0
            self.inhibition_of_return *= 0.95
            self.attention_history.append((mod, idx, datetime.now()))
            return self.current_focus
        return (Modality.VISUAL, 0)
    
    def set_top_down_goal(self, goal_features: np.ndarray):
        self.top_down_bias = 0.9 * self.top_down_bias + 0.1 * goal_features[:len(self.top_down_bias)]


class PerceptionSystem:
    def __init__(self, config: Dict[str, Any], neural_substrate: NeuralSubstrate):
        self.config = config
        self.neural_substrate = neural_substrate
        self.processors: Dict[Modality, SensoryProcessor] = {
            Modality.VISUAL: VisualProcessor(config),
            Modality.AUDITORY: AuditoryProcessor(config),
            Modality.TACTILE: TactileProcessor(config),
            Modality.OLFACTORY: OlfactoryProcessor(config),
            Modality.GUSTATORY: GustatoryProcessor(config),
            Modality.INTEROCEPTIVE: InteroceptiveProcessor(config),
            Modality.PROPRIOCEPTIVE: ProprioceptiveProcessor(config)
        }
        self.integration = MultimodalIntegration(config)
        self.attention = AttentionController(config)
        self.percept_history: List[Percept] = []
        self.active_modalities: Set[Modality] = set()
    
    async def process_input(self, inputs: Dict[Modality, np.ndarray]) -> Dict:
        percepts = {}
        for mod, data in inputs.items():
            if mod in self.processors:
                processor = self.processors[mod]
                attended_data = data * processor.attention_weights[:len(data)]
                percept = processor.process(attended_data)
                percepts[mod] = percept
                self.percept_history.append(percept)
                self.active_modalities.add(mod)
                self.neural_substrate.inject_pattern(percept.raw_data, mod)
        
        integrated = self.integration.integrate(list(percepts.values()))
        salience = self.attention.compute_salience(percepts)
        focus = self.attention.select_focus(salience)
        
        return {
            'percepts': percepts,
            'integrated': integrated,
            'salience': salience,
            'focus': focus,
            'timestamp': datetime.now()
        }
    
    def get_processor(self, modality: Modality) -> Optional[SensoryProcessor]:
        return self.processors.get(modality)
    
    def set_modality_attention(self, modality: Modality, weights: np.ndarray):
        if modality in self.processors:
            self.processors[modality].set_attention(weights)
    
    def get_cross_modal_prediction(self, source: Modality, target: Modality) -> Optional[np.ndarray]:
        return self.integration.get_cross_modal_prediction(source, target)


class InternetPerception:
    """چشم جهان‌بین: دسترسی زنده به وب برای درک و پاسخ.

    منابع بدون کلید:
    - Wikipedia REST API (فارسی + انگلیسی)
    - DuckDuckGo HTML (اسکریپ سبک)
    - دریافت و استخراج متن صفحه‌ها
    """

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AVNA-DigitalOrganism/2500.1'
    }

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.search_engines = config.get('search_engines', ['duckduckgo', 'wikipedia'])
        self.knowledge_cache: Dict[str, Any] = {}
        self.credibility_scores: Dict[str, float] = {}
        self.max_results = int(config.get('max_results', 6))
        self.timeout = int(config.get('timeout', 15))
        self.max_chars_per_source = int(config.get('max_chars_per_source', 700))
        self.queries_served = 0

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=self.HEADERS)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def research(self, query: str, max_results: Optional[int] = None) -> List[Dict]:
        """جستجوی زنده و بازگشت شواهد متنی {title, snippet, url, source}."""
        if not self.session or not query or not query.strip():
            return []
        cache_key = hashlib.sha256(query.strip().lower().encode()).hexdigest()
        if cache_key in self.knowledge_cache:
            return self.knowledge_cache[cache_key]

        limit = max_results or self.max_results
        tasks = [
            self._wikipedia_search(query, 'fa'),
            self._duckduckgo_search(query),
            self._wikipedia_search(query, 'en'),
        ]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        results: List[Dict] = []
        for batch in gathered:
            if isinstance(batch, Exception):
                logger.debug(f"web source failed: {batch}")
                continue
            results.extend(batch)

        seen_urls = set()
        unique = []
        for r in sorted(results, key=lambda x: -x.get('score', 0)):
            url = r.get('url') or f"title:{r.get('title','')}"
            if url in seen_urls:
                continue
            seen_urls.add(url)
            unique.append(r)
        unique = unique[:limit]
        for r in unique:
            r['snippet'] = r['snippet'][:self.max_chars_per_source]
        self.knowledge_cache[cache_key] = unique
        self.queries_served += len(unique)
        return unique

    async def _duckduckgo_search(self, query: str) -> List[Dict]:
        from bs4 import BeautifulSoup
        from urllib.parse import parse_qs, quote, unquote

        url = f'https://html.duckduckgo.com/html/?q={quote(query)}'
        async with self.session.get(url, timeout=self.timeout) as resp:
            html = await resp.text()
        soup = BeautifulSoup(html, 'html.parser')
        out = []
        for block in soup.select('.result'):
            anchor = block.select_one('a.result__a')
            snippet_el = block.select_one('.result__snippet')
            if not anchor:
                continue
            link = anchor.get('href', '')
            if 'uddg=' in link:
                try:
                    link = unquote(parse_qs(link.split('?', 1)[1]).get('uddg', [link])[0])
                except Exception:
                    pass
            title = anchor.get_text(' ', strip=True)
            snippet = snippet_el.get_text(' ', strip=True) if snippet_el else ''
            if title and snippet:
                out.append({'title': title, 'snippet': snippet, 'url': link,
                            'source': 'web', 'score': 0.7})
        return out[:8]

    async def _wikipedia_search(self, query: str, lang: str) -> List[Dict]:
        base = f'https://{lang}.wikipedia.org'
        search_url = (f'{base}/w/rest.php/v1/search/page?q={query}&limit=3')
        async with self.session.get(search_url, timeout=self.timeout) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
        out = []
        for page in data.get('pages', []):
            excerpt = re.sub(r'<[^>]+>', '', page.get('excerpt', '') or '')
            summary = excerpt
            try:
                sum_url = f"{base}/w/rest.php/v1/page/summary/{page.get('key', '')}"
                async with self.session.get(sum_url, timeout=self.timeout) as sresp:
                    if sresp.status == 200:
                        sdata = await sresp.json()
                        summary = sdata.get('extract') or excerpt
            except Exception:
                pass
            if summary.strip():
                out.append({
                    'title': f"{page.get('title', '')} (ویکی‌پدیا {'فا' if lang == 'fa' else 'EN'})",
                    'snippet': summary,
                    'url': f"{base}/wiki/{page.get('key', '')}",
                    'source': f'wikipedia-{lang}',
                    'score': 0.9 if lang == 'fa' else 0.75,
                })
        return out

    # ---- سازگاری با رابط قبلی ----

    async def search(self, query: str, max_results: int = 10) -> List[Dict]:
        return await self.research(query, max_results)

    async def fetch_content(self, url: str) -> Optional[str]:
        if not self.session:
            return None
        try:
            async with self.session.get(url, timeout=self.timeout) as resp:
                html = await resp.text()
            return self._extract_text(html)
        except Exception:
            return None

    @staticmethod
    def _extract_text(html: str, limit: int = 2000) -> str:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'header', 'footer']):
            tag.decompose()
        text = soup.get_text(' ', strip=True)
        return text[:limit]