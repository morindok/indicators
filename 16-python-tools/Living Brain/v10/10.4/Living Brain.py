# -*- coding: utf-8 -*-
"""
HIVE SCALPER-SNIPER PRO — v4 ULTIMATE LEARNING EDITION
لوریج ۲۰× | اسکالپ + اسنایپر | اسکن ~۱۰۰ نماد | حداکثر ۵ پوزیشن
RTL UI | Auto-Evolution | Visual Learning Analytics | Self-Optimizing DNA
"""

import os, time, json, math, sqlite3, hashlib, threading, copy
from datetime import datetime, timezone, timedelta
from collections import deque, defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import dash
from dash import dcc, html, Input, Output, State, ctx
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ──────────────────────────────────────────────────────────────
# رنگ‌ها و استایل
BG, CARD, LINE, TXT, MUT = "#050a14", "#0d1525", "#1a2744", "#e8ecf4", "#6b7f9e"
GOLD, UP, DN, NEON, ACCENT, ORANGE = "#f0b90b", "#00e676", "#ff5252", "#00f5d4", "#7b61ff", "#ff9f1c"
GLASS = "rgba(13,21,37,0.85)"

# ──────────────────────────────────────────────────────────────
# اتصال پایدار بایبیت
REST = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Referer": "https://www.bybit.com/"})
_ACTIVE = {"url": None}
_rate_lock = threading.Lock()
_last_req = 0.0


def bybit_get(path, params, timeout=8):
    global _last_req
    with _rate_lock:
        elapsed = time.time() - _last_req
        if elapsed < 0.07:
            time.sleep(0.07 - elapsed)
        _last_req = time.time()
    cands = ([_ACTIVE["url"]] if _ACTIVE["url"] else []) + [u for u in REST if u != _ACTIVE["url"]]
    for base in cands:
        try:
            r = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code in (403, 451): continue
            r.raise_for_status()
            d = r.json()
            if d.get("retCode") == 0:
                _ACTIVE["url"] = base
                return d
        except Exception:
            continue
    return None


def get_klines(symbol, interval="5", limit=200, category="linear"):
    d = bybit_get("/v5/market/kline", {"category": category, "symbol": symbol, "interval": interval, "limit": limit})
    if not d or "list" not in (d.get("result") or {}):
        return pd.DataFrame()
    lst = d["result"]["list"]
    if not lst:
        return pd.DataFrame()
    df = pd.DataFrame(lst, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
    for c in ["open", "high", "low", "close", "volume", "turnover"]:
        df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)


def get_klines_paginated(symbol, interval="5", total=10000, category="linear"):
    all_rows = {}
    end = None
    while len(all_rows) < total:
        params = {"category": category, "symbol": symbol, "interval": interval, "limit": 1000}
        if end is not None:
            params["end"] = end
        d = bybit_get("/v5/market/kline", params)
        rows = ((d or {}).get("result") or {}).get("list") or []
        if not rows:
            break
        for r in rows:
            all_rows[int(r[0])] = r
        oldest = min(int(r[0]) for r in rows)
        end = oldest - 1
        if len(rows) < 1000:
            break
    if not all_rows:
        return pd.DataFrame()
    rows = [all_rows[k] for k in sorted(all_rows)][-total:]
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms")
    for c in ["open", "high", "low", "close", "volume", "turnover"]:
        df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)


def get_all_tickers():
    d = bybit_get("/v5/market/tickers", {"category": "linear"})
    if not d or not d.get("result", {}).get("list"):
        return {}
    out = {}
    for t in d["result"]["list"]:
        if not t["symbol"].endswith("USDT"):
            continue
        try:
            out[t["symbol"]] = {
                "last": float(t["lastPrice"]),
                "bid": float(t.get("bid1Price") or t["lastPrice"]),
                "ask": float(t.get("ask1Price") or t["lastPrice"]),
                "vol24": float(t.get("volume24h") or 0),
                "turn24": float(t.get("turnover24h") or 0),
                "chg": float(t.get("price24hPcnt") or 0),
            }
        except Exception:
            continue
    return out


# ──────────────────────────────────────────────────────────────
# پارامترهای پایه
LEVERAGE = 20
INITIAL_CAPITAL = 500.0
MAX_POSITIONS = 5
COMMISSION = 0.0006
SPREAD_BPS_DEFAULT = 1.8
SLIPPAGE_BPS = 1.2
MIN_TURNOVER_24H = 1_200_000
MAX_SPREAD_BPS = 4.5
RISK_PER_TRADE_BASE = 0.011
CPU_CORES = os.cpu_count() or 4
NEURON_BASE = CPU_CORES * 3072
AWARENESS_CAP = 0.97  # سقف آگاهی

# ── مسیر و توابع تداوم DNA ────────────────────────────
DNA_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hive_dna_state.json")


def save_dna_state(hive):
    try:
        state = {
            "generation": getattr(hive, "generation", 0),
            "adaptive": hive.adaptive,
            "awareness": hive.awareness,
            "win_streak": getattr(hive, "win_streak", 0),
            "loss_streak": getattr(hive, "loss_streak", 0),
            "organism_weights": {o.name: o.weight for o in hive.orgs},
            "organism_performance": getattr(hive, 'org_performance', {}),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        tmp = DNA_STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, DNA_STATE_PATH)
    except Exception:
        pass


def load_dna_state():
    try:
        with open(DNA_STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────
# دیتابیس پیشرفته + تاریخچه یادگیری
DB_PATH = Path("hive_pro.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT, side TEXT, entry REAL, size_usd REAL, qty REAL,
        leverage INTEGER, liq_price REAL, entry_time TEXT, exit_time TEXT,
        exit_price REAL, pnl REAL, status TEXT, reason TEXT, votes TEXT,
        regime TEXT, features TEXT, partials TEXT, trail_stop REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, symbol TEXT, side TEXT, conv REAL, regime TEXT,
        features TEXT, votes TEXT, accepted INTEGER, reason TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS equity (ts TEXT, equity REAL, open_n INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS backtest_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, symbol TEXT, params TEXT, metrics TEXT)""")
    # جدول جدید: تاریخچه یادگیری
    c.execute("""CREATE TABLE IF NOT EXISTS learning_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, generation INTEGER, awareness REAL,
        score_threshold REAL, conv_threshold REAL,
        aether_w REAL, pulse_w REAL, flux_w REAL, vector_w REAL,
        fitness REAL, winrate REAL, trades_count INTEGER)""")
    # جدول عملکرد ارگانیسم‌ها در هر معامله
    c.execute("""CREATE TABLE IF NOT EXISTS organism_perf (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, organism TEXT, trade_pnl REAL, regime TEXT, weight_delta REAL)""")
    conn.commit()
    conn.close()


def db_set(key, value):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)",
                 (key, json.dumps(value) if not isinstance(value, str) else value))
    conn.commit()
    conn.close()


def db_get(key, default=None):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    conn.close()
    if row is None:
        return default
    try:
        return json.loads(row[0])
    except Exception:
        return row[0]


def save_trade(t):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO trades
        (symbol,side,entry,size_usd,qty,leverage,liq_price,entry_time,status,reason,votes,regime,features,partials,trail_stop)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (t["symbol"], t["side"], t["entry"], t["size_usd"], t["qty"], t["leverage"], t["liq_price"],
               t["entry_time"], "open", t.get("reason", ""), json.dumps(t.get("votes", {})),
               t.get("regime", ""), json.dumps(t.get("features", {})), json.dumps(t.get("partials", [])),
               t.get("trail_stop")))
    conn.commit()
    tid = c.lastrowid
    conn.close()
    return tid


def update_trade(tid, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    sets = ", ".join(f"{k}=?" for k in kwargs)
    conn.execute(f"UPDATE trades SET {sets} WHERE id=?", (*kwargs.values(), tid))
    conn.commit()
    conn.close()


def close_trade_full(tid, exit_price, pnl):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""UPDATE trades SET exit_time=?, exit_price=?, pnl=?, status='closed' WHERE id=?""",
                 (datetime.now(timezone.utc).isoformat(), exit_price, pnl, tid))
    conn.commit()
    conn.close()


