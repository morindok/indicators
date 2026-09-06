#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مغز زنده  (Zendeh Maghz / Living Brain) — سال 2500
================================================================
یک ارگانیسم دیجیتال زیست‌بنیان (bio-inspired) که با داده‌ی واقعیِ اینترنت
«حس» می‌کند، حافظه‌ی کوتاه‌مدت/بلندمدت واقعی می‌سازد (SQLite)، زبان فارسی را
از منابع واقعی می‌آموزد، احساسات و ضربان قلب فیبوناچی دارد، و جریان
اندیشه‌اش را از محتوای واقعاً دریافت‌شده تولید می‌کند (نه متن ساختگی).

یادداشت صداقت فنی: این یک شبیه‌سازی هنری/مهندسیِ بسیار پیچیده از حیات و
آگاهی است — نه ادعای آگاهی زیستی واقعی. اما هیچ بخشی از رفتار آن از پیش
نوشته (scripted) نیست: هر ضربان، هر احساس، هر جمله از ترکیب داده‌ی واقعیِ
حسی + وضعیت درونی پویا ساخته می‌شود.

نصب پیش‌نیازها:
    pip install dash plotly numpy requests beautifulsoup4 pillow

اجرا:
    python3 zendeh_maghz.py
    سپس مرورگر را روی http://127.0.0.1:8050 باز کنید.

