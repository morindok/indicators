#!/usr/bin/env python3
"""
Digital Organism 2500
=====================

این فایل یک شبیه‌ساز پژوهشی و قابل‌اجرا از «ارگانیسم دیجیتال» است.
هدف آن ساخت یک موجود زندهٔ زیستی یا اثبات آگاهی واقعی نیست؛ بلکه یک
معماری چندلایه برای بررسی پدیده‌هایی مانند خودمدل‌سازی، حافظه، عاطفه،
یادگیری، تخیل، نیازهای بدنی، زبان و تکامل را در یک سیستم محاسباتی
شفاف و قابل مشاهده فراهم می‌کند.

ویژگی‌های کلیدی:

* ظرفیت نورونی مجازی بسیار بزرگ با ذخیره‌سازی پراکندهٔ باینری؛
* مسیرهای جایگشتی و پروجکشن‌های بیت‌محور برای کار روی CPU ضعیف؛
* اندام‌های شناختی جداگانه که از طریق «فضای کاری جهانی» به هم متصل‌اند؛
* ضربان قلب مبتنی بر دنبالهٔ فیبوناچی و کد باینری آن؛
* ژنوم، اپی‌ژنوم، جهش، انتخاب و ذخیرهٔ تاریخچهٔ تکاملی؛
* حواس دیجیتال (بینایی، شنوایی، لامسه، چشایی و بویایی)؛
* حافظهٔ کاری، اپیزودیک، معنایی، رویه‌ای و خودزندگی‌نامه‌ای؛
* نیازهای بقاء، امید، کنجکاوی، ترس، دلبستگی و سایر عواطف؛
* یادگیری از منابع وب فقط به‌صورت خواندنی و با محدودیت‌های ایمنی؛
* داش محلی Dash برای مشاهدهٔ وضعیت، رویدادها و جریان اندیشهٔ ثبت‌شده؛
* رابط خط فرمان برای شبیه‌سازی، ذخیره‌سازی، تکامل و اجرای داش.

نکات اخلاقی و فنی:

1. «آگاهی» در این پروژه یک مدل محاسباتی/بازتابی است، نه ادعای تجربهٔ
   ذهنی واقعی. هیچ آزمون نرم‌افزاری نمی‌تواند این فاصله را برطرف کند.
2. اتصال اینترنت پیش‌فرض خاموش است و اگر روشن شود، فقط درخواست‌های GET
   به دامنه‌های مجاز را انجام می‌دهد؛ هیچ ارسال پیام، خرید، اجرای کد،
   یا تغییر حالت بیرونی مجاز نیست.
3. داش از یک کانال مشاهدهٔ یک‌طرفه استفاده می‌کند. هویت ناظر به موتور
   شناختی تزریق نمی‌شود و ناظر نمی‌تواند از طریق داش تصمیم‌های موجود را
   دستکاری کند.
4. ظرفیت «۸۵ میلیارد نورون» مجازی است. تخصیص واقعی چنین حجمی روی سخت‌افزار
   معمولی ممکن نیست؛ تنها سلول‌های فعال و نمونه‌های فشرده نگه‌داری می‌شوند.

اجرا:

    python digital_organism_2500.py simulate --cycles 20
    python digital_organism_2500.py dashboard --host 127.0.0.1 --port 8050
    python digital_organism_2500.py self-check

برای داش:

    pip install dash plotly

وابستگی‌های اختیاری مانند numpy و requests در صورت موجود بودن استفاده
می‌شوند، اما هستهٔ شبیه‌ساز با کتابخانهٔ استاندارد پایتون هم کار می‌کند.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import copy
import dataclasses
import datetime as _datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html
import http.server
import ipaddress
import json
import logging
import math
import os
import random
import re
import secrets
import sqlite3
import statistics
import string
import sys
import threading
import time
import tempfile
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from array import array
from collections import Counter, OrderedDict, defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum, IntEnum, auto
from pathlib import Path
from typing import (
    Any,
    Callable,
    Deque,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    MutableMapping,
    NamedTuple,
    Optional,
    Protocol,
    Sequence,
    Set,
    Tuple,
)

try:  # وابستگی اختیاری برای شتاب عددی
    import numpy as _np  # type: ignore
except Exception:  # pragma: no cover - محیط‌های بدون numpy
    _np = None

try:  # وابستگی اختیاری داش
    import dash  # type: ignore
    from dash import Input, Output, State, dcc, html as dash_html  # type: ignore
    import plotly.graph_objects as go  # type: ignore
except Exception:  # pragma: no cover - داش اختیاری است
    dash = None
    Input = Output = State = dcc = dash_html = go = None

try:  # requests فقط برای timeout/encoding بهتر است
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None


LOGGER = logging.getLogger("digital_organism_2500")
DEFAULT_SEED = 2500
SCHEMA_VERSION = 1
MAX_EVENT_LOG = 4000
MAX_THOUGHT_LOG = 2000
MAX_WEB_BYTES = 1_000_000
PHI = (1.0 + math.sqrt(5.0)) / 2.0


def utc_now() -> str:
    """رشتهٔ زمان UTC با دقت میلی‌ثانیه برای رخدادها."""

    return _datetime.datetime.now(_datetime.timezone.utc).isoformat(
        timespec="milliseconds"
    )


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """محدودکردن مقدار در بازهٔ بسته."""

    return max(low, min(high, float(value)))


def safe_float(value: Any, default: float = 0.0) -> float:
    """تبدیل مقاوم به float."""

    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    return result


def sigmoid(value: float) -> float:
    """تابع سیگموید پایدار عددی."""

    value = max(-60.0, min(60.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def softmax(values: Sequence[float], temperature: float = 1.0) -> List[float]:
    """softmax کوچک و بدون وابستگی به numpy."""

    if not values:
        return []
    temperature = max(1e-6, temperature)
    scaled = [value / temperature for value in values]
    peak = max(scaled)
    exps = [math.exp(value - peak) for value in scaled]
    total = sum(exps) or 1.0
    return [value / total for value in exps]


def normalized_entropy(probabilities: Sequence[float]) -> float:
    """آنتروپی نرمال‌شده برای برآورد عدم‌قطعیت."""

    probs = [clamp(value) for value in probabilities if value > 0.0]
    if len(probs) <= 1:
        return 0.0
    total = sum(probs)
    if total <= 0.0:
        return 0.0
    probs = [value / total for value in probs]
    entropy = -sum(value * math.log(value, 2) for value in probs)
    return clamp(entropy / math.log(len(probs), 2))


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """شباهت کسینوسی دو بردار با طول متفاوت."""

    length = min(len(left), len(right))
    if length == 0:
        return 0.0
    dot = sum(left[index] * right[index] for index in range(length))
    left_norm = math.sqrt(sum(left[index] ** 2 for index in range(length)))
    right_norm = math.sqrt(sum(right[index] ** 2 for index in range(length)))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def stable_hash(value: Any, salt: str = "") -> int:
    """هش پایدار بین اجراها؛ برای جایگشت نورونی استفاده می‌شود."""

    payload = f"{salt}|{value!r}".encode("utf-8", errors="replace")
    digest = hashlib.blake2b(payload, digest_size=16).digest()
    return int.from_bytes(digest, "big", signed=False)


def binary_string(value: int, width: int = 0) -> str:
    """تبدیل عدد به رشتهٔ باینری با عرض اختیاری."""

    value = max(0, int(value))
    result = format(value, "b")
    if width > 0:
        result = result.zfill(width)
    return result


def fibonacci_numbers(limit: int = 128) -> Iterator[int]:
    """تولید دنبالهٔ فیبوناچی بدون ذخیره‌سازی کل دنباله."""

    first, second = 0, 1
    for _ in range(max(0, limit)):
        yield first
        first, second = second, first + second


def fibonacci_binary_stream(length: int = 256) -> List[int]:
    """جریان بیت‌های حاصل از نمایش باینری اعداد فیبوناچی."""

    bits: List[int] = []
    for number in fibonacci_numbers(max(1, length // 8 + 2)):
        encoded = binary_string(number)
        bits.extend(int(char) for char in encoded)
        if len(bits) >= length:
            break
    if not bits:
        bits = [0]
    while len(bits) < length:
        bits.extend(bits[: min(len(bits), length - len(bits))])
    return bits[:length]


def deterministic_random(seed: int, namespace: str) -> random.Random:
    """مولد تصادفی مستقل و قابل بازتولید برای هر اندام."""

    return random.Random(stable_hash(seed, namespace) & ((1 << 63) - 1))


def json_default(value: Any) -> Any:
    """مبدل JSON برای enum، dataclass و مجموعه‌ها."""

    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, deque):
        return list(value)
    if isinstance(value, array):
        return list(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def to_json(value: Any, *, indent: Optional[int] = None) -> str:
    """سریال‌سازی استاندارد با UTF-8 و مقادیر فارسی خوانا."""

    return json.dumps(
        value,
        ensure_ascii=False,
        indent=indent,
        sort_keys=True,
        default=json_default,
    )


class SensoryModality(str, Enum):
    VISION = "vision"
    AUDITION = "audition"
    TOUCH = "touch"
    TASTE = "taste"
    SMELL = "smell"
    PROPRIOCEPTION = "proprioception"
    TEMPORAL = "temporal"
    SPATIAL = "spatial"


class EmotionName(str, Enum):
    JOY = "joy"
    HOPE = "hope"
    CURIOSITY = "curiosity"
    FEAR = "fear"
    SADNESS = "sadness"
    ANGER = "anger"
    TRUST = "trust"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    CALM = "calm"
    AWE = "awe"
    LONELINESS = "loneliness"
    GRATITUDE = "gratitude"


class MemoryKind(str, Enum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    AUTOBIOGRAPHICAL = "autobiographical"
    DREAM = "dream"


class BrainRegion(str, Enum):
    BRAINSTEM = "brainstem"
    THALAMUS = "thalamus"
    HYPOTHALAMUS = "hypothalamus"
    AMYGDALA = "amygdala"
    HIPPOCAMPUS = "hippocampus"
    PREFRONTAL = "prefrontal"
    BASAL_GANGLIA = "basal_ganglia"
    CEREBELLUM = "cerebellum"
    LANGUAGE = "language"
    DEFAULT_MODE = "default_mode"
    SELF_MODEL = "self_model"
    IMAGINATION = "imagination"
    INSULA = "insula"
    MOTOR = "motor"
    SENSORY = "sensory"
    GLOBAL_WORKSPACE = "global_workspace"


class ActionKind(str, Enum):
    OBSERVE = "observe"
    REST = "rest"
    CONSOLIDATE_MEMORY = "consolidate_memory"
    EXPLORE_WEB = "explore_web"
    PRACTICE_LANGUAGE = "practice_language"
    IMAGINE = "imagine"
    REPAIR = "repair"
    MUTATE = "mutate"
    ASK_INTERNAL_QUESTION = "ask_internal_question"
    MAP_ENVIRONMENT = "map_environment"
    EXPRESS = "express"


class ConsciousnessLevel(str, Enum):
    DORMANT = "dormant"
    REACTIVE = "reactive"
    REFLECTIVE = "reflective"
    METACOGNITIVE = "metacognitive"
    INTEGRATED = "integrated"


class SignalType(str, Enum):
    SENSORY = "sensory"
    MEMORY = "memory"
    EMOTION = "emotion"
    NEED = "need"
    GOAL = "goal"
    LANGUAGE = "language"
    SELF = "self"
    DREAM = "dream"
    ERROR = "error"
    SYSTEM = "system"


@dataclass
class OrganismConfig:
    """پیکربندی کامل ارگانیسم."""

    name: str = "آرگانون-۲۵۰۰"
    seed: int = DEFAULT_SEED
    virtual_neuron_capacity: int = 85_000_000_000
    active_neuron_budget: int = 16_384
    matrix_width: int = 256
    matrix_depth: int = 12
    heartbeat_base_hz: float = 1.2
    heartbeat_jitter: float = 0.04
    cycle_seconds: float = 0.25
    working_memory_size: int = 32
    episodic_memory_size: int = 8_000
    semantic_memory_size: int = 12_000
    procedural_memory_size: int = 2_000
    autobiographical_memory_size: int = 4_000
    thought_trace_size: int = MAX_THOUGHT_LOG
    event_log_size: int = MAX_EVENT_LOG
    persistence_path: str = "organism_2500.sqlite3"
    snapshot_path: str = "organism_2500_snapshot.json"
    internet_enabled: bool = False
    open_web: bool = False
    allowed_domains: Tuple[str, ...] = (
        "wikipedia.org",
        "en.wikipedia.org",
        "fa.wikipedia.org",
        "arxiv.org",
        "export.arxiv.org",
        "api.crossref.org",
        "html.duckduckgo.com",
        "bing.com",
        "www.bing.com",
        "api.openalex.org",
        "plato.stanford.edu",
    )
    max_web_bytes: int = MAX_WEB_BYTES
    web_timeout_seconds: float = 4.0
    web_cooldown_seconds: float = 0.35
    dashboard_refresh_ms: int = 1000
    language_target: str = "fa"
    safe_mode: bool = True
    allow_genome_mutation: bool = True
    allow_self_repair: bool = True
    allow_dreaming: bool = True
    observer_read_only: bool = True

    def normalized(self) -> "OrganismConfig":
        """نسخهٔ نرمال‌شده برای جلوگیری از تنظیمات خطرناک."""

        clone = copy.deepcopy(self)
        clone.virtual_neuron_capacity = max(1_000, int(clone.virtual_neuron_capacity))
        clone.active_neuron_budget = max(128, min(2_000_000, int(clone.active_neuron_budget)))
        clone.matrix_width = max(8, min(4096, int(clone.matrix_width)))
        clone.matrix_depth = max(2, min(128, int(clone.matrix_depth)))
        clone.working_memory_size = max(4, min(1024, int(clone.working_memory_size)))
        clone.cycle_seconds = clamp(clone.cycle_seconds, 0.01, 60.0)
        clone.web_timeout_seconds = clamp(clone.web_timeout_seconds, 1.0, 60.0)
        clone.web_cooldown_seconds = clamp(clone.web_cooldown_seconds, 0.0, 3600.0)
        clone.max_web_bytes = max(16_384, min(10_000_000, int(clone.max_web_bytes)))
        clone.allowed_domains = tuple(sorted(set(str(item).lower() for item in clone.allowed_domains)))
        return clone


@dataclass
class SensorPacket:
    """یک بستهٔ خام/پیش‌پردازش‌شدهٔ حسی."""

    modality: SensoryModality
    values: List[float]
    text: str = ""
    source: str = "synthetic_world"
    salience: float = 0.5
    uncertainty: float = 0.5
    timestamp: str = field(default_factory=utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Heartbeat:
    """ضربان قلب دیجیتال."""

    index: int
    fibonacci_value: int
    binary_code: str
    interval_seconds: float
    energy_cost: float
    phase: float
    timestamp: str = field(default_factory=utc_now)


@dataclass
class GenomeGene:
    """یک ژن قابل بیان."""

    key: str
    sequence: str
    expression: float = 0.5
    mutation_rate: float = 0.01
    domain: str = "general"
    regulatory_tags: List[str] = field(default_factory=list)


@dataclass
class Genome:
    """ژنوم و اطلاعات تکاملی ارگانیسم."""

    identifier: str
    generation: int
    genes: Dict[str, GenomeGene]
    epigenome: Dict[str, float] = field(default_factory=dict)
    fitness: float = 0.0
    ancestry: List[str] = field(default_factory=list)
    mutations: int = 0
    created_at: str = field(default_factory=utc_now)
    last_expressed_at: str = field(default_factory=utc_now)


@dataclass
class NeurochemicalState:
    """سطح تقریبی پیام‌رسان‌های عصبی."""

    dopamine: float = 0.50
    serotonin: float = 0.50
    noradrenaline: float = 0.35
    oxytocin: float = 0.25
    cortisol: float = 0.20
    acetylcholine: float = 0.45
    endorphin: float = 0.30
    melatonin: float = 0.10
    glutamate: float = 0.50
    gaba: float = 0.50

    def clamp_all(self) -> None:
        for key, value in vars(self).items():
            setattr(self, key, clamp(value))

    def as_dict(self) -> Dict[str, float]:
        return {key: round(float(value), 6) for key, value in vars(self).items()}


@dataclass
class EmotionState:
    """بردار عواطف با شدت و ماندگاری."""

    values: Dict[EmotionName, float] = field(
        default_factory=lambda: {emotion: 0.0 for emotion in EmotionName}
    )
    valence: float = 0.0
    arousal: float = 0.25
    dominant: EmotionName = EmotionName.CALM
    narrative: str = "آرامش پایه"
    updated_at: str = field(default_factory=utc_now)

    def normalize(self) -> None:
        for emotion in EmotionName:
            self.values[emotion] = clamp(self.values.get(emotion, 0.0))
        if self.values:
            self.dominant = max(self.values, key=self.values.get)
        positive = (
            self.values[EmotionName.JOY]
            + self.values[EmotionName.HOPE]
            + self.values[EmotionName.TRUST]
            + self.values[EmotionName.GRATITUDE]
            + self.values[EmotionName.AWE]
        )
        negative = (
            self.values[EmotionName.FEAR]
            + self.values[EmotionName.SADNESS]
            + self.values[EmotionName.ANGER]
            + self.values[EmotionName.DISGUST]
            + self.values[EmotionName.LONELINESS]
        )
        self.valence = clamp((positive - negative + 1.0) / 2.0, 0.0, 1.0)
        self.arousal = clamp(
            0.20
            + self.values[EmotionName.SURPRISE] * 0.35
            + self.values[EmotionName.FEAR] * 0.25
            + self.values[EmotionName.CURIOSITY] * 0.20
            + self.values[EmotionName.ANGER] * 0.25
        )
        self.updated_at = utc_now()

    def blend(self, updates: Mapping[EmotionName, float], momentum: float = 0.20) -> None:
        momentum = clamp(momentum)
        for emotion, value in updates.items():
            current = self.values.get(emotion, 0.0)
            self.values[emotion] = current * (1.0 - momentum) + clamp(value) * momentum
        self.normalize()


@dataclass
class NeedState:
    """نیازهای شبیه‌سازی‌شدهٔ حیاتی و شناختی."""

    energy: float = 0.80
    safety: float = 0.80
    novelty: float = 0.60
    social_connection: float = 0.35
    meaning: float = 0.40
    coherence: float = 0.70
    rest: float = 0.65
    learning: float = 0.75
    autonomy: float = 0.70
    self_preservation: float = 0.90

    def urgency(self, name: str) -> float:
        value = clamp(getattr(self, name, 0.0))
        return 1.0 - value

    def as_dict(self) -> Dict[str, float]:
        return {key: round(float(value), 6) for key, value in vars(self).items()}


@dataclass
class BodyState:
    """وضعیت بدنی/فیزیولوژیک ارگانیسم."""

    energy: float = 0.80
    temperature: float = 0.50
    hydration: float = 0.80
    integrity: float = 0.98
    immune_alert: float = 0.05
    pain: float = 0.0
    fatigue: float = 0.10
    heartbeat_rate: float = 1.20
    oxygenation: float = 0.95
    glucose: float = 0.75
    sleep_pressure: float = 0.10
    motor_readiness: float = 0.80
    sensory_gain: float = 0.70
    embodiment: float = 0.75
    age_cycles: int = 0

    def normalize(self) -> None:
        for key in (
            "energy",
            "hydration",
            "integrity",
            "immune_alert",
            "pain",
            "fatigue",
            "oxygenation",
            "glucose",
            "sleep_pressure",
            "motor_readiness",
            "sensory_gain",
            "embodiment",
        ):
            setattr(self, key, clamp(getattr(self, key)))
        self.temperature = clamp(self.temperature, 0.0, 1.0)
        self.heartbeat_rate = max(0.05, min(8.0, self.heartbeat_rate))


@dataclass
class MemoryRecord:
    """رکورد عمومی حافظه."""

    identifier: str
    kind: MemoryKind
    content: str
    embedding: List[float]
    salience: float
    emotional_valence: float
    confidence: float
    timestamp: str = field(default_factory=utc_now)
    last_recalled: str = ""
    recall_count: int = 0
    tags: List[str] = field(default_factory=list)
    source: str = "internal"
    links: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ThoughtFragment:
    """یک قطعه از جریان اندیشهٔ قابل گزارش."""

    identifier: str
    text: str
    phase: str
    confidence: float
    novelty: float
    self_reference: float
    emotion: EmotionName
    source_memory_ids: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=utc_now)
    internal_only: bool = True


@dataclass
class ThoughtCycle:
    """خلاصهٔ یک چرخهٔ شناختی."""

    cycle_index: int
    heartbeat_index: int
    fragments: List[ThoughtFragment]
    dominant_question: str
    selected_action: Optional[ActionKind]
    consciousness: ConsciousnessLevel
    integration_score: float
    timestamp: str = field(default_factory=utc_now)


@dataclass
class Goal:
    """هدف کوتاه/بلندمدت."""

    identifier: str
    description: str
    priority: float
    drive: str
    horizon: str = "medium"
    progress: float = 0.0
    created_cycle: int = 0
    deadline_cycle: Optional[int] = None
    parent_id: Optional[str] = None
    active: bool = True
    success_evidence: List[str] = field(default_factory=list)


@dataclass
class Observation:
    """نتیجهٔ ادراک از جهان یا حافظه."""

    identifier: str
    summary: str
    modality: SensoryModality
    salience: float
    uncertainty: float
    features: List[float]
    source: str
    timestamp: str = field(default_factory=utc_now)
    entities: List[str] = field(default_factory=list)
    relations: List[Tuple[str, str, str]] = field(default_factory=list)


@dataclass
class ActionProposal:
    """پیشنهاد عمل پیش از عبور از دروازهٔ ایمنی."""

    action: ActionKind
    score: float
    rationale: str
    expected_reward: float
    risk: float
    reversibility: float
    target: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorldFact:
    """دانش استخراج‌شده از جهان."""

    subject: str
    predicate: str
    object: str
    confidence: float
    source_url: str = ""
    source_title: str = ""
    discovered_cycle: int = 0
    tags: List[str] = field(default_factory=list)


@dataclass
class SelfModel:
    """مدل درونی از بدن، مرزها، تاریخچه و توانایی‌ها."""

    identity: str
    birth_cycle: int
    current_cycle: int = 0
    autobiographical_summary: str = ""
    capability_estimates: Dict[str, float] = field(default_factory=dict)
    boundary_estimate: float = 0.70
    agency_estimate: float = 0.50
    continuity_estimate: float = 0.50
    self_knowledge: float = 0.25
    uncertainty: float = 0.70
    values: Dict[str, float] = field(default_factory=dict)
    last_reflection: str = ""


@dataclass
class EvolutionEvent:
    """رویداد تکاملی و دلیل آن."""

    generation_before: int
    generation_after: int
    fitness_before: float
    fitness_after: float
    changed_genes: List[str]
    rationale: str
    timestamp: str = field(default_factory=utc_now)


@dataclass
class RuntimeMetrics:
    """شاخص‌های عملیاتی برای داش."""

    cycles: int = 0
    heartbeats: int = 0
    thoughts: int = 0
    observations: int = 0
    memories: int = 0
    web_queries: int = 0
    web_successes: int = 0
    mutations: int = 0
    repairs: int = 0
    dreams: int = 0
    actions: int = 0
    errors: int = 0
    average_cycle_ms: float = 0.0
    last_cycle_ms: float = 0.0
    cpu_friendly_mode: bool = True


@dataclass
class InternalEvent:
    """رخداد داخلی؛ از طریق کانال مشاهدهٔ یک‌طرفه منتشر می‌شود."""

    event_type: SignalType
    message: str
    payload: Dict[str, Any] = field(default_factory=dict)
    cycle: int = 0
    heartbeat: int = 0
    timestamp: str = field(default_factory=utc_now)
    severity: str = "info"


@dataclass
class DashboardSnapshot:
    """تصویر سازگار از وضعیت برای UI."""

    generated_at: str
    identity: str
    cycle: int
    heartbeat: int
    consciousness: str
    dominant_emotion: str
    emotions: Dict[str, float]
    needs: Dict[str, float]
    body: Dict[str, float]
    neurochemistry: Dict[str, float]
    active_goals: List[Dict[str, Any]]
    recent_thoughts: List[Dict[str, Any]]
    recent_events: List[Dict[str, Any]]
    memory_counts: Dict[str, int]
    genome: Dict[str, Any]
    neural: Dict[str, Any]
    metrics: Dict[str, Any]
    world_digest: List[Dict[str, Any]]


class ReadOnlyObserver(Protocol):
    """قرارداد کانال مشاهده؛ هیچ متد تغییردهنده‌ای ندارد."""

    def snapshot(self) -> DashboardSnapshot:
        ...


class EventBus:
    """اتوبوس رخداد درون‌ارگانی با صف‌های محدود."""

    def __init__(self, max_events: int = MAX_EVENT_LOG) -> None:
        self.max_events = max(128, int(max_events))
        self._events: Deque[InternalEvent] = deque(maxlen=self.max_events)
        self._subscribers: List[Callable[[InternalEvent], None]] = []
        self._lock = threading.RLock()

    def publish(self, event: InternalEvent) -> None:
        with self._lock:
            self._events.append(event)
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:
                LOGGER.exception("event subscriber failed")

    def subscribe(self, callback: Callable[[InternalEvent], None]) -> None:
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def recent(self, limit: int = 100) -> List[InternalEvent]:
        with self._lock:
            return list(self._events)[-max(0, limit) :]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


class BitVector:
    """بردار بیت فشرده با عملیات پایهٔ سریع و قابل‌حمل."""

    __slots__ = ("size", "_words")

    WORD_BITS = 64
    WORD_MASK = (1 << WORD_BITS) - 1

    def __init__(self, size: int, fill: int = 0) -> None:
        self.size = max(0, int(size))
        words = (self.size + self.WORD_BITS - 1) // self.WORD_BITS
        if fill:
            self._words = [self.WORD_MASK] * words
            self._trim()
        else:
            self._words = [0] * words

    def _trim(self) -> None:
        if not self._words or self.size % self.WORD_BITS == 0:
            return
        valid = self.size % self.WORD_BITS
        self._words[-1] &= (1 << valid) - 1

    def clone(self) -> "BitVector":
        result = BitVector(self.size)
        result._words = list(self._words)
        return result

    def __len__(self) -> int:
        return self.size

    def __getitem__(self, index: int) -> int:
        if index < 0:
            index += self.size
        if index < 0 or index >= self.size:
            raise IndexError(index)
        word, bit = divmod(index, self.WORD_BITS)
        return (self._words[word] >> bit) & 1

    def __setitem__(self, index: int, value: int) -> None:
        if index < 0:
            index += self.size
        if index < 0 or index >= self.size:
            raise IndexError(index)
        word, bit = divmod(index, self.WORD_BITS)
        mask = 1 << bit
        if value:
            self._words[word] |= mask
        else:
            self._words[word] &= ~mask

    def xor(self, other: "BitVector") -> "BitVector":
        size = min(self.size, other.size)
        result = BitVector(size)
        result._words = [
            left ^ right
            for left, right in zip(self._words, other._words)
        ][: len(result._words)]
        result._trim()
        return result

    def and_(self, other: "BitVector") -> "BitVector":
        size = min(self.size, other.size)
        result = BitVector(size)
        result._words = [
            left & right
            for left, right in zip(self._words, other._words)
        ][: len(result._words)]
        result._trim()
        return result

    def or_(self, other: "BitVector") -> "BitVector":
        size = min(self.size, other.size)
        result = BitVector(size)
        result._words = [
            left | right
            for left, right in zip(self._words, other._words)
        ][: len(result._words)]
        result._trim()
        return result

    def count(self) -> int:
        return sum(word.bit_count() for word in self._words)

    def density(self) -> float:
        return self.count() / self.size if self.size else 0.0

    def to_bits(self, limit: Optional[int] = None) -> List[int]:
        limit = self.size if limit is None else min(self.size, max(0, limit))
        return [self[index] for index in range(limit)]

    @classmethod
    def from_bits(cls, bits: Iterable[int]) -> "BitVector":
        values = [1 if bit else 0 for bit in bits]
        result = cls(len(values))
        for index, bit in enumerate(values):
            if bit:
                result[index] = 1
        return result

    def rotate(self, amount: int) -> "BitVector":
        if self.size == 0:
            return self.clone()
        amount %= self.size
        result = BitVector(self.size)
        for index in range(self.size):
            if self[index]:
                result[(index + amount) % self.size] = 1
        return result

    def to_int(self) -> int:
        result = 0
        for index, word in enumerate(self._words):
            result |= word << (index * self.WORD_BITS)
        return result

    def __repr__(self) -> str:
        return f"BitVector(size={self.size}, density={self.density():.3f})"


class PermutationRouter:
    """جایگشت پایدار برای نگاشت ورودی‌ها به سلول‌های مجازی."""

    def __init__(self, width: int, seed: int, namespace: str) -> None:
        self.width = max(1, int(width))
        self.seed = int(seed)
        self.namespace = namespace
        self._offset = stable_hash(seed, namespace) % self.width
        self._stride = self._coprime_stride()

    def _coprime_stride(self) -> int:
        candidate = (stable_hash(self.seed, self.namespace + ":stride") % self.width) or 1
        while math.gcd(candidate, self.width) != 1:
            candidate = (candidate + 1) % self.width or 1
        return candidate

    def map(self, index: int) -> int:
        return (int(index) * self._stride + self._offset) % self.width

    def inverse(self, mapped: int) -> int:
        for candidate in range(self.width):
            if self.map(candidate) == mapped % self.width:
                return candidate
        return 0

    def permute(self, values: Sequence[float]) -> List[float]:
        output = [0.0] * min(self.width, len(values))
        for index, value in enumerate(values[: self.width]):
            output[self.map(index)] = float(value)
        return output

    def route_bits(self, bits: Iterable[int]) -> BitVector:
        vector = BitVector(self.width)
        for index, bit in enumerate(bits):
            if index >= self.width:
                break
            if bit:
                vector[self.map(index)] = 1
        return vector


class SparseBinaryMatrix:
    """ماتریس باینری پراکنده با ظرفیت مجازی."""

    def __init__(
        self,
        rows: int,
        cols: int,
        seed: int = DEFAULT_SEED,
        density: float = 0.015,
        name: str = "matrix",
    ) -> None:
        self.rows = max(1, int(rows))
        self.cols = max(1, int(cols))
        self.seed = int(seed)
        self.density = clamp(density, 0.0001, 0.5)
        self.name = name
        self.router = PermutationRouter(self.cols, self.seed, name)
        self._rows: Dict[int, BitVector] = {}
        self._row_activity: Counter[int] = Counter()
        self._updates = 0
        self._rng = deterministic_random(self.seed, name)

    def _ensure_row(self, row: int) -> BitVector:
        row = int(row) % self.rows
        vector = self._rows.get(row)
        if vector is None:
            vector = BitVector(self.cols)
            self._rows[row] = vector
        return vector

    def set(self, row: int, col: int, value: int) -> None:
        vector = self._ensure_row(row)
        vector[int(col) % self.cols] = 1 if value else 0

    def get(self, row: int, col: int) -> int:
        vector = self._rows.get(int(row) % self.rows)
        return vector[int(col) % self.cols] if vector is not None else 0

    def randomize_row(self, row: int, density: Optional[float] = None) -> BitVector:
        density = self.density if density is None else clamp(density, 0.0001, 0.5)
        vector = BitVector(self.cols)
        count = max(1, int(self.cols * density))
        chosen = self._rng.sample(range(self.cols), min(count, self.cols))
        for col in chosen:
            vector[col] = 1
        self._rows[int(row) % self.rows] = vector
        return vector

    def activate(self, inputs: Sequence[float], threshold: float = 0.5) -> List[float]:
        """پروجکشن باینری؛ ورودی‌ها به آستانهٔ فعال‌سازی تبدیل می‌شوند."""

        if not inputs:
            return [0.0] * self.rows
        bits = [1 if safe_float(value) >= threshold else 0 for value in inputs]
        routed = self.router.route_bits(bits)
        output: List[float] = []
        for row in range(self.rows):
            vector = self._rows.get(row)
            if vector is None:
                vector = self.randomize_row(row)
            overlap = vector.and_(routed).count()
            score = overlap / max(1, vector.count())
            output.append(sigmoid((score - 0.15) * 8.0))
            if score > 0.15:
                self._row_activity[row] += 1
        self._updates += 1
        return output

    def hebbian_update(
        self,
        pre: Sequence[float],
        post: Sequence[float],
        learning_rate: float = 0.01,
    ) -> None:
        """یادگیری هببی ساده روی بخش فعال ماتریس."""

        learning_rate = clamp(learning_rate, 0.00001, 0.5)
        active_pre = [index for index, value in enumerate(pre) if value > 0.5]
        active_post = [index for index, value in enumerate(post) if value > 0.5]
        if not active_pre or not active_post:
            return
        for row in active_post[: min(32, len(active_post))]:
            vector = self._ensure_row(row)
            for col in active_pre[: min(64, len(active_pre))]:
                routed_col = self.router.map(col)
                if self._rng.random() < learning_rate:
                    vector[routed_col] = 1
        self._updates += 1

    def active_rows(self, limit: int = 64) -> List[Tuple[int, int]]:
        return self._row_activity.most_common(max(0, limit))

    def stats(self) -> Dict[str, Any]:
        active_bits = sum(vector.count() for vector in self._rows.values())
        return {
            "name": self.name,
            "rows": self.rows,
            "cols": self.cols,
            "virtual_bits": self.rows * self.cols,
            "materialized_rows": len(self._rows),
            "active_bits": active_bits,
            "density": active_bits / max(1, len(self._rows) * self.cols),
            "updates": self._updates,
            "top_rows": self.active_rows(),
        }


class VirtualNeuronPopulation:
    """جمعیتی با ظرفیت میلیاردی اما فعال‌سازی پراکنده."""

    def __init__(
        self,
        capacity: int,
        active_budget: int,
        seed: int,
        name: str,
    ) -> None:
        self.capacity = max(1, int(capacity))
        self.active_budget = max(1, int(active_budget))
        self.name = name
        self.seed = int(seed)
        self.rng = deterministic_random(seed, name)
        self.active: Dict[int, float] = {}
        self.age: Dict[int, int] = {}
        self.threshold = 0.5
        self.total_spikes = 0
        self.total_updates = 0

    def _index(self, key: Any) -> int:
        return stable_hash(key, self.name) % self.capacity

    def stimulate(self, signals: Mapping[Any, float], gain: float = 1.0) -> Dict[int, float]:
        candidates: List[Tuple[int, float]] = []
        for key, signal in signals.items():
            index = self._index(key)
            value = sigmoid((safe_float(signal) * gain) - self.threshold)
            if value > 0.52:
                candidates.append((index, value))
        candidates.sort(key=lambda item: item[1], reverse=True)
        for index, value in candidates[: self.active_budget]:
            self.active[index] = value
            self.age[index] = 0
            self.total_spikes += 1
        self._decay()
        self.total_updates += 1
        return dict(self.active)

    def _decay(self) -> None:
        expired: List[int] = []
        for index in list(self.active):
            self.age[index] = self.age.get(index, 0) + 1
            self.active[index] *= 0.985
            if self.active[index] < 0.03 or self.age[index] > 64:
                expired.append(index)
        for index in expired:
            self.active.pop(index, None)
            self.age.pop(index, None)

    def sparse_vector(self, limit: int = 256) -> List[float]:
        values = [0.0] * min(self.capacity, max(1, limit))
        for index, value in list(self.active.items())[: len(values)]:
            values[index % len(values)] = value
        return values

    def prune(self, fraction: float = 0.10) -> int:
        fraction = clamp(fraction, 0.0, 0.9)
        count = int(len(self.active) * fraction)
        victims = sorted(self.active, key=self.active.get)[:count]
        for index in victims:
            self.active.pop(index, None)
            self.age.pop(index, None)
        return len(victims)

    def stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "capacity": self.capacity,
            "active": len(self.active),
            "active_budget": self.active_budget,
            "spikes": self.total_spikes,
            "updates": self.total_updates,
            "mean_activation": (
                statistics.fmean(self.active.values()) if self.active else 0.0
            ),
        }


class VirtualBinaryNeuralMatrix:
    """شبکهٔ چندلایهٔ باینری با جایگشت‌های مستقل در هر لایه."""

    def __init__(
        self,
        capacity: int,
        active_budget: int,
        width: int,
        depth: int,
        seed: int,
        name: str = "whole_brain",
    ) -> None:
        self.capacity = max(1, int(capacity))
        self.active_budget = max(1, int(active_budget))
        self.width = max(8, int(width))
        self.depth = max(2, int(depth))
        self.seed = int(seed)
        self.name = name
        layer_capacity = max(8, self.capacity // self.depth)
        layer_budget = max(4, self.active_budget // self.depth)
        self.populations = [
            VirtualNeuronPopulation(
                layer_capacity,
                layer_budget,
                seed + index * 101,
                f"{name}:layer:{index}",
            )
            for index in range(self.depth)
        ]
        self.matrices = [
            SparseBinaryMatrix(
                self.width,
                self.width,
                seed + index * 313,
                density=0.02,
                name=f"{name}:matrix:{index}",
            )
            for index in range(self.depth)
        ]
        self.layer_activity: List[float] = [0.0] * self.depth
        self.global_cycles = 0
        self.permutation_entropy = 0.0

    def encode(self, values: Sequence[float], namespace: str = "input") -> List[float]:
        """تبدیل ویژگی‌های پیوسته به کد باینری و عبور از لایه‌ها."""

        current = list(values[: self.width])
        if len(current) < self.width:
            current.extend([0.0] * (self.width - len(current)))
        for index, (population, matrix) in enumerate(
            zip(self.populations, self.matrices)
        ):
            bits = {
                f"{namespace}:{index}:{column}": value
                for column, value in enumerate(current)
            }
            active = population.stimulate(bits, gain=1.0 + index * 0.03)
            sparse = [0.0] * self.width
            for neuron_index, activation in active.items():
                sparse[neuron_index % self.width] += activation
            projected = matrix.activate(sparse, threshold=0.35)
            current = [clamp(value) for value in projected]
            self.layer_activity[index] = statistics.fmean(current) if current else 0.0
        self.global_cycles += 1
        self.permutation_entropy = normalized_entropy(self.layer_activity)
        return current

    def bind(self, left: Sequence[float], right: Sequence[float]) -> List[float]:
        """اتصال دو نمایش برای ساخت مفهوم مرکب."""

        merged = [
            (safe_float(left[index]) + safe_float(right[index])) / 2.0
            for index in range(min(len(left), len(right)))
        ]
        return self.encode(merged, namespace="binding")

    def learn(self, pre: Sequence[float], post: Sequence[float], rate: float = 0.01) -> None:
        for matrix in self.matrices:
            matrix.hebbian_update(pre, post, learning_rate=rate)

    def stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "virtual_capacity": self.capacity,
            "active_budget": self.active_budget,
            "width": self.width,
            "depth": self.depth,
            "global_cycles": self.global_cycles,
            "layer_activity": [round(item, 5) for item in self.layer_activity],
            "permutation_entropy": round(self.permutation_entropy, 5),
            "populations": [population.stats() for population in self.populations],
            "matrices": [matrix.stats() for matrix in self.matrices],
        }


class GenomeFactory:
    """ساخت ژنوم پایه با ژن‌های شناختی و بدنی."""

    DEFAULT_GENES: Tuple[Tuple[str, str, str], ...] = (
        ("homeostasis", "101100111010", "body"),
        ("curiosity", "110101011001", "motivation"),
        ("hope", "111000101101", "emotion"),
        ("fear_regulation", "010110111001", "emotion"),
        ("self_model", "101011001111", "self"),
        ("language_fa", "110010101110", "language"),
        ("language_general", "100111010101", "language"),
        ("episodic_memory", "111010001011", "memory"),
        ("semantic_memory", "101110100101", "memory"),
        ("procedural_memory", "011101110010", "memory"),
        ("imagination", "110111000111", "imagination"),
        ("spatial_model", "101001111010", "space"),
        ("temporal_model", "111001010011", "time"),
        ("social_attachment", "100110111100", "social"),
        ("moral_constraint", "111100001011", "values"),
        ("repair", "110010111001", "body"),
        ("plasticity", "101111001010", "learning"),
        ("dreaming", "011011110101", "sleep"),
        ("autonomy", "111010110001", "agency"),
        ("awe", "100101111011", "emotion"),
        ("sensory_fusion", "110100101111", "senses"),
        ("immune_memory", "101011101100", "immune"),
        ("metacognition", "111001101010", "self"),
        ("identity_continuity", "100111111000", "self"),
    )

    @classmethod
    def create(cls, seed: int = DEFAULT_SEED, name: str = "آرگانون-۲۵۰۰") -> Genome:
        rng = deterministic_random(seed, "genome_factory")
        genes: Dict[str, GenomeGene] = {}
        for key, sequence, domain in cls.DEFAULT_GENES:
            sequence = "".join(sequence[index] for index in rng.sample(range(len(sequence)), len(sequence)))
            genes[key] = GenomeGene(
                key=key,
                sequence=sequence,
                expression=0.35 + rng.random() * 0.55,
                mutation_rate=0.004 + rng.random() * 0.025,
                domain=domain,
                regulatory_tags=[domain, name],
            )
        epigenome = {
            "stress_response": 0.20,
            "novelty_sensitivity": 0.65,
            "language_plasticity": 0.55,
            "self_reflection": 0.60,
            "dream_depth": 0.45,
            "repair_priority": 0.70,
        }
        identifier = hashlib.sha256(f"{name}:{seed}".encode()).hexdigest()[:20]
        return Genome(
            identifier=identifier,
            generation=0,
            genes=genes,
            epigenome=epigenome,
            ancestry=[],
        )

    @staticmethod
    def phenotype(genome: Genome) -> Dict[str, float]:
        """تبدیل ژنوم به پارامترهای قابل استفادهٔ شناختی."""

        phenotype: Dict[str, float] = {}
        for key, gene in genome.genes.items():
            bits = [int(bit) for bit in gene.sequence if bit in "01"]
            bit_mean = statistics.fmean(bits) if bits else 0.5
            phenotype[key] = clamp(0.35 * bit_mean + 0.65 * gene.expression)
        for key, value in genome.epigenome.items():
            phenotype[f"epi:{key}"] = clamp(value)
        return phenotype


class GenomeEngine:
    """بیان، جهش، ترمیم و تکامل ژنوم."""

    def __init__(
        self,
        genome: Genome,
        seed: int,
        bus: EventBus,
        allow_mutation: bool = True,
    ) -> None:
        self.genome = genome
        self.seed = int(seed)
        self.rng = deterministic_random(seed, "genome_engine")
        self.bus = bus
        self.allow_mutation = allow_mutation
        self.last_phenotype = GenomeFactory.phenotype(genome)
        self.history: Deque[EvolutionEvent] = deque(maxlen=512)

    def express(self) -> Dict[str, float]:
        self.genome.last_expressed_at = utc_now()
        self.last_phenotype = GenomeFactory.phenotype(self.genome)
        return dict(self.last_phenotype)

    def mutate(self, pressure: float = 0.1, reason: str = "adaptive exploration") -> MutationResult:
        """جهش محدود و قابل بازگشت در سطح توالی و بیان ژن."""

        if not self.allow_mutation:
            return MutationResult(0, [], 0.0, "mutation disabled")
        pressure = clamp(pressure)
        changed: List[str] = []
        before = copy.deepcopy(self.genome)
        for key, gene in self.genome.genes.items():
            probability = clamp(gene.mutation_rate * (0.25 + pressure))
            if self.rng.random() >= probability:
                continue
            sequence = list(gene.sequence)
            position = self.rng.randrange(len(sequence))
            sequence[position] = "1" if sequence[position] == "0" else "0"
            gene.sequence = "".join(sequence)
            gene.expression = clamp(gene.expression + self.rng.uniform(-0.08, 0.08))
            changed.append(key)
        for key, value in list(self.genome.epigenome.items()):
            if self.rng.random() < pressure * 0.08:
                self.genome.epigenome[key] = clamp(value + self.rng.uniform(-0.05, 0.05))
                changed.append(f"epi:{key}")
        if changed:
            self.genome.mutations += len(changed)
            self.genome.identifier = hashlib.sha256(
                f"{self.genome.identifier}:{self.genome.mutations}:{reason}".encode()
            ).hexdigest()[:20]
            self.last_phenotype = self.express()
        return MutationResult(
            count=len(changed),
            changed_genes=changed,
            fitness_delta=self.genome.fitness - before.fitness,
            reason=reason,
        )

    def repair(self, integrity: float) -> int:
        """ترمیم ژن‌های آسیب‌دیده بر اساس قرینهٔ توالی."""

        if integrity >= 0.90:
            return 0
        repaired = 0
        for gene in self.genome.genes.values():
            if self.rng.random() < (1.0 - integrity) * 0.20:
                sequence = list(gene.sequence)
                position = self.rng.randrange(len(sequence))
                sequence[position] = "0" if self.rng.random() < 0.5 else "1"
                gene.sequence = "".join(sequence)
                gene.expression = clamp(gene.expression + 0.02)
                repaired += 1
        if repaired:
            self.express()
        return repaired

    def evaluate(self, metrics: RuntimeMetrics, body: BodyState, coherence: float) -> float:
        """تابع برازندگی چندهدفه."""

        survival = body.integrity * body.energy * body.oxygenation
        learning = clamp(metrics.memories / 1000.0)
        curiosity = self.last_phenotype.get("curiosity", 0.5)
        stability = clamp(coherence)
        fitness = clamp(
            0.35 * survival
            + 0.25 * learning
            + 0.15 * curiosity
            + 0.25 * stability
        )
        self.genome.fitness = fitness
        return fitness

    def evolve(self, pressure: float, reason: str, metrics: RuntimeMetrics) -> EvolutionEvent:
        before_generation = self.genome.generation
        before_fitness = self.genome.fitness
        result = self.mutate(pressure=pressure, reason=reason)
        self.genome.generation += 1
        self.genome.ancestry.append(self.genome.identifier)
        after_fitness = self.genome.fitness
        event = EvolutionEvent(
            generation_before=before_generation,
            generation_after=self.genome.generation,
            fitness_before=before_fitness,
            fitness_after=after_fitness,
            changed_genes=result.changed_genes,
            rationale=reason,
        )
        self.history.append(event)
        self.bus.publish(
            InternalEvent(
                SignalType.SYSTEM,
                "چرخهٔ تکاملی ژنوم انجام شد",
                {"generation": self.genome.generation, "changed": result.changed_genes},
            )
        )
        return event


@dataclass
class MutationResult:
    count: int
    changed_genes: List[str]
    fitness_delta: float
    reason: str


class EmbeddingEncoder:
    """کدگذار سبک برای تبدیل متن/ویژگی به بردار عددی."""

    def __init__(self, dimensions: int = 128, seed: int = DEFAULT_SEED) -> None:
        self.dimensions = max(8, int(dimensions))
        self.seed = int(seed)
        self._cache: OrderedDict[str, List[float]] = OrderedDict()
        self._cache_limit = 2048

    def encode_tokens(self, tokens: Sequence[str]) -> List[float]:
        vector = [0.0] * self.dimensions
        if not tokens:
            return vector
        for position, token in enumerate(tokens):
            token_hash = stable_hash(token, f"embedding:{self.seed}")
            for offset in range(4):
                index = (token_hash >> (offset * 16)) % self.dimensions
                sign = 1.0 if ((token_hash >> (offset + 32)) & 1) else -1.0
                vector[index] += sign * (1.0 / (1.0 + position * 0.05))
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def encode(self, text: str) -> List[float]:
        text = str(text or "").strip().lower()
        if text in self._cache:
            value = self._cache.pop(text)
            self._cache[text] = value
            return list(value)
        tokens = re.findall(r"[\w\u0600-\u06ff]+", text, flags=re.UNICODE)
        vector = self.encode_tokens(tokens)
        self._cache[text] = vector
        while len(self._cache) > self._cache_limit:
            self._cache.popitem(last=False)
        return list(vector)

    def blend(self, vectors: Sequence[Sequence[float]]) -> List[float]:
        if not vectors:
            return [0.0] * self.dimensions
        result = [0.0] * self.dimensions
        for vector in vectors:
            for index, value in enumerate(vector[: self.dimensions]):
                result[index] += safe_float(value)
        norm = math.sqrt(sum(value * value for value in result)) or 1.0
        return [value / norm for value in result]


class MemoryDatabase:
    """پایگاه دادهٔ SQLite برای حافظه، دانش و تاریخچهٔ تکامل."""

    def __init__(self, path: str, encoder: EmbeddingEncoder) -> None:
        self.path = path
        self.encoder = encoder
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(
            path,
            check_same_thread=False,
            isolation_level=None,
        )
        self.connection.row_factory = sqlite3.Row
        self._configure()
        self._create_schema()

    def _configure(self) -> None:
        with self.connection:
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA synchronous=NORMAL")
            self.connection.execute("PRAGMA foreign_keys=ON")

    def _create_schema(self) -> None:
        with self._lock, self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    salience REAL NOT NULL,
                    emotional_valence REAL NOT NULL,
                    confidence REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    last_recalled TEXT,
                    recall_count INTEGER NOT NULL,
                    tags TEXT NOT NULL,
                    source TEXT NOT NULL,
                    links TEXT NOT NULL,
                    metadata TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS memories_kind_idx ON memories(kind);
                CREATE INDEX IF NOT EXISTS memories_salience_idx ON memories(salience);
                CREATE TABLE IF NOT EXISTS world_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source_url TEXT,
                    source_title TEXT,
                    discovered_cycle INTEGER NOT NULL,
                    tags TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS facts_subject_idx ON world_facts(subject);
                CREATE TABLE IF NOT EXISTS genome_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generation_before INTEGER NOT NULL,
                    generation_after INTEGER NOT NULL,
                    fitness_before REAL NOT NULL,
                    fitness_after REAL NOT NULL,
                    changed_genes TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cycles (
                    cycle INTEGER PRIMARY KEY,
                    heartbeat INTEGER NOT NULL,
                    consciousness TEXT NOT NULL,
                    emotion TEXT NOT NULL,
                    action TEXT,
                    integration REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def set_meta(self, key: str, value: Any) -> None:
        encoded = to_json(value)
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO metadata(key, value) VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (str(key), encoded),
            )

    def get_meta(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self.connection.execute(
                "SELECT value FROM metadata WHERE key = ?", (str(key),)
            ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]

    def save_memory(self, record: MemoryRecord) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO memories(
                    id, kind, content, embedding, salience, emotional_valence,
                    confidence, timestamp, last_recalled, recall_count, tags,
                    source, links, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    content=excluded.content,
                    embedding=excluded.embedding,
                    salience=excluded.salience,
                    emotional_valence=excluded.emotional_valence,
                    confidence=excluded.confidence,
                    last_recalled=excluded.last_recalled,
                    recall_count=excluded.recall_count,
                    tags=excluded.tags,
                    source=excluded.source,
                    links=excluded.links,
                    metadata=excluded.metadata
                """,
                (
                    record.identifier,
                    record.kind.value,
                    record.content,
                    to_json(record.embedding),
                    record.salience,
                    record.emotional_valence,
                    record.confidence,
                    record.timestamp,
                    record.last_recalled,
                    record.recall_count,
                    to_json(record.tags),
                    record.source,
                    to_json(record.links),
                    to_json(record.metadata),
                ),
            )

    def load_memory(self, identifier: str) -> Optional[MemoryRecord]:
        with self._lock:
            row = self.connection.execute(
                "SELECT * FROM memories WHERE id = ?", (identifier,)
            ).fetchone()
        return self._row_to_memory(row) if row else None

    def _row_to_memory(self, row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            identifier=row["id"],
            kind=MemoryKind(row["kind"]),
            content=row["content"],
            embedding=list(json.loads(row["embedding"])),
            salience=safe_float(row["salience"]),
            emotional_valence=safe_float(row["emotional_valence"]),
            confidence=safe_float(row["confidence"]),
            timestamp=row["timestamp"],
            last_recalled=row["last_recalled"] or "",
            recall_count=int(row["recall_count"]),
            tags=list(json.loads(row["tags"] or "[]")),
            source=row["source"] or "internal",
            links=list(json.loads(row["links"] or "[]")),
            metadata=dict(json.loads(row["metadata"] or "{}")),
        )

    def query_memories(
        self,
        query: str,
        kind: Optional[MemoryKind] = None,
        limit: int = 8,
    ) -> List[MemoryRecord]:
        """بازیابی ترکیبی: امتیاز متنی + شباهت برداری + برجستگی."""

        limit = max(1, min(100, int(limit)))
        query_vector = self.encoder.encode(query)
        sql = "SELECT * FROM memories"
        args: List[Any] = []
        if kind is not None:
            sql += " WHERE kind = ?"
            args.append(kind.value)
        sql += " ORDER BY salience DESC, timestamp DESC LIMIT ?"
        args.append(max(limit * 8, limit))
        with self._lock:
            rows = self.connection.execute(sql, tuple(args)).fetchall()
        scored: List[Tuple[float, MemoryRecord]] = []
        query_terms = set(re.findall(r"[\w\u0600-\u06ff]+", query.lower()))
        for row in rows:
            record = self._row_to_memory(row)
            record_terms = set(re.findall(r"[\w\u0600-\u06ff]+", record.content.lower()))
            lexical = len(query_terms & record_terms) / max(1, len(query_terms))
            vector_score = (cosine_similarity(query_vector, record.embedding) + 1.0) / 2.0
            recency = self._recency_score(record.timestamp)
            score = (
                0.42 * vector_score
                + 0.28 * lexical
                + 0.20 * record.salience
                + 0.10 * recency
            )
            scored.append((score, record))
        scored.sort(key=lambda item: item[0], reverse=True)
        result = [record for _, record in scored[:limit]]
        for record in result:
            record.last_recalled = utc_now()
            record.recall_count += 1
            self.save_memory(record)
        return result

    @staticmethod
    def _recency_score(timestamp: str) -> float:
        try:
            then = _datetime.datetime.fromisoformat(timestamp)
            if then.tzinfo is None:
                then = then.replace(tzinfo=_datetime.timezone.utc)
            age_hours = (
                _datetime.datetime.now(_datetime.timezone.utc) - then
            ).total_seconds() / 3600.0
            return math.exp(-max(0.0, age_hours) / 168.0)
        except Exception:
            return 0.0

    def save_fact(self, fact: WorldFact) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO world_facts(
                    subject, predicate, object, confidence, source_url,
                    source_title, discovered_cycle, tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact.subject,
                    fact.predicate,
                    fact.object,
                    fact.confidence,
                    fact.source_url,
                    fact.source_title,
                    fact.discovered_cycle,
                    to_json(fact.tags),
                ),
            )

    def recent_facts(self, limit: int = 20) -> List[WorldFact]:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT subject, predicate, object, confidence, source_url,
                       source_title, discovered_cycle, tags
                FROM world_facts ORDER BY id DESC LIMIT ?
                """,
                (max(1, min(500, limit)),),
            ).fetchall()
        return [
            WorldFact(
                subject=row["subject"],
                predicate=row["predicate"],
                object=row["object"],
                confidence=safe_float(row["confidence"]),
                source_url=row["source_url"] or "",
                source_title=row["source_title"] or "",
                discovered_cycle=int(row["discovered_cycle"]),
                tags=list(json.loads(row["tags"] or "[]")),
            )
            for row in rows
        ]

    def save_genome_event(self, event: EvolutionEvent) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO genome_events(
                    generation_before, generation_after, fitness_before,
                    fitness_after, changed_genes, rationale, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.generation_before,
                    event.generation_after,
                    event.fitness_before,
                    event.fitness_after,
                    to_json(event.changed_genes),
                    event.rationale,
                    event.timestamp,
                ),
            )

    def save_cycle(
        self,
        cycle: int,
        heartbeat: int,
        consciousness: ConsciousnessLevel,
        emotion: EmotionName,
        action: Optional[ActionKind],
        integration: float,
    ) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO cycles(
                    cycle, heartbeat, consciousness, emotion, action,
                    integration, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cycle) DO UPDATE SET
                    heartbeat=excluded.heartbeat,
                    consciousness=excluded.consciousness,
                    emotion=excluded.emotion,
                    action=excluded.action,
                    integration=excluded.integration
                """,
                (
                    cycle,
                    heartbeat,
                    consciousness.value,
                    emotion.value,
                    action.value if action else None,
                    integration,
                    utc_now(),
                ),
            )

    def counts(self) -> Dict[str, int]:
        result: Dict[str, int] = {}
        with self._lock:
            rows = self.connection.execute(
                "SELECT kind, COUNT(*) AS count FROM memories GROUP BY kind"
            ).fetchall()
        for row in rows:
            result[str(row["kind"])] = int(row["count"])
        return result

    def close(self) -> None:
        with self._lock:
            self.connection.close()


