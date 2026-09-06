# -*- coding: utf-8 -*-
"""
Bybit Footprint Chart - Stable Connection + Order-Flow Poster Style
----------------------------------------------------------------------
pip install dash dash-bootstrap-components plotly pandas numpy requests websocket-client

اجرا:
    python bybit_footprint_dash_stable.py

ویژگی‌های این نسخه:
  ۱) اتصال پایدار: هم REST و هم WebSocket روی چند دامنه/میرور بایبیت (fallback
     خودکار) امتحان می‌شن، دقیقاً به روش الگوی ارسالی شما (session + هدر
     مرورگر + چرخش بین base URL ها). یک Watchdog هم کانکشن‌های "زنده ولی ساکت"
     (silent stall) رو تشخیص و Reconnect می‌کنه.
  ۲) ظاهر الهام‌گرفته از پوستر Order Flow: هر سلول فقط یک عدد رنگی Bid×Ask
     (سبز = غلبه‌ی خرید، قرمز = غلبه‌ی فروش)، نوار جهت کندل کنار هر ستون،
     باکس طلایی دور HVN/POC، حاشیه‌ی نقطه‌چین برای Imbalance قطری، و
     برچسب‌های «فشار خرید / منطقه تعادل / فشار فروش» کنار نمودار.
  ۳) نمودارهای علمی اضافه: دلتای تجمعی (Cumulative Delta)، پروفایل حجم
     (Volume Profile) کنار فوت‌پرینت، و هیستوگرام دلتا هر ستون.
"""

import json
import threading
import time
from collections import deque
from datetime import timezone

import numpy as np
import pandas as pd
import requests
import websocket  # pip install websocket-client
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

# ==============================================================================
# 1) اتصال پایدار: چند دامنه/میرور برای REST و WebSocket + Session مرورگرگونه
# ==============================================================================
REST_CANDIDATES = [
    "https://api.bybit.com",
    "https://api.bytick.com",
    "https://api.bybit.kz",
]
WS_CANDIDATES = [
    "wss://stream.bybit.com",
    "wss://stream.bytick.com",
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.bybit.com/",
})

_ACTIVE_REST_BASE = {"url": None}
STALE_SEC = 25          # اگه این‌قدر ثانیه هیچ پیامی نیاد، یعنی کانکشن ساکت شده
WATCHDOG_INTERVAL = 5


def bybit_get(path, params, timeout=10):
    """درخواست REST با چرخش خودکار بین دامنه‌های بایبیت تا یکی جواب بده."""
    candidates = [_ACTIVE_REST_BASE["url"]] if _ACTIVE_REST_BASE["url"] else []
    candidates += [b for b in REST_CANDIDATES if b != _ACTIVE_REST_BASE["url"]]
    for base in candidates:
        try:
            resp = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if resp.status_code in (403, 451):
                continue
            resp.raise_for_status()
            data = resp.json()
            if data.get("retCode") == 0:
                _ACTIVE_REST_BASE["url"] = base
                return data
        except Exception:
            continue
    return None


# ==============================================================================
# 2) CONFIG کلی
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

# --- پالت الهام‌گرفته از پوستر Order Flow (کرم/کاغذی + سرمه‌ای + سبز/قرمز/طلایی) ---
BG_PAPER = "#f7f1e2"
BG_PLOT = "#fbf7ec"
GRID_LINE = "#d9cfb8"
NAVY = "#1b3a63"
GREEN = "#1a7a4c"
RED = "#c0392b"
GOLD = "#d4a017"
NEUTRAL_TXT = "#6b6355"
BID_COL_TAG = "#1e5aa8"
ASK_COL_TAG = "#c0392b"

# ------------------------------------------------------------------------------
STATE_LOCK = threading.RLock()
TRADES = deque(maxlen=TRADE_BUFFER_MAX)
ORDER_BOOK = {"bids": {}, "asks": {}, "ready": False}
CONN_STATUS = {"connected": False, "symbol": DEFAULT_SYMBOL, "category": DEFAULT_CATEGORY,
               "ws_host": "-", "rest_host": "-"}
LAST_MSG_TS = {"t": 0.0}

# --- سطح L3: رویدادهای خام دفتر سفارش (Add/Update/Cancel) + عکس‌فوری‌های میکروساختار ---
L3_DEPTH_LEVELS = 10          # تعداد سطوح هر سمت که برای متریک‌های L3 ردیابی می‌شن
L3_SAMPLE_INTERVAL = 1.0      # ثانیه بین هر عکس‌فوری میکروساختار
L3_EVENTS_MAX = 20_000
L3_HISTORY_MAX = 1800         # ~۳۰ دقیقه در نرخ نمونه‌برداری ۱ ثانیه
BOOK_EVENTS = deque(maxlen=L3_EVENTS_MAX)     # {ts, side, price, size, event}
BOOK_HISTORY = deque(maxlen=L3_HISTORY_MAX)   # {ts, mid, microprice, spread, obi, bid_depth, ask_depth, bids, asks}
_LAST_L3_SAMPLE = {"t": 0.0}


def _maybe_sample_book_history(now_ts):
    """هر L3_SAMPLE_INTERVAL ثانیه یک عکس‌فوری از میکروساختار دفتر می‌گیرد (باید زیر STATE_LOCK صدا زده شود)."""
    if now_ts - _LAST_L3_SAMPLE["t"] < L3_SAMPLE_INTERVAL:
        return
    _LAST_L3_SAMPLE["t"] = now_ts
    bids_sorted = sorted(ORDER_BOOK["bids"].items(), key=lambda x: -x[0])[:L3_DEPTH_LEVELS]
    asks_sorted = sorted(ORDER_BOOK["asks"].items(), key=lambda x: x[0])[:L3_DEPTH_LEVELS]
    if not bids_sorted or not asks_sorted:
        return
    best_bid_p, best_bid_s = bids_sorted[0]
    best_ask_p, best_ask_s = asks_sorted[0]
    mid = (best_bid_p + best_ask_p) / 2.0
    spread = best_ask_p - best_bid_p
    denom = best_bid_s + best_ask_s
    microprice = ((best_bid_p * best_ask_s) + (best_ask_p * best_bid_s)) / denom if denom > 0 else mid
    bid_depth = sum(s for _, s in bids_sorted)
    ask_depth = sum(s for _, s in asks_sorted)
    obi = (bid_depth - ask_depth) / (bid_depth + ask_depth) if (bid_depth + ask_depth) > 0 else 0.0
    BOOK_HISTORY.append({
        "ts": pd.Timestamp.now(tz=timezone.utc), "mid": mid, "spread": spread,
        "microprice": microprice, "obi": obi, "bid_depth": bid_depth, "ask_depth": ask_depth,
        "bids": bids_sorted, "asks": asks_sorted,
    })


# ==============================================================================
# 3) Bootstrap اولیه از REST (تا وقتی WebSocket وصل بشه، چارت خالی نمونه)
# ==============================================================================
def backfill_trades_rest(symbol, category, limit=1000):
    data = bybit_get("/v5/market/recent-trade", {"category": category, "symbol": symbol, "limit": limit})
    if not data:
        return
    items = (data.get("result") or {}).get("list") or []
    rows = []
    for t in items:
        try:
            rows.append({
                "id": t.get("execId"),
                "ts": pd.to_datetime(int(t["time"]), unit="ms", utc=True),
                "price": float(t["price"]),
                "amount": float(t["size"]),
                "side": "buy" if t.get("side") == "Buy" else "sell",
            })
        except Exception:
            continue
    with STATE_LOCK:
        TRADES.extend(rows)
        CONN_STATUS["rest_host"] = _ACTIVE_REST_BASE["url"] or "-"


def fetch_orderbook_rest(symbol, category, depth=50):
    data = bybit_get("/v5/market/orderbook", {"category": category, "symbol": symbol, "limit": depth})
    if not data:
        return
    result = data.get("result") or {}
    with STATE_LOCK:
        if not ORDER_BOOK["ready"]:
            ORDER_BOOK["bids"] = {float(p): float(s) for p, s in result.get("b", []) if float(s) > 0}
            ORDER_BOOK["asks"] = {float(p): float(s) for p, s in result.get("a", []) if float(s) > 0}


def orderbook_bootstrap_loop(symbol, category, stop_flag):
    """تا وقتی WS دفتر سفارش رو نداده، هر چند ثانیه با REST جایگزین موقت می‌گیره."""
    while not stop_flag.is_set():
        with STATE_LOCK:
            ready = ORDER_BOOK["ready"]
        if ready:
            return
        fetch_orderbook_rest(symbol, category)
        time.sleep(3)


