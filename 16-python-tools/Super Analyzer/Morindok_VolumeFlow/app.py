"""
================================================================================
 Morindok  |  Volume & Liquidity Intelligence
================================================================================
یک اپلیکیشن Dash برای رصد لحظه‌ای جریان حجم خرید/فروش ۲۰ ارز برتر بایبیت.

قابلیت‌ها:
  - دریافت ۲۰ نماد برتر USDT-Spot بر اساس گردش مالی ۲۴ ساعته (turnover24h)
  - دریافت معاملات لحظه‌ای (recent-trade) و تجمیع آن‌ها در باکت‌های ۱ دقیقه‌ای
    به تفکیک حجم خرید (Taker Buy) و حجم فروش (Taker Sell)
  - محاسبه‌ی «جریان خالص» (Net Flow = Buy - Sell) در واحد USDT برای هر ارز/دقیقه
  - رتبه‌بندی ارزها بر اساس ورودی/خروجی تجمعی حجم
  - نمودار Sankey برای نمایش چرخش سرمایه: خروج از ارزهای قرمز -> استخر USDT -> ورود به ارزهای سبز
  - Heatmap جریان حجم به ازای هر ارز در طول زمان
  - Z-Score آماری برای شناسایی جهش‌های غیرعادی حجم
  - بخش پیشنهاد (Signal) خرید/فروش بر پایه ترکیب z-score + فشار خرید + شیب روند
    (این بخش صرفاً یک سیگنال آماری است و توصیه مالی محسوب نمی‌شود)
  - تب «تحلیل تک ارز»: انتخاب ارز و تایم‌فریم، نمودار کندل‌استیک + FVG (Fair Value Gap)
    با درصد پرشدگی و حجم کندل جهش‌ساز، جریان خرید/فروش واقعی (از موتور جمع‌آوری زنده)
    یا تخمین Chaikin در نبود داده زنده، به‌همراه RSI/VWAP/نوسان/Z-Score حجم اختصاصی همان ارز

اجرا:
    pip install dash dash-bootstrap-components plotly pandas numpy requests
    python bybit_volume_flow_dash.py
سپس مرورگر را روی http://127.0.0.1:8050 باز کنید.
================================================================================
"""

import threading
import time
import traceback
from collections import defaultdict, deque
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==============================================================================
# CONFIG
# ==============================================================================
# بایبیت چند دامنه‌ی آینه (mirror) دارد؛ اگر دامنه اصلی در کشور/شبکه شما بلاک یا
# سانسور شده باشد (خطای 403 / connection reset)، به‌ترتیب دامنه‌های بعدی امتحان می‌شوند.
BYBIT_BASE_CANDIDATES = [
    "https://api.bybit.com",
    "https://api.bytick.com",     # آینه رسمی بایبیت برای مناطق محدودشده
    "https://api.bybit.kz",       # آینه منطقه‌ای
]
CATEGORY_DEFAULT = "spot"          # "spot" یا "linear" (فیوچرز پرپچوال USDT)
TOP_N = 20
TRADE_POLL_SEC = 4                 # فاصله دریافت معاملات هر نماد
TICKER_REFRESH_SEC = 90            # فاصله بروزرسانی رتبه‌بندی ۲۰ ارز برتر
BIN_SECONDS = 60                   # طول هر باکت زمانی (۱ دقیقه)
HISTORY_MINUTES = 90                # عمق تاریخچه نگه‌داری شده
ZSCORE_WINDOW = 20                  # تعداد دقایق برای محاسبه بیس‌لاین z-score
REQUEST_TIMEOUT = 8
TRADE_LIMIT = 60                    # حداکثر مجاز اسپات بایبیت برای recent-trade

SESSION = requests.Session()
SESSION.headers.update({
    # هدرهای شبیه مرورگر برای عبور از فیلترهای ساده‌ی ضدربات/Cloudflare
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json",
})

# --- تنظیمات مربوط به تب «تحلیل تک ارز» ---------------------------------------
TIMEFRAME_OPTIONS = [
    {"label": "۱ دقیقه", "value": "1"},
    {"label": "۵ دقیقه", "value": "5"},
    {"label": "۱۵ دقیقه", "value": "15"},
    {"label": "۱ ساعت", "value": "60"},
    {"label": "۴ ساعت", "value": "240"},
    {"label": "۱ روز", "value": "D"},
]
TIMEFRAME_SECONDS = {"1": 60, "5": 300, "15": 900, "60": 3600, "240": 14400, "D": 86400}
KLINE_LIMIT = 250

# دامنه‌ای که در حال حاضر کار می‌کند؛ بعد از اولین موفقیت ثابت می‌ماند تا سرعت بگیرد
_ACTIVE_BASE = {"url": None}