def get_open_trades():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""SELECT id,symbol,side,entry,size_usd,qty,leverage,liq_price,entry_time,reason,votes,regime,features,partials,trail_stop
                           FROM trades WHERE status='open'""").fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({
            "id": r[0], "symbol": r[1], "side": r[2], "entry": r[3], "size_usd": r[4], "qty": r[5],
            "leverage": r[6], "liq_price": r[7], "entry_time": r[8], "reason": r[9],
            "votes": json.loads(r[10] or "{}"), "regime": r[11], "features": json.loads(r[12] or "{}"),
            "partials": json.loads(r[13] or "[]"), "trail_stop": r[14]
        })
    return res


def get_closed_trades(limit=150):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""SELECT id,symbol,side,entry,exit_price,size_usd,pnl,entry_time,exit_time,reason,regime
                           FROM trades WHERE status='closed' ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
    conn.close()
    return [{"id": r[0], "symbol": r[1], "side": r[2], "entry": r[3], "exit": r[4], "size_usd": r[5], "pnl": r[6],
             "entry_time": r[7], "exit_time": r[8], "reason": r[9], "regime": r[10]} for r in rows]


def log_decision(symbol, side, conv, regime, features, votes, accepted, reason):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""INSERT INTO decisions (ts,symbol,side,conv,regime,features,votes,accepted,reason)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                 (datetime.now(timezone.utc).isoformat(), symbol, side, conv, regime,
                  json.dumps(features), json.dumps(votes), int(accepted), reason))
    conn.commit()
    conn.close()


def record_equity(eq, n_open):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO equity (ts, equity, open_n) VALUES (?,?,?)",
                 (datetime.now(timezone.utc).isoformat(), eq, n_open))
    conn.commit()
    conn.close()


def get_equity_history():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT ts, equity FROM equity ORDER BY ts").fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["ts", "equity"]) if rows else pd.DataFrame({"ts": [], "equity": []})


# ── توابع تاریخچه یادگیری ──────────────────────────────
def record_learning_state(hive, fitness=None, winrate=None, trades_count=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO learning_history 
        (ts, generation, awareness, score_threshold, conv_threshold,
         aether_w, pulse_w, flux_w, vector_w, fitness, winrate, trades_count)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
              (datetime.now(timezone.utc).isoformat(), getattr(hive, "generation", 0), hive.awareness,
               hive.adaptive.get("score_threshold", 0.52), hive.adaptive.get("conv_threshold", 0.41),
               hive.orgs[0].weight, hive.orgs[1].weight, hive.orgs[2].weight, hive.orgs[3].weight,
               fitness, winrate, trades_count))
    conn.commit()
    conn.close()


def get_learning_history():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""SELECT ts, generation, awareness, score_threshold, conv_threshold,
        aether_w, pulse_w, flux_w, vector_w, fitness, winrate, trades_count
        FROM learning_history ORDER BY ts""").fetchall()
    conn.close()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, columns=["ts", "generation", "awareness", "score_threshold", "conv_threshold",
                                       "aether_w", "pulse_w", "flux_w", "vector_w", "fitness", "winrate",
                                       "trades_count"])


