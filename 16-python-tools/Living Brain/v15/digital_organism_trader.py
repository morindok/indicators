# -*- coding: utf-8 -*-
"""
🧬 GENOME TRADER ORGANISM — ارگانیسم دیجیتال معامله‌گر (نسخه‌ی ارتقایافته)
===============================================================================
ویژگی‌ها:
- اسکن زنده‌ی ۱۰۰ جفت‌ارز برتر USDT بر اساس حجم ۲۴ساعته از Bybit
- fallback آفلاین امن (کش/داده‌ی مصنوعی) بدون کرش
- قلب با ضربان فیبوناچی، مغز تقویتی، DNA 64 جفتی، هورمون‌ها، کرونوکلاک
- سیستم ایمنی، گوارش/متابولیسم، حافظه‌ی کوتاه/بلندمدت، رفلکس، اسکلت خطاپذیری
- تحلیل چندتایم‌فریمی 1m/5m/15m/1h و تصمیم‌سازی ensemble
- Paper trading با سرمایه‌ی 500 دلار، لوریج 20x، کمیسیون/اسپرد
- Dash + dash-bootstrap-components v2.x + Plotly

نکته: این برنامه سفارش واقعی ارسال نمی‌کند.
"""

import os
import random
import json
import time
from collections import deque
import math
import sqlite3
import threading
import hashlib
import traceback
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import requests
try:
    import dash
    from dash import dcc, html, Input, Output
    import dash_bootstrap_components as dbc
    import plotly.graph_objects as go
except Exception:  # pragma: no cover - sandbox may miss UI deps
    class _Stub:  # minimal placeholder for import-only verification
        def __getattr__(self, name):
            return self
        def __call__(self, *args, **kwargs):
            return self
        def __iter__(self):
            return iter(())
    dash = _Stub()
    dcc = html = Input = Output = _Stub()
    class _Theme: CYBORG = None
    class _DBC(_Stub):
        themes = _Theme()
        def Table(self, *args, **kwargs): return self
        def Card(self, *args, **kwargs): return self
        def CardBody(self, *args, **kwargs): return self
        def Row(self, *args, **kwargs): return self
        def Col(self, *args, **kwargs): return self
        def Alert(self, *args, **kwargs): return self
    dbc = _DBC()
    class _GoStub(_Stub):
        class Figure:
            def __init__(self, *a, **k): pass
            def add_trace(self, *a, **k): pass
            def add_hline(self, *a, **k): pass
            def update_layout(self, *a, **k): pass
    go = _GoStub()

# =============================================================================
# 0) ثوابت
# =============================================================================
BG, CARD, LINE, TXT, MUT = "#08101d", "#101a2d", "#22324d", "#e8ecf4", "#8fa3c0"
GOLD, UP, DN, NEON = "#f0b90b", "#16d09a", "#e74c3c", "#7b61ff"

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "organism.db")
START_EQUITY = 500.0
LEVERAGE = 20.0
TAKER_FEE = 0.00055
SPREAD = 0.0002
MAX_POSITIONS = 5
SCAN_REFRESH_BEATS = 8          # هر N ضربان یک‌بار یونیورس بازاسکن شود
MAX_SCAN_CANDIDATES = 20        # از 100 تای برتر، فقط بهترین‌ها وارد پردازش عمیق شوند
MAX_API_CALLS_PER_MIN = 50      # «ریه» نرخ API
DEFAULT_INTERVALS = ["1m", "5m", "15m", "1h"]
BASE_UNIVERSE_FALLBACK = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT"]

REST_CANDIDATES = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.bybit.com/",
})
_ACTIVE_REST_BASE = {"url": None}

# Bybit v5 interval values; accepts both the app's notation and v5 notation.
BYBIT_INTERVALS = {"1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
                   "1h": "60", "2h": "120", "4h": "240", "1d": "D", "D": "D",
                   "1": "1", "3": "3", "5": "5", "15": "15", "30": "30",
                   "60": "60", "120": "120", "240": "240"}

def bybit_get(path, params, timeout=10):
    cands = ([_ACTIVE_REST_BASE["url"]] if _ACTIVE_REST_BASE["url"] else []) + \
            [b for b in REST_CANDIDATES if b != _ACTIVE_REST_BASE["url"]]
    last_error = None
    for base in cands:
        try:
            r = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code in (403, 451):
                last_error = f"HTTP {r.status_code} via {base}"
                continue
            r.raise_for_status()
            d = r.json()
            if d.get("retCode") == 0:
                _ACTIVE_REST_BASE["url"] = base
                return d
            last_error = f"Bybit retCode={d.get('retCode')} retMsg={d.get('retMsg', '')}"
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            continue
    try:
        if ORG is not None:
            ORG.last_error = f"bybit_get: {last_error or 'all REST candidates failed'}"
    except Exception:
        pass
    return None



ORGANISM_BUILD = 'scalp-force-v6'
SCALP_MODE = True
SCALP_MAX_IDLE = 45
SCALP_MIN_INTUITION = 0.15
SCALP_COOLDOWN = 20
DECISION_TRACE = deque(maxlen=60)
def trace(symbol, stage, detail=""):
    msg = f"{time.strftime('%H:%M:%S')} {symbol} BLOCKED@{stage} {detail}"
    DECISION_TRACE.append(msg)
    print(msg, flush=True)


DB_LOCK = threading.Lock()
STATE_LOCK = threading.RLock()
UI_STATE = {
    "ready": False,
    "beats": 0,
    "heartbeat": {},
    "clock": {},
    "hormones": {},
    "open_positions": [],
    "top_universe": [],
    "latest_btc_klines": [],
    "equity_history": [],
    "senses": {},
}


def now_utc():
    return datetime.now(timezone.utc)


def utc_str(dt=None):
    return (dt or now_utc()).strftime("%Y-%m-%d %H:%M:%S")


def clamp(x, lo=0.0, hi=1.0):
    return float(max(lo, min(hi, x)))


def safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


# =============================================================================
# 1) «ریه» API / rate limiter
# =============================================================================
class BreathingLimiter:
    def __init__(self, max_calls_per_min=MAX_API_CALLS_PER_MIN):
        self.max_calls_per_min = max_calls_per_min
        self.calls = []
        self.lock = threading.Lock()

    def allow(self, weight=1):
        with self.lock:
            t = time.time()
            self.calls = [x for x in self.calls if t - x < 60]
            if len(self.calls) + weight <= self.max_calls_per_min:
                self.calls.extend([t] * weight)
                return True
            return False

    def wait_hint(self):
        with self.lock:
            t = time.time()
            self.calls = [x for x in self.calls if t - x < 60]
            if not self.calls:
                return 0.0
            return max(0.0, 60 - (t - min(self.calls)))


LUNGS = BreathingLimiter()


# =============================================================================
# 2) دیتابیس و مایگریشن‌ها
# =============================================================================
def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn, table):
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return [r[1] for r in rows]
    except Exception:
        return []


def _ensure_column(conn, table, col_def):
    name = col_def.split()[0]
    cols = _table_columns(conn, table)
    if name not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")


