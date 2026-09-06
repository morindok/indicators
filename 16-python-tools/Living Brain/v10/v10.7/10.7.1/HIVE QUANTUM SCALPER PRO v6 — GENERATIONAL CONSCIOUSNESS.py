# -*- coding: utf-8 -*-
"""
HIVE PREDATOR v9.0 — RUTHLESS SCALPING ENGINE
---------------------------------------------
جراحی کامل منطق تصمیم‌گیری برای حذف کامل رفتار "دایناسوری":
۱. حذف وضعیت "خنثی" و "شکار". هر ارگانیسم در هر لحظه LONG یا SHORT است.
۲. جایگزینی محاسبات پیچیده کوانتومی با منطق "برآیند نیروهای تهاجمی" (Force Vector).
۳. کاهش شدید آستانه‌های ورود و حداقل حجم معامله برای باز کردن سریع پوزیشن.
۴. افزایش دامنه اسکن (کاهش حداقل حجم ۲۴ ساعته و افزایش حداکثر اسپرد).
"""

import os, time, json, math, sqlite3, threading
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

# ──────────────────────────────────────────────────────────────
# ۱. پیکربندی بی‌رحمانه (Ruthless Config)
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
SLIPPAGE_BPS = 1.0
MIN_TURNOVER_24H = 500_000   # کاهش شدید برای اسکن ارزهای بیشتر
MAX_SPREAD_BPS = 5.0         # افزایش برای قبول اسپردهای بیشتر
RISK_PER_TRADE_BASE = 0.025  # ریسک بالاتر برای شکار فرصت‌ها

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
def clamp(x, lo, hi): return max(lo, min(hi, x))

# ──────────────────────────────────────────────────────────────
# ۳. هستهٔ تهاجمی (Predator Core - Simplified & Ruthless)
# ──────────────────────────────────────────────────────────────
class PredatorOrganism:
    def __init__(self, name, role, base_weight=1.0, seed=1):
        self.name = name
        self.role = role
        self.base_weight = base_weight
        self.last_vote = "LONG" # شروع با LONG برای جلوگیری از مکث اولیه
        self.conviction = 0.0
        self.regime_score = {"TREND_UP": 0.0, "TREND_DOWN": 0.0, "RANGING": 0.0, "HIGH_VOL": 0.0}
        self.regime_trades = {"TREND_UP": 1, "TREND_DOWN": 1, "RANGING": 1, "HIGH_VOL": 1}

    @property
    def weight(self):
        total_score = sum(self.regime_score.values())
        total_trades = sum(self.regime_trades.values())
        avg_accuracy = total_score / total_trades
        return clamp(self.base_weight * (1.0 + avg_accuracy * 2.5), 0.6, 3.5)

    def learn(self, regime: str, reward: float):
        alpha = 0.25 # یادگیری بسیار سریع
        self.regime_score[regime] = (1 - alpha) * self.regime_score[regime] + alpha * reward
        self.regime_trades[regime] += 1

    def evaluate(self, feat, regime):
        """
        منطق جدید: محاسبه مستقیم "برآیند نیرو" (Force Vector).
        دیگر خبری از احتمالات کوانتومی و argmax نیست.
        اگر نیرو مثبت باشد -> LONG. اگر منفی باشد -> SHORT.
        """
        if self.role == "ALPHA_SNIPER":
            # اسنایپر: تمرکز بر RSI و مومنتوم خالص
            force = (feat["rsi_ext"] * 2.5) + (feat["mom"] * 4.0)
        elif self.role == "HFT_SCALPER":
            # اسکالپر: تمرکز بر جهش حجم و مومنتوم
            force = (feat["vol_surge"] * 5.0) + (feat["mom"] * 3.0)
        elif self.role == "FLOW":
            # جریان: ترکیب متعادل
            force = (feat["vol_surge"] * 3.0) + (feat["mom"] * 2.5) + (feat["rsi_ext"] * 1.5)
        else:
            # مومنتوم: تمرکز صرف بر شتاب قیمت
            force = feat["mom"] * 5.0 + feat["vol_surge"] * 2.0
        
        # تعیین جهت: هیچ حالت خنثی وجود ندارد
        if force > 0:
            self.last_vote = "LONG"
            raw_score = abs(force) * self.weight
        else:
            self.last_vote = "SHORT"
            raw_score = -abs(force) * self.weight
        
        # قاطعیت بر اساس قدرت نیرو (نرمال‌شده)
        self.conviction = clamp(abs(force) / 6.0, 0.15, 1.0)
        
        # اعمال ضریب یادگیری بر اساس رژیم بازار
        regime_accuracy = self.regime_score[regime] / max(1, self.regime_trades[regime])
        regime_multiplier = clamp(1.0 + regime_accuracy, 0.7, 1.6)
        
        return raw_score * regime_multiplier