def _bybit_get(path, params):
    """
    تلاش برای گرفتن یک endpoint از بایبیت با امتحان دامنه‌های مختلف (fallback).
    هر خطا (DNS، تایم‌اوت، 403، JSON نامعتبر و ...) پیام واضح برمی‌گرداند تا در
    نوار وضعیت اپ نمایش داده شود و کاربر بداند دقیقاً مشکل کجاست.
    """
    candidates = [_ACTIVE_BASE["url"]] if _ACTIVE_BASE["url"] else []
    candidates += [b for b in BYBIT_BASE_CANDIDATES if b != _ACTIVE_BASE["url"]]

    last_exc = None
    for base in candidates:
        try:
            resp = SESSION.get(f"{base}{path}", params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if data.get("retCode") != 0:
                raise RuntimeError(f"Bybit API error ({base}): retCode={data.get('retCode')} "
                                    f"retMsg={data.get('retMsg')}")
            _ACTIVE_BASE["url"] = base
            return data
        except requests.exceptions.SSLError as exc:
            last_exc = f"خطای SSL روی {base}: {exc}"
        except requests.exceptions.ConnectionError as exc:
            last_exc = (f"عدم دسترسی شبکه به {base} — احتمالاً بایبیت در شبکه/کشور شما "
                        f"بلاک شده یا نیاز به VPN دارید. ({exc.__class__.__name__})")
        except requests.exceptions.Timeout:
            last_exc = f"تایم‌اوت در اتصال به {base}"
        except requests.exceptions.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else "?"
            last_exc = f"HTTP {code} از {base} (احتمال بلاک منطقه‌ای/Cloudflare)"
        except ValueError as exc:
            last_exc = f"پاسخ JSON نامعتبر از {base}: {exc}"
        except Exception as exc:  # noqa: BLE001
            last_exc = f"خطای ناشناخته روی {base}: {exc}"
    raise RuntimeError(last_exc or "اتصال به هیچ‌کدام از دامنه‌های بایبیت برقرار نشد")


def fetch_klines(symbol, category, interval, limit=KLINE_LIMIT):
    """دریافت کندل‌های OHLCV از بایبیت و بازگرداندن DataFrame به ترتیب زمانی صعودی."""
    data = _bybit_get(
        "/v5/market/kline",
        {"category": category, "symbol": symbol, "interval": interval, "limit": limit},
    )
    rows = data["result"]["list"]
    rows = list(reversed(rows))  # بایبیت جدیدترین را اول برمی‌گرداند
    df = pd.DataFrame(rows, columns=["start", "open", "high", "low", "close", "volume", "turnover"])
    for col in ["start", "open", "high", "low", "close", "volume", "turnover"]:
        df[col] = df[col].astype(float)
    df["start"] = df["start"].astype(np.int64)
    df["dt"] = pd.to_datetime(df["start"], unit="ms")
    return df.reset_index(drop=True)


def _now_minute(ts=None):
    ts = ts if ts is not None else time.time()
    return int(ts // BIN_SECONDS) * BIN_SECONDS


# ==============================================================================
# DATA STORE (thread-safe)
# ==============================================================================
class FlowStore:
    def __init__(self):
        self.lock = threading.RLock()
        self.category = CATEGORY_DEFAULT
        self.symbols = []                 # لیست رتبه‌بندی‌شده ۲۰ نماد برتر
        self.last_trade_time = {}         # symbol -> آخرین timestamp دیده شده (ms)
        # bins[symbol][minute_ts] = {"buy": float, "sell": float}
        self.bins = defaultdict(lambda: defaultdict(lambda: {"buy": 0.0, "sell": 0.0}))
        self.ticker_snapshot = {}         # symbol -> {"turnover24h", "price", "pcnt24h"}
        self.status = {"connected": False, "last_update": None, "last_error": None}

    def set_category(self, category):
        with self.lock:
            if category != self.category:
                self.category = category
                self.symbols = []
                self.bins.clear()
                self.last_trade_time.clear()
                self.ticker_snapshot.clear()

    def refresh_top_symbols(self):
        try:
            data = _bybit_get("/v5/market/tickers", {"category": self.category})
            rows = data["result"]["list"]
            usdt_rows = [r for r in rows if r.get("symbol", "").endswith("USDT")]

            def turnover(r):
                try:
                    return float(r.get("turnover24h", 0) or 0)
                except (TypeError, ValueError):
                    return 0.0

            usdt_rows.sort(key=turnover, reverse=True)
            top = usdt_rows[:TOP_N]
            with self.lock:
                self.symbols = [r["symbol"] for r in top]
                for r in top:
                    try:
                        price = float(r.get("lastPrice", 0) or 0)
                        pcnt = float(r.get("price24hPcnt", 0) or 0) * 100
                    except (TypeError, ValueError):
                        price, pcnt = 0.0, 0.0
                    self.ticker_snapshot[r["symbol"]] = {
                        "turnover24h": turnover(r),
                        "price": price,
                        "pcnt24h": pcnt,
                    }
                self.status["connected"] = True
                self.status["last_error"] = None
            return True
        except Exception as exc:  # noqa: BLE001
            with self.lock:
                self.status["connected"] = False
                self.status["last_error"] = str(exc)
            print(f"[refresh_top_symbols] {exc}")
            return False

    def poll_symbol_trades(self, symbol):
        try:
            data = _bybit_get(
                "/v5/market/recent-trade",
                {"category": self.category, "symbol": symbol, "limit": TRADE_LIMIT},
            )
            trades = data["result"]["list"]
            if not trades:
                return

            with self.lock:
                last_seen = self.last_trade_time.get(symbol, 0)

            parsed = []
            for t in trades:
                try:
                    t_ms = int(t.get("time", 0))
                    price = float(t.get("price", 0) or 0)
                    size = float(t.get("size", t.get("qty", 0)) or 0)
                    side = str(t.get("side", "")).lower()
                except (TypeError, ValueError):
                    continue
                if t_ms <= last_seen:
                    continue
                parsed.append((t_ms, price, size, side))

            if not parsed:
                return

            parsed.sort(key=lambda x: x[0])
            new_last_seen = parsed[-1][0]

            with self.lock:
                for t_ms, price, size, side in parsed:
                    minute_ts = _now_minute(t_ms / 1000.0)
                    notional = price * size
                    bucket = self.bins[symbol][minute_ts]
                    if side == "buy":
                        bucket["buy"] += notional
                    elif side == "sell":
                        bucket["sell"] += notional
                self.last_trade_time[symbol] = new_last_seen
                self.status["last_update"] = datetime.now(timezone.utc)
        except Exception as exc:  # noqa: BLE001
            # نویز شبکه یک نماد نباید کل موتور جمع‌آوری را متوقف کند، ولی برای دیباگ چاپ می‌شود
            print(f"[poll_symbol_trades:{symbol}] {exc}")

    def prune_old_bins(self):
        cutoff = _now_minute() - HISTORY_MINUTES * BIN_SECONDS
        with self.lock:
            for symbol in list(self.bins.keys()):
                for minute_ts in list(self.bins[symbol].keys()):
                    if minute_ts < cutoff:
                        del self.bins[symbol][minute_ts]

    def snapshot_dataframe(self, lookback_minutes):
        """برمی‌گرداند DataFrame با ایندکس دقیقه و ستون‌های MultiIndex (symbol, buy/sell)."""
        with self.lock:
            symbols = list(self.symbols)
            bins_copy = {s: dict(self.bins.get(s, {})) for s in symbols}
            ticker_copy = dict(self.ticker_snapshot)
            status_copy = dict(self.status)

        end_minute = _now_minute()
        minute_range = list(range(end_minute - (lookback_minutes - 1) * BIN_SECONDS,
                                   end_minute + BIN_SECONDS, BIN_SECONDS))

        records = []
        for symbol in symbols:
            sym_bins = bins_copy.get(symbol, {})
            for m in minute_range:
                b = sym_bins.get(m, {"buy": 0.0, "sell": 0.0})
                records.append({"symbol": symbol, "minute": m, "buy": b["buy"], "sell": b["sell"]})

        df = pd.DataFrame(records)
        if df.empty:
            df = pd.DataFrame(columns=["symbol", "minute", "buy", "sell"])
        df["net"] = df["buy"] - df["sell"]
        df["dt"] = pd.to_datetime(df["minute"], unit="s")
        return df, ticker_copy, status_copy, minute_range


STORE = FlowStore()


# ==============================================================================
# BACKGROUND COLLECTOR THREAD
# ==============================================================================
def collector_loop():
    last_ticker_refresh = 0
    last_trade_poll = {}
    while True:
        try:
            now = time.time()
            if now - last_ticker_refresh > TICKER_REFRESH_SEC or not STORE.symbols:
                STORE.refresh_top_symbols()
                last_ticker_refresh = now

            symbols = list(STORE.symbols)
            for symbol in symbols:
                last_poll = last_trade_poll.get(symbol, 0)
                if now - last_poll >= TRADE_POLL_SEC:
                    STORE.poll_symbol_trades(symbol)
                    last_trade_poll[symbol] = now

            STORE.prune_old_bins()
            time.sleep(0.5)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            time.sleep(2)


collector_thread = threading.Thread(target=collector_loop, daemon=True)
collector_thread.start()


# ==============================================================================
# STATISTICS
# ==============================================================================
def compute_rankings(df, lookback_minutes):
    if df.empty:
        return pd.DataFrame(columns=[
            "symbol", "cum_net", "cum_buy", "cum_sell", "buy_ratio",
            "zscore", "trend_slope", "score"
        ])

    agg = df.groupby("symbol").agg(
        cum_buy=("buy", "sum"),
        cum_sell=("sell", "sum"),
    ).reset_index()
    agg["cum_net"] = agg["cum_buy"] - agg["cum_sell"]
    total = (agg["cum_buy"] + agg["cum_sell"]).replace(0, np.nan)
    agg["buy_ratio"] = (agg["cum_buy"] / total).fillna(0.5)

    zscores, slopes = {}, {}
    for symbol, g in df.groupby("symbol"):
        g = g.sort_values("minute")
        net_series = g["net"].values
        baseline = net_series[-ZSCORE_WINDOW:] if len(net_series) >= 3 else net_series
        mean, std = np.mean(baseline), np.std(baseline)
        latest = net_series[-1] if len(net_series) else 0.0
        zscores[symbol] = 0.0 if std < 1e-9 else (latest - mean) / std

        tail = net_series[-5:] if len(net_series) >= 2 else net_series
        if len(tail) >= 2:
            x = np.arange(len(tail))
            cum = np.cumsum(tail)
            slope = np.polyfit(x, cum, 1)[0]
        else:
            slope = 0.0
        slopes[symbol] = slope

    agg["zscore"] = agg["symbol"].map(zscores).fillna(0.0)
    agg["trend_slope"] = agg["symbol"].map(slopes).fillna(0.0)

    def _norm(series):
        s = series.astype(float)
        rng = s.max() - s.min()
        if rng < 1e-9:
            return s * 0.0
        return (s - s.min()) / rng * 2 - 1  # نرمال‌سازی به بازه [-1, 1]

    agg["z_norm"] = _norm(agg["zscore"])
    agg["trend_norm"] = _norm(agg["trend_slope"])
    agg["pressure_dev"] = (agg["buy_ratio"] - 0.5) * 2  # بازه [-1, 1]

    agg["score"] = (0.4 * agg["z_norm"] + 0.3 * agg["pressure_dev"] + 0.3 * agg["trend_norm"])

    agg = agg.sort_values("cum_net", ascending=False).reset_index(drop=True)
    return agg


def build_suggestion(ranking_df, ticker_snapshot, min_minutes_ok):
    if ranking_df.empty or not min_minutes_ok:
        return {
            "buy": None, "sell": None,
            "note": "در حال جمع‌آوری داده‌های کافی برای تولید سیگنال آماری... (چند دقیقه صبر کنید)",
        }
    ranked_by_score = ranking_df.sort_values("score", ascending=False)
    top = ranked_by_score.iloc[0]
    bottom = ranked_by_score.iloc[-1]

    def pack(row):
        info = ticker_snapshot.get(row["symbol"], {})
        return {
            "symbol": row["symbol"],
            "score": round(float(row["score"]), 3),
            "cum_net": float(row["cum_net"]),
            "buy_ratio": float(row["buy_ratio"]),
            "zscore": float(row["zscore"]),
            "trend_slope": float(row["trend_slope"]),
            "price": info.get("price"),
            "pcnt24h": info.get("pcnt24h"),
        }

    return {"buy": pack(top), "sell": pack(bottom), "note": None}


# ==============================================================================
# CHART BUILDERS
# ==============================================================================
DARK_BG = "#0e1117"
CARD_BG = "#161b24"
GRID_COLOR = "#232935"
GREEN = "#26d07c"
RED = "#f0466a"
ACCENT = "#4f8cff"

BASE_LAYOUT = dict(
    paper_bgcolor=CARD_BG,
    plot_bgcolor=CARD_BG,
    font=dict(color="#e6e9ef", family="Vazirmatn, Segoe UI, sans-serif"),
    margin=dict(l=10, r=10, t=40, b=10),
)


def empty_figure(message):
    fig = go.Figure()
    fig.update_layout(**BASE_LAYOUT)
    fig.add_annotation(text=message, showarrow=False, font=dict(size=15, color="#9aa4b2"))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def build_ranking_bar(ranking_df):
    if ranking_df.empty:
        return empty_figure("در حال دریافت داده از بایبیت...")
    df = ranking_df.sort_values("cum_net", ascending=True)
    colors = [GREEN if v >= 0 else RED for v in df["cum_net"]]
    fig = go.Figure(go.Bar(
        x=df["cum_net"], y=df["symbol"], orientation="h",
        marker_color=colors,
        text=[f"{v:,.0f}$" for v in df["cum_net"]],
        textposition="outside",
        hovertemplate="%{y}<br>جریان خالص: %{x:,.0f} USDT<extra></extra>",
    ))
    fig.update_layout(**BASE_LAYOUT, title="رتبه‌بندی ارزها بر اساس جریان خالص حجم (ورود/خروج)")
    fig.update_xaxes(gridcolor=GRID_COLOR, zerolinecolor="#4a5265")
    fig.update_yaxes(gridcolor=GRID_COLOR)
    return fig


def build_heatmap(df, minute_range):
    if df.empty:
        return empty_figure("در حال دریافت داده از بایبیت...")
    pivot = df.pivot_table(index="symbol", columns="minute", values="net", fill_value=0.0)
    pivot = pivot.reindex(columns=minute_range, fill_value=0.0)
    order = pivot.sum(axis=1).sort_values(ascending=False).index
    pivot = pivot.reindex(order)
    x_labels = [datetime.fromtimestamp(m, tz=timezone.utc).strftime("%H:%M") for m in pivot.columns]

    zmax = np.nanpercentile(np.abs(pivot.values), 95) if pivot.size else 1
    zmax = zmax if zmax > 0 else 1

    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=x_labels, y=pivot.index,
        colorscale=[[0, RED], [0.5, "#1a1f29"], [1, GREEN]],
        zmid=0, zmin=-zmax, zmax=zmax,
        colorbar=dict(title="Net $"),
        hovertemplate="%{y} | %{x}<br>جریان خالص: %{z:,.0f} USDT<extra></extra>",
    ))
    fig.update_layout(**BASE_LAYOUT, title="نقشه حرارتی جریان حجم دقیقه‌ای هر ارز")
    return fig


