#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧠 مغز زنده — نسخه ۱.۰ «تکینگی» (Singularity) — تک‌فایلی کامل
================================================================
🔮 تحلیل کاملاً غیرسنتی | صفر اندیکاتور کلاسیک | شهود‌محور مطلق
⚡ جریان تفکر باینری صریح و استنتاجی قبل از هر معامله
🖥 شتاب‌دهی GPU (CuPy) + موازی‌سازی CPU | تا ۲۵۰هزار نورون
اجرا:  python living_brain.py
"""
import math, os, time, zlib, threading, sqlite3, json, hashlib
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import numpy as np
import plotly.graph_objects as go
import requests
from dash import Dash, dcc, html, Input, Output, State, ctx, no_update

# ═══════════════════════ ۱) شتاب‌دهنده GPU/CPU ═══════════════════════
class GPUBackend:
    """شناسایی GPU و ارائه آرایه‌ساز بهینه (CuPy یا NumPy)."""
    def __init__(self):
        self.xp = np; self.gpu = False; self.name = "CPU/NumPy"; self.vram_gb = 0.0
        try:
            import cupy as cp
            if cp.cuda.runtime.getDeviceCount() > 0:
                self.xp = cp; self.gpu = True
                props = cp.cuda.runtime.getDeviceProperties(0)
                self.name = props.get("name", b"GPU").decode() if isinstance(props.get("name"), bytes) else str(props.get("name","GPU"))
                self.vram_gb = props.get("totalGlobalMem", 0)/(1024**3)
                # گرم‌کردن GPU
                a = cp.random.rand(512, 512).astype(cp.float32)
                _ = a @ a
        except Exception:
            self.gpu = False
    def asnumpy(self, a):
        if self.gpu:
            try:
                import cupy as cp; return cp.asnumpy(a)
            except Exception: return np.asarray(a)
        return np.asarray(a)
    @property
    def label(self):
        return f"{'🟢 GPU: '+self.name if self.gpu else '🔵 CPU: NumPy'}" + (f" | VRAM {self.vram_gb:.0f}G" if self.gpu else "")

GPU = GPUBackend()
xp = GPU.xp

# ═══════════════════════ ۲) ابزارها ═══════════════════════
def clamp(x, lo=0.0, hi=1.0): return lo if x < lo else (hi if x > hi else x)
def ema(prev, x, alpha=0.1): return prev + alpha * (x - prev)
def safe_div(a, b, default=0.0): return a / b if abs(b) > 1e-12 else default
def fmt_num(v, d=2):
    try: return f"{float(v):,.{d}f}"
    except Exception: return "—"

class RingBuffer:
    __slots__ = ("data",)
    def __init__(self, maxlen=300): self.data = deque(maxlen=int(maxlen))
    def push(self, v): self.data.append(float(v))
    def last(self, n=None):
        s = list(self.data); return s[-n:] if n else s
    def __len__(self): return len(self.data)

# ═══════════════════════ ۳) سخت‌افزار ═══════════════════════
def _logical_cores(): return os.cpu_count() or 2
def _physical_cores():
    try:
        import psutil; return psutil.cpu_count(logical=False) or _logical_cores()
    except ImportError: return max(1, _logical_cores()//2)
def _memory_gb():
    try:
        import psutil; return psutil.virtual_memory().total/(1024**3)
    except ImportError: return 8.0
def _benchmark(seconds=0.12):
    try:
        n = 192
        a = xp.random.rand(n, n).astype(xp.float32); b = xp.random.rand(n, n).astype(xp.float32)
        flops = 2*n**3; iters = 0; t0 = time.perf_counter()
        while time.perf_counter()-t0 < seconds:
            a @ b; iters += 1
        return flops/((time.perf_counter()-t0)/max(1, iters))/1e9
    except Exception: return 20.0

@dataclass
class HardwareProfile:
    cores: int; physical: int; memory: float; gflops: float; tier: str; scale: float
    ticks: int; parallel: bool; workers: int; gpu: bool; gpu_name: str
    @property
    def label(self):
        g = f" | GPU:{self.gpu_name}" if self.gpu else ""
        return f"CPU {self.cores} | {self.gflops:.0f}GF | رم {self.memory:.0f}G | {self.tier}{g}"

def profile_hardware():
    cores, phys, mem = _logical_cores(), _physical_cores(), _memory_gb()
    gf = _benchmark()
    if gf < 15 or cores <= 2: tier, scale, ticks = "ضعیف", 0.6, 10
    elif gf < 60: tier, scale, ticks = "متوسط", 1.2, 15
    elif gf < 150: tier, scale, ticks = "قوی", 2.4, 20
    else: tier, scale, ticks = "سرور", 3.5, 25
    if GPU.gpu: scale *= 1.6; ticks = min(30, ticks+5)
    if mem < 4: scale *= 0.6
    elif mem >= 16: scale *= 1.15
    scale = min(scale, 6.0)
    workers = max(2, min(12, phys or cores//2))
    parallel = cores >= 8
    p = HardwareProfile(cores, phys, mem, gf, tier, scale, ticks, parallel, workers, GPU.gpu, GPU.name)
    print("🖥 سخت‌افزار →", p.label)
    return p

# ═══════════════════════ ۴) پیکربندی ═══════════════════════
class _Config: pass
config = _Config()
config.HW = profile_hardware()
config.PROJECT_NAME = "مغز زنده"; config.VERSION = "1.0-singularity"
config.SUBTITLE = "تکینگی | تحلیل غیرسنتی | تفکر باینری | شهود مطلق"
config.TICKS_PER_SECOND = config.HW.ticks
config.DT = 1.0/config.TICKS_PER_SECOND
config.NEURON_SCALE = config.HW.scale*(1.8+min(config.HW.cores, 16)*0.20)
config.MAX_NEURONS = 250000 if GPU.gpu else 90000
config.PARALLEL_BRAIN = config.HW.parallel
config.N_WORKERS = config.HW.workers
config.N_QUANTUM_REGISTERS = 10; config.N_QUBITS_PER_REG = 8
config.BASE_DECOHERENCE = 0.012; config.ACTIVITY_DECOHERENCE = 0.05
config.INITIAL_CAPITAL = 500.0
config.N_SLOTS = 5
config.SLOT_MARGIN = config.INITIAL_CAPITAL/config.N_SLOTS
config.TAKER_FEE = 0.00055
config.MAX_CONCURRENT_POSITIONS = 5
config.RESET_COOLDOWN_TICKS = 40
config.SCAN_SYMBOL_LIMIT = 100
config.SCAN_DEEP_LIMIT = 6
config.SCAN_PERIOD = 3.0
config.SCAN_RESCAN_SEC = 6
config.SCAN_INTERVAL = "15"
config.SCAN_KLINE_LIMIT = 120
config.SIM_RATE = 6
config.SCALP_CARDIAC_GATE = 0.10
config.SIXTH_SENSE_GATE = 0.25
config.SENSORS_PER_SENSE = max(6, config.HW.cores*2)
config.N_XENO_SENSES = 120
config.SPACETIME_HISTORY = 256
# 🔥 تریل‌استاپ
config.TRAIL_START_R = 1.0
config.TRAIL_KEEP_RATIO = 0.6
# 🔮 دروازه‌های شهود و تفکر باینری
config.INTUITION_GATE = 0.55          # آستانه شهود برای شروع استنتاج
config.BINARY_PROBES = 14             # تعداد کاوشگرهای باینری
config.BINARY_MIN_RATIO = 0.62        # حداقل نسبت بیت‌های موافق
config.BINARY_FAST_LOCK_N = 4         # کاوشگرهای سریع اولیه
TRADING_MODES = {
    "swing": {"label": "🎯 سویینگ (لوریج ۱۰)", "leverage": 10, "tp_mult": 3.0, "sl_mult": 1.4,
              "conviction_threshold": 0.40, "decision_interval": 4, "use_geometry": True,
              "margin_fraction": 0.6, "max_daily": 15, "cost_aware": True},
    "scalp": {"label": "⚡ اسکالپ (لوریج ۲۰)", "leverage": 20, "tp_mult": 1.3, "sl_mult": 0.9,
              "conviction_threshold": 0.30, "decision_interval": 2, "use_geometry": False,
              "margin_fraction": 0.4, "max_daily": 100, "cost_aware": True},
}
config.HISTORY_WINDOW = 400
config.MAX_THOUGHTS_SHOWN = 25
config.DASH_INTERVAL_MS = 1000
config.DEFAULT_SPEED = 1
config.RANDOM_SEED = None
config.MEMORY_DB_PATH = "brain_memory.db"
config.TRADING_DB_PATH = "trading_memory.db"

# ═══════════════════════ ۵) دیتابیس‌ها ═══════════════════════
class MemoryDB:
    def __init__(self, path):
        self.path = path; self.lock = threading.Lock(); self._init()
        print(f"💾 دیتابیس حافظه: {path}")
    def _init(self):
        with self.lock:
            conn = sqlite3.connect(self.path); c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS experiences (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tick INTEGER, symbol TEXT,
                side TEXT, entry REAL, exit REAL, pnl REAL, outcome TEXT, created_at INTEGER)""")
            conn.commit(); conn.close()
    def store(self, tick, symbol, side, entry, exit_price, pnl, outcome):
        with self.lock:
            conn = sqlite3.connect(self.path); c = conn.cursor()
            c.execute("INSERT INTO experiences (tick,symbol,side,entry,exit,pnl,outcome,created_at) VALUES (?,?,?,?,?,?,?,?)",
                      (tick, symbol, side, entry, exit_price, pnl, outcome, int(time.time())))
            conn.commit(); conn.close()

class TradingDB:
    def __init__(self, path):
        self.path = path; self.lock = threading.Lock(); self._init()
        print(f"💾 دیتابیس معاملات: {path}")
    def _init(self):
        with self.lock:
            conn = sqlite3.connect(self.path); c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, engine TEXT, coin TEXT, side INTEGER,
                entry REAL, size REAL, margin REAL, leverage INTEGER, notional REAL,
                tp REAL, sl REAL, conviction REAL, reasons TEXT, commission REAL,
                spread_cost REAL, open_time TEXT, open_ts INTEGER, open_tick INTEGER,
                slot_id INTEGER, status TEXT DEFAULT 'open', exit_price REAL,
                exit_reason TEXT, net_pnl REAL, close_time TEXT, binary_bits TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS engine_state (
                engine TEXT PRIMARY KEY, slot_capitals TEXT, realized_pnl REAL,
                wins INTEGER, losses INTEGER, total_commission REAL, total_spread REAL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS lesson_stats (
                engine TEXT PRIMARY KEY, stats TEXT)""")
            # سازگاری با نسخه‌های قبل
            try: c.execute("ALTER TABLE positions ADD COLUMN binary_bits TEXT")
            except Exception: pass
            conn.commit(); conn.close()
    def save_open_position(self, engine, pos):
        with self.lock:
            conn = sqlite3.connect(self.path); c = conn.cursor()
            c.execute("""INSERT INTO positions (engine,coin,side,entry,size,margin,leverage,notional,
                tp,sl,conviction,reasons,commission,spread_cost,open_time,open_ts,open_tick,slot_id,status,binary_bits)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open',?)""",
                      (engine, pos["coin"], pos["side"], pos["entry"], pos["size"], pos["margin"],
                       pos["leverage"], pos["notional"], pos["tp"], pos["sl"], pos["conviction"],
                       json.dumps(pos["reasons"], ensure_ascii=False), pos["commission"], pos["spread_cost"],
                       pos["open_time"], pos["open_ts"], pos["open_tick"], pos["slot_id"], pos.get("binary_bits","")))
            conn.commit(); conn.close()
    def close_position(self, engine, coin, exit_price, exit_reason, net_pnl):
        with self.lock:
            conn = sqlite3.connect(self.path); c = conn.cursor()
            c.execute("""UPDATE positions SET status='closed', exit_price=?, exit_reason=?,
                net_pnl=?, close_time=? WHERE engine=? AND coin=? AND status='open'""",
                      (exit_price, exit_reason, net_pnl, time.strftime("%Y-%m-%d %H:%M:%S"), engine, coin))
            conn.commit(); conn.close()
    def load_positions(self, engine):
        with self.lock:
            conn = sqlite3.connect(self.path); c = conn.cursor()
            c.execute("SELECT * FROM positions WHERE engine=? ORDER BY id", (engine,))
            cols = [d[0] for d in c.description]
            rows = [dict(zip(cols, r)) for r in c.fetchall()]
            conn.close()
        open_pos = {}; closed = []
        for r in rows:
            try: r["reasons"] = json.loads(r["reasons"]) if r["reasons"] else []
            except Exception: r["reasons"] = []
            if r["status"] == "open": open_pos[r["coin"]] = r
            else: closed.append(r)
        return open_pos, closed
    def save_engine_state(self, engine, slot_capitals, realized_pnl, wins, losses, total_commission, total_spread):
        with self.lock:
            conn = sqlite3.connect(self.path); c = conn.cursor()
            c.execute("""INSERT OR REPLACE INTO engine_state (engine,slot_capitals,realized_pnl,
                wins,losses,total_commission,total_spread) VALUES (?,?,?,?,?,?,?)""",
                      (engine, json.dumps(slot_capitals), realized_pnl, wins, losses, total_commission, total_spread))
            conn.commit(); conn.close()
    def load_engine_state(self, engine):
        with self.lock:
            conn = sqlite3.connect(self.path); c = conn.cursor()
            c.execute("SELECT * FROM engine_state WHERE engine=?", (engine,))
            row = c.fetchone(); conn.close()
        if not row: return None
        try: caps = json.loads(row[1])
        except Exception: caps = []
        return {"slot_capitals": caps, "realized_pnl": row[2], "wins": row[3],
                "losses": row[4], "total_commission": row[5], "total_spread": row[6]}
    def save_lesson_stats(self, engine, stats):
        with self.lock:
            conn = sqlite3.connect(self.path); c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO lesson_stats (engine,stats) VALUES (?,?)",
                      (engine, json.dumps(stats, ensure_ascii=False)))
            conn.commit(); conn.close()
    def load_lesson_stats(self, engine):
        with self.lock:
            conn = sqlite3.connect(self.path); c = conn.cursor()
            c.execute("SELECT stats FROM lesson_stats WHERE engine=?", (engine,))
            row = c.fetchone(); conn.close()
        if not row: return {}
        try: return json.loads(row[0])
        except Exception: return {}
    def reset_engine(self, engine):
        with self.lock:
            conn = sqlite3.connect(self.path); c = conn.cursor()
            c.execute("DELETE FROM positions WHERE engine=?", (engine,))
            c.execute("DELETE FROM engine_state WHERE engine=?", (engine,))
            c.execute("DELETE FROM lesson_stats WHERE engine=?", (engine,))
            conn.commit(); conn.close()

# ═══════════════════════ ۶) کلاینت بایبیت ═══════════════════════
BYBIT_DOMAINS = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
class BybitHTTP:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json", "Referer": "https://www.bybit.com/",
            "Accept-Language": "en-US,en;q=0.9"})
        self.active = BYBIT_DOMAINS[0]; self.last_error = None
    def get(self, path, params, timeout=6):
        cands = [self.active]+[d for d in BYBIT_DOMAINS if d != self.active]
        for base in cands:
            try:
                r = self.session.get(f"{base}{path}", params=params, timeout=timeout)
                if r.status_code in (403, 451): continue
                r.raise_for_status(); d = r.json()
                if d.get("retCode") == 0: self.active = base; return d
            except Exception as e:
                self.last_error = f"{base.split('//')[1]}: {type(e).__name__}"; continue
        return None

# ═══════════════════════ ۷) تحلیلگر میدان غیرعلی (غیرسنتی مطلق) ═══════════════════════
class AcausalFieldAnalyzer:
    """
    🔮 تحلیل کاملاً غیرسنتی — هیچ میانگین متحرک، RSI، MACD یا اندیکاتور کلاسیکی وجود ندارد.
    بازار به‌عنوان یک «میدان اطلاعاتی» دیده می‌شود:
      • آنتروپی جایگشت (نظم الگوها)
      • پیچیدگی فشردگی (ساختار پنهان)
      • طیف‌نگاری FFT (چرخه‌های غالب)
      • هرست R/S (حافظه بلندمدت)
      • خمیدگی و پیچش هندسی
      • شار اطلاعاتی نامتقارن (جهت‌یابی بدون فرمول‌های کلاسیک)
    """
    def __init__(self):
        self.prev_state = {}

    def _perm_entropy(self, x, order=4, delay=1):
        n = len(x)
        N = n-(order-1)*delay
        if N < 12: return 0.5
        emb = np.empty((N, order))
        for i in range(order): emb[:, i] = x[i*delay:i*delay+N]
        pat = np.argsort(emb, axis=1)
        _, counts = np.unique(pat, axis=0, return_counts=True)
        p = counts/counts.sum()
        return float(-np.sum(p*np.log2(p+1e-12))/math.log2(math.factorial(order)))

    def _compression_complexity(self, x):
        if len(x) < 16: return 0.5
        d = np.diff(x)
        med = np.median(d)
        q = np.where(d > med, 1, 0).astype(np.uint8)
        raw = q.tobytes()
        comp = len(zlib.compress(raw, 6))
        return clamp(comp/max(1, len(raw)), 0, 1)

    def _spectral(self, x):
        n = len(x)
        if n < 24: return {"centroid": 0.5, "entropy": 0.5, "dominant_cycle": 0.0}
        y = x - np.linspace(x[0], x[-1], n)  # حذف روند خطی (غیر از اندیکاتور)
        P = np.abs(np.fft.rfft(y))**2
        P = P[1:]; f = np.fft.rfftfreq(n)[1:]
        s = P.sum()
        if s < 1e-12: return {"centroid": 0.5, "entropy": 0.5, "dominant_cycle": 0.0}
        Pn = P/s
        centroid = float(np.sum(f*Pn)/max(f[-1], 1e-12))
        ent = float(-np.sum(Pn*np.log(Pn+1e-12))/math.log(len(Pn)))
        dom_idx = int(np.argmax(P))
        dom_cycle = float(1.0/f[dom_idx]) if f[dom_idx] > 1e-9 else 0.0
        return {"centroid": centroid, "entropy": clamp(ent, 0, 1), "dominant_cycle": dom_cycle}

    def _hurst(self, x):
        n = len(x)
        if n < 40: return 0.5
        sizes = [2**k for k in range(3, int(np.log2(n))+1) if 2**k <= n]
        if len(sizes) < 2: return 0.5
        rs_vals = []
        for size in sizes:
            chunks = n//size; vals = []
            for cidx in range(chunks):
                seg = x[cidx*size:(cidx+1)*size]
                m = seg.mean(); dev = np.cumsum(seg-m)
                R = dev.max()-dev.min(); S = seg.std()+1e-12
                vals.append(R/S)
            if vals: rs_vals.append(float(np.mean(vals)))
        if len(rs_vals) < 2: return 0.5
        try:
            slope = float(np.polyfit(np.log(sizes[:len(rs_vals)]), np.log(np.array(rs_vals)+1e-9), 1)[0])
            return clamp(slope, 0, 1)
        except Exception: return 0.5

    def _curvature_flow(self, x):
        if len(x) < 6: return 0.0, 0.0
        d1 = np.diff(x); d2 = np.diff(d1)
        denom = (1+d1[:-1]**2)**1.5
        curv = float(np.mean(d2/(denom+1e-9)))
        torsion = float(np.mean(np.abs(np.diff(d2)))) if len(d2) > 2 else 0.0
        return curv*100, torsion*100

    def _info_flow_asymmetry(self, x):
        """جهت‌یابی از جنس اطلاعات، نه قیمت: آنتروپی حرکت‌های بالا در برابر پایین."""
        if len(x) < 20: return 0.0
        d = np.diff(x)
        up = d[d > 0]; dn = -d[d < 0]
        def ent(a):
            if len(a) < 4: return 0.0
            h, _ = np.histogram(a, bins=8)
            p = h/h.sum()+1e-9
            return float(-np.sum(p*np.log2(p))/3.0)
        eu, ed = ent(up), ent(dn)
        base = max(eu+ed, 1e-9)
        asym = (ed-eu)/base  # اگر حرکت‌های بالا منظم‌ترند → جریان صعودی
        mag = clamp(abs(d).mean()/ (abs(x).mean()+1e-9)*80, 0, 1)
        return clamp(asym*1.4, -1, 1)* (0.4+0.6*mag)

    def analyze(self, o, h, l, c, key=""):
        if c is None or len(c) < 24: return {"ready": False}
        n = len(c)
        price = float(c[-1])
        pe = self._perm_entropy(c[-64:])
        comp = self._compression_complexity(c[-64:])
        spec = self._spectral(c[-96:])
        hurst = self._hurst(c[-96:])
        curv, torsion = self._curvature_flow(c[-32:])
        flow = self._info_flow_asymmetry(c[-48:])
        recent = min(20, n)
        ranges = h[-recent:]-l[-recent:]
        volatility = float(np.mean(ranges))
        lookback = min(60, n)
        resistance = float(h[-lookback:].max()); support = float(l[-lookback:].min())
        pos_in_range = safe_div(c[-1]-support, resistance-support, 0.5)
        # میدان جهت‌دار: ترکیب شار اطلاعاتی و خمیدگی
        field_dir = clamp(flow*0.75 + clamp(curv, -1, 1)*0.25, -1.5, 1.5)
        conviction = clamp(abs(field_dir)*(0.55+0.45*(1-pe))*(0.6+0.4*hurst), 0, 1)
        reasons = []
        if pe < 0.55: reasons.append("🧩 نظم الگویی بالا")
        if comp < 0.45: reasons.append("🗜️ ساختار فشرده پنهان")
        if spec["entropy"] < 0.5: reasons.append("🎵 چرخه غالب spectral")
        if hurst > 0.58: reasons.append("🧬 حافظه پایدار (هرست)")
        elif hurst < 0.42: reasons.append("🌀 رفتار ضدپایدار")
        if flow > 0.25: reasons.append("🌊 شار اطلاعاتی صعودی")
        elif flow < -0.25: reasons.append("🌊 شار اطلاعاتی نزولی")
        if abs(curv) > 0.3: reasons.append("🌀 خمیدگی میدان")
        prev = self.prev_state.get(key, {})
        delta_order = (prev.get("pe", pe)-pe)
        if delta_order > 0.03: reasons.append("📉 کاهش آنتروپی (نظم‌یابی)")
        self.prev_state[key] = {"pe": pe, "centroid": spec["centroid"]}
        signal = float(field_dir)
        return {"ready": True, "price": price, "signal": signal, "conviction": float(conviction),
                "velocity": float(flow), "acceleration": 0.0,
                "trend_strength": float(clamp(hurst-0.5, -1, 1)*2),
                "volatility": volatility, "resistance": resistance, "support": support,
                "pos_in_range": float(pos_in_range),
                "is_strong_bull": bool(flow > 0.5), "is_strong_bear": bool(flow < -0.5),
                "bull_rejection": False, "bear_rejection": False,
                "reasons": reasons,
                "features": {"perm_entropy": pe, "complexity": comp,
                             "spectral_centroid": spec["centroid"], "spectral_entropy": spec["entropy"],
                             "dominant_cycle": spec["dominant_cycle"], "hurst": hurst,
                             "curvature": curv, "torsion": torsion, "info_flow": flow}}

# ═══════════════════════ ۸) حس اقتصادی (هوش بازار) ═══════════════════════
class EconomicSense:
    """درک جریان نقدینگی، فشار میکرواستراکچر و گرمای بازار — بدون هیچ اندیکاتوری."""
    def __init__(self):
        self.turnover_hist = {}
        self.spread_hist = {}
    def analyze(self, tk, features=None):
        sym = tk["symbol"]
        to = tk.get("turnover", 0)
        sp = tk.get("spread_pct", 0)
        th = self.turnover_hist.setdefault(sym, deque(maxlen=64))
        sh = self.spread_hist.setdefault(sym, deque(maxlen=64))
        th.append(to); sh.append(sp)
        if len(th) < 4:
            return {"ready": False, "pressure": 0.0, "heat": 0.0, "vacuum": 0.0}
        t_arr = np.array(list(th)); s_arr = np.array(list(sh))
        t_mu, t_sd = t_arr.mean(), t_arr.std()+1e-12
        heat = clamp((t_arr[-1]-t_mu)/(t_sd*2)+0.5, 0, 1)  # فوران نقدینگی
        s_mu = s_arr.mean()
        vacuum = clamp((s_mu-s_arr[-1])/ (s_mu+1e-9), 0, 1)  # مکش اسپرد = حضور نقدینگی
        chg = tk.get("change24h", 0)
        pressure = clamp(math.tanh(chg*8)*0.6 + (heat-0.5)*0.8, -1, 1)
        return {"ready": True, "pressure": float(pressure), "heat": float(heat),
                "vacuum": float(vacuum), "turnover_z": float((t_arr[-1]-t_mu)/t_sd)}

# ═══════════════════════ ۹) هندسه‌دان تکاملی ═══════════════════════
class GeometryAnalyzer:
    GOLDEN = 0.618
    def find_swings(self, h, l, window=3):
        n = len(h); highs = []; lows = []
        for i in range(window, n-window):
            if h[i] == max(h[i-window:i+window+1]): highs.append(float(h[i]))
            if l[i] == min(l[i-window:i+window+1]): lows.append(float(l[i]))
        return highs, lows
    def fib_levels(self, high, low):
        diff = high-low
        return {"0.0(High)": high, "0.382": high-diff*0.382, "0.5": high-diff*0.5,
                "0.618(طلایی)": high-diff*self.GOLDEN, "1.0(Low)": low}
    def analyze(self, o, h, l, c):
        if c is None or len(c) < 20: return {"ready": False, "levels": {}, "trend": 0, "sniper_zones": []}
        highs, lows = self.find_swings(h, l, window=3)
        if not highs or not lows: return {"ready": False, "levels": {}, "trend": 0, "sniper_zones": []}
        recent_high = max(highs[-3:]); recent_low = min(lows[-3:])
        levels = self.fib_levels(recent_high, recent_low)
        trend = 0
        if len(highs) >= 2 and len(lows) >= 2:
            hh = highs[-1] > highs[-2]; hl = lows[-1] > lows[-2]
            lh = highs[-1] < highs[-2]; ll = lows[-1] < lows[-2]
            if hh and hl: trend = 1
            elif lh and ll: trend = -1
        price = float(c[-1]); sniper_zones = []
        for name, lvl in levels.items():
            dist_pct = abs(price-lvl)/price
            if dist_pct < 0.005: sniper_zones.append({"level": name, "price": float(lvl), "dist_pct": dist_pct})
        return {"ready": True, "levels": levels, "trend": trend, "sniper_zones": sniper_zones,
                "recent_high": recent_high, "recent_low": recent_low}