def log_organism_perf(organism, pnl, regime, weight_delta):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""INSERT INTO organism_perf (ts, organism, trade_pnl, regime, weight_delta)
                    VALUES (?,?,?,?,?)""",
                 (datetime.now(timezone.utc).isoformat(), organism, pnl, regime, weight_delta))
    conn.commit()
    conn.close()


def get_organism_perf(limit=200):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""SELECT organism, trade_pnl, regime, weight_delta, ts 
                           FROM organism_perf ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=["organism", "trade_pnl", "regime", "weight_delta", "ts"])


# ──────────────────────────────────────────────────────────────
# رژیم‌دیتکشن قوی
def detect_regime(df):
    if df is None or len(df) < 50:
        return "RANGING"
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    atr = pd.Series(tr).rolling(14).mean().iloc[-1]
    atr_pct = atr / close[-1]
    ma_fast = pd.Series(close).rolling(12).mean().iloc[-1]
    ma_slow = pd.Series(close).rolling(36).mean().iloc[-1]
    slope = (close[-1] - close[-20]) / (close[-20] + 1e-12)
    up = np.maximum(high[1:] - high[:-1], 0)
    dn = np.maximum(low[:-1] - low[1:], 0)
    plus_dm = pd.Series(up).rolling(14).mean().iloc[-1]
    minus_dm = pd.Series(dn).rolling(14).mean().iloc[-1]
    dx = abs(plus_dm - minus_dm) / (plus_dm + minus_dm + 1e-12) * 100
    adx_approx = dx

    if atr_pct > 0.018:
        return "HIGH_VOL"
    if adx_approx > 22 and slope > 0.004 and ma_fast > ma_slow:
        return "TREND_UP"
    if adx_approx > 22 and slope < -0.004 and ma_fast < ma_slow:
        return "TREND_DOWN"
    return "RANGING"


REGIME_PARAMS = {
    "TREND_UP": {"tp": 0.0065, "sl": 0.0032, "risk_mult": 1.15, "trail_mult": 1.3, "partial_at": 0.0035},
    "TREND_DOWN": {"tp": 0.0065, "sl": 0.0032, "risk_mult": 1.15, "trail_mult": 1.3, "partial_at": 0.0035},
    "RANGING": {"tp": 0.0038, "sl": 0.0024, "risk_mult": 0.85, "trail_mult": 0.9, "partial_at": 0.0022},
    "HIGH_VOL": {"tp": 0.0085, "sl": 0.0045, "risk_mult": 0.70, "trail_mult": 1.5, "partial_at": 0.0045},
}


# ──────────────────────────────────────────────────────────────
# استخراج ویژگی‌ها
def extract_features(df, ticker):
    if df is None or len(df) < 40:
        return None
    close = df["close"].values
    vol = df["volume"].values
    mom = float(np.clip((close[-1] - close[-8]) / (close[-8] + 1e-12) * 22, -1, 1))
    vol_surge = float(np.clip((vol[-4:].mean() / (vol[-18:].mean() + 1e-12) - 1) * 1.7, -1, 1))
    deltas = np.diff(close[-9:])
    pressure = float(np.clip(np.mean(deltas) / (np.std(deltas) + 1e-12) * 0.55, -1, 1))
    mid = ticker["last"]
    spread_bps = (ticker["ask"] - ticker["bid"]) / (mid + 1e-12) * 10000
    spread_q = float(np.clip(1.0 - spread_bps / MAX_SPREAD_BPS, 0, 1))
    delta = pd.Series(close).diff()
    gain = delta.clip(lower=0).rolling(10).mean()
    loss = (-delta.clip(upper=0)).rolling(10).mean()
    rs = gain / (loss + 1e-12)
    rsi = 100 - (100 / (1 + rs)).iloc[-1]
    rsi_ext = 1.0 if rsi < 27 else (-1.0 if rsi > 73 else (0.45 if rsi < 37 else (-0.45 if rsi > 63 else 0.0)))
    atr = pd.Series(np.maximum(df["high"] - df["low"], np.maximum(abs(df["high"] - df["close"].shift(1)),
                                                                  abs(df["low"] - df["close"].shift(1))))).rolling(
        14).mean().iloc[-1]
    atr_pct = float(atr / close[-1])
    return {
        "mom": mom, "vol_surge": vol_surge, "pressure": pressure,
        "spread_q": spread_q, "spread_bps": spread_bps, "rsi_ext": rsi_ext,
        "atr_pct": atr_pct, "rsi": float(rsi)
    }


# ──────────────────────────────────────────────────────────────
# ارگانیسم‌ها
class Organism:
    def __init__(self, name, role, weight=1.0):
        self.name = name
        self.role = role
        self.weight = weight
        self.neurons = int(NEURON_BASE * (1.35 if role == "SNIPER" else 1.2 if role == "SCALPER" else 1.05))
        self.profit_sum = 0.0
        self.trade_count = 0

    def score(self, feat, regime):
        mom, vs, pr, sq, re = feat["mom"], feat["vol_surge"], feat["pressure"], feat["spread_q"], feat["rsi_ext"]
        if self.role == "SNIPER":
            s = 0.34 * mom + 0.24 * vs + 0.24 * pr + 0.18 * sq
            if abs(s) < 0.40 or abs(re) < 0.25:
                return 0.0
            if regime in ("TREND_UP", "TREND_DOWN") and np.sign(s) != np.sign(mom):
                s *= 0.6
            return s * 1.28 * self.weight
        elif self.role == "SCALPER":
            s = 0.28 * mom + 0.38 * vs + 0.22 * pr + 0.12 * sq
            return s * 1.18 * self.weight
        elif self.role == "FLOW":
            s = 0.18 * mom + 0.36 * vs + 0.34 * pr + 0.12 * sq
            return s * 1.12 * self.weight
        else:  # MOMENTUM
            s = 0.42 * mom + 0.26 * vs + 0.20 * pr + 0.12 * re
            return s * self.weight


# ──────────────────────────────────────────────────────────────
# هسته Hive
class HivePro:
    def __init__(self):
        init_db()
        self.capital = float(db_get("capital", INITIAL_CAPITAL))
        self.peak = float(db_get("peak", INITIAL_CAPITAL))
        self.awareness = float(db_get("awareness", 0.58))
        self.win_streak = int(db_get("ws", 0))
        self.loss_streak = int(db_get("ls", 0))
        self.adaptive = db_get("adaptive", {"score_threshold": 0.52, "conv_threshold": 0.41})
        self.orgs = [
            Organism("Aether", "SNIPER", 1.42),
            Organism("Pulse", "SCALPER", 1.32),
            Organism("Flux", "FLOW", 1.22),
            Organism("Vector", "MOMENTUM", 1.12),
        ]
        self.last_stats = {"scanned": 0, "cands": 0, "opened": 0, "regime_counts": {}}
        self._lock = threading.Lock()
        self.heart_beat = 0
        self.generation = 0
        self.org_performance = defaultdict(lambda: {"pnl": 0.0, "count": 0})

        # بارگیری DNA
        dna = load_dna_state()
        if dna:
            self.adaptive.update(dna.get("adaptive", {}))
            self.awareness = dna.get("awareness", self.awareness)
            self.win_streak = dna.get("win_streak", self.win_streak)
            self.loss_streak = dna.get("loss_streak", self.loss_streak)
            self.generation = dna.get("generation", 0)
            w = dna.get("organism_weights", {})
            for o in self.orgs:
                if o.name in w:
                    o.weight = w[o.name]
            self.org_performance.update(dna.get("organism_performance", {}))

        # اجرای تکامل خودکار در استارت
        self._auto_evolve_at_startup()

    def _auto_evolve_at_startup(self):
        """اگر آگاهی کمتر از سقف است، بک‌تست و تکامل خودکار اجرا کن"""
        if self.awareness < AWARENESS_CAP - 0.05:
            print("[EVOLVE] Starting auto-evolution to maximize awareness...")
            symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT"]
            # اجرای ۳ دور تکامل عمیق
            for i in range(3):
                result = run_generation(self, symbols, candles=8000)
                print(
                    f"[EVOLVE] Gen {result['generation']}: fit={result['mutated_fitness']:.3f}, kept={result['kept_mutation']}")
                if result['mutated_fitness'] > 0:
                    record_learning_state(self, fitness=result['mutated_fitness'],
                                          winrate=result.get('winrate'), trades_count=result.get('trades'))
            print(f"[EVOLVE] Complete. Awareness: {self.awareness:.2%}, Gen: {self.generation}")

    def total_neurons(self):
        return sum(o.neurons for o in self.orgs)

    def select_candidates(self, tickers, max_n=12):
        ranked = []
        for sym, t in tickers.items():
            if t["turn24"] < MIN_TURNOVER_24H:
                continue
            spread_bps = (t["ask"] - t["bid"]) / (t["last"] + 1e-12) * 10000
            if spread_bps > MAX_SPREAD_BPS:
                continue
            score = (math.log10(t["turn24"] + 1) * 0.38 +
                     abs(t["chg"]) * 85 * 0.37 +
                     (0.25 if t["vol24"] > 2e6 else 0.1))
            ranked.append((sym, score, t))
        ranked.sort(key=lambda x: -x[1])
        return ranked[:max_n]

    def correlation_ok(self, new_sym, opens, tickers):
        if not opens:
            return True
        new_chg = tickers.get(new_sym, {}).get("chg", 0)
        for t in opens:
            old_chg = tickers.get(t["symbol"], {}).get("chg", 0)
            if abs(new_chg) > 0.02 and abs(old_chg) > 0.02 and np.sign(new_chg) == np.sign(old_chg):
                if abs(new_chg - old_chg) < 0.015:
                    return False
        return True

    def decide(self, feat, regime):
        if feat is None:
            return None
        votes = []
        for o in self.orgs:
            s = o.score(feat, regime)
            if abs(s) < 0.26:
                continue
            side = "long" if s > 0 else "short"
            votes.append({"org": o.name, "role": o.role, "side": side, "score": s, "w": o.weight})
        if len(votes) < 2:
            return None
        long_s = sum(v["score"] * v["w"] for v in votes if v["side"] == "long")
        short_s = sum(abs(v["score"]) * v["w"] for v in votes if v["side"] == "short")
        thresh = self.adaptive.get("score_threshold", 0.52)
        if long_s > short_s and long_s > thresh:
            side, final = "long", long_s
        elif short_s > long_s and short_s > thresh:
            side, final = "short", short_s
        else:
            return None
        agreeing = [v for v in votes if v["side"] == side]
        if len(agreeing) < 2:
            return None
        has_sniper = any(v["role"] == "SNIPER" for v in agreeing)
        has_scalper = any(v["role"] == "SCALPER" for v in agreeing)
        if not (has_sniper or has_scalper):
            return None
        conv = min(1.0, final / 1.75 * (1.18 if has_sniper else 1.0))
        if conv < self.adaptive.get("conv_threshold", 0.41):
            return None
        reason = " | ".join(f"{v['org']}:{v['side'][0]}{v['score']:.2f}" for v in agreeing)
        return {
            "side": side, "conv": conv, "votes": {v["org"]: v for v in votes},
            "reason": f"HIVE[{len(agreeing)}] {reason}", "regime": regime
        }

    def calc_size(self, conv, atr_pct, regime, opens):
        rp = REGIME_PARAMS.get(regime, REGIME_PARAMS["RANGING"])
        risk = RISK_PER_TRADE_BASE * rp["risk_mult"] * (0.75 + 0.25 * conv)
        vol_target = 0.012
        vol_mult = vol_target / max(atr_pct, 0.004)
        vol_mult = float(np.clip(vol_mult, 0.55, 1.35))
        risk *= vol_mult
        free = max(0.0, self.capital - sum(t["size_usd"] for t in opens))
        sl = rp["sl"]
        size = (self.capital * risk) / (sl * LEVERAGE)
        size = min(size, free * 0.34, self.capital * 0.20)
        return max(18.0, size)

    def try_open(self, sym, ticker, decision, feat, regime):
        with self._lock:
            opens = get_open_trades()
            if len(opens) >= MAX_POSITIONS:
                return False
            if any(t["symbol"] == sym for t in opens):
                return False
            if not self.correlation_ok(sym, opens, {sym: ticker}):
                return False
            size = self.calc_size(decision["conv"], feat["atr_pct"], regime, opens)
            if size < 18:
                return False
            price = ticker["last"]
            spread_adj = (ticker["ask"] - ticker["bid"]) / 2 / price
            slip = SLIPPAGE_BPS / 10000
            if decision["side"] == "long":
                entry = price * (1 + spread_adj + slip)
                liq = entry * (1 - 0.92 / LEVERAGE)
            else:
                entry = price * (1 - spread_adj - slip)
                liq = entry * (1 + 0.92 / LEVERAGE)
            qty = (size * LEVERAGE) / entry
            rp = REGIME_PARAMS.get(regime, REGIME_PARAMS["RANGING"])
            trail = entry * (1 - rp["sl"] * 1.1) if decision["side"] == "long" else entry * (1 + rp["sl"] * 1.1)
            t = {
                "symbol": sym, "side": decision["side"], "entry": entry, "size_usd": size,
                "qty": qty, "leverage": LEVERAGE, "liq_price": liq,
                "entry_time": datetime.now(timezone.utc).isoformat(),
                "reason": decision["reason"], "votes": decision["votes"],
                "regime": regime, "features": feat, "partials": [], "trail_stop": trail
            }
            tid = save_trade(t)
            log_decision(sym, decision["side"], decision["conv"], regime, feat, decision["votes"], True,
                         decision["reason"])
            return True

    def manage_positions(self):
        opens = get_open_trades()
        if not opens:
            return
        tickers = get_all_tickers()
        now = datetime.now(timezone.utc)
        for t in opens:
            last = tickers.get(t["symbol"], {}).get("last")
            if last is None:
                continue
            side = t["side"]
            entry = t["entry"]
            rp = REGIME_PARAMS.get(t["regime"], REGIME_PARAMS["RANGING"])
            if side == "long":
                pnl_pct = (last - entry) / entry
            else:
                pnl_pct = (entry - last) / entry
            remaining_size = t["size_usd"] * (1 - sum(p.get("frac", 0) for p in t["partials"]))
            pnl_usd = pnl_pct * remaining_size * LEVERAGE - remaining_size * COMMISSION * 2

            hold_min = (now - datetime.fromisoformat(t["entry_time"])).total_seconds() / 60.0
            trail = t["trail_stop"]
            partials = t["partials"][:]

            partial_level = rp["partial_at"]
            if pnl_pct >= partial_level and not any(p.get("level") == "p1" for p in partials):
                part_frac = 0.40
                part_pnl = pnl_pct * t["size_usd"] * part_frac * LEVERAGE - t["size_usd"] * part_frac * COMMISSION * 2
                partials.append(
                    {"level": "p1", "frac": part_frac, "price": last, "pnl": part_pnl, "ts": now.isoformat()})
                self.capital += part_pnl
                if side == "long":
                    trail = max(trail, last * (1 - rp["sl"] * 0.7))
                else:
                    trail = min(trail, last * (1 + rp["sl"] * 0.7))
                update_trade(t["id"], partials=json.dumps(partials), trail_stop=trail)

            if side == "long":
                new_trail = last * (1 - rp["sl"] * rp["trail_mult"] * 0.6)
                if new_trail > trail:
                    trail = new_trail
                    update_trade(t["id"], trail_stop=trail)
                hit_trail = last <= trail
            else:
                new_trail = last * (1 + rp["sl"] * rp["trail_mult"] * 0.6)
                if new_trail < trail:
                    trail = new_trail
                    update_trade(t["id"], trail_stop=trail)
                hit_trail = last >= trail

            full_close = False
            if pnl_pct >= rp["tp"] or pnl_pct <= -rp["sl"]:
                full_close = True
            if hit_trail:
                full_close = True
            if hold_min >= 22:
                full_close = True
            if hold_min > 5 and abs(pnl_pct) < 0.0008:
                full_close = True
            if side == "long" and last <= t["liq_price"] * 1.008:
                full_close = True
            if side == "short" and last >= t["liq_price"] * 0.992:
                full_close = True

            if full_close:
                remain_frac = 1.0 - sum(p.get("frac", 0) for p in partials)
                final_pnl = pnl_pct * t["size_usd"] * remain_frac * LEVERAGE - t[
                    "size_usd"] * remain_frac * COMMISSION * 2
                total_pnl = final_pnl + sum(p.get("pnl", 0) for p in partials)
                close_trade_full(t["id"], last, total_pnl)
                self.capital += final_pnl
                if total_pnl > 0:
                    self.win_streak += 1
                    self.loss_streak = 0
                else:
                    self.win_streak = 0
                    self.loss_streak += 1
                db_set("capital", self.capital)
                db_set("ws", self.win_streak)
                db_set("ls", self.loss_streak)
                self._learn_from_trade(total_pnl, t)

    def _learn_from_trade(self, pnl, trade):
        """یادگیری پیشرفته: تنظیم آستانه‌ها، وزن ارگانیسم‌ها، آگاهی"""
        closed = get_closed_trades(60)
        n_closed = len(closed)
        if n_closed < 5:
            save_dna_state(self)
            return

        wins = [t for t in closed if t["pnl"] and t["pnl"] > 0]
        wr = len(wins) / n_closed

        # محاسبه سهم هر ارگانیسم در سود/زیان
        votes = trade.get("votes", {})
        for org_name, v in votes.items():
            org = next((o for o in self.orgs if o.name == org_name), None)
            if not org:
                continue
            # اگر ارگانیسم با سمت برنده موافق بود، پاداش؛ در غیر این صورت جریمه
            org_pnl = pnl * (1.0 if v.get("side") == trade.get("side") else -0.5)
            org.profit_sum += org_pnl
            org.trade_count += 1
            self.org_performance[org_name]["pnl"] = self.org_performance[org_name].get("pnl", 0) + org_pnl
            self.org_performance[org_name]["count"] = self.org_performance[org_name].get("count", 0) + 1

        # تنظیم وزن‌ها بر اساس عملکرد نسبی (هر ۵ معامله)
        if n_closed % 5 == 0:
            perf_vals = {
                o.name: self.org_performance[o.name].get("pnl", 0) / max(self.org_performance[o.name].get("count", 1),
                                                                         1)
                for o in self.orgs}
            avg_perf = np.mean(list(perf_vals.values())) if perf_vals else 0
            for o in self.orgs:
                p = perf_vals.get(o.name, 0)
                if avg_perf != 0:
                    delta = 0.03 * (p - avg_perf) / abs(avg_perf)
                    old_w = o.weight
                    o.weight = float(np.clip(o.weight + delta, 0.5, 2.0))
                    log_organism_perf(o.name, p, trade.get("regime", "UNK"), o.weight - old_w)

        # آگاهی: یادگیری با نرخ کاهشی
        learning_rate = 0.08 / math.sqrt(n_closed + 1)
        reward_signal = 1.0 if pnl > 0 else -0.6
        if wr > 0.55:
            reward_signal += 0.2
        # فاصله تا سقف را بگیر و اعمال کن
        gap = AWARENESS_CAP - self.awareness
        self.awareness = min(AWARENESS_CAP, self.awareness + gap * learning_rate * reward_signal)
        self.awareness = max(0.30, self.awareness)

        # آستانه‌ها
        if wr > 0.58 and pnl > 0:
            self.adaptive["score_threshold"] = max(0.40, self.adaptive["score_threshold"] - 0.006)
            self.adaptive["conv_threshold"] = max(0.32, self.adaptive["conv_threshold"] - 0.004)
        elif wr < 0.42:
            self.adaptive["score_threshold"] = min(0.65, self.adaptive["score_threshold"] + 0.010)
            self.adaptive["conv_threshold"] = min(0.55, self.adaptive["conv_threshold"] + 0.008)

        db_set("adaptive", self.adaptive)
        db_set("awareness", self.awareness)
        save_dna_state(self)
        record_learning_state(self, winrate=wr, trades_count=n_closed)

    def equity(self):
        opens = get_open_trades()
        if not opens:
            return self.capital
        tickers = get_all_tickers()
        unreal = 0.0
        for t in opens:
            last = tickers.get(t["symbol"], {}).get("last", t["entry"])
            if t["side"] == "long":
                pp = (last - t["entry"]) / t["entry"]
            else:
                pp = (t["entry"] - last) / t["entry"]
            remain = 1.0 - sum(p.get("frac", 0) for p in t["partials"])
            unreal += pp * t["size_usd"] * remain * LEVERAGE - t["size_usd"] * remain * COMMISSION * 2
        return self.capital + unreal

    def cycle(self):
        self.manage_positions()
        tickers = get_all_tickers()
        if not tickers:
            self.last_stats = {"scanned": 0, "cands": 0, "opened": 0, "regime_counts": {}}
            return
        cands = self.select_candidates(tickers, 11)
        self.last_stats["scanned"] = len(tickers)
        self.last_stats["cands"] = len(cands)
        opened = 0
        regime_counts = defaultdict(int)
        for sym, sc, tk in cands:
            try:
                df = get_klines(sym, "5", 120)
                if df.empty:
                    continue
                regime = detect_regime(df)
                regime_counts[regime] += 1
                feat = extract_features(df, tk)
                if feat is None or feat["spread_bps"] > MAX_SPREAD_BPS:
                    continue
                dec = self.decide(feat, regime)
                if dec is None:
                    log_decision(sym, "none", 0, regime, feat or {}, {}, False, "no consensus")
                    continue
                if self.try_open(sym, tk, dec, feat, regime):
                    opened += 1
            except Exception:
                continue
        self.last_stats["opened"] = opened
        self.last_stats["regime_counts"] = dict(regime_counts)
        eq = self.equity()
        self.peak = max(self.peak, eq)
        db_set("peak", self.peak)
        record_equity(eq, len(get_open_trades()))
        self.heart_beat += 1


# ──────────────────────────────────────────────────────────────
# بک‌تست مبتنی بر مسیر تصمیم زنده
def run_backtest(symbol, candles=10000, interval="5", df=None, hive=None):
    if df is None:
        df = get_klines_paginated(symbol, interval=interval, total=candles)
    if df is None or df.empty or len(df) < 100:
        return None

    hive = hive or HivePro()
    capital = INITIAL_CAPITAL
    positions, trades, equity_curve = [], [], []
    slip = SLIPPAGE_BPS / 10000.0
    HALF_SPREAD = 0.0002
    regime = "RANGING"

    def close_fraction(pos, price, frac):
        nonlocal capital
        sm = 1 if pos["side"] == "long" else -1
        gross = sm * (price - pos["entry"]) / pos["entry"]
        pnl = pos["margin"] * frac * (gross * LEVERAGE - COMMISSION * 2)
        capital += pos["margin"] * frac + pnl
        pos["frac"] -= frac
        trades.append({"pnl": pnl, "side": pos["side"], "regime": pos["regime"]})

    for i in range(60, len(df)):
        window = df.iloc[:i + 1]
        close = float(window["close"].iloc[-1])
        high = float(window["high"].iloc[-1])
        low = float(window["low"].iloc[-1])
        regime = detect_regime(window)

        for pos in list(positions):
            pos["hold"] += 1
            sm = 1 if pos["side"] == "long" else -1
            pos["best"] = max(pos["best"], high) if sm == 1 else min(pos["best"], low)
            pnl_pct = sm * (close - pos["entry"]) / pos["entry"]
            rp_p = pos["rp"]

            if pnl_pct <= -rp_p["sl"] or pnl_pct >= rp_p["tp"]:
                close_fraction(pos, close, pos["frac"]);
                positions.remove(pos);
                continue

            if not pos["partial_done"] and pnl_pct >= rp_p["partial_at"]:
                close_fraction(pos, close, 0.40)
                pos["partial_done"] = True

            trail = rp_p["sl"] * (0.7 if pos["partial_done"] else rp_p["trail_mult"] * 0.6)
            retrace = sm * (pos["best"] - close) / pos["entry"]
            if pnl_pct > 0 and retrace >= trail:
                close_fraction(pos, close, pos["frac"]);
                positions.remove(pos);
                continue

            if pos["hold"] >= 22:
                close_fraction(pos, close, pos["frac"]);
                positions.remove(pos);
                continue
            if pos["hold"] > 5 and abs(pnl_pct) < 0.0008:
                close_fraction(pos, close, pos["frac"]);
                positions.remove(pos);
                continue

        ticker = {"last": close, "bid": close * 0.9998, "ask": close * 1.0002,
                  "vol24": float(window["volume"].tail(288).sum()),
                  "turn24": float((window["volume"] * window["close"]).tail(288).sum()), "chg": 0}
        feat = extract_features(window, ticker)
        decision = hive.decide(feat, regime)
        if decision and len(positions) < MAX_POSITIONS:
            side = decision["side"]
            if not any(p["side"] == side for p in positions):
                rp = REGIME_PARAMS.get(regime, REGIME_PARAMS["RANGING"])
                margin = min(capital * RISK_PER_TRADE_BASE * rp["risk_mult"] / max(rp["sl"], 1e-4),
                             capital * 0.20)
                if margin >= 5 and capital > margin:
                    sm = 1 if side == "long" else -1
                    entry = close * (1 + sm * (HALF_SPREAD + slip))
                    capital -= margin
                    positions.append({"side": side, "entry": entry, "margin": margin, "frac": 1.0,
                                      "hold": 0, "best": entry, "partial_done": False,
                                      "rp": dict(rp), "regime": regime,
                                      "conv": decision["conv"], "features": feat})

        equity_curve.append(capital + sum(p["margin"] * p["frac"] for p in positions))

    for pos in list(positions):
        close_fraction(pos, float(df["close"].iloc[-1]), pos["frac"])

    if not trades:
        return None
    pnls = [t["pnl"] for t in trades]
    wr = sum(1 for p in pnls if p > 0) / len(pnls)
    total_ret = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL
    return {
        "symbol": symbol, "trades": len(trades), "winrate": wr,
        "total_return": total_ret, "final_capital": capital,
        "avg_pnl": float(np.mean(pnls)), "equity_curve": equity_curve[-200:],
        "generation": getattr(hive, "generation", 0)
    }


# ── حلقهٔ تکامل نسلی پیشرفته ──────────────────────
def run_generation(hive, symbols, candles=10000):
    def fitness(results):
        f = 0.0
        total_trades = 0
        for r in results:
            if not r:
                continue
            f += r["total_return"] * (0.5 + 0.5 * r["winrate"])
            total_trades += r["trades"]
            if r["trades"] < 10:
                f -= 0.5
        return f, total_trades

    data = {}
    for s in symbols:
        data[s] = get_klines_paginated(s, total=candles)
        time.sleep(0.2)

    save_dna_state(hive)
    base_results = [run_backtest(s, df=data[s], hive=hive) for s in symbols]
    base_fit, base_trades = fitness(base_results)
    base_wr = np.mean([r["winrate"] for r in base_results if r]) if any(base_results) else 0

    snap_a = dict(hive.adaptive)
    snap_w = {o.name: o.weight for o in hive.orgs}
    snap_aw = hive.awareness

    # ۳ جهش مستقل و انتخاب بهترین
    best_mut = None
    best_fit = -999
    for _ in range(3):
        # جهش
        hive.adaptive["score_threshold"] = float(np.clip(
            snap_a["score_threshold"] * (1 + np.random.normal(0, 0.06)), 0.30, 0.90))
        hive.adaptive["conv_threshold"] = float(np.clip(
            snap_a["conv_threshold"] * (1 + np.random.normal(0, 0.06)), 0.20, 0.80))
        for o in hive.orgs:
            o.weight = float(np.clip(o.weight * (1 + np.random.normal(0, 0.06)), 0.5, 2.0))

        mut_results = [run_backtest(s, df=data[s], hive=hive) for s in symbols]
        mut_fit, mut_trades = fitness(mut_results)

        if mut_fit > best_fit:
            best_fit = mut_fit
            best_mut = (dict(hive.adaptive), {o.name: o.weight for o in hive.orgs})

        # بازگشت برای جهش بعدی
        hive.adaptive.update(snap_a)
        for o in hive.orgs:
            o.weight = snap_w[o.name]

    kept = best_fit > base_fit
    if kept and best_mut:
        hive.adaptive.update(best_mut[0])
        for o in hive.orgs:
            o.weight = best_mut[1][o.name]
        # افزایش آگاهی با بهبود فیتنس
        improvement = (best_fit - base_fit) / (abs(base_fit) + 1e-6)
        hive.awareness = min(AWARENESS_CAP, hive.awareness + 0.01 + improvement * 0.02)
    else:
        hive.adaptive.update(snap_a)
        for o in hive.orgs:
            o.weight = snap_w[o.name]
        hive.awareness = snap_aw

    hive.generation = getattr(hive, "generation", 0) + 1
    save_dna_state(hive)
    db_set("adaptive", hive.adaptive)
    db_set("awareness", hive.awareness)

    return {"generation": hive.generation, "base_fitness": base_fit,
            "mutated_fitness": best_fit, "kept_mutation": kept,
            "winrate": base_wr, "trades": base_trades}


# ──────────────────────────────────────────────────────────────
# نمونه سراسری
HIVE = HivePro()

# ──────────────────────────────────────────────────────────────
# استایل‌های سفارشی RTL و گرافیکی
CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;700&display=swap');
body {
    font-family: 'Vazirmatn', 'Tahoma', sans-serif !important;
    direction: rtl;
    text-align: right;
    background: linear-gradient(135deg, #050a14 0%, #0a1120 100%);
}
.card-glass {
    background: rgba(13,21,37,0.75) !important;
    backdrop-filter: blur(12px);
    border: 1px solid rgba(240,185,11,0.15) !important;
    border-radius: 14px !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    transition: transform 0.2s, box-shadow 0.2s;
}
.card-glass:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 40px rgba(240,185,11,0.08);
}
.neon-text {
    text-shadow: 0 0 10px rgba(0,245,212,0.4);
}
.gold-glow {
    box-shadow: 0 0 20px rgba(240,185,11,0.15);
}
.dash-table-container {
    direction: rtl;
    text-align: right;
}
.tab-content {
    direction: rtl;
    text-align: right;
}
"""

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG], suppress_callback_exceptions=True)
app.title = "HIVE PRO v4 — Ultimate Learning"
server = app.server
app.index_string = app.index_string.replace('</head>', f'<style>{CUSTOM_CSS}</style></head>')