# ==============================================================================
# 4) WebSocket با چرخش بین میزبان‌ها + Watchdog ضد سکوت
# ==============================================================================
class BybitStream:
    def __init__(self, symbol: str, category: str = "linear"):
        self.symbol = symbol.upper()
        self.category = category
        self.ws = None
        self.thread = None
        self.stop_flag = threading.Event()
        self.host_idx = 0
        self.fail_count = 0

    def _url(self) -> str:
        host = WS_CANDIDATES[self.host_idx % len(WS_CANDIDATES)]
        return f"{host}/v5/public/{self.category}"

    def start(self):
        self.stop_flag.clear()
        self.thread = threading.Thread(target=self._run_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_flag.set()
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass

    def force_reconnect(self):
        """برای استفاده‌ی Watchdog: کانکشن فعلی رو می‌بنده تا حلقه‌ی run_forever دوباره وصل بشه."""
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass

    def _run_forever(self):
        while not self.stop_flag.is_set():
            try:
                with STATE_LOCK:
                    CONN_STATUS["ws_host"] = self._url()
                self.ws = websocket.WebSocketApp(
                    self._url(),
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self.ws.run_forever(ping_interval=20, ping_payload=json.dumps({"op": "ping"}))
            except Exception:
                pass
            with STATE_LOCK:
                CONN_STATUS["connected"] = False
            if self.stop_flag.is_set():
                break
            self.fail_count += 1
            if self.fail_count >= 2:
                self.host_idx += 1          # بعد از ۲ شکست پیاپی، میزبان بعدی رو امتحان کن
                self.fail_count = 0
            time.sleep(min(3 * (self.fail_count + 1), 12))

    def _on_open(self, ws):
        sub = {"op": "subscribe", "args": [f"publicTrade.{self.symbol}", f"orderbook.50.{self.symbol}"]}
        ws.send(json.dumps(sub))
        with STATE_LOCK:
            ORDER_BOOK["ready"] = False
            ORDER_BOOK["bids"].clear()
            ORDER_BOOK["asks"].clear()
            CONN_STATUS["connected"] = True
            CONN_STATUS["symbol"] = self.symbol
            CONN_STATUS["category"] = self.category
        LAST_MSG_TS["t"] = time.time()
        self.fail_count = 0

    def _on_error(self, ws, error):
        with STATE_LOCK:
            CONN_STATUS["connected"] = False

    def _on_close(self, ws, code, msg):
        with STATE_LOCK:
            CONN_STATUS["connected"] = False

    def _on_message(self, ws, raw):
        LAST_MSG_TS["t"] = time.time()
        try:
            msg = json.loads(raw)
        except Exception:
            return
        topic = msg.get("topic", "")
        if topic.startswith("publicTrade."):
            self._handle_trades(msg.get("data") or [])
        elif topic.startswith("orderbook."):
            self._handle_orderbook(msg)

    def _handle_trades(self, data):
        if not data:
            return
        rows = []
        for t in data:
            try:
                rows.append({
                    "id": t.get("i"),
                    "ts": pd.to_datetime(int(t["T"]), unit="ms", utc=True),
                    "price": float(t["p"]),
                    "amount": float(t["v"]),
                    "side": "buy" if t.get("S") == "Buy" else "sell",
                })
            except Exception:
                continue
        with STATE_LOCK:
            TRADES.extend(rows)

    def _handle_orderbook(self, msg):
        mtype = msg.get("type")
        data = msg.get("data") or {}
        bids, asks = data.get("b", []), data.get("a", [])
        now = time.time()
        with STATE_LOCK:
            if mtype == "snapshot":
                ORDER_BOOK["bids"] = {float(p): float(s) for p, s in bids if float(s) > 0}
                ORDER_BOOK["asks"] = {float(p): float(s) for p, s in asks if float(s) > 0}
                ORDER_BOOK["ready"] = True
            else:
                # هر تغییر سطح دفتر به‌عنوان یک رویداد L3 طبقه‌بندی می‌شه: Add / Update / Cancel
                for p, s in bids:
                    p, s = float(p), float(s)
                    existed = p in ORDER_BOOK["bids"]
                    if s == 0:
                        if existed:
                            BOOK_EVENTS.append({"ts": now, "side": "bid", "price": p, "size": 0.0, "event": "cancel"})
                        ORDER_BOOK["bids"].pop(p, None)
                    else:
                        BOOK_EVENTS.append({"ts": now, "side": "bid", "price": p, "size": s,
                                             "event": "update" if existed else "add"})
                        ORDER_BOOK["bids"][p] = s
                for p, s in asks:
                    p, s = float(p), float(s)
                    existed = p in ORDER_BOOK["asks"]
                    if s == 0:
                        if existed:
                            BOOK_EVENTS.append({"ts": now, "side": "ask", "price": p, "size": 0.0, "event": "cancel"})
                        ORDER_BOOK["asks"].pop(p, None)
                    else:
                        BOOK_EVENTS.append({"ts": now, "side": "ask", "price": p, "size": s,
                                             "event": "update" if existed else "add"})
                        ORDER_BOOK["asks"][p] = s
            _maybe_sample_book_history(now)


CURRENT_STREAM: "BybitStream | None" = None
_OB_BOOTSTRAP_STOP = threading.Event()


def restart_stream(symbol: str, category: str):
    global CURRENT_STREAM, _OB_BOOTSTRAP_STOP
    if CURRENT_STREAM is not None:
        CURRENT_STREAM.stop()
    _OB_BOOTSTRAP_STOP.set()
    with STATE_LOCK:
        TRADES.clear()
        ORDER_BOOK["ready"] = False
        ORDER_BOOK["bids"].clear()
        ORDER_BOOK["asks"].clear()
        BOOK_EVENTS.clear()
        BOOK_HISTORY.clear()
        _LAST_L3_SAMPLE["t"] = 0.0

    backfill_trades_rest(symbol, category)     # پر کردن اولیه تا وصل شدن WS

    _OB_BOOTSTRAP_STOP = threading.Event()
    threading.Thread(target=orderbook_bootstrap_loop, args=(symbol, category, _OB_BOOTSTRAP_STOP),
                      daemon=True).start()

    CURRENT_STREAM = BybitStream(symbol, category)
    CURRENT_STREAM.start()


def watchdog_loop():
    """اگه کانکشن claim می‌کنه وصله ولی مدتیه پیامی نیومده -> Reconnect اجباری."""
    while True:
        time.sleep(WATCHDOG_INTERVAL)
        with STATE_LOCK:
            connected = CONN_STATUS["connected"]
        if connected and (time.time() - LAST_MSG_TS["t"] > STALE_SEC) and CURRENT_STREAM is not None:
            CURRENT_STREAM.force_reconnect()


threading.Thread(target=watchdog_loop, daemon=True).start()


# ==============================================================================
# 5) دیتا اکسسورها
# ==============================================================================
def get_trades_df() -> pd.DataFrame:
    with STATE_LOCK:
        if not TRADES:
            return pd.DataFrame(columns=TRADE_COLS)
        df = pd.DataFrame(list(TRADES))
    if df.empty:
        return df
    cutoff = pd.Timestamp.now(tz=timezone.utc) - pd.Timedelta(hours=HISTORY_TRIM_HOURS)
    df = df[df["ts"] >= cutoff]
    return df.drop_duplicates(subset="id")


def get_orderbook_snapshot(depth=ORDER_BOOK_DEPTH):
    with STATE_LOCK:
        bids = sorted(ORDER_BOOK["bids"].items(), key=lambda x: -x[0])[:depth]
        asks = sorted(ORDER_BOOK["asks"].items(), key=lambda x: x[0])[:depth]
    return (pd.DataFrame(asks, columns=["price", "amount"]),
            pd.DataFrame(bids, columns=["price", "amount"]))


def get_book_history_df(seconds=600):
    """سری زمانی میکروساختار L3 (mid/microprice/spread/OBI/عمق) در بازه‌ی اخیر."""
    with STATE_LOCK:
        if not BOOK_HISTORY:
            return pd.DataFrame()
        hist = list(BOOK_HISTORY)
    df = pd.DataFrame(hist)
    if df.empty:
        return df
    cutoff = pd.Timestamp.now(tz=timezone.utc) - pd.Timedelta(seconds=seconds)
    return df[df["ts"] >= cutoff].reset_index(drop=True)


def get_book_events_df(seconds=120):
    """رویدادهای خام دفتر سفارش (Add/Update/Cancel) در بازه‌ی اخیر — سطح L3."""
    with STATE_LOCK:
        if not BOOK_EVENTS:
            return pd.DataFrame()
        events = list(BOOK_EVENTS)
    df = pd.DataFrame(events)
    if df.empty:
        return df
    cutoff = time.time() - seconds
    return df[df["ts"] >= cutoff].reset_index(drop=True)


# ==============================================================================
# 6) تجمیع فوت‌پرینت (نردبان قیمتی پیوسته + Imbalance قطری علمی)
# ==============================================================================
def build_footprint(df: pd.DataFrame, tick_size: float, interval_sec: int, max_cols: int):
    if df.empty:
        return None
    work = df.copy()
    work["price_bucket"] = (np.floor(work["price"] / tick_size) * tick_size).round(8)
    work["time_bucket"] = work["ts"].dt.floor(f"{interval_sec}s")

    cols_all = sorted(work["time_bucket"].unique())
    cols = cols_all[-max_cols:]
    work = work[work["time_bucket"].isin(cols)]
    if work.empty:
        return None

    min_p, max_p = work["price_bucket"].min(), work["price_bucket"].max()
    n_steps = max(int(round((max_p - min_p) / tick_size)), 0)
    rows = [round(max_p - i * tick_size, 8) for i in range(n_steps + 1)]

    ask_pivot = (work[work["side"] == "buy"]
                 .pivot_table(index="price_bucket", columns="time_bucket", values="amount",
                              aggfunc="sum", fill_value=0.0))
    bid_pivot = (work[work["side"] == "sell"]
                 .pivot_table(index="price_bucket", columns="time_bucket", values="amount",
                              aggfunc="sum", fill_value=0.0))

    ask_grid = ask_pivot.reindex(index=rows, columns=cols, fill_value=0.0)
    bid_grid = bid_pivot.reindex(index=rows, columns=cols, fill_value=0.0)

    # جهت هر ستون (برای نوار سبز/قرمز کنار هر کندل، مثل عکس)
    col_open = work.sort_values("ts").groupby("time_bucket")["price"].first().reindex(cols)
    col_close = work.sort_values("ts").groupby("time_bucket")["price"].last().reindex(cols)

    return {
        "rows": rows, "cols": cols, "tick_size": tick_size,
        "ask": ask_grid, "bid": bid_grid,
        "total": ask_grid + bid_grid, "delta": ask_grid - bid_grid,
        "col_open": col_open, "col_close": col_close,
    }


def compute_diagonal_imbalances(fp, ratio_threshold=IMBALANCE_RATIO):
    ask_grid, bid_grid, tick = fp["ask"], fp["bid"], fp["tick_size"]
    imb = {}
    for c in fp["cols"]:
        for p in fp["rows"]:
            a, b = ask_grid.loc[p, c], bid_grid.loc[p, c]
            p_below, p_above = round(p - tick, 8), round(p + tick, 8)
            b_below = bid_grid.loc[p_below, c] if p_below in bid_grid.index else 0.0
            a_above = ask_grid.loc[p_above, c] if p_above in ask_grid.index else 0.0
            buy_imb = a > 0 and b_below > 0 and (a / b_below) >= ratio_threshold
            sell_imb = b > 0 and a_above > 0 and (b / a_above) >= ratio_threshold
            imb[(p, c)] = "buy" if (buy_imb and not sell_imb) else ("sell" if sell_imb else None)
    return imb


def detect_stacked(imb, rows, cols, min_stack=STACK_MIN):
    stacked = set()
    for c in cols:
        streak_dir, streak_start, streak_len = None, 0, 0
        for ri, p in enumerate(rows):
            d = imb.get((p, c))
            if d is not None and d == streak_dir:
                streak_len += 1
            else:
                if streak_dir is not None and streak_len >= min_stack:
                    stacked.update((rows[k], c) for k in range(streak_start, streak_start + streak_len))
                streak_dir, streak_start = d, ri
                streak_len = 1 if d is not None else 0
        if streak_dir is not None and streak_len >= min_stack:
            stacked.update((rows[k], c) for k in range(streak_start, streak_start + streak_len))
    return stacked


def fmt(v):
    if v >= 1000:
        return f"{v/1000:.1f}k"
    if v >= 1:
        return f"{v:,.1f}".rstrip("0").rstrip(".")
    return f"{v:.3f}".rstrip("0").rstrip(".") if v else "0"


# ==============================================================================
# 6b) نمودارهای علمی اضافه: دلتای تجمعی، پروفایل حجم، هیستوگرام دلتا
#     (فقط محاسبه/رندر جدید؛ منطق فوت‌پرینت/آردربوک اصلی دست‌نخورده می‌ماند)
# ==============================================================================
def build_cumulative_delta(fp):
    """دلتای هر ستون + دلتای تجمعی (Cumulative Delta) روی کل بازه‌ی نمایش داده‌شده."""
    if fp is None:
        return None
    cols = fp["cols"]
    col_delta = fp["delta"].sum(axis=0).reindex(cols).fillna(0.0)
    col_vol = fp["total"].sum(axis=0).reindex(cols).fillna(0.0)
    cum_delta = col_delta.cumsum()
    return {"cols": cols, "col_delta": col_delta, "col_vol": col_vol, "cum_delta": cum_delta}


def build_volume_profile(df: pd.DataFrame, tick_size: float, price_range=None):
    """پروفایل حجم (Volume Profile) روی کل معاملات بافر‌شده: حجم خرید/فروش به ازای هر پله‌ی قیمت."""
    if df.empty:
        return None
    work = df.copy()
    work["price_bucket"] = (np.floor(work["price"] / tick_size) * tick_size).round(8)
    if price_range is not None:
        lo, hi = price_range
        work = work[(work["price_bucket"] >= lo) & (work["price_bucket"] <= hi)]
    if work.empty:
        return None
    grp = work.groupby(["price_bucket", "side"])["amount"].sum().unstack(fill_value=0.0)
    for c in ("buy", "sell"):
        if c not in grp.columns:
            grp[c] = 0.0
    grp["total"] = grp["buy"] + grp["sell"]
    grp = grp.sort_index(ascending=False)
    if grp.empty:
        return None
    poc_price = grp["total"].idxmax()
    return {"rows": grp.index.tolist(), "buy": grp["buy"], "sell": grp["sell"],
            "total": grp["total"], "poc": poc_price}


def render_cumulative_delta_figure(cd):
    """نمودار دلتای تجمعی: خط سرمه‌ای روی زمینه‌ی میله‌ای دلتای هر کندل (سبک علمی/تحلیلی)."""
    fig = go.Figure()
    if cd is None or len(cd["cols"]) == 0:
        fig.update_layout(plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER,
                           annotations=[dict(text="داده‌ای برای دلتای تجمعی نیست", x=0.5, y=0.5,
                                              showarrow=False, font=dict(color=NAVY, size=12))])
        return fig
    x_labels = [pd.Timestamp(c).strftime("%H:%M") for c in cd["cols"]]
    bar_colors = [GREEN if v >= 0 else RED for v in cd["col_delta"]]

    fig.add_trace(go.Bar(
        x=x_labels, y=cd["col_delta"], name="دلتای هر کندل",
        marker=dict(color=bar_colors, line=dict(color=NAVY, width=0.4)),
        opacity=0.55, yaxis="y1",
    ))
    fig.add_trace(go.Scatter(
        x=x_labels, y=cd["cum_delta"], name="دلتای تجمعی", mode="lines+markers",
        line=dict(color=NAVY, width=2.6),
        marker=dict(size=5, color=GOLD, line=dict(color=NAVY, width=1)),
        yaxis="y2",
    ))
    fig.add_hline(y=0, line=dict(color=GRID_LINE, width=1), row=1, col=1)

    fig.update_layout(
        plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER,
        margin=dict(l=45, r=45, t=40, b=35),
        title=dict(text="Cumulative Delta · دلتای تجمعی", font=dict(color=NAVY, size=14, family="Arial Black"), x=0.02),
        xaxis=dict(showgrid=False, tickfont=dict(color=NEUTRAL_TXT, size=9)),
        yaxis=dict(title=dict(text="دلتای کندل", font=dict(color=NEUTRAL_TXT, size=10)),
                    gridcolor=GRID_LINE, zeroline=False, tickfont=dict(color=NEUTRAL_TXT, size=9)),
        yaxis2=dict(title=dict(text="تجمعی", font=dict(color=NAVY, size=10)),
                     overlaying="y", side="right", showgrid=False, tickfont=dict(color=NAVY, size=9)),
        legend=dict(orientation="h", y=1.18, x=0, font=dict(size=9, color=NEUTRAL_TXT)),
        height=260,
        bargap=0.15,
    )
    return fig


def render_volume_profile_figure(vp, pair):
    """پروفایل حجم عمودی مثل هیستوگرام خاکستری/سبز-قرمز کنار فوت‌پرینت در پوسترها."""
    fig = go.Figure()
    if vp is None or len(vp["rows"]) == 0:
        fig.update_layout(plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER,
                           annotations=[dict(text="داده‌ای برای پروفایل حجم نیست", x=0.5, y=0.5,
                                              showarrow=False, font=dict(color=NAVY, size=12))])
        return fig
    prices = [f"{p:,.0f}" for p in vp["rows"]]

    fig.add_trace(go.Bar(
        y=prices, x=vp["buy"], name="حجم خرید (Buy)", orientation="h",
        marker=dict(color=GREEN, opacity=0.75), hovertemplate="%{y}: %{x:.2f}<extra>Buy</extra>",
    ))
    fig.add_trace(go.Bar(
        y=prices, x=-vp["sell"], name="حجم فروش (Sell)", orientation="h",
        marker=dict(color=RED, opacity=0.75), hovertemplate="%{y}: %{customdata:.2f}<extra>Sell</extra>",
        customdata=vp["sell"],
    ))

    poc_label = f"{vp['poc']:,.0f}"
    if poc_label in prices:
        poc_idx = prices.index(poc_label)
        fig.add_shape(type="line", x0=-max(vp["total"]) * 1.05, x1=max(vp["total"]) * 1.05,
                      y0=poc_idx, y1=poc_idx, line=dict(color=GOLD, width=2, dash="dot"),
                      xref="x", yref="y")
        fig.add_annotation(x=max(vp["total"]) * 1.05, y=poc_idx, text="POC", showarrow=False,
                            font=dict(color=GOLD, size=10, family="Arial Black"), xanchor="left")

    fig.update_layout(
        barmode="overlay",
        plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER,
        margin=dict(l=45, r=45, t=40, b=25),
        title=dict(text=f"Volume Profile · {pair}", font=dict(color=NAVY, size=14, family="Arial Black"), x=0.02),
        xaxis=dict(title=dict(text="حجم", font=dict(color=NEUTRAL_TXT, size=10)),
                    gridcolor=GRID_LINE, zeroline=True, zerolinecolor=NAVY, tickfont=dict(color=NEUTRAL_TXT, size=9)),
        yaxis=dict(tickfont=dict(color=NAVY, size=8), autorange="reversed"),
        legend=dict(orientation="h", y=1.18, x=0, font=dict(size=9, color=NEUTRAL_TXT)),
        height=680,
        bargap=0.08,
    )
    return fig


def render_delta_bars_figure(cd):
    """هیستوگرام مستقل دلتای هر کندل (سبز/قرمز) با میانگین متحرک ساده برای خوانایی روند دلتا."""
    fig = go.Figure()
    if cd is None or len(cd["cols"]) == 0:
        fig.update_layout(plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER,
                           annotations=[dict(text="داده‌ای برای هیستوگرام دلتا نیست", x=0.5, y=0.5,
                                              showarrow=False, font=dict(color=NAVY, size=12))])
        return fig
    x_labels = [pd.Timestamp(c).strftime("%H:%M") for c in cd["cols"]]
    deltas = cd["col_delta"]
    bar_colors = [GREEN if v >= 0 else RED for v in deltas]
    ma = pd.Series(deltas.values).rolling(window=min(5, max(2, len(deltas) // 3)), min_periods=1).mean()

    fig.add_trace(go.Bar(
        x=x_labels, y=deltas, name="دلتای کندل",
        marker=dict(color=bar_colors, line=dict(color=NAVY, width=0.4)),
    ))
    fig.add_trace(go.Scatter(
        x=x_labels, y=ma, name="میانگین متحرک دلتا", mode="lines",
        line=dict(color=NAVY, width=2, dash="dash"),
    ))
    fig.add_hline(y=0, line=dict(color=GRID_LINE, width=1))

    fig.update_layout(
        plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER,
        margin=dict(l=45, r=15, t=40, b=35),
        title=dict(text="Delta Histogram · هیستوگرام دلتا", font=dict(color=NAVY, size=14, family="Arial Black"), x=0.02),
        xaxis=dict(showgrid=False, tickfont=dict(color=NEUTRAL_TXT, size=9)),
        yaxis=dict(gridcolor=GRID_LINE, zeroline=False, tickfont=dict(color=NEUTRAL_TXT, size=9)),
        legend=dict(orientation="h", y=1.18, x=0, font=dict(size=9, color=NEUTRAL_TXT)),
        height=260,
        bargap=0.15,
    )
    return fig


# ==============================================================================
# 6c) موتور روایت اردر فلو (Order-Flow Narrative Engine)
#     شناسایی خودکار: نقطه جذب، شکست ناموفق/رد قیمت، جذب غیرفعال، پذیرش/
#     منطقه ارزش پایدار و هشدار ریسک بازگشت — دقیقاً منطق پوسترهای مرجع
#     (Absorption / Failed Breakout / Passive Absorption / Acceptance).
# ==============================================================================
def price_to_y(price, rows, n_rows):
    """تبدیل قیمت به مختصات y روی محور فوت‌پرینت (درون‌یابی خطی، مستقل از هم‌ترازی تیک)."""
    max_p, min_p = max(rows), min(rows)
    if max_p == min_p:
        return n_rows / 2.0
    frac = (max_p - price) / (max_p - min_p)
    return n_rows - frac * n_rows


def detect_order_flow_narrative(fp, cd, lookahead=3, high_frac=0.998):
    """
    روایت خودکار شبیه پوسترها:
      Location (سقف) -> Evidence (خرید تهاجمی) -> Confirmation (جذب غیرفعال/دلتای معکوس)
      -> Invalidation (شکست به بالا / پذیرش) یا Failure Path (رد قیمت و فروش).
    """
    cols = fp["cols"]
    if len(cols) < 4 or cd is None:
        return None

    col_high, col_low = {}, {}
    for c in cols:
        traded_rows = [p for p in fp["rows"] if fp["total"].loc[p, c] > 0]
        if traded_rows:
            col_high[c] = max(traded_rows)
            col_low[c] = min(traded_rows)
    if not col_high:
        return None

    peak_col = max(col_high, key=lambda c: col_high[c])
    peak_price = col_high[peak_col]
    peak_idx = cols.index(peak_col)

    near_peak_cols = [c for c in cols[peak_idx: peak_idx + lookahead] if c in col_high]
    delta_near_peak = float(sum(cd["col_delta"].get(c, 0.0) for c in near_peak_cols))
    vol_near_peak = float(sum(cd["col_vol"].get(c, 0.0) for c in near_peak_cols))

    after_cols = cols[peak_idx + 1:]
    made_higher_high = any(col_high.get(c, 0) > peak_price for c in after_cols)
    tail_cols = after_cols[-min(4, len(after_cols)):] if after_cols else []
    holding_above = (len(tail_cols) > 0 and
                      all(fp["col_close"].get(c, 0) >= peak_price * high_frac for c in tail_cols))

    reversal_risk = (delta_near_peak > 0) and (not made_higher_high) and (not holding_above) and len(after_cols) >= 2
    acceptance = made_higher_high and holding_above

    return {
        "peak_col": peak_col, "peak_idx": peak_idx, "peak_price": peak_price,
        "near_peak_cols": near_peak_cols, "delta_near_peak": delta_near_peak,
        "vol_near_peak": vol_near_peak, "made_higher_high": made_higher_high,
        "holding_above": holding_above, "reversal_risk": reversal_risk,
        "acceptance": acceptance, "after_cols": after_cols, "tail_cols": tail_cols,
    }


def add_narrative_overlays(shapes, annotations, fp, narrative, n_rows):
    """رسم عناصر روایت روی خود فوت‌پرینت: باکس جذب، فلش رد قیمت، منطقه ارزش پایدار."""
    if narrative is None:
        return
    cols = fp["cols"]
    col_w = 1.0
    rows = fp["rows"]
    near_peak_cols = narrative["near_peak_cols"]
    peak_price = narrative["peak_price"]
    peak_y = price_to_y(peak_price, rows, n_rows)

    if near_peak_cols:
        first_idx = cols.index(near_peak_cols[0])
        last_idx = cols.index(near_peak_cols[-1])
        x0, x1 = first_idx * col_w, last_idx * col_w + col_w
        shapes.append(dict(type="rect", x0=x0, x1=x1, y0=0, y1=n_rows,
                            line=dict(color=GOLD, width=2.2, dash="dot"),
                            fillcolor="rgba(212,160,23,0.08)", layer="above"))
        annotations.append(dict(x=(x0 + x1) / 2, y=n_rows + 2.6, text="نقطه جذب (Absorption)",
                                 showarrow=True, ax=0, ay=-28,
                                 font=dict(color=GOLD, size=11, family="Arial Black"),
                                 arrowcolor=GOLD, xanchor="center"))

    if narrative["reversal_risk"]:
        tail_cols = narrative["tail_cols"]
        if tail_cols:
            tail_idx = cols.index(tail_cols[-1])
            tail_x = tail_idx * col_w + col_w / 2
            tail_price = min(fp["col_close"].get(c, peak_price) for c in tail_cols)
            tail_y = price_to_y(tail_price, rows, n_rows)
            peak_x = narrative["peak_idx"] * col_w + col_w / 2
            annotations.append(dict(
                x=tail_x, y=tail_y, ax=peak_x, ay=peak_y, axref="x", ayref="y",
                text="", showarrow=True, arrowhead=3, arrowsize=1.2, arrowwidth=2.4,
                arrowcolor=RED,
            ))
            annotations.append(dict(x=(peak_x + tail_x) / 2, y=(peak_y + tail_y) / 2 - 1.2,
                                     text="رد قیمت / شکست ناموفق", showarrow=False,
                                     font=dict(color=RED, size=11, family="Arial Black")))
            annotations.append(dict(x=tail_x, y=tail_y - 1.6, text="جذب غیرفعال فروشندگان",
                                     showarrow=False, font=dict(color=RED, size=10)))

    if narrative["acceptance"] and narrative["tail_cols"]:
        tail_cols = narrative["tail_cols"]
        first_idx = cols.index(tail_cols[0])
        last_idx = cols.index(tail_cols[-1])
        x0, x1 = first_idx * col_w, last_idx * col_w + col_w
        shapes.append(dict(type="rect", x0=x0, x1=x1, y0=0, y1=n_rows,
                            line=dict(color=GREEN, width=2.2, dash="solid"),
                            fillcolor="rgba(26,122,76,0.07)", layer="above"))
        annotations.append(dict(x=(x0 + x1) / 2, y=n_rows + 2.6, text="منطقه ارزش پایدار (Value Zone)",
                                 showarrow=False, font=dict(color=GREEN, size=11, family="Arial Black"),
                                 xanchor="center"))


def build_narrative_bubbles(fp, narrative, n_rows):
    """حباب‌های حجمی رنگی نزدیک سقف/دنباله، شبیه دایره‌های سبز/صورتی پوستر."""
    if narrative is None:
        return None
    cols_of_interest = [c for c in list(narrative["near_peak_cols"]) + list(narrative["after_cols"][:4])
                         if c in fp["cols"]]
    if not cols_of_interest:
        return None
    rows = fp["rows"]
    xs, ys, sizes, colors, texts = [], [], [], [], []
    for c in cols_of_interest:
        ci = fp["cols"].index(c)
        for p in rows:
            tot = fp["total"].loc[p, c]
            if tot <= 0:
                continue
            delta = fp["delta"].loc[p, c]
            xs.append(ci * 1.0 + 0.5)
            ys.append(price_to_y(p, rows, n_rows))
            sizes.append(tot)
            colors.append(GREEN if delta >= 0 else RED)
            texts.append(f"{p:,.0f} · {fmt(tot)}")
    if not sizes:
        return None
    max_size = max(sizes)
    scaled = [8 + 26 * (s / max_size) for s in sizes]
    return dict(x=xs, y=ys, size=scaled, color=colors, text=texts)


def render_decision_map(narrative):
    """پنل «نقشه تصمیم» شبیه پوستر ۴ (Location -> Evidence -> Confirmation -> Invalidation/Failure)."""
    if narrative and narrative["acceptance"]:
        badge_color, badge_text = GREEN, "ACCEPTANCE · پذیرش قیمت"
    elif narrative and narrative["reversal_risk"]:
        badge_color, badge_text = RED, "REJECTION · رد قیمت / جذب"
    elif narrative:
        badge_color, badge_text = GOLD, "IN PROGRESS · در حال شکل‌گیری"
    else:
        badge_color, badge_text = NEUTRAL_TXT, "در انتظار داده"

    def step_box(title, subtitle, active, color):
        return html.Div([
            html.Div(title, style={"fontWeight": "800", "fontSize": "12px", "color": NAVY}),
            html.Div(subtitle, style={"fontSize": "10.5px", "color": NEUTRAL_TXT}),
        ], style={
            "border": f"2px solid {color if active else GRID_LINE}",
            "borderRadius": "10px", "padding": "7px 10px", "marginBottom": "7px",
            "background": "#fffdf7" if active else "#f2ede1",
            "opacity": 1 if active else 0.55, "flex": "1",
        })

    if narrative is None:
        loc_active = evid_active = conf_active = invalid_active = fail_active = False
    else:
        loc_active = True
        evid_active = narrative["vol_near_peak"] > 0
        conf_active = narrative["reversal_risk"] or narrative["acceptance"]
        invalid_active = narrative["acceptance"]
        fail_active = narrative["reversal_risk"]

    if narrative and narrative["reversal_risk"]:
        note_text, note_color = "⚠ دلتای مثبت بالا بدون پیشرفت قیمت — زمینه‌ی ریسک بازگشت.", RED
    elif narrative and narrative["acceptance"]:
        note_text, note_color = "✅ خریداران بزرگ بالای سقف را نگه داشتند؛ ساخت ارزش تأیید شد.", GREEN
    else:
        note_text, note_color = "⏳ در انتظار تکمیل شواهد برای تعیین وضعیت...", NEUTRAL_TXT

    return html.Div([
        html.Div([
            html.Span("نقشه تصمیم", style={"fontWeight": "800", "color": NAVY, "fontSize": "13px"}),
            html.Span(badge_text, style={
                "background": badge_color, "color": "#fff", "fontWeight": "700",
                "padding": "3px 10px", "borderRadius": "14px", "fontSize": "10.5px",
            }),
        ], style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "marginBottom": "8px"}),
        step_box("موقعیت: سقف / مقاومت", "Location: High (Resistance)", loc_active, NAVY),
        step_box("شاهد: خرید تهاجمی (حجم/دلتا)", "Evidence: Aggressive Buying", evid_active, BID_COL_TAG),
        step_box("تأیید: جذب غیرفعال (دلتای معکوس)", "Confirmation: Passive Absorption", conf_active, GOLD),
        html.Div([
            step_box("ابطال: شکست به بالا", "Invalidation: Breaks Higher", invalid_active, GREEN),
            step_box("مسیر شکست: رد و فروش", "Failure: Rejection & Sell-off", fail_active, RED),
        ], style={"display": "flex", "gap": "8px"}),
        html.Div(note_text, style={"marginTop": "6px", "fontSize": "11px", "fontWeight": "700", "color": note_color}),
    ])


# ==============================================================================
# 7) نمودار فوت‌پرینت - سبک پوستر Order Flow
# ==============================================================================
def render_footprint_figure(fp, pair, narrative=None):
    rows, cols = fp["rows"], fp["cols"]
    n_rows, n_cols = len(rows), len(cols)

    poc_per_col = {c: fp["total"][c].idxmax() for c in cols if fp["total"][c].max() > 0}
    imb = compute_diagonal_imbalances(fp)
    stacked = detect_stacked(imb, rows, cols)

    shapes, annotations = [], []
    col_w = 1.0
    dir_bar_w = 0.06

    for ci, c in enumerate(cols):
        x0, x1 = ci * col_w, ci * col_w + col_w
        o, cl = fp["col_open"].get(c, np.nan), fp["col_close"].get(c, np.nan)
        bar_color = GREEN if (pd.notna(o) and pd.notna(cl) and cl >= o) else RED
        # نوار جهت کندل کنار ستون (الهام از عکس)
        shapes.append(dict(type="rect", x0=x0, x1=x0 + dir_bar_w, y0=0, y1=n_rows,
                            fillcolor=bar_color, line=dict(width=0), layer="below"))

        for ri, p in enumerate(rows):
            y0, y1 = n_rows - ri - 1, n_rows - ri
            bid_v, ask_v, tot_v, delta_v = (fp["bid"].loc[p, c], fp["ask"].loc[p, c],
                                             fp["total"].loc[p, c], fp["delta"].loc[p, c])

            cell_bg = BG_PLOT
            border_color, border_w, border_dash = GRID_LINE, 0.6, "solid"

            direction = imb.get((p, c))
            if direction == "buy":
                border_color, border_w, border_dash = GREEN, 1.6, "dot"
            elif direction == "sell":
                border_color, border_w, border_dash = RED, 1.6, "dot"
            if (p, c) in stacked:
                border_w, border_dash = 2.4, "dash"
            if poc_per_col.get(c) == p:
                border_color, border_w, border_dash = GOLD, 2.6, "solid"
                cell_bg = "#fbeec8"

            shapes.append(dict(type="rect", x0=x0 + dir_bar_w, x1=x1, y0=y0, y1=y1,
                                line=dict(color=border_color, width=border_w, dash=border_dash),
                                fillcolor=cell_bg, layer="below"))

            if tot_v > 0:
                txt_color = GREEN if delta_v > 0 else (RED if delta_v < 0 else NEUTRAL_TXT)
                annotations.append(dict(
                    x=(x0 + dir_bar_w + x1) / 2, y=(y0 + y1) / 2,
                    text=f"{fmt(bid_v)}×{fmt(ask_v)}", showarrow=False,
                    font=dict(color=txt_color, size=10, family="Courier New, monospace"),
                    xanchor="center", yanchor="middle"))

        # هدر ستون: حجم و دلتای کل + زمان پایین
        col_vol, col_delta = fp["total"][c].sum(), fp["delta"][c].sum()
        d_color = GREEN if col_delta >= 0 else RED
        annotations.append(dict(x=(x0 + x1) / 2, y=n_rows + 0.9, text=fmt(col_vol),
                                 showarrow=False, font=dict(color=NAVY, size=10), xanchor="center"))
        annotations.append(dict(x=(x0 + x1) / 2, y=n_rows + 1.7,
                                 text=f"{'+' if col_delta >= 0 else ''}{fmt(col_delta)}",
                                 showarrow=False, font=dict(color=d_color, size=10, family="Arial Black"),
                                 xanchor="center"))
        annotations.append(dict(x=(x0 + x1) / 2, y=-0.7, text=pd.Timestamp(c).strftime("%H:%M"),
                                 showarrow=False, font=dict(color=NEUTRAL_TXT, size=9), xanchor="center"))

    # برچسب قیمت سمت چپ
    for ri, p in enumerate(rows):
        y0, y1 = n_rows - ri - 1, n_rows - ri
        annotations.append(dict(x=-0.12, y=(y0 + y1) / 2, text=f"{p:,.0f}", showarrow=False,
                                 font=dict(color=NAVY, size=9), xanchor="right"))

    # خط زمان پایین با فلش (شبیه عکس)
    shapes.append(dict(type="line", x0=-0.2, x1=n_cols * col_w + 0.3, y0=-1.1, y1=-1.1,
                        line=dict(color=NAVY, width=1.5)))
    annotations.append(dict(x=n_cols * col_w + 0.3, y=-1.1, text="▶", showarrow=False,
                             font=dict(color=NAVY, size=13), xanchor="left", yanchor="middle"))

    # برچسب‌های فشار خرید/فروش سمت راست (الهام مستقیم از عکس)
    zone_x = n_cols * col_w + 0.9
    annotations.append(dict(x=zone_x, y=n_rows * 0.83, text="▲ فشار خرید", showarrow=False,
                             font=dict(color=GREEN, size=12, family="Arial Black"), xanchor="left"))
    annotations.append(dict(x=zone_x, y=n_rows * 0.5, text="⋮ منطقه تعادل", showarrow=False,
                             font=dict(color=NEUTRAL_TXT, size=11), xanchor="left"))
    annotations.append(dict(x=zone_x, y=n_rows * 0.17, text="▼ فشار فروش", showarrow=False,
                             font=dict(color=RED, size=12, family="Arial Black"), xanchor="left"))
    shapes.append(dict(type="line", x0=zone_x - 0.25, x1=zone_x - 0.25, y0=0, y1=n_rows,
                        line=dict(color=NAVY, width=1, dash="dot")))

    # --- روایت اردر فلو: نقطه جذب / رد قیمت / منطقه ارزش پایدار ---
    add_narrative_overlays(shapes, annotations, fp, narrative, n_rows)

    status_suffix = ""
    if narrative and narrative["reversal_risk"]:
        status_suffix = "  ·  ⚠ ریسک بازگشت"
    elif narrative and narrative["acceptance"]:
        status_suffix = "  ·  ✅ پذیرش تأیید شد"

    fig = go.Figure()
    fig.update_layout(
        shapes=shapes, annotations=annotations,
        xaxis=dict(range=[-1.6, zone_x + 2.4], visible=False),
        yaxis=dict(range=[-1.6, n_rows + 2.3], visible=False),
        plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER,
        margin=dict(l=10, r=10, t=40, b=10),
        title=dict(text=f"ORDER FLOW  ·  {pair}  ·  Footprint (Live){status_suffix}",
                    font=dict(color=NAVY, size=17, family="Arial Black"), x=0.02),
        height=680,
    )

    bubbles = build_narrative_bubbles(fp, narrative, n_rows)
    if bubbles:
        fig.add_trace(go.Scatter(
            x=bubbles["x"], y=bubbles["y"], mode="markers",
            marker=dict(size=bubbles["size"], color=bubbles["color"], opacity=0.30,
                        line=dict(color=NAVY, width=1)),
            text=bubbles["text"], hoverinfo="text", showlegend=False,
        ))
    return fig


def render_orderbook_figure(asks, bids, pair):
    fig = go.Figure()
    if asks.empty and bids.empty:
        fig.update_layout(plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER)
        return fig
    asks_sorted = asks.sort_values("price", ascending=True).head(ORDER_BOOK_DEPTH)
    bids_sorted = bids.sort_values("price", ascending=False).head(ORDER_BOOK_DEPTH)
    max_size = max(asks_sorted["amount"].max() if not asks_sorted.empty else 0,
                    bids_sorted["amount"].max() if not bids_sorted.empty else 0, 1)
    n_ask, n_bid = len(asks_sorted), len(bids_sorted)
    total_rows = n_ask + n_bid
    shapes, annotations = [], []

    for i, (_, row) in enumerate(asks_sorted.sort_values("price", ascending=False).iterrows()):
        y0, y1 = total_rows - i - 1, total_rows - i
        bar = row["amount"] / max_size
        shapes.append(dict(type="rect", x0=0, x1=1, y0=y0, y1=y1,
                            fillcolor="#f3e3e0", line=dict(color=GRID_LINE, width=0.5)))
        shapes.append(dict(type="rect", x0=0, x1=bar, y0=y0 + 0.1, y1=y1 - 0.1, fillcolor=RED, line=dict(width=0)))
        annotations.append(dict(x=0.02, y=(y0 + y1) / 2, text=fmt(row["amount"]), showarrow=False,
                                 xanchor="left", font=dict(color=RED, size=9)))
        annotations.append(dict(x=0.98, y=(y0 + y1) / 2, text=f"{row['price']:,.1f}", showarrow=False,
                                 xanchor="right", font=dict(color=RED, size=9)))

    for i, (_, row) in enumerate(bids_sorted.iterrows()):
        y0, y1 = n_bid - i - 1, n_bid - i
        bar = row["amount"] / max_size
        shapes.append(dict(type="rect", x0=0, x1=1, y0=y0, y1=y1,
                            fillcolor="#e2f0e6", line=dict(color=GRID_LINE, width=0.5)))
        shapes.append(dict(type="rect", x0=0, x1=bar, y0=y0 + 0.1, y1=y1 - 0.1, fillcolor=GREEN, line=dict(width=0)))
        annotations.append(dict(x=0.02, y=(y0 + y1) / 2, text=fmt(row["amount"]), showarrow=False,
                                 xanchor="left", font=dict(color=GREEN, size=9)))
        annotations.append(dict(x=0.98, y=(y0 + y1) / 2, text=f"{row['price']:,.1f}", showarrow=False,
                                 xanchor="right", font=dict(color=GREEN, size=9)))

    fig.update_layout(
        shapes=shapes, annotations=annotations,
        xaxis=dict(range=[0, 1], visible=False),
        yaxis=dict(range=[-0.5, max(total_rows, n_bid) + 0.5], visible=False),
        plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER,
        margin=dict(l=5, r=5, t=30, b=5),
        title=dict(text="Order Book", font=dict(color=NAVY, size=13, family="Arial Black")),
        height=680,
    )
    return fig


# ==============================================================================
# 7b) نمودارهای میکروساختار سطح L3 (Level-3 Order Book Microstructure)
#     مبتنی بر جریان رویدادهای خام دفتر سفارش (Add/Update/Cancel) که در
#     BybitStream._handle_orderbook ثبت می‌شوند — نه فقط عمق تجمیعی L2.
# ==============================================================================
def _empty_l3_figure(message, height=230):
    fig = go.Figure()
    fig.update_layout(
        plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER,
        annotations=[dict(text=message, x=0.5, y=0.5, showarrow=False, font=dict(color=NAVY, size=12))],
        height=height,
    )
    return fig


def render_obi_figure(hist_df):
    """عدم‌تعادل دفتر سفارش (Order Book Imbalance) در Top-N سطح، مستقیماً از عکس‌فوری‌های L3."""
    if hist_df is None or hist_df.empty:
        return _empty_l3_figure("داده‌ای برای Order Book Imbalance نیست")
    colors = [GREEN if v >= 0 else RED for v in hist_df["obi"]]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=hist_df["ts"], y=hist_df["obi"], marker=dict(color=colors), name="OBI"))
    fig.add_hline(y=0, line=dict(color=GRID_LINE, width=1))
    fig.update_layout(
        plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER,
        margin=dict(l=45, r=15, t=40, b=30),
        title=dict(text=f"Order Book Imbalance · Top {L3_DEPTH_LEVELS} · L3",
                    font=dict(color=NAVY, size=13, family="Arial Black"), x=0.02),
        xaxis=dict(showgrid=False, tickfont=dict(color=NEUTRAL_TXT, size=9)),
        yaxis=dict(range=[-1, 1], gridcolor=GRID_LINE, tickfont=dict(color=NEUTRAL_TXT, size=9)),
        height=230,
    )
    return fig


def render_microprice_figure(hist_df, trades_df):
    """میکروپرایس (میانگین وزنی سمت مقابل بهترین قیمت‌ها) در برابر Mid و معاملات واقعی."""
    if hist_df is None or hist_df.empty:
        return _empty_l3_figure("داده‌ای برای Microprice نیست", height=260)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist_df["ts"], y=hist_df["mid"], mode="lines", name="Mid Price",
                              line=dict(color=NEUTRAL_TXT, width=1.3, dash="dot")))
    fig.add_trace(go.Scatter(x=hist_df["ts"], y=hist_df["microprice"], mode="lines", name="Microprice",
                              line=dict(color=NAVY, width=2.2)))
    if trades_df is not None and not trades_df.empty:
        window_start = hist_df["ts"].min()
        recent = trades_df[trades_df["ts"] >= window_start]
        buys, sells = recent[recent["side"] == "buy"], recent[recent["side"] == "sell"]
        fig.add_trace(go.Scatter(x=buys["ts"], y=buys["price"], mode="markers", name="معامله خرید",
                                  marker=dict(color=GREEN, size=4, opacity=0.5)))
        fig.add_trace(go.Scatter(x=sells["ts"], y=sells["price"], mode="markers", name="معامله فروش",
                                  marker=dict(color=RED, size=4, opacity=0.5)))
    fig.update_layout(
        plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER,
        margin=dict(l=45, r=15, t=40, b=30),
        title=dict(text="Microprice vs Mid vs Trades · L3", font=dict(color=NAVY, size=13, family="Arial Black"), x=0.02),
        xaxis=dict(showgrid=False, tickfont=dict(color=NEUTRAL_TXT, size=9)),
        yaxis=dict(gridcolor=GRID_LINE, tickfont=dict(color=NEUTRAL_TXT, size=9)),
        legend=dict(orientation="h", y=1.22, x=0, font=dict(size=9, color=NEUTRAL_TXT)),
        height=260,
    )
    return fig