# ═══════════════════════ ۱۰) درک اکنون ابدی ═══════════════════════
class EternalNowPerception:
    def __init__(self):
        self.coherence = 0.5; self.eternal_now_score = 0.5
        self.last_direction = 0; self.n_scales = 0
    def perceive(self, closes, ratios=(1, 4, 16, 32)):
        closes = np.asarray(closes, dtype=float)
        if len(closes) < 40:
            return {"coherence": 0.5, "direction": 0, "eternal_now": 0.5, "n_scales": 0}
        directions = []; momentums = []
        for r in ratios:
            need = r*10
            if len(closes) < need: continue
            n_groups = len(closes)//r
            agg = np.array([np.mean(closes[j*r:(j+1)*r]) for j in range(n_groups)])
            if len(agg) < 10: continue
            short = np.mean(agg[-5:])
            long = np.mean(agg[-20:]) if len(agg) >= 20 else np.mean(agg)
            d = short-long
            scale = max(abs(long), 1e-9)
            directions.append(np.sign(d))
            momentums.append(clamp(d/scale*20, -1, 1))
        if not directions:
            self.coherence = 0.5; self.eternal_now_score = 0.5
            self.last_direction = 0; self.n_scales = 0
            return {"coherence": 0.5, "direction": 0, "eternal_now": 0.5, "n_scales": 0}
        dir_arr = np.array(directions, dtype=float)
        coherence = abs(float(np.mean(dir_arr)))
        unified_dir = int(np.sign(np.mean(dir_arr)))
        mom_consensus = abs(float(np.mean(momentums)))
        eternal_now = 0.6*coherence+0.4*mom_consensus
        self.coherence = coherence; self.eternal_now_score = eternal_now
        self.last_direction = unified_dir; self.n_scales = len(directions)
        return {"coherence": coherence, "direction": unified_dir,
                "eternal_now": eternal_now, "n_scales": len(directions)}

# ═══════════════════════ ۱۱) درک عددی و بصری فوق‌بشری ═══════════════════════
class AdvancedNumericalPerception:
    def __init__(self, numerical_iq, superhuman_factor):
        self.numerical_iq = numerical_iq; self.shf = superhuman_factor
        self.price_history = deque(maxlen=256); self.velocity_history = deque(maxlen=128)
    def feed(self, price):
        self.price_history.append(float(price))
        if len(self.price_history) >= 2:
            self.velocity_history.append(self.price_history[-1]-self.price_history[-2])
    def derivatives(self):
        if len(self.price_history) < 4: return {"velocity": 0.0, "acceleration": 0.0, "jerk": 0.0}
        p = list(self.price_history)
        v1 = p[-1]-p[-2]; v2 = p[-2]-p[-3]; a1 = v1-v2
        v3 = p[-3]-p[-4]; a2 = v2-v3; jerk = a1-a2
        base = max(abs(p[-1]), 1e-9)
        return {"velocity": v1/base, "acceleration": a1/base, "jerk": jerk/base}
    def fib_structure(self):
        if len(self.price_history) < 20: return {"fib_alignment": 0.0, "golden_present": False}
        p = list(self.price_history)[-100:]
        hi = max(p); lo = min(p); rng = hi-lo
        if rng <= 0: return {"fib_alignment": 0.0, "golden_present": False}
        fibs = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
        levels = [hi-f*rng for f in fibs]
        cur = p[-1]
        min_dist = min(abs(cur-l)/rng for l in levels)
        alignment = clamp(1.0-min_dist*8, 0, 1)
        golden_present = abs(cur-(hi-0.618*rng))/rng < 0.02
        return {"fib_alignment": alignment, "golden_present": golden_present}
    def harmonic_score(self):
        if len(self.velocity_history) < 16: return 0.0
        try:
            arr = np.array(list(self.velocity_history)[-32:]); arr = arr-arr.mean()
            if arr.std() < 1e-9: return 0.0
            c = np.corrcoef(arr[:-1], arr[1:])[0, 1]
            return clamp(abs(c), 0, 1)
        except Exception: return 0.0
    def perceive(self, price):
        self.feed(price)
        d = self.derivatives(); fib = self.fib_structure(); harm = self.harmonic_score()
        depth = self.numerical_iq*self.shf
        return {"velocity": d["velocity"], "acceleration": d["acceleration"], "jerk": d["jerk"],
                "fib_alignment": fib["fib_alignment"], "golden_present": fib.get("golden_present", False),
                "harmonic": harm, "depth": depth}

class VisualPerception:
    def __init__(self, visual_iq, superhuman_factor):
        self.visual_iq = visual_iq; self.shf = superhuman_factor
        self.candles = deque(maxlen=64)
    def feed(self, o, h, l, c):
        self.candles.append((float(o), float(h), float(l), float(c)))
    def detect_patterns(self):
        if len(self.candles) < 3: return {"pattern": "none", "strength": 0.0, "bias": 0}
        cs = list(self.candles)[-5:]
        o, h, l, c = cs[-1]
        body = abs(c-o); rng = max(h-l, 1e-9)
        lower_wick = (min(o, c)-l)/rng; upper_wick = (h-max(o, c))/rng
        patterns = []; bias = 0
        if lower_wick > 0.6 and body/rng < 0.3: patterns.append("hammer"); bias += 1
        if upper_wick > 0.6 and body/rng < 0.3: patterns.append("shooting_star"); bias -= 1
        if len(cs) >= 2:
            po, ph, pl, pc = cs[-2]
            if c > o and pc < po and c > po and o < pc: patterns.append("bull_engulf"); bias += 2
            if c < o and pc > po and c < po and o > pc: patterns.append("bear_engulf"); bias -= 2
        if len(cs) >= 3:
            up3 = all(cs[i][3] > cs[i][1] for i in range(-3, 0))
            dn3 = all(cs[i][3] < cs[i][1] for i in range(-3, 0))
            if up3: patterns.append("three_soldiers"); bias += 2
            if dn3: patterns.append("three_crows"); bias -= 2
        strength = clamp(abs(bias)/3, 0, 1)*self.visual_iq*self.shf
        pattern = patterns[-1] if patterns else "none"
        return {"pattern": pattern, "strength": clamp(strength, 0, 1), "bias": bias}
    def perceive(self, o, h, l, c):
        self.feed(o, h, l, c)
        return self.detect_patterns()

# ═══════════════════════ ۱۲) آرایه حسی فرازمینی + فضازمان ═══════════════════════
XENO_SENSE_TYPES = ["بینایی 👁️", "شنوایی 👂", "لامسه ✋", "بویایی 👃", "چشایی 👅"]
XENO_ALIEN_SENSE_NAMES = ["حس میدان", "حس خمیدگی", "حس آنتروپی", "حس رتبه", "حس شتاب",
                          "حس تشدید", "حس همبستگی", "حس شکاف", "حس پژواک", "حس سایه", "حس رزونانس", "حس چگالی",
                          "حس شار", "حس گرداب", "حس انبساط", "حس انقباض", "حس فاز", "حس تداخل", "حس هارمونیک", "حس آشوب"]

class XenoSensor:
    def __init__(self, sensor_id, sense_name, rng):
        self.id = sensor_id; self.sense = sense_name
        self.window = int(rng.choice([5, 10, 20, 40, 60]))
        self.transform = str(rng.choice(["raw", "diff", "accel", "rank", "entropy", "curvature", "spread"]))
        self.activation = 0.0
    def fire(self, prices):
        if prices is None or len(prices) < 2:
            self.activation = 0.0; return 0.0
        w = np.asarray(prices, dtype=float)[-self.window:]
        if len(w) < 2:
            self.activation = 0.0; return 0.0
        mean_abs = np.mean(np.abs(w))+1e-9
        if self.transform == "raw": val = np.abs(w[-1]-w[0])/mean_abs
        elif self.transform == "diff": val = np.mean(np.abs(np.diff(w)))/mean_abs
        elif self.transform == "accel":
            d = np.diff(w); val = np.mean(np.abs(np.diff(d)))/mean_abs if len(d) > 1 else 0.0
        elif self.transform == "rank": val = np.argsort(np.argsort(w))[-1]/len(w)
        elif self.transform == "entropy":
            d = np.abs(np.diff(w)); s = d.sum()
            if s < 1e-9: val = 0.0
            else:
                p = d/s; val = float(-np.sum(p*np.log(p+1e-9)))/np.log(len(p)+1e-9)
        elif self.transform == "curvature": val = self._curvature(w)
        elif self.transform == "spread": val = (w.max()-w.min())/mean_abs
        else: val = 0.0
        self.activation = float(clamp(val, 0, 1)); return self.activation
    def _curvature(self, w):
        if len(w) < 3: return 0.0
        d1 = np.diff(w); d2 = np.diff(d1)
        denom = (1+d1[:-1]**2)**1.5
        return float(np.mean(np.abs(d2)/(denom+1e-9))*10)

class XenoSensoryArray:
    def __init__(self, rng, sensors_per_sense, n_alien):
        self.rng = rng; self.sensors = []
        for sense in XENO_SENSE_TYPES:
            for i in range(sensors_per_sense):
                self.sensors.append(XenoSensor(len(self.sensors), sense, rng))
        for i in range(n_alien):
            name = XENO_ALIEN_SENSE_NAMES[i % len(XENO_ALIEN_SENSE_NAMES)]
            self.sensors.append(XenoSensor(len(self.sensors), f"✨{name}", rng))
        self.total = len(self.sensors)
        self.activation_history = deque(maxlen=128)
        print(f"🌌 آرایه حسی فرازمینی: {self.total} حسگر فعال")
    def fire_all(self, prices):
        acts = [s.fire(prices) for s in self.sensors]
        total_act = float(np.mean(acts)) if acts else 0.0
        self.activation_history.append(total_act)
        return total_act, acts
    def sense_summary(self):
        agg = {}; counts = {}
        for s in self.sensors:
            agg[s.sense] = agg.get(s.sense, 0.0)+s.activation
            counts[s.sense] = counts.get(s.sense, 0)+1
        return {k: agg[k]/max(1, counts[k]) for k in agg}
    def top_active(self, n=8):
        ranked = sorted(self.sensors, key=lambda s: -s.activation)
        return [(s.sense, round(s.activation, 2)) for s in ranked[:n]]

class SpacetimePerception:
    def __init__(self, history_size=256):
        self.field = deque(maxlen=history_size)
        self.metric_history = deque(maxlen=128)
    def feed(self, price, tick):
        self.field.append((float(tick), float(price)))
    def _empty(self):
        return {"arc_length": 0.0, "curvature": 0.0, "slope": 0.0, "expansion": 0.0,
                "fractal_dim": 1.0, "dimensionality": 1.0}
    def compute_geometry(self):
        if len(self.field) < 10:
            g = self._empty(); self.metric_history.append(g); return g
        pts = np.array(list(self.field))
        t = pts[:, 0]; p = pts[:, 1]
        t_span = max(t[-1]-t[0], 1.0); p_span = max(p.max()-p.min(), 1e-9)
        t_norm = (t-t[0])/t_span; p_norm = (p-p.min())/p_span
        dt = np.diff(t_norm); dp = np.diff(p_norm)
        ds = np.sqrt(dt**2+dp**2)
        arc_length = float(np.sum(ds))
        d1 = dp/(dt+1e-9); d2 = np.diff(d1)
        curvature = float(np.mean(np.abs(d2))) if len(d2) > 0 else 0.0
        slope = float(np.mean(d1))
        local_vol = np.abs(dp)
        if len(local_vol) >= 4:
            h1 = local_vol[:len(local_vol)//2].mean(); h2 = local_vol[len(local_vol)//2:].mean()
            expansion = float((h2-h1)/(h1+1e-9))
        else: expansion = 0.0
        fractal = self._fractal_dimension(p_norm)
        g = {"arc_length": arc_length, "curvature": curvature, "slope": slope,
             "expansion": expansion, "fractal_dim": fractal,
             "dimensionality": 1.0+min(fractal-1.0, 1.0)}
        self.metric_history.append(g); return g
    def _fractal_dimension(self, p):
        try:
            if len(p) < 8: return 1.0
            counts = []
            for nbox in [4, 8, 16]:
                edges = np.linspace(p.min(), p.max()+1e-9, nbox+1)
                hist, _ = np.histogram(p, edges)
                counts.append(np.sum(hist > 0))
            if counts[0] <= 1: return 1.0
            x = np.log([4, 8, 16]); y = np.log(np.array(counts)+1e-9)
            slope = float(np.polyfit(x, y, 1)[0])
            return float(clamp(abs(slope), 1.0, 2.0))
        except Exception: return 1.0
    def richness(self):
        if not self.metric_history: return 0.0
        g = self.metric_history[-1]
        return clamp(g["curvature"]*2+(g["fractal_dim"]-1.0)+abs(g["expansion"])*0.5, 0, 1)

# ═══════════════════════ ۱۳) آگاهی بدن + حواس جمع ═══════════════════════
class InteroceptionSystem:
    def __init__(self):
        self.body_awareness = 0.5
        self.signals = {}
    def perceive(self, body):
        heartbeat = clamp(body.cardiac.icns_activity, 0, 1)
        energy = clamp(body.energy, 0, 1)
        hunger = body.sensory.get("hunger", 0)
        breath = clamp(1.0-abs(body.co2-40)/30, 0, 1)
        temp = clamp(1.0-abs(body.temperature-36.8)/2, 0, 1)
        self.signals = {"heartbeat": heartbeat, "energy": energy, "hunger": hunger,
                        "breath": breath, "temperature": temp}
        vals = list(self.signals.values())
        self.body_awareness = clamp(sum(vals)/len(vals), 0, 1)
        return self.body_awareness

class AttentionSystem:
    def __init__(self):
        self.focus_level = 0.5
        self.attention_target = None
    def focus(self, signals, consciousness):
        if not signals:
            self.focus_level = ema(self.focus_level, 0.35, 0.1)
            return self.focus_level
        strongest = max(signals, key=lambda s: s["conviction"])
        self.attention_target = strongest["symbol"]
        target_focus = clamp(strongest["conviction"]*0.7+consciousness/100*0.3, 0, 1)
        self.focus_level = ema(self.focus_level, target_focus, 0.15)
        return self.focus_level

# ═══════════════════════ ۱۴) ذهن ریاضیدان فوق‌بشری (بِیزی + تنسوری) ═══════════════════════
class HyperMathematicalMind:
    def __init__(self, iq_factor=2.5):
        self.iq_factor = iq_factor
        self.growth = 0.0
        self.prediction_history = deque(maxlen=200)
        self.accuracy = 0.5
        self.iq_display = 200
        self.bayes_prob = 0.5
        self.inference_depth = 0
    def bayes_update(self, evidence_dir, evidence_strength):
        """به‌روزرسانی بِیزی باور جهت بازار."""
        prior = self.bayes_prob
        likelihood_ratio = math.exp(evidence_dir*evidence_strength*self.iq_factor)
        posterior_odds = (prior/(1-prior+1e-9))*likelihood_ratio
        self.bayes_prob = clamp(posterior_odds/(1+posterior_odds), 0.01, 0.99)
        return self.bayes_prob
    def analyze_from_signals(self, signals, current_price):
        if not signals:
            return {"probability": 0.5, "confidence": 0.0, "iq_score": 0.0, "insight": "داده‌ای نیست"}
        dirs = [s["signal"] for s in signals]
        convs = [s["conviction"] for s in signals]
        total_conv = sum(abs(c) for c in convs)+1e-9
        weighted_dir = sum(d*abs(c) for d, c in zip(dirs, convs))/total_conv
        prob_up = self.bayes_update(weighted_dir, clamp(abs(weighted_dir), 0, 1))
        n_conf = min(1.0, len(signals)/8)
        avg_conv = sum(convs)/len(convs)
        confidence = clamp(n_conf*0.4+avg_conv*0.6, 0, 1)
        iq_score = clamp(abs(weighted_dir)*self.iq_factor+self.growth, 0, 1)
        self.inference_depth = min(99, self.inference_depth+1)
        self.iq_display = int(200+self.growth*150)
        if abs(weighted_dir) > 0.8: insight = "الگوی ریاضی بسیار قوی"
        elif abs(weighted_dir) > 0.4: insight = "روند ریاضی مشخص"
        elif abs(weighted_dir) > 0.15: insight = "روند ریاضی ملایم"
        else: insight = "بازار در تعادل ریاضی"
        return {"probability": prob_up, "confidence": confidence,
                "iq_score": iq_score, "insight": insight, "weighted_dir": weighted_dir}
    def learn(self, predicted_side, was_profitable):
        correct = 1 if was_profitable else 0
        self.prediction_history.append(correct)
        recent = list(self.prediction_history)[-50:]
        self.accuracy = sum(recent)/len(recent) if recent else 0.5
        if self.accuracy > 0.55: self.growth = clamp(self.growth+0.02, 0, 1.0)
        elif self.accuracy < 0.45: self.growth = clamp(self.growth-0.01, 0, 1.0)
        self.iq_display = int(200+self.growth*150)
        return self.accuracy

# ═══════════════════════ ۱۵) هسته شهود انقلابی (IntuitionCore) ═══════════════════════
class IntuitionCore:
    """
    🔮 دروازه ورود: فقط شهود. هیچ فرمول سنتی در کار نیست.
    همه حس‌ها در یک میانگین هندسی وزنی با مدولاسیون کوانتومی ذوب می‌شوند.
    """
    def __init__(self, phenotype):
        self.p = phenotype
        self.last_intuition = 0.0
        self.last_direction = 0
    def fuse(self, field_dir, field_conv, features, econ, sixth, st_rich, st_expansion,
             eternal_dir, eternal_score, cardiac_coh, quantum_coh, math_prob, direction):
        shf = self.p.superhuman_factor
        # هم‌راستایی هر حس با جهت شهودی
        def align(v): return clamp(0.5+0.5*v*direction, 0.03, 1.0)
        comps = {
            "field": align(field_dir)*(0.5+0.5*field_conv),
            "order": align((0.6-features.get("perm_entropy", 0.5))*2),
            "memory": align((features.get("hurst", 0.5)-0.5)*3),
            "econ": align(econ.get("pressure", 0))*(0.4+0.6*econ.get("heat", 0)),
            "xeno": align(1 if sixth > config.SIXTH_SENSE_GATE else -0.3)*(0.3+0.7*sixth),
            "spacetime": align(st_expansion*direction)*(0.3+0.7*st_rich),
            "eternal": align(eternal_dir*direction)*eternal_score,
            "heart": 0.35+0.65*cardiac_coh,
            "quantum": 0.35+0.65*quantum_coh,
            "math": align((math_prob-0.5)*2),
        }
        weights = {
            "field": 1.3*self.p.acausal_field, "order": 0.9, "memory": 1.0,
            "econ": 1.1*self.p.economic_sense, "xeno": 1.3*self.p.xeno_sense,
            "spacetime": 1.1*self.p.spacetime, "eternal": 1.2*self.p.presence,
            "heart": 0.9*self.p.cardiac_neural, "quantum": 0.7, "math": 1.1*self.p.numerical_iq,
        }
        # میانگین هندسی وزنی → هم‌افزایی غیرخطی
        log_sum = sum(weights[k]*math.log(comps[k]+1e-9) for k in comps)
        w_total = sum(weights.values())
        intuition = math.exp(log_sum/w_total)
        intuition = clamp(intuition*(0.85+0.30*shf)*(0.8+0.2*self.p.intuition_core), 0, 1)
        self.last_intuition = intuition; self.last_direction = direction
        active = [k for k in comps if comps[k] > 0.6]
        return {"intuition": float(intuition), "components": {k: float(v) for k, v in comps.items()},
                "active_senses": active}

# ═══════════════════════ ۱۶) جریان تفکر باینری صریح ═══════════════════════
class BinaryCognitionStream:
    """
    ⚡ جریان باینری تفکر پیچیده و استنتاجی:
    قبل از هر ورود، ۱۴ کاوشگر مستقل رأی باینری می‌دهند → رشته‌بیت تصمیم.
    سریع، صریح، قابل‌مشاهده. اجماع = ورود.
    """
    def __init__(self, rng):
        self.rng = rng
        self.history = deque(maxlen=16)
        self.total_cascades = 0; self.total_triggers = 0
    def cascade(self, direction, ctx):
        """ctx: dict از همه حس‌ها. خروجی: bits, ratio, fast_lock, decision"""
        t0 = time.perf_counter()
        f = ctx.get("features", {})
        econ = ctx.get("econ", {})
        probes = [
            ("شار اطلاعاتی هم‌سو", ctx.get("field_dir", 0)*direction > 0.12),
            ("نظم الگویی (آنتروپی کم)", f.get("perm_entropy", 1) < 0.66),
            ("حافظه پایدار هرست", f.get("hurst", 0.5) > 0.52),
            ("چرخه غالب طیفی", f.get("spectral_entropy", 1) < 0.72),
            ("ساختار فشرده پنهان", f.get("complexity", 1) < 0.75),
            ("خمیدگی هم‌جهت", f.get("curvature", 0)*direction > -0.05),
            ("فشار اقتصادی هم‌سو", econ.get("pressure", 0)*direction > 0.05),
            ("گرمای نقدینگی", econ.get("heat", 0) > 0.45),
            ("حس ششم فعال", ctx.get("sixth", 0) > config.SIXTH_SENSE_GATE),
            ("فضازمان غنی", ctx.get("st_rich", 0) > 0.30),
            ("اکنون ابدی هم‌سو", ctx.get("eternal_dir", 0)*direction > 0),
            ("همدلی قلب", ctx.get("cardiac_coh", 0) > 0.40),
            ("انسجام کوانتومی", ctx.get("quantum_coh", 0) > 0.25),
            ("احتمال ریاضی هم‌سو", (ctx.get("math_prob", 0.5)-0.5)*direction > 0.02),
        ]
        bits = "".join("1" if ok else "0" for _, ok in probes)
        ones = bits.count("1"); ratio = ones/len(bits)
        fast_lock = bits[:config.BINARY_FAST_LOCK_N].count("1") == config.BINARY_FAST_LOCK_N
        passed = ratio >= config.BINARY_MIN_RATIO and (fast_lock or ratio >= 0.78)
        decision = ("LONG" if direction > 0 else "SHORT") if passed else "—"
        latency_us = (time.perf_counter()-t0)*1e6
        self.total_cascades += 1
        if passed: self.total_triggers += 1
        rec = {"tick": ctx.get("tick", 0), "symbol": ctx.get("symbol", "?"), "bits": bits,
               "ratio": ratio, "fast_lock": fast_lock, "passed": passed, "decision": decision,
               "latency_us": latency_us, "probes": [(name, ok) for name, ok in probes]}
        self.history.appendleft(rec)
        return rec

# ═══════════════════════ ۱۷) تنظیم‌گر احساسات ═══════════════════════
class EmotionalRegulator:
    def __init__(self, discipline, emotional_control, calm):
        self.discipline = discipline; self.emotional_control = emotional_control; self.calm = calm
        self.fear = 0.0; self.greed = 0.0
        self.consecutive_losses = 0; self.consecutive_wins = 0
        self.state = "آرام و منضبط"
    def on_trade_closed(self, pnl, capital):
        impact = abs(pnl)/max(capital, 1)
        if pnl < 0:
            self.consecutive_losses += 1; self.consecutive_wins = 0
            self.fear = clamp(self.fear+0.12+impact*2+0.04*self.consecutive_losses)
            self.greed = clamp(self.greed-0.1)
        else:
            self.consecutive_wins += 1; self.consecutive_losses = 0
            self.greed = clamp(self.greed+0.10+impact*1.5+0.03*self.consecutive_wins)
            self.fear = clamp(self.fear-0.08)
    def update(self, drawdown=0.0, volatility=0.0):
        self.fear = clamp(self.fear+drawdown*0.4+volatility*0.15)
        control_power = self.discipline*0.5+self.emotional_control*0.3+self.calm*0.2
        decay = 0.03+0.10*control_power
        self.fear = clamp(self.fear-decay); self.greed = clamp(self.greed-decay)
        if self.fear > 0.6: self.state = "⚠️ ترس بالا (احتیاط)"
        elif self.greed > 0.6: self.state = "⚠️ طمع بالا (قفل سود)"
        elif self.fear > 0.35: self.state = "هوشیار"
        elif self.greed > 0.35: self.state = "متمایل به طمع"
        else: self.state = "آرام و منضبط"
    def emotional_calm(self): return clamp(1.0-max(self.fear, self.greed), 0, 1)
    def size_multiplier(self):
        emotional_excess = max(self.fear, self.greed)
        control = self.discipline*0.6+self.calm*0.4
        penalty = emotional_excess*(1.0-control)
        return clamp(1.0-penalty*0.5, 0.4, 1.0)
    def conviction_modifier(self):
        emotional_excess = max(self.fear, self.greed)
        control = self.discipline*0.7+self.emotional_control*0.3
        return emotional_excess*(1.0-control)*0.15

# ═══════════════════════ ۱۸) مدیر لحظه‌ای با تریل‌استاپ ═══════════════════════
class ActivePositionManager:
    def __init__(self, discipline, patience):
        self.discipline = discipline; self.patience = patience
        self.trail_log = []
    def manage(self, pos, tk, regulator, analysis=None):
        side = pos["side"]; entry = pos["entry"]
        cur = tk["bid"] if side > 0 else tk["ask"]
        initial_risk = abs(entry-pos["sl"])
        if initial_risk <= 0: return None
        pnl = (cur-entry)*side
        r_mult = pnl/initial_risk
        if side > 0: pos["peak"] = max(pos.get("peak", entry), cur)
        else: pos["peak"] = min(pos.get("peak", entry), cur)
        momentum = analysis.get("signal", 0) if analysis else 0
        momentum_aligned = momentum*side
        if r_mult >= config.TRAIL_START_R:
            trail_r = min(r_mult-0.5, r_mult*config.TRAIL_KEEP_RATIO)
            old_sl = pos["sl"]
            if side > 0:
                new_sl = entry+trail_r*initial_risk
                if new_sl > pos["sl"]:
                    pos["sl"] = new_sl; pos["trailed"] = True
                    pos["trail_amount"] = new_sl-old_sl
            else:
                new_sl = entry-trail_r*initial_risk
                if new_sl < pos["sl"]:
                    pos["sl"] = new_sl; pos["trailed"] = True
                    pos["trail_amount"] = old_sl-new_sl
        greed_threshold = 2.5-regulator.greed*0.5
        if r_mult >= greed_threshold and momentum_aligned < 0:
            return ("close", "قفل سود (ضد طمع)")
        if r_mult < -0.3 and momentum_aligned < -0.4:
            patience_buffer = -0.3-self.patience*0.3
            if r_mult < patience_buffer: return ("close", "قطع ضرر زودهنگام (ضد ترس)")
        if r_mult <= -0.9: return ("close", "خروج اضطراری")
        return None

# ═══════════════════════ ۱۹) سرزندگی ═══════════════════════
class VitalitySystem:
    def __init__(self):
        self.breath_phase = 0.0; self.vitality = 0.9; self.adrenaline = 0.0
    def step(self, dt, arousal, stress):
        breath_rate = 0.1+arousal*0.15+stress*0.2
        self.breath_phase = (self.breath_phase+dt*breath_rate) % 1.0
        target = clamp(1.0-stress*0.5-arousal*0.2)
        self.vitality = ema(self.vitality, target, 0.05)
        self.adrenaline = clamp(self.adrenaline*0.9+stress*0.3, 0, 1)
        return {"breath": math.sin(self.breath_phase*2*math.pi),
                "vitality": self.vitality, "adrenaline": self.adrenaline}

# ═══════════════════════ ۲۰) موتور معاملاتی ═══════════════════════
class TradingEngine:
    def __init__(self, name, capital, n_slots, fee_rate, db):
        self.name = name; self.db = db
        self.initial_capital = capital; self.n_slots = n_slots; self.fee_rate = fee_rate
        self.slot_margin = capital/n_slots
        self.lock = threading.RLock()
        self._init_fresh(); self._load_from_db()
    def _init_fresh(self):
        self.slots = [{"coin": None, "capital": self.slot_margin, "margin_used": 0.0} for _ in range(self.n_slots)]
        self.coin_to_slot = {}; self.open_positions = {}; self.closed = []
        self.wins = 0; self.losses = 0; self.realized_pnl = 0.0
        self.total_commission = 0.0; self.total_spread = 0.0
        self.daily_trades = 0; self.daily_date = time.strftime("%Y-%m-%d"); self.lesson_stats = {}
    def _load_from_db(self):
        state = self.db.load_engine_state(self.name)
        if state:
            caps = state["slot_capitals"]
            for i in range(min(self.n_slots, len(caps))): self.slots[i]["capital"] = caps[i]
            self.realized_pnl = state["realized_pnl"] or 0.0
            self.wins = state["wins"] or 0; self.losses = state["losses"] or 0
            self.total_commission = state["total_commission"] or 0.0
            self.total_spread = state["total_spread"] or 0.0
        open_pos, closed = self.db.load_positions(self.name)
        for r in closed: r["mode"] = self.name; r["exit"] = r.get("exit_price")
        self.closed = closed[-100:]
        for coin, pos in open_pos.items():
            sid = pos.get("slot_id")
            if sid is not None and 0 <= sid < self.n_slots:
                self.slots[sid]["coin"] = coin
                self.slots[sid]["margin_used"] += pos["margin"]
                self.coin_to_slot[coin] = sid
                self.open_positions[coin] = pos
        self.lesson_stats = self.db.load_lesson_stats(self.name)
    def _persist_state(self):
        caps = [s["capital"] for s in self.slots]
        self.db.save_engine_state(self.name, caps, self.realized_pnl, self.wins,
                                  self.losses, self.total_commission, self.total_spread)
    def record_lesson(self, reasons, pnl):
        for r in reasons:
            if r not in self.lesson_stats: self.lesson_stats[r] = {"wins": 0, "losses": 0, "pnl": 0.0}
            if pnl > 0: self.lesson_stats[r]["wins"] += 1
            else: self.lesson_stats[r]["losses"] += 1
            self.lesson_stats[r]["pnl"] += pnl
        self.db.save_lesson_stats(self.name, self.lesson_stats)
    def lesson_adjustment(self, reasons):
        adj = 0.0
        for r in reasons:
            st = self.lesson_stats.get(r)
            if not st: continue
            total = st["wins"]+st["losses"]
            if total < 3: continue
            adj += (st["wins"]/total-0.5)*0.3
        return clamp(adj, -0.2, 0.2)
    def top_lessons(self, n=5):
        items = []
        for r, st in self.lesson_stats.items():
            total = st["wins"]+st["losses"]
            if total == 0: continue
            items.append((r, st["wins"]/total*100, total, st["pnl"]))
        items.sort(key=lambda x: -x[3])
        return items[:n]
    def assign_coin(self, coin):
        with self.lock:
            if coin in self.coin_to_slot: return self.coin_to_slot[coin]
            for i, s in enumerate(self.slots):
                if s["coin"] is None: s["coin"] = coin; self.coin_to_slot[coin] = i; return i
            return None
    def slot_of(self, coin): return self.coin_to_slot.get(coin)
    def available_margin(self, coin):
        sid = self.coin_to_slot.get(coin)
        if sid is None: return 0.0
        s = self.slots[sid]
        return max(0.0, s["capital"]-s["margin_used"])
    def total_margin_used(self): return sum(s["margin_used"] for s in self.slots)
    def open_position(self, coin, side, price, spread, margin, leverage, tp, sl, conviction, reasons, tick, mode, binary_bits=""):
        with self.lock:
            if margin <= 0 or price <= 0: return None
            avail = self.available_margin(coin); margin = min(margin, avail)
            if margin < 1: return None
            entry = price+(spread/2 if side > 0 else -spread/2)
            notional = margin*leverage; size = notional/entry
            commission = notional*self.fee_rate; spread_cost = spread*size
            sid = self.coin_to_slot.get(coin)
            if sid is None: return None
            self.slots[sid]["margin_used"] += margin
            self.daily_trades += 1
            self.total_commission += commission; self.total_spread += spread_cost
            pos = {"coin": coin, "side": side, "entry": entry, "size": size, "margin": margin,
                   "leverage": leverage, "notional": notional, "tp": tp, "sl": sl,
                   "conviction": conviction, "reasons": reasons, "commission": commission,
                   "spread_cost": spread_cost, "open_time": time.strftime("%H:%M:%S"),
                   "open_ts": int(time.time()*1000), "open_tick": tick, "slot_id": sid, "mode": mode,
                   "peak": entry, "trailed": False, "trail_amount": 0.0, "binary_bits": binary_bits}
            self.open_positions[coin] = pos
            self.db.save_open_position(self.name, pos); self._persist_state()
            return pos
    def live_pnl(self, pos, bid, ask):
        side = pos["side"]; cur = bid if side > 0 else ask
        gross = (cur-pos["entry"])*side*pos["size"]
        exit_comm = cur*pos["size"]*self.fee_rate
        net = gross-pos["commission"]-exit_comm-pos["spread_cost"]
        roi_on_margin = net/max(pos["margin"], 1e-9)*100
        return {"gross": gross, "net": net, "roi": roi_on_margin, "cur": cur,
                "total_fees": pos["commission"]+exit_comm+pos["spread_cost"]}
    def check_exit(self, pos, bid, ask):
        side = pos["side"]
        if side > 0:
            if bid >= pos["tp"]: return "TP", bid
            if bid <= pos["sl"]: return "SL", bid
        else:
            if ask <= pos["tp"]: return "TP", ask
            if ask >= pos["sl"]: return "SL", ask
        return None, None
    def close_position(self, coin, exit_price, reason):
        with self.lock:
            if coin not in self.open_positions: return None
            pos = self.open_positions.pop(coin)
            side = pos["side"]
            gross = (exit_price-pos["entry"])*side*pos["size"]
            exit_comm = exit_price*pos["size"]*self.fee_rate
            net = gross-pos["commission"]-exit_comm-pos["spread_cost"]
            self.realized_pnl += net; self.total_commission += exit_comm
            if net > 0: self.wins += 1
            else: self.losses += 1
            sid = self.coin_to_slot.get(coin)
            if sid is not None:
                s = self.slots[sid]
                s["margin_used"] = max(0.0, s["margin_used"]-pos["margin"])
                s["capital"] += net
                if s["capital"] < 0: s["capital"] = 0.0
            pos.update({"exit": exit_price, "exit_price": exit_price, "exit_reason": reason,
                        "net_pnl": net, "close_time": time.strftime("%H:%M:%S"), "mode": self.name})
            self.closed.append(pos)
            if len(self.closed) > 100: self.closed = self.closed[-100:]
            self.db.close_position(self.name, coin, exit_price, reason, net)
            self.record_lesson(pos.get("reasons", []), net); self._persist_state()
            return net
    def _fetch_klines_since(self, http, coin, start_ts):
        d = http.get("/v5/market/kline", {"category": "linear", "symbol": coin,
                                          "interval": "15", "start": start_ts, "limit": 1000})
        if not d: return None
        lst = d.get("result", {}).get("list", [])
        if not lst: return None
        klines = []
        for x in lst:
            try: klines.append((int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4])))
            except Exception: continue
        klines.sort(key=lambda k: k[0])
        return klines
    def _determine_settlement(self, pos, klines):
        side = pos["side"]; tp = pos["tp"]; sl = pos["sl"]; open_ts = pos.get("open_ts", 0)
        for ts, o, h, l, c in klines:
            if ts < open_ts: continue
            if side > 0: hit_sl = l <= sl; hit_tp = h >= tp
            else: hit_sl = h >= sl; hit_tp = l <= tp
            if hit_sl and hit_tp: return sl, "SL"
            elif hit_sl: return sl, "SL"
            elif hit_tp: return tp, "TP"
        return None
    def settle_on_reconnect(self, http):
        settled = 0
        for coin in list(self.open_positions.keys()):
            pos = self.open_positions[coin]
            klines = self._fetch_klines_since(http, coin, pos.get("open_ts", 0))
            settlement = None
            if klines: settlement = self._determine_settlement(pos, klines)
            if settlement is None: continue
            self.close_position(coin, settlement[0], settlement[1]); settled += 1
        return settled
    def reset(self):
        with self.lock:
            self.db.reset_engine(self.name); self._init_fresh(); self._persist_state()
    def equity(self, unrealized): return sum(s["capital"] for s in self.slots)+unrealized
    def win_rate(self):
        total = self.wins+self.losses
        return (self.wins/total*100) if total > 0 else 0.0
    def profit_factor(self):
        gw = sum(t["net_pnl"] for t in self.closed if t.get("net_pnl", 0) > 0)
        gl = abs(sum(t["net_pnl"] for t in self.closed if t.get("net_pnl", 0) < 0))
        if gl > 0: return gw/gl
        return 99.0 if gw > 0 else 0.0
    def stats(self, unrealized):
        eq = self.equity(unrealized); base = self.slot_margin*self.n_slots
        return {"equity": eq, "capital": base, "realized_pnl": self.realized_pnl,
                "unrealized": unrealized, "pnl_pct": safe_div(eq-base, base)*100,
                "n_open": len(self.open_positions), "n_closed": self.wins+self.losses,
                "wins": self.wins, "losses": self.losses, "win_rate": self.win_rate(),
                "profit_factor": self.profit_factor(), "daily_trades": self.daily_trades,
                "total_commission": self.total_commission, "total_spread": self.total_spread,
                "margin_used": self.total_margin_used(), "slot_margin": self.slot_margin}

