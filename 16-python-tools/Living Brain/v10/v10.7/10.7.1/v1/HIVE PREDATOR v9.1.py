# -*- coding: utf-8 -*-
"""
HIVE PREDATOR v9.10-FINAL — REAL-TIME GENOME EVOLUTION IN BACKTEST
---------------------------------------------
تغییرات کلیدی:
۱. آپدیت آنی ژنوم در حین بک‌تست: با هر معامله بسته‌شده، نسل افزایش یافته و ژنوم در دیتابیس ذخیره می‌شود.
۲. رفع deadlock: نسل در هر سایکل زنده نیز افزایش می‌یابد.
۳. نمایش پیشرفت تکامل با نوار پیشرفت دقیق در UI.
"""

import os, time, json, math, sqlite3, threading
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import concurrent.futures
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

# ──────────────────────────────────────────────────────────────
# ۱. پیکربندی
# ──────────────────────────────────────────────────────────────
BG = "#05080f"
CARD = "rgba(8, 14, 26, 0.9)"
CARD_SOLID = "#0a101f"
TXT = "#eaf2ff"
MUT = "#8ea2c7"
GOLD = "#f5c542"
CYAN = "#14d9ff"
UP = "#00ffd0"
DN = "#ff2a6d"
NEON = "#7c5cff"
LINE = "#1a253a"

LEVERAGE = 20
INITIAL_CAPITAL = 500.0
MAX_POSITIONS = 5
COMMISSION = 0.0006
SLIPPAGE_BPS = 1.5   
MIN_TURNOVER_24H = 500_000
MAX_SPREAD_BPS = 5.0
RISK_PER_TRADE_BASE = 0.025
MAX_CANDLE_AGE_MINUTES = 15
MAX_PRICE_DEVIATION = 0.10
MIN_CONVICTION = 0.10
MIN_GENERATION_FOR_TRADING = 100

# ──────────────────────────────────────────────────────────────
# ۲. توابع کمکی
# ──────────────────────────────────────────────────────────────
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    def rtl_text(s: str) -> str:
        try: return get_display(arabic_reshaper.reshape(str(s)))
        except: return str(s)
except:
    def rtl_text(s: str) -> str: return str(s)

def now_utc() -> str: return datetime.now(timezone.utc).isoformat()
def clamp(x, lo, hi): 
    if x is None or (isinstance(x, float) and math.isnan(x)): return lo
    return max(lo, min(hi, x))

# ──────────────────────────────────────────────────────────────
# ۳. هستهٔ تهاجمی
# ──────────────────────────────────────────────────────────────
class PredatorOrganism:
    def __init__(self, name, role, base_weight=1.0, seed=1):
        self.name = name
        self.role = role
        self.base_weight = base_weight
        self.last_vote = "LONG"
        self.conviction = 0.0
        self.regime_score = {"TREND_UP": 0.0, "TREND_DOWN": 0.0, "RANGING": 0.0, "HIGH_VOL": 0.0}
        self.regime_trades = {"TREND_UP": 1, "TREND_DOWN": 1, "RANGING": 1, "HIGH_VOL": 1}

    @property
    def weight(self):
        total_score = sum(self.regime_score.values())
        total_trades = sum(self.regime_trades.values())
        avg_accuracy = total_score / max(1, total_trades)
        return clamp(self.base_weight * (1.0 + avg_accuracy * 2.5), 0.6, 3.5)

    def learn(self, regime: str, reward: float):
        alpha = 0.25
        self.regime_score[regime] = (1 - alpha) * self.regime_score[regime] + alpha * reward
        self.regime_trades[regime] += 1

    def evaluate(self, feat, regime):
        try:
            if self.role == "ALPHA_SNIPER":
                force = (feat["rsi_ext"] * 2.5) + (feat["mom"] * 4.0)
            elif self.role == "HFT_SCALPER":
                force = (feat["vol_surge"] * 5.0) + (feat["mom"] * 3.0)
            elif self.role == "FLOW":
                force = (feat["vol_surge"] * 3.0) + (feat["mom"] * 2.5) + (feat["rsi_ext"] * 1.5)
            else:
                force = feat["mom"] * 5.0 + feat["vol_surge"] * 2.0
            
            if math.isnan(force): force = 0.0
            
            if force > 0:
                self.last_vote = "LONG"
                raw_score = abs(force) * self.weight
            else:
                self.last_vote = "SHORT"
                raw_score = -abs(force) * self.weight
            
            self.conviction = clamp(abs(force) / 6.0, 0.15, 1.0)
            regime_accuracy = self.regime_score[regime] / max(1, self.regime_trades[regime])
            regime_multiplier = clamp(1.0 + regime_accuracy, 0.7, 1.6)
            
            return raw_score * regime_multiplier
        except:
            self.conviction = 0.15
            return 0.0

# ──────────────────────────────────────────────────────────────
# ۴. اتصال و داده
# ──────────────────────────────────────────────────────────────
REST = ["https://api.bybit.com", "https://api.bytick.com"]
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "HivePredator/9.10", "Accept": "application/json"})
_ACTIVE = {"url": None}
_rate_lock = threading.Lock()
_last_req = 0.0

def bybit_get(path, params, timeout=8):
    global _last_req
    with _rate_lock:
        elapsed = time.time() - _last_req
        if elapsed < 0.06: time.sleep(0.06 - elapsed)
        _last_req = time.time()
    
    for base in ([_ACTIVE["url"]] if _ACTIVE["url"] else []) + [u for u in REST if u != _ACTIVE["url"]]:
        try:
            r = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code in (403, 451): continue
            r.raise_for_status()
            d = r.json()
            if d.get("retCode") == 0:
                _ACTIVE["url"] = base
                return d
        except: continue
    return None