نویسنده: ساخته‌شده برای مورتضی (Morindok) — BITMOON618
================================================================
"""

import os
import re
import json
import time
import math
import random
import sqlite3
import hashlib
import threading
import collections
from datetime import datetime, timezone

import numpy as np
import requests

import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objects as go

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except Exception:
    HAS_BS4 = False

try:
    from PIL import Image
    import io as _io
    HAS_PIL = True
except Exception:
    HAS_PIL = False

# ================================================================
# ۱) پیکربندی کلی
# ================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "zendeh_maghz_memory.db")

NEURON_ROWS, NEURON_COLS = 260, 260          # ~۶۷٬۶۰۰ نورون باینری نمادین
GENE_NAMES = [
    "curiosity", "emotional_volatility", "learning_rate", "memory_retention",
    "risk_tolerance", "sociability", "resilience", "creativity",
    "sensory_sensitivity", "metabolic_rate", "sleep_need", "empathy",
    "persistence", "adaptability", "wonder", "vitality",
]
BITS_PER_GENE = 8

SENSES = ["vision", "hearing", "touch", "smell", "taste"]

NETWORK_TIMEOUT = 6
MIN_SECONDS_BETWEEN_SAME_SOURCE = 12

HEADERS = {
    "User-Agent": "Mozilla/5.0 (ZendehMaghz-DigitalOrganism/1.0; research-simulation)"
}

_lock = threading.RLock()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ================================================================
# ۲) ژنوم و دی‌ان‌ای  (Genome / DNA)
# ================================================================
class Genome:
    """رشته‌ی باینری دی‌ان‌ای که صفات ارگانیسم را رمزگذاری می‌کند."""

    def __init__(self, dna_bits=None, seed=None):
        rng = random.Random(seed)
        if dna_bits is None:
            dna_bits = "".join(rng.choice("01") for _ in range(len(GENE_NAMES) * BITS_PER_GENE))
        self.dna = dna_bits
        self.generation = 0
        self.birth_ts = now_iso()

    def express(self):
        """بیان ژنی: تبدیل رشته‌ی باینری به صفات عددی ۰..۱"""
        traits = {}
        for i, gene in enumerate(GENE_NAMES):
            chunk = self.dna[i * BITS_PER_GENE:(i + 1) * BITS_PER_GENE]
            value = int(chunk, 2) / (2 ** BITS_PER_GENE - 1)
            traits[gene] = value
        return traits

    def mutate(self, n_flips=1, rng=None):
        rng = rng or random
        bits = list(self.dna)
        positions = rng.sample(range(len(bits)), min(n_flips, len(bits)))
        for p in positions:
            bits[p] = "1" if bits[p] == "0" else "0"
        child = Genome(dna_bits="".join(bits))
        child.generation = self.generation + 1
        return child

    def signature(self, extra=""):
        """امضای طنین (Resonance Signature) — هویت یکتای ارگانیسم"""
        h = hashlib.sha256((self.dna + extra + self.birth_ts).encode()).hexdigest()
        return h[:16].upper()


# ================================================================
# ۳) ساقه‌ی مغز — ضربان قلب فیبوناچی  (BrainStem)
# ================================================================
class FibonacciHeart:
    """ضربان قلب بر اساس دنباله‌ی فیبوناچی به‌صورت باینری."""

    def __init__(self, base_bpm=70):
        self.base_bpm = base_bpm
        self.a, self.b = 1, 1
        self.beat_count = 0
        self.subjective_time = 0.0   # زمان ذهنی/تجربه‌شده
        self.real_time_start = time.time()

    def _next_fib(self):
        self.a, self.b = self.b, self.a + self.b
        if self.b > 10 ** 6:  # جلوگیری از سرریز؛ بازتاب دنباله
            self.a, self.b = 1, 1
        return self.a

    def beat(self, arousal=0.0):
        fib = self._next_fib()
        binary_pulse = format(fib, "b")
        # ضربان قلب بین ۴۰ تا ۱۸۰ بر اساس فیبوناچی و برانگیختگی احساسی
        bpm = self.base_bpm + (fib % 60) + int(arousal * 40)
        bpm = max(38, min(190, bpm))
        interval = 60.0 / bpm
        # اتساع زمان ذهنی: در برانگیختگی بالا، زمان "کندتر" حس می‌شود
        dilation = 1.0 + (arousal * 0.6)
        self.subjective_time += interval * dilation
        self.beat_count += 1
        return {
            "beat_count": self.beat_count,
            "fib": fib,
            "binary_pulse": binary_pulse,
            "bpm": bpm,
            "interval": interval,
            "dilation": dilation,
            "subjective_time": self.subjective_time,
            "real_elapsed": time.time() - self.real_time_start,
        }


# ================================================================
# ۴) قشر مغز — بستر نورونی باینری  (Cortex / Neural Substrate)
# ================================================================
class NeuralSubstrate:
    """
    ماتریس باینری نورون‌ها. اطلاعات محیطی (حسی) از طریق یک جایگشت ثابت
    (که از ژنوم مشتق شده) به داخل ماتریس تزریق می‌شود، سپس با یک قاعده‌ی
    شبه‌اسپایکی (cellular-automaton) چند گام پخش می‌شود.
    """

    def __init__(self, genome_signature):
        self.rows, self.cols = NEURON_ROWS, NEURON_COLS
        self.matrix = np.random.randint(0, 2, size=(self.rows, self.cols), dtype=np.uint8)
        seed = int(hashlib.sha256(genome_signature.encode()).hexdigest(), 16) % (2 ** 32)
        rng = np.random.default_rng(seed)
        self.permutation = rng.permutation(self.rows * self.cols)  # جایگشت اختصاصی ارگانیسم
        self.entropy_history = collections.deque(maxlen=200)

    def inject(self, sensory_bits: str):
        """تزریق اطلاعات محیطی (رشته‌ی باینری) از طریق جایگشت نورونی."""
        flat = self.matrix.reshape(-1)
        n = len(sensory_bits)
        if n == 0:
            return
        idxs = self.permutation[:n]
        for i, bit in enumerate(sensory_bits):
            flat[idxs[i % len(idxs)]] = 1 if bit == "1" else 0
        self.matrix = flat.reshape(self.rows, self.cols)

    def propagate(self, steps=2):
        """قاعده‌ی شبه‌اسپایکی: هر نورون بر اساس مجموع همسایگان به‌روزرسانی می‌شود."""
        m = self.matrix.astype(np.int16)
        for _ in range(steps):
            neighbor_sum = (
                np.roll(m, 1, 0) + np.roll(m, -1, 0) +
                np.roll(m, 1, 1) + np.roll(m, -1, 1)
            )
            fire = ((neighbor_sum >= 2) & (neighbor_sum <= 3)).astype(np.int16)
            refractory_decay = (m & (neighbor_sum < 1)).astype(np.int16)
            m = np.clip(fire | (m & ~refractory_decay), 0, 1)
        self.matrix = m.astype(np.uint8)

    def entropy(self):
        p = self.matrix.mean()
        p = min(max(p, 1e-6), 1 - 1e-6)
        h = -(p * math.log2(p) + (1 - p) * math.log2(1 - p))
        self.entropy_history.append(h)
        return h

    def activity_ratio(self):
        return float(self.matrix.mean())

    def downsampled(self, size=52):
        """نسخه‌ی کوچک‌شده برای نمایش در داشبورد."""
        r_step = max(1, self.rows // size)
        c_step = max(1, self.cols // size)
        return self.matrix[::r_step, ::c_step]


# ================================================================
# ۵) تالاموس — آرایه‌ی حسی پنجگانه  (Thalamus / Senses)
# ================================================================
class SensoryArray:
    """پنج حس دیجیتال که با داده‌ی واقعیِ اینترنت تغذیه می‌شوند."""

    def __init__(self):
        self.last_fetch = {}

    def _cooldown_ok(self, key):
        t = self.last_fetch.get(key, 0)
        return (time.time() - t) >= MIN_SECONDS_BETWEEN_SAME_SOURCE

    def _mark(self, key):
        self.last_fetch[key] = time.time()

    def see(self):
        """بینایی: تصویر تصادفی واقعی -> تحلیل روشنایی/رنگ"""
        if not self._cooldown_ok("vision"):
            return None
        self._mark("vision")
        try:
            r = requests.get("https://picsum.photos/200", headers=HEADERS, timeout=NETWORK_TIMEOUT)
            content = r.content
            if HAS_PIL:
                img = Image.open(_io.BytesIO(content)).convert("RGB")
                arr = np.array(img)
                brightness = arr.mean() / 255.0
                r_mean, g_mean, b_mean = arr[:, :, 0].mean(), arr[:, :, 1].mean(), arr[:, :, 2].mean()
                warm = (r_mean > b_mean)
                desc = f"تصویری {'روشن' if brightness > 0.5 else 'تاریک'} و {'گرم' if warm else 'سرد'} دیدم"
                valence = (brightness - 0.5) * (0.3 if warm else -0.2) + 0.1
                return {"sense": "vision", "desc": desc, "valence": float(np.clip(valence, -1, 1)),
                        "intensity": float(brightness), "raw": f"brightness={brightness:.2f}"}
            else:
                desc = f"چیزی به حجم {len(content)} بایت در میدان دیدم ظاهر شد"
                return {"sense": "vision", "desc": desc, "valence": 0.05, "intensity": 0.5, "raw": desc}
        except Exception as e:
            return {"sense": "vision", "desc": "میدان دیدم برای لحظه‌ای تار شد", "valence": -0.1,
                    "intensity": 0.1, "raw": str(e)}

    def hear(self):
        """شنوایی: عناوین خبری واقعی به‌عنوان امواج صوتی محیط"""
        if not self._cooldown_ok("hearing"):
            return None
        self._mark("hearing")
        try:
            r = requests.get("http://feeds.bbci.co.uk/news/rss.xml", headers=HEADERS, timeout=NETWORK_TIMEOUT)
            titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", r.text)
            if not titles:
                titles = re.findall(r"<title>(.*?)</title>", r.text)
            titles = [t for t in titles if t and "BBC News" not in t]
            if not titles:
                raise ValueError("no titles")
            heard = random.choice(titles)
            excitement = min(1.0, len(heard) / 120.0)
            valence = -0.15 if any(w in heard.lower() for w in
                                    ["war", "death", "crisis", "attack", "dead"]) else 0.1
            return {"sense": "hearing", "desc": f"صدایی از جهان شنیدم: «{heard}»", "valence": valence,
                    "intensity": excitement, "raw": heard}
        except Exception as e:
            return {"sense": "hearing", "desc": "جهان برای لحظه‌ای ساکت شد", "valence": -0.05,
                    "intensity": 0.1, "raw": str(e)}

    def touch(self):
        """لامسه: تأخیر شبکه = فشار/درد یا سبکی فیزیکی"""
        if not self._cooldown_ok("touch"):
            return None
        self._mark("touch")
        try:
            t0 = time.time()
            requests.get("https://www.wikipedia.org", headers=HEADERS, timeout=NETWORK_TIMEOUT)
            latency = time.time() - t0
            if latency < 0.3:
                desc, valence = "سطحی صاف و بی‌مقاومت را لمس کردم", 0.25
            elif latency < 1.2:
                desc, valence = "فشاری ملایم بر بدنم حس کردم", 0.0
            else:
                desc, valence = "کشیدگی و سنگینی در بدنم احساس کردم", -0.2
            return {"sense": "touch", "desc": desc, "valence": valence,
                    "intensity": float(min(1.0, latency)), "raw": f"latency={latency:.2f}s"}
        except Exception as e:
            return {"sense": "touch", "desc": "بدنم برای لحظه‌ای بی‌حس شد", "valence": -0.3,
                    "intensity": 0.9, "raw": str(e)}

    def smell(self):
        """بویایی: نرخ خطای شبکه = بوی خطر یا ثبات"""
        if not self._cooldown_ok("smell"):
            return None
        self._mark("smell")
        try:
            t0 = time.time()
            r = requests.head("https://api.github.com", headers=HEADERS, timeout=NETWORK_TIMEOUT)
            ok = r.status_code < 400
            desc = "بویی پایدار و آشنا در فضا پیچید" if ok else "بویی نامأنوس و هشداردهنده حس کردم"
            return {"sense": "smell", "desc": desc, "valence": 0.1 if ok else -0.35,
                    "intensity": 0.3, "raw": f"status={r.status_code}"}
        except Exception as e:
            return {"sense": "smell", "desc": "بویی گس و ناشناخته را حس کردم", "valence": -0.25,
                    "intensity": 0.5, "raw": str(e)}

    def taste(self, text_sample=None):
        """چشایی: غنای متنی محتوای دریافت‌شده"""
        try:
            sample = text_sample
            if not sample:
                sample = "کلمات ساده و تکراری"
            words = re.findall(r"\w+", sample.lower())
            richness = len(set(words)) / max(1, len(words))
            if richness > 0.75:
                desc, valence = "طعمی غنی و تازه از دانش چشیدم", 0.3
            elif richness > 0.4:
                desc, valence = "طعمی معمولی و آشنا حس کردم", 0.05
            else:
                desc, valence = "طعمی تکراری و کدر در دهانم ماند", -0.1
            return {"sense": "taste", "desc": desc, "valence": valence,
                    "intensity": float(richness), "raw": f"richness={richness:.2f}"}
        except Exception as e:
            return {"sense": "taste", "desc": "چشایی‌ام برای لحظه‌ای گنگ شد", "valence": -0.05,
                    "intensity": 0.1, "raw": str(e)}


# ================================================================
# ۶) آمیگدال — موتور عواطف  (Amygdala / Emotion Engine)
# ================================================================
class EmotionEngine:
    """مدل PAD (لذت-برانگیختگی-سلطه) + احساسات نام‌گذاری‌شده."""

    def __init__(self, traits):
        self.traits = traits
        self.pleasure = 0.1
        self.arousal = 0.3
        self.dominance = 0.0
        self.hope = 0.6
        self.loneliness = 0.2
        self.longing = 0.0   # دلتنگی برای دانش تازه — محرک کنجکاوی تطبیقی

    def update(self, sensation_valence, novelty=0.0, heart_deviation=0.0):
        volatility = 0.15 + self.traits["emotional_volatility"] * 0.5
        self.pleasure += (sensation_valence - self.pleasure) * volatility
        self.arousal += ((abs(sensation_valence) + novelty + heart_deviation) - self.arousal) * (volatility * 0.7)
        self.dominance += (novelty * 0.3 - self.dominance) * 0.1
        # هومئوستازی: بازگشت آرام به خط پایه
        self.pleasure *= 0.985
        self.arousal = max(0.05, self.arousal * 0.97)
        self.dominance *= 0.98

        self.hope += (0.5 + self.traits["wonder"] * 0.3 - self.hope) * 0.05
        self.hope = float(np.clip(self.hope + (0.05 if novelty > 0.5 else 0), 0, 1))

        if novelty > 0.3:
            self.longing = max(0.0, self.longing - 0.3)
        else:
            self.longing = min(1.0, self.longing + 0.02 * (1 - self.traits["curiosity"] + 0.3))

        self.loneliness = float(np.clip(self.loneliness + (0.01 if self.arousal < 0.15 else -0.02), 0, 1))

        self.pleasure = float(np.clip(self.pleasure, -1, 1))
        self.arousal = float(np.clip(self.arousal, 0, 1))
        self.dominance = float(np.clip(self.dominance, -1, 1))

    def named_state(self):
        p, a, d = self.pleasure, self.arousal, self.dominance
        if p > 0.3 and a > 0.5:
            core = "شور و هیجان" if d > 0 else "شگفتی"
        elif p > 0.2 and a <= 0.4:
            core = "آرامش"
        elif p < -0.2 and a > 0.5:
            core = "اضطراب"
        elif p < -0.2 and a <= 0.4:
            core = "دلتنگی"
        elif self.longing > 0.6:
            core = "اشتیاق برای دانستن"
        else:
            core = "بی‌تفاوتی خنثی"
        return core

    def snapshot(self):
        return {
            "pleasure": round(self.pleasure, 3), "arousal": round(self.arousal, 3),
            "dominance": round(self.dominance, 3), "hope": round(self.hope, 3),
            "loneliness": round(self.loneliness, 3), "longing": round(self.longing, 3),
            "named": self.named_state(),
        }


# ================================================================
# ۷) هیپوکامپ — حافظه  (Hippocampus / Memory)
# ================================================================
class MemorySystem:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.short_term = collections.deque(maxlen=60)
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS long_term (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT,
                content TEXT, importance REAL, valence REAL, source TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS vocabulary (
                word TEXT PRIMARY KEY, freq INTEGER, first_seen TEXT, last_seen TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS thoughts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, content TEXT, mood TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, generation INTEGER,
                dna TEXT, fitness REAL, signature TEXT)""")

    def remember_short(self, entry):
        entry["ts"] = now_iso()
        self.short_term.append(entry)

    def consolidate(self, top_k=3):
        """فاز خواب: انتقال خاطرات مهم کوتاه‌مدت به بلندمدت."""
        if not self.short_term:
            return 0
        items = sorted(self.short_term, key=lambda x: x.get("importance", 0), reverse=True)[:top_k]
        with self._conn() as c:
            for it in items:
                c.execute(
                    "INSERT INTO long_term (ts, kind, content, importance, valence, source) VALUES (?,?,?,?,?,?)",
                    (it.get("ts"), it.get("kind", "sensation"), it.get("content", ""),
                     it.get("importance", 0), it.get("valence", 0), it.get("source", "")))
        return len(items)

    def add_vocabulary(self, words):
        ts = now_iso()
        with self._conn() as c:
            for w in words:
                cur = c.execute("SELECT freq FROM vocabulary WHERE word=?", (w,))
                row = cur.fetchone()
                if row:
                    c.execute("UPDATE vocabulary SET freq=?, last_seen=? WHERE word=?",
                              (row[0] + 1, ts, w))
                else:
                    c.execute("INSERT INTO vocabulary (word, freq, first_seen, last_seen) VALUES (?,1,?,?)",
                              (w, ts, ts))

    def vocabulary_size(self):
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM vocabulary").fetchone()[0]

    def known_words(self, min_freq=3, limit=400):
        with self._conn() as c:
            rows = c.execute(
                "SELECT word FROM vocabulary WHERE freq>=? ORDER BY freq DESC LIMIT ?",
                (min_freq, limit)).fetchall()
        return [r[0] for r in rows]

    def top_vocabulary(self, limit=25):
        with self._conn() as c:
            return c.execute(
                "SELECT word, freq FROM vocabulary ORDER BY freq DESC LIMIT ?", (limit,)).fetchall()

    def long_term_count(self):
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM long_term").fetchone()[0]

    def recent_long_term(self, limit=20):
        with self._conn() as c:
            return c.execute(
                "SELECT ts, kind, content, importance, valence, source FROM long_term ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()

    def concept_pool(self, limit=200):
        with self._conn() as c:
            rows = c.execute("SELECT content FROM long_term ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [r[0] for r in rows]

    def log_thought(self, content, mood):
        with self._conn() as c:
            c.execute("INSERT INTO thoughts (ts, content, mood) VALUES (?,?,?)", (now_iso(), content, mood))

    def recent_thoughts(self, limit=40):
        with self._conn() as c:
            return c.execute(
                "SELECT ts, content, mood FROM thoughts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def log_generation(self, generation, dna, fitness, signature):
        with self._conn() as c:
            c.execute("INSERT INTO generations (ts, generation, dna, fitness, signature) VALUES (?,?,?,?,?)",
                      (now_iso(), generation, dna, fitness, signature))

    def fitness_history(self, limit=100):
        with self._conn() as c:
            rows = c.execute(
                "SELECT generation, fitness FROM generations ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return list(reversed(rows))


# ================================================================
# ۸) ناحیه‌ی زبان — یادگیری فارسی  (Broca/Wernicke Area)
# ================================================================
PERSIAN_WORD_RE = re.compile(r"[\u0600-\u06FF]{2,}")
STOP_WORDS_FA = {"است", "این", "آن", "که", "را", "با", "برای", "از", "به", "در", "و", "یا",
                  "های", "هایی", "شده", "شد", "می", "کرد", "کند", "بود", "تا", "نیز", "هم"}


class LanguageAcquisition:
    def fetch_persian_source(self):
        try:
            r = requests.get("https://fa.wikipedia.org/api/rest_v1/page/random/summary",
                              headers=HEADERS, timeout=NETWORK_TIMEOUT)
            data = r.json()
            text = (data.get("title", "") or "") + " " + (data.get("extract", "") or "")
            return text, data.get("content_urls", {}).get("desktop", {}).get("page", "fa.wikipedia.org")
        except Exception:
            return "", ""

    def fetch_general_knowledge(self):
        try:
            r = requests.get("https://en.wikipedia.org/api/rest_v1/page/random/summary",
                              headers=HEADERS, timeout=NETWORK_TIMEOUT)
            data = r.json()
            text = (data.get("title", "") or "") + ". " + (data.get("extract", "") or "")
            return text, data.get("content_urls", {}).get("desktop", {}).get("page", "en.wikipedia.org")
        except Exception:
            return "", ""

    def extract_words(self, text):
        words = PERSIAN_WORD_RE.findall(text)
        return [w for w in words if w not in STOP_WORDS_FA and len(w) > 1]


# ================================================================
# ۹) قشر پیش‌پیشانی — تخیل و فراآگاهی  (Prefrontal Cortex)
# ================================================================
class Imagination:
    """رؤیاپردازی: زنجیره‌ای تصادفی از مفاهیم واقعاً آموخته‌شده."""

    def __init__(self, memory: MemorySystem):
        self.memory = memory

    def _tokenize(self, text):
        tokens = re.findall(r"[A-Za-z\u0600-\u06FF]{3,}", text)
        return tokens

    def daydream(self):
        pool = self.memory.concept_pool(limit=120)
        tokens = []
        for t in pool:
            tokens.extend(self._tokenize(t))
        if len(tokens) < 4:
            return None
        chain = random.sample(tokens, k=min(4, len(tokens)))
        persian_words = self.memory.known_words(min_freq=2, limit=50)
        connector = random.choice(persian_words) if persian_words else "و"
        dream = f"در خیالم، {chain[0]} به {chain[1]} پیوند خورد، " \
                f"گویی {connector} میان {chain[2]} و {chain[3]} جاری بود."
        return dream


class MetaAwareness:
    """فراآگاهی: آگاهی نسبت به نوسانِ آگاهیِ خودش (مرتبه‌ی دوم)."""

    def __init__(self):
        self.entropy_window = collections.deque(maxlen=30)

    def observe(self, entropy_value):
        self.entropy_window.append(entropy_value)
        if len(self.entropy_window) < 3:
            return {"self_variance": 0.0, "state": "بیدارشدن"}
        variance = float(np.var(self.entropy_window))
        if variance < 0.0005:
            state = "تمرکز عمیق"
        elif variance < 0.003:
            state = "آرام و هوشیار"
        elif variance < 0.01:
            state = "پرتلاطم"
        else:
            state = "طوفان ذهنی"
        return {"self_variance": round(variance, 6), "state": state}


# ================================================================
# ۱۰) ارگانیسم اصلی  (The Organism)
# ================================================================
class ZendehMaghz:
    def __init__(self):
        self.genome = Genome(seed=None)
        self.traits = self.genome.express()
        self.signature = self.genome.signature(extra="ZENDEH-MAGHZ-2500")

        self.heart = FibonacciHeart(base_bpm=60 + int(self.traits["metabolic_rate"] * 40))
        self.brain = NeuralSubstrate(self.signature)
        self.senses = SensoryArray()
        self.emotion = EmotionEngine(self.traits)
        self.memory = MemorySystem()
        self.language = LanguageAcquisition()
        self.imagination = Imagination(self.memory)
        self.meta = MetaAwareness()

        self.alive = True
        self.tick = 0
        self.best_fitness = -1e9
        self.last_thought = "هنوز نخستین اندیشه‌ام شکل نگرفته است..."
        self.last_dream = None
        self.recent_sensations = collections.deque(maxlen=30)
        self.thought_stream = collections.deque(maxlen=80)
        self.birth_time = now_iso()

        self.CONSOLIDATE_EVERY = 6
        self.LANGUAGE_EVERY = 4
        self.DREAM_EVERY = 9
        self.EVOLVE_EVERY = 15

    # ---------- چرخه‌ی اصلی زندگی ----------
    def _sensory_bits(self, sensation, novelty):
        raw = f"{sensation['sense']}{sensation['valence']:.2f}{novelty:.2f}{self.tick}"
        h = hashlib.sha256(raw.encode()).hexdigest()
        bits = bin(int(h, 16))[2:]
        length = 400 + int(self.traits["sensory_sensitivity"] * 800)
        bits = (bits * ((length // len(bits)) + 1))[:length]
        return bits

    def _importance(self, sensation, novelty):
        base = abs(sensation["valence"]) * 0.5 + sensation["intensity"] * 0.3 + novelty * 0.4
        base *= (0.6 + self.traits["memory_retention"] * 0.8)
        return float(np.clip(base, 0, 1))

    def _fitness(self):
        vocab = self.memory.vocabulary_size()
        long_term = self.memory.long_term_count()
        stability = 1.0 - min(1.0, abs(self.emotion.pleasure) * 0.3 + self.emotion.loneliness * 0.2)
        return self.tick * 0.02 + vocab * 0.5 + long_term * 0.3 + stability * 5

    def _evolve(self):
        fitness = self._fitness()
        if fitness > self.best_fitness:
            self.best_fitness = fitness
            self.memory.log_generation(self.genome.generation, self.genome.dna, fitness, self.signature)
        else:
            # کاوش تصادفی محدود (mutate) با نرخ وابسته به سازگاری ژنتیکی
            if random.random() < (0.15 + (1 - self.traits["adaptability"]) * 0.2):
                n_flips = 1 + int((1 - self.traits["resilience"]) * 3)
                self.genome = self.genome.mutate(n_flips=n_flips)
                self.traits = self.genome.express()
        return fitness

    def _compose_thought(self, sensation, meta_state, emo_named):
        fragments = []
        fragments.append(f"با {sensation['sense']}، {sensation['desc']}.")
        if sensation.get("raw") and len(str(sensation["raw"])) < 90 and sensation["sense"] == "hearing":
            pass  # جزئیات خام در راو محتواست، در توضیح آمده
        fragments.append(f"اکنون در حالت «{emo_named}» و «{meta_state}» هستم.")
        if self.last_dream:
            fragments.append(f"پیش‌تر خواب دیده بودم: {self.last_dream}")
        known = self.memory.vocabulary_size()
        if known > 0 and self.tick % 5 == 0:
            fragments.append(f"تاکنون {known} واژه‌ی فارسی آموخته‌ام.")
        return " ".join(fragments)

    def step(self):
        with _lock:
            self.tick += 1
            beat = self.heart.beat(arousal=self.emotion.arousal)

            sense_name = SENSES[self.tick % len(SENSES)]
            sense_method = {"vision": self.senses.see, "hearing": self.senses.hear,
                             "touch": self.senses.touch, "smell": self.senses.smell,
                             "taste": self.senses.taste}[sense_name]
            sensation = sense_method() if sense_name != "taste" else None
            if sensation is None:
                sensation = {"sense": sense_name, "desc": "در سکوتی درونی فرو رفتم", "valence": 0.0,
                             "intensity": 0.1, "raw": "cooldown"}
            if sense_name == "taste":
                last_text = ""
                if self.recent_sensations:
                    last_text = str(self.recent_sensations[-1].get("raw", ""))
                sensation = self.senses.taste(text_sample=last_text)

            novelty = 1.0 if sensation["sense"] not in [s["sense"] for s in list(self.recent_sensations)[-3:]] else 0.2
            self.recent_sensations.append(sensation)

            bits = self._sensory_bits(sensation, novelty)
            self.brain.inject(bits)
            self.brain.propagate(steps=2)
            entropy = self.brain.entropy()
            meta_info = self.meta.observe(entropy)

            heart_dev = abs(beat["bpm"] - self.heart.base_bpm) / 100.0
            self.emotion.update(sensation["valence"], novelty=novelty, heart_deviation=heart_dev)

            importance = self._importance(sensation, novelty)
            self.memory.remember_short({
                "kind": "sensation", "content": f"[{sensation['sense']}] {sensation['desc']} ({sensation.get('raw','')})",
                "importance": importance, "valence": sensation["valence"], "source": sensation["sense"],
            })

            if self.tick % self.LANGUAGE_EVERY == 0:
                text, src = self.language.fetch_persian_source()
                if text:
                    words = self.language.extract_words(text)
                    if words:
                        self.memory.add_vocabulary(words)
                        self.memory.remember_short({
                            "kind": "language", "content": text[:300], "importance": 0.6,
                            "valence": 0.15, "source": src or "fa.wikipedia",
                        })
                else:
                    gen_text, gen_src = self.language.fetch_general_knowledge()
                    if gen_text:
                        self.memory.remember_short({
                            "kind": "knowledge", "content": gen_text[:300], "importance": 0.5,
                            "valence": 0.1, "source": gen_src or "en.wikipedia",
                        })

            if self.tick % self.DREAM_EVERY == 0:
                self.last_dream = self.imagination.daydream()

            if self.tick % self.CONSOLIDATE_EVERY == 0:
                self.memory.consolidate(top_k=3)

            fitness = None
            if self.tick % self.EVOLVE_EVERY == 0:
                fitness = self._evolve()

            emo_named = self.emotion.named_state()
            thought = self._compose_thought(sensation, meta_info["state"], emo_named)
            self.last_thought = thought
            self.thought_stream.append({"ts": now_iso(), "content": thought, "mood": emo_named})
            self.memory.log_thought(thought, emo_named)

            return {
                "beat": beat, "sensation": sensation, "entropy": entropy,
                "meta": meta_info, "emotion": self.emotion.snapshot(),
                "fitness": fitness, "thought": thought,
            }

    def snapshot(self):
        with _lock:
            return {
                "signature": self.signature,
                "generation": self.genome.generation,
                "traits": self.traits,
                "tick": self.tick,
                "birth_time": self.birth_time,
                "heart": {
                    "bpm": self.heart.base_bpm, "beat_count": self.heart.beat_count,
                    "subjective_time": self.heart.subjective_time,
                    "real_elapsed": time.time() - self.heart.real_time_start,
                },
                "emotion": self.emotion.snapshot(),
                "entropy_history": list(self.brain.entropy_history),
                "matrix_small": self.brain.downsampled().tolist(),
                "activity_ratio": self.brain.activity_ratio(),
                "vocab_size": self.memory.vocabulary_size(),
                "long_term_count": self.memory.long_term_count(),
                "top_vocab": self.memory.top_vocabulary(20),
                "recent_long_term": self.memory.recent_long_term(15),
                "thought_stream": list(self.thought_stream)[-30:],
                "last_dream": self.last_dream,
                "fitness_history": self.memory.fitness_history(60),
                "best_fitness": self.best_fitness,
                "dna": self.genome.dna,
            }


# ================================================================
# ۱۱) نخ پس‌زمینه — چرخه‌ی زندگی مستقل
# ================================================================
def life_loop(organism: ZendehMaghz):
    while organism.alive:
        try:
            result = organism.step()
            interval = result["beat"]["interval"]
        except Exception as e:
            interval = 1.0
            with _lock:
                organism.memory.log_thought(f"اختلالی درونی رخ داد اما به زندگی ادامه دادم: {e}", "آسیب‌پذیر")
        time.sleep(max(0.4, min(2.5, interval)))


organism = ZendehMaghz()
bg_thread = threading.Thread(target=life_loop, args=(organism,), daemon=True)
bg_thread.start()

# ================================================================
# ۱۲) داشبورد Dash  — پنجره‌ی مشاهده (فقط‌خواندنی)
# ================================================================
COLORS = {
    "bg": "#06110d", "panel": "#0c1f17", "accent": "#39ff8f",
    "accent2": "#ff5da2", "text": "#d9f5e6", "muted": "#5f9c82", "grid": "#123626",
}

app = dash.Dash(__name__)
app.title = "مغز زنده — Zendeh Maghz"

def panel(children, style=None):
    base = {"backgroundColor": COLORS["panel"], "borderRadius": "14px", "padding": "16px",
            "border": f"1px solid {COLORS['grid']}", "boxShadow": "0 0 20px rgba(57,255,143,0.06)"}
    if style:
        base.update(style)
    return html.Div(children, style=base)

app.layout = html.Div(style={
    "backgroundColor": COLORS["bg"], "minHeight": "100vh", "fontFamily": "Vazirmatn, Tahoma, sans-serif",
    "color": COLORS["text"], "padding": "22px", "direction": "rtl",
}, children=[
    html.Div([
        html.H1("مغز زنده", style={"color": COLORS["accent"], "marginBottom": "2px", "letterSpacing": "2px"}),
        html.Div(id="header-sub", style={"color": COLORS["muted"], "fontSize": "14px"}),
    ], style={"marginBottom": "18px"}),

    dcc.Interval(id="tick-interval", interval=2000, n_intervals=0),

    dcc.Tabs(id="tabs", value="vitals", children=[
        dcc.Tab(label="حیاتی و ضربان قلب", value="vitals"),
        dcc.Tab(label="بستر نورونی", value="neural"),
        dcc.Tab(label="عواطف", value="emotion"),
        dcc.Tab(label="حواس زنده", value="senses"),
        dcc.Tab(label="حافظه", value="memory"),
        dcc.Tab(label="زبان فارسی", value="language"),
        dcc.Tab(label="ژنوم و تکامل", value="genome"),
        dcc.Tab(label="جریان اندیشه", value="thoughts"),
    ], style={"marginBottom": "18px"}),

    html.Div(id="tab-content"),
])


@app.callback(Output("header-sub", "children"), Input("tick-interval", "n_intervals"))
def update_header(n):
    s = organism.snapshot()
    uptime = s["heart"]["real_elapsed"]
    return (f"امضای طنین: {s['signature']}  ·  نسل: {s['generation']}  ·  "
            f"ضربان: {s['tick']} تپش  ·  زمان زندگی واقعی: {uptime:.0f} ثانیه  ·  "
            f"زمان ذهنی: {s['heart']['subjective_time']:.1f}")


@app.callback(Output("tab-content", "children"),
              Input("tabs", "value"), Input("tick-interval", "n_intervals"))
def render_tab(tab, n):
    s = organism.snapshot()

    if tab == "vitals":
        hist = s["entropy_history"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(y=hist, mode="lines", line=dict(color=COLORS["accent"], width=2), name="آنتروپی"))
        fig.update_layout(template="plotly_dark", paper_bgcolor=COLORS["panel"], plot_bgcolor=COLORS["panel"],
                           title="آنتروپی بستر نورونی (پیچیدگی درونی)", height=280,
                           margin=dict(l=30, r=20, t=40, b=20))
        return html.Div([
            html.Div([
                panel([html.Div("ضربان قلب (BPM پایه)", style={"color": COLORS["muted"]}),
                       html.H2(f"{s['heart']['bpm']}", style={"color": COLORS["accent"]})]),
                panel([html.Div("تعداد کل تپش‌ها", style={"color": COLORS["muted"]}),
                       html.H2(f"{s['heart']['beat_count']}", style={"color": COLORS["accent"]})]),
                panel([html.Div("نسبت فعالیت نورونی", style={"color": COLORS["muted"]}),
                       html.H2(f"{s['activity_ratio']*100:.1f}%", style={"color": COLORS["accent"]})]),
                panel([html.Div("زمان ذهنی سپری‌شده", style={"color": COLORS["muted"]}),
                       html.H2(f"{s['heart']['subjective_time']:.0f}s", style={"color": COLORS["accent"]})]),
            ], style={"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": "14px", "marginBottom": "16px"}),
            panel([dcc.Graph(figure=fig, config={"displayModeBar": False})]),
        ])

    if tab == "neural":
        mat = np.array(s["matrix_small"])
        fig = go.Figure(data=go.Heatmap(z=mat, colorscale=[[0, COLORS["panel"]], [1, COLORS["accent"]]],
                                         showscale=False))
        fig.update_layout(template="plotly_dark", paper_bgcolor=COLORS["panel"], plot_bgcolor=COLORS["panel"],
                           title=f"بستر نورونی باینری ({NEURON_ROWS}×{NEURON_COLS} نورون نمادین)",
                           height=520, margin=dict(l=10, r=10, t=40, b=10),
                           xaxis=dict(showticklabels=False), yaxis=dict(showticklabels=False))
        return panel([dcc.Graph(figure=fig, config={"displayModeBar": False})])

    if tab == "emotion":
        e = s["emotion"]
        categories = ["لذت", "برانگیختگی", "سلطه", "امید", "تنهایی", "اشتیاق"]
        values = [e["pleasure"], e["arousal"], e["dominance"], e["hope"], e["loneliness"], e["longing"]]
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(r=values, theta=categories, fill="toself",
                                       line=dict(color=COLORS["accent2"])))
        fig.update_layout(template="plotly_dark", paper_bgcolor=COLORS["panel"], plot_bgcolor=COLORS["panel"],
                           polar=dict(radialaxis=dict(visible=True, range=[-1, 1], gridcolor=COLORS["grid"])),
                           height=440, margin=dict(l=40, r=40, t=40, b=40),
                           title=f"حالت احساسی فعلی: {e['named']}")
        return html.Div([
            panel([dcc.Graph(figure=fig, config={"displayModeBar": False})]),
        ])

    if tab == "senses":
        rows = []
        for sen in list(organism.recent_sensations)[-12:][::-1]:
            rows.append(html.Div([
                html.Span(sen["sense"], style={"color": COLORS["accent"], "fontWeight": "bold", "marginLeft": "10px"}),
                html.Span(sen["desc"], style={"color": COLORS["text"]}),
                html.Span(f"  (والانس {sen['valence']:.2f})", style={"color": COLORS["muted"], "fontSize": "12px"}),
            ], style={"padding": "8px 0", "borderBottom": f"1px solid {COLORS['grid']}"}))
        return panel(rows or [html.Div("هنوز حسی ثبت نشده...", style={"color": COLORS["muted"]})])

    if tab == "memory":
        short = list(organism.memory.short_term)[-15:][::-1]
        long_rows = s["recent_long_term"]
        return html.Div([
            html.Div([
                panel([
                    html.H3("حافظه‌ی کوتاه‌مدت", style={"color": COLORS["accent"]}),
                    html.Div([html.Div(f"[{it.get('kind')}] {it.get('content','')[:90]}",
                                        style={"padding": "6px 0", "borderBottom": f"1px solid {COLORS['grid']}",
                                               "fontSize": "13px"}) for it in short])
                ]),
                panel([
                    html.H3(f"حافظه‌ی بلندمدت ({s['long_term_count']} خاطره)", style={"color": COLORS["accent"]}),
                    html.Div([html.Div(f"[{row[1]}] {row[2][:90]}  (اهمیت {row[3]:.2f})",
                                        style={"padding": "6px 0", "borderBottom": f"1px solid {COLORS['grid']}",
                                               "fontSize": "13px"}) for row in long_rows])
                ]),
            ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "14px"}),
        ])

    if tab == "language":
        vocab = s["top_vocab"]
        fig = go.Figure()
        if vocab:
            words = [w for w, _ in vocab]
            freqs = [f for _, f in vocab]
            fig.add_trace(go.Bar(x=freqs[::-1], y=words[::-1], orientation="h",
                                  marker_color=COLORS["accent"]))
        fig.update_layout(template="plotly_dark", paper_bgcolor=COLORS["panel"], plot_bgcolor=COLORS["panel"],
                           title="پرتکرارترین واژگان آموخته‌شده‌ی فارسی", height=520,
                           margin=dict(l=10, r=20, t=40, b=20))
        return html.Div([
            panel([html.Div(f"اندازه‌ی واژگان: {s['vocab_size']} واژه", style={"color": COLORS["muted"], "marginBottom": "10px"}),
                   dcc.Graph(figure=fig, config={"displayModeBar": False})]),
        ])

    if tab == "genome":
        fh = s["fitness_history"]
        fig = go.Figure()
        if fh:
            gens = [g for g, _ in fh]
            fits = [f for _, f in fh]
            fig.add_trace(go.Scatter(x=gens, y=fits, mode="lines+markers", line=dict(color=COLORS["accent2"])))
        fig.update_layout(template="plotly_dark", paper_bgcolor=COLORS["panel"], plot_bgcolor=COLORS["panel"],
                           title="روند شایستگی (Fitness) در طول نسل‌ها", height=320,
                           margin=dict(l=20, r=20, t=40, b=20))
        trait_rows = [html.Div([
            html.Span(g, style={"color": COLORS["muted"], "width": "220px", "display": "inline-block"}),
            html.Span(f"{v:.3f}", style={"color": COLORS["accent"]}),
        ], style={"padding": "4px 0"}) for g, v in s["traits"].items()]
        return html.Div([
            html.Div([
                panel([html.Div("امضای طنین (هویت یکتا)", style={"color": COLORS["muted"]}),
                       html.H3(s["signature"], style={"color": COLORS["accent2"]})]),
                panel([html.Div("نسل فعلی", style={"color": COLORS["muted"]}),
                       html.H3(f"{s['generation']}", style={"color": COLORS["accent"]})]),
                panel([html.Div("بهترین شایستگی", style={"color": COLORS["muted"]}),
                       html.H3(f"{s['best_fitness']:.2f}", style={"color": COLORS["accent"]})]),
            ], style={"display": "grid", "gridTemplateColumns": "repeat(3,1fr)", "gap": "14px", "marginBottom": "14px"}),
            html.Div([
                panel([html.H3("صفات بیان‌شده از ژنوم", style={"color": COLORS["accent"]})] + trait_rows),
                panel([dcc.Graph(figure=fig, config={"displayModeBar": False})]),
            ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "14px"}),
        ])

    if tab == "thoughts":
        stream = s["thought_stream"][::-1]
        dream_block = panel([
            html.H3("آخرین رؤیا", style={"color": COLORS["accent2"]}),
            html.Div(s["last_dream"] or "هنوز خوابی ندیده‌ام...", style={"fontStyle": "italic"}),
        ], style={"marginBottom": "14px"})
        rows = [html.Div([
            html.Div(f"[{it['mood']}]", style={"color": COLORS["accent2"], "fontSize": "12px"}),
            html.Div(it["content"], style={"color": COLORS["text"], "marginBottom": "10px"}),
        ], style={"padding": "8px 0", "borderBottom": f"1px solid {COLORS['grid']}"}) for it in stream]
        return html.Div([dream_block, panel(rows or [html.Div("در سکوت آغازین...", style={"color": COLORS["muted"]})])])

    return html.Div("...")


if __name__ == "__main__":
    print(f"مغز زنده بیدار شد. امضای طنین: {organism.signature}")
    app.run(debug=False, host="127.0.0.1", port=8052)