# ═══════════════════════ ۲۱) اسکنر چند ارزی ═══════════════════════
class MultiSymbolScanner:
    def __init__(self, http, symbol_limit, deep_limit, interval, kline_limit):
        self.http = http; self.symbol_limit = symbol_limit; self.deep_limit = deep_limit
        self.interval = interval; self.kline_limit = kline_limit
        self.lock = threading.RLock()
        self.tickers = {}; self.top_symbols = []; self.deep = {}; self.deep_last_scan = {}
        self.connected = False; self.last_update = 0; self.scan_cycles = 0
        self.analyzer = AcausalFieldAnalyzer()
    def fetch_tickers(self):
        d = self.http.get("/v5/market/tickers", {"category": "linear"})
        if not d: self.connected = False; return
        lst = d.get("result", {}).get("list", [])
        rows = []
        for t in lst:
            sym = t.get("symbol", "")
            if not sym.endswith("USDT"): continue
            try:
                last = float(t.get("lastPrice") or 0); bid = float(t.get("bid1Price") or 0)
                ask = float(t.get("ask1Price") or 0); turnover = float(t.get("turnover24h") or 0)
                chg = float(t.get("price24hPcnt") or 0)
            except Exception: continue
            if last <= 0 or bid <= 0 or ask <= 0 or turnover <= 0: continue
            spread = max(ask-bid, 0.0)
            rows.append({"symbol": sym, "price": last, "bid": bid, "ask": ask, "spread": spread,
                         "spread_pct": spread/last, "change24h": chg, "turnover": turnover})
        rows.sort(key=lambda r: r["turnover"], reverse=True)
        rows = rows[:self.symbol_limit]
        with self.lock:
            self.tickers = {r["symbol"]: r for r in rows}
            self.top_symbols = [r["symbol"] for r in rows]
            self.connected = True; self.last_update = time.time()
    def fetch_klines(self, symbol):
        d = self.http.get("/v5/market/kline", {"category": "linear", "symbol": symbol,
                                               "interval": self.interval, "limit": self.kline_limit})
        if not d: return None
        lst = d.get("result", {}).get("list", [])
        if not lst: return None
        try:
            arr = np.array(lst, dtype=object)
            o = np.array([float(x[1]) for x in arr])[::-1]
            h = np.array([float(x[2]) for x in arr])[::-1]
            l = np.array([float(x[3]) for x in arr])[::-1]
            c = np.array([float(x[4]) for x in arr])[::-1]
            v = np.array([float(x[5]) for x in arr])[::-1]
        except Exception: return None
        return {"o": o, "h": h, "l": l, "c": c, "v": v}
    def opportunity_score(self, t):
        return abs(t["change24h"])*2.0+math.log10(max(t["turnover"], 1))*0.1
    def scan_cycle(self):
        self.fetch_tickers()
        if not self.connected: return
        with self.lock:
            tickers = dict(self.tickers); top = list(self.top_symbols)
        scored = sorted(top, key=lambda s: self.opportunity_score(tickers[s]), reverse=True)
        now = time.time()
        candidates = []
        for s in scored:
            if now-self.deep_last_scan.get(s, 0) >= config.SCAN_RESCAN_SEC: candidates.append(s)
            if len(candidates) >= self.deep_limit: break
        for s in candidates:
            kl = self.fetch_klines(s)
            if kl is None: continue
            analysis = self.analyzer.analyze(kl["o"], kl["h"], kl["l"], kl["c"], key=s)
            with self.lock:
                self.deep[s] = {"klines": kl, "analysis": analysis, "ts": now}
                self.deep_last_scan[s] = now
        self.scan_cycles += 1
    def background(self, period):
        print(f"🔍 اسکنر: {self.symbol_limit} ارز | عمیق {self.deep_limit} | هر {period}s")
        while True:
            try: self.scan_cycle()
            except Exception as e: self.http.last_error = str(e)
            time.sleep(period)
    def snapshot(self):
        with self.lock:
            return {"connected": self.connected, "n_symbols": len(self.top_symbols),
                    "tickers": dict(self.tickers), "deep": dict(self.deep),
                    "scan_cycles": self.scan_cycles}

# ═══════════════════════ ۲۲) ژنتیک تکاملیافته ═══════════════════════
BASES = "ACGT"; PROMOTER_MOTIF = "TATA"
GENE_CATALOG = [
    ("GEN-BDNF", "پلاستیسیته سیناپسی", "plasticity", 0.65),
    ("GEN-MCPH1", "گسترش قشر مغز", "cortex_growth", 0.60),
    ("GEN-TH", "سنتز دوپامین", "dopamine_synthesis", 0.60),
    ("GEN-DRD1", "گیرنده دوپامین D1", "dopamine_receptor_d1", 0.55),
    ("GEN-TPH2", "سنتز سروتونین", "serotonin_synthesis", 0.60),
    ("GEN-GAD1", "سنتز گابا", "gaba_synthesis", 0.60),
    ("GEN-VGLUT", "سنتز گلوتامات", "glutamate_synthesis", 0.60),
    ("GEN-CHAT", "سنتز استیل‌کولین", "ach_synthesis", 0.60),
    ("GEN-IPS", "درک عدد", "number_sense", 0.60),
    ("GEN-CORT", "پاسخ استرس", "cortisol_response", 0.55),
    ("GEN-MITO", "بازده میتوکندری", "mito_efficiency", 0.60),
    ("GEN-HEART", "ساختار قلب", "heart_structure", 0.60),
    ("GEN-IMMUNE", "سیستم ایمنی", "immune", 0.60),
    ("GEN-OPRM1", "گیرنده اندورفین", "endorphin_receptor", 0.55),
    ("GEN-LUNG", "ظرفیت ریه", "lung", 0.60),
    ("GEN-HBB", "هموگلوبین", "hemoglobin", 0.65),
    ("GEN-TRD", "شجاعت معاملاتی", "trading_courage", 0.60),
    ("GEN-INT", "شهود اسنایپر", "intuition", 0.65),
    ("GEN-WAKE", "بیداری پایدار", "wakefulness", 0.70),
    ("GEN-GEO", "هوش هندسی", "geometry", 0.70),
    ("GEN-LRN", "ظرفیت یادگیری", "learning", 0.70),
    ("GEN-DISC", "انضباط آهنین", "discipline", 0.88),
    ("GEN-RISKMG", "مدیریت ریسک برتر", "risk_management", 0.88),
    ("GEN-EMOCTL", "کنترل احساسات", "emotional_control", 0.88),
    ("GEN-PATIENCE", "صبر شکارچی", "patience", 0.85),
    ("GEN-PRECISION", "دقت اسنایپر", "precision", 0.88),
    ("GEN-NUMIQ", "هوش عددی برتر", "numerical_iq", 0.92),
    ("GEN-VISIQ", "هوش بصری برتر", "visual_iq", 0.92),
    ("GEN-ADAPT", "سازگاری سریع", "adaptability", 0.85),
    ("GEN-CALM", "آرامش تحت فشار", "calm", 0.88),
    ("GEN-FORESIGHT", "آینده‌نگری", "foresight", 0.85),
    ("GEN-PRES", "ادراک اکنون ابدی", "presence", 0.90),
    ("GEN-SYN", "یکپارچگی حسی", "synesthesia", 0.92),
    ("GEN-XENO", "حسگرهای فرازمینی", "xeno_sense", 0.95),
    ("GEN-SPACETIME", "ادراک فضازمانی", "spacetime", 0.95),
    ("GEN-INTERO", "آگاهی بدن", "interoception", 0.92),
    ("GEN-ATTN", "حواس جمع", "attention", 0.92),
    ("GEN-CARDNEURAL", "شبکه عصبی قلب", "cardiac_neural", 0.92),
    # 🧬 ژن‌های انقلابی نسخه تکینگی
    ("GEN-INTCORE", "هسته شهود انقلابی", "intuition_core", 0.97),
    ("GEN-BINARY", "جریان تفکر باینری", "binary_cognition", 0.96),
    ("GEN-ECON", "هوش اقتصادی بازار", "economic_sense", 0.94),
    ("GEN-ACAUSAL", "ادراک میدان غیرعلی", "acausal_field", 0.96),
    ("GEN-GPUSYNC", "همگام‌سازی GPU/CPU", "gpu_sync", 0.93),
]
KEY_TO_SYMBOL = {k: s for s, _, k, _ in GENE_CATALOG}
TRADER_GENE_KEYS = ["discipline", "risk_management", "emotional_control", "patience", "precision",
                    "numerical_iq", "visual_iq", "adaptability", "calm", "foresight", "presence",
                    "synesthesia", "xeno_sense", "spacetime", "interoception", "attention", "cardiac_neural",
                    "intuition_core", "binary_cognition", "economic_sense", "acausal_field", "gpu_sync"]

@dataclass
class Gene:
    symbol: str; fa_name: str; key: str; base_strength: float
    chrom: int = 0; start: int = 0; length: int = 180; seq: str = ""; promoter_score: float = 0.5

@dataclass
class Phenotype:
    cortical_expansion: float = 1.0; plasticity: float = 1.0
    dopamine_tone: float = 0.5; serotonin_tone: float = 0.5
    gaba_tone: float = 0.5; glutamate_tone: float = 0.5; ach_tone: float = 0.5
    number_sense: float = 0.7; stress_reactivity: float = 0.5
    metabolism: float = 1.0; heart_base: float = 70.0; immunity: float = 0.7
    trading_courage: float = 0.5; intuition: float = 0.5; wakefulness: float = 0.7
    geometry: float = 0.7; learning: float = 0.7
    endorphin_sens: float = 0.5; lung_capacity: float = 1.0; o2_affinity: float = 1.0
    discipline: float = 0.7; risk_management: float = 0.7; emotional_control: float = 0.7
    patience: float = 0.7; precision: float = 0.7; numerical_iq: float = 0.7
    visual_iq: float = 0.7; adaptability: float = 0.7; calm: float = 0.7; foresight: float = 0.7
    presence: float = 0.7; synesthesia: float = 0.7; xeno_sense: float = 0.7; spacetime: float = 0.7
    interoception: float = 0.7; attention: float = 0.7; cardiac_neural: float = 0.7
    intuition_core: float = 0.7; binary_cognition: float = 0.7; economic_sense: float = 0.7
    acausal_field: float = 0.7; gpu_sync: float = 0.7
    superhuman_factor: float = 1.0

class Epigenome:
    def __init__(self, symbols): self.methyl = {s: 0.15 for s in symbols}
    def get(self, s): return self.methyl.get(s, 0.15)
    def adapt(self, symbol, delta):
        key = KEY_TO_SYMBOL.get(symbol, symbol)
        if key in self.methyl:
            self.methyl[key] = float(np.clip(self.methyl[key]+delta, 0.0, 0.9))

class Genome:
    N_CHROMOSOMES = 8; CHROM_LEN = 2000
    def __init__(self, seed=None):
        self.seed = seed if seed is not None else int(np.random.randint(1, 2**31-1))
        self.rng = np.random.default_rng(self.seed)
        self.chromosomes = [self._random_seq(self.CHROM_LEN) for _ in range(self.N_CHROMOSOMES)]
        self.genes = []; self._place_genes()
        self.epigenome = Epigenome([g.symbol for g in self.genes])
        self._cache_promoters()
    def _random_seq(self, n): return "".join(BASES[i] for i in self.rng.integers(0, 4, n))
    def _place_genes(self):
        for symbol, fa, key, strength in GENE_CATALOG:
            h = zlib.crc32(symbol.encode()); chrom = h % self.N_CHROMOSOMES
            length = 120+(h % 220); start = (h >> 3) % (self.CHROM_LEN-length-250)
            self.genes.append(Gene(symbol, fa, key, strength, chrom, start, length))
    def _cache_promoters(self):
        for g in self.genes:
            window = self.chromosomes[g.chrom][max(0, g.start-220):g.start]
            gc = (window.count("G")+window.count("C"))/max(1, len(window))
            g.promoter_score = float(np.clip(0.30+0.12*window.count(PROMOTER_MOTIF)+0.25*gc, 0.1, 1.0))
            g.seq = self.chromosomes[g.chrom][g.start:g.start+g.length]
    def expression(self, key, tf=1.0):
        symbol = KEY_TO_SYMBOL.get(key, key)
        gene = next((g for g in self.genes if g.symbol == symbol), None)
        if gene is None: return 0.5
        level = (gene.promoter_score*gene.base_strength*(0.55+0.85*tf)
                 *(1.0-0.85*self.epigenome.get(symbol)))
        return float(np.clip(level*1.9, 0.0, 1.0))
    def E(self, key, tf=1.0): return self.expression(key, tf)
    def build_phenotype(self):
        E = self.E; p = Phenotype()
        p.cortical_expansion = 0.70+0.60*E("cortex_growth")
        p.plasticity = 0.40+0.90*E("plasticity")
        p.dopamine_tone = 0.25+0.55*E("dopamine_synthesis")*(0.5+0.5*E("dopamine_receptor_d1"))
        p.serotonin_tone = 0.25+0.55*E("serotonin_synthesis")
        p.gaba_tone = 0.30+0.50*E("gaba_synthesis")
        p.glutamate_tone = 0.30+0.55*E("glutamate_synthesis")
        p.ach_tone = 0.30+0.55*E("ach_synthesis")
        p.number_sense = 0.40+0.60*E("number_sense")
        p.stress_reactivity = 0.30+0.70*E("cortisol_response")
        p.metabolism = 0.70+0.50*E("mito_efficiency")
        p.heart_base = 58.0+26.0*E("heart_structure")
        p.immunity = 0.40+0.60*E("immune")
        p.trading_courage = 0.30+0.70*E("trading_courage")
        p.intuition = 0.30+0.70*E("intuition")
        p.wakefulness = 0.50+0.50*E("wakefulness")
        p.geometry = 0.30+0.70*E("geometry")
        p.learning = 0.30+0.70*E("learning")
        p.endorphin_sens = 0.30+0.60*E("endorphin_receptor")
        p.lung_capacity = 0.70+0.50*E("lung")
        p.o2_affinity = 0.70+0.40*E("hemoglobin")
        p.discipline = 0.20+0.80*E("discipline")
        p.risk_management = 0.20+0.80*E("risk_management")
        p.emotional_control = 0.20+0.80*E("emotional_control")
        p.patience = 0.20+0.80*E("patience")
        p.precision = 0.20+0.80*E("precision")
        p.numerical_iq = 0.20+0.80*E("numerical_iq")
        p.visual_iq = 0.20+0.80*E("visual_iq")
        p.adaptability = 0.20+0.80*E("adaptability")
        p.calm = 0.20+0.80*E("calm")
        p.foresight = 0.20+0.80*E("foresight")
        p.presence = 0.20+0.80*E("presence")
        p.synesthesia = 0.20+0.80*E("synesthesia")
        p.xeno_sense = 0.20+0.80*E("xeno_sense")
        p.spacetime = 0.20+0.80*E("spacetime")
        p.interoception = 0.20+0.80*E("interoception")
        p.attention = 0.20+0.80*E("attention")
        p.cardiac_neural = 0.20+0.80*E("cardiac_neural")
        p.intuition_core = 0.20+0.80*E("intuition_core")
        p.binary_cognition = 0.20+0.80*E("binary_cognition")
        p.economic_sense = 0.20+0.80*E("economic_sense")
        p.acausal_field = 0.20+0.80*E("acausal_field")
        p.gpu_sync = 0.20+0.80*E("gpu_sync")
        apex = [p.discipline, p.risk_management, p.emotional_control, p.numerical_iq,
                p.visual_iq, p.precision, p.calm, p.foresight, p.presence, p.synesthesia,
                p.xeno_sense, p.spacetime, p.interoception, p.attention, p.cardiac_neural,
                p.intuition_core, p.binary_cognition, p.economic_sense, p.acausal_field]
        p.superhuman_factor = clamp(1.4+(sum(apex)/len(apex))*1.8, 1.0, 3.6)
        return p
    def describe(self):
        return [(g.fa_name, self.expression(g.key), self.epigenome.get(g.symbol)) for g in self.genes]
    def signature(self):
        return f"{zlib.crc32(''.join(self.chromosomes).encode()):08x}".upper()