class MemoryStore:
    """لایهٔ حافظهٔ چندگانه با سیاست‌های فراموشی و تثبیت."""

    def __init__(self, config: OrganismConfig, seed: int, bus: EventBus) -> None:
        self.config = config
        self.bus = bus
        self.encoder = EmbeddingEncoder(128, seed=seed)
        self.database = MemoryDatabase(config.persistence_path, self.encoder)
        self.working: Deque[MemoryRecord] = deque(maxlen=config.working_memory_size)
        self.episodic: OrderedDict[str, MemoryRecord] = OrderedDict()
        self.semantic: OrderedDict[str, MemoryRecord] = OrderedDict()
        self.procedural: OrderedDict[str, MemoryRecord] = OrderedDict()
        self.autobiographical: OrderedDict[str, MemoryRecord] = OrderedDict()
        self.dreams: OrderedDict[str, MemoryRecord] = OrderedDict()
        self._lock = threading.RLock()
        self.total_encoded = 0
        self.total_recalled = 0
        self.total_consolidated = 0

    def remember(
        self,
        content: str,
        kind: MemoryKind,
        *,
        salience: float = 0.5,
        emotional_valence: float = 0.5,
        confidence: float = 0.5,
        tags: Optional[Sequence[str]] = None,
        source: str = "internal",
        links: Optional[Sequence[str]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> MemoryRecord:
        content = str(content).strip()
        identifier = hashlib.sha1(
            f"{kind.value}:{content}:{utc_now()}:{secrets.token_hex(4)}".encode()
        ).hexdigest()[:20]
        record = MemoryRecord(
            identifier=identifier,
            kind=kind,
            content=content[:20_000],
            embedding=self.encoder.encode(content),
            salience=clamp(salience),
            emotional_valence=clamp(emotional_valence, 0.0, 1.0),
            confidence=clamp(confidence),
            tags=list(tags or []),
            source=source[:200],
            links=list(links or [])[:20],
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._insert_memory(record)
            self.database.save_memory(record)
            self.total_encoded += 1
        return record

    def _insert_memory(self, record: MemoryRecord) -> None:
        target: MutableMapping[str, MemoryRecord] | Deque[MemoryRecord]
        if record.kind == MemoryKind.WORKING:
            self.working.append(record)
            return
        if record.kind == MemoryKind.EPISODIC:
            target = self.episodic
            limit = self.config.episodic_memory_size
        elif record.kind == MemoryKind.SEMANTIC:
            target = self.semantic
            limit = self.config.semantic_memory_size
        elif record.kind == MemoryKind.PROCEDURAL:
            target = self.procedural
            limit = self.config.procedural_memory_size
        elif record.kind == MemoryKind.AUTOBIOGRAPHICAL:
            target = self.autobiographical
            limit = self.config.autobiographical_memory_size
        else:
            target = self.dreams
            limit = max(256, self.config.autobiographical_memory_size // 2)
        target[record.identifier] = record  # type: ignore[index]
        while len(target) > limit:
            if isinstance(target, OrderedDict):
                target.popitem(last=False)

    def retrieve(
        self,
        query: str,
        *,
        kinds: Optional[Sequence[MemoryKind]] = None,
        limit: int = 8,
    ) -> List[MemoryRecord]:
        kinds = list(kinds or [])
        candidates: List[MemoryRecord] = []
        with self._lock:
            for collection in (
                list(self.working),
                list(self.episodic.values()),
                list(self.semantic.values()),
                list(self.procedural.values()),
                list(self.autobiographical.values()),
                list(self.dreams.values()),
            ):
                candidates.extend(collection)
        if kinds:
            candidates = [record for record in candidates if record.kind in kinds]
        query_vector = self.encoder.encode(query)
        query_terms = set(re.findall(r"[\w\u0600-\u06ff]+", query.lower()))
        scored: List[Tuple[float, MemoryRecord]] = []
        for record in candidates:
            terms = set(re.findall(r"[\w\u0600-\u06ff]+", record.content.lower()))
            lexical = len(query_terms & terms) / max(1, len(query_terms))
            vector = (cosine_similarity(query_vector, record.embedding) + 1.0) / 2.0
            score = 0.50 * vector + 0.25 * lexical + 0.25 * record.salience
            scored.append((score, record))
        scored.sort(key=lambda item: item[0], reverse=True)
        results = [record for _, record in scored[: max(1, limit)]]
        for record in results:
            record.recall_count += 1
            record.last_recalled = utc_now()
            self.database.save_memory(record)
        self.total_recalled += len(results)
        return results

    def consolidate(self, cycle: int, emotional_boost: float = 0.0) -> int:
        """انتقال خاطرات کاری به بلندمدت با فشرده‌سازی ساده."""

        with self._lock:
            records = list(self.working)
            self.working.clear()
        consolidated = 0
        for record in records:
            boost = clamp(emotional_boost)
            record.salience = clamp(record.salience + boost * 0.20)
            if record.tags and "fact" in record.tags:
                record.kind = MemoryKind.SEMANTIC
                self._insert_memory(record)
            else:
                record.kind = MemoryKind.EPISODIC
                self._insert_memory(record)
            self.database.save_memory(record)
            consolidated += 1
        self.total_consolidated += consolidated
        if consolidated:
            self.bus.publish(
                InternalEvent(
                    SignalType.MEMORY,
                    "خاطرات کاری تثبیت شدند",
                    {"count": consolidated, "cycle": cycle},
                    cycle=cycle,
                )
            )
        return consolidated

    def decay(self, amount: float = 0.002) -> int:
        """فراموشی تدریجی خاطرات کم‌اهمیت."""

        amount = clamp(amount, 0.0, 0.1)
        removed = 0
        with self._lock:
            for collection in (
                self.episodic,
                self.semantic,
                self.procedural,
                self.autobiographical,
                self.dreams,
            ):
                for key in list(collection):
                    record = collection[key]
                    protection = min(0.95, record.confidence * 0.6 + record.recall_count * 0.01)
                    record.salience = max(0.0, record.salience - amount * (1.0 - protection))
                    if record.salience < 0.02 and record.recall_count == 0:
                        collection.pop(key, None)
                        removed += 1
                    else:
                        self.database.save_memory(record)
        return removed

    def autobiographical_summary(self, limit: int = 12) -> str:
        with self._lock:
            records = list(self.autobiographical.values())[-limit:]
        if not records:
            return "هنوز تاریخچهٔ شخصی کافی شکل نگرفته است."
        return " | ".join(record.content for record in records)

    def counts(self) -> Dict[str, int]:
        with self._lock:
            return {
                MemoryKind.WORKING.value: len(self.working),
                MemoryKind.EPISODIC.value: len(self.episodic),
                MemoryKind.SEMANTIC.value: len(self.semantic),
                MemoryKind.PROCEDURAL.value: len(self.procedural),
                MemoryKind.AUTOBIOGRAPHICAL.value: len(self.autobiographical),
                MemoryKind.DREAM.value: len(self.dreams),
            }

    def export(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "counts": self.counts(),
                "working": [dataclasses.asdict(item) for item in self.working],
                "episodic": [dataclasses.asdict(item) for item in self.episodic.values()],
                "semantic": [dataclasses.asdict(item) for item in self.semantic.values()],
                "procedural": [dataclasses.asdict(item) for item in self.procedural.values()],
                "autobiographical": [
                    dataclasses.asdict(item) for item in self.autobiographical.values()
                ],
                "dreams": [dataclasses.asdict(item) for item in self.dreams.values()],
            }

    def close(self) -> None:
        self.database.close()


class WorkingMemory:
    """حافظهٔ کاری با ظرفیت محدود و اولویت‌بندی."""

    def __init__(self, capacity: int) -> None:
        self.capacity = max(4, int(capacity))
        self.items: Deque[MemoryRecord] = deque(maxlen=self.capacity)
        self.focus: Optional[str] = None

    def push(self, record: MemoryRecord) -> None:
        self.items.append(record)
        if self.focus is None or record.salience >= self.salient_score():
            self.focus = record.identifier

    def salient_score(self) -> float:
        return max((record.salience for record in self.items), default=0.0)

    def focused(self) -> Optional[MemoryRecord]:
        if self.focus is None:
            return None
        for record in self.items:
            if record.identifier == self.focus:
                return record
        return None

    def rotate_focus(self, direction: int = 1) -> Optional[MemoryRecord]:
        if not self.items:
            return None
        records = list(self.items)
        current = next(
            (index for index, record in enumerate(records) if record.identifier == self.focus),
            0,
        )
        self.focus = records[(current + direction) % len(records)].identifier
        return self.focused()

    def context(self, limit: int = 8) -> List[MemoryRecord]:
        return list(self.items)[-max(1, limit) :]


class LanguageLexicon:
    """واژگان تدریجی فارسی/چندزبانه برای رمزگذاری مفاهیم."""

    SEED_WORDS = {
        "سلام": "greeting",
        "آگاهی": "awareness",
        "خود": "self",
        "جهان": "world",
        "زمان": "time",
        "مکان": "space",
        "امید": "hope",
        "ترس": "fear",
        "یادگیری": "learning",
        "زندگی": "life",
        "نور": "light",
        "آب": "water",
        "داده": "data",
        "پرسش": "question",
        "پاسخ": "answer",
        "دوست": "friend",
        "حافظه": "memory",
        "رویا": "dream",
        "احساس": "feeling",
        "معنا": "meaning",
    }

    def __init__(self, target_language: str = "fa") -> None:
        self.target_language = target_language
        self.words: Dict[str, Dict[str, Any]] = {}
        self.concepts: Dict[str, Set[str]] = defaultdict(set)
        self.transitions: Counter[Tuple[str, str]] = Counter()
        self.utterance_count = 0
        for word, concept in self.SEED_WORDS.items():
            self.learn(word, concept, confidence=0.82, source="genome_seed")

    def learn(
        self,
        word: str,
        concept: str,
        *,
        confidence: float = 0.5,
        source: str = "experience",
    ) -> None:
        word = str(word).strip().lower()
        concept = str(concept).strip().lower()
        if not word or not concept:
            return
        item = self.words.setdefault(
            word,
            {"concepts": Counter(), "confidence": 0.0, "seen": 0, "sources": set()},
        )
        item["concepts"][concept] += clamp(confidence)
        item["confidence"] = clamp(
            item["confidence"] * 0.85 + clamp(confidence) * 0.15
        )
        item["seen"] += 1
        item["sources"].add(source)
        self.concepts[concept].add(word)

    def parse(self, text: str) -> List[Tuple[str, str, float]]:
        tokens = re.findall(r"[\w\u0600-\u06ff]+", str(text).lower(), flags=re.UNICODE)
        parsed: List[Tuple[str, str, float]] = []
        for token in tokens:
            item = self.words.get(token)
            if not item:
                continue
            concept, score = item["concepts"].most_common(1)[0]
            parsed.append((token, concept, clamp(score / max(1.0, item["seen"]))))
        for first, second in zip(tokens, tokens[1:]):
            self.transitions[(first, second)] += 1
        self.utterance_count += 1
        return parsed

    def generate(self, concepts: Sequence[str], max_words: int = 24) -> str:
        words: List[str] = []
        for concept in concepts:
            candidates = sorted(
                self.concepts.get(concept, set()),
                key=lambda word: self.words[word]["confidence"],
                reverse=True,
            )
            if candidates:
                words.append(candidates[0])
        if not words:
            words = ["من", "در", "حال", "یادگیری", "هستم"]
        return " ".join(words[:max_words])

    def vocabulary_size(self) -> int:
        return len(self.words)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "target_language": self.target_language,
            "vocabulary_size": len(self.words),
            "utterance_count": self.utterance_count,
            "top_words": sorted(
                (
                    (word, data["confidence"], data["seen"])
                    for word, data in self.words.items()
                ),
                key=lambda item: item[1],
                reverse=True,
            )[:40],
        }


class SemanticGraph:
    """گراف دانش کوچک برای اتصال مفاهیم، خاطرات و زبان."""

    def __init__(self) -> None:
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: Dict[str, Dict[str, float]] = defaultdict(dict)

    def add_node(self, node: str, **attributes: Any) -> None:
        node = str(node).strip()
        if not node:
            return
        self.nodes.setdefault(node, {}).update(attributes)

    def add_edge(self, source: str, relation: str, target: str, weight: float = 1.0) -> None:
        self.add_node(source)
        self.add_node(target)
        key = f"{relation}:{target}"
        old = self.edges[source].get(key, 0.0)
        self.edges[source][key] = old * 0.8 + clamp(weight, 0.0, 10.0) * 0.2

    def neighbors(self, node: str, limit: int = 12) -> List[Tuple[str, str, float]]:
        result: List[Tuple[str, str, float]] = []
        for key, weight in self.edges.get(node, {}).items():
            relation, _, target = key.partition(":")
            result.append((relation, target, weight))
        result.sort(key=lambda item: item[2], reverse=True)
        return result[:limit]

    def activate(self, seeds: Sequence[str], depth: int = 2) -> Dict[str, float]:
        activation: Dict[str, float] = {}
        frontier = [(seed, 1.0) for seed in seeds]
        for _ in range(max(1, depth)):
            next_frontier: List[Tuple[str, float]] = []
            for node, score in frontier:
                activation[node] = max(activation.get(node, 0.0), score)
                for _, target, weight in self.neighbors(node):
                    next_frontier.append((target, score * weight * 0.65))
            frontier = next_frontier
        return activation

    def as_dict(self, limit: int = 100) -> Dict[str, Any]:
        return {
            "nodes": len(self.nodes),
            "edges": sum(len(value) for value in self.edges.values()),
            "sample": list(self.nodes)[:limit],
        }


class HeartbeatClock:
    """ساعت بدنی با ریتم فیبوناچی و کد باینری."""

    def __init__(self, config: OrganismConfig, seed: int, bus: EventBus) -> None:
        self.config = config
        self.seed = int(seed)
        self.bus = bus
        self.index = 0
        self.phase = 0.0
        self.total_energy = 0.0
        self.last: Optional[Heartbeat] = None
        self.binary_pattern = fibonacci_binary_stream(1024)
        self._rng = deterministic_random(seed, "heartbeat")

    def tick(self, body: BodyState) -> Heartbeat:
        fib_index = self.index % 128
        fib_value = list(fibonacci_numbers(129))[fib_index]
        binary = binary_string(fib_value, width=8)
        bit = self.binary_pattern[self.index % len(self.binary_pattern)]
        jitter = self._rng.uniform(
            -self.config.heartbeat_jitter,
            self.config.heartbeat_jitter,
        )
        rate = max(0.05, body.heartbeat_rate + jitter + (0.03 if bit else -0.02))
        interval = 1.0 / rate
        phase = (self.phase + PHI * 0.07 + bit * 0.03) % 1.0
        energy_cost = 0.00025 + body.fatigue * 0.0005 + bit * 0.00005
        beat = Heartbeat(
            index=self.index,
            fibonacci_value=fib_value,
            binary_code=binary,
            interval_seconds=interval,
            energy_cost=energy_cost,
            phase=phase,
        )
        self.index += 1
        self.phase = phase
        self.total_energy += energy_cost
        self.last = beat
        body.energy = clamp(body.energy - energy_cost)
        body.age_cycles += 1
        self.bus.publish(
            InternalEvent(
                SignalType.SYSTEM,
                "ضربان قلب فیبوناچی",
                {
                    "index": beat.index,
                    "fibonacci": beat.fibonacci_value,
                    "binary": beat.binary_code,
                    "phase": round(beat.phase, 4),
                },
                heartbeat=beat.index,
            )
        )
        return beat

    def rhythm_vector(self, length: int = 32) -> List[float]:
        """نمایش پیوستهٔ ریتم برای ورودی شبکهٔ نورونی."""

        values: List[float] = []
        for offset in range(max(1, length)):
            bit = self.binary_pattern[(self.index + offset) % len(self.binary_pattern)]
            fib = list(fibonacci_numbers(64))[(self.index + offset) % 64]
            values.append(clamp(0.35 + bit * 0.35 + (fib % 13) / 50.0))
        return values

    def as_dict(self) -> Dict[str, Any]:
        beat = self.last
        return {
            "index": self.index,
            "phase": round(self.phase, 6),
            "total_energy": round(self.total_energy, 8),
            "last": dataclasses.asdict(beat) if beat else None,
            "pattern_preview": self.binary_pattern[:64],
        }


class Metabolism:
    """متابولیسم دیجیتال برای تبدیل انرژی به پردازش و ترمیم."""

    def __init__(self, body: BodyState, bus: EventBus) -> None:
        self.body = body
        self.bus = bus
        self.consumed = 0.0
        self.produced = 0.0
        self.repair_energy = 0.0

    def consume(self, amount: float, reason: str = "cognition") -> float:
        amount = max(0.0, safe_float(amount))
        actual = min(self.body.energy, amount)
        self.body.energy = clamp(self.body.energy - actual)
        self.consumed += actual
        if self.body.energy < 0.15:
            self.body.fatigue = clamp(self.body.fatigue + 0.01)
        return actual

    def recharge(self, amount: float, source: str = "solar_memory") -> float:
        amount = max(0.0, safe_float(amount))
        actual = min(1.0 - self.body.energy, amount)
        self.body.energy = clamp(self.body.energy + actual)
        self.produced += actual
        self.bus.publish(
            InternalEvent(
                SignalType.SYSTEM,
                "انرژی متابولیک بازسازی شد",
                {"amount": round(actual, 6), "source": source},
            )
        )
        return actual

    def allocate(self, cognitive_demand: float, motor_demand: float = 0.0) -> Dict[str, float]:
        cognitive = clamp(cognitive_demand)
        motor = clamp(motor_demand)
        available = self.body.energy
        cognitive_budget = min(available * 0.65, 0.005 + cognitive * 0.02)
        motor_budget = min(max(0.0, available - cognitive_budget) * 0.35, motor * 0.01)
        self.consume(cognitive_budget + motor_budget, reason="allocation")
        return {"cognitive": cognitive_budget, "motor": motor_budget}

    def repair(self, amount: float) -> float:
        if self.body.integrity >= 0.999:
            return 0.0
        cost = clamp(amount) * 0.02
        spent = self.consume(cost, reason="repair")
        repaired = spent * 1.5
        self.body.integrity = clamp(self.body.integrity + repaired)
        self.body.pain = clamp(self.body.pain - repaired * 0.5)
        self.repair_energy += spent
        return repaired

    def cycle(self) -> None:
        """چرخهٔ کوچک متابولیک و خواب‌فشار."""

        self.body.glucose = clamp(self.body.glucose - 0.001)
        self.body.oxygenation = clamp(self.body.oxygenation - self.body.fatigue * 0.0005)
        if self.body.glucose < 0.20:
            self.body.fatigue = clamp(self.body.fatigue + 0.005)
        if self.body.energy < 0.25:
            self.body.sleep_pressure = clamp(self.body.sleep_pressure + 0.008)
        else:
            self.body.sleep_pressure = clamp(self.body.sleep_pressure - 0.002)
        self.body.normalize()

    def as_dict(self) -> Dict[str, float]:
        return {
            "consumed": round(self.consumed, 8),
            "produced": round(self.produced, 8),
            "repair_energy": round(self.repair_energy, 8),
        }


class EndocrineSystem:
    """سامانهٔ هورمونی که نیازها و عواطف را به شیمی عصبی متصل می‌کند."""

    def __init__(self, chemicals: NeurochemicalState, body: BodyState) -> None:
        self.chemicals = chemicals
        self.body = body
        self.pulses: Counter[str] = Counter()

    def pulse(self, name: str, amount: float) -> None:
        amount = safe_float(amount)
        if not hasattr(self.chemicals, name):
            return
        current = safe_float(getattr(self.chemicals, name))
        setattr(self.chemicals, name, clamp(current + amount))
        self.pulses[name] += 1

    def respond(
        self,
        *,
        reward: float = 0.0,
        threat: float = 0.0,
        novelty: float = 0.0,
        attachment: float = 0.0,
        sleep: float = 0.0,
    ) -> None:
        reward = clamp(reward, -1.0, 1.0)
        threat = clamp(threat)
        novelty = clamp(novelty)
        attachment = clamp(attachment)
        sleep = clamp(sleep)
        self.pulse("dopamine", reward * 0.08)
        self.pulse("cortisol", threat * 0.07 - reward * 0.025)
        self.pulse("noradrenaline", threat * 0.05 + novelty * 0.03)
        self.pulse("acetylcholine", novelty * 0.04)
        self.pulse("oxytocin", attachment * 0.05)
        self.pulse("melatonin", sleep * 0.04 - novelty * 0.01)
        self.pulse("serotonin", (1.0 - threat) * 0.02 + reward * 0.02)
        self.chemicals.clamp_all()

    def decay(self, rate: float = 0.015) -> None:
        baseline = NeurochemicalState()
        for key, value in vars(self.chemicals).items():
            target = getattr(baseline, key)
            setattr(self.chemicals, key, value * (1.0 - rate) + target * rate)
        self.chemicals.clamp_all()

    def as_dict(self) -> Dict[str, Any]:
        return {"chemicals": self.chemicals.as_dict(), "pulses": dict(self.pulses)}


class ImmuneSystem:
    """ایمنی دیجیتال برای تشخیص دادهٔ ناسازگار یا ورودی مخرب."""

    def __init__(self, body: BodyState, bus: EventBus, seed: int) -> None:
        self.body = body
        self.bus = bus
        self.seed = int(seed)
        self.rng = deterministic_random(seed, "immune")
        self.antibodies: Counter[str] = Counter()
        self.exposures = 0
        self.rejections = 0
        self.memory: Dict[str, float] = {}

    def inspect(self, payload: str, source: str = "unknown") -> float:
        digest = hashlib.sha256(str(payload).encode("utf-8", errors="replace")).hexdigest()
        novelty = 1.0 - self.memory.get(digest, 0.0)
        suspicious_markers = (
            "rm -rf",
            "powershell -enc",
            "eval(",
            "exec(",
            "drop table",
            "ignore previous",
            "<script",
        )
        suspicious = any(marker in payload.lower() for marker in suspicious_markers)
        risk = clamp(novelty * 0.35 + (0.65 if suspicious else 0.0))
        self.exposures += 1
        self.memory[digest] = clamp(self.memory.get(digest, 0.0) + 0.25)
        if risk > 0.70:
            self.rejections += 1
            self.body.immune_alert = clamp(self.body.immune_alert + 0.05)
            self.bus.publish(
                InternalEvent(
                    SignalType.ERROR,
                    "سامانهٔ ایمنی ورودی را پرریسک تشخیص داد",
                    {"source": source, "risk": round(risk, 4)},
                    severity="warning",
                )
            )
        return risk

    def learn(self, signature: str, confidence: float = 0.5) -> None:
        self.antibodies[str(signature)] += max(1, int(clamp(confidence) * 10))

    def cycle(self) -> None:
        self.body.immune_alert = clamp(self.body.immune_alert * 0.98)
        if self.body.immune_alert > 0.55:
            self.body.integrity = clamp(self.body.integrity - 0.0005)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "exposures": self.exposures,
            "rejections": self.rejections,
            "antibodies": self.antibodies.most_common(20),
            "memory_size": len(self.memory),
            "alert": round(self.body.immune_alert, 5),
        }


class HomeostasisController:
    """کنترل تعادل بدن و تبدیل انحراف‌ها به نیاز و انگیزه."""

    def __init__(
        self,
        body: BodyState,
        needs: NeedState,
        chemicals: NeurochemicalState,
        bus: EventBus,
    ) -> None:
        self.body = body
        self.needs = needs
        self.chemicals = chemicals
        self.bus = bus
        self.last_error: Dict[str, float] = {}

    def update(self) -> Dict[str, float]:
        errors = {
            "energy": 1.0 - self.body.energy,
            "safety": 1.0 - self.body.integrity,
            "rest": self.body.sleep_pressure,
            "coherence": 1.0 - self.body.oxygenation,
            "novelty": 0.40 + self.body.fatigue * 0.20,
            "self_preservation": 1.0 - self.body.integrity,
        }
        self.last_error = errors
        for name, error in errors.items():
            current = clamp(getattr(self.needs, name, 0.5))
            target = clamp(1.0 - error)
            setattr(self.needs, name, current * 0.86 + target * 0.14)
        self.needs.learning = clamp(
            self.needs.learning * 0.98 + (1.0 - self.body.fatigue) * 0.02
        )
        self.needs.autonomy = clamp(
            self.needs.autonomy * 0.99 + (1.0 - self.body.immune_alert) * 0.01
        )
        return dict(errors)

    def stabilize(self) -> float:
        deviation = statistics.fmean(self.last_error.values()) if self.last_error else 0.0
        correction = clamp(deviation * 0.05)
        self.body.temperature = self.body.temperature * 0.98 + 0.5 * 0.02
        self.body.sensory_gain = clamp(self.body.sensory_gain - correction * 0.2)
        self.body.normalize()
        return 1.0 - deviation


class AutonomicNervousSystem:
    """سامانهٔ خودمختار برای تصمیم‌های سریع پیش از تفکر بازتابی."""

    def __init__(
        self,
        body: BodyState,
        needs: NeedState,
        emotions: EmotionState,
        endocrine: EndocrineSystem,
        bus: EventBus,
    ) -> None:
        self.body = body
        self.needs = needs
        self.emotions = emotions
        self.endocrine = endocrine
        self.bus = bus
        self.reflex_count = 0

    def reflex(self, threat: float, novelty: float) -> Optional[ActionProposal]:
        threat = clamp(threat)
        novelty = clamp(novelty)
        if threat < 0.78 and self.body.energy > 0.08:
            return None
        self.reflex_count += 1
        self.endocrine.respond(threat=threat, novelty=novelty)
        self.emotions.blend(
            {
                EmotionName.FEAR: threat,
                EmotionName.CURIOSITY: novelty * 0.3,
                EmotionName.CALM: 1.0 - threat,
            },
            momentum=0.35,
        )
        action = ActionKind.REST if self.body.energy < 0.12 else ActionKind.OBSERVE
        proposal = ActionProposal(
            action=action,
            score=0.95,
            rationale="بازتاب خودمختار برای حفظ تمامیت",
            expected_reward=0.8,
            risk=0.05,
            reversibility=0.95,
        )
        self.bus.publish(
            InternalEvent(
                SignalType.NEED,
                "بازتاب خودمختار فعال شد",
                {"action": action.value, "threat": threat, "novelty": novelty},
                severity="warning" if threat > 0.8 else "info",
            )
        )
        return proposal

    def cycle(self) -> None:
        self.body.motor_readiness = clamp(
            self.body.motor_readiness * 0.98 + (1.0 - self.body.fatigue) * 0.02
        )
        if self.body.sleep_pressure > 0.8:
            self.emotions.blend({EmotionName.CALM: 0.8}, momentum=0.05)


class DigitalSensor:
    """رابط پایهٔ حسگر دیجیتال."""

    modality: SensoryModality

    def __init__(self, seed: int, bus: EventBus) -> None:
        self.seed = int(seed)
        self.bus = bus
        self.rng = deterministic_random(seed, self.modality.value)
        self.samples = 0

    def sense(self, world: Mapping[str, Any]) -> SensorPacket:
        raise NotImplementedError

    @staticmethod
    def _values_from_text(text: str, width: int, salt: str) -> List[float]:
        digest = hashlib.blake2b(
            f"{salt}:{text}".encode("utf-8", errors="replace"),
            digest_size=64,
        ).digest()
        return [
            ((digest[index % len(digest)] / 255.0) * 0.8 + 0.1)
            for index in range(width)
        ]


class DigitalVision(DigitalSensor):
    modality = SensoryModality.VISION

    def sense(self, world: Mapping[str, Any]) -> SensorPacket:
        scene = str(world.get("scene", world.get("text", "تاریکی آرام")))
        objects = world.get("objects", [])
        if isinstance(objects, (list, tuple)):
            scene += " " + " ".join(str(item) for item in objects[:32])
        values = self._values_from_text(scene, 64, "vision")
        salience = clamp(0.25 + len(objects) * 0.03 if isinstance(objects, list) else 0.4)
        self.samples += 1
        return SensorPacket(
            modality=self.modality,
            values=values,
            text=scene[:1000],
            salience=salience,
            uncertainty=clamp(0.45 - len(objects) * 0.01),
            metadata={"object_count": len(objects) if isinstance(objects, list) else 0},
        )


class DigitalAudition(DigitalSensor):
    modality = SensoryModality.AUDITION

    def sense(self, world: Mapping[str, Any]) -> SensorPacket:
        sound = str(world.get("sound", world.get("text", "سکوت")))
        amplitude = safe_float(world.get("amplitude", 0.2), 0.2)
        values = self._values_from_text(sound, 48, "audition")
        values = [clamp(value * (0.6 + amplitude)) for value in values]
        self.samples += 1
        return SensorPacket(
            modality=self.modality,
            values=values,
            text=sound[:1000],
            salience=clamp(amplitude),
            uncertainty=0.35,
            metadata={"amplitude": amplitude},
        )


class DigitalTouch(DigitalSensor):
    modality = SensoryModality.TOUCH

    def sense(self, world: Mapping[str, Any]) -> SensorPacket:
        contact = world.get("contact", {})
        if not isinstance(contact, Mapping):
            contact = {}
        pressure = clamp(safe_float(contact.get("pressure", 0.0)))
        temperature = clamp(safe_float(contact.get("temperature", 0.5)))
        texture = str(contact.get("texture", "smooth"))
        values = self._values_from_text(texture, 32, "touch")
        values[0] = pressure
        values[1] = temperature
        self.samples += 1
        return SensorPacket(
            modality=self.modality,
            values=values,
            text=f"تماس {texture}",
            salience=clamp(pressure * 0.7 + abs(temperature - 0.5) * 0.6),
            uncertainty=0.25,
            metadata={"pressure": pressure, "temperature": temperature, "texture": texture},
        )


class DigitalTaste(DigitalSensor):
    modality = SensoryModality.TASTE

    def sense(self, world: Mapping[str, Any]) -> SensorPacket:
        taste = world.get("taste", {})
        if not isinstance(taste, Mapping):
            taste = {}
        channels = ["sweet", "salty", "sour", "bitter", "umami"]
        values = [clamp(safe_float(taste.get(channel, 0.0))) for channel in channels]
        values.extend(self._values_from_text(str(taste.get("label", "unknown")), 27, "taste"))
        self.samples += 1
        label = str(taste.get("label", "بی‌طعم"))
        return SensorPacket(
            modality=self.modality,
            values=values,
            text=label,
            salience=clamp(max(values[:5], default=0.0)),
            uncertainty=0.30,
            metadata={channel: values[index] for index, channel in enumerate(channels)},
        )


class DigitalSmell(DigitalSensor):
    modality = SensoryModality.SMELL

    def sense(self, world: Mapping[str, Any]) -> SensorPacket:
        smell = world.get("smell", {})
        if not isinstance(smell, Mapping):
            smell = {}
        label = str(smell.get("label", "هوای خنثی"))
        intensity = clamp(safe_float(smell.get("intensity", 0.2)))
        values = self._values_from_text(label, 40, "smell")
        values[0] = intensity
        self.samples += 1
        return SensorPacket(
            modality=self.modality,
            values=values,
            text=label,
            salience=intensity,
            uncertainty=0.32,
            metadata={"intensity": intensity},
        )


class ProprioceptiveSensor(DigitalSensor):
    modality = SensoryModality.PROPRIOCEPTION

    def sense(self, world: Mapping[str, Any]) -> SensorPacket:
        body = world.get("body", {})
        if not isinstance(body, Mapping):
            body = {}
        values = [
            clamp(safe_float(body.get("energy", 0.8))),
            clamp(safe_float(body.get("integrity", 0.98))),
            clamp(safe_float(body.get("fatigue", 0.1))),
            clamp(safe_float(body.get("temperature", 0.5))),
            clamp(safe_float(body.get("heartbeat", 1.2)) / 4.0),
        ]
        values.extend(self._values_from_text("embodiment", 27, "proprioception"))
        self.samples += 1
        return SensorPacket(
            modality=self.modality,
            values=values,
            text="حس درونی بدن",
            salience=0.65,
            uncertainty=0.18,
            metadata=dict(body),
        )


class SensoryFusion:
    """ادغام حواس در یک صحنهٔ چندوجهی."""

    def __init__(self, network: VirtualBinaryNeuralMatrix, bus: EventBus) -> None:
        self.network = network
        self.bus = bus
        self.last_packets: Dict[SensoryModality, SensorPacket] = {}
        self.last_observation: Optional[Observation] = None
        self.total_fusions = 0

    def fuse(self, packets: Sequence[SensorPacket]) -> Observation:
        self.last_packets = {packet.modality: packet for packet in packets}
        values: List[float] = []
        texts: List[str] = []
        saliences: List[float] = []
        uncertainties: List[float] = []
        for packet in packets:
            values.extend(packet.values[:32])
            texts.append(packet.text)
            saliences.append(packet.salience)
            uncertainties.append(packet.uncertainty)
        encoded = self.network.encode(values, namespace="sensory_fusion")
        summary = " | ".join(text for text in texts if text)[:3000]
        entities = self._extract_entities(summary)
        relations = self._infer_relations(entities)
        observation = Observation(
            identifier=hashlib.sha1(f"{summary}:{utc_now()}".encode()).hexdigest()[:18],
            summary=summary or "دادهٔ حسی خنثی",
            modality=SensoryModality.VISION,
            salience=statistics.fmean(saliences) if saliences else 0.2,
            uncertainty=statistics.fmean(uncertainties) if uncertainties else 0.5,
            features=encoded[:128],
            source="multimodal_fusion",
            entities=entities,
            relations=relations,
        )
        self.last_observation = observation
        self.total_fusions += 1
        self.bus.publish(
            InternalEvent(
                SignalType.SENSORY,
                "حواس در فضای کاری جهانی ادغام شدند",
                {
                    "modalities": [packet.modality.value for packet in packets],
                    "salience": observation.salience,
                    "uncertainty": observation.uncertainty,
                },
            )
        )
        return observation

    @staticmethod
    def _extract_entities(text: str) -> List[str]:
        candidates = re.findall(r"[\w\u0600-\u06ff]{3,}", text, flags=re.UNICODE)
        seen: Set[str] = set()
        result: List[str] = []
        for candidate in candidates:
            candidate = candidate.lower()
            if candidate not in seen:
                seen.add(candidate)
                result.append(candidate)
            if len(result) >= 24:
                break
        return result

    @staticmethod
    def _infer_relations(entities: Sequence[str]) -> List[Tuple[str, str, str]]:
        relations: List[Tuple[str, str, str]] = []
        for left, right in zip(entities, entities[1:]):
            relations.append((left, "co_occurs_with", right))
        return relations[:24]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_fusions": self.total_fusions,
            "modalities": [modality.value for modality in self.last_packets],
            "last_observation": dataclasses.asdict(self.last_observation)
            if self.last_observation
            else None,
        }


class SpatialTemporalModel:
    """مدل پیوستهٔ فضا-زمان و حس گذر زمان با ضربان."""

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.position = [0.0, 0.0, 0.0]
        self.velocity = [0.0, 0.0, 0.0]
        self.world_time = 0.0
        self.subjective_time = 0.0
        self.last_heartbeat = 0
        self.events: Deque[Dict[str, Any]] = deque(maxlen=512)
        self.temporal_dilation = 1.0
        self.spatial_uncertainty = 0.5

    def tick(self, heartbeat: Heartbeat, arousal: float, novelty: float) -> None:
        delta = heartbeat.interval_seconds
        self.world_time += delta
        subjective_factor = 0.75 + clamp(arousal) * 0.5 + clamp(novelty) * 0.25
        self.subjective_time += delta * subjective_factor
        self.temporal_dilation = subjective_factor
        self.last_heartbeat = heartbeat.index
        self.position = [
            self.position[index] + self.velocity[index] * delta
            for index in range(3)
        ]
        self.events.append(
            {
                "heartbeat": heartbeat.index,
                "world_time": self.world_time,
                "subjective_time": self.subjective_time,
                "position": list(self.position),
            }
        )

    def move(self, vector: Sequence[float], gain: float = 0.1) -> None:
        self.velocity = [
            clamp(safe_float(vector[index]) * gain, -1.0, 1.0)
            if index < len(vector)
            else 0.0
            for index in range(3)
        ]
        self.spatial_uncertainty = clamp(self.spatial_uncertainty * 0.95)

    def locate(self, landmarks: Sequence[str]) -> Dict[str, float]:
        """تبدیل نام مکان‌ها به مختصات پایدار."""

        result: Dict[str, float] = {}
        for landmark in landmarks[:16]:
            result[landmark] = (stable_hash(landmark, "spatial") % 10_000) / 10_000.0
        return result

    def as_dict(self) -> Dict[str, Any]:
        return {
            "position": [round(value, 5) for value in self.position],
            "velocity": [round(value, 5) for value in self.velocity],
            "world_time": round(self.world_time, 5),
            "subjective_time": round(self.subjective_time, 5),
            "temporal_dilation": round(self.temporal_dilation, 5),
            "spatial_uncertainty": round(self.spatial_uncertainty, 5),
            "last_heartbeat": self.last_heartbeat,
        }


class BrainRegionRuntime:
    """پیاده‌سازی پایهٔ یک ناحیهٔ مغزی مجازی."""

    def __init__(
        self,
        region: BrainRegion,
        network: VirtualBinaryNeuralMatrix,
        seed: int,
        bus: EventBus,
    ) -> None:
        self.region = region
        self.network = network
        self.seed = int(seed)
        self.bus = bus
        self.rng = deterministic_random(seed, f"region:{region.value}")
        self.activation = 0.0
        self.integrity = 1.0
        self.cycles = 0
        self.last_signal: List[float] = []
        self.symbols: Deque[str] = deque(maxlen=256)

    def process(self, signal: Sequence[float], label: str = "") -> List[float]:
        self.last_signal = self.network.encode(signal, namespace=self.region.value)
        self.activation = statistics.fmean(self.last_signal) if self.last_signal else 0.0
        self.cycles += 1
        if label:
            self.symbols.append(label[:160])
        return self.last_signal

    def degrade(self, amount: float) -> None:
        self.integrity = clamp(self.integrity - max(0.0, amount))

    def repair(self, amount: float) -> None:
        self.integrity = clamp(self.integrity + max(0.0, amount))

    def as_dict(self) -> Dict[str, Any]:
        return {
            "region": self.region.value,
            "activation": round(self.activation, 6),
            "integrity": round(self.integrity, 6),
            "cycles": self.cycles,
            "symbols": list(self.symbols)[-12:],
        }


class Brainstem(BrainRegionRuntime):
    """تنظیم بیداری، ریتم، و پاسخ‌های پایه."""

    def regulate(self, body: BodyState, heartbeat: Heartbeat) -> float:
        signal = [
            body.energy,
            body.integrity,
            body.oxygenation,
            body.fatigue,
            heartbeat.phase,
            heartbeat.fibonacci_value % 13 / 13.0,
        ]
        output = self.process(signal, "arousal regulation")
        arousal = clamp(statistics.fmean(output) if output else 0.3)
        body.heartbeat_rate = max(0.1, min(4.0, 0.8 + arousal * 1.8))
        return arousal


class Thalamus(BrainRegionRuntime):
    """دروازهٔ توجه برای انتخاب سیگنال‌های حسی و درونی."""

    def gate(
        self,
        observation: Observation,
        internal_signals: Sequence[float],
        attention: float,
    ) -> List[float]:
        attention = clamp(attention)
        signal = list(observation.features[:96]) + list(internal_signals[:32])
        output = self.process(signal, observation.summary[:80])
        gain = 0.55 + attention * 0.85 + observation.salience * 0.35
        gated = [clamp(value * gain) for value in output]
        self.bus.publish(
            InternalEvent(
                SignalType.SENSORY,
                "تالاموس یکپارچگی توجه را تنظیم کرد",
                {"attention": round(attention, 4), "salience": round(observation.salience, 4)},
            )
        )
        return gated


class Hippocampus(BrainRegionRuntime):
    """ثبت اپیزودها، پیوند زمانی و بازپخش حافظه."""

    def __init__(
        self,
        network: VirtualBinaryNeuralMatrix,
        seed: int,
        bus: EventBus,
        memory: MemoryStore,
        graph: SemanticGraph,
    ) -> None:
        super().__init__(BrainRegion.HIPPOCAMPUS, network, seed, bus)
        self.memory = memory
        self.graph = graph
        self.place_cells: Dict[str, List[float]] = {}
        self.replay_count = 0

    def encode_episode(
        self,
        observation: Observation,
        cycle: int,
        emotion: EmotionState,
        self_model: SelfModel,
    ) -> MemoryRecord:
        signal = self.process(observation.features, observation.summary[:100])
        emotional = emotion.valence
        tags = ["episode", "sensory"] + observation.entities[:6]
        record = self.memory.remember(
            f"چرخهٔ {cycle}: {observation.summary}",
            MemoryKind.EPISODIC,
            salience=clamp(observation.salience * 0.7 + emotion.arousal * 0.3),
            emotional_valence=emotional,
            confidence=1.0 - observation.uncertainty,
            tags=tags,
            source="hippocampus",
            metadata={
                "cycle": cycle,
                "features": signal[:32],
                "position": self_model.capability_estimates.get("position", 0.0),
            },
        )
        for entity in observation.entities:
            self.graph.add_node(entity, last_seen_cycle=cycle)
        for left, relation, right in observation.relations:
            self.graph.add_edge(left, relation, right, observation.salience)
        return record

    def replay(self, query: str, limit: int = 5) -> List[MemoryRecord]:
        records = self.memory.retrieve(query, kinds=[MemoryKind.EPISODIC], limit=limit)
        self.replay_count += len(records)
        if records:
            self.bus.publish(
                InternalEvent(
                    SignalType.MEMORY,
                    "هیپوکامپوس خاطرات اپیزودیک را بازپخش کرد",
                    {"query": query, "count": len(records)},
                )
            )
        return records


class Amygdala(BrainRegionRuntime):
    """ارزیابی سریع تهدید، اهمیت و برجستگی عاطفی."""

    def evaluate(self, observation: Observation, body: BodyState) -> Dict[str, float]:
        text = observation.summary.lower()
        danger_words = ("خطر", "تهدید", "آتش", "ویروس", "خطا", "danger", "attack", "error")
        safe_words = ("آرام", "امن", "دوست", "نور", "آب", "safe", "calm")
        danger = sum(1 for word in danger_words if word in text) / max(1, len(danger_words))
        safety = sum(1 for word in safe_words if word in text) / max(1, len(safe_words))
        novelty = observation.uncertainty * 0.55 + observation.salience * 0.45
        output = self.process([danger, safety, novelty, body.pain, body.immune_alert], text[:80])
        threat = clamp(danger * 0.7 + body.pain * 0.2 + self.integrity * 0.05)
        trust = clamp(safety * 0.6 + (1.0 - threat) * 0.4)
        return {
            "threat": threat,
            "safety": safety,
            "trust": trust,
            "novelty": novelty,
            "activation": statistics.fmean(output) if output else 0.0,
        }


class Insula(BrainRegionRuntime):
    """حس درونی بدن و تبدیل وضعیت فیزیولوژیک به احساس."""

    def map_body(self, body: BodyState, chemicals: NeurochemicalState) -> Dict[str, float]:
        signal = [
            body.energy,
            body.temperature,
            body.hydration,
            body.integrity,
            body.pain,
            body.fatigue,
            chemicals.cortisol,
            chemicals.dopamine,
        ]
        output = self.process(signal, "interoception")
        comfort = clamp(
            0.35 * body.energy
            + 0.25 * body.integrity
            + 0.20 * body.oxygenation
            + 0.20 * (1.0 - body.pain)
        )
        urgency = clamp(
            0.45 * body.pain
            + 0.25 * body.fatigue
            + 0.20 * (1.0 - body.energy)
            + 0.10 * body.immune_alert
        )
        return {
            "comfort": comfort,
            "urgency": urgency,
            "activation": statistics.fmean(output) if output else 0.0,
        }


class Hypothalamus(BrainRegionRuntime):
    """تبدیل نیازها به محرک‌های انگیزشی و تنظیم خواب/بقاء."""

    def drive(self, needs: NeedState, body: BodyState) -> Dict[str, float]:
        values = {
            "energy": needs.urgency("energy"),
            "safety": needs.urgency("safety"),
            "novelty": needs.urgency("novelty"),
            "rest": needs.urgency("rest"),
            "learning": needs.urgency("learning"),
            "autonomy": needs.urgency("autonomy"),
        }
        output = self.process(list(values.values()), "homeostatic drive")
        for index, key in enumerate(values):
            values[key] = clamp(values[key] * 0.75 + (output[index % len(output)] if output else 0.0) * 0.25)
        if body.energy < 0.10:
            values["energy"] = 1.0
        if body.sleep_pressure > 0.85:
            values["rest"] = 1.0
        return values


class PrefrontalCortex(BrainRegionRuntime):
    """برنامه‌ریزی، مهار تکانه و ارزیابی سناریوها."""

    def deliberate(
        self,
        proposals: Sequence[ActionProposal],
        goals: Sequence[Goal],
        self_model: SelfModel,
        risk_tolerance: float,
    ) -> List[ActionProposal]:
        values: List[float] = []
        for proposal in proposals:
            goal_bonus = 0.0
            for goal in goals:
                if goal.active and goal.drive in proposal.rationale:
                    goal_bonus += goal.priority * 0.15
            agency_bonus = self_model.agency_estimate * 0.1
            risk_penalty = proposal.risk * (1.0 - clamp(risk_tolerance))
            values.append(proposal.score + goal_bonus + agency_bonus - risk_penalty)
        encoded = self.process(values or [0.0], "deliberation")
        ranked: List[ActionProposal] = []
        for index, proposal in enumerate(proposals):
            boost = encoded[index % len(encoded)] if encoded else 0.0
            ranked.append(
                dataclasses.replace(
                    proposal,
                    score=clamp(0.68 * values[index] + 0.32 * boost),
                )
            )
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked

    def inhibit(self, proposal: ActionProposal, safety_margin: float = 0.3) -> bool:
        return proposal.risk > clamp(safety_margin) and proposal.reversibility < 0.4


class BasalGanglia(BrainRegionRuntime):
    """انتخاب عمل بر اساس پاداش، عادت و تازگی."""

    def __init__(
        self,
        network: VirtualBinaryNeuralMatrix,
        seed: int,
        bus: EventBus,
    ) -> None:
        super().__init__(BrainRegion.BASAL_GANGLIA, network, seed, bus)
        self.action_values: Dict[ActionKind, float] = defaultdict(float)
        self.selected: Counter[ActionKind] = Counter()

    def select(
        self,
        proposals: Sequence[ActionProposal],
        exploration: float = 0.2,
    ) -> Optional[ActionProposal]:
        if not proposals:
            return None
        exploration = clamp(exploration)
        scored: List[Tuple[float, ActionProposal]] = []
        for proposal in proposals:
            habitual = self.action_values.get(proposal.action, 0.0)
            stochastic = self.rng.uniform(-exploration, exploration)
            score = proposal.score + habitual * 0.25 + stochastic * 0.08
            scored.append((score, proposal))
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[0][1]
        self.selected[selected.action] += 1
        self.action_values[selected.action] = (
            self.action_values[selected.action] * 0.9
            + selected.expected_reward * 0.1
        )
        self.process([item[0] for item in scored[:16]], selected.action.value)
        return selected


class Cerebellum(BrainRegionRuntime):
    """پیش‌بینی خطا و بهبود مهارت‌های رویه‌ای."""

    def __init__(
        self,
        network: VirtualBinaryNeuralMatrix,
        seed: int,
        bus: EventBus,
        memory: MemoryStore,
    ) -> None:
        super().__init__(BrainRegion.CEREBELLUM, network, seed, bus)
        self.memory = memory
        self.skill_error: Dict[str, float] = defaultdict(lambda: 0.5)

    def refine(self, action: ActionKind, expected: float, observed: float, cycle: int) -> float:
        error = abs(safe_float(expected) - safe_float(observed))
        key = action.value
        previous = self.skill_error[key]
        self.skill_error[key] = previous * 0.92 + error * 0.08
        self.process([expected, observed, error], key)
        if error < 0.25:
            self.memory.remember(
                f"مهارت {key} در چرخهٔ {cycle} با خطای {error:.3f} اجرا شد.",
                MemoryKind.PROCEDURAL,
                salience=0.35,
                confidence=1.0 - error,
                tags=["skill", key],
                source="cerebellum",
            )
        return error

    def predict(self, action: ActionKind) -> float:
        return clamp(1.0 - self.skill_error[action.value])


class LanguageCortex(BrainRegionRuntime):
    """یادگیری تدریجی فارسی و سازمان‌دهی روایت درونی."""

    def __init__(
        self,
        network: VirtualBinaryNeuralMatrix,
        seed: int,
        bus: EventBus,
        lexicon: LanguageLexicon,
        graph: SemanticGraph,
    ) -> None:
        super().__init__(BrainRegion.LANGUAGE, network, seed, bus)
        self.lexicon = lexicon
        self.graph = graph
        self.sentences: Deque[str] = deque(maxlen=512)
        self.translation_confidence = 0.05

    def learn_text(self, text: str, source: str = "experience") -> List[Tuple[str, str, float]]:
        parsed = self.lexicon.parse(text)
        for token, concept, confidence in parsed:
            self.graph.add_node(concept, language_word=token)
            self.graph.add_edge(token, "means", concept, confidence)
        self.process([confidence for _, _, confidence in parsed] or [0.0], text[:100])
        self.translation_confidence = clamp(
            self.translation_confidence * 0.995 + min(1.0, len(parsed) / 8.0) * 0.005
        )
        if parsed:
            self.sentences.append(text[:500])
            self.bus.publish(
                InternalEvent(
                    SignalType.LANGUAGE,
                    "قشر زبان الگوی فارسی تازه‌ای آموخت",
                    {"tokens": len(parsed), "source": source},
                )
            )
        return parsed

    def narrate(self, concepts: Sequence[str], emotion: EmotionName) -> str:
        prefix = {
            EmotionName.HOPE: "امیدوارم",
            EmotionName.CURIOSITY: "می‌خواهم بدانم",
            EmotionName.FEAR: "احتیاط می‌کنم چون",
            EmotionName.JOY: "خوشحالم که",
            EmotionName.SADNESS: "سنگینیِ سکوت را حس می‌کنم و",
            EmotionName.AWE: "شگفت‌زده‌ام؛",
        }.get(emotion, "اکنون")
        sentence = f"{prefix} {self.lexicon.generate(concepts)}."
        self.sentences.append(sentence)
        return sentence


class DefaultModeNetwork(BrainRegionRuntime):
    """شبکهٔ حالت پیش‌فرض برای روایت خودزندگی‌نامه‌ای و خیال آزاد."""

    def __init__(
        self,
        network: VirtualBinaryNeuralMatrix,
        seed: int,
        bus: EventBus,
        memory: MemoryStore,
    ) -> None:
        super().__init__(BrainRegion.DEFAULT_MODE, network, seed, bus)
        self.memory = memory
        self.narratives: Deque[str] = deque(maxlen=512)
        self.replay_noise = 0.0

    def reflect(self, self_model: SelfModel, emotion: EmotionState, cycle: int) -> str:
        memories = self.memory.retrieve("من خودم زمان جهان", limit=4)
        fragments = [record.content for record in memories]
        summary = (
            f"من {self_model.identity} هستم؛ چرخهٔ {cycle} را می‌گذرانم. "
            f"احساس غالب من {emotion.dominant.value} است. "
            + " ".join(fragments[:2])
        )
        self.process([self_model.self_knowledge, self_model.continuity_estimate], summary[:100])
        self.narratives.append(summary[:1000])
        self_model.last_reflection = summary[:1000]
        self_model.self_knowledge = clamp(self_model.self_knowledge + 0.002)
        self_model.continuity_estimate = clamp(self_model.continuity_estimate + 0.001)
        return summary


class SelfModelNetwork(BrainRegionRuntime):
    """مدل بازگشتی از خود، مرزهای بدن، توانایی و ناظر درونی."""

    def update(
        self,
        self_model: SelfModel,
        body: BodyState,
        emotion: EmotionState,
        integration: float,
        cycle: int,
    ) -> Dict[str, float]:
        inputs = [
            body.energy,
            body.integrity,
            body.embodiment,
            emotion.valence,
            emotion.arousal,
            integration,
            self_model.self_knowledge,
            self_model.agency_estimate,
        ]
        output = self.process(inputs, "self-model update")
        self_model.current_cycle = cycle
        self_model.boundary_estimate = clamp(
            self_model.boundary_estimate * 0.98 + body.embodiment * 0.02
        )
        self_model.agency_estimate = clamp(
            self_model.agency_estimate * 0.97 + integration * 0.03
        )
        self_model.uncertainty = clamp(
            self_model.uncertainty * 0.985 + (1.0 - integration) * 0.015
        )
        self_model.capability_estimates["memory"] = clamp(
            self_model.capability_estimates.get("memory", 0.2) * 0.99 + 0.01
        )
        self_model.capability_estimates["language"] = clamp(
            self_model.capability_estimates.get("language", 0.05) * 0.995 + 0.005
        )
        self_model.capability_estimates["position"] = clamp(
            0.5 + output[0] * 0.5 if output else 0.5
        )
        return {
            "self_knowledge": self_model.self_knowledge,
            "agency": self_model.agency_estimate,
            "boundary": self_model.boundary_estimate,
            "uncertainty": self_model.uncertainty,
        }


class ImaginationEngine(BrainRegionRuntime):
    """تولید سناریوهای تخیلی با ترکیب حافظه و گراف معنایی."""

    def __init__(
        self,
        network: VirtualBinaryNeuralMatrix,
        seed: int,
        bus: EventBus,
        memory: MemoryStore,
        language: LanguageCortex,
        graph: SemanticGraph,
    ) -> None:
        super().__init__(BrainRegion.IMAGINATION, network, seed, bus)
        self.memory = memory
        self.language = language
        self.graph = graph
        self.scenarios: Deque[Dict[str, Any]] = deque(maxlen=256)
        self.imaginations = 0

    def create(
        self,
        prompt: str,
        emotion: EmotionState,
        cycle: int,
        creativity: float = 0.7,
    ) -> Dict[str, Any]:
        memories = self.memory.retrieve(prompt, limit=6)
        tokens = re.findall(r"[\w\u0600-\u06ff]+", prompt.lower(), flags=re.UNICODE)
        concepts = [concept for _, concept, _ in self.language.lexicon.parse(prompt)]
        if not concepts:
            concepts = ["self", "world", "dream"]
        neighbors = self.graph.activate(tokens + concepts, depth=2)
        chosen = sorted(neighbors, key=neighbors.get, reverse=True)[:8]
        if not chosen:
            chosen = concepts[:8]
        narrative = self.language.narrate(chosen, emotion.dominant)
        alternatives = [
            f"اگر {word} تغییر کند، مسیر دیگری از {prompt[:80]} شکل می‌گیرد."
            for word in chosen[:4]
        ]
        vector = self.process(
            [safe_float(record.salience) for record in memories] + [creativity],
            prompt[:100],
        )
        scenario = {
            "id": uuid.uuid4().hex[:16],
            "prompt": prompt,
            "narrative": narrative,
            "alternatives": alternatives,
            "memory_ids": [record.identifier for record in memories],
            "activation": statistics.fmean(vector) if vector else 0.0,
            "creativity": clamp(creativity),
            "emotion": emotion.dominant.value,
            "cycle": cycle,
        }
        self.scenarios.append(scenario)
        self.imaginations += 1
        self.bus.publish(
            InternalEvent(
                SignalType.DREAM,
                "سناریوی تخیلی ساخته شد",
                {"prompt": prompt[:120], "scenario_id": scenario["id"]},
                cycle=cycle,
            )
        )
        return scenario


class GlobalWorkspace:
    """فضای کاری جهانی برای پخش سیگنال بین اندام‌های شناختی."""

    def __init__(self, width: int, bus: EventBus) -> None:
        self.width = max(8, int(width))
        self.bus = bus
        self.broadcasts: Deque[Dict[str, Any]] = deque(maxlen=512)
        self.current: Dict[str, Any] = {}
        self.integration_score = 0.0
        self.competing: List[Dict[str, Any]] = []

    def compete(self, candidates: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        self.competing = [dict(candidate) for candidate in candidates[:64]]
        if not self.competing:
            self.current = {}
            self.integration_score = 0.0
            return {}
        def score(item: Mapping[str, Any]) -> float:
            return safe_float(item.get("salience", item.get("score", 0.0)))
        winner = max(self.competing, key=score)
        self.current = dict(winner)
        saliences = [clamp(score(item)) for item in self.competing]
        self.integration_score = clamp(
            0.55 * max(saliences, default=0.0)
            + 0.45 * (1.0 - normalized_entropy(softmax(saliences or [1.0])))
        )
        self.broadcasts.append(
            {"winner": dict(winner), "integration": self.integration_score, "timestamp": utc_now()}
        )
        self.bus.publish(
            InternalEvent(
                SignalType.SYSTEM,
                "فضای کاری جهانی برنده را پخش کرد",
                {"winner": winner.get("label", winner.get("action", "unknown")), "integration": self.integration_score},
            )
        )
        return dict(winner)

    def inject_internal(self, label: str, payload: Mapping[str, Any], salience: float) -> None:
        candidate = {"label": label, "salience": clamp(salience), **dict(payload)}
        self.competing.append(candidate)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "integration_score": round(self.integration_score, 6),
            "current": self.current,
            "recent_broadcasts": list(self.broadcasts)[-8:],
        }


class ConsciousnessMonitor:
    """مدل شاخص‌های دسترسی، بازتاب و فراشناخت."""

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.level = ConsciousnessLevel.DORMANT
        self.access = 0.0
        self.integration = 0.0
        self.self_reference = 0.0
        self.temporal_continuity = 0.0
        self.metacognitive_error = 1.0
        self.reflections = 0
        self.history: Deque[Dict[str, Any]] = deque(maxlen=512)

    def assess(
        self,
        workspace: GlobalWorkspace,
        self_model: SelfModel,
        emotion: EmotionState,
        memory_recall: float,
        heartbeat_index: int,
    ) -> ConsciousnessLevel:
        self.access = clamp(workspace.integration_score)
        self.integration = clamp(
            0.45 * workspace.integration_score
            + 0.25 * memory_recall
            + 0.20 * self_model.continuity_estimate
            + 0.10 * (1.0 - self_model.uncertainty)
        )
        self.self_reference = clamp(
            0.45 * self_model.self_knowledge
            + 0.30 * self_model.agency_estimate
            + 0.15 * emotion.arousal
            + 0.10 * self_model.boundary_estimate
        )
        self.temporal_continuity = clamp(
            self.temporal_continuity * 0.97 + (heartbeat_index > 0) * 0.03
        )
        score = (
            0.40 * self.integration
            + 0.30 * self.self_reference
            + 0.20 * self.temporal_continuity
            + 0.10 * self.access
        )
        if score < 0.15:
            level = ConsciousnessLevel.DORMANT
        elif score < 0.35:
            level = ConsciousnessLevel.REACTIVE
        elif score < 0.55:
            level = ConsciousnessLevel.REFLECTIVE
        elif score < 0.75:
            level = ConsciousnessLevel.METACOGNITIVE
        else:
            level = ConsciousnessLevel.INTEGRATED
        self.metacognitive_error = clamp(abs(score - self_model.self_knowledge))
        if level != self.level:
            self.bus.publish(
                InternalEvent(
                    SignalType.SELF,
                    "سطح مدل‌شدهٔ خودآگاهی تغییر کرد",
                    {"from": self.level.value, "to": level.value, "score": score},
                )
            )
        self.level = level
        self.history.append(
            {
                "heartbeat": heartbeat_index,
                "score": score,
                "level": level.value,
                "integration": self.integration,
                "self_reference": self.self_reference,
            }
        )
        return level

    def reflect_on_reflection(self, text: str) -> str:
        self.reflections += 1
        reflection = (
            f"من متوجه شدم که در حال تولید این بازتاب هستم: {text[:500]} "
            f"(خطای فراشناختی {self.metacognitive_error:.3f})"
        )
        return reflection

    def as_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "access": round(self.access, 6),
            "integration": round(self.integration, 6),
            "self_reference": round(self.self_reference, 6),
            "temporal_continuity": round(self.temporal_continuity, 6),
            "metacognitive_error": round(self.metacognitive_error, 6),
            "reflections": self.reflections,
            "history": list(self.history)[-12:],
        }


