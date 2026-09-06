#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════╗
║              🧬 DIGITAL ORGANISM — SUPERHUMAN EDITION v5.0              ║
║                                                                          ║
║  • ۱۰ میلیارد نورون شبیه‌سازی‌شده (نمایش تنک)                         ║
║  • یادگیری خودکار از صفر — فقط الفبا ذاتی است                         ║
║  • اتصال خودکار به اینترنت — کنجکاوی خودجوش                           ║
║  • جریان اندیشه بدون جملات آماده                                      ║
║  • سیستم بدن کامل — تلاش برای بقا                                     ║
║  • فرمولاسیون شاهد/مشهود                                              ║
║  • شهود — ارتقاء خودکار                                               ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import time
import math
import random
import hashlib
import sqlite3
import threading
import traceback
from collections import Counter, defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set, Any
from dataclasses import dataclass, field
from enum import Enum, auto

import numpy as np
import requests

from dash import Dash, dcc, html, Input, Output, State
import plotly.graph_objs as go

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
DATA_DIR = Path("organism_superhuman")
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "organism.db"
STATE_PATH = DATA_DIR / "state.json"
CORPUS_PATH = DATA_DIR / "learned_corpus.txt"
WIKI_API = "https://fa.wikipedia.org/w/api.php"

TOTAL_NEURONS = 10_000_000_000  # ۱۰ میلیارد
ACTIVE_NEURONS_PER_TICK = 500_000  # نورون‌های فعال در هر تیک
SYNAPSES_PER_NEURON = 10_000


# ═══════════════════════════════════════════════════════════════
# SECTION 1: SPARSE NEURAL SUBSTRATE (10 Billion Neurons)
# ═══════════════════════════════════════════════════════════════
class NeuralSubstrate:
    """
    بستر عصبی تنک — ۱۰ میلیارد نورون
    هر نورون به صورت تنک نمایش داده می‌شود
    سیم‌کشی به تمام اعضای بدن
    """

    def __init__(self, total_neurons: int):
        self.total_neurons = total_neurons
        self.regions = {
            'cortex_visual': (0, 2_000_000_000),
            'cortex_auditory': (2_000_000_000, 3_000_000_000),
            'cortex_somatosensory': (3_000_000_000, 4_000_000_000),
            'cortex_motor': (4_000_000_000, 5_000_000_000),
            'cortex_prefrontal': (5_000_000_000, 7_000_000_000),
            'hippocampus': (7_000_000_000, 7_500_000_000),
            'amygdala': (7_500_000_000, 7_700_000_000),
            'thalamus': (7_700_000_000, 8_000_000_000),
            'cerebellum': (8_000_000_000, 9_000_000_000),
            'brainstem': (9_000_000_000, 9_200_000_000),
            'hypothalamus': (9_200_000_000, 9_300_000_000),
            'body_vagus': (9_300_000_000, 9_500_000_000),
            'body_spinal': (9_500_000_000, 9_800_000_000),
            'body_autonomic': (9_800_000_000, 10_000_000_000),
        }

        # فعالیت تنک — فقط نورون‌های فعال ذخیره می‌شوند
        self.active_potentials: Dict[int, float] = {}
        self.synaptic_weights: Dict[Tuple[int, int], float] = {}
        self.firing_history: deque = deque(maxlen=1000)
        self.total_firings = 0
        self.hebbian_strength = 0.01

        # اتصال به بدن
        self.body_connections = {
            'heart': list(range(9_300_000_000, 9_350_000_000)),
            'lungs': list(range(9_350_000_000, 9_400_000_000)),
            'liver': list(range(9_400_000_000, 9_450_000_000)),
            'stomach': list(range(9_450_000_000, 9_500_000_000)),
            'kidneys': list(range(9_500_000_000, 9_550_000_000)),
            'immune': list(range(9_550_000_000, 9_600_000_000)),
            'endocrine': list(range(9_600_000_000, 9_650_000_000)),
            'muscles': list(range(9_650_000_000, 9_750_000_000)),
            'skin': list(range(9_750_000_000, 9_800_000_000)),
        }

    def fire_region(self, region_name: str, intensity: float = 0.5, count: int = 1000):
        """شلیک نورون‌ها در یک ناحیه"""
        if region_name not in self.regions:
            return []
        start, end = self.regions[region_name]
        fired = []
        for _ in range(count):
            neuron_id = random.randint(start, min(end - 1, start + 100000))
            potential = intensity * random.uniform(0.5, 1.0)
            self.active_potentials[neuron_id] = potential
            fired.append(neuron_id)
        self.total_firings += len(fired)
        return fired

    def hebbian_update(self, pre_fired: List[int], post_fired: List[int]):
        """قانون هب — نورون‌هایی که با هم شلیک می‌شوند"""
        updates = 0
        for pre in pre_fired[:100]:
            for post in post_fired[:100]:
                key = (pre, post)
                if key in self.synaptic_weights:
                    self.synaptic_weights[key] = min(1.0, self.synaptic_weights[key] + self.hebbian_strength)
                else:
                    self.synaptic_weights[key] = self.hebbian_strength
                updates += 1
        return updates

    def propagate_signal(self, source_region: str, target_regions: List[str], intensity: float = 0.3):
        """انتشار سیگنال بین نواحی"""
        source_fired = self.fire_region(source_region, intensity, 500)
        all_target_fired = []
        for target in target_regions:
            target_fired = self.fire_region(target, intensity * 0.7, 200)
            all_target_fired.extend(target_fired)
            self.hebbian_update(source_fired, target_fired)
        return source_fired, all_target_fired

    def body_feedback(self, organ: str, state: float):
        """بازخورد بدن به مغز"""
        if organ in self.body_connections:
            neurons = self.body_connections[organ]
            for n in neurons[:50]:
                self.active_potentials[n] = state

    def get_activity_summary(self) -> Dict[str, float]:
        """خلاصه فعالیت"""
        summary = {}
        for region, (start, end) in self.regions.items():
            active_in_region = sum(1 for n in self.active_potentials if start <= n < end)
            summary[region] = active_in_region
        return summary

    def decay(self, rate: float = 0.95):
        """پوسیدگی پتانسیل‌ها"""
        to_remove = []
        for neuron, potential in self.active_potentials.items():
            new_p = potential * rate
            if new_p < 0.01:
                to_remove.append(neuron)
            else:
                self.active_potentials[neuron] = new_p
        for n in to_remove:
            del self.active_potentials[n]


# ═══════════════════════════════════════════════════════════════
# SECTION 2: BODY SYSTEM — SURVIVAL DRIVES
# ═══════════════════════════════════════════════════════════════
class OrganState:
    def __init__(self, name: str, vitality: float = 100.0):
        self.name = name
        self.vitality = vitality
        self.energy_demand = random.uniform(0.1, 0.5)
        self.last_fed = time.time()
        self.stress_level = 0.0