def build_rotation_sankey(ranking_df):
    if ranking_df.empty:
        return empty_figure("در حال دریافت داده از بایبیت...")

    outflow = ranking_df[ranking_df["cum_net"] < 0].sort_values("cum_net").head(10)
    inflow = ranking_df[ranking_df["cum_net"] > 0].sort_values("cum_net", ascending=False).head(10)

    if outflow.empty and inflow.empty:
        return empty_figure("جریان قابل‌توجهی برای نمایش وجود ندارد")

    labels = list(outflow["symbol"]) + ["استخر نقدینگی USDT"] + list(inflow["symbol"])
    pool_idx = len(outflow)
    node_colors = [RED] * len(outflow) + [ACCENT] + [GREEN] * len(inflow)

    sources, targets, values, link_colors = [], [], [], []
    for i, row in enumerate(outflow.itertuples()):
        sources.append(i)
        targets.append(pool_idx)
        values.append(abs(row.cum_net))
        link_colors.append("rgba(240,70,106,0.45)")

    offset = pool_idx + 1
    for i, row in enumerate(inflow.itertuples()):
        sources.append(pool_idx)
        targets.append(offset + i)
        values.append(abs(row.cum_net))
        link_colors.append("rgba(38,208,124,0.45)")

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            label=labels, color=node_colors, pad=18, thickness=18,
            line=dict(color="#0e1117", width=1),
        ),
        link=dict(source=sources, target=targets, value=values, color=link_colors),
    ))
    fig.update_layout(**BASE_LAYOUT, title="چرخش سرمایه: خروج از ارزهای قرمز ← استخر ← ورود به ارزهای سبز")
    return fig


def build_pressure_gauge(top_symbol_info):
    if not top_symbol_info:
        return empty_figure("در انتظار داده")
    ratio = top_symbol_info["buy_ratio"] * 100
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=ratio,
        number={"suffix": "%", "font": {"color": "#e6e9ef"}},
        delta={"reference": 50, "increasing": {"color": GREEN}, "decreasing": {"color": RED}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": "#9aa4b2"},
            "bar": {"color": ACCENT},
            "steps": [
                {"range": [0, 40], "color": "#3a1523"},
                {"range": [40, 60], "color": "#232935"},
                {"range": [60, 100], "color": "#123626"},
            ],
            "threshold": {"line": {"color": "white", "width": 3}, "value": ratio},
        },
        title={"text": f"فشار خرید | {top_symbol_info['symbol']}"},
    ))
    fig.update_layout(**BASE_LAYOUT)
    return fig


# ==============================================================================
# SINGLE-COIN ANALYTICS  (تب «تحلیل تک ارز»)
# ==============================================================================
def compute_money_flow(df):
    """تخمین جریان خرید/فروش هر کندل صرفاً از روی OHLCV (به سبک Chaikin Money Flow).
    این یک برآورد آماری از محل بسته‌شدن کندل در بازه‌ی هایی/لویی است، نه معامله واقعی."""
    df = df.copy()
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    mult = (((df["close"] - df["low"]) - (df["high"] - df["close"])) / rng).fillna(0.0)
    df["mfv"] = mult * df["volume"]
    df["mfv_cum"] = df["mfv"].cumsum()
    return df


def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def compute_vwap(df):
    typical = (df["high"] + df["low"] + df["close"]) / 3
    cum_vol = df["volume"].cumsum().replace(0, np.nan)
    return (typical * df["volume"]).cumsum() / cum_vol