def render_depth_heatmap_figure(hist_df, tick_size):
    """نقشه‌ی حرارتی نقدینگی: عمق هر سطح قیمتی در طول زمان (سبز=Bid، قرمز=Ask) — امضای کلاسیک L3."""
    if hist_df is None or hist_df.empty:
        return _empty_l3_figure("داده‌ای برای Depth Heatmap نیست", height=340)

    all_prices = set()
    for _, row in hist_df.iterrows():
        for p, _ in row["bids"]:
            all_prices.add(round(p / tick_size) * tick_size)
        for p, _ in row["asks"]:
            all_prices.add(round(p / tick_size) * tick_size)
    if not all_prices:
        return _empty_l3_figure("داده‌ای برای Depth Heatmap نیست", height=340)

    price_levels = sorted(all_prices)
    price_index = {p: i for i, p in enumerate(price_levels)}
    hist_df = hist_df.reset_index(drop=True)
    z = np.zeros((len(price_levels), len(hist_df)))
    for ci, row in hist_df.iterrows():
        for p, s in row["bids"]:
            z[price_index[round(p / tick_size) * tick_size], ci] = s
        for p, s in row["asks"]:
            z[price_index[round(p / tick_size) * tick_size], ci] = -s

    fig = go.Figure(data=go.Heatmap(
        z=z, x=hist_df["ts"], y=[f"{p:,.0f}" for p in price_levels],
        colorscale=[[0.0, RED], [0.5, BG_PLOT], [1.0, GREEN]], zmid=0,
        colorbar=dict(title=dict(text="عمق", font=dict(size=9, color=NEUTRAL_TXT)),
                       tickfont=dict(size=8, color=NEUTRAL_TXT)),
    ))
    fig.update_layout(
        plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER,
        margin=dict(l=55, r=15, t=40, b=30),
        title=dict(text="Liquidity Depth Heatmap · L3", font=dict(color=NAVY, size=13, family="Arial Black"), x=0.02),
        xaxis=dict(showgrid=False, tickfont=dict(color=NEUTRAL_TXT, size=9)),
        yaxis=dict(tickfont=dict(color=NAVY, size=8)),
        height=340,
    )
    return fig


