# -*- coding: utf-8 -*-
"""
Morindok Signal Engine
========================
موتور تولید سیگنال معاملاتی، مدیریت باز/بسته شدن سیگنال بر اساس
حد سود/ضرر، و محاسبه‌ی آمار وین‌ریت. داده‌ها در SQLite ذخیره می‌شوند
تا با ری‌استارت برنامه از بین نروند.
"""

import sqlite3
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import bybit_engine as be

DB_PATH = "morindok_signals.db"


def _conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry REAL NOT NULL,
            sl REAL NOT NULL,
            tp REAL NOT NULL,
            leverage REAL NOT NULL,
            reasons TEXT,
            opened_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            closed_at TEXT,
            close_price REAL,
            result TEXT,
            pnl_r REAL
        )
    """)
    c.commit()
    return c


def has_open_signal(symbol: str) -> bool:
    with _conn() as c:
        cur = c.execute("SELECT COUNT(*) FROM signals WHERE symbol=? AND status='OPEN'", (symbol,))
        return cur.fetchone()[0] > 0


def create_signal(symbol, side, entry, sl, tp, leverage, reasons: str):
    with _conn() as c:
        c.execute("""
            INSERT INTO signals (symbol, side, entry, sl, tp, leverage, reasons, opened_at, status)
            VALUES (?,?,?,?,?,?,?,?, 'OPEN')
        """, (symbol, side, entry, sl, tp, leverage, reasons,
              datetime.now(timezone.utc).isoformat()))
        c.commit()


def get_open_signals(symbol=None) -> pd.DataFrame:
    q = "SELECT * FROM signals WHERE status='OPEN'"
    params = ()
    if symbol:
        q += " AND symbol=?"
        params = (symbol,)
    with _conn() as c:
        return pd.read_sql_query(q, c, params=params)


def get_closed_signals(symbol=None) -> pd.DataFrame:
    q = "SELECT * FROM signals WHERE status='CLOSED'"
    params = ()
    if symbol:
        q += " AND symbol=?"
        params = (symbol,)
    with _conn() as c:
        return pd.read_sql_query(q, c, params=params)


def close_signal(signal_id, close_price, result, pnl_r):
    with _conn() as c:
        c.execute("""
            UPDATE signals SET status='CLOSED', closed_at=?, close_price=?, result=?, pnl_r=?
            WHERE id=?
        """, (datetime.now(timezone.utc).isoformat(), close_price, result, pnl_r, signal_id))
        c.commit()


def check_and_close_open_signals():
    """بررسی سیگنال‌های باز و بستن آن‌ها در صورت برخورد قیمت با SL/TP"""
    open_df = get_open_signals()
    if open_df.empty:
        return
    for _, row in open_df.iterrows():
        last_price = be.get_last_price(row["symbol"])
        if last_price <= 0:
            continue
        side = row["side"]
        entry, sl, tp = row["entry"], row["sl"], row["tp"]
        risk = abs(entry - sl)
        if risk == 0:
            continue
        hit_tp = (side == "خرید (Long)" and last_price >= tp) or \
                 (side == "فروش (Short)" and last_price <= tp)
        hit_sl = (side == "خرید (Long)" and last_price <= sl) or \
                 (side == "فروش (Short)" and last_price >= sl)
        if hit_tp:
            reward = abs(tp - entry)
            close_signal(row["id"], last_price, "WIN", round(reward / risk, 2))
        elif hit_sl:
            close_signal(row["id"], last_price, "LOSS", -1.0)


# ----------------------------------------------------------------------------
# تولید سیگنال بر اساس ترکیب قدرت چند تایم‌فریمی + جریان پول + وضعیت حجم
# ----------------------------------------------------------------------------
def composite_power_score(stream, symbol: str) -> tuple:
    """
    نمره‌ی ترکیبی قدرت خریدار/فروشنده روی همه‌ی تایم‌فریم‌ها؛ تایم‌فریم‌های
    بالاتر وزن بیشتری دارند تا تاثیر کاسکید بالا -> پایین شبیه‌سازی شود.
    خروجی: (نمره‌ی نهایی -100..100, دیکشنری جزئیات هر تایم‌فریم)
    """
    total_w, total_score = 0.0, 0.0
    details = {}
    for tf_code, tf_label, tf_minutes in be.TIMEFRAMES:
        tdf = stream.get_trades_df(symbol)
        span = stream.buffer_span_minutes(symbol)
        if not tdf.empty and span >= tf_minutes * 3:
            power_df = be.compute_power_series(tdf, tf_minutes)
            source = "دقیق (تیک‌به‌تیک)"
        else:
            kdf = be.get_klines(symbol, tf_code, limit=50)
            power_df = be.estimate_power_from_kline(kdf)
            source = "تخمینی (کندل)"

        # محافظت: اگر به هر دلیلی (قطعی شبکه، پاسخ خالی از بایبیت و ...)
        # دیتافریم خالی یا بدون ستون power_pct برگردد، به جای کرش کردن
        # برنامه، آن تایم‌فریم را خنثی (۰) در نظر می‌گیریم.
        if power_df is None or power_df.empty or "power_pct" not in power_df.columns:
            details[tf_code] = {"label": tf_label, "power_pct": 0.0, "source": source}
            continue
        power_df = power_df.dropna(subset=["power_pct"])
        if power_df.empty:
            details[tf_code] = {"label": tf_label, "power_pct": 0.0, "source": source}
            continue
        last_power = float(power_df["power_pct"].iloc[-1])
        w = be.TF_WEIGHT[tf_code]
        total_w += w
        total_score += last_power * w
        details[tf_code] = {"label": tf_label, "power_pct": last_power, "source": source}

    composite = total_score / total_w if total_w > 0 else 0.0
    return composite, details


def generate_signal(stream, symbol: str):
    """
    تصمیم‌گیری تولید سیگنال جدید بر اساس:
      1) نمره‌ی ترکیبی قدرت خریدار/فروشنده روی همه‌ی تایم‌فریم‌ها
      2) جهت جریان پول ورودی از ۳۰ ارز معتبر
      3) وضعیت حجم (نباید مشکوک باشد)
    اگر شرایط برقرار بود و سیگنال بازِ دیگری برای این نماد وجود نداشت،
    سیگنال جدید در دیتابیس ثبت می‌شود.
    """
    if has_open_signal(symbol):
        return None  # تا زمانی که SL/TP قبلی نخورده، سیگنال جدید صادر نمی‌شود

    composite, details = composite_power_score(stream, symbol)

    kdf_1h = be.get_klines(symbol, "60", limit=100)
    if kdf_1h.empty:
        return None
    atr = be.compute_atr(kdf_1h, 14)
    if atr <= 0:
        return None
    last_price = float(kdf_1h["close"].iloc[-1])

    kdf_5 = be.get_klines(symbol, "5", limit=100)
    vol_df = be.analyze_volume(kdf_5) if not kdf_5.empty else pd.DataFrame()
    vol_suspicious = False
    if not vol_df.empty:
        vol_suspicious = vol_df["vol_status"].iloc[-1] == "مشکوک"

    flow_df = be.money_flow_from_top30(stream, symbol)
    inflow_score = float(flow_df["net_flow_usdt"].sum()) if not flow_df.empty else 0.0

    reasons = []
    side = None
    if composite > 15 and not vol_suspicious:
        side = "خرید (Long)"
        reasons.append(f"نمره‌ی ترکیبی قدرت خریدار در تمام تایم‌فریم‌ها مثبت است ({composite:.1f})")
        if inflow_score > 0:
            reasons.append(f"ورود خالص نقدینگی از ارزهای مرتبط ({inflow_score:,.0f} دلار)")
    elif composite < -15 and not vol_suspicious:
        side = "فروش (Short)"
        reasons.append(f"نمره‌ی ترکیبی قدرت فروشنده در تمام تایم‌فریم‌ها منفی است ({composite:.1f})")
        if inflow_score < 0:
            reasons.append(f"خروج خالص نقدینگی به سمت ارزهای دیگر ({inflow_score:,.0f} دلار)")

    if side is None:
        return None
    if vol_suspicious:
        reasons.append("⚠️ حجم مشکوک تشخیص داده شد؛ سیگنال صادر نشد")
        return None

    # تایم‌فریم‌های همسو را در دلایل ذکر کن
    aligned = [d["label"] for d in details.values()
               if (side.startswith("خرید") and d["power_pct"] > 5)
               or (side.startswith("فروش") and d["power_pct"] < -5)]
    if aligned:
        reasons.append("تایم‌فریم‌های همسو: " + "، ".join(aligned))

    volatility_pct = (atr / last_price) * 100 if last_price else 0
    leverage = max(2, min(20, round(20 / max(volatility_pct, 1.0))))

    if side.startswith("خرید"):
        sl = last_price - 1.5 * atr
        tp = last_price + 2.5 * atr
    else:
        sl = last_price + 1.5 * atr
        tp = last_price - 2.5 * atr

    reasons.append(f"ATR(14, 1h) = {atr:.4f} | نوسان = {volatility_pct:.2f}%")
    reason_text = " | ".join(reasons)

    create_signal(symbol, side, last_price, sl, tp, leverage, reason_text)
    return {
        "symbol": symbol, "side": side, "entry": last_price, "sl": sl, "tp": tp,
        "leverage": leverage, "reasons": reason_text,
    }


def winrate_stats(symbol: str) -> dict:
    closed = get_closed_signals(symbol)
    total = len(closed)
    if total == 0:
        return {"total": 0, "wins": 0, "losses": 0, "winrate": 0.0,
                "avg_rr": 0.0, "expectancy": 0.0, "profit_factor": 0.0}
    wins = closed[closed["result"] == "WIN"]
    losses = closed[closed["result"] == "LOSS"]
    winrate = (len(wins) / total) * 100
    avg_win_r = wins["pnl_r"].mean() if not wins.empty else 0.0
    avg_loss_r = losses["pnl_r"].mean() if not losses.empty else 0.0
    expectancy = (winrate / 100 * (avg_win_r or 0)) + ((1 - winrate / 100) * (avg_loss_r or 0))
    gross_win = wins["pnl_r"].sum() if not wins.empty else 0.0
    gross_loss = abs(losses["pnl_r"].sum()) if not losses.empty else 0.0
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
    return {
        "total": total, "wins": len(wins), "losses": len(losses),
        "winrate": round(winrate, 1), "avg_rr": round(avg_win_r or 0, 2),
        "expectancy": round(expectancy, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else 999.0,
    }