def get_klines(symbol, interval="5", limit=1000, category="linear"):
    d = bybit_get("/v5/market/kline", {"category": category, "symbol": symbol, "interval": interval, "limit": limit})
    if not d or "list" not in (d.get("result") or {}): return pd.DataFrame()
    lst = d["result"]["list"]
    if not lst: return pd.DataFrame()
    df = pd.DataFrame(lst, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    for c in ["ts", "open", "high", "low", "close", "volume", "turnover"]: 
        df[c] = pd.to_numeric(df[c], errors='coerce').astype(float)
    return df.sort_values("ts").reset_index(drop=True)

def get_all_tickers():
    d = bybit_get("/v5/market/tickers", {"category": "linear"})
    if not d or not d.get("result", {}).get("list"): return {}
    out = {}
    for t in d["result"]["list"]:
        if not t["symbol"].endswith("USDT"): continue
        try:
            out[t["symbol"]] = {
                "last": float(t["lastPrice"]), 
                "bid": float(t.get("bid1Price") or t["lastPrice"]),
                "ask": float(t.get("ask1Price") or t["lastPrice"]), 
                "vol24": float(t.get("volume24h") or 0), 
                "turn24": float(t.get("turnover24h") or 0), 
                "chg": float(t.get("price24hPcnt") or 0),
            }
        except: continue
    return out

# ──────────────────────────────────────────────────────────────
# ۵. تشخیص رژیم و ویژگی‌ها
# ──────────────────────────────────────────────────────────────
def detect_regime(df):
    if df is None or len(df) < 20: return "RANGING"
    try:
        close = df["close"].values
        high, low = df["high"].values, df["low"].values
        tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
        atr = pd.Series(tr).rolling(14).mean().iloc[-1]
        if np.isnan(atr): return "RANGING"
        atr_pct = atr / close[-1]
        
        if atr_pct > 0.012: return "HIGH_VOL"
        
        ma_fast = pd.Series(close).rolling(6).mean().iloc[-1]
        ma_slow = pd.Series(close).rolling(18).mean().iloc[-1]
        if np.isnan(ma_fast) or np.isnan(ma_slow): return "RANGING"
        slope = (close[-1] - close[-8]) / (close[-8] + 1e-12)
        
        if slope > 0.002 and ma_fast > ma_slow: return "TREND_UP"
        if slope < -0.002 and ma_fast < ma_slow: return "TREND_DOWN"
        return "RANGING"
    except:
        return "RANGING"

REGIME_PARAMS = {
    "TREND_UP":   {"tp": 0.0050, "sl": 0.0025, "risk_mult": 1.3, "trail_mult": 1.5, "partial_at": 0.0028},
    "TREND_DOWN": {"tp": 0.0050, "sl": 0.0025, "risk_mult": 1.3, "trail_mult": 1.5, "partial_at": 0.0028},
    "RANGING":    {"tp": 0.0032, "sl": 0.0018, "risk_mult": 1.0, "trail_mult": 1.1, "partial_at": 0.0018},
    "HIGH_VOL":   {"tp": 0.0070, "sl": 0.0038, "risk_mult": 0.9, "trail_mult": 1.8, "partial_at": 0.0038},
}

def extract_features(df, ticker):
    default_feat = {"mom": 0.0, "vol_surge": 0.0, "spread_q": 0.5, "rsi_ext": 0.0, "atr_pct": 0.01, "rsi": 50.0}
    if df is None or len(df) < 5: return default_feat
    try:
        close, vol = df["close"].values, df["volume"].values
        
        mom = float(np.clip((close[-1] - close[-2]) / (close[-2] + 1e-12) * 40, -1, 1))
        if np.isnan(mom): mom = 0.0
        
        vol_mean = vol[-8:].mean()
        vol_surge = float(np.clip((vol[-1] / (vol_mean + 1e-12) - 1) * 3.0, -1, 1))
        if np.isnan(vol_surge): vol_surge = 0.0
        
        mid = ticker["last"]
        spread_bps = (ticker["ask"] - ticker["bid"]) / (mid + 1e-12) * 10000
        spread_q = float(np.clip(1.0 - spread_bps / MAX_SPREAD_BPS, 0, 1))
        if np.isnan(spread_q): spread_q = 0.5
        
        delta = pd.Series(close).diff()
        gain = delta.clip(lower=0).rolling(5).mean()
        loss = (-delta.clip(upper=0)).rolling(5).mean()
        rs = gain / (loss + 1e-12)
        rsi = 100 - (100 / (1 + rs)).iloc[-1]
        if np.isnan(rsi): rsi = 50.0
        
        rsi_ext = 1.5 if rsi < 30 else (-1.5 if rsi > 70 else (0.8 if rsi < 40 else (-0.8 if rsi > 60 else 0.0)))
        
        tr = np.maximum(df["high"]-df["low"], np.maximum(abs(df["high"]-df["close"].shift(1)), abs(df["low"]-df["close"].shift(1))))
        atr = pd.Series(tr).rolling(14).mean().iloc[-1]
        if np.isnan(atr): atr = close[-1] * 0.01
        
        return {"mom": mom, "vol_surge": vol_surge, "spread_q": spread_q, "rsi_ext": rsi_ext, "atr_pct": float(atr/close[-1]), "rsi": float(rsi)}
    except:
        return default_feat

# ──────────────────────────────────────────────────────────────
# ۶. مدیریت دیتابیس و ژنوم
# ─────────────────────────────────────────────────────────────
DB_PATH = Path("hive_predator_v9.db")
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, side TEXT, entry REAL, size_usd REAL,
        leverage INTEGER, entry_time TEXT, exit_time TEXT, exit_price REAL, pnl REAL, 
        status TEXT, reason TEXT, votes TEXT, regime TEXT, partials TEXT, trail_stop REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, symbol TEXT, regime TEXT, side TEXT, outcome REAL, lesson TEXT)""")
    conn.commit(); conn.close()

def db_get(key, default=None):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    conn.close()
    if row is None: return default
    try: return json.loads(row[0])
    except: return row[0]

def db_set(key, value):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)", (key, json.dumps(value) if not isinstance(value, str) else value))
    conn.commit(); conn.close()

def get_open_trades():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id,symbol,side,entry,size_usd,leverage,entry_time,reason,votes,regime,partials,trail_stop FROM trades WHERE status='open'").fetchall()
    conn.close()
    return [{"id":r[0],"symbol":r[1],"side":r[2],"entry":r[3],"size_usd":r[4],"leverage":r[5],"entry_time":r[6],
             "reason":r[7],"votes":json.loads(r[8] or "{}"),"regime":r[9],"partials":json.loads(r[10] or "[]"),"trail_stop":r[11]} for r in rows]

def save_trade(t):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO trades (symbol,side,entry,size_usd,leverage,entry_time,status,reason,votes,regime,partials,trail_stop)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (t["symbol"], t["side"], t["entry"], t["size_usd"], t["leverage"], t["entry_time"], "open", 
         t["reason"], json.dumps(t["votes"]), t["regime"], json.dumps(t["partials"]), t["trail_stop"]))
    conn.commit(); tid = c.lastrowid; conn.close()
    return tid

def close_trade_full(tid, exit_price, pnl):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE trades SET exit_time=?, exit_price=?, pnl=?, status='closed' WHERE id=?",
                 (now_utc(), exit_price, pnl, tid))
    conn.commit(); conn.close()

def save_genome(hive_instance):
    """ذخیرهٔ وضعیت آموخته‌شدهٔ ارگانیسم‌ها (ژنوم) در دیتابیس تا بین اجراها حفظ شود."""
    genome = {
        o.name: {"regime_score": o.regime_score, "regime_trades": o.regime_trades, "base_weight": o.base_weight}
        for o in hive_instance.orgs
    }
    db_set("genome", genome)

def load_genome(hive_instance):
    """بازیابی ژنوم ذخیره‌شده تا هر اجرا از همان جایی که قبلاً متوقف شده بود ادامه پیدا کند."""
    genome = db_get("genome", None)
    if not genome:
        return
    for o in hive_instance.orgs:
        g = genome.get(o.name)
        if not g:
            continue
        o.regime_score.update(g.get("regime_score", {}))
        o.regime_trades.update(g.get("regime_trades", {}))

# ──────────────────────────────────────────────────────────────
# ۷. مغز شکارچی با تکامل پیوسته
# ──────────────────────────────────────────────────────────────
class PredatorHive:
    def __init__(self):
        init_db()
        self.capital = float(db_get("capital", INITIAL_CAPITAL))
        self.peak = float(db_get("peak", INITIAL_CAPITAL))
        self.generation = int(db_get("generation", 1))
        
        self.adaptive = db_get("adaptive", {"base_threshold": 0.10})
        if self.adaptive.get("base_threshold", 0) > 0.30:
            self.adaptive["base_threshold"] = 0.10
            db_set("adaptive", self.adaptive)
        
        self.orgs = [
            PredatorOrganism("Alpha", "ALPHA_SNIPER", base_weight=2.0, seed=1),
            PredatorOrganism("Pulse", "HFT_SCALPER", base_weight=1.8, seed=2),
            PredatorOrganism("Flux", "FLOW", base_weight=1.4, seed=3),
            PredatorOrganism("Vector", "MOMENTUM", base_weight=1.2, seed=4),
        ]
        load_genome(self)
        self._lock = threading.Lock()
        self.last_stats = {
            "scanned": 0, "cands": 0, "opened": 0, "regime_counts": {}, 
            "rejected_stale": 0, "rejected_price": 0, "rejected_conviction": 0,
            "rejected_margin": 0, "rejected_exists": 0, "rejected_generation": 0,
            "debug_log": [], "evolution_steps": 0
        }
        self.heart_beat = 0

    def decide_predator(self, feat, regime):
        if feat is None: 
            self._add_debug("Features is None")
            return None
        
        long_pool, short_pool = 0.0, 0.0
        votes = []
        
        for o in self.orgs:
            score = o.evaluate(feat, regime)
            side = "long" if o.last_vote == "LONG" else "short"
            if side == "long": long_pool += abs(score)
            else: short_pool += abs(score)
            
            votes.append({"org": o.name, "role": o.role, "side": side, "score": score, "vote": o.last_vote, "conviction": o.conviction, "weight": o.weight})
        
        if long_pool > short_pool and long_pool > self.adaptive["base_threshold"]:
            side, final_conv = "long", long_pool
        elif short_pool > long_pool and short_pool > self.adaptive["base_threshold"]:
            side, final_conv = "short", short_pool
        else:
            self._add_debug(f"Conviction too low - Long: {long_pool:.3f}, Short: {short_pool:.3f}, Threshold: {self.adaptive['base_threshold']:.3f}")
            return None
            
        conv = min(1.0, final_conv / 4.0)
        
        if conv < MIN_CONVICTION:
            self._add_debug(f"Conviction {conv:.3f} below minimum {MIN_CONVICTION}")
            return None
            
        reason = " | ".join([f"{v['org']}:{v['vote']}({v['conviction']:.2f})" for v in votes if v['side'] == side])
        return {"side": side, "conv": conv, "votes": {v["org"]: v for v in votes}, "reason": f"PREDATOR [{side.upper()}]: {reason}", "regime": regime}

    def _add_debug(self, msg):
        self.last_stats["debug_log"].append(f"{datetime.now().strftime('%H:%M:%S')} - {msg}")
        if len(self.last_stats["debug_log"]) > 20:
            self.last_stats["debug_log"].pop(0)

    def try_open(self, sym, ticker, decision, feat, candle_age_minutes):
        with self._lock:
            if self.generation < MIN_GENERATION_FOR_TRADING:
                self._add_debug(f"Generation lock: {self.generation}/{MIN_GENERATION_FOR_TRADING}")
                self.last_stats["rejected_generation"] = self.last_stats.get("rejected_generation", 0) + 1
                return False
            
            opens = get_open_trades()
            
            if any(t["symbol"] == sym for t in opens):
                self._add_debug(f"{sym} already has open position")
                self.last_stats["rejected_exists"] = self.last_stats.get("rejected_exists", 0) + 1
                return False
            
            if len(opens) >= MAX_POSITIONS:
                self._add_debug(f"Max positions reached ({len(opens)}/{MAX_POSITIONS})")
                return False
            
            if candle_age_minutes > MAX_CANDLE_AGE_MINUTES:
                self._add_debug(f"{sym} candle too old: {candle_age_minutes:.1f} min")
                self.last_stats["rejected_stale"] = self.last_stats.get("rejected_stale", 0) + 1
                return False
            
            price = ticker["last"]
            spread_adj = (ticker["ask"] - ticker["bid"]) / 2 / price
            slip = SLIPPAGE_BPS / 10000
            
            if decision["side"] == "long":
                entry = price * (1 + spread_adj + slip)
            else:
                entry = price * (1 - spread_adj - slip)
            
            price_deviation = abs(entry - price) / price
            if price_deviation > MAX_PRICE_DEVIATION:
                self._add_debug(f"{sym} price deviation {price_deviation:.2%} too high")
                self.last_stats["rejected_price"] = self.last_stats.get("rejected_price", 0) + 1
                return False
            
            current_used_margin = sum(t["size_usd"] for t in opens)
            rp = REGIME_PARAMS.get(decision["regime"], REGIME_PARAMS["RANGING"])
            risk_pct = RISK_PER_TRADE_BASE * rp["risk_mult"] * (0.8 + 0.2 * decision["conv"])
            margin = min((self.capital * risk_pct) / (rp["sl"] * LEVERAGE), self.capital * 0.35)
            
            if current_used_margin + margin > self.capital * 0.95:
                self._add_debug(f"Insufficient margin - Used: ${current_used_margin:.1f}, Need: ${margin:.1f}")
                self.last_stats["rejected_margin"] = self.last_stats.get("rejected_margin", 0) + 1
                return False 
            
            if margin < 5:
                self._add_debug(f"Margin too small: ${margin:.2f}")
                return False 
            
            trail = entry * (1 - rp["sl"] * 1.1) if decision["side"] == "long" else entry * (1 + rp["sl"] * 1.1)
                
            t = {
                "symbol": sym, "side": decision["side"], "entry": entry, "size_usd": margin,
                "leverage": LEVERAGE, "entry_time": now_utc(), "reason": decision["reason"],
                "votes": decision["votes"], "regime": decision["regime"], "partials": [], "trail_stop": trail
            }
            save_trade(t)
            self._add_debug(f"✓ OPENED {decision['side'].upper()} {sym} @ {entry:.4f} (${margin:.1f})")
            return True

    def manage_positions(self):
        opens = get_open_trades()
        if not opens: return
        tickers = get_all_tickers()
        now = datetime.now(timezone.utc)
        
        for t in opens:
            last = tickers.get(t["symbol"], {}).get("last")
            if last is None: continue
            
            side = t["side"]
            entry = t["entry"]
            rp = REGIME_PARAMS.get(t["regime"], REGIME_PARAMS["RANGING"])
            
            pnl_pct = (last - entry) / entry if side == "long" else (entry - last) / entry
            remain_frac = 1.0 - sum(p.get("frac", 0) for p in t["partials"])
            
            notional = t["size_usd"] * LEVERAGE 
            
            partials = t["partials"][:]
            if pnl_pct >= rp["partial_at"] and not any(p.get("level") == "p1" for p in partials):
                part_frac = 0.50 
                part_notional = notional * part_frac
                part_pnl = (pnl_pct * part_notional) - (part_notional * COMMISSION * 2)
                partials.append({"level": "p1", "frac": part_frac, "price": last, "pnl": part_pnl, "ts": now.isoformat()})
                self.capital += part_pnl
                trail = last * (1 - rp["sl"] * 0.5) if side == "long" else last * (1 + rp["sl"] * 0.5)
                
                conn = sqlite3.connect(DB_PATH)
                conn.execute("UPDATE trades SET partials=?, trail_stop=? WHERE id=?", (json.dumps(partials), trail, t["id"]))
                conn.commit(); conn.close()
                t["partials"] = partials
                t["trail_stop"] = trail

            if side == "long":
                new_trail = last * (1 - rp["sl"] * rp["trail_mult"] * 0.4)
                if new_trail > t["trail_stop"]:
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute("UPDATE trades SET trail_stop=? WHERE id=?", (new_trail, t["id"]))
                    conn.commit(); conn.close()
                    t["trail_stop"] = new_trail
                hit_trail = last <= t["trail_stop"]
            else:
                new_trail = last * (1 + rp["sl"] * rp["trail_mult"] * 0.4)
                if new_trail < t["trail_stop"]:
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute("UPDATE trades SET trail_stop=? WHERE id=?", (new_trail, t["id"]))
                    conn.commit(); conn.close()
                    t["trail_stop"] = new_trail
                hit_trail = last >= t["trail_stop"]

            full_close = False
            if pnl_pct >= rp["tp"] or pnl_pct <= -rp["sl"]: full_close = True
            if hit_trail: full_close = True
            if (now - datetime.fromisoformat(t["entry_time"])).total_seconds() / 60.0 >= 12: full_close = True 

            if full_close:
                remain_notional = notional * remain_frac
                final_pnl = (pnl_pct * remain_notional) - (remain_notional * COMMISSION * 2)
                total_pnl = final_pnl + sum(p.get("pnl", 0) for p in t["partials"])
                close_trade_full(t["id"], last, total_pnl)
                self.capital += final_pnl
                db_set("capital", self.capital)
                self.learn_from_trade(t, total_pnl)

    def learn_from_trade(self, trade, pnl):
        reward = 1.0 if pnl > 0 else -1.0
        regime = trade["regime"]
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""INSERT INTO memory (ts, symbol, regime, side, outcome, lesson) VALUES (?, ?, ?, ?, ?, ?)""",
            (now_utc(), trade["symbol"], regime, trade["side"], pnl, "WIN" if pnl > 0 else "LOSS"))
        conn.commit(); conn.close()
        
        for o in self.orgs:
            if o.name in trade["votes"]:
                o.learn(regime, reward)
        
        if pnl > 0:
            self.adaptive["base_threshold"] = max(0.05, self.adaptive["base_threshold"] - 0.01)
        else:
            self.adaptive["base_threshold"] = min(0.30, self.adaptive["base_threshold"] + 0.01)
            
        db_set("adaptive", self.adaptive)
        self.generation += 1
        db_set("generation", self.generation)
        save_genome(self)

    def evolve_step(self, regime_counts):
        self.generation += 1
        self.last_stats["evolution_steps"] = self.last_stats.get("evolution_steps", 0) + 1
        for regime, count in regime_counts.items():
            for o in self.orgs:
                o.learn(regime, 0.0)
        db_set("generation", self.generation)
        self._add_debug(f"Evolution step #{self.generation} - Regimes observed: {dict(regime_counts)}")

    def cycle(self):
        self.manage_positions()
        tickers = get_all_tickers()
        if not tickers: return
        
        ranked = []
        for sym, t in tickers.items():
            if t["turn24"] < MIN_TURNOVER_24H: continue
            spread_bps = (t["ask"] - t["bid"]) / (t["last"] + 1e-12) * 10000
            if spread_bps > MAX_SPREAD_BPS: continue
            score = math.log10(t["turn24"] + 1) * 0.2 + abs(t["chg"]) * 150 * 0.8
            ranked.append((sym, score, t))
        ranked.sort(key=lambda x: -x[1])
        cands = ranked[:15]
        
        self.last_stats["scanned"] = len(tickers)
        self.last_stats["cands"] = len(cands)
        opened = 0
        regime_counts = defaultdict(int)
        now_ts = time.time() * 1000
        
        for sym, sc, tk in cands:
            try:
                df = get_klines(sym, "5", 40)
                if df.empty: continue
                
                last_candle_ts = float(df.iloc[-1]["ts"])
                candle_age_minutes = (now_ts - last_candle_ts) / 1000 / 60
                
                if candle_age_minutes > MAX_CANDLE_AGE_MINUTES:
                    self.last_stats["rejected_stale"] = self.last_stats.get("rejected_stale", 0) + 1
                    continue
                
                regime = detect_regime(df)
                regime_counts[regime] += 1
                feat = extract_features(df, tk)
                
                dec = self.decide_predator(feat, regime)
                if dec and self.try_open(sym, tk, dec, feat, candle_age_minutes):
                    opened += 1
            except Exception as e:
                self._add_debug(f"Error processing {sym}: {str(e)}")
                continue
            
        self.last_stats["opened"] = opened
        self.last_stats["regime_counts"] = dict(regime_counts)
        self.evolve_step(regime_counts)
        self.heart_beat += 1

