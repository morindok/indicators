# -*- coding: utf-8 -*-
"""
🌙 BITMOON INSTITUTIONAL TERMINAL v4 — ادغام روند 3بعدی زنجیره‌ای + تأیید زنده اردر فلو
----------------------------------------------------------------------
معماری ادغام:
  • موتور روند (از v3): چندتایم‌فریمی، زنجیره MA/RSI/شتاب، وزن بهینه walk-forward،
    اعتبارسنجی آماری، مدیریت ریسک — بدون تغییر منطقی.
  • موتور اردر فلو (از اسکریپت فوت‌پرینت): استریم زنده WebSocket بایبیت،
    فوت‌پرینت Bid×Ask، دلتای تجمعی، OBI، موتور روایت جذب/رد قیمت.
  • لایه پل جدید: order_flow_confirmation() — سیگنال قفل‌شده روند را با جریان
    زنده سفارش می‌سنجد و برچسب می‌زند: تأییدشده ✅ / خلاف‌جهت ⚠ / در انتظار ⏳.

⚠️ صداقت علمی: تأیید اردر فلو یک هیوریستیک لحظه‌ای است (دلتای اخیر + OBI + روایت
جذب)، نه اثبات آماری. مثل بقیه اجزای سیستم، شواهد را قوی‌تر می‌کند اما تضمین
سود نمی‌دهد. تب «اعتبارسنجی» در بخش روند همچنان تنها منبع شواهد آماری واقعی است.

pip install dash dash-bootstrap-components plotly pandas numpy requests scipy websocket-client
"""

import json, threading, time, webbrowser
from collections import deque
from datetime import timezone
from threading import Timer
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import requests
import websocket
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from scipy.signal import argrelextrema

# ==============================================================================
# 0) پالت نهادی تیره واحد (هم برای روند، هم برای فوت‌پرینت استفاده می‌شود)
# ==============================================================================
BG, CARD, LINE, TXT, MUT = "#0b1220", "#121c30", "#23314d", "#e8ecf4", "#8fa3c0"
GOLD, UP, DN, PURP = "#f0b90b", "#16a085", "#e74c3c", "#a06cd5"
# نام‌های قدیمی اسکریپت فوت‌پرینت را به همین پالت تیره نگاشت می‌کنیم (بدون نیاز به
# ویرایش بدنه توابع رندر فوت‌پرینت که این نام‌ها را صدا می‌زنند):
NAVY, GREEN, RED, NEUTRAL_TXT = TXT, UP, DN, MUT
BG_PAPER, BG_PLOT, GRID_LINE = BG, CARD, LINE
BID_COL_TAG, ASK_COL_TAG = UP, DN

TELEGRAM_URL, TELEGRAM_ID = "https://t.me/BITMOON618", "BITMOON618"

# ==============================================================================
# 1) اتصال REST مشترک (هر دو موتور از همین استفاده می‌کنند)
# ==============================================================================
REST_CANDIDATES = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
WS_CANDIDATES = ["wss://stream.bybit.com", "wss://stream.bytick.com"]
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept": "application/json", "Referer": "https://www.bybit.com/"})
_ACTIVE_REST_BASE = {"url": None}

def bybit_get(path, params, timeout=10):
    cands = ([_ACTIVE_REST_BASE["url"]] if _ACTIVE_REST_BASE["url"] else []) + \
            [b for b in REST_CANDIDATES if b != _ACTIVE_REST_BASE["url"]]
    for base in cands:
        try:
            r = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code in (403, 451): continue
            r.raise_for_status(); d = r.json()
            if d.get("retCode") == 0:
                _ACTIVE_REST_BASE["url"] = base; return d
        except Exception: continue
    return None

def get_klines(symbol, interval, category="linear", limit=500):
    d = bybit_get("/v5/market/kline", {"category": category, "symbol": symbol, "interval": interval, "limit": limit})
    if not d or "list" not in (d.get("result") or {}): return pd.DataFrame()
    lst = d["result"]["list"]
    if not lst: return pd.DataFrame()
    df = pd.DataFrame(lst, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
    for c in ["open", "high", "low", "close", "volume"]: df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)

# ==============================================================================
# 2) موتور روند — هسته زنجیره‌ای 3بعدی (TII + RII + MCI) — از v3
# ==============================================================================
def closed_only(df):
    return df.iloc[:-1].reset_index(drop=True) if len(df) > 2 else df

def fast_all_ma(prices, P=200):
    n = len(prices); z = np.zeros((P, n)); c = np.cumsum(prices)
    for p in range(1, P + 1):
        if p == 1: z[0] = prices
        elif p <= n:
            z[p-1, :p-1] = c[:p-1] / np.arange(1, p)
            z[p-1, p-1:] = (c[p-1:] - np.concatenate(([0], c[:-p]))) / p
        else: z[p-1] = c / np.arange(1, n + 1)
    return z

def fast_all_rsi(prices, P=200):
    n = len(prices)
    diffs = np.diff(prices, prepend=prices[0])
    gains = np.clip(diffs, 0.0, None); losses = np.clip(-diffs, 0.0, None)
    alphas = 1.0 / np.arange(1, P + 1)
    avg_gain = np.full(P, gains[0], dtype=float); avg_loss = np.full(P, losses[0], dtype=float)
    out = np.empty((P, n), dtype=float)
    out[:, 0] = 100 - 100 / (1 + avg_gain / np.where(avg_loss == 0, 1e-10, avg_loss))
    for t in range(1, n):
        avg_gain += alphas * (gains[t] - avg_gain)
        avg_loss += alphas * (losses[t] - avg_loss)
        out[:, t] = 100 - 100 / (1 + avg_gain / np.where(avg_loss == 0, 1e-10, avg_loss))
    return out

def _rsi_single(prices, p):
    d = np.diff(prices, prepend=prices[0])
    g, l = np.clip(d, 0, None), np.clip(-d, 0, None)
    a = 1.0 / p
    ag = pd.Series(g).ewm(alpha=a, adjust=False).mean().values
    al = pd.Series(l).ewm(alpha=a, adjust=False).mean().values
    return 100 - 100 / (1 + ag / np.where(al == 0, 1e-10, al))

def chain_integrity(Z):
    return np.mean(Z[:-1] > Z[1:], axis=0) * 100.0

def slope_surface(Z):
    return np.diff(Z, axis=1, prepend=Z[:, [0]])

def momentum_chain_integrity(Zslope):
    return np.mean(Zslope[:-1] > Zslope[1:], axis=0) * 100.0

def efficiency_ratio(prices, period=20):
    n = len(prices)
    if n <= period: return np.full(n, 0.3)
    abs_diff = np.abs(np.diff(prices, prepend=prices[0]))
    roll_vol = pd.Series(abs_diff).rolling(period, min_periods=1).sum().values
    net = np.abs(prices - np.concatenate((np.full(period, prices[0]), prices[:-period])))
    return np.clip(net / np.where(roll_vol == 0, 1e-9, roll_vol), 0, 1)

def true_range(df):
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    prev_c = np.concatenate(([c[0]], c[:-1]))
    return np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))

def atr(df, period=14):
    return pd.Series(true_range(df)).ewm(alpha=1/period, adjust=False).mean().values

def volume_confirmation_factor(df, period=20):
    v = df["volume"].values
    ma_v = pd.Series(v).rolling(period, min_periods=1).mean().values
    return np.clip(v / np.where(ma_v == 0, 1e-9, ma_v), 0, 3)

def locked_signal(cti):
    state, changes = 0, []
    for i, v in enumerate(cti):
        if v >= 70 and state != 1: state = 1; changes.append((i, 1))
        elif v <= 30 and state != -1: state = -1; changes.append((i, -1))
        elif state == 1 and v < 50: state = 0; changes.append((i, 0))
        elif state == -1 and v > 50: state = 0; changes.append((i, 0))
    return state, changes

def detect_divergence(prices, rsi_vals, order=3, lookback=100):
    if len(prices) < lookback: lookback = len(prices)
    if lookback < order * 6: return None
    p, r = prices[-lookback:], rsi_vals[-lookback:]
    def clean(idx_arr, gap):
        out = []
        for i in idx_arr:
            if not out or i - out[-1] > gap: out.append(i)
        return out
    lows = clean(argrelextrema(p, np.less_equal, order=order)[0].tolist(), order)
    highs = clean(argrelextrema(p, np.greater_equal, order=order)[0].tolist(), order)
    div = None
    if len(lows) >= 2:
        i1, i2 = lows[-2], lows[-1]
        if p[i2] < p[i1] - 1e-9 and r[i2] > r[i1] + 1e-9: div = "bull"
    if len(highs) >= 2:
        j1, j2 = highs[-2], highs[-1]
        if p[j2] > p[j1] + 1e-9 and r[j2] < r[j1] - 1e-9:
            if div is None or highs[-1] > lows[-1]: div = "bear"
    return div

def regime_of(v):
    if v >= 75: return "صعودی قوی", 2
    if v >= 60: return "صعودی", 1
    if v > 40: return "رنج", 0
    if v > 25: return "نزولی", -1
    return "نزولی قوی", -2

def backtest_signal(pc, changes, horizon=10):
    trades = []
    for idx, s in changes:
        if s == 0 or idx + horizon >= len(pc): continue
        ret = (pc[idx + horizon] - pc[idx]) / pc[idx] * 100.0
        trades.append(ret if s == 1 else -ret)
    if not trades:
        return dict(n=0, win_rate=None, avg_ret=None, profit_factor=None)
    trades = np.array(trades)
    wins, losses = trades[trades > 0], trades[trades <= 0]
    gain_sum = float(wins.sum()) if len(wins) else 0.0
    loss_sum = float(-losses.sum()) if len(losses) else 1e-9
    return dict(n=len(trades), win_rate=float(len(wins)/len(trades)*100), avg_ret=float(trades.mean()),
                profit_factor=gain_sum / loss_sum)

def random_baseline(pc, n_signals, horizon, n_sims=200, seed=7):
    if n_signals < 3 or len(pc) <= horizon + 5: return None
    rng = np.random.default_rng(seed)
    n = len(pc); sims = []
    for _ in range(n_sims):
        idxs = rng.integers(0, n - horizon - 1, size=n_signals)
        dirs = rng.choice([1, -1], size=n_signals)
        rets = [(pc[i+horizon]-pc[i])/pc[i]*100*(1 if d == 1 else -1) for i, d in zip(idxs, dirs)]
        sims.append(np.mean(rets))
    return dict(mean=float(np.mean(sims)), std=float(np.std(sims)) or 1e-9)

WEIGHT_GRID = [round(x, 2) for x in np.arange(0.0, 1.01, 0.2)]