def render_book_events_figure(events_df):
    """نرخ رویدادهای خام دفتر سفارش (Add/Update/Cancel) در هر ثانیه — برای تشخیص Quote Stuffing/Spoofing."""
    if events_df is None or events_df.empty:
        return _empty_l3_figure("داده‌ای برای Book Events نیست")
    df = events_df.copy()
    df["sec"] = pd.to_datetime(df["ts"], unit="s", utc=True).dt.floor("1s")
    grp = df.groupby(["sec", "event"]).size().unstack(fill_value=0)

    fig = go.Figure()
    for col, color, label in [("add", GREEN, "Add"), ("update", GOLD, "Update"), ("cancel", RED, "Cancel")]:
        if col in grp.columns:
            fig.add_trace(go.Bar(x=grp.index, y=grp[col], name=label, marker=dict(color=color)))
    fig.update_layout(
        barmode="stack",
        plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER,
        margin=dict(l=45, r=15, t=40, b=30),
        title=dict(text="Book Event Rate (Add/Update/Cancel) · L3",
                    font=dict(color=NAVY, size=13, family="Arial Black"), x=0.02),
        xaxis=dict(showgrid=False, tickfont=dict(color=NEUTRAL_TXT, size=9)),
        yaxis=dict(gridcolor=GRID_LINE, tickfont=dict(color=NEUTRAL_TXT, size=9)),
        legend=dict(orientation="h", y=1.22, x=0, font=dict(size=9, color=NEUTRAL_TXT)),
        height=230,
    )
    return fig


