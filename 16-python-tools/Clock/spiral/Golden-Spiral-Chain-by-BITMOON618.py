# -*- coding: utf-8 -*-
"""
🌀 Golden Spiral Chain + Cycle/Reversal Analysis — زنجیره اسپیرال طلایی
       + تحلیل چرخه‌ی فاز و علامت‌گذاری نواحی احتمالیِ بازگشت (v5.0 Full System)
------------------------------------------------------------------
نسخه کامل شامل:
1. تحلیل تک نماد (اسپیرال و چرخه‌ها)
2. اسکنر زنده ۱۰ ارز برای یافتن فازهای داغ
3. پایگاه داده و آمار سیگنال‌های ثبت شده
4. رابط کاربری مدرن، تم شیشه‌ای و بنر تبلیغاتی BITMOON618
"""

import numpy as np
import pandas as pd
import requests
import dash
from dash import dcc, html, Input, Output, State, callback_context, no_update
import plotly.graph_objects as go
import time
import os
import sqlite3
import threading
import webbrowser
from threading import Timer
from datetime import datetime

# ==============================================================================
# 0) پالت رنگی و تنظیمات پایه
# ==============================================================================
BG_MAIN = "#0a0e27"
BG_CARD = "#16213e"
LINE = "rgba(255, 255, 255, 0.1)"
TXT = "#e0e0e0"
MUT = "#8892b0"
GOLD = "#ffd700"
UP = "#00ff88"
DN = "#ff4757"
WARN = "#ff8c00"

LEVEL_COLORS = ["#ffd700", "#00d4aa", "#ff8c00", "#bb86fc", "#00ff88", "#ff4757", "#5da8ff", "#f093fb"]

PHI = (1 + 5 ** 0.5) / 2.0
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_CATEGORY = "linear"

TF_LABELS = {
    "1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m",
    "60": "1h", "120": "2h", "240": "4h", "360": "6h", "720": "12h",
    "D": "1D", "W": "1W",
}
ALL_TF_ORDER = ["W", "D", "720", "360", "240", "120", "60", "30", "15", "5", "3", "1"]
DEFAULT_CHAIN = ["D", "240", "60", "15", "5", "1"]

SCAN_SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
    'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'DOTUSDT', 'LINKUSDT'
]

R0_ROOT = 100.0
UIREV = "golden-spiral-chain-v5-pro"

# ==============================================================================
# CSS اختصاصی و مدرن
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
.error-message { background: linear-gradient(135deg, rgba(255, 71, 87, 0.2) 0%, rgba(201, 42, 42, 0.2) 100%);
    border: 2px solid #ff4757; border-radius: 15px; padding: 30px; text-align: center; color: #fff; margin: 20px auto; max-width: 600px; }
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
.scanner-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 15px; }
.scanner-card { background: linear-gradient(135deg, rgba(26, 26, 46, 0.9) 0%, rgba(22, 33, 62, 0.9) 100%);
    border-radius: 14px; padding: 16px; border: 1px solid rgba(255, 255, 255, 0.08); transition: all 0.3s ease; }