def attach_live_flow(df, symbol, tf_seconds):
    """هر جا داده‌ی واقعی خرید/فروش (از موتور جمع‌آوری زنده‌ی خودمان) برای بازه‌ی
    زمانی یک کندل موجود باشد، آن را به DataFrame اضافه می‌کند. برخلاف تخمین Chaikin،
    این عدد از معاملات واقعی ثبت‌شده روی بایبیت محاسبه شده و دقیق‌تر است، اما فقط
    برای دقایق اخیر (بعد از روشن‌شدن برنامه) در دسترس است."""
    with STORE.lock:
        bins = dict(STORE.bins.get(symbol, {}))
    live_buy, live_sell = [], []
    for start_ms in df["start"]:
        start_s = int(start_ms / 1000)
        end_s = start_s + tf_seconds
        b = s = 0.0
        has_data = False
        t = (start_s // BIN_SECONDS) * BIN_SECONDS
        while t < end_s:
            bucket = bins.get(t)
            if bucket is not None:
                b += bucket["buy"]
                s += bucket["sell"]
                has_data = True
            t += BIN_SECONDS
        live_buy.append(b if has_data else np.nan)
        live_sell.append(s if has_data else np.nan)
    df = df.copy()
    df["live_buy"] = live_buy
    df["live_sell"] = live_sell
    df["live_net"] = df["live_buy"] - df["live_sell"]
    return df


def _scan_fvg_fill(kind, i, gap_low, gap_high, highs, lows, n):
    gap_size = gap_high - gap_low
    filled, fill_idx, max_pen = False, None, 0.0
    for j in range(i + 1, n):
        lo, hi = lows[j], highs[j]
        if kind == "bull":
            depth = (gap_high - lo) / gap_size if gap_size > 0 else 0.0
        else:
            depth = (hi - gap_low) / gap_size if gap_size > 0 else 0.0
        depth = max(0.0, min(1.0, depth))
        max_pen = max(max_pen, depth)
        if max_pen >= 0.999:
            filled, fill_idx = True, j
            break
    return filled, fill_idx, round(max_pen * 100, 1)


def detect_fvgs(df, max_items=20):
    """شناسایی Fair Value Gap های سه‌کندلی کلاسیک (ICT) و وضعیت پرشدن آن‌ها.
    گپی که آخرین اندیس ممکن (idx == n-2) را داشته باشد و هنوز پر نشده باشد،
    یعنی روی کندل درحال‌تشکیل (زنده/لایو) شکل گرفته: کندل جاری با دو کندل قبل
    مقایسه می‌شود تا امتداد گپ پیش از بسته‌شدن کندل قابل مشاهده باشد."""
    highs, lows, vols, times = df["high"].values, df["low"].values, df["volume"].values, df["dt"].values
    n = len(df)
    out = []
    for i in range(1, n - 1):
        is_live = (i == n - 2)
        if lows[i + 1] > highs[i - 1]:
            gap_low, gap_high = float(highs[i - 1]), float(lows[i + 1])
            filled, fill_idx, fill_pct = _scan_fvg_fill("bull", i, gap_low, gap_high, highs, lows, n)
            out.append({
                "kind": "bull", "idx": i, "gap_low": gap_low, "gap_high": gap_high,
                "creation_time": times[i], "disp_volume": float(vols[i]),
                "filled": filled, "end_time": times[fill_idx] if filled else times[-1],
                "fill_pct": fill_pct, "is_live": is_live and not filled,
            })
        if highs[i + 1] < lows[i - 1]:
            gap_low, gap_high = float(highs[i + 1]), float(lows[i - 1])
            filled, fill_idx, fill_pct = _scan_fvg_fill("bear", i, gap_low, gap_high, highs, lows, n)
            out.append({
                "kind": "bear", "idx": i, "gap_low": gap_low, "gap_high": gap_high,
                "creation_time": times[i], "disp_volume": float(vols[i]),
                "filled": filled, "end_time": times[fill_idx] if filled else times[-1],
                "fill_pct": fill_pct, "is_live": is_live and not filled,
            })
    return out[-max_items:]


def gap_liquidity(df, gap):
    """جمع جریان نقدینگی (واقعی اگر موجود باشد، وگرنه تخمین Chaikin) برای تمام
    کندل‌هایی که از لحظه‌ی تشکیل گپ تاکنون داخل بازه‌ی قیمتی آن معامله شده‌اند.
    برمی‌گرداند: (مقدار جریان, آیا از داده واقعی زنده بوده است)."""
    lo, hi = gap["gap_low"], gap["gap_high"]
    sub = df.iloc[gap["idx"]:]
    mask = (sub["low"] <= hi) & (sub["high"] >= lo)
    zone = sub[mask]
    if zone.empty:
        return 0.0, False
    if "live_net" in zone.columns and zone["live_net"].notna().any():
        return float(zone["live_net"].sum(skipna=True)), True
    return float(zone["mfv"].sum()), False


def build_symbol_chart(df, fvgs, symbol, timeframe_label):
    if df is None or df.empty:
        return empty_figure("در حال دریافت داده کندل از بایبیت...")

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.55, 0.2, 0.25], vertical_spacing=0.03,
    )

    fig.add_trace(go.Candlestick(
        x=df["dt"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color=GREEN, decreasing_line_color=RED, name="قیمت",
    ), row=1, col=1)

    if "vwap" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["dt"], y=df["vwap"], mode="lines", name="VWAP",
            line=dict(color=ACCENT, width=1.4, dash="dot"),
        ), row=1, col=1)

    if len(df) > 1:
        bar_step = df["dt"].iloc[1] - df["dt"].iloc[0]
    else:
        bar_step = pd.Timedelta(minutes=1)

    for gap in fvgs:
        is_live = gap.get("is_live", False)
        color = "rgba(38,208,124,0.22)" if gap["kind"] == "bull" else "rgba(240,70,106,0.22)"
        line_color = GREEN if gap["kind"] == "bull" else RED
        x1 = (gap["end_time"] + bar_step * 3) if is_live else gap["end_time"]
        fig.add_shape(
            type="rect", xref="x", yref="y", row=1, col=1,
            x0=df["dt"].iloc[gap["idx"] - 1], x1=x1,
            y0=gap["gap_low"], y1=gap["gap_high"],
            fillcolor=color,
            line=dict(color=line_color, width=2.2 if is_live else 0.8,
                      dash="dash" if is_live else "solid"),
        )
        label_text = f"🔴 LIVE FVG {gap['fill_pct']:.0f}%" if is_live else f"FVG {gap['fill_pct']:.0f}%"
        fig.add_annotation(
            x=df["dt"].iloc[gap["idx"] - 1], y=gap["gap_high"] if gap["kind"] == "bull" else gap["gap_low"],
            xref="x", yref="y", row=1, col=1, showarrow=False, xanchor="left",
            text=label_text,
            font=dict(size=10 if is_live else 9, color="#ffffff" if is_live else line_color),
            bgcolor="rgba(240,70,106,0.75)" if (is_live and gap["kind"] == "bear") else (
                "rgba(38,208,124,0.75)" if is_live else None),
        )

    vol_colors = [GREEN if c >= o else RED for o, c in zip(df["open"], df["close"])]
    fig.add_trace(go.Bar(x=df["dt"], y=df["volume"], marker_color=vol_colors, name="حجم"), row=2, col=1)

    if "live_net" in df.columns and df["live_net"].notna().any():
        live_colors = [GREEN if v >= 0 else RED for v in df["live_net"].fillna(0)]
        fig.add_trace(go.Bar(
            x=df["dt"], y=df["live_net"], marker_color=live_colors, name="جریان واقعی (Live)",
            opacity=0.9,
        ), row=3, col=1)
    else:
        mfv_colors = [GREEN if v >= 0 else RED for v in df["mfv"]]
        fig.add_trace(go.Bar(
            x=df["dt"], y=df["mfv"], marker_color=mfv_colors, name="جریان تخمینی (Chaikin)",
            opacity=0.85,
        ), row=3, col=1)

    fig.update_layout(
        **BASE_LAYOUT,
        title=f"{symbol} | تایم‌فریم {timeframe_label}",
        showlegend=True, legend=dict(orientation="h", y=1.06),
        xaxis_rangeslider_visible=False,
        height=680,
    )
    for r in (1, 2, 3):
        fig.update_xaxes(gridcolor=GRID_COLOR, row=r, col=1)
        fig.update_yaxes(gridcolor=GRID_COLOR, row=r, col=1)
    fig.update_yaxes(title_text="قیمت", row=1, col=1)
    fig.update_yaxes(title_text="حجم", row=2, col=1)
    fig.update_yaxes(title_text="جریان", row=3, col=1)
    return fig


def stat_mini_card(title, value, color=None):
    return dbc.Col(
        dbc.Card(
            dbc.CardBody([
                html.Div(title, className="text-muted small mb-1"),
                html.Div(value, className="fw-bold", style={"fontSize": "1.15rem", "color": color or "#e6e9ef"}),
            ]),
            className="glass-card text-center",
        ),
        width=True,
    )