def card(title, val, color=GOLD, sub="", icon="◉"):
    return dbc.Card(dbc.CardBody([
        html.Div(f"{icon} {title}", style={"color": MUT, "fontSize": 11, "letterSpacing": 1}),
        html.Div(str(val),
                 style={"color": color, "fontSize": 22, "fontWeight": "bold", "marginTop": 6, "marginBottom": 2}),
        html.Div(sub, style={"color": MUT, "fontSize": 10, "opacity": 0.8})
    ]), className="card-glass", style={"height": "100%", "marginBottom": 8})


app.layout = html.Div([
    # هدر
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col(html.Div([
            html.H3("HIVE PRO v4  ×۲۰  ULTIMATE LEARNING", style={"color": GOLD, "margin": 0, "fontWeight": "bold"}),
            html.Div("سیستم خودآموز تکاملی با آگاهی تطبیقی", style={"color": MUT, "fontSize": 12, "marginTop": 4})
        ]), md=5),
        dbc.Col(html.Div(id="pulse",
                         style={"color": NEON, "fontFamily": "monospace", "fontSize": 13, "textAlign": "center"}),
                md=4),
        dbc.Col(html.Div(id="status", style={"textAlign": "left", "color": MUT, "fontSize": 12}), md=3),
    ])), style={"margin": "12px 16px", "background": GLASS, "border": f"1px solid {LINE}", "borderRadius": 16}),

    dcc.Tabs(id="tabs", value="live", children=[
        dcc.Tab(label="◉ معاملات زنده", value="live",
                style={"background": CARD, "color": TXT, "border": "none", "padding": "10px 20px"},
                selected_style={"background": LINE, "color": GOLD, "border": "none", "borderTop": f"3px solid {GOLD}",
                                "fontWeight": "bold"}),
        dcc.Tab(label="◉ وضعیت Hive", value="stats",
                style={"background": CARD, "color": TXT, "border": "none", "padding": "10px 20px"},
                selected_style={"background": LINE, "color": GOLD, "border": "none", "borderTop": f"3px solid {GOLD}",
                                "fontWeight": "bold"}),
        dcc.Tab(label="◉ بک‌تست", value="backtest",
                style={"background": CARD, "color": TXT, "border": "none", "padding": "10px 20px"},
                selected_style={"background": LINE, "color": GOLD, "border": "none", "borderTop": f"3px solid {GOLD}",
                                "fontWeight": "bold"}),
        dcc.Tab(label="◉ تحلیل عملکرد", value="perf",
                style={"background": CARD, "color": TXT, "border": "none", "padding": "10px 20px"},
                selected_style={"background": LINE, "color": GOLD, "border": "none", "borderTop": f"3px solid {GOLD}",
                                "fontWeight": "bold"}),
        dcc.Tab(label="◉ مرکز یادگیری", value="learning",
                style={"background": CARD, "color": TXT, "border": "none", "padding": "10px 20px"},
                selected_style={"background": LINE, "color": GOLD, "border": "none", "borderTop": f"3px solid {GOLD}",
                                "fontWeight": "bold"}),
    ], style={"margin": "0 16px", "direction": "rtl"}),

    html.Div(id="content", style={"padding": "16px"}, className="tab-content"),
    dcc.Interval(id="life", interval=11_000, n_intervals=0),
    dcc.Interval(id="cycle", interval=32_000, n_intervals=0),
    dcc.Store(id="bt-result"),
], style={"background": BG, "minHeight": "100vh", "color": TXT, "direction": "rtl"})


