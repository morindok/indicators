# -*- coding: utf-8 -*-
"""
🌌 Golden Spiral Fractal LIVE Trader v5.2 — REALISTIC FILL
✅ رفع سراب بک‌تست: ورود مارکت روی CLOSE کندل (نه لیمیت غیرممکن روی سطح)
✅ علّی‌سازی: سطوح S/R فقط از کندل‌های قبل از کندل سیگنال
✅ یکسان‌سازی کامل بک‌تست و زنده: پنجره، شرط touch، خروج با High/Low
"""
import numpy as np
import pandas as pd
import requests
import time
import threading
import sqlite3
import webbrowser
import urllib3
import os
import json
from datetime import datetime
from threading import Timer
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import dash
from dash import dcc, html, Input, Output, State, ALL, callback_context, no_update
import plotly.graph_objects as go

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CANDIDATE_BASE = [
    'BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT',
    'DOTUSDT','LINKUSDT','POLUSDT','UNIUSDT','LTCUSDT','ATOMUSDT','ETCUSDT','XLMUSDT',
    'ALGOUSDT','VETUSDT','FILUSDT','APTUSDT','ARBUSDT','OPUSDT','SUIUSDT','NEARUSDT',
    'TIAUSDT','TRXUSDT','BCHUSDT','INJUSDT','SEIUSDT','TONUSDT',
    'PEPEUSDT','SHIBUSDT','WIFUSDT','BONKUSDT','FLOKIUSDT','WLDUSDT','JUPUSDT','STRKUSDT',
    'MANTAUSDT','PYTHUSDT','JTOUSDT','TNSRUSDT','ENAUSDT','ETHFIUSDT','WUSDT','OMNIUSDT',
    'NOTUSDT','IOUSDT','ZKUSDT','ZROUSDT','LISTAUSDT','BNXUSDT','KASUSDT','ONDOUSDT',
    'PENDLEUSDT','AEROUSDT','FETUSDT','RNDRUSDT','TAOUSDT','IMXUSDT',
    'GALAUSDT','SANDUSDT','MANAUSDT','AXSUSDT','ENJUSDT','CHZUSDT','PEOPLEUSDT','LRCUSDT',
    'COMPUSDT','AAVEUSDT','MKRUSDT','SNXUSDT','CRVUSDT','SUSHIUSDT','1INCHUSDT','BALUSDT',
    'KNCUSDT','BNTUSDT','YFIUSDT','BANDUSDT','GRTUSDT','ICPUSDT','EGLDUSDT','FTMUSDT','ONEUSDT',
    'ROSEUSDT','ZILUSDT','CELOUSDT','HBARUSDT','THETAUSDT','XTZUSDT','EOSUSDT','IOTAUSDT',
    'NEOUSDT','WAVESUSDT','KAVAUSDT','RUNEUSDT','LDOUSDT','RPLUSDT','BLURUSDT','DYDXUSDT',
    'GMXUSDT','PERPUSDT','JOEUSDT','CAKEUSDT','BSWUSDT','APEUSDT','GMTUSDT','MAGICUSDT','STGUSDT',
    'CFXUSDT','COTIUSDT','STXUSDT','FLOWUSDT','MINAUSDT','ZECUSDT','DASHUSDT','XMRUSDT',
    'ENSUSDT','ARUSDT','MASKUSDT','SKLUSDT','STORJUSDT','ANKRUSDT','CELRUSDT','HOTUSDT',
    'IOSTUSDT','IOTXUSDT','SXPUSDT','WOOUSDT',
]

QUAL_LOOKBACK = 10000
QUAL_LTF_LIMIT = 1000
QUAL_RECALC = 1
QUAL_MIN_STR = 100
# ⚠️ با بک‌تست واقع‌گرایانه، آستانه 2000% تقریباً هیچ ارزی رد نمی‌شود؛ مقدار منطقی تنظیم کنید
QUAL_MIN_RETURN = 300
LIVE_MIN_STR = 100

CFG = {
    'capital': 500.0, 'leverage': 10, 'risk_pct': 0.20, 'rr': 2.0,
    'sl_pct': 0.008, 'window': 150, 'min_strength': 95,
    'touch_pct': 0.0025, 'interval': '60', 'lookback': 500, 'max_open': 5,
}
COMMISSION = 0.00055
SPREAD_PCT = 0.0003
SCAN_INTERVAL = 60
COOLDOWN_SEC = 1800
DB_PATH = "spiral_signals.db"

SYS_MSG = {'text': '', 'color': '#00ff88', 'time': None}
def set_msg(txt, color='#00ff88'):
    SYS_MSG['text'] = txt
    SYS_MSG['color'] = color
    SYS_MSG['time'] = datetime.now().strftime('%H:%M:%S')
    print(f"[{SYS_MSG['time']}] {txt}")

CUSTOM_CSS = '''
@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;700;900&display=swap');
* { font-family: 'Vazirmatn', Tahoma, sans-serif; box-sizing: border-box; }
body { background: linear-gradient(135deg,#0a0e27 0%,#1a1f3a 50%,#0a0e27 100%); margin:0; min-height:100vh; direction:rtl; }
.main-header { background:linear-gradient(135deg,rgba(26,26,46,.95),rgba(22,33,62,.95)); padding:22px; border-radius:20px; margin-bottom:18px; text-align:center; border:1px solid rgba(240,185,11,.3); }
.main-header h1 { margin:0; font-size:26px; font-weight:900; background:linear-gradient(135deg,#f0b90b,#ffd700,#00d4aa); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.main-header p { color:#8892b0; margin:6px 0 0; font-size:13px; }
.glass-card { background:linear-gradient(135deg,rgba(26,26,46,.85),rgba(22,33,62,.85)); border-radius:16px; padding:18px; border:1px solid rgba(255,255,255,.1); }
.section-title { background:linear-gradient(135deg,rgba(26,26,46,.95),rgba(22,33,62,.95)); padding:15px 22px; border-radius:14px; margin-bottom:12px; border-right:4px solid #f0b90b; }
.section-title h3 { margin:0; color:#fff; font-size:16px; font-weight:700; }
.control-panel { background:linear-gradient(135deg,rgba(22,33,62,.9),rgba(26,26,46,.9)); padding:16px; border-radius:16px; margin-bottom:16px; border:1px solid rgba(255,255,255,.08); display:flex; align-items:flex-end; gap:14px; flex-wrap:wrap; }
.control-item { display:flex; flex-direction:column; gap:6px; }
.control-item label { color:#fff; font-weight:700; font-size:12px; }
.inp { background:#0a0e27; color:#fff; border:1px solid #f0b90b; border-radius:10px; padding:9px 12px; font-size:13px; width:105px; }
.refresh-btn { background:linear-gradient(135deg,#f0b90b,#ffd700); color:#000; border:none; padding:11px 24px; border-radius:50px; cursor:pointer; font-weight:900; font-size:13px; height:42px; }
.refresh-btn2 { background:linear-gradient(135deg,#bb86fc,#8c5dff); color:#fff; border:none; padding:11px 24px; border-radius:50px; cursor:pointer; font-weight:900; font-size:13px; height:42px; }
.reset-btn { background:linear-gradient(135deg,#ff4757,#c92a2a); color:#fff; border:none; padding:11px 24px; border-radius:50px; cursor:pointer; font-weight:900; font-size:13px; height:42px; }
.summary-card { background:linear-gradient(135deg,rgba(22,33,62,.9),rgba(26,26,46,.9)); padding:16px; border-radius:16px; min-width:160px; border:1px solid rgba(255,255,255,.1); display:inline-block; margin:5px; text-align:center; vertical-align:top; }
.data-table { width:100%; border-collapse:separate; border-spacing:0 6px; }
.data-table thead th { background:linear-gradient(135deg,#1a1a2e,#16213e); color:#ffd700; padding:10px; font-weight:700; text-align:center; font-size:12px; }
.data-table tbody td { padding:8px; text-align:center; color:#e0e0e0; font-size:12px; }
.data-table tbody tr { background:rgba(255,255,255,.03); }
.badge { display:inline-block; padding:5px 14px; border-radius:20px; font-weight:900; font-size:11px; }
.badge-long { background:linear-gradient(135deg,#00ff88,#00d4aa); color:#000; }
.badge-short { background:linear-gradient(135deg,#ff4757,#c92a2a); color:#fff; }
.trade-win { color:#00ff88 !important; font-weight:900; }
.trade-loss { color:#ff4757 !important; font-weight:900; }
.trade-open { color:#ffd700 !important; font-weight:900; }
.open-trade-row { background:rgba(255,215,0,.05) !important; }
.live-pos { color:#00ff88 !important; font-weight:900; }
.live-neg { color:#ff4757 !important; font-weight:900; }
.connection-status { padding:5px 13px; border-radius:20px; font-size:12px; font-weight:700; display:inline-block; margin-left:8px; }
.status-ok { background:rgba(0,255,136,.15); color:#00ff88; border:1px solid #00ff88; }
.status-err { background:rgba(255,71,87,.15); color:#ff4757; border:1px solid #ff4757; }
.custom-tabs { background:linear-gradient(135deg,rgba(22,33,62,.95),rgba(26,26,46,.95)); border-radius:16px 16px 0 0 !important; border:1px solid rgba(240,185,11,.25) !important; padding:5px !important; }
.custom-tab { background:transparent !important; color:#8892b0 !important; border:none !important; padding:12px 26px !important; font-weight:700 !important; font-size:14px !important; border-radius:12px !important; margin:0 3px !important; }
.custom-tab--selected { background:linear-gradient(135deg,#f0b90b,#ffd700) !important; color:#000 !important; font-weight:900 !important; }
.scanner-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:12px; }
.scanner-card { background:linear-gradient(135deg,rgba(26,26,46,.9),rgba(22,33,62,.9)); border-radius:12px; padding:14px; border:1px solid rgba(255,255,255,.08); }
.scanner-sym { font-size:16px; font-weight:900; color:#fff; }
.scanner-price { font-size:13px; color:#8892b0; margin:4px 0; }
.margin-bar { height:18px; background:rgba(255,255,255,.08); border-radius:10px; overflow:hidden; margin:6px 0; }
.margin-used { height:100%; background:linear-gradient(90deg,#ffd700,#ff8c00); }
.prog-bar { height:10px; background:rgba(255,255,255,.08); border-radius:6px; overflow:hidden; margin:8px 0; }
.prog-fill { height:100%; background:linear-gradient(90deg,#bb86fc,#00d4aa); transition:width .4s; }
.sym-count-badge { display:inline-block; padding:4px 12px; border-radius:20px; font-size:11px; font-weight:900; background:rgba(187,134,252,.2); color:#bb86fc; border:1px solid #bb86fc; margin-left:8px; }
.btn-rm { background:#ff4757; color:#fff; border:none; padding:4px 10px; border-radius:8px; font-size:10px; cursor:pointer; font-weight:900; }
.btn-close { background:#ff8c00; color:#fff; border:none; padding:4px 12px; border-radius:8px; font-size:11px; cursor:pointer; font-weight:900; }
.sys-msg-box { background:rgba(0,255,136,.08); border:1px solid #00ff88; border-radius:10px; padding:10px 14px; margin:10px auto 0; font-weight:700; font-size:12px; max-width:700px; }
'''