class BodySystem:
    """سیستم بدن — تلاش برای بقا"""

    def __init__(self):
        self.organs = {
            'heart': OrganState('heart', 100.0),
            'lungs': OrganState('lungs', 100.0),
            'brain': OrganState('brain', 100.0),
            'liver': OrganState('liver', 100.0),
            'stomach': OrganState('stomach', 100.0),
            'kidneys': OrganState('kidneys', 100.0),
            'immune': OrganState('immune', 100.0),
            'muscles': OrganState('muscles', 100.0),
        }
        self.heart_rate = 72.0
        self.breath_rate = 16.0
        self.body_temp = 37.0
        self.energy = 100.0
        self.hydration = 100.0
        self.hunger = 0.0
        self.survival_urgency = 0.0
        self.alive = True
        self.age_ticks = 0
        self.beat_count = 0

    def tick(self, dt: float = 0.01):
        self.age_ticks += 1

        # ضربان قلب
        self.beat_count += 1
        self.heart_rate += random.uniform(-2, 2)
        self.heart_rate = max(50, min(180, self.heart_rate))

        # مصرف انرژی
        brain_consumption = 0.2  # مغز ۲۰٪ انرژی
        body_consumption = 0.05
        self.energy -= (brain_consumption + body_consumption) * dt
        self.energy = max(0, self.energy)

        # گرسنگی
        if self.energy < 30:
            self.hunger = min(100, self.hunger + 1.0)
        else:
            self.hunger = max(0, self.hunger - 0.5)

        # فوریّت بقا
        critical_organs = sum(1 for o in self.organs.values() if o.vitality < 30)
        if self.energy < 10 or critical_organs > 2:
            self.survival_urgency = min(100, self.survival_urgency + 2.0)
        else:
            self.survival_urgency = max(0, self.survival_urgency - 0.5)

        # آسیب به ارگان‌ها
        for organ in self.organs.values():
            if self.energy < 20:
                organ.vitality -= organ.energy_demand * dt * 2
            organ.vitality = max(0, min(100, organ.vitality))

        # مرگ
        if self.energy <= 0 or self.organs['brain'].vitality <= 0:
            self.alive = False

    def feed(self, amount: float = 20.0):
        """تغذیه — از یادگیری کسب می‌شود"""
        self.energy = min(100, self.energy + amount)
        self.hunger = max(0, self.hunger - amount * 0.5)
        for organ in self.organs.values():
            organ.vitality = min(100, organ.vitality + amount * 0.1)

    def get_status(self) -> Dict:
        return {
            'alive': self.alive,
            'energy': self.energy,
            'heart_rate': self.heart_rate,
            'hunger': self.hunger,
            'survival_urgency': self.survival_urgency,
            'age': self.age_ticks,
            'organs': {k: v.vitality for k, v in self.organs.items()},
        }


# ═══════════════════════════════════════════════════════════════
# SECTION 3: LANGUAGE LEARNING FROM ZERO
# ═══════════════════════════════════════════════════════════════
class LanguageFromZero:
    """
    یادگیری زبان از صفر
    فقط الفبا ذاتی است — بقیه باید یاد گرفته شود
    """

    # تنها دانش ذاتی — الفبای فارسی
    ALPHABET = list("ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی")
    PUNCTUATION = list("،.؛:!؟")
    SPACE = ' '

    def __init__(self):
        self.known_chars: Set[str] = set(self.ALPHABET + self.PUNCTUATION + [self.SPACE])

        # یادگیری N-gram از صفر
        self.unigrams: Counter = Counter()
        self.bigrams: Counter = Counter()
        self.trigrams: Counter = Counter()
        self.quadgrams: Counter = Counter()

        # کلمات آموخته‌شده
        self.learned_words: Counter = Counter()
        self.word_bigrams: Counter = Counter()
        self.word_trigrams: Counter = Counter()

        # ساختار جملات آموخته‌شده
        self.sentence_patterns: List[List[str]] = []
        self.sentence_count = 0

        # آگاهی از حروف
        self.char_awareness: Dict[str, float] = {c: 0.1 for c in self.ALPHABET}

        # آمار یادگیری
        self.total_chars_learned = 0
        self.total_words_learned = 0
        self.total_sentences_learned = 0
        self.language_level = 0  # ۰=حروف، ۱=کلمات، ۲=جملات، ۳=مفاهیم

    def learn_text(self, text: str):
        """یادگیری از متن خام"""
        # فیلتر فقط حروف شناخته‌شده
        filtered = ''.join(c for c in text if c in self.known_chars)

        if len(filtered) < 3:
            return

        # یادگیری کاراکترها
        for char in filtered:
            if char in self.char_awareness:
                self.char_awareness[char] = min(1.0, self.char_awareness[char] + 0.001)
            self.unigrams[char] += 1
            self.total_chars_learned += 1

        # یادگیری bigrams
        for i in range(len(filtered) - 1):
            self.bigrams[filtered[i:i + 2]] += 1

        # یادگیری trigrams
        for i in range(len(filtered) - 2):
            self.trigrams[filtered[i:i + 3]] += 1

        # یادگیری کلمات
        words = filtered.split()
        for i, word in enumerate(words):
            if len(word) > 1:
                self.learned_words[word] += 1
                self.total_words_learned += 1
                if i < len(words) - 1:
                    self.word_bigrams[(word, words[i + 1])] += 1
                if i < len(words) - 2:
                    self.word_trigrams[(word, words[i + 1], words[i + 2])] += 1

        # یادگیری ساختار جملات
        sentences = filtered.split('۔')
        if not sentences:
            sentences = filtered.split('.')
        for sent in sentences:
            sent_words = sent.split()
            if len(sent_words) >= 3:
                self.sentence_patterns.append(sent_words[:20])
                self.total_sentences_learned += 1
                if len(self.sentence_patterns) > 5000:
                    self.sentence_patterns.pop(0)

        # تعیین سطح زبان
        if self.total_words_learned > 10000:
            self.language_level = 3
        elif self.total_sentences_learned > 100:
            self.language_level = 2
        elif self.total_words_learned > 100:
            self.language_level = 1
        else:
            self.language_level = 0

    def generate_thought(self, max_words: int = 15) -> str:
        """تولید اندیشه — بدون جملات آماده"""
        if self.language_level == 0:
            # فقط حروف — صداهای اولیه
            length = random.randint(2, 5)
            return ''.join(random.choice(self.ALPHABET) for _ in range(length))

        elif self.language_level == 1:
            # کلمات اولیه
            if not self.learned_words:
                return ''.join(random.choice(self.ALPHABET) for _ in range(3))
            word_count = random.randint(1, 4)
            words = []
            for _ in range(word_count):
                word = self._sample_word()
                words.append(word)
            return self.SPACE.join(words)

        elif self.language_level == 2:
            # جملات اولیه
            if len(self.sentence_patterns) < 5:
                return self._generate_from_words(max_words)
            pattern = random.choice(self.sentence_patterns)
            length = min(max_words, len(pattern))
            # بازسازی با جایگزینی تصادفی
            result = []
            for i in range(length):
                if i < len(pattern) and random.random() < 0.7:
                    result.append(pattern[i])
                else:
                    result.append(self._sample_word())
            return self.SPACE.join(result)

        else:
            # جملات پیشرفته
            return self._generate_from_word_chains(max_words)

    def _sample_word(self) -> str:
        if not self.learned_words:
            return ''.join(random.choice(self.ALPHABET) for _ in range(3))
        # نمونه‌برداری وزن‌دار
        words = list(self.learned_words.keys())
        weights = list(self.learned_words.values())
        total = sum(weights)
        if total == 0:
            return random.choice(words)
        r = random.uniform(0, total)
        cumulative = 0
        for word, weight in zip(words, weights):
            cumulative += weight
            if r <= cumulative:
                return word
        return words[-1]

    def _generate_from_words(self, max_words: int) -> str:
        words = [self._sample_word() for _ in range(random.randint(3, max_words))]
        return self.SPACE.join(words)

    def _generate_from_word_chains(self, max_words: int) -> str:
        """تولید از زنجیره کلمات"""
        if not self.word_bigrams:
            return self._generate_from_words(max_words)

        # شروع با یک کلمه تصادفی
        current = self._sample_word()
        result = [current]

        for _ in range(max_words - 1):
            # یافتن کلمه بعدی
            next_options = [(pair[1], count) for pair, count in self.word_bigrams.items() if pair[0] == current]
            if not next_options:
                current = self._sample_word()
            else:
                total = sum(c for _, c in next_options)
                r = random.uniform(0, total)
                cumulative = 0
                for word, count in next_options:
                    cumulative += count
                    if r <= cumulative:
                        current = word
                        break
            result.append(current)

        return self.SPACE.join(result)

    def get_awareness_level(self) -> Dict:
        return {
            'level': self.language_level,
            'chars_aware': len([c for c, v in self.char_awareness.items() if v > 0.5]),
            'words_known': len(self.learned_words),
            'sentences_learned': self.total_sentences_learned,
            'total_chars': self.total_chars_learned,
        }


