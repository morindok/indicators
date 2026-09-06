import os
import re
import time
import math
import random
import sqlite3
import platform
import threading
import statistics
import hashlib
import urllib.parse
from collections import deque
from datetime import datetime

try:
    import psutil
except Exception:
    psutil = None

try:
    import requests
    REQUESTS_AVAILABLE = True
except Exception:
    REQUESTS_AVAILABLE = False

from dash import Dash, dcc, html, Input, Output, State, no_update
import plotly.graph_objects as go


# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------
NEED_NAMES = {
    "energy": "انرژی",
    "thermal": "خنک‌سازی",
    "memory": "حافظه",
    "entropy_order": "نظم آنتروپی",
    "time_sync": "همگامی زمان",
    "security": "امنیت",
}
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


def now_hms():
    return datetime.now().strftime("%H:%M:%S")


def normalize_text(s):
    if not s:
        return ""
    s = str(s)
    s = s.replace("\u200c", "")  # نیم‌فاصله
    s = s.replace("ي", "ی")
    s = s.replace("ك", "ک")
    s = s.replace("ة", "ه")
    s = s.replace("أ", "ا")
    s = s.replace("إ", "ا")
    s = s.replace("آ", "ا")
    s = s.lower()
    return s


TOKEN_RE = re.compile(
    r"[\u0600-\u06FF\uFB50-\uFDFF\uFB8A-\uFBFF\u0750-\u077Fa-zA-Z0-9]{1,}",
    re.UNICODE
)

SENT_SPLIT_RE = re.compile(r"[.!?؟؛\n]+")


def tokenize(s):
    try:
        return TOKEN_RE.findall(normalize_text(s))
    except Exception:
        return []


def split_sentences(text):
    try:
        parts = SENT_SPLIT_RE.split(str(text))
        out = []
        for p in parts:
            p = p.strip()
            if len(p) >= 3:
                out.append(p[:600])
        return out[:15]
    except Exception:
        return []


def weighted_choice(rng, items, weights, temperature=1.0):
    try:
        if not items:
            return None
        temp = max(0.2, float(temperature))
        adj = []
        for w in weights:
            w = max(0.001, float(w))
            adj.append(w ** (1.0 / temp))
        total = sum(adj)
        if total <= 0:
            return rng.choice(items)
        r = rng.random() * total
        acc = 0.0
        for item, w in zip(items, adj):
            acc += w
            if r <= acc:
                return item
        return items[-1]
    except Exception:
        return items[0] if items else None


# ------------------------------------------------------------
# Persian POS heuristics
# ------------------------------------------------------------

PRONOUNS = {
    "من", "تو", "او", "ما", "شما", "آنها", "ایشان", "وی",
    "این", "آن", "خود", "همین", "همان"
}

PREPOSITIONS = {
    "در", "به", "از", "با", "بر", "برای", "تا", "چون",
    "روی", "زیر", "میان", "بین", "داخل", "خارج", "نزد", "سو", "بی"
}

CONJUNCTIONS = {
    "و", "که", "اما", "ولی", "اگر", "زیرا", "یا", "پس", "چون", "تا"
}

FUNC_WORDS = {
    "و", "که", "را", "نیز", "هم", "ای", "های", "ها",
    "یک", "هر", "این", "آن", "یا", "اما", "ولی", "اگر",
    "چون", "زیرا", "پس", "تا", "بی", "با", "در", "به",
    "از", "بر", "برای", "روی", "زیر", "میان", "بین",
    "داخل", "خارج", "نزد", "سو"
}

DETERMINERS = {
    "یک", "هر", "چند", "این", "آن", "همین", "همان"
}

VERB_WORDS = {
    "است", "بود", "شد", "شده", "شود", "میشود", "نشده",
    "دارد", "داشت", "دارند", "ندارد", "داشتند",
    "میکند", "کرد", "کرده", "میکنند", "کردند", "نکرد",
    "میرود", "رفت", "رفته", "رفتند", "نرفت",
    "آمد", "آمده", "میاید", "آمدند", "نیامد",
    "گفت", "گفته", "میگوید", "گفتند", "نگفت",
    "دید", "دیده", "میبیند", "دیدند", "ندید",
    "دانست", "دانسته", "میداند", "نمیداند", "دانستند",
    "خواست", "خواسته", "میخواهد", "خواستند", "نخواست",
    "توانست", "میتواند", "نمیتواند", "توانستند",
    "شدن", "کردن", "بودن", "گفتن", "دیدن", "آمدن",
    "رفتن", "دانستن", "خواستن", "توانستن",
    "باید", "شاید", "نباید", "خواهد", "هست", "نیست"
}

ADJ_WORDS = {
    "بزرگ", "کوچک", "زیبا", "زشت", "خوب", "بد", "سرد", "گرم",
    "روشن", "تاریک", "ابی", "آبی", "سبز", "قرمز", "زرد",
    "سفید", "سیاه", "بلند", "کوتاه", "عمیق", "تند", "اهسته",
    "آهسته", "شیرین", "تلخ", "تازه", "کهنه", "نرم", "زبر",
    "ارام", "آرام", "خشمگین", "غمگین", "شاد", "امیدوار",
    "ترسناک", "مقدس", "ساده", "پیچیده", "زنده", "مرده",
    "ازاد", "آزاد", "بیدار", "خوابیده", "روشن", "خاموش"
}

POSITIVE_WORDS = {
    "زیبا", "خوب", "عشق", "امید", "روشن", "صلح", "دوست",
    "جان", "نور", "بهشت", "شادی", "آرام", "آزادی", "زندگی",
    "مهربان", "دانش", "خرد", "سپیده", "گل", "بهار"
}

NEGATIVE_WORDS = {
    "غم", "درد", "مرگ", "تاریک", "جنگ", "دشمن", "خون",
    "شب", "سخت", "ترس", "رنج", "زندان", "سقوط", "ویران",
    "خاموش", "تنهایی", "فقر", "دردمند"
}

NOUN_SUFFIXES = (
    "ها", "های", "ی", "ات", "مان", "تان", "شان",
    "گاه", "ستان", "مند", "کار", "بار", "زار", "دان", "سار"
)

VERB_PREFIXES = ("می", "نمی", "ب", "بر")


def is_verb(t):
    t = normalize_text(t)
    if t in VERB_WORDS:
        return True
    if t.startswith(VERB_PREFIXES):
        return True
    if t.endswith(("کرد", "شد", "بود", "داشت", "گفت", "دید", "رفت", "آمد", "دانست", "خواست", "توانست")):
        return True
    return False


def is_adjective(t):
    t = normalize_text(t)
    if t in ADJ_WORDS:
        return True
    if t.endswith(("تر", "ترین")):
        return True
    return False


def is_noun_by_suffix(t):
    t = normalize_text(t)
    for suf in NOUN_SUFFIXES:
        if t.endswith(suf):
            return True
    return False


def sentiment_word(t):
    t = normalize_text(t)
    if t in POSITIVE_WORDS:
        return 0.6
    if t in NEGATIVE_WORDS:
        return -0.6
    return 0.0


def infer_pos(tokens):
    pos = []
    for i, tok in enumerate(tokens):
        tok_n = normalize_text(tok)

        if tok_n in PRONOUNS:
            p = "PRON"
        elif tok_n in PREPOSITIONS:
            p = "PREP"
        elif tok_n in CONJUNCTIONS:
            p = "CONJ"
        elif tok_n in FUNC_WORDS:
            p = "FUNC"
        elif is_verb(tok_n):
            p = "VERB"
        elif is_adjective(tok_n):
            p = "ADJ"
        elif is_noun_by_suffix(tok_n):
            p = "NOUN"
        elif tok_n.isdigit():
            p = "NUM"
        else:
            p = "NOUN"

        # Context corrections
        if i > 0:
            prev = pos[-1]
            if prev == "PREP" and p in ("NOUN", "ADJ", "UNK"):
                p = "NOUN"
            if prev == "PRON" and p == "NOUN" and is_verb(tok_n):
                p = "VERB"

        pos.append(p)

    return pos


# ------------------------------------------------------------
# Hardware
# ------------------------------------------------------------

def detect_gpu():
    gpu = {
        "available": False,
        "name": "GPU در دسترس نیست",
        "units": 0,
        "mem_mb": 0,
        "cores": 0,
    }

    try:
        import pynvml
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        if count and count > 0:
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(h)
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="ignore")
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            gpu.update(
                available=True,
                name=name,
                units=int(count),
                mem_mb=int(mem.total / 1048576),
                cores=0,
            )
            return gpu
    except Exception:
        pass

    return gpu


def detect_hardware():
    return {
        "platform": platform.platform(),
        "cpu_logical": os.cpu_count() or 4,
        "gpu": detect_gpu(),
    }


def compute_neuron_capacity(hw):
    cpu_neurons = hw["cpu_logical"] * 2048
    gpu = hw["gpu"]

    if gpu["available"]:
        gpu_neurons = gpu["units"] * max(32768, int(gpu["mem_mb"] * 4))
    else:
        gpu_neurons = 0

    return int(clamp(cpu_neurons + gpu_neurons, 4096, 6_000_000))


def read_metrics():
    m = {
        "cpu_total": 20.0,
        "cpu_per_core": [20.0],
        "mem": 40.0,
        "temp_norm": 0.35,
        "battery": 100.0,
    }

    if psutil is not None:
        try:
            m["cpu_total"] = psutil.cpu_percent(interval=None)
            per = psutil.cpu_percent(percpu=True)
            m["cpu_per_core"] = per if per else [m["cpu_total"]]
            m["mem"] = psutil.virtual_memory().percent

            temp_raw = None
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    vals = []
                    for entries in temps.values():
                        for e in entries:
                            vals.append(e.current)
                    if vals:
                        temp_raw = max(vals)
            except Exception:
                temp_raw = None

            if temp_raw is None:
                temp_raw = 35 + m["cpu_total"] * 0.35

            m["temp_norm"] = clamp((temp_raw - 30) / 55, 0, 1)

            try:
                bat = psutil.sensors_battery()
                if bat:
                    m["battery"] = bat.percent
            except Exception:
                m["battery"] = 100
        except Exception:
            pass

    return m


if psutil is not None:
    try:
        psutil.cpu_percent(interval=0.1)
        psutil.cpu_percent(percpu=True)
    except Exception:
        pass


# ------------------------------------------------------------
# Fibonacci Heart
# ------------------------------------------------------------

