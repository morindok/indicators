# living_trader_organism.py
# -*- coding: utf-8 -*-
"""
ارگانیسم دیجیتال زنده — نسخه‌ی نهایی فرابشری
- اسکن پیوسته‌ی ۱۰۰ ارز پرحجم بایبیت
- تصمیم لحظه‌ای و بازکردن معامله بلافاصله در لایو
- شورای ۷ ذهن برای چندبرابر کردن قدرت تصمیم
- بدون معامله‌ی تکراری روی ارزِ دارای موقعیت باز
- ۵۰۰ حس + شهود «ارگانون سوم» + ژنوم + هورمون + قلب فیبوناچی
PAPER TRADING ONLY — Binds to 127.0.0.1
"""

import time, json, uuid, sqlite3, threading, hashlib, platform
from collections import deque, defaultdict
from datetime import datetime, timezone

import numpy as np
import requests

import dash
from dash import dcc, html, Output, Input
import plotly.graph_objects as go

# ----------------------------------------------------------------------------
# پیکربندی سراسری
# ----------------------------------------------------------------------------
DB_PATH          = "organism.db"
UNIVERSE_SIZE    = 100          # ۱۰۰ ارز پرحجم
INTERVAL         = "1"          # کندل ۱ دقیقه‌ای برای اسکالپ
KLINE_LIMIT      = 200
LEVERAGE         = 20           # فقط paper
START_EQUITY     = 1000.0
RISK_PER_TRADE   = 0.02
TAKER_FEE        = 0.00055
TICK_SECONDS     = 2.0          # ضربان ادراک/اقدام
N_SENSES         = 500
N_MINDS          = 7            # شورای ذهن‌ها
MAX_OPEN_TOTAL   = 15           # سقف کل موقعیت‌های باز
MAX_OPEN_PER_TICK= 3            # قوی‌ترین‌ها در هر تیک
ENTRY_THRESHOLD  = 0.22         # آستانه‌ی یقین شورا
COOLDOWN_SEC     = 90           # خنک‌سازی بعد از بستن هر ارز
MAX_HOLD_SEC     = 900          # سقف نگهداری اسکالپ (۱۵ دقیقه)
SCAN_WORKERS     = 5            # نخ‌های تازه‌سازی کندل
HOST, PORT       = "127.0.0.1", 8050

BYBIT_DOMAINS = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]

# ----------------------------------------------------------------------------
# اتصال Bybit با چرخش دامنه و backoff
# ----------------------------------------------------------------------------
class BybitHTTP:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.bybit.com/",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self._dom = 0
        self._lock = threading.Lock()

    def get(self, path, params=None, retries=3):
        last_err = None
        for attempt in range(retries):
            for i in range(len(BYBIT_DOMAINS)):
                with self._lock:
                    idx = (self._dom + i) % len(BYBIT_DOMAINS)
                dom = BYBIT_DOMAINS[idx]
                try:
                    r = self.session.get(dom + path, params=params, timeout=6)
                    if r.status_code in (403, 451):
                        continue
                    j = r.json()
                    if j.get("retCode") == 0:
                        with self._lock:
                            self._dom = idx
                        return j.get("result", {})
                    last_err = j.get("retMsg")
                except Exception as e:
                    last_err = str(e)
                    continue
            time.sleep(0.4 * (attempt + 1))
        raise RuntimeError(f"Bybit fetch failed: {last_err}")

    def klines(self, symbol, interval=INTERVAL, limit=KLINE_LIMIT):
        res = self.get("/v5/market/kline",
                       {"category": "linear", "symbol": symbol,
                        "interval": interval, "limit": limit})
        rows = sorted(res.get("list", []), key=lambda x: int(x[0]))
        if not rows:
            return None
        return {
            "o": np.array([float(x[1]) for x in rows]),
            "h": np.array([float(x[2]) for x in rows]),
            "l": np.array([float(x[3]) for x in rows]),
            "c": np.array([float(x[4]) for x in rows]),
            "v": np.array([float(x[5]) for x in rows]),
            "ts": time.time(),
        }

    def all_tickers(self):
        """قیمت لحظه‌ای همه‌ی کانترکت‌های linear با یک درخواست."""
        res = self.get("/v5/market/tickers", {"category": "linear"})
        return res.get("list", [])