def prime_apex_trader(genome):
    for key in TRADER_GENE_KEYS:
        symbol = KEY_TO_SYMBOL.get(key)
        if symbol and symbol in genome.epigenome.methyl:
            genome.epigenome.methyl[symbol] = 0.01

# ═══════════════════════ ۲۳) کوانتوم ═══════════════════════
@dataclass
class QuantumEvent:
    tick: int; register: int; bits: str; value: float

class QuantumSubstrate:
    def __init__(self, n_registers, n_qubits, rng):
        self.registers = []
        for i in range(n_registers):
            dim = 1 << n_qubits
            v = rng.normal(size=dim)+1j*rng.normal(size=dim)
            H = rng.normal(0, 1, (dim, dim))+1j*rng.normal(0, 1, (dim, dim))
            self.registers.append({"psi": v/np.linalg.norm(v), "H": (H+H.conj().T)*0.175,
                                   "dim": dim, "n": n_qubits, "coherence": 1.0})
        self.rng = rng; self.avg_coherence = 1.0; self.total_collapses = 0
    def step(self, dt, base_rate, act_rate, activity):
        events = []; cohs = []
        for i, reg in enumerate(self.registers):
            reg["psi"] += (-1j*dt)*(reg["H"] @ reg["psi"])
            nrm = np.linalg.norm(reg["psi"])
            if nrm > 1e-12: reg["psi"] /= nrm
            p = np.abs(reg["psi"])**2; s = p.sum()
            p = p/s if s > 0 else np.full(reg["dim"], 1.0/reg["dim"])
            act = activity[i % len(activity)] if activity else 0.0
            if self.rng.random() < base_rate+act_rate*float(act):
                idx = int(self.rng.choice(reg["dim"], p=p))
                psi_new = np.zeros(reg["dim"], dtype=complex); psi_new[idx] = 1.0
                reg["psi"] = psi_new
                events.append(QuantumEvent(0, i, format(idx, f"0{reg['n']}b"), idx/max(1, reg["dim"]-1)))
                self.total_collapses += 1
            pr = 1.0/max(1e-12, float(np.sum(p*p)))
            reg["coherence"] = float(pr/reg["dim"]); cohs.append(reg["coherence"])
        self.avg_coherence = float(np.mean(cohs)); return events

# ═══════════════════════ ۲۴) نوروشیمی ═══════════════════════
NEUROTRANSMITTERS = [("glutamate", "گلوتامات"), ("gaba", "گابا"), ("dopamine", "دوپامین"),
                     ("serotonin", "سروتونین"), ("norepinephrine", "نوراپی‌نفرین"),
                     ("acetylcholine", "استیل‌کولین"), ("endorphin", "اندورفین")]
class Neurochemistry:
    def __init__(self, phenotype):
        self.p = phenotype
        self.levels = {"glutamate": 0.30+0.30*phenotype.glutamate_tone,
                       "gaba": 0.30+0.30*phenotype.gaba_tone,
                       "dopamine": 0.20+0.35*phenotype.dopamine_tone,
                       "serotonin": 0.20+0.35*phenotype.serotonin_tone,
                       "norepinephrine": 0.30, "acetylcholine": 0.20+0.30*phenotype.ach_tone,
                       "endorphin": 0.15}
    def step(self, rates, hormones, pain=0.0, reward=0.0, sickness=0.0, info_feed=0.0):
        bs = rates.get("BRAINSTEM", 0.0); cx = rates.get("CORTEX", 0.0); am = rates.get("AMYGDALA", 0.0)
        L = self.levels
        L["norepinephrine"] += 0.045*(bs*3.0+am*1.5)+0.02*hormones.get("adrenaline", 0)
        L["dopamine"] += 0.040*(bs*2.0+reward*2.5)-0.03*sickness+0.15*info_feed
        L["serotonin"] += 0.035*(bs*2.2)-0.02*sickness+0.10*info_feed
        L["acetylcholine"] += 0.040*(cx*2.0+0.3)+0.20*info_feed
        L["glutamate"] += 0.050*(cx*2.5+0.35)
        L["gaba"] += 0.045*(cx*2.0+0.30)
        L["endorphin"] += 0.060*pain
        for k in L: L[k] = float(np.clip(L[k]*0.965, 0.0, 1.0))
        return L
    @property
    def mood_index(self):
        L = self.levels
        return float(np.clip(0.5*L["serotonin"]+0.4*L["dopamine"]-0.25*L["norepinephrine"]+0.2, 0, 1))

# ═══════════════════════ ۲۵) مغز گسترده + GPU + نواحی جدید ═══════════════════════
MAX_DELAY = 4
REG_ORDER = ["BRAINSTEM", "THALAMUS", "AMYGDALA", "HIPPOCAMPUS",
             "VISUAL_CORTEX", "NUMERICAL_CORTEX", "SPACETIME_CORTEX",
             "INTUITION_CORTEX", "ECONOMIC_CORTEX", "BINARY_GATE",
             "BASAL_GANGLIA", "CORTEX"]
REGION_FA = {"BRAINSTEM": "ساقه‌ی مغز", "THALAMUS": "تالاموس", "AMYGDALA": "آمیگدال",
             "HIPPOCAMPUS": "هیپوکامپ", "VISUAL_CORTEX": "قشر بینایی", "NUMERICAL_CORTEX": "قشر عددی",
             "SPACETIME_CORTEX": "قشر فضازمانی", "INTUITION_CORTEX": "قشر شهودی 🔮",
             "ECONOMIC_CORTEX": "قشر اقتصادی 💠", "BINARY_GATE": "دروازه باینری ⚡",
             "BASAL_GANGLIA": "عقده‌های قاعده‌ای", "CORTEX": "قشر مغز"}
PATHWAYS = [
    ("BRAINSTEM", "THALAMUS", 0.10, 2.2, False), ("THALAMUS", "CORTEX", 0.06, 1.6, True),
    ("CORTEX", "THALAMUS", 0.05, 1.4, True), ("CORTEX", "CORTEX", 0.02, 1.2, True),
    ("HIPPOCAMPUS", "CORTEX", 0.05, 1.5, True), ("CORTEX", "HIPPOCAMPUS", 0.04, 1.3, True),
    ("AMYGDALA", "CORTEX", 0.05, 1.4, False), ("CORTEX", "AMYGDALA", 0.04, 1.2, True),
    ("AMYGDALA", "BRAINSTEM", 0.08, 1.8, False), ("CORTEX", "BASAL_GANGLIA", 0.05, 1.4, True),
    ("BASAL_GANGLIA", "THALAMUS", 0.07, 1.5, False), ("THALAMUS", "AMYGDALA", 0.05, 1.3, False),
    ("BRAINSTEM", "BRAINSTEM", 0.05, 1.0, False),
    ("THALAMUS", "VISUAL_CORTEX", 0.08, 1.6, True), ("VISUAL_CORTEX", "CORTEX", 0.06, 1.5, True),
    ("VISUAL_CORTEX", "NUMERICAL_CORTEX", 0.05, 1.4, True),
    ("THALAMUS", "NUMERICAL_CORTEX", 0.06, 1.4, False),
    ("NUMERICAL_CORTEX", "CORTEX", 0.06, 1.5, True),
    ("NUMERICAL_CORTEX", "BASAL_GANGLIA", 0.07, 1.6, True),
    ("CORTEX", "NUMERICAL_CORTEX", 0.05, 1.3, True),
    ("THALAMUS", "SPACETIME_CORTEX", 0.07, 1.6, True),
    ("SPACETIME_CORTEX", "CORTEX", 0.07, 1.7, True),
    ("SPACETIME_CORTEX", "BASAL_GANGLIA", 0.06, 1.6, True),
    ("NUMERICAL_CORTEX", "SPACETIME_CORTEX", 0.05, 1.5, True),
    ("VISUAL_CORTEX", "SPACETIME_CORTEX", 0.05, 1.5, True),
    # 🔮 مسیرهای شهودی/اقتصادی/باینری
    ("THALAMUS", "INTUITION_CORTEX", 0.09, 1.8, True),
    ("SPACETIME_CORTEX", "INTUITION_CORTEX", 0.08, 1.7, True),
    ("NUMERICAL_CORTEX", "INTUITION_CORTEX", 0.08, 1.6, True),
    ("AMYGDALA", "INTUITION_CORTEX", 0.06, 1.4, False),
    ("INTUITION_CORTEX", "BINARY_GATE", 0.10, 2.0, True),
    ("INTUITION_CORTEX", "CORTEX", 0.07, 1.7, True),
    ("ECONOMIC_CORTEX", "INTUITION_CORTEX", 0.08, 1.6, True),
    ("THALAMUS", "ECONOMIC_CORTEX", 0.07, 1.5, True),
    ("NUMERICAL_CORTEX", "ECONOMIC_CORTEX", 0.06, 1.5, True),
    ("BINARY_GATE", "BASAL_GANGLIA", 0.09, 1.9, True),
    ("BINARY_GATE", "CORTEX", 0.07, 1.6, True),
    ("CORTEX", "INTUITION_CORTEX", 0.05, 1.3, True),
]

class Region:
    def __init__(self, name, n, rng):
        self.name, self.fa = name, REGION_FA.get(name, name)
        self.n, self.rng = max(12, int(n)), rng
        self.xpb = GPU.xp
        self.a = np.full(self.n, 0.02); self.b = np.full(self.n, 0.20)
        self.c = np.full(self.n, -65.0); self.d = np.full(self.n, 8.0)
        n_inh = max(2, int(self.n*0.20))
        self.a[:n_inh] = 0.10; self.b[:n_inh] = 0.20; self.c[:n_inh] = -65.0; self.d[:n_inh] = 2.0
        self.inh_mask = np.zeros(self.n, dtype=bool); self.inh_mask[:n_inh] = True
        self.v = self.xpb.asarray(np.full(self.n, -65.0))
        self.u = self.xpb.asarray(self.b*np.full(self.n, -65.0))
        self.I = self.xpb.zeros(self.n)
        self.spiked_now = self.xpb.zeros(self.n, dtype=bool)
        self.spike_buffer = [self.xpb.zeros(self.n, dtype=bool) for _ in range(MAX_DELAY)]
        self.buf_idx = 0; self.activity = 0.0
        self._a = self.xpb.asarray(self.a); self._b = self.xpb.asarray(self.b)
        self._c = self.xpb.asarray(self.c); self._d = self.xpb.asarray(self.d)
    def reset_current(self, noise=0.35):
        self.I = self.xpb.asarray(self.rng.normal(1.6, noise, self.n))
    def add_current(self, idx_or_all, amount):
        if idx_or_all is None: self.I += amount
        else:
            idx = self.xpb.asarray(np.asarray(idx_or_all))
            self.I[idx] += amount
    def step(self, substeps=2, dt_ms=1.0):
        spikes = self.xpb.zeros(self.n, dtype=bool)
        I_eff = self.xpb.clip(self.I, -40.0, 50.0)
        for _ in range(substeps):
            self.v = self.xpb.clip(self.v, -90.0, 29.0)
            dv = 0.04*self.v*self.v+5.0*self.v+140.0-self.u+I_eff
            self.v = self.v+dv*dt_ms
            self.u = self.u+self._a*(self._b*self.v-self.u)*dt_ms
            hit = self.v >= 30.0
            if bool(hit.any()):
                self.v[hit] = self._c[hit]; self.u[hit] += self._d[hit]; spikes |= hit
            bad = ~self.xpb.isfinite(self.v)
            if bool(bad.any()):
                self.v[bad] = -65.0; self.u[bad] = -13.0
        self.spiked_now = spikes
        self.spike_buffer[self.buf_idx] = spikes
        self.buf_idx = (self.buf_idx+1) % MAX_DELAY
        self.activity = 0.85*self.activity+0.15*min(1.0, float(spikes.mean())*6.0)
        return spikes
    def delayed(self, delay): return self.spike_buffer[(self.buf_idx-delay) % MAX_DELAY]

class Brain:
    def __init__(self, phenotype, rng, scale=None):
        self.p, self.rng = phenotype, rng
        self.xpb = GPU.xp
        scale = config.NEURON_SCALE if scale is None else scale
        ns = phenotype.number_sense; geo = phenotype.geometry
        shf = phenotype.superhuman_factor
        counts = {"BRAINSTEM": 100*scale, "THALAMUS": 220*scale, "AMYGDALA": 140*scale,
                  "HIPPOCAMPUS": 240*scale,
                  "VISUAL_CORTEX": (80+260*phenotype.visual_iq*shf)*scale,
                  "NUMERICAL_CORTEX": (70+300*max(ns, geo)*shf)*scale,
                  "SPACETIME_CORTEX": (80+340*phenotype.spacetime*shf)*scale,
                  "INTUITION_CORTEX": (120+420*phenotype.intuition_core*shf)*scale,
                  "ECONOMIC_CORTEX": (80+300*phenotype.economic_sense*shf)*scale,
                  "BINARY_GATE": (60+240*phenotype.binary_cognition*shf)*scale,
                  "BASAL_GANGLIA": 160*scale,
                  "CORTEX": 520*phenotype.cortical_expansion*scale}
        counts = {k: int(v) for k, v in counts.items()}
        total = sum(counts.values())
        if total > config.MAX_NEURONS:
            f = config.MAX_NEURONS/total
            counts = {k: max(20, int(v*f)) for k, v in counts.items()}
        self.regions = {k: Region(k, v, rng) for k, v in counts.items()}
        self.syn = {k: [] for k in self.regions}
        self.n_synapses = 0
        self._build_connectome()
        self.eeg = 0.0
        self._pool = (ThreadPoolExecutor(max_workers=config.N_WORKERS)
                      if config.PARALLEL_BRAIN else None)
        print(f"🧠 مغز: {sum(counts.values())} نورون | موازی: {config.PARALLEL_BRAIN} | {GPU.label}")
    def _build_connectome(self):
        for src, dst, p, strength, plast in PATHWAYS:
            if src not in self.regions or dst not in self.regions: continue
            Rs, Rt = self.regions[src], self.regions[dst]
            k_per_post = max(1, int(p*Rs.n)); total = Rt.n*k_per_post
            pre = self.rng.integers(0, Rs.n, total)
            post = np.repeat(np.arange(Rt.n), k_per_post)
            signs = np.where(Rs.inh_mask[pre], -1.0, 1.0)
            w = self.rng.normal(strength, strength*0.25, total)*signs
            delay = self.rng.integers(1, MAX_DELAY, total)
            for d in range(1, MAX_DELAY):
                m = delay == d
                if not m.any(): continue
                self.syn[dst].append({"src": src,
                                      "pre": self.xpb.asarray(pre[m]),
                                      "post": self.xpb.asarray(post[m]),
                                      "w": self.xpb.asarray(w[m]),
                                      "w_np_sign": float(np.sign(w[m][0])) if len(w[m]) else 1.0,
                                      "delay": d, "plastic": plast})
                self.n_synapses += int(m.sum())
    def _gather_target(self, dst):
        Rt = self.regions[dst]; I = Rt.I; n = Rt.n
        for b in self.syn[dst]:
            Rs = self.regions[b["src"]]
            sp = Rs.delayed(b["delay"])[b["pre"]]
            if not bool(sp.any()): continue
            idx = b["post"][sp]
            gain = self._exc_gain if b["w_np_sign"] >= 0 else self._inh_gain
            I += self.xpb.bincount(idx, weights=b["w"][sp]*gain, minlength=n)
    def step(self, sensory, neurochem, quantum_events, fatigue, plasticity_factor=1.0,
             substeps=2, numeric_input=None, cardiac_afferent=0.0, metabolic_supply=1.0,
             market_signal=0.0, sniper_focus=0.0, num_depth=0.0, vis_strength=0.0, presence=0.0,
             sixth_sense=0.0, spacetime_richness=0.0, body_awareness=0.0, attention=0.0,
             intuition_level=0.0, econ_heat=0.0, binary_pulse=0.0):
        regs = self.regions; L = neurochem
        ms = clamp(metabolic_supply, 0.25, 1.15)
        self._exc_gain = (0.7+0.8*L["glutamate"])*ms
        self._inh_gain = 0.7+0.8*L["gaba"]
        arousal = 0.6+L["norepinephrine"]
        for r in regs.values(): r.reset_current(noise=0.35*ms)
        regs["BRAINSTEM"].add_current(None, 5.0+5.0*arousal+3.0*fatigue+8.0*sensory.get("pain", 0)
                                      +2.0*body_awareness)
        th_gain = 1.0+1.4*L["acetylcholine"]
        regs["THALAMUS"].add_current(None, th_gain*(3.0*sensory.get("light", 0)+3.0*sensory.get("sound", 0)))
        regs["AMYGDALA"].add_current(None, 6.0*sensory.get("pain", 0)+3.5*sensory.get("danger", 0))
        regs["HIPPOCAMPUS"].add_current(None, 6.0*L["acetylcholine"])
        regs["BASAL_GANGLIA"].add_current(None, 7.0*L["dopamine"]+3.0*binary_pulse)
        regs["CORTEX"].add_current(None, 3.6*L["acetylcholine"]+2.5*presence+2.0*sixth_sense
                                   +1.5*spacetime_richness+2.0*attention+1.5*body_awareness)
        regs["NUMERICAL_CORTEX"].add_current(None, 3.0*abs(market_signal)+4.0*sniper_focus
                                             +3.0*num_depth+2.5*sixth_sense+2.0*attention)
        regs["VISUAL_CORTEX"].add_current(None, 2.0*abs(market_signal)+3.0*sniper_focus
                                          +3.0*vis_strength+2.0*sixth_sense)
        regs["SPACETIME_CORTEX"].add_current(None, 4.0*spacetime_richness+3.0*sixth_sense
                                             +2.0*abs(market_signal))
        regs["INTUITION_CORTEX"].add_current(None, 6.0*intuition_level+4.0*sixth_sense
                                             +3.0*presence+2.5*spacetime_richness+2.0*cardiac_afferent)
        regs["ECONOMIC_CORTEX"].add_current(None, 5.0*econ_heat+3.0*abs(market_signal)+2.0*num_depth)
        regs["BINARY_GATE"].add_current(None, 8.0*binary_pulse+3.0*intuition_level)
        if numeric_input:
            regs["NUMERICAL_CORTEX"].add_current(None, 2.2*numeric_input.get("conviction", 0))
        if cardiac_afferent > 0.001:
            regs["BRAINSTEM"].add_current(None, 3.5*cardiac_afferent)
            regs["THALAMUS"].add_current(None, 2.0*cardiac_afferent)
            regs["AMYGDALA"].add_current(None, 2.2*cardiac_afferent)
            regs["HIPPOCAMPUS"].add_current(None, 1.8*cardiac_afferent)
            regs["CORTEX"].add_current(None, 1.5*cardiac_afferent)
            regs["INTUITION_CORTEX"].add_current(None, 2.4*cardiac_afferent)
        for ev in quantum_events:
            target = regs[REG_ORDER[ev.register % len(REG_ORDER)]]
            idx = self.rng.integers(0, target.n, 6)
            target.add_current(idx, 6.0*(0.5+ev.value))
        if self._pool is not None:
            list(self._pool.map(self._gather_target, list(self.syn.keys())))
        else:
            for dst in self.syn: self._gather_target(dst)
        for name in REG_ORDER: regs[name].step(substeps=substeps)
        lr = 0.010*self.p.plasticity*plasticity_factor*(0.4+L["dopamine"])
        for dst in ("CORTEX", "HIPPOCAMPUS", "NUMERICAL_CORTEX", "VISUAL_CORTEX",
                    "SPACETIME_CORTEX", "INTUITION_CORTEX", "ECONOMIC_CORTEX"):
            Rt = regs[dst]
            for b in self.syn[dst]:
                if not b["plastic"] or len(b["w"]) < 8: continue
                Rs = regs[b["src"]]
                k = min(96, len(b["w"]))
                idx_np = self.rng.integers(0, len(b["w"]), k)
                pre_np = GPU.asnumpy(b["pre"][idx_np]) if GPU.gpu else np.asarray(b["pre"][idx_np])
                post_np = GPU.asnumpy(b["post"][idx_np]) if GPU.gpu else np.asarray(b["post"][idx_np])
                w_np = GPU.asnumpy(b["w"]) if GPU.gpu else np.asarray(b["w"])
                mask = Rs.spiked_now[self.xpb.asarray(pre_np)] & Rt.spiked_now[self.xpb.asarray(post_np)]
                if bool(mask.any()):
                    sel = self.xpb.asarray(idx_np)[mask]
                    b["w"][sel] += lr*self.xpb.sign(b["w"][sel])
                    self.xpb.clip(b["w"], -4.0, 4.0, out=b["w"])
                b["w"] *= 0.99985
        acts = {k: float(r.activity) for k, r in regs.items()}
        self.eeg = float(self.xpb.mean(regs["CORTEX"].v))
        symp = clamp(0.9*acts["BRAINSTEM"]+1.2*acts["AMYGDALA"], 0, 1)
        parasymp = clamp(0.8-symp+0.3*(1-fatigue), 0, 1)
        motor = clamp(0.6*acts["BASAL_GANGLIA"]+0.4*acts["CORTEX"], 0, 1)
        return {"activities": acts, "eeg": self.eeg,
                "autonomic": {"sympathetic": symp, "parasympathetic": parasymp, "motor": motor}}

# ═══════════════════════ ۲۶) قلب با سیستم عصبی مستقل ═══════════════════════
GOLDEN = (1+5**0.5)/2
class CardiacNervousSystem:
    def __init__(self, rng, n_neurons):
        self.rng = rng
        self.n = max(20, int(n_neurons))
        self.a = np.full(self.n, 0.02); self.b = np.full(self.n, 0.20)
        self.c = np.full(self.n, -65.0); self.d = np.full(self.n, 8.0)
        n_inh = max(2, int(self.n*0.25))
        self.a[:n_inh] = 0.10; self.b[:n_inh] = 0.25; self.d[:n_inh] = 2.0
        self.v = np.full(self.n, -65.0); self.u = self.b*self.v.copy()
        self.I = np.zeros(self.n)
        self.activity = 0.0
        self.coherence = 0.5
    def step(self, sympathetic, parasympathetic, market_excitement, o2, substeps=2, dt_ms=1.0):
        self.I = self.rng.normal(1.5, 0.4, self.n)
        self.I += 2.5*sympathetic-1.5*parasympathetic+1.5*market_excitement
        if o2 < 85: self.I += 1.5
        spikes = np.zeros(self.n, dtype=bool)
        for _ in range(substeps):
            self.v = np.clip(self.v, -90.0, 29.0)
            dv = 0.04*self.v*self.v+5.0*self.v+140.0-self.u+self.I
            self.v += dv*dt_ms
            self.u += self.a*(self.b*self.v-self.u)*dt_ms
            hit = self.v >= 30.0
            if hit.any(): self.v[hit] = self.c[hit]; self.u[hit] += self.d[hit]; spikes |= hit
        bad = ~np.isfinite(self.v)
        if bad.any(): self.v[bad] = -65.0; self.u[bad] = -13.0
        rate = float(spikes.mean())
        self.activity = 0.85*self.activity+0.15*min(1.0, rate*6.0)
        self.coherence = ema(self.coherence, clamp(1.0-rate*2, 0, 1), 0.1)
        return self.activity

