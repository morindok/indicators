"""
================================================================================
 MORINDOK SCALP SNIPER PRO | Auto-Open & Smart Price Formatting
================================================================================
نسخه با باز شدن خودکار مرورگر و نمایش هوشمند قیمت‌ها (پشتیبانی کامل از شیبا و میم‌کوین‌ها)
اجرا:
    pip install dash dash-bootstrap-components plotly pandas numpy requests
    python Gannzilla.py
================================================================================
"""

import threading
import time
import traceback
import webbrowser
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc

# ==============================================================================
# CONFIG & MULTI-MIRROR CONNECTION SYSTEM
# ==============================================================================
BYBIT_BASE_CANDIDATES = [
    "https://api.bybit.com",
    "https://api.bytick.com",
    "https://api.bybit.kz",
]
CATEGORY = "spot"
TOP_N = 30  
TRADE_POLL_SEC = 3
BIN_SECONDS = 60
HISTORY_MINUTES = 60
REQUEST_TIMEOUT = 10

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
})

_ACTIVE_BASE = {"url": None}

def _bybit_get(path, params):
    candidates = [_ACTIVE_BASE["url"]] if _ACTIVE_BASE["url"] else []
    candidates += [b for b in BYBIT_BASE_CANDIDATES if b != _ACTIVE_BASE["url"]]

    last_exc = None
    for base in candidates:
        try:
            resp = SESSION.get(f"{base}{path}", params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if data.get("retCode") != 0:
                raise RuntimeError(f"Bybit API error: {data.get('retMsg')}")
            _ACTIVE_BASE["url"] = base
            return data
        except requests.exceptions.SSLError as exc:
            last_exc = f"خطای SSL روی {base}: {exc}"
        except requests.exceptions.ConnectionError as exc:
            last_exc = f"عدم دسترسی به {base} — احتمالاً بلاک است. ({exc.__class__.__name__})"
        except requests.exceptions.Timeout:
            last_exc = f"تایم‌اوت در اتصال به {base}"
        except requests.exceptions.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else "?"
            last_exc = f"HTTP {code} از {base}"
        except ValueError as exc:
            last_exc = f"پاسخ JSON نامعتبر از {base}: {exc}"
        except Exception as exc:
            last_exc = f"خطای ناشناخته روی {base}: {exc}"
    
    raise RuntimeError(last_exc or "اتصال به هیچ‌کدام از دامنه‌های بایبیت برقرار نشد")


def fetch_klines(symbol, interval, limit=100):
    data = _bybit_get("/v5/market/kline", {
        "category": CATEGORY, "symbol": symbol, "interval": interval, "limit": limit
    })
    rows = list(reversed(data["result"]["list"]))
    df = pd.DataFrame(rows, columns=["start", "open", "high", "low", "close", "volume", "turnover"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df["dt"] = pd.to_datetime(df["start"].astype(float), unit="ms")
    return df


def fetch_current_price(symbol):
    try:
        data = _bybit_get("/v5/market/tickers", {
            "category": CATEGORY, "symbol": symbol
        })
        if data["result"]["list"]:
            return float(data["result"]["list"][0].get("lastPrice", 0))
    except Exception:
        pass
    return None


def _now_minute(ts=None):
    ts = ts if ts is not None else time.time()
    return int(ts // BIN_SECONDS) * BIN_SECONDS


# ==============================================================================
# SMART PRICE FORMATTER (برای حل مشکل شیبا و میم‌کوین‌ها)
# ==============================================================================
def format_price(price):
    """نمایش هوشمند قیمت بر اساس تعداد اعشار مورد نیاز"""
    if price is None or price == 0:
        return "0.00"
    if price >= 1000:
        return f"{price:,.2f}"      # مثال: 65,000.50 (بیت‌کوین)
    elif price >= 1:
        return f"{price:,.4f}"      # مثال: 1.2345 (اتریوم)
    elif price >= 0.01:
        return f"{price:,.5f}"      # مثال: 0.01234
    elif price >= 0.001:
        return f"{price:,.6f}"      # مثال: 0.001234
    else:
        return f"{price:,.8f}"      # مثال: 0.00002543 (شیبا، پپه و...)


# ==============================================================================
# DATA STORE
# ==============================================================================
class FlowStore:
    def __init__(self):
        self.lock = threading.RLock()
        self.symbols = []
        self.last_trade_time = {}
        self.bins = defaultdict(lambda: defaultdict(lambda: {
            "buy": 0.0, "sell": 0.0, 
            "buy_count": 0, "sell_count": 0
        }))
        self.ticker_snapshot = {}
        self.status = {"connected": False, "last_update": None, "last_error": None}

    def refresh_top_symbols(self):
        try:
            data = _bybit_get("/v5/market/tickers", {"category": CATEGORY})
            usdt_rows = [r for r in data["result"]["list"] if r.get("symbol", "").endswith("USDT")]
            usdt_rows.sort(key=lambda r: float(r.get("turnover24h", 0) or 0), reverse=True)
            
            with self.lock:
                self.symbols = [r["symbol"] for r in usdt_rows[:TOP_N]]
                for r in usdt_rows[:TOP_N]:
                    self.ticker_snapshot[r["symbol"]] = {
                        "price": float(r.get("lastPrice", 0) or 0),
                        "pcnt24h": float(r.get("price24hPcnt", 0) or 0) * 100,
                    }
                self.status["connected"] = True
                self.status["last_error"] = None
                self.status["last_update"] = datetime.now(timezone.utc)
        except Exception as e:
            with self.lock:
                self.status["connected"] = False
                self.status["last_error"] = str(e)
            print(f"[refresh_top_symbols] {e}")

    def poll_trades(self, symbol):
        try:
            data = _bybit_get("/v5/market/recent-trade", {
                "category": CATEGORY, "symbol": symbol, "limit": 60
            })
            trades = data["result"]["list"]
            if not trades: return
            
            with self.lock:
                last_seen = self.last_trade_time.get(symbol, 0)
            
            for t in trades:
                t_ms = int(t.get("time", 0))
                if t_ms <= last_seen: continue
                price = float(t.get("price", 0))
                size = float(t.get("size", 0))
                side = str(t.get("side", "")).lower()
                
                minute_ts = _now_minute(t_ms / 1000.0)
                notional = price * size
                
                with self.lock:
                    bucket = self.bins[symbol][minute_ts]
                    if side == "buy":
                        bucket["buy"] += notional
                        bucket["buy_count"] += 1
                    elif side == "sell":
                        bucket["sell"] += notional
                        bucket["sell_count"] += 1
                    self.last_trade_time[symbol] = t_ms
        except Exception:
            pass

    def get_flow_stats(self, symbol, lookback_mins=30):
        with self.lock:
            bins = dict(self.bins.get(symbol, {}))
        cutoff = _now_minute() - lookback_mins * BIN_SECONDS
        
        total_buy, total_sell = 0.0, 0.0
        total_buy_count, total_sell_count = 0, 0
        recent_buy, recent_sell = 0.0, 0.0 
        recent_buy_count, recent_sell_count = 0, 0
        
        for ts, data in bins.items():
            if ts >= cutoff:
                total_buy += data["buy"]
                total_sell += data["sell"]
                total_buy_count += data["buy_count"]
                total_sell_count += data["sell_count"]
                
                if ts >= (cutoff + (lookback_mins - 5) * BIN_SECONDS):
                    recent_buy += data["buy"]
                    recent_sell += data["sell"]
                    recent_buy_count += data["buy_count"]
                    recent_sell_count += data["sell_count"]
                    
        net = total_buy - total_sell
        ratio = total_buy / (total_buy + total_sell) if (total_buy + total_sell) > 0 else 0.5
        recent_net = recent_buy - recent_sell
        
        avg_buy_size = total_buy / total_buy_count if total_buy_count > 0 else 0
        avg_sell_size = total_sell / total_sell_count if total_sell_count > 0 else 0
        power_ratio = round((avg_buy_size / avg_sell_size) * 10) / 10 if avg_sell_size > 0 else 0
        
        return {
            "net": net,
            "ratio": ratio,
            "recent_net": recent_net,
            "power_ratio": power_ratio,
            "avg_buy_size": avg_buy_size,
            "avg_sell_size": avg_sell_size,
            "total_buy_count": total_buy_count,
            "total_sell_count": total_sell_count
        }


STORE = FlowStore()


def collector_loop():
    last_refresh = 0
    while True:
        try:
            now = time.time()
            if now - last_refresh > 60 or not STORE.symbols:
                STORE.refresh_top_symbols()
                last_refresh = now
            
            for symbol in STORE.symbols:
                STORE.poll_trades(symbol)
            time.sleep(1)
        except Exception:
            traceback.print_exc()
            time.sleep(2)


threading.Thread(target=collector_loop, daemon=True).start()


# ==============================================================================
# LEVERAGE CALCULATOR
# ==============================================================================
def calculate_leverage(risk_percent, confidence, power_ratio, signal_type):
    base_leverage = 5.0
    if risk_percent > 0:
        risk_factor = min(2.0, max(0.5, 1.0 / (risk_percent * 2)))
    else:
        risk_factor = 1.0
    
    confidence_factor = 0.8 + (confidence - 70) * 0.035
    
    if signal_type == "BUY":
        power_factor = 1.0 + (power_ratio - 1.0) * 0.6 if power_ratio > 1.0 else 1.0
    else:
        power_factor = 1.0 + (1.0 - power_ratio) * 0.6 if power_ratio < 1.0 else 1.0
    
    leverage = base_leverage * risk_factor * confidence_factor * power_factor
    leverage = max(3.0, min(20.0, leverage))
    return round(leverage)


# ==============================================================================
# SIGNAL STATE MANAGER
# ==============================================================================
class SignalManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.active_signals = {}
        self.history_signals = []
    
    def add_signal(self, signal_data):
        with self.lock:
            symbol = signal_data["symbol"]
            if symbol not in self.active_signals:
                signal_data["status"] = "ACTIVE"
                signal_data["created_at"] = datetime.now(timezone.utc)
                signal_data["tp1_hit"] = False
                self.active_signals[symbol] = signal_data
                return True
        return False
    
    def check_and_update(self):
        with self.lock:
            symbols_to_check = list(self.active_signals.keys())
        
        for symbol in symbols_to_check:
            with self.lock:
                if symbol not in self.active_signals:
                    continue
                signal = self.active_signals[symbol].copy()
            
            current_price = fetch_current_price(symbol)
            if current_price is None:
                continue
            
            should_close = False
            exit_price = None
            exit_reason = None
            
            if signal["type"] == "BUY":
                if current_price <= signal["sl"]:
                    should_close = True
                    exit_price = signal["sl"]
                    exit_reason = "SL_HIT"
                elif current_price >= signal["tp2"]:
                    should_close = True
                    exit_price = signal["tp2"]
                    exit_reason = "TP2_HIT"
                elif current_price >= signal["tp1"] and not signal["tp1_hit"]:
                    with self.lock:
                        if symbol in self.active_signals:
                            self.active_signals[symbol]["tp1_hit"] = True
                            self.active_signals[symbol]["status"] = "TP1_HIT"
            else:
                if current_price >= signal["sl"]:
                    should_close = True
                    exit_price = signal["sl"]
                    exit_reason = "SL_HIT"
                elif current_price <= signal["tp2"]:
                    should_close = True
                    exit_price = signal["tp2"]
                    exit_reason = "TP2_HIT"
                elif current_price <= signal["tp1"] and not signal["tp1_hit"]:
                    with self.lock:
                        if symbol in self.active_signals:
                            self.active_signals[symbol]["tp1_hit"] = True
                            self.active_signals[symbol]["status"] = "TP1_HIT"
            
            if should_close:
                if signal["type"] == "BUY":
                    pnl_pct = (exit_price - signal["entry"]) / signal["entry"] * 100
                else:
                    pnl_pct = (signal["entry"] - exit_price) / signal["entry"] * 100
                
                leverage = signal.get("leverage", 5)
                pnl_with_leverage = pnl_pct * leverage
                
                closed_signal = signal.copy()
                closed_signal["exit_price"] = exit_price
                closed_signal["exit_reason"] = exit_reason
                closed_signal["pnl_pct"] = pnl_pct
                closed_signal["pnl_with_leverage"] = pnl_with_leverage
                closed_signal["closed_at"] = datetime.now(timezone.utc)
                
                with self.lock:
                    if symbol in self.active_signals:
                        del self.active_signals[symbol]
                    self.history_signals.append(closed_signal)
    
    def get_active_signals(self):
        with self.lock:
            return list(self.active_signals.values())
    
    def get_history_signals(self):
        with self.lock:
            return list(reversed(self.history_signals))
    
    def get_advanced_stats(self):
        with self.lock:
            if not self.history_signals:
                return {
                    "total_trades": 0, "wins": 0, "losses": 0,
                    "win_rate": 0, "total_pnl": 0, "total_pnl_leveraged": 0,
                    "avg_win": 0, "avg_loss": 0, "avg_win_leveraged": 0, "avg_loss_leveraged": 0,
                    "profit_factor": 0, "max_drawdown": 0, "sharpe_ratio": 0,
                    "best_trade": 0, "worst_trade": 0, "avg_rr": 0,
                    "consecutive_wins": 0, "consecutive_losses": 0,
                    "max_consecutive_wins": 0, "max_consecutive_losses": 0
                }
            
            wins = [s for s in self.history_signals if s["pnl_pct"] > 0]
            losses = [s for s in self.history_signals if s["pnl_pct"] <= 0]
            
            total_pnl = sum(s["pnl_pct"] for s in self.history_signals)
            total_pnl_leveraged = sum(s["pnl_with_leverage"] for s in self.history_signals)
            
            avg_win = sum(s["pnl_pct"] for s in wins) / len(wins) if wins else 0
            avg_loss = sum(s["pnl_pct"] for s in losses) / len(losses) if losses else 0
            avg_win_leveraged = sum(s["pnl_with_leverage"] for s in wins) / len(wins) if wins else 0
            avg_loss_leveraged = sum(s["pnl_with_leverage"] for s in losses) / len(losses) if losses else 0
            
            total_wins = sum(s["pnl_pct"] for s in wins)
            total_losses = abs(sum(s["pnl_pct"] for s in losses))
            profit_factor = total_wins / total_losses if total_losses > 0 else 0
            
            cumulative = 0
            peak = 0
            max_dd = 0
            for s in self.history_signals:
                cumulative += s["pnl_pct"]
                if cumulative > peak:
                    peak = cumulative
                dd = peak - cumulative
                if dd > max_dd:
                    max_dd = dd
            
            returns = [s["pnl_pct"] for s in self.history_signals]
            if len(returns) > 1:
                mean_return = np.mean(returns)
                std_return = np.std(returns)
                sharpe = (mean_return / std_return) * np.sqrt(252) if std_return > 0 else 0
            else:
                sharpe = 0
            
            best_trade = max(s["pnl_pct"] for s in self.history_signals)
            worst_trade = min(s["pnl_pct"] for s in self.history_signals)
            
            avg_rr = sum(s["pnl_pct"] / ((s["entry"] - s["sl"]) / s["entry"] * 100) 
                        for s in self.history_signals if s["pnl_pct"] > 0) / len(wins) if wins else 0
            
            max_con_wins = 0
            max_con_losses = 0
            current_con_wins = 0
            current_con_losses = 0
            
            for s in self.history_signals:
                if s["pnl_pct"] > 0:
                    current_con_wins += 1
                    current_con_losses = 0
                    max_con_wins = max(max_con_wins, current_con_wins)
                else:
                    current_con_losses += 1
                    current_con_wins = 0
                    max_con_losses = max(max_con_losses, current_con_losses)
            
            return {
                "total_trades": len(self.history_signals),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": len(wins) / len(self.history_signals) * 100,
                "total_pnl": total_pnl,
                "total_pnl_leveraged": total_pnl_leveraged,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "avg_win_leveraged": avg_win_leveraged,
                "avg_loss_leveraged": avg_loss_leveraged,
                "profit_factor": profit_factor,
                "max_drawdown": max_dd,
                "sharpe_ratio": sharpe,
                "best_trade": best_trade,
                "worst_trade": worst_trade,
                "avg_rr": avg_rr,
                "consecutive_wins": current_con_wins,
                "consecutive_losses": current_con_losses,
                "max_consecutive_wins": max_con_wins,
                "max_consecutive_losses": max_con_losses
            }


SIGNAL_MANAGER = SignalManager()


# ==============================================================================
# SCALP SNIPER ENGINE
# ==============================================================================
def analyze_fvg_and_structure(df):
    if len(df) < 20: return None
    
    for i in range(len(df)-2, max(0, len(df)-20), -1):
        if df['low'].iloc[i+1] > df['high'].iloc[i-1]:
            fvg_low = df['high'].iloc[i-1]
            fvg_high = df['low'].iloc[i+1]
            swing_low = df['low'].iloc[max(0, i-5):i+1].min()
            return {
                "type": "BUY",
                "fvg_low": fvg_low,
                "fvg_high": fvg_high,
                "sl": swing_low * 0.998,
                "reason": f"واکنش به گپ صعودی (FVG) در تایم {df.name if hasattr(df, 'name') else '5m/15m'}"
            }
        if df['high'].iloc[i+1] < df['low'].iloc[i-1]:
            fvg_low = df['high'].iloc[i+1]
            fvg_high = df['low'].iloc[i-1]
            swing_high = df['high'].iloc[max(0, i-5):i+1].max()
            return {
                "type": "SELL",
                "fvg_low": fvg_low,
                "fvg_high": fvg_high,
                "sl": swing_high * 1.002,
                "reason": f"ریجکت از گپ نزولی (FVG) در تایم {df.name if hasattr(df, 'name') else '5m/15m'}"
            }
    return None


def scan_for_new_signals():
    if not STORE.symbols: return
    
    candidates = STORE.symbols[:15]
    
    for symbol in candidates:
        if symbol in SIGNAL_MANAGER.active_signals:
            continue
        
        info = STORE.ticker_snapshot.get(symbol, {})
        current_price = info.get("price", 0)
        if current_price == 0: continue
        
        stats = STORE.get_flow_stats(symbol, lookback_mins=30)
        net_flow = stats["net"]
        buy_ratio = stats["ratio"]
        recent_net = stats["recent_net"]
        power_ratio = stats["power_ratio"]
        avg_buy_size = stats["avg_buy_size"]
        avg_sell_size = stats["avg_sell_size"]
        total_trades = stats["total_buy_count"] + stats["total_sell_count"]
        
        is_strong_buy_flow = recent_net > (current_price * 100) and buy_ratio > 0.58
        is_strong_sell_flow = recent_net < -(current_price * 100) and buy_ratio < 0.42
        
        if not (is_strong_buy_flow or is_strong_sell_flow):
            continue
        
        if total_trades < 2:
            continue
        
        if is_strong_buy_flow and power_ratio < 1.0:
            continue
        if is_strong_sell_flow and power_ratio > 1.0:
            continue

        try:
            df_5m = fetch_klines(symbol, "5", limit=50)
            df_5m.name = "5 دقیقه"
            structure = analyze_fvg_and_structure(df_5m)
            
            if not structure:
                df_15m = fetch_klines(symbol, "15", limit=30)
                df_15m.name = "۱۵ دقیقه"
                structure = analyze_fvg_and_structure(df_15m)
                
            if not structure:
                continue
                
            if structure["type"] == "BUY" and not is_strong_buy_flow: continue
            if structure["type"] == "SELL" and not is_strong_sell_flow: continue
            
            risk = abs(current_price - structure["sl"])
            risk_percent = (risk / current_price) * 100
            if risk == 0 or risk_percent > 2.0:
                continue
                
            tp1 = current_price + (risk * 1.5) if structure["type"] == "BUY" else current_price - (risk * 1.5)
            tp2 = current_price + (risk * 3.0) if structure["type"] == "BUY" else current_price - (risk * 3.0)
            
            score = 70
            if buy_ratio > 0.65 or buy_ratio < 0.35: score += 10
            if abs(net_flow) > (current_price * 500): score += 10
            
            if structure["type"] == "BUY" and power_ratio >= 1.5:
                score += 10
            elif structure["type"] == "SELL" and power_ratio <= 0.7:
                score += 10
            
            score = min(98, score)
            
            leverage = calculate_leverage(risk_percent, score, power_ratio, structure["type"])
            
            signal_data = {
                "symbol": symbol,
                "type": structure["type"],
                "entry": current_price,
                "sl": structure["sl"],
                "tp1": tp1,
                "tp2": tp2,
                "rr": "1:1.5 / 1:3",
                "confidence": score,
                "net_flow_usd": net_flow,
                "buy_ratio": buy_ratio,
                "power_ratio": power_ratio,
                "avg_buy_size": avg_buy_size,
                "avg_sell_size": avg_sell_size,
                "leverage": leverage,
                "risk_percent": risk_percent,
                "reason": structure["reason"],
                "deep_analysis": [
                    f"جریان نقدینگی ۳۰ دقیقه: {net_flow:,.0f}$ ({'خرید' if net_flow>0 else 'فروش'})",
                    f"فشار سفارشات: {buy_ratio*100:.1f}% {'خرید' if buy_ratio>0.5 else 'فروش'}",
                    f"نسبت قدرت (Power Ratio): {power_ratio:.1f} (میانگین خرید: {avg_buy_size:,.0f}$ / فروش: {avg_sell_size:,.0f}$)",
                    f"تایم‌فریم ساختار: {structure['type']} FVG شناسایی شد",
                    f"ریسک معامله: {risk_percent:.2f}% | لوریج پیشنهادی: {leverage}x"
                ]
            }
            
            SIGNAL_MANAGER.add_signal(signal_data)
        except Exception:
            continue


def signal_monitor_loop():
    while True:
        try:
            SIGNAL_MANAGER.check_and_update()
            scan_for_new_signals()
            time.sleep(5)
        except Exception:
            traceback.print_exc()
            time.sleep(5)


threading.Thread(target=signal_monitor_loop, daemon=True).start()


# ==============================================================================
# UI COMPONENTS
# ==============================================================================
GREEN = "#00E396"
RED = "#FF4560"
ACCENT = "#008FFB"
YELLOW = "#FEB019"
PURPLE = "#9B59B6"

def build_active_signal_card(sig):
    is_buy = sig["type"] == "BUY"
    color = GREEN if is_buy else RED
    type_text = "🟢 LONG (خرید)" if is_buy else "🔴 SHORT (فروش)"
    
    status_text = "✅ فعال" if sig["status"] == "ACTIVE" else "🎯 TP1 خورد (در انتظار TP2)"
    status_color = GREEN if sig["status"] == "ACTIVE" else YELLOW
    
    analysis_items = [html.Li(item, style={"marginBottom": "6px", "fontSize": "0.85rem", "color": "#cbd5e1"}) for item in sig["deep_analysis"]]
    
    power_ratio = sig.get("power_ratio", 0)
    power_color = GREEN if power_ratio > 1 else RED if power_ratio < 1 else "#9aa4b2"
    power_text = f"قدرت دست {'خریداران' if power_ratio > 1 else 'فروشندگان'}" if power_ratio != 1 else "تعادل"
    
    leverage = sig.get("leverage", 5)
    
    # استفاده از format_price برای نمایش صحیح شیبا و سایر ارزها
    entry_price = format_price(sig['entry'])
    sl_price = format_price(sig['sl'])
    tp1_price = format_price(sig['tp1'])
    tp2_price = format_price(sig['tp2'])
    
    return dbc.Col(
        dbc.Card(
            dbc.CardBody([
                html.Div([
                    html.Div([
                        html.H4(sig["symbol"], className="mb-0 fw-bold"),
                        html.Span(type_text, style={"color": color, "fontWeight": "800", "fontSize": "0.9rem", "backgroundColor": f"{color}15", "padding": "2px 8px", "borderRadius": "6px"})
                    ]),
                    html.Div([
                        html.Span(status_text, style={"color": status_color, "fontWeight": "700", "fontSize": "0.85rem"}),
                        html.Br(),
                        html.Span(f"امتیاز: {sig['confidence']}%", className="fw-bold", style={"color": color, "fontSize": "1rem"})
                    ], className="text-end")
                ], className="d-flex justify-content-between align-items-start mb-3"),
                
                html.Div([
                    html.Div([
                        html.Span("⚡ نسبت قدرت: ", className="text-muted small"),
                        html.Span(f"{power_ratio:.1f}", style={"color": power_color, "fontWeight": "800", "fontSize": "1.1rem"}),
                        html.Span(f" ({power_text})", className="small", style={"color": power_color})
                    ], className="text-center"),
                    html.Div([
                        html.Span("🎯 لوریج پیشنهادی: ", className="text-muted small"),
                        html.Span(f"{leverage}x", style={"color": PURPLE, "fontWeight": "800", "fontSize": "1.3rem"})
                    ], className="text-center mt-2")
                ], className="mb-3 p-3", style={"backgroundColor": "#0f1218", "borderRadius": "8px"}),
                
                html.Div([
                    html.Div([
                        html.Div("نقطه ورود", className="text-muted small mb-1"),
                        html.H5(entry_price, className="mb-0 text-white")
                    ], className="text-center p-2", style={"backgroundColor": "#1e2530", "borderRadius": "8px", "border": f"1px solid {color}40"}),
                    
                    html.Div([
                        html.Div("حد ضرر (SL)", className="text-muted small mb-1"),
                        html.H5(sl_price, className="mb-0", style={"color": RED})
                    ], className="text-center p-2", style={"backgroundColor": "rgba(255, 69, 96, 0.1)", "borderRadius": "8px", "border": "1px solid rgba(255, 69, 96, 0.3)"}),
                    
                    html.Div([
                        html.Div("حد سود ۱ (TP1)", className="text-muted small mb-1"),
                        html.H5(tp1_price, className="mb-0", style={"color": GREEN})
                    ], className="text-center p-2", style={"backgroundColor": "rgba(0, 227, 150, 0.1)", "borderRadius": "8px", "border": "1px solid rgba(0, 227, 150, 0.3)"}),
                    
                    html.Div([
                        html.Div("حد سود ۲ (TP2)", className="text-muted small mb-1"),
                        html.H5(tp2_price, className="mb-0", style={"color": GREEN})
                    ], className="text-center p-2", style={"backgroundColor": "rgba(0, 227, 150, 0.1)", "borderRadius": "8px", "border": "1px solid rgba(0, 227, 150, 0.3)"}),
                ], className="d-flex justify-content-between g-2 mb-3"),
                
                html.Div([
                    html.Span("نسبت ریسک به ریوارد: ", className="text-muted small"),
                    html.Span(sig["rr"], className="fw-bold text-white")
                ], className="mb-3 text-center"),
                
                html.Div([
                    html.H6("🔍 تحلیل عمیق چرایی سیگنال:", className="fw-bold mb-2", style={"color": ACCENT, "fontSize": "0.9rem"}),
                    html.Ul(analysis_items, style={"paddingRight": "20px", "marginBottom": "0"})
                ], style={"backgroundColor": "#0f1218", "padding": "15px", "borderRadius": "10px", "borderRight": f"3px solid {color}"})
                
            ]),
            className="h-100",
            style={
                "background": "rgba(21, 26, 35, 0.8)",
                "backdropFilter": "blur(12px)",
                "border": f"1px solid {color}50",
                "borderRadius": "16px",
                "boxShadow": f"0 8px 32px rgba(0,0,0,0.4), 0 0 15px {color}20",
                "transition": "transform 0.2s",
                "cursor": "default"
            }
        ),
        width=12, lg=6, xl=4, className="mb-4"
    )


def build_history_table(signals):
    if not signals:
        return html.Div("هنوز سیگنال بسته‌شده‌ای وجود ندارد", className="text-center text-muted p-4")
    
    rows = []
    for s in signals:
        is_win = s["pnl_pct"] > 0
        color = GREEN if is_win else RED
        result_text = "✅ TP2" if s["exit_reason"] == "TP2_HIT" else ("🎯 TP1" if s["exit_reason"] == "TP1_HIT" else "❌ SL")
        
        created_str = s["created_at"].strftime("%m-%d %H:%M") if s["created_at"] else "-"
        closed_str = s["closed_at"].strftime("%m-%d %H:%M") if s["closed_at"] else "-"
        
        leverage = s.get("leverage", 5)
        pnl_leveraged = s.get("pnl_with_leverage", s["pnl_pct"] * leverage)
        
        # استفاده از format_price برای جدول تاریخچه
        rows.append(html.Tr([
            html.Td(s["symbol"], className="fw-bold"),
            html.Td("LONG" if s["type"] == "BUY" else "SHORT", style={"color": GREEN if s["type"] == "BUY" else RED}),
            html.Td(f"{leverage}x", style={"color": PURPLE, "fontWeight": "700"}),
            html.Td(format_price(s['entry'])),
            html.Td(format_price(s['exit_price'])),
            html.Td(result_text, style={"color": color, "fontWeight": "700"}),
            html.Td(f"{s['pnl_pct']:+.2f}%", style={"color": color, "fontWeight": "700"}),
            html.Td(f"{pnl_leveraged:+.2f}%", style={"color": color, "fontWeight": "700"}),
            html.Td(created_str, className="text-muted small"),
            html.Td(closed_str, className="text-muted small"),
        ]))
    
    return dbc.Table([
        html.Thead(html.Tr([
            html.Th("نماد"), html.Th("نوع"), html.Th("لوریج"), html.Th("ورود"), html.Th("خروج"),
            html.Th("نتیجه"), html.Th("سود/ضرر"), html.Th("با لوریج"), html.Th("زمان باز"), html.Th("زمان بسته")
        ])),
        html.Tbody(rows)
    ], bordered=False, hover=True, responsive=True, className="mb-0")


def build_advanced_stats_cards(stats):
    if stats["total_trades"] == 0:
        return html.Div("هنوز معامله‌ای بسته نشده است", className="text-center text-muted p-4")
    
    win_rate_color = GREEN if stats["win_rate"] >= 50 else RED
    pnl_color = GREEN if stats["total_pnl"] >= 0 else RED
    pf_color = GREEN if stats["profit_factor"] >= 1.5 else (YELLOW if stats["profit_factor"] >= 1.0 else RED)
    
    return dbc.Row([
        dbc.Col(
            dbc.Card(
                dbc.CardBody([
                    html.Div("تعداد کل معاملات", className="text-muted small mb-2"),
                    html.H2(stats["total_trades"], className="mb-0 fw-bold"),
                    html.Div(f"{stats['wins']} برد / {stats['losses']} باخت", className="small text-muted mt-1")
                ]),
                className="h-100",
                style={"background": "rgba(21, 26, 35, 0.8)", "border": "1px solid rgba(255,255,255,0.1)", "borderRadius": "12px"}
            ),
            width=12, md=3, className="mb-3"
        ),
        dbc.Col(
            dbc.Card(
                dbc.CardBody([
                    html.Div("نرخ موفقیت (Win Rate)", className="text-muted small mb-2"),
                    html.H2(f"{stats['win_rate']:.1f}%", className="mb-0 fw-bold", style={"color": win_rate_color}),
                    html.Div("درصد معاملات سودده", className="small text-muted mt-1")
                ]),
                className="h-100",
                style={"background": "rgba(21, 26, 35, 0.8)", "border": "1px solid rgba(255,255,255,0.1)", "borderRadius": "12px"}
            ),
            width=12, md=3, className="mb-3"
        ),
        dbc.Col(
            dbc.Card(
                dbc.CardBody([
                    html.Div("سود/ضرر تجمعی", className="text-muted small mb-2"),
                    html.H2(f"{stats['total_pnl']:+.2f}%", className="mb-0 fw-bold", style={"color": pnl_color}),
                    html.Div(f"با لوریج: {stats['total_pnl_leveraged']:+.2f}%", className="small", style={"color": pnl_color, "marginTop": "4px"})
                ]),
                className="h-100",
                style={"background": "rgba(21, 26, 35, 0.8)", "border": "1px solid rgba(255,255,255,0.1)", "borderRadius": "12px"}
            ),
            width=12, md=3, className="mb-3"
        ),
        dbc.Col(
            dbc.Card(
                dbc.CardBody([
                    html.Div("Profit Factor", className="text-muted small mb-2"),
                    html.H2(f"{stats['profit_factor']:.2f}", className="mb-0 fw-bold", style={"color": pf_color}),
                    html.Div("نسبت سود به ضرر", className="small text-muted mt-1")
                ]),
                className="h-100",
                style={"background": "rgba(21, 26, 35, 0.8)", "border": "1px solid rgba(255,255,255,0.1)", "borderRadius": "12px"}
            ),
            width=12, md=3, className="mb-3"
        ),
        dbc.Col(
            dbc.Card(
                dbc.CardBody([
                    html.Div("Max Drawdown", className="text-muted small mb-2"),
                    html.H2(f"{stats['max_drawdown']:.2f}%", className="mb-0 fw-bold", style={"color": RED}),
                    html.Div("بیشترین افت سرمایه", className="small text-muted mt-1")
                ]),
                className="h-100",
                style={"background": "rgba(21, 26, 35, 0.8)", "border": "1px solid rgba(255,255,255,0.1)", "borderRadius": "12px"}
            ),
            width=12, md=3, className="mb-3"
        ),
        dbc.Col(
            dbc.Card(
                dbc.CardBody([
                    html.Div("Sharpe Ratio", className="text-muted small mb-2"),
                    html.H2(f"{stats['sharpe_ratio']:.2f}", className="mb-0 fw-bold", style={"color": ACCENT}),
                    html.Div("نسبت ریسک به بازدهی", className="small text-muted mt-1")
                ]),
                className="h-100",
                style={"background": "rgba(21, 26, 35, 0.8)", "border": "1px solid rgba(255,255,255,0.1)", "borderRadius": "12px"}
            ),
            width=12, md=3, className="mb-3"
        ),
        dbc.Col(
            dbc.Card(
                dbc.CardBody([
                    html.Div("بهترین/بدترین معامله", className="text-muted small mb-2"),
                    html.H2(f"{stats['best_trade']:+.2f}% / {stats['worst_trade']:.2f}%", className="mb-0 fw-bold", style={"fontSize": "1.2rem"}),
                    html.Div("Best / Worst", className="small text-muted mt-1")
                ]),
                className="h-100",
                style={"background": "rgba(21, 26, 35, 0.8)", "border": "1px solid rgba(255,255,255,0.1)", "borderRadius": "12px"}
            ),
            width=12, md=3, className="mb-3"
        ),
        dbc.Col(
            dbc.Card(
                dbc.CardBody([
                    html.Div("میانگین R:R محقق‌شده", className="text-muted small mb-2"),
                    html.H2(f"1:{stats['avg_rr']:.2f}", className="mb-0 fw-bold", style={"color": GREEN}),
                    html.Div("در معاملات سودده", className="small text-muted mt-1")
                ]),
                className="h-100",
                style={"background": "rgba(21, 26, 35, 0.8)", "border": "1px solid rgba(255,255,255,0.1)", "borderRadius": "12px"}
            ),
            width=12, md=3, className="mb-3"
        ),
    ], className="g-3")


# ==============================================================================
# DASH APP & LAYOUT
# ==============================================================================
FONT_URL = "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;700;800;900&display=swap"

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG, FONT_URL])
app.title = "Morindok Scalp Sniper"
server = app.server
app.config.suppress_callback_exceptions = True

app.index_string = """
<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <style>
        * { font-family: 'Vazirmatn', sans-serif !important; box-sizing: border-box; }
        html, body {
            direction: rtl; text-align: right;
            background-color: #0B0E14;
            background-image: 
                radial-gradient(at 10% 10%, rgba(0, 227, 150, 0.05) 0px, transparent 40%),
                radial-gradient(at 90% 90%, rgba(0, 143, 251, 0.05) 0px, transparent 40%);
            background-attachment: fixed;
            min-height: 100vh; color: #e6e9ef;
        }
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #0B0E14; }
        ::-webkit-scrollbar-thumb { background: #232935; border-radius: 4px; }
        
        .brand-text {
            background: linear-gradient(135deg, #00E396 0%, #008FFB 100%);
            -webkit-background-clip: text; background-clip: text; color: transparent;
            font-weight: 900;
        }
        .pulse-dot {
            width: 10px; height: 10px; background-color: #00E396; border-radius: 50%;
            display: inline-block; margin-left: 8px;
            box-shadow: 0 0 0 0 rgba(0, 227, 150, 0.7);
            animation: pulse-green 2s infinite;
        }
        @keyframes pulse-green {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 227, 150, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(0, 227, 150, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 227, 150, 0); }
        }
        
        #main-tabs.nav-tabs { border: none; gap: 6px; background: rgba(255,255,255,0.03); padding: 5px; border-radius: 14px; display: inline-flex; }
        #main-tabs.nav-tabs .nav-link {
            border: none !important; border-radius: 10px !important; color: #9aa4b2 !important;
            font-weight: 700; padding: 10px 24px !important; transition: all 0.2s;
        }
        #main-tabs.nav-tabs .nav-link.active {
            background: linear-gradient(135deg, #008FFB, #00E396) !important;
            color: #fff !important; box-shadow: 0 4px 15px rgba(0, 227, 150, 0.3);
        }
        
        table.table-dark { border-collapse: separate; border-spacing: 0; text-align: right !important; }
        table.table-dark th { color: #9aa4b2 !important; font-size: 0.75rem; font-weight: 700; background: rgba(255,255,255,0.02) !important; border-bottom: 1px solid #232935 !important; }
        table.table-dark td { border-bottom: 1px solid rgba(255,255,255,0.04) !important; vertical-align: middle !important; }
        table.table-dark tbody tr:hover { background: rgba(0, 143, 251, 0.05) !important; }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>
"""

active_signals_tab = html.Div([
    html.Div([
        html.Div([
            html.Span(className="pulse-dot"),
            html.Span(id="status-text", className="fw-bold", style={"fontSize": "0.9rem", "marginRight": "8px"})
        ], className="d-flex align-items-center p-3", style={"backgroundColor": "#151A23", "borderRadius": "12px", "border": "1px solid #232935", "display": "inline-block"}),
        html.Div(id="last-update-badge", className="p-2 text-center", style={"backgroundColor": "#151A23", "borderRadius": "8px", "border": "1px solid #232935", "fontSize": "0.9rem", "display": "inline-block", "marginRight": "15px"})
    ], className="mb-4"),
    
    html.Div(id="active-signals-container", className="mt-4"),
    
    dcc.Interval(id="refresh-interval", interval=5000, n_intervals=0),
])

history_tab = html.Div([
    html.H4("📊 آمار پیشرفته عملکرد سیستم", className="fw-bold mb-3"),
    html.Div(id="stats-container", className="mb-4"),
    
    html.Hr(style={"borderColor": "#232935", "margin": "30px 0"}),
    
    html.H4("📜 تاریخچه سیگنال‌های بسته‌شده", className="fw-bold mb-3"),
    dbc.Card(
        dbc.CardBody([
            html.Div(id="history-table-container")
        ]),
        style={"background": "rgba(21, 26, 35, 0.8)", "border": "1px solid rgba(255,255,255,0.1)", "borderRadius": "12px"}
    ),
    
    dcc.Interval(id="history-interval", interval=10000, n_intervals=0),
])

app.layout = dbc.Container(fluid=True, style={"paddingTop": "30px", "paddingBottom": "60px", "maxWidth": "1400px"}, children=[
    html.Div([
        html.Div([
            html.Div("MORINDOK SCALP SNIPER", style={"fontSize": "0.8rem", "fontWeight": "800", "letterSpacing": "2px", "color": "#00E396", "marginBottom": "8px"}),
            html.H1("شکارچی سیگنال‌های قطعی اسکالپ", className="brand-text mb-2"),
            html.P("سیگنال‌ها با فیلتر نسبت قدرت (Power Ratio) و لوریج پیشنهادی هوشمند. آمار کامل عملکرد در تب تاریخچه.", 
                   className="text-muted mb-0", style={"fontSize": "0.95rem", "maxWidth": "800px", "lineHeight": "1.7"})
        ]),
    ], className="mb-4 p-4", 
       style={"backgroundColor": "rgba(21, 26, 35, 0.6)", "backdropFilter": "blur(10px)", "borderRadius": "20px", "border": "1px solid rgba(255,255,255,0.05)"}),

    dbc.Tabs([
        dbc.Tab(active_signals_tab, label="🎯 سیگنال‌های فعال", tab_id="tab-active"),
        dbc.Tab(history_tab, label="📜 تاریخچه و آمار", tab_id="tab-history"),
    ], id="main-tabs", active_tab="tab-active", className="mb-4"),
])


# ==============================================================================
# CALLBACKS
# ==============================================================================
@app.callback(
    [Output("active-signals-container", "children"), Output("status-text", "children"), Output("last-update-badge", "children")],
    [Input("refresh-interval", "n_intervals")]
)
def update_active_signals(_n):
    active_signals = SIGNAL_MANAGER.get_active_signals()
    
    if STORE.status["connected"]:
        status_text = f"موتور فعال | {len(active_signals)} سیگنال در حال رصد"
        color = "#00E396"
    else:
        error_msg = STORE.status.get("last_error")
        error_str = str(error_msg) if error_msg else "خطای ناشناخته"
        status_text = f"خطا: {error_str[:40]}..."
        color = "#FF4560"
    
    status_html = html.Span(status_text, style={"color": color})
    
    if STORE.status["last_update"]:
        update_html = f"آخرین بروزرسانی: {STORE.status['last_update'].strftime('%H:%M:%S')}"
    else:
        update_html = "در حال دریافت..."
    
    if not active_signals:
        if not STORE.status["connected"]:
            error_str_full = str(STORE.status.get("last_error") or "خطای ناشناخته")
            cards = html.Div([
                html.Div("⚠️", style={"fontSize": "3rem", "marginBottom": "15px"}),
                html.H4("خطا در اتصال به بایبیت", className="fw-bold text-danger"),
                html.P(f"لطفاً اتصال اینترنت یا VPN را بررسی کنید. خطا: {error_str_full}", 
                       className="text-muted", style={"maxWidth": "600px", "margin": "0 auto"})
            ], className="text-center p-5", style={"backgroundColor": "rgba(255, 69, 96, 0.05)", "borderRadius": "16px", "border": "1px dashed #FF4560"})
        else:
            cards = html.Div([
                html.Div("🔍", style={"fontSize": "3rem", "marginBottom": "15px"}),
                html.H4("در حال حاضر سیگنال فعالی وجود ندارد", className="fw-bold"),
                html.P("سیستم به‌صورت لحظه‌ای بازار را اسکن می‌کند و به محض یافتن سیگنال قطعی، آن را اینجا نمایش می‌دهد.", 
                       className="text-muted", style={"maxWidth": "500px", "margin": "0 auto"})
            ], className="text-center p-5", style={"backgroundColor": "rgba(21, 26, 35, 0.5)", "borderRadius": "16px", "border": "1px dashed #232935"})
    else:
        cards = dbc.Row([build_active_signal_card(s) for s in active_signals])
    
    return cards, status_html, update_html


@app.callback(
    [Output("stats-container", "children"), Output("history-table-container", "children")],
    [Input("history-interval", "n_intervals")]
)
def update_history_tab(_n):
    stats = SIGNAL_MANAGER.get_advanced_stats()
    history_signals = SIGNAL_MANAGER.get_history_signals()
    
    stats_cards = build_advanced_stats_cards(stats)
    history_table = build_history_table(history_signals)
    
    return stats_cards, history_table


# ==============================================================================
# AUTO OPEN BROWSER & RUN
# ==============================================================================
def open_browser_automatically():
    """باز کردن خودکار مرورگر پس از راه‌اندازی سرور"""
    time.sleep(2.5)  # انتظار برای اطمینان از راه‌اندازی کامل سرور
    webbrowser.open("http://127.0.0.1:8050")


if __name__ == "__main__":
    print("="*70)
    print(" 🎯 MORINDOK SCALP SNIPER PRO INITIATED")
    print(" ✅ باز شدن خودکار مرورگر فعال است")
    print(" ✅ نمایش هوشمند قیمت‌ها (پشتیبانی از شیبا و میم‌کوین‌ها) فعال است")
    print(" آدرس: http://127.0.0.1:8050")
    print("="*70)
    
    # شروع ترد باز کردن مرورگر در پس‌زمینه
    threading.Thread(target=open_browser_automatically, daemon=True).start()
    
    # اجرای سرور
    app.run(debug=False, host="127.0.0.1", port=8050)