# ──────────────────────────────────────────────────────────────
# ۸. موتور بک‌تست با تکامل آنی در حین اجرا (اصلاح شده)
# ──────────────────────────────────────────────────────────────
def run_smart_backtest(hive_instance, max_coins=50):
    try:
        print(f"Starting backtest with {max_coins} coins...")
        tickers = get_all_tickers()
        if not tickers:
            return {"error": "خطا در دریافت داده‌های بازار"}
        
        sorted_tickers = sorted(tickers.items(), key=lambda x: x[1]["turn24"], reverse=True)[:max_coins]
        print(f"Selected {len(sorted_tickers)} coins for testing")
        
        def fetch_data(item):
            sym, t = item
            try:
                df = get_klines(sym, "5", limit=1000)
                return sym, df
            except Exception as e:
                print(f"Error fetching {sym}: {e}")
                return sym, pd.DataFrame()

        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            results = list(executor.map(fetch_data, sorted_tickers))

        total_equity_curve = [float(hive_instance.capital)]
        all_trades_log = []
        current_capital = float(hive_instance.capital)
        total_processed = 0
        total_trades = 0

        for sym, df in results:
            if df.empty or len(df) < 100: 
                continue
            
            if "ts" in df.columns:
                df["ts"] = pd.to_numeric(df["ts"], errors='coerce')
            
            open_pos = None
            
            for i in range(100, len(df)):
                try:
                    current_df = df.iloc[:i+1].copy()
                    current_candle = current_df.iloc[-1]
                    
                    mid = float(current_candle["close"])
                    spread_est = mid * (MAX_SPREAD_BPS / 20000)
                    ticker = {"last": mid, "bid": mid - spread_est, "ask": mid + spread_est}
                    
                    regime = detect_regime(current_df)
                    feat = extract_features(current_df, ticker)
                    
                    long_pool, short_pool = 0.0, 0.0
                    for o in hive_instance.orgs:
                        score = o.evaluate(feat, regime)
                        if o.last_vote == "LONG": long_pool += abs(score)
                        else: short_pool += abs(score)
                        
                    side = None
                    if long_pool > short_pool and long_pool > hive_instance.adaptive["base_threshold"]: side = "long"
                    elif short_pool > long_pool and short_pool > hive_instance.adaptive["base_threshold"]: side = "short"
                    
                    if open_pos:
                        op = open_pos
                        exit_price = ticker["bid"] if op["side"] == "long" else ticker["ask"]
                        pnl_pct = (exit_price - op["entry"]) / op["entry"] if op["side"] == "long" else (op["entry"] - exit_price) / op["entry"]
                        rp = REGIME_PARAMS.get(op["regime"], REGIME_PARAMS["RANGING"])
                        
                        close_reason = ""
                        if pnl_pct >= rp["tp"]: close_reason = "TP"
                        elif pnl_pct <= -rp["sl"]: close_reason = "SL"
                        elif (op["side"] == "long" and exit_price <= op["trail_stop"]) or (op["side"] == "short" and exit_price >= op["trail_stop"]):
                            close_reason = "TRAIL"
                            
                        if close_reason:
                            net_pnl = (pnl_pct * op["notional"]) - (op["notional"] * COMMISSION * 2)
                            current_capital += net_pnl
                            all_trades_log.append({"symbol": sym, "entry": op["entry"], "exit": exit_price, "side": op["side"], "pnl": net_pnl, "reason": close_reason})
                            total_trades += 1
                            total_equity_curve.append(float(current_capital))
                            
                            # ۱. آپدیت آنی ژنوم در حافظه برای استفاده در معاملات بعدی همین بک‌تست
                            reward = 1.0 if net_pnl > 0 else -1.0
                            for o in hive_instance.orgs:
                                o.learn(op["regime"], reward)
                            
                            # ۲. افزایش نسل و ذخیره فوری در دیتابیس تا تکامل در همان لحظه ثبت شود
                            hive_instance.generation += 1
                            save_genome(hive_instance)
                            db_set("generation", hive_instance.generation)
                            
                            open_pos = None
                    
                    if not open_pos and side:
                        rp = REGIME_PARAMS.get(regime, REGIME_PARAMS["RANGING"])
                        risk_pct = RISK_PER_TRADE_BASE * rp["risk_mult"]
                        req_margin = min((current_capital * risk_pct) / (rp["sl"] * LEVERAGE), current_capital * 0.35)
                        
                        if req_margin >= 5:
                            slip = mid * (SLIPPAGE_BPS / 10000)
                            entry_price = ticker["ask"] + slip if side == "long" else ticker["bid"] - slip
                            trail = entry_price * (1 - rp["sl"] * 1.1) if side == "long" else entry_price * (1 + rp["sl"] * 1.1)
                            
                            open_pos = {
                                "side": side, "entry": entry_price, "margin": req_margin, 
                                "notional": req_margin * LEVERAGE, "regime": regime, "trail_stop": trail
                            }
                except Exception as e:
                    print(f"Error in candle {i} for {sym}: {e}")
                    continue
            
            total_processed += 1
            if total_equity_curve and total_equity_curve[-1] != current_capital:
                total_equity_curve.append(float(current_capital))
        
        print(f"Backtest completed. Processed {total_processed} coins, {total_trades} trades. Final Generation: {hive_instance.generation}")

        wins = sum(1 for t in all_trades_log if t["pnl"] > 0)
        total = len(all_trades_log)
        win_rate = (wins / total * 100) if total > 0 else 0
        
        return {
            "equity_curve": total_equity_curve,
            "final_capital": float(current_capital),
            "total_trades": total,
            "win_rate": float(win_rate),
            "trades_log": all_trades_log[-50:]
        }
    except Exception as e:
        print(f"Critical error in backtest: {e}")
        import traceback
        traceback.print_exc()
        return {"error": f"خطای بحرانی: {str(e)}"}