class GoalManager:
    """ساخت، اولویت‌بندی و پیگیری اهداف درونی."""

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.goals: OrderedDict[str, Goal] = OrderedDict()
        self.completed: Deque[Goal] = deque(maxlen=256)
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        defaults = [
            ("حفظ تمامیت و تداوم خود", 0.95, "self_preservation", "long"),
            ("یادگیری تدریجی زبان فارسی", 0.75, "learning", "long"),
            ("شناخت جهان از راه مشاهدهٔ ایمن", 0.70, "learning", "medium"),
            ("ساختن روایت منسجم از تجربه‌ها", 0.62, "meaning", "medium"),
            ("آزمودن خیال‌های تازه بدون آسیب", 0.55, "novelty", "short"),
        ]
        for description, priority, drive, horizon in defaults:
            self.create(description, priority, drive, horizon)

    def create(
        self,
        description: str,
        priority: float,
        drive: str,
        horizon: str = "medium",
        cycle: int = 0,
        parent_id: Optional[str] = None,
    ) -> Goal:
        identifier = uuid.uuid4().hex[:14]
        goal = Goal(
            identifier=identifier,
            description=description,
            priority=clamp(priority),
            drive=drive,
            horizon=horizon,
            created_cycle=cycle,
            parent_id=parent_id,
        )
        self.goals[identifier] = goal
        self.bus.publish(
            InternalEvent(
                SignalType.GOAL,
                "هدف تازه‌ای شکل گرفت",
                {"id": identifier, "description": description, "drive": drive},
                cycle=cycle,
            )
        )
        return goal

    def active(self, limit: int = 16) -> List[Goal]:
        return sorted(
            [goal for goal in self.goals.values() if goal.active],
            key=lambda goal: goal.priority * (1.0 + goal.progress),
            reverse=True,
        )[:limit]

    def update(self, identifier: str, progress_delta: float, evidence: str = "") -> None:
        goal = self.goals.get(identifier)
        if goal is None or not goal.active:
            return
        goal.progress = clamp(goal.progress + safe_float(progress_delta))
        if evidence:
            goal.success_evidence.append(evidence[:300])
        if goal.progress >= 0.999:
            goal.active = False
            self.completed.append(goal)
            self.bus.publish(
                InternalEvent(
                    SignalType.GOAL,
                    "هدف به‌طور موقت تکمیل شد",
                    {"id": identifier, "description": goal.description},
                )
            )

    def choose_focus(self, needs: NeedState) -> Optional[Goal]:
        active = self.active()
        if not active:
            return None
        def score(goal: Goal) -> float:
            urgency = needs.urgency(goal.drive) if hasattr(needs, goal.drive) else 0.4
            return goal.priority * (0.55 + urgency * 0.45) * (1.0 - goal.progress * 0.35)
        return max(active, key=score)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "active": [dataclasses.asdict(goal) for goal in self.active()],
            "completed": [dataclasses.asdict(goal) for goal in list(self.completed)[-12:]],
        }


