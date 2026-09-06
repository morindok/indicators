# -*- coding: utf-8 -*-
"""
🌙 Bybit Trendline Volume Analyzer + 🐋 Whale Tick Scalper
------------------------------------------------------------------
تب ۱: همان تحلیل‌گر حجم ترندلاین قبلی (رسم خط روی چارت کندل، حجم خرید/فروش بالا و پایین خط).
تب ۲: پایش زنده‌ی تیک‌های معاملاتی بایبیت (WebSocket)، شمارش تیک‌های «نهنگ» (معاملات بزرگ)،
       صدور سیگنال اسکلپ وقتی عدم‌تعادل خرید/فروش نهنگ‌ها از حد آستانه بگذرد، به همراه:
         - حد سود / حد ضرر پیشنهادی
         - حجم پوزیشن و لوریج پیشنهادی برای سرمایه‌ی دلخواه (پیش‌فرض ۱۰۰ دلار)
         - ثبت هر سیگنال در دیتابیس SQLite محلی (ماندگار بین اجراهای مختلف)
         - جدول تاریخچه‌ی سیگنال‌ها + وین‌ریت زنده

⚠️ نکات صادقانه (مهم):
  - این ابزار مشاوره‌ی مالی نیست؛ یک ابزار تحلیل تکنیکال/حجمی است. تصمیم نهایی و ریسک با کاربر است.
  - «نهنگ» بر اساس ارزش دلاری هر معامله (price*size) تعریف شده، نه دیتای on-chain واقعی.
  - دیتای بایبیت جهت taker (Buy/Sell) واقعی را در استریم Public Trade می‌دهد (فیلد S)، پس این تفکیک
    دقیق‌تر از پروکسی رنگ کندل در تب ۱ است.
  - سیگنال «قطعی» به معنای «بدون خطا» نیست؛ یک قاعده‌ی مشخص و بدون ابهام برای ورود اسکلپ است که با
    رعایت حد ضرر اجرا می‌شود. لطفاً لوریج پیشنهادی را با ریسک واقعی خودتان تطبیق دهید.

نصب:
pip install dash dash-bootstrap-components plotly pandas numpy requests websocket-client
"""

import json
import os
import sqlite3
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import websocket
import dash
from dash import dcc, html, Input, Output, State, ctx, dash_table
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

# ==============================================================================
# 0) پالت رنگی تیره
# ==============================================================================
BG, CARD, LINE, TXT, MUT = "#0b1220", "#121c30", "#23314d", "#e8ecf4", "#8fa3c0"
GOLD, UP, DN = "#f0b90b", "#16a085", "#e74c3c"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_CATEGORY = "linear"
DEFAULT_INTERVAL = "15"

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whale_signals.db")

# ==============================================================================
# 1) اتصال REST پایدار به بایبیت (برای چارت کندل تب ۱)
# ==============================================================================
REST_CANDIDATES = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.bybit.com/",
})
_ACTIVE_REST_BASE = {"url": None}


def bybit_get(path, params, timeout=10):
    cands = ([_ACTIVE_REST_BASE["url"]] if _ACTIVE_REST_BASE["url"] else []) + \
            [b for b in REST_CANDIDATES if b != _ACTIVE_REST_BASE["url"]]
    for base in cands:
        try:
            r = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code in (403, 451):
                continue
            r.raise_for_status()
            d = r.json()
            if d.get("retCode") == 0:
                _ACTIVE_REST_BASE["url"] = base
                return d
        except Exception:
            continue
    return None