# ──────────────────────────────────────────────────────────────
# ۹. رابط کاربری
# ──────────────────────────────────────────────────────────────
HIVE = PredatorHive()
external_stylesheets = [dbc.themes.CYBORG, "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;700;900&display=swap"]
app = dash.Dash(__name__, external_stylesheets=external_stylesheets, suppress_callback_exceptions=True)
app.title = "HIVE PREDATOR v9.10"

app.index_string = f"""
<!DOCTYPE html>
<html lang="fa" dir="rtl">
    <head>
        {{%metas%}}
        <title>{app.title}</title>
        {{%favicon%}}
        {{%css%}}
        <style>
        :root {{ color-scheme: dark; }}
        body {{ margin:0; padding:0; background: #05080f; font-family: 'Vazirmatn', sans-serif; color: #eaf2ff; }}
        .glass-card {{
            background: rgba(8, 14, 26, 0.9) !important;
            border: 1px solid rgba(255, 42, 109, 0.2) !important;
            box-shadow: 0 4px 20px rgba(0,0,0,0.6);
            border-radius: 12px !important;
        }}
        .predator-glow {{ text-shadow: 0 0 15px rgba(255, 42, 109, 0.8); }}
        .dash-tabs .nav-link {{ border-radius: 8px !important; margin: 0 4px; font-family: 'Vazirmatn'; font-weight: bold; }}
        .debug-log {{ font-family: monospace; fontSize: 10; color: #8ea2c7; }}
        .generation-lock {{ color: #ff2a6d; font-weight: bold; animation: pulse 2s infinite; }}
        @keyframes pulse {{ 0% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} 100% {{ opacity: 1; }} }}
        </style>
    </head>
    <body>{{%app_entry%}}<footer>{{%config%}}{{%scripts%}}{{%renderer%}}</footer></body>
</html>
"""