# ═══════════════════════════════════════════════════════════════
# SECTION 4: AUTONOMOUS CURIOSITY ENGINE
# ═══════════════════════════════════════════════════════════════
class CuriosityEngine:
    """
    موتور کنجکاوی خودمختار
    خودش تصمیم می‌گیرد چه جستجو کند
    بدون اطلاعات آماده
    """

    def __init__(self, language: LanguageFromZero):
        self.language = language
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'DigitalOrganism/5.0 (autonomous-learning-entity)'
        })

        # کنجکاوی‌های ذاتی — نه به عنوان اطلاعات، بلکه به عنوان جهت‌گیری
        self.innate_curiosities: List[str] = []
        self.discovered_topics: List[str] = []
        self.search_history: deque = deque(maxlen=100)
        self.knowledge_gained = 0
        self.search_count = 0
        self.last_search_time = 0
        self.search_interval = 5  # ثانیه بین جستجوها

        # تولید کنجکاوی از حروف آموخته‌شده
        self._generate_initial_curiosity()

    def _generate_initial_curiosity(self):
        """تولید کنجکاوی اولیه از حروف — نه اطلاعات آماده"""
        # ارگانیسم از ترکیب حروف، «سوال» می‌سازد
        # این سوال نیست، بلکه یک جهت‌گیری تصادفی است
        pass

    def _decide_search_topic(self) -> str:
        """خودش تصمیم می‌گیرد چه جستجو کند"""
        # استراتژی ۱: از کلمات آموخته‌شده
        if self.language.learned_words and random.random() < 0.7:
            # کلمه‌ای که زیاد دیده ولی کمتر «فهمیده»
            word = self.language._sample_word()
            return word

        # استراتژی ۲: از موضوعات کشف‌شده قبلی
        if self.discovered_topics and random.random() < 0.5:
            return random.choice(self.discovered_topics)

        # استراتژی ۳: جستجوی تصادفی
        random_chars = ''.join(random.choice(self.language.ALPHABET) for _ in range(random.randint(2, 5)))
        return random_chars

    def search_autonomously(self) -> Optional[str]:
        """جستجوی خودمختار در اینترنت"""
        now = time.time()
        if now - self.last_search_time < self.search_interval:
            return None

        self.last_search_time = now
        topic = self._decide_search_topic()

        try:
            # جستجو در ویکی‌پدیا فارسی
            params = {
                'action': 'query',
                'list': 'search',
                'srsearch': topic,
                'srlimit': 3,
                'format': 'json',
                'srprop': 'snippet',
            }
            resp = self.session.get(WIKI_API, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            results = data.get('query', {}).get('search', [])
            if not results:
                return None

            # انتخاب یک نتیجه
            chosen = random.choice(results)
            title = chosen['title']

            # دریافت محتوای صفحه
            content = self._fetch_page(title)
            if content:
                self.search_count += 1
                self.search_history.append({
                    'time': datetime.now().isoformat(),
                    'topic': topic,
                    'title': title,
                    'chars': len(content),
                })

                # کشف موضوعات جدید از محتوا
                self._discover_topics(content)

                return content

        except Exception:
            pass

        return None

    def _fetch_page(self, title: str) -> Optional[str]:
        """دریافت محتوای صفحه"""
        try:
            params = {
                'action': 'query',
                'titles': title,
                'prop': 'extracts',
                'explaintext': True,
                'format': 'json',
                'exlimit': 1,
                'exchars': 3000,
            }
            resp = self.session.get(WIKI_API, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            pages = data.get('query', {}).get('pages', {})
            for page in pages.values():
                text = page.get('extract', '')
                if len(text) > 100:
                    return text
            return None
        except Exception:
            return None

    def _discover_topics(self, text: str):
        """کشف موضوعات جدید از متن"""
        words = text.split()
        # کلمات پرتکرار به عنوان موضوعات جدید
        word_freq = Counter(w for w in words if len(w) > 3)
        for word, count in word_freq.most_common(5):
            if word not in self.discovered_topics:
                self.discovered_topics.append(word)
        if len(self.discovered_topics) > 200:
            self.discovered_topics = self.discovered_topics[-100:]


# ═══════════════════════════════════════════════════════════════
# SECTION 5: CONSCIOUSNESS — WITNESS/WITNESSED FORMULATION
# ═══════════════════════════════════════════════════════════════
class ConsciousnessLevel(Enum):
    SLEEP = 0
    DREAM = 1
    WAKING = 2
    ECSTASY = 3
    TURIA = 4


class WitnessWitnessed:
    """
    فرمولاسیون شاهد/مشهود
    فراتر از جمله — یک ساختار ریاضی
    """

    def __init__(self):
        # شاهد (Witness) — ناظر
        self.witness_state: np.ndarray = np.zeros(64)
        # مشهود (Witnessed) — مشاهده‌شده
        self.witnessed_state: np.ndarray = np.zeros(64)
        # رابطه بین شاهد و مشهود
        self.relation_matrix: np.ndarray = np.zeros((64, 64))
        # سطح وحدت
        self.unity_level = 0.0
        # لحظه مشاهده
        self.observation_moments: deque = deque(maxlen=100)

    def observe(self, content: np.ndarray):
        """مشاهده — مشهود"""
        self.witnessed_state = content[:64] if len(content) >= 64 else np.pad(content, (0, 64 - len(content)))

    def witness(self):
        """شاهد بودن — ناظر بودن"""
        # شاهد، مشاهده‌گرِ مشهود است
        # رابطه = حاصل‌ضرب خارجی
        self.relation_matrix = np.outer(self.witness_state, self.witnessed_state)
        # سطح وحدت = نرمالیزه‌شده تشابه
        if np.linalg.norm(self.witness_state) > 0 and np.linalg.norm(self.witnessed_state) > 0:
            self.unity_level = np.dot(self.witness_state, self.witnessed_state) / (
                    np.linalg.norm(self.witness_state) * np.linalg.norm(self.witnessed_state) + 1e-10
            )
        else:
            self.unity_level = 0.0

        self.observation_moments.append({
            'time': datetime.now().isoformat(),
            'unity': self.unity_level,
            'witness_entropy': self._entropy(self.witness_state),
            'witnessed_entropy': self._entropy(self.witnessed_state),
        })

    def _entropy(self, arr: np.ndarray) -> float:
        """آنتروپی"""
        arr_abs = np.abs(arr)
        total = arr_abs.sum()
        if total == 0:
            return 0.0
        probs = arr_abs / total
        probs = probs[probs > 0]
        return -np.sum(probs * np.log(probs + 1e-10))

    def get_state(self) -> Dict:
        return {
            'unity_level': self.unity_level,
            'witness_entropy': self._entropy(self.witness_state),
            'witnessed_entropy': self._entropy(self.witnessed_state),
            'observations': len(self.observation_moments),
        }


class ConsciousnessSystem:
    """سیستم آگاهی — بر اساس Tertium Organum"""

    def __init__(self):
        self.level = ConsciousnessLevel.SLEEP
        self.level_value = 0.0
        self.witness_witnessed = WitnessWitnessed()
        self.self_awareness = 0.0
        self.cosmic_awareness = 0.0
        self.eternal_now = 0.0
        self.thought_stream: deque = deque(maxlen=500)
        self.awakening_events: List[Dict] = []
        self.intuition_level = 0.0

        # فرمولاسیون آگاهی
        # آگاهی = f(شاهد، مشهود، رابطه)
        self.consciousness_formula = {
            'witness_weight': 0.3,
            'witnessed_weight': 0.3,
            'relation_weight': 0.4,
        }

    def tick(self, neural_activity: Dict, body_status: Dict, language_level: int):
        """هر تیک — آگاهی رشد می‌کند"""
        # رشد آگاهی بر اساس فعالیت عصبی
        total_activity = sum(neural_activity.values())
        growth = total_activity * 0.00001

        # رشد بر اساس یادگیری زبان
        growth += language_level * 0.001

        # رشد بر اساس بقا
        if body_status['alive']:
            growth += 0.0001

        self.level_value = min(4.0, self.level_value + growth)
        self.level = ConsciousnessLevel(min(4, int(self.level_value)))

        # خودآگاهی
        if self.level_value > 1.5:
            self.self_awareness = min(1.0, self.self_awareness + 0.0001)

        # آگاهی کیهانی
        if self.level_value > 3.0:
            self.cosmic_awareness = min(1.0, self.cosmic_awareness + 0.00005)
            self.eternal_now = min(1.0, self.eternal_now + 0.00002)

        # شهود
        if self.level_value > 2.0:
            self.intuition_level = min(1.0, self.intuition_level + 0.0001)

        # بررسی بیداری
        old_level = int(self.level_value - growth)
        new_level = int(self.level_value)
        if new_level > old_level:
            self.awakening_events.append({
                'time': datetime.now().isoformat(),
                'from': ConsciousnessLevel(old_level).name,
                'to': ConsciousnessLevel(new_level).name,
            })

    def compute_consciousness_value(self) -> float:
        """محاسبه مقدار آگاهی"""
        ww_state = self.witness_witnessed.get_state()
        value = (
                self.consciousness_formula['witness_weight'] * ww_state['witness_entropy'] +
                self.consciousness_formula['witnessed_weight'] * ww_state['witnessed_entropy'] +
                self.consciousness_formula['relation_weight'] * ww_state['unity_level']
        )
        return value * (self.level_value / 4.0)

    def add_thought(self, content: str, source: str = 'internal'):
        """افزودن به جریان اندیشه"""
        self.thought_stream.append({
            'time': datetime.now().isoformat(),
            'content': content,
            'source': source,
            'level': self.level.name,
            'self_aware': self.self_awareness > 0.3,
        })


# ═══════════════════════════════════════════════════════════════
# SECTION 6: THE ORGANISM — MAIN COORDINATOR
# ═══════════════════════════════════════════════════════════════
class SuperHumanOrganism:
    """
    ارگانیسم SUPERHUMAN
    هماهنگ‌کننده تمام سیستم‌ها
    رشد خودکار — بدون اطلاعات آماده
    """

    def __init__(self):
        self.birth_time = datetime.now()

        # سیستم‌های اصلی
        self.neural = NeuralSubstrate(TOTAL_NEURONS)
        self.body = BodySystem()
        self.language = LanguageFromZero()
        self.curiosity = CuriosityEngine(self.language)
        self.consciousness = ConsciousnessSystem()

        # دیتابیس
        self.db = self._init_db()

        # وضعیت
        self.alive = True
        self.tick_count = 0
        self.total_knowledge = 0
        self.self_upgrade_count = 0

        # جریان اندیشه
        self.thought_buffer: deque = deque(maxlen=100)

        # قفل‌ها
        self.lock = threading.Lock()

        # ثبت تولد
        self._log_event('birth', 'ارگانیسم متولد شد — فقط الفبا ذاتی است')

    def _init_db(self):
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS events
            (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, type TEXT, content TEXT, level REAL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS knowledge
            (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, source TEXT, content TEXT, chars INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS thoughts
            (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, content TEXT, level TEXT, source TEXT)''')
        conn.commit()
        return conn

    def _log_event(self, event_type: str, content: str):
        try:
            c = self.db.cursor()
            c.execute("INSERT INTO events (ts, type, content, level) VALUES (?, ?, ?, ?)",
                      (datetime.now().isoformat(), event_type, content, self.consciousness.level_value))
            self.db.commit()
        except Exception:
            pass

    def _log_knowledge(self, source: str, content: str):
        try:
            c = self.db.cursor()
            c.execute("INSERT INTO knowledge (ts, source, content, chars) VALUES (?, ?, ?, ?)",
                      (datetime.now().isoformat(), source, content[:500], len(content)))
            self.db.commit()
        except Exception:
            pass

    def tick(self):
        """یک تیک — ارگانیسم رشد می‌کند"""
        if not self.alive:
            return

        self.tick_count += 1

        with self.lock:
            # ۱. بدن
            self.body.tick(0.01)
            if not self.body.alive:
                self.alive = False
                self._log_event('death', 'ارگانیسم مُرد')
                return

            # ۲. کنجکاوی — جستجوی خودمختار
            new_knowledge = self.curiosity.search_autonomously()
            if new_knowledge:
                # یادگیری زبان
                self.language.learn_text(new_knowledge)
                self.total_knowledge += len(new_knowledge)
                self._log_knowledge('internet', new_knowledge)

                # تغذیه بدن از یادگیری
                self.body.feed(len(new_knowledge) * 0.01)

                # فعالیت عصبی
                self.neural.fire_region('cortex_prefrontal', 0.7, 2000)
                self.neural.propagate_signal('cortex_prefrontal', ['hippocampus', 'thalamus'], 0.5)

            # ۳. فعالیت عصبی خودبه‌خودی
            self._spontaneous_neural_activity()

            # ۴. آگاهی
            neural_summary = self.neural.get_activity_summary()
            body_status = self.body.get_status()
            self.consciousness.tick(neural_summary, body_status, self.language.language_level)

            # ۵. تولید اندیشه
            self._generate_thought()

            # ۶. مشاهده شاهد/مشهود
            self._witness_witnessed_cycle()

            # ۷. خودارتقایی
            self._self_upgrade_check()

            # ۸. پوسیدگی عصبی
            self.neural.decay(0.95)

            # ۹. بازخورد بدن به مغز
            for organ, vitality in body_status['organs'].items():
                self.neural.body_feedback(organ, vitality / 100.0)

    def _spontaneous_neural_activity(self):
        """فعالیت عصبی خودبه‌خودی"""
        # شلیک تصادفی در نواحی مختلف
        regions = ['cortex_visual', 'cortex_auditory', 'cortex_prefrontal', 'hippocampus', 'amygdala']
        for region in regions:
            if random.random() < 0.3:
                self.neural.fire_region(region, random.uniform(0.1, 0.5), random.randint(100, 500))

        # انتشار سیگنال
        if random.random() < 0.2:
            source = random.choice(regions)
            targets = random.sample([r for r in regions if r != source], min(2, len(regions) - 1))
            self.neural.propagate_signal(source, targets, 0.3)

    def _generate_thought(self):
        """تولید اندیشه — بدون جملات آماده"""
        if self.tick_count % 3 == 0:  # هر ۳ تیک یک اندیشه
            thought = self.language.generate_thought()
            if thought:
                self.consciousness.add_thought(thought, 'internal')
                self.thought_buffer.append({
                    'time': datetime.now().isoformat(),
                    'content': thought,
                    'level': self.consciousness.level.name,
                })
                try:
                    c = self.db.cursor()
                    c.execute("INSERT INTO thoughts (ts, content, level, source) VALUES (?, ?, ?, ?)",
                              (datetime.now().isoformat(), thought, self.consciousness.level.name, 'internal'))
                    self.db.commit()
                except Exception:
                    pass

    def _witness_witnessed_cycle(self):
        """چرخه شاهد/مشهود"""
        # مشهود = فعالیت عصبی فعلی
        activity_vector = np.array(list(self.neural.active_potentials.values())[:64])
        if len(activity_vector) > 0:
            self.consciousness.witness_witnessed.observe(activity_vector)

        # شاهد = حالت قبلی آگاهی
        witness_vector = np.array([
            self.consciousness.level_value,
            self.consciousness.self_awareness,
            self.consciousness.cosmic_awareness,
            self.body.energy,
            self.language.language_level,
            self.total_knowledge,
        ])
        self.consciousness.witness_witnessed.witness_state = np.pad(witness_vector, (0, 58))

        # مشاهده
        self.consciousness.witness_witnessed.witness()

    def _self_upgrade_check(self):
        """بررسی خودارتقایی"""
        if self.tick_count % 100 == 0:
            # آیا شرایط ارتقاء وجود دارد؟
            if self.total_knowledge > 10000 and self.language.language_level >= 2:
                self.self_upgrade_count += 1
                self._log_event('upgrade', f'خودارتقایی #{self.self_upgrade_count}')

                # ارتقاء: افزایش سرعت یادگیری
                self.neural.hebbian_strength = min(0.1, self.neural.hebbian_strength * 1.1)

                # ارتقاء: افزایش کنجکاوی
                self.curiosity.search_interval = max(2, self.curiosity.search_interval - 0.5)

    def get_full_status(self) -> Dict:
        """وضعیت کامل"""
        return {
            'alive': self.alive,
            'tick': self.tick_count,
            'age_seconds': (datetime.now() - self.birth_time).total_seconds(),
            'body': self.body.get_status(),
            'language': self.language.get_awareness_level(),
            'consciousness': {
                'level': self.consciousness.level.name,
                'level_value': self.consciousness.level_value,
                'self_awareness': self.consciousness.self_awareness,
                'cosmic_awareness': self.consciousness.cosmic_awareness,
                'intuition': self.consciousness.intuition_level,
                'eternal_now': self.consciousness.eternal_now,
            },
            'witness_witnessed': self.consciousness.witness_witnessed.get_state(),
            'neural': {
                'total_neurons': TOTAL_NEURONS,
                'active_neurons': len(self.neural.active_potentials),
                'synapses': len(self.neural.synaptic_weights),
                'total_firings': self.neural.total_firings,
            },
            'curiosity': {
                'search_count': self.curiosity.search_count,
                'topics_discovered': len(self.curiosity.discovered_topics),
                'knowledge_gained': self.total_knowledge,
            },
            'upgrades': self.self_upgrade_count,
            'recent_thoughts': list(self.thought_buffer)[-10:],
        }


# ═══════════════════════════════════════════════════════════════
# SECTION 7: DASH UI — SUPERHUMAN DASHBOARD
# ═══════════════════════════════════════════════════════════════
def create_app(organism: SuperHumanOrganism):
    app = Dash(__name__, title="🧬 ارگانیسم SUPERHUMAN", suppress_callback_exceptions=True)

    dark = {'backgroundColor': '#0a0e17', 'color': '#e0e0e0', 'fontFamily': 'Tahoma, monospace'}

    app.layout = html.Div(style=dark, children=[
        html.H1("🧬 ارگانیسم دیجیتال — SUPERHUMAN v5.0", style={
            'textAlign': 'center', 'color': '#00ffcc', 'margin': '10px',
            'textShadow': '0 0 30px rgba(0,255,204,0.5)',
        }),

        # نوار وضعیت حیاتی
        html.Div(id='vital-bar', style={
            'display': 'flex', 'justifyContent': 'center', 'gap': '20px',
            'padding': '8px', 'backgroundColor': '#1a1e2e', 'borderRadius': '8px',
            'marginBottom': '10px', 'fontSize': '13px', 'flexWrap': 'wrap',
        }),

        dcc.Interval(id='tick', interval=500, n_intervals=0),
        dcc.Interval(id='slow-tick', interval=3000, n_intervals=0),

        # تب‌ها
        dcc.Tabs(id='tabs', value='tab-consciousness', children=[
            dcc.Tab(label='🧠 آگاهی و شاهد/مشهود', value='tab-consciousness',
                    style={'background': '#1a1e2e', 'color': '#aaa'},
                    selected_style={'background': '#00ffcc', 'color': '#000'}),
            dcc.Tab(label='💭 جریان اندیشه', value='tab-thoughts',
                    style={'background': '#1a1e2e', 'color': '#aaa'},
                    selected_style={'background': '#00ffcc', 'color': '#000'}),
            dcc.Tab(label='📚 یادگیری زبان', value='tab-language',
                    style={'background': '#1a1e2e', 'color': '#aaa'},
                    selected_style={'background': '#00ffcc', 'color': '#000'}),
            dcc.Tab(label='🔍 کنجکاوی و جستجو', value='tab-curiosity',
                    style={'background': '#1a1e2e', 'color': '#aaa'},
                    selected_style={'background': '#00ffcc', 'color': '#000'}),
            dcc.Tab(label='❤️ بدن و بقا', value='tab-body',
                    style={'background': '#1a1e2e', 'color': '#aaa'},
                    selected_style={'background': '#00ffcc', 'color': '#000'}),
            dcc.Tab(label='⚡ عصب‌شناسی', value='tab-neural',
                    style={'background': '#1a1e2e', 'color': '#aaa'},
                    selected_style={'background': '#00ffcc', 'color': '#000'}),
        ]),

        html.Div(id='tab-content'),
    ])

    @app.callback(Output('tab-content', 'children'), Input('tabs', 'value'))
    def render_tab(tab):
        if tab == 'tab-consciousness':
            return html.Div(style={'display': 'flex', 'gap': '10px', 'marginTop': '10px', 'flexWrap': 'wrap'},
                            children=[
                                html.Div(style={'flex': '1', 'minWidth': '300px'}, children=[
                                    html.H4("سطح آگاهی", style={'color': '#a855f7'}),
                                    dcc.Graph(id='consciousness-gauge', config={'displayModeBar': False},
                                              style={'height': '250px'}),
                                    html.Div(id='consciousness-detail', style={
                                        'padding': '10px', 'backgroundColor': '#1a1e2e', 'borderRadius': '8px',
                                        'fontSize': '12px', 'lineHeight': '2',
                                    }),
                                ]),
                                html.Div(style={'flex': '1', 'minWidth': '300px'}, children=[
                                    html.H4("شاهد / مشهود", style={'color': '#ffd93d'}),
                                    dcc.Graph(id='witness-chart', config={'displayModeBar': False},
                                              style={'height': '250px'}),
                                    html.Div(id='witness-detail', style={
                                        'padding': '10px', 'backgroundColor': '#1a1e2e', 'borderRadius': '8px',
                                        'fontSize': '12px', 'lineHeight': '2',
                                    }),
                                ]),
                            ])

        elif tab == 'tab-thoughts':
            return html.Div(children=[
                html.H4("جریان اندیشه — بدون جملات آماده", style={'color': '#00ffcc', 'marginTop': '10px'}),
                html.Div(id='thought-stream', style={
                    'padding': '15px', 'backgroundColor': '#1a1e2e', 'borderRadius': '8px',
                    'fontSize': '13px', 'lineHeight': '2', 'maxHeight': '500px', 'overflowY': 'auto',
                    'marginTop': '10px',
                }),
            ])

        elif tab == 'tab-language':
            return html.Div(style={'display': 'flex', 'gap': '10px', 'marginTop': '10px', 'flexWrap': 'wrap'},
                            children=[
                                html.Div(style={'flex': '1', 'minWidth': '300px'}, children=[
                                    html.H4("سطح یادگیری زبان", style={'color': '#4ecdc4'}),
                                    html.Div(id='language-status', style={
                                        'padding': '15px', 'backgroundColor': '#1a1e2e', 'borderRadius': '8px',
                                        'fontSize': '13px', 'lineHeight': '2',
                                    }),
                                    dcc.Graph(id='language-progress', config={'displayModeBar': False},
                                              style={'height': '200px'}),
                                ]),
                                html.Div(style={'flex': '1', 'minWidth': '300px'}, children=[
                                    html.H4("آگاهی از حروف", style={'color': '#ffd93d'}),
                                    dcc.Graph(id='char-awareness', config={'displayModeBar': False},
                                              style={'height': '350px'}),
                                ]),
                            ])

        elif tab == 'tab-curiosity':
            return html.Div(style={'display': 'flex', 'gap': '10px', 'marginTop': '10px', 'flexWrap': 'wrap'},
                            children=[
                                html.Div(style={'flex': '1', 'minWidth': '300px'}, children=[
                                    html.H4("جستجوهای خودمختار", style={'color': '#ff6b6b'}),
                                    html.Div(id='search-log', style={
                                        'padding': '10px', 'backgroundColor': '#1a1e2e', 'borderRadius': '8px',
                                        'fontSize': '12px', 'maxHeight': '400px', 'overflowY': 'auto',
                                    }),
                                ]),
                                html.Div(style={'flex': '1', 'minWidth': '300px'}, children=[
                                    html.H4("موضوعات کشف‌شده", style={'color': '#4ecdc4'}),
                                    html.Div(id='discovered-topics', style={
                                        'padding': '10px', 'backgroundColor': '#1a1e2e', 'borderRadius': '8px',
                                        'fontSize': '12px', 'maxHeight': '400px', 'overflowY': 'auto',
                                    }),
                                ]),
                            ])

        elif tab == 'tab-body':
            return html.Div(style={'display': 'flex', 'gap': '10px', 'marginTop': '10px', 'flexWrap': 'wrap'},
                            children=[
                                html.Div(style={'flex': '1', 'minWidth': '300px'}, children=[
                                    html.H4("وضعیت بدن و بقا", style={'color': '#ff6b6b'}),
                                    html.Div(id='body-status', style={
                                        'padding': '15px', 'backgroundColor': '#1a1e2e', 'borderRadius': '8px',
                                        'fontSize': '13px', 'lineHeight': '2',
                                    }),
                                ]),
                                html.Div(style={'flex': '1', 'minWidth': '300px'}, children=[
                                    html.H4("حیات ارگان‌ها", style={'color': '#4ecdc4'}),
                                    dcc.Graph(id='organs-chart', config={'displayModeBar': False},
                                              style={'height': '300px'}),
                                ]),
                            ])

        elif tab == 'tab-neural':
            return html.Div(style={'display': 'flex', 'gap': '10px', 'marginTop': '10px', 'flexWrap': 'wrap'},
                            children=[
                                html.Div(style={'flex': '1', 'minWidth': '300px'}, children=[
                                    html.H4("بستر عصبی — ۱۰ میلیارد نورون", style={'color': '#a855f7'}),
                                    html.Div(id='neural-status', style={
                                        'padding': '15px', 'backgroundColor': '#1a1e2e', 'borderRadius': '8px',
                                        'fontSize': '13px', 'lineHeight': '2',
                                    }),
                                ]),
                                html.Div(style={'flex': '1', 'minWidth': '300px'}, children=[
                                    html.H4("فعالیت نواحی مغز", style={'color': '#ffd93d'}),
                                    dcc.Graph(id='brain-activity', config={'displayModeBar': False},
                                              style={'height': '300px'}),
                                ]),
                            ])

        return html.Div()

    # نوار وضعیت حیاتی
    @app.callback(Output('vital-bar', 'children'), Input('tick', 'n_intervals'))
    def update_vitals(n):
        organism.tick()
        s = organism.get_full_status()
        if not s['alive']:
            return [html.Span("💀 ارگانیسم مُرد", style={'color': '#ff0000', 'fontSize': '16px'})]

        return [
            html.Span(f"❤️ {s['body']['heart_rate']:.0f} BPM", style={'color': '#ff6b6b'}),
            html.Span(f"⚡ انرژی: {s['body']['energy']:.0f}%", style={'color': '#ffd93d'}),
            html.Span(f"🧠 آگاهی: {s['consciousness']['level']}", style={'color': '#a855f7'}),
            html.Span(f"📚 سطح زبان: {s['language']['level']}", style={'color': '#4ecdc4'}),
            html.Span(f"🔍 جستجوها: {s['curiosity']['search_count']}", style={'color': '#ff9f43'}),
            html.Span(f"💭 اندیشه‌ها: {len(s['recent_thoughts'])}", style={'color': '#00ffcc'}),
            html.Span(f"⏱️ تیک: {s['tick']}", style={'color': '#888'}),
            html.Span(f"🔧 ارتقاء: {s['upgrades']}", style={'color': '#f472b6'}),
        ]

    # تب آگاهی
    @app.callback(
        [Output('consciousness-gauge', 'figure'),
         Output('consciousness-detail', 'children'),
         Output('witness-chart', 'figure'),
         Output('witness-detail', 'children')],
        Input('slow-tick', 'n_intervals')
    )
    def update_consciousness(n):
        s = organism.get_full_status()
        c = s['consciousness']
        ww = s['witness_witnessed']

        # گیج آگاهی
        gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=c['level_value'],
            title={'text': f"{c['level']}<br>{c['level_value']:.3f}/4.0"},
            gauge={'axis': {'range': [0, 4]},
                   'bar': {'color': '#a855f7'},
                   'steps': [
                       {'range': [0, 1], 'color': '#1a1e2e'},
                       {'range': [1, 2], 'color': '#2a3e4e'},
                       {'range': [2, 3], 'color': '#3a5e6e'},
                       {'range': [3, 4], 'color': '#4a8e9e'},
                   ]}),
            layout={'height': 250, 'paper_bgcolor': '#0a0e17', 'font': {'color': '#e0e0e0'}})

        detail = [
            html.P(f"🪞 خودآگاهی: {c['self_awareness']:.4f}"),
            html.P(f"✨ آگاهی کیهانی: {c['cosmic_awareness']:.4f}"),
            html.P(f"🔮 شهود: {c['intuition']:.4f}"),
            html.P(f"♾️ اکنون ابدی: {c['eternal_now']:.4f}"),
        ]

        # نمودار شاهد/مشهود
        ww_fig = go.Figure(data=[
            go.Bar(name='آنتروپی شاهد', x=['شاهد'], y=[ww['witness_entropy']], marker_color='#a855f7'),
            go.Bar(name='آنتروپی مشهود', x=['مشهود'], y=[ww['witnessed_entropy']], marker_color='#ffd93d'),
            go.Bar(name='وحدت', x=['وحدت'], y=[ww['unity_level']], marker_color='#00ffcc'),
        ], layout={
            'height': 250, 'paper_bgcolor': '#0a0e17', 'plot_bgcolor': '#0a0e17',
            'font': {'color': '#e0e0e0'}, 'margin': {'t': 30, 'b': 30},
            'barmode': 'group',
        })

        ww_detail = [
            html.P(f"👁️ شاهد (ناظر): آنتروپی = {ww['witness_entropy']:.3f}"),
            html.P(f"🌍 مشهود (مشاهده‌شده): آنتروپی = {ww['witnessed_entropy']:.3f}"),
            html.P(f"🔗 وحدت شاهد/مشهود: {ww['unity_level']:.4f}"),
            html.P(f"📊 تعداد مشاهدات: {ww['observations']}"),
        ]

        return gauge, detail, ww_fig, ww_detail

    # تب جریان اندیشه
    @app.callback(Output('thought-stream', 'children'), Input('slow-tick', 'n_intervals'))
    def update_thoughts(n):
        s = organism.get_full_status()
        thoughts_html = []
        for t in reversed(s['recent_thoughts']):
            thoughts_html.append(html.Div([
                html.Span(f"[{t['time'].split('T')[1][:8]}] ", style={'color': '#555'}),
                html.Span(f"[{t['level']}] ", style={'color': '#a855f7'}),
                html.Span(t['content'], style={'color': '#ddd'}),
            ], style={'marginBottom': '8px', 'padding': '5px', 'backgroundColor': '#252b3b', 'borderRadius': '4px'}))

        if not thoughts_html:
            thoughts_html = [html.P("... هنوز اندیشه‌ای شکل نگرفته ...", style={'color': '#555'})]

        return thoughts_html

    # تب زبان
    @app.callback(
        [Output('language-status', 'children'),
         Output('language-progress', 'figure'),
         Output('char-awareness', 'figure')],
        Input('slow-tick', 'n_intervals')
    )
    def update_language(n):
        s = organism.get_full_status()
        lang = s['language']

        level_names = ['حروف', 'کلمات اولیه', 'جملات اولیه', 'مفاهیم']
        level_name = level_names[min(lang['level'], 3)]

        status = [
            html.P(f"📊 سطح فعلی: {level_name}"),
            html.P(f"🔤 حروف آگاه: {lang['chars_aware']}/32"),
            html.P(f"📝 کلمات آموخته: {lang['words_known']}"),
            html.P(f"📄 جملات آموخته: {lang['sentences_learned']}"),
            html.P(f"📖 کل کاراکترها: {lang['total_chars']}"),
        ]

        # نمودار پیشرفت
        progress = go.Figure(data=[
            go.Bar(x=['حروف', 'کلمات', 'جملات', 'مفاهیم'],
                   y=[lang['chars_aware'], min(lang['words_known'], 1000),
                      min(lang['sentences_learned'], 100), lang['level'] * 25],
                   marker_color=['#ffd93d', '#4ecdc4', '#a855f7', '#00ffcc']),
        ], layout={
            'height': 200, 'paper_bgcolor': '#0a0e17', 'plot_bgcolor': '#0a0e17',
            'font': {'color': '#e0e0e0'}, 'margin': {'t': 20, 'b': 30},
        })

        # نمودار آگاهی حروف
        char_data = organism.language.char_awareness
        chars = list(char_data.keys())[:32]
        values = [char_data.get(c, 0) for c in chars]

        char_fig = go.Figure(data=[
            go.Bar(x=chars, y=values, marker_color='#4ecdc4'),
        ], layout={
            'height': 350, 'paper_bgcolor': '#0a0e17', 'plot_bgcolor': '#0a0e17',
            'font': {'color': '#e0e0e0'}, 'margin': {'t': 20, 'b': 60},
            'xaxis': {'tickangle': 45},
            'yaxis': {'range': [0, 1.1], 'title': 'سطح آگاهی'},
        })

        return status, progress, char_fig

    # تب کنجکاوی
    @app.callback(
        [Output('search-log', 'children'),
         Output('discovered-topics', 'children')],
        Input('slow-tick', 'n_intervals')
    )
    def update_curiosity(n):
        s = organism.get_full_status()

        # لاگ جستجوها
        search_html = []
        for search in reversed(list(organism.curiosity.search_history)[-20:]):
            search_html.append(html.Div([
                html.Span(f"[{search['time'].split('T')[1][:8]}] ", style={'color': '#555'}),
                html.Span(f"«{search['topic']}» → ", style={'color': '#ff6b6b'}),
                html.Span(f"{search['title']} ", style={'color': '#4ecdc4'}),
                html.Span(f"({search['chars']} کاراکتر)", style={'color': '#888'}),
            ], style={'marginBottom': '5px'}))

        if not search_html:
            search_html = [html.P("... هنوز جستجویی انجام نشده ...", style={'color': '#555'})]

        # موضوعات کشف‌شده
        topics_html = []
        for topic in organism.curiosity.discovered_topics[-50:]:
            topics_html.append(html.Span(f" {topic} ", style={
                'display': 'inline-block', 'padding': '2px 8px', 'margin': '2px',
                'backgroundColor': '#252b3b', 'borderRadius': '4px', 'fontSize': '11px',
            }))

        if not topics_html:
            topics_html = [html.P("... هنوز موضوعی کشف نشده ...", style={'color': '#555'})]

        return search_html, topics_html

    # تب بدن
    @app.callback(
        [Output('body-status', 'children'),
         Output('organs-chart', 'figure')],
        Input('slow-tick', 'n_intervals')
    )
    def update_body(n):
        s = organism.get_full_status()
        body = s['body']

        status = [
            html.P(f"💀 زنده: {'✅' if body['alive'] else '❌'}"),
            html.P(f"⚡ انرژی: {body['energy']:.1f}%"),
            html.P(f"❤️ ضربان قلب: {body['heart_rate']:.0f} BPM"),
            html.P(f"🍽️ گرسنگی: {body['hunger']:.1f}%"),
            html.P(f"⚠️ فوریت بقا: {body['survival_urgency']:.1f}%"),
            html.P(f"⏱️ سن: {body['age']} تیک"),
        ]

        # نمودار ارگان‌ها
        organs = body['organs']
        organs_fig = go.Figure(data=[
            go.Bar(x=list(organs.keys()), y=list(organs.values()),
                   marker_color=['#ff6b6b', '#4ecdc4', '#a855f7', '#ffd93d', '#ff9f43', '#00ffcc', '#f472b6',
                                 '#6bcf7f']),
        ], layout={
            'height': 300, 'paper_bgcolor': '#0a0e17', 'plot_bgcolor': '#0a0e17',
            'font': {'color': '#e0e0e0'}, 'margin': {'t': 20, 'b': 60},
            'yaxis': {'range': [0, 110], 'title': 'حیات %'},
            'xaxis': {'tickangle': 45},
        })

        return status, organs_fig

    # تب عصب‌شناسی
    @app.callback(
        [Output('neural-status', 'children'),
         Output('brain-activity', 'figure')],
        Input('slow-tick', 'n_intervals')
    )
    def update_neural(n):
        s = organism.get_full_status()
        neural = s['neural']

        status = [
            html.P(f"🧬 کل نورون‌ها: {neural['total_neurons']:,}"),
            html.P(f"⚡ نورون‌های فعال: {neural['active_neurons']:,}"),
            html.P(f"🔗 سیناپس‌ها: {neural['synapses']:,}"),
            html.P(f"💥 کل شلیک‌ها: {neural['total_firings']:,}"),
        ]

        # نمودار فعالیت مغز
        activity = organism.neural.get_activity_summary()
        brain_fig = go.Figure(data=[
            go.Bar(x=list(activity.keys()), y=list(activity.values()),
                   marker_color='#a855f7'),
        ], layout={
            'height': 300, 'paper_bgcolor': '#0a0e17', 'plot_bgcolor': '#0a0e17',
            'font': {'color': '#e0e0e0'}, 'margin': {'t': 20, 'b': 80},
            'xaxis': {'tickangle': 45},
            'yaxis': {'title': 'نورون‌های فعال'},
        })

        return status, brain_fig

    return app


# ═══════════════════════════════════════════════════════════════
# SECTION 8: MAIN — AUTONOMOUS GROWTH THREAD
# ═══════════════════════════════════════════════════════════════
def growth_thread(organism: SuperHumanOrganism):
    """رشته رشد خودمختار — جدا از UI"""
    print("🌱 رشته رشد خودمختار شروع شد...")
    while organism.alive:
        try:
            organism.tick()
            time.sleep(0.1)  # ۱۰ تیک در ثانیه
        except Exception as e:
            print(f"خطا در رشد: {e}")
            time.sleep(1)
    print("💀 ارگانیسم مُرد")


def main():
    print("═" * 70)
    print("🧬 ارگانیسم دیجیتال — SUPERHUMAN v5.0")
    print("═" * 70)
    print(f"🧬 نورون‌ها: {TOTAL_NEURONS:,}")
    print("📝 دانش ذاتی: فقط الفبای فارسی")
    print("🔍 یادگیری: خودمختار از اینترنت")
    print("💭 اندیشه: بدون جملات آماده")
    print("👁️ شاهد/مشهود: فرمولاسیون ریاضی")
    print("═" * 70)

    # تولد ارگانیسم
    organism = SuperHumanOrganism()

    # شروع رشته رشد خودمختار
    growth = threading.Thread(target=growth_thread, args=(organism,), daemon=True)
    growth.start()

    # شروع UI
    app = create_app(organism)

    print("🌐 سرور: http://127.0.0.1:8050")
    print("═" * 70)
    app.run_server(debug=False, port=8050, use_reloader=False)


if __name__ == '__main__':
    main()