def get_klines(symbol, interval, category="linear", limit=500):
    d = bybit_get("/v5/market/kline", {
        "category": category, "symbol": symbol, "interval": interval, "limit": limit
    })
    if not d or "list" not in (d.get("result") or {}):
        return pd.DataFrame()
    lst = d["result"]["list"]
    if not lst:
        return pd.DataFrame()
    df = pd.DataFrame(lst, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts"] = pd.to_datetime(df["ts"].astype(int), unit="ms")
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df.sort_values("ts").reset_index(drop=True)


# ==============================================================================
# 2) تحلیل ترندلاین (تب ۱) — بدون تغییر نسبت به نسخه‌ی قبل
# ==============================================================================
def _line_y_at_x(x0, y0, x1, y1, x):
    if x1 == x0:
        return y0
    t = (x - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


def analyze_trendlines(df, shapes):
    if df.empty or not shapes:
        return []
    df_closed = df.iloc[:-1] if len(df) > 2 else df
    x_ms_all = (df_closed["ts"].astype("int64") // 10**6).to_numpy(dtype=float)
    is_buy = (df_closed["close"] >= df_closed["open"]).to_numpy()
    is_sell = ~is_buy
    volume = df_closed["volume"].to_numpy()
    close = df_closed["close"].to_numpy()

    results = []
    line_no = 0
    for sh in shapes:
        if sh.get("type") != "line":
            continue
        try:
            x0 = pd.Timestamp(sh["x0"]).value // 10**6
            x1 = pd.Timestamp(sh["x1"]).value // 10**6
            y0, y1 = float(sh["y0"]), float(sh["y1"])
        except Exception:
            continue

        line_no += 1
        x_lo, x_hi = (x0, x1) if x0 <= x1 else (x1, x0)
        in_range = (x_ms_all >= x_lo) & (x_ms_all <= x_hi)
        if not in_range.any():
            results.append({
                "line_no": line_no,
                "above_buy": 0.0, "above_sell": 0.0, "below_buy": 0.0, "below_sell": 0.0,
                "above_delta": 0.0, "below_delta": 0.0, "net_delta": 0.0,
            })
            continue

        line_y = _line_y_at_x(x0, y0, x1, y1, x_ms_all[in_range])
        seg_close = close[in_range]
        seg_buy = is_buy[in_range]
        seg_sell = is_sell[in_range]
        seg_vol = volume[in_range]

        above = seg_close > line_y
        below = ~above

        above_buy = float(seg_vol[above & seg_buy].sum())
        above_sell = float(seg_vol[above & seg_sell].sum())
        below_buy = float(seg_vol[below & seg_buy].sum())
        below_sell = float(seg_vol[below & seg_sell].sum())

        above_delta = above_buy - above_sell
        below_delta = below_buy - below_sell
        net_delta = above_delta - below_delta

        results.append({
            "line_no": line_no,
            "above_buy": above_buy, "above_sell": above_sell,
            "below_buy": below_buy, "below_sell": below_sell,
            "above_delta": above_delta, "below_delta": below_delta,
            "net_delta": net_delta,
        })
    return results


def _fmt(v):
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1_000_000:
        return f"{sign}{v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"{sign}{v/1_000:.2f}K"
    return f"{sign}{v:.2f}"


def _delta_color(v):
    return UP if v > 0 else (DN if v < 0 else MUT)


def build_volume_panel(results):
    if not results:
        return dbc.Alert("برای مشاهده تحلیل حجم، یک ترندلاین روی چارت رسم کنید (از ابزار ✏️ در نوار بالای چارت).",
                          color="secondary", style={"fontSize": 13})
    cards = []
    for r in results:
        cards.append(
            dbc.Card(dbc.CardBody([
                html.Div(f"📏 ترندلاین #{r['line_no']}", style={"color": GOLD, "fontWeight": "bold", "marginBottom": 8}),
                dbc.Row([
                    dbc.Col([
                        html.Div("بالای خط", style={"color": MUT, "fontSize": 12, "marginBottom": 4}),
                        html.Div(f"🟢 خرید: {_fmt(r['above_buy'])}", style={"color": UP, "fontSize": 13}),
                        html.Div(f"🔴 فروش: {_fmt(r['above_sell'])}", style={"color": DN, "fontSize": 13}),
                        html.Div(f"Δ دلتا: {_fmt(r['above_delta'])}",
                                 style={"color": _delta_color(r['above_delta']), "fontSize": 13, "fontWeight": "bold", "marginTop": 4}),
                    ], width=6),
                    dbc.Col([
                        html.Div("پایین خط", style={"color": MUT, "fontSize": 12, "marginBottom": 4}),
                        html.Div(f"🟢 خرید: {_fmt(r['below_buy'])}", style={"color": UP, "fontSize": 13}),
                        html.Div(f"🔴 فروش: {_fmt(r['below_sell'])}", style={"color": DN, "fontSize": 13}),
                        html.Div(f"Δ دلتا: {_fmt(r['below_delta'])}",
                                 style={"color": _delta_color(r['below_delta']), "fontSize": 13, "fontWeight": "bold", "marginTop": 4}),
                    ], width=6),
                ]),
                html.Hr(style={"borderColor": LINE, "margin": "8px 0"}),
                html.Div([
                    html.Span("دلتای حاصل (بالا − پایین): ", style={"color": MUT, "fontSize": 12}),
                    html.Span(_fmt(r['net_delta']),
                              style={"color": _delta_color(r['net_delta']), "fontSize": 14, "fontWeight": "bold"}),
                ]),
            ]), style={"background": CARD, "border": f"1px solid {LINE}", "marginBottom": 10})
        )
    return html.Div(cards)


# ==============================================================================
# 3) دیتابیس SQLite برای سیگنال‌های نهنگ
# ==============================================================================
_DB_LOCK = threading.Lock()


def db_init():
    with _DB_LOCK:
        con = sqlite3.connect(DB_PATH)
        con.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id TEXT PRIMARY KEY,
                ts_open TEXT,
                symbol TEXT,
                category TEXT,
                side TEXT,
                entry REAL,
                sl REAL,
                tp REAL,
                leverage REAL,
                qty REAL,
                notional REAL,
                capital REAL,
                risk_usd REAL,
                buy_usd REAL,
                sell_usd REAL,
                whale_count INTEGER,
                entry_confidence REAL,
                final_confidence REAL,
                status TEXT DEFAULT 'OPEN',
                ts_close TEXT,
                close_price REAL,
                pnl_pct REAL
            )
        """)
        # مهاجرت نرم برای دیتابیس‌های قدیمی‌تر که ستون‌های جدید را ندارند
        existing_cols = {row[1] for row in con.execute("PRAGMA table_info(signals)").fetchall()}
        for col, coltype in [("entry_confidence", "REAL"), ("final_confidence", "REAL")]:
            if col not in existing_cols:
                con.execute(f"ALTER TABLE signals ADD COLUMN {col} {coltype}")
        con.commit()
        con.close()


def db_insert_signal(sig):
    with _DB_LOCK:
        con = sqlite3.connect(DB_PATH)
        con.execute("""
            INSERT INTO signals (id, ts_open, symbol, category, side, entry, sl, tp, leverage, qty,
                                  notional, capital, risk_usd, buy_usd, sell_usd, whale_count,
                                  entry_confidence, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'OPEN')
        """, (sig["id"], sig["ts_open"], sig["symbol"], sig["category"], sig["side"], sig["entry"],
              sig["sl"], sig["tp"], sig["leverage"], sig["qty"], sig["notional"], sig["capital"],
              sig["risk_usd"], sig["buy_usd"], sig["sell_usd"], sig["whale_count"], sig.get("confidence")))
        con.commit()
        con.close()


def db_close_signal(sig_id, status, close_price, pnl_pct, final_confidence=None):
    with _DB_LOCK:
        con = sqlite3.connect(DB_PATH)
        con.execute("""
            UPDATE signals SET status=?, ts_close=?, close_price=?, pnl_pct=?, final_confidence=? WHERE id=?
        """, (status, datetime.now(timezone.utc).isoformat(timespec="seconds"), close_price, pnl_pct,
              final_confidence, sig_id))
        con.commit()
        con.close()


def db_cancel_stale_open(sig_id):
    """سیگنال‌های باز اضافی/قدیمی (باقی‌مانده از نسخه‌ی قبلی) را می‌بندد تا فقط یک سیگنال فعال بماند."""
    with _DB_LOCK:
        con = sqlite3.connect(DB_PATH)
        con.execute("""
            UPDATE signals SET status='CANCELLED', ts_close=? WHERE id=?
        """, (datetime.now(timezone.utc).isoformat(timespec="seconds"), sig_id))
        con.commit()
        con.close()


def db_fetch_all():
    with _DB_LOCK:
        con = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM signals ORDER BY ts_open DESC", con)
        con.close()
    return df


def db_fetch_open():
    with _DB_LOCK:
        con = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM signals WHERE status='OPEN'", con)
        con.close()
    return df


db_init()

# ==============================================================================
# 4) پایش تیک‌های نهنگ + موتور سیگنال اسکلپ (WebSocket بایبیت)
# ==============================================================================
WS_CANDIDATES = {
    "linear": ["wss://stream.bybit.com/v5/public/linear", "wss://stream.bytick.com/v5/public/linear"],
    "spot": ["wss://stream.bybit.com/v5/public/spot", "wss://stream.bytick.com/v5/public/spot"],
    "inverse": ["wss://stream.bybit.com/v5/public/inverse", "wss://stream.bytick.com/v5/public/inverse"],
}


class WhaleMonitor:
    """
    یک نخ پس‌زمینه که به استریم Public Trade بایبیت وصل می‌شود و یک تحلیل حجمی چندلایه
    روی تیک‌های نهنگ اجرا می‌کند تا سیگنال اسکلپ صادر کند. لایه‌ها (هر کدام باید تأیید کنند):

      لایه ۱ — تازگی/شتاب:  اگر در کوتاه‌ترین پنجره هیچ تیک نهنگ تازه‌ای نبوده، یعنی دیتا
                            «بیات» است؛ سیستم باید واکنش به لحظه‌ی حال بدهد نه به گذشته.
      لایه ۲ — جذب/تأیید (Absorption vs Confirmation):  عدم‌تعادل خام خرید/فروش به‌تنهایی
                            گمراه‌کننده است. اگر فروش سنگین باشد ولی قیمت نریزد، یعنی خریداران
                            آن را جذب کرده‌اند (سیگنال LONG واقعی، نه SHORT خام). برعکسش هم
                            همین‌طور. این لایه جهت واقعی را از روی رفتار قیمت در برابر حجم
                            استخراج می‌کند، نه فقط از روی رنگ تیک‌ها.
      لایه ۳ — هم‌سویی چند تایم‌فریم:  جهت به‌دست‌آمده باید با پنجره‌ی بلندتر (۳ برابر) هم
                            تناقض نداشته باشد، وگرنه سیگنال رد می‌شود.
      لایه ۴ — فیلتر VWAP:  از ورود به قیمتی که خیلی از میانگین وزنی-حجمی نهنگ‌ها فاصله
                            گرفته (دنبال‌کردن حرکتی که از قبل رخ داده) پرهیز می‌شود.
      لایه ۵ — حد ضرر/سود تطبیقی با نوسان لحظه‌ای (ATR درصدی روی کندل ۱ دقیقه‌ای)، به‌جای
                            درصد ثابت، تا سیستم خودش را با شرایط لحظه‌ای بازار همگام کند.

    entry/SL/TP بعد از صدور هرگز تغییر نمی‌کنند (بدون ریپینت) و تا رسیدن به یکی از آن دو،
    سیگنال جدیدی صادر نمی‌شود. فقط «درجه اطمینان» به‌صورت زنده و شناور به‌روزرسانی می‌شود.
    """

    LONG_WINDOW_MULT = 3.0  # پنجره‌ی تأیید بلندمدت = ۳ برابر پنجره‌ی اصلی

    def __init__(self, symbol, category, whale_usd, window_sec, min_whale_count,
                 imbalance_ratio, cooldown_sec, capital_usd, risk_pct, sl_pct, tp_pct, leverage_cap,
                 short_window_sec=30.0, vwap_max_dev_pct=0.5, atr_mult=0.6):
        self.symbol = symbol.upper()
        self.category = category
        self.whale_usd = float(whale_usd)
        self.window_sec = float(window_sec)
        self.short_window_sec = float(short_window_sec)
        self.long_window_sec = self.window_sec * self.LONG_WINDOW_MULT
        self.min_whale_count = int(min_whale_count)
        self.imbalance_ratio = float(imbalance_ratio)
        self.cooldown_sec = float(cooldown_sec)
        self.capital_usd = float(capital_usd)
        self.risk_pct = float(risk_pct)
        self.sl_pct = float(sl_pct)
        self.tp_pct = float(tp_pct)
        self.leverage_cap = float(leverage_cap)
        self.vwap_max_dev_pct = float(vwap_max_dev_pct)
        self.atr_mult = float(atr_mult)

        self._lock = threading.Lock()
        self._ticks = deque()  # (epoch_seconds, side('Buy'/'Sell'), usd_value, price)
        self._last_price = None
        self._cum_buy = 0
        self._cum_sell = 0
        self._cooldown_until = 0.0
        self._connected = False
        self._stop_flag = False
        self._ws_idx = 0

        self._atr_lock = threading.Lock()
        self._atr_pct = None  # درصد نوسان لحظه‌ای (میانگین (high-low)/close روی کندل ۱ دقیقه)

        # فقط یک سیگنال «فعال» در هر لحظه؛ تا این سیگنال به حد سود یا حد ضرر نخورده،
        # سیگنال جدیدی صادر نمی‌شود (بدون تناقض/بدون ریپینت). درجه اطمینان همین سیگنال
        # هر تیک به‌روزرسانی می‌شود اما entry/SL/TP آن هرگز تغییر نمی‌کند.
        self._active_signal = None

        open_rows = db_fetch_open()
        symbol_rows = open_rows[open_rows["symbol"] == self.symbol] if not open_rows.empty else open_rows
        if not symbol_rows.empty:
            symbol_rows = symbol_rows.sort_values("ts_open")
            # اگر از اجرای قبلی چند سیگنال باز مانده باشد (باگ نسخه‌ی قبل)، فقط آخرین را
            # فعال نگه می‌داریم و بقیه را می‌بندیم تا تناقض ایجاد نشود.
            *stale, latest = symbol_rows.to_dict("records")
            for row in stale:
                db_cancel_stale_open(row["id"])
            self._active_signal = latest
            self._active_signal.setdefault("confidence", latest.get("entry_confidence") or 50.0)

        self._thread = threading.Thread(target=self._run_forever_loop, daemon=True)
        self._thread.start()
        self._atr_thread = threading.Thread(target=self._atr_refresh_loop, daemon=True)
        self._atr_thread.start()

    # -------------------------- WebSocket handling --------------------------
    def _run_forever_loop(self):
        candidates = WS_CANDIDATES.get(self.category, WS_CANDIDATES["linear"])
        while not self._stop_flag:
            url = candidates[self._ws_idx % len(candidates)]
            try:
                ws_app = websocket.WebSocketApp(
                    url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._connected = False
                ws_app.run_forever(ping_interval=20, ping_timeout=10)
            except Exception:
                pass
            self._connected = False
            self._ws_idx += 1
            if not self._stop_flag:
                time.sleep(3)

    def _on_open(self, ws):
        self._connected = True
        sub = {"op": "subscribe", "args": [f"publicTrade.{self.symbol}"]}
        try:
            ws.send(json.dumps(sub))
        except Exception:
            pass

    def _on_error(self, ws, error):
        self._connected = False

    def _on_close(self, ws, close_status_code, close_msg):
        self._connected = False

    # -------------------------- Volatility (ATR%) refresh --------------------------
    def _atr_refresh_loop(self):
        while not self._stop_flag:
            try:
                df = get_klines(self.symbol, "1", self.category, limit=50)
                if not df.empty:
                    atr_pct = float(((df["high"] - df["low"]) / df["close"]).mean() * 100.0)
                    with self._atr_lock:
                        self._atr_pct = atr_pct
            except Exception:
                pass
            for _ in range(300):  # هر ۵ دقیقه، ولی با پاسخ‌گویی سریع به توقف
                if self._stop_flag:
                    break
                time.sleep(1)

    # -------------------------- Tick ingestion & window stats --------------------------
    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
        except Exception:
            return
        trades = data.get("data")
        if not trades or not isinstance(trades, list):
            return
        now = time.time()
        with self._lock:
            for t in trades:
                try:
                    price = float(t["p"])
                    size = float(t["v"])
                    side = t["S"]  # 'Buy' or 'Sell' (taker side)
                except Exception:
                    continue
                self._last_price = price
                usd_val = price * size
                if usd_val >= self.whale_usd:
                    self._ticks.append((now, side, usd_val, price))
                    if side == "Buy":
                        self._cum_buy += 1
                    else:
                        self._cum_sell += 1
            self._cleanup_window(now)

            main_stats = self._window_stats(now, self.window_sec)
            long_stats = self._window_stats(now, self.long_window_sec)
            short_stats = self._window_stats(now, self.short_window_sec)

            if self._active_signal is not None:
                # تا وقتی سیگنال فعلی به TP یا SL نخورده، هیچ سیگنال جدیدی صادر نمی‌شود؛
                # فقط درجه اطمینانِ همین سیگنال به‌صورت زنده و بر مبنای همان لایه‌های
                # تحلیل حجمی به‌روزرسانی می‌شود.
                self._active_signal["confidence"] = self._compute_active_confidence(
                    self._active_signal, main_stats, long_stats, self._last_price)
                self._check_active_hit(self._last_price)
            else:
                self._check_signal(now, main_stats, long_stats, short_stats)

    def _cleanup_window(self, now):
        cutoff = now - self.long_window_sec
        while self._ticks and self._ticks[0][0] < cutoff:
            self._ticks.popleft()

    def _window_stats(self, now, window_sec):
        cutoff = now - window_sec
        buy_usd = sell_usd = 0.0
        count = 0
        price_start = None
        vwap_num = 0.0
        for ts, side, usd, price in self._ticks:
            if ts < cutoff:
                continue
            count += 1
            if price_start is None:
                price_start = price
            vwap_num += price * usd
            if side == "Buy":
                buy_usd += usd
            else:
                sell_usd += usd
        total = buy_usd + sell_usd
        return {
            "count": count,
            "buy_usd": buy_usd,
            "sell_usd": sell_usd,
            "total": total,
            "buy_ratio": (buy_usd / total) if total > 0 else 0.5,
            "price_start": price_start,
            "vwap": (vwap_num / total) if total > 0 else None,
        }

    @staticmethod
    def _clamp(v, lo=0.0, hi=100.0):
        return max(lo, min(hi, v))

    # -------------------------- Confidence models --------------------------
    def _compute_active_confidence(self, sig, main_stats, long_stats, price):
        """درجه اطمینان شناور سیگنال فعال؛ فقط نمایشی است و روی entry/SL/TP اثر نمی‌گذارد.
        سه جزء دارد: قدرت فعلی جریان نهنگ در پنجره‌ی اصلی، هم‌سویی پنجره‌ی بلندمدت، و
        پیشرفت واقعی قیمت به سمت حد سود/ضرر."""
        side = sig["side"]
        dir_ratio = main_stats["buy_ratio"] if side == "LONG" else (1 - main_stats["buy_ratio"])
        flow_conf = self._clamp((dir_ratio - 0.5) / 0.5 * 100.0)

        if long_stats["count"] >= self.min_whale_count:
            long_dir_ratio = long_stats["buy_ratio"] if side == "LONG" else (1 - long_stats["buy_ratio"])
            confluence_conf = self._clamp((long_dir_ratio - 0.5) / 0.5 * 100.0)
        else:
            confluence_conf = 50.0

        if price is None:
            price_conf = 50.0
        else:
            entry, tp, sl = sig["entry"], sig["tp"], sig["sl"]
            move = (price - entry) if side == "LONG" else (entry - price)
            if move >= 0:
                dist = abs(tp - entry)
                price_conf = 50.0 + 50.0 * (move / dist) if dist > 0 else 50.0
            else:
                dist = abs(entry - sl)
                price_conf = 50.0 + 50.0 * (move / dist) if dist > 0 else 50.0
            price_conf = self._clamp(price_conf)

        return round(0.40 * flow_conf + 0.25 * confluence_conf + 0.35 * price_conf, 1)

    # -------------------------- Signal engine (deep volume analysis) --------------------------
    def _check_signal(self, now, main_stats, long_stats, short_stats):
        if now < self._cooldown_until:
            return
        if main_stats["count"] < self.min_whale_count or main_stats["total"] <= 0:
            return
        if self._last_price is None or main_stats["price_start"] is None:
            return

        # لایه ۱ — تازگی: بدون تیک نهنگ تازه در کوتاه‌ترین پنجره، سیگنال بر پایه‌ی دیتای
        # بیات صادر نمی‌شود (سیستم باید به «لحظه‌ی حال» واکنش دهد).
        if short_stats["count"] < 1:
            return

        price = self._last_price
        price_change_pct = (price - main_stats["price_start"]) / main_stats["price_start"] * 100.0
        volume_score = (main_stats["buy_ratio"] - 0.5) * 200.0  # -100..100
        base_threshold = (self.imbalance_ratio - 0.5) * 200.0
        if abs(volume_score) < base_threshold:
            return

        # لایه ۲ — جذب در برابر تأیید: جهت واقعی از تطبیق «جریان حجم» با «واکنش قیمت» می‌آید
        eps = 0.02  # درصد؛ باند خنثی دور صفر برای رفتار قیمت
        if volume_score < 0:
            if price_change_pct >= -eps:
                bias, regime = "LONG", "ABSORPTION"   # فروش سنگین ولی قیمت نریخته -> جذب خریدار
            else:
                bias, regime = "SHORT", "CONFIRMED"   # فروش سنگین و قیمت هم افت کرده -> تأیید نزولی
        else:
            if price_change_pct <= eps:
                bias, regime = "SHORT", "ABSORPTION"  # خرید سنگین ولی قیمت بالا نرفته -> جذب فروشنده
            else:
                bias, regime = "LONG", "CONFIRMED"    # خرید سنگین و قیمت هم بالا رفته -> تأیید صعودی

        # لایه ۳ — هم‌سویی چند تایم‌فریم: اگر پنجره‌ی بلندمدت داده‌ی کافی دارد و در جهت
        # مخالف است، سیگنال به‌خاطر تناقض بین تایم‌فریم‌ها رد می‌شود.
        if long_stats["count"] >= self.min_whale_count:
            long_bias = "LONG" if (long_stats["buy_ratio"] - 0.5) >= 0 else "SHORT"
            if long_bias != bias:
                return

        # لایه ۴ — فیلتر VWAP: پرهیز از ورود به قیمتی که خیلی از میانگین وزنی-حجمی نهنگ‌ها فاصله دارد
        vwap = main_stats.get("vwap")
        dev_pct = 0.0
        if vwap:
            dev_pct = (price - vwap) / vwap * 100.0
            if bias == "LONG" and dev_pct > self.vwap_max_dev_pct:
                return
            if bias == "SHORT" and -dev_pct > self.vwap_max_dev_pct:
                return

        side = bias
        entry = price

        # لایه ۵ — حد ضرر/سود تطبیقی با نوسان لحظه‌ای (ATR٪)؛ نسبت ریسک‌به‌ریوارد کاربر حفظ می‌شود
        with self._atr_lock:
            atr_pct = self._atr_pct
        base_sl = self.sl_pct
        eff_sl_pct = max(base_sl, atr_pct * self.atr_mult) if atr_pct else base_sl
        scale = (eff_sl_pct / base_sl) if base_sl > 0 else 1.0
        eff_tp_pct = self.tp_pct * scale

        if side == "LONG":
            sl = entry * (1 - eff_sl_pct / 100.0)
            tp = entry * (1 + eff_tp_pct / 100.0)
        else:
            sl = entry * (1 + eff_sl_pct / 100.0)
            tp = entry * (1 - eff_tp_pct / 100.0)

        risk_usd = self.capital_usd * (self.risk_pct / 100.0)
        sl_distance_pct = eff_sl_pct / 100.0
        raw_notional = risk_usd / sl_distance_pct if sl_distance_pct > 0 else 0
        raw_leverage = raw_notional / self.capital_usd if self.capital_usd > 0 else 0
        leverage = round(min(max(raw_leverage, 1.0), self.leverage_cap), 1)
        notional = leverage * self.capital_usd
        qty = notional / entry if entry > 0 else 0

        # درجه اطمینان لحظه‌ی صدور: ترکیب قدرت جریان، شتاب تیک‌های تازه، و کیفیت ساختاری (VWAP)
        rate_short = short_stats["count"] / self.short_window_sec if self.short_window_sec > 0 else 0
        rate_main = main_stats["count"] / self.window_sec if self.window_sec > 0 else 0
        accel_ratio = (rate_short / rate_main) if rate_main > 0 else 1.0

        flow_strength = self._clamp(abs(volume_score))
        accel_strength = self._clamp(accel_ratio * 50.0)
        vwap_strength = 100.0
        if vwap:
            band = max(self.vwap_max_dev_pct, 0.01)
            vwap_strength = self._clamp(100.0 - (abs(dev_pct) / band) * 100.0)
        regime_bonus = 8.0 if regime == "ABSORPTION" else 0.0
        entry_confidence = round(self._clamp(
            0.5 * flow_strength + 0.3 * accel_strength + 0.2 * vwap_strength + regime_bonus
        ), 1)

        sig = {
            "id": str(uuid.uuid4())[:8],
            "ts_open": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "symbol": self.symbol,
            "category": self.category,
            "side": side,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "leverage": leverage,
            "qty": qty,
            "notional": notional,
            "capital": self.capital_usd,
            "risk_usd": risk_usd,
            "buy_usd": main_stats["buy_usd"],
            "sell_usd": main_stats["sell_usd"],
            "whale_count": main_stats["count"],
            "regime": regime,
            "confidence": entry_confidence,
        }
        db_insert_signal(sig)
        self._active_signal = sig
        # سیگنال بعدی فقط پس از بسته‌شدن این یکی و طی‌شدن دوره‌ی خنک‌سازی صادر می‌شود
        self._cooldown_until = 0.0

    def _check_active_hit(self, price):
        sig = self._active_signal
        if price is None or sig is None:
            return
        side = sig["side"]
        entry, sl, tp, leverage = sig["entry"], sig["sl"], sig["tp"], sig["leverage"]
        hit = None
        if side == "LONG":
            if price <= sl:
                hit = "LOSS"
            elif price >= tp:
                hit = "WIN"
        else:
            if price >= sl:
                hit = "LOSS"
            elif price <= tp:
                hit = "WIN"
        if hit:
            raw_move = (price - entry) / entry if side == "LONG" else (entry - price) / entry
            pnl_pct = raw_move * 100.0 * leverage
            final_conf = sig.get("confidence")
            db_close_signal(sig["id"], hit, price, pnl_pct, final_confidence=final_conf)
            self._active_signal = None
            # پس از بسته‌شدن سیگنال، یک دوره‌ی خنک‌سازی کوتاه قبل از امکان صدور سیگنال بعدی
            self._cooldown_until = time.time() + self.cooldown_sec

    # -------------------------- Public state for UI --------------------------
    def get_state(self):
        with self._lock:
            now = time.time()
            main_stats = self._window_stats(now, self.window_sec)
            with self._atr_lock:
                atr_pct = self._atr_pct
            return {
                "connected": self._connected,
                "last_price": self._last_price,
                "window_buy_count": sum(1 for ts, s, _, _ in self._ticks if s == "Buy" and ts >= now - self.window_sec),
                "window_sell_count": sum(1 for ts, s, _, _ in self._ticks if s == "Sell" and ts >= now - self.window_sec),
                "window_buy_usd": main_stats["buy_usd"],
                "window_sell_usd": main_stats["sell_usd"],
                "cum_buy_count": self._cum_buy,
                "cum_sell_count": self._cum_sell,
                "cooldown_remaining": max(0, int(self._cooldown_until - time.time())),
                "active_signal": dict(self._active_signal) if self._active_signal else None,
                "atr_pct": atr_pct,
            }

    def stop(self):
        self._stop_flag = True


_MONITOR_HOLDER = {"monitor": None}
_MONITOR_LOCK = threading.Lock()


def start_monitor(**kwargs):
    with _MONITOR_LOCK:
        old = _MONITOR_HOLDER["monitor"]
        if old is not None:
            old.stop()
        mon = WhaleMonitor(**kwargs)
        _MONITOR_HOLDER["monitor"] = mon
        return mon


def get_monitor():
    with _MONITOR_LOCK:
        return _MONITOR_HOLDER["monitor"]


# ==============================================================================
# 5) اپ Dash
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])
app.title = "Bybit Whale Scalper"
server = app.server

CATEGORY_OPTS = [{"label": v, "value": v} for v in ["linear", "spot", "inverse"]]
INTERVAL_OPTS = [{"label": lbl, "value": val} for lbl, val in [
    ("1m", "1"), ("3m", "3"), ("5m", "5"), ("15m", "15"),
    ("30m", "30"), ("1h", "60"), ("4h", "240"), ("1D", "D"),
]]

# --- Tab 1: Trendline layout ---
tab1_content = html.Div([
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([html.Label("نماد:", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="symbol-input", value=DEFAULT_SYMBOL, type="text",
                           style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
        dbc.Col([html.Label("بازار:", style={"fontSize": 12, "color": MUT}),
                 dcc.Dropdown(id="category-dropdown", value=DEFAULT_CATEGORY, clearable=False, options=CATEGORY_OPTS)], md=2),
        dbc.Col([html.Label("تایم‌فریم:", style={"fontSize": 12, "color": MUT}),
                 dcc.Dropdown(id="interval-dropdown", value=DEFAULT_INTERVAL, clearable=False, options=INTERVAL_OPTS)], md=2),
        dbc.Col(dbc.Button("🔄 بروزرسانی", id="refresh-btn", color="warning", className="mt-3",
                           style={"fontWeight": "bold", "color": "#0b1220", "width": "100%"}), md=2),
        dbc.Col(dbc.Button("🗑 حذف همه ترندلاین‌ها", id="clear-btn", color="danger", className="mt-3",
                           style={"fontWeight": "bold", "width": "100%"}), md=2),
        dbc.Col(html.Div(id="conn-status", style={"color": MUT, "fontSize": 11, "marginTop": 22, "textAlign": "center"}), md=2),
    ])), style={"maxWidth": 1200, "margin": "10px auto"}),

    dbc.Row([
        dbc.Col(dcc.Graph(id="candle-chart", style={"height": "70vh"},
                          config={"modeBarButtonsToAdd": ["drawline", "eraseshape"],
                                  "displaylogo": False}), width=8),
        dbc.Col([
            html.H5("📊 حجم خرید/فروش بالا و پایین ترندلاین‌ها", style={"color": GOLD, "fontSize": 14, "margin": "8px 0"}),
            html.Div(id="volume-panel"),
        ], width=4),
    ], style={"maxWidth": 1200, "margin": "0 auto"}),

    dcc.Store(id="shapes-store", data=[]),
])

# --- Tab 2: Whale scalper layout ---
whale_controls = dbc.Card(dbc.CardBody([
    dbc.Row([
        dbc.Col([html.Label("نماد:", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="w-symbol", value=DEFAULT_SYMBOL, type="text",
                           style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
        dbc.Col([html.Label("بازار:", style={"fontSize": 12, "color": MUT}),
                 dcc.Dropdown(id="w-category", value=DEFAULT_CATEGORY, clearable=False, options=CATEGORY_OPTS)], md=2),
        dbc.Col([html.Label("آستانه نهنگ ($):", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="w-whale-usd", value=50000, type="number", min=100,
                           style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
        dbc.Col([html.Label("پنجره (ثانیه):", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="w-window", value=180, type="number", min=10,
                           style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
        dbc.Col([html.Label("حداقل تیک نهنگ:", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="w-min-count", value=5, type="number", min=1,
                           style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
        dbc.Col([html.Label("نسبت عدم‌تعادل:", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="w-imbalance", value=0.65, type="number", min=0.5, max=0.95, step=0.01,
                           style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
    ], className="mb-2"),
    dbc.Row([
        dbc.Col([html.Label("خنک‌سازی بین سیگنال (ثانیه):", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="w-cooldown", value=60, type="number", min=5,
                           style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
        dbc.Col([html.Label("سرمایه ($):", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="w-capital", value=100, type="number", min=1,
                           style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
        dbc.Col([html.Label("ریسک هر ترید (٪ سرمایه):", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="w-risk", value=2, type="number", min=0.1, max=20, step=0.1,
                           style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
        dbc.Col([html.Label("حد ضرر (٪):", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="w-sl", value=0.4, type="number", min=0.05, step=0.05,
                           style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
        dbc.Col([html.Label("حد سود (٪):", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="w-tp", value=0.8, type="number", min=0.05, step=0.05,
                           style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
        dbc.Col([html.Label("سقف لوریج:", style={"fontSize": 12, "color": MUT}),
                 dcc.Input(id="w-lev-cap", value=20, type="number", min=1, max=100,
                           style={"width": "100%", "padding": 6, "borderRadius": 6})], md=2),
    ], className="mb-2"),
    dbc.Row([
        dbc.Col(dbc.Button("▶️ شروع پایش نهنگ‌ها", id="w-start-btn", color="success",
                           style={"fontWeight": "bold", "width": "100%"}), md=3),
        dbc.Col(dbc.Button("⏸ توقف پایش", id="w-stop-btn", color="secondary",
                           style={"fontWeight": "bold", "width": "100%"}), md=3),
        dbc.Col(html.Div(id="w-conn-status", style={"color": MUT, "fontSize": 12, "marginTop": 8, "textAlign": "center"}), md=3),
        dbc.Col(html.Div(id="w-cooldown-status", style={"color": MUT, "fontSize": 12, "marginTop": 8, "textAlign": "center"}), md=3),
    ]),
]), style={"background": CARD, "border": f"1px solid {LINE}", "marginBottom": 10})

whale_stats_card = dbc.Card(dbc.CardBody([
    html.Div("🐋 شمارش تیک‌های نهنگ (پنجره‌ی فعلی)", style={"color": GOLD, "fontWeight": "bold", "marginBottom": 8}),
    dbc.Row([
        dbc.Col([
            html.Div("خرید نهنگ", style={"color": MUT, "fontSize": 12}),
            html.Div(id="w-buy-count", children="0", style={"color": UP, "fontSize": 22, "fontWeight": "bold"}),
            html.Div(id="w-buy-usd", children="$0", style={"color": UP, "fontSize": 12}),
        ], width=4),
        dbc.Col([
            html.Div("فروش نهنگ", style={"color": MUT, "fontSize": 12}),
            html.Div(id="w-sell-count", children="0", style={"color": DN, "fontSize": 22, "fontWeight": "bold"}),
            html.Div(id="w-sell-usd", children="$0", style={"color": DN, "fontSize": 12}),
        ], width=4),
        dbc.Col([
            html.Div("قیمت لحظه‌ای", style={"color": MUT, "fontSize": 12}),
            html.Div(id="w-last-price", children="—", style={"color": TXT, "fontSize": 22, "fontWeight": "bold"}),
        ], width=4),
    ]),
    html.Hr(style={"borderColor": LINE, "margin": "8px 0"}),
    html.Div(id="w-cum-counts", style={"color": MUT, "fontSize": 12}),
]), style={"background": CARD, "border": f"1px solid {LINE}", "marginBottom": 10})

whale_signal_card = html.Div(id="w-signal-card")

win_rate_card = dbc.Card(dbc.CardBody([
    html.Div("🎯 وین‌ریت تا کنون", style={"color": GOLD, "fontWeight": "bold", "marginBottom": 8}),
    html.Div(id="w-winrate", style={"fontSize": 22, "fontWeight": "bold"}),
    html.Div(id="w-winrate-sub", style={"color": MUT, "fontSize": 12, "marginTop": 4}),
]), style={"background": CARD, "border": f"1px solid {LINE}", "marginBottom": 10})

signals_table = dash_table.DataTable(
    id="w-signals-table",
    columns=[
        {"name": "زمان ورود", "id": "ts_open"},
        {"name": "نماد", "id": "symbol"},
        {"name": "جهت", "id": "side"},
        {"name": "ورود", "id": "entry"},
        {"name": "حدضرر", "id": "sl"},
        {"name": "حدسود", "id": "tp"},
        {"name": "لوریج", "id": "leverage"},
        {"name": "حجم", "id": "qty"},
        {"name": "وضعیت", "id": "status"},
        {"name": "بسته‌شدن", "id": "ts_close"},
        {"name": "قیمت بسته", "id": "close_price"},
        {"name": "سود/ضرر٪", "id": "pnl_pct"},
        {"name": "اطمینان ورود", "id": "entry_confidence"},
        {"name": "اطمینان نهایی", "id": "final_confidence"},
    ],
    data=[],
    page_size=12,
    style_table={"overflowX": "auto"},
    style_header={"backgroundColor": CARD, "color": GOLD, "fontWeight": "bold", "border": f"1px solid {LINE}"},
    style_cell={"backgroundColor": BG, "color": TXT, "border": f"1px solid {LINE}", "fontSize": 12, "textAlign": "center"},
    style_data_conditional=[
        {"if": {"filter_query": "{status} = WIN"}, "color": UP},
        {"if": {"filter_query": "{status} = LOSS"}, "color": DN},
        {"if": {"filter_query": "{status} = OPEN"}, "color": GOLD},
        {"if": {"filter_query": "{status} = CANCELLED"}, "color": MUT},
        {"if": {"filter_query": "{side} = LONG"}, "backgroundColor": "#0e1f1a"},
        {"if": {"filter_query": "{side} = SHORT"}, "backgroundColor": "#2a1414"},
    ],
)

tab2_content = html.Div([
    whale_controls,
    dbc.Alert(
        "⚠️ این ابزار مشاوره‌ی مالی نیست. سیگنال‌ها بر اساس عدم‌تعادل حجمی معاملات بزرگ (پروکسی نهنگ) "
        "صادر می‌شوند و تضمینی برای سود نیستند. همیشه با حد ضرر معامله کنید و لوریج پیشنهادی را متناسب "
        "با ریسک‌پذیری خودتان تنظیم کنید.",
        color="warning", style={"fontSize": 12},
    ),
    dbc.Row([
        dbc.Col([whale_stats_card, whale_signal_card], width=5),
        dbc.Col([win_rate_card, dbc.Card(dbc.CardBody([
            html.Div("📋 تاریخچه سیگنال‌ها", style={"color": GOLD, "fontWeight": "bold", "marginBottom": 8}),
            signals_table,
        ]), style={"background": CARD, "border": f"1px solid {LINE}"})], width=7),
    ]),
    dcc.Store(id="w-config-store", data=None),
])

app.layout = html.Div([
    dcc.Tabs(id="main-tabs", value="tab-1", children=[
        dcc.Tab(label="📈 تحلیل حجم ترندلاین", value="tab-1", children=[tab1_content],
                style={"backgroundColor": CARD, "color": MUT}, selected_style={"backgroundColor": BG, "color": GOLD}),
        dcc.Tab(label="🐋 سیگنال اسکلپ نهنگ", value="tab-2", children=[tab2_content],
                style={"backgroundColor": CARD, "color": MUT}, selected_style={"backgroundColor": BG, "color": GOLD}),
    ]),
    dcc.Interval(id="refresh-interval", interval=15_000, n_intervals=0),   # تب ۱: کندل هر ۱۵ ثانیه
    dcc.Interval(id="w-interval", interval=2_000, n_intervals=0),          # تب ۲: پایش نهنگ هر ۲ ثانیه
], style={"background": BG, "minHeight": "100vh", "padding": "10px"})


# ==============================================================================
# 6) کال‌بک تب ۱: چارت کندل + ترندلاین (بدون تغییر منطقی)
# ==============================================================================
@app.callback(
    Output("candle-chart", "figure"),
    Output("shapes-store", "data"),
    Output("volume-panel", "children"),
    Output("conn-status", "children"),
    Input("refresh-interval", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    Input("clear-btn", "n_clicks"),
    Input("candle-chart", "relayoutData"),
    State("symbol-input", "value"),
    State("interval-dropdown", "value"),
    State("category-dropdown", "value"),
    State("shapes-store", "data"),
)
def update_chart(n_int, n_refresh, n_clear, relayout, symbol, interval, category, stored_shapes):
    stored_shapes = list(stored_shapes or [])
    trigger = ctx.triggered_id

    if trigger == "clear-btn":
        stored_shapes = []
    elif trigger == "candle-chart" and relayout:
        if "shapes" in relayout:
            stored_shapes = relayout["shapes"]
        else:
            for key, val in relayout.items():
                if key.startswith("shapes[") and "." in key:
                    try:
                        idx = int(key.split("[")[1].split("]")[0])
                        field = key.split(".", 1)[1]
                        if idx < len(stored_shapes):
                            stored_shapes[idx][field] = val
                    except Exception:
                        pass

    symbol = (symbol or DEFAULT_SYMBOL).upper()
    category = category or DEFAULT_CATEGORY
    interval = interval or DEFAULT_INTERVAL

    df = get_klines(symbol, interval, category, limit=500)

    if df.empty:
        empty_fig = go.Figure(layout=dict(
            paper_bgcolor=BG, plot_bgcolor=CARD,
            annotations=[dict(text="❌ دریافت دیتا از بایبیت ناموفق بود.", x=0.5, y=0.5, showarrow=False,
                               font=dict(color=DN, size=14))]))
        return empty_fig, stored_shapes, dash.no_update, "🔴 قطع"

    fig = go.Figure(data=[go.Candlestick(
        x=df["ts"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color=UP, decreasing_line_color=DN, name=symbol,
    )])
    fig.update_layout(
        shapes=stored_shapes,
        dragmode="drawline",
        newshape=dict(line_color=GOLD, line_width=2),
        template="plotly_dark",
        paper_bgcolor=BG, plot_bgcolor=CARD,
        font=dict(color=TXT),
        xaxis=dict(gridcolor=LINE, rangeslider_visible=False),
        yaxis=dict(gridcolor=LINE),
        margin=dict(l=10, r=10, t=40, b=10),
        title=dict(text=f"{symbol} — {category} — {interval}", x=0.5, font=dict(color=GOLD, size=14)),
    )

    results = analyze_trendlines(df, stored_shapes)
    panel = build_volume_panel(results)
    status = f"🟢 متصل | {pd.Timestamp.now().strftime('%H:%M:%S')}"

    return fig, stored_shapes, panel, status


# ==============================================================================
# 7) کال‌بک تب ۲: شروع/توقف پایش نهنگ
# ==============================================================================
@app.callback(
    Output("w-config-store", "data"),
    Input("w-start-btn", "n_clicks"),
    Input("w-stop-btn", "n_clicks"),
    State("w-symbol", "value"), State("w-category", "value"), State("w-whale-usd", "value"),
    State("w-window", "value"), State("w-min-count", "value"), State("w-imbalance", "value"),
    State("w-cooldown", "value"), State("w-capital", "value"), State("w-risk", "value"),
    State("w-sl", "value"), State("w-tp", "value"), State("w-lev-cap", "value"),
    prevent_initial_call=True,
)
def start_stop_monitor(n_start, n_stop, symbol, category, whale_usd, window, min_count,
                        imbalance, cooldown, capital, risk, sl, tp, lev_cap):
    trigger = ctx.triggered_id
    if trigger == "w-stop-btn":
        mon = get_monitor()
        if mon:
            mon.stop()
        return {"running": False, "symbol": symbol}

    mon = start_monitor(
        symbol=(symbol or DEFAULT_SYMBOL).upper(), category=category or DEFAULT_CATEGORY,
        whale_usd=whale_usd or 50000, window_sec=window or 180, min_whale_count=min_count or 5,
        imbalance_ratio=imbalance or 0.65, cooldown_sec=cooldown or 60, capital_usd=capital or 100,
        risk_pct=risk or 2, sl_pct=sl or 0.4, tp_pct=tp or 0.8, leverage_cap=lev_cap or 20,
    )
    return {"running": True, "symbol": mon.symbol}


def _confidence_color(v):
    if v is None:
        return MUT
    if v >= 66:
        return UP
    if v >= 33:
        return GOLD
    return DN


def _confidence_bar(v):
    v = 0 if v is None else v
    filled = int(round(v / 10))
    bar = "█" * filled + "░" * (10 - filled)
    return bar


def _signal_card(sig, running, symbol):
    if not running:
        return dbc.Alert("پایش متوقف است. برای شروع، «شروع پایش نهنگ‌ها» را بزنید.", color="secondary", style={"fontSize": 13})
    if not sig:
        return dbc.Alert(
            f"در انتظار عدم‌تعادل کافی در تیک‌های نهنگ برای {symbol}... "
            "(سیگنال جدید فقط وقتی صادر می‌شود که سیگنال قبلی نداشته باشیم)",
            color="secondary", style={"fontSize": 13})

    side_color = UP if sig["side"] == "LONG" else DN
    side_fa = "لانگ (خرید) 🟢" if sig["side"] == "LONG" else "شورت (فروش) 🔴"
    conf = sig.get("confidence")
    conf_color = _confidence_color(conf)
    return dbc.Card(dbc.CardBody([
        html.Div(f"⚡ سیگنال قطعی فعال — {sig['symbol']} (تا برخورد به TP/SL تغییر نمی‌کند)",
                  style={"color": GOLD, "fontWeight": "bold", "marginBottom": 6, "fontSize": 12}),
        html.Div(side_fa, style={"color": side_color, "fontSize": 18, "fontWeight": "bold", "marginBottom": 6}),
        html.Div(f"ورود: {sig['entry']:.4f}", style={"fontSize": 13}),
        html.Div(f"حد ضرر: {sig['sl']:.4f}", style={"fontSize": 13, "color": DN}),
        html.Div(f"حد سود: {sig['tp']:.4f}", style={"fontSize": 13, "color": UP}),
        html.Hr(style={"borderColor": LINE, "margin": "8px 0"}),
        html.Div([
            html.Span("درجه اطمینان زنده: ", style={"color": MUT, "fontSize": 12}),
            html.Span(f"{conf:.0f}٪" if conf is not None else "—",
                      style={"color": conf_color, "fontWeight": "bold", "fontSize": 14}),
        ]),
        html.Div(_confidence_bar(conf), style={"color": conf_color, "fontSize": 16, "letterSpacing": 1}),
        html.Div("این عدد فقط شدت فعلی سیگنال را نشان می‌دهد و روی ورود/حدضرر/حدسود اثر نمی‌گذارد.",
                 style={"color": MUT, "fontSize": 10, "marginTop": 2}),
        html.Hr(style={"borderColor": LINE, "margin": "8px 0"}),
        html.Div(f"سرمایه: ${sig['capital']:.0f} | ریسک این ترید: ${sig['risk_usd']:.2f}", style={"fontSize": 12, "color": MUT}),
        html.Div(f"لوریج پیشنهادی: {sig['leverage']}x", style={"fontSize": 14, "fontWeight": "bold", "color": GOLD}),
        html.Div(f"حجم پوزیشن: {sig['qty']:.5f} (نوسیونال ≈ ${sig['notional']:.2f})", style={"fontSize": 13}),
        html.Hr(style={"borderColor": LINE, "margin": "8px 0"}),
        html.Div(f"مبنای صدور: {sig['whale_count']} تیک نهنگ در پنجره | خرید ${_fmt(sig['buy_usd'])} / فروش ${_fmt(sig['sell_usd'])}",
                 style={"fontSize": 11, "color": MUT}),
    ]), style={"background": CARD, "border": f"2px solid {side_color}"})


@app.callback(
    Output("w-buy-count", "children"), Output("w-sell-count", "children"),
    Output("w-buy-usd", "children"), Output("w-sell-usd", "children"),
    Output("w-last-price", "children"), Output("w-cum-counts", "children"),
    Output("w-conn-status", "children"), Output("w-cooldown-status", "children"),
    Output("w-signal-card", "children"),
    Output("w-winrate", "children"), Output("w-winrate-sub", "children"),
    Output("w-signals-table", "data"),
    Input("w-interval", "n_intervals"),
    State("w-config-store", "data"),
)
def refresh_whale_ui(n, config):
    mon = get_monitor()
    running = bool(config and config.get("running")) and mon is not None
    symbol = (config or {}).get("symbol", DEFAULT_SYMBOL)

    if running:
        st = mon.get_state()
        buy_count, sell_count = st["window_buy_count"], st["window_sell_count"]
        buy_usd_s, sell_usd_s = f"${_fmt(st['window_buy_usd'])}", f"${_fmt(st['window_sell_usd'])}"
        price_s = f"{st['last_price']:.4f}" if st["last_price"] else "—"
        cum_s = f"مجموع از شروع پایش — خرید: {st['cum_buy_count']} | فروش: {st['cum_sell_count']}"
        conn_s = "🟢 متصل به بایبیت" if st["connected"] else "🟡 در حال اتصال..."
        if st["active_signal"]:
            cd_s = "🔒 یک سیگنال فعال باز است — تا برخورد به TP/SL، سیگنال جدید صادر نمی‌شود"
        elif st["cooldown_remaining"] > 0:
            cd_s = f"⏳ خنک‌سازی: {st['cooldown_remaining']} ثانیه"
        else:
            cd_s = "✅ آماده صدور سیگنال"
        sig_card = _signal_card(st["active_signal"], running, symbol)
    else:
        buy_count, sell_count, buy_usd_s, sell_usd_s, price_s = 0, 0, "$0", "$0", "—"
        cum_s, conn_s, cd_s = "", "⚪ غیرفعال", ""
        sig_card = _signal_card(None, running, symbol)

    df = db_fetch_all()
    if not df.empty:
        wins = int((df["status"] == "WIN").sum())
        losses = int((df["status"] == "LOSS").sum())
        total_closed = wins + losses
        winrate = (wins / total_closed * 100) if total_closed else 0.0
        winrate_s = f"{winrate:.1f}٪"
        sub_s = f"{wins} برد / {losses} باخت از {total_closed} سیگنال بسته‌شده (کل ثبت‌شده: {len(df)})"

        show = df.copy()
        for col in ["entry", "sl", "tp", "close_price"]:
            show[col] = show[col].apply(lambda v: f"{v:.4f}" if pd.notna(v) else "")
        show["qty"] = show["qty"].apply(lambda v: f"{v:.5f}" if pd.notna(v) else "")
        show["leverage"] = show["leverage"].apply(lambda v: f"{v:g}x" if pd.notna(v) else "")
        show["pnl_pct"] = show["pnl_pct"].apply(lambda v: f"{v:+.2f}٪" if pd.notna(v) else "")
        for col in ["entry_confidence", "final_confidence"]:
            if col in show.columns:
                show[col] = show[col].apply(lambda v: f"{v:.0f}٪" if pd.notna(v) else "")
        table_data = show.to_dict("records")
    else:
        winrate_s, sub_s, table_data = "—", "هنوز سیگنالی صادر نشده", []

    return (str(buy_count), str(sell_count), buy_usd_s, sell_usd_s, price_s, cum_s,
            conn_s, cd_s, sig_card, winrate_s, sub_s, table_data)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8060, use_reloader=False)
