#!/usr/bin/env python3
"""Digital trading organism — Dash + Bybit public/testnet, SQLite persistence."""
from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
from dash import Dash, Input, Output, State, dcc, html, dash_table, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objs as go

# ─── پیکربندی ───────────────────────────────────────────────
DB_PATH = Path(os.getenv("ORGANISM_DB", "organism_state.sqlite3"))
BYBIT_REST = os.getenv("BYBIT_REST", "https://api-testnet.bybit.com")
# دادهٔ عمومی مین‌نت دقیق‌تر است؛ سفارش واقعی فقط با کلید و LIVE_ORDERS=1
BYBIT_PUBLIC = os.getenv("BYBIT_PUBLIC", "https://api.bybit.com")
API_KEY = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")
LIVE_ORDERS = os.getenv("LIVE_ORDERS", "0") == "1"

START_EQUITY = 500.0
MAX_SLOTS = 5
LEVERAGE = 20
TAKER_FEE = 0.00055
UNIVERSE = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
HEARTBEAT_MS = 1000
MARKET_MS = 3000
MIN_CONFLUENCE = 0.72
MAX_SPREAD_BPS = 8.0

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "organism-trader/1.0"})


# ─── فیبوناچی باینری / کرونوکلاک ───────────────────────────
def fib(n: int) -> int:
    a, b = 1, 1
    for _ in range(max(0, n)):
        a, b = b, a + b
    return a


def binary_fib(n: int) -> tuple[int, str, float]:
    f = fib(n % 20)
    bits = format(f, "b")
    density = bits.count("1") / len(bits)
    return f, bits, density


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def session_regime(ts: datetime) -> str:
    h = ts.hour
    if 0 <= h < 7:
        return "آسیا"
    if 7 <= h < 13:
        return "لندن"
    if 13 <= h < 21:
        return "نیویورک"
    return "آرام‌شب"


