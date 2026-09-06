# -*- coding: utf-8 -*-
"""
Morindok Data Engine
=====================
موتور داده‌ی داشبورد مورین‌داک - دریافت داده از Bybit (REST + WebSocket)

این ماژول مسئول موارد زیر است:
  - دریافت کندل‌های تاریخی (Kline) از REST API بایبیت
  - دریافت آخرین قیمت (Ticker)
  - اتصال به WebSocket عمومی بایبیت و جمع‌آوری معاملات تیک‌به‌تیک (publicTrade)
    تا بتوانیم حجم خرید/فروش واقعی (Taker Buy/Sell) را به تفکیک بشماریم؛
    این داده در REST Kline بایبیت وجود ندارد و فقط از استریم معاملات
    قابل استخراج است.
  - محاسبه‌ی فرمول قدرت خریدار به فروشنده (cfield2) دقیقاً طبق فرمول کاربر:

        cfield2 = round( (Buy_I_Volume/Buy_CountI) / (Sell_I_Volume/Sell_CountI) * 10 ) / 10

    یعنی نسبت میانگین حجم هر معامله‌ی خرید به میانگین حجم هر معامله‌ی فروش.
    cfield2 > 1  => خریداران در هر معامله حجم بزرگتری وارد کرده‌اند => قدرت خرید غالب
    cfield2 < 1  => فروشندگان قدرت غالب دارند

توجه مهم برای توسعه‌دهنده (Morteza):
  Bybit علاوه بر دامنه‌ی اصلی api.bybit.com / stream.bybit.com، یک دامنه‌ی
  آینه‌ی رسمی هم به آدرس api.bytick.com / stream.bytick.com ارائه می‌دهد که
  دقیقاً برای شرایطی طراحی شده که دامنه‌ی اصلی در برخی مسیرهای شبکه در
  دسترس نیست. این ماژول ابتدا bytick را امتحان می‌کند و در صورت شکست،
  به‌صورت خودکار به bybit.com سوییچ می‌کند (و برعکس)، بدون نیاز به تغییر
  دستی کد.

  محیط اجرای من (Claude sandbox) اصلاً دسترسی شبکه به دامنه‌های بایبیت
  ندارد، بنابراین این کد در این محیط تست زنده نشده؛ اما دقیقاً بر اساس
  مستندات رسمی Bybit v5 API نوشته شده. حتماً روی سیستم خودت اجرا کن و
  خروجی پرینت "دامنه فعال: ..." را در کنسول چک کن.
"""

import json
import threading
import time
from collections import deque, defaultdict
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter, Retry
import websocket  # pip install websocket-client
import numpy as np
import pandas as pd

# دامنه‌های REST به ترتیب اولویت. اولین دامنه‌ای که پاسخ سالم بدهد، به عنوان
# دامنه‌ی فعال ذخیره و برای درخواست‌های بعدی استفاده می‌شود؛ اگر در طول اجرا
# دامنه‌ی فعال قطع شود، خودکار به دامنه‌ی بعدی سوییچ می‌شود.
REST_HOSTS = ["https://api.bytick.com", "https://api.bybit.com"]
WS_HOSTS = ["wss://stream.bytick.com/v5/public/linear", "wss://stream.bybit.com/v5/public/linear"]

CATEGORY = "linear"          # بازار فیوچرز USDT-Perp
REQUEST_TIMEOUT = 10

# هدرهای واقعی مرورگر برای جلوگیری از بلاک شدن توسط WAF/CDN روی درخواست‌های
# بدون User-Agent (که خیلی از فایروال‌ها/CDNها آن‌ها را مشکوک تلقی می‌کنند)
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