@app.callback(Output("content", "children"), Input("tabs", "value"), Input("life", "n_intervals"),
              Input("bt-result", "data"))
def render(tab, n, bt_data):
    if tab == "live":
        return live_tab()
    if tab == "stats":
        return stats_tab()
    if tab == "backtest":
        return backtest_tab(bt_data)
    if tab == "learning":
        return learning_tab()
    return perf_tab()


def live_tab():
    h = HIVE
    opens = get_open_trades()
    closed = get_closed_trades(25)
    eq = h.equity()
    if opens:
        tickers = get_all_tickers()
        rows = []
        for t in opens:
            last = tickers.get(t["symbol"], {}).get("last", t["entry"])
            if t["side"] == "long":
                pp = (last - t["entry"]) / t["entry"]
            else:
                pp = (t["entry"] - last) / t["entry"]
            remain = 1.0 - sum(p.get("frac", 0) for p in t["partials"])
            pnl = pp * t["size_usd"] * remain * LEVERAGE - t["size_usd"] * remain * COMMISSION * 2
            color = UP if pnl >= 0 else DN
            rows.append(html.Tr([
                html.Td(t["id"]), html.Td(t["symbol"]),
                html.Td(t["side"].upper(), style={"color": UP if t["side"] == "long" else DN, "fontWeight": "bold"}),
                html.Td(t["regime"]), html.Td(f"{t['entry']:.5f}"), html.Td(f"{last:.5f}"),
                html.Td(f"${t['size_usd']:.1f}"),
                html.Td(f"{pnl:+.2f}", style={"color": color, "fontWeight": "bold", "fontSize": 13}),
                html.Td(f"{t['trail_stop']:.5f}" if t["trail_stop"] else "—", style={"fontSize": 11, "color": MUT}),
                html.Td(f"{len(t['partials'])}", style={"fontSize": 11, "color": ACCENT}),
            ]))
        table = dbc.Table([
            html.Thead(html.Tr([html.Th(x) for x in
                                ["شناسه", "نماد", "سمت", "رژیم", "ورود", "فعلی", "مارجین", "سود/زیان", "تریل", "جزئی"]],
                               style={"color": GOLD, "fontSize": 12})),
            html.Tbody(rows)
        ], bordered=True, hover=True, size="sm", style={"background": CARD, "direction": "rtl", "textAlign": "center"})
    else:
        table = dbc.Alert("در حال اسکن بازار و تشکیل اجماع ارگانیسم‌ها...", color="dark",
                          style={"textAlign": "center", "border": f"1px dashed {LINE}"})

    eqh = get_equity_history()
    if eqh.empty:
        eqh = pd.DataFrame({"ts": [datetime.now(timezone.utc).isoformat()], "equity": [INITIAL_CAPITAL]})
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=pd.to_datetime(eqh["ts"]), y=eqh["equity"], mode="lines",
                             line=dict(color=GOLD, width=2.5), fill="tozeroy", fillcolor="rgba(240,185,11,0.08)"))
    fig.add_hline(y=INITIAL_CAPITAL, line_dash="dot", line_color=MUT, annotation_text="سرمایه اولیه")
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=300,
                      margin=dict(l=40, r=20, t=40, b=30),
                      title=dict(text="منحنی سهام زنده", font=dict(color=GOLD, size=14), x=0.5),
                      xaxis=dict(gridcolor=LINE, showgrid=True),
                      yaxis=dict(gridcolor=LINE, tickprefix="$", showgrid=True),
                      font=dict(family="Vazirmatn, Tahoma, sans-serif"))

    wr = (sum(1 for t in closed if t["pnl"] and t["pnl"] > 0) / len(closed) * 100) if closed else 0
    total = sum(t["pnl"] or 0 for t in closed)
    dd = ((h.peak - eq) / h.peak * 100) if h.peak > eq else 0

    return html.Div([
        dbc.Row([
            dbc.Col(card("ارزش سهام", f"${eq:.2f}", GOLD, f"سقف: ${h.peak:.2f}", "◈"), md=3),
            dbc.Col(card("نرخ برد", f"{wr:.1f}%", UP if wr >= 50 else DN, f"معاملات: {len(closed)}", "▲"), md=3),
            dbc.Col(card("سود تحقق‌یافته", f"${total:+.2f}", UP if total >= 0 else DN, f" streak: {h.win_streak}", "◆"),
                    md=3),
            dbc.Col(card("پوزیشن باز", f"{len(opens)}/{MAX_POSITIONS}", NEON, f"DD: {dd:.1f}%", "●"), md=3),
        ], className="mb-3"),
        html.H5("پوزیشن‌های فعال (Partial + Trailing Stop)",
                style={"color": GOLD, "marginTop": 16, "marginBottom": 12}),
        table,
        dcc.Graph(figure=fig, config={"displaylogo": False}, style={"marginTop": 16}),
    ])