def stat_card(title, value, color=GOLD, sub=""):
    return dbc.Card(dbc.CardBody([
        html.Div(rtl_text(title), style={"color": MUT, "fontSize": 11, "marginBottom": 4}),
        html.Div(str(value), style={"color": color, "fontSize": 20, "fontWeight": 900}),
        html.Div(rtl_text(sub), style={"color": MUT, "fontSize": 10, "marginTop": 4}),
    ]), className="glass-card", style={"height": "100%"})

def get_live_status():
    rows = []
    for o in HIVE.orgs:
        color = UP if o.last_vote == "LONG" else DN
        rows.append(html.Tr([
            html.Td(rtl_text(o.name), style={"fontWeight": "bold"}),
            html.Td(rtl_text(o.role), style={"color": MUT, "fontSize": 11}),
            html.Td(o.last_vote, style={"color": color, "fontWeight": "900", "fontSize": 14}),
            html.Td(f"{o.conviction:.0%}", style={"color": GOLD}),
            html.Td(f"{o.weight:.2f}x", style={"color": NEON}),
        ]))
    return html.Table([
        html.Thead(html.Tr([html.Th(rtl_text(x)) for x in ["واحد", "نقش", "جهت لحظه‌ای", "قاطعیت", "ضریب نفوذ"]])),
        html.Tbody(rows)
    ], style={"width": "100%", "color": TXT, "fontSize": 12})

