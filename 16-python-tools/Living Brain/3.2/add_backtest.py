#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_standalone.py
بک‌تست مستقل ۱۰۰۰۰ کندلی برای Bybit USDT Perpetual
خروجی: رشد حساب، وین‌ریت، آمار تفکیکی هر ارز، معاملات
"""

try:
    import sys
    import time
    import threading
    import traceback
    import numpy as np
    import requests
    import plotly.graph_objects as go
    from dash import Dash, dcc, html, Input, Output, State, ctx
except Exception:
    print("❌ کتابخانه‌های لازم نصب نیستند.")
    print("نصب:")
    print("pip install dash plotly numpy requests")
    traceback.print_exc()
    input("\nPress Enter to exit...")
    raise SystemExit

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="ignore")
except Exception:
    pass


# ═══════════════════════ Config ═══════════════════════
class config:
    INITIAL_CAPITAL = 500.0
    TAKER_FEE = 0.00055
    MAX_CONCURRENT_POSITIONS = 5
    TRAIL_START_R = 1.0
    TRAIL_KEEP_RATIO = 0.6


TRADING_MODES = {
    "swing": {
        "label": "🎯 سویینگ (لوریج ۱۰)",
        "leverage": 10,
        "tp_mult": 3.0,
        "sl_mult": 1.4,
        "conviction_threshold": 0.38,
        "decision_interval": 4,
        "use_geometry": True,
        "margin_fraction": 0.6,
        "trail_start_r": 1.0,
        "trail_keep_ratio": 0.6,
    },
    "scalp": {
        "label": "⚡ اسکالپ (لوریج ۲۰)",
        "leverage": 20,
        "tp_mult": 1.3,
        "sl_mult": 0.9,
        "conviction_threshold": 0.26,
        "decision_interval": 2,
        "use_geometry": False,
        "margin_fraction": 0.4,
        "trail_start_r": 0.6,
        "trail_keep_ratio": 0.5,
    },
}


# ═══════════════════════ Helpers ═══════════════════════
def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else (hi if x > hi else x)


def safe_div(a, b, default=0.0):
    return a / b if abs(b) > 1e-12 else default


def fmt_num(v, d=2):
    try:
        return f"{float(v):,.{d}f}"
    except Exception:
        return "—"


def style_fig(fig):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(2,6,23,0.35)",
        font={"family": "Tahoma", "color": "#cbd5e1", "size": 11},
        margin=dict(l=42, r=12, t=35, b=28),
        xaxis=dict(gridcolor="rgba(148,163,184,.10)", zeroline=False),
        yaxis=dict(gridcolor="rgba(148,163,184,.10)", zeroline=False),
        showlegend=False,
    )
    return fig


def stat_box(label, value, color="#e2e8f0"):
    return html.Div(
        style={
            "background": "rgba(2,6,23,.55)",
            "border": "1px solid rgba(148,163,184,.18)",
            "borderRadius": "12px",
            "padding": "10px",
        },
        children=[
            html.Div(value, style={"fontWeight": 800, "fontSize": 17, "color": color}),
            html.Div(label, style={"fontSize": 11, "color": "#94a3b8", "marginTop": 3}),
        ],
    )


# ═══════════════════════ Bybit HTTP ═══════════════════════
BYBIT_DOMAINS = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]


class BybitHTTP:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.bybit.com/",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self.active = BYBIT_DOMAINS[0]
        self.last_error = None

    def get(self, path, params, timeout=8):
        cands = [self.active] + [d for d in BYBIT_DOMAINS if d != self.active]
        for base in cands:
            try:
                r = self.session.get(f"{base}{path}", params=params, timeout=timeout)
                if r.status_code in (403, 451):
                    continue
                r.raise_for_status()
                d = r.json()
                if d.get("retCode") == 0:
                    self.active = base
                    return d
            except Exception as e:
                self.last_error = f"{base.split('//')[1]}: {type(e).__name__}"
                continue
        return None


# ═══════════════════════ Raw Analyzer ═══════════════════════
class RawPriceAnalyzer:
    def __init__(self):
        self.prev_velocity = {}

    def analyze(self, o, h, l, c, key=""):
        if c is None or len(c) < 12:
            return {"ready": False}
        n = len(c)
        ret_last = safe_div(c[-1] - c[-2], c[-2])
        prev_v = self.prev_velocity.get(key, 0.0)
        velocity = clamp(ret_last * 200.0, -2, 2)
        self.prev_velocity[key] = velocity

        streak = 0
        direction = 0
        for i in range(n - 1, max(0, n - 12), -1):
            d = 1 if c[i] >= o[i] else -1
            if direction == 0:
                direction = d
                streak = 1
            elif d == direction:
                streak += 1
            else:
                break
        trend_strength = clamp(streak / 8.0, 0, 1) * direction

        recent = min(20, n)
        ranges = h[-recent:] - l[-recent:]
        volatility = float(np.mean(ranges))

        body_last = abs(c[-1] - o[-1])
        range_last = max(h[-1] - l[-1], 1e-9)
        body_ratio = body_last / range_last
        upper_wick = safe_div(h[-1] - max(c[-1], o[-1]), range_last)
        lower_wick = safe_div(min(c[-1], o[-1]) - l[-1], range_last)

        is_strong_bull = (c[-1] > o[-1]) and (body_ratio > 0.6)
        is_strong_bear = (c[-1] < o[-1]) and (body_ratio > 0.6)
        bull_rejection = lower_wick > 0.5 and lower_wick > upper_wick * 1.5
        bear_rejection = upper_wick > 0.5 and upper_wick > lower_wick * 1.5

        lookback = min(60, n)
        resistance = float(h[-lookback:].max())
        support = float(l[-lookback:].min())
        pos_in_range = safe_div(c[-1] - support, resistance - support, 0.5)

        signal = 0.0
        signal += velocity * 0.35
        signal += trend_strength * 0.30
        if is_strong_bull:
            signal += 0.25
        if is_strong_bear:
            signal -= 0.25
        if bull_rejection:
            signal += 0.20
        if bear_rejection:
            signal -= 0.20
        if pos_in_range > 0.9:
            signal -= 0.15
        elif pos_in_range < 0.1:
            signal += 0.15

        signal = clamp(signal, -1.5, 1.5)
        return {
            "ready": True,
            "price": float(c[-1]),
            "signal": float(signal),
            "conviction": clamp(abs(signal), 0, 1),
            "velocity": float(velocity),
            "volatility": float(volatility),
        }


# ═══════════════════════ Geometry Analyzer ═══════════════════════
class GeometryAnalyzer:
    GOLDEN = 0.618

    def find_swings(self, h, l, window=3):
        n = len(h)
        highs = []
        lows = []
        for i in range(window, n - window):
            if h[i] == max(h[i - window:i + window + 1]):
                highs.append(float(h[i]))
            if l[i] == min(l[i - window:i + window + 1]):
                lows.append(float(l[i]))
        return highs, lows

    def fib_levels(self, high, low):
        diff = high - low
        return {
            "0.0(High)": high,
            "0.382": high - diff * 0.382,
            "0.5": high - diff * 0.5,
            "0.618": high - diff * self.GOLDEN,
            "1.0(Low)": low,
        }

    def analyze(self, o, h, l, c):
        if c is None or len(c) < 20:
            return {"ready": False, "levels": {}, "trend": 0}
        highs, lows = self.find_swings(h, l, window=3)
        if not highs or not lows:
            return {"ready": False, "levels": {}, "trend": 0}
        recent_high = max(highs[-3:])
        recent_low = min(lows[-3:])
        levels = self.fib_levels(recent_high, recent_low)
        trend = 0
        if len(highs) >= 2 and len(lows) >= 2:
            hh = highs[-1] > highs[-2]
            hl = lows[-1] > lows[-2]
            lh = highs[-1] < highs[-2]
            ll = lows[-1] < lows[-2]
            if hh and hl:
                trend = 1
            elif lh and ll:
                trend = -1
        return {"ready": True, "levels": levels, "trend": trend}


# ═══════════════════════ Backtest Runner ═══════════════════════
class BacktestRunner:
    def __init__(self, http):
        self.http = http
        self.lock = threading.RLock()
        self.thread = None
        self.state = {
            "status": "idle",
            "progress": 0,
            "message": "آماده برای بک‌تست ۱۰۰۰۰ کندلی",
            "results": None,
        }

    def _set(self, **kwargs):
        with self.lock:
            self.state.update(kwargs)

    def start(self, n_candles=10000, interval="15", mode="swing", n_coins=5):
        if self.thread and self.thread.is_alive():
            return False
        n_candles = max(1000, min(10000, int(n_candles or 10000)))
        n_coins = max(1, min(10, int(n_coins or 5)))
        if mode not in TRADING_MODES:
            mode = "swing"
        if interval not in ("15", "60", "240", "D"):
            interval = "15"
        self.thread = threading.Thread(
            target=self._run,
            args=(n_candles, interval, mode, n_coins),
            daemon=True,
        )
        self.thread.start()
        return True

    def _symbols(self, n_coins):
        try:
            d = self.http.get("/v5/market/tickers", {"category": "linear"}, timeout=8)
            if d:
                lst = d.get("result", {}).get("list", [])
                rows = []
                for t in lst:
                    sym = t.get("symbol", "")
                    if not sym.endswith("USDT"):
                        continue
                    try:
                        turnover = float(t.get("turnover24h") or 0)
                    except Exception:
                        turnover = 0
                    if turnover <= 0:
                        continue
                    rows.append({"symbol": sym, "turnover": turnover})
                rows.sort(key=lambda x: -x["turnover"])
                if rows:
                    return [r["symbol"] for r in rows[:max(1, int(n_coins))]]
        except Exception:
            pass
        fallback = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
                    "BNBUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"]
        return fallback[:max(1, int(n_coins))]

    def _fetch_history(self, symbol, n_candles, interval):
        rows = []
        end = None
        while len(rows) < n_candles:
            limit = min(1000, n_candles - len(rows))
            params = {
                "category": "linear",
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            }
            if end:
                params["end"] = end
            d = self.http.get("/v5/market/kline", params, timeout=10)
            if not d:
                break
            lst = (d.get("result") or {}).get("list") or []
            if not lst:
                break
            batch = []
            for x in lst:
                try:
                    batch.append({
                        "ts": int(x[0]),
                        "o": float(x[1]),
                        "h": float(x[2]),
                        "l": float(x[3]),
                        "c": float(x[4]),
                        "v": float(x[5]),
                    })
                except Exception:
                    pass
            if not batch:
                break
            rows.extend(batch)
            end = min(r["ts"] for r in batch) - 1
            self._set(
                message=f"دریافت {symbol} | {len(rows)} کندل",
                progress=int(min(45, 5 + 45 * len(rows) / max(1, n_candles))),
            )
            if len(lst) < limit:
                break
            time.sleep(0.12)
        rows.sort(key=lambda r: r["ts"])
        return rows[-n_candles:]

    def _run(self, n_candles, interval, mode, n_coins):
        try:
            self._set(status="fetching", progress=0, message="در حال آماده‌سازی...")
            symbols = self._symbols(n_coins)
            raw = {}
            for idx, sym in enumerate(symbols):
                self._set(message=f"دریافت {sym}...")
                kl = self._fetch_history(sym, n_candles, interval)
                if len(kl) >= 150:
                    raw[sym] = kl
                self._set(progress=int(5 + 45 * (idx + 1) / max(1, len(symbols))))

            if not raw:
                self._set(status="error", message="داده‌ای از بایبیت دریافت نشد.")
                return

            ts_sets = [set(k["ts"] for k in v) for v in raw.values()]
            common = sorted(set.intersection(*ts_sets))[-n_candles:]
            if len(common) < 150:
                self._set(status="error", message="کندل‌های هم‌زمان کافی پیدا نشد.")
                return

            data = {}
            for sym, klines in raw.items():
                idx = {k["ts"]: k for k in klines}
                data[sym] = {
                    "o": np.array([idx[t]["o"] for t in common], dtype=float),
                    "h": np.array([idx[t]["h"] for t in common], dtype=float),
                    "l": np.array([idx[t]["l"] for t in common], dtype=float),
                    "c": np.array([idx[t]["c"] for t in common], dtype=float),
                    "v": np.array([idx[t]["v"] for t in common], dtype=float),
                }

            mp = TRADING_MODES[mode]
            capital = config.INITIAL_CAPITAL
            equity_curve = []
            trades = []
            open_pos = {}
            per_coin = {
                sym: {
                    "trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "pnl": 0.0,
                    "fees": 0.0,
                    "margin_used": 0.0,
                }
                for sym in data
            }
            analyzers = {sym: RawPriceAnalyzer() for sym in data}
            geometries = {sym: GeometryAnalyzer() for sym in data}
            warmup = 130

            debug = {
                "signals": 0,
                "candidates": 0,
                "blocked_cost": 0,
                "blocked_ev": 0,
                "entries": 0,
            }

            entry_threshold = max(0.16, float(mp.get("conviction_threshold", 0.35)) * 0.50)
            decision_interval = max(1, int(mp.get("decision_interval", 2)))
            entry_cost_check = config.TAKER_FEE + 0.00003
            adaptive_point = warmup + max(50, (len(common) - warmup) // 4)

            def close_pos(sym, exit_price, reason, ts):
                nonlocal capital
                if sym not in open_pos:
                    return
                pos = open_pos.pop(sym)
                gross = (exit_price - pos["entry"]) * pos["side"] * pos["size"]
                close_fee = exit_price * pos["size"] * config.TAKER_FEE
                net_total = gross - close_fee - pos["open_cost"]
                capital += gross - close_fee
                st = per_coin[sym]
                st["trades"] += 1
                st["pnl"] += net_total
                st["fees"] += pos["open_cost"] + close_fee
                if net_total > 0:
                    st["wins"] += 1
                else:
                    st["losses"] += 1
                trades.append({
                    "time": time.strftime("%m-%d %H:%M", time.gmtime(ts / 1000)),
                    "coin": sym,
                    "side": pos["side"],
                    "entry": pos["entry"],
                    "exit": exit_price,
                    "reason": reason,
                    "pnl": net_total,
                    "roi": safe_div(net_total, pos["margin"]) * 100,
                })

            for i in range(warmup, len(common)):
                # Exits
                for sym in list(open_pos.keys()):
                    h = data[sym]["h"][i]
                    l = data[sym]["l"][i]
                    c = data[sym]["c"][i]
                    pos = open_pos[sym]

                    if pos["side"] > 0:
                        pos["peak"] = max(pos.get("peak", pos["entry"]), h)
                    else:
                        pos["peak"] = min(pos.get("peak", pos["entry"]), l)

                    init_r = abs(pos["entry"] - pos["initial_sl"])
                    if init_r > 1e-12:
                        cur_r = (c - pos["entry"]) * pos["side"] / init_r
                        if cur_r >= pos["trail_start_r"]:
                            trail_r = min(cur_r - 0.5, cur_r * pos["trail_keep_ratio"])
                            if pos["side"] > 0:
                                new_sl = pos["entry"] + trail_r * init_r
                                if new_sl > pos["sl"]:
                                    pos["sl"] = new_sl
                                    pos["trailed"] = True
                            else:
                                new_sl = pos["entry"] - trail_r * init_r
                                if new_sl < pos["sl"]:
                                    pos["sl"] = new_sl
                                    pos["trailed"] = True

                    exit_price = None
                    reason = None
                    if pos["side"] > 0:
                        if l <= pos["sl"]:
                            exit_price = pos["sl"]
                            reason = "Trail SL" if pos.get("trailed") else "SL"
                        elif h >= pos["tp"]:
                            exit_price = pos["tp"]
                            reason = "TP"
                    else:
                        if h >= pos["sl"]:
                            exit_price = pos["sl"]
                            reason = "Trail SL" if pos.get("trailed") else "SL"
                        elif l <= pos["tp"]:
                            exit_price = pos["tp"]
                            reason = "TP"

                    if exit_price is not None:
                        close_pos(sym, exit_price, reason, common[i])

                unreal = 0.0
                for sym, pos in open_pos.items():
                    unreal += (data[sym]["c"][i] - pos["entry"]) * pos["side"] * pos["size"]
                equity_curve.append(capital + unreal)

                if capital <= 1:
                    continue

                # Entries
                if i % decision_interval == 0 and len(open_pos) < config.MAX_CONCURRENT_POSITIONS:
                    effective_threshold = entry_threshold
                    if debug["entries"] == 0 and i > adaptive_point:
                        effective_threshold = entry_threshold * 0.75

                    candidates = []
                    for sym in data:
                        if sym in open_pos:
                            continue
                        st = max(0, i - 119)
                        o = data[sym]["o"][st:i + 1]
                        h = data[sym]["h"][st:i + 1]
                        l = data[sym]["l"][st:i + 1]
                        c = data[sym]["c"][st:i + 1]
                        an = analyzers[sym].analyze(o, h, l, c, key=sym)
                        if not an.get("ready"):
                            continue
                        sig = an.get("signal", 0.0)
                        if abs(sig) < 0.03:
                            continue
                        debug["signals"] += 1

                        conviction = clamp(abs(sig) * 1.75, 0, 1)
                        geom = geometries[sym].analyze(o, h, l, c)
                        if mp.get("use_geometry") and geom.get("ready"):
                            price = float(c[-1])
                            trend = geom.get("trend", 0)
                            side = 1 if sig > 0 else -1
                            for lvl in (geom.get("levels") or {}).values():
                                try:
                                    if price > 0 and abs(price - float(lvl)) / price < 0.0045 and trend == side:
                                        conviction = clamp(conviction + 0.20, 0, 1)
                                        break
                                except Exception:
                                    pass

                        if conviction >= effective_threshold:
                            debug["candidates"] += 1
                            candidates.append((conviction, sym, sig, an))

                    candidates.sort(key=lambda x: -x[0])

                    for conviction, sym, sig, an in candidates:
                        if len(open_pos) >= config.MAX_CONCURRENT_POSITIONS:
                            break

                        price = float(data[sym]["c"][i])
                        side = 1 if sig > 0 else -1
                        vol = max(float(an.get("volatility", 0.0)), price * 0.00085)
                        tp = price + side * vol * mp.get("tp_mult", 2.0)
                        sl = price - side * vol * mp.get("sl_mult", 1.0)

                        max_sl_dist = price * (0.8 / mp.get("leverage", 10))
                        if abs(sl - price) > max_sl_dist:
                            sl = price - side * max_sl_dist

                        tp_dist = safe_div(abs(tp - price), price, 0)
                        sl_dist = safe_div(abs(sl - price), price, 0)
                        if sl_dist <= 0 or tp_dist <= 0:
                            debug["blocked_cost"] += 1
                            continue

                        ev = conviction * tp_dist - (1 - conviction) * sl_dist - entry_cost_check
                        if tp_dist < entry_cost_check * 0.65:
                            debug["blocked_cost"] += 1
                            continue

                        ev_floor = 0.0
                        if debug["entries"] == 0 and i > adaptive_point:
                            ev_floor = -entry_cost_check * 0.35

                        if ev <= ev_floor:
                            debug["blocked_ev"] += 1
                            continue

                        used_margin = sum(p["margin"] for p in open_pos.values())
                        available = capital - used_margin
                        slots_left = max(1, config.MAX_CONCURRENT_POSITIONS - len(open_pos))
                        margin = min(available * float(mp.get("margin_fraction", 0.5)) / slots_left, available)
                        if margin < 5:
                            continue

                        notional = margin * mp.get("leverage", 10)
                        size = notional / price
                        open_fee = notional * config.TAKER_FEE
                        spread_cost = price * 0.00025 * size
                        open_cost = open_fee + spread_cost

                        if capital - open_cost < 1:
                            continue

                        capital -= open_cost
                        open_pos[sym] = {
                            "side": side,
                            "entry": price,
                            "size": size,
                            "margin": margin,
                            "tp": tp,
                            "sl": sl,
                            "initial_sl": sl,
                            "open_cost": open_cost,
                            "peak": price,
                            "trailed": False,
                            "trail_start_r": mp.get("trail_start_r", config.TRAIL_START_R),
                            "trail_keep_ratio": mp.get("trail_keep_ratio", config.TRAIL_KEEP_RATIO),
                        }
                        per_coin[sym]["margin_used"] += margin
                        debug["entries"] += 1

                self._set(
                    status="running",
                    progress=int(50 + 50 * i / max(1, len(common) - 1)),
                    message=(
                        f"شبیه‌سازی {len(common)} کندل | "
                        f"سیگنال:{debug['signals']} کاندید:{debug['candidates']} "
                        f"ورود:{debug['entries']}"
                    ),
                )

            # Close remaining
            for sym in list(open_pos.keys()):
                close_pos(sym, float(data[sym]["c"][-1]), "End", common[-1])

            equity_curve.append(capital)

            peak_eq = equity_curve[0] if equity_curve else capital
            max_dd = 0.0
            for eq in equity_curve:
                if eq > peak_eq:
                    peak_eq = eq
                dd = safe_div(peak_eq - eq, peak_eq, 0)
                if dd > max_dd:
                    max_dd = dd

            total_trades = len(trades)
            wins = sum(1 for t in trades if t["pnl"] > 0)
            losses = total_trades - wins
            win_rate = safe_div(wins, total_trades) * 100
            gw = sum(t["pnl"] for t in trades if t["pnl"] > 0)
            gl = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
            if gl > 0:
                pf = gw / gl
            else:
                pf = 99.0 if gw > 0 else 0.0

            final_equity = equity_curve[-1] if equity_curve else capital
            step = max(1, len(equity_curve) // 1200)

            per_coin_out = {}
            alloc = config.INITIAL_CAPITAL / max(1, len(per_coin))
            for sym, st in per_coin.items():
                denom = st["margin_used"] if st["margin_used"] > 0 else alloc
                per_coin_out[sym] = {
                    **st,
                    "win_rate": safe_div(st["wins"], st["trades"]) * 100,
                    "roi": safe_div(st["pnl"], denom) * 100,
                }

            results = {
                "initial_capital": config.INITIAL_CAPITAL,
                "final_equity": final_equity,
                "roi_pct": safe_div(final_equity - config.INITIAL_CAPITAL, config.INITIAL_CAPITAL) * 100,
                "total_pnl": final_equity - config.INITIAL_CAPITAL,
                "total_trades": total_trades,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "profit_factor": pf,
                "max_drawdown": max_dd * 100,
                "equity_curve": equity_curve[::step],
                "per_coin": per_coin_out,
                "closed_trades": trades[-120:][::-1],
                "symbols": list(data.keys()),
                "n_candles": len(common),
                "mode": mode,
                "interval": interval,
                "debug": debug,
            }

            if total_trades == 0:
                message = (
                    f"⚠️ هنوز معامله‌ای باز نشد | "
                    f"سیگنال:{debug['signals']} کاندید:{debug['candidates']} "
                    f"block_cost:{debug['blocked_cost']} block_ev:{debug['blocked_ev']}"
                )
            else:
                message = f"پایان بک‌تست: {total_trades} معامله | وین‌ریت {win_rate:.1f}٪"

            self._set(status="done", progress=100, message=message, results=results)

        except Exception as e:
            traceback.print_exc()
            self._set(status="error", progress=0, message=f"خطا در بک‌تست: {e}")


BACKTEST_RUNNER = BacktestRunner(BybitHTTP())


# ═══════════════════════ Dash UI ═══════════════════════
app = Dash(__name__, title="Backtest 10000")

panel_style = {
    "background": "rgba(15,23,42,.82)",
    "border": "1px solid rgba(99,102,241,.25)",
    "borderRadius": "16px",
    "padding": "16px",
    "marginBottom": "14px",
}

app.layout = html.Div(
    dir="rtl",
    style={
        "minHeight": "100vh",
        "background": "radial-gradient(1200px 800px at 80% -10%, #1e1b4b 0%, #0b1120 55%, #020617 100%)",
        "color": "#e2e8f0",
        "fontFamily": "Tahoma",
        "padding": "20px",
    },
    children=[
        html.Div(style=panel_style, children=[
            html.H2("🧪 بک‌تست مستقل ۱۰۰۰۰ کندلی", style={"color": "#c7d2fe"}),
            html.Div("اگر معامله باز نشد، وضعیت پایین صفحه تعداد سیگنال/کاندید/دلیل بلاک را نشان می‌دهد.",
                     style={"fontSize": 12, "color": "#94a3b8"}),
            html.Div(style={"display": "flex", "flexWrap": "wrap", "gap": "10px", "marginTop": "12px"}, children=[
                dcc.Dropdown(
                    id="bt-mode",
                    options=[{"label": v["label"], "value": k} for k, v in TRADING_MODES.items()],
                    value="swing",
                    clearable=False,
                    style={"width": 210, "fontSize": 12},
                ),
                dcc.Dropdown(
                    id="bt-interval",
                    options=[
                        {"label": "15 دقیقه", "value": "15"},
                        {"label": "1 ساعت", "value": "60"},
                        {"label": "4 ساعت", "value": "240"},
                    ],
                    value="15",
                    clearable=False,
                    style={"width": 120, "fontSize": 12},
                ),
                dcc.Input(id="bt-candles", type="number", value=10000, min=1000, max=10000, step=1000,
                          style={"width": 110}),
                dcc.Input(id="bt-coins", type="number", value=5, min=1, max=10, style={"width": 80}),
                html.Button("🚀 شروع بک‌تست", id="btn-start-backtest", n_clicks=0,
                            style={"padding": "8px 16px", "cursor": "pointer"}),
            ]),
            html.Progress(id="bt-progress", value=0, max=100, style={"width": "100%", "marginTop": "12px"}),
            html.Div(id="bt-status", style={"marginTop": "8px", "fontSize": 13, "color": "#34d399"}),
        ]),

        html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(12,1fr)", "gap": "14px"}, children=[
            html.Div(style={**panel_style, "gridColumn": "span 4"}, children=[
                html.H3("🏆 آمار کامل حساب", style={"color": "#c7d2fe"}),
                html.Div(id="bt-overall", style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"}),
            ]),
            html.Div(style={**panel_style, "gridColumn": "span 8"}, children=[
                html.H3("📈 نمودار رشد سرمایه", style={"color": "#c7d2fe"}),
                dcc.Graph(id="bt-equity", config={"displayModeBar": False}, style={"height": 280}),
            ]),
        ]),

        html.Div(style={"display": "grid", "gridTemplateColumns": "repeat(12,1fr)", "gap": "14px"}, children=[
            html.Div(style={**panel_style, "gridColumn": "span 7"}, children=[
                html.H3("📊 ریز عملکرد هر ارز", style={"color": "#c7d2fe"}),
                html.Div(id="bt-coin-table", style={"maxHeight": 360, "overflowY": "auto"}),
            ]),
            html.Div(style={**panel_style, "gridColumn": "span 5"}, children=[
                html.H3("📜 آخرین معاملات", style={"color": "#c7d2fe"}),
                html.Div(id="bt-trades", style={"maxHeight": 360, "overflowY": "auto"}),
            ]),
        ]),

        dcc.Interval(id="bt-clock", interval=1000, n_intervals=0),
    ],
)


@app.callback(
    [
        Output("bt-progress", "value"),
        Output("bt-status", "children"),
        Output("bt-overall", "children"),
        Output("bt-equity", "figure"),
        Output("bt-coin-table", "children"),
        Output("bt-trades", "children"),
    ],
    Input("bt-clock", "n_intervals"),
    Input("btn-start-backtest", "n_clicks"),
    State("bt-mode", "value"),
    State("bt-interval", "value"),
    State("bt-candles", "value"),
    State("bt-coins", "value"),
    prevent_initial_call=False,
)
def bt_update(n_intervals, n_clicks, mode, interval, candles, coins):
    triggered = ""
    try:
        triggered = ctx.triggered_id
    except Exception:
        try:
            triggered = ctx.triggered[0]["prop_id"].split(".")[0]
        except Exception:
            triggered = ""

    if triggered == "btn-start-backtest" and n_clicks:
        try:
            BACKTEST_RUNNER.start(
                int(candles or 10000),
                interval or "15",
                mode or "swing",
                int(coins or 5),
            )
        except Exception:
            pass

    with BACKTEST_RUNNER.lock:
        status = BACKTEST_RUNNER.state.get("status", "idle")
        progress = int(BACKTEST_RUNNER.state.get("progress", 0))
        message = BACKTEST_RUNNER.state.get("message", "")
        results = BACKTEST_RUNNER.state.get("results")

    fig = go.Figure()
    style_fig(fig)
    overall = [html.Div("برای شروع، دکمه «شروع بک‌تست» را بزنید.", style={"color": "#94a3b8"})]
    coin_table = html.Div("—", style={"color": "#94a3b8"})
    trades_div = html.Div("—", style={"color": "#94a3b8"})

    if status == "error":
        overall = [html.Div(message, style={"color": "#f87171"})]

    if results:
        roi_color = "#4ade80" if results.get("roi_pct", 0) >= 0 else "#f87171"
        pf = results.get("profit_factor", 0)
        pf_txt = f"{pf:.2f}" if pf < 90 else "∞"

        overall = [
            stat_box("سرمایه اولیه", f"{fmt_num(results.get('initial_capital', 0))}$"),
            stat_box("سرمایه نهایی", f"{fmt_num(results.get('final_equity', 0))}$", roi_color),
            stat_box("رشد حساب (ROI)", f"{results.get('roi_pct', 0):+.2f}٪", roi_color),
            stat_box("سود/زیان خالص", f"{fmt_num(results.get('total_pnl', 0))}$", roi_color),
            stat_box("وین‌ریت", f"{results.get('win_rate', 0):.1f}٪"),
            stat_box("تعداد معاملات", f"{results.get('total_trades', 0)}"),
            stat_box("برد / باخت", f"{results.get('wins', 0)}W / {results.get('losses', 0)}L"),
            stat_box("Profit Factor", pf_txt),
            stat_box("حداکثر افت", f"{results.get('max_drawdown', 0):.1f}٪", "#f87171"),
            stat_box("کندل هم‌زمان", f"{results.get('n_candles', 0)}"),
            stat_box("تعداد ارزها", f"{len(results.get('symbols', []))}"),
            stat_box("حالت", TRADING_MODES.get(results.get("mode", "swing"), {}).get("label", "—")),
        ]

        fig = go.Figure()
        fig.add_scatter(
            y=results.get("equity_curve", []),
            line=dict(color="#4ade80", width=2),
            fill="tozeroy",
            fillcolor="rgba(74,222,128,.12)",
        )
        style_fig(fig)
        fig.update_layout(title="نمودار رشد سرمایه")

        header = html.Tr([
            html.Th("ارز"), html.Th("معاملات"), html.Th("وین‌ریت"), html.Th("برد/باخت"),
            html.Th("PnL خالص"), html.Th("ROI مارجین"), html.Th("کارمزد"),
        ], style={"color": "#94a3b8"})

        rows = []
        for sym, st in results.get("per_coin", {}).items():
            wr = st.get("win_rate", 0)
            pnl = st.get("pnl", 0)
            roi = st.get("roi", 0)
            wr_color = "#4ade80" if wr >= 50 else "#fbbf24"
            pnl_color = "#4ade80" if pnl >= 0 else "#f87171"
            rows.append(html.Tr([
                html.Td(sym, style={"fontWeight": "bold", "color": "#fbbf24"}),
                html.Td(st.get("trades", 0)),
                html.Td(f"{wr:.1f}٪", style={"color": wr_color}),
                html.Td(f"{st.get('wins', 0)}W / {st.get('losses', 0)}L"),
                html.Td(f"{pnl:+.2f}$", style={"color": pnl_color, "fontWeight": "bold"}),
                html.Td(f"{roi:+.1f}٪", style={"color": pnl_color}),
                html.Td(f"{fmt_num(st.get('fees', 0))}$", style={"color": "#94a3b8"}),
            ], style={"borderBottom": "1px solid rgba(148,163,184,.12)"}))

        coin_table = html.Table([html.Thead(header), html.Tbody(rows)],
                                style={"width": "100%", "borderCollapse": "collapse", "fontSize": 12}) if rows else \
            html.Div("هیچ معامله‌ای ثبت نشد.", style={"color": "#94a3b8"})

        header2 = html.Tr([
            html.Th("زمان"), html.Th("ارز"), html.Th("جهت"), html.Th("ورود"),
            html.Th("خروج"), html.Th("دلیل"), html.Th("PnL"),
        ], style={"color": "#94a3b8"})

        rows2 = []
        for t in results.get("closed_trades", []):
            pnl = t.get("pnl", 0)
            pnl_color = "#4ade80" if pnl >= 0 else "#f87171"
            side_txt = "🟢" if t.get("side", 1) > 0 else "🔴"
            rows2.append(html.Tr([
                html.Td(t.get("time", "—"), style={"fontSize": 10}),
                html.Td(t.get("coin", "—"), style={"fontWeight": "bold", "color": "#fbbf24"}),
                html.Td(side_txt),
                html.Td(fmt_num(t.get("entry", 0), 4)),
                html.Td(fmt_num(t.get("exit", 0), 4)),
                html.Td(t.get("reason", "—"), style={"fontSize": 10}),
                html.Td(f"{pnl:+.2f}$", style={"color": pnl_color, "fontWeight": "bold"}),
            ], style={"borderBottom": "1px solid rgba(148,163,184,.12)"}))

        trades_div = html.Table([html.Thead(header2), html.Tbody(rows2)],
                                style={"width": "100%", "borderCollapse": "collapse", "fontSize": 12}) if rows2 else \
            html.Div("لیست معاملات خالی است.", style={"color": "#94a3b8"})

    return progress, message, overall, fig, coin_table, trades_div


if __name__ == "__main__":
    print("Starting standalone backtest dashboard...")
    print("Open: http://127.0.0.1:8071")
    try:
        app.run(debug=False, host="127.0.0.1", port=8071, use_reloader=False)
    except Exception:
        traceback.print_exc()
        input("\nPress Enter to exit...")