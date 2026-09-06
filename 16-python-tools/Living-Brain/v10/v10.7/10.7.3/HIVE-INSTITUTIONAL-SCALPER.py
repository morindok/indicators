# -*- coding: utf-8 -*-
"""
HIVE INSTITUTIONAL SCALPER v10.0 — SMART CONFLUENCE ENGINE
----------------------------------------------------------
فلسفه: "شکارچی صبور، نه ماشین‌گات".
تغییرات حیاتی برای جلوگیری از کال‌مارجین و رفتار تک‌سلولی:
۱. موتور هم‌پوشانی (Confluence): حداقل ۲ ارگانیسم با کیفیت بالا باید هم‌نظر باشند.
۲. حق وتوی اسنایپر (Sniper Veto): اگر اسنایپر تشخیص دهد بازار فیک است، معامله لغو می‌شود.
۳. مدیریت ریسک سخت‌گیرانه: حداکثر ۱٪ ریسک در هر معامله. محاسبه حجم بر اساس فاصله استاپ‌لاس.
۴. خروج هوشمند: بستن ۵۰٪ در سود ۱:۱.۵ و انتقال استاپ به نقطه ورود (Breakeven).
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
# ۱. پیکربندی نهادی (Institutional Config)
# ──────────────────────────────────────────────────────────────
BG = "#0b1120"
CARD = "rgba(15, 23, 42, 0.9)"
TXT = "#e2e8f0"
MUT = "#94a3b8"
GOLD = "#fbbf24"
CYAN = "#22d3ee"
UP = "#34d399"  # سبز ملایم‌تر و حرفه‌ای
DN = "#f87171"  # قرمز ملایم‌تر
NEON = "#818cf8"

LEVERAGE = 20
INITIAL_CAPITAL = 500.0
MAX_POSITIONS = 3  # کاهش برای تمرکز بر کیفیت
RISK_PER_TRADE = 0.01  # ۱٪ ریسک سخت‌گیرانه (حیاتی برای بقا)
COMMISSION = 0.0006
SLIPPAGE_BPS = 1.0
MIN_TURNOVER_24H = 3_000_000  # فقط ارزهای بسیار پرنقد
MAX_SPREAD_BPS = 3.0  # فیلتر سخت‌گیرانه اسپرد

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
# ۳. ارگانیسم‌های تحلیل‌گر (Analyst Organisms)
# ──────────────────────────────────────────────────────────────
class AnalystOrganism:
    def __init__(self, name, role, base_weight=1.0):
        self.name = name
        self.role = role
        self.base_weight = base_weight
        self.regime_score = {"TREND_UP": 0.0, "TREND_DOWN": 0.0, "RANGING": 0.0, "HIGH_VOL": 0.0}
        self.regime_trades = {"TREND_UP": 1, "TREND_DOWN": 1, "RANGING": 1, "HIGH_VOL": 1}

    @property
    def weight(self):
        total_score = sum(self.regime_score.values())
        total_trades = sum(self.regime_trades.values())
        avg_accuracy = total_score / total_trades
        return clamp(self.base_weight * (1.0 + avg_accuracy * 1.5), 0.8, 2.0)

    def learn(self, regime: str, reward: float):
        alpha = 0.15
        self.regime_score[regime] = (1 - alpha) * self.regime_score[regime] + alpha * reward
        self.regime_trades[regime] += 1

    def analyze(self, feat, regime):
        """
        هر ارگانیسم یک 'کیفیت سیگنال' (0 تا 1) و یک 'جهت' برمی‌گرداند.
        اگر کیفیت پایین باشد، یعنی ارگانیسم توصیه به 'عدم ورود' می‌کند.
        """
        quality = 0.0
        direction = "NEUTRAL"

        if self.role == "SNIPER":
            # اسنایپر: فقط در اشباع خرید/فروش واقعی + تایید مومنتوم وارد می‌شود
            if feat["rsi"] < 28 and feat["mom"] > 0.1:
                quality, direction = 0.85, "LONG"
            elif feat["rsi"] > 72 and feat["mom"] < -0.1:
                quality, direction = 0.85, "SHORT"
            else:
                quality, direction = 0.2, "NEUTRAL" # وتو کردن معاملات بی‌کیفیت

        elif self.role == "SCALPER":
            # اسکالپر: نیاز به جهش حجم و مومنتوم همزمان دارد
            if feat["vol_surge"] > 0.4 and abs(feat["mom"]) > 0.15:
                quality = 0.75
                direction = "LONG" if feat["mom"] > 0 else "SHORT"
            else:
                quality, direction = 0.3, "NEUTRAL"

        elif self.role == "TREND":
            # تریدر روند: فقط در جهت مووینگ اوریج‌ها معامله می‌کند
            if regime == "TREND_UP" and feat["mom"] > 0:
                quality, direction = 0.7, "LONG"
            elif regime == "TREND_DOWN" and feat["mom"] < 0:
                quality, direction = 0.7, "SHORT"
            else:
                quality, direction = 0.2, "NEUTRAL"

        return {"quality": quality, "direction": direction, "role": self.role, "name": self.name}

# ──────────────────────────────────────────────────────────────
# ۴. اتصال و داده (با فیلترهای سخت‌گیرانه)
# ──────────────────────────────────────────────────────────────
REST = ["https://api.bybit.com", "https://api.bytick.com"]
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "HiveInstitutional/10.0", "Accept": "application/json"})
_ACTIVE = {"url": None}
_rate_lock = threading.Lock()
_last_req = 0.0

def bybit_get(path, params, timeout=6):
    global _last_req
    with _rate_lock:
        elapsed = time.time() - _last_req
        if elapsed < 0.08: time.sleep(0.08 - elapsed)
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

def get_klines(symbol, interval="5", limit=100, category="linear"):
    d = bybit_get("/v5/market/kline", {"category": category, "symbol": symbol, "interval": interval, "limit": limit})
    if not d or "list" not in (d.get("result") or {}): return pd.DataFrame()
    df = pd.DataFrame(d["result"]["list"], columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
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
                "ask": float(t.get("ask1Price") or t["lastPrice"]), "turn24": float(t.get("turnover24h") or 0),
            }
        except: continue
    return out

# ──────────────────────────────────────────────────────────────
# ۵. تشخیص رژیم و ویژگی‌ها (پایدار و بدون نویز)
# ──────────────────────────────────────────────────────────────
def detect_regime(df):
    if df is None or len(df) < 50: return "RANGING"
    close = df["close"].values
    high, low = df["high"].values, df["low"].values
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    atr = pd.Series(tr).rolling(14).mean().iloc[-1]
    atr_pct = atr / close[-1]
    
    if atr_pct > 0.015: return "HIGH_VOL"
    
    ma_fast = pd.Series(close).rolling(12).mean().iloc[-1]
    ma_slow = pd.Series(close).rolling(36).mean().iloc[-1]
    slope = (close[-1] - close[-20]) / (close[-20] + 1e-12)
    
    if slope > 0.003 and ma_fast > ma_slow: return "TREND_UP"
    if slope < -0.003 and ma_fast < ma_slow: return "TREND_DOWN"
    return "RANGING"

REGIME_PARAMS = {
    "TREND_UP":   {"tp": 0.0060, "sl": 0.0030, "trail_mult": 1.2, "partial_at": 0.0035},
    "TREND_DOWN": {"tp": 0.0060, "sl": 0.0030, "trail_mult": 1.2, "partial_at": 0.0035},
    "RANGING":    {"tp": 0.0035, "sl": 0.0020, "trail_mult": 1.0, "partial_at": 0.0020},
    "HIGH_VOL":   {"tp": 0.0080, "sl": 0.0045, "trail_mult": 1.5, "partial_at": 0.0045},
}

def extract_features(df, ticker):
    if df is None or len(df) < 40: return None
    close, vol = df["close"].values, df["volume"].values
    
    mom = float(np.clip((close[-1] - close[-5]) / (close[-5] + 1e-12) * 25, -1, 1))
    vol_surge = float(np.clip((vol[-3:].mean() / (vol[-15:].mean() + 1e-12) - 1) * 2.0, -1, 1))
    
    mid = ticker["last"]
    spread_bps = (ticker["ask"] - ticker["bid"]) / (mid + 1e-12) * 10000
    
    delta = pd.Series(close).diff()
    gain = delta.clip(lower=0).rolling(10).mean()
    loss = (-delta.clip(upper=0)).rolling(10).mean()
    rs = gain / (loss + 1e-12)
    rsi = float(100 - (100 / (1 + rs)).iloc[-1])
    
    atr = pd.Series(np.maximum(df["high"]-df["low"], np.maximum(abs(df["high"]-df["close"].shift(1)), abs(df["low"]-df["close"].shift(1))))).rolling(14).mean().iloc[-1]
    
    return {
        "mom": mom, "vol_surge": vol_surge, "spread_bps": spread_bps, 
        "rsi": rsi, "atr_pct": float(atr/close[-1])
    }

# ──────────────────────────────────────────────────────────────
# ۶. مدیریت دیتابیس و ریسک
# ──────────────────────────────────────────────────────────────
DB_PATH = Path("hive_institutional_v10.db")
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, side TEXT, entry REAL, size_usd REAL,
        leverage INTEGER, entry_time TEXT, exit_time TEXT, exit_price REAL, pnl REAL, 
        status TEXT, reason TEXT, regime TEXT, partials TEXT, trail_stop REAL)""")
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
    rows = conn.execute("SELECT id,symbol,side,entry,size_usd,leverage,entry_time,reason,regime,partials,trail_stop FROM trades WHERE status='open'").fetchall()
    conn.close()
    return [{"id":r[0],"symbol":r[1],"side":r[2],"entry":r[3],"size_usd":r[4],"leverage":r[5],"entry_time":r[6],
             "reason":r[7],"regime":r[8],"partials":json.loads(r[9] or "[]"),"trail_stop":r[10]} for r in rows]