def optimize_weights(pc_train, tii_t, rii_t, mci_t, horizon):
    best = (0.5, 0.3, 0.2); best_score = -1e18
    for w1 in WEIGHT_GRID:
        for w2 in WEIGHT_GRID:
            w3 = round(1 - w1 - w2, 2)
            if w3 < -1e-9 or w3 > 1.0001: continue
            w3 = max(0.0, w3)
            cti = w1*tii_t + w2*rii_t + w3*mci_t
            _, changes = locked_signal(cti)
            bt = backtest_signal(pc_train, changes, horizon)
            if bt["n"] >= 3 and bt["avg_ret"] is not None and bt["avg_ret"] > best_score:
                best_score, best = bt["avg_ret"], (w1, w2, w3)
    return best

def equity_and_drawdown(pc, changes, horizon):
    eq = [100.0]
    for idx, s in changes:
        if s == 0 or idx + horizon >= len(pc): continue
        ret = (pc[idx+horizon]-pc[idx])/pc[idx]*100
        d = ret if s == 1 else -ret
        eq.append(eq[-1]*(1+d/100))
    eq = np.array(eq)
    if len(eq) < 2: return eq, 0.0
    peak = np.maximum.accumulate(eq)
    return eq, float(((eq-peak)/peak*100).min())

def risk_suggestion(atr_val, price, risk_pct=1.0, capital=10000.0, atr_mult=2.0):
    stop_dist = atr_val * atr_mult
    stop_pct = stop_dist / price * 100 if price else 0
    risk_amount = capital * risk_pct / 100
    position_size = risk_amount / stop_dist if stop_dist > 0 else 0
    return dict(stop_pct=stop_pct, stop_dist=stop_dist, position_size=position_size,
                risk_amount=risk_amount, position_value=position_size*price)

def analyze_tf(df, horizon=10, train_split=0.7):
    cl = closed_only(df); pc = cl["close"].values; cur = df["close"].values[-1]; n = len(pc)
    Z = fast_all_ma(pc); R = fast_all_rsi(pc)
    tii = chain_integrity(Z); rii = chain_integrity(R)
    Zslope = slope_surface(Z); mci = momentum_chain_integrity(Zslope)
    cut = int(n*train_split) if n > 80 else n
    enough_oos = (n - cut) > horizon + 5
    w = optimize_weights(pc[:cut], tii[:cut], rii[:cut], mci[:cut], horizon) if n > 40 else (0.5, 0.3, 0.2)
    cti = w[0]*tii + w[1]*rii + w[2]*mci
    state, changes = locked_signal(cti)
    cti_l, tii_l, rii_l, mci_l = cti[-1], tii[-1], rii[-1], mci[-1]
    reg, rs = regime_of(cti_l)
    if enough_oos:
        test_changes = [c for c in changes if c[0] >= cut]
        test_bt = backtest_signal(pc, test_changes, horizon)
        rb = random_baseline(pc[cut:], test_bt["n"], horizon) if test_bt["n"] else None
        z_edge = (test_bt["avg_ret"]-rb["mean"])/rb["std"] if (rb and test_bt["avg_ret"] is not None) else None
        eq_curve, max_dd = equity_and_drawdown(pc[cut:], test_changes, horizon)
    else:
        test_bt, rb, z_edge = dict(n=0, win_rate=None, avg_ret=None, profit_factor=None), None, None
        eq_curve, max_dd = np.array([100.0]), 0.0
    er_val = float(efficiency_ratio(pc)[-1])
    vol_ratio = float(volume_confirmation_factor(df)[-1])
    atr_val = float(atr(cl)[-1]) if len(cl) > 15 else float(np.std(pc[-15:]) if len(pc) >= 15 else 0)
    rsi14 = _rsi_single(pc, 14)
    div = detect_divergence(pc, rsi14)
    base_conf = abs(cti_l-50)*2
    conf = base_conf
    if test_bt["n"] >= 3:
        conf = 0.4*base_conf + 0.6*test_bt["win_rate"]
        if z_edge is not None:
            conf = conf*0.6 if z_edge < 0 else min(99, conf*1.05) if z_edge > 1 else conf
    if er_val < 0.2: conf *= 0.75
    if vol_ratio < 0.7: conf *= 0.9
    conf = int(max(0, min(99, round(conf))))
    lock_ts = cl["ts"].iloc[changes[-1][0]] if changes else cl["ts"].iloc[-1]
    sig = {1: "خرید", -1: "فروش", 0: "انتظار"}[state]
    if state == 1 and cti_l >= 75: sig = "خرید قوی"
    if state == -1 and cti_l <= 25: sig = "فروش قوی"
    return dict(cur=cur, cti=cti_l, tii=tii_l, rii=rii_l, mci=mci_l, reg=reg, rs=rs, state=state,
                sig=sig, conf=conf, div=div, lock_ts=lock_ts, weights=w, test_bt=test_bt, rb=rb,
                z_edge=z_edge, max_dd=max_dd, eq_curve=eq_curve, er=er_val, vol_ratio=vol_ratio,
                atr=atr_val, oos_used=enough_oos,
                series=dict(tii=tii, rii=rii, mci=mci, cti=cti, ts=cl["ts"], changes=changes))

TIMEFRAMES = ['1', '3', '5', '15', '30', '60', '120', '240', '360', '720', 'D', 'W', 'M']
TF_NAMES = {'1':'1m','3':'3m','5':'5m','15':'15m','30':'30m','60':'1H','120':'2H',
            '240':'4H','360':'6H','720':'12H','D':'1D','W':'1W','M':'1M'}
W_TF = {'1':1,'3':1,'5':2,'15':2,'30':3,'60':4,'120':4,'240':5,'360':5,'720':6,'D':7,'W':8,'M':8}
TREND_CACHE = {"symbol": None, "category": None, "ts": 0.0, "data": {}, "ms": 0}

def get_all(symbol, category="linear", force=False):
    now = time.time()
    if not force and TREND_CACHE["symbol"] == symbol and TREND_CACHE["category"] == category and \
       (now - TREND_CACHE["ts"]) < 45 and TREND_CACHE["data"]:
        return TREND_CACHE["data"], TREND_CACHE["ms"]
    t0 = time.time(); out = {}
    with ThreadPoolExecutor(max_workers=13) as ex:
        futs = {ex.submit(get_klines, symbol, tf, category): tf for tf in TIMEFRAMES}
        for f in as_completed(futs):
            df = f.result()
            if not df.empty: out[futs[f]] = df
    ms = int((time.time()-t0)*1000)
    TREND_CACHE.update(symbol=symbol, category=category, ts=now, data=out, ms=ms)
    return out, ms

# ==============================================================================
# 3) موتور اردر فلو زنده — استریم WebSocket + فوت‌پرینت + روایت (از اسکریپت فوت‌پرینت)
# ==============================================================================
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_CATEGORY = "linear"
DEFAULT_TICK_SIZE = 10.0
DEFAULT_INTERVAL_SEC = 60
MAX_COLUMNS = 16
HISTORY_TRIM_HOURS = 3
ORDER_BOOK_DEPTH = 12
IMBALANCE_RATIO = 3.0
STACK_MIN = 3
TRADE_BUFFER_MAX = 300_000
TRADE_COLS = ["id", "ts", "price", "amount", "side"]
STALE_SEC = 25
WATCHDOG_INTERVAL = 5

STATE_LOCK = threading.RLock()
TRADES = deque(maxlen=TRADE_BUFFER_MAX)
ORDER_BOOK = {"bids": {}, "asks": {}, "ready": False}
CONN_STATUS = {"connected": False, "symbol": DEFAULT_SYMBOL, "category": DEFAULT_CATEGORY,
               "ws_host": "-", "rest_host": "-"}
LAST_MSG_TS = {"t": 0.0}

L3_DEPTH_LEVELS = 10
L3_SAMPLE_INTERVAL = 1.0
L3_EVENTS_MAX = 20_000
L3_HISTORY_MAX = 1800
BOOK_EVENTS = deque(maxlen=L3_EVENTS_MAX)
BOOK_HISTORY = deque(maxlen=L3_HISTORY_MAX)
_LAST_L3_SAMPLE = {"t": 0.0}

def _maybe_sample_book_history(now_ts):
    if now_ts - _LAST_L3_SAMPLE["t"] < L3_SAMPLE_INTERVAL: return
    _LAST_L3_SAMPLE["t"] = now_ts
    bids_sorted = sorted(ORDER_BOOK["bids"].items(), key=lambda x: -x[0])[:L3_DEPTH_LEVELS]
    asks_sorted = sorted(ORDER_BOOK["asks"].items(), key=lambda x: x[0])[:L3_DEPTH_LEVELS]
    if not bids_sorted or not asks_sorted: return
    best_bid_p, best_bid_s = bids_sorted[0]; best_ask_p, best_ask_s = asks_sorted[0]
    mid = (best_bid_p+best_ask_p)/2.0
    bid_depth = sum(s for _, s in bids_sorted); ask_depth = sum(s for _, s in asks_sorted)
    obi = (bid_depth-ask_depth)/(bid_depth+ask_depth) if (bid_depth+ask_depth) > 0 else 0.0
    BOOK_HISTORY.append({"ts": pd.Timestamp.now(tz=timezone.utc), "mid": mid, "obi": obi,
                          "bid_depth": bid_depth, "ask_depth": ask_depth})

def backfill_trades_rest(symbol, category, limit=1000):
    data = bybit_get("/v5/market/recent-trade", {"category": category, "symbol": symbol, "limit": limit})
    if not data: return
    items = (data.get("result") or {}).get("list") or []
    rows = []
    for t in items:
        try:
            rows.append({"id": t.get("execId"), "ts": pd.to_datetime(int(t["time"]), unit="ms", utc=True),
                         "price": float(t["price"]), "amount": float(t["size"]),
                         "side": "buy" if t.get("side") == "Buy" else "sell"})
        except Exception: continue
    with STATE_LOCK:
        TRADES.extend(rows); CONN_STATUS["rest_host"] = _ACTIVE_REST_BASE["url"] or "-"

def fetch_orderbook_rest(symbol, category, depth=50):
    data = bybit_get("/v5/market/orderbook", {"category": category, "symbol": symbol, "limit": depth})
    if not data: return
    result = data.get("result") or {}
    with STATE_LOCK:
        if not ORDER_BOOK["ready"]:
            ORDER_BOOK["bids"] = {float(p): float(s) for p, s in result.get("b", []) if float(s) > 0}
            ORDER_BOOK["asks"] = {float(p): float(s) for p, s in result.get("a", []) if float(s) > 0}

def orderbook_bootstrap_loop(symbol, category, stop_flag):
    while not stop_flag.is_set():
        with STATE_LOCK: ready = ORDER_BOOK["ready"]
        if ready: return
        fetch_orderbook_rest(symbol, category); time.sleep(3)