# ──────────────────────────────────────────────────────────────
# ۴. اتصال و داده (بهینه‌شده)
# ──────────────────────────────────────────────────────────────
REST = ["https://api.bybit.com", "https://api.bytick.com"]
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "HivePredator/9.0", "Accept": "application/json"})
_ACTIVE = {"url": None}
_rate_lock = threading.Lock()
_last_req = 0.0

def bybit_get(path, params, timeout=5):
    global _last_req
    with _rate_lock:
        elapsed = time.time() - _last_req
        if elapsed < 0.05: time.sleep(0.05 - elapsed)
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

def get_klines(symbol, interval="5", limit=60, category="linear"):
    d = bybit_get("/v5/market/kline", {"category": category, "symbol": symbol, "interval": interval, "limit": limit})
    if not d or "list" not in (d.get("result") or {}): return pd.DataFrame()
    lst = d["result"]["list"]
    if not lst: return pd.DataFrame()
    df = pd.DataFrame(lst, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    for c in ["open", "high", "low", "close", "volume", "turnover"]: df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)

def get_all_tickers():
    d = bybit_get("/v5/market/tickers", {"category": "linear"})
    if not d or not d.get("result", {}).get("list"): return {}
    out = {}
    for t in d["result"]["list"]:
        if not t["symbol"].endswith("USDT"): continue
        try:
            out[t["symbol"]] = {
                "last": float(t["lastPrice"]), "bid": float(t.get("bid1Price") or t["lastPrice"]),
                "ask": float(t.get("ask1Price") or t["lastPrice"]), 
                "vol24": float(t.get("volume24h") or 0), "turn24": float(t.get("turnover24h") or 0), 
                "chg": float(t.get("price24hPcnt") or 0),
            }
        except: continue
    return out

# ──────────────────────────────────────────────────────────────
# ۵. تشخیص رژیم و ویژگی‌ها (فوق‌حساس)
# ──────────────────────────────────────────────────────────────
def detect_regime(df):
    if df is None or len(df) < 20: return "RANGING"
    close = df["close"].values
    high, low = df["high"].values, df["low"].values
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    atr = pd.Series(tr).rolling(14).mean().iloc[-1]
    atr_pct = atr / close[-1]
    
    if atr_pct > 0.012: return "HIGH_VOL"
    
    ma_fast = pd.Series(close).rolling(6).mean().iloc[-1]
    ma_slow = pd.Series(close).rolling(18).mean().iloc[-1]
    slope = (close[-1] - close[-8]) / (close[-8] + 1e-12)
    
    if slope > 0.002 and ma_fast > ma_slow: return "TREND_UP"
    if slope < -0.002 and ma_fast < ma_slow: return "TREND_DOWN"
    return "RANGING"

REGIME_PARAMS = {
    "TREND_UP":   {"tp": 0.0050, "sl": 0.0025, "risk_mult": 1.3, "trail_mult": 1.5, "partial_at": 0.0028},
    "TREND_DOWN": {"tp": 0.0050, "sl": 0.0025, "risk_mult": 1.3, "trail_mult": 1.5, "partial_at": 0.0028},
    "RANGING":    {"tp": 0.0032, "sl": 0.0018, "risk_mult": 1.0, "trail_mult": 1.1, "partial_at": 0.0018},
    "HIGH_VOL":   {"tp": 0.0070, "sl": 0.0038, "risk_mult": 0.9, "trail_mult": 1.8, "partial_at": 0.0038},
}