def init_db():
    with DB_LOCK, db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS identity(
            id INTEGER PRIMARY KEY CHECK(id=1),
            dna TEXT, genome TEXT, born TEXT, brain BLOB
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS trades(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            side TEXT,
            qty REAL,
            entry REAL,
            exit REAL,
            tp REAL,
            sl REAL,
            margin REAL,
            notional REAL,
            status TEXT,
            pnl REAL,
            confidence REAL,
            regime TEXT,
            opened TEXT,
            closed TEXT,
            features TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS equity(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            equity REAL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS mind(
            k TEXT PRIMARY KEY,
            v TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS memory(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            kind TEXT,
            payload TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS scanner_cache(
            id INTEGER PRIMARY KEY CHECK(id=1),
            ts TEXT,
            payload TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS experiences(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            symbol TEXT,
            side TEXT,
            payload TEXT
        )""")

        # migration/extension without destructive reset
        for col in [
            "mark REAL", "position_units REAL", "position_notional REAL", "entry_confidence REAL",
            "entry_brain_signal TEXT", "entry_hormones TEXT", "risk_status TEXT",
            "entry_mark REAL", "liquidation_price REAL", "entry_timeframe TEXT", "scan_rank INTEGER",
            "entry_fee REAL", "spread_cost REAL", "current_price REAL", "exit_reason TEXT", "reason TEXT", "intuition REAL"
        ]:
            _ensure_column(c, "trades", col)

        c.commit()


def mind_get(k, default=None):
    with DB_LOCK, db() as c:
        row = c.execute("SELECT v FROM mind WHERE k=?", (k,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["v"])
    except Exception:
        return row["v"]


def mind_set(k, v):
    with DB_LOCK, db() as c:
        c.execute(
            "INSERT INTO mind(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (k, json.dumps(v, ensure_ascii=False)),
        )
        c.commit()


def memory_add(kind, payload):
    with DB_LOCK, db() as c:
        c.execute("INSERT INTO memory(ts,kind,payload) VALUES(?,?,?)", (utc_str(), kind, json.dumps(payload, ensure_ascii=False)))
        c.commit()


def save_scanner_cache(payload):
    with DB_LOCK, db() as c:
        c.execute("INSERT INTO scanner_cache(id,ts,payload) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET ts=excluded.ts,payload=excluded.payload",
                  (utc_str(), json.dumps(payload, ensure_ascii=False)))
        c.commit()


def load_scanner_cache():
    with DB_LOCK, db() as c:
        row = c.execute("SELECT payload FROM scanner_cache WHERE id=1").fetchone()
    if not row:
        return None
    try:
        return json.loads(row["payload"])
    except Exception:
        return None


# =============================================================================
# 3) ژنوم، DNA، مغز
# =============================================================================
GENE_NAMES = [
    "risk_appetite", "patience", "aggression", "confidence_threshold",
    "tp_atr_mult", "sl_atr_mult", "trend_bias", "meanrev_bias",
    "volume_sensitivity", "learning_rate", "greed", "fear_control",
]
BASES = "ATGC"


def platform_id():
    try:
        import platform
        return platform.node()
    except Exception:
        return "host"


def _fib_word(n_chars):
    a, b = "0", "01"
    while len(b) < n_chars:
        a, b = b, b + a
    return b[:n_chars]


def build_genome(seed):
    rng = np.random.default_rng(seed)
    genes = {g: float(np.round(rng.uniform(0.25, 0.85), 4)) for g in GENE_NAMES}
    genes["confidence_threshold"] = float(np.round(rng.uniform(0.55, 0.72), 4))
    genes["tp_atr_mult"] = float(np.round(rng.uniform(1.15, 2.4), 3))
    genes["sl_atr_mult"] = float(np.round(rng.uniform(0.85, 1.5), 3))
    genes["learning_rate"] = float(np.round(rng.uniform(0.02, 0.08), 4))
    return genes


def build_dna_ladder(seed, pairs=64):
    rng = np.random.default_rng(seed + 777)
    comp = {"A": "T", "T": "A", "G": "C", "C": "G"}
    left = "".join(rng.choice(list(BASES)) for _ in range(pairs))
    right = "".join(comp[b] for b in left)
    return left, right


class Brain:
    def __init__(self, n_features, seed, weights=None):
        self.n_features = n_features
        cpu = os.cpu_count() or 4
        budget = max(32, int(cpu * 128))
        h1 = max(24, int(budget * 0.55))
        h2 = max(12, int(budget * 0.35))
        self.layout = [n_features, h1, h2, 3]
        self.total_neurons = sum(self.layout)
        self.n_synapses = sum(self.layout[i] * self.layout[i + 1] for i in range(len(self.layout) - 1))
        rng = np.random.default_rng(seed + 4242)
        if weights is not None:
            self.W = [np.array(w, dtype=np.float64) for w in weights]
        else:
            self.W = []
            for i in range(len(self.layout) - 1):
                fan = self.layout[i]
                self.W.append(rng.standard_normal((self.layout[i], self.layout[i + 1])) / math.sqrt(max(1, fan)))

    def forward(self, x):
        a = np.asarray(x, dtype=np.float64)
        for i, w in enumerate(self.W):
            a = a @ w
            if i < len(self.W) - 1:
                a = np.tanh(a)
        a = np.asarray(a, dtype=np.float64)
        e = np.exp(a - np.max(a))
        return e / (e.sum() + 1e-12)

    def reinforce(self, x, action_idx, reward, lr):
        x = np.asarray(x, dtype=np.float64)
        acts = [x]
        a = x
        for i, w in enumerate(self.W):
            z = a @ w
            a = np.tanh(z) if i < len(self.W) - 1 else z
            acts.append(a)
        p = self.forward(x)
        target = p.copy()
        sig = np.tanh(reward)
        target[action_idx] += lr * sig * (1 - p[action_idx])
        target = np.clip(target, 1e-6, None)
        target /= target.sum()
        grad = (p - target)
        self.W[-1] -= lr * np.outer(acts[-2], grad)

    def serialize(self):
        return json.dumps([w.tolist() for w in self.W], ensure_ascii=False)


# =============================================================================
# 4) هورمون‌ها، قلب، کرونوکلاک، سیستم ایمنی، حافظه
# =============================================================================
HORMONES = ["dopamine", "cortisol", "adrenaline", "serotonin", "oxytocin", "testosterone", "melatonin", "endorphin"]


def default_hormones():
    return {h: 0.5 for h in HORMONES}


def update_hormones(h, recent_wins, recent_losses, volatility, session_liquidity, win_streak):
    h = dict(h)
    h["dopamine"] = clamp(0.4 + 0.09 * recent_wins - 0.05 * recent_losses)
    h["cortisol"] = clamp(0.28 + 0.12 * recent_losses - 0.05 * recent_wins)
    h["adrenaline"] = clamp(0.25 + volatility)
    h["serotonin"] = clamp(0.55 + 0.05 * (recent_wins - recent_losses))
    h["testosterone"] = clamp(0.4 + 0.08 * win_streak)
    h["melatonin"] = clamp(1.0 - session_liquidity)
    h["oxytocin"] = clamp(0.5 + 0.03 * recent_wins)
    h["endorphin"] = clamp(0.45 + 0.06 * recent_wins - 0.03 * recent_losses)
    return h


def chronoclock():
    now = now_utc()
    hour = now.hour + now.minute / 60.0
    if 0 <= hour < 8:
        session, liq = "آسیا", 0.6
    elif 8 <= hour < 13:
        session, liq = "لندن", 0.9
    elif 13 <= hour < 17:
        session, liq = "همپوشانی لندن/نیویورک", 1.0
    elif 17 <= hour < 21:
        session, liq = "نیویورک", 0.85
    else:
        session, liq = "اواخر آمریکا", 0.5
    return {"utc": utc_str(now), "session": session, "liquidity": liq, "hour": round(hour, 2)}


def _heartbeat_from_beats(beats):
    word = _fib_word(4181)
    bit = word[beats % len(word)]
    bpm = 62 + (18 if bit == "1" else 0)
    return {"beats": beats, "bit": bit, "bpm": bpm, "genome_char": BASES[beats % 4]}


def snapshot_ui_state():
    with STATE_LOCK:
        snap = dict(UI_STATE)
        snap["heartbeat"] = dict(UI_STATE.get("heartbeat", {}))
        snap["clock"] = dict(UI_STATE.get("clock", {}))
        snap["hormones"] = dict(UI_STATE.get("hormones", {}))
        snap["open_positions"] = [dict(x) for x in UI_STATE.get("open_positions", [])]
        snap["top_universe"] = [dict(x) for x in UI_STATE.get("top_universe", [])]
        snap["latest_btc_klines"] = [dict(x) for x in UI_STATE.get("latest_btc_klines", [])]
        snap["equity_history"] = [dict(x) for x in UI_STATE.get("equity_history", [])]
        snap["senses"] = dict(UI_STATE.get("senses", {}))
        return snap


def publish_ui_state(**updates):
    with STATE_LOCK:
        for key, value in updates.items():
            if key in ("heartbeat", "clock", "hormones", "senses") and isinstance(value, dict):
                UI_STATE[key] = dict(value)
            elif key in ("open_positions", "top_universe", "latest_btc_klines", "equity_history") and isinstance(value, list):
                UI_STATE[key] = [dict(x) for x in value]
            else:
                UI_STATE[key] = value


def heartbeat_state():
    snap = snapshot_ui_state()
    beats = int(snap.get("beats") or snap.get("heartbeat", {}).get("beats") or 0)
    hb = snap.get("heartbeat") or _heartbeat_from_beats(beats)
    return hb


def current_drawdown():
    with DB_LOCK, db() as c:
        rows = c.execute("SELECT equity FROM equity ORDER BY id").fetchall()
    if not rows:
        return 0.0, START_EQUITY
    eqs = [float(r["equity"]) for r in rows]
    peak = max(eqs)
    cur = eqs[-1]
    if peak <= 0:
        return 0.0, cur
    return max(0.0, (peak - cur) / peak), cur


def recent_perf(n=15):
    with DB_LOCK, db() as c:
        rows = c.execute("SELECT pnl FROM trades WHERE status='CLOSED' ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    pnls = [float(r["pnl"] or 0) for r in rows]
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p <= 0)
    streak = 0
    for p in pnls:
        if p > 0:
            streak += 1
        else:
            break
    return wins, losses, streak


def win_rate():
    with DB_LOCK, db() as c:
        rows = c.execute("SELECT pnl FROM trades WHERE status='CLOSED'").fetchall()
    if not rows:
        return 0.0, 0
    wins = sum(1 for r in rows if float(r["pnl"] or 0) > 0)
    return round(100 * wins / len(rows), 1), len(rows)


def open_positions():
    with DB_LOCK, db() as c:
        rows = c.execute("SELECT * FROM trades WHERE status='OPEN' ORDER BY id ASC").fetchall()
    return [dict(r) for r in rows]


def current_equity():
    with DB_LOCK, db() as c:
        row = c.execute("SELECT equity FROM equity ORDER BY id DESC LIMIT 1").fetchone()
    return float(row["equity"] if row else START_EQUITY)


def push_equity(eq):
    with DB_LOCK, db() as c:
        c.execute("INSERT INTO equity(ts,equity) VALUES(?,?)", (utc_str(), float(eq)))
        c.commit()


def persist_hormones(h):
    mind_set("hormones", h)


def short_memory_add(item, limit=120):
    mem = mind_get("short_memory", []) or []
    mem.append(item)
    mem = mem[-limit:]
    mind_set("short_memory", mem)


def long_memory_add(item):
    memory_add("long", item)
    count = int(mind_get("long_memory_count", 0) or 0) + 1
    mind_set("long_memory_count", count)


# =============================================================================
# 5) Bybit v5 REST + fallback آفلاین
# ============================================================================
def bybit_klines(symbol, interval, category="linear", limit=200):
    d = bybit_get("/v5/market/kline", {"category": category, "symbol": symbol,
                                        "interval": BYBIT_INTERVALS.get(str(interval), str(interval)),
                                        "limit": limit})
    rows = (d or {}).get("result", {}).get("list", [])
    if not rows:
        return pd.DataFrame()
    try:
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
        df["ts"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms", utc=True)
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="raise").astype(float)
        return df[["ts", "open", "high", "low", "close", "volume"]].sort_values("ts").reset_index(drop=True)
    except Exception as e:
        try: ORG.last_error = f"bybit_klines: {e}"
        except Exception: pass
        return pd.DataFrame()

def _symbol_seed(symbol):
    return int(hashlib.sha256(symbol.encode("utf-8")).hexdigest(), 16) % (2**31)

def synthetic_ohlcv(symbol, interval="5m", limit=200):
    seed = _symbol_seed(symbol + interval); rng = np.random.default_rng(seed)
    now = pd.Timestamp.utcnow().floor("min")
    step = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}.get(interval, 5)
    base = 100 + (seed % 5000) / 100.0; prices = [base]
    for _ in range(limit - 1): prices.append(max(0.0001, prices[-1] * (1 + rng.normal(((seed % 23)-11)/100000.0, 0.002+(seed%17)/10000.0))) )
    prices = np.array(prices); op = np.roll(prices, 1); op[0] = prices[0]
    hi = np.maximum(op, prices) * (1 + np.abs(rng.normal(0.0008, 0.0004, size=limit)))
    lo = np.minimum(op, prices) * (1 - np.abs(rng.normal(0.0008, 0.0004, size=limit)))
    volu = np.abs(rng.normal(1000, 300, size=limit)) * (1 + np.linspace(0, 1, limit))
    return pd.DataFrame({"ts": pd.date_range(end=now, periods=limit, freq=f"{step}min"), "open": op, "high": hi, "low": lo, "close": prices, "volume": volu})

def fetch_klines(symbol, interval="5m", limit=200):
    try:
        df = bybit_klines(symbol, interval, category="linear", limit=limit)
        return df if not df.empty else synthetic_ohlcv(symbol, interval, limit)
    except Exception as e:
        try: ORG.last_error = f"fetch_klines: {e}"
        except Exception: pass
        return synthetic_ohlcv(symbol, interval, limit)

def fetch_all_24hr():
    d = bybit_get("/v5/market/tickers", {"category": "linear"})
    rows = (d or {}).get("result", {}).get("list", [])
    return rows or None

def refresh_top_universe(force=False):
    cached = load_scanner_cache() or {}; last = cached.get("ts")
    if not force and last:
        try:
            if (now_utc() - datetime.fromisoformat(last)).total_seconds() < 180: return cached
        except Exception as e:
            try: ORG.last_error = f"universe_cache: {e}"
            except Exception: pass
    tickers = fetch_all_24hr()
    if tickers:
        pairs = []
        for t in tickers:
            s = t.get("symbol", "")
            if not s.endswith("USDT") or any(x in s for x in ["UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT"]): continue
            quote = safe_float(t.get("turnover24h", 0.0)); change = safe_float(t.get("price24hPcnt", 0.0)) * 100
            last_price = safe_float(t.get("lastPrice", 0.0)); vol = safe_float(t.get("volume24h", 0.0))
            pairs.append({"symbol": s, "quoteVolume": quote, "changePct": change, "lastPrice": last_price, "volume": vol,
                          "score": math.log10(quote + 10.0) + abs(change) * 0.02 + math.log10(vol + 10.0) * 0.2})
        pairs.sort(key=lambda x: x["quoteVolume"], reverse=True); top = pairs[:100]
        if top:
            payload = {"ts": utc_str(), "universe": top}; save_scanner_cache(payload); mind_set("top_universe", top); return payload
    cached_top = cached.get("universe") or mind_get("top_universe", []) or []
    if not cached_top: cached_top = [{"symbol": s, "quoteVolume": 0.0, "changePct": 0.0, "lastPrice": 0.0, "volume": 0.0, "score": 0.0} for s in BASE_UNIVERSE_FALLBACK]
    payload = {"ts": utc_str(), "universe": cached_top}; save_scanner_cache(payload); mind_set("top_universe", cached_top); return payload

def get_mark_price(symbol, fallback_df=None):
    d = bybit_get("/v5/market/tickers", {"category": "linear", "symbol": symbol})
    rows = (d or {}).get("result", {}).get("list", [])
    if rows and rows[0].get("lastPrice") is not None: return safe_float(rows[0]["lastPrice"], None)
    if fallback_df is not None and not fallback_df.empty: return float(fallback_df["close"].iloc[-1])
    return None


# =============================================================================
# 6) بدن/حواس/گوارش: تحلیل چندتایم‌فریمی و ensemble
# =============================================================================
def _ema(a, n):
    return pd.Series(a).ewm(span=n, adjust=False).mean().to_numpy()


def _rsi(close, n=14):
    d = np.diff(close, prepend=close[0])
    up = np.clip(d, 0, None)
    dn = -np.clip(d, None, 0)
    ru = pd.Series(up).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    rd = pd.Series(dn).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    rs = ru / (rd + 1e-12)
    return 100 - 100 / (1 + rs)


def _atr(df, n=14):
    h, l, c = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    pc = np.roll(c, 1)
    pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def _structure_break(c):
    if len(c) < 20:
        return 0.0
    hi = np.max(c[-20:-1])
    lo = np.min(c[-20:-1])
    if c[-1] > hi:
        return 1.0
    if c[-1] < lo:
        return -1.0
    return 0.0


def metabolize(df):
    if df is None or df.empty or len(df) < 40:
        return None
    c = df["close"].to_numpy()
    o = df["open"].to_numpy()
    v = df["volume"].to_numpy()
    price = c[-1]
    ema_f, ema_s = _ema(c, 9), _ema(c, 26)
    rsi = _rsi(c)
    atr = _atr(df)
    ret1 = c[-1] / c[-2] - 1
    ret5 = c[-1] / c[-6] - 1 if len(c) >= 6 else ret1
    trend = (ema_f[-1] - ema_s[-1]) / (price + 1e-12)
    atr_pct = atr[-1] / (price + 1e-12)
    momentum = np.tanh((rsi[-1] - 50) / 18)
    is_buy = c >= o
    win = min(30, len(c))
    vb = v[-win:][is_buy[-win:]].sum()
    vs = v[-win:][~is_buy[-win:]].sum()
    vdelta = (vb - vs) / (vb + vs + 1e-12)
    slope = (ema_s[-1] - ema_s[max(0, -10)]) / (price + 1e-12)
    z = (ret1 - np.mean(np.diff(c[-30:]) / c[-31:-1])) / (np.std(np.diff(c[-30:]) / c[-31:-1]) + 1e-12) if len(c) > 31 else 0.0
    energy = float(np.tanh((abs(trend) * 140 + abs(vdelta) * 1.8 + abs(z) * 0.35 + atr_pct * 35) / 3))
    regime = "TREND" if abs(slope) / (atr_pct + 1e-12) > 1.0 else "RANGE"
    struct = _structure_break(c)
    sense = {
        "trend": float(np.tanh(trend * 180)),
        "momentum": float(momentum),
        "volatility": float(np.tanh(atr_pct * 100)),
        "orderflow": float(vdelta),
        "structure": float(struct),
        "anomaly": float(np.tanh(abs(z) / 3)),
    }
    return {
        "price": float(price),
        "atr": float(atr[-1]),
        "rsi": float(rsi[-1]),
        "trend": float(trend),
        "momentum": float(momentum),
        "vdelta": float(vdelta),
        "slope": float(slope),
        "zscore": float(z),
        "energy": energy,
        "regime": regime,
        "structure": float(struct),
        "senses": sense,
        "ret1": float(ret1),
        "ret5": float(ret5),
        "atr_pct": float(atr_pct),
    }


def perceive_bundle(df_map):
    """خروجی 12 ویژگی برای سازگاری با brain قدیمی/جدید."""
    if not df_map or not all(k in df_map for k in DEFAULT_INTERVALS):
        return None
    b1, b5, b15, b60 = (df_map[k] for k in DEFAULT_INTERVALS)
    p1, p5, p15, p60 = (metabolize(x) for x in (b1, b5, b15, b60))
    if not all([p1, p5, p15, p60]):
        return None
    # 12 ویژگی: 4 بازده / 1 روند / 1 مومنتوم / 1 orderflow / 1 structure / 1 anomaly / 1 انرژی / 1 هورمون-رها
    feats = np.array([
        np.tanh(p1["ret1"] * 120),
        np.tanh(p5["ret1"] * 90),
        np.tanh(p15["ret1"] * 70),
        np.tanh(p60["ret1"] * 45),
        np.tanh((p5["trend"] + p15["trend"]) * 120),
        p5["momentum"],
        p5["vdelta"],
        p5["structure"],
        np.tanh(p5["zscore"] / 2),
        p5["energy"],
        np.tanh((p5["atr_pct"] * 120) - 1),
        0.0,
    ], dtype=np.float64)
    senses = {
        "روند": round(abs(p5["senses"]["trend"]) * 100, 1),
        "مومنتوم": round(abs(p5["senses"]["momentum"]) * 100, 1),
        "نوسان": round(abs(p5["senses"]["volatility"]) * 100, 1),
        "اوردرفلو": round(abs(p5["senses"]["orderflow"]) * 100, 1),
        "ساختار": round(abs(p5["senses"]["structure"]) * 100, 1),
        "ناهنجاری": round(abs(p5["senses"]["anomaly"]) * 100, 1),
    }
    return {"feats": feats, "senses": senses, "price": p5["price"], "atr": p5["atr"], "rsi": p5["rsi"], "regime": p5["regime"], "vdelta": p5["vdelta"], "zscore": p5["zscore"], "energy": p5["energy"], "slope": p5["slope"], "structure": p5["structure"], "ret1": p5["ret1"], "ret5": p5["ret5"]}


def current_hormone_risk(h):
    return clamp(0.45 + 0.28 * h["dopamine"] + 0.22 * h["testosterone"] - 0.35 * h["cortisol"] - 0.18 * h["melatonin"])


# =============================================================================
# 7) ارگانیسم
# =============================================================================
class Organism:
    def __init__(self):
        init_db()
        self.n_features = 12
        self.hormones = mind_get("hormones", default_hormones()) or default_hormones()
        self.top_universe = []
        self.cooldown_until = 0.0
        self.synthetic_mode = False
        self.adaptive_threshold = None
        self.last_trade_time = 0.0
        self.trade_count = 0
        self.epsilon = 0.15
        self.symbol_cooldowns = {}
        self.last_error = None
        self._load_or_birth()
        self.scan_cycle = 0
        self.last_scan_refresh = 0
        self._prime_ui_state()

    def _seed(self):
        raw = f"{os.getpid()}-{platform_id()}-organism".encode()
        return int(hashlib.sha256(raw).hexdigest(), 16) % (2**31)

    def _load_or_birth(self):
        with DB_LOCK, db() as c:
            row = c.execute("SELECT * FROM identity WHERE id=1").fetchone()
        seed = self._seed()
        if row:
            self.genome = json.loads(row["genome"])
            self.dna = json.loads(row["dna"])
            self.born = row["born"]
            weights = json.loads(row["brain"]) if row["brain"] else None
            try:
                self.brain = Brain(self.n_features, seed, weights=weights)
            except Exception:
                self.brain = Brain(self.n_features, seed)
        else:
            self.genome = build_genome(seed)
            left, right = build_dna_ladder(seed)
            self.dna = {"left": left, "right": right}
            self.born = utc_str()
            self.brain = Brain(self.n_features, seed)
            with DB_LOCK, db() as c:
                c.execute("INSERT INTO identity(id,dna,genome,born,brain) VALUES(1,?,?,?,?)",
                          (json.dumps(self.dna, ensure_ascii=False), json.dumps(self.genome, ensure_ascii=False), self.born, self.brain.serialize()))
                c.commit()

    def save_brain(self):
        with DB_LOCK, db() as c:
            c.execute("UPDATE identity SET brain=? WHERE id=1", (self.brain.serialize(),))
            c.commit()

    def save_identity(self):
        with DB_LOCK, db() as c:
            c.execute("UPDATE identity SET dna=?, genome=?, born=?, brain=? WHERE id=1",
                      (json.dumps(self.dna, ensure_ascii=False), json.dumps(self.genome, ensure_ascii=False), self.born, self.brain.serialize()))
            c.commit()

    def _prime_ui_state(self):
        self.cooldown_until = getattr(self, "cooldown_until", 0.0)
        self.last_error = getattr(self, "last_error", None)
        beats = int(mind_get("beats", 0) or 0)
        hb = _heartbeat_from_beats(beats)
        eq = current_equity()
        dd, peak = current_drawdown()
        wr, ntr = win_rate()
        wins, losses, streak = recent_perf()
        open_pos = open_positions()
        price_map = {p["symbol"]: safe_float(p.get("current_price") or p.get("mark") or p.get("entry"), p["entry"]) for p in open_pos}
        unreal = total_unrealized_pnl(open_pos, price_map)
        hist = []
        with DB_LOCK, db() as c:
            rows = c.execute("SELECT ts,equity FROM equity ORDER BY id DESC LIMIT 120").fetchall()
        for r in reversed(rows):
            hist.append({"ts": r["ts"], "equity": float(r["equity"] or START_EQUITY)})
        publish_ui_state(
            ready=True,
            beats=beats,
            heartbeat=hb,
            equity=eq,
            peak_equity=peak,
            drawdown=dd,
            win_rate=wr,
            trade_count=ntr,
            recent_wins=wins,
            recent_losses=losses,
            streak=streak,
            open_positions=open_pos,
            open_positions_count=len(open_pos),
            free_margin=eq - sum(float(p.get("margin", 0)) for p in open_pos),
            margin_usage=(1 - (eq - sum(float(p.get("margin", 0)) for p in open_pos)) / eq) * 100 if eq > 0 else 0.0,
            unrealized_pnl=unreal,
            cooldown_until=self.cooldown_until,
            top_universe=self.top_universe,
            scanner_count=len(self.top_universe or []),
            hormones=self.hormones,
            last_error=self.last_error,
            equity_history=hist or [{"ts": utc_str(), "equity": eq}],
        )

    def refresh_universe(self, force=False):
        payload = refresh_top_universe(force=force)
        self.top_universe = payload.get("universe", []) if payload else []
        self.last_scan_refresh = int(mind_get("beats", 0) or 0)
        publish_ui_state(top_universe=self.top_universe, scanner_count=len(self.top_universe or []))
        return self.top_universe

    def hormones_and_defense(self):
        wins, losses, streak = recent_perf()
        dd, eq = current_drawdown()
        clock = chronoclock()
        vol_proxy = 0.0
        if self.top_universe:
            sample = self.top_universe[: min(10, len(self.top_universe))]
            arr = [safe_float(x.get("changePct", 0.0)) for x in sample]
            vol_proxy = np.std(arr) / 100.0 if arr else 0.0
        self.hormones = update_hormones(self.hormones, wins, losses, clamp(vol_proxy), clock["liquidity"], streak)
        persist_hormones(self.hormones)
        defense = {
            "cooldown": streak >= 3,
            "loss_streak": streak,
            "drawdown": dd,
            "dd_block": dd >= 0.25,
            "risk_appetite": current_hormone_risk(self.hormones),
        }
        if defense["cooldown"]:
            self.symbol_cooldowns[getattr(self, "last_trade_symbol", "__global__")] = time.time() + min(90, 15 + 15 * streak)
        publish_ui_state(hormones=self.hormones, cooldown_until=self.cooldown_until, drawdown=dd)
        return defense

    def decide(self, bundle, market_context=None):
        symbol = (market_context or {}).get("symbol", bundle.get("symbol", "?")) if isinstance(market_context or {}, dict) else bundle.get("symbol", "?")
        p = self.brain.forward(bundle["feats"])
        long_s, short_s, hold_s = [float(x) for x in p]
        g = self.genome
        h = self.hormones
        risk_app = current_hormone_risk(h)
        trend = bundle["senses"]["روند"] / 100.0
        orderflow = bundle["senses"]["اوردرفلو"] / 100.0
        anomaly = bundle["senses"]["ناهنجاری"] / 100.0
        structure = bundle["senses"]["ساختار"] / 100.0
        regime = bundle["regime"]
        # ensemble cortex
        trend_long = max(0.0, trend + 0.15 * structure)
        trend_short = max(0.0, -trend + 0.15 * structure)
        if regime == "TREND":
            trend_long *= 1.2 + 0.4 * g["trend_bias"]
            trend_short *= 1.2 + 0.4 * g["trend_bias"]
        else:
            trend_long *= 1.0 + 0.3 * g["meanrev_bias"] if bundle["rsi"] < 45 else 0.9
            trend_short *= 1.0 + 0.3 * g["meanrev_bias"] if bundle["rsi"] > 55 else 0.9
        flow_long = max(0.0, orderflow)
        flow_short = max(0.0, -orderflow)
        brain_long = long_s
        brain_short = short_s
        hormone_long = risk_app * (1 - h["cortisol"] * 0.45)
        hormone_short = risk_app * (1 - h["cortisol"] * 0.45)
        if anomaly > 0.8:
            hold_s += 0.18
        long_score = 0.38 * brain_long + 0.24 * trend_long + 0.16 * flow_long + 0.12 * hormone_long + 0.10 * (1 - anomaly)
        short_score = 0.38 * brain_short + 0.24 * trend_short + 0.16 * flow_short + 0.12 * hormone_short + 0.10 * (1 - anomaly)
        hold_score = 0.30 * hold_s + 0.30 * anomaly + 0.20 * h["melatonin"] + 0.20 * h["cortisol"]
        vec = np.array([long_score, short_score, hold_score], dtype=np.float64)
        vec = vec / (vec.sum() + 1e-12)
        idx = int(np.argmax(vec))
        conf = float(vec[idx])
        base = self.genome["confidence_threshold"]
        idle_min = max(0.0, (time.time() - self.last_trade_time) / 60.0)
        eff_threshold = max(0.30, base - 0.02 * idle_min)
        thr = eff_threshold
        if anomaly > 0.8:
            thr += 0.06
        if h["cortisol"] > 0.75:
            thr += 0.04
        momentum_proxy = clamp(0.6 * trend + 0.4 * orderflow)
        conf_norm = clamp(conf)
        intuition = clamp(0.65 * conf_norm + 0.35 * abs(momentum_proxy))
        side = None
        if idx == 0 and conf >= thr:
            side = "LONG"
        elif idx == 1 and conf >= thr:
            side = "SHORT"
        exploratory = False
        size_factor = 1.0
        if side is None:
            trace(symbol, "threshold", f"conf={conf:.3f} thr={thr:.3f} intuition={intuition:.3f}")
        if side is None and intuition > 0.35 and random.random() < self.epsilon:
            side = "LONG" if momentum_proxy >= 0 else "SHORT"
            exploratory = True
            size_factor = 0.5
        dominant = "trend" if abs(trend) >= abs(orderflow) else "flow"
        reason = f"conf={conf:.2f} thr={thr:.2f} intuition={intuition:.2f}"
        if side:
            reason += f" {side} {dominant}"
        if exploratory:
            reason += " exploratory"
        return {
            "side": side, "conf": conf, "vec": vec.tolist(), "action_idx": idx,
            "thr": thr, "risk_appetite": risk_app, "hold": float(vec[2]),
            "intuition": float(intuition), "reason": reason,
            "exploratory": exploratory, "size_factor": size_factor,
        }


ORG = None


# =============================================================================
# 8) حساب‌داری معاملات
# =============================================================================
def record_trade(t, reason="", intuition=0.0):
    with DB_LOCK, db() as c:
        c.execute(
            """INSERT INTO trades(
                symbol,side,qty,entry,exit,tp,sl,margin,notional,status,pnl,confidence,regime,opened,closed,features,
                mark,position_units,position_notional,entry_confidence,entry_brain_signal,entry_hormones,risk_status,
                entry_mark,liquidation_price,entry_timeframe,scan_rank,entry_fee,spread_cost,current_price,exit_reason,reason,intuition
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                t["symbol"], t["side"], t["qty"], t["entry"], None, t["tp"], t["sl"], t["margin"], t["notional"],
                "OPEN", 0.0, t["confidence"], t.get("regime", ""), t["opened"], None, t.get("features", ""),
                t["entry_mark"], t["position_units"], t["position_notional"], t["entry_confidence"], t["entry_brain_signal"],
                t["entry_hormones"], t["risk_status"], t["entry_mark"], t["liquidation_price"], t.get("entry_timeframe", "5m"),
                t.get("scan_rank", None), t["entry_fee"], t["spread_cost"], t["entry_mark"], None, reason, intuition,
            ),
        )
        c.commit()


def close_trade(trade_id, exit_price, pnl, reason="TP/SL"):
    with DB_LOCK, db() as c:
        c.execute("UPDATE trades SET status='CLOSED', exit=?, pnl=?, closed=?, exit_reason=? WHERE id=?",
                  (exit_price, pnl, utc_str(), reason, trade_id))
        c.commit()


# =============================================================================
# 9) سیستم ایمنی / رفلکس / مدیریت پوزیشن
# =============================================================================
def risk_status_for_position(p, mark_price, total_equity, dd):
    direction = 1 if p["side"] == "LONG" else -1
    pnl = direction * (mark_price - p["entry"]) / p["entry"] * p["notional"]
    roe = (pnl / (p["margin"] + 1e-12)) * 100
    liq = safe_float(p.get("liquidation_price", 0.0), 0.0)
    liq_gap = abs(mark_price - liq) / (mark_price + 1e-12) if liq else 1.0
    if dd >= 0.12:
        return "قرنطینهٔ افت سرمایه"
    if liq and liq_gap < 0.015:
        return "هشدار لیکوییدیشن"
    if roe < -20:
        return "ریسک بالا"
    if abs(pnl) / (total_equity + 1e-12) > 0.08:
        return "بزرگ"
    return "عادی"


def immune_can_open(symbol, bundle, open_pos, defense):
    if defense["dd_block"]:
        trace(symbol, "immune", "drawdown")
        return False, "بلاک افت سرمایه"
    if ORG.symbol_cooldowns.get(symbol, 0) > time.time() or time.time() < ORG.cooldown_until:
        trace(symbol, "cooldown", "symbol/global")
        return False, "کول‌داون پس از باخت"
    if bundle["senses"]["ناهنجاری"] > 95:
        trace(symbol, "immune", "anomaly")
        return False, "قرنطینهٔ ناهنجاری"
    # محدودیت همبستگی ساده: اگر چند پوزیشن هم‌جهت روی بیت/آلت‌ها باز است، از بازکردن جدید جلوگیری کن
    same_side = [p for p in open_pos if p["side"] == "LONG" and bundle["ret1"] > 0 or p["side"] == "SHORT" and bundle["ret1"] < 0]
    if len(same_side) >= 5:
        trace(symbol, "liquidity", "same-side concentration")
        return False, "تراکم هم‌جهت"
    if len(open_pos) >= MAX_POSITIONS:
        trace(symbol, "liquidity", "max positions")
        return False, "ظرفیت پر"
    return True, "مجاز"


def reflex_close_check(p, mark_price):
    direction = 1 if p["side"] == "LONG" else -1
    if p["side"] == "LONG" and mark_price <= p["sl"]:
        return True, "استاپ‌لاس"
    if p["side"] == "SHORT" and mark_price >= p["sl"]:
        return True, "استاپ‌لاس"
    liq = safe_float(p.get("liquidation_price", 0.0), 0.0)
    if liq:
        if p["side"] == "LONG" and mark_price <= liq * 1.01:
            return True, "حفاظت لیکوییدیشن"
        if p["side"] == "SHORT" and mark_price >= liq * 0.99:
            return True, "حفاظت لیکوییدیشن"
    # نزدیک TP را هم به سرعت ببندیم
    if p["side"] == "LONG" and mark_price >= p["tp"]:
        return True, "تیک‌پرافیت"
    if p["side"] == "SHORT" and mark_price <= p["tp"]:
        return True, "تیک‌پرافیت"
    return False, ""


# =============================================================================
# 10) هسته‌ی اسکن و تصمیم‌سازی
# =============================================================================
def evaluate_symbol(symbol, scan_rank=0):
    # دریافت داده‌های چندتایم‌فریمی با fallback
    df_map = {}
    for tf in DEFAULT_INTERVALS:
        try:
            df_map[tf] = fetch_klines(symbol, interval=tf, limit=220 if tf != "1h" else 180)
        except Exception as e:
            try: ORG.last_error = f"evaluate_symbol:{symbol}:{tf}: {e}"
            except Exception: pass
            df_map[tf] = synthetic_ohlcv(symbol, interval=tf, limit=220 if tf != "1h" else 180)
    bundle = perceive_bundle(df_map)
    if not bundle:
        trace(symbol, "data", "empty bundle")
        return None
    if ORG is None:
        trace(symbol, "organism", "ORG unavailable")
        return None
    bundle["symbol"] = symbol
    decision = ORG.decide(bundle, {"symbol": symbol})
    return {
        "symbol": symbol,
        "bundle": bundle,
        "decision": decision,
        "mark_price": bundle["price"],
        "scan_rank": scan_rank,
    }


def total_unrealized_pnl(open_pos, price_map):
    total = 0.0
    for p in open_pos:
        mp = price_map.get(p["symbol"], p.get("mark") or p["entry"])
        direction = 1 if p["side"] == "LONG" else -1
        pnl = direction * (mp - p["entry"]) / p["entry"] * p["notional"]
        total += pnl
    return total


def heartbeat_cycle():
    if ORG is None:
        return
    beats = int(mind_get("beats", 0) or 0) + 1
    mind_set("beats", beats)
    hb = _heartbeat_from_beats(beats)
    clock = chronoclock()
    if hb["beats"] == 1 or hb["beats"] - ORG.last_scan_refresh >= SCAN_REFRESH_BEATS:
        ORG.refresh_universe(force=True)
    elif not ORG.top_universe:
        ORG.refresh_universe(force=False)

    defense = ORG.hormones_and_defense()
    open_pos = open_positions()

    # اسکلت/رفلکس: مدیریت فوری پوزیشن‌های باز قبل از هر تصمیم جدید
    price_map = {}
    for p in open_pos:
        price = get_mark_price(p["symbol"]) or p.get("current_price") or p["entry"]
        price_map[p["symbol"]] = price
        close_now, reason = reflex_close_check(p, price)
        if close_now:
            direction = 1 if p["side"] == "LONG" else -1
            gross = direction * (price - p["entry"]) / p["entry"] * p["notional"]
            fees = p["notional"] * (TAKER_FEE * 2 + SPREAD)
            pnl = gross - fees
            close_trade(p["id"], price, pnl, reason=reason)
            try:
                feats = np.array(json.loads(p["features"])) if p.get("features") else None
                if feats is not None:
                    action_idx = 0 if p["side"] == "LONG" else 1
                    reward = pnl / (p["margin"] + 1e-12)
                    ORG.brain.reinforce(feats, action_idx, reward, ORG.genome["learning_rate"])
                    ORG.save_brain()
            except Exception as e:
                try:
                    ORG.last_error = f"heartbeat_reinforce: {e}"
                except Exception:
                    pass
            long_memory_add({"kind": "close", "symbol": p["symbol"], "pnl": pnl, "reason": reason, "ts": utc_str()})

    # داده‌کاوی/گوارش: از 100 برتر، بهترین‌ها را به‌سرعت تحلیل کن
    universe = ORG.top_universe or ORG.refresh_universe(force=False) or []
    open_pos = open_positions()
    open_syms = {p["symbol"] for p in open_pos}
    free_slots = max(0, MAX_POSITIONS - len(open_pos))
    eq = current_equity()
    dd, _ = current_drawdown()

    candidates = []
    scalp_candidates = []
    for item in universe[:100]:
        symbol = item["symbol"]
        try:
            evaled = evaluate_symbol(symbol, scan_rank=int(item.get("rank", 0) or 0))
            if not evaled:
                trace(symbol, "data", "evaluation rejected")
                continue
            bundle = evaled["bundle"]
            d = evaled["decision"]
            score = 0.52 * d["conf"] + 0.18 * bundle["senses"]["روند"] / 100 + 0.12 * bundle["senses"]["اوردرفلو"] / 100 + 0.08 * bundle["energy"] + 0.10 * d["risk_appetite"]
            candidates.append((score, evaled))
            if bundle.get("price") and d.get("intuition") is not None and d.get("side"):
                scalp_candidates.append((symbol, float(d["intuition"]), float(bundle["price"]), d["side"], evaled))
            short_memory_add({"ts": utc_str(), "symbol": symbol, "score": score, "regime": bundle["regime"], "price": bundle["price"]})
        except Exception as e:
            ORG.last_error = str(e)
            continue

    candidates.sort(key=lambda x: x[0], reverse=True)
    selected = candidates[:MAX_SCAN_CANDIDATES]

    # موقعیت‌های جدید: تا سقف 5
    if free_slots > 0 and (getattr(ORG, "synthetic_mode", False) or clock["liquidity"] >= 0.45) and  (not SCALP_MODE and time.time() < ORG.cooldown_until) == False:
        for score, ev in selected:
            if free_slots <= 0:
                break
            sym = ev["symbol"]
            if sym in open_syms:
                trace(sym, "liquidity", "already open")
                continue
            bundle = ev["bundle"]
            d = ev["decision"]
            can_open, reason = immune_can_open(sym, bundle, open_pos, defense)
            if not can_open:
                continue
            if not d["side"]:
                trace(sym, "threshold", "no side")
                continue
            # position sizing scaled by confidence and hormones
            risk_app = d["risk_appetite"]
            conf = d["conf"]
            scale = clamp(0.25 + conf * 0.95 + 0.35 * risk_app, 0.18, 1.25)
            if d.get("exploratory"):
                scale *= d.get("size_factor", 1.0)
            margin = (eq / MAX_POSITIONS) * scale
            if margin <= 0:
                trace(sym, "liquidity", "margin <= 0")
                continue
            entry = bundle["price"]
            notional = margin * LEVERAGE
            qty = notional / entry
            atr = bundle["atr"]
            if d["side"] == "LONG":
                tp = entry + ORG.genome["tp_atr_mult"] * atr
                sl = entry - ORG.genome["sl_atr_mult"] * atr
                liq = entry * (1 - 1 / LEVERAGE + 0.004)
            else:
                tp = entry - ORG.genome["tp_atr_mult"] * atr
                sl = entry + ORG.genome["sl_atr_mult"] * atr
                liq = entry * (1 + 1 / LEVERAGE - 0.004)
            fee = notional * TAKER_FEE
            spread_cost = notional * SPREAD
            risk_status = "عادی"
            t = {
                "symbol": sym,
                "side": d["side"],
                "qty": qty,
                "entry": entry,
                "tp": tp,
                "sl": sl,
                "margin": margin,
                "notional": notional,
                "confidence": conf,
                "regime": bundle["regime"],
                "opened": utc_str(),
                "features": json.dumps(bundle["feats"].tolist(), ensure_ascii=False),
                "entry_mark": entry,
                "position_units": qty,
                "position_notional": notional,
                "entry_confidence": conf,
                "entry_brain_signal": json.dumps(d["vec"], ensure_ascii=False),
                "entry_hormones": json.dumps(ORG.hormones, ensure_ascii=False),
                "risk_status": risk_status,
                "liquidation_price": liq,
                "entry_timeframe": "ensemble(1m,5m,15m,1h)",
                "scan_rank": int(ev.get("scan_rank") or 0),
                "entry_fee": fee,
                "spread_cost": spread_cost,
            }
            record_trade(t, reason=d.get("reason", reason), intuition=d.get("intuition", 0.0))
            ORG.last_trade_time = time.time()
            ORG.trade_count = getattr(ORG, "trade_count", 0) + 1
            if ORG.trade_count % 20 == 0:
                ORG.epsilon = max(0.05, ORG.epsilon - 0.01)
            open_syms.add(sym)
            free_slots -= 1
            memory_add("open", {"symbol": sym, "side": d["side"], "confidence": conf, "score": score, "ts": utc_str()})

    # اسکالپ اجباری پس از بی‌کاری طولانی: مستقل از گیت‌های ورود عادی
    if SCALP_MODE and scalp_candidates and time.time() - ORG.last_trade_time > SCALP_MAX_IDLE:
        sym, intuition, entry, side, ev = max(scalp_candidates, key=lambda x: x[1])
        if intuition >= SCALP_MIN_INTUITION and ORG.symbol_cooldowns.get(sym, 0) <= time.time() and sym not in open_syms:
            bundle, d = ev["bundle"], ev["decision"]
            margin = max(1.0, eq / MAX_POSITIONS * 0.25)
            notional, qty = margin * LEVERAGE, margin * LEVERAGE / entry
            sl = entry * (1 - 0.003) if side == "LONG" else entry * (1 + 0.003)
            tp = entry * (1 + 0.005) if side == "LONG" else entry * (1 - 0.005)
            liq = entry * (1 - 1 / LEVERAGE + 0.004) if side == "LONG" else entry * (1 + 1 / LEVERAGE - 0.004)
            t = {"symbol": sym, "side": side, "qty": qty, "entry": entry, "tp": tp, "sl": sl, "margin": margin, "notional": notional, "confidence": d["conf"], "regime": bundle["regime"], "opened": utc_str(), "features": json.dumps(bundle["feats"].tolist(), ensure_ascii=False), "entry_mark": entry, "position_units": qty, "position_notional": notional, "entry_confidence": d["conf"], "entry_brain_signal": json.dumps(d["vec"], ensure_ascii=False), "entry_hormones": json.dumps(ORG.hormones, ensure_ascii=False), "risk_status": "عادی", "liquidation_price": liq, "entry_timeframe": "ensemble(1m,5m,15m,1h)", "scan_rank": int(ev.get("scan_rank") or 0), "entry_fee": notional * TAKER_FEE, "spread_cost": notional * SPREAD}
            record_trade(t, reason="forced_scalp", intuition=intuition)
            ORG.last_trade_time = time.time()
            ORG.symbol_cooldowns[sym] = time.time() + SCALP_COOLDOWN
            print(f"FORCED_SCALP {sym} {side} @ {entry}", flush=True)
        else:
            trace(sym, "cooldown", f"scalp intuition={intuition:.3f}")

    # به‌روزرسانی equity و risk status
    with DB_LOCK, db() as c:
        rows = c.execute("SELECT * FROM trades WHERE status='OPEN' ORDER BY id ASC").fetchall()
    current_open = [dict(r) for r in rows]
    for p in current_open:
        price_map[p["symbol"]] = price_map.get(p["symbol"], get_mark_price(p["symbol"]) or p["entry"])
        status = risk_status_for_position(p, price_map[p["symbol"]], eq, dd)
        with DB_LOCK, db() as c:
            c.execute("UPDATE trades SET current_price=?, mark=?, risk_status=? WHERE id=?",
                      (price_map[p["symbol"]], price_map[p["symbol"]], status, p["id"]))
            c.commit()

    # اکویتی شناور را ثبت کن
    unreal = total_unrealized_pnl(current_open, price_map)
    equity_value = eq + unreal
    push_equity(equity_value)
    btc_chart = []
    try:
        btc_df = fetch_klines("BTCUSDT", interval="5m", limit=150)
        if btc_df is not None and not btc_df.empty:
            btc_df = btc_df.tail(150)
            btc_chart = [{"ts": r["ts"].isoformat() if hasattr(r["ts"], "isoformat") else str(r["ts"]), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"]), "volume": float(r["volume"])} for _, r in btc_df.iterrows()]
    except Exception as e:
        try:
            ORG.last_error = f"heartbeat_btc_chart: {e}"
        except Exception:
            pass
        btc_chart = snap.get("latest_btc_klines", []) if 'snap' in locals() else []
    ORG.scan_cycle += 1
    memory_add("heartbeat", {"beats": hb["beats"], "bpm": hb["bpm"], "equity": equity_value, "ts": utc_str()})
    publish_ui_state(
        ready=True,
        beats=beats,
        heartbeat=hb,
        clock=clock,
        equity=equity_value,
        peak_equity=max(peak if 'peak' in locals() else equity_value, equity_value),
        drawdown=dd,
        win_rate=wr if 'wr' in locals() else 0.0,
        trade_count=ntr if 'ntr' in locals() else 0,
        recent_wins=wins if 'wins' in locals() else 0,
        recent_losses=losses if 'losses' in locals() else 0,
        streak=streak if 'streak' in locals() else 0,
        open_positions=current_open,
        open_positions_count=len(current_open),
        free_margin=eq - sum(float(p.get("margin", 0)) for p in current_open),
        margin_usage=((1 - (eq - sum(float(p.get("margin", 0)) for p in current_open)) / eq) * 100) if eq > 0 else 0.0,
        unrealized_pnl=unreal,
        scanner_count=len(ORG.top_universe or []),
        top_universe=ORG.top_universe or [],
        senses=(candidates[0][1]["bundle"]["senses"] if candidates else {}),
        hormones=ORG.hormones,
        cooldown_until=ORG.cooldown_until,
        last_error=ORG.last_error,
        latest_btc_klines=btc_chart,
    )


# =============================================================================
# 11) داشبورد Dash
# =============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])
app.title = "🧬 ارگانیسم دیجیتال معامله‌گر"
server = app.server


def stat_card(title, value, sub="", color=GOLD):
    return dbc.Card(
        dbc.CardBody([
            html.Div(title, style={"color": MUT, "fontSize": 12}),
            html.Div(value, style={"color": color, "fontSize": 22, "fontWeight": "bold"}),
            html.Div(sub, style={"color": MUT, "fontSize": 11}),
        ]),
        style={"background": CARD, "border": f"1px solid {LINE}", "marginBottom": 10},
    )


def bar(label, val, color):
    val = float(val)
    return html.Div([
        html.Div([
            html.Span(label, style={"color": TXT, "fontSize": 12}),
            html.Span(f"{val:.0f}%", style={"color": color, "fontSize": 12, "float": "left"}),
        ]),
        html.Div(html.Div(style={"width": f"{max(2, min(100, val))}%", "height": 8, "background": color, "borderRadius": 4}),
                 style={"background": LINE, "borderRadius": 4, "height": 8, "margin": "3px 0 10px"}),
    ])


app.layout = html.Div([
    html.Div([
        html.Span("🧬 GENOME TRADER ORGANISM", style={"color": GOLD, "fontSize": 22, "fontWeight": "bold"}),
        html.Span(id="heartbeat-badge", style={"color": UP, "marginRight": 16, "float": "left"}),
    ], style={"padding": "12px 20px"}),
    dcc.Tabs(id="tabs", value="bio", children=[
        dcc.Tab(label="🧠 زیست‌سنجی و آگاهی", value="bio", style={"background": CARD, "color": MUT}, selected_style={"background": BG, "color": GOLD}),
        dcc.Tab(label="📈 معاملات زنده", value="trade", style={"background": CARD, "color": MUT}, selected_style={"background": BG, "color": GOLD}),
    ]),
    html.Div(id="tab-content", style={"padding": "16px"}),
    dcc.Interval(id="tick", interval=3000, n_intervals=0),
    dcc.Interval(id="pulse", interval=2000, n_intervals=0),
], style={"background": BG, "minHeight": "100vh", "color": TXT})


def _format_duration(start_utc_str):
    try:
        dt = datetime.strptime(start_utc_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        sec = int((now_utc() - dt).total_seconds())
        if sec < 60:
            return f"{sec} ثانیه"
        if sec < 3600:
            return f"{sec // 60} دقیقه"
        return f"{sec // 3600} ساعت {((sec % 3600) // 60)} دقیقه"
    except Exception:
        return "نامشخص"


def _position_row(p):
    mark = safe_float(p.get("current_price") or p.get("mark") or p.get("entry"), p["entry"])
    direction = 1 if p["side"] == "LONG" else -1
    pnl = direction * (mark - p["entry"]) / p["entry"] * p["notional"]
    pnl_pct = (pnl / (p["margin"] + 1e-12)) * 100
    roe = pnl_pct
    liq = safe_float(p.get("liquidation_price", 0.0), 0.0)
    entry_fee = safe_float(p.get("entry_fee", p["notional"] * TAKER_FEE), 0.0)
    spread_cost = safe_float(p.get("spread_cost", p["notional"] * SPREAD), 0.0)
    current_eq = current_equity()
    dd, _ = current_drawdown()
    risk = p.get("risk_status") or risk_status_for_position(p, mark, current_eq, dd)
    entry_h = p.get("entry_hormones")
    try:
        entry_h = json.dumps(json.loads(entry_h), ensure_ascii=False) if entry_h else ""
    except Exception:
        entry_h = entry_h or ""
    return html.Tr([
        html.Td(p["symbol"], style={"color": TXT, "fontSize": 12}),
        html.Td("لانگ" if p["side"] == "LONG" else "شورت", style={"color": UP if p["side"] == "LONG" else DN, "fontSize": 12}),
        html.Td("20x", style={"color": GOLD, "fontSize": 12}),
        html.Td(f"{p['entry']:.6f}", style={"color": TXT, "fontSize": 12}),
        html.Td(f"{mark:.6f}", style={"color": TXT, "fontSize": 12}),
        html.Td(f"{p['qty']:.6f}", style={"color": TXT, "fontSize": 12}),
        html.Td(f"${p['notional']:.2f}", style={"color": TXT, "fontSize": 12}),
        html.Td(f"${p['margin']:.2f}", style={"color": TXT, "fontSize": 12}),
        html.Td(f"${pnl:+.2f}", style={"color": UP if pnl >= 0 else DN, "fontSize": 12, "fontWeight": "bold"}),
        html.Td(f"{pnl_pct:+.2f}%", style={"color": UP if pnl_pct >= 0 else DN, "fontSize": 12}),
        html.Td(f"{roe:+.2f}%", style={"color": UP if roe >= 0 else DN, "fontSize": 12}),
        html.Td(f"{liq:.6f}" if liq else "-", style={"color": MUT, "fontSize": 12}),
        html.Td(f"{p['sl']:.6f}", style={"color": DN, "fontSize": 12}),
        html.Td(f"{p['tp']:.6f}", style={"color": UP, "fontSize": 12}),
        html.Td(f"${entry_fee:.2f}", style={"color": TXT, "fontSize": 12}),
        html.Td(f"${spread_cost:.2f}", style={"color": TXT, "fontSize": 12}),
        html.Td(p.get("opened", ""), style={"color": TXT, "fontSize": 12}),
        html.Td(_format_duration(p.get("opened", "")), style={"color": TXT, "fontSize": 12}),
        html.Td(f"{safe_float(p.get('entry_confidence', p.get('confidence', 0)))*100:.0f}%", style={"color": GOLD, "fontSize": 12}),
        html.Td(str(p.get("entry_brain_signal", ""))[:90], style={"color": MUT, "fontSize": 12, "maxWidth": 180}),
        html.Td(entry_h[:90], style={"color": MUT, "fontSize": 12, "maxWidth": 180}),
        html.Td(risk, style={"color": NEON if "عادی" in risk else DN if "ریسک" in risk or "هشدار" in risk else GOLD, "fontSize": 12}),
    ])


def render_bio():
    snap = snapshot_ui_state()
    hb = snap.get("heartbeat") or _heartbeat_from_beats(int(snap.get("beats") or 0))
    clock = snap.get("clock") or chronoclock()
    wr = safe_float(snap.get("win_rate", 0.0), 0.0)
    ntr = int(snap.get("trade_count", 0) or 0)
    wins = int(snap.get("recent_wins", 0) or 0)
    losses = int(snap.get("recent_losses", 0) or 0)
    streak = int(snap.get("streak", 0) or 0)
    eq = safe_float(snap.get("equity", START_EQUITY), START_EQUITY)
    peak = safe_float(snap.get("peak_equity", START_EQUITY), START_EQUITY)
    dd = safe_float(snap.get("drawdown", 0.0), 0.0)
    senses = snap.get("senses", {}) or {}
    hormones = snap.get("hormones", default_hormones()) or default_hormones()
    genes_rows = [dbc.Col(stat_card(k, f"{v}", "ژن", NEON), md=3) for k, v in ORG.genome.items()]
    horm_bars = [bar(h.capitalize(), hormones.get(h, 0.5) * 100, UP if hormones.get(h, 0.5) > 0.5 else GOLD) for h in HORMONES]
    sense_bars = [bar(k, v, NEON) for k, v in senses.items()]
    scanner_count = int(snap.get("scanner_count", len(snap.get("top_universe", []))) or 0)
    def_card = stat_card("🛡️ ایمنی", "فعال", f"افت سرمایه {dd*100:.1f}% | کول‌داون تا {int(max(0, snap.get('cooldown_until', 0) - time.time()))} ثانیه", DN if dd > 0.1 else UP)
    mem_short = mind_get("short_memory", []) or []
    last_mem = mem_short[-1] if mem_short else {}
    return html.Div([
        dbc.Row([
            dbc.Col(stat_card("❤️ ضربان قلب", f"{hb['bpm']} BPM", f"بیت فیبوناچی: {hb['bit']} | ضربان #{hb['beats']}", DN), md=3),
            dbc.Col(stat_card("🧠 نورون‌ها", f"{ORG.brain.total_neurons:,}", f"سیناپس: {ORG.brain.n_synapses:,} | CPU={os.cpu_count()}", NEON), md=3),
            dbc.Col(stat_card("🕒 کرونوکلاک", clock["session"], f"UTC {clock['utc']} | نقدینگی {int(clock['liquidity']*100)}%", GOLD), md=3),
            dbc.Col(stat_card("🩸 جریان ژنوم", hb["genome_char"], "نوکلئوتید در گردش مغز", UP), md=3),
        ]),
        dbc.Row([
            dbc.Col(stat_card("💰 سرمایه", f"${eq:,.2f}", f"پیک ${peak:,.2f} | شروع ${START_EQUITY:.0f}", UP if eq >= START_EQUITY else DN), md=3),
            dbc.Col(stat_card("🎯 وین‌ریت", f"{wr}%", f"{ntr} معامله بسته‌شده", GOLD), md=3),
            dbc.Col(stat_card("🔥 استریک برد", f"{streak}", f"{wins}W / {losses}L اخیر", UP), md=3),
            dbc.Col(stat_card("🌐 اسکنر زنده", f"{scanner_count} نماد", f"Top-100 USDT از Bybit | {(_ACTIVE_REST_BASE.get('url') or 'اتصال در انتظار')}", NEON), md=3),
        ]),
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([html.H6("🔬 حواس چندلایه", style={"color": GOLD})] + sense_bars), style={"background": CARD, "border": f"1px solid {LINE}"}), md=4),
            dbc.Col(dbc.Card(dbc.CardBody([html.H6("🧪 سیستم هورمونی", style={"color": GOLD})] + horm_bars), style={"background": CARD, "border": f"1px solid {LINE}"}), md=4),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H6("🧠 حافظه و ایمنی", style={"color": GOLD}),
                def_card,
                stat_card("🧬 حافظه کوتاه‌مدت", str(len(mem_short)), f"آخرین: {json.dumps(last_mem, ensure_ascii=False)[:90]}", MUT),
                stat_card("🧬 حافظه بلندمدت", f"{mind_get('long_memory_count', 0) or 0}", "تجربه‌های ذخیره‌شده", MUT),
            ]), style={"background": CARD, "border": f"1px solid {LINE}"}), md=4),
        ], style={"marginTop": 10}),
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([html.H6("🧬 نردبان DNA و هویت", style={"color": GOLD}),
                                          html.Div("نردبان DNA (64 جفت):", style={"color": MUT, "fontSize": 12}),
                                          html.Div(ORG.dna["left"], style={"color": UP, "fontFamily": "monospace", "letterSpacing": 2, "fontSize": 12}),
                                          html.Div("|" * len(ORG.dna["left"]), style={"color": MUT, "fontFamily": "monospace", "letterSpacing": 2, "fontSize": 8}),
                                          html.Div(ORG.dna["right"], style={"color": DN, "fontFamily": "monospace", "letterSpacing": 2, "fontSize": 12})]), style={"background": CARD, "border": f"1px solid {LINE}"}), md=4),
            dbc.Col(dbc.Card(dbc.CardBody([html.H6("🛠️ اندام‌های فعال", style={"color": GOLD}),
                                          html.Ul([
                                              html.Li("قلب: Fibonacci heartbeat 62-80 BPM"),
                                              html.Li("مغز: شبکه‌ی CPU-scaled + reinforcement"),
                                              html.Li("ریه: rate limit API"),
                                              html.Li("پوست/حواس: 1m/5m/15m/1h + order-flow proxy"),
                                              html.Li("ایمنی: drawdown / cooldown / correlation limit"),
                                              html.Li("گوارش: تبدیل داده خام به انرژی و ویژگی"),
                                          ], style={"color": TXT})]), style={"background": CARD, "border": f"1px solid {LINE}"}), md=4),
            dbc.Col(dbc.Card(dbc.CardBody([html.H6("🧬 ژن‌های تریدر", style={"color": GOLD})] + [dbc.Row(genes_rows)]), style={"background": CARD, "border": f"1px solid {LINE}"}), md=4),
        ], style={"marginTop": 10}),
    ])