# تایم‌فریم‌های مدنظر کاربر به همراه طول هر کندل به دقیقه
TIMEFRAMES = [
    ("1",   "1 دقیقه",  1),
    ("5",   "5 دقیقه",  5),
    ("15",  "15 دقیقه", 15),
    ("30",  "30 دقیقه", 30),
    ("60",  "1 ساعته",  60),
    ("240", "4 ساعته",  240),
    ("D",   "روزانه",   1440),
]
# وزن هر تایم‌فریم در نمره‌ی ترکیبی؛ تایم‌فریم بالاتر تاثیر بیشتری روی
# تایم‌فریم‌های پایین‌تر دارد (کاسکید از بالا به پایین)
TF_WEIGHT = {"1": 1.0, "5": 1.5, "15": 2.0, "30": 3.0, "60": 4.0, "240": 5.0, "D": 6.0}

# ۳۰ ارز معتبر برای آنالیز چرخش سرمایه
TOP_30 = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT",
    "AVAXUSDT", "TRXUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT", "LTCUSDT", "BCHUSDT",
    "NEARUSDT", "UNIUSDT", "ATOMUSDT", "ETCUSDT", "XLMUSDT", "APTUSDT", "FILUSDT",
    "ARBUSDT", "OPUSDT", "SUIUSDT", "INJUSDT", "TIAUSDT", "RNDRUSDT", "STXUSDT",
    "IMXUSDT", "AAVEUSDT",
]