# ==============================================================================
# 8) داشبورد Dash - ظاهر پوستری کاغذی
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY,
                 "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;800&display=swap"])
app.title = "Order Flow · Bybit Footprint"

app.index_string = """
<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    {%metas%}<title>{%title%}</title>{%favicon%}{%css%}
    <style>
        body { font-family:'Vazirmatn',sans-serif !important; background:#f7f1e2; color:#1b3a63; }
        .paper-card {
            background:#fffdf7 !important; border:1.5px solid #1b3a63 !important;
            border-radius:14px !important; padding:18px; margin-bottom:18px;
            box-shadow: 4px 4px 0px rgba(27,58,99,0.15);
        }
        .poster-title {
            font-weight:800; font-size:2.4rem; color:#1b3a63; text-align:center;
            letter-spacing:2px;
        }
        .poster-sub { text-align:center; color:#c0392b; font-weight:600; margin-bottom:6px;}
        .legend-item { margin-bottom:4px; }
        .badge-conn { font-weight:700; padding:6px 14px; border-radius:20px; }
    </style>
</head>
<body>{%app_entry%}{%config%}{%scripts%}{%renderer%}</body>
</html>
"""

app.layout = dbc.Container([
    html.Div([
        html.Div("ORDER FLOW", className="poster-title"),
        html.Div("خواندن نبرد واقعی خریداران و فروشندگان — داده زنده بایبیت", className="poster-sub"),
    ], className="mt-4 mb-2"),

    html.Div(id="global-warning-banner", style={"display": "none"}),

    dbc.Row([
        dbc.Col(dcc.Input(id="pair-input", type="text", value=DEFAULT_SYMBOL,
                           style={"width": "100%"}, placeholder="Symbol"), width=2),
        dbc.Col(dcc.Dropdown(id="category-dropdown",
                              options=[{"label": "Linear (Perp)", "value": "linear"},
                                       {"label": "Spot", "value": "spot"}],
                              value=DEFAULT_CATEGORY, clearable=False), width=2),
        dbc.Col(dcc.Input(id="tick-input", type="number", value=DEFAULT_TICK_SIZE, min=0.1, step=0.1,
                           style={"width": "100%"}, placeholder="Tick Size"), width=2),
        dbc.Col(dcc.Dropdown(id="interval-dropdown",
                              options=[{"label": f"{m} دقیقه", "value": m * 60} for m in [1, 5, 15, 30, 60]],
                              value=DEFAULT_INTERVAL_SEC, clearable=False), width=2),
        dbc.Col(html.Button("اتصال / Apply", id="apply-btn", n_clicks=0, className="btn w-100",
                             style={"background": NAVY, "color": "#fff", "fontWeight": "700",
                                    "borderRadius": "20px"}), width=2),
        dbc.Col(html.Div(id="conn-status", className="badge-conn"), width=2),
    ], className="mb-3 g-2 align-items-center"),

    dcc.Interval(id="tick", interval=1500, n_intervals=0),

    dbc.Row([
        dbc.Col(dbc.Card(dcc.Graph(id="footprint-graph", config={"displayModeBar": False}),
                          className="paper-card"), width=6),
        dbc.Col(dbc.Card(dcc.Graph(id="volume-profile-graph", config={"displayModeBar": False}),
                          className="paper-card"), width=3),
        dbc.Col([
            dbc.Card(dcc.Graph(id="orderbook-graph", config={"displayModeBar": False}),
                      className="paper-card"),
            dbc.Card(id="decision-map-panel", className="paper-card"),
            dbc.Card([
                html.H6("چطور اردر فلو را بخوانیم", style={"fontWeight": "800", "color": NAVY}),
                html.Div("✔ فشار خرید تهاجمی (زدن به Ask)", className="legend-item"),
                html.Div("✔ فشار فروش تهاجمی (زدن به Bid)", className="legend-item"),
                html.Div("✔ باکس طلایی = HVN / نقطه کنترل حجم", className="legend-item"),
                html.Div("✔ حاشیه نقطه‌چین = Imbalance قطری", className="legend-item"),
                html.Div("✔ نوار کنار ستون = جهت کلی کندل", className="legend-item"),
                html.Div("✔ باکس نقطه‌چین طلایی = ناحیه جذب سقف (Absorption)", className="legend-item"),
                html.Div("✔ فلش قرمز = رد قیمت / شکست ناموفق (Failed Breakout)", className="legend-item"),
                html.Div("✔ باکس سبز = منطقه ارزش پایدار (Value Zone)", className="legend-item"),
                html.Div("✔ حباب‌های رنگی = حجم تهاجمی خرید/فروش نزدیک سقف", className="legend-item"),
            ], className="paper-card"),
        ], width=3),
    ]),

    dbc.Row([
        dbc.Col(dbc.Card(dcc.Graph(id="cumulative-delta-graph", config={"displayModeBar": False}),
                          className="paper-card"), width=6),
        dbc.Col(dbc.Card(dcc.Graph(id="delta-bars-graph", config={"displayModeBar": False}),
                          className="paper-card"), width=6),
    ]),

    html.Div([
        html.Div("LEVEL 3 · MICROSTRUCTURE", className="poster-title", style={"fontSize": "1.5rem"}),
        html.Div("جریان خام رویدادهای دفتر سفارش (Add / Update / Cancel) — فراتر از عمق تجمیعی L2",
                  className="poster-sub"),
    ], className="mt-2 mb-1"),

    dbc.Row([
        dbc.Col(dbc.Card(dcc.Graph(id="obi-graph", config={"displayModeBar": False}),
                          className="paper-card"), width=6),
        dbc.Col(dbc.Card(dcc.Graph(id="book-events-graph", config={"displayModeBar": False}),
                          className="paper-card"), width=6),
    ]),
    dbc.Row([
        dbc.Col(dbc.Card(dcc.Graph(id="microprice-graph", config={"displayModeBar": False}),
                          className="paper-card"), width=6),
        dbc.Col(dbc.Card(dcc.Graph(id="depth-heatmap-graph", config={"displayModeBar": False}),
                          className="paper-card"), width=6),
    ]),

    dbc.Card([
        html.H6("نکات کلیدی", style={"fontWeight": "800", "color": NAVY}),
        html.Div("★ همیشه سمت تهاجمی‌تر (Imbalance) را دنبال کنید، نه هر عدد تنها را."),
        html.Div("★ به گره‌های پرحجم (HVN) احترام بگذارید؛ قیمت اغلب به آن‌ها واکنش نشان می‌دهد."),
        html.Div("★ Order Flow را همیشه در کنار ساختار بازار و مدیریت ریسک استفاده کنید."),
        html.Div("★ OBI و Microprice سیگنال‌های زودهنگام‌اند؛ آن‌ها را با فوت‌پرینت و حجم تأیید کنید."),
        html.Div("★ نرخ بالای Cancel/Update در Book Event Rate می‌تواند نشانه‌ی Spoofing یا Quote Stuffing باشد."),
    ], className="paper-card"),

], fluid=True)


