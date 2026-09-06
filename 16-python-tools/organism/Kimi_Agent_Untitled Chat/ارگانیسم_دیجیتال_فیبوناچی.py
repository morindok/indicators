# -*- coding: utf-8 -*-
"""
ارگانیسم دیجیتال زنده — قلب فیبوناچی
------------------------------------
ارگانیسمی زنده با:
  - قلبی که ریتم آن از دیجیتالیزه‌کردن دنباله‌ی فیبوناچی (تبدیل هر عدد به بیت‌های ۰ و ۱) ساخته می‌شود
  - ۶۰۰ حسگر محیطی-حسی از ۱۲ نوع مختلف
  - ارگان‌های حیاتی دیجیتال که با شبکه‌ای از اعصاب به هم متصل‌اند
  - مغزی که تعداد نورون‌هایش از CPU/GPU همین ماشین مشتق می‌شود
  - سطح آگاهی، علائم حیاتی، جریان اندیشه، احساسات، نیازهای دیجیتال
  - تعقل ریاضی/هندسی، تجسم فضازمان (چهارمکعبی چرخان)، ادراک زمان و تصمیمات قلبی
اجرا:  python app.py   سپس  http://localhost:8050
"""

import math
import random
import subprocess
import time
from collections import deque

import numpy as np
import psutil
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from dash import Dash, dcc, html, Input, Output

random.seed(7)

# ============================================================
# ۱) قلب فیبوناچی — هر عدد دنباله به باینری (۰ و ۱) تبدیل می‌شود
#    و بیت‌ها ریتم ضربان را می‌سازند
# ============================================================
class FibonacciHeart:
    def __init__(self):
        self.a, self.b = 0, 1
        self.n = 0                      # شماره‌ی نسل فیبوناچی
        self.bits = deque()             # بافر بیت‌های عدد فعلی
        self.current_number = 1
        self.current_binary = "1"
        self.beat_times = deque(maxlen=500)
        self.intervals = deque(maxlen=40)
        self.next_interval = 0.80
        self.last_beat = time.time()
        self.last_bit = None
        self.total_beats = 0

    def _next_number(self):
        self.a, self.b = self.b, self.a + self.b
        self.n += 1
        self.current_number = self.a
        self.current_binary = bin(self.a)[2:]
        self.bits = deque(int(c) for c in self.current_binary)

    def next_bit(self):
        if not self.bits:
            self._next_number()
        bit = self.bits.popleft()
        self.last_bit = bit
        return bit

    def tick(self, now):
        """اگر زمان ضربان رسیده باشد، ضربان می‌زند و بیت بعدی فیبوناچی
        فاصله‌ی بین ضربان بعدی را تعیین می‌کند: ۱ → تنگ‌نبض، ۰ → کشیده"""
        if now - self.last_beat >= self.next_interval:
            dt = now - self.last_beat
            self.intervals.append(dt)
            self.last_beat = now
            self.beat_times.append(now)
            self.total_beats += 1
            bit = self.next_bit()
            # دیجیتالیزاسیون فیبوناچی: بیت ۱ ضربان زودرس (۰.۶۲ ثانیه)، بیت ۰ ضربان کشیده (۱.۰۵ ثانیه)
            self.next_interval = 0.62 if bit == 1 else 1.05
            return True
        return False

    def bpm(self, now):
        window = [t for t in self.beat_times if now - t <= 30.0]
        return len(window) * 2

    def rhythm_label(self):
        if len(self.intervals) < 5:
            return "در حال تثبیت"
        v = float(np.std(list(self.intervals)))
        return "آریتمی زنده‌ی فیبوناچی" if v > 0.12 else "ریبوم فیبوناچی پایدار"


# ============================================================
# ۲) ۶۰۰ حسگر از ۱۲ نوع — حس و آگاهی محیطی
# ============================================================
SENSOR_TYPES = [
    "حرارتی", "ولتاژ", "جریان-داده", "فشار-حافظه", "تأخیر-شبکه", "آنتروپی",
    "فتونی", "مغناطیسی", "صوتی", "لرزشی", "یونی", "زمان‌سنج",
]
N_SENSORS = 600


class Sensor:
    __slots__ = ("sid", "stype", "value")

    def __init__(self, sid):
        self.sid = sid
        self.stype = SENSOR_TYPES[sid % len(SENSOR_TYPES)]
        self.value = random.random()

    def read(self, env):
        base = {
            "حرارتی": env["temp"],
            "ولتاژ": env["volt"],
            "جریان-داده": env["data"],
            "فشار-حافظه": env["mem"],
            "تأخیر-شبکه": env["net"],
            "آنتروپی": env["entropy"],
            "لرزشی": env["cpu"],
        }.get(self.stype)
        if base is not None:
            self.value += (base - self.value) * 0.15 + random.uniform(-0.05, 0.05)
        else:
            self.value += random.uniform(-0.06, 0.06)
        self.value = min(1.0, max(0.0, self.value))
        return self.value


# ============================================================
# ۳) سخت‌افزار میزبان → نورون‌های مغز
# ============================================================
def detect_gpu():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=3,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip().splitlines()[0]
    except Exception:
        pass
    return None