def extract_features(df, ticker):
    if df is None or len(df) < 20: return None
    close, vol = df["close"].values, df["volume"].values
    
    # مومنتوم فوق‌حساس به ۲ کندل آخر
    mom = float(np.clip((close[-1] - close[-2]) / (close[-2] + 1e-12) * 40, -1, 1))
    vol_surge = float(np.clip((vol[-1] / (vol[-8:].mean() + 1e-12) - 1) * 3.0, -1, 1))
    
    mid = ticker["last"]
    spread_bps = (ticker["ask"] - ticker["bid"]) / (mid + 1e-12) * 10000
    spread_q = float(np.clip(1.0 - spread_bps / MAX_SPREAD_BPS, 0, 1))
    
    delta = pd.Series(close).diff()
    gain = delta.clip(lower=0).rolling(5).mean()
    loss = (-delta.clip(upper=0)).rolling(5).mean()
    rs = gain / (loss + 1e-12)
    rsi = 100 - (100 / (1 + rs)).iloc[-1]
    rsi_ext = 1.5 if rsi < 30 else (-1.5 if rsi > 70 else (0.8 if rsi < 40 else (-0.8 if rsi > 60 else 0.0)))
    
    atr = pd.Series(np.maximum(df["high"]-df["low"], np.maximum(abs(df["high"]-df["close"].shift(1)), abs(df["low"]-df["close"].shift(1))))).rolling(14).mean().iloc[-1]
    return {"mom": mom, "vol_surge": vol_surge, "spread_q": spread_q, "rsi_ext": rsi_ext, "atr_pct": float(atr/close[-1]), "rsi": float(rsi)}