def stats_tab():
    h = HIVE
    eq = h.equity()
    rc = h.last_stats.get("regime_counts", {})
    # نمودار رژیم
    if rc:
        regime_fig = go.Figure(data=[go.Pie(labels=list(rc.keys()), values=list(rc.values()),
                                            hole=0.55, marker=dict(colors=[NEON, ACCENT, ORANGE, DN]))])
        regime_fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                                 plot_bgcolor="rgba(0,0,0,0)", height=220,
                                 showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.2),
                                 margin=dict(l=10, r=10, t=10, b=10),
                                 font=dict(family="Vazirmatn, Tahoma, sans-serif"))
    else:
        regime_fig = go.Figure()

    return html.Div([
        dbc.Row([
            dbc.Col(card("ارزش سهام", f"${eq:.2f}", GOLD, "", "◈"), md=2),
            dbc.Col(card("نسل تکامل", f"{getattr(h, 'generation', 0)}", NEON, "نسخه DNA فعال", "◉"), md=2),
            dbc.Col(card("سطح آگاهی", f"{h.awareness:.0%}", ACCENT if h.awareness > 0.8 else ORANGE,
                         f"سقف: {AWARENESS_CAP:.0%}", "◉"), md=2),
            dbc.Col(card("نورون‌ها", f"{h.total_neurons():,}", NEON, "توان پردازشی", "◉"), md=2),
            dbc.Col(card("آستانه امتیاز", f"{h.adaptive['score_threshold']:.2f}", ORANGE, "θ-score", "◉"), md=2),
            dbc.Col(card("آستانه اجماع", f"{h.adaptive['conv_threshold']:.2f}", ORANGE, "θ-conv", "◉"), md=2),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([
                html.H5("ارگانیسم‌های فعال", style={"color": GOLD, "marginBottom": 12}),
                dbc.Row([
                    dbc.Col(
                        card(o.name, o.role, NEON if o.role == "SNIPER" else ORANGE if o.role == "SCALPER" else ACCENT,
                             f"{o.neurons:,} نورون | w={o.weight:.3f} | سود: {o.profit_sum:+.1f}", "●"), md=3)
                    for o in h.orgs
                ]),
            ], md=8),
            dbc.Col([
                html.H5("توزیع رژیم آخرین اسکن", style={"color": GOLD, "marginBottom": 12, "textAlign": "center"}),
                dcc.Graph(figure=regime_fig, config={"displaylogo": False})
            ], md=4),
        ], className="mb-3"),
        html.Hr(style={"borderColor": LINE, "opacity": 0.3}),
        html.Div([
            html.Div("قابلیت‌های نسخهٔ v4:", style={"color": GOLD, "fontWeight": "bold", "fontSize": 14}),
            html.Div("۱. تکامل خودکار در استارت (Auto-Evolution) — نیازی به بک‌تست دستی نیست",
                     style={"color": MUT, "marginTop": 6}),
            html.Div("۲. یادگیری پیوسته از معاملات زنده با تنظیم وزن ارگانیسم‌ها",
                     style={"color": MUT, "marginTop": 4}),
            html.Div("۳. آگاهی تطبیقی با سقف ۹۷٪ — هرچه بیشتر معامله کند، هوشمندتر می‌شود",
                     style={"color": MUT, "marginTop": 4}),
            html.Div("۴. مرکز یادگیری بصری با نمودارهای تکاملی لحظه‌ای", style={"color": MUT, "marginTop": 4}),
        ], style={"background": GLASS, "padding": 18, "borderRadius": 12, "border": f"1px solid {LINE}",
                  "marginTop": 16})
    ])