def build_symbol_stats(df, symbol):
    if df is None or df.empty or len(df) < 5:
        return html.Div(
            dbc.Alert("در حال جمع‌آوری داده‌های کافی برای این ارز...", color="secondary"),
        )

    last = df.iloc[-1]
    first_visible = df.iloc[0]
    pct_change = (last["close"] - first_visible["open"]) / first_visible["open"] * 100 if first_visible["open"] else 0
    rsi_val = compute_rsi(df["close"]).iloc[-1]
    vwap_val = df["vwap"].iloc[-1] if "vwap" in df.columns else np.nan
    vwap_dev = (last["close"] - vwap_val) / vwap_val * 100 if vwap_val and not np.isnan(vwap_val) else 0.0
    returns = df["close"].pct_change().dropna()
    volatility = returns.tail(30).std() * 100 if len(returns) else 0.0
    vol_mean, vol_std = df["volume"].tail(30).mean(), df["volume"].tail(30).std()
    vol_z = (last["volume"] - vol_mean) / vol_std if vol_std and vol_std > 0 else 0.0

    live_ratio = None
    if "live_buy" in df.columns:
        tot_buy, tot_sell = df["live_buy"].sum(), df["live_sell"].sum()
        if (tot_buy + tot_sell) > 0:
            live_ratio = tot_buy / (tot_buy + tot_sell)

    rsi_color = RED if rsi_val >= 70 else (GREEN if rsi_val <= 30 else "#e6e9ef")
    pct_color = GREEN if pct_change >= 0 else RED

    cards = [
        stat_mini_card("قیمت لحظه‌ای", f"{last['close']:,.4f}"),
        stat_mini_card("تغییر در بازه", f"{pct_change:+.2f}%", pct_color),
        stat_mini_card("RSI (14)", f"{rsi_val:.1f}", rsi_color),
        stat_mini_card("فاصله از VWAP", f"{vwap_dev:+.2f}%"),
        stat_mini_card("نوسان اخیر (۳۰ کندل)", f"{volatility:.2f}%"),
        stat_mini_card("Z-Score حجم", f"{vol_z:+.2f}"),
    ]
    if live_ratio is not None:
        cards.append(stat_mini_card("فشار خرید زنده (Live)", f"{live_ratio*100:.1f}%",
                                     GREEN if live_ratio >= 0.5 else RED))
    else:
        cards.append(stat_mini_card("فشار خرید زنده (Live)", "داده کافی نیست", "#9aa4b2"))

    return dbc.Row(cards, className="g-2")


def build_fvg_table(df, fvgs, current_price):
    if not fvgs:
        return dbc.Alert("در این بازه هیچ Fair Value Gap فعالی شناسایی نشد.", color="secondary")
    rows = []
    for gap in reversed(fvgs):
        kind_fa = "صعودی" if gap["kind"] == "bull" else "نزولی"
        color = GREEN if gap["kind"] == "bull" else RED
        if gap.get("is_live"):
            status = "🔴 زنده (در حال تشکیل)"
        elif gap["filled"]:
            status = "پر شده"
        else:
            status = "فعال (باز)"
        dist = (current_price - gap["gap_high"]) / current_price * 100 if gap["kind"] == "bull" \
            else (gap["gap_low"] - current_price) / current_price * 100
        liq_val, is_real = gap_liquidity(df, gap)
        liq_color = GREEN if liq_val >= 0 else RED
        liq_text = f"{liq_val:+,.0f}" + (" (واقعی)" if is_real else " (تخمینی)")
        row_style = {"backgroundColor": "rgba(240,70,106,0.08)"} if gap.get("is_live") else {}
        rows.append(html.Tr([
            html.Td(kind_fa, style={"color": color, "fontWeight": 600}),
            html.Td(pd.Timestamp(gap["creation_time"]).strftime("%m-%d %H:%M")),
            html.Td(f"{gap['gap_low']:,.4f} — {gap['gap_high']:,.4f}"),
            html.Td(f"{gap['disp_volume']:,.2f}"),
            html.Td(status),
            html.Td(f"{gap['fill_pct']:.0f}%"),
            html.Td(f"{dist:+.2f}%"),
            html.Td(liq_text, style={"color": liq_color}),
        ], style=row_style))
    header = html.Thead(html.Tr([
        html.Th("نوع"), html.Th("زمان تشکیل"), html.Th("بازه قیمتی گپ"), html.Th("حجم کندل جهش‌ساز"),
        html.Th("وضعیت"), html.Th("درصد پرشدگی"), html.Th("فاصله تا قیمت فعلی"), html.Th("جریان نقدینگی داخل گپ"),
    ]))
    return dbc.Table([header, html.Tbody(rows)], bordered=False, hover=True, color="dark",
                      responsive=True, striped=True)


LIVE_TF_OPTIONS = [
    {"label": "1m", "value": "1"},
    {"label": "5m", "value": "5"},
    {"label": "15m", "value": "15"},
    {"label": "1h", "value": "60"},
    {"label": "4h", "value": "240"},
    {"label": "1D", "value": "D"},
]


def build_mini_tf_figure(df_tf, gaps, tf_label):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df_tf["dt"], open=df_tf["open"], high=df_tf["high"], low=df_tf["low"], close=df_tf["close"],
        increasing_line_color=GREEN, decreasing_line_color=RED, name="",
    ))

    bar_step = (df_tf["dt"].iloc[1] - df_tf["dt"].iloc[0]) if len(df_tf) > 1 else pd.Timedelta(minutes=1)
    for gap in gaps:
        is_live = gap.get("is_live", False)
        color = "rgba(38,208,124,0.22)" if gap["kind"] == "bull" else "rgba(240,70,106,0.22)"
        line_color = GREEN if gap["kind"] == "bull" else RED
        x1 = (gap["end_time"] + bar_step * 3) if is_live else gap["end_time"]
        fig.add_shape(
            type="rect", xref="x", yref="y",
            x0=df_tf["dt"].iloc[gap["idx"] - 1], x1=x1,
            y0=gap["gap_low"], y1=gap["gap_high"],
            fillcolor=color,
            line=dict(color=line_color, width=2.2 if is_live else 0.8,
                      dash="dash" if is_live else "solid"),
        )
        if is_live:
            fig.add_annotation(
                x=df_tf["dt"].iloc[gap["idx"] - 1],
                y=gap["gap_high"] if gap["kind"] == "bull" else gap["gap_low"],
                xref="x", yref="y", showarrow=False, xanchor="left",
                text=f"🔴 LIVE {gap['fill_pct']:.0f}%",
                font=dict(size=10, color="#ffffff"),
                bgcolor="rgba(38,208,124,0.85)" if gap["kind"] == "bull" else "rgba(240,70,106,0.85)",
            )

    layout_kwargs = dict(BASE_LAYOUT)
    layout_kwargs["margin"] = dict(l=6, r=6, t=32, b=6)
    fig.update_layout(
        **layout_kwargs,
        title=tf_label, showlegend=False, xaxis_rangeslider_visible=False,
        height=300,
    )
    fig.update_xaxes(gridcolor=GRID_COLOR)
    fig.update_yaxes(gridcolor=GRID_COLOR)
    return fig


def _live_tf_card(tf_value, tf_label, symbol, category):
    """برای یک تایم‌فریم مشخص، آخرین کندل‌ها را می‌گیرد و یک نمودار کندل‌استیک زنده
    به‌همراه جعبه‌ی FVG روی کندل‌های واقعی همان تایم‌فریم می‌سازد تا
    دقیقاً دیده شود قیمت چطور روی گپ در حال حرکت است."""
    try:
        df_tf = fetch_klines(symbol, category, tf_value, limit=60)
    except Exception as exc:  # noqa: BLE001
        return dbc.Col(dbc.Card(dbc.CardBody([
            html.Div(tf_label, className="fw-bold mb-1"),
            html.Div(f"خطا در دریافت داده: {exc}", className="text-danger small"),
        ]), className="glass-card"), width=6)

    df_tf = compute_money_flow(df_tf)
    tf_seconds = TIMEFRAME_SECONDS.get(tf_value, 60)
    df_tf = attach_live_flow(df_tf, symbol, tf_seconds)
    gaps = detect_fvgs(df_tf, max_items=15)
    live_gaps = [g for g in gaps if g.get("is_live")]

    border_color = "rgba(255,255,255,0.06)"
    footer = []
    if not live_gaps:
        footer = [html.Div("⚪ در حال حاضر گپ زنده‌ای در این تایم‌فریم شکل نگرفته", className="text-muted small")]
    else:
        for g in live_gaps:
            liq_val, is_real = gap_liquidity(df_tf, g)
            liq_color = GREEN if liq_val >= 0 else RED
            kind_label = "🟢 گپ صعودی زنده" if g["kind"] == "bull" else "🔴 گپ نزولی زنده"
            border_color = GREEN if g["kind"] == "bull" else RED
            gap_pct = (g["gap_high"] - g["gap_low"]) / df_tf["close"].iloc[-1] * 100
            footer += [
                html.Div(kind_label, className="live-badge px-2 py-1 d-inline-block",
                         style={"color": border_color, "fontWeight": 600}),
                html.Div(f"بازه: {g['gap_low']:,.4f} – {g['gap_high']:,.4f}  ({gap_pct:.2f}%)",
                         className="small text-muted"),
                html.Div([
                    "نقدینگی داخل گپ: ",
                    html.Span(f"{liq_val:+,.0f}", style={"color": liq_color, "fontWeight": 600}),
                    html.Span(" (واقعی)" if is_real else " (تخمینی)", className="text-muted"),
                ], className="small"),
            ]

    fig = build_mini_tf_figure(df_tf, gaps, tf_label)

    return dbc.Col(
        dbc.Card([
            dcc.Graph(figure=fig, id=f"mini-chart-{tf_value}", config={"displaylogo": False},
                       style={"height": "300px"}),
            dbc.CardBody(footer, className="pt-2"),
        ], className="glass-card", style={"borderColor": border_color, "borderWidth": "1.5px"}),
        width=6, className="mb-2",
    )