# ─── دیتابیس ────────────────────────────────────────────────
class Memory:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    def _init(self) -> None:
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT, side TEXT, qty REAL, entry REAL, exit REAL,
                    sl REAL, tp REAL, leverage INTEGER, fee REAL, pnl REAL,
                    status TEXT, opened_at TEXT, closed_at TEXT,
                    reason TEXT, genome TEXT
                );
                CREATE TABLE IF NOT EXISTS lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT, symbol TEXT, lesson TEXT, delta REAL
                );
                CREATE TABLE IF NOT EXISTS genes (
                    key TEXT PRIMARY KEY, value REAL
                );
                CREATE TABLE IF NOT EXISTS equity_log (
                    ts TEXT, equity REAL
                );
                """
            )

    def execute(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self.lock, self._conn() as c:
            cur = c.execute(sql, args)
            c.commit()
            return cur.fetchall()

    def open_trades(self) -> list[dict]:
        rows = self.execute("SELECT * FROM trades WHERE status='open' ORDER BY id")
        return [dict(r) for r in rows]

    def all_closed(self) -> list[dict]:
        rows = self.execute("SELECT * FROM trades WHERE status='closed' ORDER BY id")
        return [dict(r) for r in rows]

    def save_gene(self, key: str, value: float) -> None:
        self.execute(
            "INSERT INTO genes(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, float(value)),
        )

    def load_genes(self) -> dict[str, float]:
        return {r["key"]: r["value"] for r in self.execute("SELECT key,value FROM genes")}

    def log_equity(self, equity: float) -> None:
        self.execute("INSERT INTO equity_log(ts,equity) VALUES(?,?)", (utc_now().isoformat(), equity))

    def equity_series(self) -> list[dict]:
        return [dict(r) for r in self.execute("SELECT ts,equity FROM equity_log ORDER BY ts")]


# ─── بایبیت پایدار ──────────────────────────────────────────
class BybitFeed:
    def __init__(self):
        self.lock = threading.Lock()
        self.tickers: dict[str, dict] = {}
        self.klines: dict[str, pd.DataFrame] = {}
        self.ok = False
        self.last_error = ""
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _get(self, base: str, path: str, params: dict) -> dict:
        r = SESSION.get(f"{base}{path}", params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        if data.get("retCode") != 0:
            raise RuntimeError(data.get("retMsg", "bybit error"))
        return data.get("result") or {}

    def _refresh(self) -> None:
        tickers = {}
        for sym in UNIVERSE:
            t = self._get(BYBIT_PUBLIC, "/v5/market/tickers", {"category": "linear", "symbol": sym})
            row = (t.get("list") or [None])[0]
            if not row:
                continue
            bid, ask = float(row["bid1Price"]), float(row["ask1Price"])
            last = float(row["lastPrice"])
            spread_bps = ((ask - bid) / last) * 1e4 if last else 99
            tickers[sym] = {
                "last": last,
                "bid": bid,
                "ask": ask,
                "spread_bps": spread_bps,
                "mark": float(row.get("markPrice") or last),
                "turnover24h": float(row.get("turnover24h") or 0),
                "price24hPcnt": float(row.get("price24hPcnt") or 0),
            }
            raw = self._get(
                BYBIT_PUBLIC,
                "/v5/market/kline",
                {"category": "linear", "symbol": sym, "interval": "5", "limit": 120},
            )
            lst = list(reversed(raw.get("list") or []))
            if len(lst) < 30:
                continue
            df = pd.DataFrame(lst, columns=["t", "o", "h", "l", "c", "vol", "turn"])
            for col in ("o", "h", "l", "c", "vol"):
                df[col] = df[col].astype(float)
            self.klines[sym] = df
        with self.lock:
            self.tickers = tickers
            self.ok = bool(tickers)
            self.last_error = ""

    def _loop(self) -> None:
        while not self._stop:
            try:
                self._refresh()
            except Exception as e:
                with self.lock:
                    self.ok = False
                    self.last_error = str(e)
            time.sleep(2.4)

    def snapshot(self) -> tuple[dict, dict, bool, str]:
        with self.lock:
            return dict(self.tickers), dict(self.klines), self.ok, self.last_error


# ─── ارگان‌ها / هورمون‌ها / ژن‌ها ──────────────────────────
ORGANS = [
    "چشم‌ساختار", "گوش‌حجم", "پوست‌نوسان", "ریه نقدینگی",
    "کبد نویز", "قلب ریسک", "قشرمنطق", "هیپوکامپ",
    "مخچه اجرا", "حسه ششم",
]
HORMONES = [
    "کورتیزول", "دوپامین", "آدرنالین", "سروتونین",
    "ملاتونین", "نورآدرنالین", "استیل‌کولین", "اکسی‌توسین",
]


@dataclass
class Organism:
    memory: Memory
    beat: int = 0
    genes: dict[str, float] = field(default_factory=dict)
    hormones: dict[str, float] = field(default_factory=dict)
    organ_fire: dict[str, float] = field(default_factory=dict)
    awareness: dict[str, float] = field(default_factory=dict)
    lessons: deque = field(default_factory=lambda: deque(maxlen=40))
    equity: float = START_EQUITY
    realized: float = 0.0
    neurons: int = max(8, os.cpu_count() or 4) * 64
    last_pulse: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        defaults = {
            "trend_w": 0.28, "mr_w": 0.18, "vol_w": 0.16,
            "flow_w": 0.14, "struct_w": 0.14, "sixth_w": 0.10,
            "fear": 0.35, "greed": 0.35, "patience": 0.70,
        }
        stored = self.memory.load_genes()
        self.genes = {**defaults, **stored}
        self.hormones = {h: 0.45 for h in HORMONES}
        self.organ_fire = {o: 0.4 for o in ORGANS}
        opens = self.memory.open_trades()
        locked = sum(float(t["qty"]) * float(t["entry"]) / LEVERAGE for t in opens)
        closed = self.memory.all_closed()
        self.realized = sum(float(t["pnl"]) for t in closed)
        self.equity = START_EQUITY + self.realized
        if not self.memory.equity_series():
            self.memory.log_equity(self.equity)

    def pulse(self) -> dict[str, Any]:
        self.beat += 1
        f, bits, density = binary_fib(self.beat)
        codon = int(bits[-8:], 2) / 255.0 if len(bits) >= 8 else density
        self.last_pulse = {
            "beat": self.beat,
            "fib": f,
            "bits": bits,
            "density": density,
            "codon": codon,
            "genome_stream": f"{bits}-{codon:.3f}",
            "chrono": utc_now().isoformat(),
            "session": session_regime(utc_now()),
        }
        return self.last_pulse

    def learn(self, symbol: str, pnl: float, reason: str) -> None:
        delta = float(np.clip(pnl / 25.0, -0.04, 0.04))
        key = "trend_w" if "روند" in reason else "mr_w" if "رنج" in reason else "sixth_w"
        self.genes[key] = float(np.clip(self.genes.get(key, 0.2) + delta, 0.05, 0.45))
        self.genes["patience"] = float(np.clip(self.genes["patience"] + (-0.02 if pnl < 0 else 0.01), 0.4, 0.95))
        self.memory.save_gene(key, self.genes[key])
        self.memory.save_gene("patience", self.genes["patience"])
        lesson = f"{symbol}: {'تقویت' if pnl>0 else 'تنبیه'} {key} | {reason}"
        self.lessons.append(lesson)
        self.memory.execute(
            "INSERT INTO lessons(ts,symbol,lesson,delta) VALUES(?,?,?,?)",
            (utc_now().isoformat(), symbol, lesson, delta),
        )


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(s: pd.Series, n: int = 14) -> float:
    d = s.diff()
    up, down = d.clip(lower=0), -d.clip(upper=0)
    rs = up.ewm(alpha=1 / n, adjust=False).mean() / (down.ewm(alpha=1 / n, adjust=False).mean() + 1e-12)
    return float(100 - (100 / (1 + rs.iloc[-1])))


def atr(df: pd.DataFrame, n: int = 14) -> float:
    h, l, c = df["h"], df["l"], df["c"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / n, adjust=False).mean().iloc[-1])


def analyze(symbol: str, df: pd.DataFrame, ticker: dict, org: Organism) -> dict:
    c = df["c"]
    e8, e21, e55 = ema(c, 8).iloc[-1], ema(c, 21).iloc[-1], ema(c, 55).iloc[-1]
    r = rsi(c)
    a = atr(df)
    vol_z = float((df["vol"].iloc[-1] - df["vol"].mean()) / (df["vol"].std() + 1e-12))
    bb_mid = c.rolling(20).mean().iloc[-1]
    bb_std = c.rolling(20).std().iloc[-1]
    bw = (2 * bb_std) / (bb_mid + 1e-12)
    hh = c.iloc[-20:-1].max()
    ll = c.iloc[-20:-1].min()
    last = float(c.iloc[-1])
    slope = float((e8 - e55) / (last + 1e-12))
    structure = 1.0 if last > hh * 0.998 and e8 > e21 > e55 else -1.0 if last < ll * 1.002 and e8 < e21 < e55 else 0.0
    regime = "روند" if abs(slope) > 0.0018 and bw > 0.012 else "رنج" if bw < 0.018 else "نوسانی"
    spread_ok = ticker["spread_bps"] <= MAX_SPREAD_BPS
    flow = float(np.tanh(vol_z / 2) * (1 if structure >= 0 else -1))
    visual = float(np.clip(0.5 + 8 * slope + 0.15 * structure, 0, 1))
    sixth = float(np.clip(0.5 + 0.25 * structure + 0.15 * np.tanh(vol_z) - 0.2 * abs(r - 50) / 50, 0, 1))
    number_sense = float(np.clip(1 - abs(math.log10(max(last, 1e-9)) % 1 - 0.5), 0, 1))

    g = org.genes
    long_score = (
        g["trend_w"] * max(0, slope * 80)
        + g["struct_w"] * max(0, structure)
        + g["flow_w"] * max(0, flow)
        + g["vol_w"] * (1 if 0.008 < bw < 0.05 else 0.2)
        + g["sixth_w"] * sixth
        + (0.08 if 42 < r < 68 else 0)
    )
    short_score = (
        g["trend_w"] * max(0, -slope * 80)
        + g["struct_w"] * max(0, -structure)
        + g["flow_w"] * max(0, -flow)
        + g["vol_w"] * (1 if 0.008 < bw < 0.05 else 0.2)
        + g["sixth_w"] * (1 - sixth)
        + (0.08 if 32 < r < 58 else 0)
    )
    mr_long = g["mr_w"] * (1 if regime == "رنج" and r < 32 and last < bb_mid else 0)
    mr_short = g["mr_w"] * (1 if regime == "رنج" and r > 68 and last > bb_mid else 0)
    long_score += mr_long
    short_score += mr_short
    if not spread_ok:
        long_score *= 0.25
        short_score *= 0.25

    side = "Buy" if long_score > short_score else "Sell"
    score = max(long_score, short_score)
    reason = f"{regime}|RSI={r:.1f}|ATR%={(a/last)*100:.2f}|vis={visual:.2f}"
    sl_dist = max(a * 1.15, last * 0.0012)
    tp_dist = sl_dist * 1.45
    if side == "Buy":
        sl, tp = last - sl_dist, last + tp_dist
    else:
        sl, tp = last + sl_dist, last - tp_dist

    organs = {
        "چشم‌ساختار": visual,
        "گوش‌حجم": float(np.clip(0.5 + 0.2 * vol_z, 0, 1)),
        "پوست‌نوسان": float(np.clip(bw * 12, 0, 1)),
        "ریه نقدینگی": float(np.clip(1 - ticker["spread_bps"] / 20, 0, 1)),
        "کبد نویز": float(np.clip(1 - abs(vol_z) / 6, 0, 1)),
        "قلب ریسک": float(np.clip(org.equity / START_EQUITY, 0, 1)),
        "قشرمنطق": float(np.clip(score, 0, 1)),
        "هیپوکامپ": float(np.clip(org.genes["patience"], 0, 1)),
        "مخچه اجرا": 0.92 if spread_ok else 0.2,
        "حسه ششم": sixth,
    }
    return {
        "symbol": symbol,
        "last": last,
        "side": side,
        "score": float(score),
        "regime": regime,
        "rsi": r,
        "atr": a,
        "spread_bps": ticker["spread_bps"],
        "visual": visual,
        "sixth": sixth,
        "number_sense": number_sense,
        "organs": organs,
        "sl": sl,
        "tp": tp,
        "reason": reason,
        "spread_ok": spread_ok,
    }


def emotion_gate(org: Organism, score: float) -> tuple[bool, str]:
    dd = max(0.0, (START_EQUITY - org.equity) / START_EQUITY)
    org.hormones["کورتیزول"] = float(np.clip(0.25 + dd * 2.2, 0, 1))
    org.hormones["دوپامین"] = float(np.clip(0.3 + max(0, org.realized) / 80, 0, 1))
    org.hormones["آدرنالین"] = float(np.clip(0.25 + (score - 0.5), 0, 1))
    org.hormones["سروتونین"] = float(np.clip(0.75 - dd, 0, 1))
    org.hormones["ملاتونین"] = 0.7 if session_regime(utc_now()) == "آرام‌شب" else 0.25
    org.hormones["نورآدرنالین"] = float(np.clip(score, 0, 1))
    org.hormones["استیل‌کولین"] = org.genes["patience"]
    org.hormones["اکسی‌توسین"] = 0.55
    if org.hormones["کورتیزول"] > 0.82:
        return False, "کورتیزول بالا — دفاع از سرمایه"
    if org.hormones["ملاتونین"] > 0.65 and score < 0.86:
        return False, "جلسه کم‌عمق — صبر"
    if org.hormones["دوپامین"] > 0.85:
        return score > MIN_CONFLUENCE + 0.08, "جلوگیری از بیش‌معامله پس از سود"
    need = MIN_CONFLUENCE + 0.06 * org.hormones["کورتیزول"]
    return score >= need, f"آستانه={need:.2f}"


class Broker:
    def __init__(self, org: Organism, feed: BybitFeed):
        self.org = org
        self.feed = feed
        self.lock = threading.Lock()

    def mark(self, symbol: str) -> float:
        t = self.feed.tickers.get(symbol) or {}
        return float(t.get("last") or 0)

    def fee(self, notional: float) -> float:
        return abs(notional) * TAKER_FEE

    def recover(self) -> None:
        """تعیین‌تکلیف معاملات باز بعد از ری‌استارت."""
        for t in self.org.memory.open_trades():
            px = self.mark(t["symbol"])
            if not px:
                continue
            self._maybe_close(dict(t), px, "بازیابی پس از اجرا")

    def _maybe_close(self, t: dict, px: float, why: str) -> None:
        side, sl, tp = t["side"], float(t["sl"]), float(t["tp"])
        hit = (side == "Buy" and (px <= sl or px >= tp)) or (side == "Sell" and (px >= sl or px <= tp))
        if not hit and why != "بازیابی اجباری":
            return
        qty, entry = float(t["qty"]), float(t["entry"])
        raw = (px - entry) * qty if side == "Buy" else (entry - px) * qty
        fee = float(t["fee"]) + self.fee(px * qty)
        pnl = raw - fee
        self.org.memory.execute(
            "UPDATE trades SET exit=?, fee=?, pnl=?, status='closed', closed_at=? WHERE id=?",
            (px, fee, pnl, utc_now().isoformat(), t["id"]),
        )
        self.org.realized += pnl
        self.org.equity = START_EQUITY + self.org.realized
        self.org.memory.log_equity(self.org.equity)
        self.org.learn(t["symbol"], pnl, t.get("reason") or why)

    def manage(self) -> None:
        with self.lock:
            for t in self.org.memory.open_trades():
                px = self.mark(t["symbol"])
                if px:
                    self._maybe_close(t, px, "مدیریت زنده")

    def allocate(self, ideas: list[dict]) -> list[dict]:
        opens = self.org.memory.open_trades()
        used = {t["symbol"] for t in opens}
        free_slots = MAX_SLOTS - len(opens)
        if free_slots <= 0:
            return []
        ranked = [i for i in ideas if i["symbol"] not in used and i["spread_ok"]]
        ranked.sort(key=lambda x: x["score"], reverse=True)
        picked = []
        for idea in ranked:
            ok, gate = emotion_gate(self.org, idea["score"])
            idea["gate"] = gate
            if ok:
                picked.append(idea)
            if len(picked) >= free_slots:
                break
        if not picked:
            return []
        scores = np.array([p["score"] for p in picked], dtype=float)
        weights = scores / scores.sum()
        locked = sum(float(t["qty"]) * float(t["entry"]) / LEVERAGE for t in opens)
        budget = max(0.0, self.org.equity - locked)
        out = []
        for w, idea in zip(weights, picked):
            usd = budget * float(w)
            if usd < 15:
                continue
            idea = dict(idea)
            idea["usd"] = usd
            out.append(idea)
        return out

    def open_idea(self, idea: dict) -> None:
        px = idea["last"]
        # اسپرد: خرید روی ask، فروش روی bid
        t = self.feed.tickers.get(idea["symbol"], {})
        fill = float(t.get("ask") if idea["side"] == "Buy" else t.get("bid") or px)
        notional = idea["usd"] * LEVERAGE
        qty = notional / fill
        fee = self.fee(notional)
        genome = self.org.last_pulse.get("genome_stream", "")
        self.org.memory.execute(
            """INSERT INTO trades(symbol,side,qty,entry,exit,sl,tp,leverage,fee,pnl,status,opened_at,closed_at,reason,genome)
               VALUES(?,?,?,?,NULL,?,?,?,?,0,'open',?,NULL,?,?)""",
            (
                idea["symbol"], idea["side"], qty, fill, idea["sl"], idea["tp"],
                LEVERAGE, fee, utc_now().isoformat(), idea["reason"], genome,
            ),
        )


# ─── هسته زنده ──────────────────────────────────────────────
memory = Memory(DB_PATH)
feed = BybitFeed()
organism = Organism(memory)
broker = Broker(organism, feed)
feed.start()
time.sleep(0.4)
broker.recover()

latest_ideas: list[dict] = []
state_lock = threading.Lock()


def cognition_tick() -> dict:
    organism.pulse()
    tickers, klines, ok, err = feed.snapshot()
    ideas = []
    fused_organs = {o: [] for o in ORGANS}
    awareness = {
        "اتصال": 1.0 if ok else 0.0,
        "ادراک عدد": 0.0,
        "هم‌فازی رژیم": 0.0,
        "فهم بصری": 0.0,
        "جریان سفارش": 0.0,
        "کرونوکلاک": 1.0,
        "ثبات هیجان": 1.0 - organism.hormones.get("کورتیزول", 0.4),
    }
    for sym in UNIVERSE:
        if sym not in klines or sym not in tickers:
            continue
        idea = analyze(sym, klines[sym], tickers[sym], organism)
        ideas.append(idea)
        for o, v in idea["organs"].items():
            fused_organs[o].append(v)
        awareness["ادراک عدد"] += idea["number_sense"]
        awareness["فهم بصری"] += idea["visual"]
        awareness["جریان سفارش"] += idea["organs"]["گوش‌حجم"]
        awareness["هم‌فازی رژیم"] += 1 if idea["regime"] != "نوسانی" else 0.45
    n = max(1, len(ideas))
    for k in list(awareness):
        if k not in ("اتصال", "کرونوکلاک", "ثبات هیجان"):
            awareness[k] /= n
    organism.organ_fire = {o: float(np.mean(v) if v else 0.3) for o, v in fused_organs.items()}
    organism.awareness = awareness
    broker.manage()
    opened = []
    if ok:
        for idea in broker.allocate(ideas):
            broker.open_idea(idea)
            opened.append(idea["symbol"])
    with state_lock:
        global latest_ideas
        latest_ideas = ideas
    return {"ok": ok, "err": err, "opened": opened, "ideas": ideas}


# ─── رابط ───────────────────────────────────────────────────
app = Dash(__name__, external_stylesheets=[dbc.themes.CYBORG], title="ارگانیسم تریدر")
app.layout = dbc.Container(
    [
        html.H3("ارگانیسم دیجیتال — تریدر هوشمند (پیپر/تست‌نت)", className="mt-3"),
        html.Div(id="heartbeat-banner", className="mb-2"),
        dcc.Interval(id="beat", interval=HEARTBEAT_MS),
        dcc.Interval(id="market", interval=MARKET_MS),
        dbc.Tabs(
            [
                dbc.Tab(label="آمار توانایی و آگاهی", tab_id="tab-stats", children=[
                    dbc.Row(
                        [
                            dbc.Col(dcc.Graph(id="g-organs"), md=6),
                            dbc.Col(dcc.Graph(id="g-hormones"), md=6),
                        ]
                    ),
                    dbc.Row(
                        [
                            dbc.Col(dcc.Graph(id="g-aware"), md=6),
                            dbc.Col(html.Div(id="stats-cards"), md=6),
                        ]
                    ),
                    html.H5("حافظه / درس‌ها"),
                    html.Pre(id="lessons", style={"whiteSpace": "pre-wrap"}),
                ]),
                dbc.Tab(label="معاملات زنده", tab_id="tab-trade", children=[
                    dbc.Row(
                        [
                            dbc.Col(html.Div(id="trade-kpis"), md=12),
                        ]
                    ),
                    dcc.Graph(id="g-equity"),
                    html.H5("معاملات باز"),
                    dash_table.DataTable(
                        id="open-table",
                        style_table={"overflowX": "auto"},
                        style_header={"backgroundColor": "#111"},
                        style_cell={"backgroundColor": "#1a1a1a", "color": "#eee", "textAlign": "center", "fontSize": 13},
                    ),
                    html.H5("ایده‌های لحظه‌ای (غیرتصادفی)"),
                    dash_table.DataTable(
                        id="idea-table",
                        style_table={"overflowX": "auto"},
                        style_header={"backgroundColor": "#111"},
                        style_cell={"backgroundColor": "#1a1a1a", "color": "#eee", "textAlign": "center", "fontSize": 13},
                    ),
                ]),
            ],
            id="tabs",
            active_tab="tab-stats",
        ),
    ],
    fluid=True,
)


def bar(title: str, mapping: dict, color: str) -> go.Figure:
    fig = go.Figure(go.Bar(x=list(mapping.values()), y=list(mapping.keys()), orientation="h", marker_color=color))
    fig.update_layout(
        title=title, template="plotly_dark", height=360, margin=dict(l=90, r=20, t=40, b=30),
        xaxis=dict(range=[0, 1]),
    )
    return fig


@app.callback(
    Output("heartbeat-banner", "children"),
    Output("g-organs", "figure"),
    Output("g-hormones", "figure"),
    Output("g-aware", "figure"),
    Output("stats-cards", "children"),
    Output("lessons", "children"),
    Input("beat", "n_intervals"),
)
def on_beat(_):
    p = organism.last_pulse or organism.pulse()
    banner = dbc.Alert(
        f"ضربان {p.get('beat')} | Fib={p.get('fib')} | باینری {p.get('bits')} | "
        f"جریان ژنوم {p.get('genome_stream')} | جلسه {p.get('session')} | نورون {organism.neurons} | "
        f"حالت {'LIVE' if LIVE_ORDERS and API_KEY else 'PAPER'}",
        color="danger" if p.get("beat", 0) % 2 else "info",
        className="mb-0",
    )
    cards = dbc.ListGroup(
        [
            dbc.ListGroupItem(f"سرمایه: {organism.equity:.2f} دلار"),
            dbc.ListGroupItem(f"PnL محقق: {organism.realized:.2f}"),
            dbc.ListGroupItem(f"ژن روند {organism.genes.get('trend_w',0):.3f} | رنج {organism.genes.get('mr_w',0):.3f} | صبر {organism.genes.get('patience',0):.3f}"),
            dbc.ListGroupItem(f"نردبان DNA: " + " → ".join(f"{k}:{v:.2f}" for k, v in list(organism.genes.items())[:6])),
            dbc.ListGroupItem("قدرت حواس روی مقیاس مدل (۰ تا ۱) کالیبره شده، نه ادعای دانایی مطلق."),
        ]
    )
    lessons = "\n".join(list(organism.lessons)[-12:] or ["هنوز درسی ثبت نشده"])
    return (
        banner,
        bar("ارگان‌های هماهنگ", organism.organ_fire, "#27d0e2"),
        bar("هورمون‌ها", organism.hormones, "#e27d27"),
        bar("سطح آگاهی به مارکت", organism.awareness, "#7de227"),
        cards,
        lessons,
    )


@app.callback(
    Output("trade-kpis", "children"),
    Output("g-equity", "figure"),
    Output("open-table", "data"),
    Output("open-table", "columns"),
    Output("idea-table", "data"),
    Output("idea-table", "columns"),
    Input("market", "n_intervals"),
)
def on_market(_):
    tick = cognition_tick()
    closed = organism.memory.all_closed()
    wins = [t for t in closed if float(t["pnl"]) > 0]
    wr = (len(wins) / len(closed) * 100) if closed else 0.0
    opens = organism.memory.open_trades()
    for t in opens:
        px = broker.mark(t["symbol"])
        if px:
            t["mark"] = px
            raw = (px - float(t["entry"])) * float(t["qty"]) if t["side"] == "Buy" else (float(t["entry"]) - px) * float(t["qty"])
            t["upnl"] = round(raw - float(t["fee"]), 3)
    kpis = dbc.Row(
        [
            dbc.Col(dbc.Card(dbc.CardBody([html.H6("سرمایه"), html.H4(f"{organism.equity:.2f}$")])), md=3),
            dbc.Col(dbc.Card(dbc.CardBody([html.H6("وین‌ریت"), html.H4(f"{wr:.1f}%")])), md=3),
            dbc.Col(dbc.Card(dbc.CardBody([html.H6("باز / بسته‌شده"), html.H4(f"{len(opens)} / {len(closed)}")])), md=3),
            dbc.Col(dbc.Card(dbc.CardBody([html.H6("فید"), html.H4("پایدار" if tick["ok"] else tick["err"][:28])])), md=3),
        ],
        className="my-3",
    )
    series = organism.memory.equity_series()
    fig = go.Figure()
    if series:
        fig.add_trace(go.Scatter(x=[s["ts"] for s in series], y=[s["equity"] for s in series], mode="lines", name="رشد ۵۰۰$"))
    fig.update_layout(template="plotly_dark", height=320, title="نمودار رشد سرمایه از ۵۰۰ دلار", margin=dict(t=40, l=40, r=20, b=40))
    open_cols = [{"name": c, "id": c} for c in ["id", "symbol", "side", "qty", "entry", "mark", "sl", "tp", "upnl", "reason"]]
    idea_rows = [
        {
            "symbol": i["symbol"],
            "side": i["side"],
            "score": round(i["score"], 3),
            "regime": i["regime"],
            "rsi": round(i["rsi"], 1),
            "spread_bps": round(i["spread_bps"], 2),
            "sixth": round(i["sixth"], 2),
            "reason": i["reason"],
        }
        for i in tick["ideas"]
    ]
    idea_cols = [{"name": c, "id": c} for c in ["symbol", "side", "score", "regime", "rsi", "spread_bps", "sixth", "reason"]]
    pretty_open = []
    for t in opens:
        pretty_open.append({k: (round(t[k], 5) if isinstance(t.get(k), float) else t.get(k)) for k in [c["id"] for c in open_cols]})
    return kpis, fig, pretty_open, open_cols, idea_rows, idea_cols


if __name__ == "__main__":
    print("PAPER پیش‌فرض است. برای سفارش تست‌نت: BYBIT_API_KEY / BYBIT_API_SECRET و LIVE_ORDERS=1")
    app.run(host="127.0.0.1", port=8061, debug=False)