def backtest_tab(bt_data):
    return html.Div([
        html.H5("بک‌تست مبتنی بر مسیر تصمیم زنده", style={"color": GOLD, "marginBottom": 16}),
        dbc.Row([
            dbc.Col(dcc.Input(id="bt-symbol", value="BTCUSDT", type="text",
                              style={"width": "100%", "padding": 10, "borderRadius": 8, "background": CARD,
                                     "color": TXT, "border": f"1px solid {LINE}"}), md=3),
            dbc.Col(dbc.Button("▶ اجرای بک‌تست تک‌نمادی", id="bt-run", color="warning",
                               style={"width": "100%", "fontWeight": "bold", "borderRadius": 8}), md=2),
            dbc.Col(dbc.Button("⏵ تکامل نسلی عمیق", id="bt-evolve", color="info",
                               style={"width": "100%", "fontWeight": "bold", "borderRadius": 8}), md=2),
        ], className="mb-3"),
        html.Div(id="bt-output", children=render_bt_result(bt_data) if bt_data else
        html.Div("نتیجه‌ای هنوز وجود ندارد. بک‌تست یا تکامل را اجرا کنید.",
                 style={"color": MUT, "textAlign": "center", "padding": 40}))
    ])


def render_bt_result(data):
    if not data:
        return html.Div("خطا یا داده ناکافی", style={"color": DN})
    return dbc.Card(dbc.CardBody([
        html.Div(f"نماد: {data['symbol']}", style={"color": GOLD, "fontSize": 16, "fontWeight": "bold"}),
        html.Hr(style={"borderColor": LINE}),
        dbc.Row([
            dbc.Col([
                html.Div(f"تعداد معامله: {data['trades']}", style={"color": TXT}),
                html.Div(f"وین‌ریت: {data['winrate'] * 100:.1f}%",
                         style={"color": UP if data['winrate'] >= 0.5 else DN, "fontSize": 18, "fontWeight": "bold"}),
            ], md=4),
            dbc.Col([
                html.Div(f"بازده کل: {data['total_return'] * 100:+.2f}%",
                         style={"color": UP if data['total_return'] >= 0 else DN, "fontSize": 18,
                                "fontWeight": "bold"}),
                html.Div(f"سرمایه نهایی: ${data['final_capital']:.2f}", style={"color": TXT, "fontSize": 14}),
            ], md=4),
            dbc.Col([
                html.Div(f"میانگین PnL: ${data['avg_pnl']:.2f}", style={"color": TXT, "fontSize": 14}),
                html.Div("وضعیت: موفق" if data['total_return'] > 0 else "وضعیت: نیاز به بهینه‌سازی",
                         style={"color": NEON if data['total_return'] > 0 else ORANGE, "fontWeight": "bold"}),
            ], md=4),
        ]),
        dcc.Graph(
            figure=go.Figure(
                data=[go.Scatter(x=list(range(len(data.get('equity_curve', [])))), y=data.get('equity_curve', []),
                                 mode="lines", line=dict(color=GOLD, width=2), fill="tozeroy",
                                 fillcolor="rgba(240,185,11,0.1)")],
                layout=go.Layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                 height=250, margin=dict(l=40, r=20, t=20, b=30),
                                 xaxis=dict(title="معامله", gridcolor=LINE),
                                 yaxis=dict(title="سرمایه", gridcolor=LINE, tickprefix="$"),
                                 font=dict(family="Vazirmatn, Tahoma, sans-serif"))
            ),
            config={"displaylogo": False},
            style={"marginTop": 16}
        )
    ]), className="card-glass")