def build_live_fvg_panel(symbol, category, selected_tfs):
    if not symbol or not selected_tfs:
        return dbc.Alert("حداقل یک تایم‌فریم را برای پایش زنده انتخاب کنید.", color="secondary")
    cards = []
    for tf in selected_tfs:
        label = next((o["label"] for o in LIVE_TF_OPTIONS if o["value"] == tf), tf)
        cards.append(_live_tf_card(tf, label, symbol, category))
    return dbc.Row(cards, className="g-2")


# ==============================================================================
# DASH APP
# ==============================================================================
FONT_URL = "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;600;700;800&display=swap"
TELEGRAM_URL = "https://t.me/BITMOON618"

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG, FONT_URL])
app.title = "Morindok Volume Intelligence"
server = app.server

# --- CSS سفارشی: هویت بصری حرفه‌ای، فونت فارسی، افکت شیشه‌ای، تب‌های پیل‌شکل و ... ---
app.index_string = """
<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <style>
        * { font-family: 'Vazirmatn', 'Segoe UI', sans-serif !important; box-sizing: border-box; }
        html, body {
            background: radial-gradient(ellipse 1200px 600px at 20% -10%, #16283b 0%, transparent 60%),
                        radial-gradient(ellipse 900px 500px at 100% 0%, #0f2a2a 0%, transparent 55%),
                        linear-gradient(180deg, #0a0d13 0%, #070910 100%);
            background-attachment: fixed;
            min-height: 100vh;
        }
        ::-webkit-scrollbar { width: 10px; height: 10px; }
        ::-webkit-scrollbar-track { background: #0a0d13; }
        ::-webkit-scrollbar-thumb { background: #2a3444; border-radius: 8px; }
        ::-webkit-scrollbar-thumb:hover { background: #3d4d66; }

        /* ---------- نوار برند بالای صفحه ---------- */
        .top-accent-bar {
            height: 4px; width: 100%; border-radius: 999px; margin-bottom: 18px;
            background: linear-gradient(90deg, #4f8cff 0%, #26d07c 50%, #26d0ce 100%);
            box-shadow: 0 0 18px rgba(79,140,255,0.35);
        }

        /* ---------- بنر تلگرام ---------- */
        .telegram-banner {
            background: linear-gradient(100deg, #1b8dd9 0%, #2aa9e0 35%, #26d0ce 100%);
            background-size: 200% 200%;
            animation: bannerShift 6s ease infinite;
            border: none !important;
            border-radius: 16px !important;
            padding: 14px 22px !important;
            box-shadow: 0 6px 24px rgba(38, 169, 224, 0.35);
            transition: transform 0.18s ease, box-shadow 0.18s ease;
            color: #ffffff !important;
        }
        .telegram-banner:hover {
            transform: translateY(-2px) scale(1.005);
            box-shadow: 0 10px 32px rgba(38, 169, 224, 0.5);
        }
        @keyframes bannerShift {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }

        @keyframes livePulse {
            0%   { box-shadow: 0 0 0 0 rgba(240,70,106,0.45); }
            70%  { box-shadow: 0 0 0 8px rgba(240,70,106,0); }
            100% { box-shadow: 0 0 0 0 rgba(240,70,106,0); }
        }
        .live-badge { animation: livePulse 1.8s infinite; border-radius: 10px; }

        /* ---------- عنوان و برندینگ ---------- */
        .brand-row { display: flex; align-items: center; gap: 14px; }
        .brand-mark {
            width: 46px; height: 46px; border-radius: 14px; flex-shrink: 0;
            background: linear-gradient(135deg, #4f8cff, #26d07c);
            display: flex; align-items: center; justify-content: center;
            font-size: 1.4rem; box-shadow: 0 6px 18px rgba(79,140,255,0.35);
        }
        .app-title {
            background: linear-gradient(90deg, #9cc4ff, #26d07c 55%, #4f8cff);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            font-weight: 800 !important;
            letter-spacing: 0.3px;
        }
        .eyebrow-label {
            font-size: 0.72rem; font-weight: 700; letter-spacing: 2.2px;
            color: #4fd1c5; text-transform: uppercase; margin-bottom: 4px;
        }

        /* ---------- کارت‌های شیشه‌ای ---------- */
        .glass-card {
            background: rgba(22, 27, 36, 0.72) !important;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.07) !important;
            border-radius: 18px !important;
            box-shadow: 0 8px 28px rgba(0,0,0,0.35);
            padding: 10px;
            transition: box-shadow 0.25s ease, transform 0.25s ease, border-color 0.25s ease;
        }
        .glass-card:hover {
            box-shadow: 0 14px 40px rgba(0,0,0,0.5);
            border-color: rgba(79,140,255,0.25) !important;
        }

        .control-card {
            background: linear-gradient(145deg, rgba(28,34,45,0.75), rgba(18,22,30,0.75)) !important;
            border: 1px solid rgba(255,255,255,0.07) !important;
            border-radius: 16px !important;
            padding: 16px 20px !important;
        }

        /* ---------- تب‌های اصلی به شکل پیل ---------- */
        #main-tabs.nav-tabs {
            border-bottom: none !important;
            gap: 8px;
            background: rgba(15,18,25,0.6);
            padding: 6px;
            border-radius: 14px;
            display: inline-flex;
            margin-bottom: 6px;
        }
        #main-tabs.nav-tabs .nav-link {
            border: none !important;
            border-radius: 10px !important;
            color: #9aa4b2 !important;
            font-weight: 600;
            padding: 9px 22px !important;
            transition: all 0.2s ease;
        }
        #main-tabs.nav-tabs .nav-link:hover { color: #e6e9ef !important; background: rgba(255,255,255,0.05); }
        #main-tabs.nav-tabs .nav-link.active {
            background: linear-gradient(135deg, #4f8cff, #2aa9e0) !important;
            color: #ffffff !important;
            box-shadow: 0 4px 14px rgba(79,140,255,0.35);
        }

        /* ---------- جدول‌ها ---------- */
        table.table-dark { border-collapse: separate !important; border-spacing: 0; }
        table.table-dark td, table.table-dark th { border-color: rgba(255,255,255,0.06) !important; padding: 10px 12px !important; }
        table.table-dark thead th {
            text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.8px;
            color: #9aa4b2 !important; background: rgba(255,255,255,0.03) !important;
        }
        table.table-dark tbody tr:hover { background: rgba(79,140,255,0.06) !important; }

        /* ---------- دراپ‌داون‌ها ---------- */
        .Select-control, .dash-dropdown .Select-control {
            border-radius: 10px !important; border: 1px solid rgba(255,255,255,0.1) !important;
        }
        .Select-menu-outer { border-radius: 10px !important; overflow: hidden; }

        hr.section-divider { border-color: rgba(255,255,255,0.08); margin: 28px 0; }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>
        {%config%}
        {%scripts%}
        {%renderer%}
    </footer>
</body>
</html>
"""