.scanner-card:hover { transform: translateY(-3px); border-color: #00d4aa; }
.scanner-sym { font-size: 18px; font-weight: 900; color: #fff; margin-bottom: 8px; }
.scanner-price { font-size: 14px; color: #8892b0; margin-bottom: 10px; }
.progress-bar { height: 6px; background: rgba(255, 255, 255, 0.08); border-radius: 3px; overflow: hidden; margin-top: 6px; }
.progress-fill { height: 100%; background: linear-gradient(90deg, #00d4aa, #00ff88); transition: width 0.3s; }
.badge-hit { background: linear-gradient(135deg, #00ff88 0%, #00d4aa 100%); color: #000; padding: 4px 10px; border-radius: 12px; font-weight: 700; font-size: 11px;}
.badge-miss { background: linear-gradient(135deg, #ff4757 0%, #c92a2a 100%); color: #fff; padding: 4px 10px; border-radius: 12px; font-weight: 700; font-size: 11px;}
.badge-open { background: linear-gradient(135deg, #ffd700 0%, #ff8c00 100%); color: #000; padding: 4px 10px; border-radius: 12px; font-weight: 700; font-size: 11px;}

/* Fix for Checklist Styling */
.tf-checklist { display: flex; flex-wrap: wrap; gap: 5px; }
.tf-checklist label {
    background: rgba(255,255,255,0.05); padding: 8px 14px; border-radius: 8px;
    border: 1px solid rgba(255,255,255,0.1); cursor: pointer; color: #fff;
    transition: all 0.2s; font-size: 13px; font-weight: 600;
}
.tf-checklist label:has(input:checked) {
    background: rgba(0, 212, 170, 0.2) !important; border: 1px solid #00d4aa !important;
    color: #00ff88 !important; font-weight: 700 !important; box-shadow: 0 0 10px rgba(0, 212, 170, 0.3);
}
.tf-checklist input[type="checkbox"] { margin-left: 6px; accent-color: #00d4aa; }
'''

app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.title = "BITMOON618 | سیستم جامع اسپیرال طلایی"
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
# 1) اتصال REST پایدار به بایبیت
# ==============================================================================
REST_CANDIDATES = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
_ACTIVE_REST_BASE = {"url": None}


def bybit_get(path, params, timeout=10):
    cands = ([_ACTIVE_REST_BASE["url"]] if _ACTIVE_REST_BASE["url"] else []) + \
            [b for b in REST_CANDIDATES if b != _ACTIVE_REST_BASE["url"]]
    for base in cands:
        try:
            r = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code in (403, 451): continue
            r.raise_for_status()
            d = r.json()
            if d.get("retCode") == 0:
                _ACTIVE_REST_BASE["url"] = base
                return d
        except Exception:
            continue
    return None


def get_klines(symbol, interval, category="linear", limit=200):
    d = bybit_get("/v5/market/kline", {"category": category, "symbol": symbol, "interval": interval, "limit": limit})
    if not d or "list" not in (d.get("result") or {}): return pd.DataFrame()
    lst = d["result"]["list"]
    if not lst: return pd.DataFrame()
    df = pd.DataFrame(lst, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
    for c in ["open", "high", "low", "close", "volume"]: df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)


# ==============================================================================
# 2) هندسه‌ی اسپیرال لگاریتمی طلایی و تحلیل چرخه
# ==============================================================================
def golden_spiral_r(theta, r0, growth_per_quarter_turn=PHI):
    k = np.log(growth_per_quarter_turn) / (np.pi / 2.0)
    return r0 * np.exp(k * theta)


def xy_from_idx(idx, level_index, dtheta, r0, alternate_dir):
    direction = -1.0 if (alternate_dir and level_index % 2 == 1) else 1.0
    theta_growth = idx * dtheta
    theta_pos = direction * theta_growth
    r = golden_spiral_r(theta_growth, r0)
    return r * np.cos(theta_pos), r * np.sin(theta_pos)


def transform_xy(x_rel, y_rel, anchor, rotation):
    c, s = np.cos(rotation), np.sin(rotation)
    x_abs = anchor[0] + (x_rel * c - y_rel * s)
    y_abs = anchor[1] + (x_rel * s + y_rel * c)
    return x_abs, y_abs


def find_swing_extrema(df, left=2, right=2):
    n = len(df)
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    idxs = []
    for i in range(left, n - right):
        wh = high[i - left:i + right + 1]
        wl = low[i - left:i + right + 1]
        if high[i] == wh.max() and np.argmax(wh) == left:
            idxs.append(i)
        elif low[i] == wl.min() and np.argmin(wl) == left:
            idxs.append(i)
    return sorted(set(idxs))


def phase_stats(idx_list, dtheta, n_buckets=8):
    if not idx_list: return None
    theta_growth = np.asarray(idx_list, dtype=float) * dtheta
    phase = np.mod(theta_growth, 2 * np.pi)
    edges = np.linspace(0, 2 * np.pi, n_buckets + 1)
    counts, _ = np.histogram(phase, bins=edges)
    total = int(counts.sum())
    expected = total / n_buckets if n_buckets else 0.0
    if expected > 0:
        z = (counts - expected) / np.sqrt(expected * (1.0 - 1.0 / n_buckets) + 1e-9)
    else:
        z = np.zeros(n_buckets)
    return dict(edges=edges, counts=counts, expected=expected, z=z, total=total, n_buckets=n_buckets)


def confidence_label(z, total):
    if total < 12: return "نمونه کم"
    if z >= 2.5: return "قوی 🔥"
    if z >= 1.5: return "متوسط ⚡"
    return "ضعیف"


def flag_future_candles(n_last_idx, dtheta, pstat, n_future, z_threshold):
    flagged = []
    if pstat is None: return flagged
    n_buckets = pstat["n_buckets"]
    for step in range(1, n_future + 1):
        idx = n_last_idx + step
        phase = (idx * dtheta) % (2 * np.pi)
        b = min(int(phase / (2 * np.pi) * n_buckets), n_buckets - 1)
        z = float(pstat["z"][b])
        if z >= z_threshold:
            flagged.append(dict(
                idx=idx, step=step, bucket=b, z=z,
                count=int(pstat["counts"][b]), expected=float(pstat["expected"]),
                confidence=confidence_label(z, pstat["total"]),
            ))
    return flagged


def build_chain(dfs_by_tf, order, dtheta, r0_root, scale_ratio, alternate_dir,
                fine_per_candle=8, swing_lr=2, n_buckets=8, n_future=8, z_threshold=1.0):
    anchor = (0.0, 0.0)
    rotation = 0.0
    levels_out = []

    for level_index, tf in enumerate(order):
        df = dfs_by_tf.get(tf)
        if df is None or len(df) < 2: continue

        n = len(df)
        r0 = r0_root * (scale_ratio ** level_index)
        idx_candles = np.arange(n, dtype=float)
        x_rel_c, y_rel_c = xy_from_idx(idx_candles, level_index, dtheta, r0, alternate_dir)
        x_c, y_c = transform_xy(x_rel_c, y_rel_c, anchor, rotation)

        is_up = (df["close"] >= df["open"]).to_numpy()
        vol = df["volume"].to_numpy()
        vmin, vmax = (float(vol.min()), float(vol.max())) if n else (0.0, 1.0)
        vol_norm = (vol - vmin) / (vmax - vmin + 1e-9)

        idx_fine = np.linspace(0.0, n - 1.0, num=max(60, n * fine_per_candle))
        x_rel_f, y_rel_f = xy_from_idx(idx_fine, level_index, dtheta, r0, alternate_dir)
        x_f, y_f = transform_xy(x_rel_f, y_rel_f, anchor, rotation)

        swing_left = max(1, swing_lr)
        extrema_idx = find_swing_extrema(df, left=swing_left, right=swing_left)
        pstat = phase_stats(extrema_idx, dtheta, n_buckets=n_buckets)
        flagged = flag_future_candles(n - 1, dtheta, pstat, n_future, z_threshold)

        idx_future_fine = np.linspace(n - 1.0, n - 1.0 + n_future, num=max(30, n_future * fine_per_candle))
        xr_ff, yr_ff = xy_from_idx(idx_future_fine, level_index, dtheta, r0, alternate_dir)
        x_ff, y_ff = transform_xy(xr_ff, yr_ff, anchor, rotation)

        for fl in flagged:
            xr, yr = xy_from_idx(np.array([fl["idx"]], dtype=float), level_index, dtheta, r0, alternate_dir)
            xa, ya = transform_xy(xr, yr, anchor, rotation)
            fl["x"], fl["y"] = float(xa[0]), float(ya[0])

        revolutions_covered = (n - 1) * dtheta / (2 * np.pi)
        levels_out.append(dict(
            tf=tf, level_index=level_index,
            x=x_c, y=y_c, is_up=is_up, vol_norm=vol_norm, ts=df["ts"].to_numpy(),
            x_fine=x_f, y_fine=y_f, x_future_fine=x_ff, y_future_fine=y_ff,
            anchor_from=anchor, extrema_idx=extrema_idx, pstat=pstat, flagged=flagged,
            revolutions_covered=revolutions_covered,
        ))

        anchor = (float(x_c[-1]), float(y_c[-1]))
        if len(x_c) >= 2:
            rotation = float(np.arctan2(y_c[-1] - y_c[-2], x_c[-1] - x_c[-2]))

    return levels_out


# ==============================================================================
# 3) پایگاه داده سیگنال‌ها
# ==============================================================================
class SpiralDatabase:
    def __init__(self, db_path="spiral_signals.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL, symbol TEXT NOT NULL, tf TEXT NOT NULL,
                    current_price REAL, phase_deg REAL, z_score REAL,
                    confidence TEXT, target_step INTEGER, status TEXT DEFAULT 'OPEN',
                    outcome TEXT, notes TEXT
                )
            ''')

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def insert_signal(self, symbol, tf, current_price, phase_deg, z_score, confidence, target_step, notes=""):
        with self._lock, self._get_conn() as conn:
            # جلوگیری از ثبت سیگنال تکراری برای یک نماد و تایم فریم در ۴ ساعت گذشته
            cursor = conn.execute('''
                SELECT id FROM signals WHERE symbol=? AND tf=? AND julianday('now') - julianday(timestamp) < 0.16
            ''', (symbol, tf))
            if cursor.fetchone(): return None

            cursor = conn.execute('''
                INSERT INTO signals (timestamp, symbol, tf, current_price, phase_deg, z_score, confidence, target_step, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
            datetime.now().isoformat(), symbol, tf, current_price, phase_deg, z_score, confidence, target_step, notes))
            return cursor.lastrowid

    def get_all_signals(self, limit=100):
        with self._get_conn() as conn:
            return pd.read_sql_query('SELECT * FROM signals ORDER BY id DESC LIMIT ?', conn, params=(limit,))

    def get_stats(self):
        df = self.get_all_signals(500)
        if df.empty: return {'total': 0, 'open': 0, 'avg_z': 0, 'by_symbol': pd.DataFrame()}
        by_sym = df.groupby('symbol').agg(
            total=('id', 'count'), avg_z=('z_score', 'mean'), max_z=('z_score', 'max')
        ).reset_index()
        return {
            'total': len(df), 'open': len(df[df['status'] == 'OPEN']),
            'avg_z': df['z_score'].mean(), 'by_symbol': by_sym
        }


signal_db = SpiralDatabase()


# ==============================================================================
# 4) اسکنر زنده ۱۰ ارز
# ==============================================================================
class SpiralScanner:
    def __init__(self, db):
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
                    time.sleep(300)  # اسکن هر ۵ دقیقه
                except Exception as e:
                    print(f"❌ خطای اسکنر: {e}")
                    time.sleep(60)

        threading.Thread(target=worker, daemon=True).start()

    def _scan_symbol(self, symbol):
        try:
            dfs = {}
            for tf in ['60', '240']:  # 1H and 4H
                df = get_klines(symbol, tf, limit=60)
                if not df.empty: dfs[tf] = df
            if not dfs: return None

            dtheta = 2 * np.pi / 13
            levels = build_chain(dfs, list(dfs.keys()), dtheta, R0_ROOT, 0.382, True,
                                 swing_lr=2, n_buckets=8, n_future=5, z_threshold=1.5)

            res = {'symbol': symbol, 'signals': [], 'phases': {}}
            for lv in levels:
                tf = lv['tf']
                pstat = lv['pstat']
                if pstat and pstat['total'] > 5:
                    hot_b = np.argmax(pstat['z'])
                    res['phases'][tf] = {
                        'deg': (pstat['edges'][hot_b] + pstat['edges'][hot_b + 1]) / 2 * 180 / np.pi,
                        'z': pstat['z'][hot_b]
                    }

                for fl in lv['flagged']:
                    if fl['z'] >= 2.0 and fl['step'] <= 3:
                        self.db.insert_signal(
                            symbol=symbol, tf=tf,
                            current_price=float(dfs[tf]['close'].iloc[-1]),
                            phase_deg=fl['bucket'] * 45,
                            z_score=fl['z'], confidence=fl['confidence'], target_step=fl['step']
                        )
                        res['signals'].append(fl)
            return res
        except Exception as e:
            return None

    def _scan_all(self):
        self.scan_running = True
        for sym in SCAN_SYMBOLS:
            r = self._scan_symbol(sym)
            if r:
                with self._lock: self.last_results[sym] = r
            time.sleep(1)
        self.scan_running = False
        self.last_scan_time = datetime.now()

    def get_results(self):
        with self._lock: return self.last_results.copy()


scanner = SpiralScanner(signal_db)


# ==============================================================================
# 5) نمودار Plotly و پنل چرخه
# ==============================================================================
def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgba(hex_color, alpha):
    r, g, b = _hex_to_rgb(hex_color)
    return f"rgba({r},{g},{b},{alpha:.3f})"


def add_phi_guide_rings(fig, n_rings=6):
    theta = np.linspace(0, 2 * np.pi, 120)
    for k in range(1, n_rings + 1):
        r = R0_ROOT * (PHI ** (k - 2))
        fig.add_trace(go.Scatter(
            x=r * np.cos(theta), y=r * np.sin(theta), mode="lines",
            line=dict(color=_rgba(GOLD, 0.10), width=1, dash="dot"),
            hoverinfo="skip", showlegend=False,
        ))


def build_figure(levels, symbol):
    fig = go.Figure()
    if not levels:
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', uirevision=UIREV,
                          font=dict(family="Vazirmatn, sans-serif", color=TXT),
                          annotations=[dict(text="داده‌ای برای رسم موجود نیست.", x=0.5, y=0.5, showarrow=False,
                                            font=dict(color=DN, size=14))])
        return fig

    add_phi_guide_rings(fig)
    n_chunks, op_lo, op_hi, w_lo, w_hi = 14, 0.10, 0.95, 1.1, 3.4

    for lv in levels:
        x, y, is_up, vol_norm, tf = lv["x"], lv["y"], lv["is_up"], lv["vol_norm"], lv["tf"]
        xf, yf = lv["x_fine"], lv["y_fine"]
        level_color = LEVEL_COLORS[lv["level_index"] % len(LEVEL_COLORS)]

        ax, ay = lv["anchor_from"]
        fig.add_trace(go.Scatter(x=[ax, xf[0]], y=[ay, yf[0]], mode="lines",
                                 line=dict(color=_rgba(MUT, 0.5), width=1, dash="dot"), hoverinfo="skip",
                                 showlegend=False))

        n_pts = len(xf)
        edges = np.linspace(0, n_pts - 1, n_chunks + 1).astype(int)
        for ci in range(n_chunks):
            a, b = edges[ci], edges[ci + 1]
            if b <= a: continue
            b = min(b + 1, n_pts - 1)
            frac = (ci + 1) / n_chunks
            fig.add_trace(go.Scatter(x=xf[a:b + 1], y=yf[a:b + 1], mode="lines",
                                     line=dict(color=_rgba(level_color, op_lo + (op_hi - op_lo) * frac),
                                               width=w_lo + (w_hi - w_lo) * frac),
                                     hoverinfo="skip", showlegend=False))

        fig.add_trace(go.Scatter(x=lv["x_future_fine"], y=lv["y_future_fine"], mode="lines",
                                 line=dict(color=_rgba(level_color, 0.45), width=1.4, dash="dash"), hoverinfo="skip",
                                 showlegend=False))

        if lv["extrema_idx"]:
            ex = np.array(lv["extrema_idx"])
            fig.add_trace(go.Scatter(x=x[ex], y=y[ex], mode="markers",
                                     marker=dict(color="rgba(0,0,0,0)", size=13,
                                                 line=dict(color=_rgba(TXT, 0.6), width=1.3), symbol="circle-open"),
                                     hoverinfo="skip", showlegend=False))

        marker_colors = np.where(is_up, UP, DN)
        marker_sizes = 5 + 14 * vol_norm
        fig.add_trace(go.Scatter(x=x, y=y, mode="markers",
                                 marker=dict(color=marker_colors, size=marker_sizes,
                                             line=dict(color=_rgba(BG_MAIN, 0.9), width=0.8), opacity=0.95),
                                 hovertext=[f"{TF_LABELS.get(tf, tf)} | {pd.Timestamp(t).strftime('%Y-%m-%d %H:%M')}"
                                            for t in lv["ts"]],
                                 hoverinfo="text", showlegend=False))

        for glow_size, glow_op in [(46, 0.10), (30, 0.18), (18, 0.30)]:
            fig.add_trace(go.Scatter(x=[x[-1]], y=[y[-1]], mode="markers",
                                     marker=dict(color=level_color, size=glow_size, opacity=glow_op), hoverinfo="skip",
                                     showlegend=False))

        fig.add_trace(go.Scatter(x=[x[-1]], y=[y[-1]], mode="markers+text",
                                 marker=dict(color=GOLD, size=12, line=dict(color=TXT, width=1.4), symbol="diamond"),
                                 text=[f"  {TF_LABELS.get(tf, tf)}"], textposition="middle right",
                                 textfont=dict(color=level_color, size=13, family="Vazirmatn, Arial Black"),
                                 hovertext=f"{TF_LABELS.get(tf, tf)} — آخرین کندل", hoverinfo="text", showlegend=False))

        for fl in lv["flagged"]:
            z_clip = float(np.clip(fl["z"], 0, 3.0))
            base_size = 12 + 6 * (z_clip / 3.0)
            for gs, go_op in [(base_size + 18, 0.12), (base_size + 9, 0.20)]:
                fig.add_trace(go.Scatter(x=[fl["x"]], y=[fl["y"]], mode="markers",
                                         marker=dict(color=WARN, size=gs, opacity=go_op), hoverinfo="skip",
                                         showlegend=False))
            fig.add_trace(go.Scatter(x=[fl["x"]], y=[fl["y"]], mode="markers+text",
                                     marker=dict(color=WARN, size=base_size, symbol="diamond-wide",
                                                 line=dict(color=TXT, width=1)),
                                     text=["⚠"], textposition="middle center", textfont=dict(size=10, color=BG_MAIN),
                                     hovertext=(
                                         f"{TF_LABELS.get(tf, tf)} — ناحیه‌ی احتمالیِ بازگشت (+{fl['step']} کندل)<br>z≈{fl['z']:.2f} | {fl['confidence']}"),
                                     hoverinfo="text", showlegend=False))

    fig.update_layout(uirevision=UIREV, template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='rgba(0,0,0,0)',
                      font=dict(family="Vazirmatn, sans-serif", color=TXT),
                      xaxis=dict(visible=False, scaleanchor="y", scaleratio=1), yaxis=dict(visible=False),
                      margin=dict(l=10, r=10, t=40, b=10), height=750)
    return fig


def build_cycle_panel(levels):
    if not levels: return html.Div("داده‌ای برای تحلیل موجود نیست.",
                                   style={'textAlign': 'center', 'color': '#8892b0', 'padding': '20px'})
    cards = []
    cards.append(html.Div([
        html.P("⚠️ این تحلیل، خوشه‌بندی آماری سبکی از فاز زاویه‌ای بازگشت‌های تاریخی روی اسپیرال است.",
               style={'color': '#ffd700', 'fontSize': '12px', 'margin': '0', 'fontWeight': '600'})
    ], style={'background': 'rgba(255, 215, 0, 0.08)', 'border': '1px solid rgba(255, 215, 0, 0.3)',
              'borderRadius': '12px', 'padding': '12px', 'marginBottom': '15px'}))

    for lv in levels:
        tf_label = TF_LABELS.get(lv["tf"], lv["tf"])
        level_color = LEVEL_COLORS[lv["level_index"] % len(LEVEL_COLORS)]
        pstat = lv["pstat"]
        flagged = lv["flagged"]
        body = [html.Div(f"🔁 تایم‌فریم {tf_label}",
                         style={'color': level_color, 'fontWeight': '900', 'fontSize': '16px', 'marginBottom': '8px',
                                'borderBottom': f'1px solid {level_color}40', 'paddingBottom': '5px'})]

        if pstat is None or pstat["total"] == 0:
            body.append(html.Div("نقطه بازگشتی کافی یافت نشد.", style={'color': '#8892b0', 'fontSize': '12px'}))
        else:
            order_b = np.argsort(-pstat["z"])[:2]
            for b in order_b:
                z = pstat["z"][b]
                deg = (pstat["edges"][b] + pstat["edges"][b + 1]) / 2 * 180 / np.pi
                z_color = '#00ff88' if z >= 1.5 else ('#ffd700' if z >= 1.0 else '#8892b0')
                body.append(html.Div([
                    html.Span(f"🔥 فاز داغ ~{deg:.0f}° ", style={'color': z_color, 'fontWeight': '700'}),
                    html.Span(f"| مشاهده {int(pstat['counts'][b])} / انتظار {pstat['expected']:.1f}",
                              style={'color': '#e0e0e0', 'fontSize': '11px'}),
                    html.Span(f" (z≈{z:.2f})", style={'color': z_color, 'fontSize': '11px', 'fontWeight': '700'})
                ], style={'marginBottom': '6px', 'background': 'rgba(255,255,255,0.03)', 'padding': '6px',
                          'borderRadius': '8px'}))

            if flagged:
                body.append(html.Div("⚠️ نواحی احتمالی بازگشت پیش‌رو:",
                                     style={'color': '#ff8c00', 'fontSize': '13px', 'fontWeight': '700',
                                            'marginTop': '10px', 'marginBottom': '5px'}))
                for fl in flagged:
                    body.append(html.Div([
                        html.Span(f"• +{fl['step']} کندل ", style={'fontWeight': '700'}),
                        html.Span(f"| z≈{fl['z']:.2f} ", style={'color': '#ffd700'}),
                        html.Span(f"| {fl['confidence']}", style={'color': '#8892b0', 'fontSize': '11px'})
                    ], style={'fontSize': '12px', 'color': '#e0e0e0', 'padding': '4px 0'}))
        cards.append(html.Div(body, className="glass-card",
                              style={'marginBottom': '12px', 'borderRight': f'3px solid {level_color}',
                                     'padding': '15px'}))
    return html.Div(cards)


# ==============================================================================
# 6) Layout و رابط کاربری (UI)
# ==============================================================================
CATEGORY_OPTS = [{"label": v, "value": v} for v in ["linear", "spot", "inverse"]]
TF_CHECK_OPTS = [{"label": TF_LABELS[tf], "value": tf} for tf in ALL_TF_ORDER]

tab1_content = html.Div([
    html.Div([
        html.Div([html.Label("🎯 نماد:"), dcc.Input(id='symbol-input', value=DEFAULT_SYMBOL, type='text',
                                                    style={'width': '140px', 'backgroundColor': '#0a0e27',
                                                           'color': '#fff', 'border': '1px solid #00d4aa',
                                                           'borderRadius': '10px', 'padding': '10px',
                                                           'fontWeight': '700'})], className="control-item"),
        html.Div([html.Label("📊 بازار:"),
                  dcc.Dropdown(id='category-dropdown', value=DEFAULT_CATEGORY, options=CATEGORY_OPTS, clearable=False,
                               style={'width': '140px', 'backgroundColor': '#0a0e27', 'color': '#000'})],
                 className="control-item"),
        html.Div([html.Label("🕯️ تعداد کندل:"),
                  dcc.Input(id='ncandles-input', type='number', value=55, min=21, max=144, step=1,
                            style={'width': '100px', 'backgroundColor': '#0a0e27', 'color': '#fff',
                                   'border': '1px solid #ffd700', 'borderRadius': '10px', 'padding': '10px'})],
                 className="control-item"),
        html.Div([html.Label("🔄 کندل در هر دور:"),
                  dcc.Input(id='dtheta-input', type='number', value=13, min=5, max=34, step=1,
                            style={'width': '100px', 'backgroundColor': '#0a0e27', 'color': '#fff',
                                   'border': '1px solid #ffd700', 'borderRadius': '10px', 'padding': '10px'})],
                 className="control-item"),
        html.Div([html.Label("📐 نسبت مقیاس:"),
                  dcc.Input(id='scale-input', type='number', value=0.382, min=0.15, max=0.7, step=0.01,
                            style={'width': '100px', 'backgroundColor': '#0a0e27', 'color': '#fff',
                                   'border': '1px solid #00d4aa', 'borderRadius': '10px', 'padding': '10px'})],
                 className="control-item"),
        html.Button('🔄 بروزرسانی', id='refresh-btn', n_clicks=0, className="refresh-btn"),
    ], className="control-panel"),
    html.Div([
        html.Div([
            html.Label("⏱️ زنجیره تایم‌فریم‌ها:"),
            dcc.Checklist(id='tf-checklist', options=TF_CHECK_OPTS, value=DEFAULT_CHAIN, inline=True,
                          className='tf-checklist')
        ], style={'flex': '2', 'minWidth': '300px'}),
        html.Div([html.Label("🔍 پنجره سوینگ:"),
                  dcc.Input(id='swing-input', type='number', value=2, min=1, max=5, step=1,
                            style={'width': '80px', 'backgroundColor': '#0a0e27', 'color': '#fff',
                                   'border': '1px solid #bb86fc', 'borderRadius': '8px', 'padding': '8px',
                                   'textAlign': 'center'})], className="control-item"),
        html.Div([html.Label("📊 باکت فاز:"),
                  dcc.Input(id='buckets-input', type='number', value=8, min=4, max=16, step=1,
                            style={'width': '80px', 'backgroundColor': '#0a0e27', 'color': '#fff',
                                   'border': '1px solid #bb86fc', 'borderRadius': '8px', 'padding': '8px',
                                   'textAlign': 'center'})], className="control-item"),
        html.Div([html.Label("🔮 کندل آینده:"),
                  dcc.Input(id='future-input', type='number', value=8, min=1, max=21, step=1,
                            style={'width': '80px', 'backgroundColor': '#0a0e27', 'color': '#fff',
                                   'border': '1px solid #bb86fc', 'borderRadius': '8px', 'padding': '8px',
                                   'textAlign': 'center'})], className="control-item"),
        html.Div([html.Label("⚡ آستانه Z:"),
                  dcc.Input(id='zthresh-input', type='number', value=1.0, min=0.5, max=3.0, step=0.1,
                            style={'width': '80px', 'backgroundColor': '#0a0e27', 'color': '#fff',
                                   'border': '1px solid #bb86fc', 'borderRadius': '8px', 'padding': '8px',
                                   'textAlign': 'center'})], className="control-item"),
    ], className="control-panel", style={'alignItems': 'center'}),
    html.Div([
        html.Div([
            html.Div([html.H3("🌀 نمودار زنجیره اسپیرال طلایی")], className="section-title"),
            html.Div([dcc.Graph(id='spiral-chart', config={"displaylogo": False, "scrollZoom": True})],
                     className="glass-card", style={'padding': '10px'}),
        ], style={'width': '68%', 'display': 'inline-block', 'verticalAlign': 'top', 'marginRight': '1%'}),
        html.Div([
            html.Div([html.H3("📈 تحلیل چرخه و نواحی بازگشت")], className="section-title",
                     style={'borderRightColor': '#ffd700'}),
            html.Div(id='cycle-panel', style={'maxHeight': '750px', 'overflowY': 'auto', 'paddingRight': '5px'}),
        ], style={'width': '30%', 'display': 'inline-block', 'verticalAlign': 'top'}),
    ], style={'marginBottom': '20px'})
])

tab2_content = html.Div([
    html.Div([html.H3("🛰️ اسکنر زنده فازهای اسپیرال")], className="section-title",
             style={'borderRightColor': '#ffd700'}),
    html.P("🔍 اسکن خودکار ۱۰ ارز برای یافتن نواحی داغ بازگشتی (Z-Score بالا)",
           style={'color': '#8892b0', 'margin': '0 0 15px 0', 'padding': '0 20px'}),
    html.Div(id='scanner-status-bar', style={'marginBottom': '15px'}),
    html.Div(id='scanner-active-signals', style={'marginBottom': '25px'}),
    html.Div([
        html.Div([html.H3("📊 نمای کلی فازهای داغ")], className="section-title"),
        html.Div(id='scanner-grid', className="scanner-grid"),
    ], style={'marginBottom': '25px'}),
])

tab3_content = html.Div([
    html.Div([html.H3("📊 آمار عملکرد پیش‌بینی فازها")], className="section-title",
             style={'borderRightColor': '#bb86fc'}),
    html.Div(id='stats-summary-cards', style={'marginBottom': '20px', 'textAlign': 'center'}),
    html.Div([
        html.Div([html.H3("📋 تاریخچه سیگنال‌های فاز")], className="section-title"),
        html.Div([html.Div(id='stats-history-table', style={'overflowX': 'auto'})], className="glass-card"),
    ], style={'marginBottom': '20px'}),
])

app.layout = html.Div([
    html.Div([
        html.Div([
            html.Span("🌙", className="banner-logo"),
            html.Div([html.H2("به کانال BITMOON618 بپیوندید!"),
                      html.P("تحلیل‌های هندسی کریپتو | اسپیرال طلایی | آموزش رایگان")], className="banner-text"),
        ], className="banner-left"),
        html.A([html.Span("📢"), html.Span("عضویت در کانال")], href="https://t.me/BITMOON618", target="_blank",
               className="banner-btn"),
    ], className="bitmoon-banner"),
    html.Div([
        html.H1("🌀 سیستم جامع تحلیل اسپیرال طلایی و چرخه‌های زمانی"),
        html.P("زنجیره هندسی تایم‌فریم‌ها + اسکنر زنده + پایگاه داده | نسخه حرفه‌ای v5.0",
               style={'color': '#8892b0', 'margin': '8px 0 0 0', 'fontSize': '14px'}),
        html.Div(id='connection-indicator', style={'marginTop': '10px'}),
    ], className="main-header"),
    dcc.Tabs(id='main-tabs', value='tab-analysis', className='custom-tabs', children=[
        dcc.Tab(label='🌀 تحلیل تک نماد', value='tab-analysis', className='custom-tab',
                selected_className='custom-tab--selected'),
        dcc.Tab(label='🛰️ اسکنر ۱۰ ارز', value='tab-scanner', className='custom-tab',
                selected_className='custom-tab--selected'),
        dcc.Tab(label='📊 پایگاه داده و آمار', value='tab-stats', className='custom-tab',
                selected_className='custom-tab--selected'),
    ]),
    html.Div(tab1_content, id='tab-1-wrapper'),
    html.Div(tab2_content, id='tab-2-wrapper', style={'display': 'none'}),
    html.Div(tab3_content, id='tab-3-wrapper', style={'display': 'none'}),
    html.Div([html.P("💎 ساخته شده با ❤️ برای تریدرهای حرفه‌ای | BITMOON618",
                     style={'color': '#8892b0', 'textAlign': 'center', 'margin': '0', 'fontSize': '14px'})],
             style={'padding': '20px', 'marginTop': '30px'}),
    dcc.Interval(id='auto-refresh', interval=60000, n_intervals=0),
    dcc.Interval(id='scanner-refresh', interval=30000, n_intervals=0),
    dcc.Interval(id='stats-refresh', interval=15000, n_intervals=0),
], style={'backgroundColor': '#0a0e27', 'padding': '20px', 'minHeight': '100vh'})


# ==============================================================================
# 7) کال‌بک‌ها
# ==============================================================================
@app.callback([Output('tab-1-wrapper', 'style'), Output('tab-2-wrapper', 'style'), Output('tab-3-wrapper', 'style')],
              Input('main-tabs', 'value'))
def switch_tab(t):
    h, s = {'display': 'none'}, {}
    if t == 'tab-analysis':
        return s, h, h
    elif t == 'tab-scanner':
        return h, s, h
    elif t == 'tab-stats':
        return h, h, s
    return s, h, h


@app.callback(Output('connection-indicator', 'children'), Input('auto-refresh', 'n_intervals'),
              Input('refresh-btn', 'n_clicks'), prevent_initial_call=False)
def update_connection_indicator(h, r):
    d = bybit_get("/v5/market/tickers", {"category": "linear", "symbol": "BTCUSDT"}, timeout=5)
    ep = _ACTIVE_REST_BASE["url"] or "-"
    if d and d.get("retCode") == 0:
        try:
            price = float(d['result']['list'][0]['lastPrice'])
            return html.Div([html.Span("🟢 متصل", className="connection-status status-ok"),
                             html.Span(f"💰 BTC: ${price:,.2f}  |  🌐 Endpoint: {ep}",
                                       style={'color': '#8892b0', 'fontSize': '13px', 'fontWeight': '600'})])
        except:
            pass
    return html.Div([html.Span("🔴 قطع", className="connection-status status-err"),
                     html.Span(f"  خطا در اتصال به بایبیت", style={'color': '#ff8c8c', 'fontSize': '12px'})])


@app.callback([Output('spiral-chart', 'figure'), Output('cycle-panel', 'children')],
              [Input('refresh-btn', 'n_clicks'), Input('auto-refresh', 'n_intervals')],
              [State('symbol-input', 'value'), State('category-dropdown', 'value'), State('tf-checklist', 'value'),
               State('ncandles-input', 'value'),
               State('dtheta-input', 'value'), State('scale-input', 'value'), State('swing-input', 'value'),
               State('buckets-input', 'value'),
               State('future-input', 'value'), State('zthresh-input', 'value')])
def update_dashboard(nc, ni, symbol, category, tf_selected, n_candles, candles_per_turn, scale_ratio, swing_lr,
                     n_buckets, n_future, z_threshold):
    symbol, category = (symbol or DEFAULT_SYMBOL).upper(), category or DEFAULT_CATEGORY
    n_candles, candles_per_turn = int(n_candles or 55), float(candles_per_turn or 13)
    scale_ratio, swing_lr = float(scale_ratio or 0.382), int(swing_lr or 2)
    n_buckets, n_future, z_threshold = int(n_buckets or 8), int(n_future or 8), float(z_threshold or 1.0)
    order = [tf for tf in ALL_TF_ORDER if tf in (tf_selected or [])] or list(DEFAULT_CHAIN)
    dfs = {}
    for tf in order:
        df = get_klines(symbol, tf, category, limit=n_candles + 5)
        if not df.empty:
            df = df.iloc[:-1] if len(df) > 2 else df
            dfs[tf] = df.tail(n_candles).reset_index(drop=True)
    order = [tf for tf in order if tf in dfs]
    if not order:
        return go.Figure(layout=dict(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', annotations=[
            dict(text="❌ دریافت دیتا ناموفق.", x=0.5, y=0.5, showarrow=False,
                 font=dict(color=DN, size=14))])), html.Div("داده‌ای موجود نیست.", className="error-message")

    dtheta = 2 * np.pi / candles_per_turn
    levels = build_chain(dfs, order, dtheta, R0_ROOT, scale_ratio, True, swing_lr=swing_lr, n_buckets=n_buckets,
                         n_future=n_future, z_threshold=z_threshold)
    return build_figure(levels, symbol), build_cycle_panel(levels)


@app.callback([Output('scanner-status-bar', 'children'), Output('scanner-active-signals', 'children'),
               Output('scanner-grid', 'children')], Input('scanner-refresh', 'n_intervals'))
def update_scanner(n):
    results = scanner.get_results()
    status = f"📡 آخرین اسکن: {scanner.last_scan_time.strftime('%H:%M:%S') if scanner.last_scan_time else 'در حال اسکن...'} | 🔄 وضعیت: {'در حال اسکن' if scanner.scan_running else 'آماده'}"
    sb = html.Div([html.Span(status, style={'color': '#00ff88', 'fontWeight': '700'})], className="glass-card",
                  style={'padding': '15px'})

    df = signal_db.get_all_signals(20)
    open_df = df[df['status'] == 'OPEN']
    if not open_df.empty:
        rows = []
        for _, r in open_df.iterrows():
            rows.append(html.Tr([
                html.Td(pd.to_datetime(r['timestamp']).strftime('%m-%d %H:%M')),
                html.Td(html.Span(r['symbol'], style={'fontWeight': '900', 'color': '#ffd700'})),
                html.Td(TF_LABELS.get(r['tf'], r['tf'])),
                html.Td(f"${r['current_price']:,.2f}"),
                html.Td(f"{r['phase_deg']:.0f}°"),
                html.Td(f"{r['z_score']:.2f}", style={'color': '#00ff88', 'fontWeight': '700'}),
                html.Td(r['confidence']),
                html.Td(f"+{r['target_step']} کندل"),
                html.Td(html.Span("⏳ فعال", className="badge-open")),
            ]))
        sig_table = html.Div([html.Div([html.H3("⚡ سیگنال‌های فعال بازگشتی")], className="section-title",
                                       style={'borderRightColor': '#ff8c00'}), html.Div([html.Table([html.Thead(html.Tr(
            [html.Th('زمان'), html.Th('نماد'), html.Th('TF'), html.Th('قیمت'), html.Th('فاز'), html.Th('Z-Score'),
             html.Th('اطمینان'), html.Th('هدف'), html.Th('وضعیت')])), html.Tbody(rows)], className="signals-table")],
                                                                                        className="glass-card")],
                             style={'marginBottom': '20px'})
    else:
        sig_table = html.Div([html.Div([html.H3("⚡ سیگنال‌های فعال")], className="section-title"), html.Div([html.P(
            "در حال حاضر سیگنال فعالی ثبت نشده است.",
            style={'textAlign': 'center', 'color': '#8892b0', 'padding': '20px'})], className="glass-card")],
                             style={'marginBottom': '20px'})

    cards = []
    for sym in SCAN_SYMBOLS:
        r = results.get(sym)
        if not r:
            cards.append(html.Div([html.Div(sym, className="scanner-sym", style={'color': '#555'}),
                                   html.Div("⏳ در انتظار...", className="scanner-price")], className="scanner-card"))
            continue

        max_z, hot_tf = 0, "-"
        for tf, pdata in r['phases'].items():
            if pdata['z'] > max_z: max_z, hot_tf = pdata['z'], tf

        z_color = '#00ff88' if max_z >= 2.0 else ('#ffd700' if max_z >= 1.5 else '#8892b0')
        cards.append(html.Div([
            html.Div(sym, className="scanner-sym"),
            html.Div(f"داغ‌ترین فاز در {TF_LABELS.get(hot_tf, hot_tf)}", className="scanner-price"),
            html.Div(f"Z-Score: {max_z:.2f}",
                     style={'color': z_color, 'fontWeight': '900', 'fontSize': '16px', 'marginBottom': '8px'}),
            html.Div(className="progress-bar",
                     children=[html.Div(className="progress-fill", style={'width': f'{min(max_z * 30, 100)}%'})])
        ], className="scanner-card"))
    return sb, sig_table, cards


@app.callback([Output('stats-summary-cards', 'children'), Output('stats-history-table', 'children')],
              Input('stats-refresh', 'n_intervals'))
def update_stats(n):
    stats = signal_db.get_stats()
    cards = html.Div([
        html.Div([html.Div("📊 کل سیگنال‌ها", style={'fontSize': '13px', 'color': '#8892b0'}),
                  html.Div(f"{stats['total']}",
                           style={'fontSize': '28px', 'color': '#fff', 'fontWeight': '900', 'marginTop': '8px'})],
                 className="summary-card"),
        html.Div([html.Div("⏳ سیگنال‌های باز", style={'fontSize': '13px', 'color': '#8892b0'}),
                  html.Div(f"{stats['open']}",
                           style={'fontSize': '28px', 'color': '#ffd700', 'fontWeight': '900', 'marginTop': '8px'})],
                 className="summary-card"),
        html.Div([html.Div("⚡ میانگین Z-Score", style={'fontSize': '13px', 'color': '#8892b0'}),
                  html.Div(f"{stats['avg_z']:.2f}",
                           style={'fontSize': '28px', 'color': '#00ff88', 'fontWeight': '900', 'marginTop': '8px'})],
                 className="summary-card"),
    ])

    df = signal_db.get_all_signals(50)
    if not df.empty:
        rows = []
        for _, r in df.iterrows():
            rows.append(html.Tr([
                html.Td(pd.to_datetime(r['timestamp']).strftime('%m-%d %H:%M')),
                html.Td(html.Span(r['symbol'], style={'fontWeight': '900', 'color': '#ffd700'})),
                html.Td(TF_LABELS.get(r['tf'], r['tf'])),
                html.Td(f"{r['phase_deg']:.0f}°"),
                html.Td(f"{r['z_score']:.2f}", style={'color': '#00ff88', 'fontWeight': '700'}),
                html.Td(r['confidence']),
                html.Td(html.Span(r['status'], className=f"badge-{r['status'].lower()}")),
            ]))
        table = html.Table([html.Thead(html.Tr(
            [html.Th('زمان'), html.Th('نماد'), html.Th('TF'), html.Th('فاز'), html.Th('Z-Score'), html.Th('اطمینان'),
             html.Th('وضعیت')])), html.Tbody(rows)], className="signals-table")
    else:
        table = html.Div("هنوز سیگنالی ثبت نشده است...",
                         style={'textAlign': 'center', 'color': '#8892b0', 'padding': '30px'})
    return cards, table


# ==============================================================================
# 8) اجرا و باز کردن خودکار مرورگر
# ==============================================================================
def open_browser():
    try:
        webbrowser.open_new("http://127.0.0.1:8061")
        print("🌐 مرورگر باز شد: http://127.0.0.1:8061")
    except Exception as e:
        print(f"⚠️ خطا در باز کردن مرورگر: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Starting BITMOON618 Golden Spiral v5.0 Pro (Full System)")
    print("=" * 60)

    # فقط در پروسه اصلی اجرا می‌شود (نه reloader)
    if not os.environ.get('WERKZEUG_RUN_MAIN'):
        Timer(1.5, open_browser).start()

    app.run(debug=True, host="127.0.0.1", port=8061, use_reloader=False)