@app.callback(
    Output("conn-status", "children"), Output("conn-status", "style"),
    Input("apply-btn", "n_clicks"),
    State("pair-input", "value"), State("category-dropdown", "value"),
    prevent_initial_call=False,
)
def apply_connection(_, pair, category):
    symbol = (pair or DEFAULT_SYMBOL).upper().replace("_", "").replace("/", "")
    category = category or DEFAULT_CATEGORY
    with STATE_LOCK:
        needs_restart = (CONN_STATUS["symbol"] != symbol or CONN_STATUS["category"] != category
                          or CURRENT_STREAM is None)
    if needs_restart:
        restart_stream(symbol, category)
    with STATE_LOCK:
        connected, host = CONN_STATUS["connected"], CONN_STATUS["ws_host"]
    bg = GREEN if connected else GOLD
    text = f"● {symbol} | {'متصل' if connected else 'در حال اتصال...'}"
    return text, {"background": bg, "color": "#fff", "fontWeight": "700",
                   "padding": "6px 14px", "borderRadius": "20px", "textAlign": "center"}


@app.callback(
    Output("footprint-graph", "figure"), Output("orderbook-graph", "figure"),
    Output("cumulative-delta-graph", "figure"), Output("volume-profile-graph", "figure"),
    Output("delta-bars-graph", "figure"),
    Output("decision-map-panel", "children"),
    Output("global-warning-banner", "children"), Output("global-warning-banner", "style"),
    Output("obi-graph", "figure"), Output("microprice-graph", "figure"),
    Output("depth-heatmap-graph", "figure"), Output("book-events-graph", "figure"),
    Input("tick", "n_intervals"),
    State("tick-input", "value"), State("interval-dropdown", "value"),
)
def update_charts(_, tick_size, interval_sec):
    tick_size = float(tick_size or DEFAULT_TICK_SIZE)
    interval_sec = int(interval_sec or DEFAULT_INTERVAL_SEC)
    with STATE_LOCK:
        pair = CONN_STATUS["symbol"]

    df = get_trades_df()
    fp = build_footprint(df, tick_size, interval_sec, MAX_COLUMNS)

    cd = build_cumulative_delta(fp) if fp else None
    narrative = detect_order_flow_narrative(fp, cd) if fp else None

    fp_fig = render_footprint_figure(fp, pair, narrative) if fp else go.Figure(
        layout=dict(plot_bgcolor=BG_PLOT, paper_bgcolor=BG_PAPER,
                    annotations=[dict(text="در حال دریافت دیتای زنده...", x=0.5, y=0.5,
                                       showarrow=False, font=dict(color=NAVY, size=14))]))
    asks, bids = get_orderbook_snapshot()
    ob_fig = render_orderbook_figure(asks, bids, pair)

    cum_delta_fig = render_cumulative_delta_figure(cd)
    delta_bars_fig = render_delta_bars_figure(cd)

    price_range = (min(fp["rows"]), max(fp["rows"])) if fp else None
    vp = build_volume_profile(df, tick_size, price_range=price_range)
    vp_fig = render_volume_profile_figure(vp, pair)

    decision_map_children = render_decision_map(narrative)

    banner_base_style = {"display": "block", "textAlign": "center", "fontWeight": "800",
                          "padding": "10px 16px", "borderRadius": "10px", "margin": "0 0 14px 0",
                          "color": "#fff", "fontSize": "13px", "letterSpacing": "0.4px"}
    if narrative and narrative["reversal_risk"]:
        banner_text = "⚠ هشدار: دلتای مثبت بالا در سقف بدون پیشرفت قیمت — ریسک بازگشت (Reversal Risk) شناسایی شد."
        banner_style = {**banner_base_style, "background": RED}
    elif narrative and narrative["acceptance"]:
        banner_text = "✅ پذیرش قیمت بالای سقف تأیید شد — منطقه ارزش پایدار در حال شکل‌گیری است."
        banner_style = {**banner_base_style, "background": GREEN}
    else:
        banner_text = ""
        banner_style = {"display": "none"}

    # --- سطح L3: میکروساختار دفتر سفارش ---
    hist_df = get_book_history_df(seconds=600)
    events_df = get_book_events_df(seconds=120)
    obi_fig = render_obi_figure(hist_df)
    microprice_fig = render_microprice_figure(hist_df, df)
    depth_heatmap_fig = render_depth_heatmap_figure(hist_df, tick_size)
    book_events_fig = render_book_events_figure(events_df)

    return (fp_fig, ob_fig, cum_delta_fig, vp_fig, delta_bars_fig, decision_map_children,
            banner_text, banner_style, obi_fig, microprice_fig, depth_heatmap_fig, book_events_fig)


if __name__ == "__main__":
    print("در حال اتصال پایدار به بایبیت (چند میزبان fallback)...")
    restart_stream(DEFAULT_SYMBOL, DEFAULT_CATEGORY)
    time.sleep(2)
    app.run(debug=True, host="0.0.0.0", port=8050)