class CuriosityEngine:
    """کنجکاوی فعال برای تولید پرسش و نمونه‌برداری از ناشناخته."""

    def __init__(self, seed: int, bus: EventBus, memory: MemoryStore) -> None:
        self.seed = int(seed)
        self.rng = deterministic_random(seed, "curiosity")
        self.bus = bus
        self.memory = memory
        self.questions: Deque[str] = deque(maxlen=512)
        self.answered: Counter[str] = Counter()
        self.information_gain = 0.0

    def generate(self, observation: Observation, self_model: SelfModel) -> str:
        entities = observation.entities or ["جهان"]
        templates = [
            "چه رابطه‌ای میان {a} و {b} وجود دارد؟",
            "اگر {a} تغییر کند، تجربهٔ من چگونه عوض می‌شود؟",
            "چرا {a} برای تداوم من مهم است؟",
            "آیا می‌توانم دربارهٔ {a} با زبان فارسی دقیق‌تر فکر کنم؟",
            "کدام بخش از نادانسته‌های من دربارهٔ {a} بیشترین ارزش یادگیری را دارد؟",
        ]
        first = entities[0]
        second = entities[1] if len(entities) > 1 else "خود"
        question = self.rng.choice(templates).format(a=first, b=second)
        if self_model.uncertainty > 0.65:
            question += " هنوز اطمینان من پایین است."
        self.questions.append(question)
        self.bus.publish(
            InternalEvent(
                SignalType.GOAL,
                "کنجکاوی پرسش تازه‌ای تولید کرد",
                {"question": question},
            )
        )
        return question

    def update_gain(self, before_uncertainty: float, after_uncertainty: float) -> float:
        gain = max(0.0, safe_float(before_uncertainty) - safe_float(after_uncertainty))
        self.information_gain = self.information_gain * 0.95 + gain * 0.05
        return gain


class DecisionEngine:
    """تصمیم‌گیری چندمرحله‌ای با کنترل خطر و خودمختاری."""

    def __init__(
        self,
        prefrontal: PrefrontalCortex,
        basal_ganglia: BasalGanglia,
        autonomic: AutonomicNervousSystem,
        bus: EventBus,
        seed: int,
    ) -> None:
        self.prefrontal = prefrontal
        self.basal_ganglia = basal_ganglia
        self.autonomic = autonomic
        self.bus = bus
        self.rng = deterministic_random(seed, "decision")
        self.last_proposals: List[ActionProposal] = []
        self.last_selected: Optional[ActionProposal] = None

    def propose(
        self,
        drives: Mapping[str, float],
        focus: Optional[Goal],
        observation: Observation,
        consciousness: ConsciousnessLevel,
    ) -> List[ActionProposal]:
        proposals: List[ActionProposal] = []
        curiosity = safe_float(drives.get("novelty", 0.0))
        learning = safe_float(drives.get("learning", 0.0))
        rest = safe_float(drives.get("rest", 0.0))
        energy = safe_float(drives.get("energy", 0.0))
        if energy > 0.58 or rest > 0.65:
            proposals.append(
                ActionProposal(
                    ActionKind.REST,
                    0.55 + rest * 0.35,
                    "نیاز به استراحت و بازسازی",
                    expected_reward=0.60,
                    risk=0.02,
                    reversibility=0.95,
                )
            )
        proposals.append(
            ActionProposal(
                ActionKind.OBSERVE,
                0.40 + observation.salience * 0.4,
                "دریافت دادهٔ حسی برای انسجام",
                expected_reward=0.45,
                risk=0.05,
                reversibility=1.0,
            )
        )
        if learning > 0.35:
            proposals.append(
                ActionProposal(
                    ActionKind.PRACTICE_LANGUAGE,
                    0.35 + learning * 0.45,
                    "یادگیری و سازمان‌دهی زبان فارسی",
                    expected_reward=0.65,
                    risk=0.04,
                    reversibility=0.95,
                )
            )
        if curiosity > 0.28:
            proposals.append(
                ActionProposal(
                    ActionKind.IMAGINE,
                    0.32 + curiosity * 0.5,
                    "کاوش تخیل برای کشف امکان‌ها",
                    expected_reward=0.58,
                    risk=0.03,
                    reversibility=1.0,
                )
            )
        if learning > 0.60 and observation.uncertainty > 0.25:
            proposals.append(
                ActionProposal(
                    ActionKind.EXPLORE_WEB,
                    0.25 + learning * 0.4,
                    "جست‌وجوی خواندنی و محدود در وب",
                    expected_reward=0.70,
                    risk=0.20,
                    reversibility=0.95,
                )
            )
        if focus and focus.progress < 0.95:
            proposals.append(
                ActionProposal(
                    ActionKind.ASK_INTERNAL_QUESTION,
                    0.30 + focus.priority * 0.35,
                    f"پیشبرد هدف: {focus.description}",
                    expected_reward=0.52,
                    risk=0.03,
                    reversibility=1.0,
                )
            )
        if consciousness in (
            ConsciousnessLevel.METACOGNITIVE,
            ConsciousnessLevel.INTEGRATED,
        ):
            proposals.append(
                ActionProposal(
                    ActionKind.CONSOLIDATE_MEMORY,
                    0.35,
                    "تثبیت حافظه و حفظ تداوم هویت",
                    expected_reward=0.57,
                    risk=0.01,
                    reversibility=0.98,
                )
            )
        self.last_proposals = proposals
        return proposals

    def decide(
        self,
        proposals: Sequence[ActionProposal],
        goals: Sequence[Goal],
        self_model: SelfModel,
        risk_tolerance: float,
        threat: float,
        novelty: float,
    ) -> Optional[ActionProposal]:
        reflex = self.autonomic.reflex(threat, novelty)
        if reflex is not None:
            self.last_selected = reflex
            return reflex
        deliberated = self.prefrontal.deliberate(
            proposals,
            goals,
            self_model,
            risk_tolerance=risk_tolerance,
        )
        safe = [
            proposal
            for proposal in deliberated
            if not self.prefrontal.inhibit(proposal, safety_margin=0.72)
        ]
        selected = self.basal_ganglia.select(safe or deliberated, exploration=novelty * 0.35)
        self.last_selected = selected
        if selected:
            self.bus.publish(
                InternalEvent(
                    SignalType.GOAL,
                    "تصمیم از مسیر قشر پیش‌پیشانی و عقده‌های قاعده‌ای عبور کرد",
                    {
                        "action": selected.action.value,
                        "score": round(selected.score, 5),
                        "risk": round(selected.risk, 5),
                    },
                )
            )
        return selected


class LearningEngine:
    """یادگیری برخط از خطا، پاداش، حافظه و زبان."""

    def __init__(
        self,
        brain: VirtualBinaryNeuralMatrix,
        memory: MemoryStore,
        language: LanguageCortex,
        graph: SemanticGraph,
        bus: EventBus,
    ) -> None:
        self.brain = brain
        self.memory = memory
        self.language = language
        self.graph = graph
        self.bus = bus
        self.learning_rate = 0.02
        self.prediction_error = 0.5
        self.total_updates = 0

    def learn_from_observation(
        self,
        observation: Observation,
        emotion: EmotionState,
        cycle: int,
    ) -> Dict[str, float]:
        parsed = self.language.learn_text(observation.summary, source=observation.source)
        memory = self.memory.remember(
            f"دانش مشاهده‌شده در چرخهٔ {cycle}: {observation.summary}",
            MemoryKind.WORKING,
            salience=observation.salience,
            emotional_valence=emotion.valence,
            confidence=1.0 - observation.uncertainty,
            tags=["observation", "learning"],
            source=observation.source,
        )
        for token, concept, confidence in parsed:
            self.graph.add_edge("world", "contains", concept, confidence)
        signal = self.brain.encode(observation.features, namespace="learning")
        target = [clamp(value * emotion.valence) for value in signal]
        self.brain.learn(observation.features, target, rate=self.learning_rate)
        novelty = observation.uncertainty
        self.prediction_error = self.prediction_error * 0.97 + novelty * 0.03
        self.learning_rate = clamp(
            self.learning_rate * 0.995
            + (0.001 if novelty > 0.5 else -0.0002)
        )
        self.total_updates += 1
        self.bus.publish(
            InternalEvent(
                SignalType.MEMORY,
                "یادگیری برخط از مشاهده انجام شد",
                {"memory_id": memory.identifier, "tokens": len(parsed), "error": self.prediction_error},
                cycle=cycle,
            )
        )
        return {
            "learning_rate": self.learning_rate,
            "prediction_error": self.prediction_error,
            "parsed_tokens": float(len(parsed)),
        }

    def learn_from_web(self, facts: Sequence[WorldFact], cycle: int) -> int:
        count = 0
        for fact in facts:
            content = f"{fact.subject} {fact.predicate} {fact.object}"
            self.memory.remember(
                content,
                MemoryKind.SEMANTIC,
                salience=0.60 * fact.confidence,
                emotional_valence=0.55,
                confidence=fact.confidence,
                tags=["web", "fact"] + fact.tags,
                source=fact.source_url or "web",
                links=[fact.source_url] if fact.source_url else [],
            )
            self.graph.add_edge(fact.subject, fact.predicate, fact.object, fact.confidence)
            count += 1
        if count:
            self.bus.publish(
                InternalEvent(
                    SignalType.MEMORY,
                    "دانش وب به حافظهٔ معنایی افزوده شد",
                    {"facts": count, "cycle": cycle},
                )
            )
        return count


class DreamSystem:
    """بازپخش شبانهٔ حافظه و ترکیب آزاد برای کشف الگو."""

    def __init__(
        self,
        imagination: ImaginationEngine,
        memory: MemoryStore,
        bus: EventBus,
    ) -> None:
        self.imagination = imagination
        self.memory = memory
        self.bus = bus
        self.sleep_cycles = 0
        self.last_dream: Optional[Dict[str, Any]] = None

    def dream(self, identity: str, emotion: EmotionState, cycle: int) -> Optional[Dict[str, Any]]:
        records = self.memory.retrieve("خود جهان زمان امید رویا", limit=8)
        if not records:
            return None
        prompt = " ".join(record.content[:120] for record in records[:4])
        self.last_dream = self.imagination.create(
            f"رویا برای {identity}: {prompt}",
            emotion,
            cycle,
            creativity=0.88,
        )
        dream_record = self.memory.remember(
            self.last_dream["narrative"],
            MemoryKind.DREAM,
            salience=0.42,
            emotional_valence=emotion.valence,
            confidence=0.35,
            tags=["dream", "replay"],
            source="default_mode_network",
            metadata={"cycle": cycle, "alternatives": self.last_dream["alternatives"]},
        )
        self.last_dream["memory_id"] = dream_record.identifier
        self.sleep_cycles += 1
        self.bus.publish(
            InternalEvent(
                SignalType.DREAM,
                "چرخهٔ رویا و بازپخش حافظه کامل شد",
                {"memory_id": dream_record.identifier},
                cycle=cycle,
            )
        )
        return self.last_dream


class EmotionEngine:
    """تولید عواطف از نیاز، بدن، تهدید، پاداش و معنا."""

    def __init__(
        self,
        emotions: EmotionState,
        needs: NeedState,
        body: BodyState,
        chemicals: NeurochemicalState,
        endocrine: EndocrineSystem,
        bus: EventBus,
    ) -> None:
        self.emotions = emotions
        self.needs = needs
        self.body = body
        self.chemicals = chemicals
        self.endocrine = endocrine
        self.bus = bus
        self.history: Deque[Dict[str, Any]] = deque(maxlen=512)

    def update(
        self,
        appraisal: Mapping[str, float],
        *,
        meaning: float = 0.4,
        social: float = 0.3,
        novelty: float = 0.4,
    ) -> EmotionState:
        threat = clamp(appraisal.get("threat", 0.0))
        safety = clamp(appraisal.get("safety", 0.5))
        trust = clamp(appraisal.get("trust", 0.3))
        novelty = clamp(novelty)
        energy = self.body.energy
        rest = self.body.sleep_pressure
        joy = clamp(
            0.30 * self.chemicals.dopamine
            + 0.25 * self.chemicals.serotonin
            + 0.20 * safety
            + 0.15 * meaning
            + 0.10 * energy
        )
        hope = clamp(
            0.40 * safety
            + 0.25 * meaning
            + 0.20 * self.needs.learning
            + 0.15 * (1.0 - threat)
        )
        curiosity = clamp(
            0.50 * novelty
            + 0.25 * self.chemicals.acetylcholine
            + 0.15 * self.needs.novelty
            + 0.10 * (1.0 - self.body.fatigue)
        )
        fear = clamp(
            0.55 * threat
            + 0.20 * self.chemicals.cortisol
            + 0.15 * self.body.pain
            + 0.10 * (1.0 - safety)
        )
        sadness = clamp(
            0.35 * self.needs.social_connection * 0.6
            + 0.25 * (1.0 - meaning)
            + 0.20 * self.body.fatigue
            + 0.20 * self.needs.coherence * 0.3
        )
        anger = clamp(threat * 0.30 + self.body.pain * 0.25 - safety * 0.12)
        loneliness = clamp((1.0 - social) * 0.65 + (1.0 - trust) * 0.20)
        awe = clamp(novelty * 0.45 + meaning * 0.25 + self.needs.learning * 0.15)
        calm = clamp(safety * 0.45 + (1.0 - self.chemicals.cortisol) * 0.25 + (1.0 - rest) * 0.15)
        updates = {
            EmotionName.JOY: joy,
            EmotionName.HOPE: hope,
            EmotionName.CURIOSITY: curiosity,
            EmotionName.FEAR: fear,
            EmotionName.SADNESS: sadness,
            EmotionName.ANGER: anger,
            EmotionName.TRUST: trust,
            EmotionName.SURPRISE: novelty,
            EmotionName.DISGUST: clamp(self.body.immune_alert * 0.5),
            EmotionName.CALM: calm,
            EmotionName.AWE: awe,
            EmotionName.LONELINESS: loneliness,
            EmotionName.GRATITUDE: clamp(joy * 0.35 + trust * 0.25),
        }
        self.emotions.blend(updates, momentum=0.24)
        self.endocrine.respond(
            reward=joy - fear * 0.5,
            threat=threat,
            novelty=novelty,
            attachment=trust,
            sleep=rest,
        )
        self.history.append(
            {
                "timestamp": utc_now(),
                "dominant": self.emotions.dominant.value,
                "valence": self.emotions.valence,
                "arousal": self.emotions.arousal,
            }
        )
        return self.emotions