def render_trade():
    snap = snapshot_ui_state()
    open_pos = snap.get("open_positions", []) or []
    wr = safe_float(snap.get("win_rate", 0.0), 0.0)
    ntr = int(snap.get("trade_count", 0) or 0)
    eq = safe_float(snap.get("equity", START_EQUITY), START_EQUITY)
    dd = safe_float(snap.get("drawdown", 0.0), 0.0)
    free_margin = safe_float(snap.get("free_margin", eq), eq)
    margin_usage = safe_float(snap.get("margin_usage", 0.0), 0.0)
    unreal = safe_float(snap.get("unrealized_pnl", 0.0), 0.0)
    summary = [
        stat_card("💰 سرمایه", f"${eq:,.2f}", f"افت سرمایه {dd*100:.1f}%", UP if eq >= START_EQUITY else DN),
        stat_card("🧮 مارجین آزاد", f"${free_margin:,.2f}", f"استفاده {margin_usage:.1f}%", GOLD),
        stat_card("📈 سود شناور", f"${unreal:+.2f}", f"کل بازده باز", UP if unreal >= 0 else DN),
        stat_card("🎯 وین‌ریت", f"{wr}%", f"{ntr} معامله بسته‌شده", NEON),
    ]

    eq_fig = go.Figure()
    eq_rows = snap.get("equity_history", []) or []
    if eq_rows:
        eq_fig.add_trace(go.Scatter(x=[r["ts"] for r in eq_rows], y=[r["equity"] for r in eq_rows], mode="lines", line=dict(color=GOLD, width=2), fill="tozeroy", fillcolor="rgba(240,185,11,0.08)"))
    eq_fig.add_hline(y=START_EQUITY, line_dash="dot", line_color=MUT)
    eq_fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD, height=260, margin=dict(l=10, r=10, t=30, b=10), title=dict(text="رشد سرمایه", x=0.5, font=dict(color=GOLD, size=13)))

    cfig = go.Figure()
    latest = snap.get("latest_btc_klines", []) or []
    if latest:
        df = pd.DataFrame(latest)
        cfig.add_trace(go.Candlestick(x=df["ts"], open=df["open"], high=df["high"], low=df["low"], close=df["close"], increasing_line_color=UP, decreasing_line_color=DN))
    cfig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD, height=360, xaxis=dict(gridcolor=LINE, rangeslider_visible=False), yaxis=dict(gridcolor=LINE), margin=dict(l=10, r=10, t=30, b=10), title=dict(text="BTCUSDT — 5m", x=0.5, font=dict(color=GOLD, size=13)))

    headers = ["نماد", "جهت", "لوریج", "ورود", "مارک", "حجم (واحد)", "نوشنل", "مارجین", "PnL USD", "PnL %", "ROE %", "لیکوییدیشن", "استاپ", "تیک‌پرافیت", "کارمزد", "اسپرد", "ورود UTC", "مدت نگهداری", "اطمینان ورود", "سیگنال مغز", "هورمون‌های ورود", "ریسک"]
    header = html.Tr([html.Th(h, style={"color": MUT, "fontSize": 12}) for h in headers])
    rows = [_position_row(p) for p in open_pos]
    trades_table = dbc.Table([html.Thead(header), html.Tbody(rows)], bordered=False, color="dark", hover=True, responsive=True)
    if not open_pos:
        trades_table = dbc.Alert("هیچ پوزیشن بازی نداریم؛ ارگانیسم در کمین فرصت مناسب است.", color="secondary", style={"fontSize": 13})

    return html.Div([
        dbc.Row([dbc.Col(x, md=3) for x in summary]),
        dbc.Row([dbc.Col(dcc.Graph(figure=cfig), md=7), dbc.Col(dcc.Graph(figure=eq_fig), md=5)]),
        dbc.Card(dbc.CardBody([html.H6("📋 جدول کامل پوزیشن‌های باز", style={"color": GOLD}), trades_table]), style={"background": CARD, "border": f"1px solid {LINE}", "marginTop": 10}),
    ])