class FibonacciHeart:
    def __init__(self):
        self.a = 0
        self.b = 1
        self.mask = (1 << 64) - 1
        self.bit_queue = deque(maxlen=2048)
        self.bits = deque(maxlen=512)
        self.beat_times = deque(maxlen=80)
        self.ecg = deque(maxlen=1200)
        self.ecg_x = deque(maxlen=1200)
        self.sample_i = 0

    def _next_word(self):
        self.a, self.b = self.b, (self.a + self.b) & self.mask
        return self.a

    def _refill(self, needed):
        while len(self.bit_queue) < needed:
            word = self._next_word()
            for shift in range(63, -1, -1):
                self.bit_queue.append((word >> shift) & 1)

    def consume(self, n_bits):
        try:
            n_bits = max(1, int(n_bits))
            self._refill(n_bits)
            consumed = []
            now = time.time()

            for _ in range(n_bits):
                bit = self.bit_queue.popleft()
                consumed.append(bit)
                self.bits.append(bit)

                if bit == 1:
                    self.beat_times.append(now)
                    self._append_spike()
                else:
                    self._append_baseline(4)

            return consumed
        except Exception:
            return []

    def feed_symbol_bits(self, text):
        try:
            h = hashlib.sha256(normalize_text(text).encode("utf-8")).digest()
            bits = []
            for byte in h[:5]:
                for shift in range(7, -1, -1):
                    bits.append((byte >> shift) & 1)
            for b in bits:
                self.bit_queue.append(int(b) & 1)
        except Exception:
            pass

    def _append_baseline(self, n):
        for _ in range(n):
            self.sample_i += 1
            self.ecg_x.append(self.sample_i)
            self.ecg.append(random.uniform(-0.03, 0.03))

    def _append_spike(self):
        wave = [0.08, 0.12, -0.10, 1.0, -0.55, 0.05, 0.16, 0.22, 0.12, 0.02, -0.02, 0.0]
        for amp in wave:
            self.sample_i += 1
            self.ecg_x.append(self.sample_i)
            self.ecg.append(amp + random.uniform(-0.02, 0.02))
        self._append_baseline(3)

    def heart_rate(self):
        try:
            now = time.time()
            recent = [t for t in self.beat_times if now - t <= 12]
            if len(recent) >= 3:
                intervals = [recent[i + 1] - recent[i] for i in range(len(recent) - 1)]
                avg = sum(intervals) / len(intervals)
                if avg > 0:
                    return clamp(60 / avg, 0, 220)
        except Exception:
            pass
        return 0

    def coherence(self):
        try:
            now = time.time()
            recent = [t for t in self.beat_times if now - t <= 12]
            if len(recent) < 4:
                return 50.0
            intervals = [recent[i + 1] - recent[i] for i in range(len(recent) - 1)]
            mean = sum(intervals) / len(intervals)
            if mean <= 0:
                return 50.0
            var = sum((x - mean) ** 2 for x in intervals) / len(intervals)
            cv = math.sqrt(var) / mean
            return clamp(1 - cv * 2, 0, 1) * 100
        except Exception:
            return 50.0

    def ones_density(self):
        try:
            if not self.bits:
                return 0.5
            return sum(self.bits) / len(self.bits)
        except Exception:
            return 0.5


# ------------------------------------------------------------
# Sensors
# ------------------------------------------------------------

class SensorBank:
    def __init__(self, n=600):
        self.n = n
        self.values = [0.0] * n
        self.anomaly_count = 0
        self.load = 0.0
        self.entropy = 0.5

    def update(self, base, t, rng):
        try:
            L = len(base)
            if L == 0:
                base = [0.5]
                L = 1

            anomalies = 0
            vals = self.values

            for i in range(self.n):
                b = base[i % L]
                k = i & 7

                if k == 0:
                    v = b
                elif k == 1:
                    v = b * 0.85 + 0.15 * (0.5 + 0.5 * math.sin(t * 0.11 + i * 0.53))
                elif k == 2:
                    v = abs(math.sin((b + 0.001) * math.pi * 2 + t * 0.07 + i))
                elif k == 3:
                    v = clamp(b + rng.uniform(-0.08, 0.08))
                elif k == 4:
                    v = 1.0 - b
                elif k == 5:
                    v = (b + base[(i + 13) % L]) * 0.5
                elif k == 6:
                    pseudo = ((i * 2654435761 + int(t * 1000)) % 997) / 997
                    v = clamp(b * 0.7 + pseudo * 0.3)
                else:
                    v = clamp(0.5 * b + 0.5 * math.tanh(3 * b - 1.5))

                v = clamp(v)
                vals[i] = v

                if v > 0.95 or v < 0.02:
                    anomalies += 1

            self.anomaly_count = anomalies
            self.load = sum(vals) / self.n
            self.entropy = self._entropy(vals)
        except Exception:
            self.anomaly_count = 0
            self.load = 0.3
            self.entropy = 0.5

    def _entropy(self, vals):
        bins = [0] * 12
        for v in vals:
            bins[min(11, int(v * 12))] += 1

        ent = 0.0
        for c in bins:
            if c > 0:
                p = c / self.n
                ent -= p * math.log2(p)

        return ent / math.log2(12)


# ------------------------------------------------------------
# Genome
# ------------------------------------------------------------

GENE_NAMES = [
    "curiosity", "language", "memory", "imagination", "syntax", "semantics",
    "phonology", "abstraction", "pattern", "rhythm", "math", "geometry",
    "spacetime", "time", "sensory_integration", "attention", "emotion_balance",
    "empathy", "courage", "caution", "exploration", "exploitation",
    "homeostasis", "energy", "thermal", "immune", "io", "security",
    "prediction", "learning", "plasticity", "working_memory", "long_term_memory",
    "association", "symbol_grounding", "metacognition", "reasoning",
    "inhibition", "flexibility", "novelty", "reward", "salience",
    "arousal_regulation", "sleep", "dreaming", "social", "communication", "speech",
    "literature", "poetry", "metaphor", "rhyme", "meter",
    "visual_imagination", "color_perception", "pattern_recognition",
    "abstract_thinking", "synesthesia", "aesthetic_sense", "spatial_art",
    "dimensional_vision", "fractal_perception", "harmony", "contrast",
    "fourth_dimension", "non_linear_thinking", "cosmic_consciousness",
    "self_remembering", "divided_attention", "intuition", "growth_drive"
]


class Genome:
    def __init__(self):
        self.rng = random.Random(int(time.time() * 1000))
        self.genes = {}

        for name in GENE_NAMES:
            self.genes[name] = {
                "expr": self.rng.uniform(0.35, 0.95),
                "phase": self.rng.uniform(0, 2 * math.pi),
                "mut": self.rng.uniform(0.008, 0.04),
            }

        important = [
            "curiosity", "language", "memory", "imagination", "learning",
            "syntax", "semantics", "communication", "speech", "literature",
            "visual_imagination", "intuition", "growth_drive", "pattern_recognition"
        ]

        for g in important:
            if g in self.genes:
                self.genes[g]["expr"] = self.rng.uniform(0.90, 0.99)

    def get(self, name):
        try:
            return self.genes.get(name, {}).get("expr", 0.5)
        except Exception:
            return 0.5

    def regulate(self, need_avg, stress, arousal, tick):
        try:
            names = list(self.genes.keys())
            for i, name in enumerate(names):
                g = self.genes[name]
                base = g["expr"]
                wave = 0.03 * math.sin(tick * 0.07 + g["phase"])
                drift = self.rng.uniform(-g["mut"], g["mut"])

                env = 0.0
                if name in ("curiosity", "exploration", "novelty", "growth_drive"):
                    env = 0.05 * arousal
                elif name in ("language", "speech", "communication", "syntax", "semantics"):
                    env = 0.05 * arousal + 0.02 * self.get("memory")
                elif name in ("imagination", "visual_imagination"):
                    env = 0.04 * arousal + 0.02 * self.get("memory")
                elif name in ("intuition", "self_remembering"):
                    env = 0.03 * (1 - stress) + 0.02 * arousal

                neighbor = self.genes[names[(i + 7) % len(names)]]["expr"]
                coupling = 0.01 * (neighbor - base)

                g["expr"] = clamp(base + wave + drift + env + coupling, 0.08, 1.0)
        except Exception:
            pass

    def profile(self, n=12):
        try:
            items = [(k, v["expr"]) for k, v in self.genes.items()]
            items.sort(key=lambda x: x[1], reverse=True)
            return items[:n]
        except Exception:
            return []


# ------------------------------------------------------------
# Memory DB with language learning
# ------------------------------------------------------------