class BybitStream:
    def __init__(self, symbol, category="linear"):
        self.symbol = symbol.upper(); self.category = category
        self.ws = None; self.thread = None; self.stop_flag = threading.Event()
        self.host_idx = 0; self.fail_count = 0

    def _url(self):
        return f"{WS_CANDIDATES[self.host_idx % len(WS_CANDIDATES)]}/v5/public/{self.category}"

    def start(self):
        self.stop_flag.clear()
        self.thread = threading.Thread(target=self._run_forever, daemon=True); self.thread.start()

    def stop(self):
        self.stop_flag.set()
        try:
            if self.ws: self.ws.close()
        except Exception: pass

    def force_reconnect(self):
        try:
            if self.ws: self.ws.close()
        except Exception: pass

    def _run_forever(self):
        while not self.stop_flag.is_set():
            try:
                with STATE_LOCK: CONN_STATUS["ws_host"] = self._url()
                self.ws = websocket.WebSocketApp(self._url(), on_open=self._on_open, on_message=self._on_message,
                                                  on_error=self._on_error, on_close=self._on_close)
                self.ws.run_forever(ping_interval=20, ping_payload=json.dumps({"op": "ping"}))
            except Exception: pass
            with STATE_LOCK: CONN_STATUS["connected"] = False
            if self.stop_flag.is_set(): break
            self.fail_count += 1
            if self.fail_count >= 2: self.host_idx += 1; self.fail_count = 0
            time.sleep(min(3*(self.fail_count+1), 12))

    def _on_open(self, ws):
        ws.send(json.dumps({"op": "subscribe", "args": [f"publicTrade.{self.symbol}", f"orderbook.50.{self.symbol}"]}))
        with STATE_LOCK:
            ORDER_BOOK["ready"] = False; ORDER_BOOK["bids"].clear(); ORDER_BOOK["asks"].clear()
            CONN_STATUS["connected"] = True; CONN_STATUS["symbol"] = self.symbol; CONN_STATUS["category"] = self.category
        LAST_MSG_TS["t"] = time.time(); self.fail_count = 0

    def _on_error(self, ws, error):
        with STATE_LOCK: CONN_STATUS["connected"] = False

    def _on_close(self, ws, code, msg):
        with STATE_LOCK: CONN_STATUS["connected"] = False

    def _on_message(self, ws, raw):
        LAST_MSG_TS["t"] = time.time()
        try: msg = json.loads(raw)
        except Exception: return
        topic = msg.get("topic", "")
        if topic.startswith("publicTrade."): self._handle_trades(msg.get("data") or [])
        elif topic.startswith("orderbook."): self._handle_orderbook(msg)

    def _handle_trades(self, data):
        if not data: return
        rows = []
        for t in data:
            try:
                rows.append({"id": t.get("i"), "ts": pd.to_datetime(int(t["T"]), unit="ms", utc=True),
                             "price": float(t["p"]), "amount": float(t["v"]),
                             "side": "buy" if t.get("S") == "Buy" else "sell"})
            except Exception: continue
        with STATE_LOCK: TRADES.extend(rows)

    def _handle_orderbook(self, msg):
        mtype = msg.get("type"); data = msg.get("data") or {}
        bids, asks = data.get("b", []), data.get("a", [])
        now = time.time()
        with STATE_LOCK:
            if mtype == "snapshot":
                ORDER_BOOK["bids"] = {float(p): float(s) for p, s in bids if float(s) > 0}
                ORDER_BOOK["asks"] = {float(p): float(s) for p, s in asks if float(s) > 0}
                ORDER_BOOK["ready"] = True
            else:
                for p, s in bids:
                    p, s = float(p), float(s)
                    existed = p in ORDER_BOOK["bids"]
                    if s == 0:
                        if existed: BOOK_EVENTS.append({"ts": now, "side": "bid", "price": p, "size": 0.0, "event": "cancel"})
                        ORDER_BOOK["bids"].pop(p, None)
                    else:
                        BOOK_EVENTS.append({"ts": now, "side": "bid", "price": p, "size": s, "event": "update" if existed else "add"})
                        ORDER_BOOK["bids"][p] = s
                for p, s in asks:
                    p, s = float(p), float(s)
                    existed = p in ORDER_BOOK["asks"]
                    if s == 0:
                        if existed: BOOK_EVENTS.append({"ts": now, "side": "ask", "price": p, "size": 0.0, "event": "cancel"})
                        ORDER_BOOK["asks"].pop(p, None)
                    else:
                        BOOK_EVENTS.append({"ts": now, "side": "ask", "price": p, "size": s, "event": "update" if existed else "add"})
                        ORDER_BOOK["asks"][p] = s
            _maybe_sample_book_history(now)

CURRENT_STREAM = None
_OB_BOOTSTRAP_STOP = threading.Event()

def restart_stream(symbol, category):
    global CURRENT_STREAM, _OB_BOOTSTRAP_STOP
    if CURRENT_STREAM is not None: CURRENT_STREAM.stop()
    _OB_BOOTSTRAP_STOP.set()
    with STATE_LOCK:
        TRADES.clear(); ORDER_BOOK["ready"] = False; ORDER_BOOK["bids"].clear(); ORDER_BOOK["asks"].clear()
        BOOK_EVENTS.clear(); BOOK_HISTORY.clear(); _LAST_L3_SAMPLE["t"] = 0.0
    backfill_trades_rest(symbol, category)
    _OB_BOOTSTRAP_STOP = threading.Event()
    threading.Thread(target=orderbook_bootstrap_loop, args=(symbol, category, _OB_BOOTSTRAP_STOP), daemon=True).start()
    CURRENT_STREAM = BybitStream(symbol, category); CURRENT_STREAM.start()

def watchdog_loop():
    while True:
        time.sleep(WATCHDOG_INTERVAL)
        with STATE_LOCK: connected = CONN_STATUS["connected"]
        if connected and (time.time()-LAST_MSG_TS["t"] > STALE_SEC) and CURRENT_STREAM is not None:
            CURRENT_STREAM.force_reconnect()

threading.Thread(target=watchdog_loop, daemon=True).start()

def get_trades_df():
    with STATE_LOCK:
        if not TRADES: return pd.DataFrame(columns=TRADE_COLS)
        df = pd.DataFrame(list(TRADES))
    if df.empty: return df
    cutoff = pd.Timestamp.now(tz=timezone.utc) - pd.Timedelta(hours=HISTORY_TRIM_HOURS)
    return df[df["ts"] >= cutoff].drop_duplicates(subset="id")

def get_orderbook_snapshot(depth=ORDER_BOOK_DEPTH):
    with STATE_LOCK:
        bids = sorted(ORDER_BOOK["bids"].items(), key=lambda x: -x[0])[:depth]
        asks = sorted(ORDER_BOOK["asks"].items(), key=lambda x: x[0])[:depth]
    return pd.DataFrame(asks, columns=["price", "amount"]), pd.DataFrame(bids, columns=["price", "amount"])

def get_book_history_df(seconds=600):
    with STATE_LOCK:
        if not BOOK_HISTORY: return pd.DataFrame()
        hist = list(BOOK_HISTORY)
    df = pd.DataFrame(hist)
    if df.empty: return df
    cutoff = pd.Timestamp.now(tz=timezone.utc) - pd.Timedelta(seconds=seconds)
    return df[df["ts"] >= cutoff].reset_index(drop=True)

def build_footprint(df, tick_size, interval_sec, max_cols):
    if df.empty: return None
    work = df.copy()
    work["price_bucket"] = (np.floor(work["price"]/tick_size)*tick_size).round(8)
    work["time_bucket"] = work["ts"].dt.floor(f"{interval_sec}s")
    cols_all = sorted(work["time_bucket"].unique()); cols = cols_all[-max_cols:]
    work = work[work["time_bucket"].isin(cols)]
    if work.empty: return None
    min_p, max_p = work["price_bucket"].min(), work["price_bucket"].max()
    n_steps = max(int(round((max_p-min_p)/tick_size)), 0)
    rows = [round(max_p - i*tick_size, 8) for i in range(n_steps+1)]
    ask_pivot = work[work["side"]=="buy"].pivot_table(index="price_bucket", columns="time_bucket", values="amount", aggfunc="sum", fill_value=0.0)
    bid_pivot = work[work["side"]=="sell"].pivot_table(index="price_bucket", columns="time_bucket", values="amount", aggfunc="sum", fill_value=0.0)
    ask_grid = ask_pivot.reindex(index=rows, columns=cols, fill_value=0.0)
    bid_grid = bid_pivot.reindex(index=rows, columns=cols, fill_value=0.0)
    col_open = work.sort_values("ts").groupby("time_bucket")["price"].first().reindex(cols)
    col_close = work.sort_values("ts").groupby("time_bucket")["price"].last().reindex(cols)
    return {"rows": rows, "cols": cols, "tick_size": tick_size, "ask": ask_grid, "bid": bid_grid,
            "total": ask_grid+bid_grid, "delta": ask_grid-bid_grid, "col_open": col_open, "col_close": col_close}

def compute_diagonal_imbalances(fp, ratio_threshold=IMBALANCE_RATIO):
    ask_grid, bid_grid, tick = fp["ask"], fp["bid"], fp["tick_size"]
    imb = {}
    for c in fp["cols"]:
        for p in fp["rows"]:
            a, b = ask_grid.loc[p, c], bid_grid.loc[p, c]
            p_below, p_above = round(p-tick, 8), round(p+tick, 8)
            b_below = bid_grid.loc[p_below, c] if p_below in bid_grid.index else 0.0
            a_above = ask_grid.loc[p_above, c] if p_above in ask_grid.index else 0.0
            buy_imb = a > 0 and b_below > 0 and (a/b_below) >= ratio_threshold
            sell_imb = b > 0 and a_above > 0 and (b/a_above) >= ratio_threshold
            imb[(p, c)] = "buy" if (buy_imb and not sell_imb) else ("sell" if sell_imb else None)
    return imb

def detect_stacked(imb, rows, cols, min_stack=STACK_MIN):
    stacked = set()
    for c in cols:
        streak_dir, streak_start, streak_len = None, 0, 0
        for ri, p in enumerate(rows):
            d = imb.get((p, c))
            if d is not None and d == streak_dir: streak_len += 1
            else:
                if streak_dir is not None and streak_len >= min_stack:
                    stacked.update((rows[k], c) for k in range(streak_start, streak_start+streak_len))
                streak_dir, streak_start = d, ri; streak_len = 1 if d is not None else 0
        if streak_dir is not None and streak_len >= min_stack:
            stacked.update((rows[k], c) for k in range(streak_start, streak_start+streak_len))
    return stacked

def fmt(v):
    if v >= 1000: return f"{v/1000:.1f}k"
    if v >= 1: return f"{v:,.1f}".rstrip("0").rstrip(".")
    return f"{v:.3f}".rstrip("0").rstrip(".") if v else "0"

def build_cumulative_delta(fp):
    if fp is None: return None
    cols = fp["cols"]
    col_delta = fp["delta"].sum(axis=0).reindex(cols).fillna(0.0)
    col_vol = fp["total"].sum(axis=0).reindex(cols).fillna(0.0)
    return {"cols": cols, "col_delta": col_delta, "col_vol": col_vol, "cum_delta": col_delta.cumsum()}