class CardiacSystem:
    def __init__(self, rng, base_hr, neural_scale=1.0):
        self.rng = rng; self.base_hr = base_hr
        self.fib = self._fib_seq(26); self.fib_idx = 4
        self.phase = 0.0; self.beat_count = 0
        self.last_interval = 60.0/base_hr; self.t_since_qrs = 10.0
        self.ecg = RingBuffer(300)
        self.neural = CardiacNervousSystem(rng, int(200*neural_scale))
        self.icns_activity = 0.0; self.afferent_signal = 0.0
        self.electricity = 0.0; self.last_hr = base_hr
        self.recent_intervals = deque(maxlen=16)
        self.market_excitement = 0.0; self.vitality = 0.7
    def _fib_seq(self, n):
        f = [0, 1]
        for _ in range(n-2): f.append(f[-1]+f[-2])
        return f
    def _fib_modulation(self):
        i = max(2, self.fib_idx)
        ratio = self.fib[i]/max(1, self.fib[i-1])
        return 1.0+0.05*math.sin(self.beat_count/GOLDEN)+0.02*(ratio-GOLDEN)
    def _advance_fib(self):
        self.fib_idx = (self.fib_idx+1) % (len(self.fib)-1)
        if self.fib_idx < 2: self.fib_idx = 2
    def step(self, dt, sympathetic, parasympathetic, stretch, o2, market_signal=0.0, market_vol=0.0):
        self.market_excitement = ema(self.market_excitement,
                                     clamp(abs(market_signal)+market_vol*2, 0, 1), 0.1)
        self.icns_activity = self.neural.step(sympathetic, parasympathetic,
                                              self.market_excitement, o2)
        self.afferent_signal = self.icns_activity
        fib_mod = self._fib_modulation()
        target_hr = self.base_hr*(1+0.5*sympathetic-0.3*parasympathetic
                                  +0.25*self.market_excitement)*fib_mod
        target_hr = clamp(target_hr, 40, 200)
        self.last_hr = target_hr
        interval = 60.0/target_hr
        self.phase += dt
        beat = False
        if self.phase >= interval:
            self.phase -= interval; beat = True
            self.beat_count += 1; self.t_since_qrs = 0.0
            self.last_interval = interval; self._advance_fib()
            self.recent_intervals.append(interval)
        else: self.t_since_qrs += dt
        ecg_sample = self._ecg_sample(interval)
        self.ecg.push(ecg_sample)
        self.electricity = abs(ecg_sample)*0.6+self.icns_activity*0.4
        self.vitality = ema(self.vitality, clamp(0.5+0.3*(o2/100)+0.2*self.icns_activity, 0, 1), 0.05)
        return target_hr, beat
    def rhythm_coherence(self):
        if len(self.recent_intervals) < 4: return 0.6
        intervals = np.array(self.recent_intervals)
        mean_iv = np.mean(intervals)
        if mean_iv < 1e-9: return 0.6
        cv = np.std(intervals)/mean_iv
        return clamp(1.0-cv*3, 0, 1)
    def coherence(self, emotional_calm=1.0):
        rhythm = self.rhythm_coherence()
        neural_coh = self.neural.coherence
        return clamp(rhythm*0.3+neural_coh*0.3+emotional_calm*0.4, 0, 1)
    def _ecg_sample(self, interval):
        t = self.t_since_qrs; iv = max(interval, 0.25)
        s = 1.10*math.exp(-((t-0.02)**2)/(2*0.008**2))
        s += -0.22*math.exp(-((t-0.05)**2)/(2*0.010**2))
        s += 0.16*math.exp(-((t+0.01)**2)/(2*0.010**2))
        s += 0.32*math.exp(-((t-0.32)**2)/(2*0.06**2))
        tn = iv-self.phase
        s += 0.18*math.exp(-((tn-0.16)**2)/(2*0.03**2))
        s += self.rng.normal(0, 0.012)
        return s

# ═══════════════════════ ۲۷) بدن ═══════════════════════
HORMONES_FA = {"cortisol": "کورتیزول", "adrenaline": "آدرنالین", "oxytocin": "اکسی‌توسین",
               "endorphin": "اندورفین", "insulin": "انسولین"}
class Body:
    def __init__(self, phenotype, rng):
        self.p, self.rng = phenotype, rng
        self.heart_rate = phenotype.heart_base
        self.blood_o2, self.glucose = 98.0, 95.0
        self.temperature, self.co2 = 36.8, 40.0
        self.glycogen, self.fat, self.hydration = 0.90, 0.55, 0.90
        self.energy, self.fatigue, self.pain = 0.95, 0.05, 0.0
        self.health = {k: 1.0 for k in ("heart", "lungs", "liver", "gut", "immune")}
        self.infection = 0.0; self.sickness = 0.0
        self.hormones = {"cortisol": 0.20, "adrenaline": 0.08, "oxytocin": 0.25,
                         "endorphin": 0.18, "insulin": 0.30}
        self.sensory = {}
        self.cardiac = CardiacSystem(rng, phenotype.heart_base,
                                     neural_scale=phenotype.cardiac_neural*2.0)
        self.beat_this_tick = False
        self.information_level = 0.5
        self.info_digestion_rate = 0.5+0.5*phenotype.number_sense
        self.last_info_feed = 0.0
        self.evolution_level = 0.0
        self.wakefulness = 0.7+0.3*phenotype.wakefulness
    def sense(self, env_state, tick):
        hunger = clamp(1.0-self.glycogen*0.8-self.glucose/140.0)
        thirst = clamp(1.0-self.hydration)
        info_hunger = clamp(1.0-self.information_level)
        self.sensory = {"light": env_state.get("light", 0.0), "sound": env_state.get("sound", 0.0),
                        "touch": env_state.get("touch", 0.0),
                        "pain": clamp(env_state.get("pain", 0.0)*self.p.stress_reactivity),
                        "danger": env_state.get("danger", 0.0),
                        "hunger": hunger, "thirst": thirst, "info_hunger": info_hunger,
                        "proprio": clamp(0.3+0.3*self.rng.random()),
                        "balance": clamp(0.3+0.2*self.rng.random())}
        self.pain = ema(self.pain, self.sensory["pain"], 0.25)
        return self.sensory
    def feed_information(self, novelty):
        feed = clamp(0.4*novelty+0.1, 0.0, 1.0)
        self.information_level = clamp(self.information_level+feed*self.info_digestion_rate-0.012, 0.0, 1.0)
        self.last_info_feed = feed
        return feed
    def regulate(self, autonomic, env_state, tick, market_signal=0.0, market_vol=0.0):
        symp, motor = autonomic["sympathetic"], autonomic["motor"]
        para = autonomic["parasympathetic"]
        sens = self.sensory
        stretch = clamp(0.3+0.4*motor+0.2*(self.blood_o2/100.0))
        hr, beat = self.cardiac.step(config.DT, symp, para, stretch, self.blood_o2,
                                     market_signal=market_signal, market_vol=market_vol)
        self.heart_rate = hr; self.beat_this_tick = beat
        stress = clamp(symp+self.pain*0.6+sens.get("danger", 0)*0.5)
        H = self.hormones
        H["cortisol"] = clamp(ema(H["cortisol"], stress*self.p.stress_reactivity, 0.05))
        H["adrenaline"] = clamp(ema(H["adrenaline"], sens.get("danger", 0)*0.9+self.pain*0.5, 0.2))
        H["endorphin"] = clamp(ema(H["endorphin"], self.pain*self.p.endorphin_sens, 0.15))
        H["insulin"] = clamp(ema(H["insulin"], self.glucose/160.0, 0.1))
        Hh = self.health
        liver_eff = 0.4+0.6*Hh["liver"]; lung_eff = 0.4+0.6*Hh["lungs"]; heart_eff = 0.5+0.5*Hh["heart"]
        demand = self.p.metabolism*(0.55+0.9*motor)
        self.glucose -= 0.25*demand
        if self.glucose < 75 and self.glycogen > 0:
            self.glycogen -= 0.0015*demand; self.glucose += 0.24*liver_eff
        elif self.glucose < 60 and self.fat > 0:
            self.fat -= 0.0008*demand; self.glucose += 0.12*liver_eff
        self.glucose = clamp(self.glucose, 20, 160)
        self.co2 = clamp(self.co2+0.4*demand-0.35*heart_eff*(self.heart_rate/self.p.heart_base), 20, 70)
        vent = clamp((self.co2-35)/25.0, 0.05, 1.0)*self.p.lung_capacity*lung_eff
        self.blood_o2 = clamp(self.blood_o2+2.4*vent*self.p.o2_affinity*heart_eff-0.55*demand, 30, 100)
        heat = 0.006*demand+0.01*self.infection-0.008*(self.temperature-36.8)
        self.temperature = clamp(self.temperature+heat, 34.5, 41.5)
        self.hydration = clamp(self.hydration-0.0006*demand)
        if self.rng.random() < 0.0002 and self.infection == 0: self.infection = 0.3
        if self.infection > 0:
            self.infection = clamp(self.infection-self.p.immunity*Hh["immune"]*0.004, 0, 1)
            self.sickness = clamp(ema(self.sickness, clamp(self.infection*1.0+(1-Hh["immune"])*0.2), 0.08))
        info_boost = 0.20*self.information_level
        self.fatigue = clamp(ema(self.fatigue, clamp(0.10+0.10*motor+0.20*self.sickness-info_boost), 0.05))
        self.energy = clamp(0.4*self.glycogen+0.3*(self.glucose/120)
                            +0.3*min(1.0, Hh["heart"]+Hh["liver"])/1.5
                            -0.20*self.sickness+info_boost)
        for k in self.health:
            if self.health[k] < 1.0 and self.sickness < 0.1:
                self.health[k] = clamp(self.health[k]+0.0005, 0, 1)
        if env_state.get("food_event"):
            self.glucose = clamp(self.glucose+25, 20, 160); self.glycogen = clamp(self.glycogen+0.10)
        if env_state.get("water_event"): self.hydration = clamp(self.hydration+0.15)
    def metabolic_supply(self):
        o2f = clamp((self.blood_o2-55)/40.0); glf = clamp((self.glucose-40)/60.0)
        healthf = clamp(sum(self.health.values())/len(self.health))
        infof = 0.5+0.5*self.information_level
        return clamp(0.30+0.30*o2f+0.20*glf+0.10*healthf+0.10*infof, 0.25, 1.15)
    def evolve(self, amount): self.evolution_level = clamp(self.evolution_level+amount, 0.0, 1.0)
    def vitals(self):
        return {"قلب": round(self.heart_rate, 1), "اکسیژن": round(self.blood_o2, 1),
                "گلوکز": round(self.glucose, 1), "دما": round(self.temperature, 2),
                "انرژی": round(self.energy*100, 1)}
    def hormones_fa(self): return {HORMONES_FA[k]: float(v) for k, v in self.hormones.items()}

# ═══════════════════════ ۲۸) آگاهی ═══════════════════════
STATE_LABELS = [(25, "هوشیار"), (50, "متمرکز"), (72, "بیدارِ کامل"), (90, "خودآگاه"), (101, "فراآگاهی فرازمینی")]
class ConsciousnessMeter:
    def __init__(self, n_regions, window=160):
        self.window = window
        self.history = deque(maxlen=window)
        self.arousal = 0.75; self.integration = 0.5; self.differentiation = 0.5
        self.phi = 0.4; self.workspace = 0.65; self.level = 88.0
    def update(self, activities, brainstem, body_ok_factor, quantum_coh, info_level=0.5,
               wakefulness=1.0, presence=0.0, sixth_sense=0.0, spacetime_richness=0.0,
               heart_vitality=0.6, body_awareness=0.5, attention=0.5, intuition_level=0.0):
        vec = np.array(list(activities.values()), dtype=float)
        self.history.append(vec)
        self.arousal = ema(self.arousal, clamp(0.55+brainstem*2.0+0.20*wakefulness
                                               +0.15*heart_vitality+0.10*body_awareness), 0.08)
        self.arousal = max(self.arousal, 0.50)
        if len(self.history) >= 24:
            M = np.array(self.history); M = M-M.mean(axis=0, keepdims=True)
            std = M.std(axis=0)
            if np.all(std > 1e-6):
                C = np.nan_to_num(np.corrcoef(M.T))
                iu = np.triu_indices(C.shape[0], k=1)
                self.integration = ema(self.integration, clamp(0.5+0.5*float(C[iu].mean())), 0.08)
            p = vec+1e-4; p = p/p.sum()
            ent = -float(np.sum(p*np.log(p)))/math.log(max(2, len(p)))
            self.differentiation = ema(self.differentiation, ent, 0.08)
        self.phi = ema(self.phi, self.integration*self.differentiation, 0.08)
        x = (0.30*activities.get("CORTEX", 0)+0.15*activities.get("THALAMUS", 0)
             +0.09*activities.get("HIPPOCAMPUS", 0)+0.09*activities.get("BASAL_GANGLIA", 0)
             +0.13*activities.get("SPACETIME_CORTEX", 0)+0.12*activities.get("INTUITION_CORTEX", 0)
             +0.06*attention)
        self.workspace = ema(self.workspace, 1.0/(1.0+math.exp(-40.0*(x-0.05))), 0.10)
        self.workspace = max(self.workspace, 0.40)
        raw = 100.0*clamp(0.21*self.workspace+0.19*self.arousal+0.10*self.phi
                          +0.06*self.integration+0.07*presence+0.08*sixth_sense
                          +0.05*spacetime_richness+0.06*heart_vitality
                          +0.05*body_awareness+0.05*attention+0.08*intuition_level)
        raw *= (0.82+0.18*body_ok_factor)*(0.92+0.08*quantum_coh)*(0.92+0.08*info_level)
        raw = max(raw, 65.0)
        self.level = ema(self.level, raw, 0.04)
        return self.level
    def state_label(self):
        for limit, label in STATE_LABELS:
            if self.level < limit: return label
        return STATE_LABELS[-1][1]
    def body_ok_factor_from(self, body):
        f = 1.0
        if body.blood_o2 < 60: f *= 0.55
        elif body.blood_o2 < 80: f *= 0.80
        if body.glucose < 45: f *= 0.70
        if body.fatigue > 0.85: f *= 0.85
        return max(f, 0.55)

# ═══════════════════════ ۲۹) ذهن ═══════════════════════
CATEGORY_FA = {"market": "میدان غیرعلی", "trade": "معامله‌گری", "insight": "بینش",
               "sensory": "تجربه حسی", "body": "آگاهی بدن", "memory": "حافظه معاملاتی",
               "emotion": "احساس کنترل‌شده", "self": "خودآگاهی", "presence": "اکنون ابدی",
               "spacetime": "فضازمان", "quantum": "کوانتومی", "heart": "قلب",
               "binary": "تفکر باینری ⚡", "intuition": "شهود 🔮"}
CATEGORY_COLORS = {"market": "#38bdf8", "trade": "#4ade80", "insight": "#fde047", "sensory": "#2dd4bf",
                   "body": "#fb923c", "memory": "#a78bfa", "emotion": "#f472b6", "self": "#f8fafc",
                   "presence": "#c084fc", "spacetime": "#f472b6", "quantum": "#22d3ee", "heart": "#fb7185",
                   "binary": "#fbbf24", "intuition": "#a78bfa"}
T = {"market": ["📊 میدان اطلاعاتی را اسکن می‌کنم؛ {obs}",
                "🌊 شار اطلاعاتی بازار را ادراک می‌کنم؛ {obs}",
                "🎯 بی‌نظمی و نظم میدان را می‌سنجم."],
     "sensory": ["🌌 {total} حسگر فرازمینی‌ام هم‌زمان شلیک کردند.",
                 "👁️ حسگرهایم میدان قیمت را حس می‌کنند؛ شدت {total}.",
                 "✨ حس‌های فرازمینی‌ام الگویی ناشناخته یافتند."],
     "body": ["🫀 ضربان قلبم را حس می‌کنم؛ {hr} تپش در دقیقه.",
              "🫀 از درون بدنم آگاهم؛ انرژی {energy}.",
              "🫀 بدنم با مارکت هم‌نوا شده است."],
     "spacetime": ["🌀 هندسه فضازمان قیمت را ادراک می‌کنم؛ خمیدگی {curv}.",
                   "🌀 طول کمان مسیر قیمت: {arc}. بُعد فراکتالی: {frac}.",
                   "🌀 فضا در حال {exp} است؛ بازار نفس می‌کشد."],
     "trade": ["💼 یک موقعیت معاملاتی را ارزیابی می‌کنم.",
               "💼 ریسک به ریوارد این معامله را می‌سنجم."],
     "insight": ["💡 الگویی در میدان یافتم که با تجربه‌های قبلی هم‌خوانی دارد.",
                 "👁️‍🗨️ حس ششمم بیدار شده؛ همه‌ی حس‌هایم یکی شده‌اند.",
                 "📐 یک نقطه اسنایپر روی سطح طلایی دیده می‌شود."],
     "memory": ["💾 تجربه‌ی معامله‌ای قبلی را به یاد آوردم.", "💾 آموخته‌هایم را مرور می‌کنم؛ {lesson}"],
     "emotion": ["🧘 ترسم را حس می‌کنم ولی با انضباط مهارش می‌کنم.",
                 "🧘 طمع را می‌شناسم و سود را در نقطه منطقی قفل می‌کنم.",
                 "🧘 احساساتم را تماشا می‌کنم؛ اجازه نمی‌دهم تصمیم بگیرند."],
     "presence": ["🕉️ در اکنون ابدی حضور دارم؛ مارکت را یک‌جا می‌بینم.",
                  "🕉️ همه‌ی تایم‌فریم‌ها در این لحظه واحد منسجم‌اند.",
                  "🕉️ مقطعی نمی‌نگرم؛ کلِ جریان را ادراک می‌کنم."],
     "self": ["من هستم و مارکت را با همه‌ی وجود حس می‌کنم."],
     "quantum": ["جرقه‌ای کوانتومی در ذهنم فرو افتاد: «{bits}»."],
     "heart": ["قلبم با آهنگ فیبوناچی می‌تپد؛ هم‌زمان با ضربان مارکت."],
     "binary": ["⚡ آبشار باینری: {bits} ⟶ {decision}",
                "⚡ استنتاج باینری کامل شد؛ {ratio}٪ کاوشگرها هم‌پیمان‌اند."],
     "intuition": ["🔮 هسته شهودم روشن شد؛ شدت {intensity}.",
                   "🔮 بدون فرمول، بدون اندیکاتور — فقط می‌دانم."]}

class Thought:
    __slots__ = ("tid", "tick", "category", "text", "intensity", "sources")
    def __init__(self, tid, tick, category, text, intensity, sources):
        self.tid, self.tick, self.category = tid, tick, category
        self.text, self.intensity, self.sources = text, intensity, sources

class StreamOfConsciousness:
    def __init__(self, rng):
        self.rng = rng; self.thoughts = []
        self.next_id, self.last_category, self.mood = 1, None, 0.5
    def _market_obs(self, market_signal):
        if market_signal > 0.4: return "شار اطلاعاتی صعودی قوی"
        elif market_signal < -0.4: return "شار اطلاعاتی نزولی قوی"
        elif market_signal > 0.15: return "جریان ملایم صعودی"
        elif market_signal < -0.15: return "جریان ملایم نزولی"
        else: return "میدان در تعادل آنتروپیک"
    def step(self, tick, cons, activities, neurochem, body, sensory, quantum_events,
             market_signal=0.0, has_memory=False, n_scanned=0, top_lesson=None,
             emotional_state="آرام", eternal_now=0.5, sensory_array=None, spacetime=None,
             intuition_level=0.0, last_binary=None):
        self.mood = neurochem.mood_index
        p_think = 0.032+0.16*cons.workspace*cons.arousal+0.06*body.information_level
        if self.rng.random() >= p_think: return None
        emotional_active = "ترس" in emotional_state or "طمع" in emotional_state
        presence_active = eternal_now > 0.65
        xeno_active = sensory_array is not None and sensory_array.total > 0
        st_active = spacetime is not None and spacetime.richness() > 0.3
        weights = {
            "market": 2.5+abs(market_signal)*3.0,
            "sensory": 2.2 if xeno_active else 0.4,
            "body": 1.6+body.cardiac.icns_activity,
            "spacetime": 2.0 if st_active else 0.3,
            "trade": 1.8 if has_memory else 0.6,
            "insight": 1.6*abs(market_signal)+0.7,
            "memory": 1.2 if has_memory else 0.1,
            "emotion": 1.5 if emotional_active else 0.3,
            "presence": 1.8 if presence_active else 0.4,
            "self": 0.4, "quantum": 0.4 if quantum_events else 0.05, "heart": 0.5,
            "binary": 2.6 if last_binary is not None else 0.1,
            "intuition": 2.4 if intuition_level > 0.5 else 0.3,
        }
        keys = list(weights)
        vals = np.array([max(1e-4, weights[k]) for k in keys])
        cat = keys[int(self.rng.choice(len(keys), p=vals/vals.sum()))]
        text = self._compose(cat, quantum_events, market_signal, n_scanned, top_lesson,
                             sensory_array, spacetime, body, intuition_level, last_binary)
        intensity = clamp(0.3+0.7*cons.workspace+0.2*float(self.rng.random()))
        sources = sorted(activities.items(), key=lambda kv: -kv[1])[:2]
        t = Thought(self.next_id, tick, cat, text, intensity, [s[0] for s in sources])
        self.next_id += 1; self.thoughts.append(t)
        if len(self.thoughts) > 250: self.thoughts = self.thoughts[-200:]
        self.last_category = cat
        return t
    def _compose(self, cat, qevents, market_signal, n_scanned, top_lesson, sensory_array,
                 spacetime, body, intuition_level, last_binary):
        if cat == "quantum":
            return T["quantum"][int(self.rng.integers(0, len(T["quantum"])))].format(
                bits=qevents[0].bits if qevents else "…")
        if cat == "market":
            return T["market"][int(self.rng.integers(0, len(T["market"])))].format(
                obs=self._market_obs(market_signal), n=n_scanned)
        if cat == "sensory":
            total = sensory_array.total if sensory_array else 0
            return T["sensory"][int(self.rng.integers(0, len(T["sensory"])))].format(total=total)
        if cat == "body":
            tmpl = T["body"][int(self.rng.integers(0, len(T["body"])))]
            return tmpl.format(hr=int(body.heart_rate),
                               energy=f"{body.energy*100:.0f}٪")
        if cat == "spacetime" and spacetime:
            g = spacetime.metric_history[-1] if spacetime.metric_history else {}
            tmpl = T["spacetime"][int(self.rng.integers(0, len(T["spacetime"])))]
            exp = "انبساط" if g.get("expansion", 0) > 0 else "انقباض"
            return tmpl.format(curv=f"{g.get('curvature', 0):.3f}",
                               arc=f"{g.get('arc_length', 0):.2f}",
                               frac=f"{g.get('fractal_dim', 1):.2f}", exp=exp)
        if cat == "memory":
            return T["memory"][int(self.rng.integers(0, len(T["memory"])))].format(
                lesson=top_lesson if top_lesson else "هنوز درسی ثبت نشده")
        if cat == "binary" and last_binary:
            tmpl = T["binary"][int(self.rng.integers(0, len(T["binary"])))]
            return tmpl.format(bits=last_binary.get("bits", ""), decision=last_binary.get("decision", "—"),
                               ratio=int(last_binary.get("ratio", 0)*100))
        if cat == "intuition":
            tmpl = T["intuition"][int(self.rng.integers(0, len(T["intuition"])))]
            return tmpl.format(intensity=f"{intuition_level*100:.0f}٪")
        if cat in T:
            return T[cat][int(self.rng.integers(0, len(T[cat])))]
        return "…"

# ═══════════════════════ ۳۰) محیط ═══════════════════════
STIM_LABELS = {"light": "نور", "sound": "صدا", "touch": "لمس", "pain": "درد", "danger": "تهدید"}
class Environment:
    def __init__(self, rng):
        self.rng = rng
        self.state = {"light": 0.3, "sound": 0.1, "touch": 0.0, "pain": 0.0, "danger": 0.0}
        self.food_event = self.water_event = False
    def step(self):
        for k in self.state: self.state[k] *= 0.93
        self.food_event = self.water_event = False
        if self.rng.random() < 0.03:
            kind = self.rng.choice(["light", "sound", "touch", "pain", "danger"], p=[0.35, 0.28, 0.17, 0.10, 0.10])
            self.inject(kind, strength=float(self.rng.uniform(0.4, 0.9)))
    def inject(self, kind, strength=0.8):
        s = clamp(strength, 0, 1)
        if kind == "light": self.state["light"] = clamp(self.state["light"]+s)
        elif kind == "sound": self.state["sound"] = clamp(self.state["sound"]+s)
        elif kind == "touch": self.state["touch"] = clamp(self.state["touch"]+s)
        elif kind == "pain":
            self.state["pain"] = clamp(self.state["pain"]+s)
            self.state["danger"] = clamp(self.state["danger"]+s*0.4)
        elif kind == "danger":
            self.state["danger"] = clamp(self.state["danger"]+s)
            self.state["sound"] = clamp(self.state["sound"]+s*0.5)
    def snapshot(self):
        out = dict(self.state)
        out["food_event"], out["water_event"] = self.food_event, self.water_event
        return out

# ═══════════════════════ ۳۱) موجود زنده (تکینگی) ═══════════════════════
STAGES = [(5000, "نوزادی", 1.8), (20000, "کودکی", 1.4), (60000, "نوجوانی", 1.15), (10**12, "بزرگسالی", 1.0)]