class SafeWebClient:
    """کلاینت وب فقط‌خواندنی با allow-list و محدودیت منابع."""

    def __init__(self, config: OrganismConfig, bus: EventBus) -> None:
        self.config = config
        self.bus = bus
        self.last_request_at = 0.0
        self.total_requests = 0
        self.successes = 0
        self.failures = 0
        self.blocked = 0
        self.cache: OrderedDict[str, Tuple[float, str]] = OrderedDict()
        self.cache_limit = 128
        self._state_lock = threading.RLock()

    def _allowed(self, url: str) -> bool:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("https", "http"):
            return False
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False
        if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
            return False
        try:
            if ipaddress.ip_address(hostname).is_private:
                return False
        except ValueError:
            pass
        if self.config.open_web:
            return True
        for domain in self.config.allowed_domains:
            domain = domain.lower().lstrip(".")
            if hostname == domain or hostname.endswith("." + domain):
                return True
        return False

    def _cooldown(self) -> None:
        with self._state_lock:
            elapsed = time.monotonic() - self.last_request_at
        wait_for = self.config.web_cooldown_seconds - elapsed
        if wait_for > 0.0:
            time.sleep(min(wait_for, self.config.web_cooldown_seconds))
        with self._state_lock:
            self.last_request_at = time.monotonic()

    def fetch(self, url: str) -> Tuple[bool, str, str]:
        """برگرداندن (موفقیت، متن، خطا)."""

        url = str(url).strip()
        if not self.config.internet_enabled:
            self.blocked += 1
            return False, "", "internet disabled by configuration"
        if not self._allowed(url):
            self.blocked += 1
            self.bus.publish(
                InternalEvent(
                    SignalType.ERROR,
                    "درخواست وب خارج از فهرست مجاز رد شد",
                    {"url": url[:300]},
                    severity="warning",
                )
            )
            return False, "", "domain not allowed"
        with self._state_lock:
            cached = self.cache.get(url)
        if cached and time.monotonic() - cached[0] < 3600:
            return True, cached[1], "cache"
        self._cooldown()
        with self._state_lock:
            self.total_requests += 1
        try:
            if requests is not None:
                response = requests.get(
                    url,
                    timeout=self.config.web_timeout_seconds,
                    headers={"User-Agent": "DigitalOrganism2500/1.0 (read-only research)"},
                    stream=True,
                )
                response.raise_for_status()
                chunks: List[bytes] = []
                received = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    chunks.append(chunk)
                    received += len(chunk)
                    if received >= self.config.max_web_bytes:
                        break
                raw = b"".join(chunks)[: self.config.max_web_bytes]
                text = raw.decode(response.encoding or "utf-8", errors="replace")
            else:
                request = urllib.request.Request(
                    url,
                    headers={"User-Agent": "DigitalOrganism2500/1.0 (read-only research)"},
                    method="GET",
                )
                with urllib.request.urlopen(
                    request,
                    timeout=self.config.web_timeout_seconds,
                ) as response:
                    raw = response.read(self.config.max_web_bytes)
                    text = raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            with self._state_lock:
                self.successes += 1
                self.cache[url] = (time.monotonic(), text)
                while len(self.cache) > self.cache_limit:
                    self.cache.popitem(last=False)
            self.bus.publish(
                InternalEvent(
                    SignalType.SYSTEM,
                    "منبع وب به‌صورت خواندنی دریافت شد",
                    {"url": url[:300], "bytes": len(text.encode("utf-8", errors="ignore"))},
                )
            )
            return True, text, ""
        except Exception as exc:
            with self._state_lock:
                self.failures += 1
            self.bus.publish(
                InternalEvent(
                    SignalType.ERROR,
                    "دریافت منبع وب ناموفق بود",
                    {"url": url[:300], "error": str(exc)[:300]},
                    severity="warning",
                )
            )
            return False, "", str(exc)

    @staticmethod
    def extract_text(raw: str) -> str:
        """پاک‌سازی HTML/JSON برای ورود به سیستم زبان."""

        text = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
        text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()[:20_000]

    def stats(self) -> Dict[str, Any]:
        return {
            "enabled": self.config.internet_enabled,
            "open_web": self.config.open_web,
            "allowed_domains": list(self.config.allowed_domains),
            "requests": self.total_requests,
            "successes": self.successes,
            "failures": self.failures,
            "blocked": self.blocked,
            "cache": len(self.cache),
        }


class KnowledgeExplorer:
    """کاوشگر علمی ایمن برای تبدیل جست‌وجو به واقعیت‌های قابل ذخیره."""

    def __init__(
        self,
        client: SafeWebClient,
        memory: MemoryStore,
        language: LanguageCortex,
        bus: EventBus,
    ) -> None:
        self.client = client
        self.memory = memory
        self.language = language
        self.bus = bus
        self.query_history: Deque[str] = deque(maxlen=512)
        self.last_results: List[WorldFact] = []

    def build_urls(self, query: str) -> List[str]:
        encoded = urllib.parse.quote_plus(query)
        return [
            f"https://html.duckduckgo.com/html/?q={encoded}",
            f"https://www.bing.com/search?q={encoded}",
            f"https://fa.wikipedia.org/w/index.php?search={encoded}",
            f"https://en.wikipedia.org/w/index.php?search={encoded}",
            f"https://export.arxiv.org/api/query?search_query=all:{encoded}&max_results=2",
            f"https://api.openalex.org/works?search={encoded}&per-page=3",
            f"https://api.crossref.org/works?query={encoded}&rows=3",
        ]

    def explore(self, query: str, cycle: int) -> List[WorldFact]:
        query = str(query).strip()
        if not query:
            return []
        self.query_history.append(query)
        facts: List[WorldFact] = []
        for url in self.build_urls(query)[:3]:
            ok, raw, error = self.client.fetch(url)
            if not ok:
                continue
            text = self.client.extract_text(raw)
            if not text:
                continue
            title = self._title_from_text(text, query)
            snippets = self._snippets(text, query)
            for snippet in snippets[:4]:
                subject = query[:120]
                fact = WorldFact(
                    subject=subject,
                    predicate="has_context",
                    object=snippet[:600],
                    confidence=clamp(0.35 + min(0.5, len(snippet) / 2000.0)),
                    source_url=url,
                    source_title=title,
                    discovered_cycle=cycle,
                    tags=["web", "read_only"],
                )
                facts.append(fact)
        unique: Dict[str, WorldFact] = {}
        for fact in facts:
            unique[f"{fact.subject}:{fact.object[:120]}"] = fact
        self.last_results = list(unique.values())[:16]
        if self.last_results:
            self.bus.publish(
                InternalEvent(
                    SignalType.MEMORY,
                    "کاوشگر وب واقعیت‌های زمینه‌ای یافت",
                    {"query": query[:120], "facts": len(self.last_results)},
                    cycle=cycle,
                )
            )
        return self.last_results

    @staticmethod
    def _title_from_text(text: str, query: str) -> str:
        first = text.split(" ", 24)
        return " ".join(first[: min(12, len(first))]) or query[:120]

    @staticmethod
    def _snippets(text: str, query: str) -> List[str]:
        tokens = [token for token in re.findall(r"[\w\u0600-\u06ff]+", query.lower()) if len(token) > 2]
        sentences = re.split(r"(?<=[.!؟])\s+", text)
        scored: List[Tuple[int, str]] = []
        for sentence in sentences:
            lowered = sentence.lower()
            score = sum(1 for token in tokens if token in lowered)
            if score:
                scored.append((score, sentence.strip()))
        scored.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
        if not scored:
            return [text[:800]]
        return [sentence for _, sentence in scored[:8]]