def render_cumulative_delta_figure(cd):
    fig = go.Figure()
    if cd is None or len(cd["cols"]) == 0:
        fig.update_layout(plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER,
                           annotations=[dict(text="داده‌ای برای دلتای تجمعی نیست", x=0.5, y=0.5, showarrow=False, font=dict(color=NAVY, size=12))])
        return fig
    x_labels = [pd.Timestamp(c).strftime("%H:%M") for c in cd["cols"]]
    bar_colors = [GREEN if v >= 0 else RED for v in cd["col_delta"]]
    fig.add_trace(go.Bar(x=x_labels, y=cd["col_delta"], name="دلتای هر کندل", marker=dict(color=bar_colors), opacity=0.55, yaxis="y1"))
    fig.add_trace(go.Scatter(x=x_labels, y=cd["cum_delta"], name="دلتای تجمعی", mode="lines+markers",
                              line=dict(color=GOLD, width=2.6), marker=dict(size=5, color=GOLD), yaxis="y2"))
    fig.add_hline(y=0, line=dict(color=GRID_LINE, width=1))
    fig.update_layout(plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER, margin=dict(l=45, r=45, t=40, b=35),
                      title=dict(text="دلتای تجمعی (Cumulative Delta) — زنده", font=dict(color=GOLD, size=13, family="Tahoma"), x=0.02),
                      xaxis=dict(showgrid=False, tickfont=dict(color=NEUTRAL_TXT, size=9)),
                      yaxis=dict(gridcolor=GRID_LINE, tickfont=dict(color=NEUTRAL_TXT, size=9)),
                      yaxis2=dict(overlaying="y", side="right", showgrid=False, tickfont=dict(color=GOLD, size=9)),
                      legend=dict(orientation="h", y=1.18, x=0, font=dict(size=9, color=NEUTRAL_TXT)), height=260, bargap=0.15)
    return fig

def price_to_y(price, rows, n_rows):
    max_p, min_p = max(rows), min(rows)
    if max_p == min_p: return n_rows/2.0
    return n_rows - ((max_p-price)/(max_p-min_p))*n_rows

def detect_order_flow_narrative(fp, cd, lookahead=3, high_frac=0.998):
    cols = fp["cols"]
    if len(cols) < 4 or cd is None: return None
    col_high = {}
    for c in cols:
        traded_rows = [p for p in fp["rows"] if fp["total"].loc[p, c] > 0]
        if traded_rows: col_high[c] = max(traded_rows)
    if not col_high: return None
    peak_col = max(col_high, key=lambda c: col_high[c]); peak_price = col_high[peak_col]; peak_idx = cols.index(peak_col)
    near_peak_cols = [c for c in cols[peak_idx:peak_idx+lookahead] if c in col_high]
    delta_near_peak = float(sum(cd["col_delta"].get(c, 0.0) for c in near_peak_cols))
    vol_near_peak = float(sum(cd["col_vol"].get(c, 0.0) for c in near_peak_cols))
    after_cols = cols[peak_idx+1:]
    made_higher_high = any(col_high.get(c, 0) > peak_price for c in after_cols)
    tail_cols = after_cols[-min(4, len(after_cols)):] if after_cols else []
    holding_above = len(tail_cols) > 0 and all(fp["col_close"].get(c, 0) >= peak_price*high_frac for c in tail_cols)
    reversal_risk = (delta_near_peak > 0) and (not made_higher_high) and (not holding_above) and len(after_cols) >= 2
    acceptance = made_higher_high and holding_above
    return dict(peak_col=peak_col, peak_idx=peak_idx, peak_price=peak_price, near_peak_cols=near_peak_cols,
                delta_near_peak=delta_near_peak, vol_near_peak=vol_near_peak, made_higher_high=made_higher_high,
                holding_above=holding_above, reversal_risk=reversal_risk, acceptance=acceptance,
                after_cols=after_cols, tail_cols=tail_cols)

def add_narrative_overlays(shapes, annotations, fp, narrative, n_rows):
    if narrative is None: return
    cols = fp["cols"]; col_w = 1.0; rows = fp["rows"]
    near_peak_cols = narrative["near_peak_cols"]; peak_price = narrative["peak_price"]; peak_y = price_to_y(peak_price, rows, n_rows)
    if near_peak_cols:
        first_idx, last_idx = cols.index(near_peak_cols[0]), cols.index(near_peak_cols[-1])
        x0, x1 = first_idx*col_w, last_idx*col_w+col_w
        shapes.append(dict(type="rect", x0=x0, x1=x1, y0=0, y1=n_rows, line=dict(color=GOLD, width=2.2, dash="dot"),
                            fillcolor="rgba(240,185,11,0.08)", layer="above"))
        annotations.append(dict(x=(x0+x1)/2, y=n_rows+2.6, text="نقطه جذب (Absorption)", showarrow=True, ax=0, ay=-28,
                                 font=dict(color=GOLD, size=11, family="Tahoma"), arrowcolor=GOLD, xanchor="center"))
    if narrative["reversal_risk"]:
        tail_cols = narrative["tail_cols"]
        if tail_cols:
            tail_idx = cols.index(tail_cols[-1]); tail_x = tail_idx*col_w+col_w/2
            tail_price = min(fp["col_close"].get(c, peak_price) for c in tail_cols)
            tail_y = price_to_y(tail_price, rows, n_rows); peak_x = narrative["peak_idx"]*col_w+col_w/2
            annotations.append(dict(x=tail_x, y=tail_y, ax=peak_x, ay=peak_y, axref="x", ayref="y", text="",
                                     showarrow=True, arrowhead=3, arrowsize=1.2, arrowwidth=2.4, arrowcolor=RED))
            annotations.append(dict(x=(peak_x+tail_x)/2, y=(peak_y+tail_y)/2-1.2, text="رد قیمت / شکست ناموفق",
                                     showarrow=False, font=dict(color=RED, size=11, family="Tahoma")))
    if narrative["acceptance"] and narrative["tail_cols"]:
        tail_cols = narrative["tail_cols"]
        first_idx, last_idx = cols.index(tail_cols[0]), cols.index(tail_cols[-1])
        x0, x1 = first_idx*col_w, last_idx*col_w+col_w
        shapes.append(dict(type="rect", x0=x0, x1=x1, y0=0, y1=n_rows, line=dict(color=GREEN, width=2.2),
                            fillcolor="rgba(22,160,133,0.07)", layer="above"))
        annotations.append(dict(x=(x0+x1)/2, y=n_rows+2.6, text="منطقه ارزش پایدار (Value Zone)", showarrow=False,
                                 font=dict(color=GREEN, size=11, family="Tahoma"), xanchor="center"))

def render_footprint_figure(fp, pair, narrative=None):
    rows, cols = fp["rows"], fp["cols"]; n_rows, n_cols = len(rows), len(cols)
    poc_per_col = {c: fp["total"][c].idxmax() for c in cols if fp["total"][c].max() > 0}
    imb = compute_diagonal_imbalances(fp); stacked = detect_stacked(imb, rows, cols)
    shapes, annotations = [], []; col_w = 1.0; dir_bar_w = 0.06
    for ci, c in enumerate(cols):
        x0, x1 = ci*col_w, ci*col_w+col_w
        o, cl = fp["col_open"].get(c, np.nan), fp["col_close"].get(c, np.nan)
        bar_color = GREEN if (pd.notna(o) and pd.notna(cl) and cl >= o) else RED
        shapes.append(dict(type="rect", x0=x0, x1=x0+dir_bar_w, y0=0, y1=n_rows, fillcolor=bar_color, line=dict(width=0), layer="below"))
        for ri, p in enumerate(rows):
            y0, y1 = n_rows-ri-1, n_rows-ri
            bid_v, ask_v, tot_v, delta_v = fp["bid"].loc[p, c], fp["ask"].loc[p, c], fp["total"].loc[p, c], fp["delta"].loc[p, c]
            cell_bg = BG_PLOT; border_color, border_w, border_dash = GRID_LINE, 0.6, "solid"
            direction = imb.get((p, c))
            if direction == "buy": border_color, border_w, border_dash = GREEN, 1.6, "dot"
            elif direction == "sell": border_color, border_w, border_dash = RED, 1.6, "dot"
            if (p, c) in stacked: border_w, border_dash = 2.4, "dash"
            if poc_per_col.get(c) == p: border_color, border_w, border_dash = GOLD, 2.6, "solid"; cell_bg = "#241f10"
            shapes.append(dict(type="rect", x0=x0+dir_bar_w, x1=x1, y0=y0, y1=y1,
                                line=dict(color=border_color, width=border_w, dash=border_dash), fillcolor=cell_bg, layer="below"))
            if tot_v > 0:
                txt_color = GREEN if delta_v > 0 else (RED if delta_v < 0 else NEUTRAL_TXT)
                annotations.append(dict(x=(x0+dir_bar_w+x1)/2, y=(y0+y1)/2, text=f"{fmt(bid_v)}×{fmt(ask_v)}", showarrow=False,
                                         font=dict(color=txt_color, size=10, family="Courier New, monospace"), xanchor="center", yanchor="middle"))
        col_vol, col_delta = fp["total"][c].sum(), fp["delta"][c].sum()
        d_color = GREEN if col_delta >= 0 else RED
        annotations.append(dict(x=(x0+x1)/2, y=n_rows+0.9, text=fmt(col_vol), showarrow=False, font=dict(color=TXT, size=10), xanchor="center"))
        annotations.append(dict(x=(x0+x1)/2, y=n_rows+1.7, text=f"{'+' if col_delta>=0 else ''}{fmt(col_delta)}", showarrow=False,
                                 font=dict(color=d_color, size=10, family="Tahoma"), xanchor="center"))
        annotations.append(dict(x=(x0+x1)/2, y=-0.7, text=pd.Timestamp(c).strftime("%H:%M"), showarrow=False,
                                 font=dict(color=NEUTRAL_TXT, size=9), xanchor="center"))
    for ri, p in enumerate(rows):
        y0, y1 = n_rows-ri-1, n_rows-ri
        annotations.append(dict(x=-0.12, y=(y0+y1)/2, text=f"{p:,.0f}", showarrow=False, font=dict(color=TXT, size=9), xanchor="right"))
    add_narrative_overlays(shapes, annotations, fp, narrative, n_rows)
    status_suffix = ""
    if narrative and narrative["reversal_risk"]: status_suffix = "  ·  ⚠ ریسک بازگشت"
    elif narrative and narrative["acceptance"]: status_suffix = "  ·  ✅ پذیرش تأیید شد"
    fig = go.Figure()
    fig.update_layout(shapes=shapes, annotations=annotations,
                      xaxis=dict(range=[-1.6, n_cols*col_w+1.6], visible=False),
                      yaxis=dict(range=[-1.6, n_rows+2.3], visible=False),
                      plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER, margin=dict(l=10, r=10, t=40, b=10),
                      title=dict(text=f"فوت‌پرینت زنده · {pair}{status_suffix}", font=dict(color=GOLD, size=15, family="Tahoma"), x=0.02),
                      height=560)
    return fig