# ──────────────────────────────────────────────────────────────
# ۶. مدیریت دیتابیس
# ──────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────
# ۷. مغز شکارچی (Predator Hive - Ruthless Mode)
# ──────────────────────────────────────────────────────────────
class PredatorHive:
    def __init__(self):
        init_db()
        self.capital = float(db_get("capital", INITIAL_CAPITAL))
        self.peak = float(db_get("peak", INITIAL_CAPITAL))
        self.generation = int(db_get("generation", 1))
        self.adaptive = db_get("adaptive", {"base_threshold": 0.3}) # آستانه بسیار پایین
        
        self.orgs = [
            PredatorOrganism("Alpha", "ALPHA_SNIPER", base_weight=2.0, seed=1),
            PredatorOrganism("Pulse", "HFT_SCALPER", base_weight=1.8, seed=2),
            PredatorOrganism("Flux", "FLOW", base_weight=1.4, seed=3),
            PredatorOrganism("Vector", "MOMENTUM", base_weight=1.2, seed=4),
        ]
        self._lock = threading.Lock()
        self.last_stats = {"scanned": 0, "cands": 0, "opened": 0, "regime_counts": {}}
        self.heart_beat = 0

    def decide_predator(self, feat, regime):
        if feat is None: return None
        
        # استخر قاطعیت: جمع‌آوری تمام سیگنال‌ها (همه LONG یا SHORT هستند)
        long_pool = 0.0
        short_pool = 0.0
        votes = []
        
        for o in self.orgs:
            score = o.evaluate(feat, regime)
            side = "long" if o.last_vote == "LONG" else "short"
            if side == "long":
                long_pool += abs(score)
            else:
                short_pool += abs(score)
            
            votes.append({
                "org": o.name, "role": o.role, "side": side, 
                "score": score, "vote": o.last_vote, 
                "conviction": o.conviction, "weight": o.weight
            })
        
        # تصمیم‌گیری بی‌رحمانه: هرگاه برتری قاطع وجود داشته باشد، وارد شو
        if long_pool > short_pool and long_pool > self.adaptive["base_threshold"]:
            side, final_conv = "long", long_pool
        elif short_pool > long_pool and short_pool > self.adaptive["base_threshold"]:
            side, final_conv = "short", short_pool
        else:
            return None # فقط اگر واقعاً هیچ نیرویی نباشد (بسیار نادر)
            
        conv = min(1.0, final_conv / 4.0)
        reason = " | ".join([f"{v['org']}:{v['vote']}({v['conviction']:.2f})" for v in votes if v['side'] == side])
        return {"side": side, "conv": conv, "votes": {v["org"]: v for v in votes}, "reason": f"PREDATOR [{side.upper()}]: {reason}", "regime": regime}

    def try_open(self, sym, ticker, decision, feat):
        with self._lock:
            opens = get_open_trades()
            if len(opens) >= MAX_POSITIONS or any(t["symbol"] == sym for t in opens):
                return False
            
            rp = REGIME_PARAMS.get(decision["regime"], REGIME_PARAMS["RANGING"])
            risk = RISK_PER_TRADE_BASE * rp["risk_mult"] * (0.8 + 0.2 * decision["conv"])
            size = min((self.capital * risk) / (rp["sl"] * LEVERAGE), self.capital * 0.35)
            if size < 10: return False # حداقل حجم بسیار پایین
            
            price = ticker["last"]
            spread_adj = (ticker["ask"] - ticker["bid"]) / 2 / price
            slip = SLIPPAGE_BPS / 10000
            
            if decision["side"] == "long":
                entry = price * (1 + spread_adj + slip)
                trail = entry * (1 - rp["sl"] * 1.1)
            else:
                entry = price * (1 - spread_adj - slip)
                trail = entry * (1 + rp["sl"] * 1.1)
                
            t = {
                "symbol": sym, "side": decision["side"], "entry": entry, "size_usd": size,
                "leverage": LEVERAGE, "entry_time": now_utc(), "reason": decision["reason"],
                "votes": decision["votes"], "regime": decision["regime"], "partials": [], "trail_stop": trail
            }
            save_trade(t)
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
            
            partials = t["partials"][:]
            if pnl_pct >= rp["partial_at"] and not any(p.get("level") == "p1" for p in partials):
                part_frac = 0.50 # بستن سریع ۵۰٪ برای قفل سود
                part_pnl = pnl_pct * t["size_usd"] * part_frac * LEVERAGE - t["size_usd"] * part_frac * COMMISSION * 2
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
            if (now - datetime.fromisoformat(t["entry_time"])).total_seconds() / 60.0 >= 12: full_close = True # خروج بسیار سریع

            if full_close:
                final_pnl = pnl_pct * t["size_usd"] * remain_frac * LEVERAGE - t["size_usd"] * remain_frac * COMMISSION * 2
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
            self.adaptive["base_threshold"] = max(0.15, self.adaptive["base_threshold"] - 0.008)
        else:
            self.adaptive["base_threshold"] = min(0.40, self.adaptive["base_threshold"] + 0.012)
            
        db_set("adaptive", self.adaptive)
        self.generation += 1
        db_set("generation", self.generation)

    def cycle(self):
        self.manage_positions()
        tickers = get_all_tickers()
        if not tickers: return
        
        # اسکن گسترده و تهاجمی
        ranked = []
        for sym, t in tickers.items():
            if t["turn24"] < MIN_TURNOVER_24H: continue
            spread_bps = (t["ask"] - t["bid"]) / (t["last"] + 1e-12) * 10000
            if spread_bps > MAX_SPREAD_BPS: continue
            # امتیازدهی تهاجمی به نوسان و حجم
            score = math.log10(t["turn24"] + 1) * 0.2 + abs(t["chg"]) * 150 * 0.8
            ranked.append((sym, score, t))
        ranked.sort(key=lambda x: -x[1])
        cands = ranked[:15] # اسکن ۱۵ نامزد برتر
        
        self.last_stats["scanned"] = len(tickers)
        self.last_stats["cands"] = len(cands)
        opened = 0
        regime_counts = defaultdict(int)
        
        for sym, sc, tk in cands:
            try:
                df = get_klines(sym, "5", 40) # فقط ۴۰ کندل برای سرعت حداکثری
                if df.empty: continue
                regime = detect_regime(df)
                regime_counts[regime] += 1
                feat = extract_features(df, tk)
                if feat is None: continue
                
                dec = self.decide_predator(feat, regime)
                if dec and self.try_open(sym, tk, dec, feat):
                    opened += 1
            except: continue
            
        self.last_stats["opened"] = opened
        self.last_stats["regime_counts"] = dict(regime_counts)
        self.heart_beat += 1