# ----------------------------------------------------------------------------
# حافظه‌ی پایدار (SQLite) — اسکیمای حفظ‌شده
# ----------------------------------------------------------------------------
class DB:
    def __init__(self, path=DB_PATH):
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self._init()

    def _init(self):
        with self.lock:
            c = self.conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, engine TEXT, coin TEXT, side INTEGER,
                entry REAL, size REAL, margin REAL, leverage INTEGER, notional REAL,
                tp REAL, sl REAL, conviction REAL, reasons TEXT, commission REAL,
                spread_cost REAL, open_time TEXT, open_ts INTEGER, open_tick INTEGER,
                slot_id INTEGER, status TEXT DEFAULT 'open', exit_price REAL,
                exit_reason TEXT, net_pnl REAL, close_time TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS engine_state (
                engine TEXT PRIMARY KEY, slot_capitals TEXT, realized_pnl REAL,
                wins INTEGER, losses INTEGER, total_commission REAL, total_spread REAL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS gene_expression (
                gene TEXT PRIMARY KEY, value REAL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS experiences (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tick INTEGER, symbol TEXT,
                side TEXT, entry REAL, exit REAL, pnl REAL, outcome TEXT, created_at INTEGER)""")
            self.conn.commit()

    def save_gene(self, gene, val):
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO gene_expression VALUES (?,?)",
                              (gene, val))
            self.conn.commit()

    def save_state(self, engine, realized, wins, losses, comm, spread):
        with self.lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO engine_state VALUES (?,?,?,?,?,?,?)",
                (engine, "{}", realized, wins, losses, comm, spread))
            self.conn.commit()

    def load_state(self, engine):
        with self.lock:
            return self.conn.execute(
                "SELECT realized_pnl,wins,losses,total_commission,total_spread "
                "FROM engine_state WHERE engine=?", (engine,)).fetchone()

    def load_open_positions(self):
        with self.lock:
            rows = self.conn.execute(
                "SELECT id,coin,side,entry,size,margin,leverage,notional,tp,sl,"
                "conviction,commission,spread_cost,open_ts FROM positions "
                "WHERE status='open'").fetchall()
        return rows

    def record_position(self, p):
        with self.lock:
            self.conn.execute(
                """INSERT INTO positions
                   (engine,coin,side,entry,size,margin,leverage,notional,tp,sl,
                    conviction,reasons,commission,spread_cost,open_time,open_ts,
                    open_tick,slot_id,status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (p["engine"], p["coin"], p["side"], p["entry"], p["size"], p["margin"],
                 p["leverage"], p["notional"], p["tp"], p["sl"], p["conviction"],
                 json.dumps(p["reasons"], ensure_ascii=False), p["commission"],
                 p["spread_cost"], p["open_time"], p["open_ts"], p["open_tick"],
                 p["slot_id"], "open"))
            pid = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            self.conn.commit()
        return pid

    def close_position(self, pid, exit_price, reason, net_pnl):
        with self.lock:
            self.conn.execute(
                "UPDATE positions SET status='closed', exit_price=?, exit_reason=?, "
                "net_pnl=?, close_time=? WHERE id=?",
                (exit_price, reason, net_pnl,
                 datetime.now(timezone.utc).isoformat(), pid))
            self.conn.commit()

    def record_experience(self, tick, symbol, side, entry, exit_p, pnl):
        with self.lock:
            self.conn.execute(
                "INSERT INTO experiences (tick,symbol,side,entry,exit,pnl,outcome,created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (tick, symbol, "L" if side == 1 else "S", entry, exit_p, pnl,
                 "win" if pnl >= 0 else "loss", int(time.time())))
            self.conn.commit()

    def history(self, limit=50):
        with self.lock:
            return self.conn.execute(
                "SELECT coin,side,entry,exit_price,net_pnl,exit_reason,close_time "
                "FROM positions WHERE status='closed' ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()


# ----------------------------------------------------------------------------
# ژنوم پایدار (اثرانگشت سخت‌افزار)
# ----------------------------------------------------------------------------
class Genome:
    GENES = ["RISK_MANAGEMENT", "AGGRESSION", "PATIENCE", "INTUITION",
             "PATTERN_SENSE", "VOLATILITY_LOVE", "MEAN_REVERT", "MOMENTUM_RIDE",
             "SELF_PRESERVATION", "CURIOSITY"]

    def __init__(self):
        fp = f"{platform.node()}|{platform.machine()}|{uuid.getnode()}"
        h = hashlib.sha256(fp.encode()).hexdigest()
        self.dna_id = h[:16]
        rng = np.random.default_rng(int(h[:8], 16))
        self.expression = {g: float(rng.uniform(0.35, 0.95)) for g in self.GENES}

    def express(self, gene):
        return self.expression.get(gene, 0.5)


# ----------------------------------------------------------------------------
# قلب فیبوناچی — علامت حیاتی (اقدام دیگر منتظر ضربان نمی‌ماند)
# ----------------------------------------------------------------------------
class FibonacciHeart:
    def __init__(self):
        a, b = "0", "01"
        while len(b) < 4096:
            a, b = b, b + a
        self.word = b
        self.i = 0

    def beat(self):
        bit = int(self.word[self.i % len(self.word)])
        self.i += 1
        return bit  # 1=سیستول (اوج تهاجم)، 0=دیاستول


# ----------------------------------------------------------------------------
# سامانه‌ی ۵۰۰ حس
# ----------------------------------------------------------------------------
class SensoryCortex:
    def __init__(self, n=N_SENSES):
        self.n = n

    def perceive(self, k, live_price=None):
        c = k["c"].copy()
        if live_price:
            c[-1] = live_price          # ادغام قیمت لحظه‌ای در ادراک
        h, l, o, v = k["h"], k["l"], k["o"], k["v"]
        if len(c) < 60:
            return None
        ret = np.diff(np.log(c + 1e-12))
        senses = []

        # مومنتوم چندمقیاسی (۱۰۰)
        for w in np.linspace(2, 100, 100).astype(int):
            w = min(w, len(c) - 1)
            senses.append(np.tanh((c[-1] - c[-w]) / (c[-w] + 1e-12) * 50))
        # نوسان چندمقیاسی (۸۰)
        for w in np.linspace(3, 90, 80).astype(int):
            w = min(w, len(ret))
            senses.append(np.tanh(np.std(ret[-w:]) * 200))
        # کالبد کندل: بدنه/سایه‌ها (۶۰)
        rng_ = (h - l) + 1e-12
        for arr in (np.abs(c - o) / rng_,
                    (h - np.maximum(c, o)) / rng_,
                    (np.minimum(c, o) - l) / rng_):
            for w in (1, 3, 5, 8, 13, 21, 34, 55, 89, 144):
                w = min(w, len(arr))
                senses.append(np.tanh(np.mean(arr[-w:]) * 2 - 1))
        # حجم (۶۰)
        vn = v / (np.mean(v[-100:]) + 1e-12)
        for w in np.linspace(1, 100, 60).astype(int):
            w = min(w, len(vn))
            senses.append(np.tanh(np.mean(vn[-w:]) - 1))
        # خودهمبستگی/ریتم (۶۰)
        for lag in np.linspace(1, 60, 60).astype(int):
            lag = min(lag, len(ret) - 2)
            a, b = ret[:-lag], ret[lag:]
            m = min(len(a), len(b))
            if m > 3:
                corr = np.corrcoef(a[-m:], b[-m:])[0, 1]
                senses.append(0.0 if np.isnan(corr) else float(corr))
            else:
                senses.append(0.0)
        # آنتروپی (۴۰)
        for w in np.linspace(10, 120, 40).astype(int):
            w = min(w, len(ret))
            hist, _ = np.histogram(ret[-w:], bins=8)
            p = hist / (hist.sum() + 1e-12)
            senses.append(-np.sum(p * np.log(p + 1e-12)) / np.log(8) * 2 - 1)
        # فراکتال/تلاطم (۴۰)
        for w in np.linspace(8, 100, 40).astype(int):
            w = min(w, len(c))
            seg = c[-w:]
            hl = (np.max(seg) - np.min(seg)) / \
                 (np.mean(np.abs(np.diff(seg))) * len(seg) + 1e-12)
            senses.append(np.tanh(hl - 1))

        arr = np.array(senses, dtype=float)
        if len(arr) < self.n:
            arr = np.concatenate([arr, np.zeros(self.n - len(arr))])
        return np.clip(arr[:self.n], -1, 1)


# ----------------------------------------------------------------------------
# شهود ارگانون سوم — حافظه‌ی نومنال جداگانه برای هر ارز
# ----------------------------------------------------------------------------
class TertiumOrganum:
    def __init__(self, n=N_SENSES):
        rng = np.random.default_rng(3)
        self.axes = rng.standard_normal((3, n))
        self.axes /= np.linalg.norm(self.axes, axis=1, keepdims=True)
        self.mem = defaultdict(lambda: deque(maxlen=64))

    def intuit(self, symbol, senses):
        proj = self.axes @ senses
        mem = self.mem[symbol]
        mem.append(proj)
        M = np.array(mem)
        if len(M) >= 5:
            flow = np.tanh(np.mean(np.diff(M[:, 0])) * 30)
            depth = np.tanh(proj[1])
            timesense = np.tanh(proj[2] - np.mean(M[:, 2]))
        else:
            flow, depth, timesense = 0.0, float(np.tanh(proj[1])), 0.0
        noumenon = float(np.tanh(0.5 * flow + 0.3 * depth + 0.2 * timesense))
        clarity = float(1.0 / (1.0 + np.std(M[:, 0]))) if len(M) >= 3 else 0.3
        return {"noumenon": noumenon, "clarity": clarity,
                "flow": float(flow), "depth": float(depth), "time": float(timesense)}


# ----------------------------------------------------------------------------
# ارگان‌های مغز — فعال‌سازی نرم جداگانه برای هر ارز
# ----------------------------------------------------------------------------
class Organs:
    NAMES = ["Cortex", "Hippocampus", "Amygdala", "VisualCortex",
             "Cerebellum", "PinealGland", "NumericalLobe", "IntuitionCore"]

    def __init__(self, n=N_SENSES, seed=42):
        rng = np.random.default_rng(seed)
        self.W = {}
        for name in self.NAMES:
            w = rng.standard_normal(n) * rng.uniform(0.2, 1.0)
            self.W[name] = w / (np.linalg.norm(w) + 1e-12)
        self.act = defaultdict(lambda: {name: 0.0 for name in self.NAMES})

    def fire(self, symbol, senses, intuition):
        state = self.act[symbol]
        for name in self.NAMES:
            a = intuition["noumenon"] * intuition["clarity"] if name == "IntuitionCore" \
                else float(np.tanh(self.W[name] @ senses))
            state[name] = 0.6 * state[name] + 0.4 * a
        return dict(state)


# ----------------------------------------------------------------------------
# سامانه‌ی هورمونی
# ----------------------------------------------------------------------------
class Endocrine:
    def __init__(self):
        self.h = {"adrenaline": 0.2, "cortisol": 0.3, "dopamine": 0.5,
                  "serotonin": 0.6, "oxytocin": 0.4, "melatonin": 0.2}

    def update(self, mean_amygdala, mean_clarity, mean_flow, recent_pnl):
        vol = abs(mean_amygdala)
        self.h["adrenaline"] = float(np.clip(0.5 * self.h["adrenaline"] + 0.5 * vol, 0, 1))
        self.h["cortisol"]   = float(np.clip(0.6 * self.h["cortisol"] + 0.4 * max(0, -recent_pnl), 0, 1))
        self.h["dopamine"]   = float(np.clip(0.6 * self.h["dopamine"] + 0.4 * max(0, recent_pnl), 0, 1))
        self.h["serotonin"]  = float(np.clip(0.7 * self.h["serotonin"] + 0.3 * mean_clarity, 0, 1))
        self.h["oxytocin"]   = float(np.clip(0.8 * self.h["oxytocin"] + 0.2 * abs(mean_flow), 0, 1))
        self.h["melatonin"]  = float(np.clip(0.9 * self.h["melatonin"] + 0.1 * (1 - vol), 0, 1))
        return dict(self.h)

    def risk_multiplier(self):
        return float(np.clip(0.5 + 0.6 * self.h["dopamine"] + 0.4 * self.h["adrenaline"]
                             - 0.7 * self.h["cortisol"], 0.15, 1.6))


def detect_regime(c):
    if len(c) < 50:
        return "UNKNOWN"
    ret = np.diff(np.log(c[-50:] + 1e-12))
    vol = np.std(ret)
    trend = abs(c[-1] - c[-50]) / (np.sum(np.abs(np.diff(c[-50:]))) + 1e-12)
    if vol > 0.006:
        return "VOLATILE_CHAOS"
    if trend > 0.35:
        return "TRENDING"
    return "RANGING"


# ----------------------------------------------------------------------------
# شورای ذهن‌ها — چندبرابر کردن قدرت تصمیم
# هر ذهن یک آگاهی مستقل با بیان ژنی جهش‌یافته است؛ اجماع + توافق = یقین نهایی
# ----------------------------------------------------------------------------
class MindCouncil:
    def __init__(self, genome, n_minds=N_MINDS):
        self.g = genome
        base = {
            "Cortex":        0.9 * genome.express("MOMENTUM_RIDE"),
            "Hippocampus":   0.7 * genome.express("PATTERN_SENSE"),
            "Amygdala":      0.8 * genome.express("SELF_PRESERVATION"),
            "VisualCortex":  0.7 * genome.express("PATTERN_SENSE"),
            "Cerebellum":    0.6 * genome.express("PATIENCE"),
            "PinealGland":   0.8 * genome.express("INTUITION"),
            "NumericalLobe": 0.9 * genome.express("RISK_MANAGEMENT"),
            "IntuitionCore": 1.2 * genome.express("INTUITION"),
        }
        rng = np.random.default_rng(int(genome.dna_id, 16) % (2**32))
        self.minds = []
        for _ in range(n_minds):
            self.minds.append({k_: v * float(rng.uniform(0.7, 1.3))
                               for k_, v in base.items()})

    def decide(self, activations, intuition, regime):
        votes = []
        for W in self.minds:
            raw = sum(W[k_] * activations.get(k_, 0.0) for k_ in W)
            raw += 1.4 * intuition["noumenon"] * intuition["clarity"]
            if regime == "RANGING":
                raw = -0.6 * raw - 0.4 * activations.get("Cortex", 0.0)
            elif regime == "VOLATILE_CHAOS":
                raw *= 0.5
            votes.append(float(np.tanh(raw)))
        votes = np.array(votes)
        mean = float(np.mean(votes))
        side = 1 if mean > 0 else -1
        agreement = float(np.mean(np.sign(votes) == side))     # وحدت شورا
        conviction = float(min(1.0, abs(mean)
                               * (0.4 + 0.6 * agreement)
                               * (0.5 + 0.5 * intuition["clarity"])
                               * (1.0 + 0.3 * self.g.express("AGGRESSION"))))
        reasons = {"mean_vote": round(mean, 3),
                   "agreement": round(agreement, 2),
                   "clarity": round(intuition["clarity"], 2),
                   "noumenon": round(intuition["noumenon"], 3),
                   "regime": regime,
                   "top_organ": max(activations, key=lambda x: abs(activations[x]))}
        return side, conviction, reasons


# ----------------------------------------------------------------------------
# اسکنر بازار — کهکشان ۱۰۰ ارز، همیشه تازه
# ----------------------------------------------------------------------------
class MarketScanner:
    def __init__(self, http):
        self.http = http
        self.symbols = []
        self.klines = {}
        self.prices = {}
        self.lock = threading.Lock()
        self._stop = False
        self._universe_ts = 0

    def start(self):
        self._select_universe()
        threading.Thread(target=self._ticker_loop, daemon=True).start()
        for i in range(SCAN_WORKERS):
            threading.Thread(target=self._kline_worker, args=(i,), daemon=True).start()

    def _select_universe(self):
        try:
            tickers = self.http.all_tickers()
            usdt = [t for t in tickers if t["symbol"].endswith("USDT")
                    and float(t.get("turnover24h", 0)) > 0]
            usdt.sort(key=lambda t: float(t["turnover24h"]), reverse=True)
            with self.lock:
                self.symbols = [t["symbol"] for t in usdt[:UNIVERSE_SIZE]]
                for t in usdt[:UNIVERSE_SIZE]:
                    self.prices[t["symbol"]] = float(t["lastPrice"])
            self._universe_ts = time.time()
        except Exception:
            pass

    def _ticker_loop(self):
        """قیمت زنده‌ی همه‌ی ارزها هر ۲ ثانیه با یک درخواست bulk."""
        while not self._stop:
            try:
                tickers = self.http.all_tickers()
                with self.lock:
                    wanted = set(self.symbols)
                    for t in tickers:
                        if t["symbol"] in wanted:
                            self.prices[t["symbol"]] = float(t["lastPrice"])
                if time.time() - self._universe_ts > 600:   # کهکشان هر ۱۰ دقیقه تازه
                    self._select_universe()
            except Exception:
                pass
            time.sleep(TICK_SECONDS)

    def _kline_worker(self, worker_id):
        """هر نخ بخشی از کهکشان را چرخشی تازه می‌کند."""
        while not self._stop:
            with self.lock:
                syms = list(self.symbols)
            if not syms:
                time.sleep(1)
                continue
            for idx, sym in enumerate(syms):
                if idx % SCAN_WORKERS != worker_id:
                    continue
                try:
                    k = self.http.klines(sym)
                    if k is not None:
                        with self.lock:
                            self.klines[sym] = k
                except Exception:
                    pass
                time.sleep(0.25)   # رعایت rate-limit؛ کل کهکشان ~هر ۵-۸ ثانیه تازه

    def snapshot(self):
        with self.lock:
            return dict(self.klines), dict(self.prices), list(self.symbols)


# ----------------------------------------------------------------------------
# موتور اسکالپ — بدون معامله‌ی تکراری، خروج چندلایه
# ----------------------------------------------------------------------------
class ScalperEngine:
    def __init__(self, db):
        self.db = db
        self.lock = threading.Lock()
        self.equity = START_EQUITY
        self.realized = 0.0
        self.wins = 0
        self.losses = 0
        self.commission = 0.0
        self.spread = 0.0
        self.positions = {}          # pid -> dict
        self.open_coins = set()      # قفل ارزهای دارای موقعیت باز
        self.cooldown = {}           # coin -> ts آخرین بستن
        row = db.load_state("organism")
        if row:
            self.realized, self.wins, self.losses, self.commission, self.spread = row
            self.equity = START_EQUITY + self.realized
        # بازیابی موقعیت‌های باز از جلسه‌ی قبل (تداوم حیات)
        for r in db.load_open_positions():
            pid, coin, side, entry, size, margin, lev, notional, tp, sl, conv, comm, spr, ots = r
            self.positions[pid] = {
                "pid": pid, "coin": coin, "side": side, "entry": entry, "size": size,
                "margin": margin, "leverage": lev, "notional": notional, "tp": tp,
                "sl": sl, "conviction": conv, "commission": comm, "spread_cost": spr,
                "open_ts": ots, "peak": entry}
            self.open_coins.add(coin)

    def can_open(self, coin):
        with self.lock:
            if coin in self.open_coins:                      # ❌ معامله‌ی تکراری ممنوع
                return False
            if len(self.positions) >= MAX_OPEN_TOTAL:
                return False
            if time.time() - self.cooldown.get(coin, 0) < COOLDOWN_SEC:
                return False
        return True

    def open_trade(self, coin, price, side, conviction, reasons, hormone_mult, tick):
        if not self.can_open(coin):
            return False
        margin = self.equity * RISK_PER_TRADE * (0.5 + conviction) * hormone_mult
        margin = max(1.0, min(margin, self.equity * 0.15))
        notional = margin * LEVERAGE
        size = notional / price
        comm = notional * TAKER_FEE
        spread_cost = notional * 0.0001
        tp_pct = 0.0025 + 0.004 * conviction
        sl_pct = 0.0020 + 0.003 * (1 - conviction)
        p = {"engine": "organism", "coin": coin, "side": side, "entry": price,
             "size": size, "margin": margin, "leverage": LEVERAGE, "notional": notional,
             "tp": price * (1 + side * tp_pct), "sl": price * (1 - side * sl_pct),
             "conviction": conviction, "reasons": reasons, "commission": comm,
             "spread_cost": spread_cost,
             "open_time": datetime.now(timezone.utc).isoformat(),
             "open_ts": int(time.time()), "open_tick": tick, "slot_id": 0}
        pid = self.db.record_position(p)
        p["pid"] = pid
        p["peak"] = price
        with self.lock:
            self.positions[pid] = p
            self.open_coins.add(coin)
            self.commission += comm
            self.spread += spread_cost
        return True

    def manage(self, prices, tick):
        """خروج لحظه‌ای: TP/SL + تریلینگ + سقف زمان."""
        now = time.time()
        to_close = []
        with self.lock:
            items = list(self.positions.items())
        for pid, p in items:
            price = prices.get(p["coin"])
            if price is None:
                continue
            side = p["side"]
            # تریلینگ: قله‌ی سود را دنبال کن
            if side == 1:
                p["peak"] = max(p["peak"], price)
                trail = p["peak"] * (1 - 0.0022)
                if price >= p["tp"]:
                    to_close.append((pid, price, "TP"))
                elif price <= p["sl"]:
                    to_close.append((pid, price, "SL"))
                elif p["peak"] > p["entry"] * 1.002 and price <= trail:
                    to_close.append((pid, price, "TRAIL"))
                elif now - p["open_ts"] > MAX_HOLD_SEC:
                    to_close.append((pid, price, "TIME"))
            else:
                p["peak"] = min(p["peak"], price)
                trail = p["peak"] * (1 + 0.0022)
                if price <= p["tp"]:
                    to_close.append((pid, price, "TP"))
                elif price >= p["sl"]:
                    to_close.append((pid, price, "SL"))
                elif p["peak"] < p["entry"] * 0.998 and price >= trail:
                    to_close.append((pid, price, "TRAIL"))
                elif now - p["open_ts"] > MAX_HOLD_SEC:
                    to_close.append((pid, price, "TIME"))
        for pid, price, reason in to_close:
            self._close(pid, price, reason, tick)

    def _close(self, pid, price, reason, tick):
        with self.lock:
            p = self.positions.pop(pid, None)
            if p is None:
                return
            self.open_coins.discard(p["coin"])
            self.cooldown[p["coin"]] = time.time()
        gross = p["side"] * (price - p["entry"]) * p["size"]
        exit_comm = p["notional"] * TAKER_FEE
        net = gross - p["commission"] - exit_comm - p["spread_cost"]
        with self.lock:
            self.realized += net
            self.equity += net
            self.commission += exit_comm
            if net >= 0:
                self.wins += 1
            else:
                self.losses += 1
        self.db.close_position(pid, price, reason, net)
        self.db.record_experience(tick, p["coin"], p["side"], p["entry"], price, net)
        self.db.save_state("organism", self.realized, self.wins, self.losses,
                           self.commission, self.spread)

    def unrealized(self, prices):
        u = 0.0
        with self.lock:
            for p in self.positions.values():
                pr = prices.get(p["coin"])
                if pr:
                    u += p["side"] * (pr - p["entry"]) * p["size"]
        return u

    def stats(self, prices=None):
        with self.lock:
            total = self.wins + self.losses
            return {"equity": self.equity, "realized": self.realized,
                    "unrealized": self.unrealized(prices or {}) if prices else 0.0,
                    "wins": self.wins, "losses": self.losses,
                    "win_rate": (self.wins / total * 100) if total else 0.0,
                    "open": len(self.positions), "commission": self.commission}


# ----------------------------------------------------------------------------
# ارگانیسم — حلقه‌ی حیات: ادراک ۱۰۰ ارز → شورا → اقدام بلافاصله
# ----------------------------------------------------------------------------
class Organism:
    def __init__(self):
        self.http = BybitHTTP()
        self.db = DB()
        self.genome = Genome()
        for g, v in self.genome.expression.items():
            self.db.save_gene(g, v)
        self.heart = FibonacciHeart()
        self.senses = SensoryCortex()
        self.tertium = TertiumOrganum()
        self.organs = Organs()
        self.endocrine = Endocrine()
        self.council = MindCouncil(self.genome)
        self.engine = ScalperEngine(self.db)
        self.scanner = MarketScanner(self.http)

        self.tick = 0
        self.state = {"activations": {}, "hormones": dict(self.endocrine.h),
                      "intuition": {"noumenon": 0, "clarity": 0, "flow": 0,
                                    "depth": 0, "time": 0},
                      "top_signals": [], "heartbeat": 0, "scanned": 0,
                      "universe": 0, "error": None}

        self.scanner.start()
        threading.Thread(target=self._live, daemon=True).start()

    def _live(self):
        while True:
            t0 = time.time()
            try:
                self.tick += 1
                beat = self.heart.beat()
                self.state["heartbeat"] = beat
                klines, prices, symbols = self.scanner.snapshot()

                candidates = []
                agg_act = defaultdict(float)
                sum_clarity = sum_flow = sum_amyg = 0.0
                n_eval = 0

                # ادراک همه‌ی کهکشان در همین تیک
                for sym in symbols:
                    k = klines.get(sym)
                    price = prices.get(sym)
                    if k is None or price is None:
                        continue
                    s = self.senses.perceive(k, live_price=price)
                    if s is None:
                        continue
                    intuition = self.tertium.intuit(sym, s)
                    acts = self.organs.fire(sym, s, intuition)
                    c_live = k["c"].copy()
                    c_live[-1] = price
                    regime = detect_regime(c_live)
                    side, conv, reasons = self.council.decide(acts, intuition, regime)

                    n_eval += 1
                    sum_clarity += intuition["clarity"]
                    sum_flow += intuition["flow"]
                    sum_amyg += acts["Amygdala"]
                    for kk, vv in acts.items():
                        agg_act[kk] += vv

                    candidates.append({"symbol": sym, "side": side, "conv": conv,
                                       "price": price, "reasons": reasons,
                                       "regime": regime})

                # قوی‌ترین‌ها اول — اقدام بلافاصله در همین تیک
                candidates.sort(key=lambda x: x["conv"], reverse=True)
                hormone_mult = self.endocrine.risk_multiplier()
                if beat == 1:
                    hormone_mult *= 1.15      # سیستول: اوج تهاجم
                opened = 0
                for cand in candidates:
                    if opened >= MAX_OPEN_PER_TICK:
                        break
                    if cand["conv"] < ENTRY_THRESHOLD:
                        break                 # لیست مرتب است؛ بقیه ضعیف‌ترند
                    if self.engine.open_trade(cand["symbol"], cand["price"],
                                              cand["side"], cand["conv"],
                                              cand["reasons"], hormone_mult,
                                              self.tick):
                        opened += 1

                # مدیریت خروج با قیمت زنده‌ی همه‌ی ارزها
                self.engine.manage(prices, self.tick)

                if n_eval:
                    recent = float(np.tanh(self.engine.realized / 100.0))
                    hormones = self.endocrine.update(
                        sum_amyg / n_eval, sum_clarity / n_eval,
                        sum_flow / n_eval, recent)
                    self.state.update({
                        "activations": {k_: v / n_eval for k_, v in agg_act.items()},
                        "hormones": hormones,
                        "intuition": {"noumenon": np.mean([c["reasons"]["noumenon"]
                                                           for c in candidates[:20]]) if candidates else 0,
                                      "clarity": sum_clarity / n_eval,
                                      "flow": sum_flow / n_eval,
                                      "depth": 0.0, "time": 0.0},
                        "top_signals": candidates[:12],
                        "scanned": n_eval,
                        "universe": len(symbols),
                        "error": None,
                    })
            except Exception as e:
                self.state["error"] = str(e)
            # تیک دقیق — ادراک هرگز عقب نمی‌افتد
            time.sleep(max(0.2, TICK_SECONDS - (time.time() - t0)))


ORG = Organism()

# ----------------------------------------------------------------------------
# رابط کاربری Dash (فارسی، RTL)
# ----------------------------------------------------------------------------
app = dash.Dash(__name__)
app.title = "ارگانیسم معامله‌گر زنده"

CARD = {"background": "#12151c", "border": "1px solid #2a2f3a",
        "borderRadius": "12px", "padding": "12px", "margin": "8px"}

app.layout = html.Div(style={"background": "#0b0d12", "color": "#e6e6e6",
                             "fontFamily": "Tahoma, sans-serif",
                             "minHeight": "100vh", "direction": "rtl"}, children=[
    html.H2("🧬 ارگانیسم معامله‌گر زنده — شکارچی ۱۰۰ ارز",
            style={"textAlign": "center", "padding": "10px"}),
    html.Div(id="vitals", style={"textAlign": "center", "color": "#7cf"}),
    dcc.Tabs(id="tabs", value="t1", children=[
        dcc.Tab(label="کالبد و آگاهی", value="t1",
                style={"background": "#12151c", "color": "#ccc"},
                selected_style={"background": "#1c2230", "color": "#7cf"}),
        dcc.Tab(label="اتاق معاملات", value="t2",
                style={"background": "#12151c", "color": "#ccc"},
                selected_style={"background": "#1c2230", "color": "#7cf"}),
    ]),
    html.Div(id="tab-content"),
    dcc.Interval(id="tick", interval=2000, n_intervals=0),
])


@app.callback(Output("vitals", "children"), Input("tick", "n_intervals"))
def _vitals(_):
    s = ORG.state
    hb = "🫀 سیستول" if s["heartbeat"] == 1 else "🩶 دیاستول"
    err = f" | ⚠️ {s['error']}" if s.get("error") else ""
    return (f"DNA: {ORG.genome.dna_id} | تیک: {ORG.tick} | {hb} | "
            f"کهکشان: {s['universe']} ارز | اسکن این تیک: {s['scanned']} | "
            f"حس‌ها: {N_SENSES} × شورا: {N_MINDS} ذهن{err}")


@app.callback(Output("tab-content", "children"),
              Input("tabs", "value"), Input("tick", "n_intervals"))
def _render(tab, _):
    return _body_tab() if tab == "t1" else _trade_tab()


def _body_tab():
    s = ORG.state
    acts, horm, intu = s["activations"] or {}, s["hormones"] or {}, s["intuition"] or {}

    org_fig = go.Figure(go.Bar(
        x=list(acts.values()), y=list(acts.keys()), orientation="h",
        marker_color=["#7cf" if v >= 0 else "#f77" for v in acts.values()]))
    org_fig.update_layout(template="plotly_dark", title="فعالیت میانگین ارگان‌ها (کل کهکشان)",
                          height=320, margin=dict(l=10, r=10, t=40, b=10))

    hv, hk = list(horm.values()), list(horm.keys())
    horm_fig = go.Figure(go.Scatterpolar(
        r=hv + hv[:1] if hv else [], theta=hk + hk[:1] if hk else [],
        fill="toself", line_color="#f7a"))
    horm_fig.update_layout(template="plotly_dark", title="سامانه‌ی هورمونی",
                           height=320, margin=dict(l=30, r=30, t=40, b=30))

    genes = ORG.genome.expression
    gene_fig = go.Figure(go.Bar(x=list(genes.keys()), y=list(genes.values()),
                                marker_color="#8f8"))
    gene_fig.update_layout(template="plotly_dark", title="بیان ژنوم (DNA)",
                           height=300, margin=dict(l=10, r=10, t=40, b=60))

    labels = ["نومن", "شفافیت", "جریان وحدت"]
    vals = [abs(float(intu.get(k, 0) or 0)) for k in ("noumenon", "clarity", "flow")]
    intu_fig = go.Figure(go.Scatterpolar(r=vals + vals[:1], theta=labels + labels[:1],
                                         fill="toself", line_color="#fc7"))
    intu_fig.update_layout(template="plotly_dark",
                           title="حس ششم — ادراک بُعد بالاتر (ارگانون سوم)",
                           height=320, margin=dict(l=30, r=30, t=40, b=30))

    half = {"width": "48%", "display": "inline-block", "verticalAlign": "top"}
    return html.Div([
        html.Div([dcc.Graph(figure=org_fig)], style={**CARD, **half}),
        html.Div([dcc.Graph(figure=horm_fig)], style={**CARD, **half}),
        html.Div([dcc.Graph(figure=intu_fig)], style={**CARD, **half}),
        html.Div([dcc.Graph(figure=gene_fig)], style={**CARD, **half}),
    ])


def _trade_tab():
    _, prices, _ = ORG.scanner.snapshot()
    st = ORG.engine.stats(prices)
    s = ORG.state

    stat_cards = html.Div([
        _stat("سرمایه", f"${st['equity']:.2f}"),
        _stat("سود تحقق‌یافته", f"${st['realized']:.2f}"),
        _stat("سود شناور", f"${st['unrealized']:.2f}"),
        _stat("نرخ برد", f"{st['win_rate']:.1f}%"),
        _stat("برد/باخت", f"{st['wins']}/{st['losses']}"),
        _stat("موقعیت باز", f"{st['open']}/{MAX_OPEN_TOTAL}"),
        _stat("کارمزد", f"${st['commission']:.2f}"),
    ], style={"display": "flex", "flexWrap": "wrap", "justifyContent": "center"})

    tbl = {"width": "100%", "borderCollapse": "collapse", "textAlign": "center"}

    # رادار قوی‌ترین سیگنال‌های این تیک
    sig_rows = [html.Tr([html.Th(x) for x in
                ["نماد", "جهت", "یقین شورا", "توافق", "رژیم", "قیمت"]])]
    for c in s.get("top_signals", []):
        col = "#8f8" if c["side"] == 1 else "#f88"
        sig_rows.append(html.Tr([
            html.Td(c["symbol"]),
            html.Td("خرید" if c["side"] == 1 else "فروش", style={"color": col}),
            html.Td(f"{c['conv']:.2f}"),
            html.Td(f"{c['reasons']['agreement']:.0%}"),
            html.Td(c["regime"]),
            html.Td(f"{c['price']:.6g}"),
        ]))

    # موقعیت‌های باز با PnL زنده
    open_rows = [html.Tr([html.Th(x) for x in
                 ["نماد", "جهت", "ورود", "قیمت زنده", "PnL شناور", "TP", "SL", "یقین"]])]
    with ORG.engine.lock:
        plist = list(ORG.engine.positions.values())
    for p in plist:
        pr = prices.get(p["coin"], p["entry"])
        upnl = p["side"] * (pr - p["entry"]) * p["size"]
        col = "#8f8" if upnl >= 0 else "#f88"
        open_rows.append(html.Tr([
            html.Td(p["coin"]),
            html.Td("خرید" if p["side"] == 1 else "فروش"),
            html.Td(f"{p['entry']:.6g}"), html.Td(f"{pr:.6g}"),
            html.Td(f"{upnl:+.3f}$", style={"color": col}),
            html.Td(f"{p['tp']:.6g}"), html.Td(f"{p['sl']:.6g}"),
            html.Td(f"{p.get('conviction', 0):.2f}"),
        ]))

    hist_rows = [html.Tr([html.Th(x) for x in
                 ["نماد", "جهت", "ورود", "خروج", "PnL", "دلیل"]])]
    for coin, side, entry, ex, pnl, reason, in ORG.db.history(30):
        col = "#8f8" if (pnl or 0) >= 0 else "#f88"
        hist_rows.append(html.Tr([
            html.Td(coin), html.Td("خرید" if side == 1 else "فروش"),
            html.Td(f"{entry:.6g}" if entry else "-"),
            html.Td(f"{ex:.6g}" if ex else "-"),
            html.Td(f"{pnl:+.3f}" if pnl is not None else "-", style={"color": col}),
            html.Td(reason or "-"),
        ]))

    return html.Div([
        stat_cards,
        html.Div([html.H4(f"🎯 رادار قوی‌ترین سیگنال‌ها (آستانه‌ی ورود: {ENRY_THRESHOLD})"),
                  html.Table(sig_rows, style=tbl)], style=CARD),
        html.Div([html.H4("موقعیت‌های باز (هر ارز فقط یک موقعیت)"),
                  html.Table(open_rows, style=tbl)], style=CARD),
        html.Div([html.H4("تاریخچه‌ی معاملات"),
                  html.Table(hist_rows, style=tbl)], style=CARD),
    ])


def _stat(title, value):
    return html.Div([html.Div(title, style={"color": "#9ab", "fontSize": "13px"}),
                     html.Div(value, style={"fontSize": "20px", "fontWeight": "bold"})],
                    style={**CARD, "minWidth": "120px", "textAlign": "center"})


if __name__ == "__main__":
    print(f"🧬 ارگانیسم زنده شد | DNA={ORG.genome.dna_id}")
    print(f"→ کهکشان: {UNIVERSE_SIZE} ارز | {N_SENSES} حس | شورای {N_MINDS} ذهن")
    print(f"→ http://{HOST}:{PORT}  (Paper trading)")
    app.run(host=HOST, port=PORT, debug=False)
