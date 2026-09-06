# -*- coding: utf-8 -*-
"""
🌀 Golden Fractal Spiral — Cycle Analysis & Reversal Prediction (v2.3 Fixed UTC)
------------------------------------------------------------------
✅ رفع مشکل تبدیل زمان در تب سیگنال‌ها
✅ تمام زمان‌ها به صورت Unix Timestamp (UTC) ذخیره و نمایش داده می‌شوند
"""

import numpy as np
import pandas as pd
import requests
import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objects as go
import time
import os
import sqlite3
import threading
import webbrowser
from threading import Timer
from datetime import datetime, timezone
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==============================================================================
# 0) ثابت‌ها
# ==============================================================================
BG_MAIN = "#0a0e27"
TXT = "#e0e0e0"
MUT = "#8892b0"
UP = "#00ff88"
DN = "#ff4757"
GOLD = "#ffd700"

PHI = (1 + np.sqrt(5)) / 2
B = np.log(PHI) / (np.pi / 2)
GOLDEN_ANGLE = 2 * np.pi / (PHI ** 2)
ORBIT_TURNS = 2.0
TH_MAX = ORBIT_TURNS * 2 * np.pi
GROWTH = np.exp(B * TH_MAX)
GOLDEN_FRACTIONS = [0.382, 0.5, 0.618, 0.786, 1.0]
DEFAULT_SYMBOL = "BTCUSDT"

TF_CHAIN = [
    ("D",   "روزانه",  GOLD,     1440, 100.0),
    ("240", "۴ساعته",  "#ff8c00", 240,  40.0),
    ("60",  "۱ساعته",  "#bb86fc", 60,   16.0),
    ("15",  "۱۵دقیقه", "#00d4aa", 15,    6.5),
    ("5",   "۵دقیقه",  "#00ff88", 5,     2.6),
    ("1",   "۱دقیقه",  "#5da8ff", 1,     1.0),
]

SCAN_SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
    'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'DOTUSDT', 'LINKUSDT',
    'MATICUSDT', 'UNIUSDT', 'LTCUSDT', 'ATOMUSDT', 'ETCUSDT',
    'XLMUSDT', 'ALGOUSDT', 'VETUSDT', 'FILUSDT', 'APTUSDT', 'ARBUSDT'
]

# ==============================================================================
# CSS
# ==============================================================================
CUSTOM_CSS = '''
@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;700;900&display=swap');
* { font-family: 'Vazirmatn', 'Segoe UI', Tahoma, sans-serif; box-sizing: border-box; }
body { background: linear-gradient(135deg, #0a0e27 0%, #1a1f3a 50%, #0a0e27 100%);
       margin: 0; padding: 0; min-height: 100vh; direction: rtl; }
.bitmoon-banner { background: linear-gradient(135deg, #f093fb 0%, #f5576c 25%, #ffd700 50%, #f5576c 75%, #f093fb 100%);
    background-size: 400% 400%; animation: gradientShift 8s ease infinite;
    padding: 20px 30px; border-radius: 20px; margin-bottom: 25px;
    box-shadow: 0 10px 40px rgba(245, 87, 108, 0.4); border: 2px solid rgba(255, 255, 255, 0.3); }
@keyframes gradientShift { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
.banner-content { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 15px; }
.banner-left { display: flex; align-items: center; gap: 20px; }
.banner-logo { font-size: 50px; animation: moonPulse 2s ease-in-out infinite; display: inline-block; }
@keyframes moonPulse { 0%, 100% { transform: scale(1) rotate(0deg); } 50% { transform: scale(1.15) rotate(10deg); } }
.banner-text h2 { margin: 0; color: #fff; font-size: 28px; font-weight: 900; text-shadow: 2px 2px 8px rgba(0,0,0,0.5); }
.banner-text p { margin: 5px 0 0 0; color: rgba(255,255,255,0.95); font-size: 15px; font-weight: 600; }
.banner-btn { background: #fff; color: #f5576c; padding: 14px 35px; border-radius: 50px; text-decoration: none;
    font-weight: 900; font-size: 17px; box-shadow: 0 5px 20px rgba(0,0,0,0.3); transition: all 0.3s ease;
    display: inline-flex; align-items: center; gap: 10px; border: 3px solid rgba(255,255,255,0.5); cursor: pointer; }
.banner-btn:hover { transform: scale(1.1); background: #ffd700; color: #000; }
.main-header { background: linear-gradient(135deg, rgba(26, 26, 46, 0.95) 0%, rgba(22, 33, 62, 0.95) 100%);
    padding: 25px; border-radius: 20px; margin-bottom: 20px;
    box-shadow: 0 8px 32px rgba(0, 212, 170, 0.15); border: 1px solid rgba(0, 212, 170, 0.2); text-align: center; }
.main-header h1 { margin: 0; background: linear-gradient(135deg, #00d4aa 0%, #00ff88 50%, #ffd700 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
    font-size: 32px; font-weight: 900; }
.main-header p { color: #8892b0; margin: 8px 0 0 0; font-size: 14px; }
.control-panel { background: linear-gradient(135deg, rgba(22, 33, 62, 0.9) 0%, rgba(26, 26, 46, 0.9) 100%);
    padding: 20px; border-radius: 18px; margin-bottom: 20px; border: 1px solid rgba(255, 255, 255, 0.08);
    display: flex; align-items: flex-end; gap: 20px; flex-wrap: wrap; }
.control-item { display: flex; flex-direction: column; gap: 8px; }
.control-item label { color: #fff; font-weight: 700; font-size: 14px; }
.refresh-btn { background: linear-gradient(135deg, #00d4aa 0%, #00ff88 100%); color: #000; border: none;
    padding: 12px 28px; border-radius: 50px; cursor: pointer; font-weight: 900; font-size: 15px;
    box-shadow: 0 5px 20px rgba(0, 212, 170, 0.4); transition: all 0.3s ease; height: 45px; }
.refresh-btn:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(0, 212, 170, 0.6); }
.glass-card { background: linear-gradient(135deg, rgba(26, 26, 46, 0.8) 0%, rgba(22, 33, 62, 0.8) 100%);
    border-radius: 18px; padding: 20px; border: 1px solid rgba(255, 255, 255, 0.1); }
.section-title { background: linear-gradient(135deg, rgba(26, 26, 46, 0.95) 0%, rgba(22, 33, 62, 0.95) 100%);
    padding: 18px 25px; border-radius: 15px; margin-bottom: 15px; border-right: 4px solid #00d4aa; }
.section-title h3 { margin: 0; color: #fff; font-size: 18px; font-weight: 700; }
.connection-status { padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: 700; display: inline-block; margin-right: 8px; }
.status-ok { background: rgba(0, 255, 136, 0.15); color: #00ff88; border: 1px solid #00ff88; }
.status-err { background: rgba(255, 71, 87, 0.15); color: #ff4757; border: 1px solid #ff4757; }
.custom-tabs { background: linear-gradient(135deg, rgba(22, 33, 62, 0.95) 0%, rgba(26, 26, 46, 0.95) 100%);
    border-radius: 18px 18px 0 0 !important; border: 1px solid rgba(0, 212, 170, 0.2) !important; padding: 5px !important; }
.custom-tab { background: transparent !important; color: #8892b0 !important; border: none !important;
    padding: 14px 28px !important; font-weight: 700 !important; font-size: 15px !important;
    border-radius: 12px !important; margin: 0 4px !important; }
.custom-tab--selected { background: linear-gradient(135deg, #00d4aa 0%, #00ff88 100%) !important;
    color: #000 !important; box-shadow: 0 5px 20px rgba(0, 212, 170, 0.4) !important; font-weight: 900 !important; }
.signals-table { width: 100%; border-collapse: separate; border-spacing: 0 8px; }
.signals-table thead th { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #ffd700;
    padding: 14px; font-weight: 700; text-align: center; font-size: 14px; }
.signals-table tbody tr { background: rgba(255, 255, 255, 0.03); transition: all 0.3s ease; }
.signals-table tbody tr:hover { background: rgba(0, 212, 170, 0.1); }
.signals-table tbody td { padding: 12px; text-align: center; color: #e0e0e0; font-size: 13px; }
.summary-card { background: linear-gradient(135deg, rgba(22, 33, 62, 0.9) 0%, rgba(26, 26, 46, 0.9) 100%);
    padding: 20px; border-radius: 18px; min-width: 190px; border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3); display: inline-block; margin: 6px; text-align: center; }
.scanner-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 15px; }
.scanner-card { background: linear-gradient(135deg, rgba(26, 26, 46, 0.9) 0%, rgba(22, 33, 62, 0.9) 100%);
    border-radius: 14px; padding: 16px; border: 1px solid rgba(255, 255, 255, 0.08); transition: all 0.3s ease; position: relative; overflow: hidden;}
.scanner-card:hover { transform: translateY(-3px); border-color: #00d4aa; }
.scanner-sym { font-size: 18px; font-weight: 900; color: #fff; margin-bottom: 8px; }
.progress-bar { height: 6px; background: rgba(255, 255, 255, 0.08); border-radius: 3px; overflow: hidden; margin-top: 6px; }
.progress-fill { height: 100%; background: linear-gradient(90deg, #00d4aa, #00ff88); transition: width 0.3s; }
.badge-up { background: rgba(0, 255, 136, 0.15); color: #00ff88; border: 1px solid #00ff88; padding: 4px 10px; border-radius: 12px; font-weight: 700; font-size: 11px;}
.badge-down { background: rgba(255, 71, 87, 0.15); color: #ff4757; border: 1px solid #ff4757; padding: 4px 10px; border-radius: 12px; font-weight: 700; font-size: 11px;}
.badge-neutral { background: rgba(136, 146, 176, 0.15); color: #8892b0; border: 1px solid #8892b0; padding: 4px 10px; border-radius: 12px; font-weight: 700; font-size: 11px;}
.cycle-card { background: rgba(255,255,255,0.03); border-radius: 12px; padding: 12px; margin-bottom: 10px; border-right: 3px solid; }
.pred-card { background: rgba(255,255,255,0.05); border-radius: 12px; padding: 12px; margin-bottom: 10px; border: 1px solid rgba(255,255,255,0.1); transition: all 0.2s; }
.pred-card:hover { transform: scale(1.02); border-color: #ffd700; }
.utc-badge { background: rgba(187, 134, 252, 0.15); color: #bb86fc; border: 1px solid #bb86fc; padding: 3px 10px; border-radius: 10px; font-size: 10px; font-weight: 700; display: inline-block; margin-right: 5px; }
'''