# ──────────────────────────────────────────────────────────────
# ۸. رابط کاربری تهاجمی
# ──────────────────────────────────────────────────────────────
HIVE = PredatorHive()
external_stylesheets = [dbc.themes.CYBORG, "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;700;900&display=swap"]
app = dash.Dash(__name__, external_stylesheets=external_stylesheets, suppress_callback_exceptions=True)
app.title = "HIVE PREDATOR v9.0"

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
            dbc.Col(html.H2("HIVE PREDATOR v9.0", className="predator-glow", style={"margin": 0, "color": DN, "fontWeight": 900, "letterSpacing": "2px"}), md=6),
            dbc.Col(html.Div(id="pulse", style={"color": CYAN, "fontFamily": "monospace", "fontSize": 12, "textAlign": "left"}), md=6),
        ], align="center")), className="glass-card mb-3 mt-2"),

        dcc.Tabs(id="tabs", value="live", parent_className="dash-tabs", children=[
            dcc.Tab(label="اتاق فرمان زنده", value="live", style={"background": CARD_SOLID, "color": TXT}, selected_style={"background": LINE, "color": DN}),
            dcc.Tab(label="حافظه یادگیری", value="learning", style={"background": CARD_SOLID, "color": TXT}, selected_style={"background": LINE, "color": DN}),
        ]),
        html.Div(id="content", className="mt-3"),
        dcc.Interval(id="life", interval=4_000, n_intervals=0), # به‌روزرسانی بسیار سریع UI
        dcc.Interval(id="cycle", interval=12_000, n_intervals=0), # سایکل معاملاتی ۱۲ ثانیه‌ای
    ])
], style={"minHeight": "100vh", "paddingBottom": "40px"})