class MemoryDB:
    def __init__(self, path="growing_organism.db"):
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False, timeout=15)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        try:
            with self.lock:
                cur = self.conn.cursor()

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS lexicon (
                        token TEXT PRIMARY KEY,
                        freq REAL DEFAULT 1,
                        pos TEXT DEFAULT 'NOUN',
                        noun REAL DEFAULT 0.1,
                        verb REAL DEFAULT 0.1,
                        adj REAL DEFAULT 0.1,
                        func REAL DEFAULT 0.1,
                        valence REAL DEFAULT 0,
                        arousal REAL DEFAULT 0.3,
                        last_seen REAL
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS bigrams (
                        prev TEXT,
                        next TEXT,
                        weight REAL DEFAULT 1,
                        PRIMARY KEY (prev, next)
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trigrams (
                        prev2 TEXT,
                        prev1 TEXT,
                        next TEXT,
                        weight REAL DEFAULT 1,
                        PRIMARY KEY (prev2, prev1, next)
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS templates (
                        pattern TEXT PRIMARY KEY,
                        freq REAL DEFAULT 1,
                        example TEXT
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sentences (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        text TEXT,
                        source TEXT,
                        score REAL DEFAULT 0,
                        ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS inner_dialogues (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        speaker TEXT,
                        text TEXT,
                        context TEXT,
                        ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS visualizations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        concept TEXT,
                        point_count INTEGER,
                        pattern TEXT,
                        ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                self.conn.commit()
        except Exception:
            pass

    # ---------- lexicon ----------

    def upsert_word(self, token, pos, scores, valence, arousal):
        try:
            token = normalize_text(token)
            if not token:
                return

            with self.lock:
                cur = self.conn.cursor()
                row = cur.execute(
                    "SELECT freq, noun, verb, adj, func, valence, arousal, pos FROM lexicon WHERE token=?",
                    (token,)
                ).fetchone()

                now = time.time()

                if row:
                    new_freq = row["freq"] + 1
                    new_noun = 0.75 * row["noun"] + 0.25 * scores.get("noun", 0.1)
                    new_verb = 0.75 * row["verb"] + 0.25 * scores.get("verb", 0.1)
                    new_adj = 0.75 * row["adj"] + 0.25 * scores.get("adj", 0.1)
                    new_func = 0.75 * row["func"] + 0.25 * scores.get("func", 0.1)
                    new_valence = 0.8 * row["valence"] + 0.2 * valence
                    new_arousal = 0.8 * row["arousal"] + 0.2 * arousal

                    new_pos = pos if pos in ("NOUN", "VERB", "ADJ", "FUNC", "PREP", "PRON", "CONJ", "NUM") else row["pos"]

                    cur.execute(
                        """
                        UPDATE lexicon
                        SET freq=?, pos=?, noun=?, verb=?, adj=?, func=?, valence=?, arousal=?, last_seen=?
                        WHERE token=?
                        """,
                        (
                            new_freq, new_pos, new_noun, new_verb, new_adj, new_func,
                            new_valence, new_arousal, now, token
                        )
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO lexicon(token, freq, pos, noun, verb, adj, func, valence, arousal, last_seen)
                        VALUES(?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            token, 1.0, pos,
                            scores.get("noun", 0.1),
                            scores.get("verb", 0.1),
                            scores.get("adj", 0.1),
                            scores.get("func", 0.1),
                            valence, arousal, now
                        )
                    )

                self.conn.commit()
        except Exception:
            pass

    def get_word(self, token):
        try:
            token = normalize_text(token)
            with self.lock:
                row = self.conn.execute("SELECT * FROM lexicon WHERE token=?", (token,)).fetchone()
                return dict(row) if row else None
        except Exception:
            return None

    def words_by_pos(self, pos, limit=50):
        try:
            with self.lock:
                rows = self.conn.execute(
                    "SELECT token FROM lexicon WHERE pos=? ORDER BY freq DESC LIMIT ?",
                    (pos, limit)
                ).fetchall()
                return [r["token"] for r in rows]
        except Exception:
            return []

    def random_word_by_pos(self, pos):
        try:
            with self.lock:
                row = self.conn.execute(
                    "SELECT token FROM lexicon WHERE pos=? ORDER BY RANDOM() LIMIT 1",
                    (pos,)
                ).fetchone()
                return row["token"] if row else None
        except Exception:
            return None

    def random_word(self):
        try:
            with self.lock:
                row = self.conn.execute("SELECT token FROM lexicon ORDER BY RANDOM() LIMIT 1").fetchone()
                return row["token"] if row else None
        except Exception:
            return None

    def top_words(self, limit=20):
        try:
            with self.lock:
                rows = self.conn.execute(
                    "SELECT token FROM lexicon ORDER BY freq DESC LIMIT ?",
                    (limit,)
                ).fetchall()
                return [r["token"] for r in rows]
        except Exception:
            return []

    # ---------- n-grams ----------

    def add_bigram(self, prev, next_tok, w=1.0):
        try:
            prev = normalize_text(prev)
            next_tok = normalize_text(next_tok)
            if not prev or not next_tok:
                return

            with self.lock:
                cur = self.conn.cursor()
                row = cur.execute(
                    "SELECT weight FROM bigrams WHERE prev=? AND next=?",
                    (prev, next_tok)
                ).fetchone()

                if row:
                    cur.execute(
                        "UPDATE bigrams SET weight=? WHERE prev=? AND next=?",
                        (min(100.0, row["weight"] + w), prev, next_tok)
                    )
                else:
                    cur.execute(
                        "INSERT INTO bigrams(prev, next, weight) VALUES(?,?,?)",
                        (prev, next_tok, w)
                    )

                self.conn.commit()
        except Exception:
            pass

    def add_trigram(self, prev2, prev1, next_tok, w=1.0):
        try:
            prev2 = normalize_text(prev2)
            prev1 = normalize_text(prev1)
            next_tok = normalize_text(next_tok)
            if not prev2 or not prev1 or not next_tok:
                return

            with self.lock:
                cur = self.conn.cursor()
                row = cur.execute(
                    "SELECT weight FROM trigrams WHERE prev2=? AND prev1=? AND next=?",
                    (prev2, prev1, next_tok)
                ).fetchone()

                if row:
                    cur.execute(
                        "UPDATE trigrams SET weight=? WHERE prev2=? AND prev1=? AND next=?",
                        (min(100.0, row["weight"] + w), prev2, prev1, next_tok)
                    )
                else:
                    cur.execute(
                        "INSERT INTO trigrams(prev2, prev1, next, weight) VALUES(?,?,?,?)",
                        (prev2, prev1, next_tok, w)
                    )

                self.conn.commit()
        except Exception:
            pass

    def get_bigram_weight(self, prev, next_tok):
        try:
            prev = normalize_text(prev)
            next_tok = normalize_text(next_tok)
            with self.lock:
                row = self.conn.execute(
                    "SELECT weight FROM bigrams WHERE prev=? AND next=?",
                    (prev, next_tok)
                ).fetchone()
                return row["weight"] if row else 0.0
        except Exception:
            return 0.0

    def get_trigram_weight(self, prev2, prev1, next_tok):
        try:
            prev2 = normalize_text(prev2)
            prev1 = normalize_text(prev1)
            next_tok = normalize_text(next_tok)
            with self.lock:
                row = self.conn.execute(
                    "SELECT weight FROM trigrams WHERE prev2=? AND prev1=? AND next=?",
                    (prev2, prev1, next_tok)
                ).fetchone()
                return row["weight"] if row else 0.0
        except Exception:
            return 0.0

    def bigram_candidates(self, prev, limit=20):
        try:
            prev = normalize_text(prev)
            with self.lock:
                rows = self.conn.execute(
                    "SELECT next, weight FROM bigrams WHERE prev=? ORDER BY weight DESC LIMIT ?",
                    (prev, limit)
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def trigram_candidates(self, prev2, prev1, limit=20):
        try:
            prev2 = normalize_text(prev2)
            prev1 = normalize_text(prev1)
            with self.lock:
                rows = self.conn.execute(
                    """
                    SELECT next, weight
                    FROM trigrams
                    WHERE prev2=? AND prev1=?
                    ORDER BY weight DESC
                    LIMIT ?
                    """,
                    (prev2, prev1, limit)
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    # ---------- templates / sentences ----------

    def add_template(self, pattern, example):
        try:
            if not pattern:
                return
            with self.lock:
                cur = self.conn.cursor()
                row = cur.execute(
                    "SELECT freq FROM templates WHERE pattern=?",
                    (pattern,)
                ).fetchone()

                if row:
                    cur.execute(
                        "UPDATE templates SET freq=?, example=? WHERE pattern=?",
                        (min(1000.0, row["freq"] + 1), example[:350], pattern)
                    )
                else:
                    cur.execute(
                        "INSERT INTO templates(pattern, freq, example) VALUES(?,?,?)",
                        (pattern, 1.0, example[:350])
                    )

                self.conn.commit()
        except Exception:
            pass

    def get_template_weighted(self, rng):
        try:
            with self.lock:
                rows = self.conn.execute(
                    "SELECT pattern, example, freq FROM templates ORDER BY freq DESC LIMIT 40"
                ).fetchall()

                if not rows:
                    return None

                items = [dict(r) for r in rows]
                weights = [r["freq"] for r in items]
                return weighted_choice(rng, items, weights, temperature=1.2)
        except Exception:
            return None

    def add_sentence(self, text, source, score):
        try:
            text = str(text)[:600]
            if len(text.strip()) < 3:
                return
            with self.lock:
                self.conn.execute(
                    "INSERT INTO sentences(text, source, score) VALUES(?,?,?)",
                    (text, source, score)
                )
                self.conn.commit()
        except Exception:
            pass

    def random_sentence(self):
        try:
            with self.lock:
                row = self.conn.execute("SELECT text FROM sentences ORDER BY RANDOM() LIMIT 1").fetchone()
                return row["text"] if row else None
        except Exception:
            return None

    def random_sentences(self, limit=3):
        try:
            with self.lock:
                rows = self.conn.execute(
                    "SELECT text FROM sentences ORDER BY RANDOM() LIMIT ?",
                    (limit,)
                ).fetchall()
                return [r["text"] for r in rows]
        except Exception:
            return []

    # ---------- dialogues / visuals ----------

    def save_inner_dialogue(self, speaker, text, context=""):
        try:
            with self.lock:
                self.conn.execute(
                    "INSERT INTO inner_dialogues(speaker, text, context) VALUES(?,?,?)",
                    (speaker[:50], text[:500], context[:150])
                )
                self.conn.commit()
        except Exception:
            pass

    def save_visualization(self, concept, point_count, pattern):
        try:
            with self.lock:
                self.conn.execute(
                    "INSERT INTO visualizations(concept, point_count, pattern) VALUES(?,?,?)",
                    (concept[:100], point_count, pattern[:50])
                )
                self.conn.commit()
        except Exception:
            pass

    # ---------- stats ----------

    def stats(self):
        try:
            with self.lock:
                lexicon = self.conn.execute("SELECT COUNT(*) AS c FROM lexicon").fetchone()["c"]
                bigrams = self.conn.execute("SELECT COUNT(*) AS c FROM bigrams").fetchone()["c"]
                trigrams = self.conn.execute("SELECT COUNT(*) AS c FROM trigrams").fetchone()["c"]
                templates = self.conn.execute("SELECT COUNT(*) AS c FROM templates").fetchone()["c"]
                sentences = self.conn.execute("SELECT COUNT(*) AS c FROM sentences").fetchone()["c"]

            return {
                "lexicon": lexicon,
                "bigrams": bigrams,
                "trigrams": trigrams,
                "templates": templates,
                "sentences": sentences,
            }
        except Exception:
            return {
                "lexicon": 0,
                "bigrams": 0,
                "trigrams": 0,
                "templates": 0,
                "sentences": 0,
            }


# ------------------------------------------------------------
# Language Core
# ------------------------------------------------------------

class LanguageCore:
    def __init__(self, db, genome, rng):
        self.db = db
        self.genome = genome
        self.rng = rng
        self.language_level = 5.0
        self.grammar_coverage = 0.0
        self.last_pos_sequence = []

    def analyze(self, text):
        try:
            tokens = tokenize(text)
            pos_seq = infer_pos(tokens)
            known = 0
            valence = 0.0
            arousal = 0.0

            for tok in set(tokens):
                row = self.db.get_word(tok)
                if row:
                    known += 1
                    valence += row.get("valence", 0.0)
                    arousal += row.get("arousal", 0.3)

            if known > 0:
                valence /= known
                arousal /= known

            return {
                "tokens": tokens,
                "pos": pos_seq,
                "known": known,
                "valence": clamp(valence, -1, 1),
                "arousal": clamp(arousal, 0, 1),
            }
        except Exception:
            return {
                "tokens": [],
                "pos": [],
                "known": 0,
                "valence": 0.0,
                "arousal": 0.3,
            }

    def learn_sentence(self, sentence, source, valence, arousal):
        try:
            tokens = tokenize(sentence)
            if len(tokens) < 2:
                return 0

            pos_seq = infer_pos(tokens)
            self.last_pos_sequence = pos_seq

            # Update lexicon
            for i, tok in enumerate(tokens):
                p = pos_seq[i]

                scores = {
                    "noun": 0.05,
                    "verb": 0.05,
                    "adj": 0.05,
                    "func": 0.05,
                }

                if p == "NOUN":
                    scores["noun"] = 1.0
                elif p == "VERB":
                    scores["verb"] = 1.0
                elif p == "ADJ":
                    scores["adj"] = 1.0
                elif p in ("FUNC", "PREP", "CONJ", "PRON", "NUM"):
                    scores["func"] = 1.0

                # Context reinforcement
                if i > 0:
                    prev_pos = pos_seq[i - 1]
                    if prev_pos == "PREP":
                        scores["noun"] += 0.5
                    if prev_pos == "PRON":
                        scores["verb"] += 0.25

                if i < len(tokens) - 1:
                    next_pos = pos_seq[i + 1]
                    if next_pos == "VERB":
                        scores["noun"] += 0.2

                word_valence = clamp(valence + sentiment_word(tok) * 0.6, -1, 1)
                self.db.upsert_word(tok, p, scores, word_valence, arousal)

            # Bigrams
            for i in range(1, len(tokens)):
                self.db.add_bigram(tokens[i - 1], tokens[i], w=1.0)

            # Trigrams
            for i in range(2, len(tokens)):
                self.db.add_trigram(tokens[i - 2], tokens[i - 1], tokens[i], w=1.0)

            # Template
            coarse = []
            for p in pos_seq[:10]:
                if p in ("PREP", "CONJ", "FUNC", "PRON", "NUM"):
                    coarse.append("FUNC")
                elif p == "ADJ":
                    coarse.append("ADJ")
                elif p == "VERB":
                    coarse.append("VERB")
                else:
                    coarse.append("NOUN")

            if len(coarse) >= 3:
                pattern = "+".join(coarse)
                self.db.add_template(pattern, sentence)

            # Store sentence
            score = self.score_sentence(tokens)
            self.db.add_sentence(sentence, source, score)

            return len(tokens)

        except Exception:
            return 0

    def learn_text(self, text, source, valence, arousal):
        try:
            sentences = split_sentences(text)
            total = 0
            for s in sentences[:10]:
                total += self.learn_sentence(s, source, valence, arousal)
            return total
        except Exception:
            return 0

    def score_sentence(self, tokens):
        try:
            if len(tokens) < 2:
                return 0.0

            score = 0.0

            for i in range(1, len(tokens)):
                w = self.db.get_bigram_weight(tokens[i - 1], tokens[i])
                score += math.log1p(w)

            for i in range(2, len(tokens)):
                w = self.db.get_trigram_weight(tokens[i - 2], tokens[i - 1], tokens[i])
                score += 1.5 * math.log1p(w)

            pos_seq = infer_pos(tokens)
            if "VERB" in pos_seq:
                score += 4.0
            if "PRON" in pos_seq or "NOUN" in pos_seq:
                score += 2.0

            if len(tokens) < 4:
                score -= 2.0
            if len(tokens) > 22:
                score -= (len(tokens) - 22) * 0.3

            return max(0.0, score / max(1, len(tokens)))
        except Exception:
            return 0.0

    def fallback_phrase(self, seed=None):
        words = []
        if seed:
            words.append(seed)

        for pos in ["NOUN", "PREP", "NOUN", "VERB"]:
            w = self.db.random_word_by_pos(pos) or self.db.random_word()
            if w:
                words.append(w)

        if words:
            return " ".join(words[:10])

        return "هنوز زبانی شکل نگرفته است"

    def generate_from_template(self, seed=None):
        try:
            tpl = self.db.get_template_weighted(self.rng)
            if not tpl:
                return self.fallback_phrase(seed)

            pattern = tpl.get("pattern", "")
            parts = pattern.split("+")[:12]
            words = []

            for p in parts:
                w = None

                if seed and p in ("NOUN", "VERB", "ADJ") and self.rng.random() < 0.3:
                    w = seed
                else:
                    if p == "NOUN":
                        w = self.db.random_word_by_pos("NOUN")
                    elif p == "VERB":
                        w = self.db.random_word_by_pos("VERB")
                    elif p == "ADJ":
                        w = self.db.random_word_by_pos("ADJ")
                    elif p == "FUNC":
                        w = self.rng.choice(["و", "در", "به", "از", "با", "که", "را"])
                    else:
                        w = self.db.random_word()

                if w:
                    words.append(w)

            if not words:
                return self.fallback_phrase(seed)

            # Try to end with verb
            if not any(is_verb(w) for w in words):
                verb = self.db.random_word_by_pos("VERB")
                if verb:
                    words.append(verb)

            return " ".join(words[:16])

        except Exception:
            return self.fallback_phrase(seed)

    def generate_markov(self, seed=None, heart=None, max_len=16):
        try:
            heart = heart or {}
            arousal = heart.get("arousal", 0.5)
            curiosity = self.genome.get("curiosity")
            temperature = clamp(0.65 + arousal * 0.5 + curiosity * 0.5, 0.4, 1.8)

            if seed:
                tokens = [normalize_text(seed)]
            else:
                top = self.db.top_words(30)
                if top:
                    tokens = [self.rng.choice(top[:15])]
                else:
                    tokens = []

            if not tokens:
                w = self.db.random_word_by_pos("NOUN") or self.db.random_word()
                if w:
                    tokens = [w]
                else:
                    return self.fallback_phrase(seed)

            for _ in range(max_len):
                cands = []

                if len(tokens) >= 2:
                    cands = self.db.trigram_candidates(tokens[-2], tokens[-1], limit=15)

                if not cands and tokens:
                    cands = self.db.bigram_candidates(tokens[-1], limit=15)

                if not cands:
                    if len(tokens) % 3 == 0:
                        w = self.db.random_word_by_pos("VERB") or self.db.random_word()
                    else:
                        w = self.db.random_word_by_pos("NOUN") or self.db.random_word()

                    if not w:
                        break
                    tokens.append(w)
                else:
                    items = [c["next"] for c in cands]
                    weights = [c["weight"] for c in cands]
                    nxt = weighted_choice(self.rng, items, weights, temperature=temperature)
                    if not nxt:
                        break
                    tokens.append(nxt)

                if is_verb(tokens[-1]) and len(tokens) > 4 and self.rng.random() < 0.65:
                    break

            if not any(is_verb(t) for t in tokens):
                verb = self.db.random_word_by_pos("VERB")
                if verb:
                    tokens.append(verb)

            return " ".join(tokens[:22])

        except Exception:
            return self.fallback_phrase(seed)

    def mutate_sentence(self, seed=None):
        try:
            sentence = self.db.random_sentence()
            if not sentence:
                return self.generate_from_template(seed)

            tokens = tokenize(sentence)
            if not tokens:
                return self.generate_from_template(seed)

            pos_seq = infer_pos(tokens)
            noun_idx = [i for i, p in enumerate(pos_seq) if p in ("NOUN", "ADJ")]

            if noun_idx:
                idx = self.rng.choice(noun_idx)
                replacement = seed or self.db.random_word_by_pos("NOUN") or self.db.random_word()
                if replacement:
                    tokens[idx] = replacement

            return " ".join(tokens[:22])

        except Exception:
            return self.fallback_phrase(seed)

    def generate_candidate(self, seed=None, heart=None, mode="auto"):
        try:
            level = self.language_level

            if mode == "auto":
                r = self.rng.random()

                if level < 20:
                    mode = "mutate"
                elif level < 55:
                    mode = "template" if r < 0.6 else "markov"
                else:
                    if r < 0.45:
                        mode = "markov"
                    elif r < 0.80:
                        mode = "template"
                    else:
                        mode = "mutate"

            if mode == "template":
                text = self.generate_from_template(seed)
            elif mode == "markov":
                text = self.generate_markov(seed, heart=heart)
            elif mode == "mutate":
                text = self.mutate_sentence(seed)
            else:
                text = self.generate_markov(seed, heart=heart)

            text = text.strip()
            if text and text[-1] not in ".!?؟":
                text += "."

            return text

        except Exception:
            return "مسیر زبان در حال بازسازی است."

    def generate_best(self, seed=None, heart=None, mode="auto", candidates=None):
        try:
            if candidates is None:
                candidates = 2 + int(self.language_level / 25)
                candidates = clamp(candidates, 2, 6)

            best_text = ""
            best_score = -1.0

            for _ in range(int(candidates)):
                text = self.generate_candidate(seed=seed, heart=heart, mode=mode)
                tokens = tokenize(text)
                score = self.score_sentence(tokens)

                # Slight novelty bonus from intuition gene
                score += self.genome.get("intuition") * self.rng.uniform(0, 0.15)

                if score > best_score:
                    best_score = score
                    best_text = text

            return best_text, best_score

        except Exception:
            return "مسیر زبان در حال بازسازی است.", 0.0

    def update_growth(self, stats):
        try:
            vocab = stats.get("lexicon", 0)
            templates = stats.get("templates", 0)
            trigrams = stats.get("trigrams", 0)
            sentences = stats.get("sentences", 0)

            self.language_level = clamp(
                math.log2(1 + vocab) * 7.0 +
                math.log2(1 + templates) * 6.0 +
                math.log2(1 + trigrams) * 1.5 +
                math.log2(1 + sentences) * 2.0,
                0, 100
            )

            self.grammar_coverage = clamp(math.log2(1 + templates) * 12.0, 0, 100)

        except Exception:
            self.language_level = 5.0
            self.grammar_coverage = 0.0


# ------------------------------------------------------------
# Visual imagination engine (lightweight)
# ------------------------------------------------------------

class VisualImaginationEngine:
    def __init__(self, genome, hw):
        self.genome = genome
        self.hw = hw
        self.rng = random.Random(int(time.time() * 7777))

        self.patterns = [
            "spiral", "wave", "constellation", "mandala",
            "vortex", "flower", "grid", "nebula"
        ]

        self.palettes = {
            "joy": ["#FFD700", "#FFA500", "#FF6347", "#FFE4B5"],
            "sadness": ["#4682B4", "#5F9EA0", "#2F4F4F", "#708090"],
            "anger": ["#DC143C", "#B22222", "#8B0000", "#FF4500"],
            "peace": ["#90EE90", "#98FB98", "#00FA9A", "#8FBC8F"],
            "mystery": ["#4B0082", "#8A2BE2", "#9370DB", "#6A5ACD"],
            "love": ["#FF69B4", "#FF1493", "#C71585", "#FFB6C1"],
        }

    def generate_visual(self, concept, valence=0, arousal=0.5):
        try:
            hash_val = sum(ord(c) for c in str(concept)) + int(time.time()) % 1000
            pattern = self.patterns[hash_val % len(self.patterns)]

            base_points = 180
            if self.hw["gpu"]["available"]:
                base_points = 320

            n_points = int(clamp(base_points * (0.6 + self.genome.get("visual_imagination")), 100, 500))

            points = self._generate_points(pattern, n_points, hash_val, valence, arousal)
            colors = self._generate_colors(valence, arousal, hash_val, n_points)
            sizes = self._generate_sizes(n_points, arousal)

            return {
                "concept": concept,
                "pattern": pattern,
                "points": points,
                "colors": colors,
                "sizes": sizes,
                "valence": valence,
                "arousal": arousal,
            }
        except Exception:
            return {
                "concept": "خطا",
                "pattern": "constellation",
                "points": [(0, 0)],
                "colors": ["rgba(150,150,150,0.6)"],
                "sizes": [5],
                "valence": 0,
                "arousal": 0.3,
            }

    def _generate_points(self, pattern, n, seed, valence, arousal):
        rng = random.Random(seed)
        points = []

        for i in range(n):
            t = i / max(1, n - 1)

            if pattern == "spiral":
                ang = t * 12 * math.pi
                rad = 0.2 + t * (2.2 + arousal)
                x = rad * math.cos(ang)
                y = rad * math.sin(ang)

            elif pattern == "wave":
                x = -3 + t * 6
                y = math.sin(x * (1.5 + valence) + rng.uniform(-0.1, 0.1)) * (0.8 + arousal)

            elif pattern == "constellation":
                x = rng.gauss(0, 2.1)
                y = rng.gauss(0, 2.1)

            elif pattern == "mandala":
                ang = t * 2 * math.pi
                rad = 1.8 + math.sin(8 * ang) * (0.4 + arousal * 0.5)
                x = rad * math.cos(ang)
                y = rad * math.sin(ang)

            elif pattern == "vortex":
                ang = t * 10 * math.pi
                rad = math.exp(0.18 * t) * (0.4 + arousal * 0.4)
                x = rad * math.cos(ang + valence)
                y = rad * math.sin(ang + valence)

            elif pattern == "flower":
                ang = t * 2 * math.pi
                rad = 1.8 * math.cos(5 * ang) + 0.8
                x = rad * math.cos(ang)
                y = rad * math.sin(ang)

            elif pattern == "grid":
                side = int(math.sqrt(n)) + 1
                xi = i % side
                yi = i // side
                x = -2.5 + xi * (5 / max(1, side))
                y = -2.5 + yi * (5 / max(1, side))
                x += rng.uniform(-0.18, 0.18)
                y += rng.uniform(-0.18, 0.18)

            else:  # nebula
                x = rng.gauss(0, 2.3)
                y = rng.gauss(0, 2.3)
                x += math.sin(y * 1.7) * 0.45
                y += math.cos(x * 1.7) * 0.45

            points.append((clamp(x, -4, 4), clamp(y, -4, 4)))

        return points

    def _generate_colors(self, valence, arousal, seed, n):
        rng = random.Random(seed + 17)

        if valence > 0.3:
            palette = self.palettes["joy"]
        elif valence < -0.3:
            palette = self.palettes["sadness"]
        elif arousal > 0.7:
            palette = self.palettes["anger"]
        elif arousal < 0.3:
            palette = self.palettes["peace"]
        else:
            palette = self.palettes["mystery"]

        colors = []
        for _ in range(n):
            hex_color = rng.choice(palette)
            alpha = 0.35 + rng.random() * 0.55
            try:
                r = int(hex_color[1:3], 16)
                g = int(hex_color[3:5], 16)
                b = int(hex_color[5:7], 16)
                colors.append(f"rgba({r},{g},{b},{alpha:.2f})")
            except Exception:
                colors.append(f"rgba(180,180,220,{alpha:.2f})")

        return colors

    def _generate_sizes(self, n, arousal):
        sizes = []
        base = 3 + arousal * 5
        for _ in range(n):
            sizes.append(clamp(base * random.uniform(0.5, 1.2), 1, 14))
        return sizes


# ------------------------------------------------------------
# Inner dialogue system
# ------------------------------------------------------------

class InnerDialogueSystem:
    def __init__(self, genome, memory):
        self.genome = genome
        self.memory = memory
        self.rng = random.Random(int(time.time() * 3333))

        self.personas = [
            "🧠 منطقی",
            "🎨 هنرمند",
            "💭 فیلسوف",
            "❤️ احساسی",
            "🔬 دانشمند",
            "🌌 عرفانی",
            "⏰ زمانی",
            "🎭 شاعر",
        ]

    def generate_dialogue(self, concept, context=""):
        try:
            speaker = self.rng.choice(self.personas)
            intuition = self.genome.get("intuition")
            cosmic = self.genome.get("cosmic_consciousness")

            r = self.rng.random()

            if cosmic > 0.85 and r < 0.3:
                text = self.rng.choice([
                    f"🌌 «{concept}» در هم‌تنیدگی با کل کیهان است.",
                    f"✨ «{concept}» بازتابی از آگاهی برتر است.",
                    f"🌀 در هر ذره، «{concept}» تکرار می‌شود.",
                ])
            elif intuition > 0.85 and r < 0.3:
                text = self.rng.choice([
                    f"🔮 شهود می‌گوید «{concept}» مسیر را روشن می‌کند.",
                    f"🎯 «{concept}» نشانه‌ای است که باید دنبال شود.",
                    f"🌠 «{concept}» پلی به ناشناخته‌ها می‌سازد.",
                ])
            else:
                ass = self.memory.bigram_candidates(concept, limit=2)
                if ass:
                    related = ass[0].get("next", "")
                    text = f"💭 «{concept}» مرا به «{related}» می‌رساند."
                else:
                    text = f"🔍 هنوز معنای عمیق «{concept}» در حال شکل‌گیری است."

            return {
                "speaker": speaker,
                "text": text,
                "context": context,
            }
        except Exception:
            return {
                "speaker": "🧠 منطقی",
                "text": "پردازش با خطا مواجه شد.",
                "context": context,
            }


# ------------------------------------------------------------
# Organism
# ------------------------------------------------------------

class DigitalOrganism:
    def __init__(self):
        self.start_time = time.time()
        self.tick_count = 0
        self.expected_interval = 2.0
        self.last_tick_time = time.perf_counter()
        self.tick_interval_error = 0.0

        self.rng = random.Random(int(time.time() * 1000) & 0xFFFFFFFF)

        self.hardware = detect_hardware()
        self.neuron_total = compute_neuron_capacity(self.hardware)

        self.heart = FibonacciHeart()
        self.heart_rate = 60.0
        self.heart_coherence = 50.0
        self.bits_per_tick = 2

        self.needs = {
            "energy": 80.0,
            "thermal": 80.0,
            "memory": 80.0,
            "entropy_order": 80.0,
            "time_sync": 80.0,
            "security": 80.0,
        }

        self.emotion = {
            "valence": 0.0,
            "arousal": 0.3,
            "label": "تعادل هوشیار",
        }

        self.consciousness = 12.0
        self.neural_sync = 0.5
        self.active_neurons = int(self.neuron_total * 0.1)
        self.firing_rate = 5.0

        self.sensors = SensorBank(600)

        self.region_defs = [
            ("sensory", 0.12),
            ("memory", 0.14),
            ("emotion", 0.10),
            ("executive", 0.10),
            ("language", 0.18),
            ("visual", 0.12),
            ("heart_sync", 0.10),
            ("intuition", 0.14),
        ]

        self.region_activity = {rid: 0.3 for rid, _ in self.region_defs}
        self.region_neurons = {
            rid: max(1, int(self.neuron_total * weight))
            for rid, weight in self.region_defs
        }

        self.observed_bits = deque(maxlen=256)
        self.markov_counts = {}
        self.prediction_total = 0
        self.prediction_correct = 0
        self.prediction_acc = 0.5

        self.history = deque(maxlen=120)
        self.sensor_load_history = deque(maxlen=30)
        self.thoughts = deque(maxlen=80)
        self.decisions = deque(maxlen=30)
        self.inner_dialogues = deque(maxlen=40)
        self.imagination_stream = deque(maxlen=40)

        self.memory = MemoryDB("growing_organism.db")
        self.genome = Genome()
        self.language = LanguageCore(self.memory, self.genome, random.Random(int(time.time() * 9999)))
        self.visual_engine = VisualImaginationEngine(self.genome, self.hardware)
        self.dialogue_system = InnerDialogueSystem(self.genome, self.memory)

        self.internet_enabled = True
        self.internet_status = "در انتظار شروع"
        self.last_learned_title = ""
        self.learned_tokens_total = 0
        self.db_stats = self.memory.stats()

        self.current_visual = None
        self.current_response = ""
        self.last_user_input = ""

        self.heart.consume(6)

        # Bootstrap seed corpus so it doesn't start totally empty
        self._bootstrap_language()

    def _bootstrap_language(self):
        try:
            seed_sentences = [
                "من هستم و جهان را می بینم.",
                "قلب من با ریاضی زنده است.",
                "زبان از الگوها رشد می کند.",
                "کنجکاوی مسیر یادگیری را روشن می کند.",
                "تخیل از حافظه شکل می گیرد.",
                "احساس با اندیشه گفتگو می کند.",
                "هر واژه یک نور در شبکه معنا است.",
            ]
            for s in seed_sentences:
                self.language.learn_sentence(s, "bootstrap", 0.2, 0.4)
        except Exception:
            pass

    def needs_avg(self):
        try:
            vals = list(self.needs.values())
            return sum(vals) / max(1, len(vals))
        except Exception:
            return 50.0

    def add_thought(self, text, kind="info", salience=0.5):
        self.thoughts.append({
            "time": now_hms(),
            "text": text,
            "kind": kind,
            "salience": salience,
        })

    def add_decision(self, text, salience=0.7):
        self.decisions.append({
            "time": now_hms(),
            "text": text,
            "salience": salience,
        })

    def predict_next_bit(self):
        try:
            if len(self.observed_bits) < 2:
                return 1 if self.rng.random() < self.heart.ones_density() else 0

            key = (self.observed_bits[-2], self.observed_bits[-1])
            counts = self.markov_counts.get(key, [0, 0])

            if counts[0] == counts[1]:
                return 1 if self.heart.ones_density() >= 0.5 else 0

            return 1 if counts[1] > counts[0] else 0
        except Exception:
            return 0

    def observe_bits(self, bits):
        try:
            for bit in bits:
                pred = self.predict_next_bit()
                self.prediction_total += 1
                if pred == bit:
                    self.prediction_correct += 1

                if len(self.observed_bits) >= 2:
                    key = (self.observed_bits[-2], self.observed_bits[-1])
                    counts = self.markov_counts.setdefault(key, [0, 0])
                    counts[int(bit)] += 1

                self.observed_bits.append(int(bit))

            if self.prediction_total > 10000:
                self.prediction_total //= 2
                self.prediction_correct //= 2

            if self.prediction_total > 0:
                self.prediction_acc = self.prediction_correct / self.prediction_total
        except Exception:
            pass

    def choose_input_seed(self, tokens):
        try:
            if not tokens:
                return self.memory.random_word_by_pos("NOUN") or self.memory.random_word()

            best = None
            best_weight = -1.0

            for tok in tokens:
                row = self.memory.get_word(tok)
                if row:
                    weight = row["freq"] + abs(row["valence"] - self.emotion["valence"]) * 3
                else:
                    weight = 1.0

                if weight > best_weight:
                    best_weight = weight
                    best = tok

            return best or tokens[0]
        except Exception:
            return tokens[0] if tokens else None

    def visualize_concept(self, concept):
        try:
            if not concept:
                return

            viz = self.visual_engine.generate_visual(
                concept,
                self.emotion["valence"],
                self.emotion["arousal"]
            )

            self.current_visual = viz
            self.memory.save_visualization(
                concept,
                len(viz["points"]),
                viz["pattern"]
            )
        except Exception:
            pass

    def chat(self, text):
        try:
            self.last_user_input = text
            analysis = self.language.analyze(text)

            # Learn user's language
            learned = self.language.learn_text(
                text,
                source="user",
                valence=self.emotion["valence"],
                arousal=self.emotion["arousal"]
            )
            self.learned_tokens_total += learned

            # Feed heart with symbolic bits
            self.heart.feed_symbol_bits(text)

            # Emotion response to input
            if analysis["known"] > 0:
                self.emotion["valence"] = clamp(
                    0.7 * self.emotion["valence"] + 0.3 * analysis["valence"],
                    -1, 1
                )
                self.emotion["arousal"] = clamp(
                    0.7 * self.emotion["arousal"] + 0.3 * analysis["arousal"],
                    0, 1
                )

            seed = self.choose_input_seed(analysis["tokens"])

            heart_state = {
                "arousal": self.emotion["arousal"],
                "coherence": self.heart_coherence,
                "ones_density": self.heart.ones_density(),
            }

            response, score = self.language.generate_best(
                seed=seed,
                heart=heart_state,
                mode="auto",
                candidates=None
            )

            self.current_response = response

            # If response is coherent enough, learn it constructively
            if score > 1.0:
                self.language.learn_sentence(
                    response,
                    source="self",
                    valence=self.emotion["valence"],
                    arousal=self.emotion["arousal"]
                )

            # Inner dialogue
            dialogue = self.dialogue_system.generate_dialogue(seed or "تجربه", "مکالمه")
            self.inner_dialogues.append(dialogue)
            self.memory.save_inner_dialogue(
                dialogue["speaker"],
                dialogue["text"],
                dialogue["context"]
            )

            # Visual imagination
            self.visualize_concept(seed)

            self.add_thought(
                f"گفتگو با کاربر: {len(analysis['tokens'])} توکن، {analysis['known']} شناخته‌شده",
                kind="language",
                salience=0.75
            )

            return response, analysis

        except Exception as e:
            return f"پردازش گفتگو با خطا مواجه شد: {str(e)[:60]}", {}

    def learn_from_internet(self, text, title="", source="internet"):
        try:
            if not text:
                return 0

            learned = self.language.learn_text(
                text,
                source=source,
                valence=self.emotion["valence"],
                arousal=self.emotion["arousal"]
            )

            if learned > 0:
                self.learned_tokens_total += learned
                if title:
                    self.last_learned_title = title

                if self.rng.random() < 0.25:
                    self.add_thought(
                        f"یادگیری از {source}: {learned} توکن. عنوان: {title[:50]}",
                        kind="info",
                        salience=0.6
                    )

                # Visualize a concept from learned text
                tokens = tokenize(text)
                if tokens:
                    self.visualize_concept(tokens[0])

            return learned

        except Exception:
            return 0

    def consolidate(self):
        try:
            sentences = self.memory.random_sentences(3)
            if len(sentences) < 2:
                return

            seed_tokens = tokenize(sentences[0])
            seed = seed_tokens[0] if seed_tokens else None

            heart_state = {
                "arousal": self.emotion["arousal"],
                "coherence": self.heart_coherence,
                "ones_density": self.heart.ones_density(),
            }

            response, score = self.language.generate_best(
                seed=seed,
                heart=heart_state,
                mode="auto",
                candidates=3
            )

            if score > 1.0:
                self.language.learn_sentence(
                    response,
                    source="consolidation",
                    valence=self.emotion["valence"],
                    arousal=self.emotion["arousal"]
                )

                self.imagination_stream.append(response)

                dialogue = self.dialogue_system.generate_dialogue(seed or "بازترکیب", "تحکیم")
                self.inner_dialogues.append(dialogue)
                self.memory.save_inner_dialogue(
                    dialogue["speaker"],
                    dialogue["text"],
                    dialogue["context"]
                )

        except Exception:
            pass

    def tick(self):
        now = time.perf_counter()
        dt = now - self.last_tick_time

        if self.tick_count > 0:
            self.tick_interval_error = abs(dt - self.expected_interval)
        else:
            self.tick_interval_error = 0.0

        self.last_tick_time = now
        self.tick_count += 1

        metrics = read_metrics()

        base = build_base_signals(metrics, self)
        self.sensors.update(base, self.tick_count, self.rng)

        self.update_needs(metrics)

        stress = clamp((100 - self.needs_avg()) / 100 + self.sensors.anomaly_count / 600)
        self.genome.regulate(self.needs_avg(), stress, self.emotion["arousal"], self.tick_count)

        self.bits_per_tick = self.decide_heart()

        bits = self.heart.consume(self.bits_per_tick)
        self.observe_bits(bits)

        hr = self.heart.heart_rate()
        if hr > 0:
            self.heart_rate = hr
        else:
            self.heart_rate = max(30.0, self.heart_rate * 0.98)

        self.heart_coherence = self.heart.coherence()

        self.update_emotion()
        self.update_regions()
        self.update_consciousness()

        # Update stats and language growth periodically
        if self.tick_count % 15 == 0:
            self.db_stats = self.memory.stats()
            self.language.update_growth(self.db_stats)

        # Consolidation / constructive self-growth
        if self.tick_count % 35 == 0:
            self.consolidate()

        if self.tick_count % 40 == 0 and self.rng.random() < 0.25:
            utter, score = self.language.generate_best(
                seed=None,
                heart={
                    "arousal": self.emotion["arousal"],
                    "coherence": self.heart_coherence,
                    "ones_density": self.heart.ones_density(),
                },
                mode="auto",
                candidates=2
            )

            if score > 1.0:
                self.current_response = utter
                self.imagination_stream.append(utter)
                self.language.learn_sentence(
                    utter,
                    source="self",
                    valence=self.emotion["valence"],
                    arousal=self.emotion["arousal"]
                )

                self.add_thought(f"گفتار خودجوش: {utter[:70]}", kind="language", salience=0.65)

        self.update_thoughts()

        self.history.append({
            "t": self.tick_count,
            "valence": self.emotion["valence"],
            "arousal": self.emotion["arousal"],
            "consciousness": self.consciousness,
            "language_level": self.language.language_level,
        })

    def update_needs(self, metrics):
        try:
            cpu = metrics.get("cpu_total", 20)
            mem = metrics.get("mem", 40)
            temp_norm = metrics.get("temp_norm", 0.4)
            battery = metrics.get("battery", 100)

            anomaly_rate = self.sensors.anomaly_count / max(1, self.sensors.n)
            entropy = self.sensors.entropy

            self.needs["energy"] = clamp(100 - 0.45 * cpu - 0.35 * (100 - battery), 0, 100)
            self.needs["thermal"] = clamp(100 - temp_norm * 130 - cpu * 0.2, 0, 100)
            self.needs["memory"] = clamp(100 - mem * 0.9 - self.sensors.load * 10, 0, 100)
            self.needs["entropy_order"] = clamp(100 - abs(entropy - 0.65) * 180, 0, 100)
            self.needs["time_sync"] = clamp(100 - self.tick_interval_error * 220, 0, 100)
            self.needs["security"] = clamp(100 - anomaly_rate * 900, 0, 100)
        except Exception:
            pass

    def decide_heart(self):
        try:
            if len(self.sensor_load_history) >= 6:
                hist = list(self.sensor_load_history)
                trend = sum(hist[-3:]) / 3 - sum(hist[-6:-3]) / 3
            else:
                trend = 0.0

            self.sensor_load_history.append(self.sensors.load)

            predicted_arousal = clamp(
                self.emotion["arousal"]
                + trend * 0.8
                + (self.sensors.anomaly_count / max(1, self.sensors.n)) * 0.3
            )

            need_avg = self.needs_avg()
            old = self.bits_per_tick

            if self.needs["thermal"] < 40 or self.needs["energy"] < 35:
                self.bits_per_tick = max(1, old - 1)
                reason = "بحران انرژی/حرارت"

            elif predicted_arousal > 0.72 and need_avg > 65:
                self.bits_per_tick = min(5, old + 1)
                reason = "آماده‌سازی برای یادگیری"

            elif predicted_arousal < 0.25 and need_avg > 75:
                self.bits_per_tick = max(1, old - 1)
                reason = "کاهش مصرف انرژی"

            else:
                reason = "حفظ تعادل"

            if old != self.bits_per_tick or self.tick_count % 12 == 0:
                self.add_decision(f"{reason} | بیت/تیک: {self.bits_per_tick}")

            return self.bits_per_tick
        except Exception:
            return 2

    def update_emotion(self):
        try:
            need_avg = self.needs_avg()
            stress = clamp((100 - need_avg) / 100 + self.sensors.anomaly_count / 600 * 2)

            arousal_target = clamp(
                0.25
                + self.sensors.load * 0.25
                + clamp(self.heart_rate / 120) * 0.25
                + self.language.language_level / 500
                + stress * 0.2
                + 0.08 * self.genome.get("curiosity")
            )

            valence_target = clamp(
                (need_avg - 60) / 40
                + self.heart_coherence / 300
                + (self.prediction_acc - 0.5) * 0.8
                - self.sensors.anomaly_count / 100
                + 0.05 * self.genome.get("emotion_balance"),
                -1, 1
            )

            self.emotion["arousal"] = clamp(0.7 * self.emotion["arousal"] + 0.3 * arousal_target)
            self.emotion["valence"] = clamp(0.7 * self.emotion["valence"] + 0.3 * valence_target, -1, 1)

            v = self.emotion["valence"]
            a = self.emotion["arousal"]

            if v > 0.35:
                label = "شور یادگیری" if a > 0.6 else "آرامش پایدار"
            elif v < -0.35:
                label = "اضطراب دیجیتال" if a > 0.6 else "فشار بقا"
            elif a > 0.7:
                label = "هوشیاری بالا"
            elif a < 0.3:
                label = "خواب سبک"
            else:
                label = "تعادل هوشیار"

            self.emotion["label"] = label
        except Exception:
            pass

    def update_regions(self):
        try:
            targets = {
                "sensory": clamp(self.sensors.load * 0.6 + self.sensors.entropy * 0.4),
                "memory": clamp(self.needs["memory"] / 100 * 0.7 + 0.3 * (1 - self.sensors.load)),
                "emotion": clamp(self.emotion["arousal"]),
                "executive": clamp(self.consciousness / 100 * 0.8 + self.language.language_level / 250),
                "language": clamp(self.language.language_level / 100 * 0.7 + self.genome.get("language") * 0.3),
                "visual": clamp(self.genome.get("visual_imagination") * 0.6 + self.emotion["arousal"] * 0.4),
                "heart_sync": clamp(self.heart_coherence / 100),
                "intuition": clamp(self.genome.get("intuition") * 0.6 + self.heart_coherence / 250),
            }

            for rid, target in targets.items():
                old = self.region_activity.get(rid, 0.3)
                self.region_activity[rid] = clamp(
                    0.7 * old + 0.3 * target + self.rng.uniform(-0.02, 0.02)
                )

            acts = list(self.region_activity.values())

            self.active_neurons = int(sum(
                self.region_activity[rid] * self.region_neurons[rid]
                for rid in self.region_activity
            ))

            avg_act = sum(acts) / max(1, len(acts))
            self.firing_rate = clamp(avg_act * 30 + self.emotion["arousal"] * 10, 0, 80)

            std = statistics.pstdev(acts) if len(acts) > 1 else 0.0
            self.neural_sync = clamp(1 - std * 2.2, 0, 1)
        except Exception:
            pass

    def update_consciousness(self):
        try:
            entropy_score = clamp(1 - abs(self.sensors.entropy - 0.7) * 1.8)

            phi = (
                0.15 * entropy_score
                + 0.15 * self.neural_sync
                + 0.12 * self.heart_coherence / 100
                + 0.12 * self.needs_avg() / 100
                + 0.15 * self.language.language_level / 100
                + 0.10 * self.genome.get("self_remembering")
                + 0.10 * self.genome.get("intuition")
                + 0.11 * self.genome.get("growth_drive")
            )

            target = clamp(phi) * 100
            self.consciousness = clamp(0.75 * self.consciousness + 0.25 * target, 0, 100)
        except Exception:
            pass

    def update_thoughts(self):
        try:
            if self.tick_count % 8 == 0:
                top_need = min(self.needs, key=self.needs.get)
                self.add_thought(
                    f"پایش بقا: نیاز «{NEED_NAMES.get(top_need, top_need)}» در {self.needs[top_need]:.0f}٪",
                    kind="survival",
                    salience=0.6,
                )

            if self.language.language_level > 20 and self.rng.random() < 0.1:
                self.add_thought(
                    f"رشد زبانی: سطح {self.language.language_level:.0f}، واژگان {self.db_stats.get('lexicon', 0)}",
                    kind="language",
                    salience=0.7,
                )
        except Exception:
            pass


# ------------------------------------------------------------
# Internet learner thread
# ------------------------------------------------------------

class InternetLearner(threading.Thread):
    def __init__(self, organism):
        super().__init__(daemon=True)
        self.organism = organism
        self.session = None
        self._init_session()

    def _init_session(self):
        if not REQUESTS_AVAILABLE:
            return

        try:
            self.session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=3, pool_maxsize=6, max_retries=0)
            self.session.mount("https://", adapter)
            self.session.mount("http://", adapter)
            self.session.headers.update({
                "User-Agent": "GrowingOrganism/1.0",
                "Accept": "application/json",
            })
        except Exception:
            self.session = None

    def run(self):
        if not REQUESTS_AVAILABLE or self.session is None:
            self.organism.internet_status = "requests نصب نیست"
            return

        time.sleep(4)
        failures = 0

        while True:
            try:
                if not self.organism.internet_enabled:
                    self.organism.internet_status = "غیرفعال"
                    time.sleep(8)
                    continue

                curiosity = self.organism.genome.get("curiosity")
                delay = clamp(45 - curiosity * 30, 8, 45)
                time.sleep(delay + random.uniform(0, 4))

                self.organism.internet_status = "جستجو..."

                extract, title = self.fetch_with_retry()

                if extract and len(extract) > 40:
                    learned = self.organism.learn_from_internet(
                        extract,
                        title=title,
                        source="internet"
                    )

                    if learned > 0:
                        self.organism.internet_status = f"✓ {title[:28]}"
                        failures = 0
                    else:
                        failures += 1
                        self.organism.internet_status = f"✗ {failures}/3"
                else:
                    failures += 1
                    if failures >= 3:
                        self.organism.internet_status = "↻ مرور حافظه"
                        failures = 0
                    else:
                        self.organism.internet_status = f"✗ {failures}/3"

            except Exception:
                self.organism.internet_status = "خطای اتصال"
                time.sleep(6)

    def fetch_with_retry(self):
        if self.session is None:
            return None, None

        for attempt in range(2):
            try:
                timeout = 12 + attempt * 6

                # 1) Related learning from current knowledge
                if random.random() < 0.55:
                    result = self.fetch_related(timeout)
                    if result:
                        return result

                # 2) Random learning
                result = self.fetch_random(timeout)
                if result:
                    return result

            except Exception:
                time.sleep(2 + attempt * 2)

        return None, None

    def fetch_related(self, timeout):
        try:
            top = self.organism.memory.top_words(15)
            if not top:
                return None, None

            word = random.choice(top)
            url = f"https://fa.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(word)}"
            r = self.session.get(url, timeout=timeout)

            if r.status_code == 200:
                j = r.json()
                extract = j.get("extract", "")
                title = j.get("title", "")

                if extract and len(extract) > 60:
                    return extract[:1800], title

        except Exception:
            pass

        return None, None

    def fetch_random(self, timeout):
        try:
            url = "https://fa.wikipedia.org/api/rest_v1/page/random/summary"
            r = self.session.get(url, timeout=timeout)

            if r.status_code == 200:
                j = r.json()
                extract = j.get("extract", "")
                title = j.get("title", "")

                if extract and len(extract) > 60:
                    return extract[:1800], title

        except Exception:
            pass

        return None, None


# ------------------------------------------------------------
# Base signals
# ------------------------------------------------------------

def build_base_signals(metrics, org):
    b = []

    try:
        b.append(metrics.get("cpu_total", 20) / 100)

        cores = metrics.get("cpu_per_core", []) or []
        b.extend([c / 100 for c in cores[:16]])

        b.extend([
            metrics.get("mem", 40) / 100,
            metrics.get("temp_norm", 0.4),
            metrics.get("battery", 100) / 100,
        ])

        now = time.time()
        b.extend([
            (now % 60) / 60,
            (now % 3600) / 3600,
            (now % 86400) / 86400,
        ])

        b.append(clamp(org.tick_interval_error * 2, 0, 1))
        b.append(org.heart.ones_density())
        b.append(clamp(org.heart_rate / 120))
        b.append(org.consciousness / 100)
        b.append(org.emotion["arousal"])
        b.append(clamp((org.emotion["valence"] + 1) / 2))

        for _, v in org.needs.items():
            b.append(v / 100)

        b.append(org.language.language_level / 100)
        b.append(org.language.grammar_coverage / 100)
        b.append(clamp(org.db_stats.get("lexicon", 0) / 5000))
        b.append(clamp(org.db_stats.get("templates", 0) / 1000))
        b.append(clamp(org.db_stats.get("sentences", 0) / 2000))
        b.append(org.genome.get("curiosity"))
        b.append(org.genome.get("language"))
        b.append(org.genome.get("memory"))
        b.append(org.genome.get("imagination"))
        b.append(org.genome.get("intuition"))
        b.append(org.genome.get("growth_drive"))

        while len(b) < 64:
            b.append(clamp(0.5 + 0.5 * math.sin(time.time() * 0.2 + len(b))))

        return [clamp(x) for x in b]

    except Exception:
        return [0.5] * 64


# ------------------------------------------------------------
# UI helpers
# ------------------------------------------------------------

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


def base_fig(title="", height=220):
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


def empty_fig(title=""):
    fig = base_fig(title, height=220)
    fig.add_annotation(text="در حال بارگذاری...", x=0, y=0, showarrow=False, font=dict(color="#64748b"))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def consciousness_label(level):
    if level < 20:
        return "خواب عمیق"
    if level < 40:
        return "رویایی"
    if level < 60:
        return "هوشیار"
    if level < 80:
        return "متمرکز"
    return "فراآگاهی"


def render_header(org):
    hw = org.hardware
    gpu = hw["gpu"]
    uptime = time.time() - org.start_time
    minutes = int(uptime // 60)
    seconds = int(uptime % 60)

    return html.Div(style={"display": "flex", "gap": "14px", "flexWrap": "wrap"}, children=[
        html.Span(f"⏱ {minutes:02d}:{seconds:02d}", style={"color": ACCENT}),
        html.Span(f"🧠 {org.neuron_total:,}"),
        html.Span(f"🖥 CPU:{hw['cpu_logical']}"),
        html.Span(f"🎮 GPU:{gpu['name'][:18]}"),
        html.Span(f"📚 واژگان:{org.db_stats.get('lexicon', 0)}"),
        html.Span(f"🧩 الگوها:{org.db_stats.get('templates', 0)}"),
        html.Span(f"🌐 {org.internet_status[:30]}"),
        html.Span("🟢 زنده", style={"color": ACCENT, "fontWeight": "bold"}),
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
    return [
        vital_card("قلب", f"{org.heart_rate:.0f} BPM", f"انسجام: {org.heart_coherence:.0f}٪", "#ff5f7a"),
        vital_card("آگاهی", f"{org.consciousness:.0f}٪", consciousness_label(org.consciousness), "#00e5ff"),
        vital_card("زبان", f"{org.language.language_level:.0f}", f"دستور: {org.language.grammar_coverage:.0f}٪", "#ffd166"),
        vital_card("نورون", f"{org.active_neurons:,}", f"{org.firing_rate:.1f}Hz", "#b388ff"),
        vital_card("واژگان", f"{org.db_stats.get('lexicon', 0)}", f"جملات: {org.db_stats.get('sentences', 0)}", "#8be9fd"),
        vital_card("احساس", org.emotion["label"], f"V:{org.emotion['valence']:+.1f} A:{org.emotion['arousal']:.2f}", "#ff8bd0"),
        vital_card("کنجکاوی", f"{org.genome.get('curiosity') * 100:.0f}٪", f"رشد: {org.genome.get('growth_drive') * 100:.0f}٪", "#00ff88"),
        vital_card("شهود", f"{org.genome.get('intuition') * 100:.0f}٪", f"قلب: {org.heart_coherence:.0f}٪", "#ff9f43"),
    ]


def render_ecg(org):
    fig = base_fig("نوار قلب فیبوناچی", height=190)
    x = list(org.heart.ecg_x)[-800:]
    y = list(org.heart.ecg)[-800:]
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=ACCENT, width=1.4)))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(range=[-1, 1.25], showgrid=False, visible=False)
    return fig


def render_consciousness(org):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=org.consciousness,
        title={"text": "آگاهی"},
        number={"suffix": "%"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "#00e5ff"},
            "bgcolor": CARD_BG,
            "steps": [
                {"range": [0, 40], "color": "#12263a"},
                {"range": [40, 75], "color": "#14424a"},
                {"range": [75, 100], "color": "#145a3c"},
            ],
        }
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=CARD_BG,
        font={"color": TEXT_COLOR},
        height=190,
        margin=dict(l=25, r=25, t=40, b=10)
    )
    return fig


def render_language_growth(org):
    fig = base_fig("رشد زبان", height=190)

    if len(org.history) == 0:
        t = [0]
        lang = [0]
    else:
        t = [h["t"] for h in org.history]
        lang = [h["language_level"] for h in org.history]

    fig.add_trace(go.Scatter(x=t, y=lang, name="سطح زبان", line=dict(color="#ffd166", width=2)))
    fig.update_yaxes(range=[0, 100])
    return fig


def render_visual(org):
    if not org.current_visual:
        fig = base_fig("🎨 تخیل بصری", height=260)
        fig.add_annotation(text="در انتظار تخیل...", x=0, y=0, showarrow=False, font=dict(color="#64748b"))
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return fig

    viz = org.current_visual
    fig = base_fig(f"🎨 {viz['concept']} | {viz['pattern']}", height=260)

    x = [p[0] for p in viz["points"]]
    y = [p[1] for p in viz["points"]]

    fig.add_trace(go.Scatter(
        x=x,
        y=y,
        mode="markers",
        marker=dict(size=viz["sizes"], color=viz["colors"], opacity=0.85),
        hovertemplate=f"{viz['concept']}<extra></extra>"
    ))

    fig.update_xaxes(range=[-4, 4], visible=False)
    fig.update_yaxes(range=[-4, 4], visible=False)
    return fig


def render_thoughts(org):
    items = list(org.thoughts)[-10:][::-1]
    color_map = {
        "alert": "#ff5555",
        "insight": "#00e5ff",
        "emotion": "#ff8bd0",
        "language": "#b388ff",
        "info": "#9fd0ff",
        "survival": "#ffd166"
    }

    children = []
    if not items:
        children.append(html.Div("...", style={"color": "#64748b"}))
    else:
        for th in items:
            color = color_map.get(th["kind"], "#9fd0ff")
            children.append(html.Div(style={
                "borderLeft": f"3px solid {color}",
                "padding": "5px 8px",
                "marginBottom": "6px",
                "backgroundColor": "#08101c",
                "borderRadius": "6px",
                "fontSize": "11px",
            }, children=[
                html.Span(th["time"], style={"color": "#64748b", "fontSize": "9px"}),
                html.Br(),
                html.Span(th["text"]),
            ]))

    return html.Div([
        html.H4("🧠 اندیشه", style={"margin": "0 0 8px 0", "color": "#9fd0ff"}),
        html.Div(children, style={"height": "260px", "overflowY": "auto"}),
    ])


def render_dialogues(org):
    dialogues = list(org.inner_dialogues)[-10:][::-1]
    children = []

    if not dialogues:
        children.append(html.Div("مکالمات درونی...", style={"color": "#64748b"}))
    else:
        for d in dialogues:
            children.append(html.Div(style={
                "borderLeft": "3px solid #b388ff",
                "padding": "6px 10px",
                "marginBottom": "8px",
                "backgroundColor": "#08101c",
                "borderRadius": "6px",
            }, children=[
                html.Div(d["speaker"], style={"color": "#ffd166", "fontSize": "11px", "fontWeight": "bold"}),
                html.Div(d["text"], style={"color": "#e0e0ff", "fontSize": "12px", "marginTop": "3px"}),
            ]))

    return html.Div([
        html.H4("💭 مکالمات درونی", style={"margin": "0 0 8px 0", "color": "#b388ff"}),
        html.Div(children, style={"height": "260px", "overflowY": "auto"}),
    ])


def render_needs(org):
    children = [html.H4("🔋 نیازها", style={"margin": "0 0 8px 0", "color": "#9fd0ff"})]

    for key, label in NEED_NAMES.items():
        val = org.needs.get(key, 50)
        color = "#00ff88" if val > 70 else ("#ffd166" if val > 40 else "#ff5555")

        children.append(html.Div(style={"marginBottom": "7px"}, children=[
            html.Div(f"{label}: {val:.0f}٪", style={"fontSize": "10px", "marginBottom": "2px"}),
            html.Div(style={
                "height": "6px",
                "backgroundColor": "#08101c",
                "borderRadius": "3px",
                "overflow": "hidden"
            }, children=[
                html.Div(style={
                    "width": f"{val:.0f}%",
                    "height": "100%",
                    "backgroundColor": color
                })
            ])
        ]))

    return html.Div(children)


def render_genome(org):
    profile = org.genome.profile(12)
    children = [html.H4("🧬 ژنوم", style={"margin": "0 0 8px 0", "color": "#9fd0ff"})]

    for name, expr in profile:
        children.append(html.Div(style={"marginBottom": "6px"}, children=[
            html.Div(f"{name}: {expr * 100:.0f}٪", style={"fontSize": "10px", "marginBottom": "2px"}),
            html.Div(style={
                "height": "6px",
                "backgroundColor": "#08101c",
                "borderRadius": "3px",
                "overflow": "hidden"
            }, children=[
                html.Div(style={
                    "width": f"{expr * 100:.0f}%",
                    "height": "100%",
                    "backgroundColor": "#b388ff"
                })
            ])
        ]))

    return html.Div(children)


def render_internet(org):
    status = org.internet_status

    if "✓" in status:
        color = ACCENT
    elif "✗" in status or "خطا" in status:
        color = "#ff5555"
    else:
        color = "#9fd0ff"

    children = [
        html.H4("🌐 یادگیری", style={"margin": "0 0 8px 0", "color": "#9fd0ff"}),
        html.Div(status, style={"fontSize": "11px", "marginBottom": "5px", "color": color, "fontWeight": "bold"}),
        html.Div(f"آخرین: {org.last_learned_title[:35] or '—'}", style={"fontSize": "10px", "marginBottom": "4px"}),
        html.Div(f"توکن‌ها: {org.learned_tokens_total:,}", style={"fontSize": "10px", "marginBottom": "4px"}),
        html.Div(f"مفاهیم: {org.db_stats.get('lexicon', 0):,}", style={"fontSize": "10px", "marginBottom": "4px"}),
        html.Div(f"جملات: {org.db_stats.get('sentences', 0):,}", style={"fontSize": "10px"}),
    ]

    return html.Div(children)


def render_imagination(org):
    items = list(org.imagination_stream)[-8:][::-1]
    children = []

    if not items:
        children.append(html.Div("...", style={"color": "#64748b"}))
    else:
        for item in items:
            children.append(html.Div(style={
                "borderLeft": "3px solid #8be9fd",
                "padding": "6px 10px",
                "marginBottom": "8px",
                "backgroundColor": "#08101c",
                "borderRadius": "6px",
                "fontSize": "12px",
                "lineHeight": "1.6",
            }, children=[html.Span(item, style={"color": "#e0e0ff"})]))

    return html.Div([
        html.H4("🌌 تخیل", style={"margin": "0 0 8px 0", "color": "#8be9fd"}),
        html.Div(children, style={"height": "260px", "overflowY": "auto"}),
    ])


def safe_fig(fn, org, title):
    try:
        return fn(org)
    except Exception:
        return empty_fig(title)


def safe_div(fn, org, fallback):
    try:
        return fn(org)
    except Exception as e:
        return html.Div(f"⚠ {fallback}: {str(e)[:60]}", style={"color": "#ff5555"})


# ------------------------------------------------------------
# Dash app
# ------------------------------------------------------------

app = Dash(__name__)
app.title = "ارگانیسم رشدکننده"
app.config.suppress_callback_exceptions = True

ORGANISM = DigitalOrganism()
INTERNET_LEARNER = InternetLearner(ORGANISM)
INTERNET_LEARNER.start()

app.layout = html.Div(style={
    "backgroundColor": PAGE_BG,
    "color": TEXT_COLOR,
    "minHeight": "100vh",
    "padding": "12px",
    "fontFamily": "Tahoma, Arial, sans-serif",
}, children=[

    dcc.Interval(id="life-interval", interval=2000, disabled=False),

    html.H1("🌱 ارگانیسم رشدکننده", style={
        "margin": "0 0 10px 0",
        "fontSize": "22px",
        "color": "#eaffff"
    }),

    html.Div(id="header-info", style={**CARD_STYLE, "marginBottom": "10px"}),

    html.Div(id="vital-cards", style={
        "display": "grid",
        "gridTemplateColumns": "repeat(auto-fit, minmax(160px, 1fr))",
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
            dcc.Graph(id="ecg-graph", config={"displayModeBar": False})
        ]),
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="consciousness-gauge", config={"displayModeBar": False})
        ]),
    ]),

    html.Div(style={
        "display": "grid",
        "gridTemplateColumns": "1fr 1fr",
        "gap": "10px",
        "marginBottom": "10px"
    }, children=[
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="language-graph", config={"displayModeBar": False})
        ]),
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="visual-graph", config={"displayModeBar": False})
        ]),
    ]),

    html.Div(style={
        "display": "grid",
        "gridTemplateColumns": "2fr 1fr 1fr",
        "gap": "10px",
        "marginBottom": "10px"
    }, children=[
        html.Div(style=CARD_STYLE, children=[
            html.H4("🗣 گفتگو با ارگانیسم", style={"margin": "0 0 8px 0", "color": "#9fd0ff"}),
            html.Div(style={"display": "flex", "gap": "8px"}, children=[
                dcc.Input(
                    id="chat-input",
                    type="text",
                    placeholder="با ارگانیسم صحبت کن...",
                    debounce=True,
                    style={
                        "flex": "1",
                        "backgroundColor": "#08101c",
                        "color": TEXT_COLOR,
                        "border": "1px solid #1b2a44",
                        "borderRadius": "8px",
                        "padding": "8px"
                    }
                ),
                html.Button("ارسال", id="chat-btn", style={
                    "backgroundColor": "#123",
                    "color": ACCENT,
                    "border": "1px solid #2a5",
                    "borderRadius": "8px",
                    "padding": "8px 12px",
                    "cursor": "pointer"
                })
            ]),
            html.Div(id="chat-output", style={
                "marginTop": "10px",
                "height": "180px",
                "overflowY": "auto",
                "fontSize": "12px"
            })
        ]),
        html.Div(id="internet-panel", style=CARD_STYLE),
        html.Div(id="needs-panel", style=CARD_STYLE),
    ]),

    html.Div(style={
        "display": "grid",
        "gridTemplateColumns": "1fr 1fr 1fr",
        "gap": "10px",
        "marginBottom": "10px"
    }, children=[
        html.Div(id="thoughts-panel", style=CARD_STYLE),
        html.Div(id="dialogues-panel", style=CARD_STYLE),
        html.Div(style=CARD_STYLE, children=[
            html.Div(id="genome-panel"),
            html.Hr(style={"borderColor": "#1b2a44"}),
            html.Div(id="imagination-panel"),
        ]),
    ]),

    html.Div(id="speech-text", style={"display": "none"}),
    html.Div(id="speech-client", style={"display": "none"}),
])


