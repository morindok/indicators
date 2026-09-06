# -*- coding: utf-8 -*-
"""
Bybit Footprint Chart - Stable Connection + Order-Flow Poster Style + SIGNAL ENGINE
----------------------------------------------------------------------
pip install dash dash-bootstrap-components plotly pandas numpy requests websocket-client

اجرا:
    python bybit_footprint_dash_stable.py

ویژگی‌های این نسخه:
  ۱) اتصال پایدار: هم REST و هم WebSocket روی چند دامنه/میرور بایبیت (fallback
     خودکار) + Watchdog ضد سکوت.
  ۲) ظاهر الهام‌گرفته از پوستر Order Flow: سلول‌های Bid×Ask، نوار جهت کندل،
     باکس طلایی POC/HVN، حاشیه نقطه‌چین Imbalance قطری، برچسب‌های فشار.
  ۳) نمودارهای علمی: دلتای تجمعی، پروفایل حجم، هیستوگرام دلتا، میکروساختار L3.
  ۴) ★ جدید ★ موتور سیگنال بر اساس شش خوانش فوت‌پرینتِ پوسترها:
     TOTAL VOLUME / BAR DELTA / DELTA% / MAX +DELTA / MAX -DELTA / BAR POC
     نقشه سیگنال‌دهی از زنجیره‌ی فاکتورها عبور می‌کند:
       G1 نردبان Bid×Ask (Sell-classified vs Buy-classified)
       G2 حجم کل نسبت به میانگین  (Net pressure is NOT total activity)
       G3 دلتا٪ با مخرج حجم کل    (Delta% needs the denominator)
       G4 قله‌ی فشار کجاست؟        (Where did pressure peak?)
       G5 قیمت با آن چه کرد؟       (What did price do with it?)
     + سیگنال Imbalance انباشته (Stacked) + سیگنال روایت (جذب/پذیرش).
  ۵) ★ جدید ★ پاپ‌آپ مودال + صدا (Web Audio API) هنگام صدور هر سیگنال،
     با Cool-down ضد اسپم و بستن خودکار.
     ※ بعد از باز شدن داشبورد یک‌بار دکمه‌ی «فعال‌سازی صدا» را بزنید
       (محدودیت autoplay مرورگر).
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
STALE_SEC = 25
WATCHDOG_INTERVAL = 5


def bybit_get(path, params, timeout=10):
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

# --- ★ CONFIG موتور سیگنال (آستانه‌های نقشه سیگنال‌دهی) ---
SIG_DELTA_PCT = 15.0        # آستانه‌ی |Delta%| برای عبور از گیت ۳
SIG_VOL_RATIO = 1.15        # حجم کل ستون آخر باید حداقل این ضربدر میانگین باشد (گیت ۲)
SIG_COOLDOWN_SEC = 120      # ضد اسپم: هر نوع سیگنال حداکثر هر ۲ دقیقه یک‌بار
SIG_AUTO_CLOSE_SEC = 20     # بستن خودکار مودال بعد از این مدت

TRADE_COLS = ["id", "ts", "price", "amount", "side"]

# --- پالت کاغذی + پالت تیره‌ی پوسترها ---
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

# پالت تیره‌ی پوستر (برای پنل سیگنال و مودال)
DARK_BG = "#171426"
DARK_CELL = "#221d33"
DARK_BORDER = "#3a3450"
CREAM = "#f5efe0"
PINK = "#e0407a"
TEAL = "#57b8d0"

# ------------------------------------------------------------------------------
STATE_LOCK = threading.RLock()
TRADES = deque(maxlen=TRADE_BUFFER_MAX)
ORDER_BOOK = {"bids": {}, "asks": {}, "ready": False}
CONN_STATUS = {"connected": False, "symbol": DEFAULT_SYMBOL, "category": DEFAULT_CATEGORY,
               "ws_host": "-", "rest_host": "-"}
LAST_MSG_TS = {"t": 0.0}

# --- ★ وضعیت جهانی موتور سیگنال ---
SIGNAL_STATE = {"last_id": 0, "fired_keys": {}, "latest": None, "modal_opened_at": 0.0}
SIGNAL_LOG = deque(maxlen=50)

# --- سطح L3 ---
L3_DEPTH_LEVELS = 10
L3_SAMPLE_INTERVAL = 1.0
L3_EVENTS_MAX = 20_000
L3_HISTORY_MAX = 1800
BOOK_EVENTS = deque(maxlen=L3_EVENTS_MAX)
BOOK_HISTORY = deque(maxlen=L3_HISTORY_MAX)
_LAST_L3_SAMPLE = {"t": 0.0}


def _maybe_sample_book_history(now_ts):
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
# 3) Bootstrap اولیه از REST
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
                self.host_idx += 1
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

    backfill_trades_rest(symbol, category)

    _OB_BOOTSTRAP_STOP = threading.Event()
    threading.Thread(target=orderbook_bootstrap_loop, args=(symbol, category, _OB_BOOTSTRAP_STOP),
                      daemon=True).start()

    CURRENT_STREAM = BybitStream(symbol, category)
    CURRENT_STREAM.start()


def watchdog_loop():
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
# 6) تجمیع فوت‌پرینت
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
# 6b) نمودارهای علمی: دلتای تجمعی، پروفایل حجم، هیستوگرام دلتا
# ==============================================================================
def build_cumulative_delta(fp):
    if fp is None:
        return None
    cols = fp["cols"]
    col_delta = fp["delta"].sum(axis=0).reindex(cols).fillna(0.0)
    col_vol = fp["total"].sum(axis=0).reindex(cols).fillna(0.0)
    cum_delta = col_delta.cumsum()
    return {"cols": cols, "col_delta": col_delta, "col_vol": col_vol, "cum_delta": cum_delta}


def build_volume_profile(df: pd.DataFrame, tick_size: float, price_range=None):
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
# 6c) موتور روایت اردر فلو
# ==============================================================================
def price_to_y(price, rows, n_rows):
    max_p, min_p = max(rows), min(rows)
    if max_p == min_p:
        return n_rows / 2.0
    frac = (max_p - price) / (max_p - min_p)
    return n_rows - frac * n_rows


def detect_order_flow_narrative(fp, cd, lookahead=3, high_frac=0.998):
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
# 6d) ★ موتور سیگنال: شش خوانش فوت‌پرینت + نقشه سیگنال‌دهی عبوری از فاکتورها ★
# ==============================================================================
def compute_bar_readings(fp):
    """برای هر ستون، دقیقاً شش خوانش پوسترها + طبقه‌بندی خرید/فروش + کف/سقف قبلی."""
    if fp is None:
        return []
    readings = []
    prev_low = prev_high = None
    for c in fp["cols"]:
        tot_s = fp["total"][c]
        dlt_s = fp["delta"][c]
        total = float(tot_s.sum())
        delta = float(dlt_s.sum())
        delta_pct = (delta / total * 100.0) if total > 0 else 0.0
        traded = tot_s[tot_s > 0]
        if len(traded) > 0:
            high = float(traded.index.max()); low = float(traded.index.min())
            max_plus_v = float(dlt_s.max()); max_plus_p = float(dlt_s.idxmax())
            max_minus_v = float(dlt_s.min()); max_minus_p = float(dlt_s.idxmin())
            poc = float(tot_s.idxmax())
        else:
            high = low = max_plus_v = max_plus_p = max_minus_v = max_minus_p = poc = None
        o = fp["col_open"].get(c, np.nan); cl = fp["col_close"].get(c, np.nan)
        readings.append({
            "col": c,
            "total_volume": total,                       # TOTAL VOLUME
            "bar_delta": delta,                          # BAR DELTA
            "delta_pct": delta_pct,                      # DELTA %
            "buy_classified": float(fp["ask"][c].sum()), # AT ASK OR HIGHER
            "sell_classified": float(fp["bid"][c].sum()),# AT BID OR LOWER
            "max_plus_v": max_plus_v, "max_plus_p": max_plus_p,   # MAX +DELTA
            "max_minus_v": max_minus_v, "max_minus_p": max_minus_p,  # MAX -DELTA
            "poc": poc,                                  # BAR POC
            "high": high, "low": low,
            "open": float(o) if pd.notna(o) else None,
            "close": float(cl) if pd.notna(cl) else None,
            "prev_low": prev_low, "prev_high": prev_high,
        })
        if low is not None:
            prev_low, prev_high = low, high
    return readings


def _make_sig(kind, side, last, vol_ratio):
    """ساخت آبجکت سیگنال با metrics شش‌گانه و دلایل فارسی به سبک پوسترها."""
    m = {
        "total_volume": last["total_volume"], "bar_delta": last["bar_delta"],
        "delta_pct": last["delta_pct"], "poc": last["poc"],
        "max_plus_v": last["max_plus_v"], "max_plus_p": last["max_plus_p"],
        "max_minus_v": last["max_minus_v"], "max_minus_p": last["max_minus_p"],
        "buy_cls": last["buy_classified"], "sell_cls": last["sell_classified"],
    }
    t = pd.Timestamp(last["col"]).strftime("%H:%M")
    if kind == "ABSORPTION" and side == "LONG":
        title = "🟢 LONG · جذب فروش + پس‌گرفتن کف"
        desc = ("فشار فروش سنگین روی نردبان Bid×Ask توسط خریداران غیرفعال جذب شد؛ "
                "منفی‌ترین قیمت بسته را کنترل نکرد و قیمت کف قبلی را پس گرفت.")
        reasons = [
            f"گیت۱ نردبان Bid×Ask: تهاجم فروش غالب — Sell {m['sell_cls']:,.0f} vs Buy {m['buy_cls']:,.0f} (دلتا {m['bar_delta']:+,.0f})",
            f"گیت۲ فشار خالص ≠ کل فعالیت: حجم کل {m['total_volume']:,.0f} = {vol_ratio:.2f}× میانگین → فشار واقعی",
            f"گیت۳ Delta% با مخرج حجم کل: {m['delta_pct']:.1f}% → فروش تهاجمی معنادار",
            f"گیت۴ قله فشار فروش: Max −Delta = {m['max_minus_v']:,.0f} در {m['max_minus_p']:,.0f}",
            f"گیت۵ قیمت با آن چه کرد؟ Close={last['close']:,.0f} بالای کف قبلی ({last['prev_low']:,.0f}) و بالای منفی‌ترین سطح → جذب = LONG",
        ]
    elif kind == "ABSORPTION" and side == "SHORT":
        title = "🔴 SHORT · جذب خرید + از دست‌رفتن سقف"
        desc = ("فشار خرید سنگین روی نردبان توسط فروشندگان غیرفعال جذب شد؛ "
                "مثبت‌ترین قیمت بسته را کنترل نکرد و قیمت سقف قبلی را پس نگرفت.")
        reasons = [
            f"گیت۱ نردبان Bid×Ask: تهاجم خرید غالب — Buy {m['buy_cls']:,.0f} vs Sell {m['sell_cls']:,.0f} (دلتا {m['bar_delta']:+,.0f})",
            f"گیت۲ فشار خالص ≠ کل فعالیت: حجم کل {m['total_volume']:,.0f} = {vol_ratio:.2f}× میانگین → فشار واقعی",
            f"گیت۳ Delta% با مخرج حجم کل: +{m['delta_pct']:.1f}% → خرید تهاجمی معنادار",
            f"گیت۴ قله فشار خرید: Max +Delta = {m['max_plus_v']:,.0f} در {m['max_plus_p']:,.0f}",
            f"گیت۵ قیمت با آن چه کرد؟ Close={last['close']:,.0f} زیر سقف قبلی ({last['prev_high']:,.0f}) و زیر مثبت‌ترین سطح → جذب = SHORT",
        ]
    elif kind == "STACKED_IMB":
        d = "خرید" if side == "LONG" else "فروش"
        title = f"{'🟢 LONG' if side == 'LONG' else '🔴 SHORT'} · Imbalance انباشته {d}"
        desc = f"حداقل {STACK_MIN} پله Imbalance قطری هم‌جهت در ستون آخر — تهاجم پایدار {d}."
        reasons = [
            f"نردبان Bid×Ask: زنجیره Imbalance قطری {d} (Stacked ≥ {STACK_MIN})",
            f"حجم کل ستون: {m['total_volume']:,.0f} · دلتا: {m['bar_delta']:+,.0f} ({m['delta_pct']:.1f}%)",
            f"قله فشار: Max +Delta {m['max_plus_v']:,.0f} / Max −Delta {m['max_minus_v']:,.0f}",
        ]
    else:  # NARRATIVE
        title = f"{'🟢 LONG' if side == 'LONG' else '🔴 SHORT'} · روایت اردر فلو"
        desc = "تشخیص سطح کلان روایت (جذب/پذیرش) توسط موتور روایت."
        reasons = ["جزئیات در پنل نقشه تصمیم."]
    return {"key": (kind, side, str(last["col"])), "kind": kind, "side": side,
            "title_fa": title, "desc_fa": desc, "col": last["col"], "time_str": t,
            "metrics": m, "reasons": reasons}


def evaluate_signal_map(readings, imb, stacked):
    """
    نقشه سیگنال‌دهی: زنجیره‌ی ۵ گیتی (مطابق پوسترها) باید یک‌جا عبور کند.
    خروجی: (gates برای پنل, لیست سیگنال‌های نامزد, verdict فعلی)
    """
    gates, signals, verdict = [], [], None
    if not readings or len(readings) < 2:
        return gates, signals, verdict
    last = readings[-1]
    if last["total_volume"] <= 0 or last["close"] is None:
        return gates, signals, verdict

    avg_vol = float(np.mean([r["total_volume"] for r in readings[:-1]]))
    vol_ratio = last["total_volume"] / avg_vol if avg_vol > 0 else 0.0
    vol_ok = vol_ratio >= SIG_VOL_RATIO
    bear_path = last["bar_delta"] < 0

    if bear_path:
        price_ok = (last["prev_low"] is not None
                    and last["close"] > last["prev_low"]
                    and last["close"] > (last["max_minus_p"] or 0)
                    and last["close"] >= (last["open"] if last["open"] is not None else last["close"]))
        gates = [
            {"label": "گیت۱ · نردبان Bid×Ask — تهاجم فروش (Sell-classified غالب)",
             "value": f"Sell {last['sell_classified']:,.0f} vs Buy {last['buy_classified']:,.0f}", "passed": True},
            {"label": "گیت۲ · حجم کل نسبت به میانگین (Net pressure ≠ total activity)",
             "value": f"{vol_ratio:.2f}× (آستانه ≥ {SIG_VOL_RATIO}×)", "passed": vol_ok},
            {"label": "گیت۳ · Delta% با مخرج حجم کل (Delta% needs denominator)",
             "value": f"{last['delta_pct']:.1f}% (آستانه ≤ -{SIG_DELTA_PCT}%)", "passed": last["delta_pct"] <= -SIG_DELTA_PCT},
            {"label": "گیت۴ · قله فشار فروش کجاست؟ (Where did pressure peak)",
             "value": f"Max −Delta {last['max_minus_v']:,.0f} @ {last['max_minus_p']:,.0f}", "passed": (last["max_minus_v"] or 0) < 0},
            {"label": "گیت۵ · قیمت با آن چه کرد؟ پس‌گرفتن کف قبلی / منفی‌ترین قیمت Close را کنترل نکرد",
             "value": (f"Close {last['close']:,.0f} vs PriorLow {last['prev_low']:,.0f}" if last["prev_low"] else "-"),
             "passed": price_ok},
        ]
        if all(g["passed"] for g in gates):
            verdict = "LONG"
            signals.append(_make_sig("ABSORPTION", "LONG", last, vol_ratio))
    else:
        price_ok = (last["prev_high"] is not None
                    and last["close"] < last["prev_high"]
                    and last["close"] < (last["max_plus_p"] or 0)
                    and last["close"] <= (last["open"] if last["open"] is not None else last["close"]))
        gates = [
            {"label": "گیت۱ · نردبان Bid×Ask — تهاجم خرید (Buy-classified غالب)",
             "value": f"Buy {last['buy_classified']:,.0f} vs Sell {last['sell_classified']:,.0f}", "passed": True},
            {"label": "گیت۲ · حجم کل نسبت به میانگین (Net pressure ≠ total activity)",
             "value": f"{vol_ratio:.2f}× (آستانه ≥ {SIG_VOL_RATIO}×)", "passed": vol_ok},
            {"label": "گیت۳ · Delta% با مخرج حجم کل (Delta% needs denominator)",
             "value": f"+{last['delta_pct']:.1f}% (آستانه ≥ +{SIG_DELTA_PCT}%)", "passed": last["delta_pct"] >= SIG_DELTA_PCT},
            {"label": "گیت۴ · قله فشار خرید کجاست؟ (Where did pressure peak)",
             "value": f"Max +Delta {last['max_plus_v']:,.0f} @ {last['max_plus_p']:,.0f}", "passed": (last["max_plus_v"] or 0) > 0},
            {"label": "گیت۵ · قیمت با آن چه کرد؟ عدم پس‌گرفتن سقف قبلی / مثبت‌ترین قیمت Close را کنترل نکرد",
             "value": (f"Close {last['close']:,.0f} vs PriorHigh {last['prev_high']:,.0f}" if last["prev_high"] else "-"),
             "passed": price_ok},
        ]
        if all(g["passed"] for g in gates):
            verdict = "SHORT"
            signals.append(_make_sig("ABSORPTION", "SHORT", last, vol_ratio))

    # --- سیگنال Imbalance انباشته در ستون آخر ---
    last_col = last["col"]
    stack_dirs = set()
    for (p, c) in stacked:
        if c == last_col:
            d = imb.get((p, c))
            if d:
                stack_dirs.add(d)
    if "buy" in stack_dirs:
        signals.append(_make_sig("STACKED_IMB", "LONG", last, vol_ratio))
    if "sell" in stack_dirs:
        signals.append(_make_sig("STACKED_IMB", "SHORT", last, vol_ratio))

    return gates, signals, verdict


# --- رندر پنل تیره‌ی «نقشه سیگنال‌دهی» به سبک پوسترها ---
def _sig_chip(label_en, value_text, color):
    return html.Div([
        html.Div(label_en, style={"fontSize": "9px", "color": "#9a93a8", "letterSpacing": "1px", "direction": "ltr"}),
        html.Div(value_text, style={"fontSize": "14px", "fontWeight": "800", "color": color,
                                     "fontFamily": "Courier New, monospace", "direction": "ltr"}),
    ], style={"background": DARK_CELL, "border": f"1px solid {DARK_BORDER}", "borderRadius": "10px",
              "padding": "7px 10px", "flex": "1", "minWidth": "120px", "textAlign": "center"})


def _gate_row(g):
    icon = "✔" if g["passed"] else "✖"
    icolor = "#7dd8a5" if g["passed"] else "#8a8496"
    return html.Div([
        html.Span(icon, style={"color": icolor, "fontWeight": "800", "marginLeft": "8px"}),
        html.Div([
            html.Div(g["label"], style={"fontSize": "11px", "color": CREAM, "fontWeight": "600"}),
            html.Div(g["value"], style={"fontSize": "10.5px", "color": "#9a93a8",
                                         "fontFamily": "Courier New, monospace", "direction": "ltr", "textAlign": "right"}),
        ], style={"flex": "1"}),
    ], style={"display": "flex", "alignItems": "center", "padding": "5px 8px",
              "borderBottom": f"1px dashed {DARK_BORDER}"})


def render_signal_map_panel(readings, gates, verdict, latest_sig, log_list, pair):
    last = readings[-1] if readings else None
    children = []

    children.append(html.Div([
        html.Span("SIGNAL MAP · نقشه سیگنال‌دهی", style={"fontWeight": "800", "color": CREAM, "fontSize": "15px"}),
        html.Span(f"{pair} · آخرین ستون کامل", style={"color": "#9a93a8", "fontSize": "10.5px", "marginRight": "10px"}),
    ], style={"display": "flex", "alignItems": "baseline", "marginBottom": "10px"}))

    if last and last["total_volume"] > 0:
        # --- شش خوانش فوت‌پرینت (پوستر ۱) ---
        children.append(html.Div([
            _sig_chip("TOTAL VOLUME", f"{last['total_volume']:,.0f}", CREAM),
            _sig_chip("BAR DELTA", f"{last['bar_delta']:+,.0f}", "#7dd8a5" if last["bar_delta"] >= 0 else PINK),
            _sig_chip("DELTA %", f"{last['delta_pct']:.1f}%", "#7dd8a5" if last["delta_pct"] >= 0 else PINK),
            _sig_chip("MAX +DELTA", f"{last['max_plus_v']:+,.0f} @ {last['max_plus_p']:,.0f}", TEAL),
            _sig_chip("MAX −DELTA", f"{last['max_minus_v']:,.0f} @ {last['max_minus_p']:,.0f}", PINK),
            _sig_chip("BAR POC", f"{last['poc']:,.0f}", GOLD),
        ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginBottom": "10px"}))

        # --- نردبان Bid×Ask:_sell vs buy classified (پوستر ۲) ---
        tot_cls = last["sell_classified"] + last["buy_classified"]
        if tot_cls > 0:
            sell_w = last["sell_classified"] / tot_cls * 100
            children.append(html.Div([
                html.Div([
                    html.Div("SELL-CLASSIFIED (AT BID OR LOWER)", style={"fontSize": "9px", "color": PINK, "direction": "ltr"}),
                    html.Div(f"{last['sell_classified']:,.0f}", style={"fontSize": "12px", "color": PINK, "fontWeight": "800", "direction": "ltr"}),
                ], style={"flex": "1"}),
                html.Div([
                    html.Div("BUY-CLASSIFIED (AT ASK OR HIGHER)", style={"fontSize": "9px", "color": TEAL, "direction": "ltr", "textAlign": "right"}),
                    html.Div(f"{last['buy_classified']:,.0f}", style={"fontSize": "12px", "color": TEAL, "fontWeight": "800", "direction": "ltr", "textAlign": "right"}),
                ], style={"flex": "1"}),
            ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "4px"}))
            children.append(html.Div([
                html.Div(style={"width": f"{sell_w:.1f}%", "background": PINK, "height": "8px", "borderRadius": "4px 0 0 4px"}),
                html.Div(style={"width": f"{100 - sell_w:.1f}%", "background": TEAL, "height": "8px", "borderRadius": "0 4px 4px 0"}),
            ], style={"display": "flex", "marginBottom": "12px"}))

    # --- زنجیره گیت‌ها ---
    if gates:
        children.append(html.Div("زنجیره عبور از فاکتورها (ستون آخر):",
                                  style={"fontSize": "11px", "color": "#9a93a8", "marginBottom": "4px"}))
        for g in gates:
            children.append(_gate_row(g))

    # --- verdict ---
    if verdict == "LONG":
        v_color, v_text = "#2ea86b", "🟢 سیگنال LONG · همه گیت‌ها عبور کردند"
    elif verdict == "SHORT":
        v_color, v_text = PINK, "🔴 سیگنال SHORT · همه گیت‌ها عبور کردند"
    else:
        v_color, v_text = "#8a8496", "NO SIGNAL · در انتظار عبور هم‌زمان گیت‌ها"
    children.append(html.Div(v_text, style={"marginTop": "10px", "textAlign": "center", "fontWeight": "800",
                                             "color": "#171426", "background": v_color,
                                             "borderRadius": "12px", "padding": "8px", "fontSize": "13px"}))

    # --- تاریخچه سیگنال‌ها ---
    if log_list:
        log_rows = []
        for s in list(log_list)[:6]:
            sc = "#2ea86b" if s["side"] == "LONG" else PINK
            log_rows.append(html.Div([
                html.Span(s["time_str"], style={"color": "#9a93a8", "fontSize": "10px",
                                                 "fontFamily": "Courier New, monospace", "marginLeft": "8px"}),
                html.Span(s["side"], style={"background": sc, "color": "#fff", "borderRadius": "8px",
                                             "padding": "1px 8px", "fontSize": "9.5px", "fontWeight": "800", "marginLeft": "8px"}),
                html.Span(s["title_fa"], style={"color": CREAM, "fontSize": "10.5px"}),
            ], style={"display": "flex", "alignItems": "center", "padding": "3px 0"}))
        children.append(html.Div([
            html.Div("آخرین سیگنال‌ها:", style={"fontSize": "11px", "color": "#9a93a8", "margin": "10px 0 4px"}),
            *log_rows,
        ]))

    return html.Div(children, style={"background": DARK_BG, "borderRadius": "14px", "padding": "14px",
                                      "border": f"1.5px solid {DARK_BORDER}"})


def render_signal_modal_body(sig, pair):
    m = sig["metrics"]
    chips = html.Div([
        _sig_chip("TOTAL VOLUME", f"{m['total_volume']:,.0f}", CREAM),
        _sig_chip("BAR DELTA", f"{m['bar_delta']:+,.0f}", "#7dd8a5" if m["bar_delta"] >= 0 else PINK),
        _sig_chip("DELTA %", f"{m['delta_pct']:.1f}%", "#7dd8a5" if m["delta_pct"] >= 0 else PINK),
        _sig_chip("MAX +DELTA", f"{m['max_plus_v']:+,.0f} @ {m['max_plus_p']:,.0f}", TEAL),
        _sig_chip("MAX −DELTA", f"{m['max_minus_v']:,.0f} @ {m['max_minus_p']:,.0f}", PINK),
        _sig_chip("BAR POC", f"{m['poc']:,.0f}", GOLD),
    ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "margin": "12px 0"})

    reasons = [html.Li(r, style={"color": CREAM, "fontSize": "12px", "marginBottom": "6px", "lineHeight": "1.7"})
               for r in sig["reasons"]]

    return html.Div([
        html.Div(sig["desc_fa"], style={"color": "#cfc9dd", "fontSize": "12.5px", "lineHeight": "1.8"}),
        chips,
        html.Div("چرا این سیگنال؟ (عبور از فاکتورها):", style={"color": GOLD, "fontWeight": "800", "fontSize": "12px", "marginBottom": "6px"}),
        html.Ul(reasons, style={"paddingRight": "18px", "margin": 0}),
        html.Div("⚠ این هشدار صرفاً اطلاعی است؛ Order Flow را همیشه با ساختار بازار و مدیریت ریسک ترکیب کنید.",
                 style={"marginTop": "12px", "color": "#9a93a8", "fontSize": "10.5px"}),
        html.Div(f"{pair} · {sig['time_str']} · ILLUSTRATIVE ENGINE",
                 style={"marginTop": "6px", "color": "#6f6981", "fontSize": "9.5px",
                         "fontFamily": "Courier New, monospace", "direction": "ltr", "textAlign": "right"}),
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

    for ri, p in enumerate(rows):
        y0, y1 = n_rows - ri - 1, n_rows - ri
        annotations.append(dict(x=-0.12, y=(y0 + y1) / 2, text=f"{p:,.0f}", showarrow=False,
                                 font=dict(color=NAVY, size=9), xanchor="right"))

    shapes.append(dict(type="line", x0=-0.2, x1=n_cols * col_w + 0.3, y0=-1.1, y1=-1.1,
                        line=dict(color=NAVY, width=1.5)))
    annotations.append(dict(x=n_cols * col_w + 0.3, y=-1.1, text="▶", showarrow=False,
                             font=dict(color=NAVY, size=13), xanchor="left", yanchor="middle"))

    zone_x = n_cols * col_w + 0.9
    annotations.append(dict(x=zone_x, y=n_rows * 0.83, text="▲ فشار خرید", showarrow=False,
                             font=dict(color=GREEN, size=12, family="Arial Black"), xanchor="left"))
    annotations.append(dict(x=zone_x, y=n_rows * 0.5, text="⋮ منطقه تعادل", showarrow=False,
                             font=dict(color=NEUTRAL_TXT, size=11), xanchor="left"))
    annotations.append(dict(x=zone_x, y=n_rows * 0.17, text="▼ فشار فروش", showarrow=False,
                             font=dict(color=RED, size=12, family="Arial Black"), xanchor="left"))
    shapes.append(dict(type="line", x0=zone_x - 0.25, x1=zone_x - 0.25, y0=0, y1=n_rows,
                        line=dict(color=NAVY, width=1, dash="dot")))

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
# 7b) نمودارهای میکروساختار سطح L3
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
# 8) داشبورد Dash - ظاهر پوستری کاغذی + مودال سیگنال
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY,
                 "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;800&display=swap"])
app.title = "Order Flow · Bybit Footprint · Signal Engine"

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
        .modal-content { background:#171426 !important; color:#f5efe0 !important;
                         border:2px solid #d4a017 !important; border-radius:16px !important; }
        .modal-header, .modal-footer { background:#171426 !important; border-color:#3a3450 !important; }
        .btn-close { filter: invert(1) grayscale(1) brightness(2); }
        @keyframes sigpulse { 0%{box-shadow:0 0 0 0 rgba(212,160,23,.7);} 100%{box-shadow:0 0 0 14px rgba(212,160,23,0);} }
        .sig-pulse { animation: sigpulse 1.2s infinite; }
    </style>
</head>
<body>{%app_entry%}{%config%}{%scripts%}{%renderer%}</body>
</html>
"""