app.layout = html.Div([
    dbc.Container(fluid=True, children=[
        dbc.Card(dbc.CardBody(dbc.Row([
            dbc.Col(html.H2("HIVE PREDATOR v9.10", className="predator-glow", style={"margin": 0, "color": DN, "fontWeight": 900, "letterSpacing": "2px"}), md=6),
            dbc.Col(html.Div(id="pulse", style={"color": CYAN, "fontFamily": "monospace", "fontSize": 12, "textAlign": "left"}), md=6),
        ], align="center")), className="glass-card mb-3 mt-2"),

        dcc.Tabs(id="tabs", value="live", parent_className="dash-tabs", children=[
            dcc.Tab(label="اتاق فرمان زنده", value="live", style={"background": CARD_SOLID, "color": TXT}, selected_style={"background": LINE, "color": DN}),
            dcc.Tab(label="لاگ دیباگ", value="debug", style={"background": CARD_SOLID, "color": TXT}, selected_style={"background": LINE, "color": DN}),
            dcc.Tab(label="ژورنال معاملات", value="journal", style={"background": CARD_SOLID, "color": TXT}, selected_style={"background": LINE, "color": DN}),
            dcc.Tab(label="بک‌تست و تکامل ژنوم", value="backtest", style={"background": CARD_SOLID, "color": TXT}, selected_style={"background": LINE, "color": DN}),
        ]),
        html.Div(id="content", className="mt-3"),
        dcc.Interval(id="life", interval=4_000, n_intervals=0),
        dcc.Interval(id="cycle", interval=12_000, n_intervals=0),
    ])
], style={"minHeight": "100vh", "paddingBottom": "40px"})