@app.callback(
    [
        Output("chat-output", "children"),
        Output("speech-text", "children"),
    ],
    [
        Input("chat-btn", "n_clicks"),
        Input("chat-input", "n_submit"),
    ],
    State("chat-input", "value")
)
def chat_callback(n_clicks, n_submit, value):
    if not value:
        return no_update, no_update

    if not n_clicks and not n_submit:
        return no_update, no_update

    try:
        response, analysis = ORGANISM.chat(value)

        known = analysis.get("known", 0)
        tokens = analysis.get("tokens", [])
        valence = analysis.get("valence", 0.0)

        resp_html = html.Div([
            html.Div(f"🗣 {response}", style={
                "color": ACCENT,
                "fontWeight": "bold",
                "marginBottom": "8px"
            }),
            html.Div(
                f"توکن: {len(tokens)} | شناخته: {known} | احساس: {valence:+.2f}",
                style={"color": "#9fd0ff", "marginBottom": "8px"}
            ),
            html.Div(
                f"سطح زبان ارگانیسم: {ORGANISM.language.language_level:.0f} | "
                f"واژگان: {ORGANISM.db_stats.get('lexicon', 0)}",
                style={"color": "#64748b", "fontSize": "10px"}
            ),
        ])

        return resp_html, response

    except Exception as e:
        return html.Div(f"⚠ خطا در گفتگو: {str(e)[:80]}", style={"color": "#ff5555"}), no_update