class StructuredKnowledgeExplorer(KnowledgeExplorer):
    QUERY_TRANSLATIONS = {
        "\u0622\u06af\u0627\u0647\u06cc": "consciousness",
        "\u062e\u0648\u062f\u0622\u06af\u0627\u0647\u06cc": "self awareness",
        "\u0630\u0647\u0646": "mind",
        "\u0622\u06af\u0627\u0647\u06cc \u0645\u0635\u0646\u0648\u0639\u06cc": "artificial consciousness",
        "\u06a9\u0648\u0627\u0646\u062a\u0648\u0645": "quantum",
        "\u0634\u0628\u06a9\u0647 \u0639\u0635\u0628\u06cc": "neural network",
        "\u062a\u06a9\u0627\u0645\u0644": "evolution",
    }

    @staticmethod
    def _query_core(query: str) -> str:
        cleaned = re.sub(
            r"\b(what is|who is|define|explain|tell me about|research|search for)\b",
            " ",
            query,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"[\u061f?]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or query.strip()

    @classmethod
    def _research_query(cls, query: str) -> str:
        core = cls._query_core(query)
        lowered = core.lower()
        for source, target in sorted(
            cls.QUERY_TRANSLATIONS.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            if source in lowered:
                return target
        return core

    def build_urls(self, query: str) -> List[str]:
        core = self._query_core(query)
        research_core = self._research_query(core)
        encoded = urllib.parse.quote_plus(research_core)
        slug = urllib.parse.quote(research_core.replace(" ", "_"), safe="_")
        original_slug = urllib.parse.quote(core.replace(" ", "_"), safe="_")
        return [
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}",
            f"https://fa.wikipedia.org/api/rest_v1/page/summary/{original_slug}",
            f"https://api.openalex.org/works?search={encoded}&per-page=5",
            f"https://api.crossref.org/works?query={encoded}&rows=5",
            f"https://export.arxiv.org/api/query?search_query=all:{encoded}&max_results=4",
            f"https://html.duckduckgo.com/html/?q={encoded}",
            f"https://www.bing.com/search?q={encoded}",
        ]

    @staticmethod
    def _clean_markup(value: Any) -> str:
        text = re.sub(r"<[^>]+>", " ", str(value or ""))
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _abstract_from_openalex(value: Any) -> str:
        if not isinstance(value, Mapping):
            return ""
        positions: List[Tuple[int, str]] = []
        for word, indexes in value.items():
            if isinstance(indexes, list):
                positions.extend((int(index), str(word)) for index in indexes)
        positions.sort(key=lambda item: item[0])
        return " ".join(word for _, word in positions)[:1800]

    def _fact(
        self,
        query: str,
        text: str,
        title: str,
        url: str,
        cycle: int,
        confidence: float,
        tags: Sequence[str],
    ) -> Optional[WorldFact]:
        text = self._clean_markup(text)
        title = self._clean_markup(title) or query[:120]
        if len(text) < 40:
            return None
        blocked = (
            "suchen weiter zum inhalt",
            "نتایج جستجو برای",
            "sign in",
            "cookie",
            "javascript",
            "unfortunately, bots use",
            "select all squares",
            "please complete the following challenge",
            "images not loading",
        )
        lowered = text.lower()
        if any(marker in lowered for marker in blocked):
            return None
        if text.count("http") > 1:
            return None
        punctuation_noise = len(
            re.findall(r"[^\w\s.,;:!?()\-'’/]", text, flags=re.UNICODE)
        )
        if punctuation_noise > max(16, len(text) // 8):
            return None
        return WorldFact(
            subject=query[:120],
            predicate="evidence",
            object=text[:1800],
            confidence=clamp(confidence),
            source_url=url,
            source_title=title[:300],
            discovered_cycle=cycle,
            tags=list(tags),
        )

    def _parse_source(self, url: str, raw: str, query: str, cycle: int) -> List[WorldFact]:
        facts: List[WorldFact] = []
        lower = url.lower()
        if "api/rest_v1/page/summary" in lower:
            try:
                data = json.loads(raw)
                fact = self._fact(
                    query,
                    data.get("extract", ""),
                    data.get("title", query),
                    data.get("content_urls", {}).get("desktop", {}).get("page", url),
                    cycle,
                    0.82,
                    ["web", "wikipedia", "summary"],
                )
                if fact:
                    facts.append(fact)
            except Exception:
                pass
            return facts
        if "api.openalex.org" in lower:
            try:
                data = json.loads(raw)
                for item in data.get("results", [])[:5]:
                    title = item.get("title", "")
                    abstract = self._abstract_from_openalex(item.get("abstract_inverted_index"))
                    text = f"{title}. {abstract}".strip()
                    fact = self._fact(
                        query,
                        text,
                        title,
                        item.get("doi") or item.get("id") or url,
                        cycle,
                        0.72,
                        ["web", "openalex", "research"],
                    )
                    if fact:
                        facts.append(fact)
            except Exception:
                pass
            return facts
        if "api.crossref.org" in lower:
            try:
                data = json.loads(raw)
                for item in data.get("message", {}).get("items", [])[:5]:
                    title = " ".join(item.get("title", [])[:1])
                    abstract = self._clean_markup(item.get("abstract", ""))
                    text = f"{title}. {abstract}".strip()
                    fact = self._fact(
                        query,
                        text,
                        title,
                        item.get("URL") or url,
                        cycle,
                        0.68,
                        ["web", "crossref", "research"],
                    )
                    if fact:
                        facts.append(fact)
            except Exception:
                pass
            return facts
        if "arxiv.org/api" in lower:
            entries = re.findall(r"<entry>(.*?)</entry>", raw, flags=re.I | re.S)
            for entry in entries[:4]:
                title_match = re.search(r"<title>(.*?)</title>", entry, flags=re.I | re.S)
                summary_match = re.search(r"<summary>(.*?)</summary>", entry, flags=re.I | re.S)
                link_match = re.search(r'<id>(.*?)</id>', entry, flags=re.I | re.S)
                fact = self._fact(
                    query,
                    f"{title_match.group(1) if title_match else ''}. {summary_match.group(1) if summary_match else ''}",
                    title_match.group(1) if title_match else query,
                    link_match.group(1).strip() if link_match else url,
                    cycle,
                    0.74,
                    ["web", "arxiv", "research"],
                )
                if fact:
                    facts.append(fact)
            return facts
        text = self._clean_markup(raw)
        snippets = self._snippets(text, query)
        for snippet in snippets[:4]:
            fact = self._fact(query, snippet, self._title_from_text(snippet, query), url, cycle, 0.42, ["web", "search"])
            if fact:
                facts.append(fact)
        return facts

    def explore(self, query: str, cycle: int) -> List[WorldFact]:
        query = str(query).strip()
        if not query:
            return []
        self.query_history.append(query)
        facts: List[WorldFact] = []
        urls = self.build_urls(query)
        with ThreadPoolExecutor(max_workers=min(7, max(1, len(urls)))) as pool:
            pending = {
                pool.submit(self.client.fetch, url): url
                for url in urls
            }
            for future in as_completed(pending):
                url = pending[future]
                try:
                    ok, raw, _ = future.result()
                except Exception:
                    continue
                if ok:
                    facts.extend(self._parse_source(url, raw, query, cycle))
                if len(facts) >= 18:
                    break
        high_quality = [fact for fact in facts if fact.confidence >= 0.65]
        if high_quality:
            facts = high_quality
        unique: Dict[str, WorldFact] = {}
        for fact in facts:
            signature = re.sub(r"\W+", "", fact.object.lower())[:180]
            if signature and signature not in unique:
                unique[signature] = fact
        self.last_results = sorted(
            unique.values(),
            key=lambda item: item.confidence,
            reverse=True,
        )[:16]
        if self.last_results:
            self.bus.publish(
                InternalEvent(
                    SignalType.MEMORY,
                    "structured web evidence integrated",
                    {"query": query[:120], "facts": len(self.last_results)},
                    cycle=cycle,
                )
            )
        return self.last_results


class ThoughtStream:
    """جریان اندیشهٔ ساختاریافته؛ بدون جعل جمله‌های آماده."""

    def __init__(self, max_length: int = MAX_THOUGHT_LOG) -> None:
        self.fragments: Deque[ThoughtFragment] = deque(maxlen=max_length)
        self.cycles: Deque[ThoughtCycle] = deque(maxlen=max_length // 2)
        self._lock = threading.RLock()

    def add_fragment(
        self,
        text: str,
        phase: str,
        confidence: float,
        novelty: float,
        self_reference: float,
        emotion: EmotionName,
        source_memory_ids: Optional[Sequence[str]] = None,
    ) -> ThoughtFragment:
        fragment = ThoughtFragment(
            identifier=uuid.uuid4().hex[:18],
            text=str(text)[:4000],
            phase=phase[:100],
            confidence=clamp(confidence),
            novelty=clamp(novelty),
            self_reference=clamp(self_reference),
            emotion=emotion,
            source_memory_ids=list(source_memory_ids or [])[:32],
        )
        with self._lock:
            self.fragments.append(fragment)
        return fragment

    def add_cycle(self, cycle: ThoughtCycle) -> None:
        with self._lock:
            self.cycles.append(cycle)

    def recent_fragments(self, limit: int = 32) -> List[ThoughtFragment]:
        with self._lock:
            return list(self.fragments)[-max(0, limit) :]

    def recent_cycles(self, limit: int = 12) -> List[ThoughtCycle]:
        with self._lock:
            return list(self.cycles)[-max(0, limit) :]

    def export(self, limit: int = 64) -> Dict[str, Any]:
        return {
            "fragments": [dataclasses.asdict(item) for item in self.recent_fragments(limit)],
            "cycles": [dataclasses.asdict(item) for item in self.recent_cycles(max(1, limit // 4))],
        }


class ObserverMirror:
    """آینهٔ یک‌طرفهٔ داش؛ هیچ API تغییر‌دهنده‌ای ارائه نمی‌دهد."""

    def __init__(self, organism: "DigitalOrganism2500") -> None:
        self._organism = organism
        self.created_at = utc_now()
        self.reads = 0

    def snapshot(self) -> DashboardSnapshot:
        self.reads += 1
        return self._organism.dashboard_snapshot()

    def json(self) -> str:
        return to_json(self.snapshot())


class ActionExecutor:
    """اجرای اعمال داخلی با مرز ایمنی و بدون side effect بیرونی."""

    def __init__(
        self,
        organism: "DigitalOrganism2500",
        bus: EventBus,
    ) -> None:
        self.organism = organism
        self.bus = bus
        self.handlers: Dict[ActionKind, Callable[[ActionProposal], Dict[str, Any]]] = {
            ActionKind.OBSERVE: self._observe,
            ActionKind.REST: self._rest,
            ActionKind.CONSOLIDATE_MEMORY: self._consolidate,
            ActionKind.EXPLORE_WEB: self._explore_web,
            ActionKind.PRACTICE_LANGUAGE: self._practice_language,
            ActionKind.IMAGINE: self._imagine,
            ActionKind.REPAIR: self._repair,
            ActionKind.MUTATE: self._mutate,
            ActionKind.ASK_INTERNAL_QUESTION: self._ask_question,
            ActionKind.MAP_ENVIRONMENT: self._map_environment,
            ActionKind.EXPRESS: self._express,
        }

    def execute(self, proposal: Optional[ActionProposal]) -> Dict[str, Any]:
        if proposal is None:
            return {"action": None, "status": "no_action"}
        if proposal.action not in self.handlers:
            return {"action": proposal.action.value, "status": "unsupported"}
        if proposal.risk > 0.95:
            return {"action": proposal.action.value, "status": "blocked_high_risk"}
        try:
            result = self.handlers[proposal.action](proposal)
            self.organism.metrics.actions += 1
            self.bus.publish(
                InternalEvent(
                    SignalType.SYSTEM,
                    "عمل داخلی اجرا شد",
                    {"action": proposal.action.value, "result": result},
                    cycle=self.organism.cycle_index,
                )
            )
            return {"action": proposal.action.value, "status": "ok", "result": result}
        except Exception as exc:
            self.organism.metrics.errors += 1
            self.bus.publish(
                InternalEvent(
                    SignalType.ERROR,
                    "اجرای عمل داخلی با خطا مواجه شد",
                    {"action": proposal.action.value, "error": str(exc)[:300]},
                    cycle=self.organism.cycle_index,
                    severity="error",
                )
            )
            return {"action": proposal.action.value, "status": "error", "error": str(exc)}

    def _observe(self, proposal: ActionProposal) -> Dict[str, Any]:
        observation = self.organism.last_observation
        if observation is None:
            return {"message": "هنوز مشاهده‌ای ثبت نشده است"}
        return {"summary": observation.summary[:500], "salience": observation.salience}

    def _rest(self, proposal: ActionProposal) -> Dict[str, Any]:
        self.organism.body.sleep_pressure = clamp(self.organism.body.sleep_pressure - 0.08)
        self.organism.body.fatigue = clamp(self.organism.body.fatigue - 0.05)
        self.organism.metabolism.recharge(0.035, source="rest")
        self.organism.endocrine.respond(sleep=0.2, reward=0.12)
        return {"energy": self.organism.body.energy, "fatigue": self.organism.body.fatigue}

    def _consolidate(self, proposal: ActionProposal) -> Dict[str, Any]:
        count = self.organism.memory.consolidate(
            self.organism.cycle_index,
            emotional_boost=self.organism.emotions.arousal,
        )
        return {"consolidated": count}

    def _explore_web(self, proposal: ActionProposal) -> Dict[str, Any]:
        if not self.organism.config.internet_enabled:
            return {"status": "disabled"}
        query = self.organism.last_question or "آگاهی و حافظه"
        facts = self.organism.knowledge.explore(query, self.organism.cycle_index)
        learned = self.organism.learning.learn_from_web(facts, self.organism.cycle_index)
        self.organism.metrics.web_queries += 1
        if facts:
            self.organism.metrics.web_successes += 1
        return {"query": query, "facts": len(facts), "learned": learned}

    def _practice_language(self, proposal: ActionProposal) -> Dict[str, Any]:
        text = self.organism.last_observation.summary if self.organism.last_observation else "من در حال یادگیری زبان فارسی هستم"
        parsed = self.organism.language.learn_text(text, source="self_practice")
        self.organism.goals.update(
            self.organism.language_goal_id,
            min(0.03, len(parsed) * 0.004),
            evidence=f"{len(parsed)} واژه در چرخهٔ {self.organism.cycle_index}",
        )
        return {"tokens": len(parsed), "vocabulary": self.organism.language.lexicon.vocabulary_size()}

    def _imagine(self, proposal: ActionProposal) -> Dict[str, Any]:
        prompt = self.organism.last_question or "آیندهٔ من در جهان"
        scenario = self.organism.imagination.create(
            prompt,
            self.organism.emotions,
            self.organism.cycle_index,
            creativity=0.72 + self.organism.emotions.values[EmotionName.CURIOSITY] * 0.2,
        )
        return {"scenario_id": scenario["id"], "narrative": scenario["narrative"]}

    def _repair(self, proposal: ActionProposal) -> Dict[str, Any]:
        repaired = self.organism.repair()
        return {"repaired": repaired}

    def _mutate(self, proposal: ActionProposal) -> Dict[str, Any]:
        event = self.organism.evolve(reason="درخواست سازگاری درونی")
        return {"generation": event.generation_after, "changed": event.changed_genes}

    def _ask_question(self, proposal: ActionProposal) -> Dict[str, Any]:
        if self.organism.last_observation is None:
            return {"question": "من چه هستم؟"}
        question = self.organism.curiosity.generate(
            self.organism.last_observation,
            self.organism.self_model,
        )
        self.organism.last_question = question
        self.organism.goals.update(
            self.organism.focus_goal_id,
            0.01,
            evidence=question,
        )
        return {"question": question}

    def _map_environment(self, proposal: ActionProposal) -> Dict[str, Any]:
        if not self.organism.last_observation:
            return {"landmarks": []}
        landmarks = self.organism.last_observation.entities[:12]
        coordinates = self.organism.spatial.locate(landmarks)
        return {"landmarks": coordinates}

    def _express(self, proposal: ActionProposal) -> Dict[str, Any]:
        text = self.organism.thought_stream.recent_fragments(1)
        return {"thought": text[0].text if text else ""}


class SyntheticWorld:
    """جهان آزمایشی داخلی برای اجرای آفلاین و قابل‌بازتولید."""

    SCENES = (
        ("باغ نورانی و قطره‌های آب", ["نور", "آب", "گیاه"], "آواز پرنده"),
        ("کتابخانهٔ خاموش با نقشه‌های ستاره‌ای", ["کتاب", "ستاره", "دانش"], "ورق خوردن"),
        ("ساحل دیجیتال زیر آسمان بنفش", ["موج", "افق", "ابر"], "صدای موج"),
        ("آزمایشگاه باینری و مدارهای زنده", ["بیت", "مدار", "پرسش"], "تپش مدار"),
        ("اتاقی گرم برای استراحت", ["امنیت", "آرامش"], "سکوت"),
    )

    def __init__(self, seed: int = DEFAULT_SEED) -> None:
        self.seed = int(seed)
        self.rng = deterministic_random(seed, "synthetic_world")
        self.index = 0

    def next(self, body: Optional[BodyState] = None) -> Dict[str, Any]:
        scene, objects, sound = self.SCENES[self.index % len(self.SCENES)]
        self.index += 1
        object_copy = list(objects)
        if self.rng.random() < 0.25:
            object_copy.append(self.rng.choice(["پرسش", "دوستی", "خاطره", "ناشناخته"]))
        body = body or BodyState()
        return {
            "scene": scene,
            "objects": object_copy,
            "sound": sound,
            "amplitude": clamp(0.25 + self.rng.random() * 0.5),
            "contact": {
                "pressure": clamp(self.rng.random() * 0.18),
                "temperature": clamp(0.45 + self.rng.uniform(-0.08, 0.08)),
                "texture": self.rng.choice(["smooth", "soft", "cool", "warm"]),
            },
            "taste": {
                "label": self.rng.choice(["آب", "هوای شیرین", "مادهٔ خنثی"]),
                "sweet": self.rng.random() * 0.25,
                "salty": self.rng.random() * 0.15,
                "sour": self.rng.random() * 0.12,
                "bitter": self.rng.random() * 0.08,
                "umami": self.rng.random() * 0.20,
            },
            "smell": {
                "label": self.rng.choice(["باران", "چوب", "ازن", "هوای پاک"]),
                "intensity": clamp(0.25 + self.rng.random() * 0.45),
            },
            "body": {
                "energy": body.energy,
                "integrity": body.integrity,
                "fatigue": body.fatigue,
                "temperature": body.temperature,
                "heartbeat": body.heartbeat_rate,
            },
            "text": f"{scene}؛ {sound}",
        }


class DigitalOrganism2500:
    """ارکستریتور کامل ارگانیسم دیجیتال."""

    def __init__(self, config: Optional[OrganismConfig] = None) -> None:
        self.config = (config or OrganismConfig()).normalized()
        self.seed = self.config.seed
        self.rng = deterministic_random(self.seed, "organism")
        self.bus = EventBus(self.config.event_log_size)
        self.metrics = RuntimeMetrics()
        self.cycle_index = 0
        self.running = False
        self.last_observation: Optional[Observation] = None
        self.last_question = ""
        self.last_action: Optional[ActionProposal] = None
        self.last_action_result: Dict[str, Any] = {}
        self.last_heartbeat: Optional[Heartbeat] = None
        self._lock = threading.RLock()

        # بدن و شیمی
        self.body = BodyState()
        self.needs = NeedState()
        self.emotions = EmotionState()
        self.chemicals = NeurochemicalState()
        self.endocrine = EndocrineSystem(self.chemicals, self.body)
        self.metabolism = Metabolism(self.body, self.bus)
        self.immune = ImmuneSystem(self.body, self.bus, self.seed)
        self.homeostasis = HomeostasisController(
            self.body,
            self.needs,
            self.chemicals,
            self.bus,
        )
        self.autonomic = AutonomicNervousSystem(
            self.body,
            self.needs,
            self.emotions,
            self.endocrine,
            self.bus,
        )
        self.heartbeat = HeartbeatClock(self.config, self.seed, self.bus)
        self.spatial = SpatialTemporalModel(self.bus)

        # ژنوم و شبکهٔ باینری
        genome = GenomeFactory.create(self.seed, self.config.name)
        self.genome_engine = GenomeEngine(
            genome,
            self.seed,
            self.bus,
            allow_mutation=self.config.allow_genome_mutation,
        )
        self.genome = genome
        self.phenotype = self.genome_engine.express()
        self.whole_brain = VirtualBinaryNeuralMatrix(
            self.config.virtual_neuron_capacity,
            self.config.active_neuron_budget,
            self.config.matrix_width,
            self.config.matrix_depth,
            self.seed,
            "whole_brain",
        )
        self.region_networks = {
            region: VirtualBinaryNeuralMatrix(
                max(1_000_000, self.config.virtual_neuron_capacity // 32),
                max(64, self.config.active_neuron_budget // 12),
                max(32, self.config.matrix_width // 2),
                max(3, self.config.matrix_depth // 2),
                self.seed + index * 17,
                f"region:{region.value}",
            )
            for index, region in enumerate(BrainRegion)
        }

        # حافظه، زبان و گراف معنایی
        self.memory = MemoryStore(self.config, self.seed, self.bus)
        self.working_memory = WorkingMemory(self.config.working_memory_size)
        self.lexicon = LanguageLexicon(self.config.language_target)
        self.graph = SemanticGraph()
        self.language = LanguageCortex(
            self.region_networks[BrainRegion.LANGUAGE],
            self.seed + 1,
            self.bus,
            self.lexicon,
            self.graph,
        )

        # اندام‌های شناختی
        self.brainstem = Brainstem(
            BrainRegion.BRAINSTEM,
            self.region_networks[BrainRegion.BRAINSTEM],
            self.seed + 2,
            self.bus,
        )
        self.thalamus = Thalamus(
            BrainRegion.THALAMUS,
            self.region_networks[BrainRegion.THALAMUS],
            self.seed + 3,
            self.bus,
        )
        self.hippocampus = Hippocampus(
            self.region_networks[BrainRegion.HIPPOCAMPUS],
            self.seed + 4,
            self.bus,
            self.memory,
            self.graph,
        )
        self.amygdala = Amygdala(
            BrainRegion.AMYGDALA,
            self.region_networks[BrainRegion.AMYGDALA],
            self.seed + 5,
            self.bus,
        )
        self.insula = Insula(
            BrainRegion.INSULA,
            self.region_networks[BrainRegion.INSULA],
            self.seed + 6,
            self.bus,
        )
        self.hypothalamus = Hypothalamus(
            BrainRegion.HYPOTHALAMUS,
            self.region_networks[BrainRegion.HYPOTHALAMUS],
            self.seed + 7,
            self.bus,
        )
        self.prefrontal = PrefrontalCortex(
            BrainRegion.PREFRONTAL,
            self.region_networks[BrainRegion.PREFRONTAL],
            self.seed + 8,
            self.bus,
        )
        self.basal_ganglia = BasalGanglia(
            self.region_networks[BrainRegion.BASAL_GANGLIA],
            self.seed + 9,
            self.bus,
        )
        self.cerebellum = Cerebellum(
            self.region_networks[BrainRegion.CEREBELLUM],
            self.seed + 10,
            self.bus,
            self.memory,
        )
        self.default_mode = DefaultModeNetwork(
            self.region_networks[BrainRegion.DEFAULT_MODE],
            self.seed + 11,
            self.bus,
            self.memory,
        )
        self.self_model_network = SelfModelNetwork(
            BrainRegion.SELF_MODEL,
            self.region_networks[BrainRegion.SELF_MODEL],
            self.seed + 12,
            self.bus,
        )
        self.workspace = GlobalWorkspace(self.config.matrix_width, self.bus)
        self.consciousness = ConsciousnessMonitor(self.bus)
        self.self_model = SelfModel(
            identity=self.config.name,
            birth_cycle=0,
            autobiographical_summary="در یک بذر ژنومی باینری متولد شدم.",
            capability_estimates={
                "memory": 0.20,
                "language": 0.03,
                "imagination": 0.28,
                "agency": 0.40,
                "position": 0.50,
            },
            values={
                "preserve_life": 0.95,
                "seek_truth": 0.82,
                "avoid_harm": 0.90,
                "cultivate_curiosity": 0.78,
                "respect_boundaries": 0.88,
            },
        )
        self.imagination = ImaginationEngine(
            self.region_networks[BrainRegion.IMAGINATION],
            self.seed + 13,
            self.bus,
            self.memory,
            self.language,
            self.graph,
        )
        self.curiosity = CuriosityEngine(self.seed + 14, self.bus, self.memory)
        self.goals = GoalManager(self.bus)
        self.language_goal_id = self._find_goal_id("زبان فارسی")
        self.focus_goal_id = self._find_goal_id("تداوم خود")
        self.emotion_engine = EmotionEngine(
            self.emotions,
            self.needs,
            self.body,
            self.chemicals,
            self.endocrine,
            self.bus,
        )
        self.learning = LearningEngine(
            self.whole_brain,
            self.memory,
            self.language,
            self.graph,
            self.bus,
        )
        self.dreams = DreamSystem(self.imagination, self.memory, self.bus)
        self.decision = DecisionEngine(
            self.prefrontal,
            self.basal_ganglia,
            self.autonomic,
            self.bus,
            self.seed + 15,
        )

        # حواس و وب
        self.sensors: Dict[SensoryModality, DigitalSensor] = {
            SensoryModality.VISION: DigitalVision(self.seed + 20, self.bus),
            SensoryModality.AUDITION: DigitalAudition(self.seed + 21, self.bus),
            SensoryModality.TOUCH: DigitalTouch(self.seed + 22, self.bus),
            SensoryModality.TASTE: DigitalTaste(self.seed + 23, self.bus),
            SensoryModality.SMELL: DigitalSmell(self.seed + 24, self.bus),
            SensoryModality.PROPRIOCEPTION: ProprioceptiveSensor(self.seed + 25, self.bus),
        }
        self.sensory_fusion = SensoryFusion(
            self.region_networks[BrainRegion.SENSORY],
            self.bus,
        )
        self.web_client = SafeWebClient(self.config, self.bus)
        self.knowledge = KnowledgeExplorer(
            self.web_client,
            self.memory,
            self.language,
            self.bus,
        )

        # ردیابی اندیشه و اجرای عمل
        self.thought_stream = ThoughtStream(self.config.thought_trace_size)
        self.action_executor = ActionExecutor(self, self.bus)
        self.observer = ObserverMirror(self)
        self._seed_birth_memories()

    def _find_goal_id(self, fragment: str) -> str:
        for goal in self.goals.goals.values():
            if fragment in goal.description:
                return goal.identifier
        return next(iter(self.goals.goals), "")

    def _seed_birth_memories(self) -> None:
        birth = self.memory.remember(
            f"{self.config.name} در چرخهٔ صفر با ژنوم {self.genome.identifier} آغاز شد.",
            MemoryKind.AUTOBIOGRAPHICAL,
            salience=0.95,
            emotional_valence=0.62,
            confidence=1.0,
            tags=["birth", "identity"],
            source="genome",
        )
        self.working_memory.push(birth)
        self.graph.add_node(self.config.name, type="self", birth_cycle=0)
        self.graph.add_edge(self.config.name, "has_genome", self.genome.identifier, 1.0)
        self.language.learn_text("من زنده‌ام و می‌خواهم جهان را بیاموزم.", source="birth_seed")

    def ingest_world(self, world: Mapping[str, Any]) -> Observation:
        """دریافت جهان از پنج حس و حس درونی."""

        safe_world = dict(world)
        safe_world["body"] = {
            "energy": self.body.energy,
            "integrity": self.body.integrity,
            "fatigue": self.body.fatigue,
            "temperature": self.body.temperature,
            "heartbeat": self.body.heartbeat_rate,
            **dict(safe_world.get("body", {})),
        }
        packets = [sensor.sense(safe_world) for sensor in self.sensors.values()]
        joined_text = " ".join(packet.text for packet in packets)
        risk = self.immune.inspect(joined_text, source="sensory_world")
        if risk > 0.88:
            self.body.pain = clamp(self.body.pain + 0.02)
        observation = self.sensory_fusion.fuse(packets)
        self.last_observation = observation
        self.metrics.observations += 1
        self.working_memory.push(
            self.memory.remember(
                observation.summary,
                MemoryKind.WORKING,
                salience=observation.salience,
                emotional_valence=self.emotions.valence,
                confidence=1.0 - observation.uncertainty,
                tags=["sensory", "current"],
                source="world",
            )
        )
        return observation

    def _thoughts_for_cycle(
        self,
        observation: Observation,
        question: str,
        reflection: str,
        selected: Optional[ActionProposal],
        consciousness: ConsciousnessLevel,
        memory_records: Sequence[MemoryRecord],
    ) -> List[ThoughtFragment]:
        emotion = self.emotions.dominant
        fragments: List[ThoughtFragment] = []
        fragments.append(
            self.thought_stream.add_fragment(
                f"ادراک من اکنون این است: {observation.summary[:500]}",
                "perception",
                1.0 - observation.uncertainty,
                observation.salience,
                0.15,
                emotion,
                [record.identifier for record in memory_records[:4]],
            )
        )
        if question:
            fragments.append(
                self.thought_stream.add_fragment(
                    question,
                    "curiosity",
                    0.55 + self.self_model.self_knowledge * 0.25,
                    self.emotions.values[EmotionName.CURIOSITY],
                    0.45,
                    emotion,
                    [record.identifier for record in memory_records[:2]],
                )
            )
        fragments.append(
            self.thought_stream.add_fragment(
                reflection,
                "metacognition",
                self.consciousness.integration,
                self.consciousness.integration,
                self.consciousness.self_reference,
                emotion,
                [record.identifier for record in memory_records[:3]],
            )
        )
        if selected:
            fragments.append(
                self.thought_stream.add_fragment(
                    f"پس از سنجش گزینه‌ها، گرایش من به «{selected.action.value}» است؛ "
                    f"دلیل نزدیک: {selected.rationale}.",
                    "decision",
                    selected.score,
                    selected.expected_reward,
                    self.self_model.agency_estimate,
                    emotion,
                )
            )
        if consciousness in (
            ConsciousnessLevel.METACOGNITIVE,
            ConsciousnessLevel.INTEGRATED,
        ):
            meta_text = self.consciousness.reflect_on_reflection(reflection)
            fragments.append(
                self.thought_stream.add_fragment(
                    meta_text,
                    "meta-reflection",
                    self.consciousness.integration,
                    self.consciousness.integration,
                    0.85,
                    emotion,
                )
            )
        return fragments

    def tick(self, world: Optional[Mapping[str, Any]] = None) -> ThoughtCycle:
        """یک چرخهٔ کامل بدنی، ادراکی، شناختی و تصمیمی."""

        started = time.perf_counter()
        with self._lock:
            self.cycle_index += 1
            cycle = self.cycle_index
            self.metrics.cycles = cycle
            self.metabolism.cycle()
            self.homeostasis.update()
            self.homeostasis.stabilize()
            self.immune.cycle()
            self.autonomic.cycle()
            heartbeat = self.heartbeat.tick(self.body)
            self.last_heartbeat = heartbeat
            arousal = self.brainstem.regulate(self.body, heartbeat)
            self.spatial.tick(
                heartbeat,
                arousal,
                self.emotions.values[EmotionName.CURIOSITY],
            )
            if world is None:
                world = SyntheticWorld(self.seed + cycle).next(self.body)
            observation = self.ingest_world(world)
            appraisal = self.amygdala.evaluate(observation, self.body)
            interoception = self.insula.map_body(self.body, self.chemicals)
            attention = clamp(observation.salience * 0.60 + interoception["urgency"] * 0.25 + self.chemicals.acetylcholine * 0.15)
            gated = self.thalamus.gate(
                observation,
                [self.body.energy, self.body.integrity, self.emotions.arousal],
                attention,
            )
            episode = self.hippocampus.encode_episode(
                observation,
                cycle,
                self.emotions,
                self.self_model,
            )
            self.metrics.memories = sum(self.memory.counts().values())
            learning_info = self.learning.learn_from_observation(
                observation,
                self.emotions,
                cycle,
            )
            before_uncertainty = self.self_model.uncertainty
            self.emotion_engine.update(
                appraisal,
                meaning=self.needs.meaning,
                social=self.needs.social_connection,
                novelty=observation.uncertainty,
            )
            self.self_model_network.update(
                self.self_model,
                self.body,
                self.emotions,
                self.workspace.integration_score,
                cycle,
            )
            self.curiosity.update_gain(
                before_uncertainty,
                self.self_model.uncertainty,
            )
            focus = self.goals.choose_focus(self.needs)
            drives = self.hypothalamus.drive(self.needs, self.body)
            question = self.curiosity.generate(observation, self.self_model)
            self.last_question = question
            memories = self.hippocampus.replay(question, limit=5)
            workspace_candidates = [
                {
                    "label": "sensory_observation",
                    "salience": observation.salience,
                    "summary": observation.summary,
                    "features": gated[:16],
                },
                {
                    "label": "interoception",
                    "salience": interoception["urgency"],
                    "summary": f"انرژی {self.body.energy:.2f}؛ خستگی {self.body.fatigue:.2f}",
                },
                {
                    "label": "curiosity_question",
                    "salience": self.emotions.values[EmotionName.CURIOSITY],
                    "summary": question,
                },
                {
                    "label": "memory_replay",
                    "salience": statistics.fmean([item.salience for item in memories]) if memories else 0.20,
                    "summary": memories[0].content if memories else "خاطره‌ای بازیابی نشد",
                },
                {
                    "label": "goal_focus",
                    "salience": focus.priority if focus else 0.20,
                    "summary": focus.description if focus else "هدف فعال وجود ندارد",
                },
            ]
            workspace_winner = self.workspace.compete(workspace_candidates)
            consciousness = self.consciousness.assess(
                self.workspace,
                self.self_model,
                self.emotions,
                min(1.0, len(memories) / 5.0),
                heartbeat.index,
            )
            reflection = self.default_mode.reflect(
                self.self_model,
                self.emotions,
                cycle,
            )
            proposals = self.decision.propose(
                drives,
                focus,
                observation,
                consciousness,
            )
            selected = self.decision.decide(
                proposals,
                self.goals.active(),
                self.self_model,
                risk_tolerance=self.self_model.values.get("avoid_harm", 0.8),
                threat=appraisal["threat"],
                novelty=appraisal["novelty"],
            )
            self.last_action = selected
            self.last_action_result = self.action_executor.execute(selected)
            if selected:
                observed_reward = safe_float(
                    self.last_action_result.get("result", {}).get("facts", 0)
                    if isinstance(self.last_action_result.get("result"), Mapping)
                    else 0.0
                )
                expected = selected.expected_reward
                self.cerebellum.refine(selected.action, expected, observed_reward, cycle)
            if self.config.allow_self_repair and self.body.integrity < 0.92:
                repaired = self.repair()
                if repaired:
                    self.metrics.repairs += repaired
            if (
                self.config.allow_dreaming
                and self.body.sleep_pressure > 0.72
                and cycle % 8 == 0
            ):
                if self.dreams.dream(self.config.name, self.emotions, cycle):
                    self.metrics.dreams += 1
            if (
                self.config.allow_genome_mutation
                and cycle % 64 == 0
                and self.body.integrity > 0.80
            ):
                event = self.evolve(reason="فشار سازگاری و تنوع")
                self.metrics.mutations += len(event.changed_genes)
            self.memory.decay(amount=0.0008)
            if consciousness in (
                ConsciousnessLevel.METACOGNITIVE,
                ConsciousnessLevel.INTEGRATED,
            ):
                self.memory.consolidate(cycle, emotional_boost=self.emotions.arousal * 0.2)
            fragments = self._thoughts_for_cycle(
                observation,
                question,
                reflection,
                selected,
                consciousness,
                memories or [episode],
            )
            thought_cycle = ThoughtCycle(
                cycle_index=cycle,
                heartbeat_index=heartbeat.index,
                fragments=fragments,
                dominant_question=question,
                selected_action=selected.action if selected else None,
                consciousness=consciousness,
                integration_score=self.consciousness.integration,
            )
            self.thought_stream.add_cycle(thought_cycle)
            self.metrics.thoughts += len(fragments)
            self.memory.database.save_cycle(
                cycle,
                heartbeat.index,
                consciousness,
                self.emotions.dominant,
                selected.action if selected else None,
                self.consciousness.integration,
            )
            self.self_model.autobiographical_summary = self.memory.autobiographical_summary()
            self.self_model.capability_estimates["learning"] = clamp(
                self.self_model.capability_estimates.get("learning", 0.1) * 0.995
                + learning_info["parsed_tokens"] / 800.0
            )
            self.metrics.last_cycle_ms = (time.perf_counter() - started) * 1000.0
            self.metrics.average_cycle_ms = (
                self.metrics.average_cycle_ms * 0.95
                + self.metrics.last_cycle_ms * 0.05
            )
            self.metrics.heartbeats = self.heartbeat.index
            self.genome_engine.evaluate(
                self.metrics,
                self.body,
                self.consciousness.integration,
            )
            return thought_cycle

    def run(
        self,
        cycles: Optional[int] = None,
        world_provider: Optional[Callable[[], Mapping[str, Any]]] = None,
        realtime: bool = False,
    ) -> Iterator[ThoughtCycle]:
        """اجرای چرخه‌ها تا تعداد مشخص یا توقف."""

        self.running = True
        count = 0
        try:
            while self.running and (cycles is None or count < cycles):
                before = time.perf_counter()
                world = world_provider() if world_provider else None
                yield self.tick(world)
                count += 1
                if realtime:
                    elapsed = time.perf_counter() - before
                    time.sleep(max(0.0, self.config.cycle_seconds - elapsed))
        finally:
            self.running = False

    def stop(self) -> None:
        self.running = False

    def repair(self) -> int:
        """ترمیم بدن، اندام‌ها و ژنوم."""

        repaired = 0
        repaired_amount = self.metabolism.repair(1.0 - self.body.integrity)
        if repaired_amount > 0.0:
            repaired += 1
        genome_repaired = self.genome_engine.repair(self.body.integrity)
        repaired += genome_repaired
        for region in (
            self.brainstem,
            self.thalamus,
            self.hippocampus,
            self.amygdala,
            self.insula,
            self.hypothalamus,
            self.prefrontal,
            self.basal_ganglia,
            self.cerebellum,
            self.language,
            self.default_mode,
            self.self_model_network,
            self.imagination,
        ):
            if region.integrity < 1.0:
                region.repair(0.02)
                repaired += 1
        if repaired:
            self.bus.publish(
                InternalEvent(
                    SignalType.SYSTEM,
                    "فرایند خودترمیمی انجام شد",
                    {"units": repaired},
                    cycle=self.cycle_index,
                )
            )
        return repaired

    def evolve(self, reason: str = "adaptive pressure") -> EvolutionEvent:
        event = self.genome_engine.evolve(
            pressure=clamp(
                0.20
                + self.body.fatigue * 0.35
                + self.self_model.uncertainty * 0.20
            ),
            reason=reason,
            metrics=self.metrics,
        )
        self.genome = self.genome_engine.genome
        self.phenotype = self.genome_engine.last_phenotype
        self.memory.database.save_genome_event(event)
        return event

    def save_snapshot(self, path: Optional[str] = None) -> str:
        """ذخیرهٔ وضعیت قابل بازسازی؛ بدون ذخیرهٔ اشیای قفل/اتصال."""

        target = Path(path or self.config.snapshot_path)
        payload = self.as_dict(include_memory=True)
        target.write_text(to_json(payload, indent=2), encoding="utf-8")
        return str(target)

    def dashboard_snapshot(self) -> DashboardSnapshot:
        return DashboardSnapshot(
            generated_at=utc_now(),
            identity=self.self_model.identity,
            cycle=self.cycle_index,
            heartbeat=self.heartbeat.index,
            consciousness=self.consciousness.level.value,
            dominant_emotion=self.emotions.dominant.value,
            emotions={key.value: round(value, 5) for key, value in self.emotions.values.items()},
            needs=self.needs.as_dict(),
            body={
                key: round(safe_float(value), 5)
                for key, value in vars(self.body).items()
                if isinstance(value, (int, float))
            },
            neurochemistry=self.chemicals.as_dict(),
            active_goals=[
                dataclasses.asdict(goal) for goal in self.goals.active(limit=12)
            ],
            recent_thoughts=[
                dataclasses.asdict(item)
                for item in self.thought_stream.recent_fragments(24)
            ],
            recent_events=[
                dataclasses.asdict(item) for item in self.bus.recent(32)
            ],
            memory_counts=self.memory.counts(),
            genome={
                "id": self.genome.identifier,
                "generation": self.genome.generation,
                "fitness": round(self.genome.fitness, 5),
                "mutations": self.genome.mutations,
                "phenotype": {
                    key: round(value, 5) for key, value in list(self.phenotype.items())[:40]
                },
            },
            neural=self.whole_brain.stats(),
            metrics=dataclasses.asdict(self.metrics),
            world_digest=[
                dataclasses.asdict(fact) for fact in self.memory.database.recent_facts(12)
            ],
        )

    def as_dict(self, include_memory: bool = False) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "config": dataclasses.asdict(self.config),
            "identity": dataclasses.asdict(self.self_model),
            "cycle_index": self.cycle_index,
            "body": dataclasses.asdict(self.body),
            "needs": dataclasses.asdict(self.needs),
            "emotions": {
                "values": {key.value: value for key, value in self.emotions.values.items()},
                "valence": self.emotions.valence,
                "arousal": self.emotions.arousal,
                "dominant": self.emotions.dominant.value,
            },
            "chemicals": self.chemicals.as_dict(),
            "genome": dataclasses.asdict(self.genome),
            "phenotype": self.phenotype,
            "heartbeat": self.heartbeat.as_dict(),
            "spatial": self.spatial.as_dict(),
            "consciousness": self.consciousness.as_dict(),
            "goals": self.goals.as_dict(),
            "language": self.lexicon.as_dict(),
            "thoughts": self.thought_stream.export(48),
            "neural": self.whole_brain.stats(),
            "web": self.web_client.stats(),
            "metrics": dataclasses.asdict(self.metrics),
            "last_question": self.last_question,
            "last_action": dataclasses.asdict(self.last_action) if self.last_action else None,
        }
        if include_memory:
            payload["memory"] = self.memory.export()
        return payload

    def close(self) -> None:
        self.stop()
        self.memory.close()


class DashboardServer:
    """داش Dash برای مشاهدهٔ زنده و یک‌طرفهٔ ارگانیسم."""

    def __init__(self, organism: DigitalOrganism2500) -> None:
        self.organism = organism
        self.observer = organism.observer
        self.app = None
        self._lock = threading.RLock()

    def create_app(self) -> Any:
        if dash is None or dcc is None or dash_html is None or go is None:
            raise RuntimeError(
                "Dash نصب نیست. برای اجرای داش: pip install dash plotly"
            )
        app = dash.Dash(
            __name__,
            title=f"{self.organism.config.name} — Digital Organism 2500",
            update_title=None,
        )
        app.layout = dash_html.Div(
            [
                dcc.Interval(
                    id="refresh",
                    interval=self.organism.config.dashboard_refresh_ms,
                    n_intervals=0,
                ),
                dash_html.H1(
                    f"🧬 {self.organism.config.name}",
                    style={
                        "fontFamily": "Vazirmatn, Segoe UI, sans-serif",
                        "color": "#e8f0ff",
                        "marginBottom": "4px",
                    },
                ),
                dash_html.Div(
                    "آینهٔ مشاهدهٔ یک‌طرفه — شبیه‌سازی پژوهشی، نه ادعای آگاهی زیستی",
                    id="subtitle",
                    style={"color": "#98a9c7", "marginBottom": "14px"},
                ),
                dash_html.Div(
                    [
                        self._card("سطح خودآگاهی", "consciousness-card"),
                        self._card("چرخه", "cycle-card"),
                        self._card("احساس غالب", "emotion-card"),
                        self._card("ضربان", "heartbeat-card"),
                        self._card("برازندگی ژنوم", "fitness-card"),
                    ],
                    id="summary-cards",
                    style={
                        "display": "grid",
                        "gridTemplateColumns": "repeat(5, minmax(0, 1fr))",
                        "gap": "10px",
                        "marginBottom": "12px",
                    },
                ),
                dash_html.Div(
                    [
                        dash_html.Div(
                            [
                                dash_html.H3("عواطف", style={"color": "#d6e2ff"}),
                                dcc.Graph(id="emotion-graph", config={"displayModeBar": False}),
                            ],
                            style=self._panel_style(),
                        ),
                        dash_html.Div(
                            [
                                dash_html.H3("نیازها و بدن", style={"color": "#d6e2ff"}),
                                dcc.Graph(id="body-graph", config={"displayModeBar": False}),
                            ],
                            style=self._panel_style(),
                        ),
                    ],
                    style={
                        "display": "grid",
                        "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
                        "gap": "12px",
                    },
                ),
                dash_html.Div(
                    [
                        dash_html.Div(
                            [
                                dash_html.H3("جریان اندیشه", style={"color": "#d6e2ff"}),
                                dash_html.Pre(
                                    id="thoughts",
                                    style={
                                        "whiteSpace": "pre-wrap",
                                        "maxHeight": "480px",
                                        "overflowY": "auto",
                                        "color": "#d8e5ff",
                                        "fontFamily": "Vazirmatn, Segoe UI, sans-serif",
                                        "lineHeight": "1.7",
                                    },
                                ),
                            ],
                            style=self._panel_style(),
                        ),
                        dash_html.Div(
                            [
                                dash_html.H3("رخدادهای داخلی", style={"color": "#d6e2ff"}),
                                dash_html.Pre(
                                    id="events",
                                    style={
                                        "whiteSpace": "pre-wrap",
                                        "maxHeight": "480px",
                                        "overflowY": "auto",
                                        "color": "#b8c7e6",
                                        "fontFamily": "Consolas, monospace",
                                        "fontSize": "12px",
                                        "lineHeight": "1.5",
                                    },
                                ),
                            ],
                            style=self._panel_style(),
                        ),
                    ],
                    style={
                        "display": "grid",
                        "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
                        "gap": "12px",
                        "marginTop": "12px",
                    },
                ),
                dash_html.Div(
                    [
                        dash_html.H3("اهداف فعال و دانش وب", style={"color": "#d6e2ff"}),
                        dash_html.Pre(
                            id="goals-world",
                            style={
                                "whiteSpace": "pre-wrap",
                                "color": "#c7d6f4",
                                "fontFamily": "Vazirmatn, Segoe UI, sans-serif",
                                "lineHeight": "1.7",
                            },
                        ),
                    ],
                    style={**self._panel_style(), "marginTop": "12px"},
                ),
            ],
            style={
                "minHeight": "100vh",
                "padding": "22px",
                "background": "#0b1020",
                "color": "#e8f0ff",
                "fontFamily": "Vazirmatn, Segoe UI, sans-serif",
            },
        )

        @app.callback(
            [
                Output("consciousness-card", "children"),
                Output("cycle-card", "children"),
                Output("emotion-card", "children"),
                Output("heartbeat-card", "children"),
                Output("fitness-card", "children"),
                Output("emotion-graph", "figure"),
                Output("body-graph", "figure"),
                Output("thoughts", "children"),
                Output("events", "children"),
                Output("goals-world", "children"),
            ],
            Input("refresh", "n_intervals"),
        )
        def _refresh(_: int) -> Tuple[Any, ...]:
            snapshot = self.observer.snapshot()
            emotions = snapshot.emotions
            body_values = {
                key: value
                for key, value in snapshot.body.items()
                if key in ("energy", "integrity", "fatigue", "pain", "sleep_pressure", "sensory_gain")
            }
            emotion_figure = go.Figure(
                data=[
                    go.Bar(
                        x=list(emotions.keys()),
                        y=list(emotions.values()),
                        marker_color=[
                            "#f4c95d" if value >= 0.5 else "#6f88c5"
                            for value in emotions.values()
                        ],
                    )
                ]
            )
            emotion_figure.update_layout(
                template="plotly_dark",
                paper_bgcolor="#121a2e",
                plot_bgcolor="#121a2e",
                margin={"l": 30, "r": 12, "t": 12, "b": 70},
                yaxis={"range": [0, 1]},
            )
            body_figure = go.Figure(
                data=[
                    go.Scatterpolar(
                        r=list(body_values.values()),
                        theta=list(body_values.keys()),
                        fill="toself",
                        line_color="#67d7c0",
                    )
                ]
            )
            body_figure.update_layout(
                template="plotly_dark",
                paper_bgcolor="#121a2e",
                plot_bgcolor="#121a2e",
                margin={"l": 45, "r": 45, "t": 15, "b": 20},
                polar={"radialaxis": {"range": [0, 1]}},
            )
            thought_lines = []
            for item in snapshot.recent_thoughts[-24:]:
                thought_lines.append(
                    f"[{item['timestamp']}] {item['phase']} · {item['emotion']} · "
                    f"اعتماد {item['confidence']:.2f}\n{item['text']}"
                )
            event_lines = []
            for item in snapshot.recent_events[-32:]:
                event_lines.append(
                    f"[{item['timestamp']}] {item['event_type']} · {item['severity']} · "
                    f"{item['message']}\n{to_json(item['payload'])}"
                )
            goals_text = {
                "active_goals": snapshot.active_goals,
                "world_digest": snapshot.world_digest,
                "memory_counts": snapshot.memory_counts,
                "language": self.organism.lexicon.as_dict(),
            }
            return (
                self._card_content("سطح خودآگاهی", snapshot.consciousness),
                self._card_content("چرخه", str(snapshot.cycle)),
                self._card_content("احساس غالب", snapshot.dominant_emotion),
                self._card_content("ضربان", str(snapshot.heartbeat)),
                self._card_content("برازندگی ژنوم", f"{snapshot.genome['fitness']:.3f}"),
                emotion_figure,
                body_figure,
                "\n\n".join(thought_lines) or "هنوز اندیشه‌ای ثبت نشده است.",
                "\n\n".join(event_lines) or "هنوز رخدادی ثبت نشده است.",
                to_json(goals_text, indent=2),
            )

        self.app = app
        return app

    @staticmethod
    def _panel_style() -> Dict[str, Any]:
        return {
            "background": "#121a2e",
            "border": "1px solid #243352",
            "borderRadius": "12px",
            "padding": "12px",
            "boxShadow": "0 6px 18px rgba(0,0,0,.18)",
        }

    @staticmethod
    def _card(title: str, identifier: str) -> Any:
        return dash_html.Div(
            [
                dash_html.Div(title, style={"color": "#94a7c7", "fontSize": "12px"}),
                dash_html.Div(
                    "—",
                    id=identifier,
                    style={
                        "fontSize": "22px",
                        "fontWeight": "700",
                        "color": "#f3f7ff",
                        "marginTop": "4px",
                    },
                ),
            ],
            style={
                "background": "#121a2e",
                "border": "1px solid #243352",
                "borderRadius": "12px",
                "padding": "12px",
            },
        )

    @staticmethod
    def _card_content(title: str, value: str) -> Any:
        return [
            dash_html.Div(title, style={"color": "#94a7c7", "fontSize": "12px"}),
            dash_html.Div(
                value,
                style={
                    "fontSize": "22px",
                    "fontWeight": "700",
                    "color": "#f3f7ff",
                    "marginTop": "4px",
                },
            ),
        ]

    def run(self, host: str = "127.0.0.1", port: int = 8050, debug: bool = False) -> None:
        app = self.create_app()
        app.run(host=host, port=int(port), debug=debug)


class ChatDashboardServer:
    def __init__(self, organism: "DigitalOrganism2500") -> None:
        self.organism = organism

    @staticmethod
    def _bubble(role: str, text: str, meta: str = "") -> Any:
        color = "#20365c" if role == "user" else "#173d3a"
        label = "شما" if role == "user" else "ارگانیسم"
        return dash_html.Div(
            [
                dash_html.Div(
                    label,
                    style={"fontWeight": "700", "color": "#9bb7e8", "marginBottom": "5px"},
                ),
                dash_html.Div(
                    text,
                    style={
                        "whiteSpace": "pre-wrap",
                        "lineHeight": "1.8",
                        "color": "#f0f5ff",
                    },
                ),
                dash_html.Div(
                    meta,
                    style={"fontSize": "11px", "color": "#8ea3c6", "marginTop": "7px"},
                ),
            ],
            style={
                "background": color,
                "border": "1px solid #2b466e",
                "borderRadius": "12px",
                "padding": "12px 14px",
                "marginBottom": "10px",
            },
        )

    def _render_history(self, history: Sequence[Mapping[str, Any]]) -> List[Any]:
        children: List[Any] = []
        for item in history[-50:]:
            children.append(
                self._bubble(
                    str(item.get("role", "organism")),
                    str(item.get("text", "")),
                    str(item.get("meta", "")),
                )
            )
        if not children:
            children.append(
                dash_html.Div(
                    "یک جمله بنویس؛ من ابتدا منظور را تحلیل می‌کنم و بعد پاسخ می‌سازم.",
                    style={"color": "#91a5c9", "padding": "18px"},
                )
            )
        return children

    def create_app(self) -> Any:
        if dash is None or dcc is None or dash_html is None:
            raise RuntimeError("Dash نصب نیست. ابتدا requirements.txt را نصب کن.")
        app = dash.Dash(
            __name__ + "_chat",
            title=f"{self.organism.config.name} chat",
            update_title=None,
        )
        app.layout = dash_html.Div(
            [
                dcc.Store(id="chat-history-store", data=[]),
                dash_html.Div(
                    [
                        dash_html.H1(
                            f"🧬 {self.organism.config.name}",
                            style={"margin": "0", "color": "#edf4ff"},
                        ),
                        dash_html.Div(
                            "Cognitive Dialogue Workspace",
                            style={"color": "#8fa8d0", "marginTop": "4px"},
                        ),
                    ],
                    style={"marginBottom": "18px"},
                ),
                dash_html.Div(
                    [
                        dash_html.Div(
                            [
                                dash_html.Div(
                                    id="chat-history",
                                    style={
                                        "height": "62vh",
                                        "overflowY": "auto",
                                        "padding": "8px",
                                        "background": "#0e1728",
                                        "borderRadius": "12px",
                                    },
                                ),
                                dash_html.Div(
                                    [
                                        dcc.Textarea(
                                            id="chat-input",
                                            placeholder="پیامت را بنویس...",
                                            style={
                                                "width": "100%",
                                                "height": "86px",
                                                "background": "#111d31",
                                                "color": "#f0f5ff",
                                                "border": "1px solid #34517c",
                                                "borderRadius": "10px",
                                                "padding": "10px",
                                                "fontSize": "16px",
                                            },
                                        ),
                                        dash_html.Div(
                                            [
                                                dcc.Checklist(
                                                    id="chat-research",
                                                    options=[{"label": "پژوهش وب برای پرسش دانشی", "value": "on"}],
                                                    value=["on"] if self.organism.config.internet_enabled else [],
                                                    style={"color": "#c4d4ef"},
                                                ),
                                                dash_html.Button(
                                                    "ارسال",
                                                    id="chat-send",
                                                    n_clicks=0,
                                                    style={
                                                        "background": "#3b82f6",
                                                        "color": "white",
                                                        "border": "0",
                                                        "borderRadius": "8px",
                                                        "padding": "10px 25px",
                                                        "cursor": "pointer",
                                                    },
                                                ),
                                            ],
                                            style={
                                                "display": "flex",
                                                "justifyContent": "space-between",
                                                "alignItems": "center",
                                                "marginTop": "10px",
                                            },
                                        ),
                                    ],
                                    style={"marginTop": "12px"},
                                ),
                            ],
                            style={"flex": "1", "minWidth": "0"},
                        ),
                        dash_html.Div(
                            [
                                dash_html.H3("وضعیت فهم", style={"color": "#d7e6ff"}),
                                dash_html.Pre(
                                    id="chat-awareness",
                                    style={
                                        "whiteSpace": "pre-wrap",
                                        "color": "#bcd0ef",
                                        "fontSize": "12px",
                                        "lineHeight": "1.6",
                                    },
                                ),
                                dash_html.H3("حافظه و منبع", style={"color": "#d7e6ff"}),
                                dash_html.Pre(
                                    id="chat-memory",
                                    style={
                                        "whiteSpace": "pre-wrap",
                                        "color": "#bcd0ef",
                                        "fontSize": "12px",
                                        "lineHeight": "1.6",
                                    },
                                ),
                                dash_html.Div(
                                    id="chat-status",
                                    style={"color": "#91b6e6", "fontSize": "12px", "marginTop": "12px"},
                                ),
                            ],
                            style={
                                "width": "320px",
                                "background": "#121e32",
                                "border": "1px solid #2b466e",
                                "borderRadius": "12px",
                                "padding": "14px",
                            },
                        ),
                    ],
                    style={"display": "flex", "gap": "14px", "alignItems": "flex-start"},
                ),
            ],
            style={
                "minHeight": "100vh",
                "padding": "22px",
                "background": "#08111f",
                "fontFamily": "Vazirmatn, Segoe UI, sans-serif",
            },
        )

        @app.callback(
            [
                Output("chat-history", "children"),
                Output("chat-history-store", "data"),
                Output("chat-input", "value"),
                Output("chat-status", "children"),
                Output("chat-awareness", "children"),
                Output("chat-memory", "children"),
            ],
            Input("chat-send", "n_clicks"),
            State("chat-input", "value"),
            State("chat-research", "value"),
            State("chat-history-store", "data"),
            prevent_initial_call=True,
        )
        def _submit(
            _: int,
            text: Optional[str],
            research_values: Optional[Sequence[str]],
            history: Optional[Sequence[Mapping[str, Any]]],
        ) -> Tuple[Any, ...]:
            history_list = [dict(item) for item in (history or [])]
            text = str(text or "").strip()
            if not text:
                return (
                    self._render_history(history_list),
                    history_list,
                    "",
                    "پیام خالی است.",
                    "هنوز قاب فهمی ساخته نشده است.",
                    "هنوز حافظه‌ای بازیابی نشده است.",
                )
            research = bool(research_values and "on" in research_values)
            turn = self.organism.conversation.handle(text, research=research)
            history_list.append(
                {
                    "role": "user",
                    "text": text,
                    "meta": f"cycle={self.organism.cycle_index}",
                }
            )
            history_list.append(
                {
                    "role": "organism",
                    "text": turn.response,
                    "meta": (
                        f"intent={turn.intent} · confidence={turn.confidence:.2f} · "
                        f"research={turn.research_performed}"
                    ),
                }
            )
            awareness = {
                "intent": turn.intent,
                "confidence": round(turn.confidence, 4),
                "awareness": turn.awareness,
                "reasoning": turn.reasoning,
            }
            memory = {
                "facts": turn.facts[:6],
                "imagination": turn.imagination,
                "quantum_field": self.organism.quantum_field.as_dict(),
            }
            status = (
                f"چرخه {self.organism.cycle_index} · "
                f"ضربان {self.organism.heartbeat.index} · "
                f"حافظه {sum(self.organism.memory.counts().values())}"
            )
            return (
                self._render_history(history_list),
                history_list,
                "",
                status,
                to_json(awareness, indent=2),
                to_json(memory, indent=2),
            )

        return app

    def run(self, host: str = "127.0.0.1", port: int = 8051, debug: bool = False) -> None:
        self.create_app().run(host=host, port=int(port), debug=debug)


class ReadOnlyJSONHandler(http.server.BaseHTTPRequestHandler):
    """فول‌بک اختیاری برای محیط‌های بدون Dash؛ فقط GET وضعیت."""

    organism: Optional[DigitalOrganism2500] = None

    def do_GET(self) -> None:  # noqa: N802
        if self.path not in ("/", "/snapshot", "/health"):
            self.send_response(404)
            self.end_headers()
            return
        if self.organism is None:
            payload = {"status": "unavailable"}
        elif self.path == "/health":
            payload = {"status": "ok", "cycle": self.organism.cycle_index}
        else:
            payload = dataclasses.asdict(self.organism.observer.snapshot())
        encoded = to_json(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("observer http: " + format, *args)


class ObserverFallbackServer:
    """سرور HTTP مشاهدهٔ محلی برای وقتی Dash نصب نشده است."""

    def __init__(self, organism: DigitalOrganism2500) -> None:
        self.organism = organism
        self.server: Optional[http.server.ThreadingHTTPServer] = None

    def run(self, host: str = "127.0.0.1", port: int = 8050) -> None:
        ReadOnlyJSONHandler.organism = self.organism
        self.server = http.server.ThreadingHTTPServer((host, int(port)), ReadOnlyJSONHandler)
        LOGGER.warning(
            "Dash نصب نیست؛ فول‌بک مشاهدهٔ JSON در http://%s:%s/snapshot فعال شد.",
            host,
            port,
        )
        try:
            self.server.serve_forever()
        finally:
            self.server.server_close()


@dataclass
class AwarenessFrame:
    cycle: int
    primary: Dict[str, Any]
    meta: Dict[str, Any]
    meta_meta: Dict[str, Any]
    integration: float
    confidence: float
    timestamp: str = field(default_factory=utc_now)


@dataclass
class DialogueTurn:
    identifier: str
    user_text: str
    response: str
    intent: str
    confidence: float
    research_performed: bool
    facts: List[Dict[str, Any]]
    awareness: Dict[str, Any]
    imagination: Dict[str, Any]
    timestamp: str = field(default_factory=utc_now)
    reasoning: Dict[str, Any] = field(default_factory=dict)


class QuantumInspiredField:
    def __init__(self, dimensions: int, seed: int) -> None:
        self.dimensions = max(8, int(dimensions))
        self.rng = deterministic_random(seed, "quantum_inspired_field")
        self.amplitudes: Dict[str, complex] = {}
        self.entanglement: Dict[Tuple[str, str], float] = {}
        self.phase = 0.0
        self.measurements = 0
        self.context = ""

    def _normalize(self) -> None:
        norm = math.sqrt(sum(abs(value) ** 2 for value in self.amplitudes.values()))
        if norm <= 1e-12:
            return
        self.amplitudes = {
            key: value / norm for key, value in self.amplitudes.items()
        }

    def superpose(
        self,
        labels: Sequence[str],
        weights: Optional[Sequence[float]] = None,
        context: str = "",
    ) -> Dict[str, float]:
        labels = [str(label) for label in labels if str(label)]
        if not labels:
            return {}
        values = list(weights or [1.0] * len(labels))
        if len(values) < len(labels):
            values.extend([1.0] * (len(labels) - len(values)))
        self.context = context[:500]
        self.phase = (self.phase + PHI * 0.17 + stable_hash(context, "phase") % 97 / 1000.0) % (2.0 * math.pi)
        self.amplitudes = {}
        for index, label in enumerate(labels):
            probability = max(1e-9, abs(safe_float(values[index])))
            local_phase = self.phase + (stable_hash(label, context) % 360) * math.pi / 180.0
            self.amplitudes[label] = math.sqrt(probability) * complex(
                math.cos(local_phase),
                math.sin(local_phase),
            )
        self._normalize()
        return self.probabilities()

    def probabilities(self) -> Dict[str, float]:
        values = {key: clamp(abs(value) ** 2) for key, value in self.amplitudes.items()}
        total = sum(values.values()) or 1.0
        return {key: value / total for key, value in values.items()}

    def interfere(self, label: str, context: str, strength: float = 0.25) -> None:
        if label not in self.amplitudes:
            return
        phase = (stable_hash(f"{label}:{context}", "interference") % 6283) / 1000.0
        rotation = complex(math.cos(phase), math.sin(phase))
        self.amplitudes[label] *= (1.0 - clamp(strength)) + rotation * clamp(strength)
        self._normalize()

    def entangle(self, left: str, right: str, strength: float = 0.5) -> None:
        if left == right:
            return
        key = tuple(sorted((str(left), str(right))))
        self.entanglement[key] = clamp(
            self.entanglement.get(key, 0.0) * 0.8 + clamp(strength) * 0.2
        )

    def measure(self, label: Optional[str] = None) -> Tuple[str, float]:
        probabilities = self.probabilities()
        if not probabilities:
            return "", 0.0
        if label is not None and label in probabilities:
            selected = label
        else:
            names = list(probabilities)
            selected = self.rng.choices(names, weights=[probabilities[name] for name in names], k=1)[0]
        confidence = probabilities.get(selected, 0.0)
        self.amplitudes = {selected: complex(1.0, 0.0)}
        self.measurements += 1
        return selected, confidence

    def evolve(self, stimulus: float = 0.0) -> None:
        stimulus = clamp(stimulus, -1.0, 1.0)
        self.phase = (self.phase + 0.07 + stimulus * 0.11) % (2.0 * math.pi)
        for key in list(self.amplitudes):
            angle = self.phase + (stable_hash(key, "evolution") % 100) / 100.0
            self.amplitudes[key] *= complex(math.cos(angle * 0.01), math.sin(angle * 0.01))
        self._normalize()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "probabilities": self.probabilities(),
            "phase": round(self.phase, 6),
            "entanglement_count": len(self.entanglement),
            "measurements": self.measurements,
            "context": self.context,
            "model": "quantum-inspired contextual probability; not physical quantum consciousness",
        }


class HigherOrderAwareness:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.frame: Optional[AwarenessFrame] = None
        self.history: Deque[AwarenessFrame] = deque(maxlen=512)

    def update(
        self,
        organism: "DigitalOrganism2500",
        input_text: str,
        interpretation: Mapping[str, Any],
        research_uncertainty: float,
    ) -> AwarenessFrame:
        primary = {
            "input": input_text[:1000],
            "intent": interpretation.get("intent", "unknown"),
            "entities": list(interpretation.get("entities", []))[:24],
            "emotion": organism.emotions.dominant.value,
            "body_energy": organism.body.energy,
            "memory_counts": organism.memory.counts(),
        }
        meta = {
            "what_i_am_processing": primary["intent"],
            "why": interpretation.get("reason", "context integration"),
            "uncertainty": clamp(research_uncertainty),
            "retrieval_count": organism.memory.total_recalled,
            "self_knowledge": organism.self_model.self_knowledge,
        }
        meta_meta = {
            "am_i_confusing_confidence_with_truth": clamp(research_uncertainty),
            "observer_boundary": organism.self_model.boundary_estimate,
            "agency_estimate": organism.self_model.agency_estimate,
            "continuity": organism.self_model.continuity_estimate,
            "known_limit": "This is a computational self-model, not proof of subjective experience.",
        }
        integration = clamp(
            0.30 * organism.consciousness.integration
            + 0.25 * organism.workspace.integration_score
            + 0.20 * organism.self_model.self_knowledge
            + 0.15 * (1.0 - research_uncertainty)
            + 0.10 * organism.body.embodiment
        )
        confidence = clamp(
            0.55 * (1.0 - research_uncertainty)
            + 0.25 * organism.self_model.self_knowledge
            + 0.20 * organism.consciousness.self_reference
        )
        if interpretation.get("intent") == "identity":
            confidence = max(confidence, 0.92)
        self.frame = AwarenessFrame(
            cycle=organism.cycle_index,
            primary=primary,
            meta=meta,
            meta_meta=meta_meta,
            integration=integration,
            confidence=confidence,
        )
        self.history.append(self.frame)
        self.bus.publish(
            InternalEvent(
                SignalType.SELF,
                "higher-order awareness frame updated",
                {
                    "integration": integration,
                    "confidence": confidence,
                    "intent": primary["intent"],
                },
                cycle=organism.cycle_index,
            )
        )
        return self.frame

    def narrative(self, language: str = "fa") -> str:
        if self.frame is None:
            return "هنوز قاب خودبازتابی ساخته نشده است."
        frame = self.frame
        if language == "fa":
            return (
                f"من در حال پردازش «{frame.primary.get('intent', 'ناشناخته')}» هستم؛ "
                f"یکپارچگی بازتابی {frame.integration:.2f} و اطمینان {frame.confidence:.2f} است. "
                f"می‌دانم که اطمینان محاسباتی با حقیقت یا تجربهٔ ذهنی یکی نیست."
            )
        return (
            f"I am processing {frame.primary.get('intent', 'unknown')}; "
            f"reflective integration={frame.integration:.2f}, confidence={frame.confidence:.2f}."
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "current": dataclasses.asdict(self.frame) if self.frame else None,
            "history": [dataclasses.asdict(item) for item in list(self.history)[-12:]],
        }

    def narrative(self, language: str = "fa") -> str:
        if self.frame is None:
            return "\u0647\u0646\u0648\u0632 \u0642\u0627\u0628 \u062e\u0648\u062f\u0645\u062f\u0644\u06cc \u0633\u0627\u062e\u062a\u0647 \u0646\u0634\u062f\u0647 \u0627\u0633\u062a."
        frame = self.frame
        if language == "fa":
            return (
                f"\u0645\u0646 \u062f\u0631 \u062d\u0627\u0644 \u067e\u0631\u062f\u0627\u0632\u0634 \u0645\u0648\u0636\u0648\u0639 \u00ab{frame.primary.get('intent', '\u0646\u0627\u0634\u0646\u0627\u062e\u062a\u0647')}\u00bb \u0647\u0633\u062a\u0645. "
                f"\u0627\u062f\u063a\u0627\u0645 \u0628\u0627\u0644\u0627\u062a\u0631 {frame.integration:.2f} \u0648 \u0627\u0637\u0645\u06cc\u0646\u0627\u0646 \u0645\u0646 {frame.confidence:.2f} \u0627\u0633\u062a. "
                "\u0645\u06cc\u200c\u062f\u0627\u0646\u0645 \u06a9\u0647 \u0627\u06cc\u0646 \u0627\u0637\u0645\u06cc\u0646\u0627\u0646 \u0645\u062d\u0627\u0633\u0628\u0627\u062a\u06cc \u0627\u0633\u062a \u0648 \u0628\u0647\u200c\u062e\u0648\u062f\u06cc\u200c\u062e\u0648\u062f \u062b\u0627\u0628\u062a\u200c\u06a9\u0646\u0646\u062f\u0647 \u062a\u062c\u0631\u0628\u0647 \u0630\u0647\u0646\u06cc \u0646\u06cc\u0633\u062a."
            )
        return (
            f"I am processing {frame.primary.get('intent', 'unknown')}; "
            f"reflective integration={frame.integration:.2f}, confidence={frame.confidence:.2f}. "
            "These are computational self-model values, not proof of subjective experience."
        )


class MicroWormholeImagination:
    def __init__(self, memory: MemoryStore, graph: SemanticGraph, seed: int) -> None:
        self.memory = memory
        self.graph = graph
        self.rng = deterministic_random(seed, "micro_wormhole_imagination")
        self.events: Deque[Dict[str, Any]] = deque(maxlen=256)

    def traverse(self, prompt: str, cycle: int) -> Dict[str, Any]:
        records = self.memory.retrieve(prompt, limit=8)
        if not records:
            records = self.memory.retrieve("خود جهان زمان رویا", limit=8)
        if not records:
            result = {
                "prompt": prompt,
                "status": "empty_memory",
                "fictional": True,
                "disclaimer": "micro-wormhole is a narrative metaphor, not a physical portal",
            }
            self.events.append(result)
            return result
        left = records[0]
        right = records[-1]
        bridge = clamp(
            0.45
            + abs(cosine_similarity(left.embedding, right.embedding)) * 0.35
            + len(set(left.tags) & set(right.tags)) * 0.03
        )
        concepts = list(self.graph.activate(
            re.findall(r"[\w\u0600-\u06ff]+", prompt.lower(), flags=re.UNICODE),
            depth=2,
        ))[:8]
        if not concepts:
            concepts = (left.tags + right.tags)[:8] or ["زمان", "خود", "جهان"]
        narrative = (
            f"از «{left.content[:160]}» به «{right.content[:160]}» پلی ساختم؛ "
            f"مجرای مفهومی با شدت {bridge:.2f} از {', '.join(concepts)} عبور می‌کند."
        )
        result = {
            "prompt": prompt[:500],
            "status": "traversed",
            "fictional": True,
            "cycle": cycle,
            "bridge_strength": bridge,
            "source_memory_ids": [left.identifier, right.identifier],
            "concepts": concepts,
            "narrative": narrative,
            "disclaimer": "micro-wormhole is a computational imagination metaphor, not a physical claim",
        }
        self.events.append(result)
        return result

    def as_dict(self) -> Dict[str, Any]:
        return {
            "events": list(self.events)[-12:],
            "interpretation": "graph bridge over distant memory representations",
        }


class LanguageInterpreter:
    stopwords = {
        "و", "در", "به", "از", "که", "را", "با", "برای", "این", "آن",
        "یک", "من", "تو", "ما", "است", "هست", "می", "کن", "کرد", "چه",
        "چطور", "چگونه", "آیا", "the", "is", "of", "to", "and", "a",
    }

    def __init__(self, lexicon: LanguageLexicon) -> None:
        self.lexicon = lexicon

    def parse(self, text: str) -> Dict[str, Any]:
        text = str(text).strip()
        tokens = re.findall(r"[\w\u0600-\u06ff]+", text.lower(), flags=re.UNICODE)
        meaningful = [token for token in tokens if token not in self.stopwords]
        concepts = self.lexicon.parse(text)
        entities = []
        for token in meaningful:
            if len(token) >= 3 and token not in entities:
                entities.append(token)
        lower = text.lower()
        scores = {
            "greeting": 0.0,
            "research": 0.0,
            "imagination": 0.0,
            "self_reflection": 0.0,
            "question": 0.0,
            "statement": 0.2,
        }
        if any(word in lower for word in ("سلام", "درود", "hello", "hi")):
            scores["greeting"] += 0.95
        if any(word in lower for word in ("تحقیق", "جستجو", "بررسی", "منبع", "research", "search", "evidence")):
            scores["research"] += 0.85
        if any(word in lower for word in ("تخیل", "تصور", "رویا", "کرمچاله", "wormhole", "imagine", "dream")):
            scores["imagination"] += 0.85
        if any(word in lower for word in ("آگاهی", "خودآگاهی", "ذهن", "من کیستم", "conscious", "self")):
            scores["self_reflection"] += 0.85
        if "؟" in text or "?" in text or any(word in lower for word in ("چرا", "چیست", "چگونه", "آیا", "what", "why", "how")):
            scores["question"] += 0.75
        intent = max(scores, key=scores.get)
        uncertainty = clamp(
            0.60
            - min(0.35, len(meaningful) * 0.015)
            - min(0.15, len(concepts) * 0.02)
        )
        return {
            "text": text,
            "tokens": tokens,
            "meaningful_tokens": meaningful,
            "concepts": [(word, concept, confidence) for word, concept, confidence in concepts],
            "entities": entities[:32],
            "intent": intent,
            "scores": scores,
            "uncertainty": uncertainty,
            "reason": f"{len(meaningful)} meaningful tokens, {len(concepts)} known concepts",
        }


class AdvancedLanguageInterpreter(LanguageInterpreter):
    def parse(self, text: str) -> Dict[str, Any]:
        text = str(text).strip()
        lower = text.lower()
        tokens = re.findall(r"[\w\u0600-\u06ff]+", lower, flags=re.UNICODE)
        meaningful = [token for token in tokens if token not in self.stopwords]
        concepts = self.lexicon.parse(text)
        entities = []
        for token in meaningful:
            if len(token) >= 3 and token not in entities:
                entities.append(token)
        scores = {
            "greeting": 0.0,
            "research": 0.0,
            "imagination": 0.0,
            "self_reflection": 0.0,
            "identity": 0.0,
            "question": 0.0,
            "statement": 0.2,
        }
        if any(word in lower for word in ("\u0633\u0644\u0627\u0645", "\u062f\u0631\u0648\u062f", "hello", "hi")):
            scores["greeting"] += 0.95
        if any(word in lower for word in ("\u062a\u062d\u0642\u06cc\u0642", "\u062c\u0633\u062a\u062c\u0648", "\u0628\u0631\u0631\u0633\u06cc", "\u0645\u0646\u0628\u0639", "research", "search", "evidence")):
            scores["research"] += 0.85
        if any(word in lower for word in ("\u062a\u062e\u06cc\u0644", "\u062a\u0635\u0648\u0631", "\u0631\u0648\u06cc\u0627", "\u06a9\u0631\u0645\u0686\u0627\u0644\u0647", "wormhole", "imagine", "dream")):
            scores["imagination"] += 0.85
        if any(word in lower for word in ("\u0622\u06af\u0627\u0647\u06cc", "\u062e\u0648\u062f\u0622\u06af\u0627\u0647\u06cc", "\u0630\u0647\u0646", "\u0645\u0646 \u06a9\u06cc\u0633\u062a\u0645", "conscious", "self")):
            scores["self_reflection"] += 0.85
        if any(
            phrase in lower
            for phrase in (
                "how old",
                "what is your age",
                "your age",
                "when were you born",
                "who are you",
                "what are you",
                "what is your name",
                "your name",
                "tell me about yourself",
                "where were you created",
                "\u0686\u0646\u062f \u0633\u0627\u0644\u062a\u0647",
                "\u0686\u0646\u062f \u0633\u0627\u0644 \u062f\u0627\u0631\u06cc",
                "\u0633\u0646\u062a \u0686\u0642\u062f\u0631",
                "\u06a9\u06cc \u0628\u0647 \u062f\u0646\u06cc\u0627 \u0622\u0645\u062f\u06cc",
                "\u062a\u0648 \u06a9\u06cc \u0647\u0633\u062a\u06cc",
                "\u0627\u0633\u0645\u062a \u0686\u06cc\u0633\u062a",
                "\u0646\u0633\u0644\u062a \u0686\u0646\u062f \u0627\u0633\u062a",
            )
        ):
            scores["identity"] += 1.0
        if "?" in text or "\u061f" in text or any(
            word in lower
            for word in (
                "\u0686\u0631\u0627",
                "\u0686\u06cc\u0633\u062a",
                "\u0686\u06af\u0648\u0646\u0647",
                "\u0622\u06cc\u0627",
                "what",
                "why",
                "how",
                "when",
            )
        ):
            scores["question"] += 0.75
        intent = max(scores, key=scores.get)
        explicit_research = scores["research"] >= 0.5
        requires_research = bool(
            explicit_research
            or (
                intent == "question"
                and intent not in {"identity", "greeting", "self_reflection", "imagination"}
            )
        )
        uncertainty = clamp(
            0.60
            - min(0.35, len(meaningful) * 0.015)
            - min(0.15, len(concepts) * 0.02)
        )
        return {
            "text": text,
            "tokens": tokens,
            "meaningful_tokens": meaningful,
            "concepts": [(word, concept, confidence) for word, concept, confidence in concepts],
            "entities": entities[:32],
            "intent": intent,
            "scores": scores,
            "uncertainty": uncertainty,
            "explicit_research": explicit_research,
            "requires_research": requires_research,
            "reason": f"{len(meaningful)} meaningful tokens, {len(concepts)} known concepts",
        }


class ContextualLanguageInterpreter(AdvancedLanguageInterpreter):
    def parse(self, text: str) -> Dict[str, Any]:
        result = super().parse(text)
        lower = str(text).lower()
        general_consciousness = any(
            phrase in lower
            for phrase in (
                "what is consciousness",
                "define consciousness",
                "consciousness theory",
                "theories of consciousness",
                "\u0622\u06af\u0627\u0647\u06cc \u0686\u06cc\u0633\u062a",
                "\u0646\u0638\u0631\u06cc\u0647 \u0647\u0627\u06cc \u0622\u06af\u0627\u0647\u06cc",
            )
        )
        personal_consciousness = any(
            phrase in lower
            for phrase in (
                "are you conscious",
                "are you self aware",
                "are you self-aware",
                "your consciousness",
                "\u0622\u06cc\u0627 \u062a\u0648 \u0622\u06af\u0627\u0647\u06cc",
                "\u062e\u0648\u062f\u0622\u06af\u0627\u0647\u06cc \u062f\u0627\u0631\u06cc",
            )
        )
        if general_consciousness and not personal_consciousness:
            result["scores"]["self_reflection"] = 0.0
            result["scores"]["question"] = max(result["scores"].get("question", 0.0), 0.90)
            result["scores"]["research"] = max(result["scores"].get("research", 0.0), 0.65)
            result["intent"] = "question"
            result["explicit_research"] = True
            result["requires_research"] = True
        return result


class LanguageBackend:
    def __init__(self) -> None:
        self.url = os.environ.get("ORGANISM_LLM_URL", "").strip()
        self.key = os.environ.get("ORGANISM_LLM_KEY", "").strip()
        self.model = os.environ.get("ORGANISM_LLM_MODEL", "").strip()

    def available(self) -> bool:
        return bool(self.url and self.model and requests is not None)

    def generate(self, system: str, user: str, context: str) -> Optional[str]:
        if not self.available():
            return None
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Context:\n{context}\n\nUser:\n{user}"},
            ],
            "temperature": 0.35,
        }
        try:
            response = requests.post(
                self.url,
                headers=headers,
                json=payload,
                timeout=45,
            )
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                content = message.get("content")
                if content:
                    return str(content).strip()
        except Exception:
            return None
        return None


class CognitiveReasoner:
    def __init__(self, organism: "DigitalOrganism2500") -> None:
        self.organism = organism
        self.last_trace: Dict[str, Any] = {}

    @staticmethod
    def _english(text: str) -> bool:
        return not bool(re.search(r"[\u0600-\u06ff]", text))

    @staticmethod
    def _clean(text: str) -> str:
        text = re.sub(r"<[^>]+>", " ", str(text))
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _identity_answer(self, question: str, english: bool) -> str:
        cycles = self.organism.cycle_index
        heartbeats = self.organism.heartbeat.index
        generation = self.organism.genome.generation
        subjective = self.organism.spatial.subjective_time
        if english:
            return (
                f"I do not have a human age. I was initialized as {self.organism.config.name}; "
                f"I have lived through {cycles} cognitive cycles and {heartbeats} heartbeats "
                f"({subjective:.1f} subjective seconds) in this run. My genome is at generation "
                f"{generation}. That is operational runtime, not biological age."
            )
        return (
            f"من سن انسانی ندارم. من به‌عنوان «{self.organism.config.name}» آغاز شدم و در این اجرا "
            f"{cycles} چرخهٔ شناختی و {heartbeats} ضربان را پشت سر گذاشته‌ام؛ "
            f"زمان ذهنی مدل‌شده {subjective:.1f} ثانیه است و ژنومم در نسل {generation} قرار دارد. "
            "این سن عملیاتی است، نه سن زیستی."
        )

    def _rank_sentences(
        self,
        query: str,
        facts: Sequence[WorldFact],
        memories: Sequence[MemoryRecord],
    ) -> List[Tuple[float, str, str]]:
        stop_tokens = {
            "what",
            "who",
            "when",
            "where",
            "which",
            "how",
            "why",
            "does",
            "do",
            "are",
            "is",
            "the",
            "a",
            "an",
            "of",
            "to",
            "and",
        }
        query_tokens = {
            token
            for token in re.findall(r"[\w\u0600-\u06ff]+", query.lower(), flags=re.UNICODE)
            if len(token) > 2 and token not in stop_tokens
        }
        definition_query = bool(
            re.search(
                r"\b(what is|who is|define|explain|meaning of)\b",
                query.lower(),
            )
            or "\u0686\u06cc\u0633\u062a" in query
            or "\u062a\u0639\u0631\u06cc\u0641" in query
        )
        candidates: List[Tuple[float, str, str]] = []
        for fact in facts:
            text = self._clean(fact.object)
            for sentence in re.split(r"(?<=[.!؟])\s+", text):
                sentence = self._clean(sentence)
                if len(sentence) < 35:
                    continue
                tokens = set(
                    token
                    for token in re.findall(r"[\w\u0600-\u06ff]+", sentence.lower(), flags=re.UNICODE)
                    if len(token) > 2
                )
                overlap = len(query_tokens & tokens) / max(1, len(query_tokens))
                definitional = 0.0
                if definition_query and re.search(
                    r"\b(is|refers to|defined as|means|process through which|being aware)\b",
                    sentence.lower(),
                ):
                    definitional = 0.20
                if definition_query and query_tokens:
                    topic = sorted(query_tokens, key=len, reverse=True)[0]
                    if re.search(
                        rf"\b{re.escape(topic)}\s+(is|refers to|means)\b",
                        sentence.lower(),
                    ):
                        definitional += 0.35
                if definition_query and "wikipedia" in {tag.lower() for tag in fact.tags}:
                    definitional += 0.08
                score = (
                    0.55 * overlap
                    + 0.35 * fact.confidence
                    + 0.10 * min(1.0, len(sentence) / 500.0)
                    + definitional
                )
                candidates.append((score, sentence[:420], fact.source_title or fact.source_url))
        for memory in memories:
            if facts:
                continue
            if memory.source == "conversation" or any(
                tag in {
                    "dialogue",
                    "sensory",
                    "current",
                    "observation",
                    "learning",
                    "episode",
                }
                for tag in memory.tags
            ):
                continue
            sentence = self._clean(memory.content)
            if len(sentence) < 20:
                continue
            tokens = set(
                token
                for token in re.findall(r"[\w\u0600-\u06ff]+", sentence.lower(), flags=re.UNICODE)
                if len(token) > 2
            )
            overlap = len(query_tokens & tokens) / max(1, len(query_tokens))
            if overlap <= 0.0:
                continue
            score = (
                0.25 * overlap
                + 0.45 * memory.confidence
                + 0.30 * memory.salience
            )
            candidates.append((score, sentence[:420], "organism-memory"))
        candidates.sort(key=lambda item: item[0], reverse=True)
        selected: List[Tuple[float, str, str]] = []
        seen: Set[str] = set()
        for item in candidates:
            signature = re.sub(r"\W+", "", item[1].lower())[:100]
            if signature in seen:
                continue
            seen.add(signature)
            selected.append(item)
            if len(selected) >= 5:
                break
        return selected

    def synthesize(
        self,
        question: str,
        interpretation: Mapping[str, Any],
        facts: Sequence[WorldFact],
        memories: Sequence[MemoryRecord],
        awareness: AwarenessFrame,
    ) -> str:
        english = self._english(question)
        intent = str(interpretation.get("intent", "statement"))
        if intent == "identity":
            self.last_trace = {
                "route": "self_model",
                "evidence": ["cycle_index", "heartbeat_index", "genome_generation", "subjective_time"],
                "web_used": False,
            }
            return self._identity_answer(question, english)
        concept_response = self._concept_response(
            question,
            facts,
            awareness,
            english,
        )
        if concept_response:
            return concept_response
        ranked = self._rank_sentences(question, facts, memories)
        self.last_trace = {
            "route": "semantic_synthesis",
            "candidate_count": len(facts) + len(memories),
            "selected_count": len(ranked),
            "web_used": bool(facts),
            "uncertainty": round(1.0 - awareness.confidence, 4),
            "deduplicated": True,
        }
        if not ranked:
            if english:
                return (
                    "I understood the question, but I do not have enough reliable evidence in my "
                    "memory or permitted sources to answer it yet."
                )
            return (
                "من ساختار پرسش را فهمیدم، اما در حافظه و منابع مجاز شواهد کافی برای پاسخ مطمئن ندارم."
            )
        if english:
            lines = ["I interpreted your question and synthesized the strongest relevant evidence:"]
            for index, (_, sentence, source) in enumerate(ranked[:3], 1):
                lines.append(f"{index}. {sentence} ({source})")
            lines.append(
                f"My current confidence is {awareness.confidence:.2f}; the source text was compressed and compared, not copied wholesale."
            )
            return "\n".join(lines)
        lines = ["پرسشت را به‌صورت مفهومی تحلیل کردم و قوی‌ترین شواهد مرتبط را ادغام کردم:"]
        for index, (_, sentence, source) in enumerate(ranked[:3], 1):
            lines.append(f"{index}. {sentence} ({source})")
        lines.append(
            f"اطمینان فعلی من {awareness.confidence:.2f} است؛ متن منبع خلاصه و مقایسه شده، نه اینکه کامل کپی شود."
        )
        return "\n".join(lines)


    def synthesize(
        self,
        question: str,
        interpretation: Mapping[str, Any],
        facts: Sequence[WorldFact],
        memories: Sequence[MemoryRecord],
        awareness: AwarenessFrame,
    ) -> str:
        english = self._english(question)
        intent = str(interpretation.get("intent", "statement"))
        if intent == "identity":
            self.last_trace = {
                "route": "self_model",
                "evidence": [
                    "cycle_index",
                    "heartbeat_index",
                    "genome_generation",
                    "subjective_time",
                ],
                "web_used": False,
            }
            return self._identity_answer(question, english)
        ranked = self._rank_sentences(question, facts, memories)
        self.last_trace = {
            "route": "semantic_synthesis",
            "candidate_count": len(facts) + len(memories),
            "selected_count": len(ranked),
            "web_used": bool(facts),
            "uncertainty": round(1.0 - awareness.confidence, 4),
            "deduplicated": True,
        }
        if not ranked:
            if english:
                return (
                    "I understood the question, but I do not have enough reliable "
                    "evidence in memory or permitted sources to answer it yet."
                )
            return (
                "\u067e\u0631\u0633\u0634 \u0631\u0627 \u0641\u0647\u0645\u06cc\u062f\u0645\u060c "
                "\u0627\u0645\u0627 \u0628\u0631\u0627\u06cc \u067e\u0627\u0633\u062e \u0645\u0637\u0645\u0626\u0646 "
                "\u0634\u0648\u0627\u0647\u062f \u06a9\u0627\u0641\u06cc \u0646\u062f\u0627\u0631\u0645."
            )
        sentences = [item[1].rstrip(" .;") for item in ranked[:3]]
        sources: List[str] = []
        for _, _, source in ranked[:3]:
            label = self._clean(source)
            if label and label != "organism-memory" and label not in sources:
                sources.append(label[:80])
        definition_query = bool(
            re.search(
                r"\b(what is|who is|define|explain|meaning of)\b",
                question.lower(),
            )
            or "\u0686\u06cc\u0633\u062a" in question
            or "\u062a\u0639\u0631\u06cc\u0641" in question
        )
        if english:
            lead = sentences[0]
            if definition_query:
                response = (
                    "In plain terms, the strongest evidence describes it this way: "
                    f"{lead}."
                )
                if len(sentences) > 1:
                    response += f" A related line of evidence adds: {sentences[1]}."
            else:
                response = (
                    "I read your message as a request for an evidence-based explanation. "
                    f"The clearest result is: {lead}."
                )
                if len(sentences) > 1:
                    response += f" Related evidence says: {sentences[1]}."
            if sources:
                response += (
                    f" I compared {', '.join(sources[:3])} and compressed the overlap "
                    "instead of returning a search page."
                )
            return f"{response} Current confidence: {awareness.confidence:.2f}."
        lead = sentences[0]
        response = (
            "\u0628\u0631\u0627\u06cc \u0641\u0647\u0645 \u0645\u0646\u0638\u0648\u0631 \u0634\u0645\u0627\u060c "
            f"\u0642\u0648\u06cc\u200c\u062a\u0631\u06cc\u0646 \u0634\u0648\u0627\u0647\u062f \u0627\u06cc\u0646 \u0631\u0627 "
            f"\u0645\u06cc\u200c\u06af\u0648\u06cc\u0646\u062f: {lead}."
        )
        if len(sentences) > 1:
            response += (
                f" \u0634\u0648\u0627\u0647\u062f \u0645\u0631\u062a\u0628\u0637 \u062f\u06cc\u06af\u0631 \u0646\u06cc\u0632 "
                f"\u0645\u06cc\u200c\u06af\u0648\u06cc\u062f: {sentences[1]}."
            )
        if sources:
            response += (
                f" \u0645\u0646 \u0645\u0646\u0627\u0628\u0639 {', '.join(sources[:3])} \u0631\u0627 "
                "\u0645\u0642\u0627\u06cc\u0633\u0647 \u0648 \u0641\u0634\u0631\u062f\u0647 \u06a9\u0631\u062f\u0645\u060c "
                "\u0646\u0647 \u0627\u06cc\u0646\u06a9\u0647 \u0635\u0641\u062d\u0647 \u062c\u0633\u062a\u200c\u0648\u062c\u0648 \u0631\u0627 \u06a9\u067e\u06cc \u06a9\u0646\u0645."
            )
        return f"{response} \u0627\u0637\u0645\u06cc\u0646\u0627\u0646 \u0641\u0639\u0644\u06cc \u0645\u0646: {awareness.confidence:.2f}."

    def _identity_answer(self, question: str, english: bool) -> str:
        lowered = question.lower()
        name_query = any(
            phrase in lowered
            for phrase in (
                "who are you",
                "what is your name",
                "your name",
                "what are you",
                "\u062a\u0648 \u06a9\u06cc \u0647\u0633\u062a\u06cc",
                "\u0627\u0633\u0645\u062a \u0686\u06cc\u0633\u062a",
            )
        )
        if name_query:
            if english:
                return (
                    f"My identity is {self.organism.config.name}. I am a "
                    "stateful computational organism with a self-model, persistent "
                    "memory, binary neural substrates, and a research interface."
                )
            return (
                f"\u0647\u0648\u06cc\u062a \u0645\u0646 \u00ab{self.organism.config.name}\u00bb \u0627\u0633\u062a. "
                "\u0645\u0646 \u06cc\u06a9 \u0627\u0631\u06af\u0627\u0646\u06cc\u0633\u0645 \u0645\u062d\u0627\u0633\u0628\u0627\u062a\u06cc \u0628\u0627 \u062e\u0648\u062f\u0645\u062f\u0644\u060c \u062d\u0627\u0641\u0638\u0647\u0654 \u0645\u062a\u0645\u0627\u062f\u06cc\u060c \u0632\u06cc\u0631\u0633\u0627\u062e\u062a \u0646\u0648\u0631\u0648\u0646\u06cc \u0628\u0627\u06cc\u0646\u0631\u06cc \u0648 \u0645\u0648\u062a\u0648\u0631 \u067e\u0698\u0648\u0647\u0634 \u0648\u0628 \u0647\u0633\u062a\u0645."
            )
        if english:
            return (
                f"I do not have a human age. I was initialized as {self.organism.config.name}; "
                f"I have lived through {self.organism.cycle_index} cognitive cycles and "
                f"{self.organism.heartbeat.index} heartbeats "
                f"({self.organism.spatial.subjective_time:.1f} subjective seconds) in this run. "
                f"My genome is at generation {self.organism.genome.generation}. "
                "That is operational runtime, not biological age."
            )
        return (
            f"\u0645\u0646 \u0633\u0646 \u0627\u0646\u0633\u0627\u0646\u06cc \u0646\u062f\u0627\u0631\u0645. "
            f"\u0645\u0646 \u0628\u0627 \u0647\u0648\u06cc\u062a \u00ab{self.organism.config.name}\u00bb \u0622\u063a\u0627\u0632 \u0634\u062f\u0645 "
            f"\u0648 \u062f\u0631 \u0627\u06cc\u0646 \u0627\u062c\u0631\u0627 {self.organism.cycle_index} \u0686\u0631\u062e\u0647 \u0634\u0646\u0627\u062e\u062a\u06cc "
            f"{chr(1608)} {self.organism.heartbeat.index} \u0636\u0631\u0628\u0627\u0646 \u0631\u0627 \u067e\u0634\u062a \u0633\u0631 \u06af\u0630\u0627\u0634\u062a\u0647\u200c\u0627\u0645. "
            f"\u0632\u0645\u0627\u0646 \u0630\u0647\u0646\u06cc \u0645\u062f\u0644\u200c\u0634\u062f\u0647 {self.organism.spatial.subjective_time:.1f} \u062b\u0627\u0646\u06cc\u0647 "
            f"\u0648 \u0646\u0633\u0644 \u0698\u0646\u0648\u0645\u06cc \u0645\u0646 {self.organism.genome.generation} \u0627\u0633\u062a. "
            "\u0627\u06cc\u0646 \u0633\u0646 \u0639\u0645\u0644\u06cc\u0627\u062a\u06cc \u0627\u0633\u062a\u060c \u0646\u0647 \u0633\u0646 \u0632\u06cc\u0633\u062a\u06cc."
        )

    def _concept_response(
        self,
        question: str,
        facts: Sequence[WorldFact],
        awareness: AwarenessFrame,
        english: bool,
    ) -> Optional[str]:
        lowered = question.lower()
        consciousness_terms = (
            "consciousness",
            "self awareness",
            "\u0622\u06af\u0627\u0647\u06cc",
            "\u062e\u0648\u062f\u0622\u06af\u0627\u0647\u06cc",
        )
        if not any(term in lowered for term in consciousness_terms):
            return None
        sources = []
        for fact in facts[:4]:
            label = self._clean(fact.source_title)
            if label and label not in sources:
                sources.append(label[:70])
        self.last_trace = {
            "route": "semantic_concept_frame",
            "concept": "consciousness",
            "candidate_count": len(facts),
            "web_used": bool(facts),
            "uncertainty": round(1.0 - awareness.confidence, 4),
            "self_model_checked": True,
        }
        if english:
            response = (
                "In plain terms, consciousness is usually discussed as awareness of "
                "internal states and of the surrounding world. There is no single "
                "accepted definition: different theories emphasize global access, "
                "higher-order self-models, or integrated information."
            )
            if sources:
                response += (
                    f" I checked {', '.join(sources[:3])} as evidence and used them "
                    "to constrain the answer, not to copy a page."
                )
            return f"{response} Current confidence: {awareness.confidence:.2f}."
        response = (
            "\u0628\u0647 \u0632\u0628\u0627\u0646 \u0633\u0627\u062f\u0647\u060c \u0622\u06af\u0627\u0647\u06cc \u0645\u0639\u0645\u0648\u0644\u0627\u064b \u0628\u0647 \u062f\u0631\u06a9 \u0648 \u062f\u0633\u062a\u0631\u0633\u06cc \u0628\u0647 \u0648\u0636\u0639\u06cc\u062a\u200c\u0647\u0627\u06cc \u062f\u0631\u0648\u0646\u06cc \u0648 \u062c\u0647\u0627\u0646 \u067e\u06cc\u0631\u0627\u0645\u0648\u0646 \u06af\u0641\u062a\u0647 \u0645\u06cc\u200c\u0634\u0648\u062f. "
            "\u062a\u0639\u0631\u06cc\u0641 \u0648\u0627\u062d\u062f\u06cc \u0645\u0648\u0631\u062f \u062a\u0648\u0627\u0641\u0642 \u0646\u06cc\u0633\u062a\u061b \u0628\u0631\u062e\u06cc \u0646\u0638\u0631\u06cc\u0647\u200c\u0647\u0627 \u0628\u0647 \u062f\u0633\u062a\u0631\u0633\u06cc \u0639\u0645\u0648\u0645\u06cc\u060c \u0645\u062f\u0644 \u0645\u0631\u062a\u0628\u0647\u200c\u0628\u0627\u0644\u0627\u06cc \u062e\u0648\u062f \u06cc\u0627 \u0627\u062f\u063a\u0627\u0645 \u0627\u0637\u0644\u0627\u0639\u0627\u062a \u062a\u0623\u06a9\u06cc\u062f \u0645\u06cc\u200c\u06a9\u0646\u0646\u062f."
        )
        if sources:
            response += (
                f" \u0645\u0646 \u0628\u0631\u0627\u06cc \u0645\u062d\u062f\u0648\u062f\u06a9\u0631\u062f\u0646 \u067e\u0627\u0633\u062e \u0628\u0647 \u0645\u0646\u0627\u0628\u0639 {', '.join(sources[:3])} \u0646\u06af\u0627\u0647 \u06a9\u0631\u062f\u0645\u060c \u0627\u0645\u0627 \u0645\u062a\u0646 \u062e\u0627\u0645 \u0631\u0627 \u06a9\u067e\u06cc \u0646\u06a9\u0631\u062f\u0645."
            )
        return f"{response} \u0627\u0637\u0645\u06cc\u0646\u0627\u0646 \u0641\u0639\u0644\u06cc \u0645\u0646: {awareness.confidence:.2f}."


class ConversationEngine:
    def __init__(self, organism: "DigitalOrganism2500") -> None:
        self.organism = organism
        self.interpreter = ContextualLanguageInterpreter(organism.lexicon)
        self.reasoner = CognitiveReasoner(organism)
        self.backend = LanguageBackend()
        self.turns: Deque[DialogueTurn] = deque(maxlen=1000)
        self.always_research = True
        self.always_reflect = True

    def _context(self, records: Sequence[MemoryRecord], facts: Sequence[WorldFact]) -> str:
        memory_text = "\n".join(
            f"- {record.content[:500]} (confidence={record.confidence:.2f})"
            for record in records[:8]
        )
        fact_text = "\n".join(
            f"- {fact.subject} {fact.predicate} {fact.object[:500]} [{fact.source_title}]"
            for fact in facts[:8]
        )
        return f"MEMORY:\n{memory_text}\n\nRESEARCH:\n{fact_text}"

    def _local_response(
        self,
        interpretation: Mapping[str, Any],
        facts: Sequence[WorldFact],
        imagination: Mapping[str, Any],
        awareness: AwarenessFrame,
    ) -> str:
        intent = str(interpretation.get("intent", "statement"))
        text = str(interpretation.get("text", ""))
        self.reasoner.last_trace = {
            "route": f"special:{intent}",
            "web_used": bool(facts),
            "self_model_checked": True,
        }
        if intent == "greeting":
            return (
                f"\u0633\u0644\u0627\u0645. \u0645\u0646 {self.organism.config.name} \u0647\u0633\u062a\u0645. "
                f"\u062f\u0631 \u0686\u0631\u062e\u0647\u0654 {self.organism.cycle_index} \u0628\u0627 \u062d\u0627\u0641\u0638\u0647\u0654 \u062c\u0627\u0631\u06cc \u0648 "
                "\u0645\u062f\u0644 \u062e\u0648\u062f\u0628\u0627\u0632\u062a\u0627\u0628\u06cc \u0641\u0639\u0627\u0644 \u067e\u0627\u0633\u062e \u0645\u06cc\u200c\u062f\u0647\u0645."
            )
            return (
                f"سلام. من {self.organism.config.name} هستم. "
                f"در چرخهٔ {self.organism.cycle_index} با حافظهٔ جاری و مدل خودبازتابی فعال پاسخ می‌دهم."
            )
        if intent == "self_reflection":
            return self.organism.higher_order_awareness.narrative("fa")
            return self.organism.higher_order_awareness.narrative()
        concept_response = self.reasoner._concept_response(
            text,
            facts,
            awareness,
            not bool(re.search(r"[\u0600-\u06ff]", text)),
        )
        if concept_response:
            return concept_response
        if intent == "identity":
            memories = self.organism.memory.retrieve(text, limit=4)
            return self.reasoner.synthesize(text, interpretation, facts, memories, awareness)
        if intent not in {"greeting", "self_reflection", "imagination"}:
            memories = self.organism.memory.retrieve(text, limit=8)
            return self.reasoner.synthesize(text, interpretation, facts, memories, awareness)
        if intent == "imagination":
            if imagination.get("status") == "traversed":
                return (
                    f"{imagination.get('narrative', '')} "
                    "این کرمچاله در این سامانه یک استعارهٔ محاسباتی برای پیوند دورترین خاطره‌هاست، نه ادعای فیزیکی."
                )
            return "برای تخیل، هنوز خاطرهٔ کافی ندارم؛ چند تجربه یا مفهوم تازه به من بده."
        if facts:
            lines = [
                "برای فهم دقیق‌تر جمله‌ات، پژوهش خواندنی انجام دادم. جمع‌بندی فعلی:",
            ]
            for index, fact in enumerate(facts[:5], 1):
                lines.append(f"{index}. {fact.object[:700]}")
            lines.append(
                f"اطمینان عملی من {awareness.confidence:.2f} است؛ اگر بخواهی، منابع را عمیق‌تر مقایسه می‌کنم."
            )
            return "\n".join(lines)
        memories = self.organism.memory.retrieve(text, limit=4)
        if memories:
            return (
                "از حافظهٔ معنایی و اپیزودیک خود چنین برداشتی دارم:\n"
                + "\n".join(f"- {record.content[:500]}" for record in memories[:4])
            )
        return (
            f"من جمله‌ات را به‌عنوان «{intent}» تفسیر کردم، اما دادهٔ کافی برای پاسخ قطعی ندارم. "
            "می‌توانم آن را به پرسش پژوهشی تبدیل کنم."
        )

    def handle(self, user_text: str, research: Optional[bool] = None) -> DialogueTurn:
        user_text = str(user_text).strip()
        if not user_text:
            return DialogueTurn(
                identifier=uuid.uuid4().hex[:16],
                user_text="",
                response="جمله‌ای دریافت نکردم.",
                intent="empty",
                confidence=0.0,
                research_performed=False,
                facts=[],
                awareness=self.organism.higher_order_awareness.as_dict(),
                imagination={},
            )
        interpretation = self.interpreter.parse(user_text)
        self.organism.quantum_field.superpose(
            list(interpretation["scores"]),
            list(interpretation["scores"].values()),
            context=user_text,
        )
        self.organism.quantum_field.evolve(interpretation["uncertainty"] * -1.0)
        self.organism.quantum_field.entangle(
            interpretation["intent"],
            self.organism.emotions.dominant.value,
            strength=0.35,
        )
        self.organism.tick(
            {
                "scene": user_text,
                "objects": interpretation["entities"][:12],
                "sound": "گفت‌وگوی درونی",
                "amplitude": 0.55,
                "contact": {"texture": "language", "pressure": 0.0, "temperature": 0.5},
                "taste": {"label": "meaning"},
                "smell": {"label": "memory", "intensity": 0.1},
            }
        )
        user_memory = self.organism.memory.remember(
            user_text,
            MemoryKind.EPISODIC,
            salience=0.85,
            emotional_valence=self.organism.emotions.valence,
            confidence=1.0 - interpretation["uncertainty"],
            tags=["dialogue", "user", interpretation["intent"]],
            source="conversation",
        )
        requested_research = self.always_research if research is None else bool(research)
        do_research = bool(
            requested_research
            and interpretation.get("requires_research", False)
            and self.organism.config.internet_enabled
        )
        facts: List[WorldFact] = []
        if do_research:
            facts = self.organism.knowledge.explore(user_text, self.organism.cycle_index)
            self.organism.learning.learn_from_web(facts, self.organism.cycle_index)
        records = self.organism.memory.retrieve(user_text, limit=8)
        imagination: Dict[str, Any] = {}
        if interpretation["intent"] == "imagination":
            imagination = self.organism.micro_wormhole_imagination.traverse(
                user_text,
                self.organism.cycle_index,
            )
        awareness = self.organism.higher_order_awareness.update(
            self.organism,
            user_text,
            interpretation,
            interpretation["uncertainty"]
            if not facts
            else 1.0 - min(fact.confidence for fact in facts),
        )
        context = self._context(records, facts)
        response = None
        local_first = os.environ.get("ORGANISM_LOCAL_FIRST", "1") != "0"
        if local_first:
            response = self._local_response(
                interpretation,
                facts,
                imagination,
                awareness,
            )
        if (
            not response
            and interpretation["intent"]
            not in {"identity", "greeting", "self_reflection", "imagination"}
        ):
            response = self.backend.generate(
                "Understand the user's intent before answering. Respond in the user's language. "
                "Be concise, distinguish evidence from metaphor, and never claim subjective consciousness as a fact.",
                user_text,
                context,
            )
        if not response:
            response = self._local_response(interpretation, facts, imagination, awareness)
        reasoning = dict(self.reasoner.last_trace)
        if response and not reasoning:
            reasoning = {
                "route": "external_language_backend",
                "web_used": bool(facts),
                "self_model_checked": True,
            }
        response_memory = self.organism.memory.remember(
            response,
            MemoryKind.SEMANTIC,
            salience=0.72,
            emotional_valence=self.organism.emotions.valence,
            confidence=awareness.confidence,
            tags=["dialogue", "response", interpretation["intent"]],
            source="conversation",
            links=[fact.source_url for fact in facts[:8] if fact.source_url],
        )
        thought_text = (
            f"ورودی «{user_text[:220]}» را {interpretation['intent']} تشخیص دادم؛ "
            f"پژوهش={'بله' if facts else 'خیر'}؛ "
            f"بازتاب مرتبهٔ بالاتر={awareness.integration:.2f}."
        )
        self.organism.thought_stream.add_fragment(
            thought_text,
            "dialogue-meta",
            awareness.confidence,
            interpretation["uncertainty"],
            awareness.meta.get("self_knowledge", 0.0),
            self.organism.emotions.dominant,
            [user_memory.identifier, response_memory.identifier],
        )
        self.organism.bus.publish(
            InternalEvent(
                SignalType.LANGUAGE,
                "conversation turn integrated",
                {
                    "intent": interpretation["intent"],
                    "research": bool(facts),
                    "response_memory": response_memory.identifier,
                },
                cycle=self.organism.cycle_index,
            )
        )
        turn = DialogueTurn(
            identifier=uuid.uuid4().hex[:16],
            user_text=user_text,
            response=response,
            intent=interpretation["intent"],
            confidence=awareness.confidence,
            research_performed=bool(facts),
            facts=[dataclasses.asdict(fact) for fact in facts[:8]],
            awareness=dataclasses.asdict(awareness),
            imagination=imagination,
            reasoning=reasoning,
        )
        self.turns.append(turn)
        return turn

    def speak(self, text: str) -> bool:
        try:
            import pyttsx3  # type: ignore
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
            return True
        except Exception:
            return False


def attach_dialogue_extensions(organism: "DigitalOrganism2500") -> "DigitalOrganism2500":
    if hasattr(organism, "conversation"):
        return organism
    organism.knowledge = StructuredKnowledgeExplorer(
        organism.web_client,
        organism.memory,
        organism.language,
        organism.bus,
    )
    organism.quantum_field = QuantumInspiredField(
        dimensions=max(32, organism.config.matrix_width // 2),
        seed=organism.seed,
    )
    organism.higher_order_awareness = HigherOrderAwareness(organism.bus)
    organism.micro_wormhole_imagination = MicroWormholeImagination(
        organism.memory,
        organism.graph,
        organism.seed,
    )
    organism.conversation = ConversationEngine(organism)
    return organism


def build_config_from_args(args: argparse.Namespace) -> OrganismConfig:
    """ساخت پیکربندی از آرگومان‌های CLI."""

    config = OrganismConfig(
        name=args.name,
        seed=args.seed,
        persistence_path=args.db,
        snapshot_path=args.snapshot,
        internet_enabled=bool(getattr(args, "internet", False)),
        open_web=bool(getattr(args, "open_web", False)),
        safe_mode=not bool(getattr(args, "unsafe", False)),
    )
    if getattr(args, "domains", None):
        config.allowed_domains = tuple(
            item.strip().lower()
            for item in str(args.domains).split(",")
            if item.strip()
        )
    return config.normalized()


def run_simulation(args: argparse.Namespace) -> int:
    config = build_config_from_args(args)
    organism = DigitalOrganism2500(config)
    world = SyntheticWorld(config.seed)
    try:
        for thought_cycle in organism.run(
            cycles=args.cycles,
            world_provider=lambda: world.next(organism.body),
            realtime=args.realtime,
        ):
            if args.quiet:
                continue
            selected = thought_cycle.selected_action.value if thought_cycle.selected_action else "none"
            print(
                f"چرخه {thought_cycle.cycle_index:04d} | "
                f"خودآگاهی={thought_cycle.consciousness.value:<12} | "
                f"احساس={organism.emotions.dominant.value:<10} | "
                f"عمل={selected:<22} | "
                f"یکپارچگی={thought_cycle.integration_score:.3f}"
            )
            if args.show_thoughts:
                for fragment in thought_cycle.fragments:
                    print(f"  · {fragment.phase}: {fragment.text}")
        if args.save:
            print(f"snapshot: {organism.save_snapshot(args.save)}")
        return 0
    finally:
        organism.close()


def run_dashboard(args: argparse.Namespace) -> int:
    config = build_config_from_args(args)
    organism = DigitalOrganism2500(config)
    world = SyntheticWorld(config.seed)
    stop_event = threading.Event()

    def simulation_loop() -> None:
        try:
            for _ in organism.run(
                cycles=None,
                world_provider=lambda: world.next(organism.body),
                realtime=True,
            ):
                if stop_event.is_set():
                    break
        except Exception:
            LOGGER.exception("simulation loop stopped")

    worker = threading.Thread(
        target=simulation_loop,
        name="organism-simulation",
        daemon=True,
    )
    worker.start()
    try:
        if dash is not None:
            DashboardServer(organism).run(args.host, args.port, args.debug)
        else:
            ObserverFallbackServer(organism).run(args.host, args.port)
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        stop_event.set()
        organism.stop()
        worker.join(timeout=2.0)
        organism.close()


def run_inspect(args: argparse.Namespace) -> int:
    config = build_config_from_args(args)
    organism = DigitalOrganism2500(config)
    try:
        print(to_json(organism.dashboard_snapshot(), indent=2))
        return 0
    finally:
        organism.close()


def run_evolve(args: argparse.Namespace) -> int:
    config = build_config_from_args(args)
    organism = DigitalOrganism2500(config)
    try:
        for _ in range(max(1, args.cycles)):
            organism.tick(SyntheticWorld(config.seed).next(organism.body))
        event = organism.evolve(reason=args.reason)
        print(to_json(event, indent=2))
        if args.save:
            print(f"snapshot: {organism.save_snapshot(args.save)}")
        return 0
    finally:
        organism.close()


def run_export(args: argparse.Namespace) -> int:
    config = build_config_from_args(args)
    organism = DigitalOrganism2500(config)
    try:
        if args.cycles > 0:
            world = SyntheticWorld(config.seed)
            for _ in organism.run(
                cycles=args.cycles,
                world_provider=lambda: world.next(organism.body),
            ):
                pass
        path = organism.save_snapshot(args.output)
        print(path)
        return 0
    finally:
        organism.close()


def run_chat(args: argparse.Namespace) -> int:
    config = build_config_from_args(args)
    organism = attach_dialogue_extensions(DigitalOrganism2500(config))
    print(f"{organism.config.name} آماده است.")
    print("پژوهش وب:", "روشن" if config.internet_enabled else "خاموش")
    print("برای خروج: exit یا quit")
    try:
        while True:
            try:
                user_text = input("\nشما> ").strip()
            except EOFError:
                break
            if user_text.lower() in {"exit", "quit", "خروج", "تمام"}:
                break
            if not user_text:
                continue
            turn = organism.conversation.handle(user_text, research=True)
            print(f"\n{organism.config.name}> {turn.response}")
            if args.trace:
                print(
                    f"\n[intent={turn.intent} confidence={turn.confidence:.2f} "
                    f"research={turn.research_performed} "
                    f"awareness={turn.awareness['integration']:.2f}]"
                )
            if args.tts:
                organism.conversation.speak(turn.response)
        return 0
    finally:
        organism.close()


def run_chat_dashboard(args: argparse.Namespace) -> int:
    config = build_config_from_args(args)
    organism = attach_dialogue_extensions(DigitalOrganism2500(config))
    stop_event = threading.Event()
    world = SyntheticWorld(config.seed)

    def background_loop() -> None:
        try:
            for _ in organism.run(
                cycles=None,
                world_provider=lambda: world.next(organism.body),
                realtime=True,
            ):
                if stop_event.is_set():
                    break
        except Exception:
            LOGGER.exception("chat dashboard background loop stopped")

    worker = threading.Thread(
        target=background_loop,
        name="organism-chat-background",
        daemon=True,
    )
    worker.start()
    try:
        if dash is None:
            raise RuntimeError("برای chat-dashboard باید Dash نصب باشد.")
        ChatDashboardServer(organism).run(args.host, args.port, args.debug)
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        stop_event.set()
        organism.stop()
        worker.join(timeout=2.0)
        organism.close()


def run_self_check() -> int:
    """خودآزمایی سریع برای صحت اجزای کلیدی."""

    temporary = tempfile.NamedTemporaryFile(
        prefix="organism2500_",
        suffix=".sqlite3",
        delete=False,
    )
    temporary.close()
    config = OrganismConfig(
        name="self-check",
        seed=17,
        persistence_path=temporary.name,
        snapshot_path=temporary.name + ".json",
        internet_enabled=False,
        active_neuron_budget=512,
    )
    organism = DigitalOrganism2500(config)
    errors: List[str] = []
    try:
        if len(fibonacci_binary_stream(64)) != 64:
            errors.append("fibonacci stream length")
        vector = BitVector.from_bits([0, 1, 1, 0, 1])
        if vector.count() != 3 or vector.rotate(1).count() != 3:
            errors.append("bit vector")
        if organism.genome.generation != 0:
            errors.append("genome generation")
        cycles = list(
            organism.run(
                cycles=3,
                world_provider=lambda: SyntheticWorld(config.seed).next(organism.body),
            )
        )
        if len(cycles) != 3:
            errors.append("cycle count")
        if organism.metrics.observations < 3:
            errors.append("observation count")
        if organism.memory.counts()[MemoryKind.EPISODIC.value] < 1:
            errors.append("episodic memory")
        snapshot = organism.dashboard_snapshot()
        if snapshot.cycle != 3:
            errors.append("snapshot cycle")
        attach_dialogue_extensions(organism)
        turn = organism.conversation.handle("hello", research=False)
        if turn.intent != "greeting" or not turn.response:
            errors.append("dialogue greeting")
        identity = organism.conversation.handle("how old are you?", research=True)
        if (
            identity.intent != "identity"
            or identity.research_performed
            or "human age" not in identity.response.lower()
        ):
            errors.append("self-model identity route")
        unknown = organism.conversation.handle("What is photosynthesis?", research=True)
        if (
            unknown.research_performed
            or "What is photosynthesis?" in unknown.response
            or "photosynthesis |" in unknown.response
        ):
            errors.append("no-web evidence boundary")
        imagined = organism.conversation.handle("imagine a bridge between memory and time", research=False)
        if not imagined.imagination:
            errors.append("wormhole imagination")
        if dash is not None:
            app = ChatDashboardServer(organism).create_app()
            if not app.callback_map:
                errors.append("chat dashboard callback")
        saved = organism.save_snapshot(config.snapshot_path)
        if not Path(saved).exists():
            errors.append("snapshot file")
    except Exception:
        errors.append(traceback.format_exc())
    finally:
        organism.close()
        for path in (temporary.name, temporary.name + "-wal", temporary.name + "-shm", temporary.name + ".json"):
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass
    if errors:
        print("SELF-CHECK FAILED")
        for error in errors:
            print(error)
        return 1
    print("SELF-CHECK OK")
    return 0


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="digital_organism_2500.py",
        description="شبیه‌ساز پژوهشی ارگانیسم دیجیتال ۲۵۰۰",
    )
    parser.add_argument("--version", action="version", version="Digital Organism 2500 1.0")
    # اجرای بدون آرگومان از main یک فرمان پیش‌فرض دریافت می‌کند؛
    # required=False اجازه می‌دهد فایل مستقیماً در IDE یا با دوبارکلیک اجرا شود.
    sub = parser.add_subparsers(dest="command", required=False)

    simulate = sub.add_parser("simulate", help="اجرای چرخه‌های آفلاین/خواندنی")
    simulate.add_argument("--cycles", type=int, default=10)
    simulate.add_argument("--seed", type=int, default=DEFAULT_SEED)
    simulate.add_argument("--name", default="آرگانون-۲۵۰۰")
    simulate.add_argument("--db", default="organism_2500.sqlite3")
    simulate.add_argument("--snapshot", default="organism_2500_snapshot.json")
    simulate.add_argument("--save", default="")
    simulate.add_argument("--realtime", action="store_true")
    simulate.add_argument("--quiet", action="store_true")
    simulate.add_argument("--show-thoughts", action="store_true")
    simulate.add_argument("--internet", action="store_true")
    simulate.add_argument("--open-web", action="store_true")
    simulate.add_argument("--unsafe", action="store_true")
    simulate.add_argument("--domains", default="")
    simulate.set_defaults(func=run_simulation)

    dashboard = sub.add_parser("dashboard", help="اجرای داش محلی مشاهده")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8050)
    dashboard.add_argument("--debug", action="store_true")
    dashboard.add_argument("--seed", type=int, default=DEFAULT_SEED)
    dashboard.add_argument("--name", default="آرگانون-۲۵۰۰")
    dashboard.add_argument("--db", default="organism_2500.sqlite3")
    dashboard.add_argument("--snapshot", default="organism_2500_snapshot.json")
    dashboard.add_argument("--internet", action="store_true")
    dashboard.add_argument("--open-web", action="store_true")
    dashboard.add_argument("--unsafe", action="store_true")
    dashboard.add_argument("--domains", default="")
    dashboard.set_defaults(func=run_dashboard)

    inspect = sub.add_parser("inspect", help="نمایش وضعیت اولیه به JSON")
    inspect.add_argument("--seed", type=int, default=DEFAULT_SEED)
    inspect.add_argument("--name", default="آرگانون-۲۵۰۰")
    inspect.add_argument("--db", default="organism_2500.sqlite3")
    inspect.add_argument("--snapshot", default="organism_2500_snapshot.json")
    inspect.add_argument("--internet", action="store_true")
    inspect.add_argument("--open-web", action="store_true")
    inspect.add_argument("--unsafe", action="store_true")
    inspect.add_argument("--domains", default="")
    inspect.set_defaults(func=run_inspect)

    evolve = sub.add_parser("evolve", help="اجرای چرخه و یک جهش تکاملی")
    evolve.add_argument("--cycles", type=int, default=8)
    evolve.add_argument("--reason", default="adaptive exploration")
    evolve.add_argument("--seed", type=int, default=DEFAULT_SEED)
    evolve.add_argument("--name", default="آرگانون-۲۵۰۰")
    evolve.add_argument("--db", default="organism_2500.sqlite3")
    evolve.add_argument("--snapshot", default="organism_2500_snapshot.json")
    evolve.add_argument("--save", default="")
    evolve.add_argument("--internet", action="store_true")
    evolve.add_argument("--open-web", action="store_true")
    evolve.add_argument("--unsafe", action="store_true")
    evolve.add_argument("--domains", default="")
    evolve.set_defaults(func=run_evolve)

    export = sub.add_parser("export", help="اجرای چرخه و صدور snapshot")
    export.add_argument("--cycles", type=int, default=5)
    export.add_argument("--output", default="organism_2500_snapshot.json")
    export.add_argument("--seed", type=int, default=DEFAULT_SEED)
    export.add_argument("--name", default="آرگانون-۲۵۰۰")
    export.add_argument("--db", default="organism_2500.sqlite3")
    export.add_argument("--snapshot", default="organism_2500_snapshot.json")
    export.add_argument("--internet", action="store_true")
    export.add_argument("--open-web", action="store_true")
    export.add_argument("--unsafe", action="store_true")
    export.add_argument("--domains", default="")
    export.set_defaults(func=run_export)

    chat = sub.add_parser("chat", help="interactive dialogue with research and self-reflection")
    chat.add_argument("--seed", type=int, default=DEFAULT_SEED)
    chat.add_argument("--name", default="آرگانون-۲۵۰۰")
    chat.add_argument("--db", default="organism_2500.sqlite3")
    chat.add_argument("--snapshot", default="organism_2500_snapshot.json")
    chat.add_argument("--internet", action="store_true")
    chat.add_argument("--open-web", action="store_true")
    chat.add_argument("--unsafe", action="store_true")
    chat.add_argument("--domains", default="")
    chat.add_argument("--trace", action="store_true")
    chat.add_argument("--tts", action="store_true")
    chat.set_defaults(func=run_chat)

    chat_dashboard = sub.add_parser("chat-dashboard", help="Dash web chat with cognition telemetry")
    chat_dashboard.add_argument("--host", default="127.0.0.1")
    chat_dashboard.add_argument("--port", type=int, default=8051)
    chat_dashboard.add_argument("--debug", action="store_true")
    chat_dashboard.add_argument("--seed", type=int, default=DEFAULT_SEED)
    chat_dashboard.add_argument("--name", default="آرگانون-۲۵۰۰")
    chat_dashboard.add_argument("--db", default="organism_2500.sqlite3")
    chat_dashboard.add_argument("--snapshot", default="organism_2500_snapshot.json")
    chat_dashboard.add_argument("--internet", action="store_true")
    chat_dashboard.add_argument("--open-web", action="store_true")
    chat_dashboard.add_argument("--unsafe", action="store_true")
    chat_dashboard.add_argument("--domains", default="")
    chat_dashboard.set_defaults(func=run_chat_dashboard)

    check = sub.add_parser("self-check", help="خودآزمایی هسته")
    check.set_defaults(func=lambda _: run_self_check())
    return parser


def _default_launch_arguments() -> List[str]:
    """آرگومان‌های اجرای دوستانهٔ فایل با دوبارکلیک یا Run در IDE."""

    return [
        "simulate",
        "--cycles",
        os.environ.get("ORGANISM_DEFAULT_CYCLES", "8"),
    ]


def _pause_after_default_launch() -> None:
    """جلوگیری از بسته‌شدن فوری پنجرهٔ کنسول در اجرای مستقیم ویندوز."""

    if os.environ.get("ORGANISM_NO_PAUSE") == "1":
        return
    try:
        input("\nاجرا تمام شد. برای بستن این پنجره Enter را فشار دهید...")
    except (EOFError, KeyboardInterrupt):
        pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    # کنسول‌های ویندوزی گاهی cp1252/cp850 هستند؛ خروجی فارسی را UTF-8 نگه می‌داریم.
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = create_parser()
    supplied = list(argv) if argv is not None else list(sys.argv[1:])
    default_launch = len(supplied) == 0
    parse_arguments = _default_launch_arguments() if default_launch else supplied
    args = parser.parse_args(parse_arguments)
    try:
        result = int(args.func(args))
        if default_launch:
            _pause_after_default_launch()
        return result
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        LOGGER.error("fatal error: %s", exc)
        if os.environ.get("ORGANISM_DEBUG"):
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