def fmt_p(p):
    a = abs(p)
    if a >= 10000: return f"{p:.0f}"
    elif a >= 1000: return f"{p:.1f}"
    elif a >= 1: return f"{p:.2f}"
    elif a >= 0.1: return f"{p:.4f}"
    elif a >= 0.01: return f"{p:.5f}"
    elif a >= 0.001: return f"{p:.6f}"
    else: return f"{p:.8f}"

class BybitAPIClient:
    REST = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
    def __init__(self):
        self.session = requests.Session()
        self._base = None
        self._lock = threading.Lock()
        self._cache = {}
        rs = Retry(total=2, backoff_factor=0.5, status_forcelist=[500,502,503,504], allowed_methods=["GET"], raise_on_status=False)
        ad = HTTPAdapter(max_retries=rs, pool_connections=10, pool_maxsize=20)
        self.session.mount("https://", ad)
        self.headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
    def _req(self, path, params, timeout=15):
        ordered = ([self._base] if self._base else []) + [e for e in self.REST if e != self._base]
        for base in ordered:
            for verify in (True, False):
                try:
                    r = self.session.get(f"{base}{path}", params=params, headers=self.headers, timeout=timeout, verify=verify)
                    if r.status_code == 429: time.sleep(3); continue
                    if r.status_code in (403, 451): break
                    if r.status_code != 200: continue
                    d = r.json()
                    if d.get('retCode') != 0: return None
                    self._base = base
                    return d
                except requests.exceptions.SSLError:
                    if verify: continue
                    break
                except: continue
        return None
    def get_klines(self, symbol, interval="60", limit=500):
        key = f"{symbol}|{interval}|{limit}"
        with self._lock:
            if key in self._cache:
                ts, df = self._cache[key]
                if time.time() - ts < 30: return df.copy()
        all_k, rem, end = [], limit, None
        while rem > 0:
            b = min(rem, 1000)
            params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": b}
            if end: params["end"] = end
            d = self._req("/v5/market/kline", params)
            if not d or 'list' not in (d.get('result') or {}): break
            lst = d['result']['list']
            if not lst: break
            all_k.extend(lst); rem -= len(lst)
            if len(lst) < b: break
            end = int(lst[-1][0]) - 1
        if not all_k: return pd.DataFrame()
        df = pd.DataFrame(all_k, columns=['ts','open','high','low','close','volume','turnover'])
        df['ts_num'] = df['ts'].astype(float) / 1000.0
        for c in ['open','high','low','close','volume']: df[c] = df[c].astype(float)
        df['datetime'] = pd.to_datetime(df['ts_num'], unit='s')
        df = df.drop_duplicates(subset=['ts']).sort_values('ts_num').reset_index(drop=True)
        if len(df) > limit: df = df.iloc[-limit:].reset_index(drop=True)
        with self._lock: self._cache[key] = (time.time(), df.copy())
        return df
    def get_ticker(self, symbol):
        d = self._req("/v5/market/tickers", {"category": "linear", "symbol": symbol}, timeout=10)
        if not d: return None
        lst = d.get('result', {}).get('list', [])
        if not lst: return None
        return {'lastPrice': float(lst[0].get('lastPrice', 0))}
    def test_connection(self):
        t = self.get_ticker("BTCUSDT")
        return (True, t['lastPrice']) if t else (False, 0)
    def get_all_usdt_symbols(self):
        d = self._req("/v5/market/instruments-info", {"category": "linear", "limit": "1000"}, timeout=20)
        if not d: return []
        lst = d.get('result', {}).get('list', [])
        return [i.get('symbol', '') for i in lst if i.get('symbol', '').endswith('USDT') and i.get('status') == 'Trading']

bybit = BybitAPIClient()

