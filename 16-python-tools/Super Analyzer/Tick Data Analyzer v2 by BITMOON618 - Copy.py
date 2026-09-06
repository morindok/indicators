import dash
from dash import dcc, html, Input, Output, State, callback_context, no_update
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import requests
import time
import urllib3
import os
from datetime import datetime, timedelta
import json
import threading
import sqlite3
import webbrowser
from threading import Timer
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== تنظیمات ====================
SCAN_SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
    'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'DOTUSDT', 'LINKUSDT',
    'MATICUSDT', 'UNIUSDT', 'LTCUSDT', 'ATOMUSDT', 'ETCUSDT',
    'XLMUSDT', 'ALGOUSDT', 'VETUSDT', 'FILUSDT', 'APTUSDT', 'ARBUSDT'
]

TOTAL_CAPITAL = 500.0
RISK_PER_TRADE = 0.02
COMMISSION_RATE = 0.0006
MIN_FREE_MARGIN = 5.0

# ==================== CSS ====================
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
.glass-card { background: linear-gradient(135deg, rgba(26, 26, 46, 0.8) 0%, rgba(22, 33, 62, 0.8) 100%);
    border-radius: 18px; padding: 20px; border: 1px solid rgba(255, 255, 255, 0.1); }
.section-title { background: linear-gradient(135deg, rgba(26, 26, 46, 0.95) 0%, rgba(22, 33, 62, 0.95) 100%);
    padding: 18px 25px; border-radius: 15px; margin-bottom: 15px; border-right: 4px solid #00d4aa; }
.section-title h3 { margin: 0; color: #fff; font-size: 18px; font-weight: 700; }
.signals-table { width: 100%; border-collapse: separate; border-spacing: 0 8px; }
.signals-table thead th { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #ffd700;
    padding: 14px; font-weight: 700; text-align: center; font-size: 14px; }
.signals-table tbody tr { background: rgba(255, 255, 255, 0.03); transition: all 0.3s ease; }
.signals-table tbody tr:hover { background: rgba(0, 212, 170, 0.1); }
.signals-table tbody td { padding: 12px; text-align: center; color: #e0e0e0; font-size: 13px; }
.signal-badge { display: inline-block; padding: 6px 16px; border-radius: 20px; font-weight: 900; font-size: 12px; }
.badge-strong-buy { background: linear-gradient(135deg, #00ff88 0%, #00d4aa 100%); color: #000; animation: glowGreen 2s ease-in-out infinite; }
.badge-sell { background: linear-gradient(135deg, #ff8c00 0%, #ff6b00 100%); color: #fff; }
.badge-strong-sell { background: linear-gradient(135deg, #ff4757 0%, #c92a2a 100%); color: #fff; animation: glowRed 2s ease-in-out infinite; }
@keyframes glowGreen { 0%, 100% { box-shadow: 0 0 10px rgba(0, 255, 136, 0.5); } 50% { box-shadow: 0 0 25px rgba(0, 255, 136, 0.9); } }
@keyframes glowRed { 0%, 100% { box-shadow: 0 0 10px rgba(255, 71, 87, 0.5); } 50% { box-shadow: 0 0 25px rgba(255, 71, 87, 0.9); } }
.summary-card { background: linear-gradient(135deg, rgba(22, 33, 62, 0.9) 0%, rgba(26, 26, 46, 0.9) 100%);
    padding: 20px; border-radius: 18px; min-width: 190px; border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3); display: inline-block; margin: 6px; text-align: center; }
.data-table { width: 100%; border-collapse: separate; border-spacing: 0 6px; }
.data-table thead th { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #ffd700; padding: 12px; font-weight: 700; text-align: center; font-size: 13px; }
.data-table tbody td { padding: 10px; text-align: center; color: #e0e0e0; font-size: 12px; }
.data-table tbody tr { background: rgba(255, 255, 255, 0.03); }
.confirm-badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-weight: 700; font-size: 11px; }
.confirm-strong { background: rgba(0, 255, 136, 0.2); color: #00ff88; border: 1px solid #00ff88; }
.confirm-half { background: rgba(255, 215, 0, 0.2); color: #ffd700; border: 1px solid #ffd700; }
.confirm-none { background: rgba(255, 71, 87, 0.15); color: #ff8c8c; border: 1px solid #ff4757; }
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
.trade-params { display: inline-block; padding: 4px 10px; border-radius: 8px;
    background: rgba(255, 215, 0, 0.15); color: #ffd700; font-size: 11px; font-weight: 700; margin: 2px; }
.trade-win { color: #00ff88 !important; font-weight: 900; }
.trade-loss { color: #ff4757 !important; font-weight: 900; }
.trade-open { color: #ffd700 !important; font-weight: 900; animation: pulseGold 2s infinite; }
@keyframes pulseGold { 0%, 100% { text-shadow: 0 0 5px rgba(255,215,0,0.5); } 50% { text-shadow: 0 0 15px rgba(255,215,0,0.9); } }
.scanner-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 15px; }
.scanner-card { background: linear-gradient(135deg, rgba(26, 26, 46, 0.9) 0%, rgba(22, 33, 62, 0.9) 100%);
    border-radius: 14px; padding: 16px; border: 1px solid rgba(255, 255, 255, 0.08); transition: all 0.3s ease; }
.scanner-card:hover { transform: translateY(-3px); border-color: #00d4aa; }
.scanner-sym { font-size: 18px; font-weight: 900; color: #fff; margin-bottom: 8px; }
.scanner-price { font-size: 14px; color: #8892b0; margin-bottom: 10px; }
.progress-bar { height: 6px; background: rgba(255, 255, 255, 0.08); border-radius: 3px; overflow: hidden; margin-top: 6px; }
.progress-fill { height: 100%; background: linear-gradient(90deg, #00d4aa, #00ff88); transition: width 0.3s; }
.margin-bar { height: 20px; background: rgba(255,255,255,0.08); border-radius: 10px; overflow: hidden; margin: 8px 0; }
.margin-used { height: 100%; background: linear-gradient(90deg, #ffd700, #ff8c00); border-radius: 10px; transition: width 0.5s ease; }
.open-trade-row { background: rgba(255, 215, 0, 0.05) !important; border-right: 3px solid #ffd700 !important; }
.live-pnl-positive { color: #00ff88 !important; font-weight: 900 !important; }
.live-pnl-negative { color: #ff4757 !important; font-weight: 900 !important; }
.factor-tag { display: inline-block; padding: 2px 6px; border-radius: 6px; font-size: 10px; font-weight: 700; margin: 1px; }
.error-message { background: linear-gradient(135deg, rgba(255, 71, 87, 0.2) 0%, rgba(201, 42, 42, 0.2) 100%);
    border: 2px solid #ff4757; border-radius: 15px; padding: 30px; text-align: center; color: #fff; margin: 20px auto; max-width: 600px; }
'''

app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.title = "BITMOON618 | سیستم تحلیل تیک"
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
# 🔌 اتصال بایبیت
# ==============================================================================
class BybitAPIClient:
    REST_ENDPOINTS = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]

    def __init__(self):
        self.session = requests.Session()
        self._active_base = None
        self._lock = threading.Lock()
        self._cache = {}
        retry_strategy = Retry(total=2, backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504], allowed_methods=["GET"], raise_on_status=False)
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
        }

    def _cache_ttl(self, interval):
        try: iv = int(interval)
        except: iv = 1
        if iv <= 1: return 15
        if iv <= 5: return 30
        if iv <= 60: return 60
        return 120

    def _cache_key(self, symbol, interval, limit, end=None):
        return f"{symbol}|{interval}|{limit}|{str(end) if end else 'live'}"

    def _get_cached(self, key, interval):
        with self._lock:
            if key not in self._cache: return None
            ts, df = self._cache[key]
            if (time.time() - ts) < self._cache_ttl(interval): return df.copy()
            del self._cache[key]
            return None

    def _set_cached(self, key, df):
        with self._lock:
            self._cache[key] = (time.time(), df.copy())
            if len(self._cache) > 50:
                oldest = sorted(self._cache, key=lambda k: self._cache[k][0])[:10]
                for k in oldest: del self._cache[k]

    def _request(self, path, params, timeout=15):
        ordered = []
        if self._active_base and self._active_base in self.REST_ENDPOINTS:
            ordered.append(self._active_base)
        for ep in self.REST_ENDPOINTS:
            if ep not in ordered: ordered.append(ep)
        for base in ordered:
            for verify in (True, False):
                try:
                    r = self.session.get(f"{base}{path}", params=params,
                        headers=self.headers, timeout=timeout, verify=verify)
                    if r.status_code == 429:
                        time.sleep(min(float(r.headers.get('Retry-After', 3)), 5))
                        continue
                    if r.status_code in (403, 451): break
                    if r.status_code != 200: continue
                    try: data = r.json()
                    except: continue
                    if data.get('retCode') != 0:
                        return None, f"API: {data.get('retMsg', '?')}"
                    if base != self._active_base:
                        print(f"✅ اتصال با {base}")
                        self._active_base = base
                    return data, None
                except requests.exceptions.SSLError:
                    if verify: continue
                    break
                except requests.exceptions.Timeout: continue
                except requests.exceptions.RequestException: break
                except Exception: break
        return None, "تمام دامنه‌ها شکست خوردند"

    def get_klines(self, symbol="BTCUSDT", interval="5", limit=200, end_time=None):
        cache_key = self._cache_key(symbol, interval, limit, end_time)
        cached = self._get_cached(cache_key, interval)
        if cached is not None: return cached
        params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
        if end_time is not None:
            try: params["end"] = int(pd.Timestamp(end_time).timestamp() * 1000)
            except: pass
        data, err = self._request("/v5/market/kline", params, timeout=15)
        if data is None: return pd.DataFrame()
        if not isinstance(data, dict) or 'result' not in data: return pd.DataFrame()
        lst = data['result'].get('list') or []
        if not lst: return pd.DataFrame()
        df = pd.DataFrame(lst, columns=['startTime', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        df['startTime'] = pd.to_datetime(df['startTime'].astype(int), unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.sort_values('startTime').reset_index(drop=True)
        self._set_cached(cache_key, df)
        return df

    def get_ticker(self, symbol="BTCUSDT"):
        data, err = self._request("/v5/market/tickers",
                                  {"category": "linear", "symbol": symbol}, timeout=10)
        if data is None: return None, err
        lst = data.get('result', {}).get('list', [])
        if not lst: return None, "داده‌ای برنگشت"
        try:
            item = lst[0]
            return {
                'lastPrice': float(item.get('lastPrice', 0)),
                'bid': float(item.get('bid1Price', 0) or item.get('lastPrice', 0)),
                'ask': float(item.get('ask1Price', 0) or item.get('lastPrice', 0)),
                'spread': float(item.get('ask1Price', 0) or 0) - float(item.get('bid1Price', 0) or 0),
            }, None
        except Exception as e:
            return None, str(e)

    def test_connection(self):
        info, err = self.get_ticker("BTCUSDT")
        if info is None: return False, err, 0
        return True, None, info['lastPrice']

    @property
    def active_endpoint(self):
        return self._active_base or "-"


bybit_client = BybitAPIClient()

# ==============================================================================
# 💾 پایگاه داده
# ==============================================================================
DB_PATH = "bitmoon_signals.db"

class SignalDatabase:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL, symbol TEXT NOT NULL,
                    signal_type TEXT NOT NULL, entry_price REAL NOT NULL,
                    tp_price REAL NOT NULL, sl_price REAL NOT NULL,
                    leverage INTEGER NOT NULL, confirmation_score INTEGER,
                    atr REAL, spread REAL, commission_rate REAL,
                    risk_usd REAL DEFAULT 10.0,
                    margin_used REAL DEFAULT 0.0,
                    position_size REAL DEFAULT 0.0,
                    rr_ratio REAL DEFAULT 1.67,
                    status TEXT DEFAULT 'OPEN', exit_price REAL,
                    exit_time TEXT, outcome TEXT, pnl_percent REAL,
                    pnl_usd REAL, notes TEXT
                )
            ''')
            for col, default in [('risk_usd', '10.0'), ('margin_used', '0.0'),
                                 ('position_size', '0.0'), ('rr_ratio', '1.67')]:
                try: conn.execute(f'ALTER TABLE signals ADD COLUMN {col} REAL DEFAULT {default}')
                except: pass
            conn.execute('CREATE INDEX IF NOT EXISTS idx_symbol ON signals(symbol)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_status ON signals(status)')

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def insert_signal(self, symbol, signal_type, entry_price, tp_price, sl_price,
                     leverage, confirmation_score, atr, spread, commission_rate,
                     risk_usd=10.0, margin_used=0.0, position_size=0.0, rr_ratio=1.67, notes=""):
        with self._lock, self._get_conn() as conn:
            cursor = conn.execute('''
                INSERT INTO signals
                (timestamp, symbol, signal_type, entry_price, tp_price, sl_price,
                 leverage, confirmation_score, atr, spread, commission_rate,
                 risk_usd, margin_used, position_size, rr_ratio, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (datetime.now().isoformat(), symbol, signal_type, entry_price,
                  tp_price, sl_price, leverage, confirmation_score, atr,
                  spread, commission_rate, risk_usd, margin_used, position_size,
                  rr_ratio, notes))
            return cursor.lastrowid

    def close_signal(self, signal_id, exit_price, outcome, pnl_percent, pnl_usd):
        with self._lock, self._get_conn() as conn:
            conn.execute('''
                UPDATE signals
                SET status='CLOSED', exit_price=?, exit_time=?, outcome=?,
                    pnl_percent=?, pnl_usd=?
                WHERE id=?
            ''', (exit_price, datetime.now().isoformat(), outcome,
                  pnl_percent, pnl_usd, signal_id))

    def get_all_signals(self, limit=500):
        with self._get_conn() as conn:
            return pd.read_sql_query('SELECT * FROM signals ORDER BY id DESC LIMIT ?', conn, params=(limit,))

    def get_open_signals(self):
        with self._get_conn() as conn:
            return pd.read_sql_query('SELECT * FROM signals WHERE status="OPEN"', conn)

    def get_used_margin(self):
        open_df = self.get_open_signals()
        if open_df.empty: return 0.0
        total = 0.0
        for _, row in open_df.iterrows():
            if pd.notna(row.get('margin_used')) and row['margin_used'] > 0:
                total += float(row['margin_used'])
            else:
                risk = float(row.get('risk_usd', 10.0) or 10.0)
                entry = float(row['entry_price'])
                sl = float(row['sl_price'])
                lev = float(row['leverage'])
                if entry > 0 and lev > 0:
                    sl_pct = abs(entry - sl) / entry
                    if sl_pct > 0:
                        total += (risk / sl_pct) / lev
        return total

    def get_free_margin(self):
        used = self.get_used_margin()
        return max(0.0, TOTAL_CAPITAL - used), used

    def get_open_with_live_pnl(self, current_prices):
        df = self.get_open_signals()
        if df.empty: return df
        results = []
        for _, row in df.iterrows():
            current_price = current_prices.get(row['symbol'], row['entry_price'])
            entry = float(row['entry_price'])
            sl = float(row['sl_price'])
            lev = float(row['leverage'])
            spread = float(row['spread']) if row['spread'] else 0.0
            risk = float(row.get('risk_usd', 10.0) or 10.0)
            sl_pct = abs(entry - sl) / entry if entry > 0 else 0.01
            pos_size = risk / sl_pct if sl_pct > 0 else 0.0
            margin = pos_size / lev if lev > 0 else pos_size
            if row['signal_type'] in ('STRONG_BUY', 'BUY'):
                price_chg = (current_price - entry) / entry * 100
            else:
                price_chg = (entry - current_price) / entry * 100
            pnl_gross = pos_size * (price_chg / 100)
            spread_pct = (spread / entry * 100) if entry > 0 else 0
            total_cost = spread_pct + COMMISSION_RATE * 2 * 100
            costs = pos_size * (total_cost / 100)
            net_pnl = pnl_gross - costs
            pnl_pct_m = (net_pnl / margin * 100) if margin > 0 else 0
            if row['signal_type'] in ('STRONG_BUY', 'BUY'):
                d_tp = (row['tp_price'] - current_price) / current_price * 100 if current_price > 0 else 0
                d_sl = (current_price - sl) / current_price * 100 if current_price > 0 else 0
            else:
                d_tp = (current_price - row['tp_price']) / current_price * 100 if current_price > 0 else 0
                d_sl = (sl - current_price) / current_price * 100 if current_price > 0 else 0
            new_row = row.to_dict()
            new_row.update({
                'current_price': current_price,
                'position_size_usd': round(pos_size, 2),
                'margin_used': round(margin, 2),
                'risk_usd': round(risk, 2),
                'live_pnl_percent': round(pnl_pct_m, 2),
                'live_pnl_usd': round(net_pnl, 2),
                'dist_tp_pct': round(d_tp, 2),
                'dist_sl_pct': round(d_sl, 2),
            })
            results.append(new_row)
        return pd.DataFrame(results)

    def get_statistics(self):
        with self._get_conn() as conn:
            df = pd.read_sql_query('SELECT * FROM signals WHERE status="CLOSED"', conn)
        if df.empty:
            return {
                'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
                'total_pnl_pct': 0, 'total_pnl_usd': 0, 'avg_win': 0, 'avg_loss': 0,
                'profit_factor': 0, 'max_drawdown': 0, 'best_trade': 0, 'worst_trade': 0,
                'by_symbol': pd.DataFrame(), 'equity_curve': [TOTAL_CAPITAL]
            }
        wins = df[df['outcome'] == 'WIN']
        losses = df[df['outcome'] == 'LOSS']
        total = len(df)
        win_rate = (len(wins) / total * 100) if total > 0 else 0
        avg_win = wins['pnl_percent'].mean() if not wins.empty else 0
        avg_loss = losses['pnl_percent'].mean() if not losses.empty else 0
        gp = wins['pnl_usd'].sum() if not wins.empty else 0
        gl = abs(losses['pnl_usd'].sum()) if not losses.empty else 0
        pf = (gp / gl) if gl > 0 else 0
        df_s = df.sort_values('timestamp')
        cap = TOTAL_CAPITAL
        eq = [cap]
        for _, r in df_s.iterrows():
            cap += r['pnl_usd']
            eq.append(cap)
        ea = np.array(eq)
        peak = np.maximum.accumulate(ea)
        dd = (peak - ea) / peak * 100
        mdd = float(dd.max()) if len(dd) > 0 else 0
        bs = df.groupby('symbol').agg({
            'outcome': lambda x: (x == 'WIN').sum(),
            'pnl_usd': 'sum', 'pnl_percent': 'mean'
        }).rename(columns={'outcome': 'wins', 'pnl_usd': 'total_pnl', 'pnl_percent': 'avg_pnl'})
        bs['total_trades'] = df.groupby('symbol').size()
        bs['win_rate'] = (bs['wins'] / bs['total_trades'] * 100).round(1)
        bs = bs.reset_index()
        return {
            'total_trades': total, 'wins': len(wins), 'losses': len(losses),
            'win_rate': round(win_rate, 1), 'total_pnl_pct': round(df['pnl_percent'].sum(), 2),
            'total_pnl_usd': round(df['pnl_usd'].sum(), 2),
            'avg_win': round(float(avg_win), 2), 'avg_loss': round(float(avg_loss), 2),
            'profit_factor': round(float(pf), 2), 'max_drawdown': round(mdd, 2),
            'best_trade': round(float(df['pnl_percent'].max()), 2) if not df.empty else 0,
            'worst_trade': round(float(df['pnl_percent'].min()), 2) if not df.empty else 0,
            'by_symbol': bs, 'equity_curve': eq
        }

    def get_live_statistics(self, current_prices):
        cs = self.get_statistics()
        cp = cs['total_pnl_usd']
        open_df = self.get_open_with_live_pnl(current_prices)
        op = float(open_df['live_pnl_usd'].sum()) if not open_df.empty else 0.0
        tl = cp + op
        tl_pct = (tl / TOTAL_CAPITAL) * 100
        um = float(open_df['margin_used'].sum()) if not open_df.empty else 0.0
        fm = max(0.0, TOTAL_CAPITAL - um)
        mup = (um / TOTAL_CAPITAL * 100) if TOTAL_CAPITAL > 0 else 0
        ce = cs.get('equity_curve', [TOTAL_CAPITAL])
        if isinstance(ce, np.ndarray): ce = ce.tolist()
        elif not isinstance(ce, list): ce = [TOTAL_CAPITAL]
        le = ce.copy()
        if not open_df.empty:
            rc = le[-1] if le else TOTAL_CAPITAL
            for _, row in open_df.sort_values('timestamp').iterrows():
                rc += float(row['live_pnl_usd'])
                le.append(rc)
        return {
            'closed': cs, 'open_trades': open_df, 'open_count': len(open_df),
            'open_pnl_usd': round(op, 2), 'closed_pnl_usd': round(cp, 2),
            'total_live_pnl_usd': round(tl, 2), 'total_live_pnl_pct': round(tl_pct, 2),
            'live_equity_curve': le,
            'used_margin': round(um, 2), 'free_margin': round(fm, 2),
            'margin_usage_pct': round(mup, 1), 'total_capital': TOTAL_CAPITAL,
        }


signal_db = SignalDatabase()

# ==============================================================================
# 🧠 سیستم مدیریت سرمایه پیشرفته (Kelly + Expectancy)
# ==============================================================================
class AdvancedMoneyManager:
    """
    سیستم چندلایه برای Expectancy مثبت:
    1. Kelly Criterion (نصف برای محافظه‌کاری)
    2. تعدیل نوسان (ATR%)
    3. تعدیل کیفیت سیگنال
    4. Anti-Martingale در loss streak
    5. Drawdown protection
    6. Correlation cap
    7. R:R پویا
    """

    def __init__(self, db, capital=TOTAL_CAPITAL):
        self.db = db
        self.capital = capital
        self.base_risk_pct = 0.02
        self.max_risk_pct = 0.025
        self.min_risk_pct = 0.005
        self.max_concurrent = 3
        self.dd_warning = 15.0
        self.dd_critical = 25.0

    def calculate_kelly(self):
        """Kelly Criterion - نصف برای محافظه‌کاری"""
        stats = self.db.get_statistics()
        if stats['total_trades'] < 15:
            return self.base_risk_pct * 0.75
        wr = stats['win_rate'] / 100
        aw = abs(stats['avg_win'])
        al = abs(stats['avg_loss'])
        if al == 0 or aw == 0: return self.base_risk_pct
        r_ratio = aw / al
        kelly = wr - ((1 - wr) / r_ratio)
        half_kelly = kelly / 2
        return max(self.min_risk_pct, min(self.max_risk_pct, half_kelly))

    def get_volatility_factor(self, atr_pct):
        """ضریب تعدیل بر اساس نوسان بازار"""
        if atr_pct < 0.3: return 1.2
        elif atr_pct < 0.8: return 1.1
        elif atr_pct < 1.5: return 1.0
        elif atr_pct < 3.0: return 0.75
        elif atr_pct < 5.0: return 0.5
        else: return 0.3

    def get_quality_factor(self, score):
        """ضریب تعدیل بر اساس کیفیت سیگنال"""
        if score >= 90: return 1.25
        elif score >= 80: return 1.10
        elif score >= 70: return 1.00
        else: return 0.6

    def get_streak_factor(self):
        """Anti-Martingale: کاهش ریسک در loss streak"""
        signals = self.db.get_all_signals(limit=15)
        closed = signals[signals['status'] == 'CLOSED'].sort_values('timestamp', ascending=False)
        if closed.empty or len(closed) < 3: return 1.0
        streak = 0
        last_out = None
        for _, r in closed.iterrows():
            if last_out is None:
                last_out = r['outcome']
                streak = 1
            elif r['outcome'] == last_out:
                streak += 1
                if streak >= 5: break
            else: break
        if last_out == 'LOSS':
            if streak >= 5: return 0.3
            if streak >= 4: return 0.5
            if streak >= 3: return 0.7
        elif last_out == 'WIN':
            if streak >= 5: return 1.15
            if streak >= 3: return 1.05
        return 1.0

    def get_drawdown_factor(self):
        """کاهش ریسک در drawdown بالا"""
        stats = self.db.get_statistics()
        dd = stats.get('max_drawdown', 0)
        eq = self.capital + stats.get('total_pnl_usd', 0)
        cur_dd = max(0, (self.capital - eq) / self.capital * 100)
        eff_dd = max(dd, cur_dd)
        if eff_dd >= self.dd_critical: return 0.0
        elif eff_dd >= self.dd_warning: return 0.4
        elif eff_dd >= 10: return 0.7
        return 1.0

    def get_directional_exposure(self, direction):
        """محاسبه exposure در یک جهت"""
        open_trades = self.db.get_open_signals()
        if open_trades.empty: return 0, 0.0
        count = 0
        margin = 0.0
        for _, r in open_trades.iterrows():
            td = 'LONG' if r['signal_type'] in ('STRONG_BUY', 'BUY') else 'SHORT'
            if td == direction:
                count += 1
                margin += float(r.get('margin_used', 0) or 0.0)
        return count, margin

    def calculate_risk(self, signal_type, score, atr_pct, free_margin):
        """محاسبه ریسک بهینه با ترکیب همه فاکتورها"""
        kelly = self.calculate_kelly()
        vol_f = self.get_volatility_factor(atr_pct)
        qual_f = self.get_quality_factor(score)
        streak_f = self.get_streak_factor()
        dd_f = self.get_drawdown_factor()
        direction = 'LONG' if signal_type in ('STRONG_BUY', 'BUY') else 'SHORT'
        count, used_m = self.get_directional_exposure(direction)
        dir_f = 1.0
        if count >= self.max_concurrent:
            return 0.0, 0.0, {'blocked': f'too_many_{direction}', 'count': count}
        elif count == 2: dir_f = 0.5

        risk_pct = kelly * vol_f * qual_f * streak_f * dd_f * dir_f
        risk_pct = max(self.min_risk_pct, min(self.max_risk_pct, risk_pct))
        risk_usd = self.capital * risk_pct
        risk_usd = min(risk_usd, free_margin * 0.85)

        if dd_f == 0.0:
            return 0.0, 0.0, {'blocked': 'drawdown_critical'}

        return risk_usd, risk_pct, {
            'kelly': round(kelly * 100, 2),
            'volatility': round(vol_f, 2),
            'quality': round(qual_f, 2),
            'streak': round(streak_f, 2),
            'drawdown': round(dd_f, 2),
            'direction': f"{count}/{self.max_concurrent}",
            'final_pct': round(risk_pct * 100, 2),
        }

    def get_adaptive_sl_tp(self, atr_pct):
        """R:R پویا بر اساس نوسان بازار"""
        if atr_pct < 0.5: return 1.2, 2.2
        elif atr_pct < 1.0: return 1.3, 2.3
        elif atr_pct < 2.0: return 1.5, 2.5
        elif atr_pct < 3.5: return 1.5, 3.0
        else: return 2.0, 3.5

    def compute_expectancy(self):
        """Expectancy = (W% × AvgW) - (L% × AvgL)"""
        stats = self.db.get_statistics()
        if stats['total_trades'] == 0:
            return 0.0, 0.0, "بدون داده"
        wr = stats['win_rate'] / 100
        lr = 1 - wr
        aw = abs(stats['avg_win']) / 100
        al = abs(stats['avg_loss']) / 100
        exp = (wr * aw) - (lr * al)
        exp_usd = exp * self.capital
        if exp > 0.015: q = "🔥 عالی"
        elif exp > 0.005: q = "✅ خوب"
        elif exp > 0: q = "⚠️ قابل قبول"
        elif exp > -0.005: q = "⚠️ بهینه‌سازی نیاز"
        else: q = "🔴 منفی"
        return exp * 100, exp_usd, q

    def compute_expectancy_by_type(self):
        """Expectancy تفکیک شده بر اساس نوع سیگنال"""
        with self.db._get_conn() as conn:
            df = pd.read_sql_query('''
                SELECT signal_type,
                       COUNT(*) as trades,
                       AVG(CASE WHEN outcome='WIN' THEN pnl_percent END) as avg_win,
                       AVG(CASE WHEN outcome='LOSS' THEN pnl_percent END) as avg_loss,
                       SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate
                FROM signals WHERE status='CLOSED'
                GROUP BY signal_type
            ''', conn)
        if df.empty: return pd.DataFrame()
        df['win_rate'] = df['win_rate'] / 100
        df['loss_rate'] = 1 - df['win_rate']
        df['avg_win'] = df['avg_win'].fillna(0) / 100
        df['avg_loss'] = df['avg_loss'].fillna(0).abs() / 100
        df['expectancy_pct'] = (df['win_rate'] * df['avg_win'] - df['loss_rate'] * df['avg_loss']) * 100
        df['expectancy_usd'] = df['expectancy_pct'] / 100 * self.capital
        return df


money_manager = AdvancedMoneyManager(signal_db)

# ==============================================================================
# 🎯 محاسبه‌گر با مدیریت سرمایه پیشرفته
# ==============================================================================
class TradeCalculator:
    @staticmethod
    def calculate_atr(df, period=14):
        if df is None or df.empty or len(df) < period: return None
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]

    @staticmethod
    def compute_trade_params(signal_type, entry_price, atr, spread,
                             money_manager, confirmation_score=100,
                             commission_rate=COMMISSION_RATE):
        """پارامترهای معامله با AdvancedMoneyManager"""
        if pd.isna(atr) or atr <= 0 or entry_price <= 0: return None
        fm, um = money_manager.db.get_free_margin()
        if fm < MIN_FREE_MARGIN: return None

        atr_pct = (atr / entry_price) * 100
        spread_pct = (spread / entry_price) * 100 if spread else 0
        total_cost = spread_pct + (commission_rate * 2 * 100)

        # SL/TP پویا بر اساس ATR%
        sl_mult, tp_mult = money_manager.get_adaptive_sl_tp(atr_pct)
        sl_dist = sl_mult * atr
        tp_dist = tp_mult * atr
        tp_pct = (tp_dist / entry_price) * 100
        net_tp = tp_pct - total_cost
        if net_tp <= 0.1: return None

        if signal_type in ('STRONG_BUY', 'BUY'):
            direction = 'LONG'
            sl_price = entry_price - sl_dist
            tp_price = entry_price + tp_dist
        else:
            direction = 'SHORT'
            sl_price = entry_price + sl_dist
            tp_price = entry_price - tp_dist

        sl_pct = sl_dist / entry_price
        if sl_pct <= 0: return None

        # لوریج پویا بر اساس نوسان
        if atr_pct < 0.8: lev = 10
        elif atr_pct < 1.5: lev = 7
        elif atr_pct < 3.0: lev = 5
        else: lev = 3
        lev = max(2, min(20, lev))

        # ریسک پیشرفته
        risk_usd, risk_pct, factors = money_manager.calculate_risk(
            signal_type, confirmation_score, atr_pct, fm)
        if risk_usd <= 0 or 'blocked' in factors: return None

        # Position Size
        pos_size = risk_usd / sl_pct
        margin_req = pos_size / lev

        # اطمینان نهایی
        if margin_req > fm * 0.9:
            margin_req = fm * 0.85
            pos_size = margin_req * lev
            risk_usd = pos_size * sl_pct

        pos_qty = pos_size / entry_price
        pot_profit = pos_size * (tp_dist / entry_price) - pos_size * (total_cost / 100)

        return {
            'direction': direction,
            'entry_price': round(entry_price, 6),
            'sl_price': round(sl_price, 6),
            'tp_price': round(tp_price, 6),
            'leverage': lev,
            'sl_distance_pct': round(sl_pct * 100, 2),
            'tp_distance_pct': round((tp_dist / entry_price) * 100, 2),
            'rr_ratio': round(tp_dist / sl_dist, 2),
            'net_tp_pct': round(net_tp, 2),
            'spread_pct': round(spread_pct, 3),
            'total_cost_pct': round(total_cost, 3),
            'atr_pct': round(atr_pct, 2),
            'risk_usd': round(risk_usd, 2),
            'risk_pct': round(risk_pct * 100, 2),
            'position_size_usd': round(pos_size, 2),
            'position_qty': round(pos_qty, 6),
            'margin_required': round(margin_req, 2),
            'potential_profit': round(pot_profit, 2),
            'factors': factors,
            'sl_mult': sl_mult,
            'tp_mult': tp_mult,
        }


# ==============================================================================
# 🔍 تحلیل تیک و سیگنال
# ==============================================================================
class TickAnalyzer:
    def enhanced_analysis(self, df):
        if df is None or df.empty: return pd.DataFrame()
        results = []
        for idx, c in df.iterrows():
            et = max(20, min(int(c['volume'] / 0.01), 500))
            np.random.seed(int(c['startTime'].timestamp()) % 10000)
            body = abs(c['close'] - c['open'])
            upper_s = c['high'] - max(c['open'], c['close'])
            lower_s = min(c['open'], c['close']) - c['low']
            total_r = c['high'] - c['low']
            if total_r == 0 or pd.isna(total_r): total_r = 0.01
            if pd.isna(body) or pd.isna(upper_s) or pd.isna(lower_s):
                bbr = 0.5
            elif c['close'] >= c['open']:
                bbr = 0.55 + (body / total_r) * 0.2
                if lower_s > body: bbr += 0.1
            else:
                bbr = 0.45 - (body / total_r) * 0.2
                if upper_s > body: bbr -= 0.1
            bbr = np.clip(bbr, 0.1, 0.9)
            pt = int(et * bbr)
            nt = et - pt
            tv = c['volume'] if not pd.isna(c['volume']) else 0
            pv = tv * bbr * np.random.uniform(0.8, 1.2)
            nv = tv - pv
            noise = np.random.normal(0, 0.05)
            pt = max(0, int(pt * (1 + noise)))
            nt = max(0, et - pt)
            tr_r = pt / (pt + nt) if (pt + nt) > 0 else 0.5
            vr = pv / (pv + nv) if (pv + nv) > 0 else 0.5
            results.append({
                'time': c['startTime'], 'open': c['open'], 'high': c['high'],
                'low': c['low'], 'close': c['close'], 'volume': c['volume'],
                'positive_ticks': pt, 'negative_ticks': nt,
                'total_ticks': pt + nt,
                'positive_volume': round(pv, 4),
                'negative_volume': round(nv, 4),
                'tick_ratio': round(tr_r, 4),
                'volume_ratio': round(vr, 4),
                'net_ticks': pt - nt,
                'net_volume': round(pv - nv, 4),
                'candle_direction': 1 if c['close'] >= c['open'] else -1
            })
        return pd.DataFrame(results)

    def generate_signals(self, df):
        if df is None or df.empty: return pd.DataFrame()
        d = df.copy()
        d['price_sma'] = d['close'].rolling(5).mean()
        d['volume_pressure'] = d['net_volume'] / d['volume'].replace(0, 1)
        d['tick_momentum'] = d['net_ticks'].rolling(3).sum()
        delta = d['net_ticks'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1)
        d['tick_rsi'] = 100 - (100 / (1 + rs))
        d['signal_score'] = 0
        d.loc[d['tick_ratio'] > 0.60, 'signal_score'] += 2
        d.loc[d['tick_ratio'] < 0.40, 'signal_score'] -= 2
        d.loc[d['volume_pressure'] > 0.3, 'signal_score'] += 2
        d.loc[d['volume_pressure'] < -0.3, 'signal_score'] -= 2
        d.loc[d['tick_momentum'] > 10, 'signal_score'] += 1
        d.loc[d['tick_momentum'] < -10, 'signal_score'] -= 1
        d.loc[d['tick_rsi'] < 30, 'signal_score'] += 2
        d.loc[d['tick_rsi'] > 70, 'signal_score'] -= 2
        pu = d['close'] > d['price_sma']
        tpd = d['volume_pressure'] < 0
        pdn = d['close'] < d['price_sma']
        tpu = d['volume_pressure'] > 0
        d.loc[pdn & tpu, 'signal_score'] += 3
        d.loc[pu & tpd, 'signal_score'] -= 3
        d['signal'] = 'HOLD'
        sbm = (d['signal_score'] >= 4) & (d['tick_ratio'] >= 0.70)
        d.loc[sbm, 'signal'] = 'STRONG_BUY'
        bm = (d['signal_score'] >= 2) & (d['signal_score'] < 4) & (d['signal'] == 'HOLD')
        d.loc[bm, 'signal'] = 'BUY'
        ssm = (d['signal_score'] <= -4) & (d['tick_ratio'] <= 0.30)
        d.loc[ssm, 'signal'] = 'STRONG_SELL'
        sm = (d['signal_score'] <= -2) & (d['signal_score'] > -4) & (d['signal'] == 'HOLD')
        d.loc[sm, 'signal'] = 'SELL'
        return d


class SignalConfirmationEngine:
    def __init__(self, api_client):
        self.api_client = api_client

    def get_htf_trend(self, symbol, htf_interval="60", ema_period=50):
        df = self.api_client.get_klines(symbol=symbol, interval=htf_interval, limit=ema_period + 30)
        if df is None or df.empty or len(df) < ema_period: return 0
        df = df.copy()
        df['ema'] = df['close'].ewm(span=ema_period, adjust=False).mean()
        lc = df['close'].iloc[-1]; le = df['ema'].iloc[-1]
        ri = max(0, len(df) - 6); pe = df['ema'].iloc[ri]
        slope = le - pe
        if lc > le and slope > 0: return 1
        elif lc < le and slope < 0: return -1
        return 0

    def _compute_reliability(self, df):
        d = df.copy()
        vm = d['volume'].rolling(20, min_periods=5).mean()
        vs = d['volume'].rolling(20, min_periods=5).std().replace(0, np.nan)
        d['volume_zscore'] = ((d['volume'] - vm) / vs).fillna(0)
        hl = d['high'] - d['low']
        hc = (d['high'] - d['close'].shift()).abs()
        lc = (d['low'] - d['close'].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        atr = tr.rolling(14, min_periods=5).mean()
        atr_pct = (atr / d['close']) * 100
        d['atr_percentile'] = atr_pct.rank(pct=True) * 100
        d['atr_percentile'] = d['atr_percentile'].fillna(50)
        tm = d['total_ticks'].rolling(20, min_periods=5).median()
        d['sample_reliable'] = d['total_ticks'] >= tm.fillna(d['total_ticks'].median())
        d['atr'] = atr
        return d

    def confirm(self, df, symbol, htf_interval="60"):
        if df is None or df.empty: return df
        df = self._compute_reliability(df)
        htf = self.get_htf_trend(symbol, htf_interval)
        df['htf_trend'] = htf
        scores, reasons = [], []
        for _, r in df.iterrows():
            score, rsns, direction = 0, [], 0
            if r['signal'] in ('BUY', 'STRONG_BUY'): direction = 1
            elif r['signal'] in ('SELL', 'STRONG_SELL'): direction = -1
            if direction != 0:
                if htf == direction:
                    score += 40; rsns.append('هم‌راستا')
                elif htf == -direction:
                    score -= 20; rsns.append('خلاف')
                else: score += 10
                if r['volume_zscore'] > 0.5:
                    score += 25; rsns.append('حجم بالا')
                elif r['volume_zscore'] < -1:
                    score -= 15
                else: score += 10
                if r['atr_percentile'] < 80: score += 15
                else: score -= 10
                if r['sample_reliable']: score += 20
            scores.append(max(0, min(100, score)))
            reasons.append(' | '.join(rsns) if rsns else '-')
        df['confirmation_score'] = scores
        df['confirmation_reasons'] = reasons
        def level(r):
            if r['signal'] == 'HOLD': return '-'
            if r['confirmation_score'] >= 70: return 'قوی و تایید شده'
            elif r['confirmation_score'] >= 40: return 'نیمه تایید'
            return 'بدون تایید'
        df['confirmation_level'] = df.apply(level, axis=1)
        return df


def _local_extrema(series, window=1, mode='max'):
    idxs = []
    n = len(series)
    for i in range(window, n - window):
        seg = series.iloc[i - window:i + window + 1]
        val = series.iloc[i]
        if mode == 'max' and val == seg.max(): idxs.append(series.index[i])
        elif mode == 'min' and val == seg.min(): idxs.append(series.index[i])
    return idxs


def add_signal_trendlines(fig, df, min_confirm=40, lookahead=6, max_lines=6):
    if df is None or df.empty: return fig
    df = df.reset_index(drop=True); n = len(df)
    sb = df[(df['signal'] == 'STRONG_BUY') & (df['confirmation_score'] >= min_confirm)].tail(max_lines)
    ss = df[(df['signal'] == 'STRONG_SELL') & (df['confirmation_score'] >= min_confirm)].tail(max_lines)
    lc = df['close'].iloc[-1]; lt = df['time'].iloc[-1]
    for idx, row in sb.iterrows():
        ei = min(n - 1, idx + lookahead)
        if ei - idx < 2: continue
        wdf = df.iloc[idx:ei + 1]
        hp = _local_extrema(wdf['high'], window=1, mode='max')
        cands = sorted(set([idx] + hp))
        i1, i2 = (cands[0], cands[-1]) if len(cands) >= 2 else (idx, ei)
        if i1 == i2: continue
        x1, y1 = df['time'].iloc[i1], df['high'].iloc[i1]
        x2, y2 = df['time'].iloc[i2], df['high'].iloc[i2]
        fig.add_shape(type="line", x0=x1, y0=y1, x1=x2, y1=y2,
                      line=dict(color="#00d4aa", width=1.5, dash="dot"), layer="above")
        slope = (y2 - y1) / (x2 - x1).total_seconds()
        lvn = y2 + slope * (lt - x2).total_seconds()
        broken = lc > lvn
        label = "✅ شکسته شد" if broken else "⏳ در انتظار"
        lc_col = "#00ff88" if broken else "#8892b0"
        fig.add_annotation(x=x2, y=y2, text=label, showarrow=False,
            font=dict(size=9, color=lc_col),
            bgcolor="rgba(0,50,30,0.75)", bordercolor="#00d4aa",
            borderwidth=1, yshift=14, xanchor="left")
    for idx, row in ss.iterrows():
        ei = min(n - 1, idx + lookahead)
        if ei - idx < 2: continue
        wdf = df.iloc[idx:ei + 1]
        lp = _local_extrema(wdf['low'], window=1, mode='min')
        cands = sorted(set([idx] + lp))
        i1, i2 = (cands[0], cands[-1]) if len(cands) >= 2 else (idx, ei)
        if i1 == i2: continue
        x1, y1 = df['time'].iloc[i1], df['low'].iloc[i1]
        x2, y2 = df['time'].iloc[i2], df['low'].iloc[i2]
        fig.add_shape(type="line", x0=x1, y0=y1, x1=x2, y1=y2,
                      line=dict(color="#ff6b6b", width=1.5, dash="dot"), layer="above")
        slope = (y2 - y1) / (x2 - x1).total_seconds()
        lvn = y2 + slope * (lt - x2).total_seconds()
        broken = lc < lvn
        label = "✅ شکسته شد" if broken else "⏳ در انتظار"
        lc_col = "#ff4757" if broken else "#8892b0"
        fig.add_annotation(x=x2, y=y2, text=label, showarrow=False,
            font=dict(size=9, color=lc_col),
            bgcolor="rgba(50,0,0,0.75)", bordercolor="#ff6b6b",
            borderwidth=1, yshift=-14, xanchor="left")
    return fig


# ==============================================================================
# 📡 اسکنر ۲۱ ارز با مدیریت سرمایه پیشرفته
# ==============================================================================
class MultiSymbolScanner:
    def __init__(self, api_client, analyzer, confirmer, db):
        self.api_client = api_client
        self.analyzer = analyzer
        self.confirmer = confirmer
        self.db = db
        self.last_results = {}
        self.scan_running = False
        self.last_scan_time = None
        self._lock = threading.Lock()
        self._start_thread()

    def _start_thread(self):
        def worker():
            print(f"🔍 بررسی {len(self.db.get_open_signals())} trade باز باقی‌مانده...")
            self._check_open_trades()
            while True:
                try:
                    self._scan_all()
                    self._check_open_trades()
                    time.sleep(120)
                except Exception as e:
                    print(f"❌ خطای اسکنر: {e}")
                    time.sleep(30)
        threading.Thread(target=worker, daemon=True).start()

    def _scan_symbol(self, symbol):
        try:
            klines = self.api_client.get_klines(symbol=symbol, interval="5", limit=60)
            if klines is None or klines.empty or len(klines) < 20: return None
            analysis = self.analyzer.enhanced_analysis(klines)
            if analysis is None or analysis.empty: return None
            analysis = self.analyzer.generate_signals(analysis)
            analysis = self.confirmer.confirm(analysis, symbol, htf_interval="60")
            latest = analysis.iloc[-1]
            ticker, _ = self.api_client.get_ticker(symbol)
            if ticker is None: return None
            atr = TradeCalculator.calculate_atr(klines)
            spread = ticker.get('spread', 0)
            if spread <= 0: spread = ticker['ask'] - ticker['bid']
            return {
                'symbol': symbol, 'price': latest['close'],
                'signal': latest['signal'], 'score': latest['signal_score'],
                'confirm_score': latest['confirmation_score'],
                'confirm_level': latest['confirmation_level'],
                'tick_ratio': latest['tick_ratio'],
                'htf_trend': latest.get('htf_trend', 0),
                'atr': atr, 'spread': spread, 'volume': latest['volume'],
                'timestamp': datetime.now(),
            }
        except Exception as e:
            print(f"❌ خطا در اسکن {symbol}: {e}")
            return None

    def _scan_all(self):
        print(f"🔍 شروع اسکن {len(SCAN_SYMBOLS)} ارز...")
        self.scan_running = True
        for sym in SCAN_SYMBOLS:
            r = self._scan_symbol(sym)
            if r:
                with self._lock: self.last_results[sym] = r
                if r['signal'] in ('STRONG_BUY', 'STRONG_SELL') and r['confirm_score'] >= 70:
                    self._try_register_signal(r)
            time.sleep(0.5)
        self.scan_running = False
        self.last_scan_time = datetime.now()
        print(f"✅ اسکن کامل شد")

    def _try_register_signal(self, result):
        sym = result['symbol']
        recent = self.db.get_all_signals(limit=10)
        if not recent.empty:
            rs = recent[recent['symbol'] == sym]
            if not rs.empty:
                lt = pd.to_datetime(rs.iloc[0]['timestamp'])
                if (datetime.now() - lt).total_seconds() < 900: return

        fm, um = self.db.get_free_margin()
        print(f"\n📊 [{sym}] مارجین آزاد: ${fm:.2f} | استفاده‌شده: ${um:.2f}")

        params = TradeCalculator.compute_trade_params(
            signal_type=result['signal'],
            entry_price=result['price'],
            atr=result['atr'],
            spread=result['spread'],
            money_manager=money_manager,
            confirmation_score=result['confirm_score']
        )

        if params is None:
            print(f"   ⛔ سیگنال {sym} رد شد")
            return

        f = params['factors']
        print(f"   🎯 Quality: {result['confirm_score']}/100 | Vol: {params['atr_pct']:.2f}%")
        print(f"   📊 Kelly: {f.get('kelly', 0):.2f}% | Vol×{f.get('volatility', 1):.2f} "
              f"| Qual×{f.get('quality', 1):.2f} | Streak×{f.get('streak', 1):.2f} "
              f"| DD×{f.get('drawdown', 1):.2f}")
        print(f"   💰 Risk: ${params['risk_usd']:.2f} ({params['risk_pct']:.2f}%)")
        print(f"   🎲 R:R = 1:{params['rr_ratio']} | L:{params['leverage']}x | M: ${params['margin_required']:.2f}")

        notes = (f"tick={result['tick_ratio']:.2f}, htf={result['htf_trend']}, "
                 f"kelly={f.get('kelly',0):.2f}%, vol={f.get('volatility',1):.2f}, "
                 f"qual={f.get('quality',1):.2f}, streak={f.get('streak',1):.2f}, "
                 f"dd={f.get('drawdown',1):.2f}, rr=1:{params['rr_ratio']}")

        self.db.insert_signal(
            symbol=sym, signal_type=result['signal'],
            entry_price=params['entry_price'], tp_price=params['tp_price'],
            sl_price=params['sl_price'], leverage=params['leverage'],
            confirmation_score=result['confirm_score'], atr=result['atr'],
            spread=result['spread'], commission_rate=COMMISSION_RATE,
            risk_usd=params['risk_usd'], margin_used=params['margin_required'],
            position_size=params['position_size_usd'],
            rr_ratio=params['rr_ratio'], notes=notes
        )
        print(f"   ✅ ثبت: {sym} {result['signal']} @ {params['entry_price']}")

    def _check_open_trades(self):
        """فقط TP/SL بررسی - بدون بستن زمانی"""
        ot = self.db.get_open_signals()
        if ot.empty: return
        for _, t in ot.iterrows():
            try:
                ti, _ = self.api_client.get_ticker(t['symbol'])
                if ti is None: continue
                cp = ti['lastPrice']
                en = float(t['entry_price'])
                tp = float(t['tp_price'])
                sl = float(t['sl_price'])
                st = t['signal_type']
                out, ep = None, None
                if st in ('STRONG_BUY', 'BUY'):
                    if cp >= tp: out, ep = 'WIN', tp
                    elif cp <= sl: out, ep = 'LOSS', sl
                else:
                    if cp <= tp: out, ep = 'WIN', tp
                    elif cp >= sl: out, ep = 'LOSS', sl

                if out:
                    risk = float(t.get('risk_usd', 10.0) or 10.0)
                    sl_pct = abs(en - sl) / en if en > 0 else 0.01
                    pos = risk / sl_pct if sl_pct > 0 else 0.0
                    spread = float(t['spread']) if t['spread'] else 0.0
                    if st in ('STRONG_BUY', 'BUY'):
                        gross = pos * (ep - en) / en
                    else:
                        gross = pos * (en - ep) / en
                    sp = (spread / en * 100) if en > 0 else 0
                    tc = sp + COMMISSION_RATE * 2 * 100
                    costs = pos * (tc / 100)
                    net = gross - costs
                    lev = float(t['leverage'])
                    mu = pos / lev if lev > 0 else pos
                    pnl_pct = (net / mu * 100) if mu > 0 else 0
                    self.db.close_signal(
                        signal_id=t['id'], exit_price=ep, outcome=out,
                        pnl_percent=round(pnl_pct, 2), pnl_usd=round(net, 2)
                    )
                    print(f"🏁 Trade بسته: {t['symbol']} - {out} ({pnl_pct:+.2f}% | ${net:+.2f})")
            except Exception as e:
                print(f"⚠️ خطا: {e}")

    def get_results(self):
        with self._lock: return self.last_results.copy()

    def get_current_prices(self):
        with self._lock: return {s: r['price'] for s, r in self.last_results.items()}

    def get_scan_status(self):
        return {
            'running': self.scan_running,
            'last_scan': self.last_scan_time,
            'total_symbols': len(SCAN_SYMBOLS),
        }


# ==============================================================================
# 🏗️ Layout
# ==============================================================================
analyzer = TickAnalyzer()
confirmer = SignalConfirmationEngine(bybit_client)
scanner = MultiSymbolScanner(bybit_client, analyzer, confirmer, signal_db)

CONFIRM_BADGE_CLASS = {
    'قوی و تایید شده': 'confirm-strong',
    'نیمه تایید': 'confirm-half',
    'بدون تایید': 'confirm-none',
}

tab1_content = html.Div([
    html.Div([
        html.Div([
            html.Label("🎯 نماد:"),
            dcc.Dropdown(id='symbol-dropdown',
                options=[{'label': ' BTC/USDT', 'value': 'BTCUSDT'},
                         {'label': '🔷 ETH/USDT', 'value': 'ETHUSDT'},
                         {'label': '🟣 SOL/USDT', 'value': 'SOLUSDT'},
                         {'label': '⚪ XRP/USDT', 'value': 'XRPUSDT'},
                         {'label': '🟡 DOGE/USDT', 'value': 'DOGEUSDT'}],
                value='BTCUSDT', style={'width': '220px', 'backgroundColor': '#0a0e27', 'color': '#fff'}),
        ], className="control-item"),
        html.Div([
            html.Label("📊 تعداد کندل:"),
            dcc.Input(id='candle-count', type='number', value=50, min=10, max=200,
                style={'width': '120px', 'backgroundColor': '#0a0e27', 'color': '#fff',
                       'border': '1px solid #00d4aa', 'borderRadius': '10px', 'padding': '10px'}),
        ], className="control-item"),
        html.Div([
            html.Label("🛡️ حداقل تایید:"),
            dcc.Input(id='min-confirm-score', type='number', value=0, min=0, max=100, step=10,
                style={'width': '120px', 'backgroundColor': '#0a0e27', 'color': '#fff',
                       'border': '1px solid #ffd700', 'borderRadius': '10px', 'padding': '10px'}),
        ], className="control-item"),
        html.Div([
            html.Label("📐 حداقل ترندلاین:"),
            dcc.Input(id='trendline-min-score', type='number', value=40, min=0, max=100, step=10,
                style={'width': '120px', 'backgroundColor': '#0a0e27', 'color': '#fff',
                       'border': '1px solid #00d4aa', 'borderRadius': '10px', 'padding': '10px'}),
        ], className="control-item"),
        html.Button('🔄 بروزرسانی', id='refresh-btn', n_clicks=0, className="refresh-btn"),
        html.Div(id='status-text', style={'color': '#00ff88', 'fontWeight': '700', 'paddingBottom': '10px'}),
    ], className="control-panel"),
    html.Div(id='signals-table-section'),
    html.Div(id='summary-cards', style={'marginBottom': '20px', 'textAlign': 'center'}),
    html.Div([
        html.Div([html.H3("📈 نمودار کندل‌استیک")], className="section-title"),
        html.Div([dcc.Graph(id='main-chart', style={'height': '600px'})], className="glass-card"),
    ], style={'marginBottom': '20px'}),
    html.Div([
        html.Div([
            html.Div([html.H3("📊 تحلیل حجم تیک‌ها")], className="section-title"),
            html.Div([dcc.Graph(id='volume-chart', style={'height': '400px'})], className="glass-card"),
        ], style={'width': '49%', 'display': 'inline-block', 'verticalAlign': 'top', 'marginRight': '1%'}),
        html.Div([
            html.Div([html.H3("📉 نسبت تیک‌ها")], className="section-title"),
            html.Div([dcc.Graph(id='ratio-chart', style={'height': '400px'})], className="glass-card"),
        ], style={'width': '49%', 'display': 'inline-block', 'verticalAlign': 'top'}),
    ], style={'marginBottom': '20px'}),
    html.Div([
        html.Div([html.H3("🎯 سیگنال‌های خرید و فروش")], className="section-title"),
        html.Div([dcc.Graph(id='signal-chart', style={'height': '400px'})], className="glass-card"),
    ], style={'marginBottom': '20px'}),
    html.Div([
        html.Div([html.H3("📐 RSI مبتنی بر تیک")], className="section-title"),
        html.Div([dcc.Graph(id='rsi-chart', style={'height': '300px'})], className="glass-card"),
    ], style={'marginBottom': '20px'}),
    html.Div([
        html.Div([html.H3("📋 جدول کامل داده‌ها")], className="section-title"),
        html.Div([html.Div(id='data-table', style={'overflowX': 'auto'})], className="glass-card"),
    ], style={'marginBottom': '20px'}),
])

tab2_content = html.Div([
    html.Div([
        html.Div([html.H3("🛰️ اسکنر زنده ۲۱ ارز")], className="section-title", style={'borderRightColor': '#ffd700'}),
        html.P("🔍 اسکن خودکار + مدیریت سرمایه پیشرفته (Kelly) + R:R پویا + Expectancy مثبت",
               style={'color': '#8892b0', 'margin': '0 0 15px 0', 'padding': '0 20px'}),
    ]),
    html.Div(id='scanner-status-bar', style={'marginBottom': '15px'}),
    html.Div(id='scanner-margin-panel', style={'marginBottom': '15px'}),
    html.Div(id='scanner-open-trades', style={'marginBottom': '25px'}),
    html.Div(id='scanner-strong-signals', style={'marginBottom': '25px'}),
    html.Div([
        html.Div([html.H3("📊 نمای کلی همه ۲۱ ارز")], className="section-title"),
        html.Div(id='scanner-grid', className="scanner-grid"),
    ], style={'marginBottom': '25px'}),
])

tab3_content = html.Div([
    html.Div([
        html.Div([html.H3("📊 آمار عملکرد کلی + Expectancy")], className="section-title", style={'borderRightColor': '#bb86fc'}),
        html.P("🧠 آمار لحظه‌ای شامل Trade های بسته + باز زنده | مدیریت ریسک Kelly + Expectancy",
               style={'color': '#8892b0', 'margin': '0 0 15px 0', 'padding': '0 20px'}),
    ]),
    html.Div(id='performance-summary-cards', style={'marginBottom': '20px', 'textAlign': 'center'}),
    html.Div(id='expectancy-section', style={'marginBottom': '20px'}),
    html.Div([
        html.Div([
            html.Div([html.H3("📈 نمودار رشد سرمایه زنده")], className="section-title"),
            html.Div([dcc.Graph(id='equity-chart', style={'height': '450px'})], className="glass-card"),
        ], style={'marginBottom': '20px'}),
    ]),
    html.Div([
        html.Div([
            html.Div([html.H3("📊 وین‌ریت (از Trade های بسته)")], className="section-title"),
            html.Div([dcc.Graph(id='winrate-chart', style={'height': '400px'})], className="glass-card"),
        ], style={'width': '49%', 'display': 'inline-block', 'verticalAlign': 'top', 'marginRight': '1%'}),
        html.Div([
            html.Div([html.H3("🪙 آمار هر نماد")], className="section-title"),
            html.Div([html.Div(id='symbol-stats-table', style={'overflowX': 'auto', 'maxHeight': '400px', 'overflowY': 'auto'})],
                     className="glass-card"),
        ], style={'width': '49%', 'display': 'inline-block', 'verticalAlign': 'top'}),
    ], style={'marginBottom': '20px'}),
    html.Div([
        html.Div([html.H3("📋 تاریخچه کامل (بسته + باز زنده)")], className="section-title"),
        html.Div([html.Div(id='history-table', style={'overflowX': 'auto'})], className="glass-card"),
    ], style={'marginBottom': '20px'}),
])

app.layout = html.Div([
    dcc.Store(id='analysis-data'),
    html.Div([
        html.Div([
            html.Div([
                html.Span("🌙", className="banner-logo"),
                html.Div([
                    html.H2("به کانال BITMOON618 بپیوندید!"),
                    html.P("تحلیل‌های حرفه‌ای کریپتو | سیگنال‌های ویژه | آموزش رایگان"),
                ], className="banner-text"),
            ], className="banner-left"),
            html.A([html.Span("📢"), html.Span("عضویت در کانال")],
                href="https://t.me/BITMOON618", target="_blank", className="banner-btn"),
        ], className="banner-content"),
    ], className="bitmoon-banner"),

    html.Div([
        html.H1("📊 سیستم جامع تحلیل تیک دیتا بایبیت"),
        html.P("تحلیل تیک‌ها + اسکن ۲۱ ارز + مدیریت سرمایه Kelly + Expectancy | نسخه 5.0",
               style={'color': '#8892b0', 'margin': '8px 0 0 0', 'fontSize': '14px'}),
        html.Div(id='connection-indicator', style={'marginTop': '10px'}),
    ], className="main-header"),

    dcc.Tabs(id='main-tabs', value='tab-analysis', className='custom-tabs',
             children=[
                 dcc.Tab(label='📈 تحلیل تک نماد', value='tab-analysis', className='custom-tab',
                         selected_className='custom-tab--selected'),
                 dcc.Tab(label='🛰️ اسکنر ۲۱ ارز', value='tab-scanner', className='custom-tab',
                         selected_className='custom-tab--selected'),
                 dcc.Tab(label='📊 پایگاه داده و آمار', value='tab-performance', className='custom-tab',
                         selected_className='custom-tab--selected'),
             ]),

    html.Div(tab1_content, id='tab-1-wrapper'),
    html.Div(tab2_content, id='tab-2-wrapper', style={'display': 'none'}),
    html.Div(tab3_content, id='tab-3-wrapper', style={'display': 'none'}),

    html.Div([
        html.P("💎 ساخته شده با ❤️ برای تریدرهای حرفه‌ای | BITMOON618",
            style={'color': '#8892b0', 'textAlign': 'center', 'margin': '0', 'fontSize': '14px'}),
    ], style={'padding': '20px', 'marginTop': '30px'}),

    dcc.Interval(id='auto-refresh', interval=120000, n_intervals=0),
    dcc.Interval(id='health-check', interval=60000, n_intervals=0),
    dcc.Interval(id='scanner-refresh', interval=30000, n_intervals=0),
    dcc.Interval(id='perf-refresh', interval=10000, n_intervals=0),
], style={'backgroundColor': '#0a0e27', 'padding': '20px', 'minHeight': '100vh'})


# ==================== Callbacks ====================

@app.callback(
    [Output('tab-1-wrapper', 'style'), Output('tab-2-wrapper', 'style'), Output('tab-3-wrapper', 'style')],
    Input('main-tabs', 'value'))
def switch_tab(t):
    h = {'display': 'none'}; s = {}
    if t == 'tab-analysis': return s, h, h
    elif t == 'tab-scanner': return h, s, h
    elif t == 'tab-performance': return h, h, s
    return s, h, h


@app.callback(
    Output('connection-indicator', 'children'),
    Input('health-check', 'n_intervals'), Input('refresh-btn', 'n_clicks'), prevent_initial_call=False)
def update_connection_indicator(h, r):
    ok, err, price = bybit_client.test_connection()
    ep = bybit_client.active_endpoint
    if ok:
        return html.Div([
            html.Span("🟢 متصل", className="connection-status status-ok"),
            html.Span(f"💰 BTC: ${price:,.2f}  |  🌐 Endpoint: {ep}",
                      style={'color': '#8892b0', 'fontSize': '13px', 'fontWeight': '600'}),
        ])
    return html.Div([
        html.Span("🔴 قطع", className="connection-status status-err"),
        html.Span(f"  خطا: {err}", style={'color': '#ff8c8c', 'fontSize': '12px'}),
    ])


@app.callback(
    [Output('main-chart', 'figure'), Output('volume-chart', 'figure'),
     Output('ratio-chart', 'figure'), Output('signal-chart', 'figure'),
     Output('rsi-chart', 'figure'), Output('summary-cards', 'children'),
     Output('data-table', 'children'), Output('status-text', 'children'),
     Output('signals-table-section', 'children')],
    [Input('refresh-btn', 'n_clicks'), Input('auto-refresh', 'n_intervals')],
    [State('symbol-dropdown', 'value'), State('candle-count', 'value'),
     State('min-confirm-score', 'value'), State('trendline-min-score', 'value')])
def update_dashboard(nc, ni, symbol, cc, mcs, tms):
    kdf = bybit_client.get_klines(symbol=symbol, interval="5", limit=cc or 50)
    ef = go.Figure()
    ef.update_layout(template='plotly_dark', paper_bgcolor='#1a1a2e', plot_bgcolor='#16213e', height=400)
    ef.add_annotation(text="❌ خطا در دریافت داده!", xref="paper", yref="paper", x=0.5, y=0.5,
                      showarrow=False, font=dict(size=20, color="#ff4757"))
    et = html.Div("داده‌ای موجود نیست", style={'textAlign': 'center', 'color': '#8892b0', 'padding': '30px'})
    es = html.Div([
        html.Div([html.H3("⚡ سیگنال‌های ویژه")], className="section-title", style={'borderRightColor': '#ffd700'}),
        html.Div([html.P("🕐 در حال حاضر سیگنال فعالی وجود ندارد.",
                   style={'textAlign': 'center', 'color': '#8892b0', 'padding': '30px'})
        ], className="glass-card"),
    ], style={'marginBottom': '25px'})
    if kdf is None or kdf.empty:
        err_s = html.Div([html.Div([
            html.H3("⚠️ خطا در دریافت داده", style={'color': '#ff4757', 'marginBottom': '15px'}),
            html.P("از VPN استفاده کنید", style={'textAlign': 'right'}),
        ], className="error-message")])
        return (ef, ef, ef, ef, ef, [], et, "❌ خطا", err_s)

    adf = analyzer.enhanced_analysis(kdf)
    if adf is None or adf.empty:
        return (ef, ef, ef, ef, ef, [], et, "❌ خطا", es)

    adf = analyzer.generate_signals(adf)
    adf = confirmer.confirm(adf, symbol, htf_interval="60")

    fm = make_subplots(rows=1, cols=1)
    fm.add_trace(go.Candlestick(x=adf['time'], open=adf['open'], high=adf['high'],
        low=adf['low'], close=adf['close'], name='کندل',
        increasing_line_color='#00d4aa', decreasing_line_color='#ff4757',
        increasing_fillcolor='#00d4aa', decreasing_fillcolor='#ff4757'))
    for i, r in adf.iterrows():
        fm.add_annotation(x=r['time'], y=r['high'], text=f"▲ {r['positive_ticks']}",
            showarrow=False, yshift=25, font=dict(size=10, color='#00ff88'),
            bgcolor='rgba(0,50,30,0.85)', borderpad=4, bordercolor='#00ff88', borderwidth=1)
        fm.add_annotation(x=r['time'], y=r['low'], text=f"▼ {r['negative_ticks']}",
            showarrow=False, yshift=-25, font=dict(size=10, color='#ff6b6b'),
            bgcolor='rgba(50,0,0,0.85)', borderpad=4, bordercolor='#ff6b6b', borderwidth=1)
    fm = add_signal_trendlines(fm, adf, min_confirm=tms if tms is not None else 40)
    fm.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(22, 33, 62, 0.5)', xaxis_rangeslider_visible=False,
        height=600, margin=dict(l=50, r=30, t=30, b=50))
    fm.update_xaxes(gridcolor='rgba(255,255,255,0.05)', tickangle=45)
    fm.update_yaxes(gridcolor='rgba(255,255,255,0.05)', title="قیمت")

    fv = go.Figure()
    fv.add_trace(go.Bar(x=adf['time'], y=adf['positive_volume'],
        name='حجم خرید', marker=dict(color='rgba(0, 212, 170, 0.8)')))
    fv.add_trace(go.Bar(x=adf['time'], y=-adf['negative_volume'],
        name='حجم فروش', marker=dict(color='rgba(255, 71, 87, 0.8)')))
    fv.add_trace(go.Scatter(x=adf['time'], y=adf['volume'], name='حجم کل',
        line=dict(color='#ffd700', width=2.5), yaxis='y2'))
    fv.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(22, 33, 62, 0.5)', barmode='relative', height=400,
        margin=dict(l=50, r=50, t=30, b=30),
        yaxis2=dict(overlaying='y', side='right', gridcolor='rgba(255,255,255,0.05)'))

    fr = go.Figure()
    fr.add_trace(go.Scatter(x=adf['time'], y=adf['tick_ratio'] * 100,
        name='نسبت تیک مثبت', line=dict(color='#00d4aa', width=2.5),
        fill='tozeroy', fillcolor='rgba(0,212,170,0.15)'))
    fr.add_trace(go.Scatter(x=adf['time'], y=adf['volume_ratio'] * 100,
        name='نسبت حجم مثبت', line=dict(color='#ffd700', width=2.5),
        fill='tozeroy', fillcolor='rgba(255,215,0,0.1)'))
    fr.add_hline(y=70, line_dash="dash", line_color="#00ff88", annotation_text="خرید قوی 70%")
    fr.add_hline(y=30, line_dash="dash", line_color="#ff4757", annotation_text="فروش قوی 30%")
    fr.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(22, 33, 62, 0.5)', height=400, margin=dict(l=50, r=50, t=30, b=30))
    fr.update_yaxes(range=[0, 100])

    fs = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]])
    fs.add_trace(go.Scatter(x=adf['time'], y=adf['close'], name='قیمت',
        line=dict(color='#fff', width=2)), row=1, col=1)
    bs = adf[adf['signal'].isin(['BUY', 'STRONG_BUY'])]
    fs.add_trace(go.Scatter(x=bs['time'], y=bs['close'], mode='markers',
        name='سیگنال خرید', marker=dict(symbol='triangle-up', size=18, color='#00ff88')), row=1, col=1)
    ss = adf[adf['signal'].isin(['SELL', 'STRONG_SELL'])]
    fs.add_trace(go.Scatter(x=ss['time'], y=ss['close'], mode='markers',
        name='سیگنال فروش', marker=dict(symbol='triangle-down', size=18, color='#ff4757')), row=1, col=1)
    cs = ['#00ff88' if s > 0 else '#ff4757' for s in adf['signal_score']]
    fs.add_trace(go.Bar(x=adf['time'], y=adf['signal_score'],
        name='امتیاز', marker_color=cs, opacity=0.7), row=2, col=1)
    fs.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(22, 33, 62, 0.5)', height=400, margin=dict(l=50, r=50, t=30, b=30))

    fri = go.Figure()
    fri.add_trace(go.Scatter(x=adf['time'], y=adf['tick_rsi'], name='Tick RSI',
        line=dict(color='#bb86fc', width=2.5), fill='tozeroy', fillcolor='rgba(187,134,252,0.15)'))
    fri.add_hline(y=70, line_dash="dash", line_color="#ff4757", annotation_text="اشباع خرید (70)")
    fri.add_hline(y=30, line_dash="dash", line_color="#00d4aa", annotation_text="اشباع فروش (30)")
    fri.add_hline(y=50, line_dash="dot", line_color="#888")
    fri.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(22, 33, 62, 0.5)', height=300,
        margin=dict(l=50, r=50, t=30, b=30), yaxis=dict(range=[0, 100]))

    l = adf.iloc[-1]
    tpt = int(adf['positive_ticks'].sum())
    tnt = int(adf['negative_ticks'].sum())
    csig = l['signal']
    sc = {'STRONG_BUY': '#00ff88', 'BUY': '#00d4aa', 'HOLD': '#ffd700',
          'SELL': '#ff8c00', 'STRONG_SELL': '#ff4757'}.get(csig, '#fff')
    st = {'STRONG_BUY': '🟢 خرید قوی', 'BUY': ' خرید', 'HOLD': ' نگهداری',
          'SELL': '🔴 فروش', 'STRONG_SELL': '🔴 فروش قوی'}.get(csig, '?')
    ct = l['confirmation_level'] if l['signal'] != 'HOLD' else '-'
    scards = html.Div([
        html.Div([html.Div(f"💰 قیمت: ${l['close']:,.2f}", style={'fontSize': '18px', 'color': '#fff', 'fontWeight': '900'}),
                  html.Div(f"تغییر: {((l['close']-l['open'])/l['open']*100):+.2f}%",
                      style={'fontSize': '14px', 'marginTop': '5px',
                             'color': '#00ff88' if l['close']>=l['open'] else '#ff4757', 'fontWeight': '700'})
        ], className="summary-card"),
        html.Div([html.Div(f"🟢 تیک+: {tpt:,}", style={'fontSize': '16px', 'color': '#00d4aa', 'fontWeight': '700'})],
            className="summary-card"),
        html.Div([html.Div(f"🔴 تیک-: {tnt:,}", style={'fontSize': '16px', 'color': '#ff4757', 'fontWeight': '700'})],
            className="summary-card"),
        html.Div([html.Div(f" نسبت: {l['tick_ratio']*100:.1f}%", style={'fontSize': '16px', 'color': '#ffd700', 'fontWeight': '700'})],
            className="summary-card"),
        html.Div([html.Div(f" سیگنال: {st}", style={'fontSize': '18px', 'color': sc, 'fontWeight': '900'}),
                  html.Div(f"تایید: {ct}", style={'fontSize': '13px', 'color': '#8892b0', 'marginTop': '5px'})
        ], className="summary-card", style={'border': f'2px solid {sc}'}),
    ])

    td = adf.tail(20).copy()
    td['ts'] = td['time'].dt.strftime('%Y-%m-%d %H:%M')
    th = html.Table([
        html.Thead(html.Tr([
            html.Th('زمان'), html.Th('بستن'), html.Th('تیک+'), html.Th('تیک-'),
            html.Th('نسبت%'), html.Th('RSI'), html.Th('سیگنال'), html.Th('تایید')])),
        html.Tbody([html.Tr([
            html.Td(r['ts']),
            html.Td(f"${r['close']:,.2f}", style={'fontWeight': '600'}),
            html.Td(f"{int(r['positive_ticks']):,}", style={'color': '#00ff88'}),
            html.Td(f"{int(r['negative_ticks']):,}", style={'color': '#ff4757'}),
            html.Td(f"{r['tick_ratio']*100:.1f}%", style={'color': '#ffd700', 'fontWeight': '700'}),
            html.Td(f"{r['tick_rsi']:.1f}" if not pd.isna(r['tick_rsi']) else "-"),
            html.Td(r['signal'], style={
                'color': {'STRONG_BUY': '#00ff88', 'BUY': '#00d4aa', 'HOLD': '#ffd700',
                         'SELL': '#ff8c00', 'STRONG_SELL': '#ff4757'}.get(r['signal'], '#fff'),
                'fontWeight': '900'
            }),
            html.Td(r['confirmation_level'] if r['signal'] != 'HOLD' else '-'),
        ]) for _, r in td.iterrows()])
    ], className="data-table")

    sra = adf[adf['signal'].isin(['STRONG_BUY', 'BUY', 'SELL', 'STRONG_SELL'])]
    thr = mcs if mcs is not None else 0
    sr = sra[sra['confirmation_score'] >= thr].tail(15)

    if not sr.empty:
        srd = sr.iloc[::-1]
        srows = []
        for _, r in srd.iterrows():
            stype = r['signal']
            bc = {'STRONG_BUY': 'badge-strong-buy', 'BUY': 'badge-buy',
                  'SELL': 'badge-sell', 'STRONG_SELL': 'badge-strong-sell'}.get(stype, '')
            sl = {'STRONG_BUY': '🚀 خرید قوی', 'BUY': '📈 خرید',
                  'SELL': '📉 فروش', 'STRONG_SELL': '💥 فروش قوی'}.get(stype, stype)
            cl = r['confirmation_level']
            cc = CONFIRM_BADGE_CLASS.get(cl, 'confirm-none')
            atr = TradeCalculator.calculate_atr(kdf)
            ti, _ = bybit_client.get_ticker(symbol)
            spread = ti['spread'] if ti else 0
            params = TradeCalculator.compute_trade_params(stype, r['close'], atr, spread, money_manager, r['confirmation_score']) if atr else None
            ph = ""
            if params:
                ph = html.Div([
                    html.Span(f"L:{params['leverage']}x", className="trade-params"),
                    html.Span(f"R:R 1:{params['rr_ratio']}", className="trade-params", style={'background': 'rgba(187,134,252,0.15)', 'color': '#bb86fc'}),
                    html.Span(f"TP: ${params['tp_price']:,.4f}", className="trade-params", style={'background': 'rgba(0,255,136,0.15)', 'color': '#00ff88'}),
                    html.Span(f"SL: ${params['sl_price']:,.4f}", className="trade-params", style={'background': 'rgba(255,71,87,0.15)', 'color': '#ff4757'}),
                    html.Span(f"Risk: ${params['risk_usd']:.2f}", className="trade-params", style={'background': 'rgba(255,140,0,0.15)', 'color': '#ff8c00'}),
                    html.Span(f"M: ${params['margin_required']:,.0f}", className="trade-params", style={'background': 'rgba(187,134,252,0.15)', 'color': '#bb86fc'}),
                ])
            srows.append(html.Tr([
                html.Td(r['time'].strftime('%m-%d %H:%M'), style={'fontWeight': '600'}),
                html.Td(f"${r['close']:,.2f}", style={'fontWeight': '700'}),
                html.Td(f"{r['tick_ratio']*100:.1f}%", style={'color': '#ffd700', 'fontWeight': '700'}),
                html.Td(f"{r['tick_rsi']:.1f}" if not pd.isna(r['tick_rsi']) else "-"),
                html.Td(f"{r['signal_score']:.0f}",
                       style={'color': '#00ff88' if r['signal_score'] > 0 else '#ff4757', 'fontWeight': '700'}),
                html.Td(html.Span(sl, className=f"signal-badge {bc}")),
                html.Td(html.Span(f"{cl} ({r['confirmation_score']:.0f})",
                    className=f"confirm-badge {cc}"), title=r['confirmation_reasons']),
                html.Td(ph if params else "-"),
            ]))
        ssection = html.Div([
            html.Div([html.H3("⚡ سیگنال‌های ویژه + پارامترهای بهینه (Kelly)")],
                className="section-title", style={'borderRightColor': '#ffd700'}),
            html.Div([html.Table([
                html.Thead(html.Tr([
                    html.Th('زمان'), html.Th('قیمت'), html.Th('نسبت'), html.Th('RSI'),
                    html.Th('امتیاز'), html.Th('سیگنال'), html.Th('تایید'), html.Th('پارامترها'),
                ])),
                html.Tbody(srows)
            ], className="signals-table")], className="glass-card"),
        ], style={'marginBottom': '25px'})
    else:
        ssection = es

    htf = l.get('htf_trend', 0)
    hs = 'صعودی' if htf == 1 else ('نزولی' if htf == -1 else 'خنثی')
    stat = (f"✅ {datetime.now().strftime('%H:%M:%S')} | {symbol} | {len(adf)} کندل | "
            f"روند: {hs} | 🌐 {bybit_client.active_endpoint}")
    return (fm, fv, fr, fs, fri, scards, th, stat, ssection)


@app.callback(
    [Output('scanner-status-bar', 'children'),
     Output('scanner-margin-panel', 'children'),
     Output('scanner-open-trades', 'children'),
     Output('scanner-strong-signals', 'children'),
     Output('scanner-grid', 'children')],
    Input('scanner-refresh', 'n_intervals'))
def update_scanner(n):
    results = scanner.get_results()
    status = scanner.get_scan_status()
    cp = scanner.get_current_prices()

    fm, um = signal_db.get_free_margin()
    mup = (um / TOTAL_CAPITAL * 100) if TOTAL_CAPITAL > 0 else 0

    ot = signal_db.get_open_with_live_pnl(cp)
    oc = len(ot)
    op = float(ot['live_pnl_usd'].sum()) if not ot.empty else 0.0

    lss = status['last_scan'].strftime('%H:%M:%S') if status['last_scan'] else 'در حال اسکن...'
    sb = html.Div([
        html.Span(f"📡 آخرین اسکن: {lss}", style={'color': '#00ff88', 'fontWeight': '700', 'marginLeft': '20px'}),
        html.Span(f"🔄 وضعیت: {'در حال اسکن...' if status['running'] else 'آماده'}",
                  style={'color': '#ffd700' if status['running'] else '#00d4aa', 'fontWeight': '700', 'marginLeft': '20px'}),
        html.Span(f"💾 Trade های باز: {oc}", style={'color': '#ffd700', 'fontWeight': '700', 'marginLeft': '20px'}),
        html.Span(f"💰 PnL باز زنده: ${op:+.2f}",
                  style={'color': '#00ff88' if op >= 0 else '#ff4757', 'fontWeight': '700'}),
    ], className="glass-card", style={'padding': '15px', 'display': 'flex', 'gap': '30px', 'flexWrap': 'wrap'})

    mc = '#00ff88' if mup < 60 else ('#ffd700' if mup < 85 else '#ff4757')
    ms = "✅ خوب" if mup < 60 else ("⚠️ نزدیک حد" if mup < 85 else "🔴 تقریباً پر")

    # Kelly و Expectancy
    kelly = money_manager.calculate_kelly() * 100
    exp_pct, exp_usd, exp_q = money_manager.compute_expectancy()
    dd_f = money_manager.get_drawdown_factor()
    streak_f = money_manager.get_streak_factor()

    mp = html.Div([
        html.Div([html.H3("🏦 مدیریت سرمایه پیشرفته + 🧠 Kelly/Expectancy")],
            className="section-title", style={'borderRightColor': '#bb86fc'}),
        html.Div([
            html.Div([
                html.Div(f"💰 سرمایه کل: ${TOTAL_CAPITAL:,.0f}", style={'color': '#fff', 'fontWeight': '900', 'fontSize': '15px'}),
                html.Div(f"📊 مارجین استفاده: ${um:,.2f}", style={'color': '#ffd700', 'fontWeight': '700', 'fontSize': '13px', 'marginTop': '5px'}),
                html.Div(f"🆓 مارجین آزاد: ${fm:,.2f}", style={'color': '#00ff88', 'fontWeight': '700', 'fontSize': '13px', 'marginTop': '5px'}),
                html.Div(f"📈 استفاده: {mup:.1f}%", style={'color': mc, 'fontWeight': '900', 'fontSize': '13px', 'marginTop': '5px'}),
            ], style={'width': '280px'}),
            html.Div([
                html.Div(f"🧠 Kelly Optimal: {kelly:.2f}%", style={'color': '#bb86fc', 'fontWeight': '900', 'fontSize': '14px', 'marginBottom': '5px'}),
                html.Div(f"🎯 Expectancy: {exp_pct:+.2f}% (${exp_usd:+.2f}/trade)", style={
                    'color': '#00ff88' if exp_pct > 0 else '#ff4757', 'fontWeight': '900', 'fontSize': '14px', 'marginBottom': '5px'}),
                html.Div(f"{exp_q}", style={'fontSize': '12px', 'marginTop': '5px'}),
                html.Div(f"📊 Streak×{streak_f:.2f} | DD×{dd_f:.2f}", style={'color': '#8892b0', 'fontSize': '11px', 'marginTop': '5px'}),
            ], style={'flex': '1', 'marginRight': '20px'}),
            html.Div([
                html.Div(f"میزان استفاده: {mup:.1f}%", style={'color': mc, 'fontWeight': '700', 'fontSize': '12px', 'marginBottom': '5px'}),
                html.Div(className="margin-bar", children=[
                    html.Div(className="margin-used", style={'width': f'{min(mup, 100)}%'})
                ]),
                html.Div(ms, style={'color': mc, 'fontWeight': '700', 'fontSize': '11px', 'marginTop': '8px'}),
            ], style={'width': '250px'}),
        ], style={'display': 'flex', 'flexWrap': 'wrap', 'gap': '20px'}),
    ], className="glass-card", style={'marginBottom': '15px'})

    if not ot.empty:
        orows = []
        for _, r in ot.sort_values('timestamp', ascending=False).iterrows():
            pc = 'live-pnl-positive' if r['live_pnl_usd'] >= 0 else 'live-pnl-negative'
            bc = 'badge-strong-buy' if 'BUY' in r['signal_type'] else 'badge-strong-sell'
            bl = '🚀 LONG' if 'BUY' in r['signal_type'] else '💥 SHORT'
            et = pd.to_datetime(r['timestamp']).strftime('%m-%d %H:%M')
            tp = datetime.now() - pd.to_datetime(r['timestamp'])
            h, rem = divmod(tp.seconds, 3600)
            m, _ = divmod(rem, 60)
            ts = f"{tp.days}d {h}h" if tp.days > 0 else (f"{h}h {m}m" if h > 0 else f"{m}m")
            orows.append(html.Tr([
                html.Td(et, style={'fontSize': '11px'}),
                html.Td(html.Span(r['symbol'], style={'fontWeight': '900', 'color': '#ffd700'})),
                html.Td(html.Span(bl, className=f"signal-badge {bc}")),
                html.Td(f"${r['entry_price']:,.4f}", style={'fontSize': '11px'}),
                html.Td(f"${r['current_price']:,.4f}", style={'fontSize': '11px', 'fontWeight': '700'}),
                html.Td(f"{int(r['leverage'])}x", style={'color': '#ffd700', 'fontWeight': '700'}),
                html.Td(f"${r['margin_used']:,.2f}", style={'color': '#bb86fc', 'fontWeight': '700', 'fontSize': '11px'}),
                html.Td(f"${r['risk_usd']:,.2f}", style={'color': '#ff8c00', 'fontSize': '11px'}),
                html.Td(html.Div([
                    html.Div(f"🎯 ${r['tp_price']:,.4f}", style={'color': '#00ff88', 'fontSize': '11px'}),
                    html.Div(f"{r['dist_tp_pct']:+.2f}%", style={'color': '#8892b0', 'fontSize': '10px'}),
                ])),
                html.Td(html.Div([
                    html.Div(f"🛑 ${r['sl_price']:,.4f}", style={'color': '#ff4757', 'fontSize': '11px'}),
                    html.Div(f"{r['dist_sl_pct']:+.2f}%", style={'color': '#8892b0', 'fontSize': '10px'}),
                ])),
                html.Td(ts, style={'color': '#8892b0', 'fontSize': '11px'}),
                html.Td(f"{r['live_pnl_percent']:+.2f}%", className=pc),
                html.Td(f"${r['live_pnl_usd']:+.2f}", className=pc),
            ], className="open-trade-row"))
        os_ = html.Div([
            html.Div([html.H3(f"🔥 Trade های باز فعال ({oc})")],
                className="section-title", style={'borderRightColor': '#ffd700'}),
            html.Div([html.Table([
                html.Thead(html.Tr([
                    html.Th('زمان'), html.Th('نماد'), html.Th('نوع'), html.Th('ورود'),
                    html.Th('فعلی'), html.Th('L'), html.Th('مارجین'), html.Th('ریسک'),
                    html.Th('TP'), html.Th('SL'), html.Th('مدت'), html.Th('PnL %'), html.Th('PnL $'),
                ])),
                html.Tbody(orows),
            ], className="signals-table", style={'overflowX': 'auto'})], className="glass-card"),
        ], style={'marginBottom': '25px'})
    else:
        os_ = html.Div([
            html.Div([html.H3("🔥 Trade های باز فعال")], className="section-title"),
            html.Div([html.P("💤 در حال حاضر trade بازی وجود ندارد...",
                             style={'textAlign': 'center', 'color': '#8892b0', 'padding': '30px'})],
                     className="glass-card"),
        ], style={'marginBottom': '25px'})

    ss = []
    for sym, r in results.items():
        if r['signal'] in ('STRONG_BUY', 'STRONG_SELL') and r['confirm_score'] >= 70:
            ss.append(r)
    ss.sort(key=lambda x: x['confirm_score'], reverse=True)

    if ss:
        rows = []
        for r in ss:
            params = TradeCalculator.compute_trade_params(
                r['signal'], r['price'], r['atr'], r['spread'],
                money_manager, r['confirm_score'])
            if not params: continue
            bc = 'badge-strong-buy' if 'BUY' in r['signal'] else 'badge-strong-sell'
            bl = '🚀 خرید قوی' if 'BUY' in r['signal'] else '💥 فروش قوی'
            f = params['factors']
            rows.append(html.Tr([
                html.Td(html.Span(r['symbol'], style={'fontWeight': '900', 'fontSize': '16px', 'color': '#ffd700'})),
                html.Td(f"${r['price']:,.4f}", style={'fontWeight': '700'}),
                html.Td(html.Span(bl, className=f"signal-badge {bc}")),
                html.Td(f"{r['confirm_score']:.0f}/100", style={'color': '#00ff88', 'fontWeight': '900'}),
                html.Td(html.Div([
                    html.Span(f"⚡ {params['leverage']}x", className="trade-params"),
                    html.Span(f"R:R 1:{params['rr_ratio']}", className="trade-params", style={'background': 'rgba(187,134,252,0.15)', 'color': '#bb86fc'}),
                ])),
                html.Td(html.Div([
                    html.Div(f"🎯 TP: ${params['tp_price']:,.4f} (+{params['tp_distance_pct']:.2f}%)",
                            style={'color': '#00ff88', 'fontSize': '11px'}),
                    html.Div(f"🛑 SL: ${params['sl_price']:,.4f} (-{params['sl_distance_pct']:.2f}%)",
                            style={'color': '#ff4757', 'fontSize': '11px'}),
                ])),
                html.Td(html.Div([
                    html.Div(f"💰 Risk: ${params['risk_usd']:.2f}", style={'color': '#ff8c00', 'fontSize': '11px', 'fontWeight': '700'}),
                    html.Div(f"📊 Size: ${params['position_size_usd']:,.0f}", style={'color': '#ffd700', 'fontSize': '11px'}),
                    html.Div(f"🏦 Margin: ${params['margin_required']:,.2f}", style={'color': '#bb86fc', 'fontSize': '11px'}),
                ])),
                html.Td(html.Div([
                    html.Span(f"Kelly:{f.get('kelly',0):.1f}%", className="factor-tag", style={'background': 'rgba(187,134,252,0.2)', 'color': '#bb86fc'}),
                    html.Span(f"Vol×{f.get('volatility',1):.2f}", className="factor-tag", style={'background': 'rgba(0,212,170,0.2)', 'color': '#00d4aa'}),
                    html.Span(f"Q×{f.get('quality',1):.2f}", className="factor-tag", style={'background': 'rgba(255,215,0,0.2)', 'color': '#ffd700'}),
                    html.Span(f"Streak×{f.get('streak',1):.2f}", className="factor-tag", style={'background': 'rgba(255,140,0,0.2)', 'color': '#ff8c00'}),
                    html.Span(f"DD×{f.get('drawdown',1):.2f}", className="factor-tag", style={'background': 'rgba(255,71,87,0.2)', 'color': '#ff4757'}),
                ])),
                html.Td(html.Div([
                    html.Div(f"🎁 Net: +{params['net_tp_pct']:.2f}%", style={'color': '#00ff88', 'fontWeight': '700', 'fontSize': '11px'}),
                    html.Div(f"💵 Est: ${params['potential_profit']:+.2f}", style={'color': '#00ff88', 'fontWeight': '700', 'fontSize': '11px'}),
                ])),
            ]))
        ss_ = html.Div([
            html.Div([html.H3(f"🎯 سیگنال‌های قوی جدید ({len(ss)})")],
                className="section-title", style={'borderRightColor': '#00ff88'}),
            html.Div([html.Table([
                html.Thead(html.Tr([
                    html.Th('نماد'), html.Th('قیمت'), html.Th('سیگنال'), html.Th('تایید'),
                    html.Th('L/R:R'), html.Th('TP/SL'), html.Th('Risk/Margin'), html.Th('فاکتورها'), html.Th('Est'),
                ])),
                html.Tbody(rows),
            ], className="signals-table", style={'overflowX': 'auto'})], className="glass-card"),
        ], style={'marginBottom': '25px'})
    else:
        ss_ = html.Div([
            html.Div([html.H3("🎯 سیگنال‌های قوی جدید")], className="section-title"),
            html.Div([html.P("🔍 در حال حاضر سیگنال قوی جدیدی وجود ندارد...",
                             style={'textAlign': 'center', 'color': '#8892b0', 'padding': '30px'})],
                     className="glass-card"),
        ], style={'marginBottom': '25px'})

    cards = []
    for sym in SCAN_SYMBOLS:
        r = results.get(sym)
        if not r:
            cards.append(html.Div([
                html.Div(sym, className="scanner-sym", style={'color': '#555'}),
                html.Div("⏳ در انتظار اسکن...", className="scanner-price"),
            ], className="scanner-card"))
            continue
        sc = {'STRONG_BUY': '#00ff88', 'BUY': '#00d4aa', 'HOLD': '#ffd700',
              'SELL': '#ff8c00', 'STRONG_SELL': '#ff4757'}.get(r['signal'], '#8892b0')
        st = {'STRONG_BUY': '🚀 خرید قوی', 'BUY': '📈 خرید', 'HOLD': '⏸️ نگهداری',
              'SELL': '📉 فروش', 'STRONG_SELL': '💥 فروش قوی'}.get(r['signal'], '?')
        ht = '📈' if r['htf_trend'] == 1 else ('📉' if r['htf_trend'] == -1 else '➖')
        cp = r['confirm_score']
        cards.append(html.Div([
            html.Div([
                html.Span(sym, className="scanner-sym"),
                html.Span(ht, style={'marginLeft': '8px', 'fontSize': '18px'}),
            ]),
            html.Div(f"${r['price']:,.4f}", className="scanner-price"),
            html.Div([html.Span(st, style={'color': sc, 'fontWeight': '900', 'fontSize': '14px'})],
                style={'marginBottom': '8px'}),
            html.Div([
                html.Div(f"تایید: {cp:.0f}/100",
                    style={'color': '#00ff88' if cp >= 70 else ('#ffd700' if cp >= 40 else '#ff8c8c'),
                           'fontWeight': '700', 'fontSize': '12px'}),
                html.Div(className="progress-bar", children=[
                    html.Div(className="progress-fill", style={'width': f'{cp}%'})
                ])
            ]),
            html.Div(f"نسبت: {r['tick_ratio']*100:.1f}% | Vol: {r['volume']:,.0f}",
                style={'color': '#8892b0', 'fontSize': '11px', 'marginTop': '6px'}),
        ], className="scanner-card", style={'borderColor': sc if r['signal'] != 'HOLD' else 'rgba(255,255,255,0.08)'}))
    return sb, mp, os_, ss_, cards


@app.callback(
    [Output('performance-summary-cards', 'children'),
     Output('expectancy-section', 'children'),
     Output('equity-chart', 'figure'),
     Output('winrate-chart', 'figure'),
     Output('symbol-stats-table', 'children'),
     Output('history-table', 'children')],
    Input('perf-refresh', 'n_intervals'))
def update_performance(n):
    cp = scanner.get_current_prices()
    ls = signal_db.get_live_statistics(cp)
    cs = ls['closed']
    ot = ls['open_trades']
    alls = signal_db.get_all_signals(limit=500)

    # Expectancy و Kelly
    exp_pct, exp_usd, exp_q = money_manager.compute_expectancy()
    kelly = money_manager.calculate_kelly() * 100
    exp_by = money_manager.compute_expectancy_by_type()

    mc = '#00ff88' if ls['margin_usage_pct'] < 60 else ('#ffd700' if ls['margin_usage_pct'] < 85 else '#ff4757')
    cards = html.Div([
        html.Div([
            html.Div(f"🎯 Expectancy", style={'fontSize': '13px', 'color': '#bb86fc'}),
            html.Div(f"{exp_pct:+.2f}%", style={'fontSize': '32px',
                'color': '#00ff88' if exp_pct > 0 else '#ff4757', 'fontWeight': '900', 'marginTop': '8px'}),
            html.Div(f"${exp_usd:+.2f} per trade", style={'fontSize': '11px', 'color': '#8892b0', 'marginTop': '4px'}),
            html.Div(exp_q, style={'fontSize': '12px', 'color': '#bb86fc', 'fontWeight': '700', 'marginTop': '4px'}),
        ], className="summary-card", style={'border': '3px solid #bb86fc', 'minWidth': '240px'}),
        html.Div([
            html.Div(f"🧠 Kelly", style={'fontSize': '13px', 'color': '#bb86fc'}),
            html.Div(f"{kelly:.2f}%", style={'fontSize': '28px', 'color': '#bb86fc', 'fontWeight': '900', 'marginTop': '8px'}),
            html.Div(f"Half-Kelly محافظه‌کارانه", style={'fontSize': '11px', 'color': '#8892b0', 'marginTop': '4px'}),
        ], className="summary-card", style={'border': '2px solid #bb86fc'}),
        html.Div([
            html.Div(f"🔥 PnL کلی زنده", style={'fontSize': '13px', 'color': '#ffd700'}),
            html.Div(f"${ls['total_live_pnl_usd']:+.2f}", style={'fontSize': '28px',
                'color': '#00ff88' if ls['total_live_pnl_usd'] >= 0 else '#ff4757', 'fontWeight': '900', 'marginTop': '8px'}),
            html.Div(f"{ls['total_live_pnl_pct']:+.2f}% | بسته: ${ls['closed_pnl_usd']:+.2f} | باز: ${ls['open_pnl_usd']:+.2f}",
                style={'fontSize': '11px', 'color': '#8892b0', 'marginTop': '4px'}),
        ], className="summary-card", style={'border': '3px solid #ffd700', 'minWidth': '260px'}),
        html.Div([
            html.Div(f"🏦 مارجین", style={'fontSize': '13px', 'color': '#bb86fc'}),
            html.Div(f"{ls['margin_usage_pct']:.1f}%", style={'fontSize': '28px', 'color': mc, 'fontWeight': '900', 'marginTop': '8px'}),
            html.Div(f"استفاده: ${ls['used_margin']:,.2f} | آزاد: ${ls['free_margin']:,.2f}",
                style={'fontSize': '11px', 'color': '#8892b0', 'marginTop': '4px'}),
        ], className="summary-card", style={'border': '2px solid #bb86fc'}),
        html.Div([
            html.Div(f"📊 کل معاملات (بسته)", style={'fontSize': '13px', 'color': '#8892b0'}),
            html.Div(f"{cs['total_trades']}", style={'fontSize': '28px', 'color': '#fff', 'fontWeight': '900', 'marginTop': '8px'}),
            html.Div(f"{cs['wins']} برد / {cs['losses']} باخت | {ls['open_count']} باز",
                style={'fontSize': '12px', 'color': '#8892b0', 'marginTop': '4px'}),
        ], className="summary-card"),
        html.Div([
            html.Div(f"🎯 Win Rate", style={'fontSize': '13px', 'color': '#8892b0'}),
            html.Div(f"{cs['win_rate']:.1f}%", style={'fontSize': '28px',
                'color': '#00ff88' if cs['win_rate'] >= 55 else ('#ffd700' if cs['win_rate'] >= 45 else '#ff4757'),
                'fontWeight': '900', 'marginTop': '8px'}),
        ], className="summary-card", style={'border': '2px solid #00d4aa'}),
        html.Div([
            html.Div(f"📈 Profit Factor", style={'fontSize': '13px', 'color': '#8892b0'}),
            html.Div(f"{cs['profit_factor']:.2f}", style={'fontSize': '28px',
                'color': '#00ff88' if cs['profit_factor'] >= 1.5 else ('#ffd700' if cs['profit_factor'] >= 1 else '#ff4757'),
                'fontWeight': '900', 'marginTop': '8px'}),
        ], className="summary-card"),
        html.Div([
            html.Div(f"📉 Max DD", style={'fontSize': '13px', 'color': '#8892b0'}),
            html.Div(f"{cs['max_drawdown']:.1f}%", style={'fontSize': '28px',
                'color': '#ff4757' if cs['max_drawdown'] > 20 else '#ffd700',
                'fontWeight': '900', 'marginTop': '8px'}),
        ], className="summary-card"),
    ])

    # Expectancy by signal type table
    if not exp_by.empty:
        exp_rows = []
        for _, r in exp_by.iterrows():
            ec = '#00ff88' if r['expectancy_pct'] > 0 else '#ff4757'
            exp_rows.append(html.Tr([
                html.Td(html.Span(r['signal_type'], style={'fontWeight': '900', 'color': '#ffd700'})),
                html.Td(f"{int(r['trades'])}", style={'fontWeight': '700'}),
                html.Td(f"{r['win_rate']*100:.1f}%", style={'color': '#00ff88', 'fontWeight': '700'}),
                html.Td(f"{r['avg_win']*100:+.2f}%", style={'color': '#00ff88'}),
                html.Td(f"{-r['avg_loss']*100:+.2f}%", style={'color': '#ff4757'}),
                html.Td(f"{r['expectancy_pct']:+.2f}%", style={'color': ec, 'fontWeight': '900', 'fontSize': '14px'}),
                html.Td(f"${r['expectancy_usd']:+.2f}", style={'color': ec, 'fontWeight': '700'}),
            ]))
        exp_s = html.Div([
            html.Div([html.H3("🎯 Expectancy بر اساس نوع سیگنال")],
                className="section-title", style={'borderRightColor': '#bb86fc'}),
            html.Div([html.Table([
                html.Thead(html.Tr([
                    html.Th('نوع'), html.Th('تعداد'), html.Th('Win Rate'),
                    html.Th('میانگین برد'), html.Th('میانگین باخت'),
                    html.Th('Expectancy %'), html.Th('Expectancy $'),
                ])),
                html.Tbody(exp_rows),
            ], className="data-table")], className="glass-card"),
        ], style={'marginBottom': '20px'})
    else:
        exp_s = html.Div()

    # نمودار رشد سرمایه
    eq = ls['live_equity_curve']
    if len(eq) > 1:
        xd = list(range(len(eq)))
        fe = go.Figure()
        ce = cs['total_trades'] + 1 if cs['total_trades'] > 0 else 1
        fe.add_trace(go.Scatter(x=xd[:ce], y=eq[:ce],
            mode='lines+markers', name='Trade های بسته',
            line=dict(color='#00ff88', width=3), marker=dict(size=6, color='#00ff88'),
            fill='tozeroy', fillcolor='rgba(0,255,136,0.1)'))
        if len(eq) > ce:
            fe.add_trace(go.Scatter(x=xd[ce-1:], y=eq[ce-1:],
                mode='lines+markers', name='Trade های باز (زنده)',
                line=dict(color='#ffd700', width=3, dash='dot'),
                marker=dict(size=8, color='#ffd700', symbol='star'),
                fill='tozeroy', fillcolor='rgba(255,215,0,0.15)'))
        fe.add_hline(y=TOTAL_CAPITAL, line_dash="dash", line_color="#ffd700",
            annotation_text=f"سرمایه اولیه ${TOTAL_CAPITAL:.0f}", annotation_font_color="#ffd700")
        fp = eq[-1] - TOTAL_CAPITAL
        fp_p = (fp / TOTAL_CAPITAL) * 100
        fe.add_annotation(x=xd[-1], y=eq[-1],
            text=f"💰 فعلی: ${eq[-1]:,.2f} ({fp_p:+.1f}%)",
            showarrow=True, arrowhead=2, ax=-40, ay=-40,
            font=dict(size=14, color='#00ff88' if fp >= 0 else '#ff4757', weight='bold'),
            bgcolor='rgba(0,50,30,0.9)', bordercolor='#00ff88', borderwidth=2, borderpad=8)
        fe.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(22, 33, 62, 0.5)', height=450,
            margin=dict(l=50, r=30, t=30, b=50),
            xaxis=dict(title='تعداد معاملات', gridcolor='rgba(255,255,255,0.05)'),
            yaxis=dict(title='سرمایه ($)', gridcolor='rgba(255,255,255,0.05)'),
            showlegend=True, legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1))
    else:
        fe = go.Figure()
        fe.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(22, 33, 62, 0.5)', height=450)
        fe.add_annotation(text="📊 داده‌ای برای نمایش نیست...",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="#8892b0"))

    # ✅ نمودار وین‌ریت - اصلاح شده برای جلوگیری از خطای Pie Chart
    if cs['total_trades'] > 0:
        fwr = make_subplots(rows=1, cols=2,
            specs=[[{"type": "pie"}, {"type": "xy"}]],
            subplot_titles=("نسبت برد/باخت", "توزیع PnL معاملات"))
        fwr.add_trace(go.Pie(labels=['برد', 'باخت'],
            values=[cs['wins'], cs['losses']],
            marker=dict(colors=['#00ff88', '#ff4757']), hole=0.55,
            textinfo='label+percent', textfont=dict(size=14, color='white')), row=1, col=1)
        closed = alls[alls['status'] == 'CLOSED']
        if not closed.empty:
            pnl = closed['pnl_percent'].dropna().tolist()
            colors = ['#00ff88' if p > 0 else '#ff4757' for p in pnl]
            fwr.add_trace(go.Histogram(x=pnl, marker_color=colors, nbinsx=20,
                name='PnL %', opacity=0.85), row=1, col=2)
            # ✅ استفاده از Scatter به جای add_vline برای جلوگیری از خطای Pie Chart
            if pnl:
                y_min = min(pnl)
                y_max = max(pnl)
                fwr.add_trace(go.Scatter(
                    x=[0, 0], y=[y_min, y_max],
                    mode='lines', line=dict(color="#ffd700", dash="dash", width=2),
                    showlegend=False, name='Zero Line'
                ), row=1, col=2)
        fwr.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(22, 33, 62, 0.5)', height=400, showlegend=False,
            margin=dict(l=50, r=30, t=50, b=30))
    else:
        fwr = go.Figure()
        fwr.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(22, 33, 62, 0.5)', height=400)
        fwr.add_annotation(text="هنوز معامله بسته‌ای وجود ندارد", xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False, font=dict(size=16, color="#8892b0"))

    # جدول آمار نمادها
    bs = cs.get('by_symbol', pd.DataFrame())
    if not bs.empty:
        srows = []
        for _, r in bs.iterrows():
            srows.append(html.Tr([
                html.Td(html.Span(r['symbol'], style={'fontWeight': '900', 'color': '#ffd700'})),
                html.Td(f"{int(r['total_trades'])}", style={'fontWeight': '700'}),
                html.Td(f"{int(r['wins'])}/{int(r['total_trades'])}", style={'color': '#00ff88'}),
                html.Td(f"{r['win_rate']:.1f}%", style={
                    'color': '#00ff88' if r['win_rate'] >= 55 else ('#ffd700' if r['win_rate'] >= 45 else '#ff4757'),
                    'fontWeight': '900'}),
                html.Td(f"${r['total_pnl']:+.2f}", style={
                    'color': '#00ff88' if r['total_pnl'] > 0 else '#ff4757', 'fontWeight': '700'}),
                html.Td(f"{r['avg_pnl']:+.2f}%", style={'fontWeight': '600'}),
            ]))
        st_ = html.Table([
            html.Thead(html.Tr([
                html.Th('نماد'), html.Th('معاملات'), html.Th('برد/کل'),
                html.Th('Win Rate'), html.Th('کل PnL'), html.Th('میانگین PnL'),
            ])),
            html.Tbody(srows),
        ], className="data-table")
    else:
        st_ = html.Div("داده‌ای موجود نیست", style={'textAlign': 'center', 'color': '#8892b0', 'padding': '20px'})

    # تاریخچه کامل
    hrows = []
    if not ot.empty:
        for _, r in ot.sort_values('timestamp', ascending=False).iterrows():
            ts = pd.to_datetime(r['timestamp']).strftime('%m-%d %H:%M')
            pc = 'live-pnl-positive' if r['live_pnl_usd'] >= 0 else 'live-pnl-negative'
            bc = 'badge-strong-buy' if 'BUY' in r['signal_type'] else 'badge-strong-sell'
            bl = '🚀 LONG' if 'BUY' in r['signal_type'] else '💥 SHORT'
            hrows.append(html.Tr([
                html.Td(ts, style={'fontSize': '11px'}),
                html.Td(html.Span(r['symbol'], style={'fontWeight': '900', 'color': '#ffd700'})),
                html.Td(html.Span(bl, className=f"signal-badge {bc}")),
                html.Td(f"${r['entry_price']:,.4f}", style={'fontSize': '11px'}),
                html.Td(f"${r['current_price']:,.4f}", style={'fontSize': '11px', 'fontWeight': '700'}),
                html.Td(f"${r['tp_price']:,.4f}", style={'color': '#00ff88', 'fontSize': '11px'}),
                html.Td(f"${r['sl_price']:,.4f}", style={'color': '#ff4757', 'fontSize': '11px'}),
                html.Td(f"{int(r['leverage'])}x", style={'color': '#ffd700', 'fontWeight': '700'}),
                html.Td(f"${r['margin_used']:,.2f}", style={'color': '#bb86fc', 'fontSize': '11px'}),
                html.Td(html.Span("⏳ باز", className="trade-open")),
                html.Td('-', style={'fontSize': '11px'}),
                html.Td(f"{r['live_pnl_percent']:+.2f}%", className=pc),
                html.Td(f"${r['live_pnl_usd']:+.2f}", className=pc),
            ], className="open-trade-row"))
    cl = alls[alls['status'] == 'CLOSED']
    if not cl.empty:
        for _, r in cl.iterrows():
            ts = pd.to_datetime(r['timestamp']).strftime('%m-%d %H:%M')
            oc_ = {'WIN': 'trade-win', 'LOSS': 'trade-loss'}.get(r['outcome'], '')
            ot_ = {'WIN': '✅ برد', 'LOSS': '❌ باخت'}.get(r['outcome'], '-')
            ps = f"{r['pnl_percent']:+.2f}%" if not pd.isna(r['pnl_percent']) else '-'
            pus = f"${r['pnl_usd']:+.2f}" if not pd.isna(r['pnl_usd']) else '-'
            bc = 'badge-strong-buy' if 'BUY' in r['signal_type'] else 'badge-strong-sell'
            bl = '🚀 LONG' if 'BUY' in r['signal_type'] else '💥 SHORT'
            mu = r.get('margin_used', 0) or 0
            hrows.append(html.Tr([
                html.Td(ts, style={'fontSize': '11px'}),
                html.Td(html.Span(r['symbol'], style={'fontWeight': '900', 'color': '#ffd700'})),
                html.Td(html.Span(bl, className=f"signal-badge {bc}")),
                html.Td(f"${r['entry_price']:,.4f}", style={'fontSize': '11px'}),
                html.Td(f"${r['exit_price']:,.4f}", style={'fontSize': '11px', 'color': '#8892b0'}),
                html.Td(f"${r['tp_price']:,.4f}", style={'color': '#00ff88', 'fontSize': '11px'}),
                html.Td(f"${r['sl_price']:,.4f}", style={'color': '#ff4757', 'fontSize': '11px'}),
                html.Td(f"{int(r['leverage'])}x", style={'color': '#ffd700', 'fontWeight': '700'}),
                html.Td(f"${mu:,.2f}", style={'color': '#bb86fc', 'fontSize': '11px'}),
                html.Td(html.Span(ot_, className=oc_)),
                html.Td(f"${r['exit_price']:,.4f}", style={'fontSize': '11px'}),
                html.Td(ps, style={
                    'color': '#00ff88' if not pd.isna(r['pnl_percent']) and r['pnl_percent'] > 0 else '#ff4757',
                    'fontWeight': '700'} if not pd.isna(r['pnl_percent']) else {}),
                html.Td(pus, style={
                    'color': '#00ff88' if not pd.isna(r['pnl_usd']) and r['pnl_usd'] > 0 else '#ff4757',
                    'fontWeight': '700'} if not pd.isna(r['pnl_usd']) else {}),
            ]))

    if hrows:
        ht_ = html.Table([
            html.Thead(html.Tr([
                html.Th('زمان'), html.Th('نماد'), html.Th('نوع'), html.Th('ورود'),
                html.Th('فعلی/خروج'), html.Th('TP'), html.Th('SL'), html.Th('L'),
                html.Th('مارجین'), html.Th('وضعیت'), html.Th('خروج'), html.Th('PnL %'), html.Th('PnL $'),
            ])),
            html.Tbody(hrows),
        ], className="signals-table")
    else:
        ht_ = html.Div("هنوز سیگنالی ثبت نشده است...",
            style={'textAlign': 'center', 'color': '#8892b0', 'padding': '30px'})

    return cards, exp_s, fe, fwr, st_, ht_


# ==============================================================================
# 🚀 اجرا
# ==============================================================================
def open_browser():
    try:
        webbrowser.open_new("http://127.0.0.1:8050")
        print("🌐 مرورگر باز شد: http://127.0.0.1:8050")
    except Exception as e:
        print(f"⚠️ خطا در باز کردن مرورگر: {e}")


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Starting BITMOON618 Dash Server v5.0 (Advanced Money Management)")
    print(f"💾 DB: {DB_PATH}")
    print(f"📡 اسکنر: {len(SCAN_SYMBOLS)} ارز")
    print(f"💰 سرمایه: ${TOTAL_CAPITAL:,.0f}")
    print(f"🔥 Trade های باز: {len(signal_db.get_open_signals())}")
    u = signal_db.get_used_margin()
    print(f"🏦 مارجین: ${u:,.2f} استفاده / ${TOTAL_CAPITAL - u:,.2f} آزاد")
    k = money_manager.calculate_kelly() * 100
    ep, eu, eq = money_manager.compute_expectancy()
    print(f"🧠 Kelly Optimal: {k:.2f}%")
    print(f"🎯 Expectancy: {ep:+.2f}% (${eu:+.2f}/trade) - {eq}")
    print("=" * 60)

    ok, err, price = bybit_client.test_connection()
    if ok:
        print(f"✅ اتصال: BTC ${price:,.2f}")
    else:
        print(f"⚠️ خطا: {err}")

    # ✅ فقط در پروسه اصلی اجرا می‌شود (نه reloader)
    if not os.environ.get('WERKZEUG_RUN_MAIN'):
        Timer(1.5, open_browser).start()

    app.run(debug=True, port=8050, host='127.0.0.1')