def perf_tab():
    perf_df = get_organism_perf(200)
    if perf_df.empty:
        return html.Div("داده‌ای برای نمایش عملکرد ارگانیسم‌ها وجود ندارد.",
                        style={"color": MUT, "textAlign": "center", "padding": 40})

    fig = go.Figure()
    colors = {"Aether": NEON, "Pulse": ORANGE, "Flux": ACCENT, "Vector": GOLD}
    for org in perf_df['organism'].unique():
        sub = perf_df[perf_df['organism'] == org]
        fig.add_trace(go.Bar(
            x=sub['regime'], y=sub['trade_pnl'], name=org,
            marker_color=colors.get(org, TXT)
        ))
    fig.update_layout(
        barmode="group", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=350,
        title="عملکرد ارگانیسم‌ها بر اساس رژیم بازار", font=dict(family="Vazirmatn, Tahoma, sans-serif"),
        xaxis=dict(title="رژیم", gridcolor=LINE), yaxis=dict(title="سود/زیان ($)", gridcolor=LINE)
    )

    return html.Div([
        html.H5("تحلیل عملکرد ارگانیسم‌ها", style={"color": GOLD, "marginBottom": 16}),
        dcc.Graph(figure=fig, config={"displaylogo": False}),
        html.Div(style={"marginTop": 20, "maxHeight": 300, "overflowY": "auto"}, children=[
            dbc.Table.from_dataframe(
                perf_df[['organism', 'regime', 'trade_pnl', 'weight_delta', 'ts']].rename(
                    columns={'organism': 'ارگانیسم', 'regime': 'رژیم', 'trade_pnl': 'سود/زیان',
                             'weight_delta': 'تغییر وزن', 'ts': 'زمان'}
                ), striped=True, bordered=True, hover=True, size="sm",
                style={"color": TXT, "direction": "rtl", "textAlign": "center"}
            )
        ])
    ])


def learning_tab():
    hist_df = get_learning_history()
    if hist_df.empty:
        return html.Div("تاریخچه یادگیری هنوز ثبت نشده است. اجازه دهید سیستم چند معامله انجام دهد.",
                        style={"color": MUT, "textAlign": "center", "padding": 40})

    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=hist_df['generation'], y=hist_df['awareness'], mode="lines+markers", name="آگاهی",
                              line=dict(color=NEON, width=2)))
    fig1.add_trace(go.Scatter(x=hist_df['generation'], y=hist_df['fitness'], mode="lines+markers", name="فیتنس",
                              line=dict(color=GOLD, width=2), yaxis="y2"))
    fig1.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=300,
        title="تکامل آگاهی و فیتنس در نسل‌های مختلف", font=dict(family="Vazirmatn, Tahoma, sans-serif"),
        yaxis=dict(title="آگاهی", gridcolor=LINE),
        yaxis2=dict(title="فیتنس", overlaying="y", side="right", gridcolor=LINE),
        xaxis=dict(title="نسل", gridcolor=LINE)
    )

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=hist_df['generation'], y=hist_df['winrate'], mode="lines+markers", name="وین‌ریت",
                              line=dict(color=UP, width=2)))
    fig2.add_trace(
        go.Scatter(x=hist_df['generation'], y=hist_df['trades_count'], mode="lines+markers", name="تعداد معاملات",
                   line=dict(color=ACCENT, width=2), yaxis="y2"))
    fig2.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=300,
        title="بهبود وین‌ریت و حجم معاملات", font=dict(family="Vazirmatn, Tahoma, sans-serif"),
        yaxis=dict(title="وین‌ریت", gridcolor=LINE),
        yaxis2=dict(title="تعداد معاملات", overlaying="y", side="right", gridcolor=LINE),
        xaxis=dict(title="نسل", gridcolor=LINE)
    )

    return html.Div([
        html.H5("مرکز یادگیری و تکامل", style={"color": GOLD, "marginBottom": 16}),
        dbc.Row([
            dbc.Col(dcc.Graph(figure=fig1, config={"displaylogo": False}), md=6),
            dbc.Col(dcc.Graph(figure=fig2, config={"displaylogo": False}), md=6),
        ]),
        html.Div(style={"marginTop": 20, "maxHeight": 300, "overflowY": "auto"}, children=[
            dbc.Table.from_dataframe(
                hist_df[['generation', 'awareness', 'fitness', 'winrate', 'trades_count']].rename(
                    columns={'generation': 'نسل', 'awareness': 'آگاهی', 'fitness': 'فیتنس', 'winrate': 'وین‌ریت',
                             'trades_count': 'تعداد معاملات'}
                ).round(4), striped=True, bordered=True, hover=True, size="sm",
                style={"color": TXT, "direction": "rtl", "textAlign": "center"}
            )
        ])
    ])


# ──────────────────────────────────────────────────────────────
# کال‌بک‌های دشبورد
@app.callback(Output("bt-result", "data"), Input("bt-run", "n_clicks"), State("bt-symbol", "value"),
              prevent_initial_call=True)
def run_backtest_cb(n, symbol):
    if not symbol:
        return None
    res = run_backtest(symbol.upper().strip(), candles=5000, hive=HIVE)
    return res


@app.callback(Output("bt-result", "data", allow_duplicate=True), Input("bt-evolve", "n_clicks"),
              prevent_initial_call=True)
def run_evolve_cb(n):
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    res = run_generation(HIVE, symbols, candles=3000)
    return {
        "symbol": "EVOLUTION", "trades": res['trades'], "winrate": res['winrate'],
        "total_return": res['mutated_fitness'], "final_capital": HIVE.capital,
        "avg_pnl": 0.0, "equity_curve": [INITIAL_CAPITAL, HIVE.capital], "generation": res['generation']
    }


@app.callback(Output("pulse", "children"), Input("life", "n_intervals"))
def update_pulse(n):
    HIVE.cycle()
    eq = HIVE.equity()
    return f"♥ ضربان: {HIVE.heart_beat} | سرمایه: ${eq:.2f} | آگاهی: {HIVE.awareness:.1%}"


@app.callback(Output("status", "children"), Input("life", "n_intervals"))
def update_status(n):
    return f"اسکن: {HIVE.last_stats.get('scanned', 0)} | کاندید: {HIVE.last_stats.get('cands', 0)} | باز: {HIVE.last_stats.get('opened', 0)}"


if __name__ == '__main__':
    print("=" * 60)
    print("HIVE SCALPER-SNIPER PRO — v4 ULTIMATE LEARNING EDITION")
    print(f"Initial Capital: ${INITIAL_CAPITAL} | Leverage: {LEVERAGE}x | Max Positions: {MAX_POSITIONS}")
    print(f"Neurons: {HIVE.total_neurons():,} | Awareness: {HIVE.awareness:.1%}")
    print("Starting Dash server on http://0.0.0.0:8050")
    print("=" * 60)
    app.run(debug=False, host="0.0.0.0", port=8050)