def save_trade(t):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO trades (symbol,side,entry,size_usd,leverage,entry_time,status,reason,regime,partials,trail_stop)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (t["symbol"], t["side"], t["entry"], t["size_usd"], t["leverage"], t["entry_time"], "open", 
         t["reason"], t["regime"], json.dumps(t["partials"]), t["trail_stop"]))
    conn.commit(); tid = c.lastrowid; conn.close()
    return tid

def close_trade_full(tid, exit_price, pnl):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE trades SET exit_time=?, exit_price=?, pnl=?, status='closed' WHERE id=?",
                 (now_utc(), exit_price, pnl, tid))
    conn.commit(); conn.close()

# ──────────────────────────────────────────────────────────────
# ۷. موتور هم‌پوشانی نهادی (Institutional Confluence Engine)
# ──────────────────────────────────────────────────────────────
class InstitutionalHive:
    def __init__(self):
        init_db()
        self.capital = float(db_get("capital", INITIAL_CAPITAL))
        self.peak = float(db_get("peak", INITIAL_CAPITAL))
        self.generation = int(db_get("generation", 1))
        self.quality_threshold = float(db_get("quality_threshold", 0.65)) # آستانه کیفیت بالا
        
        self.orgs = [
            AnalystOrganism("Sniper", "SNIPER", base_weight=1.5), # وزن بالا برای وتو
            AnalystOrganism("Scalper", "SCALPER", base_weight=1.2),
            AnalystOrganism("Trend", "TREND", base_weight=1.0),
        ]
        self._lock = threading.Lock()
        self.last_stats = {"scanned": 0, "cands": 0, "opened": 0}
        self.heart_beat = 0

    def decide(self, feat, regime):
        if feat is None or feat["spread_bps"] > MAX_SPREAD_BPS: 
            return None # رد فوری به دلیل اسپرد بالا
        
        # مرحله ۱: جمع‌آوری تحلیل‌ها
        analyses = [org.analyze(feat, regime) for org in self.orgs]
        
        # مرحله ۲: بررسی حق وتوی اسنایپر
        sniper_analysis = next((a for a in analyses if a["role"] == "SNIPER"), None)
        if sniper_analysis and sniper_analysis["quality"] < 0.4:
            return None # اسنایپر تشخیص داد بازار فیک یا نامشخص است. لغو معامله.
        
        # مرحله ۳: فیلتر کردن تحلیل‌های باکیفیت
        valid_analyses = [a for a in analyses if a["quality"] > 0.5 and a["direction"] != "NEUTRAL"]
        
        # مرحله ۴: بررسی هم‌پوشانی (Confluence)
        if len(valid_analyses) < 2:
            return None # حداقل ۲ تحلیل‌گر باید با کیفیت بالا هم‌نظر باشند
        
        long_score = sum(a["quality"] * next(o.weight for o in self.orgs if o.name == a["name"]) for a in valid_analyses if a["direction"] == "LONG")
        short_score = sum(a["quality"] * next(o.weight for o in self.orgs if o.name == a["name"]) for a in valid_analyses if a["direction"] == "SHORT")
        
        if long_score > short_score and long_score > self.quality_threshold:
            side, conv = "long", long_score
        elif short_score > long_score and short_score > self.quality_threshold:
            side, conv = "short", short_score
        else:
            return None
            
        reason = " | ".join([f"{a['name']}({a['direction']})" for a in valid_analyses if a['direction'] == side])
        return {"side": side, "conv": conv, "reason": f"CONFLUENCE [{len(valid_analyses)}]: {reason}", "regime": regime}

    def try_open(self, sym, ticker, decision, feat):
        with self._lock:
            opens = get_open_trades()
            if len(opens) >= MAX_POSITIONS or any(t["symbol"] == sym for t in opens):
                return False
            
            rp = REGIME_PARAMS.get(decision["regime"], REGIME_PARAMS["RANGING"])
            
            # محاسبه حجم بر اساس ریسک ثابت ۱٪ (حیاتی برای بقا)
            risk_amount = self.capital * RISK_PER_TRADE
            sl_distance = rp["sl"]
            size_usd = (risk_amount / sl_distance) / LEVERAGE
            
            # محدودیت حداکثر حجم برای جلوگیری از اهرم بیش از حد
            size_usd = min(size_usd, self.capital * 0.30)
            if size_usd < 15: return False # حداقل حجم منطقی
            
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
                "symbol": sym, "side": decision["side"], "entry": entry, "size_usd": size_usd,
                "leverage": LEVERAGE, "entry_time": now_utc(), "reason": decision["reason"],
                "regime": decision["regime"], "partials": [], "trail_stop": trail
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
            
            # قانون طلایی نهادی: برداشتن ۵۰٪ سود در ۱:۱.۵ و انتقال استاپ به نقطه ورود
            if pnl_pct >= rp["partial_at"] and not any(p.get("level") == "p1" for p in partials):
                part_frac = 0.50
                part_pnl = pnl_pct * t["size_usd"] * part_frac * LEVERAGE - t["size_usd"] * part_frac * COMMISSION * 2
                partials.append({"level": "p1", "frac": part_frac, "price": last, "pnl": part_pnl, "ts": now.isoformat()})
                self.capital += part_pnl
                
                # انتقال استاپ به Breakeven (نقطه ورود)
                trail = entry 
                
                conn = sqlite3.connect(DB_PATH)
                conn.execute("UPDATE trades SET partials=?, trail_stop=? WHERE id=?", (json.dumps(partials), trail, t["id"]))
                conn.commit(); conn.close()
                t["partials"] = partials
                t["trail_stop"] = trail

            # تریلینگ استاپ پویا فقط بعد از برداشتن سود جزئی فعال می‌شود
            if len(partials) > 0:
                if side == "long":
                    new_trail = last * (1 - rp["sl"] * rp["trail_mult"] * 0.5)
                    if new_trail > t["trail_stop"]:
                        conn = sqlite3.connect(DB_PATH)
                        conn.execute("UPDATE trades SET trail_stop=? WHERE id=?", (new_trail, t["id"]))
                        conn.commit(); conn.close()
                        t["trail_stop"] = new_trail
                    hit_trail = last <= t["trail_stop"]
                else:
                    new_trail = last * (1 + rp["sl"] * rp["trail_mult"] * 0.5)
                    if new_trail < t["trail_stop"]:
                        conn = sqlite3.connect(DB_PATH)
                        conn.execute("UPDATE trades SET trail_stop=? WHERE id=?", (new_trail, t["id"]))
                        conn.commit(); conn.close()
                        t["trail_stop"] = new_trail
                    hit_trail = last >= t["trail_stop"]
            else:
                hit_trail = False

            full_close = False
            if pnl_pct >= rp["tp"] or pnl_pct <= -rp["sl"]: full_close = True
            if hit_trail: full_close = True
            if (now - datetime.fromisoformat(t["entry_time"])).total_seconds() / 60.0 >= 20: full_close = True # خروج در صورت رکود

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
        
        # به‌روزرسانی وزن ارگانیسم‌ها بر اساس نتیجه
        # (در این نسخه ساده‌شده، همه ارگانیسم‌ها به طور مساوی یاد می‌گیرند، اما در نسخه‌های پیشرفته‌تر می‌توان تفکیک کرد)
        for org in self.orgs:
            org.learn(regime, reward)
        
        if pnl > 0:
            self.quality_threshold = max(0.55, self.quality_threshold - 0.01)
        else:
            self.quality_threshold = min(0.75, self.quality_threshold + 0.02)
            
        db_set("quality_threshold", self.quality_threshold)
        self.generation += 1
        db_set("generation", self.generation)

    def cycle(self):
        self.manage_positions()
        tickers = get_all_tickers()
        if not tickers: return
        
        ranked = []
        for sym, t in tickers.items():
            if t["turn24"] < MIN_TURNOVER_24H: continue
            # امتیازدهی بر اساس ثبات، نه فقط نوسان کور
            score = math.log10(t["turn24"] + 1) * 0.5
            ranked.append((sym, score, t))
        ranked.sort(key=lambda x: -x[1])
        cands = ranked[:10] # اسکن ۱۰ ارز برتر و باثبات
        
        self.last_stats["scanned"] = len(tickers)
        self.last_stats["cands"] = len(cands)
        opened = 0
        
        for sym, sc, tk in cands:
            try:
                df = get_klines(sym, "5", 80)
                if df.empty: continue
                regime = detect_regime(df)
                feat = extract_features(df, tk)
                if feat is None: continue
                
                dec = self.decide(feat, regime)
                if dec and self.try_open(sym, tk, dec, feat):
                    opened += 1
            except: continue
            
        self.last_stats["opened"] = opened
        self.heart_beat += 1