@app.callback(Output("tab-content", "children"), Input("tabs", "value"), Input("tick", "n_intervals"))
def render_tab(tab, _):
    try:
        if tab == "trade":
            return render_trade()
        return render_bio()
    except Exception as e:
        try:
            if ORG is not None:
                ORG.last_error = str(e)
                publish_ui_state(last_error=str(e))
        except Exception:
            pass
        return dbc.Alert(f"خطا در رندر: {e}", color="danger")


@app.callback(Output("heartbeat-badge", "children"), Input("pulse", "n_intervals"))
def pulse(_):
    try:
        snap = snapshot_ui_state()
        hb = snap.get("heartbeat") or _heartbeat_from_beats(int(snap.get("beats") or 0))
        heart = "💗" if hb["bit"] == "1" else "🤍"
        return f"{heart} {hb['bpm']} BPM | ضربان #{hb['beats']} | ژنوم:{hb['genome_char']}"
    except Exception:
        return "در حال پایش..."


# =============================================================================
# 12) حلقه‌ی حیات
# =============================================================================
def life_loop():
    while True:
        try:
            heartbeat_cycle()
        except Exception as e:
            ORG.last_error = str(e)
            print("life_loop error:", e)
            traceback.print_exc(limit=1)
        time.sleep(8)


# =============================================================================
# 13) main
# =============================================================================
def main():
    global ORG
    ORG = Organism()
    init_db()
    ORG.refresh_universe(force=True)
    if current_equity() == START_EQUITY:
        push_equity(START_EQUITY)
    ORG._prime_ui_state()
    threading.Thread(target=life_loop, daemon=True).start()
    print(f"🧬 ارگانیسم متولد شد | نورون‌ها: {ORG.brain.total_neurons:,} | DNA: {ORG.dna['left'][:16]}...")
    app.run(debug=False, host="127.0.0.1", port=8070, use_reloader=False)


if __name__ == "__main__":
    main()