app.layout = dbc.Container([
    html.Div([
        html.Div("ORDER FLOW · SIGNAL ENGINE", className="poster-title"),
        html.Div("خواندن نبرد واقعی خریداران و فروشندگان + هشدار صوتی سیگنال — داده زنده بایبیت", className="poster-sub"),
        html.Div([
            html.Button("🔇 فعال‌سازی صدا", id="sound-unlock-btn",
                         style={"background": NAVY, "color": "#fff", "border": "none", "borderRadius": "18px",
                                 "padding": "6px 16px", "fontWeight": "700", "cursor": "pointer"}),
            html.Div(id="sound-state", style={"fontSize": "11px", "color": NEUTRAL_TXT}),
            html.Div(id="latest-signal-badge", className="badge-conn"),
        ], style={"display": "flex", "gap": "10px", "justifyContent": "center", "alignItems": "center",
                  "marginBottom": "8px"}),
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

    # --- ★ پنل نقشه سیگنال‌دهی (تیره، سبک پوسترها) ---
    dbc.Row([
        dbc.Col(html.Div(id="signal-map-panel"), width=12),
    ], className="mb-3"),

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
                html.Div("✔ شش خوانش هر ستون: Total Volume / Bar Delta / Delta% / Max±Delta / POC", className="legend-item"),
                html.Div("✔ Delta% بدون مخرج حجم کل ناقص است (پوستر ۳)", className="legend-item"),
                html.Div("✔ فشار خالص ≠ کل فعالیت؛ حجم نسبی را چک کنید (پوستر ۲)", className="legend-item"),
                                html.Div("✔ قله فشار (Max ±Delta) کجاست؟ سطح سنگین باید واکنش بگیرد (پوستر ۴)", className="legend-item"),
                html.Div("✔ قیمت با فشار چه کرد؟ پس‌گرفتن کف/سقف قبلی = جذب (پوستر ۵)", className="legend-item"),
                html.Div("✔ فشار خرید تهاجمی (زدن به Ask) / فشار فروش تهاجمی (زدن به Bid)", className="legend-item"),
                html.Div("✔ باکس طلایی = HVN / نقطه کنترل حجم", className="legend-item"),
                html.Div("✔ حاشیه نقطه‌چین = Imbalance قطری", className="legend-item"),
                html.Div("✔ نوار کنار ستون = جهت کلی کندل", className="legend-item"),
                html.Div("✔ باکس نقطه‌چین طلایی = ناحیه جذب سقف (Absorption)", className="legend-item"),
                html.Div("✔ فلش قرمز = رد قیمت / شکست ناموفق (Failed Breakout)", className="legend-item"),
                html.Div("✔ باکس سبز = منطقه ارزش پایدار (Value Zone)", className="legend-item"),
                html.Div("✔ حباب‌های رنگی = حجم تهاجمی خرید/فروش نزدیک سقف", className="legend-item"),
                html.Div("✔ 🚨 صدور سیگنال = پاپ‌آپ مودال + صدا (پس از فعال‌سازی صدا)", className="legend-item"),
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
        html.Div("★ سیگنال فقط وقتی صادر می‌شود که همه‌ی گیت‌های نقشه سیگنال‌دهی هم‌زمان عبور کنند."),
        html.Div("★ آستانه‌ها در بالای فایل: SIG_DELTA_PCT / SIG_VOL_RATIO / SIG_COOLDOWN_SEC / SIG_AUTO_CLOSE_SEC"),
    ], className="paper-card"),

    # --- ★ پاپ‌آپ مودال سیگنال (تیره/طلایی، سبک پوسترها) ---
    dbc.Modal([
        dbc.ModalHeader(
            dbc.ModalTitle(id="signal-modal-title", style={"color": CREAM, "fontWeight": "800"}),
            close_button=True,
            style={"background": DARK_BG, "borderBottom": f"1px solid {DARK_BORDER}"},
        ),
        dbc.ModalBody(id="signal-modal-body", style={"background": DARK_BG, "color": CREAM}),
        dbc.ModalFooter(
            dbc.Button("بستن", id="signal-modal-close",
                        style={"background": GOLD, "color": "#171426", "fontWeight": "800",
                               "border": "none", "borderRadius": "12px", "padding": "6px 22px"}),
            style={"background": DARK_BG, "borderTop": f"1px solid {DARK_BORDER}"},
        ),
    ], id="signal-modal", is_open=False, centered=True, size="lg", backdrop=True, scrollable=True),

    # divهای مخفی: تریگر صدا + خروجی noop کلاینت‌ساید
    html.Div(id="signal-sound-trigger", style={"display": "none"}),
    html.Div(id="sound-noop", style={"display": "none"}),

], fluid=True)