class SignalDatabase:
    def __init__(self, path=DB_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._init()
    def _conn(self): return sqlite3.connect(self.path)
    def _init(self):
        with self._conn() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, symbol TEXT, signal_type TEXT,
                entry_price REAL, tp_price REAL, sl_price REAL, leverage INTEGER, strength REAL,
                level_price REAL, risk_usd REAL, margin_used REAL, position_size REAL, pos_value REAL,
                entry_comm REAL, rr_ratio REAL, status TEXT DEFAULT 'OPEN', exit_price REAL,
                exit_time TEXT, outcome TEXT, pnl_percent REAL, pnl_usd REAL, notes TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS qualification (
                symbol TEXT PRIMARY KEY, ret REAL, trades INTEGER, passed INTEGER, ts TEXT)''')
    def insert(self, **kw):
        with self._lock, self._conn() as c:
            c.execute('''INSERT INTO signals (timestamp,symbol,signal_type,entry_price,tp_price,sl_price,
                leverage,strength,level_price,risk_usd,margin_used,position_size,pos_value,entry_comm,rr_ratio,notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (datetime.now().isoformat(), kw['symbol'], kw['signal_type'], kw['entry_price'], kw['tp_price'],
                 kw['sl_price'], kw['leverage'], kw['strength'], kw['level_price'], kw['risk_usd'],
                 kw['margin_used'], kw['pos_size'] if 'pos_size' in kw else kw['position_size'], kw['pos_value'] if 'pos_value' in kw else kw['position_size'], kw['entry_comm'], kw['rr_ratio'], kw.get('notes', '')))
    def close(self, sid, exit_price, outcome, pnl_pct, pnl_usd, notes=''):
        with self._lock, self._conn() as c:
            c.execute('''UPDATE signals SET status='CLOSED', exit_price=?, exit_time=?, outcome=?,
                pnl_percent=?, pnl_usd=?, notes=? WHERE id=?''',
                (exit_price, datetime.now().isoformat(), outcome, pnl_pct, pnl_usd, notes, sid))
    def get_all(self, limit=500):
        with self._conn() as c:
            return pd.read_sql_query('SELECT * FROM signals ORDER BY id DESC LIMIT ?', c, params=(limit,))
    def get_open(self):
        with self._conn() as c:
            return pd.read_sql_query('SELECT * FROM signals WHERE status="OPEN"', c)
    def get_trade(self, sid):
        with self._conn() as c:
            r = pd.read_sql_query('SELECT * FROM signals WHERE id=?', c, params=(sid,))
        return r.iloc[0] if not r.empty else None
    def used_margin(self):
        o = self.get_open()
        return float(o['margin_used'].sum()) if not o.empty else 0.0
    def free_margin(self):
        u = self.used_margin()
        return max(0.0, CFG['capital'] - u), u
    def last_signal_time(self, symbol):
        with self._conn() as c:
            r = pd.read_sql_query('SELECT timestamp FROM signals WHERE symbol=? ORDER BY id DESC LIMIT 1', c, params=(symbol,))
        return pd.to_datetime(r.iloc[0]['timestamp']) if not r.empty else None
    def save_qual(self, symbol, ret, trades, passed):
        with self._lock, self._conn() as c:
            c.execute('INSERT OR REPLACE INTO qualification (symbol,ret,trades,passed,ts) VALUES (?,?,?,?,?)',
                      (symbol, ret, trades, int(passed), datetime.now().isoformat()))
    def load_qual_full(self):
        with self._conn() as c:
            return pd.read_sql_query('SELECT symbol,ret,trades,passed FROM qualification', c)
    def clear_qual(self):
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM qualification")
    def remove_qual(self, symbol):
        with self._lock, self._conn() as c:
            c.execute("UPDATE qualification SET passed=0 WHERE symbol=?", (symbol,))
    def reset_trades(self):
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM signals")
            try:
                c.execute("DELETE FROM sqlite_sequence WHERE name='signals'")
            except Exception:
                pass
    def manual_close(self, sid, current_price):
        t = self.get_trade(sid)
        if t is None or t['status'] != 'OPEN': return None
        en, pos, mg, st = t['entry_price'], t['position_size'], t['margin_used'], t['signal_type']
        gross = (current_price - en) * pos if st == 'LONG' else (en - current_price) * pos
        net = gross - t['entry_comm'] - pos * current_price * COMMISSION
        roi = (net / mg * 100) if mg > 0 else 0
        outcome = 'WIN' if net > 0 else 'LOSS'
        self.close(sid, current_price, outcome, round(roi, 2), round(net, 2), notes='MANUAL_CLOSE')
        return {'net': net, 'roi': roi, 'outcome': outcome, 'price': current_price}
    def open_with_pnl(self, prices):
        o = self.get_open()
        if o.empty: return o
        rows = []
        for _, r in o.iterrows():
            cp = prices.get(r['symbol'], r['entry_price'])
            en, pos, mg = r['entry_price'], r['position_size'], r['margin_used']
            gross = (cp - en) * pos if r['signal_type'] == 'LONG' else (en - cp) * pos
            net = gross - r['entry_comm'] - pos * cp * COMMISSION
            d = r.to_dict()
            d.update({'current_price': cp, 'live_pnl_usd': round(net, 2), 'live_roi': round(net / mg * 100, 2) if mg > 0 else 0})
            rows.append(d)
        return pd.DataFrame(rows)
    def stats(self):
        with self._conn() as c:
            df = pd.read_sql_query('SELECT * FROM signals WHERE status="CLOSED"', c)
        if df.empty:
            return {'total': 0, 'wins': 0, 'losses': 0, 'wr': 0, 'pf': 0, 'mdd': 0, 'pnl': 0, 'final': CFG['capital'], 'equity': [CFG['capital']]}
        w = df[df['outcome'] == 'WIN']; l = df[df['outcome'] == 'LOSS']
        gw = w['pnl_usd'].sum() if not w.empty else 0
        gl = abs(l['pnl_usd'].sum()) if not l.empty else 1
        cap = CFG['capital']; eq = [cap]
        for _, r in df.sort_values('id').iterrows():
            cap += r['pnl_usd']; eq.append(cap)
        ea = np.array(eq); pk = np.maximum.accumulate(ea)
        dd = ((pk - ea) / pk * 100).max() if len(ea) else 0
        return {'total': len(df), 'wins': len(w), 'losses': len(l), 'wr': round(len(w)/len(df)*100, 1),
                'pf': round(gw/gl, 2) if gl > 0 else 99, 'mdd': round(float(dd), 2),
                'pnl': round(float(df['pnl_usd'].sum()), 2), 'final': round(float(eq[-1]), 2), 'equity': eq}

db = SignalDatabase()

def sr_from_arrays(ho, hc, ref, lo2=None, lc2=None, bins=60):
    if len(ho) < 30: return []
    al = np.linspace(0, 1, 20)
    pts = ho[:, None] + al[None, :] * (hc - ho)[:, None]
    ap = [pts.flatten(), ho]
    aw = [np.full(pts.size, 3.0), np.full(len(ho), 2.5)]
    if lo2 is not None and len(lo2) > 0:
        al2 = np.linspace(0, 1, 10)
        pts2 = lo2[:, None] + al2[None, :] * (lc2 - lo2)[:, None]
        ap.append(pts2.flatten())
        aw.append(np.full(pts2.size, 1.0))
    ap = np.concatenate(ap); aw = np.concatenate(aw)
    pr = ap.max() - ap.min()
    if pr <= 0: return []
    hist, be = np.histogram(ap, bins=bins, weights=aw)
    bc = (be[:-1] + be[1:]) / 2
    mh = np.mean(hist)
    peaks = []
    for i in range(2, len(hist) - 2):
        if hist[i] > hist[i-1] and hist[i] > hist[i+1] and hist[i] > hist[i-2] and \
           hist[i] > hist[i+2] and hist[i] > mh * 1.4:
            peaks.append((bc[i], hist[i]))
    peaks.sort(key=lambda x: -x[1])
    ms = peaks[0][1] if peaks else 1
    return [{'price': float(p), 'strength': int(v / ms * 100), 'type': 'support' if p < ref else 'resistance'} for p, v in peaks[:10]]

# =====================================================================
# ✅ بک‌تست واقع‌گرایانه (v5.2)
#  - سطوح فقط از کندل‌های قبل از i (بدون lookahead)
#  - ورود مارکت روی CLOSE کندل i، فقط اگر کلوز داخل touch_pct سطح باشد
#  - SL/TP از فاصله سطح؛ بررسی خروج از کندل i+1 با High/Low (اولویت SL)
# =====================================================================
def run_backtest(df_htf, df_ltf=None, lookback=10000, window=150, recalc=1,
                 min_str=100, cap0=500, lev=10, risk=0.20, rr=2.0, slp=0.008,
                 touch=0.0025):
    if df_ltf is None: df_ltf = pd.DataFrame()
    total = len(df_htf)
    lookback = min(int(lookback), total)
    df_bt = df_htf.iloc[-lookback:].reset_index(drop=True)
    bt_start, bt_end = df_bt["ts_num"].iloc[0], df_bt["ts_num"].iloc[-1]
    if len(df_ltf) > 0:
        dl = df_ltf[(df_ltf["ts_num"] >= bt_start) & (df_ltf["ts_num"] <= bt_end)]
        lt, lo, lc = dl["ts_num"].values, dl["open"].values, dl["close"].values
    else:
        lt, lo, lc = np.array([]), np.array([]), np.array([])
    capital = cap0
    trades = []
    eq = [capital]
    open_t = None
    sr = []
    ho = df_bt["open"].values; hc = df_bt["close"].values
    hh = df_bt["high"].values; hl = df_bt["low"].values
    ht = df_bt["ts_num"].values
    start_i = min(window, len(df_bt) - 1)
    for i in range(start_i, len(df_bt)):
        ch, cl2, cc = hh[i], hl[i], hc[i]
        if (i - start_i) % recalc == 0:
            ws = max(0, i - window + 1)
            # ✅ علّی: کندل i در ساخت سطوح دخالت ندارد
            lm = (lt >= ht[ws]) & (lt < ht[i]) if len(lt) > 0 else None
            sr = sr_from_arrays(ho[ws:i], hc[ws:i], cc,
                                lo[lm] if (lm is not None and lm.any()) else None,
                                lc[lm] if (lm is not None and lm.any()) else None)
        if open_t is not None:
            hit, xp = False, 0
            if open_t["dir"] == "LONG":
                if cl2 <= open_t["sl"]: hit, xp = True, open_t["sl"]
                elif ch >= open_t["tp"]: hit, xp = True, open_t["tp"]
            else:
                if ch >= open_t["sl"]: hit, xp = True, open_t["sl"]
                elif cl2 <= open_t["tp"]: hit, xp = True, open_t["tp"]
            if hit:
                gross = (xp - open_t["entry"]) * open_t["pos_size"] if open_t["dir"] == "LONG" else (open_t["entry"] - xp) * open_t["pos_size"]
                net = gross - open_t["entry_comm"] - open_t["pos_size"] * xp * COMMISSION
                capital += net
                open_t["pnl"] = net
                trades.append(open_t)
                open_t = None
            eq.append(capital)
            continue
        for lv in sr:
            if lv["strength"] < min_str: continue
            lp = lv["price"]
            if not (cl2 <= lp <= ch): continue
            # ✅✅ ورود واقع‌گرایانه: مارکت روی CLOSE، فقط اگر کلوز روی سطح باشد
            if abs(cc - lp) / lp > touch: continue
            if lv["type"] == "support":
                d = "LONG"; entry = cc * (1 + SPREAD_PCT)
            else:
                d = "SHORT"; entry = cc * (1 - SPREAD_PCT)
            sld = lp * slp
            sl = entry - sld if d == "LONG" else entry + sld
            tp = entry + sld * rr if d == "LONG" else entry - sld * rr
            margin = capital * risk
            if margin <= 0: continue
            pos_value = margin * lev
            pos_size = pos_value / entry
            loss_if_sl = sld * pos_size
            if loss_if_sl > capital * 0.9:
                pos_size = (capital * 0.9) / sld
                pos_value = pos_size * entry
                margin = pos_value / lev
            entry_comm = pos_value * COMMISSION
            if entry_comm >= margin * 0.5: continue
            open_t = {"dir": d, "entry": entry, "sl": sl, "tp": tp, "pos_size": pos_size, "margin": margin, "entry_comm": entry_comm}
            break
        eq.append(capital)
    if open_t is not None:
        lp2 = hc[-1]
        gross = (lp2 - open_t["entry"]) * open_t["pos_size"] if open_t["dir"] == "LONG" else (open_t["entry"] - lp2) * open_t["pos_size"]
        net = gross - open_t["entry_comm"] - open_t["pos_size"] * lp2 * COMMISSION
        capital += net
        open_t["pnl"] = net
        trades.append(open_t)
        eq[-1] = capital
    ret = (eq[-1] - cap0) / cap0 * 100
    return trades, eq, {'ret': round(ret, 1), 'total': len(trades)}

class BacktestQualifier:
    def __init__(self):
        self._lock = threading.Lock()
        self.progress = {}
        self.qualified = []
        self.running = False
        self.done = False
        self.total_symbols = 0
        self._gen = 0
        self.all_symbols = self._load_symbols()
        self._reset_progress()
        try:
            rows = db.load_qual_full()
            for _, r in rows.iterrows():
                s = r['symbol']
                if s in self.progress and r['passed']:
                    self.progress[s]['status'] = 'passed'
                    self.progress[s]['ret'] = r['ret'] if pd.notna(r['ret']) else None
                    self.progress[s]['trades'] = int(r['trades']) if pd.notna(r['trades']) else None
                    self.qualified.append(s)
        except Exception as e:
            print(f"⚠️ خطا در بارگذاری نتایج قبلی: {e}")
        threading.Thread(target=self._run, daemon=True).start()
    def _load_symbols(self):
        try:
            api_syms = bybit.get_all_usdt_symbols()
            if api_syms:
                base_set = set(CANDIDATE_BASE); api_set = set(api_syms)
                merged = [s for s in CANDIDATE_BASE if s in api_set]
                for s in sorted(api_set - base_set): merged.append(s)
                return merged
        except Exception as e:
            print(f"⚠️ خطا در API: {e}")
        return CANDIDATE_BASE.copy()
    def _reset_progress(self):
        self.progress = {s: {'status': 'pending', 'ret': None, 'trades': None} for s in self.all_symbols}
        self.total_symbols = len(self.all_symbols)
    def _run(self):
        my_gen = self._gen
        self.running = True
        self.done = False
        for sym in list(self.all_symbols):
            if self._gen != my_gen: return
            with self._lock:
                if self.progress[sym]['status'] != 'pending': continue
                self.progress[sym]['status'] = 'testing'
            try:
                df_h = bybit.get_klines(sym, '60', limit=QUAL_LOOKBACK)
                if df_h is None or len(df_h) < 2000: raise Exception('دیتای ناکافی')
                df_l = bybit.get_klines(sym, '15', limit=QUAL_LTF_LIMIT)
                _, _, stats = run_backtest(df_h, df_l, lookback=len(df_h), window=CFG['window'],
                    recalc=QUAL_RECALC, min_str=QUAL_MIN_STR, cap0=CFG['capital'],
                    lev=CFG['leverage'], risk=CFG['risk_pct'], rr=CFG['rr'], slp=CFG['sl_pct'],
                    touch=CFG['touch_pct'])
                ret, ntr = stats['ret'], stats['total']
                passed = ret > QUAL_MIN_RETURN
                db.save_qual(sym, ret, ntr, passed)
                with self._lock:
                    self.progress[sym]['ret'] = ret
                    self.progress[sym]['trades'] = ntr
                    self.progress[sym]['status'] = 'passed' if passed else 'failed'
                    if passed and sym not in self.qualified: self.qualified.append(sym)
                    if not passed and sym in self.qualified: self.qualified.remove(sym)
            except Exception:
                with self._lock: self.progress[sym]['status'] = 'error'
            time.sleep(0.3)
        if self._gen == my_gen:
            self.running = False
            self.done = True
    def restart(self):
        self._gen += 1
        self.running = False
        db.clear_qual()
        self._reset_progress()
        self.qualified = []
        self.done = False
        set_msg("🔄 اجرای مجدد — همه ارزها از نو تست می‌شوند", "#bb86fc")
        threading.Thread(target=self._run, daemon=True).start()
    def remove_symbol(self, symbol):
        with self._lock:
            if symbol in self.qualified: self.qualified.remove(symbol)
            if symbol in self.progress:
                self.progress[symbol]['status'] = 'removed'
                self.progress[symbol]['ret'] = None
                self.progress[symbol]['trades'] = None
        db.remove_qual(symbol)
        set_msg(f"🗑️ {symbol} از لیست تایید شده حذف شد", "#ff4757")
    def snapshot(self):
        with self._lock:
            return ({k: dict(v) for k, v in self.progress.items()}, list(self.qualified), self.running, self.done, self.total_symbols)

qualifier = BacktestQualifier()

# ✅ فاصله SL از خود سطح (مثل بک‌تست)، ورود مارکت روی قیمت لحظه‌ای
def compute_params(direction, price, level, strength):
    entry = price * (1 + SPREAD_PCT) if direction == 'LONG' else price * (1 - SPREAD_PCT)
    sld = level * CFG['sl_pct']
    sl = entry - sld if direction == 'LONG' else entry + sld
    tp = entry + sld * CFG['rr'] if direction == 'LONG' else entry - sld * CFG['rr']
    margin = CFG['capital'] * CFG['risk_pct']
    pos_value = margin * CFG['leverage']
    pos_size = pos_value / entry
    loss_if_sl = sld * pos_size
    if loss_if_sl > CFG['capital'] * 0.9:
        pos_size = (CFG['capital'] * 0.9) / sld
        pos_value = pos_size * entry
        margin = pos_value / CFG['leverage']
    return {'direction': direction, 'entry': entry, 'sl': sl, 'tp': tp, 'margin': margin,
            'pos_value': pos_value, 'pos_size': pos_size, 'entry_comm': pos_value * COMMISSION,
            'risk': loss_if_sl, 'level': level, 'strength': strength}

class SpiralScanner:
    def __init__(self):
        self.results = {}
        self.running = False
        self.last_scan = None
        self._lock = threading.Lock()
        threading.Thread(target=self._worker, daemon=True).start()
    def _worker(self):
        while True:
            try:
                self._scan_all()
                self._check_trades()
            except Exception as e:
                print(f"❌ خطای اسکنر: {e}")
            time.sleep(SCAN_INTERVAL)
    def _scan_all(self):
        open_syms = set(db.get_open()['symbol'].tolist())
        syms = list(set(qualifier.qualified) | open_syms)
        self.running = True
        for sym in syms:
            r = self._scan_symbol(sym)
            with self._lock: self.results[sym] = r
            time.sleep(0.4)
        self.running = False
        self.last_scan = datetime.now()
    def _scan_symbol(self, sym):
        try:
            df = bybit.get_klines(sym, interval=CFG['interval'], limit=CFG['lookback'])
            if df is None or df.empty or len(df) < 50:
                return {'symbol': sym, 'error': 'دیتای کندل دریافت نشد'}
            done = df.iloc[:-1].reset_index(drop=True)
            tk = bybit.get_ticker(sym)
            if not tk: return {'symbol': sym, 'error': 'تیکر دریافت نشد'}
            price = tk['lastPrice']

            # ✅ پنجره S/R دقیقاً همان window بک‌تست (نه کل lookback)
            win = min(int(CFG['window']), len(done))
            dw = done.iloc[-win:]

            # ✅ داده LTF هم‌اندازه پنجره (مثل بک‌تست)
            ltf_tf = {'240': '60', '60': '15', '15': '5'}.get(CFG['interval'], '15')
            mult = {'60': 4, '15': 3, '5': 1}.get(ltf_tf, 4)
            df_l = bybit.get_klines(sym, ltf_tf, limit=win * mult + 20)
            lo2 = df_l['open'].values if len(df_l) > 0 else None
            lc2 = df_l['close'].values if len(df_l) > 0 else None

            levels = sr_from_arrays(dw['open'].values, dw['close'].values, price, lo2, lc2)
            for lv in levels: lv['type'] = 'support' if lv['price'] < price else 'resistance'
            info = {'symbol': sym, 'price': price, 'levels': levels[:4], 'signal': None, 'error': None, 'timestamp': datetime.now()}

            # آخرین کندل بسته = کندل i در بک‌تست
            last = done.iloc[-1]
            ch_l, cl_l, cc_l = last['high'], last['low'], last['close']
            open_syms = set(db.get_open()['symbol'].tolist())
            for lv in levels:
                if lv['strength'] < LIVE_MIN_STR: continue
                lp = lv['price']
                if not (cl_l <= lp <= ch_l): continue                    # همان شرط cross
                if abs(cc_l - lp) / lp > CFG['touch_pct']: continue      # همان شرط کلوز بک‌تست
                if abs(price - lp) / lp > CFG['touch_pct']: continue     # ✅ الان هم قابل اجراست
                if sym in open_syms: break
                if len(open_syms) >= CFG['max_open']: break
                lt_ = db.last_signal_time(sym)
                if lt_ and (datetime.now() - lt_).total_seconds() < COOLDOWN_SEC: break
                fm, _ = db.free_margin()
                if fm < CFG['capital'] * CFG['risk_pct'] * 0.5: break
                direction = 'LONG' if lv['type'] == 'support' else 'SHORT'
                p = compute_params(direction, price, lp, lv['strength'])
                db.insert(symbol=sym, signal_type=direction, entry_price=p['entry'], tp_price=p['tp'],
                          sl_price=p['sl'], leverage=CFG['leverage'], strength=lv['strength'],
                          level_price=lp, risk_usd=p['risk'], margin_used=p['margin'],
                          position_size=p['pos_size'], pos_value=p['pos_value'],
                          entry_comm=p['entry_comm'], rr_ratio=CFG['rr'],
                          notes=f"touch L{lv['strength']} d={abs(price-lp)/lp*100:.2f}%")
                info['signal'] = direction
                break
            return info
        except Exception as e:
            return {'symbol': sym, 'error': str(e)}
    def _check_trades(self):
        ot = db.get_open()
        if ot.empty: return
        for _, t in ot.iterrows():
            tk = bybit.get_ticker(t['symbol'])
            if not tk: continue
            cp = tk['lastPrice']
            # ✅ بررسی با High/Low کندل در حال تشکیل (مثل بک‌تست)، نه فقط تیک 60 ثانیه
            hi_f = lo_f = cp
            try:
                dfc = bybit.get_klines(t['symbol'], CFG['interval'], limit=1)
                if dfc is not None and not dfc.empty:
                    hi_f = max(float(dfc.iloc[-1]['high']), cp)
                    lo_f = min(float(dfc.iloc[-1]['low']), cp)
            except Exception:
                pass
            en, tp, sl = t['entry_price'], t['tp_price'], t['sl_price']
            pos, mg = t['position_size'], t['margin_used']
            out = ep = None
            if t['signal_type'] == 'LONG':
                if lo_f <= sl: out, ep = 'LOSS', sl      # اولویت SL مثل بک‌تست
                elif hi_f >= tp: out, ep = 'WIN', tp
            else:
                if hi_f >= sl: out, ep = 'LOSS', sl
                elif lo_f <= tp: out, ep = 'WIN', tp
            if out:
                gross = (ep - en) * pos if t['signal_type'] == 'LONG' else (en - ep) * pos
                net = gross - t['entry_comm'] - pos * ep * COMMISSION
                roi = (net / mg * 100) if mg > 0 else 0
                db.close(t['id'], ep, out, round(roi, 2), round(net, 2))
                print(f"🏁 {t['symbol']}: {out} | ${net:+.2f}")
    def get_results(self):
        with self._lock: return self.results.copy()
    def prices(self):
        with self._lock: return {s: r['price'] for s, r in self.results.items() if r.get('price')}

scanner = SpiralScanner()

def gen_spirals(x0, y0, x1, y1, dirs, np_=40, loops=1.0):
    N = len(x0)
    if N == 0: return np.empty((0, np_)), np.empty((0, np_))
    b = 0.3063489
    dx, dy = x1 - x0, y1 - y0
    dist = np.hypot(dx, dy)
    ta = np.arctan2(dy, dx)
    th = np.linspace(0, loops * 2 * np.pi, np_)
    r = np.exp(b * th) - 1
    sc = np.where(r[-1] > 0, dist / r[-1], 0)
    td = dirs[:, None] * th[None, :]
    xs = r[None, :] * np.cos(td) * sc[:, None]
    ys = r[None, :] * np.sin(td) * sc[:, None]
    ea = np.arctan2(ys[:, -1], xs[:, -1])
    rot = ta - ea
    cr, sr = np.cos(rot)[:, None], np.sin(rot)[:, None]
    return xs * cr - ys * sr + x0[:, None], xs * sr + ys * cr + y0[:, None]

def build_spiral_fig(df, levels, price):
    min_ts = df["ts_num"].min()
    ts = df["ts_num"].max() - min_ts
    pmin, pmax = df["low"].min(), df["high"].max()
    ps = pmax - pmin if pmax != pmin else 1
    if ts == 0: ts = 1
    st = ts * 4.0
    psc = st / ps
    ht, ho, hc = df["ts_num"].values, df["open"].values, df["close"].values
    x0 = (ht - min_ts) * 4.0
    y0 = (ho - pmin) * psc
    step = np.append(np.diff(ht), np.diff(ht)[-1] if len(ht) > 1 else 1) * 4.0
    x1 = x0 + step
    y1 = (hc - pmin) * psc
    bl = hc >= ho
    Xr, Yr = gen_spirals(x0, y0, x1, y1, np.where(bl, 1.0, -1.0))
    fig = go.Figure()
    for mk, cl in [(bl, "#00e676"), (~bl, "#ff5252")]:
        if mk.sum() == 0: continue
        Xs, Ys = Xr[mk], Yr[mk]
        N, np_ = Xs.shape
        Xf, Yf = Xs.flatten(), Ys.flatten()
        if N > 1:
            ni = np.arange(1, N) * np_
            Xf, Yf = np.insert(Xf, ni, np.nan), np.insert(Yf, ni, np.nan)
        fig.add_trace(go.Scattergl(x=Xf, y=Yf, mode='lines', line=dict(color=cl, width=2), opacity=0.9, showlegend=False))
    for lv in levels:
        c = "#00e676" if lv['type'] == 'support' else "#ff5252"
        yv = (lv['price'] - pmin) * psc
        fig.add_hline(y=yv, line_dash="dash", line_color=c, line_width=1 + lv['strength']/50,
                      opacity=0.4 + lv['strength']/200, annotation_text=f"{fmt_p(lv['price'])} ({lv['strength']}%)",
                      annotation_position="right", annotation_font_size=10, annotation_font_color=c)
    yv = (price - pmin) * psc
    fig.add_hline(y=yv, line_dash="solid", line_color="#ffd700", line_width=1.5,
                  annotation_text=f"قیمت: {fmt_p(price)}", annotation_position="right",
                  annotation_font_size=10, annotation_font_color="#ffd700")
    yt = np.linspace(0, st, 6)
    yl = [fmt_p(pmin + v / psc) for v in yt]
    fig.update_layout(template="plotly_dark", paper_bgcolor="#0a0e27", plot_bgcolor="#121c30",
                      xaxis=dict(visible=False),
                      yaxis=dict(tickmode='array', tickvals=yt, ticktext=yl, gridcolor="#23314d", scaleanchor="x", scaleratio=1),
                      height=520, margin=dict(l=70, r=110, t=40, b=30), hovermode="closest")
    return fig

app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.title = "Golden Spiral LIVE Trader v5.2"
app.index_string = f'''<!DOCTYPE html><html><head>
{{%metas%}}<title>{{%title%}}</title>{{%favicon%}}{{%css%}}
<style>{CUSTOM_CSS}</style></head><body>
{{%app_entry%}}<footer>{{%config%}}
{{%scripts%}}{{%renderer%}}</footer></body></html>'''

def ci(l, id_, v=None, tp='number', w=100):
    return html.Div([html.Label(l), dcc.Input(id=id_, value=v, type=tp, className='inp', style={'width': f'{w}px'})], className='control-item')

app.layout = html.Div([
    html.Div([
        html.H1("🌀 سیستم معاملاتی زنده اسپیرال فراکتالی"),
        html.P(f"100+ ارز بایبیت | آستانه: {QUAL_MIN_RETURN:.0f}% | ریسک 20% | لوریج 10x | PnL زنده | ریست کامل",
               style={'color': '#8892b0', 'margin': '6px 0 0', 'fontSize': '13px'}),
        html.Div(id='connection-indicator', style={'marginTop': '10px'}),
        html.Div(id='sys-msg-box'),
    ], className="main-header"),
    html.Div([
        ci("💰 سرمایه:", 'cfg-cap', 500), ci("⚡ لوریج:", 'cfg-lev', 10),
        ci("⚠️ ریسک%:", 'cfg-risk', 20), ci("🎯 R:R:", 'cfg-rr', 2),
        ci("🛑 SL%:", 'cfg-sl', 0.8), ci("📐 پنجره:", 'cfg-win', 150),
        ci("⚡ قدرت:", 'cfg-str', 95), ci("👆 لمس%:", 'cfg-touch', 0.25),
        html.Div([html.Label("📊 TF:"), dcc.Dropdown(id='cfg-tf',
            options=[{'label': t, 'value': t} for t in ['15','60','240']], value='60',
            style={'width': '90px', 'backgroundColor': '#0a0e27', 'color': '#fff'})], className='control-item'),
        html.Button('💾 ذخیره', id='save-cfg', className='refresh-btn'),
        html.Span(id='cfg-status', style={'color': '#00ff88', 'fontWeight': '700', 'paddingBottom': '10px'}),
    ], className='control-panel'),
    dcc.Tabs(id='main-tabs', value='tab-qual', className='custom-tabs', children=[
        dcc.Tab(label='🧪 صلاحیت‌سنجی', value='tab-qual', className='custom-tab', selected_className='custom-tab--selected'),
        dcc.Tab(label='🌀 تحلیل اسپیرال', value='tab-spiral', className='custom-tab', selected_className='custom-tab--selected'),
        dcc.Tab(label='🛰️ اسکنر زنده', value='tab-scanner', className='custom-tab', selected_className='custom-tab--selected'),
        dcc.Tab(label='📊 آمار و تاریخچه', value='tab-stats', className='custom-tab', selected_className='custom-tab--selected'),
    ]),
    html.Div(id='tab-qual', children=[
        html.Div([html.Div([html.H3(f"🧪 بک‌تست صلاحیت‌سنجی روی همه نمادهای USDT (آستانه {QUAL_MIN_RETURN:.0f}%)")],
            className='section-title', style={'borderRightColor': '#bb86fc'}),
            html.Div(id='qual-status', style={'marginBottom': '10px'}),
            html.Div(id='qual-progress'),
            html.Div(id='qual-qualified-list', style={'marginTop': '15px'}),
            html.Div(style={'display': 'flex', 'gap': '10px', 'marginTop': '10px'}, children=[
                html.Button('🔄 اجرای مجدد صلاحیت‌سنجی (تست همه از نو)', id='qual-rerun', className='refresh-btn2'),
            ]),
            html.Div(id='qual-table', style={'overflowX': 'auto', 'marginTop': '15px'}),
        ], className='glass-card'),
    ]),
    html.Div(id='tab-spiral', style={'display': 'none'}, children=[
        html.Div([
            html.Div([html.Label("🎯 نماد:"), dcc.Dropdown(id='ana-sym',
                options=[{'label': s, 'value': s} for s in CANDIDATE_BASE[:50]], value='BTCUSDT',
                style={'width': '180px', 'backgroundColor': '#0a0e27', 'color': '#fff'})], className='control-item'),
            html.Button('🔄 بروزرسانی', id='ana-refresh', className='refresh-btn'),
        ], className='control-panel'),
        html.Div([dcc.Graph(id='spiral-chart')], className='glass-card'),
        html.Div(id='sr-table-div', className='glass-card', style={'marginTop': '15px'}),
    ]),
    html.Div(id='tab-scanner', style={'display': 'none'}, children=[
        html.Div(id='scan-status', style={'marginBottom': '12px'}),
        html.Div(id='scan-margin', style={'marginBottom': '12px'}),
        html.Div(id='scan-open', style={'marginBottom': '15px'}),
        html.Div(id='scan-signals', style={'marginBottom': '15px'}),
        html.Div([html.Div([html.H3("📡 ارزهای تایید شده")], className='section-title'),
                  html.Div(id='scan-grid', className='scanner-grid')], className='glass-card'),
    ]),
    html.Div(id='tab-stats', style={'display': 'none'}, children=[
        html.Div(style={'textAlign': 'center', 'marginBottom': '12px'}, children=[
            html.Button('🗑️ ریست کامل سیستم معاملات (حذف همه معاملات)', id='reset-trades', className='reset-btn'),
        ]),
        html.Div(id='stat-cards', style={'textAlign': 'center', 'marginBottom': '15px'}),
        html.Div([html.Div([html.H3("📈 رشد سرمایه")], className='section-title'),
                  html.Div([dcc.Graph(id='equity-chart', style={'height': '400px'})])], className='glass-card'),
        html.Div([html.Div([html.H3("📋 تاریخچه معاملات")], className='section-title'),
                  html.Div(id='history-div', style={'overflowX': 'auto'})], className='glass-card', style={'marginTop': '15px'}),
    ]),
    dcc.Interval(id='iv-health', interval=60000),
    dcc.Interval(id='iv-scan', interval=15000),
    dcc.Interval(id='iv-stat', interval=10000),
], style={'padding': '18px', 'minHeight': '100vh'})

@app.callback([Output('tab-qual', 'style'), Output('tab-spiral', 'style'),
               Output('tab-scanner', 'style'), Output('tab-stats', 'style')],
              Input('main-tabs', 'value'))
def switch_tab(t):
    h, s = {'display': 'none'}, {}
    tabs = ['tab-qual', 'tab-spiral', 'tab-scanner', 'tab-stats']
    return [s if tab == t else h for tab in tabs]

@app.callback(Output('connection-indicator', 'children'), Input('iv-health', 'n_intervals'))
def conn(n):
    ok, p = bybit.test_connection()
    if ok:
        return html.Div([html.Span("🟢 متصل", className='connection-status status-ok'),
                         html.Span(f"💰 BTC: ${p:,.2f}", style={'color': '#8892b0', 'fontSize': '13px'})])
    return html.Span("🔴 قطع", className='connection-status status-err')

@app.callback(Output('sys-msg-box', 'children'), Input('iv-scan', 'n_intervals'))
def show_sys_msg(n):
    if not SYS_MSG['text']: return html.Div()
    return html.Div(f"[{SYS_MSG['time']}] {SYS_MSG['text']}", className='sys-msg-box',
                    style={'color': SYS_MSG['color'], 'borderColor': SYS_MSG['color']})

@app.callback(Output('sys-msg-box', 'children', allow_duplicate=True),
              Input({'type': 'close-trade', 'index': ALL}, 'n_clicks'),
              prevent_initial_call=True)
def close_action(clicks):
    ctx = callback_context
    if not ctx.triggered: return no_update
    trig = ctx.triggered[0]
    pid = trig['prop_id']
    if not (pid.startswith('{') and 'close-trade' in pid): return no_update
    if not trig['value']: return no_update
    try:
        d = json.loads(pid.split('.')[0]); sid = int(d['index'])
    except Exception:
        return no_update
    t = db.get_trade(sid)
    if t is None:
        msg = f"❌ معامله #{sid} یافت نشد"
        set_msg(msg, "#ff4757")
        return html.Div(f"[{SYS_MSG['time']}] {msg}", className='sys-msg-box', style={'color': '#ff4757', 'borderColor': '#ff4757'})
    price = None
    tk = bybit.get_ticker(t['symbol'])
    if tk: price = tk['lastPrice']
    if price is None: price = scanner.prices().get(t['symbol']) or t['entry_price']
    result = db.manual_close(sid, price)
    if result:
        msg = (f"✅ {t['symbol']} دستی بسته شد @ {fmt_p(result['price'])} | "
               f"PnL: ${result['net']:+.2f} ({result['roi']:+.2f}%) {result['outcome']}")
        col = "#00ff88" if result['net'] > 0 else "#ff4757"
        set_msg(msg, col)
        return html.Div(f"[{SYS_MSG['time']}] {msg}", className='sys-msg-box', style={'color': col, 'borderColor': col})
    return no_update

@app.callback(Output('sys-msg-box', 'children', allow_duplicate=True),
              Input('reset-trades', 'n_clicks'),
              prevent_initial_call=True)
def reset_trades(n):
    if not n: return no_update
    db.reset_trades()
    msg = "🗑️ سیستم معاملات ریست شد — همه معاملات حذف و از نو شروع می‌شود"
    set_msg(msg, "#ffd700")
    return html.Div(f"[{SYS_MSG['time']}] {msg}", className='sys-msg-box', style={'color': '#ffd700', 'borderColor': '#ffd700'})

@app.callback(Output('cfg-status', 'children'), Input('save-cfg', 'n_clicks'),
              State('cfg-cap', 'value'), State('cfg-lev', 'value'), State('cfg-risk', 'value'),
              State('cfg-rr', 'value'), State('cfg-sl', 'value'), State('cfg-win', 'value'),
              State('cfg-str', 'value'), State('cfg-touch', 'value'), State('cfg-tf', 'value'))
def save_cfg(n, cap, lev, risk, rr, sl, win, st, touch, tf):
    if not n: return ""
    CFG.update({'capital': float(cap or 500), 'leverage': int(lev or 10),
                'risk_pct': float(risk or 20) / 100, 'rr': float(rr or 2),
                'sl_pct': float(sl or 0.8) / 100, 'window': int(win or 150),
                'min_strength': int(st or 95), 'touch_pct': float(touch or 0.25) / 100,
                'interval': tf or '60'})
    set_msg(f"تنظیمات ذخیره شد: L:{CFG['leverage']}x ریسک:{CFG['risk_pct']*100:.0f}%")
    return f"✅ L:{CFG['leverage']}x | ریسک:{CFG['risk_pct']*100:.0f}%"

@app.callback([Output('qual-status', 'children'), Output('qual-progress', 'children'),
               Output('qual-qualified-list', 'children'), Output('qual-table', 'children')],
              Input('iv-scan', 'n_intervals'),
              Input({'type': 'remove-sym', 'index': ALL}, 'n_clicks'))
def update_qual(n, remove_clicks):
    for trig in callback_context.triggered:
        pid = trig['prop_id']
        if pid.startswith('{') and 'remove-sym' in pid and trig['value']:
            try:
                d = json.loads(pid.split('.')[0])
                qualifier.remove_symbol(d['index'])
            except Exception:
                pass
    prog, qualified, running, done, total_sym = qualifier.snapshot()
    tested = sum(1 for v in prog.values() if v['status'] not in ('pending', 'testing'))
    total = len(prog)
    status = html.Div([
        html.Span(f"🧪 وضعیت: {'در حال تست...' if running else ('✅ کامل شد' if done else '⏳')}",
                  style={'color': '#bb86fc', 'fontWeight': '900', 'marginLeft': '14px'}),
        html.Span(f"تست: {tested}/{total}", style={'color': '#fff', 'fontWeight': '700', 'marginLeft': '14px'}),
        html.Span(f"✅ تایید (>{QUAL_MIN_RETURN}%): {len(qualified)}", style={'color': '#00ff88', 'fontWeight': '900', 'marginLeft': '14px'}),
        html.Span(f"⚠️ ریسک: {CFG['risk_pct']*100:.0f}% | لوریج: {CFG['leverage']}x",
                  style={'color': '#ff4757', 'fontWeight': '900', 'marginLeft': '14px'}),
        html.Span(f"📊 کل نمادها: {total_sym}", className='sym-count-badge'),
    ])
    pct = (tested/total*100) if total > 0 else 0
    pbar = html.Div([
        html.Div(f"پیشرفت: {tested}/{total} ({pct:.0f}%)", style={'color': '#8892b0', 'fontSize': '12px'}),
        html.Div(className='prog-bar', children=[html.Div(className='prog-fill', style={'width': f'{pct:.0f}%'})]),
    ])
    if qualified:
        rm_buttons = []
        for sym in sorted(qualified):
            rm_buttons.append(html.Div([
                html.Span(sym, style={'fontWeight': '900', 'color': '#00ff88', 'marginLeft': '8px'}),
                html.Button('🗑️ حذف', id={'type': 'remove-sym', 'index': sym}, className='btn-rm'),
            ], style={'display': 'inline-block', 'margin': '4px', 'background': 'rgba(0,255,136,.08)',
                      'padding': '6px 10px', 'borderRadius': '8px', 'border': '1px solid #00ff88'}))
        qualified_list = html.Div([
            html.H4(f"✅ ارزهای تایید شده ({len(qualified)}) — برای حذف کلیک کنید:",
                    style={'color': '#00ff88', 'marginBottom': '10px', 'fontSize': '14px'}),
            html.Div(rm_buttons, style={'display': 'flex', 'flexWrap': 'wrap', 'gap': '6px'}),
        ], className='glass-card', style={'borderColor': '#00ff88'})
    else:
        qualified_list = html.Div("هنوز ارزی تایید نشده است",
                                  style={'color': '#8892b0', 'padding': '10px', 'textAlign': 'center'})
    rows = []
    order = {'passed': 0, 'testing': 1, 'failed': 2, 'removed': 3, 'error': 4, 'pending': 5}
    sorted_syms = sorted(prog.keys(), key=lambda s: (order.get(prog[s]['status'], 6), -(prog[s].get('ret') or -999)))
    for sym in sorted_syms[:150]:
        v = prog[sym]
        stt = v['status']
        icon = {'passed': '✅ تایید', 'failed': '❌ رد', 'testing': '🔄 تست', 'error': '⚠️ خطا',
                'pending': '⏳', 'removed': '🗑️ حذف‌شده'}.get(stt, stt)
        col = {'passed': '#00ff88', 'failed': '#ff4757', 'testing': '#ffd700', 'error': '#ff8c00',
               'pending': '#8892b0', 'removed': '#8892b0'}.get(stt, '#fff')
        rows.append(html.Tr([
            html.Td(html.Span(sym, style={'fontWeight': '900', 'color': '#ffd700'})),
            html.Td(html.Span(icon, style={'color': col, 'fontWeight': '700'})),
            html.Td(f"{v['ret']:+.1f}%" if v['ret'] is not None else '-',
                    style={'color': '#00ff88' if (v['ret'] or 0) > QUAL_MIN_RETURN else '#ff4757', 'fontWeight': '900'}),
            html.Td(f"{v['trades']}" if v['trades'] is not None else '-', style={'color': '#8892b0'}),
        ]))
    tbl = html.Table([
        html.Thead(html.Tr([html.Th('نماد'), html.Th('وضعیت'), html.Th(f'بازده (آستانه {QUAL_MIN_RETURN:.0f}%)'), html.Th('معاملات')])),
        html.Tbody(rows)], className='data-table')
    return status, pbar, qualified_list, tbl

@app.callback(Output('qual-rerun', 'children'), Input('qual-rerun', 'n_clicks'), prevent_initial_call=True)
def rerun_qual(n):
    if n: qualifier.restart()
    return no_update

@app.callback([Output('spiral-chart', 'figure'), Output('sr-table-div', 'children')],
              Input('ana-refresh', 'n_clicks'), State('ana-sym', 'value'))
def update_spiral(n, sym):
    sym = sym or 'BTCUSDT'
    df = bybit.get_klines(sym, interval=CFG['interval'], limit=CFG['lookback'])
    if df is None or df.empty:
        return go.Figure(), html.P("❌ دیتا دریافت نشد", style={'color': '#ff4757', 'textAlign': 'center'})
    done = df.iloc[:-1]
    tk = bybit.get_ticker(sym)
    price = tk['lastPrice'] if tk else df['close'].iloc[-1]
    levels = sr_from_arrays(done['open'].values, done['close'].values, price)
    fig = build_spiral_fig(done, levels, price)
    rows = []
    for lv in levels:
        tc = '#00ff88' if lv['type'] == 'support' else '#ff4757'
        rows.append(html.Tr([
            html.Td(fmt_p(lv['price']), style={'fontWeight': '700'}),
            html.Td('🟢 حمایت' if lv['type'] == 'support' else '🔴 مقاومت', style={'color': tc, 'fontWeight': '900'}),
            html.Td(f"{lv['strength']}", style={'color': tc, 'fontWeight': '900'}),
            html.Td(f"{(lv['price'] - price) / price * 100:+.2f}%"),
        ]))
    tbl = html.Table([html.Thead(html.Tr([html.Th('قیمت'), html.Th('نوع'), html.Th('قدرت'), html.Th('فاصله')])),
                      html.Tbody(rows)], className='data-table') if rows else \
          html.P("سطحی یافت نشد", style={'color': '#8892b0', 'textAlign': 'center'})
    return fig, tbl

@app.callback([Output('scan-status', 'children'), Output('scan-margin', 'children'),
               Output('scan-open', 'children'), Output('scan-signals', 'children'),
               Output('scan-grid', 'children')],
              Input('iv-scan', 'n_intervals'))
def update_scanner(n):
    res = scanner.get_results()
    qualified = qualifier.qualified
    fm, um = db.free_margin()
    mup = um / CFG['capital'] * 100 if CFG['capital'] > 0 else 0
    ot_open = db.get_open()
    live_prices = scanner.prices()
    if not ot_open.empty:
        for s in set(ot_open['symbol'].tolist()):
            tk = bybit.get_ticker(s)
            if tk: live_prices[s] = tk['lastPrice']
    ot = db.open_with_pnl(live_prices)
    op = float(ot['live_pnl_usd'].sum()) if not ot.empty else 0.0
    ls = scanner.last_scan.strftime('%H:%M:%S') if scanner.last_scan else '...'
    sb = html.Div([
        html.Span(f"📡 آخرین اسکن: {ls}", style={'color': '#00ff88', 'fontWeight': '700', 'marginLeft': '16px'}),
        html.Span(f"✅ ارزهای فعال: {len(qualified)}", style={'color': '#bb86fc', 'fontWeight': '700', 'marginLeft': '16px'}),
        html.Span(f"💾 باز: {len(ot)}", style={'color': '#ffd700', 'fontWeight': '700', 'marginLeft': '16px'}),
        html.Span(f"💰 PnL باز: ${op:+.2f}", style={'color': '#00ff88' if op >= 0 else '#ff4757', 'fontWeight': '700'}),
    ], className='glass-card', style={'padding': '13px'})
    mc = '#00ff88' if mup < 60 else ('#ffd700' if mup < 85 else '#ff4757')
    mp = html.Div([html.Div([
        html.Div(f"💰 سرمایه: ${CFG['capital']:,.0f} | ⚡ {CFG['leverage']}x | 🎯 R:R 1:{CFG['rr']} | ⚠️ ریسک:{CFG['risk_pct']*100:.0f}%",
                 style={'color': '#fff', 'fontWeight': '700', 'fontSize': '13px'}),
        html.Div(f"📊 مارجین: ${um:,.2f} | 🆓 ${fm:,.2f} ({mup:.1f}%)",
                 style={'color': mc, 'fontWeight': '700', 'fontSize': '12px', 'marginTop': '5px'}),
        html.Div(className='margin-bar', children=[html.Div(className='margin-used', style={'width': f'{min(mup,100)}%'})]),
    ])], className='glass-card', style={'padding': '13px'})
    if not ot.empty:
        rows = []
        for _, r in ot.sort_values('timestamp', ascending=False).iterrows():
            pc = 'live-pos' if r['live_pnl_usd'] >= 0 else 'live-neg'
            bc = 'badge-long' if r['signal_type'] == 'LONG' else 'badge-short'
            rows.append(html.Tr([
                html.Td(pd.to_datetime(r['timestamp']).strftime('%m-%d %H:%M'), style={'fontSize': '11px'}),
                html.Td(html.Span(r['symbol'], style={'fontWeight': '900', 'color': '#ffd700'})),
                html.Td(html.Span('🚀 LONG' if r['signal_type'] == 'LONG' else '💥 SHORT', className=f'badge {bc}')),
                html.Td(fmt_p(r['entry_price'])),
                html.Td(fmt_p(r['current_price']), style={'fontWeight': '700'}),
                html.Td(f"{int(r['leverage'])}x", style={'color': '#ffd700'}),
                html.Td(f"🎯 {fmt_p(r['tp_price'])}", style={'color': '#00ff88', 'fontSize': '11px'}),
                html.Td(f"🛑 {fmt_p(r['sl_price'])}", style={'color': '#ff4757', 'fontSize': '11px'}),
                html.Td(f"{r['live_roi']:+.2f}%", className=pc),
                html.Td(f"${r['live_pnl_usd']:+.2f}", className=pc),
                html.Td(html.Button('✖️ ببند', id={'type': 'close-trade', 'index': int(r['id'])}, className='btn-close')),
            ], className='open-trade-row'))
        os_ = html.Div([html.Div([html.H3(f"🔥 معاملات باز ({len(ot)}) — PnL زنده")], className='section-title'),
            html.Div([html.Table([html.Thead(html.Tr([
                html.Th('زمان'), html.Th('نماد'), html.Th('نوع'), html.Th('ورود'), html.Th('فعلی'),
                html.Th('L'), html.Th('TP'), html.Th('SL'), html.Th('ROI%'), html.Th('PnL$'), html.Th('عملیات')])),
                html.Tbody(rows)], className='data-table')], className='glass-card')])
    else:
        os_ = html.Div([html.Div([html.H3("🔥 معاملات باز")], className='section-title'),
            html.Div([html.P("💤 معامله بازی وجود ندارد...", style={'textAlign': 'center', 'color': '#8892b0', 'padding': '20px'})], className='glass-card')])
    alls = db.get_all(limit=15)
    if not alls.empty:
        rows = []
        for _, r in alls.iterrows():
            oc = {'WIN': 'trade-win', 'LOSS': 'trade-loss'}.get(r.get('outcome'), 'trade-open')
            ot_ = {'WIN': '✅ برد', 'LOSS': '❌ باخت'}.get(r.get('outcome'), '⏳ باز')
            note = ' 🔧دستی' if r.get('notes') == 'MANUAL_CLOSE' else ''
            bc = 'badge-long' if r['signal_type'] == 'LONG' else 'badge-short'
            rows.append(html.Tr([
                html.Td(pd.to_datetime(r['timestamp']).strftime('%m-%d %H:%M'), style={'fontSize': '11px'}),
                html.Td(html.Span(r['symbol'], style={'fontWeight': '900', 'color': '#ffd700'})),
                html.Td(html.Span(r['signal_type'], className=f'badge {bc}')),
                html.Td(f"{int(r['strength'])}", style={'fontWeight': '900'}),
                html.Td(fmt_p(r['entry_price'])),
                html.Td(html.Span(ot_ + note, className=oc)),
                html.Td(f"${r['pnl_usd']:+.2f}" if pd.notna(r['pnl_usd']) else '-',
                        style={'color': '#00ff88' if pd.notna(r['pnl_usd']) and r['pnl_usd'] > 0 else '#ff4757', 'fontWeight': '700'}),
            ]))
        ss_ = html.Div([html.Div([html.H3("🎯 آخرین سیگنال‌ها")], className='section-title'),
            html.Div([html.Table([html.Thead(html.Tr([html.Th('زمان'), html.Th('نماد'), html.Th('نوع'),
            html.Th('قدرت'), html.Th('ورود'), html.Th('وضعیت'), html.Th('PnL$')])),
            html.Tbody(rows)], className='data-table')], className='glass-card')])
    else:
        ss_ = html.Div([html.Div([html.H3("🎯 سیگنال‌ها")], className='section-title'),
            html.Div([html.P("🔍 هنوز سیگنالی ثبت نشده...", style={'textAlign': 'center', 'color': '#8892b0', 'padding': '20px'})], className='glass-card')])
    cards = []
    tracked = list(set(qualifier.qualified) | set(ot['symbol'].tolist()) if not ot.empty else set(qualified))
    if not tracked:
        cards.append(html.Div([html.Div("⏳ در انتظار صلاحیت‌سنجی...", className='scanner-sym'),
            html.Div(f"ابتدا تب «صلاحیت‌سنجی» باید ارزهایی با بازده > {QUAL_MIN_RETURN:.0f}% را تایید کند", className='scanner-price')],
            className='scanner-card'))
    for sym in tracked:
        r = res.get(sym)
        is_open = (not ot.empty) and (sym in set(ot['symbol'].tolist()))
        if not r:
            cards.append(html.Div([html.Div(sym, className='scanner-sym'),
                html.Div("⏳ در انتظار اسکن...", className='scanner-price')], className='scanner-card'))
            continue
        if r.get('error'):
            cards.append(html.Div([html.Div(sym, className='scanner-sym', style={'color': '#ff8c00'}),
                html.Div(f"⚠️ {r['error']}", style={'color': '#ff8c00', 'fontSize': '11px'})],
                className='scanner-card', style={'borderColor': '#ff8c00'}))
            continue
        lvs = r['levels']
        sup = next((l for l in lvs if l['type'] == 'support'), None)
        resn = next((l for l in lvs if l['type'] == 'resistance'), None)
        sig = r['signal']
        sc = '#00ff88' if sig == 'LONG' else ('#ff4757' if sig == 'SHORT' else ('#ffd700' if is_open else 'rgba(255,255,255,.08)'))
        cards.append(html.Div([
            html.Div([html.Span(sym, className='scanner-sym'),
                      html.Span(" 💼 باز" if is_open else "", style={'color': '#ffd700', 'fontWeight': '900', 'fontSize': '11px'}),
                      html.Span(f" 🎯 {sig}" if sig else "", style={'color': sc, 'fontWeight': '900', 'fontSize': '12px'})]),
            html.Div(f"${fmt_p(r['price'])}", className='scanner-price'),
            html.Div(f"🟢 {fmt_p(sup['price'])} ({sup['strength']})" if sup else "🟢 -", style={'color': '#00d4aa', 'fontSize': '11px'}),
            html.Div(f"🔴 {fmt_p(resn['price'])} ({resn['strength']})" if resn else "🔴 -", style={'color': '#ff8c8c', 'fontSize': '11px'}),
        ], className='scanner-card', style={'borderColor': sc}))
    return sb, mp, os_, ss_, cards

@app.callback([Output('stat-cards', 'children'), Output('equity-chart', 'figure'),
               Output('history-div', 'children')],
              Input('iv-stat', 'n_intervals'))
def update_stats(n):
    st = db.stats()
    ot = db.open_with_pnl(scanner.prices())
    op = float(ot['live_pnl_usd'].sum()) if not ot.empty else 0.0
    live = st['pnl'] + op
    cards = html.Div([
        html.Div([html.Div("🎯 Win Rate", style={'fontSize': '12px', 'color': '#8892b0'}),
                  html.Div(f"{st['wr']}%", style={'fontSize': '26px', 'color': '#00ff88', 'fontWeight': '900', 'marginTop': '6px'})], className='summary-card'),
        html.Div([html.Div("📊 معاملات", style={'fontSize': '12px', 'color': '#8892b0'}),
                  html.Div(f"{st['total']} ({len(ot)} باز)", style={'fontSize': '26px', 'color': '#fff', 'fontWeight': '900', 'marginTop': '6px'})], className='summary-card'),
        html.Div([html.Div("💰 نهایی", style={'fontSize': '12px', 'color': '#8892b0'}),
                  html.Div(f"${st['final']:,.2f}", style={'fontSize': '26px', 'color': '#ffd700', 'fontWeight': '900', 'marginTop': '6px'})], className='summary-card'),
        html.Div([html.Div("🔥 PnL زنده", style={'fontSize': '12px', 'color': '#8892b0'}),
                  html.Div(f"${live:+.2f}", style={'fontSize': '26px', 'color': '#00ff88' if live >= 0 else '#ff4757', 'fontWeight': '900', 'marginTop': '6px'})], className='summary-card'),
        html.Div([html.Div("📈 PF", style={'fontSize': '12px', 'color': '#8892b0'}),
                  html.Div(f"{st['pf']}", style={'fontSize': '26px', 'color': '#00d4aa', 'fontWeight': '900', 'marginTop': '6px'})], className='summary-card'),
        html.Div([html.Div("📉 Max DD", style={'fontSize': '12px', 'color': '#8892b0'}),
                  html.Div(f"{st['mdd']}%", style={'fontSize': '26px', 'color': '#ff4757', 'fontWeight': '900', 'marginTop': '6px'})], className='summary-card'),
    ])
    eq = st['equity']
    fig = go.Figure()
    if len(eq) > 1:
        fig.add_trace(go.Scatter(x=list(range(len(eq))), y=eq, mode='lines+markers',
            line=dict(color='#00ff88', width=3), marker=dict(size=6), fill='tozeroy', fillcolor='rgba(0,255,136,.1)'))
    fig.add_hline(y=CFG['capital'], line_dash='dash', line_color='#ffd700', annotation_text=f"شروع: ${CFG['capital']:.0f}")
    fig.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(22,33,62,.5)',
        height=400, margin=dict(l=50, r=30, t=30, b=40), yaxis=dict(title='$', gridcolor='rgba(255,255,255,.05)'))
    alls = db.get_all(limit=200)
    if not alls.empty:
        rows = []
        for _, r in alls.iterrows():
            oc = {'WIN': 'trade-win', 'LOSS': 'trade-loss'}.get(r.get('outcome'), 'trade-open')
            ot_ = {'WIN': '✅ برد', 'LOSS': '❌ باخت'}.get(r.get('outcome'), '⏳ باز')
            note = ' 🔧دستی' if r.get('notes') == 'MANUAL_CLOSE' else ''
            bc = 'badge-long' if r['signal_type'] == 'LONG' else 'badge-short'
            rows.append(html.Tr([
                html.Td(pd.to_datetime(r['timestamp']).strftime('%m-%d %H:%M'), style={'fontSize': '11px'}),
                html.Td(html.Span(r['symbol'], style={'fontWeight': '900', 'color': '#ffd700'})),
                html.Td(html.Span(r['signal_type'], className=f'badge {bc}')),
                html.Td(f"{int(r['strength'])}"),
                html.Td(fmt_p(r['entry_price'])),
                html.Td(fmt_p(r['exit_price']) if pd.notna(r['exit_price']) else '-', style={'color': '#8892b0'}),
                html.Td(f"{int(r['leverage'])}x", style={'color': '#ffd700'}),
                html.Td(html.Span(ot_ + note, className=oc)),
                html.Td(f"${r['pnl_usd']:+.2f}" if pd.notna(r['pnl_usd']) else '-',
                        style={'color': '#00ff88' if pd.notna(r['pnl_usd']) and r['pnl_usd'] > 0 else '#ff4757', 'fontWeight': '700'}),
            ]))
        hd = html.Table([html.Thead(html.Tr([html.Th('زمان'), html.Th('نماد'), html.Th('نوع'), html.Th('قدرت'),
            html.Th('ورود'), html.Th('خروج'), html.Th('L'), html.Th('وضعیت'), html.Th('PnL$')])),
            html.Tbody(rows)], className='data-table')
    else:
        hd = html.P("هنوز معامله‌ای ثبت نشده...", style={'textAlign': 'center', 'color': '#8892b0', 'padding': '25px'})
    return cards, fig, hd

def open_browser():
    try: webbrowser.open_new("http://127.0.0.1:8070")
    except: pass

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Golden Spiral LIVE Trader v5.2")
    print("✅ رفع سراب بک‌تست + یکسان‌سازی کامل")
    ok, p = bybit.test_connection()
    print(f"✅ اتصال: BTC ${p:,.2f}" if ok else "⚠️ خطا در اتصال")
    print("=" * 60)
    if not os.environ.get('WERKZEUG_RUN_MAIN'):
        Timer(1.5, open_browser).start()
    app.run(debug=True, host='127.0.0.1', port=8070, use_reloader=False)