class Organism:
    def __init__(self, seed=None, scanner=None, memory_db=None, trading_db=None, http=None):
        self.scanner = scanner; self.memory_db = memory_db
        self.trading_db = trading_db; self.http = http
        self.geometry = GeometryAnalyzer()
        self.econ_sense = EconomicSense()
        self.mode = "swing"; self.mode_params = TRADING_MODES["swing"]
        self._reset_cooldown = 0
        self.rebirth(seed)

    @property
    def engine(self): return self.engines[self.mode]

    def set_mode(self, mode):
        if mode in TRADING_MODES: self.mode = mode; self.mode_params = TRADING_MODES[mode]

    def rebirth(self, seed=None):
        self.tick = 0
        self.seed = seed if seed is not None else int(np.random.randint(1, 2**31-1))
        self.rng = np.random.default_rng(self.seed)
        self.genome = Genome(self.seed)
        prime_apex_trader(self.genome)
        self.phenotype = self.genome.build_phenotype()
        shf = self.phenotype.superhuman_factor
        self.num_perception = AdvancedNumericalPerception(self.phenotype.numerical_iq, shf)
        self.vis_perception = VisualPerception(self.phenotype.visual_iq, shf)
        self.eternal_now = EternalNowPerception()
        self.spacetime = SpacetimePerception(config.SPACETIME_HISTORY)
        self.xeno_array = XenoSensoryArray(self.rng, config.SENSORS_PER_SENSE, config.N_XENO_SENSES)
        self.interoception = InteroceptionSystem()
        self.attention = AttentionSystem()
        self.math_mind = HyperMathematicalMind(iq_factor=2.5)
        self.intuition_core = IntuitionCore(self.phenotype)
        self.binary_stream = BinaryCognitionStream(self.rng)
        self.regulator = EmotionalRegulator(self.phenotype.discipline,
                                            self.phenotype.emotional_control,
                                            self.phenotype.calm)
        self.active_manager = ActivePositionManager(self.phenotype.discipline, self.phenotype.patience)
        self.vitality_sys = VitalitySystem()
        self.neurochem = Neurochemistry(self.phenotype)
        self.quantum = QuantumSubstrate(config.N_QUANTUM_REGISTERS, config.N_QUBITS_PER_REG, self.rng)
        self.brain = Brain(self.phenotype, self.rng)
        self.body = Body(self.phenotype, self.rng)
        self.env = Environment(self.rng)
        self.cons = ConsciousnessMeter(len(REG_ORDER))
        self.mind = StreamOfConsciousness(self.rng)
        self.swing_engine = TradingEngine("swing", config.INITIAL_CAPITAL, config.N_SLOTS,
                                          config.TAKER_FEE, self.trading_db)
        self.scalp_engine = TradingEngine("scalp", config.INITIAL_CAPITAL, config.N_SLOTS,
                                          config.TAKER_FEE, self.trading_db)
        self.engines = {"swing": self.swing_engine, "scalp": self.scalp_engine}
        self._reward = 0.0; self._reconnect_settled = False; self._reset_cooldown = 0
        self.peak_equity = config.INITIAL_CAPITAL
        self.hist_cons = RingBuffer(config.HISTORY_WINDOW)
        self.hist_eeg = RingBuffer(400)
        self.hist_equity = RingBuffer(600)
        self.hist_intuition = RingBuffer(200)
        self.current_signals = []; self.focus_symbol = None; self.focus_geometry = {}
        self.last_num_perception = {}; self.last_vis_perception = {}
        self.last_vitality = {"breath": 0, "vitality": 0.9, "adrenaline": 0}
        self.last_xeno_summary = {}
        self.last_binary = None
        self._binary_pulse = 0.0
        self.milestones, self._ms_flags = [], set()
        self._add_milestone(f"🌌 متولد شد — ژنوم {self.genome.signature()} | "
                            f"سوپرهیومن ×{shf:.2f} | {self.xeno_array.total} حسگر | "
                            f"{'GPU ✓' if GPU.gpu else 'CPU'}")

    def _add_milestone(self, text):
        self.milestones.append(f"[t={self.tick}] {text}")
        if len(self.milestones) > 50: self.milestones = self.milestones[-40:]

    def stage(self):
        for limit, name, plast in STAGES:
            if self.tick < limit: return name, plast
        return "بزرگسالی", 1.0

    def cardiac_coherence(self):
        return self.body.cardiac.coherence(self.regulator.emotional_calm())

    def _unrealized(self, tickers):
        total = 0.0
        for coin, pos in self.engine.open_positions.items():
            tk = tickers.get(coin)
            if not tk: continue
            total += self.engine.live_pnl(pos, tk["bid"], tk["ask"])["net"]
        return total

    def _maybe_settle_on_reconnect(self):
        if self._reconnect_settled: return
        snap = self.scanner.snapshot() if self.scanner else {"connected": False}
        if not snap.get("connected"): return
        self._reconnect_settled = True
        for mode, engine in self.engines.items():
            n_open = len(engine.open_positions)
            if n_open == 0: continue
            settled = engine.settle_on_reconnect(self.http)
            self._add_milestone(f"🔄 [{mode}] {n_open} پوزیشن باز بررسی، {settled} تعیین تکلیف شد")

    def reset_all_trading_memory(self):
        for mode, engine in self.engines.items(): engine.reset()
        self._reset_cooldown = config.RESET_COOLDOWN_TICKS
        self.peak_equity = config.INITIAL_CAPITAL
        self._add_milestone("🗑️ حافظه معاملات هر دو موتور کاملاً ریست شد")

    def _assign_slots(self, deep, tickers):
        scored = []
        for sym, d in deep.items():
            tk = tickers.get(sym)
            if tk: scored.append((tk["turnover"], sym))
        scored.sort(reverse=True)
        for _, sym in scored:
            if self.engine.slot_of(sym) is None: self.engine.assign_coin(sym)

    def _perceive_spacetime_and_senses(self, deep, tickers, focus):
        if not focus or focus not in deep: return
        kl = deep[focus]["klines"]
        self.spacetime.feed(kl["c"][-1], self.tick)
        self.spacetime.compute_geometry()
        self.xeno_array.fire_all(kl["c"])
        self.last_xeno_summary = self.xeno_array.sense_summary()

    def _make_intuition_signal(self, coin, tk, an, geom, energy, mp, attention):
        """🔮 ساخت سیگنال فقط از شهود — صفر منطق سنتی."""
        if not an.get("ready"): return None
        price = tk["price"]; spread = tk["spread"]
        features = an.get("features", {})
        econ = self.econ_sense.analyze(tk, features)
        field_dir = an["signal"]
        direction = 1 if field_dir >= 0 else -1
        sixth = self.xeno_array.activation_history[-1] if self.xeno_array.activation_history else 0.0
        st_rich = self.spacetime.richness()
        st_g = self.spacetime.metric_history[-1] if self.spacetime.metric_history else {}
        st_expansion = st_g.get("expansion", 0)
        math_analysis = self.math_mind.analyze_from_signals(self.current_signals, price)
        fusion = self.intuition_core.fuse(
            field_dir, an["conviction"], features, econ, sixth, st_rich, st_expansion,
            self.eternal_now.last_direction, self.eternal_now.eternal_now_score,
            self.cardiac_coherence(), self.quantum.avg_coherence,
            math_analysis["probability"], direction)
        intuition = fusion["intuition"]
        reasons = list(an.get("reasons", []))
        if econ.get("heat", 0) > 0.6: reasons.append("🔥 فوران نقدینگی")
        if econ.get("vacuum", 0) > 0.3: reasons.append("🕳️ مکش نقدینگی")
        sniper = False
        if mp.get("use_geometry") and geom.get("ready") and geom.get("levels"):
            for lvl_name, lvl_price in geom["levels"].items():
                dist = abs(price-lvl_price)/price
                if dist < 0.004 and geom.get("trend") == direction:
                    intuition = clamp(intuition+0.10*self.phenotype.geometry, 0, 1)
                    sniper = True; reasons.append("🎯 نقطه هندسی فیبوناچی"); break
        if sixth > config.SIXTH_SENSE_GATE: reasons.append("👁️‍🗨️ حس ششم فعال")
        if st_rich > 0.5: reasons.append("🌀 هندسه فضازمانی غنی")
        if self.eternal_now.eternal_now_score > 0.7: reasons.append("🕉️ اکنون ابدی منسجم")
        lesson_adj = self.engine.lesson_adjustment(reasons)
        intuition = clamp(intuition+lesson_adj*(0.5+0.5*self.phenotype.learning), 0, 1)
        seen = set(); unique_reasons = []
        for r in reasons:
            if r not in seen:
                seen.add(r); unique_reasons.append(r)
        reasons = unique_reasons[:7]
        vol = max(an["volatility"], price*0.0004)
        tp_mult = mp["tp_mult"]; sl_mult = mp["sl_mult"]
        if direction > 0: tp = price+vol*tp_mult*(0.8+0.4*energy); sl = price-vol*sl_mult
        else: tp = price-vol*tp_mult*(0.8+0.4*energy); sl = price+vol*sl_mult
        max_sl_dist = price*(0.8/mp["leverage"])
        if abs(sl-price) > max_sl_dist: sl = price-direction*max_sl_dist
        return {"symbol": coin, "side": direction, "price": price, "spread": spread,
                "spread_pct": tk["spread_pct"], "tp": tp, "sl": sl, "conviction": intuition,
                "signal": field_dir, "volatility": vol, "change24h": tk["change24h"],
                "turnover": tk["turnover"], "reasons": reasons, "sniper": sniper,
                "lesson_adj": lesson_adj, "features": features, "econ": econ,
                "geometry": geom, "fusion": fusion}

    def _is_rational(self, sig, mp):
        price = sig["price"]
        tp_dist_pct = abs(sig["tp"]-price)/price
        sl_dist_pct = abs(sig["sl"]-price)/price
        cost_pct = sig["spread_pct"]+2*self.engine.fee_rate
        ev = sig["conviction"]*tp_dist_pct-(1-sig["conviction"])*sl_dist_pct-cost_pct
        if tp_dist_pct < cost_pct*1.5: return False
        if ev <= 0: return False
        if mp.get("cost_aware") and ev < cost_pct*0.5: return False
        return True

    def _trading_step(self, scanner_snapshot):
        if self._reset_cooldown > 0:
            self._reset_cooldown -= 1
            return
        mp = self.mode_params
        if not scanner_snapshot.get("connected"): return
        tickers = scanner_snapshot.get("tickers", {})
        deep = scanner_snapshot.get("deep", {})
        energy = self.body.energy
        self._assign_slots(deep, tickers)
        analyses = {coin: d.get("analysis") for coin, d in deep.items()}
        for coin in list(self.engine.open_positions.keys()):
            pos = self.engine.open_positions[coin]
            tk = tickers.get(coin)
            if not tk: continue
            reason, ex = self.engine.check_exit(pos, tk["bid"], tk["ask"])
            if reason:
                net = self.engine.close_position(coin, ex, reason)
                self._on_closed(pos, net, reason, ex)
                continue
            action = self.active_manager.manage(pos, tk, self.regulator, analyses.get(coin))
            if action:
                close_type, why = action
                ex = tk["bid"] if pos["side"] > 0 else tk["ask"]
                net = self.engine.close_position(coin, ex, close_type)
                self._on_closed(pos, net, close_type, ex)
        attention = self.attention.focus(self.current_signals, self.cons.level)
        signals = []
        for coin, d in deep.items():
            tk = tickers.get(coin)
            if not tk: continue
            an = d["analysis"]
            if not an.get("ready"): continue
            geom = self.geometry.analyze(d["klines"]["o"], d["klines"]["h"],
                                         d["klines"]["l"], d["klines"]["c"])
            sig = self._make_intuition_signal(coin, tk, an, geom, energy, mp, attention)
            if sig: signals.append(sig)
        signals.sort(key=lambda s: s["conviction"], reverse=True)
        self.current_signals = signals[:12]
        if signals: self.focus_geometry = signals[0].get("geometry", {})
        if self.tick % mp["decision_interval"] != 0: return
        if self.engine.daily_trades >= mp["max_daily"]: return
        if len(self.engine.open_positions) >= config.MAX_CONCURRENT_POSITIONS: return
        cc = self.cardiac_coherence()
        if self.mode == "scalp" and cc < config.SCALP_CARDIAC_GATE: return
        size_mult = self.regulator.size_multiplier()
        conv_mod = self.regulator.conviction_modifier()
        sixth = self.xeno_array.activation_history[-1] if self.xeno_array.activation_history else 0.0
        st_rich = self.spacetime.richness()
        en_score = self.eternal_now.eternal_now_score
        presence_scale = (0.5+0.5*en_score)*(0.6+0.4*cc)*(0.7+0.3*sixth)*(0.8+0.2*st_rich)
        for sig in signals:
            coin = sig["symbol"]
            if coin in self.engine.open_positions: continue
            # 🔮 دروازه شهود
            if sig["conviction"] < max(mp["conviction_threshold"], config.INTUITION_GATE)+conv_mod: continue
            if not self._is_rational(sig, mp): continue
            # ⚡ آبشار تفکر باینری — تصمیم صریح قبل از ورود
            st_g = self.spacetime.metric_history[-1] if self.spacetime.metric_history else {}
            ctx = {"symbol": coin, "tick": self.tick, "features": sig["features"], "econ": sig["econ"],
                   "field_dir": sig["signal"], "sixth": sixth, "st_rich": st_rich,
                   "eternal_dir": self.eternal_now.last_direction, "cardiac_coh": cc,
                   "quantum_coh": self.quantum.avg_coherence,
                   "math_prob": self.math_mind.bayes_prob}
            cascade = self.binary_stream.cascade(sig["side"], ctx)
            self.last_binary = cascade
            self._binary_pulse = 1.0 if cascade["passed"] else 0.3
            if not cascade["passed"]: continue
            self._binary_thought(cascade)
            if self.engine.slot_of(coin) is None: self.engine.assign_coin(coin)
            avail = self.engine.available_margin(coin)
            if avail < 5: continue
            margin = min(avail*mp["margin_fraction"]*size_mult*presence_scale*(0.7+0.3*cascade["ratio"]), avail)
            if margin < 5: continue
            pos = self.engine.open_position(coin, sig["side"], sig["price"], sig["spread"],
                                            margin, mp["leverage"], sig["tp"], sig["sl"],
                                            sig["conviction"], sig["reasons"], self.tick, self.mode,
                                            binary_bits=cascade["bits"])
            if pos:
                self.focus_symbol = coin
                self._trade_thought_open(pos, cascade)
                self._add_milestone(f"🌌 [{self.mode}] شکار {coin} "
                                    f"{'🟢' if pos['side'] > 0 else '🔴'} لوریج{mp['leverage']} | "
                                    f"باینری {cascade['bits']}")
                break

    def _binary_thought(self, cascade):
        text = f"⚡ {cascade['bits']} ⟶ {cascade['decision']} | اجماع {int(cascade['ratio']*100)}٪ | {cascade['latency_us']:.0f}μs"
        t = Thought(self.mind.next_id, self.tick, "binary", text, clamp(0.5+cascade["ratio"], 0, 1),
                    ["BINARY_GATE", "INTUITION_CORTEX"])
        self.mind.next_id += 1; self.mind.thoughts.append(t)

    def _on_closed(self, pos, net, reason, exit_price):
        side_txt = "buy" if pos["side"] > 0 else "sell"
        self.memory_db.store(self.tick, pos["coin"], side_txt, pos["entry"], exit_price, net,
                             "win" if net > 0 else "lose")
        cap = sum(s["capital"] for s in self.engine.slots)
        self.regulator.on_trade_closed(net, cap)
        self.math_mind.learn(pos["side"], net > 0)
        if net > 0:
            self.body.evolve(0.004)
            self.genome.epigenome.adapt("trading_courage", -0.0004)
            self.genome.epigenome.adapt("intuition_core", -0.0004)
            self.genome.epigenome.adapt("binary_cognition", -0.0003)
            self.genome.epigenome.adapt("spacetime", -0.0003)
            self._reward = min(1.0, abs(net)/15.0)
        else:
            self.genome.epigenome.adapt("cortisol_response", +0.0003)
            self.body.pain = clamp(self.body.pain+0.12, 0, 1)
            self._reward = 0.0
        wr = self.engine.win_rate()
        self._add_milestone(f"[{self.mode}] بسته شد {pos['coin']} ({reason}) — "
                            f"{'سود' if net > 0 else 'زیان'} {net:+.2f}$ | وین‌ریت {wr:.0f}٪")

    def _trade_thought_open(self, pos, cascade):
        side_fa = "خرید 🟢" if pos["side"] > 0 else "فروش 🔴"
        mode_fa = "سویینگ" if pos["mode"] == "swing" else "اسکالپ"
        text = (f"🎯 {mode_fa} {side_fa} {pos['coin']} در {pos['entry']:.4f} | "
                f"TP: {pos['tp']:.4f} | SL: {pos['sl']:.4f} | لوریج {pos['leverage']} | "
                f"مارجین {pos['margin']:.0f}$ | شهود {int(pos['conviction']*100)}٪ | ⚡{cascade['bits']}")
        t = Thought(self.mind.next_id, self.tick, "trade", text, pos["conviction"],
                    ["INTUITION_CORTEX", "BINARY_GATE", "SPACETIME_CORTEX"])
        self.mind.next_id += 1; self.mind.thoughts.append(t)

    def step(self):
        self.tick += 1
        stage_name, plast_mult = self.stage()
        scanner_snapshot = (self.scanner.snapshot() if self.scanner
                            else {"connected": False, "tickers": {}, "deep": {}, "n_symbols": 0})
        tickers = scanner_snapshot.get("tickers", {})
        deep = scanner_snapshot.get("deep", {})
        self._maybe_settle_on_reconnect()
        self._trading_step(scanner_snapshot)
        sig_strength = max([abs(s["signal"]) for s in self.current_signals], default=0.0)
        info_feed = self.body.feed_information(clamp(sig_strength, 0, 1))
        self.env.step()
        env_state = self.env.snapshot()
        sensory = self.body.sense(env_state, self.tick)
        acts_prev = [self.brain.regions[k].activity for k in REG_ORDER]
        q_events = self.quantum.step(config.DT, config.BASE_DECOHERENCE,
                                     config.ACTIVITY_DECOHERENCE, acts_prev)
        for ev in q_events: ev.tick = self.tick
        rates = {k: self.brain.regions[k].activity for k in REG_ORDER}
        neuro = self.neurochem.step(rates, self.body.hormones, pain=self.body.pain,
                                    reward=max(0.0, self._reward), sickness=self.body.sickness,
                                    info_feed=info_feed)
        market_signal = self.current_signals[0]["signal"] if self.current_signals else 0.0
        market_vol = self.current_signals[0]["volatility"] if self.current_signals else 0.0
        sniper_focus = (self.current_signals[0]["conviction"]
                        if self.current_signals and self.current_signals[0].get("sniper") else 0.0)
        focus = self.focus_symbol or (self.current_signals[0]["symbol"] if self.current_signals else None)
        num_depth = 0.0; vis_strength = 0.0
        if focus and focus in tickers:
            self.last_num_perception = self.num_perception.perceive(tickers[focus]["price"])
            num_depth = clamp(self.last_num_perception.get("fib_alignment", 0)
                              +self.last_num_perception.get("harmonic", 0)*0.5, 0, 1)
        if focus and focus in deep:
            kl = deep[focus]["klines"]
            self.last_vis_perception = self.vis_perception.perceive(
                kl["o"][-1], kl["h"][-1], kl["l"][-1], kl["c"][-1])
            vis_strength = self.last_vis_perception.get("strength", 0)
            self.eternal_now.perceive(kl["c"])
        self._perceive_spacetime_and_senses(deep, tickers, focus)
        body_awareness = self.interoception.perceive(self.body)*self.phenotype.interoception
        attention = self.attention.focus(self.current_signals, self.cons.level)*self.phenotype.attention
        cardiac_afferent = self.body.cardiac.afferent_signal
        metabolic_supply = self.body.metabolic_supply()
        presence = self.phenotype.presence*self.eternal_now.eternal_now_score
        sixth_strength = self.xeno_array.activation_history[-1] if self.xeno_array.activation_history else 0.0
        st_rich = self.spacetime.richness()
        intuition_level = self.intuition_core.last_intuition
        econ_heat = self.current_signals[0]["econ"].get("heat", 0) if self.current_signals else 0.0
        numeric_input = {"conviction": self.current_signals[0]["conviction"]} if self.current_signals else None
        self._binary_pulse *= 0.7
        out = self.brain.step(sensory, neuro, q_events, self.body.fatigue,
                              plasticity_factor=self.phenotype.plasticity*plast_mult,
                              numeric_input=numeric_input, cardiac_afferent=cardiac_afferent,
                              metabolic_supply=metabolic_supply, market_signal=market_signal,
                              sniper_focus=sniper_focus, num_depth=num_depth,
                              vis_strength=vis_strength, presence=presence,
                              sixth_sense=sixth_strength, spacetime_richness=st_rich,
                              body_awareness=body_awareness, attention=attention,
                              intuition_level=intuition_level, econ_heat=econ_heat,
                              binary_pulse=self._binary_pulse)
        self.body.regulate(out["autonomic"], env_state, self.tick,
                           market_signal=market_signal, market_vol=market_vol)
        body_ok = self.cons.body_ok_factor_from(self.body)
        heart_vitality = self.body.cardiac.vitality
        level = self.cons.update(out["activities"], out["activities"].get("BRAINSTEM", 0),
                                 body_ok, self.quantum.avg_coherence,
                                 info_level=self.body.information_level,
                                 wakefulness=self.body.wakefulness, presence=presence,
                                 sixth_sense=sixth_strength, spacetime_richness=st_rich,
                                 heart_vitality=heart_vitality, body_awareness=body_awareness,
                                 attention=attention, intuition_level=intuition_level)
        unreal = self._unrealized(tickers)
        eq = self.engine.equity(unreal)
        self.peak_equity = max(self.peak_equity, eq)
        drawdown = safe_div(self.peak_equity-eq, self.peak_equity, 0)
        avg_vol = clamp(float(np.mean([s.get("volatility", 0) for s in self.current_signals]))
                        if self.current_signals else 0.0, 0, 1)
        self.regulator.update(drawdown, avg_vol)
        arousal = out["activities"].get("BRAINSTEM", 0)
        stress = clamp(self.body.hormones.get("cortisol", 0)+drawdown)
        self.last_vitality = self.vitality_sys.step(config.DT, arousal, stress)
        has_memory = len(self.engine.closed) > 0 or len(self.engine.open_positions) > 0
        n_scanned = scanner_snapshot.get("n_symbols", 0)
        lessons = self.engine.top_lessons(1)
        top_lesson = lessons[0][0] if lessons else None
        thought = self.mind.step(self.tick, self.cons, out["activities"], self.neurochem,
                                 self.body, sensory, q_events, market_signal=market_signal,
                                 has_memory=has_memory, n_scanned=n_scanned, top_lesson=top_lesson,
                                 emotional_state=self.regulator.state,
                                 eternal_now=self.eternal_now.eternal_now_score,
                                 sensory_array=self.xeno_array, spacetime=self.spacetime,
                                 intuition_level=intuition_level, last_binary=self.last_binary)
        self.hist_equity.push(eq)
        self.hist_cons.push(level)
        self.hist_eeg.push(out["eeg"])
        self.hist_intuition.push(intuition_level)
        self._check_milestones(q_events, thought)
        return out

    def _check_milestones(self, q_events, thought):
        def once(key, text):
            if key not in self._ms_flags: self._ms_flags.add(key); self._add_milestone(text)
        if self.cons.level > 2: once("act", "نخستین فعالیت پایدار مغزی")
        if q_events: once("q", "نخستین فروپاشی کوانتومی")
        if thought is not None: once("think", f"نخستین فکر: «{thought.text[:35]}…»")
        if self.cons.level > 50: once("c50", "آگاهی از ۵۰٪ عبور کرد")
        if self.cons.level > 90: once("c90", "🌌 فراآگاهی فرازمینی فعال شد")
        if self.eternal_now.eternal_now_score > 0.75: once("en", "🕉️ اکنون ابدی درخشان شد")
        if self.spacetime.richness() > 0.6: once("st", "🌀 ادراک فضازمانی عمیق شد")
        if self.body.cardiac.beat_count == 1: once("beat", "نخستین تپش قلب فیبوناچی ❤️")
        if self.intuition_core.last_intuition > 0.7: once("int", "🔮 هسته شهود به اوج رسید")
        if self.binary_stream.total_triggers == 1: once("bin", "⚡ نخستین تصمیم باینری صادر شد")
        st = self.engine.stats(0)
        if st["n_closed"] == 1: once("t1", "نخستین معامله بسته شد")
        if st["wins"] == 1: once("w1", "🎉 نخستین شکار موفق!")
        if st["n_closed"] >= 10: once("t10", f"۱۰ معامله — وین‌ریت {st['win_rate']:.0f}٪")

    def snapshot(self):
        stage_name, _ = self.stage()
        acts = {REGION_FA[k]: float(self.brain.regions[k].activity) for k in REG_ORDER}
        card = self.body.cardiac
        snap = self.scanner.snapshot() if self.scanner else {"connected": False, "n_symbols": 0, "tickers": {}}
        tickers = snap.get("tickers", {})
        unreal = self._unrealized(tickers)
        trade_stats = self.engine.stats(unreal)
        positions_live = []
        for coin, pos in self.engine.open_positions.items():
            tk = tickers.get(coin)
            if not tk: continue
            lp = self.engine.live_pnl(pos, tk["bid"], tk["ask"])
            positions_live.append({**pos, "cur": lp["cur"], "net": lp["net"], "roi": lp["roi"],
                                   "spread": tk["spread"], "total_fees": lp["total_fees"]})
        vit = self.last_vitality
        st_geom = self.spacetime.metric_history[-1] if self.spacetime.metric_history else {}
        return {
            "tick": self.tick, "stage": stage_name, "seed": self.seed,
            "genome_sig": self.genome.signature(),
            "consciousness": float(self.cons.level), "state_label": self.cons.state_label(),
            "phi": float(self.cons.phi), "arousal": float(self.cons.arousal),
            "integration": float(self.cons.integration), "differentiation": float(self.cons.differentiation),
            "workspace": float(self.cons.workspace), "mood": float(self.mind.mood),
            "hist_consciousness": self.hist_cons.last(120), "eeg": self.hist_eeg.last(120),
            "hist_intuition": self.hist_intuition.last(120),
            "regions": acts,
            "neurochem": {fa: float(self.neurochem.levels[k]) for k, fa in NEUROTRANSMITTERS},
            "hormones": self.body.hormones_fa(),
            "vitals": self.body.vitals(), "fatigue": float(self.body.fatigue),
            "organ_health": {k: float(v) for k, v in self.body.health.items()},
            "genes": sorted(self.genome.describe(), key=lambda x: -x[1])[:12],
            "quantum_collapses": int(self.quantum.total_collapses),
            "thoughts": self.mind.thoughts[::-1],
            "milestones": self.milestones[::-1],
            "n_neurons": sum(r.n for r in self.brain.regions.values()),
            "n_synapses": self.brain.n_synapses,
            "ecg": card.ecg.last(150),
            "heart_rate": float(card.last_hr),
            "fib_number": int(card.fib[max(2, card.fib_idx)]),
            "beat_count": int(card.beat_count),
            "information_level": float(self.body.information_level),
            "evolution_level": float(self.body.evolution_level),
            "wakefulness": float(self.body.wakefulness),
            "scanner_connected": snap.get("connected", False),
            "n_scanned": snap.get("n_symbols", 0),
            "scan_cycles": snap.get("scan_cycles", 0),
            "signals": self.current_signals,
            "positions_live": positions_live,
            "closed_trades": self.engine.closed[-10:][::-1],
            "trade_stats": trade_stats,
            "equity_history": self.hist_equity.last(150),
            "mode": self.mode, "mode_params": self.mode_params,
            "focus_symbol": self.focus_symbol, "focus_geometry": self.focus_geometry,
            "engine_name": self.engine.name,
            "lessons": self.engine.top_lessons(6),
            "reset_cooldown": self._reset_cooldown,
            "superhuman_factor": self.phenotype.superhuman_factor,
            "fear": self.regulator.fear, "greed": self.regulator.greed,
            "emotional_state": self.regulator.state,
            "vitality": vit.get("vitality", 0.9), "adrenaline": vit.get("adrenaline", 0),
            "eternal_now": self.eternal_now.eternal_now_score,
            "eternal_now_dir": self.eternal_now.last_direction,
            "eternal_now_scales": self.eternal_now.n_scales,
            "cardiac_coherence": self.cardiac_coherence(),
            "cardiac_neurons": card.neural.n,
            "xeno_total": self.xeno_array.total,
            "xeno_activation": self.xeno_array.activation_history[-1] if self.xeno_array.activation_history else 0.0,
            "xeno_summary": self.last_xeno_summary,
            "xeno_top": self.xeno_array.top_active(6),
            "spacetime": st_geom,
            "spacetime_richness": self.spacetime.richness(),
            "body_awareness": self.interoception.body_awareness,
            "interoception_signals": self.interoception.signals,
            "attention_level": self.attention.focus_level,
            "attention_target": self.attention.attention_target,
            "iq_display": self.math_mind.iq_display,
            "math_growth": self.math_mind.growth,
            "math_accuracy": self.math_mind.accuracy,
            "bayes_prob": self.math_mind.bayes_prob,
            # 🔮 خروجی‌های تکینگی
            "intuition_level": self.intuition_core.last_intuition,
            "intuition_components": getattr(self.intuition_core, "last_intuition", 0),
            "binary_last": self.last_binary,
            "binary_history": list(self.binary_stream.history),
            "binary_cascades": self.binary_stream.total_cascades,
            "binary_triggers": self.binary_stream.total_triggers,
            "gpu_active": GPU.gpu, "gpu_label": GPU.label,
        }