# ==============================================================================
# 9) Callback ها
# ==============================================================================
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
    Output("signal-map-panel", "children"),
    Output("latest-signal-badge", "children"), Output("latest-signal-badge", "style"),
    Output("signal-sound-trigger", "children"),
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

    # --- ★ موتور سیگنال: شش خوانش + زنجیره گیت‌ها ---
    imb = compute_diagonal_imbalances(fp) if fp else {}
    stacked = detect_stacked(imb, fp["rows"], fp["cols"]) if fp else set()
    readings = compute_bar_readings(fp) if fp else []
    gates, sig_candidates, verdict = evaluate_signal_map(readings, imb, stacked)

    # --- سیگنال‌های روایت اردر فلو (جذب سقف / پذیرش) ---
    if narrative and readings:
        avg_vol = float(np.mean([r["total_volume"] for r in readings[:-1]])) if len(readings) > 1 else 0.0
        vol_ratio_now = readings[-1]["total_volume"] / avg_vol if avg_vol > 0 else 0.0
        if narrative["reversal_risk"]:
            nsig = _make_sig("NARRATIVE", "SHORT", readings[-1], vol_ratio_now)
            nsig["title_fa"] = "🔴 SHORT · ریسک بازگشت سقف (روایت جذب)"
            nsig["desc_fa"] = ("دلتای مثبت سنگین نزدیک سقف بدون پیشرفت قیمت — "
                               "خریداران تهاجمی توسط فروشندگان غیرفعال جذب شدند (رد قیمت / شکست ناموفق).")
            nsig["reasons"] = [
                f"روایت: قله قیمت {narrative['peak_price']:,.0f} با دلتای مثبت {narrative['delta_near_peak']:+,.0f} بدون ثبت سقف بالاتر",
                "قیمت بالای سقف حفظ نشد → جذب خرید = SHORT",
            ] + nsig["reasons"]
            sig_candidates.append(nsig)
        if narrative["acceptance"]:
            nsig = _make_sig("NARRATIVE", "LONG", readings[-1], vol_ratio_now)
            nsig["title_fa"] = "🟢 LONG · پذیرش سقف (روایت ارزش)"
            nsig["desc_fa"] = ("خریداران بزرگ سقف را ثبت و بالای آن حفظ کردند — "
                               "ساخت ارزش تأیید شد (منطقه ارزش پایدار).")
            nsig["reasons"] = [
                f"روایت: سقف {narrative['peak_price']:,.0f} ثبت شد و قیمت در ستون‌های بعد بالای آن ماند → پذیرش = LONG",
            ] + nsig["reasons"]
            sig_candidates.append(nsig)

    # --- ★ صدور سیگنال جدید (با Cool-down ضد اسپم) ---
    new_signal = None
    with STATE_LOCK:
        for sig in sig_candidates:
            key = sig["key"]
            last_fired = SIGNAL_STATE["fired_keys"].get(key)
            if last_fired is None or (time.time() - last_fired) > SIG_COOLDOWN_SEC:
                SIGNAL_STATE["fired_keys"][key] = time.time()
                SIGNAL_STATE["last_id"] += 1
                sig["id"] = SIGNAL_STATE["last_id"]
                SIGNAL_STATE["latest"] = sig
                SIGNAL_LOG.appendleft(sig)
                new_signal = sig
                break

    # --- رندر نمودارها ---
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

    # --- سطح L3 ---
    hist_df = get_book_history_df(seconds=600)
    events_df = get_book_events_df(seconds=120)
    obi_fig = render_obi_figure(hist_df)
    microprice_fig = render_microprice_figure(hist_df, df)
    depth_heatmap_fig = render_depth_heatmap_figure(hist_df, tick_size)
    book_events_fig = render_book_events_figure(events_df)

    # --- ★ پنل نقشه سیگنال + بج آخرین سیگنال + تریگر صدا ---
    with STATE_LOCK:
        latest = SIGNAL_STATE["latest"]
        log_snapshot = list(SIGNAL_LOG)
    signal_map_children = render_signal_map_panel(readings, gates, verdict, latest, log_snapshot, pair)

    if latest:
        badge_children = f"🚨 آخرین سیگنال: {latest['title_fa']} · {latest['time_str']}"
        badge_style = {"background": "#2ea86b" if latest["side"] == "LONG" else PINK,
                       "color": "#fff", "fontWeight": "700", "padding": "6px 14px",
                       "borderRadius": "20px", "textAlign": "center"}
    else:
        badge_children = "هنوز سیگنالی صادر نشده"
        badge_style = {"background": "#e5decd", "color": NEUTRAL_TXT, "fontWeight": "700",
                       "padding": "6px 14px", "borderRadius": "20px", "textAlign": "center"}

    sound_trigger = f"{new_signal['id']}:{new_signal['side']}" if new_signal else dash.no_update

    return (fp_fig, ob_fig, cum_delta_fig, vp_fig, delta_bars_fig, decision_map_children,
            banner_text, banner_style, obi_fig, microprice_fig, depth_heatmap_fig, book_events_fig,
            signal_map_children, badge_children, badge_style, sound_trigger)