_session = requests.Session()
_session.headers.update(_HEADERS)
_retry = Retry(
    total=3, backoff_factor=0.6,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
_session.mount("https://", HTTPAdapter(max_retries=_retry))

# اندیس دامنه‌ی فعال REST؛ به‌صورت پویا بر اساس موفق/ناموفق بودن درخواست‌ها
# جابه‌جا می‌شود (خودِ برنامه یاد می‌گیرد کدام دامنه از مسیر شبکه‌ی کاربر
# در دسترس است، بدون نیاز به دخالت دستی).
_active_rest_idx = 0
_active_ws_idx = 0
_host_lock = threading.Lock()


def _get(path: str, params: dict) -> dict | None:
    """
    درخواست GET با تلاش روی همه‌ی دامنه‌های REST_HOSTS به ترتیب، شروع از
    دامنه‌ی فعال فعلی. اگر یک دامنه خطا داد (فیلتر/بلاک/تایم‌اوت)، بلافاصله
    دامنه‌ی بعدی امتحان می‌شود و در صورت موفقیت، همان به‌عنوان دامنه‌ی فعال
    برای درخواست‌های بعدی ذخیره می‌شود.
    """
    global _active_rest_idx
    n = len(REST_HOSTS)
    last_exc = None
    for offset in range(n):
        idx = (_active_rest_idx + offset) % n
        host = REST_HOSTS[idx]
        try:
            r = _session.get(f"{host}{path}", params=params, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            # بایبیت حتی روی خطاهای منطقی (نماد نامعتبر و ...) کد retCode می‌دهد
            if data.get("retCode") not in (0, None):
                last_exc = RuntimeError(f"retCode={data.get('retCode')} retMsg={data.get('retMsg')}")
                continue
            with _host_lock:
                _active_rest_idx = idx
            return data
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            continue
    print(f"[bybit_engine] هیچ‌کدام از دامنه‌های REST پاسخ ندادند ({path}): {last_exc}")
    return None


def active_rest_host() -> str:
    return REST_HOSTS[_active_rest_idx]


def active_ws_host() -> str:
    return WS_HOSTS[_active_ws_idx]


# ----------------------------------------------------------------------------
# REST layer
# ----------------------------------------------------------------------------
def get_klines(symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
    """دریافت کندل‌های تاریخی از Bybit v5 REST API (با fallback خودکار دامنه)"""
    params = {"category": CATEGORY, "symbol": symbol, "interval": interval, "limit": limit}
    data = _get("/v5/market/kline", params)
    rows = (data or {}).get("result", {}).get("list", [])

    cols = ["start", "open", "high", "low", "close", "volume", "turnover"]
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        return df
    for c in cols:
        df[c] = pd.to_numeric(df[c])
    df["time"] = pd.to_datetime(df["start"], unit="ms", utc=True)
    df = df.sort_values("time").reset_index(drop=True)
    return df


def get_ticker(symbol: str) -> dict:
    """آخرین قیمت و اطلاعات لحظه‌ای نماد (با fallback خودکار دامنه)"""
    params = {"category": CATEGORY, "symbol": symbol}
    data = _get("/v5/market/tickers", params)
    lst = (data or {}).get("result", {}).get("list", [])
    return lst[0] if lst else {}


def get_last_price(symbol: str) -> float:
    t = get_ticker(symbol)
    try:
        return float(t.get("lastPrice", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    """ATR ساده برای تعیین حد ضرر/سود و اهرم پیشنهادی"""
    if df.empty or len(df) < period + 1:
        return 0.0
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]
    return float(atr) if not np.isnan(atr) else 0.0


def diagnose_connectivity(symbol: str = "BTCUSDT") -> None:
    """
    تست سریع اتصال به هر دو دامنه‌ی REST هنگام استارت برنامه و چاپ نتیجه
    در کنسول، تا مشکل شبکه (فیلتر/بلاک/DNS) سریع قابل تشخیص باشد.
    """
    print("=" * 60)
    print("[bybit_engine] در حال تست اتصال به دامنه‌های Bybit ...")
    for host in REST_HOSTS:
        try:
            r = _session.get(f"{host}/v5/market/time", timeout=6)
            ok = r.status_code == 200
            print(f"  {'✅' if ok else '❌'} {host}  ->  status={r.status_code}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ❌ {host}  ->  خطا: {exc}")
    print(f"[bybit_engine] دامنه‌ی فعال انتخاب‌شده برای شروع: {active_rest_host()}")
    print("=" * 60)


# ----------------------------------------------------------------------------
# WebSocket trade-stream layer  (برای استخراج حجم خرید/فروش واقعی تیک‌به‌تیک)
# ----------------------------------------------------------------------------
class TradeStreamManager:
    """
    مدیریت اتصال‌های وب‌سوکت عمومی بایبیت برای دریافت معاملات لحظه‌ای
    (publicTrade) و نگهداری بافر معاملات هر نماد در حافظه.

    چون Bybit REST Kline حجم خرید/فروش را به تفکیک نمی‌دهد، تنها راه
    دقیق محاسبه‌ی cfield2 استفاده از استریم معاملات زنده و انباشت آن
    در طول زمان اجرای برنامه است. هرچه برنامه بیشتر اجرا بماند، عمق
    تاریخچه‌ی دقیق قدرت خریدار/فروشنده بیشتر می‌شود.
    """

    MAX_TRADES_PER_SYMBOL = 60000   # ظرفیت بافر هر نماد (~چند روز دیتای پرحجم)
    SYMBOLS_PER_SOCKET = 10          # هر اتصال حداکثر روی چند نماد ساب می‌شود

    def __init__(self, symbols):
        self.symbols = list(dict.fromkeys(symbols))  # حذف تکراری با حفظ ترتیب
        self.trade_buffers = defaultdict(lambda: deque(maxlen=self.MAX_TRADES_PER_SYMBOL))
        self._threads = []
        self._stop = False

    def start(self):
        chunks = [self.symbols[i:i + self.SYMBOLS_PER_SOCKET]
                  for i in range(0, len(self.symbols), self.SYMBOLS_PER_SOCKET)]
        for chunk in chunks:
            th = threading.Thread(target=self._run_socket, args=(chunk,), daemon=True)
            th.start()
            self._threads.append(th)

    def stop(self):
        self._stop = True

    def _run_socket(self, symbols_chunk):
        host_idx = 0  # اندیس دامنه‌ی وب‌سوکت که این ترد با آن شروع می‌کند
        while not self._stop:
            host = WS_HOSTS[host_idx % len(WS_HOSTS)]
            opened_ok = {"flag": False}
            try:
                ws = websocket.WebSocketApp(
                    host,
                    header=[f"User-Agent: {_HEADERS['User-Agent']}"],
                    on_open=lambda w: (opened_ok.__setitem__("flag", True),
                                        self._on_open(w, symbols_chunk)),
                    on_message=self._on_message,
                    on_error=lambda w, e: print(f"[ws-error] دامنه {host} -> {e}"),
                    on_close=lambda w, c, m: None,
                )
                ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as exc:  # noqa: BLE001
                print(f"[bybit_engine] خطای وب‌سوکت روی {host}: {exc}")
            # اگر این دامنه اصلا باز نشد (فیلتر/بلاک)، سراغ دامنه‌ی بعدی برو
            if not opened_ok["flag"]:
                host_idx += 1
            if not self._stop:
                time.sleep(5)  # تلاش مجدد پس از قطعی

    def _on_open(self, ws, symbols_chunk):
        args = [f"publicTrade.{s}" for s in symbols_chunk]
        ws.send(json.dumps({"op": "subscribe", "args": args}))

    def _on_message(self, ws, message):
        try:
            msg = json.loads(message)
        except json.JSONDecodeError:
            return
        data = msg.get("data")
        if not data or not isinstance(data, list):
            return
        for tr in data:
            try:
                symbol = tr["s"]
                self.trade_buffers[symbol].append({
                    "t": int(tr["T"]),                # میلی‌ثانیه
                    "p": float(tr["p"]),
                    "v": float(tr["v"]),
                    "side": tr["S"],                  # "Buy" یا "Sell"
                })
            except (KeyError, ValueError, TypeError):
                continue

    def get_trades_df(self, symbol: str) -> pd.DataFrame:
        buf = self.trade_buffers.get(symbol)
        if not buf:
            return pd.DataFrame(columns=["t", "p", "v", "side"])
        df = pd.DataFrame(list(buf))
        df["time"] = pd.to_datetime(df["t"], unit="ms", utc=True)
        return df

    def buffer_span_minutes(self, symbol: str) -> float:
        """چند دقیقه دیتای واقعی تیک‌به‌تیک در بافر داریم"""
        buf = self.trade_buffers.get(symbol)
        if not buf or len(buf) < 2:
            return 0.0
        return (buf[-1]["t"] - buf[0]["t"]) / 60000.0


# ----------------------------------------------------------------------------
# محاسبه‌ی cfield2 (قدرت خریدار به فروشنده) طبق فرمول کاربر
# ----------------------------------------------------------------------------
def _cfield2(buy_vol, buy_cnt, sell_vol, sell_cnt):
    """
    پیاده‌سازی دقیق فرمول:
    cfield2 = round( (Buy_I_Volume/Buy_CountI) / (Sell_I_Volume/Sell_CountI) *10 ) /10
    شرط اعتبار: هر دو طرف باید حداقل یک معامله داشته باشند (tno > 1)
    """
    tno = buy_cnt + sell_cnt
    if buy_cnt <= 0 or sell_cnt <= 0 or tno <= 1:
        return None
    avg_buy = buy_vol / buy_cnt
    avg_sell = sell_vol / sell_cnt
    if avg_sell == 0:
        return None
    cfield2 = round((avg_buy / avg_sell) * 10) / 10
    if cfield2 >= 0:
        return cfield2
    return None


def compute_power_series(trades_df: pd.DataFrame, tf_minutes: int) -> pd.DataFrame:
    """
    باکت‌بندی معاملات تیک‌به‌تیک بر اساس تایم‌فریم و محاسبه‌ی cfield2 برای
    هر کندل. خروجی: DataFrame با ستون‌های time, cfield2, buy_vol, sell_vol,
    buy_cnt, sell_cnt, power_pct (نرمال‌شده برای نمایش -100..100)
    """
    if trades_df.empty:
        return pd.DataFrame(columns=["time", "cfield2", "buy_vol", "sell_vol",
                                      "buy_cnt", "sell_cnt", "power_pct"])

    df = trades_df.copy()
    df = df.set_index("time")
    rule = f"{tf_minutes}min"

    buy = df[df["side"] == "Buy"]["v"].resample(rule).agg(["sum", "count"])
    sell = df[df["side"] == "Sell"]["v"].resample(rule).agg(["sum", "count"])
    merged = buy.join(sell, how="outer", lsuffix="_buy", rsuffix="_sell").fillna(0)
    merged = merged.rename(columns={
        "sum_buy": "buy_vol", "count_buy": "buy_cnt",
        "sum_sell": "sell_vol", "count_sell": "sell_cnt",
    })

    records = []
    for ts, row in merged.iterrows():
        cf = _cfield2(row["buy_vol"], row["buy_cnt"], row["sell_vol"], row["sell_cnt"])
        # نرمال‌سازی برای نمایش بصری: (cfield2 - 1) به بازه‌ی درصدی
        power_pct = None if cf is None else max(-100.0, min(100.0, (cf - 1.0) * 100.0))
        records.append({
            "time": ts, "cfield2": cf,
            "buy_vol": row["buy_vol"], "sell_vol": row["sell_vol"],
            "buy_cnt": row["buy_cnt"], "sell_cnt": row["sell_cnt"],
            "power_pct": power_pct,
        })
    cols = ["time", "cfield2", "buy_vol", "sell_vol", "buy_cnt", "sell_cnt", "power_pct"]
    return pd.DataFrame(records, columns=cols) if records else pd.DataFrame(columns=cols)


def estimate_power_from_kline(kdf: pd.DataFrame) -> pd.DataFrame:
    """
    تخمین قدرت خریدار/فروشنده از روی کندل معمولی، برای بازه‌هایی که هنوز
    داده‌ی تیک‌به‌تیک کافی در بافر جمع نشده (مثلاً بلافاصله پس از اجرای برنامه).
    این یک روش جایگزین (proxy) است، نه محاسبه‌ی دقیق طبق فرمول اصلی، و در
    رابط کاربری با برچسب «تخمینی» مشخص می‌شود.
    """
    empty_cols = ["time", "cfield2", "power_pct", "buy_vol", "sell_vol"]
    if kdf.empty:
        return pd.DataFrame(columns=empty_cols)
    out = kdf.copy()
    body = (out["close"] - out["open"])
    rng = (out["high"] - out["low"]).replace(0, np.nan)
    buy_ratio = (0.5 + 0.5 * (body / rng)).clip(0.05, 0.95).fillna(0.5)
    out["buy_vol"] = out["volume"] * buy_ratio
    out["sell_vol"] = out["volume"] * (1 - buy_ratio)
    # تخمین تعداد معاملات از حجم (فرض میانگین اندازه ثابت) صرفا برای نسبت
    out["cfield2"] = (out["buy_vol"] / out["sell_vol"].replace(0, np.nan)).round(1)
    out["power_pct"] = ((out["cfield2"] - 1.0) * 100).clip(-100, 100)
    return out[["time", "cfield2", "power_pct", "buy_vol", "sell_vol"]]


# ----------------------------------------------------------------------------
# آنالیز عمق مشکوک بودن حجم
# ----------------------------------------------------------------------------
def analyze_volume(kdf: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """
    آنالیز عمقی حجم برای هر کندل:
      - z-score حجم نسبت به میانگین متحرک (شناسایی جهش‌های غیرعادی)
      - نسبت حجم به تغییر قیمت (حجم بالا + حرکت قیمتی ناچیز => مشکوک،
        احتمال شست‌وشوی حجم / دستکاری / جذب سفارش بدون افشای قیمت)
    خروجی ستون status: "عادی" | "قابل توجه" | "مشکوک"
    """
    if kdf.empty:
        return kdf
    out = kdf.copy()
    out["vol_mean"] = out["volume"].rolling(window, min_periods=5).mean()
    out["vol_std"] = out["volume"].rolling(window, min_periods=5).std().replace(0, np.nan)
    out["vol_z"] = (out["volume"] - out["vol_mean"]) / out["vol_std"]
    out["price_chg_pct"] = ((out["close"] - out["open"]).abs() / out["open"]) * 100

    def classify(row):
        z = row["vol_z"]
        pchg = row["price_chg_pct"]
        if pd.isna(z):
            return "در حال محاسبه"
        if z > 3.5 and pchg < 0.15:
            return "مشکوک"          # حجم خیلی بالا بدون حرکت قیمتی متناسب
        if z > 2.0:
            return "قابل توجه"
        return "عادی"

    out["vol_status"] = out.apply(classify, axis=1)
    return out


# ----------------------------------------------------------------------------
# چرخش سرمایه‌ی واقعی میان ۳۰ ارز و ارز انتخابی
# ----------------------------------------------------------------------------
def money_flow_from_top30(stream: TradeStreamManager, target_symbol: str,
                           coins=None, lookback_buckets: int = 24) -> pd.DataFrame:
    """
    برای هر یک از ۳۰ ارز، سری زمانی «جریان نقدی خالص» (خرید - فروش به دلار)
    را در باکت‌های ۵ دقیقه‌ای از بافر معاملات زنده می‌سازد، سپس با استفاده
    از همبستگی با تاخیر (lag 0..3 کندل) نسبت به ارز هدف، مشخص می‌کند کدام
    ارزها همزمان یا اندکی زودتر از ارز هدف، ورودی/خروجی پول داشته‌اند.
    این یک مدل همبستگی است، نه رابطه‌ی علّی قطعی.
    """
    coins = coins or TOP_30
    coins = [c for c in coins if c != target_symbol]

    target_trades = stream.get_trades_df(target_symbol)
    if target_trades.empty:
        return pd.DataFrame(columns=["symbol", "net_flow_usdt", "lag_bars", "correlation"])
    target_flow = _net_flow_series(target_trades, 5).tail(lookback_buckets)
    if target_flow.empty or target_flow["net_flow"].std() == 0:
        return pd.DataFrame(columns=["symbol", "net_flow_usdt", "lag_bars", "correlation"])

    rows = []
    for c in coins:
        tdf = stream.get_trades_df(c)
        if tdf.empty or len(tdf) < 10:
            continue
        flow = _net_flow_series(tdf, 5).tail(lookback_buckets)
        if flow.empty or flow["net_flow"].std() == 0:
            continue
        best_corr, best_lag = -2.0, 0
        for lag in range(0, 4):
            a = target_flow["net_flow"].reset_index(drop=True)
            b = flow["net_flow"].shift(lag).reset_index(drop=True)
            n = min(len(a), len(b))
            if n < 5:
                continue
            corr = np.corrcoef(a.tail(n), b.tail(n))[0, 1]
            if not np.isnan(corr) and corr > best_corr:
                best_corr, best_lag = corr, lag
        if best_corr > 0.15:  # فقط همبستگی مثبت معنادار
            rows.append({
                "symbol": c,
                "net_flow_usdt": float(flow["net_flow"].tail(3).sum()),
                "lag_bars": best_lag,
                "correlation": round(float(best_corr), 2),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("correlation", ascending=False).reset_index(drop=True)


def _net_flow_series(trades_df: pd.DataFrame, tf_minutes: int) -> pd.DataFrame:
    df = trades_df.copy()
    df["value"] = df["p"] * df["v"]
    df = df.set_index("time")
    buy_val = df[df["side"] == "Buy"]["value"].resample(f"{tf_minutes}min").sum()
    sell_val = df[df["side"] == "Sell"]["value"].resample(f"{tf_minutes}min").sum()
    net = (buy_val - sell_val).rename("net_flow").fillna(0)
    return net.reset_index()