telegram_banner = html.A(
    dbc.Alert(
        dbc.Row(
            [
                dbc.Col(html.Span("✈️", style={"fontSize": "1.8rem"}), width="auto",
                        className="d-flex align-items-center"),
                dbc.Col([
                    html.Div("برای دریافت اندیکاتورها، تحلیل‌های گن و سیگنال‌های اختصاصی مورینداک",
                             style={"fontWeight": 600, "fontSize": "1.02rem"}),
                    html.Div("به کانال تلگرام بپیوندید", style={"opacity": 0.9, "fontSize": "0.9rem"}),
                ], className="d-flex flex-column justify-content-center"),
                dbc.Col(
                    html.Div(
                        ["@BITMOON618 ", html.Span("←", style={"fontSize": "1.2rem"})],
                        style={
                            "fontWeight": 800, "fontSize": "1.15rem",
                            "background": "rgba(255,255,255,0.18)",
                            "padding": "6px 18px", "borderRadius": "999px",
                            "whiteSpace": "nowrap",
                        },
                    ),
                    width="auto", className="d-flex align-items-center ms-auto",
                ),
            ],
            align="center", className="g-2",
        ),
        color=None, className="telegram-banner mb-3",
    ),
    href=TELEGRAM_URL, target="_blank", style={"textDecoration": "none"},
)

controls = dbc.Row(
    [
        dbc.Col([
            html.Label("بازار", className="text-muted small"),
            dcc.Dropdown(
                id="category-dd",
                options=[
                    {"label": "اسپات (Spot)", "value": "spot"},
                    {"label": "فیوچرز پرپچوال (Linear)", "value": "linear"},
                ],
                value=CATEGORY_DEFAULT, clearable=False,
                style={"color": "#0e1117"},
            ),
        ], width=3),
        dbc.Col([
            html.Label("بازه زمانی تحلیل", className="text-muted small"),
            dcc.Dropdown(
                id="lookback-dd",
                options=[
                    {"label": "۵ دقیقه", "value": 5},
                    {"label": "۱۵ دقیقه", "value": 15},
                    {"label": "۳۰ دقیقه", "value": 30},
                    {"label": "۶۰ دقیقه", "value": 60},
                ],
                value=15, clearable=False,
                style={"color": "#0e1117"},
            ),
        ], width=3),
        dbc.Col([
            html.Div(id="status-badge", className="mt-4"),
        ], width=6, className="d-flex align-items-end justify-content-end"),
    ],
    className="control-card mb-4 g-3",
)


def graph_card(graph_id, height):
    return dbc.Card(
        dcc.Graph(id=graph_id, style={"height": height}, config={"displaylogo": False}),
        className="glass-card h-100",
    )


overview_tab = html.Div([
    controls,
    html.Div("CAPITAL FLOW RANKING", className="eyebrow-label mt-1"),
    dbc.Row([
        dbc.Col(graph_card("ranking-bar", "520px"), width=5),
        dbc.Col(graph_card("heatmap", "520px"), width=7),
    ], className="mb-4 g-3"),
    html.Div("CAPITAL ROTATION & PRESSURE", className="eyebrow-label"),
    dbc.Row([
        dbc.Col(graph_card("sankey", "460px"), width=7),
        dbc.Col(graph_card("gauge", "460px"), width=5),
    ], className="mb-4 g-3"),
    html.Div("SIGNAL", className="eyebrow-label"),
    dbc.Row([
        dbc.Col(html.Div(id="suggestion-card"), width=12),
    ], className="mb-4"),
    html.Div("FULL RANKING", className="eyebrow-label"),
    dbc.Row([
        dbc.Col(dbc.Card(html.Div(id="ranking-table"), className="glass-card"), width=12),
    ]),
], className="pt-3")


symbol_controls = dbc.Row(
    [
        dbc.Col([
            html.Label("ارز", className="text-muted small"),
            dcc.Dropdown(id="symbol-dd", options=[], value=None, clearable=False,
                         style={"color": "#0e1117"}),
        ], width=4),
        dbc.Col([
            html.Label("تایم‌فریم قیمت", className="text-muted small"),
            dcc.Dropdown(id="timeframe-dd", options=TIMEFRAME_OPTIONS, value="15", clearable=False,
                         style={"color": "#0e1117"}),
        ], width=4),
        dbc.Col(html.Div(id="symbol-status", className="mt-4 text-muted small"), width=4),
    ],
    className="control-card mb-4 g-3",
)

symbol_tab = html.Div([
    symbol_controls,
    dbc.Row([
        dbc.Col(dbc.Card(dcc.Graph(id="symbol-chart", style={"height": "680px"},
                                    config={"displaylogo": False}), className="glass-card"), width=12),
    ], className="mb-4"),
    html.Div("ASSET STATISTICS", className="eyebrow-label"),
    html.H5("سیستم آماری اختصاصی ارز", className="text-light mb-2"),
    html.Div(id="symbol-stats", className="mb-4"),

    html.Hr(className="section-divider"),

    html.Div([
        html.Div("LIVE MONITORING", className="eyebrow-label"),
        html.H5("پایش هم‌زمان گپ‌های قیمتی روی چند تایم‌فریم", className="text-light d-inline-block me-3 mb-1"),
        html.P("وضعیت گپ‌های در حال شکل‌گیری و نقدینگی ورودی/خروجی هر بازه را به‌صورت زنده و همزمان دنبال کنید.",
               className="text-muted small mb-3"),
    ]),
    dcc.Checklist(
        id="live-tf-checklist",
        options=LIVE_TF_OPTIONS,
        value=["1", "5", "15", "60"],
        inline=True,
        className="mb-3",
        inputStyle={"marginInlineEnd": "6px", "marginInlineStart": "16px"},
    ),
    html.Div(id="live-fvg-panel", className="mb-4"),

    html.Hr(className="section-divider"),

    html.Div("STRUCTURE ANALYSIS", className="eyebrow-label"),
    html.H5("Fair Value Gap های شناسایی‌شده در تایم‌فریم انتخابی", className="text-light mb-2"),
    dbc.Card(html.Div(id="fvg-table"), className="glass-card"),
    dcc.Interval(id="live-fvg-interval", interval=5000, n_intervals=0),
], className="pt-3")


app.layout = dbc.Container(
    fluid=True,
    style={"minHeight": "100vh", "paddingTop": "20px", "paddingBottom": "40px", "paddingInline": "28px"},
    children=[
        html.Div(className="top-accent-bar"),
        telegram_banner,
        html.Div([
            html.Div([
                html.Div("MORINDOK · MARKET INTELLIGENCE", className="eyebrow-label"),
                html.Div([
                    html.Div("📡", className="brand-mark"),
                    html.H2("پایش جریان نقدینگی بازار ارز دیجیتال", className="app-title mb-0"),
                ], className="brand-row"),
                html.P("تحلیل لحظه‌ای جریان ورود و خروج نقدینگی، رتبه‌بندی ارزها و شناسایی گپ‌های قیمتی روی بازار بایبیت",
                       className="text-muted mb-4 mt-2"),
            ]),
        ]),
        dbc.Tabs([
            dbc.Tab(overview_tab, label="نمای کلی بازار", tab_id="tab-overview"),
            dbc.Tab(symbol_tab, label="تحلیل اختصاصی ارز", tab_id="tab-symbol"),
        ], id="main-tabs", active_tab="tab-overview"),
        dcc.Interval(id="interval", interval=6000, n_intervals=0),
        html.Div(id="dummy-category-trigger", style={"display": "none"}),
    ],
)


def status_badge_content(status):
    connected = status.get("connected")
    last_update = status.get("last_update")
    last_error = status.get("last_error")
    color = GREEN if connected else RED
    text = "متصل به بایبیت" if connected else "قطع / خطا در اتصال"
    ts_text = last_update.strftime("%H:%M:%S UTC") if last_update else "—"
    children = [
        dbc.Badge(
            [html.Span("● ", style={"color": color}), f"{text} | آخرین بروزرسانی: {ts_text}"],
            color="dark", className="p-2", style={"fontSize": "0.85rem"},
        )
    ]
    if not connected and last_error:
        children.append(
            html.Div(last_error, className="text-danger small mt-1", style={"maxWidth": "480px"})
        )
    return html.Div(children, className="text-end")