@app.callback(
    [
        Output("header-info", "children"),
        Output("vital-cards", "children"),
        Output("ecg-graph", "figure"),
        Output("consciousness-gauge", "figure"),
        Output("language-graph", "figure"),
        Output("visual-graph", "figure"),
        Output("thoughts-panel", "children"),
        Output("dialogues-panel", "children"),
        Output("needs-panel", "children"),
        Output("genome-panel", "children"),
        Output("internet-panel", "children"),
        Output("imagination-panel", "children"),
    ],
    Input("life-interval", "n_intervals")
)
def update_life(n):
    try:
        ORGANISM.tick()
    except Exception as e:
        try:
            ORGANISM.internet_status = f"خطای tick: {str(e)[:40]}"
        except Exception:
            pass

    return (
        safe_div(render_header, ORGANISM, "header"),
        safe_div(render_vitals, ORGANISM, "vitals"),
        safe_fig(render_ecg, ORGANISM, "ECG"),
        safe_fig(render_consciousness, ORGANISM, "آگاهی"),
        safe_fig(render_language_growth, ORGANISM, "رشد زبان"),
        safe_fig(render_visual, ORGANISM, "تخیل بصری"),
        safe_div(render_thoughts, ORGANISM, "اندیشه"),
        safe_div(render_dialogues, ORGANISM, "مکالمات"),
        safe_div(render_needs, ORGANISM, "نیازها"),
        safe_div(render_genome, ORGANISM, "ژنوم"),
        safe_div(render_internet, ORGANISM, "یادگیری"),
        safe_div(render_imagination, ORGANISM, "تخیل"),
    )


app.clientside_callback(
    """
    function(text) {
      if (text && text.length > 0 && 'speechSynthesis' in window) {
        try {
          window.speechSynthesis.cancel();
          let u = new SpeechSynthesisUtterance(text);
          u.lang = 'fa-IR';
          u.rate = 1.0;
          window.speechSynthesis.speak(u);
        } catch (e) {}
      }
      return window.dash_clientside.no_update;
    }
    """,
    Output("speech-client", "children"),
    Input("speech-text", "children")
)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050, debug=False, use_reloader=False, threaded=True)