def render_decision_map(narrative):
    if narrative and narrative["acceptance"]: badge_color, badge_text = UP, "ACCEPTANCE · پذیرش قیمت"
    elif narrative and narrative["reversal_risk"]: badge_color, badge_text = DN, "REJECTION · رد قیمت / جذب"
    elif narrative: badge_color, badge_text = GOLD, "IN PROGRESS · در حال شکل‌گیری"
    else: badge_color, badge_text = MUT, "در انتظار داده"

    def step_box(title, subtitle, active, color):
        return html.Div([html.Div(title, style={"fontWeight": "800", "fontSize": "12px", "color": TXT}),
                          html.Div(subtitle, style={"fontSize": "10.5px", "color": MUT})],
                         style={"border": f"2px solid {color if active else LINE}", "borderRadius": "10px",
                                "padding": "7px 10px", "marginBottom": "7px", "background": CARD,
                                "opacity": 1 if active else 0.45, "flex": "1"})

    if narrative is None:
        loc_active = evid_active = conf_active = invalid_active = fail_active = False
    else:
        loc_active = True; evid_active = narrative["vol_near_peak"] > 0
        conf_active = narrative["reversal_risk"] or narrative["acceptance"]
        invalid_active = narrative["acceptance"]; fail_active = narrative["reversal_risk"]

    if narrative and narrative["reversal_risk"]:
        note_text, note_color = "⚠ دلتای مثبت بالا بدون پیشرفت قیمت — زمینه ریسک بازگشت.", DN
    elif narrative and narrative["acceptance"]:
        note_text, note_color = "✅ خریداران بزرگ بالای سقف را نگه داشتند؛ ساخت ارزش تأیید شد.", UP
    else:
        note_text, note_color = "⏳ در انتظار تکمیل شواهد...", MUT

    return html.Div([
        html.Div([html.Span("نقشه تصمیم اردر فلو", style={"fontWeight": "800", "color": GOLD, "fontSize": "13px"}),
                  html.Span(badge_text, style={"background": badge_color, "color": "#fff", "fontWeight": "700",
                                               "padding": "3px 10px", "borderRadius": "14px", "fontSize": "10.5px"})],
                 style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "marginBottom": "8px"}),
        step_box("موقعیت: سقف / مقاومت", "Location: High", loc_active, TXT),
        step_box("شاهد: خرید تهاجمی", "Evidence: Aggressive Buying", evid_active, UP),
        step_box("تأیید: جذب غیرفعال", "Confirmation: Passive Absorption", conf_active, GOLD),
        html.Div([step_box("ابطال: شکست به بالا", "Invalidation", invalid_active, UP),
                  step_box("مسیر شکست: رد و فروش", "Failure", fail_active, DN)], style={"display": "flex", "gap": "8px"}),
        html.Div(note_text, style={"marginTop": "6px", "fontSize": "11px", "fontWeight": "700", "color": note_color}),
    ])

# ==============================================================================
# 4) لایه پل: تأیید اردر فلو برای سیگنال روند
# ==============================================================================
def order_flow_confirmation(fp, cd, narrative, trend_state, of_symbol, trend_symbol):
    if of_symbol != trend_symbol:
        return dict(score=0, label="⚠ نماد اردر فلو با نماد روند یکی نیست — اتصال را بروز کنید", agree=None, ready=False)
    if fp is None or cd is None or len(cd["cols"]) == 0:
        return dict(score=0, label="در حال دریافت دیتای زنده اردر فلو...", agree=None, ready=False)

    recent_n = min(8, len(cd["cols"]))
    recent_delta = float(cd["col_delta"].iloc[-recent_n:].sum())
    delta_sign = 1 if recent_delta > 0 else (-1 if recent_delta < 0 else 0)

    hist = get_book_history_df(seconds=120)
    obi_val = float(hist["obi"].iloc[-5:].mean()) if not hist.empty else 0.0
    obi_sign = 1 if obi_val > 0.05 else (-1 if obi_val < -0.05 else 0)

    narrative_sign = 0
    if narrative:
        if narrative.get("acceptance"): narrative_sign = 1
        elif narrative.get("reversal_risk"): narrative_sign = -1

    score = int(delta_sign*40 + obi_sign*30 + narrative_sign*30)  # -100..100
    agree = None
    if trend_state != 0 and score != 0:
        agree = (np.sign(score) == trend_state)

    if score > 30: label = "🟢 اردر فلو زنده: تأیید خرید"
    elif score < -30: label = "🔴 اردر فلو زنده: تأیید فروش"
    else: label = "⚖️ اردر فلو زنده: خنثی/نامشخص"

    return dict(score=score, label=label, agree=agree, ready=True, recent_delta=recent_delta, obi=obi_val)

def final_signal_badge(trend_sig, trend_state, of):
    if not of["ready"]:
        return of["label"], MUT
    if trend_state == 0:
        return f"{trend_sig} (بدون سیگنال روندی فعال)", MUT
    if of["agree"] is True:
        return f"{trend_sig} — ✅ تأییدشده با اردر فلو زنده", UP if trend_state == 1 else DN
    if of["agree"] is False:
        return f"{trend_sig} — ⚠ خلاف‌جهت اردر فلو زنده، احتیاط", "#f39c12"
    return f"{trend_sig} — ⏳ در انتظار تأیید اردر فلو", MUT

# ==============================================================================
# 5) چارت‌سازهای روند (3D) — بدون تغییر نسبت به v3
# ==============================================================================
def _axis(title_text=""):
    return dict(title=dict(text=title_text, font=dict(color=MUT, size=10, family="Tahoma")),
                gridcolor=LINE, tickfont=dict(color=MUT, size=9, family="Tahoma"), color=MUT)