# --- ★ باز شدن پاپ‌آپ مودال به محض صدور سیگنال ---
@app.callback(
    Output("signal-modal", "is_open", allow_duplicate=True),
    Output("signal-modal-title", "children"),
    Output("signal-modal-body", "children"),
    Input("signal-sound-trigger", "children"),
    prevent_initial_call=True,
)
def open_signal_modal(trig):
    if not trig:
        return dash.no_update, dash.no_update, dash.no_update
    with STATE_LOCK:
        sig = SIGNAL_STATE["latest"]
        pair = CONN_STATUS["symbol"]
        SIGNAL_STATE["modal_opened_at"] = time.time()
    if sig is None:
        return dash.no_update, dash.no_update, dash.no_update
    return True, f"🚨 سیگنال جدید · {sig['title_fa']}", render_signal_modal_body(sig, pair)


# --- بستن دستی مودال (دکمه + ضربدر + backdrop) ---
@app.callback(
    Output("signal-modal", "is_open", allow_duplicate=True),
    Input("signal-modal-close", "n_clicks"),
    Input("signal-modal", "n_dismiss"),
    prevent_initial_call=True,
)
def close_signal_modal(n_close, n_dismiss):
    if (n_close or 0) > 0 or (n_dismiss or 0) > 0:
        with STATE_LOCK:
            SIGNAL_STATE["modal_opened_at"] = 0.0
        return False
    return dash.no_update