@app.callback(Output("content", "children"), Input("tabs", "value"), Input("life", "n_intervals"))
def render(tab, _):
    trig = dash.callback_context.triggered
    trigger_id = trig[0]["prop_id"].split(".")[0] if trig else None
    if tab == "backtest" and trigger_id == "life":
        return dash.no_update

    if tab == "live":
        generation_lock_msg = None
        if HIVE.generation < MIN_GENERATION_FOR_TRADING:
            progress_pct = (HIVE.generation / MIN_GENERATION_FOR_TRADING) * 100
            generation_lock_msg = dbc.Alert([
                html.H4("🧬 تکامل ژنوم در جریان است", style={"color": DN, "marginBottom": "10px"}),
                html.P(f"سیستم در حال یادگیری از بازار است. تا نسل {MIN_GENERATION_FOR_TRADING} معامله‌ای باز نخواهد شد.", style={"marginBottom": "10px"}),
                html.Div([
                    dbc.Progress(value=progress_pct, label=f"{progress_pct:.1f}%", color="danger", style={"height": "30px"}),
                ]),
                html.P(f"نسل فعلی: {HIVE.generation} از {MIN_GENERATION_FOR_TRADING}", className="generation-lock", style={"marginTop": "10px", "fontSize": "18px"})
            ], color="dark", className="glass-card", style={"borderColor": DN, "marginBottom": "20px"})
        
        opens = get_open_trades()
        if opens:
            tickers = get_all_tickers()
            rows = []
            for t in opens:
                last = tickers.get(t["symbol"], {}).get("last", t["entry"])
                pnl_pct = (last - t["entry"]) / t["entry"] if t["side"] == "long" else (t["entry"] - last) / t["entry"]
                remain = 1.0 - sum(p.get("frac", 0) for p in t["partials"])
                
                notional = t["size_usd"] * LEVERAGE
                pnl = (pnl_pct * notional * remain) - (notional * remain * COMMISSION * 2)
                color = UP if pnl >= 0 else DN
                
                votes_list = [f"{v.get('org')}:{v.get('vote')}({v.get('conviction',0):.2f})" for v in t["votes"].values()]
                votes_str = " + ".join(votes_list)
                
                rows.append(html.Tr([
                    html.Td(t["symbol"], style={"fontWeight": "bold"}),
                    html.Td(t["side"].upper(), style={"color": UP if t["side"]=="long" else DN, "fontWeight": "900"}),
                    html.Td(f"{t['entry']:.4f}"),
                    html.Td(f"{last:.4f}"),
                    html.Td(f"${t['size_usd']:.1f} (x{t['leverage']})"),
                    html.Td(f"${pnl:+.2f}", style={"color": color, "fontWeight": "900"}),
                    html.Td(votes_str, style={"fontSize": 10, "color": CYAN}),
                ]))
            table = dbc.Table([
                html.Thead(html.Tr([html.Th(rtl_text(x)) for x in ["نماد", "سمت", "ورود", "فعلی", "مارجین", "PnL خالص", "تاییدیه"]]), style={"color": GOLD}),
                html.Tbody(rows)
            ], bordered=True, hover=True, size="sm", className="glass-card")
        else:
            table = dbc.Alert("در حال شکار فرصت‌های اسکالپ در بازار...", color="dark", className="glass-card", style={"borderColor": CYAN})

        content = html.Div([
            dbc.Row([
                dbc.Col(stat_card("سرمایه در دسترس", f"${HIVE.capital:.2f}", GOLD, f"Peak: ${HIVE.peak:.2f}"), md=3),
                dbc.Col(stat_card("پوزیشن‌های فعال", f"{len(opens)}/{MAX_POSITIONS}", DN), md=3),
                dbc.Col(stat_card("نسل تکامل", f"{HIVE.generation}", CYAN, f"آستانه: {HIVE.adaptive['base_threshold']:.3f}"), md=3),
                dbc.Col(stat_card("معاملات باز شده", f"{HIVE.last_stats.get('opened', 0)}", UP), md=3),
            ], className="g-3 mb-3"),
            
            dbc.Row([
                dbc.Col(stat_card("رد شده (نسل)", f"{HIVE.last_stats.get('rejected_generation', 0)}", DN), md=2),
                dbc.Col(stat_card("رد شده (کندل قدیمی)", f"{HIVE.last_stats.get('rejected_stale', 0)}", MUT), md=2),
                dbc.Col(stat_card("رد شده (قیمت)", f"{HIVE.last_stats.get('rejected_price', 0)}", MUT), md=2),
                dbc.Col(stat_card("رد شده (مارجین)", f"{HIVE.last_stats.get('rejected_margin', 0)}", MUT), md=2),
                dbc.Col(stat_card("اسکن شده", f"{HIVE.last_stats.get('cands', 0)}", CYAN), md=2),
            ], className="g-3 mb-3"),
            
            html.H4("وضعیت لحظه‌ای واحدهای شکارچی", style={"color": DN, "marginBottom": 12, "fontWeight": 900}),
            dbc.Card(dbc.CardBody(get_live_status()), className="glass-card mb-3"),
            html.H4("پوزیشن‌های باز", style={"color": GOLD, "marginBottom": 12, "fontWeight": 900}),
            table,
        ])
        
        if generation_lock_msg:
            return html.Div([generation_lock_msg, content])
        return content
    
    elif tab == "debug":
        debug_logs = HIVE.last_stats.get("debug_log", [])
        log_items = [html.Div(log, className="debug-log", style={"marginBottom": "4px", "padding": "4px", "background": "rgba(0,0,0,0.3)"}) for log in reversed(debug_logs)]
        
        return html.Div([
            html.H4("لاگ دیباگ زنده", style={"color": DN, "marginBottom": 12, "fontWeight": 900}),
            dbc.Card(dbc.CardBody([
                html.Div(log_items, style={"maxHeight": "500px", "overflowY": "auto"})
            ]), className="glass-card")
        ])
    
    elif tab == "journal":
        conn = sqlite3.connect(DB_PATH)
        journal_rows = conn.execute("SELECT symbol, side, entry, exit_price, size_usd, leverage, pnl, entry_time, exit_time, reason FROM trades WHERE status='closed' ORDER BY id DESC LIMIT 50").fetchall()
        conn.close()
        
        j_table = []
        for r in journal_rows:
            color = UP if (r[6] or 0) > 0 else DN
            j_table.append(html.Tr([
                html.Td(r[0], style={"fontWeight": "bold"}),
                html.Td(r[1].upper(), style={"color": UP if r[1]=='long' else DN, "fontWeight": "bold"}),
                html.Td(f"{r[2]:.4f}"),
                html.Td(f"{r[3]:.4f}"),
                html.Td(f"${r[4]:.1f} (x{r[5]})"),
                html.Td(f"${(r[6] or 0):+.2f}", style={"color": color, "fontWeight": "900"}),
                html.Td(r[9], style={"fontSize": 10, "color": MUT}),
            ]))
            
        return html.Div([
            html.H4("ژورنال اختصاصی معاملات", style={"color": DN, "marginBottom": 12, "fontWeight": 900}),
            dbc.Card(dbc.CardBody([
                html.Table([
                    html.Thead(html.Tr([html.Th(rtl_text(x)) for x in ["نماد", "سمت", "ورود", "خروج", "مارجین", "PnL خالص", "دلیل خروج"]]), style={"color": GOLD}),
                    html.Tbody(j_table)
                ], style={"width": "100%", "color": TXT, "fontSize": 12})
            ]), className="glass-card")
        ])

    elif tab == "backtest":
        return html.Div([
            html.H4("بک‌تست هوشمند و تکامل ژنوم", style={"color": DN, "marginBottom": 12, "fontWeight": 900}),
            dbc.Row([
                dbc.Col(dbc.Button("شروع بک‌تست و تکامل ژنوم", id="bt-btn", color="danger", className="w-100", style={"fontWeight": "bold", "fontSize": 16}), md=4),
                dbc.Col(html.Div(id="bt-stats", style={"color": GOLD, "fontWeight": "bold", "textAlign": "center", "fontSize": 16, "paddingTop": "10px"}), md=8),
            ], className="g-3 mb-3"),
            dcc.Loading(
                id="bt-loading",
                type="circle",
                color="#ff2a6d",
                children=html.Div(id="bt-graph", style={"height": "500px"})
            )
        ])
    
    return html.Div()