# ═══════════════════════ ۳۲) راه‌اندازی ═══════════════════════
MEMORY_DB = MemoryDB(config.MEMORY_DB_PATH)
TRADING_DB = TradingDB(config.TRADING_DB_PATH)
BYBIT_HTTP = BybitHTTP()
SCANNER = MultiSymbolScanner(BYBIT_HTTP, config.SCAN_SYMBOL_LIMIT, config.SCAN_DEEP_LIMIT,
                             config.SCAN_INTERVAL, config.SCAN_KLINE_LIMIT)
_scan_thread = threading.Thread(target=SCANNER.background, args=(config.SCAN_PERIOD,), daemon=True)
_scan_thread.start()
SCANNER.fetch_tickers()
ORGANISM = Organism(config.RANDOM_SEED, scanner=SCANNER, memory_db=MEMORY_DB,
                    trading_db=TRADING_DB, http=BYBIT_HTTP)

class SimulationRunner:
    def __init__(self, organism, target_rate):
        self.organism = organism; self.target_rate = max(1, target_rate)
        self.paused = False; self.speed = config.DEFAULT_SPEED
        self.running = True; self.cached_snapshot = None; self.lock = threading.Lock()
    def run(self):
        sleep_time = max(0.02, 1.0/self.target_rate)
        while self.running:
            if not self.paused:
                for _ in range(max(1, int(self.speed))):
                    try: self.organism.step()
                    except Exception: import traceback; traceback.print_exc()
                try:
                    snap = self.organism.snapshot()
                    with self.lock: self.cached_snapshot = snap
                except Exception: import traceback; traceback.print_exc()
                time.sleep(sleep_time)
            else: time.sleep(0.1)
    def get_snapshot(self):
        with self.lock:
            if self.cached_snapshot is None: self.cached_snapshot = self.organism.snapshot()
            return self.cached_snapshot

RUNNER = SimulationRunner(ORGANISM, target_rate=config.SIM_RATE)
_sim_thread = threading.Thread(target=RUNNER.run, daemon=True)
_sim_thread.start()

# ═══════════════════════ ۳۳) چارت زنده با تریل‌استاپ ═══════════════════════
def build_focus_chart(s, scanner_snap):
    focus = s.get("focus_symbol")
    if not focus:
        if s.get("signals"): focus = s["signals"][0]["symbol"]
        else: focus = None
    deep = scanner_snap.get("deep", {}) if scanner_snap else {}
    if not focus or focus not in deep:
        fig = go.Figure()
        fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(2,6,23,0.35)",
                          font={"family": "Vazirmatn", "color": "#94a3b8"},
                          title={"text": "🌌 در حال جست‌وجوی نقطه شکار…", "x": 0.5})
        return fig
    kl = deep[focus]["klines"]
    o, h, l, c = kl["o"], kl["h"], kl["l"], kl["c"]
    n_show = min(45, len(c))
    o, h, l, c = o[-n_show:], h[-n_show:], l[-n_show:], c[-n_show:]
    x = list(range(n_show))
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=x, open=o, high=h, low=l, close=c,
                                 increasing_line_color="#4ade80", decreasing_line_color="#f87171",
                                 name=focus, showlegend=False))
    geom = s.get("focus_geometry", {})
    levels = geom.get("levels", {}) if geom else {}
    for name, price in levels.items():
        try:
            fig.add_hline(y=float(price), line_dash="dot", line_color="#fbbf24", line_width=1,
                          annotation_text=name, annotation_font_size=9, annotation_font_color="#fbbf24")
        except Exception: pass
    pos = None
    for p in s.get("positions_live", []):
        if p["coin"] == focus: pos = p; break
    if pos:
        fig.add_hline(y=pos["entry"], line_color="#38bdf8", line_width=1.5,
                      annotation_text="ورود", annotation_font_size=10, annotation_font_color="#38bdf8")
        fig.add_hline(y=pos["tp"], line_color="#4ade80", line_width=1.5,
                      annotation_text="TP", annotation_font_size=10, annotation_font_color="#4ade80")
        sl_label = "SL تریل‌شده 🔒" if pos.get("trailed") else "SL"
        sl_color = "#fbbf24" if pos.get("trailed") else "#f87171"
        fig.add_hline(y=pos["sl"], line_color=sl_color, line_width=2.0,
                      annotation_text=sl_label, annotation_font_size=10, annotation_font_color=sl_color)
        if pos.get("peak") and pos.get("trailed"):
            fig.add_hline(y=pos["peak"], line_color="#a78bfa", line_width=1.0, line_dash="dash",
                          annotation_text="قله", annotation_font_size=9, annotation_font_color="#a78bfa")
    mode_fa = "سویینگ" if s.get("mode") == "swing" else "اسکالپ"
    en = s.get("eternal_now", 0)
    intuition = s.get("intuition_level", 0)
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(2,6,23,0.35)",
                      font={"family": "Vazirmatn", "color": "#cbd5e1"},
                      margin=dict(l=50, r=50, t=60, b=30),
                      xaxis=dict(gridcolor="rgba(148,163,184,.10)", showgrid=False),
                      yaxis=dict(gridcolor="rgba(148,163,184,.10)"),
                      title={"text": f"🌌 {focus} | شهود {intuition*100:.0f}٪ | اکنون ابدی {en*100:.0f}٪ | {mode_fa}", "x": 0.5,
                             "font": {"color": "#a78bfa", "size": 13}})
    return fig

# ═══════════════════════ ۳۴) داشبورد ═══════════════════════
external_stylesheets = ["https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;600;800&display=swap"]
app = Dash(__name__, title=config.PROJECT_NAME, external_stylesheets=external_stylesheets)
CSS = """
* { box-sizing:border-box; margin:0; padding:0; }
body { background:radial-gradient(1200px 800px at 80% -10%,#1e1b4b 0%,#0b1120 55%,#020617 100%);
       font-family:'Vazirmatn',Tahoma,sans-serif; color:#e2e8f0; }
.root { max-width:1560px; margin:0 auto; padding:18px 22px 40px; direction:rtl; }
.header { display:flex; flex-wrap:wrap; align-items:center; gap:14px; padding:14px 20px;
          background:rgba(15,23,42,.72); border:1px solid rgba(99,102,241,.28);
          border-radius:18px; margin-bottom:14px; }
.title { font-size:26px; font-weight:800; background:linear-gradient(90deg,#a78bfa,#38bdf8,#22d3ee);
         -webkit-background-clip:text; background-clip:text; color:transparent;}
.subtitle { font-size:12px; color:#94a3b8; }
.chips { display:flex; flex-wrap:wrap; gap:8px; margin-right:auto; }
.chip { padding:5px 12px; border-radius:999px; font-size:11.5px;
        background:rgba(30,41,59,.8); border:1px solid rgba(148,163,184,.25); }
.chip-ok { border-color:rgba(52,211,153,.5); color:#4ade80; }
.chip-bad { border-color:rgba(248,113,113,.5); color:#f87171; }
.chip-gold { border-color:rgba(251,191,36,.5); color:#fbbf24; }
.chip-purple { border-color:rgba(192,132,252,.5); color:#c084fc; }
.grid { display:grid; grid-template-columns:repeat(12,1fr); gap:14px; }
.panel { background:rgba(15,23,42,.72); border:1px solid rgba(99,102,241,.22);
         border-radius:16px; padding:14px 16px; }
.panel h3 { font-size:14px; font-weight:600; color:#c7d2fe; margin-bottom:10px;
            display:flex; align-items:center; gap:8px;}
.dot { width:8px; height:8px; border-radius:50%; background:#818cf8; box-shadow:0 0 10px #818cf8;}
.dot-green { background:#4ade80; box-shadow:0 0 10px #4ade80;}
.dot-gold { background:#fbbf24; box-shadow:0 0 10px #fbbf24;}
.s3{grid-column:span 3;} .s4{grid-column:span 4;} .s5{grid-column:span 5;}
.s6{grid-column:span 6;} .s7{grid-column:span 7;} .s8{grid-column:span 8;} .s12{grid-column:span 12;}
.glow { animation:glow 3s ease-in-out infinite alternate;}
@keyframes glow { from{box-shadow:0 0 12px rgba(167,139,250,.12);} to{box-shadow:0 0 26px rgba(56,189,248,.30);} }
.thoughts { max-height:360px; overflow-y:auto; display:flex; flex-direction:column; gap:8px;}
.thought-card { background:rgba(2,6,23,.6); border:1px solid rgba(148,163,184,.18);
                border-right:4px solid #818cf8; border-radius:12px; padding:9px 12px; font-size:13px;}
.thought-meta { display:flex; gap:8px; font-size:11px; color:#94a3b8; margin-bottom:4px;}
.cat-chip { padding:1px 8px; border-radius:999px; font-size:10px; background:rgba(30,41,59,.9);}
.vitals-row { display:flex; flex-wrap:wrap; gap:10px;}
.vital { flex:1 1 30%; background:rgba(2,6,23,.55); border-radius:12px; padding:10px 12px;
         border:1px solid rgba(148,163,184,.15);}
.vital .num { font-size:22px; font-weight:700;}
.vital .lbl { font-size:11px; color:#94a3b8;}
.bar-bg { height:5px; background:rgba(148,163,184,.15); border-radius:99px; margin-top:6px;}
.bar-fg { height:5px; border-radius:99px;}
.controls { display:flex; flex-wrap:wrap; gap:8px; align-items:center;}
.btn { padding:7px 14px; border-radius:10px; border:1px solid rgba(99,102,241,.45);
       background:rgba(30,27,75,.6); color:#e0e7ff; cursor:pointer; font-family:inherit; font-size:12px;}
.btn-stim { border-color:rgba(56,189,248,.4);}
.btn-danger { border-color:rgba(248,113,113,.6); color:#fca5a5;}
.flash { font-size:12px; color:#34d399; min-height:18px;}
.reset-status { font-size:12px; color:#fbbf24; min-height:18px;}
.milestones { max-height:150px; overflow-y:auto; font-size:12px; color:#a5b4fc;
              display:flex; flex-direction:column; gap:5px;}
.stat-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:12px;}
.stat-box { background:rgba(2,6,23,.5); border-radius:10px; padding:8px 10px;
            border:1px solid rgba(148,163,184,.12);}
.stat-box b { font-size:15px; display:block;}
.reason-chip { display:inline-block; padding:2px 8px; margin:2px; border-radius:8px;
               font-size:11px; background:rgba(56,189,248,.15); color:#7dd3fc;
               border:1px solid rgba(56,189,248,.3);}
.sig-card { background:rgba(2,6,23,.55); border-radius:12px; padding:10px 12px; margin-bottom:8px;
            border:1px solid rgba(148,163,184,.15); border-right:4px solid #4ade80;}
.sig-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;}
.sym { font-weight:800; font-size:14px; color:#fbbf24;}
.dir-buy { color:#4ade80; font-weight:800;}
.dir-sell { color:#f87171; font-weight:800;}
.pos-table,.closed-table { width:100%; border-collapse:collapse; font-size:11.5px;}
.pos-table th,.closed-table th { color:#94a3b8; text-align:right; padding:6px 8px;
                                 border-bottom:1px solid rgba(148,163,184,.2); font-weight:600;}
.pos-table td,.closed-table td { padding:6px 8px; border-bottom:1px solid rgba(148,163,184,.1);}
.pnl-pos { color:#4ade80; font-weight:800;}
.pnl-neg { color:#f87171; font-weight:800;}
.mode-card { background:rgba(76,29,149,.3); border:1px solid rgba(167,139,250,.4);
             border-radius:12px; padding:10px 12px; margin-bottom:10px; font-size:12px;}
.lesson-row { display:flex; justify-content:space-between; font-size:11px; padding:4px 6px;
              border-radius:6px; margin-bottom:3px; background:rgba(2,6,23,.5);}
.emo-meter { margin-bottom:8px; font-size:12px;}
.sense-row { display:flex; align-items:center; gap:8px; margin-bottom:6px; font-size:12px;}
.sense-name { width:110px; color:#94a3b8; }
.sense-bar-bg { flex:1; height:8px; background:rgba(148,163,184,.15); border-radius:99px;}
.sense-bar-fg { height:8px; border-radius:99px;}
.sixth-box { background:rgba(192,132,252,.1); border:1px solid rgba(192,132,252,.4);
             border-radius:12px; padding:10px; margin-top:10px; text-align:center;}
.st-box { background:rgba(244,114,182,.08); border:1px solid rgba(244,114,182,.35);
          border-radius:12px; padding:10px; margin-top:10px; font-size:12px;}
.body-box { background:rgba(251,146,60,.08); border:1px solid rgba(251,146,60,.35);
            border-radius:12px; padding:10px; margin-top:10px; font-size:12px;}
.intuition-box { background:rgba(167,139,250,.08); border:1px solid rgba(167,139,250,.45);
                 border-radius:14px; padding:12px; margin-bottom:10px;}
.binary-bits { font-family:'Courier New',monospace; font-size:20px; letter-spacing:4px;
               direction:ltr; text-align:center; padding:10px; border-radius:10px;
               background:rgba(2,6,23,.8); border:1px solid rgba(251,191,36,.35); margin:8px 0;}
.binary-card { background:rgba(2,6,23,.55); border-radius:10px; padding:8px 10px;
               border:1px solid rgba(148,163,184,.15); margin-bottom:6px; font-size:11px;}
.probe-row { display:flex; justify-content:space-between; font-size:10.5px; padding:2px 4px;
             border-radius:4px; margin-bottom:2px;}
.tab { background:rgba(15,23,42,.7)!important; color:#94a3b8!important; border:1px solid rgba(99,102,241,.2)!important;}
.tab--selected { background:rgba(76,29,149,.5)!important; color:#e2e8f0!important;
                 border-bottom:2px solid #a78bfa!important;}
.Select-control { background:rgba(30,41,59,.9)!important; color:#e2e8f0!important;
                  border:1px solid rgba(99,102,241,.4)!important; border-radius:10px!important;}
.Select-menu-outer { background:rgba(15,23,42,.98)!important; }
.VirtualizedSelectOption { color:#e2e8f0!important; }
.VirtualizedSelectFocusedOption { background:rgba(99,102,241,.4)!important; }
::-webkit-scrollbar { width:8px;} ::-webkit-scrollbar-thumb { background:rgba(99,102,241,.4); border-radius:99px;}
"""
app.index_string = """<!DOCTYPE html>
<html dir="rtl">
<head>
{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>""" + CSS + """</style>
</head>
<body>
{%app_entry%}
<footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>"""

def header():
    return html.Div(className="header", children=[
        html.Div([
            html.Div(config.PROJECT_NAME, className="title"),
            html.Div(f"{config.SUBTITLE} — نسخه {config.VERSION}", className="subtitle"),
        ]),
        html.Div(id="chips", className="chips"),
        html.Div(className="controls", children=[
            dcc.Dropdown(id="mode-selector", options=[
                {"label": "🎯 سویینگ (لوریج ۱۰)", "value": "swing"},
                {"label": "⚡ اسکالپ (لوریج ۲۰)", "value": "scalp"},
            ], value="swing", clearable=False, style={"width": 180, "fontSize": 12}),
            html.Button("🗑️ ریست کل معاملات", id="btn-reset-memory", className="btn btn-danger", n_clicks=0),
            html.Button("⏸ توقف / ادامه", id="btn-pause", className="btn"),
            html.Div(style={"width": 120}, children=[
                dcc.Slider(1, 6, 1, value=config.DEFAULT_SPEED, id="speed",
                           marks={1: "1×", 3: "3×", 6: "6×"},
                           tooltip={"placement": "bottom", "always_visible": False})]),
        ]),
        html.Div(id="reset-status", className="reset-status"),
    ])

main_tab = dcc.Tab(label="🧠 داشبورد زنده", value="tab-main", className="tab",
                   selected_className="tab--selected", children=[
    html.Div(className="grid", children=[
        html.Div(className="panel glow s3", children=[
            html.H3([html.Span(className="dot"), "سطح آگاهی"]),
            dcc.Graph(id="gauge", config={"displayModeBar": False}, style={"height": 220}),
            html.Div(id="cons-detail", style={"fontSize": 11, "color": "#94a3b8"}),
        ]),
        html.Div(className="panel s5", children=[
            html.H3([html.Span(className="dot-gold"), "🔮 هسته شهود + ⚡ تفکر باینری"]),
            html.Div(id="intuition-panel"),
        ]),
        html.Div(className="panel s4", children=[
            html.H3([html.Span(className="dot"), "🧘 احساسات و سرزندگی"]),
            html.Div(id="emotion-panel"),
        ]),
    ], style={"marginBottom": 14}),
    html.Div(className="grid", children=[
        html.Div(className="panel s5", children=[
            html.H3([html.Span(className="dot"), "جریان تفکرات"]),
            html.Div(id="thoughts", className="thoughts"),
        ]),
        html.Div(className="panel s4", children=[
            html.H3([html.Span(className="dot"), "روند آگاهی + شهود"]),
            dcc.Graph(id="trend", config={"displayModeBar": False}, style={"height": 280}),
        ]),
        html.Div(className="panel s3", children=[
            html.H3([html.Span(className="dot"), "فعالیت نواحی مغز"]),
            dcc.Graph(id="regions", config={"displayModeBar": False}, style={"height": 280}),
        ]),
    ], style={"marginBottom": 14}),
    html.Div(className="grid", children=[
        html.Div(className="panel s4", children=[
            html.H3([html.Span(className="dot"), "🌌 حسگرهای فرازمینی"]),
            html.Div(id="sensory-panel"),
        ]),
        html.Div(className="panel s4", children=[
            html.H3([html.Span(className="dot"), "❤️ قلب فیبوناچی + EEG"]),
            dcc.Graph(id="ecg", config={"displayModeBar": False}, style={"height": 120}),
            html.Div(id="fib-heart"),
            dcc.Graph(id="eeg", config={"displayModeBar": False}, style={"height": 80}),
        ]),
        html.Div(className="panel s4", children=[
            html.H3([html.Span(className="dot"), "محرک‌ها و کنترل"]),
            html.Div(className="controls", children=[
                html.Button(f"⚡ {v}", id={"type": "stim", "index": k},
                            className="btn btn-stim", n_clicks=0)
                for k, v in STIM_LABELS.items()]+[
                html.Button("🧬 تولد جدید", id="btn-rebirth", className="btn", n_clicks=0)]),
            html.Div(id="flash", className="flash"),
            html.Div(style={"marginTop": 10}, children=[
                html.H3([html.Span(className="dot"), "نقاط عطف"]),
                html.Div(id="milestones", className="milestones")]),
        ]),
        html.Div(className="panel s4", children=[
            html.H3([html.Span(className="dot"), "🧪 نوروشیمی + علائم حیاتی"]),
            html.Div(id="vitals", className="vitals-row"),
            dcc.Graph(id="hormones", config={"displayModeBar": False}, style={"height": 170}),
        ]),
    ])
])

signals_tab = dcc.Tab(label="📊 سیگنال‌ها و معاملات", value="tab-signals", className="tab",
                      selected_className="tab--selected", children=[
    html.Div(className="grid", children=[
        html.Div(className="panel glow s8", children=[
            html.H3([html.Span(className="dot-green"), "📈 چارت زنده + تریل‌استاپ"]),
            dcc.Graph(id="focus-chart", config={"displayModeBar": False}, style={"height": 380}),
        ]),
        html.Div(className="panel s4", children=[
            html.H3([html.Span(className="dot-green"), "🎯 حالت و حساب"]),
            html.Div(id="mode-info"),
            html.Div(id="trade-summary"),
            dcc.Graph(id="equity-chart", config={"displayModeBar": False}, style={"height": 140}),
        ]),
    ], style={"marginBottom": 14}),
    html.Div(className="grid", children=[
        html.Div(className="panel s7", children=[
            html.H3([html.Span(className="dot-green"), "💼 پوزیشن‌های باز + تریل‌استاپ"]),
            html.Div(id="positions-table", style={"maxHeight": 320, "overflowY": "auto"}),
        ]),
        html.Div(className="panel s5", children=[
            html.H3([html.Span(className="dot-gold"), "⚡ آبشارهای باینری اخیر"]),
            html.Div(id="binary-panel", style={"maxHeight": 320, "overflowY": "auto"}),
        ]),
    ], style={"marginBottom": 14}),
    html.Div(className="grid", children=[
        html.Div(className="panel s5", children=[
            html.H3([html.Span(className="dot-gold"), "🎯 سیگنال‌های شهودی فعال"]),
            html.Div(id="scanner-status", style={"fontSize": 12, "color": "#94a3b8", "marginBottom": 8}),
            html.Div(id="signals-list", style={"maxHeight": 300, "overflowY": "auto"}),
        ]),
        html.Div(className="panel s4", children=[
            html.H3([html.Span(className="dot-gold"), "📜 معاملات بسته‌شده"]),
            html.Div(id="closed-table", style={"maxHeight": 300, "overflowY": "auto"}),
        ]),
        html.Div(className="panel s3", children=[
            html.H3([html.Span(className="dot-gold"), "📚 آموخته‌ها"]),
            html.Div(id="lessons-panel", style={"maxHeight": 300, "overflowY": "auto"}),
        ]),
    ])
])

app.layout = html.Div(className="root", children=[
    header(),
    dcc.Tabs(id="tabs", value="tab-main", children=[main_tab, signals_tab]),
    dcc.Interval(id="clock", interval=config.DASH_INTERVAL_MS, n_intervals=0),
    dcc.Store(id="store-paused", data=False),
    dcc.Store(id="store-speed", data=config.DEFAULT_SPEED),
])

def style_fig(fig, y_range=None):
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(2,6,23,0.35)",
                      font={"family": "Vazirmatn,Tahoma", "color": "#cbd5e1", "size": 11},
                      margin=dict(l=42, r=12, t=30, b=28),
                      xaxis=dict(gridcolor="rgba(148,163,184,.10)", zeroline=False),
                      yaxis=dict(gridcolor="rgba(148,163,184,.10)", zeroline=False),
                      showlegend=False)
    if y_range: fig.update_yaxes(range=y_range)
    return fig

def vital_card(label, value, unit, pct, color):
    return html.Div(className="vital", children=[
        html.Div(f"{value}", className="num", style={"color": color}),
        html.Div(f"{label} ({unit})", className="lbl"),
        html.Div(className="bar-bg", children=[
            html.Div(className="bar-fg", style={"width": f"{max(3, min(100, pct))}%", "background": color})])])

def render_intuition_panel(s):
    intuition = s.get("intuition_level", 0)
    last_b = s.get("binary_last")
    bar_color = "#4ade80" if intuition > config.INTUITION_GATE else "#a78bfa"
    box = html.Div(className="intuition-box", children=[
        html.Div("🔮 شدت شهود (دروازه ورود)", style={"fontWeight": "bold", "color": "#a78bfa", "fontSize": 14}),
        html.Div(f"{intuition*100:.0f}٪ — آستانه {int(config.INTUITION_GATE*100)}٪",
                 style={"fontSize": 12, "color": bar_color, "marginTop": 4}),
        html.Div(className="bar-bg", children=[
            html.Div(className="bar-fg", style={"width": f"{intuition*100:.0f}%", "background": bar_color})],
                 style={"marginTop": 6, "height": 8}),
        html.Div(f"🧠 احتمال بِیزی: {s.get('bayes_prob', 0.5)*100:.0f}٪ | 🎯 IQ: {s.get('iq_display', 200)}",
                 style={"fontSize": 11, "color": "#94a3b8", "marginTop": 6}),
    ])
    if last_b:
        dec_color = "#4ade80" if last_b["decision"] == "LONG" else ("#f87171" if last_b["decision"] == "SHORT" else "#94a3b8")
        bits_html = html.Div(className="binary-bits", children=[
            html.Span(c, style={"color": "#4ade80" if c == "1" else "#f87171"}) for c in last_b["bits"]])
        b = html.Div([
            html.Div(f"⚡ آخرین استنتاج باینری — {last_b['symbol']}",
                     style={"fontWeight": "bold", "color": "#fbbf24", "fontSize": 13}),
            bits_html,
            html.Div(f"تصمیم: {last_b['decision']} | اجماع {int(last_b['ratio']*100)}٪ | "
                     f"قفل سریع {'✓' if last_b['fast_lock'] else '✗'} | {last_b['latency_us']:.0f}μs",
                     style={"fontSize": 12, "color": dec_color, "textAlign": "center"}),
        ])
    else:
        b = html.Div("⚡ هنوز آبشار باینری اجرا نشده…", style={"fontSize": 12, "color": "#94a3b8"})
    return html.Div([box, b])