def suggestion_card_content(suggestion):
    if suggestion["note"]:
        return dbc.Alert(suggestion["note"], color="secondary")

    buy, sell = suggestion["buy"], suggestion["sell"]

    def make_col(item, is_buy):
        color = GREEN if is_buy else RED
        label = "پیشنهاد رصد برای خرید (جریان ورودی قوی)" if is_buy else "پیشنهاد رصد برای فروش/احتیاط (جریان خروجی قوی)"
        pcnt = item.get("pcnt24h")
        pcnt_txt = f"{pcnt:+.2f}%" if pcnt is not None else "—"
        price_txt = f"{item['price']:,.4f}" if item.get("price") else "—"
        return dbc.Col(
            dbc.Card(
                dbc.CardBody([
                    html.H5(label, style={"color": color}),
                    html.H3(item["symbol"], className="mb-2"),
                    html.P([
                        f"قیمت: {price_txt}   |   تغییر ۲۴ساعته: {pcnt_txt}",
                    ], className="text-muted mb-1"),
                    html.P([
                        f"جریان خالص در بازه: {item['cum_net']:,.0f} USDT   |   ",
                        f"فشار خرید: {item['buy_ratio']*100:.1f}%   |   ",
                        f"z-score: {item['zscore']:.2f}",
                    ], className="mb-1"),
                    html.P(f"امتیاز ترکیبی سیگنال: {item['score']:.3f}", className="mb-0 fw-bold"),
                ]),
                style={"backgroundColor": CARD_BG, "borderColor": color, "borderWidth": "1.5px"},
            ),
            width=6,
        )

    return dbc.Row([
        make_col(buy, True),
        make_col(sell, False),
        dbc.Col(
            html.P(
                "⚠️ این تحلیل صرفاً یک سیگنال آماری بر پایه جریان حجم معاملات اخیر است و توصیه مالی محسوب نمی‌شود. "
                "تصمیم‌گیری نهایی معاملاتی بر عهده شماست.",
                className="text-muted small mt-2",
            ),
            width=12,
        ),
    ])


def ranking_table_content(ranking_df, ticker_snapshot):
    if ranking_df.empty:
        return html.Div()
    rows = []
    for i, r in enumerate(ranking_df.itertuples(), start=1):
        info = ticker_snapshot.get(r.symbol, {})
        net_color = GREEN if r.cum_net >= 0 else RED
        rows.append(html.Tr([
            html.Td(i),
            html.Td(r.symbol, className="fw-bold"),
            html.Td(f"{r.cum_net:,.0f}", style={"color": net_color}),
            html.Td(f"{r.cum_buy:,.0f}"),
            html.Td(f"{r.cum_sell:,.0f}"),
            html.Td(f"{r.buy_ratio*100:.1f}%"),
            html.Td(f"{r.zscore:.2f}"),
            html.Td(f"{info.get('pcnt24h', 0):+.2f}%" if info else "—"),
        ]))
    header = html.Thead(html.Tr([
        html.Th("#"), html.Th("نماد"), html.Th("جریان خالص ($)"), html.Th("حجم خرید ($)"),
        html.Th("حجم فروش ($)"), html.Th("فشار خرید"), html.Th("Z-Score"), html.Th("تغییر ۲۴س"),
    ]))
    table = dbc.Table([header, html.Tbody(rows)], bordered=False, hover=True, color="dark", responsive=True, striped=True)
    return html.Div([html.H5("لیست کامل ارزها به ترتیب جریان ورودی/خروجی"), table])


@app.callback(Output("dummy-category-trigger", "children"), Input("category-dd", "value"))
def on_category_change(category):
    STORE.set_category(category)
    return category


@app.callback(
    [
        Output("ranking-bar", "figure"),
        Output("heatmap", "figure"),
        Output("sankey", "figure"),
        Output("gauge", "figure"),
        Output("suggestion-card", "children"),
        Output("ranking-table", "children"),
        Output("status-badge", "children"),
    ],
    [Input("interval", "n_intervals"), Input("lookback-dd", "value")],
)
def refresh_dashboard(_n, lookback_minutes):
    df, ticker_snapshot, status, minute_range = STORE.snapshot_dataframe(lookback_minutes)
    ranking_df = compute_rankings(df, lookback_minutes)

    non_empty_minutes = df[df["net"] != 0]["minute"].nunique() if not df.empty else 0
    min_minutes_ok = non_empty_minutes >= min(5, lookback_minutes)

    top_info = None
    if not ranking_df.empty:
        top_row = ranking_df.sort_values("score", ascending=False).iloc[0]
        top_info = {"symbol": top_row["symbol"], "buy_ratio": top_row["buy_ratio"]}

    suggestion = build_suggestion(ranking_df, ticker_snapshot, min_minutes_ok)

    return (
        build_ranking_bar(ranking_df),
        build_heatmap(df, minute_range),
        build_rotation_sankey(ranking_df),
        build_pressure_gauge(top_info),
        suggestion_card_content(suggestion),
        ranking_table_content(ranking_df, ticker_snapshot),
        status_badge_content(status),
    )


@app.callback(
    [Output("symbol-dd", "options"), Output("symbol-dd", "value")],
    [Input("interval", "n_intervals")],
    [State("symbol-dd", "value")],
)
def populate_symbol_dropdown(_n, current_value):
    with STORE.lock:
        symbols = list(STORE.symbols)
    if not symbols:
        return dash.no_update, dash.no_update
    options = [{"label": s, "value": s} for s in symbols]
    value = current_value if current_value in symbols else symbols[0]
    return options, value


@app.callback(
    [
        Output("symbol-chart", "figure"),
        Output("symbol-stats", "children"),
        Output("fvg-table", "children"),
        Output("symbol-status", "children"),
    ],
    [
        Input("interval", "n_intervals"),
        Input("symbol-dd", "value"),
        Input("timeframe-dd", "value"),
        Input("main-tabs", "active_tab"),
    ],
)
def refresh_symbol_tab(_n, symbol, timeframe, active_tab):
    # برای صرفه‌جویی در تعداد درخواست‌ها، فقط وقتی این تب فعال است داده می‌گیریم
    if active_tab != "tab-symbol" or not symbol or not timeframe:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    category = STORE.category
    tf_label = next((o["label"] for o in TIMEFRAME_OPTIONS if o["value"] == timeframe), timeframe)

    try:
        df = fetch_klines(symbol, category, timeframe)
        status_msg = f"✅ {symbol} | {len(df)} کندل دریافت شد"
    except Exception as exc:  # noqa: BLE001
        empty = empty_figure(f"خطا در دریافت کندل: {exc}")
        return empty, html.Div(), html.Div(), f"❌ {exc}"

    df = compute_money_flow(df)
    df["vwap"] = compute_vwap(df)
    tf_seconds = TIMEFRAME_SECONDS.get(timeframe, 60)
    df = attach_live_flow(df, symbol, tf_seconds)
    fvgs = detect_fvgs(df)

    chart = build_symbol_chart(df, fvgs, symbol, tf_label)
    stats = build_symbol_stats(df, symbol)
    current_price = float(df["close"].iloc[-1])
    table = build_fvg_table(df, fvgs, current_price)

    return chart, stats, table, status_msg


@app.callback(
    Output("live-fvg-panel", "children"),
    [
        Input("live-fvg-interval", "n_intervals"),
        Input("symbol-dd", "value"),
        Input("live-tf-checklist", "value"),
        Input("main-tabs", "active_tab"),
    ],
)
def refresh_live_fvg_panel(_n, symbol, selected_tfs, active_tab):
    if active_tab != "tab-symbol" or not symbol:
        return dash.no_update
    return build_live_fvg_panel(symbol, STORE.category, selected_tfs or [])


def _open_browser_when_ready(url, delay=1.8):
    def _worker():
        time.sleep(delay)
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=_worker, daemon=True).start()


if __name__ == "__main__":
    PORT = 8050
    URL = f"http://127.0.0.1:{PORT}"
    print("=" * 60)
    print(" Bybit Volume Flow Monitor | Morindok")
    print(f" در حال اجرا روی: {URL}")
    print(" برای خروج، این پنجره را ببندید یا Ctrl+C بزنید.")
    print("=" * 60)
    _open_browser_when_ready(URL)
    app.run(debug=False, host="127.0.0.1", port=PORT)