@app.callback(
    [Output("bt-stats", "children"), Output("bt-graph", "children")],
    Input("bt-btn", "n_clicks"),
    prevent_initial_call=True
)
def run_backtest_callback(n_clicks):
    try:
        print("Backtest callback triggered...")
        result = run_smart_backtest(HIVE, max_coins=50)
        print(f"Backtest result: {result.keys() if isinstance(result, dict) else 'Error'}")
        
        if "error" in result:
            print(f"Backtest error: {result['error']}")
            return result["error"], None
        
        stats = html.Div([
            f"سرمایه نهایی: ${result['final_capital']:.2f} | ",
            f"معاملات: {result['total_trades']} | ",
            f"وین ریت: {result['win_rate']:.1f}% | ",
            html.Span("✓ ژنوم آپدیت و ذخیره شد!", style={"color": UP})
        ])
        
        if not result.get("equity_curve") or len(result["equity_curve"]) == 0:
            return "داده‌ای برای نمایش وجود ندارد", None
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            y=result["equity_curve"],
            mode="lines",
            name="رشد سرمایه",
            line=dict(color="#00ffd0", width=2),
            fill="tozeroy",
            fillcolor="rgba(0, 255, 208, 0.1)"
        ))
        
        fig.add_shape(type="line", x0=0, y0=INITIAL_CAPITAL, x1=len(result["equity_curve"])-1, y1=INITIAL_CAPITAL,
                      line=dict(color="#ff2a6d", width=1, dash="dash"))
        
        fig.update_layout(
            template="plotly_dark",
            title="نمودار رشد سرمایه",
            xaxis_title="توالی معاملات",
            yaxis_title="سرمایه (دلار)",
            font={"family": "Vazirmatn"},
            margin=dict(l=40, r=40, t=40, b=40),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )
        
        print("Returning backtest results...")
        return stats, dcc.Graph(figure=fig, style={"height": "100%"})
    except Exception as e:
        print(f"Critical error in callback: {e}")
        import traceback
        traceback.print_exc()
        return f"خطا: {str(e)}", None

@app.callback(Output("pulse", "children"), Input("life", "n_intervals"))
def update_pulse(_):
    lock_status = " LOCKED" if HIVE.generation < MIN_GENERATION_FOR_TRADING else "✓ ACTIVE"
    return f"BEAT #{HIVE.heart_beat} | GEN {HIVE.generation} | {lock_status} | THRESH: {HIVE.adaptive['base_threshold']:.3f} | {now_utc().split('T')[1][:8]}"

@app.callback(Output("cycle", "disabled"), Input("cycle", "n_intervals"), prevent_initial_call=False)
def run_cycle(_):
    HIVE.cycle()
    return False

if __name__ == "__main__":
    print("Launching HIVE PREDATOR v9.10 — REAL-TIME GENOME EVOLUTION")
    print(f"Trading will start after generation {MIN_GENERATION_FOR_TRADING}")
    app.run(debug=False, host="0.0.0.0", port=8050, use_reloader=False)