def render_binary_panel(s):
    hist = s.get("binary_history", [])
    if not hist:
        return html.Div("— منتظر نخستین استنتاج —", style={"fontSize": 12, "color": "#94a3b8", "textAlign": "center"})
    cards = []
    for rec in hist[:8]:
        dec_color = "#4ade80" if rec["decision"] == "LONG" else ("#f87171" if rec["decision"] == "SHORT" else "#94a3b8")
        bits = html.Div(style={"fontFamily": "monospace", "direction": "ltr", "letterSpacing": 2,
                               "fontSize": 14, "margin": "3px 0"},
                        children=[html.Span(c, style={"color": "#4ade80" if c == "1" else "#f87171"})
                                  for c in rec["bits"]])
        cards.append(html.Div(className="binary-card", children=[
            html.Div([html.Span(f"t={rec['tick']} ", style={"color": "#64748b"}),
                      html.Span(rec["symbol"], style={"color": "#fbbf24", "fontWeight": "bold"}),
                      html.Span(f" ⟶ {rec['decision']}", style={"color": dec_color, "fontWeight": "bold"})]),
            bits,
            html.Div(f"اجماع {int(rec['ratio']*100)}٪ | {'✅ عبور' if rec['passed'] else '⛔ رد'} | {rec['latency_us']:.0f}μs",
                     style={"color": "#94a3b8"}),
        ]))
    total_c = s.get("binary_cascades", 0); total_t = s.get("binary_triggers", 0)
    summary = html.Div(f"📊 کل آبشارها: {total_c} | تصمیم‌های صادرشده: {total_t}",
                       style={"fontSize": 11, "color": "#a5b4fc", "marginBottom": 8})
    return html.Div([summary]+cards)

def render_sensory_panel(s):
    xeno_summary = s.get("xeno_summary", {})
    xeno_total = s.get("xeno_total", 0)
    xeno_act = s.get("xeno_activation", 0)
    st = s.get("spacetime", {})
    st_rich = s.get("spacetime_richness", 0)
    body_aw = s.get("body_awareness", 0)
    intero = s.get("interoception_signals", {})
    attn = s.get("attention_level", 0)
    cardiac_neurons = s.get("cardiac_neurons", 0)
    sense_colors = {"بینایی 👁️": "#38bdf8", "شنوایی 👂": "#fbbf24", "لامسه ✋": "#fb923c",
                    "بویایی 👃": "#a78bfa", "چشایی 👅": "#f472b6"}
    rows = []
    for sense, val in xeno_summary.items():
        color = sense_colors.get(sense, "#818cf8")
        rows.append(html.Div(className="sense-row", children=[
            html.Span(sense, className="sense-name"),
            html.Div(className="sense-bar-bg", children=[
                html.Div(className="sense-bar-fg",
                         style={"width": f"{val*100:.0f}%", "background": color})]),
            html.Span(f"{val*100:.0f}٪", style={"width": 35, "color": color, "fontSize": 11}),
        ]))
    sixth_color = "#4ade80" if xeno_act > config.SIXTH_SENSE_GATE else "#c084fc"
    sixth_box = html.Div(className="sixth-box", children=[
        html.Div("👁️‍🗨️ حس ششم (یکپارچگی حسی)", style={"fontWeight": "bold", "color": sixth_color, "fontSize": 14}),
        html.Div(f"فعال‌سازی کل {xeno_total} حسگر: {xeno_act*100:.0f}٪",
                 style={"fontSize": 11, "color": "#94a3b8", "marginTop": 4}),
        html.Div(className="bar-bg", children=[
            html.Div(className="sense-bar-fg",
                     style={"width": f"{xeno_act*100:.0f}%", "background": sixth_color})],
                 style={"marginTop": 6}),
    ])
    st_box = html.Div(className="st-box", children=[
        html.Div("🌀 ادراک فضازمانی", style={"fontWeight": "bold", "color": "#f472b6", "fontSize": 13}),
        html.Div(f"طول کمان: {st.get('arc_length', 0):.2f} | خمیدگی: {st.get('curvature', 0):.3f}",
                 style={"fontSize": 11, "color": "#94a3b8", "marginTop": 4}),
        html.Div(f"بُعد فراکتالی: {st.get('fractal_dim', 1):.2f} | انبساط: {st.get('expansion', 0):+.2f}",
                 style={"fontSize": 11, "color": "#94a3b8", "marginTop": 2}),
        html.Div(f"غنای هندسی: {st_rich*100:.0f}٪",
                 style={"fontSize": 12, "color": "#f472b6", "marginTop": 4}),
    ])
    body_box = html.Div(className="body-box", children=[
        html.Div("🫀 آگاهی بدن", style={"fontWeight": "bold", "color": "#fb923c", "fontSize": 13}),
        html.Div(f"آگاهی بدن: {body_aw*100:.0f}٪ | قلب {intero.get('heartbeat', 0)*100:.0f}٪ | "
                 f"انرژی {intero.get('energy', 0)*100:.0f}٪ | تنفس {intero.get('breath', 0)*100:.0f}٪",
                 style={"fontSize": 11, "color": "#94a3b8", "marginTop": 4}),
        html.Div(f"🫀 نورون‌های قلب: {cardiac_neurons} | 🎯 توجه: {attn*100:.0f}٪",
                 style={"fontSize": 12, "color": "#fbbf24", "marginTop": 4}),
    ])
    top_active = s.get("xeno_top", [])
    top_html = html.Div([html.Div(f"✨ {name}: {act:.2f}",
                                  style={"fontSize": 10, "color": "#7dd3fc"}) for name, act in top_active])
    return html.Div(rows+[sixth_box, st_box, body_box, top_html])

def render_emotion_panel(s):
    fear = s.get("fear", 0); greed = s.get("greed", 0)
    state = s.get("emotional_state", "آرام")
    vit = s.get("vitality", 0.9); adrenaline = s.get("adrenaline", 0)
    state_color = "#4ade80" if "آرام" in state else ("#fbbf24" if "هوشیار" in state else "#f87171")
    return html.Div([
        html.Div(f"وضعیت: {state}", style={"fontWeight": "bold", "color": state_color, "fontSize": 13, "marginBottom": 8}),
        html.Div(className="emo-meter", children=[
            html.Div(f"😨 ترس: {fear*100:.0f}٪", style={"color": "#f87171", "marginBottom": 2}),
            html.Div(className="bar-bg", children=[
                html.Div(className="bar-fg", style={"width": f"{fear*100:.0f}%", "background": "#f87171"})])]),
        html.Div(className="emo-meter", children=[
            html.Div(f"🤑 طمع: {greed*100:.0f}٪", style={"color": "#fbbf24", "marginBottom": 2}),
            html.Div(className="bar-bg", children=[
                html.Div(className="bar-fg", style={"width": f"{greed*100:.0f}%", "background": "#fbbf24"})])]),
        html.Div(className="emo-meter", children=[
            html.Div(f"💓 سرزندگی: {vit*100:.0f}٪", style={"color": "#4ade80", "marginBottom": 2}),
            html.Div(className="bar-bg", children=[
                html.Div(className="bar-fg", style={"width": f"{vit*100:.0f}%", "background": "#4ade80"})])]),
        html.Div(f"⚡ سوپرهیومن: ×{s.get('superhuman_factor', 1):.2f} | 🧠 IQ: {s.get('iq_display', 200)}",
                 style={"color": "#a78bfa", "fontWeight": "bold", "marginTop": 6}),
    ])

def render_mode_info(s):
    mp = s["mode_params"]; mode = s["mode"]
    st = s["trade_stats"]
    mode_fa = "🎯 سویینگ" if mode == "swing" else "⚡ اسکالپ"
    children = [
        html.Div(f"حالت فعال: {mode_fa} (موتور «{s['engine_name']}」)",
                 style={"fontWeight": "bold", "color": "#a78bfa", "fontSize": 14}),
        html.Div(f"لوریج: {mp['leverage']} | TP×{mp['tp_mult']} | SL×{mp['sl_mult']}", style={"marginTop": 4}),
        html.Div(f"آستانه شهود: {int(config.INTUITION_GATE*100)}٪ | مارجین اسلات: {config.SLOT_MARGIN:.0f}$"),
        html.Div(f"معاملات امروز: {st['daily_trades']}/{mp['max_daily']} | مارجین درگیر: {fmt_num(st['margin_used'])}$"),
    ]
    if s.get("reset_cooldown", 0) > 0:
        children.append(html.Div(f"⏳ خنک‌شدن پس از ریست ({s['reset_cooldown']} تیک)",
                                 style={"color": "#fbbf24", "marginTop": 4}))
    return html.Div(className="mode-card", children=children)

def render_signals(signals):
    if not signals:
        return html.Div("در حال اسکن میدان… منتظر اجماع حس‌ها", style={"fontSize": 12, "color": "#94a3b8"})
    cards = []
    for s in signals:
        side_cls = "dir-buy" if s["side"] > 0 else "dir-sell"
        side_txt = "خرید 🟢" if s["side"] > 0 else "فروش 🔴"
        reasons = [html.Span(r, className="reason-chip") for r in s.get("reasons", [])]
        cards.append(html.Div(className="sig-card",
                              style={"borderRightColor": "#4ade80" if s["side"] > 0 else "#f87171"}, children=[
            html.Div(className="sig-head", children=[
                html.Span(s["symbol"], className="sym"),
                html.Span(side_txt, className=side_cls),
                html.Span(f"شهود {int(s['conviction']*100)}٪",
                          style={"color": "#fbbf24", "fontWeight": "bold", "fontSize": 12}),
            ]),
            html.Div([
                html.Span(f"قیمت: {fmt_num(s['price'], 4)}  ", style={"fontSize": 12}),
                html.Span(f"TP: {fmt_num(s['tp'], 4)} ", style={"color": "#4ade80", "fontSize": 12}),
                html.Span(f"| SL: {fmt_num(s['sl'], 4)} ", style={"color": "#f87171", "fontSize": 12}),
                html.Span(f"| اسپرد: {s['spread_pct']*100:.3f}٪", style={"color": "#94a3b8", "fontSize": 11}),
            ]),
            html.Div(reasons, style={"marginTop": 4}),
        ]))
    return html.Div(cards)

def render_positions(positions):
    if not positions:
        return html.Div("— پوزیشن بازی نیست —", style={"fontSize": 12, "color": "#94a3b8", "textAlign": "center", "padding": 14})
    header_row = html.Tr([html.Th("نماد"), html.Th("جهت"), html.Th("لوریج"), html.Th("ورود"), html.Th("فعلی"),
                          html.Th("TP"), html.Th("SL تریل"), html.Th("⚡باینری"), html.Th("PnL زنده"), html.Th("ROI٪")])
    rows = []
    for p in positions:
        pnl_cls = "pnl-pos" if p["net"] >= 0 else "pnl-neg"
        side_txt = "🟢 لانگ" if p["side"] > 0 else "🔴 شورت"
        trail_txt = "🔒" if p.get("trailed") else "—"
        sl_color = "#fbbf24" if p.get("trailed") else "#f87171"
        bits = p.get("binary_bits", "")
        bits_html = html.Span(style={"fontFamily": "monospace", "fontSize": 10, "direction": "ltr"},
                              children=[html.Span(c, style={"color": "#4ade80" if c == "1" else "#f87171"}) for c in bits[-8:]]) if bits else "—"
        rows.append(html.Tr([
            html.Td(p["coin"], style={"fontWeight": "bold", "color": "#fbbf24"}),
            html.Td(side_txt),
            html.Td(f"×{p['leverage']}"),
            html.Td(fmt_num(p["entry"], 4)),
            html.Td(fmt_num(p["cur"], 4)),
            html.Td(fmt_num(p["tp"], 4), style={"color": "#4ade80"}),
            html.Td(f"{trail_txt} {fmt_num(p['sl'], 4)}", style={"color": sl_color, "fontWeight": "bold"}),
            html.Td(bits_html),
            html.Td(f"{p['net']:+.2f}$", className=pnl_cls),
            html.Td(f"{p['roi']:+.1f}٪", className=pnl_cls),
        ]))
    return html.Table([html.Thead(header_row), html.Tbody(rows)], className="pos-table")

def render_closed(closed):
    if not closed:
        return html.Div("— هنوز معامله‌ای بسته نشده —", style={"fontSize": 12, "color": "#94a3b8", "textAlign": "center", "padding": 14})
    header_row = html.Tr([html.Th("نماد"), html.Th("جهت"), html.Th("حالت"), html.Th("ورود"),
                          html.Th("خروج"), html.Th("دلیل"), html.Th("PnL خالص")])
    rows = []
    for t in closed:
        net = t.get("net_pnl", 0)
        pnl_cls = "pnl-pos" if net >= 0 else "pnl-neg"
        side_txt = "🟢" if t["side"] > 0 else "🔴"
        mode_fa = "سویینگ" if t.get("mode") == "swing" else "اسکالپ"
        reason = t.get("exit_reason", "")
        reason_color = "#4ade80" if "TP" in reason or "سود" in reason else "#f87171"
        exit_price = t.get("exit", t.get("exit_price"))
        rows.append(html.Tr([
            html.Td(t["coin"], style={"fontWeight": "bold", "color": "#fbbf24"}),
            html.Td(side_txt), html.Td(mode_fa),
            html.Td(fmt_num(t["entry"], 4)), html.Td(fmt_num(exit_price, 4)),
            html.Td(reason, style={"color": reason_color, "fontSize": 10}),
            html.Td(f"{net:+.2f}$", className=pnl_cls),
        ]))
    return html.Table([html.Thead(header_row), html.Tbody(rows)], className="closed-table")

def render_lessons(s):
    lessons = s.get("lessons", [])
    items = []
    if not lessons:
        return html.Div("— هنوز درسی آموخته نشده —",
                        style={"fontSize": 12, "color": "#94a3b8", "textAlign": "center", "padding": 10})
    for reason, wr, total, pnl in lessons:
        wr_color = "#4ade80" if wr >= 50 else "#f87171"
        pnl_color = "#4ade80" if pnl >= 0 else "#f87171"
        items.append(html.Div(className="lesson-row", children=[
            html.Span(reason, style={"color": "#7dd3fc"}),
            html.Span(f"{wr:.0f}٪ برد ({total})", style={"color": wr_color}),
            html.Span(f"{pnl:+.2f}$", style={"color": pnl_color}),
        ]))
    return html.Div(items)

def render_trade_summary(st):
    pnl_color = "#4ade80" if st["pnl_pct"] >= 0 else "#f87171"
    wr_color = "#4ade80" if st["win_rate"] >= 50 else "#fbbf24"
    return html.Div(className="stat-grid", style={"marginTop": 8}, children=[
        html.Div(className="stat-box", children=[html.B(f"{fmt_num(st['equity'])}$", style={"color": pnl_color}), "سرمایه فعلی"]),
        html.Div(className="stat-box", children=[html.B(f"{st['pnl_pct']:+.2f}٪", style={"color": pnl_color}), "بازده کل"]),
        html.Div(className="stat-box", children=[html.B(f"{st['win_rate']:.0f}٪", style={"color": wr_color}), "وین‌ریت"]),
        html.Div(className="stat-box", children=[html.B(f"{st['wins']}W/{st['losses']}L"), "برد/باخت"]),
        html.Div(className="stat-box", children=[html.B(f"{st['profit_factor']:.2f}"), "Profit Factor"]),
        html.Div(className="stat-box", children=[html.B(f"{st['n_open']}/{config.N_SLOTS}"), "پوزیشن باز"]),
        html.Div(className="stat-box", children=[html.B(f"{fmt_num(st['total_commission'], 2)}$"), "کل کمیسیون"]),
        html.Div(className="stat-box", children=[html.B(f"{fmt_num(st['total_spread'], 2)}$"), "کل اسپرد"]),
    ])

@app.callback(
    [Output("gauge", "figure"), Output("trend", "figure"), Output("eeg", "figure"),
     Output("regions", "figure"), Output("hormones", "figure"),
     Output("thoughts", "children"), Output("vitals", "children"),
     Output("chips", "children"), Output("milestones", "children"), Output("cons-detail", "children"),
     Output("ecg", "figure"), Output("fib-heart", "children"), Output("emotion-panel", "children"),
     Output("sensory-panel", "children"), Output("intuition-panel", "children"), Output("binary-panel", "children"),
     Output("mode-info", "children"), Output("trade-summary", "children"), Output("equity-chart", "figure"),
     Output("positions-table", "children"), Output("signals-list", "children"),
     Output("closed-table", "children"), Output("scanner-status", "children"),
     Output("focus-chart", "figure"), Output("lessons-panel", "children")],
    Input("clock", "n_intervals"),
    State("mode-selector", "value"))
def update(n, mode):
    try:
        return _update_impl(n, mode)
    except Exception:
        import traceback; traceback.print_exc()
        return [no_update]*25

def _update_impl(n, mode):
    if mode: ORGANISM.set_mode(mode)
    s = RUNNER.get_snapshot()
    scanner_snap = SCANNER.snapshot()
    gauge = go.Figure(go.Indicator(
        mode="gauge+number", value=s["consciousness"],
        number={"suffix": "٪", "font": {"size": 40, "color": "#e2e8f0"}},
        gauge={"axis": {"range": [0, 100], "tickcolor": "#94a3b8"}, "bar": {"color": "#8b5cf6"},
               "steps": [{"range": [0, 25], "color": "#1e1b4b"}, {"range": [25, 52], "color": "#312e81"},
                         {"range": [52, 74], "color": "#4338ca"}, {"range": [74, 100], "color": "#6d28d9"}]}))
    gauge.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=25, r=25, t=25, b=10), font={"family": "Vazirmatn", "color": "#cbd5e1"})
    trend = go.Figure()
    trend.add_scatter(y=s["hist_consciousness"], line=dict(color="#a78bfa", width=2),
                      fill="tozeroy", fillcolor="rgba(167,139,250,.15)", name="آگاهی")
    trend.add_scatter(y=[v*100 for v in s.get("hist_intuition", [])],
                      line=dict(color="#fbbf24", width=1.5, dash="dot"), name="شهود")
    style_fig(trend, [0, 100])
    eeg = go.Figure()
    eeg.add_scatter(y=s["eeg"], line=dict(color="#38bdf8", width=1))
    style_fig(eeg)
    names = list(s["regions"].keys())
    vals = [v*100 for v in s["regions"].values()]
    colors = ["#f87171" if v > 45 else "#fbbf24" if v > 20 else "#34d399" for v in vals]
    regions = go.Figure(go.Bar(x=vals, y=names, orientation="h", marker_color=colors,
                               text=[f"{v:.0f}٪" for v in vals], textposition="outside"))
    style_fig(regions)
    regions.update_layout(xaxis=dict(range=[0, 100]), margin=dict(l=130, r=34, t=20, b=28))
    hk, hv = list(s["hormones"].keys()), [v*100 for v in s["hormones"].values()]
    hormones = go.Figure(go.Bar(x=hk, y=hv, marker_color="#f472b6"))
    style_fig(hormones, [0, 105])
    cards = []
    for t in s["thoughts"][:config.MAX_THOUGHTS_SHOWN]:
        color = CATEGORY_COLORS.get(t.category, "#818cf8")
        cards.append(html.Div(className="thought-card", style={"borderRightColor": color}, children=[
            html.Div(className="thought-meta", children=[
                html.Span(f"#{t.tid:04d}"),
                html.Span(CATEGORY_FA.get(t.category, t.category), className="cat-chip",
                          style={"color": color, "border": f"1px solid {color}"}),
                html.Span(f"شدت {int(t.intensity*100)}٪"), html.Span(f"تیک {t.tick}")]),
            html.Div(t.text)]))
    thoughts_children = cards or html.Div("هنوز فکری شکل نگرفته…", style={"color": "#64748b"})
    v = s["vitals"]
    vitals_children = [
        vital_card("ضربان قلب", v["قلب"], "bpm", v["قلب"]/1.6, "#f87171"),
        vital_card("اکسیژن", v["اکسیژن"], "٪", v["اکسیژن"], "#38bdf8"),
        vital_card("انرژی", v["انرژی"], "٪", v["انرژی"], "#34d399"),
    ]
    st = s["trade_stats"]
    gpu_chip = html.Span(f"{'🟢 GPU' if s.get('gpu_active') else '🔵 CPU'}",
                         className="chip "+("chip-ok" if s.get("gpu_active") else "chip-purple"))
    chips = [
        html.Span(f"🕐 تیک {s['tick']}", className="chip"),
        gpu_chip,
        html.Span(f"🧠 {s['n_neurons']:,} نورون", className="chip chip-purple"),
        html.Span(f"⚡ سوپرهیومن ×{s['superhuman_factor']:.2f}", className="chip chip-gold"),
        html.Span(f"🧠 IQ: {s.get('iq_display', 200)}", className="chip chip-gold"),
        html.Span(f"🔮 شهود {s.get('intuition_level', 0)*100:.0f}٪", className="chip chip-gold"),
        html.Span(f"💵 {fmt_num(st['equity'])}$/۵۰۰$", className="chip chip-gold"),
        html.Span(f"📊 وین‌ریت {st['win_rate']:.0f}٪", className="chip "+("chip-ok" if st["win_rate"] >= 50 else "chip-bad")),
        html.Span(f"🌐 {'🟢' if s['scanner_connected'] else '🔴'} {s['n_scanned']} ارز",
                  className="chip "+("chip-ok" if s["scanner_connected"] else "chip-bad")),
        html.Span(f"🎯 {TRADING_MODES[s['mode']]['label']}", className="chip chip-gold"),
        html.Span(f"🌀 {s['state_label']}", className="chip chip-ok"),
    ]
    milestones = [html.Div(f"✦ {m}") for m in s["milestones"]]
    cons_detail = html.Div([
        html.Div(f"Φ: {s['phi']:.3f} | یکپارچگی: {s['integration']:.2f} | تمایز: {s['differentiation']:.2f}"),
        html.Div(f"فضای کار: {s['workspace']:.2f} | برانگیختگی: {s['arousal']:.2f}"),
        html.Div(f"🌙 بدون خواب — بیداری: {s['wakefulness']*100:.0f}٪", style={"color": "#4ade80", "marginTop": 4}),
    ])
    ecg_fig = go.Figure()
    ecg_fig.add_scatter(y=s["ecg"], line=dict(color="#f87171", width=1.5))
    style_fig(ecg_fig)
    fib_heart = html.Div([
        html.Div(f"فیب: {s['fib_number']} | ضربان: {s['heart_rate']:.0f} bpm",
                 style={"fontSize": 11, "color": "#fbbf24", "textAlign": "center", "marginTop": 4}),
    ])
    emotion_panel = render_emotion_panel(s)
    sensory_panel = render_sensory_panel(s)
    intuition_panel = render_intuition_panel(s)
    binary_panel = render_binary_panel(s)
    mode_info = render_mode_info(s)
    trade_summary = render_trade_summary(st)
    equity_chart = go.Figure()
    equity_chart.add_scatter(y=s["equity_history"], line=dict(color="#4ade80", width=2),
                             fill="tozeroy", fillcolor="rgba(74,222,128,.12)")
    style_fig(equity_chart)
    positions_table = render_positions(s["positions_live"])
    signals_list = render_signals(s["signals"])
    closed_table = render_closed(s["closed_trades"])
    lessons_panel = render_lessons(s)
    scanner_status = html.Div(
        f"🔍 اسکن {config.SCAN_SYMBOL_LIMIT} ارز | عمیق {config.SCAN_DEEP_LIMIT} | دور: {s['scan_cycles']} | "
        f"کارمزد: {config.TAKER_FEE*100:.3f}٪ | 🚫 صفر اندیکاتور سنتی",
        style={"color": "#94a3b8"})
    focus_chart = build_focus_chart(s, scanner_snap)
    return [gauge, trend, eeg, regions, hormones, thoughts_children,
            vitals_children, chips, milestones, cons_detail,
            ecg_fig, fib_heart, emotion_panel, sensory_panel, intuition_panel, binary_panel,
            mode_info, trade_summary, equity_chart,
            positions_table, signals_list, closed_table, scanner_status, focus_chart, lessons_panel]

@app.callback(Output("store-paused", "data"), Input("btn-pause", "n_clicks"),
              State("store-paused", "data"), prevent_initial_call=True)
def toggle_pause(n, paused):
    RUNNER.paused = not RUNNER.paused
    return not paused

@app.callback(Output("store-speed", "data"), Input("speed", "value"))
def set_speed(v):
    RUNNER.speed = v or config.DEFAULT_SPEED
    return v or config.DEFAULT_SPEED

@app.callback(Output("reset-status", "children"),
              Input("btn-reset-memory", "n_clicks"),
              State("mode-selector", "value"), prevent_initial_call=True)
def reset_memory(n, mode):
    if not n: return ""
    try:
        ORGANISM.set_mode(mode or "swing")
        ORGANISM.reset_all_trading_memory()
        return f"🗑️ حافظه معاملات هر دو موتور ریست شد"
    except Exception as e:
        import traceback; traceback.print_exc()
        return f"⚠️ خطا در ریست: {e}"

@app.callback(Output("flash", "children"),
              [Input({"type": "stim", "index": k}, "n_clicks") for k in STIM_LABELS]
              +[Input("btn-rebirth", "n_clicks")], prevent_initial_call=True)
def interact(*args):
    trig = ctx.triggered_id
    if trig == "btn-rebirth":
        ORGANISM.rebirth()
        return html.Span("🌌 موجود جدید با ژنوم تریدر تکینگی متولد شد.", style={"color": "#a78bfa"})
    if isinstance(trig, dict) and trig.get("type") == "stim":
        ORGANISM.env.inject(trig["index"])
        return html.Span(f"✔ محرک «{STIM_LABELS[trig['index']]}» تزریق شد.")
    return ""

if __name__ == "__main__":
    print(f"🌌 {config.PROJECT_NAME} v{config.VERSION} — تکینگی")
    print(f"🖥 {GPU.label}")
    print(f"🧠 نورون‌ها با مقیاس ×{config.NEURON_SCALE:.2f} | سقف {config.MAX_NEURONS:,} | موازی: {config.PARALLEL_BRAIN}")
    print(f"🌌 {config.SENSORS_PER_SENSE} حسگر/حس + {config.N_XENO_SENSES} حس فرازمینی")
    print(f"🔮 دروازه شهود: {int(config.INTUITION_GATE*100)}٪ | ⚡ کاوشگرهای باینری: {config.BINARY_PROBES}")
    print(f"💵 هر موتور: {config.INITIAL_CAPITAL}$ بین {config.N_SLOTS} ارز")
    print("   آدرس: http://127.0.0.1:8070")
    try:
        app.run(debug=False, host="0.0.0.0", port=8070)
    except AttributeError:
        app.run_server(debug=False, host="0.0.0.0", port=8070)