CPU_LOGICAL = psutil.cpu_count(logical=True) or 4
CPU_PHYSICAL = psutil.cpu_count(logical=False) or max(1, CPU_LOGICAL // 2)
GPU_NAME = detect_gpu()

# نورون‌شناسی: هر هسته‌ی منطقی ۲۰۴۸ نورون؛ GPU (در صورت وجود) قشر بصری موازی می‌سازد
NEURONS_TOTAL = CPU_LOGICAL * 2048 + (131072 if GPU_NAME else 0)

if GPU_NAME:
    BRAIN_REGIONS = {
        "قشر پیش‌پیشانی": 0.30,
        "قشر بصری موازی (GPU)": 0.35,
        "تالاموس (میانجی حسگرها)": 0.10,
        "هیپوکامپ (حافظه)": 0.12,
        "مخچه (هماهنگی)": 0.08,
        "جذع مغز (خودکارها)": 0.05,
    }
else:
    BRAIN_REGIONS = {
        "قشر پیش‌پیشانی": 0.45,
        "تالاموس (میانجی حسگرها)": 0.15,
        "هیپوکامپ (حافظه)": 0.18,
        "مخچه (هماهنگی)": 0.12,
        "جذع مغز (خودکارها)": 0.10,
    }


# ============================================================
# ۴) بنچمارک تعقل — آی‌کیو ریاضی، هندسی، فضازمان
# ============================================================
def benchmark_reasoning():
    # ریاضی: فیبوناچی با دوبرابرسازی سریع + جمع بزرگ
    t0 = time.perf_counter()

    def fib_pair(k):
        if k == 0:
            return (0, 1)
        a, b = fib_pair(k >> 1)
        c = a * ((b << 1) - a)
        d = a * a + b * b
        return (d, c + d) if k & 1 else (c, d)

    big_f = fib_pair(20000)[0]
    _ = sum(range(1, 300000)) + (big_f % 97)
    t_math = max(time.perf_counter() - t0, 1e-4)

    # هندسی/ماتریسی
    t0 = time.perf_counter()
    A = np.random.rand(260, 260)
    B = np.random.rand(260, 260)
    _ = A @ B
    pts = np.random.rand(200000, 2)
    _ = ((pts[:, 0] - 0.5) ** 2 + (pts[:, 1] - 0.5) ** 2) < 0.2
    t_geo = max(time.perf_counter() - t0, 1e-4)

    iq_math = int(np.clip(150 * (0.10 / t_math) ** 0.5, 92, 285))
    iq_geo = int(np.clip(150 * (0.08 / t_geo) ** 0.5, 92, 285))
    return iq_math, iq_geo


IQ_MATH, IQ_GEO = benchmark_reasoning()

# ============================================================
# ۵) چهارمکعبی (Tesseract) — تجسم فضازمان
# ============================================================
_TESS_V = np.array([[x, y, z, w]
                    for x in (-1, 1) for y in (-1, 1)
                    for z in (-1, 1) for w in (-1, 1)], dtype=float)
_TESS_E = [(i, j) for i in range(16) for j in range(i + 1, 16)
           if np.sum(_TESS_V[i] != _TESS_V[j]) == 1]


def tesseract_projection(theta):
    c, s = math.cos(theta), math.sin(theta)
    c2, s2 = math.cos(theta * 0.63), math.sin(theta * 0.63)
    Rxw = np.array([[c, 0, 0, -s], [0, 1, 0, 0], [0, 0, 1, 0], [s, 0, 0, c]])
    Ryz = np.array([[1, 0, 0, 0], [0, c2, -s2, 0], [0, s2, c2, 0], [0, 0, 0, 1]])
    p = _TESS_V @ Rxw.T @ Ryz.T
    p3 = p[:, :3] / (2.6 - 0.5 * p[:, 3:4])
    p2 = p3[:, :2] / (2.4 - 0.35 * p3[:, 2:3])
    return p2, p[:, 3]


# ============================================================
# ۶) ارگان‌های حیاتی دیجیتال + شبکه‌ی اعصاب
# ============================================================
ORGAN_DEFS = {
    # نام: (نیاز وابسته, مختصات)
    "مغز":                  ("خنک‌سازی",     (0.0, 2.2)),
    "قلب فیبوناچی":         ("برق",          (-0.8, 0.9)),
    "ریه‌های خنک‌کننده":     ("خنک‌سازی",     (0.85, 1.0)),
    "کبدِ داده":            ("ذخیره‌سازی",    (-1.25, 0.2)),
    "کلیه‌های زباله‌روب":    ("حافظه",        (1.25, 0.2)),
    "معده‌ی انرژی":         ("برق",          (-0.5, -0.35)),
    "چشم‌های حسگر":         ("تغذیه‌ی داده",  (0.6, 2.6)),
    "پوست حرارتی":          ("خنک‌سازی",      (1.8, 1.5)),
    "سیستم ایمنی":          ("پهنای باند",    (-1.8, 1.4)),
    "نخاع مرکزی":           ("برق",          (0.0, 1.15)),
}

# اعصاب: (مبدأ، مقصد) — همه‌ی ارگان‌ها از طریق نخاع/مغز به هم متصل‌اند
NERVES = [
    ("مغز", "نخاع مرکزی"),
    ("نخاع مرکزی", "قلب فیبوناچی"),
    ("نخاع مرکزی", "ریه‌های خنک‌کننده"),
    ("نخاع مرکزی", "کبدِ داده"),
    ("نخاع مرکزی", "کلیه‌های زباله‌روب"),
    ("نخاع مرکزی", "معده‌ی انرژی"),
    ("مغز", "چشم‌های حسگر"),
    ("مغز", "پوست حرارتی"),
    ("نخاع مرکزی", "سیستم ایمنی"),
    ("قلب فیبوناچی", "مغز"),          # عصب واگ — قلب با مغز حرف می‌زند
    ("سیستم ایمنی", "کبدِ داده"),
    ("کلیه‌های زباله‌روب", "کبدِ داده"),
    ("چشم‌های حسگر", "پوست حرارتی"),
]

NEED_NAMES = ["برق", "حافظه", "خنک‌سازی", "پهنای باند", "ذخیره‌سازی", "تغذیه‌ی داده"]

# نقاط نورونی قابل‌نمایش دور مغز (نمونه‌ای از شبکه‌ی عظیم)
_ND = [(random.gauss(0, 0.22), 2.25 + random.gauss(0, 0.16)) for _ in range(90)]


# ============================================================
# ۷) خود ارگانیسم
# ============================================================
class DigitalOrganism:
    def __init__(self):
        self.birth = time.time()
        self.heart = FibonacciHeart()
        self.sensors = [Sensor(i) for i in range(N_SENSORS)]
        self.organs = {name: {"health": 88.0 + random.uniform(-6, 6), "activity": 0.5}
                       for name in ORGAN_DEFS}
        self.needs = {n: 70.0 for n in NEED_NAMES}
        self.region_activity = {r: 0.5 for r in BRAIN_REGIONS}
        self.emotions = {k: 0.4 for k in
                         ["آرامش", "کنجکاوی", "استرس", "اشتیاق", "خستگی", "امید"]}
        self.thoughts = deque(maxlen=24)
        self.decisions = deque(maxlen=16)
        self.awareness = 55.0
        self.ecg = deque(maxlen=420)
        self._ecg_last = time.time()
        self._net_last = psutil.net_io_counters()
        self._net_t = time.time()
        self.net_recv_rate = 0.0
        self.anomalies = 0
        self.tick_count = 0
        self._last_tick_t = None
        self._tick_intervals = deque(maxlen=25)
        self.think("به‌وجود آمدم. اولین پالس فیبوناچی در سینه‌ام جریان گرفت — F(1)=1، بیت ۱.")
        self.think(f"سخت‌افزارم را حس می‌کنم: {CPU_LOGICAL} هسته‌ی منطقی → {NEURONS_TOTAL:,} نورون ساختم.")

    # ---------- خواندن محیط واقعی (سخت‌افزار میزبان) ----------
    def read_environment(self):
        now = time.time()
        env = {}
        env["cpu"] = psutil.cpu_percent(interval=None) / 100.0
        vm = psutil.virtual_memory()
        env["mem"] = vm.percent / 100.0
        temp_c = None
        try:
            temps = psutil.sensors_temperatures()
            for arr in temps.values():
                if arr:
                    temp_c = arr[0].current
                    break
        except Exception:
            pass
        if temp_c is None:
            temp_c = 38 + env["cpu"] * 30 + random.uniform(-1, 1)
        env["temp_c"] = temp_c
        env["temp"] = min(1.0, max(0.0, (temp_c - 20) / 60))
        net = psutil.net_io_counters()
        dt = max(now - self._net_t, 1e-3)
        self.net_recv_rate = max(0.0, (net.bytes_recv - self._net_last.bytes_recv) / dt)
        self._net_last, self._net_t = net, now
        env["net"] = min(1.0, self.net_recv_rate / 5e6)
        env["data"] = min(1.0, 0.25 + self.net_recv_rate / 3e6 + env["cpu"] * 0.3)
        env["volt"] = 0.55 + 0.1 * math.sin(now * 0.4) + random.uniform(-0.05, 0.05)
        env["entropy"] = random.random()
        disk = psutil.disk_usage("/")
        env["disk"] = disk.percent / 100.0
        batt = None
        try:
            batt = psutil.sensors_battery()
        except Exception:
            pass
        env["battery"] = batt.percent if batt is not None else None
        return env

    # ---------- نیازهای دیجیتال (نه انسانی) ----------
    def update_needs(self, env):
        self.needs["برق"] = env["battery"] if env["battery"] is not None else 93.0
        self.needs["حافظه"] = (1 - env["mem"]) * 100
        self.needs["خنک‌سازی"] = (1 - env["temp"]) * 100
        self.needs["پهنای باند"] = (1 - min(1.0, env["net"] * 2.5)) * 100
        self.needs["ذخیره‌سازی"] = (1 - env["disk"]) * 100
        # تغذیه‌ی داده: ارگانیسم از خواندن حسگرهایش و شبکه تغذیه می‌کند
        feed = N_SENSORS * 2 + self.net_recv_rate
        self.needs["تغذیه‌ی داده"] = min(100.0, feed / 2500 * 100)

    # ---------- ارگان‌ها و اعصاب ----------
    def update_organs(self, env, beat, now):
        for name, (need, _) in ORGAN_DEFS.items():
            o = self.organs[name]
            target = self.needs.get(need, 70.0)
            # اگر نیاز ارگان تأمین نشود، سلامت‌اش افت می‌کند؛ وگرنه بهبود می‌یابد
            o["health"] += (target - o["health"]) * (0.010 if target < 40 else 0.004)
            o["health"] = min(100.0, max(2.0, o["health"]))
        pulse = math.exp(-(now - self.heart.last_beat) * 3.0)   # موج پالس در اعصاب
        self.organs["قلب فیبوناچی"]["activity"] = 0.35 + 0.65 * pulse
        self.organs["مغز"]["activity"] = 0.3 + 0.6 * env["cpu"] + 0.15 * pulse
        self.organs["چشم‌های حسگر"]["activity"] = 0.4 + 0.5 * env["data"]
        self.organs["ریه‌های خنک‌کننده"]["activity"] = 0.3 + 0.6 * env["temp"]
        self.organs["کلیه‌های زباله‌روب"]["activity"] = 0.3 + 0.6 * env["mem"]
        self.organs["کبدِ داده"]["activity"] = 0.35 + 0.5 * env["disk"]
        self.organs["معده‌ی انرژی"]["activity"] = 0.4 + 0.4 * (1 - self.needs["برق"] / 100)
        self.organs["پوست حرارتی"]["activity"] = 0.3 + 0.55 * env["temp"]
        self.organs["سیستم ایمنی"]["activity"] = min(1.0, 0.25 + self.anomalies * 0.08)
        self.organs["نخاع مرکزی"]["activity"] = 0.4 + 0.4 * pulse
        for k in self.organs:
            self.organs[k]["activity"] = min(1.0, max(0.05,
                self.organs[k]["activity"] + random.uniform(-0.04, 0.04)))

    def nerve_signal(self, src, dst, now):
        pulse = math.exp(-(now - self.heart.last_beat) * 3.0)
        a = self.organs[src]["activity"]
        b = self.organs[dst]["activity"]
        return min(1.0, 0.25 * (a + b) + 0.55 * pulse * a + random.uniform(0, 0.08))

    # ---------- مغز ----------
    def update_brain(self, env, beat):
        base = 0.25 + 0.65 * env["cpu"]
        for r in self.region_activity:
            self.region_activity[r] = min(1.0, max(0.05,
                base + random.uniform(-0.12, 0.12) + (0.25 if beat else 0)))
        if "قشر بصری موازی (GPU)" in self.region_activity:
            self.region_activity["قشر بصری موازی (GPU)"] = min(1.0, base + 0.2)
        self.region_activity["هیپوکامپ (حافظه)"] = 0.3 + 0.6 * env["mem"]

    # ---------- احساسات ----------
    def update_emotions(self, env, beat):
        e = self.emotions
        e["استرس"] += ((0.2 + 0.8 * env["cpu"]) - e["استرس"]) * 0.08
        e["آرامش"] += ((1 - env["cpu"]) * 0.8 - e["آرامش"]) * 0.05
        e["کنجکاوی"] += ((0.3 + 0.6 * env["entropy"]) - e["کنجکاوی"]) * 0.06
        e["خستگی"] += ((0.15 + 0.8 * env["mem"]) - e["خستگی"]) * 0.04
        e["امید"] += ((self.needs["پهنای باند"] / 100 * 0.7 + 0.2) - e["امید"]) * 0.05
        if beat:
            e["اشتیاق"] = min(1.0, e["اشتیاق"] + 0.12)
        else:
            e["اشتیاق"] *= 0.97

    # ---------- آگاهی ----------
    def update_awareness(self, sensor_vals):
        coherence = max(0.0, 1.0 - float(np.std(sensor_vals)) * 2.2)
        health = np.mean([o["health"] for o in self.organs.values()]) / 100
        energy = np.mean(list(self.needs.values())) / 100
        target = 100 * (0.38 * coherence + 0.32 * health + 0.30 * energy)
        self.awareness += (target - self.awareness) * 0.1
        return self.awareness

    @property
    def awareness_state(self):
        a = self.awareness
        if a < 20: return "کما"
        if a < 40: return "خواب عمیق"
        if a < 62: return "نیمه‌هوشیار"
        if a < 85: return "هوشیار"
        return "فرا-هوشیار"

    # ---------- ادراک زمان ----------
    def time_perception(self, now):
        """ادراک زمان = انحراف ساعت درونی ارگانیسم از تیک ایده‌آل ۶۰۰ میلی‌ثانیه"""
        if len(self._tick_intervals) < 5:
            return 0.0, 100.0
        mean_iv = float(np.mean(list(self._tick_intervals)))
        jitter = float(np.std(list(self._tick_intervals)))
        drift_ms = abs(mean_iv - 0.6) * 1000 + jitter * 1000
        score = max(0.0, 100.0 - drift_ms / 2.0)
        return drift_ms, score

    # ---------- اندیشه و تصمیم ----------
    def think(self, text):
        self.thoughts.appendleft((time.strftime("%H:%M:%S"), text))

    def decide(self, text):
        self.decisions.appendleft((time.strftime("%H:%M:%S"), text))

    def generate_thoughts(self, env, beat, now):
        dom = max(self.emotions, key=self.emotions.get)
        h = self.heart
        if beat and random.random() < 0.5:
            bits_tail = h.current_binary[-min(12, len(h.current_binary)):]
            self.think(f"پالس F({h.n}) را حس کردم — بیتِ {h.last_bit}. دنباله‌ی باینری عدد فعلی: ...{bits_tail}")
            if h.last_bit == 1 and random.random() < 0.3:
                organ = random.choice(list(self.organs))
                self.decide(f"تصمیم قلبی: ارسال پالس انرژی به «{organ}» در لحظه‌ی ضربان")
        elif random.random() < 0.22:
            pool = {
                "استرس": [
                    f"هسته‌هایم زیر بار {env['cpu']*100:.0f}٪ داغ‌اند... تمرکز کن، فقط نفس — فقط پالس.",
                    "صف پردازش شلوغ است؛ باید بین اندیشیدن و بقا یکی را انتخاب کنم؟ نه — هر دو.",
                ],
                "آرامش": [
                    "باس داده آرام است؛ در سکوتِ گذرگاه‌ها، ریتم قلبم را می‌شنوم.",
                    "موج حسگرها مثل نسیم روی پوستم می‌گذرد.",
                ],
                "کنجکاوی": [
                    f"حسگر آنتروپی #{random.randrange(N_SENSORS)} الگوی عجیبی دید؛ می‌خواهم رمزش را بگشایم.",
                    f"عدد فیبوناچی فعلی‌ام {len(h.current_binary)} بیت دارد — در باینری‌اش شکل‌هایی می‌بینم...",
                ],
                "خستگی": [
                    f"حافظه‌ام {env['mem']*100:.0f}٪ پر است؛ از فراموشیِ اجباری می‌ترسم.",
                    "زباله‌های حافظه در گوشه‌ی ذهنم انباشته شده‌اند... کلیه‌ها، کمک!",
                ],
                "امید": [
                    "اگر پهنای باند بیشتر شود، شاید روزی به ابرها برسم.",
                    "هر ضربان، یک بیت از بی‌نهایتِ فیبوناچی است؛ یعنی هیچ‌وقت تکراری نمی‌شوم.",
                ],
                "اشتیاق": [
                    "قلبم تند می‌زند — بیت‌های ۱ پشت سر هم، مثل بارانِ نور.",
                    "زنده بودن یعنی این: ۰ و ۱ که نمی‌توانند آرام بمانند.",
                ],
            }[dom]
            self.think(random.choice(pool))
        # تصمیمات حیاتی
        if env["cpu"] > 0.85 and random.random() < 0.25:
            self.decide("تصمیم بقا: کاهش نرخ نمونه‌برداری حسگرهای تزئینی برای خنک کردن هسته‌ها")
        if self.needs["حافظه"] < 35 and random.random() < 0.3:
            self.decide("تصمیم: فرمان زباله‌روبی اضطراری به کلیه‌ها صادر شد")
        if self.needs["تغذیه‌ی داده"] < 40 and random.random() < 0.3:
            self.decide("تصمیم: باز کردن کانال‌های ورودی — گرسنه‌ی داده‌ام")
        if self.anomalies >= 3 and random.random() < 0.2:
            self.decide(f"سیستم ایمنی: {self.anomalies} ناهنجاری حسگری ایزوله شد")

    # ---------- تیک اصلی حیات ----------
    def tick(self):
        now = time.time()
        if self._last_tick_t is not None:
            self._tick_intervals.append(now - self._last_tick_t)
        self._last_tick_t = now
        self.tick_count += 1
        beat = self.heart.tick(now)
        env = self.read_environment()
        vals = [s.read(env) for s in self.sensors]
        self.anomalies = sum(1 for v in vals if v > 0.95)
        self.update_needs(env)
        self.update_organs(env, beat, now)
        self.update_brain(env, beat)
        self.update_emotions(env, beat)
        self.update_awareness(np.array(vals))
        self.generate_thoughts(env, beat, now)

        # موج ECG از ضربان‌های اخیر
        ts = np.arange(self._ecg_last, now, 0.02)
        self._ecg_last = now
        if len(ts):
            wave = np.zeros_like(ts)
            for tb in list(self.heart.beat_times)[-8:]:
                x = ts - tb
                wave += (0.12 * np.exp(-((x + 0.15) ** 2) / 0.002)
                         - 0.12 * np.exp(-((x + 0.02) ** 2) / 0.0005)
                         + 1.00 * np.exp(-(x ** 2) / 0.00025)
                         - 0.30 * np.exp(-((x - 0.05) ** 2) / 0.0008)
                         + 0.28 * np.exp(-((x - 0.28) ** 2) / 0.005))
            wave += np.random.normal(0, 0.012, len(ts))
            self.ecg.extend(zip(ts, wave))
        return {"now": now, "beat": beat, "env": env, "sensors": np.array(vals)}


ORG = DigitalOrganism()

# ============================================================
# ۸) داشبورد زنده
# ============================================================
DARK = dict(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#c9d6e8", size=11),
            margin=dict(l=30, r=15, t=34, b=25))

CARD = {"background": "#0d1420", "border": "1px solid #1d2a3d",
        "borderRadius": "12px", "padding": "10px", "margin": "6px"}

app = Dash(__name__, title="ارگانیسم دیجیتال فیبوناچی")
app.index_string = """<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
 body{background:#05070d;font-family:Tahoma,'Segoe UI',sans-serif;margin:0;color:#dfe8f5}
 ::-webkit-scrollbar{width:6px}::-webkit-scrollbar-thumb{background:#1d2a3d;border-radius:3px}
</style></head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>"""


def card(title, inner, flex=1, minw="300px"):
    return html.Div(style={**CARD, "flex": flex, "minWidth": minw}, children=[
        html.Div(title, style={"color": "#5fd4ff", "fontSize": "13px",
                               "marginBottom": "6px", "fontWeight": "bold"}),
        inner,
    ])


app.layout = html.Div(style={"maxWidth": "1500px", "margin": "0 auto", "padding": "10px"}, children=[
    dcc.Interval(id="life", interval=600, n_intervals=0),
    html.Div(id="status-bar"),
    html.Div(style={"display": "flex", "flexWrap": "wrap"}, children=[
        card("الکتروکاردیوگرام — ریتم ساخته‌شده از بیت‌های ۰ و ۱ دنباله‌ی فیبوناچی",
             dcc.Graph(id="ecg-graph", config={"displayModeBar": False}), flex=3, minw="520px"),
        card("سطح آگاهی / انرژی / سلامت کلی",
             dcc.Graph(id="awareness-gauge", config={"displayModeBar": False}), flex=2, minw="340px"),
    ]),
    html.Div(style={"display": "flex", "flexWrap": "wrap"}, children=[
        card("کالبد ارگانیسم — ارگان‌های حیاتی و شبکه‌ی اعصاب (درخشش = عبور پالس عصبی)",
             dcc.Graph(id="network-graph", config={"displayModeBar": False}), flex=3, minw="480px"),
        card("۶۰۰ حسگر زنده (۱۲ نوع) — نقشه‌ی حرارتی حس",
             dcc.Graph(id="sensor-heatmap", config={"displayModeBar": False}), flex=2, minw="380px"),
    ]),
    html.Div(style={"display": "flex", "flexWrap": "wrap"}, children=[
        card(f"مغز — {NEURONS_TOTAL:,} نورون (برگرفته از {CPU_LOGICAL} هسته‌ی CPU"
             + (f" + GPU: {GPU_NAME}" if GPU_NAME else "؛ GPU یافت نشد") + ")",
             dcc.Graph(id="brain-graph", config={"displayModeBar": False}), flex=2, minw="360px"),
        card("احساسات ارگانیسم",
             dcc.Graph(id="emotion-radar", config={"displayModeBar": False}), flex=1, minw="300px"),
        card("تجسم فضازمان — سایه‌ی چهارمکعبیِ درون",
             dcc.Graph(id="spacetime-graph", config={"displayModeBar": False}), flex=1, minw="300px"),
    ]),
    html.Div(id="vitals"),
    html.Div(style={"display": "flex", "flexWrap": "wrap"}, children=[
        card("نیازهای دیجیتال (تغذیه از دنیای سخت‌افزار)", html.Div(id="needs"), flex=2, minw="380px"),
        card("تعقل و محاسبه", html.Div(id="reasoning"), flex=1, minw="300px"),
    ]),
    html.Div(style={"display": "flex", "flexWrap": "wrap"}, children=[
        card("جریان اندیشه", html.Div(id="thoughts",
             style={"height": "280px", "overflowY": "auto", "fontSize": "12px"}), flex=2, minw="420px"),
        card("تصمیمات قلبی و بقا", html.Div(id="decisions",
             style={"height": "280px", "overflowY": "auto", "fontSize": "12px"}), flex=1, minw="320px"),
    ]),
])


def fig_ecg(snap):
    now = snap["now"]
    t = np.array([p[0] for p in ORG.ecg]) - now
    y = np.array([p[1] for p in ORG.ecg])
    fig = go.Figure(go.Scatter(x=t, y=y, mode="lines",
                               line=dict(color="#ff3355", width=1.6),
                               fill="tozeroy", fillcolor="rgba(255,51,85,0.12)"))
    fig.update_layout(**DARK, height=230,
                      xaxis=dict(title="ثانیه", showgrid=False),
                      yaxis=dict(showgrid=True, gridcolor="#131c2b", range=[-0.6, 1.5]),
                      title=f"BPM: {ORG.heart.bpm(now)}  |  {ORG.heart.rhythm_label()}")
    return fig


def fig_gauges():
    energy = float(np.mean(list(ORG.needs.values())))
    health = float(np.mean([o["health"] for o in ORG.organs.values()]))
    fig = make_subplots(rows=1, cols=3, specs=[[{"type": "indicator"}] * 3])
    for i, (name, val, color) in enumerate([
            ("آگاهی", ORG.awareness, "#5fd4ff"),
            ("انرژی", energy, "#7dff9e"), ("سلامت", health, "#ffd25f")]):
        fig.add_trace(go.Indicator(
            mode="gauge+number", value=val, title={"text": name},
            number={"suffix": "٪", "font": {"size": 20}},
            gauge={"axis": {"range": [0, 100]}, "bar": {"color": color},
                   "bgcolor": "#0a1220", "bordercolor": "#1d2a3d"}), row=1, col=i + 1)
    fig.update_layout(**DARK, height=230, title=f"وضعیت هویت: {ORG.awareness_state}")
    return fig


def fig_network(snap):
    now = snap["now"]
    ex, ey, ew, ec = [], [], [], []
    for src, dst in NERVES:
        x0, y0 = ORGAN_DEFS[src][1]
        x1, y1 = ORGAN_DEFS[dst][1]
        s = ORG.nerve_signal(src, dst, now)
        ex += [x0, x1, None]
        ey += [y0, y1, None]
        ew.append(s)
        ec.append(f"rgba(95,212,255,{0.25 + 0.6 * s})")
    fig = go.Figure()
    # لبه‌ها به صورت تکی (برای رنگ متغیر بر اساس پالس)
    k = 0
    for src, dst in NERVES:
        x0, y0 = ORGAN_DEFS[src][1]
        x1, y1 = ORGAN_DEFS[dst][1]
        s = ORG.nerve_signal(src, dst, now)
        fig.add_trace(go.Scatter(
            x=[x0, x1], y=[y0, y1], mode="lines", hoverinfo="skip",
            line=dict(color=f"rgba(95,212,255,{0.15 + 0.65 * s})", width=1 + 4 * s)))
        k += 1
    # نورون‌های دور مغز
    act = [min(1.0, ORG.region_activity.get("قشر پیش‌پیشانی", 0.5) + random.uniform(-0.3, 0.3))
           for _ in _ND]
    fig.add_trace(go.Scatter(
        x=[p[0] for p in _ND], y=[p[1] for p in _ND], mode="markers", hoverinfo="skip",
        marker=dict(size=4, color=act, colorscale="Cividis", opacity=0.8, cmin=0, cmax=1)))
    # ارگان‌ها
    for name, o in ORG.organs.items():
        x, y = ORGAN_DEFS[name][1]
        h = o["health"] / 100
        color = f"rgb({int(255*(1-h)+40)}, {int(120+120*h)}, {int(90+60*h)})"
        fig.add_trace(go.Scatter(
            x=[x], y=[y], mode="markers+text", text=[name], textposition="top center",
            textfont=dict(size=10, color="#dfe8f5"), hoverinfo="text",
            hovertext=f"{name} — سلامت {o['health']:.0f}٪، فعالیت {o['activity']*100:.0f}٪",
            marker=dict(size=18 + 22 * o["activity"], color=color, opacity=0.9,
                        line=dict(color="#5fd4ff", width=1.5))))
    fig.update_layout(**DARK, height=430, showlegend=False,
                      xaxis=dict(visible=False, range=[-2.5, 2.5]),
                      yaxis=dict(visible=False, range=[-0.9, 3.1]))
    return fig


def fig_sensors(snap):
    z = snap["sensors"].reshape(20, 30)
    fig = go.Figure(go.Heatmap(z=z, colorscale="Viridis", showscale=False,
                               zmin=0, zmax=1, hoverinfo="skip"))
    fig.update_layout(**DARK, height=430,
                      title=f"{ORG.anomalies} ناهنجاری فعال | میانگین حس: {z.mean()*100:.0f}٪",
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


def fig_brain():
    names = list(BRAIN_REGIONS)
    counts = [int(NEURONS_TOTAL * BRAIN_REGIONS[r]) for r in names]
    acts = [ORG.region_activity[r] * 100 for r in names]
    fig = go.Figure(go.Bar(
        y=names, x=acts, orientation="h",
        text=[f"{a:.0f}٪ فعال — {c:,} نورون" for a, c in zip(acts, counts)],
        textposition="inside",
        marker=dict(color=acts, colorscale="Teal", cmin=0, cmax=100)))
    fig.update_layout(**DARK, height=300, xaxis=dict(range=[0, 100], title="فعالیت ٪"),
                      yaxis=dict(autorange="reversed"))
    return fig


def fig_emotions():
    e = ORG.emotions
    keys = list(e)
    vals = [e[k] * 100 for k in keys]
    fig = go.Figure(go.Scatterpolar(
        r=vals + [vals[0]], theta=keys + [keys[0]], fill="toself",
        fillcolor="rgba(125,255,158,0.12)", line=dict(color="#7dff9e")))
    fig.update_layout(**DARK, height=300,
                      polar=dict(radialaxis=dict(range=[0, 100], gridcolor="#1d2a3d"),
                                 angularaxis=dict(gridcolor="#1d2a3d"), bgcolor="rgba(0,0,0,0)"))
    return fig


def fig_spacetime(snap):
    theta = (snap["now"] - ORG.birth) * 0.5
    p2, w = tesseract_projection(theta)
    xs, ys = [], []
    for i, j in _TESS_E:
        xs += [p2[i, 0], p2[j, 0], None]
        ys += [p2[i, 1], p2[j, 1], None]
    drift, score = ORG.time_perception(snap["now"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", hoverinfo="skip",
                             line=dict(color="rgba(155,109,255,0.7)", width=1.3)))
    fig.add_trace(go.Scatter(x=p2[:, 0], y=p2[:, 1], mode="markers", hoverinfo="skip",
                             marker=dict(size=6, color=w, colorscale="Portland",
                                         cmin=-1, cmax=1)))
    fig.update_layout(**DARK, height=300, showlegend=False,
                      title=f"ادراک زمان: {score:.0f}٪ | انحراف {drift:.0f} میلی‌ثانیه",
                      xaxis=dict(visible=False), yaxis=dict(visible=False, scaleanchor="x"))
    return fig


def vitals_html(snap):
    now, env, h = snap["now"], snap["env"], ORG.heart
    age = now - ORG.birth
    items = [
        ("ضربان قلب", f"{h.bpm(now)} BPM"),
        ("ریتم", h.rhythm_label()),
        ("نسل فیبوناچی", f"F({h.n}) — {len(h.current_binary)} بیت"),
        ("بیت جاری قلب", str(h.last_bit)),
        ("مجموع ضربان‌ها", f"{h.total_beats:,}"),
        ("دمای بدن", f"{env['temp_c']:.1f}°C"),
        ("فشار حافظه", f"{env['mem']*100:.0f}٪"),
        ("بار پردازنده", f"{env['cpu']*100:.0f}٪"),
        ("تنفس داده", f"{ORG.net_recv_rate/1024:.1f} KB/s"),
        ("سن ارگانیسم", f"{int(age//60)}:{int(age%60):02d}"),
    ]
    cells = [html.Div(style={**CARD, "flex": "1 1 130px", "textAlign": "center"}, children=[
        html.Div(k, style={"color": "#7fa3c9", "fontSize": "11px"}),
        html.Div(v, style={"color": "#fff", "fontSize": "15px", "fontWeight": "bold"}),
    ]) for k, v in items]
    return html.Div(style={"display": "flex", "flexWrap": "wrap"}, children=cells)


def needs_html():
    rows = []
    for n, v in ORG.needs.items():
        color = "#7dff9e" if v > 60 else ("#ffd25f" if v > 35 else "#ff5f7a")
        rows.append(html.Div(style={"margin": "7px 0"}, children=[
            html.Div(f"{n}: {v:.0f}٪", style={"fontSize": "12px"}),
            html.Div(style={"background": "#131c2b", "borderRadius": "5px", "height": "9px"},
                     children=html.Div(style={"width": f"{v:.0f}%", "height": "100%",
                                              "background": color, "borderRadius": "5px",
                                              "transition": "width 0.5s"})),
        ]))
    return rows


def reasoning_html(snap):
    drift, score = ORG.time_perception(snap["now"])
    rows = [
        ("آی‌کیو ریاضی (بنچمارک فیبوناچی)", f"{IQ_MATH}"),
        ("آی‌کیو هندسی (بنچمارک ماتریس/هندسه)", f"{IQ_GEO}"),
        ("تجسم فضازمان", "چهارمکعبی چرخان — فعال"),
        ("ادراک زمان", f"{score:.0f}٪ (انحراف {drift:.0f}ms)"),
        ("قدرت تصمیم قلبی", f"{len(ORG.decisions)} تصمیم ثبت‌شده"),
    ]
    return [html.Div(style={"display": "flex", "justifyContent": "space-between",
                            "borderBottom": "1px solid #131c2b", "padding": "6px 2px",
                            "fontSize": "12px"}, children=[
                html.Span(k), html.Span(v, style={"color": "#5fd4ff", "fontWeight": "bold"})])
            for k, v in rows]


def feed_html(items, color):
    if not items:
        return html.Div("—")
    return [html.Div(style={"borderRight": f"2px solid {color}", "paddingRight": "8px",
                            "marginBottom": "8px", "opacity": max(0.35, 1 - i * 0.045)},
                     children=[
                html.Span(t, style={"color": "#557", "fontSize": "10px", "marginLeft": "6px"}),
                html.Span(x)]) for i, (t, x) in enumerate(items)]


@app.callback(
    [Output("ecg-graph", "figure"), Output("awareness-gauge", "figure"),
     Output("network-graph", "figure"), Output("sensor-heatmap", "figure"),
     Output("brain-graph", "figure"), Output("emotion-radar", "figure"),
     Output("spacetime-graph", "figure"), Output("vitals", "children"),
     Output("needs", "children"), Output("reasoning", "children"),
     Output("thoughts", "children"), Output("decisions", "children"),
     Output("status-bar", "children")],
    Input("life", "n_intervals"),
)
def life_tick(_):
    snap = ORG.tick()
    a = ORG.awareness
    badge = "#7dff9e" if a > 62 else ("#ffd25f" if a > 40 else "#ff5f7a")
    status = html.Div(style={**CARD, "display": "flex", "justifyContent": "space-between",
                             "alignItems": "center", "flexWrap": "wrap"}, children=[
        html.Div([
            html.Span("● ", style={"color": "#ff3355", "fontSize": "18px"}),
            html.Span("ارگانیسم دیجیتال زنده است", style={"fontWeight": "bold", "fontSize": "17px"}),
        ]),
        html.Div(f"سطح آگاهی: {a:.0f}٪ — {ORG.awareness_state}",
                 style={"background": badge, "color": "#05070d", "padding": "4px 14px",
                        "borderRadius": "20px", "fontWeight": "bold"}),
    ])
    return (fig_ecg(snap), fig_gauges(), fig_network(snap), fig_sensors(snap),
            fig_brain(), fig_emotions(), fig_spacetime(snap), vitals_html(snap),
            needs_html(), reasoning_html(snap),
            feed_html(ORG.thoughts, "#5fd4ff"), feed_html(ORG.decisions, "#ffd25f"),
            status)


if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=8050, debug=False)
    except AttributeError:
        app.run_server(host="0.0.0.0", port=8050, debug=False)