# --- بستن خودکار مودال بعد از SIG_AUTO_CLOSE_SEC ---
@app.callback(
    Output("signal-modal", "is_open", allow_duplicate=True),
    Input("tick", "n_intervals"),
    prevent_initial_call=True,
)
def auto_close_signal_modal(_):
    with STATE_LOCK:
        opened_at = SIGNAL_STATE["modal_opened_at"]
    if opened_at and (time.time() - opened_at) > SIG_AUTO_CLOSE_SEC:
        with STATE_LOCK:
            SIGNAL_STATE["modal_opened_at"] = 0.0
        return False
    return dash.no_update


# --- ★ کلاینت‌ساید: پخش صدای هشدار (بوق صعودی برای LONG / نزولی برای SHORT) ---
app.clientside_callback(
    """
    function(trig){
        if(!trig) return window.dash_clientside.no_update;
        var parts = String(trig).split(":");
        var side = parts.length > 1 ? parts[1] : "LONG";
        try{
            if(!window.__audioCtx){
                window.__audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }
            var ctx = window.__audioCtx;
            if(window.__soundUnlocked){
                if(ctx.state === "suspended"){ ctx.resume(); }
                var seq = (side === "SHORT") ? [784, 622, 494] : [523, 659, 784];
                var now = ctx.currentTime;
                for(var i = 0; i < seq.length; i++){
                    var o = ctx.createOscillator();
                    var g = ctx.createGain();
                    o.type = (side === "SHORT") ? "sawtooth" : "sine";
                    o.frequency.value = seq[i];
                    g.gain.setValueAtTime(0.0001, now + i * 0.17);
                    g.gain.exponentialRampToValueAtTime(0.5, now + i * 0.17 + 0.02);
                    g.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.17 + 0.15);
                    o.connect(g); g.connect(ctx.destination);
                    o.start(now + i * 0.17); o.stop(now + i * 0.17 + 0.2);
                }
            }
        }catch(e){}
        return window.dash_clientside.no_update;
    }
    """,
    Output("sound-noop", "children"),
    Input("signal-sound-trigger", "children"),
    prevent_initial_call=True,
)