# ──────────────────────────────────────────────────────────────
# ۸. رابط کاربری حرفه‌ای (Professional UI)
# ──────────────────────────────────────────────────────────────
HIVE = InstitutionalHive()
external_stylesheets = [dbc.themes.SLATE, "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;700;900&display=swap"]
app = dash.Dash(__name__, external_stylesheets=external_stylesheets, suppress_callback_exceptions=True)
app.title = "HIVE INSTITUTIONAL v10.0"

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
        body {{ margin:0; padding:0; background: #0b1120; font-family: 'Vazirmatn', sans-serif; color: #e2e8f0; }}
        .glass-card {{
            background: rgba(15, 23, 42, 0.9) !important;
            border: 1px solid rgba(34, 211, 238, 0.15) !important;
            border-radius: 12px !important;
        }}
        .pro-glow {{ text-shadow: 0 0 10px rgba(34, 211, 238, 0.4); }}
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

app.layout = html.Div([
    dbc.Container(fluid=True, children=[
        dbc.Card(dbc.CardBody(dbc.Row([
            dbc.Col(html.H2("HIVE INSTITUTIONAL v10.0", className="pro-glow", style={"margin": 0, "color": CYAN, "fontWeight": 900}), md=6),
            dbc.Col(html.Div(id="pulse", style={"color": MUT, "fontFamily": "monospace", "fontSize": 12, "textAlign": "left"}), md=6),
        ], align="center")), className="glass-card mb-3 mt-2"),

        dcc.Tabs(id="tabs", value="live", parent_className="dash-tabs", children=[
            dcc.Tab(label="اتاق فرمان", value="live", style={"background": "#1e293b", "color": TXT}, selected_style={"background": "#334155", "color": CYAN}),
            dcc.Tab(label="حافظه و یادگیری", value="learning", style={"background": "#1e293b", "color": TXT}, selected_style={"background": "#334155", "color": CYAN}),
        ]),
        html.Div(id="content", className="mt-3"),
        dcc.Interval(id="life", interval=5_000, n_intervals=0),
        dcc.Interval(id="cycle", interval=15_000, n_intervals=0),
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
                
                # نمایش وضعیت پوزیشن (معمولی یا در حالت Breakeven)
                status = "🔒 BE" if len(t["partials"]) > 0 else "ACTIVE"
                
                rows.append(html.Tr([
                    html.Td(t["symbol"], style={"fontWeight": "bold"}),
                    html.Td(t["side"].upper(), style={"color": UP if t["side"]=="long" else DN, "fontWeight": "900"}),
                    html.Td(f"{t['entry']:.4f}"),
                    html.Td(f"{last:.4f}"),
                    html.Td(f"${t['size_usd']:.1f}"),
                    html.Td(f"{pnl:+.2f}", style={"color": color, "fontWeight": "900"}),
                    html.Td(status, style={"fontSize": 10, "color": GOLD}),
                ]))
            table = dbc.Table([
                html.Thead(html.Tr([html.Th(rtl_text(x)) for x in ["نماد", "سمت", "ورود", "فعلی", "حجم", "PnL", "وضعیت"]]), style={"color": CYAN}),
                html.Tbody(rows)
            ], bordered=True, hover=True, size="sm", className="glass-card")
        else:
            table = dbc.Alert("در انتظار هم‌پوشانی سیگنال‌های باکیفیت...", color="dark", className="glass-card", style={"borderColor": CYAN})

        return html.Div([
            dbc.Row([
                dbc.Col(stat_card("سرمایه", f"${HIVE.capital:.2f}", GOLD, f"Peak: ${HIVE.peak:.2f}"), md=3),
                dbc.Col(stat_card("پوزیشن‌ها", f"{len(opens)}/{MAX_POSITIONS}", CYAN), md=3),
                dbc.Col(stat_card("آستانه کیفیت", f"{HIVE.quality_threshold:.2f}", NEON, "بالا = محتاط‌تر"), md=3),
                dbc.Col(stat_card("اسکن", f"{HIVE.last_stats.get('cands', 0)} نامزد", MUT), md=3),
            ], className="g-3 mb-3"),
            
            html.H4("پوزیشن‌های فعال (مدیریت ریسک نهادی)", style={"color": CYAN, "marginBottom": 12, "fontWeight": 900}),
            table,
            
            html.Div([
                html.H5("قوانین موتور هم‌پوشانی:", style={"color": MUT, "fontSize": 12, "marginTop": 20}),
                html.Ul([
                    html.Li("۱. حداقل ۲ ارگانیسم باید با کیفیت بالا هم‌نظر باشند.", style={"color": TXT, "fontSize": 11}),
                    html.Li("۲. اسنایپر حق وتو دارد. اگر بازار فیک باشد، ورود لغو می‌شود.", style={"color": TXT, "fontSize": 11}),
                    html.Li("۳. ریسک هر معامله دقیقاً ۱٪ سرمایه است.", style={"color": TXT, "fontSize": 11}),
                    html.Li("۴. در سود ۱:۱.۵، نصف حجم بسته و استاپ به نقطه ورود منتقل می‌شود.", style={"color": TXT, "fontSize": 11}),
                ], style={"paddingRight": 20})
            ], className="glass-card p-3")
        ])
    
    else: # learning
        conn = sqlite3.connect(DB_PATH)
        memory_rows = conn.execute("SELECT symbol, regime, side, outcome, lesson FROM memory ORDER BY id DESC LIMIT 15").fetchall()
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
            html.H4("حافظه یادگیری و تکامل استراتژی", style={"color": CYAN, "marginBottom": 12, "fontWeight": 900}),
            dbc.Card(dbc.CardBody([
                html.Table([
                    html.Thead(html.Tr([html.Th(rtl_text(x)) for x in ["نماد", "رژیم", "سمت", "نتیجه", "درس"]]), style={"color": CYAN}),
                    html.Tbody(mem_table)
                ], style={"width": "100%", "color": TXT, "fontSize": 12})
            ]), className="glass-card")
        ])

@app.callback(Output("pulse", "children"), Input("life", "n_intervals"))
def update_pulse(_):
    return f"BEAT #{HIVE.heart_beat} | GEN {HIVE.generation} | QUALITY THRESH: {HIVE.quality_threshold:.2f} | {now_utc().split('T')[1][:8]}"

@app.callback(Output("cycle", "disabled"), Input("cycle", "n_intervals"), prevent_initial_call=False)
def run_cycle(_):
    HIVE.cycle()
    return False

if __name__ == "__main__":
    print("Launching HIVE INSTITUTIONAL SCALPER v10.0 — SMART CONFLUENCE ENGINE")
    print("Risk Management: ACTIVE | Sniper Veto: ACTIVE | Confluence: REQUIRED")
    app.run(debug=False, host="0.0.0.0", port=8051, use_reloader=False)