def build_ma_3d(df, symbol, interval, mode):
    prices = df["close"].values.astype(float); vols = df["volume"].values.astype(float)
    n = len(prices); step = max(1, n//220); x = np.arange(0, n, step); m = len(x)
    p_ds, v_ds = prices[x], vols[x]
    t_lbl = df["ts"].iloc[x].dt.strftime("%m-%d %H:%M").values
    Zf = fast_all_ma(prices); Z = Zf[:, x]; y = np.arange(1, 201); cur = prices[-1]
    if mode == "discount":
        SZ = (cur-Z)/Z*100; cs, ct = "RdYlGn", "فاصله %"; lim = float(np.nanpercentile(np.abs(SZ), 98))+1e-6; cmin, cmax = -lim, lim
    elif mode == "momentum":
        lk = max(2, m//12); pv = np.empty_like(Z); pv[:, lk:] = Z[:, :-lk]; pv[:, :lk] = Z[:, :lk]
        SZ = (Z-pv)/np.where(pv==0, 1e-9, pv)*100; cs, ct = "RdYlGn", "شیب %"; lim = float(np.nanpercentile(np.abs(SZ), 98))+1e-6; cmin, cmax = -lim, lim
    else: SZ, cs, ct, cmin, cmax = Z, "Plasma", "قیمت", None, None
    fig = go.Figure()
    fig.add_trace(go.Surface(x=x, y=y, z=Z, surfacecolor=SZ, colorscale=cs, cmin=cmin, cmax=cmax, opacity=0.95,
                             colorbar=dict(title=ct, thickness=12, len=0.75, tickfont=dict(color=MUT, family="Tahoma")), name="MA 1-200"))
    fig.add_trace(go.Scatter3d(x=x, y=np.ones(m), z=p_ds, mode="lines", line=dict(color="white", width=9), name="قیمت"))
    fig.add_trace(go.Scatter3d(x=x, y=np.ones(m), z=p_ds, mode="lines", line=dict(color=GOLD, width=3), showlegend=False))
    for p, c2 in [(20, "#f1c40f"), (50, "#e67e22"), (100, "#00d2ff"), (200, "#ff2d55")]:
        fig.add_trace(go.Scatter3d(x=x, y=np.full(m, p), z=Z[p-1], mode="lines", line=dict(color=c2, width=5), name=f"MA {p}"))
    zmin, zmax = float(Z.min()), float(Z.max()); span = (zmax-zmin) or 1; vmax = v_ds.max() or 1
    vx, vy, vz = [], [], []
    for i in range(m):
        h = 0.18*span*(v_ds[i]/vmax)
        vx += [x[i], x[i], None]; vy += [205, 205, None]; vz += [zmin-.07*span, zmin-.07*span+h, None]
    fig.add_trace(go.Scatter3d(x=vx, y=vy, z=vz, mode="lines", hoverinfo="skip", line=dict(color="rgba(143,163,192,.4)", width=2), name="حجم"))
    d = Zf[19]-Zf[49]; cross = np.where(np.diff(np.sign(d)) != 0)[0]+1
    if len(cross):
        gx, gz, gc, gt = [], [], [], []
        for ci in cross[-6:]:
            g = d[ci] > 0
            gx.append(int(ci//step)); gz.append(float(Zf[49, ci])); gc.append(UP if g else DN); gt.append("کراس طلایی" if g else "کراس مرگ")
        fig.add_trace(go.Scatter3d(x=gx, y=[50]*len(gx), z=gz, mode="markers+text", text=gt, textposition="top center",
                                   textfont=dict(size=9, color=TXT, family="Tahoma"), marker=dict(size=6, color=gc, symbol="diamond"), name="کراس 20/50"))
    ma_last = Zf[:, -1]
    for vals, c2, tag in [(ma_last[ma_last < cur], UP, "حمایت هم‌گرایی"), (ma_last[ma_last >= cur], DN, "مقاومت هم‌گرایی")]:
        if len(vals) == 0: continue
        hst, ed = np.histogram(vals, bins=15); i = int(np.argmax(hst)); lvl = float((ed[i]+ed[i+1])/2)
        fig.add_trace(go.Scatter3d(x=[x[0], x[-1]], y=[100, 100], z=[lvl, lvl], mode="lines+text", text=["", f"{tag} {lvl:,.0f}"],
                                   textfont=dict(size=10, color=c2, family="Tahoma"), line=dict(color=c2, width=3, dash="dash"), name=tag))
    st = max(1, m//6)
    fig.update_layout(scene=dict(xaxis=dict(**_axis("زمان"), tickvals=x[::st].tolist(), ticktext=t_lbl[::st].tolist()),
                                 yaxis=dict(**_axis("دوره MA")), zaxis=dict(**_axis("قیمت")),
                                 camera=dict(eye=dict(x=1.7, y=1.7, z=0.9)), bgcolor="rgba(0,0,0,0)"),
                      legend=dict(orientation="h", y=0.01, font=dict(size=10, color=MUT, family="Tahoma")),
                      margin=dict(l=25, r=25, b=25, t=45), paper_bgcolor=BG,
                      title=dict(text=f"سطح 3D سیستم MA 1-200 | {symbol} {interval}", font=dict(size=15, color=GOLD, family="Tahoma")),
                      uirevision=f"ma-{symbol}-{interval}")
    return fig

def build_rsi_3d(df, symbol, interval):
    prices = df["close"].values.astype(float)
    n = len(prices); step = max(1, n//220); x = np.arange(0, n, step); m = len(x)
    t_lbl = df["ts"].iloc[x].dt.strftime("%m-%d %H:%M").values
    Rf = fast_all_rsi(prices); R = Rf[:, x]; y = np.arange(1, 201)
    fig = go.Figure()
    fig.add_trace(go.Surface(x=x, y=y, z=R, surfacecolor=R, colorscale="RdYlGn", cmin=0, cmax=100, opacity=0.95,
                             colorbar=dict(title="RSI", thickness=12, len=0.75, tickfont=dict(color=MUT, family="Tahoma")), name="RSI 1-200"))
    for lvl, c2, tag in [(70, DN, "اشباع خرید 70"), (50, MUT, "خط میانی 50"), (30, UP, "اشباع فروش 30")]:
        fig.add_trace(go.Scatter3d(x=[x[0], x[-1]], y=[100, 100], z=[lvl, lvl], mode="lines+text", text=["", tag],
                                   textfont=dict(size=10, color=c2, family="Tahoma"), line=dict(color=c2, width=3, dash="dash"), name=tag))
    for p, c2, w in [(14, GOLD, 7), (50, "#f1c40f", 4), (100, "#00d2ff", 4), (200, "#ff2d55", 4)]:
        fig.add_trace(go.Scatter3d(x=x, y=np.full(m, p), z=R[p-1], mode="lines", line=dict(color=c2, width=w), name=f"RSI {p}"))
    st = max(1, m//6)
    fig.update_layout(scene=dict(xaxis=dict(**_axis("زمان"), tickvals=x[::st].tolist(), ticktext=t_lbl[::st].tolist()),
                                 yaxis=dict(**_axis("دوره RSI")), zaxis=dict(**_axis("RSI"), range=[0, 100]),
                                 camera=dict(eye=dict(x=1.7, y=1.7, z=0.9)), bgcolor="rgba(0,0,0,0)"),
                      legend=dict(orientation="h", y=0.01, font=dict(size=10, color=MUT, family="Tahoma")),
                      margin=dict(l=25, r=25, b=25, t=45), paper_bgcolor=BG,
                      title=dict(text=f"سطح 3D سیستم RSI 1-200 | {symbol} {interval}", font=dict(size=15, color=GOLD, family="Tahoma")),
                      uirevision=f"rsi-{symbol}-{interval}")
    return fig

def build_momentum_3d(df, symbol, interval):
    prices = df["close"].values.astype(float)
    n = len(prices); step = max(1, n//220); x = np.arange(0, n, step); m = len(x)
    t_lbl = df["ts"].iloc[x].dt.strftime("%m-%d %H:%M").values
    Zf = fast_all_ma(prices); Sf = slope_surface(Zf); S = Sf[:, x]; y = np.arange(1, 201)
    lim = float(np.nanpercentile(np.abs(S), 97))+1e-9
    fig = go.Figure()
    fig.add_trace(go.Surface(x=x, y=y, z=S, surfacecolor=S, colorscale="RdYlGn", cmin=-lim, cmax=lim, opacity=0.95,
                             colorbar=dict(title="شتاب MA", thickness=12, len=0.75, tickfont=dict(color=MUT, family="Tahoma")), name="شتاب زنجیره MA"))
    for p, c2 in [(20, "#f1c40f"), (50, "#e67e22"), (100, "#00d2ff"), (200, "#ff2d55")]:
        fig.add_trace(go.Scatter3d(x=x, y=np.full(m, p), z=S[p-1], mode="lines", line=dict(color=c2, width=5), name=f"شتاب MA{p}"))
    st = max(1, m//6)
    fig.update_layout(scene=dict(xaxis=dict(**_axis("زمان"), tickvals=x[::st].tolist(), ticktext=t_lbl[::st].tolist()),
                                 yaxis=dict(**_axis("دوره MA")), zaxis=dict(**_axis("شتاب")),
                                 camera=dict(eye=dict(x=1.7, y=1.7, z=0.9)), bgcolor="rgba(0,0,0,0)"),
                      legend=dict(orientation="h", y=0.01, font=dict(size=10, color=MUT, family="Tahoma")),
                      margin=dict(l=25, r=25, b=25, t=45), paper_bgcolor=BG,
                      title=dict(text=f"سطح 3D شتاب زنجیره‌ای (MCI) | {symbol} {interval}", font=dict(size=15, color=GOLD, family="Tahoma")),
                      uirevision=f"mom-{symbol}-{interval}")
    return fig

def build_integrity(a, symbol, interval):
    s = a["series"]
    n = len(s["cti"]); step = max(1, n//300); x = np.arange(n)[::step]
    tl = s["ts"].iloc[::step].dt.strftime("%m-%d %H:%M").values
    fig = go.Figure()
    fig.add_hrect(y0=70, y1=100, fillcolor="rgba(22,160,133,.12)", line_width=0)
    fig.add_hrect(y0=0, y1=30, fillcolor="rgba(231,76,60,.12)", line_width=0)
    for lvl, c2 in [(70, UP), (30, DN), (50, MUT)]: fig.add_hline(y=lvl, line=dict(color=c2, width=1, dash="dot"))
    fig.add_trace(go.Scatter(x=x, y=s["cti"][::step], name="CTI ترکیبی (3 بعد)", line=dict(color=GOLD, width=2.6)))
    fig.add_trace(go.Scatter(x=x, y=s["tii"][::step], name="TII تراز MA", line=dict(color="#00d2ff", width=1.1)))
    fig.add_trace(go.Scatter(x=x, y=s["rii"][::step], name="RII تراز RSI", line=dict(color="#e05fd0", width=1.1)))
    fig.add_trace(go.Scatter(x=x, y=s["mci"][::step], name="MCI شتاب زنجیره", line=dict(color=PURP, width=1.1)))
    if s["changes"]:
        ci = [c[0] for c in s["changes"]]; cv = [s["cti"][i] for i in ci]
        cc = [UP if c[1]==1 else (DN if c[1]==-1 else MUT) for c in s["changes"]]
        fig.add_trace(go.Scatter(x=ci, y=cv, mode="markers", name="تغییر قفل سیگنال", marker=dict(size=8, color=cc, symbol="diamond")))
    fig.update_layout(plot_bgcolor=CARD, paper_bgcolor=BG, height=280, margin=dict(l=40, r=20, t=35, b=30),
                      xaxis=dict(gridcolor=LINE, tickfont=dict(color=MUT, size=9, family="Tahoma"),
                                 tickvals=x[::max(1, len(x)//6)].tolist(), ticktext=tl[::max(1, len(tl)//6)].tolist()),
                      yaxis=dict(gridcolor=LINE, range=[0, 100], tickfont=dict(color=MUT, size=9, family="Tahoma")),
                      legend=dict(orientation="h", y=1.12, font=dict(size=10, color=MUT, family="Tahoma")),
                      title=dict(text=f"🔗 یکپارچگی زنجیره 3بعدی | {symbol} {interval}", font=dict(size=13, color=GOLD, family="Tahoma")))
    return fig

def build_equity_chart(a):
    eq = a["eq_curve"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=eq, mode="lines", line=dict(color=GOLD, width=2), name="سرمایه فرضی (OOS)"))
    fig.update_layout(plot_bgcolor=CARD, paper_bgcolor=BG, height=220, margin=dict(l=40, r=20, t=35, b=30),
                      xaxis=dict(gridcolor=LINE, tickfont=dict(color=MUT, size=9)), yaxis=dict(gridcolor=LINE, tickfont=dict(color=MUT, size=9)),
                      title=dict(text=f"منحنی سرمایه OOS | حداکثر افت: {a['max_dd']:.1f}%", font=dict(size=12, color=GOLD, family="Tahoma")))
    return fig

# ==============================================================================
# 6) اجزای UI روند (KPI/جدول/اعتبارسنجی/ریسک) — از v3 + کارت تأیید اردر فلو
# ==============================================================================
def telegram_banner():
    return html.A(html.Div([
        html.Span("🌙", style={"fontSize": 30}),
        html.Div([html.Div([html.Span("کانال نهادی ترید ", style={"fontWeight": "bold"}),
                            html.Span(TELEGRAM_ID, dir="ltr", style={"fontWeight": "bold", "color": "#ffd75e"})]),
                  html.Div("روند 3بعدی زنجیره‌ای + تأیید زنده اردر فلو — عضویت رایگان", style={"fontSize": 11})],
                 style={"flex": "1", "textAlign": "right"}),
        html.Div("عضویت ✈", style={"background": GOLD, "color": "#0b1220", "borderRadius": 8, "padding": "8px 18px", "fontWeight": "bold"}),
    ], style={"display": "flex", "alignItems": "center", "gap": 14, "padding": "12px 18px", "direction": "rtl",
              "background": "linear-gradient(90deg,#121c30 0%,#1a2b4a 60%,#229ED9 130%)", "color": TXT, "borderRadius": 12,
              "margin": "12px auto", "maxWidth": 1220, "border": f"1px solid {LINE}"}),
        href=TELEGRAM_URL, target="_blank", style={"textDecoration": "none", "display": "block", "padding": "0 16px"})

def kpi_cards(a, htf_align, of):
    sc = UP if a["state"] == 1 else (DN if a["state"] == -1 else MUT)
    align_txt, align_c = {"up": ("هم‌راستا 🟢", UP), "down": ("خلاف‌جهت 🔴", DN), "none": ("—", MUT)}[htf_align]
    final_txt, final_c = final_signal_badge(a["sig"], a["state"], of)
    cards = [("قیمت", f"{a['cur']:,.2f}", GOLD),
             ("سیگنال نهایی (روند+فلو)", final_txt, final_c),
             ("CTI (3بعدی)", f"{a['cti']:.0f}", sc),
             ("TII / RII / MCI", f"{a['tii']:.0f} / {a['rii']:.0f} / {a['mci']:.0f}", MUT),
             ("اطمینان روند", f"{a['conf']}%", sc),
             ("امتیاز اردر فلو", f"{of['score']:+d}" if of["ready"] else "—", UP if of.get("score", 0) > 0 else (DN if of.get("score", 0) < 0 else MUT)),
             ("همراستایی HTF", align_txt, align_c),
             ("واگرایی", {"bull": "مثبت 🟢", "bear": "منفی 🔴", None: "—"}[a["div"]], UP if a["div"]=="bull" else (DN if a["div"]=="bear" else MUT))]
    return html.Div([html.Div([html.Div(t, style={"fontSize": 10, "color": MUT}),
                                html.Div(v, style={"fontSize": 14, "fontWeight": "bold", "color": c})],
                               style={"flex": "1", "minWidth": 150, "background": CARD, "borderRadius": 10, "padding": "10px",
                                      "textAlign": "center", "border": f"1px solid {LINE}", "borderTop": f"3px solid {c}"})
                      for t, v, c in cards],
                     style={"display": "flex", "gap": 8, "justifyContent": "center", "flexWrap": "wrap", "padding": "0 16px"})

def verdict_banner(overall, bulls, bears, lock_ts, of):
    reg, rs = regime_of(overall)
    col = UP if rs > 0 else (DN if rs < 0 else "#f39c12")
    emoji = "🟢" if rs > 0 else ("🔴" if rs < 0 else "⚖️")
    conf = int(abs(overall-50)*2)
    of_line = of["label"]
    return html.Div([
        html.Div([html.Span(emoji, style={"fontSize": 32, "marginLeft": 12}),
                  html.Div([html.Div(f"روند کلی بازار: {reg}", style={"fontSize": 19, "fontWeight": "bold", "color": col}),
                            html.Div([html.Span(f"شاخص لحظه‌ای {conf}% | اجماع: {bulls} صعودی / {bears} نزولی | "),
                                      html.Span("🔒 قفل روی کندل بسته: ", style={"color": MUT}),
                                      html.Span(lock_ts.strftime("%m-%d %H:%M"), dir="ltr", style={"color": GOLD})],
                                     style={"fontSize": 11, "color": MUT})], style={"textAlign": "right"})],
                 style={"display": "flex", "alignItems": "center", "justifyContent": "center", "direction": "rtl"}),
        html.Div([html.Div(style={"width": f"{overall:.0f}%", "background": f"linear-gradient(90deg,{DN},#f39c12,{UP})", "height": 8, "borderRadius": 4})],
                 style={"background": LINE, "height": 8, "borderRadius": 4, "marginTop": 10}),
        html.Div(of_line, style={"fontSize": 12, "color": GOLD, "marginTop": 8, "textAlign": "center", "fontWeight": "bold"}),
    ], style={"background": CARD, "borderRadius": 12, "padding": "14px 20px", "maxWidth": 1220, "margin": "12px auto",
             "border": f"1px solid {LINE}", "borderRight": f"6px solid {col}"})

ROW_BG = {2: "#0f2b1f", 1: "#0d241c", 0: "#241f10", -1: "#2b1515", -2: "#331010"}

def build_table(rows, htf_tf):
    htf_row = rows.get(htf_tf)
    th = lambda t, w: html.Th(t, style={"width": w, "padding": "8px 3px", "fontSize": 11, "background": GOLD, "color": "#0b1220"})
    trs = []
    for tf in TIMEFRAMES:
        a = rows.get(tf)
        if a is None: continue
        td = lambda ch, b=False, c=TXT: html.Td(ch, style={"padding": "5px 3px", "fontSize": 11, "textAlign": "center", "color": c,
                                                    "borderBottom": f"1px solid {LINE}", "fontWeight": "bold" if b else "normal"})
        sc = UP if a["rs"] > 0 else (DN if a["rs"] < 0 else "#f39c12")
        align = "—"
        if htf_row is not None and tf != htf_tf:
            if (a["rs"] > 0 and htf_row["rs"] > 0) or (a["rs"] < 0 and htf_row["rs"] < 0): align = "🟢"
            elif a["rs"] == 0 or htf_row["rs"] == 0: align = "⚖️"
            else: align = "🔴"
        trs.append(html.Tr([td(TF_NAMES[tf], True), td(f"{a['cur']:,.1f}"), td(f"{a['cti']:.0f}"),
                            td(f"{a['tii']:.0f}/{a['rii']:.0f}/{a['mci']:.0f}"),
                            td(html.Span(a["reg"], style={"color": sc})), td({"bull": "🟢", "bear": "🔴", None: "—"}[a["div"]]), td(align),
                            td(html.Div([html.Span(f"🔒 {a['sig']} ", style={"color": UP if a['state']==1 else (DN if a['state']==-1 else MUT), "fontWeight": "bold"}),
                                         html.Span(f"{a['conf']}%", style={"fontSize": 9, "color": MUT})]))],
                           style={"background": ROW_BG[a["rs"]]}))
    return html.Table([html.Thead(html.Tr([th("TF", "7%"), th("قیمت", "13%"), th("CTI", "8%"), th("TII/RII/MCI", "17%"),
                                           th("رژیم", "13%"), th("واگ.", "7%"), th("همراستا HTF", "10%"), th("سیگنال قفل‌شده", "25%")])), html.Tbody(trs)],
                      style={"width": "100%", "tableLayout": "fixed", "borderCollapse": "collapse", "background": CARD,
                             "borderRadius": 10, "overflow": "hidden", "border": f"1px solid {LINE}"})

def build_validation_panel(a, horizon):
    bt, rb, z = a["test_bt"], a["rb"], a["z_edge"]
    w1, w2, w3 = a["weights"]
    def stat_card(t, v, c=TXT):
        return html.Div([html.Div(t, style={"fontSize": 10, "color": MUT}), html.Div(v, style={"fontSize": 15, "fontWeight": "bold", "color": c})],
                        style={"flex": "1", "minWidth": 140, "background": CARD, "borderRadius": 10, "padding": "10px", "textAlign": "center", "border": f"1px solid {LINE}"})
    if not a["oos_used"] or bt["n"] == 0:
        body = html.Div("داده کافی برای اعتبارسنجی OOS این تایم‌فریم نیست.", style={"color": MUT, "textAlign": "center", "padding": 20})
    else:
        zc = UP if (z is not None and z > 1) else ("#f39c12" if (z is not None and z >= 0) else DN)
        ztxt = f"{z:+.2f}σ" if z is not None else "—"
        pfc = UP if bt["profit_factor"] >= 1 else DN
        body = html.Div([html.Div([
            stat_card("وزن‌های بهینه (TII/RII/MCI)", f"{w1:.1f} / {w2:.1f} / {w3:.1f}"),
            stat_card("تعداد سیگنال OOS", str(bt["n"])),
            stat_card("نرخ برد OOS", f"{bt['win_rate']:.0f}%", UP if bt["win_rate"] >= 50 else DN),
            stat_card(f"میانگین بازده (افق {horizon})", f"{bt['avg_ret']:+.2f}%", UP if bt["avg_ret"] >= 0 else DN),
            stat_card("ضریب سود", f"{bt['profit_factor']:.2f}", pfc),
            stat_card("z-score", ztxt, zc),
            stat_card("حداکثر افت (OOS)", f"{a['max_dd']:.1f}%", DN if a["max_dd"] < -10 else "#f39c12")],
            style={"display": "flex", "gap": 8, "flexWrap": "wrap", "justifyContent": "center"})])
    return html.Div([html.Div("🧪 اعتبارسنجی Walk-Forward", style={"color": GOLD, "fontWeight": "bold", "textAlign": "center", "marginBottom": 10}), body])

def build_risk_panel(a, capital, risk_pct):
    r = risk_suggestion(a["atr"], a["cur"], risk_pct=risk_pct, capital=capital)
    def stat_card(t, v, c=TXT):
        return html.Div([html.Div(t, style={"fontSize": 10, "color": MUT}), html.Div(v, style={"fontSize": 15, "fontWeight": "bold", "color": c})],
                        style={"flex": "1", "minWidth": 150, "background": CARD, "borderRadius": 10, "padding": "10px", "textAlign": "center", "border": f"1px solid {LINE}"})
    return html.Div([html.Div("🛡 مدیریت ریسک بر اساس ATR", style={"color": GOLD, "fontWeight": "bold", "textAlign": "center", "marginBottom": 10}),
                     html.Div([stat_card("ATR فعلی", f"{a['atr']:,.2f}"), stat_card("فاصله حد ضرر (2×ATR)", f"{r['stop_dist']:,.2f} ({r['stop_pct']:.2f}%)"),
                               stat_card("مقدار ریسک‌شده", f"${r['risk_amount']:,.2f}"), stat_card("حجم پوزیشن پیشنهادی", f"{r['position_size']:,.4f}"),
                               stat_card("ارزش پوزیشن", f"${r['position_value']:,.2f}")],
                              style={"display": "flex", "gap": 8, "flexWrap": "wrap", "justifyContent": "center"})])

# ==============================================================================
# 7) اپ Dash — ادغام کامل
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY], title="BITMOON Terminal v4")
app.index_string = '''<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
  html, body { direction: rtl !important; text-align: right !important; background: #0b1220 !important; }
  body, button, input, select, label, div, th, td, .navbar-brand,
  .dash-dropdown, .Select-control, .Select-value-label, .Select-option, .Select-placeholder {
     font-family: Tahoma, "Segoe UI", Arial, sans-serif !important; }
  .js-plotly-plot, .svg-container, .gl-container, .plot-container { direction: ltr !important; }
  .Select-control { background: #121c30 !important; border-color: #23314d !important; }
  .Select-menu-outer { background: #121c30 !important; border-color: #23314d !important; text-align: right; }
  .Select-option, .Select-value-label { color: #e8ecf4 !important; }
  .nav-tabs { border-color: #23314d; }
  .nav-link { color: #8fa3c0 !important; font-family: Tahoma !important; }
  .nav-link.active { color: #f0b90b !important; background: #121c30 !important; border-color: #23314d !important; font-weight: bold; }
  .card { background: #121c30 !important; border-color: #23314d !important; }
</style>
</head>
<body dir="rtl">{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body>
</html>'''

app.layout = html.Div([
    dbc.Navbar(color="dark", dark=True, style={"background": CARD, "borderBottom": f"2px solid {GOLD}"},
               children=dbc.Container(fluid=True, children=[
        dbc.NavbarBrand("🌙 BITMOON TERMINAL v4 — روند 3بعدی + تأیید زنده اردر فلو", style={"fontWeight": "bold", "color": GOLD}),
        dbc.Button("✈ BITMOON618", href=TELEGRAM_URL, target="_blank", color="warning", size="sm", style={"fontWeight": "bold", "color": "#0b1220"})])),
    telegram_banner(),
    dbc.Card(dbc.CardBody([dbc.Row([
        dbc.Col([html.Label("نماد:", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="symbol-input", value="BTCUSDT", style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
        dbc.Col([html.Label("دسته:", style={"fontSize": 12, "color": MUT}),
                 dcc.Dropdown(id="category-dropdown", value="linear", clearable=False,
                              options=[{"label": "Linear", "value": "linear"}, {"label": "Spot", "value": "spot"}])], md=1),
        dbc.Col([html.Label("تایم‌فریم اصلی:", style={"fontSize": 12, "color": MUT}),
                 dcc.Dropdown(id="interval-dropdown", value="15", clearable=False,
                              options=[{"label": TF_NAMES[t], "value": t} for t in ["1", "5", "15", "60", "240", "D"]])], md=2),
        dbc.Col([html.Label("فیلتر HTF:", style={"fontSize": 12, "color": MUT}),
                 dcc.Dropdown(id="htf-dropdown", value="240", clearable=False,
                              options=[{"label": TF_NAMES[t], "value": t} for t in ["60", "240", "360", "720", "D", "W"]])], md=2),
        dbc.Col([html.Label("افق Backtest:", style={"fontSize": 12, "color": MUT}),
                 dcc.Dropdown(id="bt-horizon-dropdown", value=10, clearable=False,
                              options=[{"label": str(v), "value": v} for v in [5, 10, 20, 30]])], md=1),
        dbc.Col([html.Label("سرمایه ($):", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="capital-input", type="number", value=10000, style={"width": "100%", "padding": 6, "borderRadius": 6})], md=1),
        dbc.Col([html.Label("ریسک (%):", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="risk-input", type="number", value=1.0, step=0.1, style={"width": "100%", "padding": 6, "borderRadius": 6})], md=1),
        dbc.Col(dbc.Button("🔄 تحلیل روند", id="refresh-btn", color="warning", className="mt-3",
                           style={"fontWeight": "bold", "color": "#0b1220", "width": "100%"}), md=1),
        dbc.Col(dbc.Button("⚡ اتصال اردرفلو", id="apply-of-btn", color="info", className="mt-3",
                           style={"fontWeight": "bold", "width": "100%"}), md=1),
    ])]), style={"maxWidth": 1220, "margin": "10px auto"}),
    dbc.Row([dbc.Col(html.Div(id="of-conn-status", style={"textAlign": "center", "color": MUT, "fontSize": 11}), width=12)]),

    html.Div(id="verdict-wrap"),
    html.Div(id="kpi-row"),
    dbc.Card(dbc.CardBody(dbc.Tabs(id="tabs", active_tab="tab-ma", children=[
        dbc.Tab(label="📈 سطح 3D مووینگ‌ها", tab_id="tab-ma", children=[
            dbc.RadioItems(id="ma-mode-radio", value="price", inline=True, style={"fontSize": 11, "color": TXT, "margin": "8px"},
                           options=[{"label": "قیمت", "value": "price"}, {"label": "پریمیوم", "value": "discount"}, {"label": "مومنتوم", "value": "momentum"}]),
            dcc.Graph(id="ma-3d-chart", style={"height": "58vh"})]),
        dbc.Tab(label="📉 سطح 3D RSI", tab_id="tab-rsi", children=dcc.Graph(id="rsi-3d-chart", style={"height": "60vh"})),
        dbc.Tab(label="⚡ سطح 3D شتاب (MCI)", tab_id="tab-mom", children=dcc.Graph(id="mom-3d-chart", style={"height": "60vh"})),
        dbc.Tab(label="🩸 فوت‌پرینت زنده", tab_id="tab-fp", children=[
            dbc.Row([
                dbc.Col(dcc.Graph(id="footprint-graph", style={"height": "56vh"}), width=8),
                dbc.Col([html.Div(id="decision-map-panel", style={"marginBottom": 10}),
                         dcc.Graph(id="cumdelta-graph", style={"height": "24vh"})], width=4),
            ])]),
        dbc.Tab(label="🧪 اعتبارسنجی", tab_id="tab-val", children=html.Div(id="validation-wrap", style={"padding": 20})),
        dbc.Tab(label="🛡 مدیریت ریسک", tab_id="tab-risk", children=[html.Div(id="risk-wrap", style={"padding": 20}), dcc.Graph(id="equity-chart")])])),
        style={"maxWidth": 1220, "margin": "12px auto"}),
    html.Div(dcc.Graph(id="integrity-chart"), style={"maxWidth": 1220, "margin": "0 auto"}),
    html.H4("📊 ماتریس نهادی سیگنال — همه تایم‌فریم‌ها", style={"textAlign": "center", "color": GOLD, "margin": "16px 0 8px"}),
    html.Div(id="table-wrap", style={"maxWidth": 1190, "margin": "0 auto", "padding": "0 16px"}),
    telegram_banner(),
    html.Div(id="status-msg", style={"textAlign": "center", "color": UP, "fontWeight": "bold", "padding": "12px 0 22px"}),
    dcc.Interval(id="trend-interval", interval=60_000, n_intervals=0),
    dcc.Interval(id="of-interval", interval=1500, n_intervals=0),
], style={"background": BG, "minHeight": "100vh"})

# ---- Callback ۱: اتصال زنده اردر فلو (سریع، هر 1.5 ثانیه) ----
@app.callback(
    Output("footprint-graph", "figure"), Output("cumdelta-graph", "figure"),
    Output("decision-map-panel", "children"), Output("of-conn-status", "children"),
    Input("of-interval", "n_intervals"), Input("apply-of-btn", "n_clicks"),
    State("symbol-input", "value"), State("category-dropdown", "value"),
)
def update_orderflow(n_int, n_clicks, symbol, category):
    symbol = (symbol or "BTCUSDT").upper()
    category = category or "linear"
    ctx = dash.callback_context
    if ctx.triggered and ctx.triggered[0]["prop_id"].startswith("apply-of-btn"):
        with STATE_LOCK:
            needs_restart = CONN_STATUS["symbol"] != symbol or CONN_STATUS["category"] != category or CURRENT_STREAM is None
        if needs_restart:
            restart_stream(symbol, category)

    df = get_trades_df()
    fp = build_footprint(df, DEFAULT_TICK_SIZE, DEFAULT_INTERVAL_SEC, MAX_COLUMNS)
    cd = build_cumulative_delta(fp) if fp else None
    narrative = detect_order_flow_narrative(fp, cd) if fp else None
    fp_fig = render_footprint_figure(fp, symbol, narrative) if fp else go.Figure(layout=dict(
        plot_bgcolor=CARD, paper_bgcolor=BG,
        annotations=[dict(text="در حال دریافت دیتای زنده اردر فلو...", x=0.5, y=0.5, showarrow=False, font=dict(color=GOLD, size=13))]))
    cd_fig = render_cumulative_delta_figure(cd)
    decision_map = render_decision_map(narrative)
    with STATE_LOCK:
        connected, ws_host, of_symbol = CONN_STATUS["connected"], CONN_STATUS["ws_host"], CONN_STATUS["symbol"]
    status = f"{'🟢 متصل' if connected else '🟡 در حال اتصال...'} | {of_symbol} | {ws_host}"
    return fp_fig, cd_fig, decision_map, status

# ---- Callback ۲: تحلیل روند (کندی، هر 60 ثانیه یا با کلیک) ----
@app.callback(
    Output("ma-3d-chart", "figure"), Output("rsi-3d-chart", "figure"), Output("mom-3d-chart", "figure"),
    Output("integrity-chart", "figure"), Output("kpi-row", "children"), Output("verdict-wrap", "children"),
    Output("table-wrap", "children"), Output("validation-wrap", "children"),
    Output("risk-wrap", "children"), Output("equity-chart", "figure"), Output("status-msg", "children"),
    Input("refresh-btn", "n_clicks"), Input("trend-interval", "n_intervals"), Input("of-interval", "n_intervals"),
    Input("tabs", "active_tab"), Input("ma-mode-radio", "value"), Input("bt-horizon-dropdown", "value"),
    Input("htf-dropdown", "value"), Input("capital-input", "value"), Input("risk-input", "value"),
    State("symbol-input", "value"), State("interval-dropdown", "value"), State("category-dropdown", "value"),
)
def update_trend(n_clicks, n_trend, n_of, active, ma_mode, bt_horizon, htf_tf, capital, risk_pct, symbol, interval_3d, category):
    symbol = (symbol or "BTCUSDT").upper()
    category = category or "linear"
    capital = capital or 10000; risk_pct = risk_pct or 1.0
    ctx = dash.callback_context
    force = bool(ctx.triggered and ctx.triggered[0]["prop_id"].startswith("refresh-btn"))
    data, ms = get_all(symbol, category, force=force)
    if not data:
        empty = go.Figure()
        return (empty, empty, empty, empty, html.Div(), html.Div(), html.Div(), html.Div(), html.Div(), empty, "❌ اتصال روند برقرار نشد.")

    def _pick_df(d, *keys):
        for k in keys:
            v = d.get(k)
            if v is not None and not v.empty: return v
        return next(iter(d.values()))
    df_3d = _pick_df(data, interval_3d, "15")

    rows = {tf: analyze_tf(df, horizon=bt_horizon) for tf, df in data.items()}
    a = rows.get(interval_3d) or rows.get("15") or next(iter(rows.values()))

    htf_row = rows.get(htf_tf); htf_align = "none"
    if htf_row is not None and interval_3d != htf_tf:
        if a["rs"] > 0 and htf_row["rs"] > 0: htf_align = "up"
        elif a["rs"] < 0 and htf_row["rs"] < 0: htf_align = "down"
        elif a["rs"] != 0 and htf_row["rs"] != 0: htf_align = "down"

    tot_w = sum(W_TF.get(t, 1) for t in rows)
    overall = sum(W_TF.get(t, 1)*r["cti"] for t, r in rows.items())/tot_w
    bulls = sum(1 for r in rows.values() if r["rs"] > 0); bears = sum(1 for r in rows.values() if r["rs"] < 0)

    # --- پل تأیید اردر فلو: سیگنال اصلی رو با جریان زنده سفارش می‌سنجیم ---
    df_of = get_trades_df()
    fp_of = build_footprint(df_of, DEFAULT_TICK_SIZE, DEFAULT_INTERVAL_SEC, MAX_COLUMNS)
    cd_of = build_cumulative_delta(fp_of) if fp_of else None
    narrative_of = detect_order_flow_narrative(fp_of, cd_of) if fp_of else None
    with STATE_LOCK: of_symbol = CONN_STATUS["symbol"]
    of = order_flow_confirmation(fp_of, cd_of, narrative_of, a["state"], of_symbol, symbol)

    fig_ma = build_ma_3d(df_3d, symbol, interval_3d, ma_mode) if active == "tab-ma" else dash.no_update
    fig_rsi = build_rsi_3d(df_3d, symbol, interval_3d) if active == "tab-rsi" else dash.no_update
    fig_mom = build_momentum_3d(df_3d, symbol, interval_3d) if active == "tab-mom" else dash.no_update

    return (fig_ma, fig_rsi, fig_mom, build_integrity(a, symbol, interval_3d),
            kpi_cards(a, htf_align, of), verdict_banner(overall, bulls, bears, a["lock_ts"], of),
            build_table(rows, htf_tf), build_validation_panel(a, bt_horizon),
            build_risk_panel(a, capital, risk_pct), build_equity_chart(a),
            f"✅ {len(data)} تایم‌فریم روند در {ms}ms | وزن‌ها: {a['weights'][0]:.1f}/{a['weights'][1]:.1f}/{a['weights'][2]:.1f} | {pd.Timestamp.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    print("در حال اتصال اردر فلو زنده به بایبیت...")
    restart_stream(DEFAULT_SYMBOL, DEFAULT_CATEGORY)
    time.sleep(1.5)
    Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:8050/")).start()
    app.run(debug=True, host="0.0.0.0", port=8050, use_reloader=False)