# --- ★ کلاینت‌ساید: باز کردن قفل autoplay صدا با یک کلیک کاربر ---
app.clientside_callback(
    """
    function(n){
        if(!n) return window.dash_clientside.no_update;
        try{
            if(!window.__audioCtx){
                window.__audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }
            if(window.__audioCtx.state === "suspended"){ window.__audioCtx.resume(); }
            window.__soundUnlocked = true;
            var ctx = window.__audioCtx;
            var o = ctx.createOscillator();
            var g = ctx.createGain();
            o.frequency.value = 880;
            o.connect(g); g.connect(ctx.destination);
            g.gain.setValueAtTime(0.3, ctx.currentTime);
            g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.18);
            o.start(); o.stop(ctx.currentTime + 0.2);
        }catch(e){}
        return "🔊 صدا فعال شد — از این به بعد هر سیگنال با بوق اعلام می‌شود";
    }
    """,
    Output("sound-state", "children"),
    Input("sound-unlock-btn", "n_clicks"),
    prevent_initial_call=True,
)


if __name__ == "__main__":
    print("در حال اتصال پایدار به بایبیت (چند میزبان fallback)...")
    print("یادآوری: بعد از باز شدن داشبورد در مرورگر، یک‌بار دکمه‌ی «فعال‌سازی صدا» را بزنید.")
    restart_stream(DEFAULT_SYMBOL, DEFAULT_CATEGORY)
    time.sleep(2)
    app.run(debug=True, host="0.0.0.0", port=8050)