@app.callback(Output("content", "children"), Input("tabs", "value"), Input("life", "n_intervals"))
def render(tab, _):
    if tab == "live":
        opens = get_open_trades()
        if opens:
            tickers = get_all_tickers()
            rows = []
            for t in opens:
                last = tickers.get(t["symbol"], {}).get("last", t["entry"])
                pnl_pct = (last - t["entry"]) / t["entry"] if t["side"] == "long" else (t["entry"] - last) / t["entry"]
                remain = 1.0 - sum(p.get("frac", 0) for p in t["partials"])
                pnl = pnl_pct * t["size_usd"] * remain * LEVERAGE - t["size_usd"] * remain * COMMISSION * 2
                color = UP if pnl >= 0 else DN
                
                votes_list = [f"{v.get('org')}:{v.get('vote')}({v.get('conviction',0):.2f})" for v in t["votes"].values()]
                votes_str = " + ".join(votes_list)
                
                rows.append(html.Tr([
                    html.Td(t["symbol"], style={"fontWeight": "bold"}),
                    html.Td(t["side"].upper(), style={"color": UP if t["side"]=="long" else DN, "fontWeight": "900"}),
                    html.Td(f"{t['entry']:.4f}"),
                    html.Td(f"{last:.4f}"),
                    html.Td(f"${t['size_usd']:.1f}"),
                    html.Td(f"{pnl:+.2f}", style={"color": color, "fontWeight": "900"}),
                    html.Td(votes_str, style={"fontSize": 10, "color": CYAN}),
                ]))
            table = dbc.Table([
                html.Thead(html.Tr([html.Th(rtl_text(x)) for x in ["نماد", "سمت", "ورود", "فعلی", "حجم", "PnL", "تاییدیه واحدها"]]), style={"color": GOLD}),
                html.Tbody(rows)
            ], bordered=True, hover=True, size="sm", className="glass-card")
        else:
            table = dbc.Alert("در حال شکار فرصت‌های اسکالپ در بازار...", color="dark", className="glass-card", style={"borderColor": CYAN})

        return html.Div([
            dbc.Row([
                dbc.Col(stat_card("سرمایه زنده", f"${HIVE.capital:.2f}", GOLD, f"Peak: ${HIVE.peak:.2f}"), md=3),
                dbc.Col(stat_card("پوزیشن‌های فعال", f"{len(opens)}/{MAX_POSITIONS}", DN), md=3),
                dbc.Col(stat_card("نسل تکامل", f"{HIVE.generation}", CYAN, f"آستانه پویا: {HIVE.adaptive['base_threshold']:.3f}"), md=3),
                dbc.Col(stat_card("اسکن شده", f"{HIVE.last_stats.get('cands', 0)} نامزد", MUT, f"از {HIVE.last_stats.get('scanned', 0)} ارز"), md=3),
            ], className="g-3 mb-3"),
            
            html.H4("وضعیت لحظه‌ای واحدهای شکارچی", style={"color": DN, "marginBottom": 12, "fontWeight": 900}),
            dbc.Card(dbc.CardBody(get_live_status()), className="glass-card mb-3"),
            
            html.H4("پوزیشن‌های باز (مدیریت ریسک تهاجمی)", style={"color": GOLD, "marginBottom": 12, "fontWeight": 900}),
            table,
        ])
    
    else: # learning
        conn = sqlite3.connect(DB_PATH)
        memory_rows = conn.execute("SELECT symbol, regime, side, outcome, lesson FROM memory ORDER BY id DESC LIMIT 20").fetchall()
        conn.close()
        
        mem_table = []
        for r in memory_rows:
            color = UP if r[3] > 0 else DN
            mem_table.append(html.Tr([
                html.Td(r[0], style={"fontWeight": "bold"}),
                html.Td(rtl_text(r[1]), style={"color": CYAN, "fontSize": 11}),
                html.Td(r[2].upper(), style={"color": UP if r[2]=='long' else DN, "fontWeight": "bold"}),
                html.Td(f"${r[3]:+.2f}", style={"color": color, "fontWeight": "900"}),
                html.Td(rtl_text(r[4]), style={"color": GOLD, "fontSize": 11}),
            ]))
            
        return html.Div([
            html.H4("حافظه یادگیری نهادی (به‌روزرسانی وزن‌ها در لحظه)", style={"color": DN, "marginBottom": 12, "fontWeight": 900}),
            dbc.Card(dbc.CardBody([
                html.P("سیستم پس از هر معامله، ضریب نفوذ (Weight) واحدهایی که در آن تصمیم مشارکت داشتند را بر اساس نتیجه (سود/ضرر) و رژیم بازار به‌روز می‌کند.", style={"color": TXT, "marginBottom": 16}),
                html.Table([
                    html.Thead(html.Tr([html.Th(rtl_text(x)) for x in ["نماد", "رژیم", "سمت", "نتیجه", "درس"]]), style={"color": GOLD}),
                    html.Tbody(mem_table)
                ], style={"width": "100%", "color": TXT, "fontSize": 12})
            ]), className="glass-card")
        ])

@app.callback(Output("pulse", "children"), Input("life", "n_intervals"))
def update_pulse(_):
    return f"BEAT #{HIVE.heart_beat} | GEN {HIVE.generation} | THRESH: {HIVE.adaptive['base_threshold']:.3f} | {now_utc().split('T')[1][:8]}"

@app.callback(Output("cycle", "disabled"), Input("cycle", "n_intervals"), prevent_initial_call=False)
def run_cycle(_):
    HIVE.cycle()
    return False

if __name__ == "__main__":
    print("Launching HIVE PREDATOR v9.0 — RUTHLESS SCALPING ENGINE")
    print("WARNING: This is an extremely aggressive institutional algorithm. Monitor closely.")
    app.run(debug=False, host="0.0.0.0", port=8050, use_reloader=False)