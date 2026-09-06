# -*- coding: utf-8 -*-
"""
HIVE SCALPER-SNIPER PRO — v3 GENERATIONAL
لوریج ۲۰× | اسکالپ + اسنایپر | اسکن ~۱۰۰ نماد | حداکثر ۵ پوزیشن

نسبت به نسخهٔ ۲ سه قابلیت اضافه شده است:
  A. واکشی صفحه‌بندی‌شدهٔ تا ۱۰٬۰۰۰ کندل (get_klines_paginated)
  B. بک‌تست مبتنی بر مسیر تصمیم زنده (HivePro.decide) به‌جای منطق سبک مومنتوم
  C. تداوم DNA (save/load_dna_state) + حلقهٔ تکامل نسلی تپه‌نوردی (run_generation)

هشدار: شبیه‌ساز است. سود تضمینی وجود ندارد. لوریج ۲۰× بسیار پرریسک است.
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
# رنگ‌ها
BG, CARD, LINE, TXT, MUT = "#0b1220", "#121c30", "#23314d", "#e8ecf4", "#8fa3c0"
GOLD, UP, DN, NEON, ACCENT, ORANGE = "#f0b90b", "#16a085", "#e74c3c", "#00f5d4", "#7b61ff", "#ff9f1c"

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

# ── پچ A: واکشی صفحه‌بندی‌شده تا ۱۰٬۰۰۰ کندل ──────────────────
def get_klines_paginated(symbol, interval="5", total=10000, category="linear"):
    """واکشی total کندل با پیمایش معکوس روی پارامتر end در API بایبیت."""
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
        end = oldest - 1                 # صفحهٔ بعدی: قدیمی‌تر از قدیمی‌ترین کندل فعلی
        if len(rows) < 1000:
            break                        # به ابتدای تاریخچه رسیدیم
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
SLIPPAGE_BPS = 1.2          # لغزش شبیه‌سازی‌شده
MIN_TURNOVER_24H = 1_200_000
MAX_SPREAD_BPS = 4.5
RISK_PER_TRADE_BASE = 0.011
CPU_CORES = os.cpu_count() or 4
NEURON_BASE = CPU_CORES * 3072

# ── پچ C-1: مسیر و توابع تداوم DNA ────────────────────────────
DNA_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hive_dna_state.json")

def save_dna_state(hive):
    """نوشتن اتمیک وضعیت تکاملی روی دیسک."""
    try:
        state = {
            "generation": getattr(hive, "generation", 0),
            "adaptive": hive.adaptive,
            "awareness": hive.awareness,
            "win_streak": getattr(hive, "win_streak", 0),
            "loss_streak": getattr(hive, "loss_streak", 0),
            "organism_weights": {o.name: o.weight for o in hive.orgs},
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        tmp = DNA_STATE_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, DNA_STATE_PATH)      # نوشتن اتمیک
    except Exception:
        pass

def load_dna_state():
    try:
        with open(DNA_STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return None

# ──────────────────────────────────────────────────────────────
# دیتابیس پیشرفته
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
         t["entry_time"], "open", t.get("reason",""), json.dumps(t.get("votes",{})),
         t.get("regime",""), json.dumps(t.get("features",{})), json.dumps(t.get("partials",[])), t.get("trail_stop")))
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
    return [{"id":r[0],"symbol":r[1],"side":r[2],"entry":r[3],"exit":r[4],"size_usd":r[5],"pnl":r[6],
             "entry_time":r[7],"exit_time":r[8],"reason":r[9],"regime":r[10]} for r in rows]

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

# ──────────────────────────────────────────────────────────────
# رژیم‌دیتکشن قوی
def detect_regime(df):
    """بازگرداندن: TREND_UP, TREND_DOWN, RANGING, HIGH_VOL"""
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
    "TREND_UP":   {"tp": 0.0065, "sl": 0.0032, "risk_mult": 1.15, "trail_mult": 1.3, "partial_at": 0.0035},
    "TREND_DOWN": {"tp": 0.0065, "sl": 0.0032, "risk_mult": 1.15, "trail_mult": 1.3, "partial_at": 0.0035},
    "RANGING":    {"tp": 0.0038, "sl": 0.0024, "risk_mult": 0.85, "trail_mult": 0.9, "partial_at": 0.0022},
    "HIGH_VOL":   {"tp": 0.0085, "sl": 0.0045, "risk_mult": 0.70, "trail_mult": 1.5, "partial_at": 0.0045},
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
    atr = pd.Series(np.maximum(df["high"]-df["low"], np.maximum(abs(df["high"]-df["close"].shift(1)), abs(df["low"]-df["close"].shift(1))))).rolling(14).mean().iloc[-1]
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

    def score(self, feat, regime):
        mom, vs, pr, sq, re = feat["mom"], feat["vol_surge"], feat["pressure"], feat["spread_q"], feat["rsi_ext"]
        if self.role == "SNIPER":
            s = 0.34*mom + 0.24*vs + 0.24*pr + 0.18*sq
            if abs(s) < 0.40 or abs(re) < 0.25:
                return 0.0
            if regime in ("TREND_UP", "TREND_DOWN") and np.sign(s) != np.sign(mom):
                s *= 0.6
            return s * 1.28 * self.weight
        elif self.role == "SCALPER":
            s = 0.28*mom + 0.38*vs + 0.22*pr + 0.12*sq
            return s * 1.18 * self.weight
        elif self.role == "FLOW":
            s = 0.18*mom + 0.36*vs + 0.34*pr + 0.12*sq
            return s * 1.12 * self.weight
        else:  # MOMENTUM
            s = 0.42*mom + 0.26*vs + 0.20*pr + 0.12*re
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
            Organism("Pulse",  "SCALPER", 1.32),
            Organism("Flux",   "FLOW", 1.22),
            Organism("Vector", "MOMENTUM", 1.12),
        ]
        self.last_stats = {"scanned": 0, "cands": 0, "opened": 0, "regime_counts": {}}
        self._lock = threading.Lock()
        self.heart_beat = 0

        # ── پچ C-2: بارگیری DNA (فایل بر دیتابیس اولویت دارد) ──
        self.generation = 0
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
            log_decision(sym, decision["side"], decision["conv"], regime, feat, decision["votes"], True, decision["reason"])
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
                partials.append({"level": "p1", "frac": part_frac, "price": last, "pnl": part_pnl, "ts": now.isoformat()})
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
                final_pnl = pnl_pct * t["size_usd"] * remain_frac * LEVERAGE - t["size_usd"] * remain_frac * COMMISSION * 2
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
        """۶. یادگیری بعد از معامله — تنظیم آستانه‌ها + تداوم DNA"""
        closed = get_closed_trades(40)
        if len(closed) < 8:
            save_dna_state(self)   # حتی با نمونهٔ کم، وضعیت را ماندگار کن
            return
        wins = [t for t in closed if t["pnl"] and t["pnl"] > 0]
        wr = len(wins) / len(closed)
        if wr > 0.58 and pnl > 0:
            self.adaptive["score_threshold"] = max(0.45, self.adaptive["score_threshold"] - 0.008)
            self.adaptive["conv_threshold"] = max(0.36, self.adaptive["conv_threshold"] - 0.006)
            self.awareness = min(0.96, self.awareness + 0.004)
        elif wr < 0.42:
            self.adaptive["score_threshold"] = min(0.62, self.adaptive["score_threshold"] + 0.012)
            self.adaptive["conv_threshold"] = min(0.50, self.adaptive["conv_threshold"] + 0.010)
            self.awareness = max(0.40, self.awareness - 0.003)
        db_set("adaptive", self.adaptive)
        db_set("awareness", self.awareness)
        save_dna_state(self)       # ── پچ C-3: نوشتن DNA پس از هر یادگیری ──

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
# ── پچ B: بک‌تست مبتنی بر مسیر تصمیم زنده (HivePro.decide) ─────
def run_backtest(symbol, candles=10000, interval="5", df=None, hive=None):
    """
    بک‌تست با همان منطق تصمیم زنده:
      - ورود از HivePro.decide (نه منطق سبک مومنتوم)
      - چند پوزیشن هم‌زمان تا MAX_POSITIONS، بدون قفل تک‌پوزیشنی
      - مدیریت پوزیشن آینهٔ manage_positions: خروج جزئی ۴۰٪، تریلینگ، توقف زمانی
    """
    if df is None:
        df = get_klines_paginated(symbol, interval=interval, total=candles)
    if df is None or df.empty or len(df) < 100:
        return None

    hive = hive or HivePro()          # DNA ذخیره‌شده هنگام ساخت بارگیری می‌شود
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

        # ── مدیریت پوزیشن‌های باز (آینهٔ manage_positions) ──
        for pos in list(positions):
            pos["hold"] += 1
            sm = 1 if pos["side"] == "long" else -1
            pos["best"] = max(pos["best"], high) if sm == 1 else min(pos["best"], low)
            pnl_pct = sm * (close - pos["entry"]) / pos["entry"]
            rp_p = pos["rp"]

            if pnl_pct <= -rp_p["sl"] or pnl_pct >= rp_p["tp"]:
                close_fraction(pos, close, pos["frac"]); positions.remove(pos); continue

            if not pos["partial_done"] and pnl_pct >= rp_p["partial_at"]:
                close_fraction(pos, close, 0.40)      # بستن ۴۰٪
                pos["partial_done"] = True

            trail = rp_p["sl"] * (0.7 if pos["partial_done"] else rp_p["trail_mult"] * 0.6)
            retrace = sm * (pos["best"] - close) / pos["entry"]
            if pnl_pct > 0 and retrace >= trail:
                close_fraction(pos, close, pos["frac"]); positions.remove(pos); continue

            if pos["hold"] >= 22:                     # توقف زمانی
                close_fraction(pos, close, pos["frac"]); positions.remove(pos); continue
            if pos["hold"] > 5 and abs(pnl_pct) < 0.0008:   # رکود
                close_fraction(pos, close, pos["frac"]); positions.remove(pos); continue

        # ── ورود از مسیر زنده ──
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

    for pos in list(positions):       # تسویهٔ باقی‌مانده در آخرین قیمت
        close_fraction(pos, float(df["close"].iloc[-1]), pos["frac"])

    if not trades:
        return None
    pnls = [t["pnl"] for t in trades]
    wr = sum(1 for p in pnls if p > 0) / len(pnls)
    total_ret = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL
    return {
        "symbol": symbol, "trades": len(trades), "winrate": wr,
        "total_return": total_ret, "final_capital": capital,
        "avg_pnl": float(np.mean(pnls)), "equity_curve": equity_curve[-100:],
        "generation": getattr(hive, "generation", 0)
    }

# ── پچ C-4: حلقهٔ تکامل نسلی (تپه‌نوردی) ──────────────────────
def run_generation(hive, symbols, candles=10000):
    """یک نسل تکامل: جهش پارامترها، ارزیابی، و نگه‌داشتن جهش بهتر."""
    def fitness(results):
        f = 0.0
        for r in results:
            if not r:
                continue
            f += r["total_return"] * (0.5 + 0.5 * r["winrate"])
            if r["trades"] < 10:
                f -= 0.5              # جریمهٔ کم‌معاملگی
        return f

    data = {s: get_klines_paginated(s, total=candles) for s in symbols}

    save_dna_state(hive)             # پایه را ماندگار کن
    base_fit = fitness([run_backtest(s, df=data[s], hive=hive) for s in symbols])

    snap_a = dict(hive.adaptive)
    snap_w = {o.name: o.weight for o in hive.orgs}

    hive.adaptive["score_threshold"] = float(np.clip(
        snap_a["score_threshold"] * (1 + np.random.normal(0, 0.07)), 0.30, 0.90))
    hive.adaptive["conv_threshold"] = float(np.clip(
        snap_a["conv_threshold"] * (1 + np.random.normal(0, 0.07)), 0.20, 0.80))
    for o in hive.orgs:
        o.weight = float(np.clip(o.weight * (1 + np.random.normal(0, 0.07)), 0.5, 2.0))

    save_dna_state(hive)
    mut_fit = fitness([run_backtest(s, df=data[s], hive=hive) for s in symbols])

    kept = mut_fit > base_fit        # تپه‌نوردی: فقط جهش بهتر می‌ماند
    if not kept:
        hive.adaptive.update(snap_a)
        for o in hive.orgs:
            o.weight = snap_w[o.name]

    hive.generation = getattr(hive, "generation", 0) + 1
    save_dna_state(hive)
    db_set("adaptive", hive.adaptive)
    return {"generation": hive.generation, "base_fitness": base_fit,
            "mutated_fitness": mut_fit, "kept_mutation": kept}

# ──────────────────────────────────────────────────────────────
# نمونه سراسری
HIVE = HivePro()

# ──────────────────────────────────────────────────────────────
# رابط کاربری
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG], suppress_callback_exceptions=True)
app.title = "HIVE PRO v3 — Generational"
server = app.server

def card(title, val, color=GOLD, sub=""):
    return dbc.Card(dbc.CardBody([
        html.Div(title, style={"color": MUT, "fontSize": 11}),
        html.Div(str(val), style={"color": color, "fontSize": 19, "fontWeight": "bold"}),
        html.Div(sub, style={"color": MUT, "fontSize": 10})
    ]), style={"background": CARD, "border": f"1px solid {LINE}", "height": "100%"})

app.layout = html.Div([
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col(html.H3("HIVE PRO v3  ×20  GENERATIONAL", style={"color": GOLD, "margin": 0}), md=5),
        dbc.Col(html.Div(id="pulse", style={"color": NEON, "fontFamily": "monospace", "fontSize": 13}), md=4),
        dbc.Col(html.Div(id="status", style={"textAlign": "right", "color": MUT, "fontSize": 12}), md=3),
    ])), style={"margin": "8px 12px", "background": CARD, "border": f"1px solid {LINE}"}),

    dcc.Tabs(id="tabs", value="live", children=[
        dcc.Tab(label="معاملات زنده", value="live", style={"background": CARD, "color": TXT}, selected_style={"background": LINE, "color": GOLD}),
        dcc.Tab(label="وضعیت Hive + رژیم", value="stats", style={"background": CARD, "color": TXT}, selected_style={"background": LINE, "color": GOLD}),
        dcc.Tab(label="بک‌تست", value="backtest", style={"background": CARD, "color": TXT}, selected_style={"background": LINE, "color": GOLD}),
        dcc.Tab(label="تحلیل عملکرد", value="perf", style={"background": CARD, "color": TXT}, selected_style={"background": LINE, "color": GOLD}),
    ], style={"margin": "0 12px"}),
    html.Div(id="content", style={"padding": "12px"}),
    dcc.Interval(id="life", interval=11_000, n_intervals=0),
    dcc.Interval(id="cycle", interval=32_000, n_intervals=0),
    dcc.Store(id="bt-result"),
], style={"background": BG, "minHeight": "100vh", "color": TXT})

@app.callback(Output("content", "children"), Input("tabs", "value"), Input("life", "n_intervals"), Input("bt-result", "data"))
def render(tab, n, bt_data):
    if tab == "live":
        return live_tab()
    if tab == "stats":
        return stats_tab()
    if tab == "backtest":
        return backtest_tab(bt_data)
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
                html.Td(t["side"].upper(), style={"color": UP if t["side"]=="long" else DN}),
                html.Td(t["regime"]), html.Td(f"{t['entry']:.5f}"), html.Td(f"{last:.5f}"),
                html.Td(f"${t['size_usd']:.1f}"), html.Td(f"{pnl:+.2f}", style={"color": color, "fontWeight": "bold"}),
                html.Td(f"{t['trail_stop']:.5f}" if t["trail_stop"] else "—", style={"fontSize": 11}),
                html.Td(f"{len(t['partials'])}", style={"fontSize": 11}),
            ]))
        table = dbc.Table([
            html.Thead(html.Tr([html.Th(x) for x in ["ID","نماد","سمت","رژیم","ورود","فعلی","مارجین","PnL","Trail","Partial"]])),
            html.Tbody(rows)
        ], bordered=True, hover=True, size="sm", style={"background": CARD})
    else:
        table = dbc.Alert("در حال اسکن و تشکیل اجماع...", color="secondary")

    eqh = get_equity_history()
    if eqh.empty:
        eqh = pd.DataFrame({"ts": [datetime.now(timezone.utc).isoformat()], "equity": [INITIAL_CAPITAL]})
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=pd.to_datetime(eqh["ts"]), y=eqh["equity"], mode="lines",
                             line=dict(color=GOLD, width=2), fill="tozeroy", fillcolor="rgba(240,185,11,0.1)"))
    fig.add_hline(y=INITIAL_CAPITAL, line_dash="dot", line_color=MUT)
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD, height=270,
                      margin=dict(l=40, r=20, t=30, b=30), title=dict(text="Equity Live", font=dict(color=GOLD, size=13)),
                      xaxis=dict(gridcolor=LINE), yaxis=dict(gridcolor=LINE, tickprefix="$"))

    wr = (sum(1 for t in closed if t["pnl"] and t["pnl"] > 0) / len(closed) * 100) if closed else 0
    total = sum(t["pnl"] or 0 for t in closed)
    return html.Div([
        dbc.Row([
            dbc.Col(card("Equity", f"${eq:.2f}", GOLD, f"Peak ${h.peak:.2f}"), md=3),
            dbc.Col(card("WinRate", f"{wr:.1f}%", UP if wr >= 50 else DN), md=3),
            dbc.Col(card("Realized", f"${total:+.2f}", UP if total >= 0 else DN), md=3),
            dbc.Col(card("Open", f"{len(opens)}/{MAX_POSITIONS}", NEON), md=3),
        ], className="mb-3"),
        html.H5("پوزیشن‌های باز (Partial + Trailing فعال)", style={"color": GOLD}),
        table,
        dcc.Graph(figure=fig, config={"displaylogo": False}),
    ])

def stats_tab():
    h = HIVE
    eq = h.equity()
    rc = h.last_stats.get("regime_counts", {})
    return html.Div([
        dbc.Row([
            dbc.Col(card("Equity", f"${eq:.2f}", GOLD), md=2),
            dbc.Col(card("نسل", f"{getattr(h,'generation',0)}", NEON), md=2),
            dbc.Col(card("آگاهی", f"{h.awareness:.0%}", NEON), md=2),
            dbc.Col(card("نورون", f"{h.total_neurons():,}", ACCENT), md=2),
            dbc.Col(card("آستانه امتیاز", f"{h.adaptive['score_threshold']:.2f}", ORANGE), md=2),
            dbc.Col(card("آستانه Conv", f"{h.adaptive['conv_threshold']:.2f}", ORANGE), md=2),
        ], className="mb-3"),
        html.H5("ارگانیسم‌ها", style={"color": GOLD}),
        dbc.Row([
            dbc.Col(card(o.name, o.role, NEON if o.role=="SNIPER" else ORANGE if o.role=="SCALPER" else ACCENT,
                         f"{o.neurons:,} ن | w={o.weight:.3f}"), md=3) for o in h.orgs
        ], className="mb-3"),
        html.H5("توزیع رژیم آخرین اسکن", style={"color": GOLD}),
        html.Div([html.Span(f"{k}: {v}   ", style={"color": NEON if "TREND" in k else MUT}) for k, v in rc.items()] or "—"),
        html.Hr(style={"borderColor": LINE}),
        html.Div([
            html.Div("قابلیت‌های نسخهٔ v3:", style={"color": GOLD, "fontWeight": "bold"}),
            html.Div("A. واکشی صفحه‌بندی‌شدهٔ تا ۱۰٬۰۰۰ کندل", style={"color": MUT}),
            html.Div("B. بک‌تست مبتنی بر مسیر تصمیم زنده (HivePro.decide) با چند پوزیشن", style={"color": MUT}),
            html.Div("C. تداوم DNA روی دیسک + تکامل نسلی تپه‌نوردی", style={"color": MUT}),
        ], style={"background": CARD, "padding": 14, "borderRadius": 8, "border": f"1px solid {LINE}"})
    ])

def backtest_tab(bt_data):
    return html.Div([
        html.H5("بک‌تست (مسیر تصمیم زنده)", style={"color": GOLD}),
        dbc.Row([
            dbc.Col(dcc.Input(id="bt-symbol", value="BTCUSDT", type="text",
                              style={"width": "100%", "padding": 8, "borderRadius": 6}), md=3),
            dbc.Col(dbc.Button("اجرای بک‌تست", id="bt-run", color="warning", style={"width": "100%", "fontWeight": "bold"}), md=2),
        ], className="mb-3"),
        html.Div(id="bt-output", children=render_bt_result(bt_data) if bt_data else "نتیجه‌ای هنوز وجود ندارد.")
    ])

def render_bt_result(data):
    if not data:
        return "خطا یا داده ناکافی"
    return dbc.Card(dbc.CardBody([
        html.Div(f"نماد: {data['symbol']}", style={"color": GOLD}),
        html.Div(f"تعداد معامله: {data['trades']}"),
        html.Div(f"وین‌ریت: {data['winrate']*100:.1f}%", style={"color": UP if data['winrate']>=0.5 else DN}),
        html.Div(f"بازده کل: {data['total_return']*100:+.2f}%", style={"color": UP if data['total_return']>=0 else DN}),
        html.Div(f"سرمایه نهایی: ${data['final_capital']:.2f}"),
        html.Div(f"میانگین PnL: ${data['avg_pnl']:+.2f}"),
        html.Div(f"نسل: {data.get('generation', 0)}", style={"color": MUT}),
    ]), style={"background": CARD, "border": f"1px solid {LINE}"})

def perf_tab():
    closed = get_closed_trades(100)
    if not closed:
        return html.Div("هنوز معامله بسته‌شده‌ای برای تحلیل وجود ندارد.", style={"color": MUT})
    pnls = [t["pnl"] for t in closed if t["pnl"] is not None]
    wr = sum(1 for p in pnls if p > 0) / len(pnls) if pnls else 0
    by_regime = defaultdict(list)
    for t in closed:
        by_regime[t.get("regime") or "UNK"].append(t["pnl"] or 0)
    regime_stats = []
    for reg, vals in by_regime.items():
        if vals:
            regime_stats.append(html.Div(f"{reg}: n={len(vals)} | WR={sum(1 for v in vals if v>0)/len(vals)*100:.0f}% | Avg={np.mean(vals):+.2f}"))
    return html.Div([
        html.H5("تحلیل عملکرد (یادگیری بعد از معامله)", style={"color": GOLD}),
        dbc.Row([
            dbc.Col(card("WinRate", f"{wr*100:.1f}%", UP if wr>=0.5 else DN), md=3),
            dbc.Col(card("Avg PnL", f"${np.mean(pnls):+.2f}" if pnls else "—", GOLD), md=3),
            dbc.Col(card("Best", f"${max(pnls):+.2f}" if pnls else "—", UP), md=3),
            dbc.Col(card("Worst", f"${min(pnls):+.2f}" if pnls else "—", DN), md=3),
        ], className="mb-3"),
        html.H5("عملکرد بر اساس رژیم", style={"color": GOLD}),
        html.Div(regime_stats, style={"background": CARD, "padding": 12, "borderRadius": 8}),
        html.P("آستانه‌ها و وزن‌های ارگانیسم‌ها روی دیسک (hive_dna_state.json) ماندگار می‌شوند و بین اجراها ادامه می‌یابند.", style={"color": MUT, "marginTop": 12})
    ])

@app.callback(Output("pulse", "children"), Output("status", "children"), Input("life", "n_intervals"))
def header(n):
    h = HIVE
    h.heart_beat += 1
    return (f"BEAT #{h.heart_beat}  |  GEN {getattr(h,'generation',0)}  |  θ={h.adaptive['score_threshold']:.2f}",
            f"نورون {h.total_neurons():,} | آگاهی {h.awareness:.0%} | لوریج {LEVERAGE}×")

@app.callback(Output("cycle", "disabled"), Input("cycle", "n_intervals"), prevent_initial_call=False)
def run_cycle(n):
    HIVE.cycle()
    return False

@app.callback(Output("bt-result", "data"), Input("bt-run", "n_clicks"), State("bt-symbol", "value"), prevent_initial_call=True)
def do_backtest(n, symbol):
    if not n:
        return None
    symbol = (symbol or "BTCUSDT").upper().strip()
    result = run_backtest(symbol, candles=5000)   # UI: ۵۰۰۰ کندل؛ برای ۱۰٬۰۰۰ عدد را افزایش دهید
    return result

if __name__ == "__main__":
    print("HIVE PRO v3 GENERATIONAL starting...")
    print(f"Neurons: {HIVE.total_neurons():,} | Leverage: {LEVERAGE}x | Max Pos: {MAX_POSITIONS} | Gen: {HIVE.generation}")
    print("Features: Paginated Klines | Live-decide Backtest | DNA Persistence + Generational Evolution")
    print("WARNING: Simulation only. 20x leverage is extremely risky. No profit guarantee.")
    app.run(debug=True, host="0.0.0.0", port=8060, use_reloader=False)