app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.title = "BITMOON618 | سیستم فراکتال و چرخه‌های زمانی"
app.index_string = f'''
<!DOCTYPE html>
<html><head>
    {{%metas%}}<title>{{%title%}}</title>{{%favicon%}}{{%css%}}
    <style>{CUSTOM_CSS}</style>
</head><body>
    {{%app_entry%}}
    <footer>{{%config%}}{{%scripts%}}{{%renderer%}}</footer>
</body></html>'''

# ==============================================================================
# 1) اتصال بایبیت
# ==============================================================================
class BybitAPIClient:
    REST_ENDPOINTS = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]

    def __init__(self):
        self.session = requests.Session()
        self._active_base = None
        self._lock = threading.Lock()
        self._cache = {}
        self._server_time_cache = None
        self._server_time_ts = 0
        self.headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}

    def _cache_key(self, symbol, interval, limit): return f"{symbol}|{interval}|{limit}"

    def _get_cached(self, key, interval):
        with self._lock:
            if key not in self._cache: return None
            ts, df = self._cache[key]
            try:
                iv = int(interval)
                ttl = 30 if iv <= 15 else 120
            except ValueError:
                ttl = 300
            if (time.time() - ts) < ttl: return df.copy()
            del self._cache[key]
            return None

    def _set_cached(self, key, df):
        with self._lock:
            self._cache[key] = (time.time(), df.copy())
            if len(self._cache) > 100:
                oldest = sorted(self._cache, key=lambda k: self._cache[k][0])[:20]
                for k in oldest: del self._cache[k]

    def _request(self, path, params, timeout=10):
        ordered = [self._active_base] if self._active_base else []
        ordered.extend([ep for ep in self.REST_ENDPOINTS if ep not in ordered])
        for base in ordered:
            try:
                r = self.session.get(f"{base}{path}", params=params, headers=self.headers, timeout=timeout, verify=False)
                if r.status_code == 429: time.sleep(2); continue
                if r.status_code != 200: continue
                data = r.json()
                if data.get('retCode') != 0: continue
                if base != self._active_base: self._active_base = base
                return data
            except: continue
        return None

    def get_server_time(self):
        """زمان دقیق سرور بایبیت (UTC)"""
        if self._server_time_cache and (time.time() - self._server_time_ts) < 5:
            return self._server_time_cache
        data = self._request("/v5/market/time", {})
        if data and 'result' in data:
            server_ms = int(data['result'].get('timeSecond', 0)) * 1000
            if server_ms == 0:
                server_ms = int(data['result'].get('timeNano', 0)) // 1_000_000
            if server_ms > 0:
                server_time = datetime.fromtimestamp(server_ms / 1000, tz=timezone.utc)
                self._server_time_cache = server_time
                self._server_time_ts = time.time()
                return server_time
        return datetime.now(timezone.utc)

    def get_klines(self, symbol="BTCUSDT", interval="5", limit=80):
        cache_key = self._cache_key(symbol, interval, limit)
        cached = self._get_cached(cache_key, interval)
        if cached is not None: return cached
        data = self._request("/v5/market/kline", {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit})
        if not data or 'result' not in data or 'list' not in data['result']: return pd.DataFrame()
        lst = data['result']['list']
        if not lst: return pd.DataFrame()
        df = pd.DataFrame(lst, columns=['ts', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        df['ts'] = pd.to_datetime(df['ts'].astype(int), unit='ms', utc=True)
        for c in ['open', 'high', 'low', 'close', 'volume']: df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df.sort_values('ts').reset_index(drop=True)
        self._set_cached(cache_key, df)
        return df

    def test_connection(self):
        data = self._request("/v5/market/tickers", {"category": "linear", "symbol": "BTCUSDT"})
        if data and 'result' in data and data['result']['list']:
            return True, float(data['result']['list'][0]['lastPrice'])
        return False, 0

bybit_client = BybitAPIClient()

# ==============================================================================
# 2) توابع کمکی زمان UTC
# ==============================================================================
def ts_to_utc_str(ts_value):
    """تبدیل هر نوع timestamp به رشته UTC مطمئن"""
    try:
        if isinstance(ts_value, (int, float)):
            # Unix timestamp (ثانیه یا میلی‌ثانیه)
            if ts_value > 1e12:  # میلی‌ثانیه
                dt = datetime.fromtimestamp(ts_value / 1000, tz=timezone.utc)
            else:  # ثانیه
                dt = datetime.fromtimestamp(ts_value, tz=timezone.utc)
            return dt.strftime('%m-%d %H:%M') + ' UTC'
        elif isinstance(ts_value, str):
            # تلاش برای parse کردن
            # اگر عدد خالص باشد
            try:
                val = float(ts_value)
                if val > 1e12:
                    dt = datetime.fromtimestamp(val / 1000, tz=timezone.utc)
                else:
                    dt = datetime.fromtimestamp(val, tz=timezone.utc)
                return dt.strftime('%m-%d %H:%M') + ' UTC'
            except ValueError:
                pass
            # parse به عنوان ISO string
            dt = pd.Timestamp(ts_value)
            if dt.tzinfo is None:
                dt = dt.tz_localize('UTC')
            else:
                dt = dt.tz_convert('UTC')
            return dt.strftime('%m-%d %H:%M') + ' UTC'
        elif isinstance(ts_value, pd.Timestamp):
            if ts_value.tzinfo is None:
                ts_value = ts_value.tz_localize('UTC')
            else:
                ts_value = ts_value.tz_convert('UTC')
            return ts_value.strftime('%m-%d %H:%M') + ' UTC'
        elif isinstance(ts_value, datetime):
            if ts_value.tzinfo is None:
                ts_value = ts_value.replace(tzinfo=timezone.utc)
            else:
                ts_value = ts_value.astimezone(timezone.utc)
            return ts_value.strftime('%m-%d %H:%M') + ' UTC'
        else:
            return str(ts_value)
    except Exception:
        return str(ts_value)


def now_utc_timestamp():
    """Unix timestamp فعلی سرور بایبیت (ثانیه)"""
    st = bybit_client.get_server_time()
    return st.timestamp()

# ==============================================================================
# 3) ریاضیات اسپیرال
# ==============================================================================
def orbit_xy(a0, cx, cy, rot, th):
    r = a0 * np.exp(B * th)
    return cx + r * np.cos(th + rot), cy + r * np.sin(th + rot)

def candle_price_path(row, n=24):
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    t = np.linspace(0, 1, n)
    return np.piecewise(t,
        [t < 0.25, (t >= 0.25) & (t < 0.6), t >= 0.6],
        [lambda t: o + (h - o) * (t / 0.25),
         lambda t: h - (h - l) * ((t - 0.25) / 0.35),
         lambda t: l + (c - l) * ((t - 0.6) / 0.40)])

def mini_spiral(prices, size, cx, cy, rot):
    th = np.linspace(0, 1.5 * 2 * np.pi, len(prices))
    base = np.exp(B * (th - th[-1]))
    lo, hi = prices.min(), prices.max()
    pn = (prices - lo) / (hi - lo + 1e-12)
    r = size * base * (0.7 + 0.6 * pn)
    return cx + r * np.cos(th + rot), cy + r * np.sin(th + rot)

def get_progress(ts_start, duration_min):
    now = bybit_client.get_server_time()
    if ts_start.tzinfo is None:
        ts_start = ts_start.tz_localize('UTC')
    now_ts = pd.Timestamp(now)
    delta = (now_ts - ts_start).total_seconds() / 60.0 / duration_min
    return min(max(delta, 0.0), 1.0)

def fmt_countdown(mins):
    mins = int(round(mins))
    if mins < 60: return f"{mins}m"
    if mins < 1440: return f"{mins//60}h{mins%60:02d}m"
    return f"{mins//1440}d{(mins%1440)//60}h"

def analyze_cycles(data_dict):
    cycles = {}
    for tf, name, color, minutes, r_max in TF_CHAIN:
        df = data_dict.get(tf)
        if df is None or df.empty: continue
        progress = get_progress(df.iloc[-1]["ts"], minutes)
        n = len(df)
        theta_per = TH_MAX / max(n, 1)
        th_a = (n - 1 + progress) * theta_per
        close = df["close"]
        ma = close.rolling(min(20, n)).mean().iloc[-1]
        dev = (close.iloc[-1] - ma) / ma
        cycles[tf] = {
            "name": name, "color": color, "minutes": minutes, "progress": progress,
            "phase_deg": np.rad2deg(th_a % (2 * np.pi)), "turn": int(th_a // (2 * np.pi)),
            "time_left": (1 - progress) * minutes, "dev": dev, "dir_hint": -1 if dev > 0 else 1,
        }
    return cycles

def predict_reversals(cycles, window_min=20, horizon=3):
    now = bybit_client.get_server_time()
    now_pd = pd.Timestamp(now)
    cands = []
    for tf, c in cycles.items():
        weight = np.log10(c["minutes"] + 1) + 1
        for k in range(horizon):
            for frac in GOLDEN_FRACTIONS:
                t = (k + (frac - c["progress"])) * c["minutes"]
                if t < 0: continue
                cands.append({"t": t, "tf": tf, "w": weight, "dir": c["dir_hint"], "frac": frac})
    cands.sort(key=lambda c: c["t"])
    clusters = []
    for c in cands:
        placed = False
        for cl in clusters:
            if abs(cl["t"] - c["t"]) <= window_min:
                cl["m"].append(c)
                cl["t"] = np.mean([m["t"] for m in cl["m"]])
                placed = True
                break
        if not placed: clusters.append({"t": c["t"], "m": [c]})
    preds = []
    for cl in clusters:
        tfs = set(m["tf"] for m in cl["m"])
        if len(tfs) < 2: continue
        score = sum(m["w"] for m in cl["m"])
        net_dir = sum(m["w"] * m["dir"] for m in cl["m"])
        predicted_time = now_pd + pd.Timedelta(minutes=cl["t"])
        preds.append({
            "time": predicted_time, "in_min": cl["t"], "score": score,
            "n_tf": len(tfs), "tfs": sorted(tfs), "dir": 1 if net_dir >= 0 else -1,
        })
    preds.sort(key=lambda p: p["in_min"])
    if preds:
        mx = max(p["score"] for p in preds)
        for p in preds: p["power"] = int(100 * p["score"] / mx)
    return preds[:8]

# ==============================================================================
# 4) پایگاه داده — ذخیره به صورت Unix Timestamp (UTC)
# ==============================================================================
class ReversalDatabase:
    def __init__(self, db_path="fractal_signals.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS reversals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                symbol TEXT NOT NULL,
                predicted_time REAL NOT NULL,
                direction INTEGER NOT NULL,
                power REAL NOT NULL,
                n_tf INTEGER NOT NULL,
                tfs TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING',
                notes TEXT
            )''')

    def _get_conn(self): return sqlite3.connect(self.db_path)

    def insert_signal(self, symbol, predicted_time, direction, power, n_tf, tfs, notes=""):
        with self._lock, self._get_conn() as conn:
            now_ts = now_utc_timestamp()
            # جلوگیری از تکرار: سیگنال مشابه در ۷۲ دقیقه اخیر
            cursor = conn.execute(
                'SELECT id FROM reversals WHERE symbol=? AND (? - timestamp) < 4320',
                (symbol, now_ts)
            )
            if cursor.fetchone(): return None

            # تبدیل predicted_time به unix timestamp
            if isinstance(predicted_time, pd.Timestamp):
                pred_ts = predicted_time.timestamp()
            elif isinstance(predicted_time, datetime):
                pred_ts = predicted_time.timestamp()
            else:
                pred_ts = float(predicted_time)

            conn.execute('''INSERT INTO reversals
                (timestamp, symbol, predicted_time, direction, power, n_tf, tfs, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (now_ts, symbol, pred_ts, direction, power, n_tf, ','.join(tfs), notes))

    def get_all_signals(self, limit=100):
        with self._get_conn() as conn:
            return pd.read_sql_query('SELECT * FROM reversals ORDER BY id DESC LIMIT ?', conn, params=(limit,))

signal_db = ReversalDatabase()

# ==============================================================================
# 5) اسکنر ۲۱ ارز
# ==============================================================================
class FractalScanner:
    def __init__(self, api, db):
        self.api = api
        self.db = db
        self.last_results = {}
        self.scan_running = False
        self.last_scan_time = None
        self._lock = threading.Lock()
        self._start_thread()

    def _start_thread(self):
        def worker():
            while True:
                try:
                    self._scan_all()
                    time.sleep(300)
                except Exception as e:
                    print(f"❌ خطای اسکنر: {e}")
                    time.sleep(60)
        threading.Thread(target=worker, daemon=True).start()

    def _scan_symbol(self, symbol):
        try:
            data_dict = {}
            for tf, _, _, _, _ in TF_CHAIN:
                df = self.api.get_klines(symbol, tf, limit=80)
                if not df.empty: data_dict[tf] = df
            if not data_dict: return None
            cycles = analyze_cycles(data_dict)
            preds = predict_reversals(cycles)
            current_price = data_dict[TF_CHAIN[-1][0]]['close'].iloc[-1] if TF_CHAIN[-1][0] in data_dict else 0
            res = {'symbol': symbol, 'price': current_price, 'cycles': cycles, 'preds': preds, 'best_pred': preds[0] if preds else None}
            if preds and preds[0]['power'] >= 75 and preds[0]['n_tf'] >= 3:
                self.db.insert_signal(symbol, preds[0]['time'], preds[0]['dir'], preds[0]['power'], preds[0]['n_tf'], preds[0]['tfs'])
            return res
        except Exception as e:
            print(f"❌ خطا در اسکن {symbol}: {e}")
            return None

    def _scan_all(self):
        self.scan_running = True
        for sym in SCAN_SYMBOLS:
            r = self._scan_symbol(sym)
            if r:
                with self._lock: self.last_results[sym] = r
            time.sleep(0.5)
        self.scan_running = False
        self.last_scan_time = bybit_client.get_server_time()

    def get_results(self):
        with self._lock: return self.last_results.copy()

scanner = FractalScanner(bybit_client, signal_db)

# ==============================================================================
# 6) نمودار و پنل‌ها
# ==============================================================================
def build_live_fractal(data_dict, symbol, preds):
    fig = go.Figure()
    if not data_dict: return fig, []
    R0 = TF_CHAIN[0][4] * 1.25
    rng = np.random.default_rng(42)
    fig.add_trace(go.Scatter(x=rng.uniform(-R0, R0, 220), y=rng.uniform(-R0, R0, 220), mode="markers",
                             marker=dict(size=rng.uniform(0.5, 2.0, 220), color=TXT, opacity=rng.uniform(0.05, 0.25, 220)),
                             showlegend=False, hoverinfo="skip"))
    for k in range(1, 6):
        rr = TF_CHAIN[0][4] / (PHI ** (k * 0.7))
        th = np.linspace(0, 2 * np.pi, 180)
        fig.add_trace(go.Scatter(x=rr*np.cos(th), y=rr*np.sin(th), mode="lines", line=dict(color=GOLD, width=0.6, dash="dot"), opacity=0.15, showlegend=False, hoverinfo="skip"))
    center = (0.0, 0.0)
    rot = 0.0
    active_points = []
    tf_status = []
    level0 = None
    for level, (tf, name, color, minutes, r_max) in enumerate(TF_CHAIN):
        df = data_dict.get(tf)
        if df is None or df.empty: continue
        n = len(df)
        n_closed = max(n - 1, 0)
        a0 = r_max / GROWTH
        mini_size = max(r_max * 0.05, 0.05)
        theta_per = TH_MAX / max(n, 1)
        progress = get_progress(df.iloc[-1]["ts"], minutes)
        th_a = (n_closed + progress) * theta_per
        if level0 is None:
            level0 = dict(a0=a0, rot=rot, center=center, n_closed=n_closed, progress=progress, theta_per=theta_per, minutes=minutes)
        th_full = np.linspace(0, TH_MAX, 500)
        fx, fy = orbit_xy(a0, center[0], center[1], rot, th_full)
        fig.add_trace(go.Scatter(x=fx, y=fy, mode="lines", line=dict(color=color, width=1.2, dash="dot"), opacity=0.40, showlegend=False, hoverinfo="skip"))
        n_pts = max(int(500 * th_a / TH_MAX), 8)
        th_trav = np.linspace(0, th_a, n_pts)
        tx, ty = orbit_xy(a0, center[0], center[1], rot, th_trav)
        fig.add_trace(go.Scatter(x=tx, y=ty, mode="lines", line=dict(color=color, width=7), opacity=0.12, showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=tx, y=ty, mode="lines", line=dict(color=color, width=2.2), opacity=0.95, showlegend=False, hoverinfo="skip"))
        bull_x, bull_y, bear_x, bear_y = [], [], [], []
        for i in range(max(n_closed - 14, 0), n_closed):
            row = df.iloc[i]
            th_i = (i + 0.5) * theta_per
            px, py = orbit_xy(a0, center[0], center[1], rot, np.array([th_i]))
            mx, my = mini_spiral(candle_price_path(row), mini_size, px[0], py[0], rot + th_i)
            if row["close"] >= row["open"]: bull_x += list(mx) + [None]; bull_y += list(my) + [None]
            else: bear_x += list(mx) + [None]; bear_y += list(my) + [None]
        if bull_x: fig.add_trace(go.Scatter(x=bull_x, y=bull_y, mode="lines", line=dict(color=UP, width=1), opacity=0.6, showlegend=False, hoverinfo="skip"))
        if bear_x: fig.add_trace(go.Scatter(x=bear_x, y=bear_y, mode="lines", line=dict(color=DN, width=1), opacity=0.6, showlegend=False, hoverinfo="skip"))
        ax, ay = orbit_xy(a0, center[0], center[1], rot, np.array([th_a]))
        ax, ay = float(ax[0]), float(ay[0])
        act = df.iloc[-1]
        fig.add_trace(go.Scatter(x=[ax], y=[ay], mode="markers", marker=dict(size=22 - level*2, color=color, opacity=0.18), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=[ax], y=[ay], mode="markers+text", marker=dict(size=max(9 - level, 5), color=color, line=dict(width=1.5, color="white")),
                                 text=[f"{act['close']:,.0f}"], textposition="top center", textfont=dict(color=color, size=10, family="monospace"), showlegend=False,
                                 hovertext=(f"🕐 {name}<br>قیمت: {act['close']:,.2f}<br>فاز چرخه: {np.rad2deg(th_a % (2*np.pi)):.0f}°<br>پیشرفت: {progress*100:.0f}%"), hoverinfo="text"))
        active_points.append((ax, ay, color))
        tf_status.append((tf, name, color, act["close"], progress))
        center = (ax, ay)
        rot = rot + th_a + GOLDEN_ANGLE
    if level0 and preds:
        for p in preds:
            future_th = (level0["n_closed"] + level0["progress"] + p["in_min"] / level0["minutes"]) * level0["theta_per"]
            if future_th > TH_MAX: continue
            px, py = orbit_xy(level0["a0"], 0, 0, level0["rot"], np.array([future_th]))
            d_color = UP if p["dir"] > 0 else DN
            d_txt = "بازگشت صعودی" if p["dir"] > 0 else "بازگشت نزولی"
            size = 8 + p["power"] / 12
            fig.add_trace(go.Scatter(x=[px[0]], y=[py[0]], mode="markers", marker=dict(size=size + 8, color=d_color, opacity=0.2, symbol="diamond"), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=[px[0]], y=[py[0]], mode="markers+text", marker=dict(size=size, color=d_color, symbol="diamond", line=dict(width=1.5, color="white")),
                                     text=[fmt_countdown(p["in_min"])], textposition="bottom center", textfont=dict(color=d_color, size=9), showlegend=False,
                                     hovertext=(f"🔮 {d_txt}<br>زمان سرور: {p['time'].strftime('%m-%d %H:%M')} UTC<br>قدرت: {p['power']}%<br>TF‌ها: {', '.join(p['tfs'])}"), hoverinfo="text"))
    for i in range(len(active_points) - 1):
        x1, y1, _ = active_points[i]; x2, y2, _ = active_points[i+1]
        fig.add_trace(go.Scatter(x=[x1, x2], y=[y1, y2], mode="lines", line=dict(color=MUT, width=1, dash="dash"), opacity=0.6, showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=[0], y=[0], mode="markers", marker=dict(size=12, color=GOLD, symbol="star", line=dict(width=1.5, color="white")), name="مرکز", hoverinfo="skip"))
    server_time = bybit_client.get_server_time()
    fig.update_layout(uirevision="GOLDEN_SPIRAL_FIXED", template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color=TXT, family="Vazirmatn"),
                      showlegend=False, margin=dict(l=10, r=10, t=45, b=10), dragmode="zoom",
                      title=dict(text=f"🌀 {symbol} | زمان سرور: {server_time.strftime('%H:%M:%S')} UTC", x=0.5, font=dict(color=GOLD, size=13)),
                      xaxis=dict(range=[-R0, R0], showgrid=False, zeroline=False, showticklabels=False),
                      yaxis=dict(range=[-R0, R0], scaleanchor="x", scaleratio=1, showgrid=False, zeroline=False, showticklabels=False))
    return fig, tf_status

def build_prediction_panel(preds):
    if not preds: return html.Div("هم‌گرایی معناداری یافت نشد.", style={'textAlign': 'center', 'color': '#8892b0', 'padding': '20px'})
    cards = []
    for i, p in enumerate(preds):
        d_color = UP if p["dir"] > 0 else DN
        d_txt = "🟢 بازگشت صعودی" if p["dir"] > 0 else "🔴 بازگشت نزولی"
        cards.append(html.Div([
            html.Div([
                html.Span(f"🔮 #{i+1}", style={'color': '#ffd700', 'fontWeight': '900', 'fontSize': '13px'}),
                html.Span(d_txt, style={'color': d_color, 'fontSize': '13px', 'fontWeight': '700', 'marginRight': '10px'}),
                html.Span(f"⏳ {fmt_countdown(p['in_min'])}", style={'color': '#e0e0e0', 'fontSize': '12px', 'float': 'left'})
            ], style={'marginBottom': '8px'}),
            html.Div([html.Div(style={'width': f"{p['power']}%", 'height': '5px', 'background': d_color, 'borderRadius': '3px'})],
                     style={'background': 'rgba(255,255,255,0.05)', 'height': '5px', 'borderRadius': '3px', 'overflow': 'hidden'}),
            html.Div([
                html.Span("UTC", className="utc-badge"),
                html.Span(f"قدرت: {p['power']}%", style={'color': '#8892b0', 'fontSize': '11px'}),
                html.Span(f" | {p['n_tf']} TF", style={'color': '#8892b0', 'fontSize': '11px', 'marginRight': '5px'}),
                html.Span(f" | {p['time'].strftime('%m-%d %H:%M')}", style={'color': '#bb86fc', 'fontSize': '11px', 'float': 'left', 'fontWeight': '700'})
            ], style={'marginTop': '6px'}),
            html.Div(" | ".join(p["tfs"]), style={'color': '#8892b0', 'fontSize': '10px', 'marginTop': '4px'})
        ], className="pred-card"))
    return html.Div(cards)

def build_tf_panel(tf_status, cycles):
    cards = []
    for tf, name, color, price, progress in tf_status:
        c = cycles.get(tf, {})
        cards.append(html.Div([
            html.Div([
                html.Span("●", style={'color': color, 'fontSize': '16px', 'marginRight': '8px'}),
                html.Span(name, style={'color': '#fff', 'fontSize': '14px', 'fontWeight': '700'}),
                html.Span(f"{price:,.2f}", style={'color': color, 'fontSize': '13px', 'fontFamily': 'monospace', 'float': 'left'})
            ]),
            html.Div([html.Div(style={'width': f"{progress*100:.0f}%", 'height': '4px', 'background': color, 'borderRadius': '2px'})],
                     style={'background': 'rgba(255,255,255,0.05)', 'height': '4px', 'borderRadius': '2px', 'marginTop': '8px', 'overflow': 'hidden'}),
            html.Div(f"فاز: {c.get('phase_deg', 0):.0f}° | دور {c.get('turn', 0)} | تا تکمیل: {fmt_countdown(c.get('time_left', 0))}",
                     style={'color': '#8892b0', 'fontSize': '11px', 'marginTop': '6px'})
        ], className="cycle-card", style={'borderRightColor': color}))
    return html.Div(cards)

# ==============================================================================
# 7) Layout
# ==============================================================================
tab1_content = html.Div([
    html.Div([
        html.Div([html.Label("🎯 نماد:"), dcc.Input(id='symbol-input', value=DEFAULT_SYMBOL, type='text', style={'width': '140px', 'backgroundColor': '#0a0e27', 'color': '#fff', 'border': '1px solid #00d4aa', 'borderRadius': '10px', 'padding': '10px', 'fontWeight': '700'})], className="control-item"),
        html.Button('🔄 بروزرسانی', id='refresh-btn', n_clicks=0, className="refresh-btn"),
        html.Div(id='status-text', style={'color': '#00ff88', 'fontWeight': '700', 'paddingBottom': '10px'}),
    ], className="control-panel"),
    html.Div([
        html.Div([
            html.Div([html.H3("🌀 نمودار کهکشانی اسپیرال فراکتال")], className="section-title"),
            html.Div([dcc.Graph(id='spiral-chart', config={"displaylogo": False, "scrollZoom": True})], className="glass-card", style={'padding': '10px'}),
        ], style={'width': '68%', 'display': 'inline-block', 'verticalAlign': 'top', 'marginRight': '1%'}),
        html.Div([
            html.Div([html.H3("🔮 نقاط بازگشتی پیش‌بینی‌شده")], className="section-title", style={'borderRightColor': '#ffd700'}),
            html.Div(id='pred-panel', style={'maxHeight': '350px', 'overflowY': 'auto', 'marginBottom': '15px'}),
            html.Div([html.H3("🕐 چرخه تایم‌فریم‌ها")], className="section-title", style={'borderRightColor': '#bb86fc'}),
            html.Div(id='tf-panel', style={'maxHeight': '350px', 'overflowY': 'auto'}),
        ], style={'width': '30%', 'display': 'inline-block', 'verticalAlign': 'top'}),
    ], style={'marginBottom': '20px'})
])

tab2_content = html.Div([
    html.Div([html.H3("🛰️ اسکنر زنده هم‌گرایی چرخه‌ها (۲۱ ارز)")], className="section-title", style={'borderRightColor': '#ffd700'}),
    html.P("🔍 اسکن خودکار برای یافتن نقاط بازگشتی قوی | زمان بر اساس سرور بایبیت (UTC)", style={'color': '#8892b0', 'margin': '0 0 15px 0', 'padding': '0 20px'}),
    html.Div(id='scanner-status-bar', style={'marginBottom': '15px'}),
    html.Div(id='scanner-active-signals', style={'marginBottom': '25px'}),
    html.Div([html.Div([html.H3("📊 نمای کلی چرخه‌ها")], className="section-title"), html.Div(id='scanner-grid', className="scanner-grid")], style={'marginBottom': '25px'}),
])

tab3_content = html.Div([
    html.Div([html.H3("📊 آمار و تاریخچه پیش‌بینی‌ها")], className="section-title", style={'borderRightColor': '#bb86fc'}),
    html.Div(id='stats-summary-cards', style={'marginBottom': '20px', 'textAlign': 'center'}),
    html.Div([html.Div([html.H3("📋 تاریخچه سیگنال‌های هم‌گرایی")], className="section-title"), html.Div([html.Div(id='stats-history-table', style={'overflowX': 'auto'})], className="glass-card")], style={'marginBottom': '20px'}),
])

app.layout = html.Div([
    dcc.Store(id='data-store', data={}),
    html.Div([
        html.Div([html.Span("🌙", className="banner-logo"), html.Div([html.H2("به کانال BITMOON618 بپیوندید!"), html.P("تحلیل‌های هندسی کریپتو | چرخه‌های زمانی | آموزش رایگان")], className="banner-text")], className="banner-left"),
        html.A([html.Span("📢"), html.Span("عضویت در کانال")], href="https://t.me/BITMOON618", target="_blank", className="banner-btn"),
    ], className="bitmoon-banner"),
    html.Div([html.H1("🌀 سیستم جامع فراکتال و چرخه‌های زمانی"), html.P("پیش‌بینی نقاط بازگشتی بر اساس هم‌گرایی کسرهای طلایی | زمان سرور بایبیت (UTC) | نسخه v2.3", style={'color': '#8892b0', 'margin': '8px 0 0 0', 'fontSize': '14px'}), html.Div(id='connection-indicator', style={'marginTop': '10px'})], className="main-header"),
    dcc.Tabs(id='main-tabs', value='tab-analysis', className='custom-tabs', children=[
        dcc.Tab(label='🌀 تحلیل تک نماد', value='tab-analysis', className='custom-tab', selected_className='custom-tab--selected'),
        dcc.Tab(label='🛰️ اسکنر ۲۱ ارز', value='tab-scanner', className='custom-tab', selected_className='custom-tab--selected'),
        dcc.Tab(label='📊 پایگاه داده و آمار', value='tab-stats', className='custom-tab', selected_className='custom-tab--selected'),
    ]),
    html.Div(tab1_content, id='tab-1-wrapper'),
    html.Div(tab2_content, id='tab-2-wrapper', style={'display': 'none'}),
    html.Div(tab3_content, id='tab-3-wrapper', style={'display': 'none'}),
    html.Div([html.P("💎 ساخته شده با ❤️ برای تریدرهای حرفه‌ای | BITMOON618", style={'color': '#8892b0', 'textAlign': 'center', 'margin': '0', 'fontSize': '14px'})], style={'padding': '20px', 'marginTop': '30px'}),
    dcc.Interval(id='live-tick', interval=5000, n_intervals=0),
    dcc.Interval(id='data-refresh', interval=60000, n_intervals=0),
    dcc.Interval(id='scanner-refresh', interval=30000, n_intervals=0),
    dcc.Interval(id='stats-refresh', interval=15000, n_intervals=0),
], style={'backgroundColor': '#0a0e27', 'padding': '20px', 'minHeight': '100vh'})

# ==============================================================================
# 8) کال‌بک‌ها
# ==============================================================================
@app.callback([Output('tab-1-wrapper', 'style'), Output('tab-2-wrapper', 'style'), Output('tab-3-wrapper', 'style')], Input('main-tabs', 'value'))
def switch_tab(t):
    h, s = {'display': 'none'}, {}
    if t == 'tab-analysis': return s, h, h
    elif t == 'tab-scanner': return h, s, h
    elif t == 'tab-stats': return h, h, s
    return s, h, h

@app.callback(Output('connection-indicator', 'children'), Input('data-refresh', 'n_intervals'))
def update_connection_indicator(n):
    ok, price = bybit_client.test_connection()
    ep = bybit_client._active_base or "-"
    server_time = bybit_client.get_server_time()
    time_str = server_time.strftime('%H:%M:%S')
    if ok:
        return html.Div([
            html.Span("🟢 متصل", className="connection-status status-ok"),
            html.Span(f"💰 BTC: ${price:,.2f}  |  🕐 سرور: {time_str} UTC  |  🌐 {ep}",
                      style={'color': '#8892b0', 'fontSize': '13px', 'fontWeight': '600'})
        ])
    return html.Div([html.Span("🔴 قطع", className="connection-status status-err")])

@app.callback(Output('data-store', 'data'), Output('status-text', 'children'), Input('data-refresh', 'n_intervals'), Input('refresh-btn', 'n_clicks'), State('symbol-input', 'value'))
def fetch_data(n_ref, n_btn, symbol):
    symbol = (symbol or DEFAULT_SYMBOL).upper()
    data, ok = {}, 0
    for tf, _, _, _, _ in TF_CHAIN:
        df = bybit_client.get_klines(symbol, tf, limit=80)
        if not df.empty:
            df["ts"] = df["ts"].dt.strftime("%Y-%m-%d %H:%M:%S+00:00")
            data[tf] = df.to_dict("records")
            ok += 1
    server_time = bybit_client.get_server_time()
    return data, f"✅ {ok}/{len(TF_CHAIN)} تایم‌فریم | 🕐 سرور: {server_time.strftime('%H:%M:%S')} UTC"

@app.callback([Output('spiral-chart', 'figure'), Output('pred-panel', 'children'), Output('tf-panel', 'children')], Input('live-tick', 'n_intervals'), State('data-store', 'data'), State('symbol-input', 'value'))
def animate(tick, stored, symbol):
    symbol = (symbol or DEFAULT_SYMBOL).upper()
    if not stored:
        empty = go.Figure(layout=dict(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', annotations=[dict(text="⏳ در حال دریافت داده...", x=0.5, y=0.5, showarrow=False, font=dict(color=MUT, size=14))]))
        return empty, html.Div(), html.Div()
    data_dict = {}
    for tf, recs in stored.items():
        if recs:
            df = pd.DataFrame(recs)
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
            data_dict[tf] = df
    cycles = analyze_cycles(data_dict)
    preds = predict_reversals(cycles)
    fig, tf_status = build_live_fractal(data_dict, symbol, preds)
    return fig, build_prediction_panel(preds), build_tf_panel(tf_status, cycles)

@app.callback([Output('scanner-status-bar', 'children'), Output('scanner-active-signals', 'children'), Output('scanner-grid', 'children')], Input('scanner-refresh', 'n_intervals'))
def update_scanner(n):
    results = scanner.get_results()
    server_time = bybit_client.get_server_time()
    time_str = server_time.strftime('%H:%M:%S')
    scan_time_str = scanner.last_scan_time.strftime('%H:%M:%S') if scanner.last_scan_time else 'در حال اسکن...'
    status = f"📡 آخرین اسکن: {scan_time_str} UTC | 🕐 سرور فعلی: {time_str} UTC | 🔄 وضعیت: {'در حال اسکن' if scanner.scan_running else 'آماده'}"
    sb = html.Div([html.Span(status, style={'color': '#00ff88', 'fontWeight': '700'})], className="glass-card", style={'padding': '15px'})

    df = signal_db.get_all_signals(20)
    if not df.empty:
        rows = []
        for _, r in df.iterrows():
            d_color = UP if r['direction'] > 0 else DN
            d_txt = "🟢 صعودی" if r['direction'] > 0 else "🔴 نزولی"
            # ✅ استفاده از تابع مطمئن تبدیل زمان
            ts_str = ts_to_utc_str(r['timestamp'])
            pred_str = ts_to_utc_str(r['predicted_time'])
            rows.append(html.Tr([
                html.Td(ts_str),
                html.Td(html.Span(r['symbol'], style={'fontWeight': '900', 'color': '#ffd700'})),
                html.Td(pred_str),
                html.Td(html.Span(d_txt, style={'color': d_color, 'fontWeight': '700'})),
                html.Td(f"{r['power']}%", style={'color': '#00ff88', 'fontWeight': '700'}),
                html.Td(f"{r['n_tf']} TF"),
                html.Td(r['tfs']),
            ]))
        sig_table = html.Div([html.Div([html.H3("⚡ سیگنال‌های هم‌گرایی قوی ثبت شده")], className="section-title", style={'borderRightColor': '#ff8c00'}), html.Div([html.Table([html.Thead(html.Tr([html.Th('زمان ثبت'), html.Th('نماد'), html.Th('زمان هدف'), html.Th('جهت'), html.Th('قدرت'), html.Th('تعداد TF'), html.Th('تایم‌فریم‌ها')])), html.Tbody(rows)], className="signals-table")], className="glass-card")], style={'marginBottom': '20px'})
    else:
        sig_table = html.Div([html.Div([html.H3("⚡ سیگنال‌های هم‌گرایی")], className="section-title"), html.Div([html.P("در حال حاضر سیگنال هم‌گرایی قوی ثبت نشده است.", style={'textAlign': 'center', 'color': '#8892b0', 'padding': '20px'})], className="glass-card")], style={'marginBottom': '20px'})

    cards = []
    for sym in SCAN_SYMBOLS:
        r = results.get(sym)
        if not r:
            cards.append(html.Div([html.Div(sym, className="scanner-sym", style={'color': '#555'}), html.Div("⏳ در انتظار...", style={'color': '#8892b0'})], className="scanner-card"))
            continue
        bp = r.get('best_pred')
        if bp:
            d_color = UP if bp['dir'] > 0 else DN
            d_txt = "🟢 صعودی" if bp['dir'] > 0 else "🔴 نزولی"
            badge_cls = "badge-up" if bp['dir'] > 0 else "badge-down"
            cards.append(html.Div([
                html.Div(sym, className="scanner-sym"),
                html.Div(f"قیمت: ${r['price']:,.2f}", style={'color': '#8892b0', 'fontSize': '12px', 'marginBottom': '8px'}),
                html.Div([html.Span(d_txt, className=badge_cls), html.Span(f"⏳ {fmt_countdown(bp['in_min'])}", style={'color': '#e0e0e0', 'fontSize': '11px', 'float': 'left'})], style={'marginBottom': '8px'}),
                html.Div(f"قدرت: {bp['power']}% | {bp['n_tf']} TF", style={'color': d_color, 'fontWeight': '700', 'fontSize': '13px'}),
                html.Div(f"🕐 هدف: {bp['time'].strftime('%H:%M')} UTC", style={'color': '#bb86fc', 'fontSize': '11px', 'marginTop': '6px'}),
                html.Div(className="progress-bar", children=[html.Div(className="progress-fill", style={'width': f"{bp['power']}%", 'background': d_color})])
            ], className="scanner-card"))
        else:
            cards.append(html.Div([html.Div(sym, className="scanner-sym"), html.Div(f"قیمت: ${r['price']:,.2f}", style={'color': '#8892b0', 'fontSize': '12px'}), html.Div([html.Span("خنثی", className="badge-neutral")], style={'marginTop': '8px'})], className="scanner-card"))
    return sb, sig_table, cards

@app.callback([Output('stats-summary-cards', 'children'), Output('stats-history-table', 'children')], Input('stats-refresh', 'n_intervals'))
def update_stats(n):
    df = signal_db.get_all_signals(500)
    total = len(df)
    up_count = len(df[df['direction'] > 0]) if not df.empty else 0
    avg_power = df['power'].mean() if not df.empty else 0
    cards = html.Div([
        html.Div([html.Div("📊 کل پیش‌بینی‌ها", style={'fontSize': '13px', 'color': '#8892b0'}), html.Div(f"{total}", style={'fontSize': '28px', 'color': '#fff', 'fontWeight': '900', 'marginTop': '8px'})], className="summary-card"),
        html.Div([html.Div("🟢 پیش‌بینی صعودی", style={'fontSize': '13px', 'color': '#8892b0'}), html.Div(f"{up_count}", style={'fontSize': '28px', 'color': '#00ff88', 'fontWeight': '900', 'marginTop': '8px'})], className="summary-card"),
        html.Div([html.Div("🔴 پیش‌بینی نزولی", style={'fontSize': '13px', 'color': '#8892b0'}), html.Div(f"{total - up_count}", style={'fontSize': '28px', 'color': '#ff4757', 'fontWeight': '900', 'marginTop': '8px'})], className="summary-card"),
        html.Div([html.Div("⚡ میانگین قدرت", style={'fontSize': '13px', 'color': '#8892b0'}), html.Div(f"{avg_power:.1f}%", style={'fontSize': '28px', 'color': '#ffd700', 'fontWeight': '900', 'marginTop': '8px'})], className="summary-card"),
    ])
    if not df.empty:
        df_show = df.head(50)
        rows = []
        for _, r in df_show.iterrows():
            d_color = UP if r['direction'] > 0 else DN
            d_txt = "🟢 صعودی" if r['direction'] > 0 else "🔴 نزولی"
            # ✅ استفاده از تابع مطمئن تبدیل زمان
            ts_str = ts_to_utc_str(r['timestamp'])
            pred_str = ts_to_utc_str(r['predicted_time'])
            rows.append(html.Tr([
                html.Td(ts_str),
                html.Td(html.Span(r['symbol'], style={'fontWeight': '900', 'color': '#ffd700'})),
                html.Td(pred_str),
                html.Td(html.Span(d_txt, style={'color': d_color, 'fontWeight': '700'})),
                html.Td(f"{r['power']}%", style={'color': '#00ff88', 'fontWeight': '700'}),
                html.Td(f"{r['n_tf']} TF"),
                html.Td(r['tfs']),
            ]))
        table = html.Table([html.Thead(html.Tr([html.Th('زمان ثبت'), html.Th('نماد'), html.Th('زمان هدف'), html.Th('جهت'), html.Th('قدرت'), html.Th('تعداد TF'), html.Th('تایم‌فریم‌ها')])), html.Tbody(rows)], className="signals-table")
    else:
        table = html.Div("هنوز سیگنالی ثبت نشده است...", style={'textAlign': 'center', 'color': '#8892b0', 'padding': '30px'})
    return cards, table

# ==============================================================================
# 9) اجرا
# ==============================================================================
def open_browser():
    try:
        webbrowser.open_new("http://127.0.0.1:8060")
        print("🌐 مرورگر باز شد: http://127.0.0.1:8060")
    except Exception as e: print(f"⚠️ خطا در باز کردن مرورگر: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Starting BITMOON618 Golden Fractal v2.3 (Fixed UTC)")
    print("=" * 60)
    server_time = bybit_client.get_server_time()
    print(f"🕐 زمان سرور بایبیت: {server_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    if not os.environ.get('WERKZEUG_RUN_MAIN'):
        Timer(1.5, open_browser).start()
    app.run(debug=True, host="127.0.0.1", port=8060, use_reloader=False)