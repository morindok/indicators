# -*- coding: utf-8 -*-
"""
🌌 Golden Spiral Fractal + Walk-Forward Backtest (Final - Leverage Fixed)
"""

import numpy as np
import pandas as pd
import requests
import dash
from dash import dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

# ==============================================================================
# 0) تنظیمات
# ==============================================================================
BG, CARD, LINE, TXT, MUT = "#0b1220", "#121c30", "#23314d", "#e8ecf4", "#8fa3c0"
GOLD, GREEN, RED = "#f0b90b", "#00e676", "#ff5252"
GREEN_LTF, RED_LTF = "#69f0ae", "#ff8a80"
NODE_COLOR, CYAN = "#ffffff", "#00e5ff"

DEFAULT_SYMBOL = "BTCUSDT"
TIMEFRAMES = ['1', '3', '5', '15', '30', '60', '120', '240', '360', '720', 'D', 'W', 'M']

SPREAD_FACTOR = 4.0
HTF_LOOPS = 1.0
NUM_POINTS_HTF = 40
NUM_POINTS_LTF = 16
LTF_SCALE = 0.12
LTF_LOOPS = 0.75

SR_BINS = 80
SR_THRESHOLD = 1.5
SR_MAX_LEVELS = 12

BT_COMM = 0.00055
BT_SPREAD = 0.0003


# ==============================================================================
# 1) فرمت قیمت
# ==============================================================================
def fmt_p(price):
    a = abs(price)
    if a >= 10000:
        return f"{price:.0f}"
    elif a >= 1000:
        return f"{price:.1f}"
    elif a >= 1:
        return f"{price:.2f}"
    elif a >= 0.1:
        return f"{price:.4f}"
    elif a >= 0.01:
        return f"{price:.5f}"
    elif a >= 0.001:
        return f"{price:.6f}"
    elif a >= 0.0001:
        return f"{price:.7f}"
    else:
        return f"{price:.8f}"


def fmt_pa(prices):
    if len(prices) == 0: return []
    m = np.nanmedian(prices)
    a = abs(m)
    if a >= 10000:
        d = 0
    elif a >= 1000:
        d = 1
    elif a >= 1:
        d = 2
    elif a >= 0.1:
        d = 4
    elif a >= 0.01:
        d = 5
    elif a >= 0.001:
        d = 6
    else:
        d = 8
    return [f"{p:.{d}f}" for p in prices]


# ==============================================================================
# 2) API بایبیت با Pagination
# ==============================================================================
REST = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
SES = requests.Session()
SES.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
_AR = {"url": None}


def api_get(path, params, timeout=15):
    cs = ([_AR["url"]] if _AR["url"] else []) + [b for b in REST if b != _AR["url"]]
    for base in cs:
        try:
            r = SES.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code in (403, 451): continue
            r.raise_for_status()
            d = r.json()
            if d.get("retCode") == 0:
                _AR["url"] = base
                return d
        except:
            continue
    return None


def get_klines(symbol, interval, limit=500):
    all_klines = []
    remaining = limit
    end_time = None
    while remaining > 0:
        batch = min(remaining, 1000)
        params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": batch}
        if end_time: params["end"] = end_time
        d = api_get("/v5/market/kline", params)
        if not d or "list" not in (d.get("result") or {}): break
        lst = d["result"]["list"]
        if not lst: break
        all_klines.extend(lst)
        remaining -= len(lst)
        if len(lst) < batch: break
        end_time = int(lst[-1][0]) - 1
    if not all_klines: return pd.DataFrame()
    df = pd.DataFrame(all_klines, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts_num"] = df["ts"].astype(float) / 1000.0
    for c in ["open", "high", "low", "close", "volume", "turnover"]:
        df[c] = df[c].astype(float)
    df["datetime"] = pd.to_datetime(df["ts_num"], unit='s')
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts_num").reset_index(drop=True)
    if len(df) > limit: df = df.iloc[-limit:].reset_index(drop=True)
    return df


def tf_sec(tf):
    tf = str(tf)
    if tf == 'D': return 86400
    if tf == 'W': return 604800
    if tf == 'M': return 2592000
    return int(tf) * 60


# ==============================================================================
# 3) اسپیرال
# ==============================================================================
def gen_spirals(x0, y0, x1, y1, dirs, np_=40, loops=1.0):
    N = len(x0)
    if N == 0: return np.empty((0, np_)), np.empty((0, np_))
    b = 0.3063489
    dx, dy = x1 - x0, y1 - y0
    dist = np.hypot(dx, dy)
    ta = np.arctan2(dy, dx)
    th = np.linspace(0, loops * 2 * np.pi, np_)
    r = np.exp(b * th) - 1
    mr = r[-1]
    sc = np.where(mr > 0, dist / mr, 0)
    td = dirs[:, None] * th[None, :]
    xs = r[None, :] * np.cos(td) * sc[:, None]
    ys = r[None, :] * np.sin(td) * sc[:, None]
    ea = np.arctan2(ys[:, -1], xs[:, -1])
    rot = ta - ea
    cr, sr = np.cos(rot)[:, None], np.sin(rot)[:, None]
    return xs * cr - ys * sr + x0[:, None], xs * sr + ys * cr + y0[:, None]


def flat_nan(X, Y, mask=None):
    if mask is not None: X, Y = X[mask], Y[mask]
    N = len(X)
    if N == 0: return np.array([]), np.array([])
    np_ = X.shape[1]
    Xf, Yf = X.flatten(), Y.flatten()
    if N > 1:
        ni = np.arange(1, N) * np_
        Xf, Yf = np.insert(Xf, ni, np.nan), np.insert(Yf, ni, np.nan)
    return Xf, Yf


# ==============================================================================
# 4) ساخت نمودار اسپیرال
# ==============================================================================
def build_spiral_figure(df_htf, df_ltf, htf_sec, ltf_sec):
    min_ts = df_htf["ts_num"].min()
    ts = df_htf["ts_num"].max() - min_ts
    pmin = df_htf["low"].min()
    pmax = df_htf["high"].max()
    ps = pmax - pmin if pmax != pmin else 1
    if ts == 0: ts = 1
    st = ts * SPREAD_FACTOR
    psc = st / ps

    ht = df_htf["ts_num"].values
    ho = df_htf["open"].values
    hc = df_htf["close"].values

    x0 = (ht - min_ts) * SPREAD_FACTOR
    y0 = (ho - pmin) * psc
    x1 = x0 + htf_sec * SPREAD_FACTOR
    y1 = (hc - pmin) * psc

    bl = hc >= ho
    dr = np.where(bl, 1.0, -1.0)
    Xr, Yr = gen_spirals(x0, y0, x1, y1, dr, NUM_POINTS_HTF, HTF_LOOPS)

    al = np.linspace(0, 1, NUM_POINTS_HTF)
    te = ht + htf_sec
    tm = ht[:, None] + al[None, :] * (te - ht)[:, None]
    pm = ho[:, None] + al[None, :] * (hc - ho)[:, None]

    traces = []
    for mk, cl in [(bl, GREEN), (~bl, RED)]:
        ns = mk.sum()
        if ns == 0: continue
        Xs, Ys = flat_nan(Xr, Yr, mk)
        tsr = pd.to_datetime(tm[mk].flatten(), unit='s').strftime('%Y-%m-%d %H:%M').values
        psr = fmt_pa(pm[mk].flatten())
        cdl = [[t, p] for t, p in zip(tsr, psr)]
        if ns > 1:
            for idx in sorted(np.arange(1, ns) * NUM_POINTS_HTF):
                cdl.insert(idx, [None, None])
        traces.append(go.Scattergl(
            x=Xs, y=Ys, mode='lines', line=dict(color=cl, width=2), opacity=0.9,
            customdata=cdl,
            hovertemplate="<b>⏱ %{customdata[0]}</b><br>💰 %{customdata[1]}<extra></extra>",
            showlegend=False))

    traces.append(go.Scattergl(
        x=x0, y=y0, mode='markers',
        marker=dict(size=4, color=np.where(bl, GREEN, RED), symbol='circle',
                    line=dict(width=1, color=NODE_COLOR)),
        customdata=[[t, p] for t, p in zip(
            pd.to_datetime(ht, unit='s').strftime('%Y-%m-%d %H:%M').values, fmt_pa(ho))],
        hovertemplate="<b>🔗</b> %{customdata[0]}<br>💰 %{customdata[1]}<extra></extra>",
        showlegend=False))

    lt = df_ltf["ts_num"].values
    lo = df_ltf["open"].values
    lc = df_ltf["close"].values
    pi = np.searchsorted(ht, lt, side='right') - 1
    he = ht + htf_sec
    vm = (pi >= 0) & (pi < len(ht)) & (lt < he[pi])
    vlt, vlo, vlc, vp = lt[vm], lo[vm], lc[vm], pi[vm]

    if len(vlt) > 0:
        ps2, pe = ht[vp], he[vp]
        pr2 = (vlt - ps2) / (pe - ps2)
        pidx = (pr2 * (NUM_POINTS_HTF - 1)).astype(int)
        bx, by = Xr[vp, pidx], Yr[vp, pidx]
        x1l = bx + ltf_sec * SPREAD_FACTOR * LTF_SCALE
        y1l = by + (vlc - vlo) * psc * LTF_SCALE
        bl2 = vlc >= vlo
        dr2 = np.where(bl2, 1.0, -1.0)
        Xl, Yl = gen_spirals(bx, by, x1l, y1l, dr2, NUM_POINTS_LTF, LTF_LOOPS)
        al2 = np.linspace(0, 1, NUM_POINTS_LTF)
        te2 = vlt + ltf_sec
        tm2 = vlt[:, None] + al2[None, :] * (te2 - vlt)[:, None]
        pm2 = vlo[:, None] + al2[None, :] * (vlc - vlo)[:, None]
        for mk, cl in [(bl2, GREEN_LTF), (~bl2, RED_LTF)]:
            ns = mk.sum()
            if ns == 0: continue
            Xs, Ys = flat_nan(Xl, Yl, mk)
            tsr = pd.to_datetime(tm2[mk].flatten(), unit='s').strftime('%Y-%m-%d %H:%M').values
            psr = fmt_pa(pm2[mk].flatten())
            cdl = [[t, p] for t, p in zip(tsr, psr)]
            if ns > 1:
                for idx in sorted(np.arange(1, ns) * NUM_POINTS_LTF):
                    cdl.insert(idx, [None, None])
            traces.append(go.Scattergl(
                x=Xs, y=Ys, mode='lines', line=dict(color=cl, width=1), opacity=0.6,
                customdata=cdl,
                hovertemplate="<b>⏱ %{customdata[0]}</b><br>💰 %{customdata[1]}<extra></extra>",
                showlegend=False))

    return traces, st, pmin, psc, Xr, Yr, y0


# ==============================================================================
# 5) استخراج S/R
# ==============================================================================
def extract_sr(Y_htf, Y_ltf, node_y, pmin, psc, cur_price):
    hp = (Y_htf.flatten() / psc) + pmin
    hp = hp[~np.isnan(hp)]
    lp = np.array([])
    if Y_ltf is not None and len(Y_ltf) > 0:
        lp = (Y_ltf.flatten() / psc) + pmin
        lp = lp[~np.isnan(lp)]
    np_ = (node_y / psc) + pmin
    np_ = np_[~np.isnan(np_)]
    if len(hp) == 0: return []
    ap = np.concatenate([hp, lp, np_])
    aw = np.concatenate([np.full(len(hp), 3.0), np.full(len(lp), 1.0), np.full(len(np_), 2.5)])
    pr = ap.max() - ap.min()
    if pr == 0: pr = 1
    hist, be = np.histogram(ap, bins=SR_BINS, weights=aw)
    bc = (be[:-1] + be[1:]) / 2
    mh = np.mean(hist)
    peaks = []
    for i in range(2, len(hist) - 2):
        if hist[i] > hist[i - 1] and hist[i] > hist[i + 1] and hist[i] > hist[i - 2] and \
                hist[i] > hist[i + 2] and hist[i] > mh * SR_THRESHOLD:
            peaks.append((bc[i], hist[i]))
    peaks.sort(key=lambda x: x[1], reverse=True)
    sr = []
    ms = peaks[0][1] if peaks else 1
    for idx, (price, vs) in enumerate(peaks[:SR_MAX_LEVELS]):
        ns = int((vs / ms) * 100)
        tc = "support" if price < cur_price else "resistance"
        sr.append({"rank": idx + 1, "price": price, "price_str": fmt_p(price),
                   "type": "Support 🟢" if tc == "support" else "Resistance 🔴",
                   "type_code": tc, "strength": ns,
                   "distance_%": round(((price - cur_price) / cur_price) * 100, 4)})
    return sr


# ==============================================================================
# 6) 🏦 بک‌تست Walk-Forward با لوریج واقعی
# ==============================================================================
def extract_sr_window(wo, wc, wl, wh, lo2, lc2, cur):
    if len(wo) < 5: return []
    ap, aw = [], []
    for i in range(len(wo)):
        pts = np.linspace(wo[i], wc[i], 20)
        ap.extend(pts);
        aw.extend([3.0] * 20)
    ap.extend(wo);
    aw.extend([2.5] * len(wo))
    if len(lo2) > 0:
        for i in range(len(lo2)):
            pts = np.linspace(lo2[i], lc2[i], 10)
            ap.extend(pts);
            aw.extend([1.0] * 10)
    ap, aw = np.array(ap), np.array(aw)
    pr = ap.max() - ap.min()
    if pr == 0: return []
    hist, be = np.histogram(ap, bins=60, weights=aw)
    bc = (be[:-1] + be[1:]) / 2
    mh = np.mean(hist)
    peaks = []
    for i in range(2, len(hist) - 2):
        if hist[i] > hist[i - 1] and hist[i] > hist[i + 1] and hist[i] > hist[i - 2] and \
                hist[i] > hist[i + 2] and hist[i] > mh * 1.4:
            peaks.append((bc[i], hist[i]))
    peaks.sort(key=lambda x: x[1], reverse=True)
    ms = peaks[0][1] if peaks else 1
    levels = []
    for price, vs in peaks[:10]:
        ns = int((vs / ms) * 100)
        tc = "support" if price < cur else "resistance"
        levels.append({"price": price, "strength": ns, "type_code": tc})
    return levels


def run_backtest(df_htf, df_ltf, lookback=500, window=80, recalc=5,
                 min_str=95, cap0=500, lev=5, risk=0.02, rr=2.0, slp=0.008):
    """
    ═══════════════════════════════════════════════════════════
    بک‌تست Walk-Forward با لوریج واقعی

    فرمول:
    Margin = Capital × Risk%
    Position Value = Margin × Leverage
    Position Size = Position Value / Entry Price
    P&L = (Exit - Entry) × Position Size
    ROI = P&L / Margin × 100
    ═══════════════════════════════════════════════════════════
    """
    total = len(df_htf)
    lookback = min(int(lookback), total)
    df_bt = df_htf.iloc[-lookback:].copy().reset_index(drop=True)

    bt_start = df_bt["ts_num"].iloc[0]
    bt_end = df_bt["ts_num"].iloc[-1]
    df_ltf_bt = df_ltf[(df_ltf["ts_num"] >= bt_start) &
                       (df_ltf["ts_num"] <= bt_end)].reset_index(drop=True) if len(df_ltf) > 0 else pd.DataFrame()

    capital = cap0
    trades = []
    eq = [capital]
    eqt = [str(df_bt["datetime"].iloc[0])]
    open_t = None
    sr = []

    ho = df_bt["open"].values
    hc = df_bt["close"].values
    hh = df_bt["high"].values
    hl = df_bt["low"].values
    hdt = df_bt["datetime"].values
    ht = df_bt["ts_num"].values

    lo = df_ltf_bt["open"].values if len(df_ltf_bt) > 0 else np.array([])
    lc = df_ltf_bt["close"].values if len(df_ltf_bt) > 0 else np.array([])
    lt = df_ltf_bt["ts_num"].values if len(df_ltf_bt) > 0 else np.array([])

    start_i = min(window, len(df_bt) - 1)

    for i in range(start_i, len(df_bt)):
        ch, cl2, cc, ct = hh[i], hl[i], hc[i], str(hdt[i])

        # ─── هر N کندل: S/R جدید ───
        if (i - start_i) % recalc == 0:
            ws = max(0, i - window + 1)
            t_s, t_e = ht[ws], ht[i]
            lm = (lt >= t_s) & (lt <= t_e)
            sr = extract_sr_window(ho[ws:i + 1], hc[ws:i + 1], hl[ws:i + 1], hh[ws:i + 1],
                                   lo[lm] if len(lt) > 0 else np.array([]),
                                   lc[lm] if len(lt) > 0 else np.array([]), cc)

        # ─── مدیریت پوزیشن باز ───
        if open_t is not None:
            hit = False
            xp = 0
            if open_t["dir"] == "LONG":
                if cl2 <= open_t["sl"]:
                    hit, xp = True, open_t["sl"]
                elif ch >= open_t["tp"]:
                    hit, xp = True, open_t["tp"]
            else:
                if ch >= open_t["sl"]:
                    hit, xp = True, open_t["sl"]
                elif cl2 <= open_t["tp"]:
                    hit, xp = True, open_t["tp"]

            if hit:
                # ─── P&L با لوریج ───
                if open_t["dir"] == "LONG":
                    gross_pnl = (xp - open_t["entry"]) * open_t["pos_size"]
                else:
                    gross_pnl = (open_t["entry"] - xp) * open_t["pos_size"]

                total_comm = open_t["entry_comm"] + open_t["pos_size"] * xp * BT_COMM
                net_pnl = gross_pnl - total_comm
                roi_margin = (net_pnl / open_t["margin_used"]) * 100 if open_t["margin_used"] > 0 else 0

                capital += net_pnl

                open_t["exit_price"] = xp
                open_t["exit_time"] = ct
                open_t["gross_pnl"] = round(gross_pnl, 4)
                open_t["total_comm"] = round(total_comm, 6)
                open_t["pnl"] = round(net_pnl, 4)
                open_t["roi_margin"] = round(roi_margin, 2)
                open_t["result"] = "WIN ✅" if net_pnl > 0 else "LOSS ❌"
                open_t["cap_after"] = round(capital, 2)
                trades.append(open_t)
                open_t = None

            eq.append(capital)
            eqt.append(ct)
            continue

        # ─── سیگنال جدید ───
        for lv in sr:
            if lv["strength"] < min_str: continue
            lp = lv["price"]
            if not (cl2 <= lp <= ch): continue
            if abs(cc - lp) / lp > slp * 2: continue

            if lv["type_code"] == "support":
                d = "LONG"
                entry = lp * (1 + BT_SPREAD)
                sld = lp * slp
                sl = entry - sld
                tp = entry + sld * rr
            else:
                d = "SHORT"
                entry = lp * (1 - BT_SPREAD)
                sld = lp * slp
                sl = entry + sld
                tp = entry - sld * rr

            # ═══════════════════════════════════════════════
            # ⭐ لوریج واقعی:
            # Margin → Position Value → Position Size → P&L
            # ═══════════════════════════════════════════════
            margin_used = capital * risk
            if margin_used <= 0: continue

            # ارزش پوزیشن = مارجین × لوریج
            pos_value = margin_used * lev

            # اندازه پوزیشن
            pos_size = pos_value / entry

            # بررسی ریسک: ضرر در صورت SL
            loss_if_sl = sld * pos_size
            max_loss = capital * 0.9
            if loss_if_sl > max_loss:
                pos_size = max_loss / sld
                pos_value = pos_size * entry
                margin_used = pos_value / lev

            # کمیسیون ورود
            entry_comm = pos_value * BT_COMM
            if entry_comm >= margin_used * 0.5: continue

            open_t = {
                "id": len(trades) + 1,
                "dir": d,
                "entry_time": ct,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "sl_dist": sld,
                "pos_size": pos_size,
                "pos_value": round(pos_value, 2),
                "margin_used": round(margin_used, 2),
                "lev": lev,
                "entry_comm": entry_comm,
                "risk_amount": round(loss_if_sl, 2),
                "lv_price": lp,
                "lv_str": lv["strength"],
                "exit_price": None,
                "exit_time": None,
                "gross_pnl": 0,
                "total_comm": 0,
                "pnl": 0,
                "roi_margin": 0,
                "result": "OPEN",
                "cap_after": capital
            }
            break

        eq.append(capital)
        eqt.append(ct)

    # بستن پوزیشن باز مانده
    if open_t is not None:
        lp2 = hc[-1]
        if open_t["dir"] == "LONG":
            gross_pnl = (lp2 - open_t["entry"]) * open_t["pos_size"]
        else:
            gross_pnl = (open_t["entry"] - lp2) * open_t["pos_size"]
        total_comm = open_t["entry_comm"] + open_t["pos_size"] * lp2 * BT_COMM
        net_pnl = gross_pnl - total_comm
        roi_margin = (net_pnl / open_t["margin_used"]) * 100 if open_t["margin_used"] > 0 else 0
        capital += net_pnl
        open_t["exit_price"] = lp2
        open_t["exit_time"] = str(hdt[-1])
        open_t["gross_pnl"] = round(gross_pnl, 4)
        open_t["total_comm"] = round(total_comm, 6)
        open_t["pnl"] = round(net_pnl, 4)
        open_t["roi_margin"] = round(roi_margin, 2)
        open_t["result"] = "WIN ✅" if net_pnl > 0 else "LOSS ❌"
        open_t["cap_after"] = round(capital, 2)
        trades.append(open_t)
        eq[-1] = capital

    stats = _stats(trades, eq, cap0)
    stats["lookback"] = lookback
    stats["actual"] = len(df_bt)
    stats["start"] = str(df_bt["datetime"].iloc[0])[:16]
    stats["end"] = str(df_bt["datetime"].iloc[-1])[:16]
    stats["leverage"] = lev
    return trades, eq, eqt, stats


def _stats(trades, eq, cap0):
    if not trades:
        return {"total": 0, "wins": 0, "losses": 0, "wr": 0, "pf": 0,
                "mdd": 0, "pnl": 0, "comm": 0, "final": cap0, "ret": 0,
                "aw": 0, "al": 0, "avg_roi": 0, "tpv": 0, "tmg": 0, "leverage": 1}
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    tp = sum(t["pnl"] for t in trades)
    tc = sum(t["total_comm"] for t in trades)
    gw = sum(t["pnl"] for t in wins) if wins else 0
    gl = abs(sum(t["pnl"] for t in losses)) if losses else 1
    e = np.array(eq)
    rm = np.maximum.accumulate(e)
    dd = ((e - rm) / rm * 100).min()
    avg_roi = np.mean([t["roi_margin"] for t in trades]) if trades else 0
    tpv = sum(t["pos_value"] for t in trades)
    tmg = sum(t["margin_used"] for t in trades)
    return {"total": len(trades), "wins": len(wins), "losses": len(losses),
            "wr": round(len(wins) / len(trades) * 100, 1),
            "pf": round(gw / gl, 2) if gl > 0 else 99,
            "mdd": round(abs(dd), 2), "pnl": round(tp, 2), "comm": round(tc, 2),
            "final": round(e[-1], 2), "ret": round((e[-1] - cap0) / cap0 * 100, 2),
            "aw": round(gw / len(wins), 2) if wins else 0,
            "al": round(gl / len(losses), 2) if losses else 0,
            "avg_roi": round(avg_roi, 2), "tpv": round(tpv, 2), "tmg": round(tmg, 2)}


# ==============================================================================
# 7) UI
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])
app.title = "Spiral Backtest"

app.index_string = '''<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
.dash-dropdown .Select-control{background-color:#121c30!important;border:1px solid #23314d!important}
.dash-dropdown .Select-value-label{color:#e8ecf4!important}
.dash-dropdown .Select-menu-outer{background-color:#121c30!important;border:1px solid #23314d!important}
.dash-dropdown .Select-option{background-color:#121c30!important;color:#e8ecf4!important}
body{background:#0b1220}
.sc{background:#121c30;border:1px solid #23314d;border-radius:10px;padding:10px;text-align:center;margin:3px}
.sv{font-size:16px;font-weight:bold}.sl{font-size:10px;color:#8fa3c0}
</style></head><body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>'''

app.layout = html.Div([
    dbc.Container([
        html.H3("🌀 اسپیرال فراکتالی + بک‌تست Walk-Forward",
                style={"color": GOLD, "textAlign": "center", "marginTop": "15px", "fontWeight": "bold"}),

        dbc.Row([
            dbc.Col([html.Label("نماد:", style={"color": TXT}),
                     dcc.Input(id="sym", value=DEFAULT_SYMBOL, type="text",
                               className="form-control bg-dark text-light")], md=2),
            dbc.Col([html.Label("HTF:", style={"color": TXT}),
                     dcc.Dropdown(id="htf",
                                  options=[{'label': f'{t}m' if t not in 'DWM' else t, 'value': t} for t in TIMEFRAMES],
                                  value='60')], md=2),
            dbc.Col([html.Label("LTF:", style={"color": TXT}),
                     dcc.Dropdown(id="ltf",
                                  options=[{'label': f'{t}m' if t not in 'DWM' else t, 'value': t} for t in TIMEFRAMES],
                                  value='15')], md=2),
            dbc.Col([html.Label("کندل HTF:", style={"color": TXT}),
                     dcc.Input(id="hlim", value=1000, type="number", min=50, max=10000,
                               className="form-control bg-dark text-light")], md=2),
            dbc.Col([html.Label("کندل LTF:", style={"color": TXT}),
                     dcc.Input(id="llim", value=1000, type="number", min=50, max=5000,
                               className="form-control bg-dark text-light")], md=2),
            dbc.Col([dbc.Button("🚀 اجرا", id="go", color="warning", className="mt-4 w-100",
                                style={"fontWeight": "bold"})], md=2),
        ], className="justify-content-center mt-2 align-items-end"),

        dbc.Row([
            dbc.Col([html.Label("💰 سرمایه ($):", style={"color": TXT, "fontSize": "11px"}),
                     dcc.Input(id="cap", value=500, type="number", className="form-control bg-dark text-light")], md=2),
            dbc.Col([html.Label("⚡ لوریج (x):", style={"color": GOLD, "fontSize": "11px", "fontWeight": "bold"}),
                     dcc.Input(id="lev", value=5, type="number", min=1, max=125,
                               className="form-control bg-dark text-light",
                               style={"border": f"2px solid {GOLD}"})], md=2),
            dbc.Col([html.Label("⚠️ ریسک/مارجین %:", style={"color": TXT, "fontSize": "11px"}),
                     dcc.Input(id="rsk", value=2, type="number", min=0.5, max=50, step=0.5,
                               className="form-control bg-dark text-light")], md=2),
            dbc.Col([html.Label("🎯 R:R:", style={"color": TXT, "fontSize": "11px"}),
                     dcc.Input(id="rr", value=2, type="number", min=1, max=5, step=0.5,
                               className="form-control bg-dark text-light")], md=1),
            dbc.Col([html.Label("🛑 SL %:", style={"color": TXT, "fontSize": "11px"}),
                     dcc.Input(id="slp", value=0.8, type="number", min=0.1, max=5, step=0.1,
                               className="form-control bg-dark text-light")], md=1),
            dbc.Col([html.Label("📐 پنجره:", style={"color": TXT, "fontSize": "11px"}),
                     dcc.Input(id="win", value=80, type="number", min=20, max=200,
                               className="form-control bg-dark text-light")], md=2),
            dbc.Col([html.Label("🔄 بازنگری:", style={"color": TXT, "fontSize": "11px"}),
                     dcc.Input(id="rec", value=5, type="number", min=1, max=20,
                               className="form-control bg-dark text-light")], md=1),
            dbc.Col([html.Label("⚡ قدرت:", style={"color": TXT, "fontSize": "11px"}),
                     dcc.Input(id="mstr", value=95, type="number", min=50, max=100, step=5,
                               className="form-control bg-dark text-light")], md=1),
        ], className="justify-content-center mt-2 align-items-end"),

        dbc.Row([
            dbc.Col([
                html.Label("📊 تعداد کندل بک‌تست:", style={"color": GOLD, "fontSize": "12px", "fontWeight": "bold"}),
                dcc.Input(id="lb", value=500, type="number", min=50, max=10000, step=50,
                          className="form-control bg-dark text-light",
                          style={"border": f"2px solid {GOLD}", "fontWeight": "bold"}),
            ], md=4),
            dbc.Col([
                html.Label("⏱ بازه:", style={"color": MUT, "fontSize": "11px"}),
                html.Div(id="period-info", style={"color": TXT, "fontSize": "13px", "padding": "8px",
                                                  "backgroundColor": CARD, "borderRadius": "5px", "marginTop": "4px"}),
            ], md=8),
        ], className="justify-content-center mt-3 align-items-end",
            style={"padding": "10px", "border": f"1px solid {GOLD}", "borderRadius": "8px"}),

        dcc.Tabs(id="tabs", value="tab-spiral", children=[
            dcc.Tab(label="🌀 اسپیرال + S/R", value="tab-spiral",
                    style={"backgroundColor": CARD, "color": MUT},
                    selected_style={"backgroundColor": "#1a2740", "color": GOLD}),
            dcc.Tab(label="📈 بک‌تست", value="tab-bt",
                    style={"backgroundColor": CARD, "color": MUT},
                    selected_style={"backgroundColor": "#1a2740", "color": GOLD}),
        ], style={"marginTop": "15px"}),

        html.Div(id="tab-content"),
        dcc.Store(id='store')
    ], fluid=True)
], style={"background": BG, "minHeight": "100vh"})


# ==============================================================================
# 8) Callbacks
# ==============================================================================
@app.callback(Output('period-info', 'children'), Input('lb', 'value'), Input('htf', 'value'))
def period_info(lb, htf):
    if not lb or not htf: return "—"
    s = tf_sec(htf) * int(lb)
    if s < 3600:
        return f"⏱ {s / 60:.0f} دقیقه"
    elif s < 86400:
        return f"⏱ {s / 3600:.1f} ساعت"
    elif s < 2592000:
        return f"⏱ {s / 86400:.1f} روز"
    else:
        return f"⏱ {s / 2592000:.1f} ماه"


@app.callback(Output('store', 'data'),
              Input('go', 'n_clicks'),
              State('sym', 'value'), State('htf', 'value'), State('ltf', 'value'),
              State('hlim', 'value'), State('llim', 'value'),
              State('cap', 'value'), State('lev', 'value'), State('rsk', 'value'),
              State('rr', 'value'), State('slp', 'value'),
              State('win', 'value'), State('rec', 'value'), State('mstr', 'value'),
              State('lb', 'value'))
def run(n, sym, htf, ltf, hlim, llim, cap, lev, rsk, rr, slp, win, rec, mstr, lb):
    if not n: return {"ok": False, "err": "دکمه اجرا را بزنید"}
    sym = (sym or DEFAULT_SYMBOL).upper()
    hlim, llim, lb = int(hlim or 1000), int(llim or 1000), int(lb or 500)
    lev = int(lev or 5)

    if lb > hlim:
        return {"ok": False, "err": f"⚠️ کندل بک‌تست ({lb}) > کندل HTF ({hlim})"}

    hs, ls = tf_sec(htf), tf_sec(ltf)
    df_h = get_klines(sym, htf, limit=hlim)
    df_l = get_klines(sym, ltf, limit=llim)

    if df_h.empty: return {"ok": False, "err": "⚠️ دیتای HTF دریافت نشد"}
    if df_l.empty: return {"ok": False, "err": "⚠️ دیتای LTF دریافت نشد"}

    traces, st, pmin, psc, Xr, Yr, ny = build_spiral_figure(df_h, df_l, hs, ls)
    cur = df_h["close"].iloc[-1]
    sr = extract_sr(Xr, Yr, ny, pmin, psc, cur)

    trades, eq, eqt, stats = run_backtest(
        df_h, df_l, lookback=lb, window=int(win or 80), recalc=int(rec or 5),
        min_str=int(mstr or 95), cap0=float(cap or 500), lev=lev,
        risk=float(rsk or 2) / 100, rr=float(rr or 2), slp=float(slp or 0.8) / 100)

    trace_data = []
    for t in traces:
        td = {"x": t.x.tolist() if hasattr(t.x, 'tolist') else list(t.x),
              "y": t.y.tolist() if hasattr(t.y, 'tolist') else list(t.y),
              "mode": t.mode}
        if t.mode == 'lines':
            td["line"] = {"color": t.line.color, "width": t.line.width}
            td["opacity"] = t.opacity if t.opacity else 1
        elif t.mode == 'markers':
            mc = t.marker.color
            td["marker"] = {"size": t.marker.size,
                            "color": mc.tolist() if hasattr(mc, 'tolist') else mc}
        td["customdata"] = t.customdata if t.customdata else None
        td["hovertemplate"] = t.hovertemplate if t.hovertemplate else ""
        trace_data.append(td)

    return {"ok": True, "sym": sym, "htf": htf, "ltf": ltf,
            "cur": cur, "cur_str": fmt_p(cur),
            "sr": sr, "traces": trace_data,
            "st": st, "pmin": pmin, "psc": psc,
            "trades": trades, "eq": eq, "eqt": eqt, "stats": stats, "lb": lb}


@app.callback(Output('tab-content', 'children'), Input('tabs', 'value'), Input('store', 'data'))
def render(tab, data):
    if not data or not data.get("ok"):
        err = data.get("err", "⚠️ ابتدا «اجرا» را بزنید") if data else "⚠️ ابتدا «اجرا» را بزنید"
        return html.P(err, style={"color": RED, "textAlign": "center", "marginTop": "50px", "fontSize": "16px"})
    if tab == "tab-spiral":
        return render_spiral(data)
    else:
        return render_bt(data)


def render_spiral(data):
    traces_data = data.get("traces", [])
    sr = data.get("sr", [])
    st, pmin, psc = data.get("st", 1), data.get("pmin", 0), data.get("psc", 1)
    cur_str, sym = data.get("cur_str", ""), data.get("sym", "")

    fig = go.Figure()
    for td in traces_data:
        if td["mode"] == "lines":
            fig.add_trace(go.Scattergl(x=td["x"], y=td["y"], mode="lines",
                                       line=dict(color=td["line"]["color"], width=td["line"]["width"]),
                                       opacity=td.get("opacity", 1), customdata=td.get("customdata"),
                                       hovertemplate=td.get("hovertemplate", ""), showlegend=False))
        elif td["mode"] == "markers":
            fig.add_trace(go.Scattergl(x=td["x"], y=td["y"], mode="markers",
                                       marker=dict(size=td["marker"]["size"], color=td["marker"]["color"]),
                                       customdata=td.get("customdata"),
                                       hovertemplate=td.get("hovertemplate", ""), showlegend=False))

    for lv in sr:
        c = GREEN if lv["type_code"] == "support" else RED
        yv = (lv["price"] - pmin) * psc
        fig.add_hline(y=yv, line_dash="dash", line_color=c, line_width=1 + lv["strength"] / 50,
                      opacity=0.4 + lv["strength"] / 200,
                      annotation_text=f'{lv["price_str"]} ({lv["strength"]}%)',
                      annotation_position="right", annotation_font_size=10, annotation_font_color=c)

    yt = np.linspace(0, st, 6)
    yl = [fmt_p(pmin + v / psc) for v in yt]
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
                      title=dict(text=f"🌀 {sym} | {cur_str}", font=dict(color=GOLD, size=14)),
                      xaxis=dict(showgrid=False, zeroline=False, visible=False),
                      yaxis=dict(tickmode='array', tickvals=yt, ticktext=yl, showgrid=True, gridcolor=LINE,
                                 title="Price", color=TXT, scaleanchor="x", scaleratio=1),
                      margin=dict(l=70, r=100, t=60, b=30), height=500, hovermode="closest", uirevision='constant')

    tbl_data = [{"#": l["rank"], "قیمت": l["price_str"], "نوع": l["type"],
                 "قدرت": l["strength"], "فاصله%": l["distance_%"]} for l in sr]
    ns = sum(1 for l in sr if l["type_code"] == "support")
    nr = sum(1 for l in sr if l["type_code"] == "resistance")

    return html.Div([
        dcc.Graph(figure=fig),
        html.P(f"🟢 {ns} حمایت | 🔴 {nr} مقاومت | 💰 {cur_str}",
               style={"color": MUT, "textAlign": "center", "fontSize": "13px", "marginTop": "10px"}),
        html.Div([dash_table.DataTable(
            data=tbl_data, columns=[{"name": k, "id": k} for k in tbl_data[0].keys()] if tbl_data else [],
            style_table={'overflowX': 'auto', 'border': f'1px solid {LINE}'},
            style_cell={'backgroundColor': CARD, 'color': TXT, 'textAlign': 'center',
                        'border': f'1px solid {LINE}', 'fontSize': '12px', 'padding': '6px'},
            style_header={'backgroundColor': '#1a2740', 'color': GOLD, 'fontWeight': 'bold'},
            style_data_conditional=[
                {'if': {'filter_query': '{نوع} contains "Support"'}, 'color': GREEN},
                {'if': {'filter_query': '{نوع} contains "Resistance"'}, 'color': RED}],
            page_size=12, sort_action="native")], style={"margin": "10px 0 30px"})])


def render_bt(data):
    trades = data.get("trades", [])
    eq, eqt = data.get("eq", []), data.get("eqt", [])
    stats = data.get("stats", {})
    sym, lb = data.get("sym", ""), data.get("lb", 0)
    lev = stats.get("leverage", 1)

    cards = dbc.Row([
        dbc.Col(html.Div([html.Div(f"{stats.get('wr', 0)}%", className="sv", style={"color": GREEN}),
                          html.Div("Win Rate", className="sl")], className="sc"), md=1),
        dbc.Col(html.Div([html.Div(f"{stats.get('total', 0)}", className="sv", style={"color": GOLD}),
                          html.Div("Trades", className="sl")], className="sc"), md=1),
        dbc.Col(html.Div([html.Div(f"${stats.get('final', 0):.2f}", className="sv",
                                   style={"color": GREEN if stats.get('pnl', 0) >= 0 else RED}),
                          html.Div("Final $", className="sl")], className="sc"), md=2),
        dbc.Col(html.Div([html.Div(f"{stats.get('ret', 0):.1f}%", className="sv",
                                   style={"color": GREEN if stats.get('ret', 0) >= 0 else RED}),
                          html.Div("Return", className="sl")], className="sc"), md=1),
        dbc.Col(html.Div([html.Div(f"{stats.get('mdd', 0):.1f}%", className="sv", style={"color": RED}),
                          html.Div("Max DD", className="sl")], className="sc"), md=1),
        dbc.Col(html.Div([html.Div(f"{stats.get('pf', 0):.2f}", className="sv", style={"color": CYAN}),
                          html.Div("PF", className="sl")], className="sc"), md=1),
        dbc.Col(html.Div([html.Div(f"{lev}x", className="sv", style={"color": GOLD}),
                          html.Div("Leverage", className="sl")], className="sc"), md=1),
        dbc.Col(html.Div([html.Div(f"{stats.get('avg_roi', 0):.1f}%", className="sv", style={"color": CYAN}),
                          html.Div("Avg ROI/Margin", className="sl")], className="sc"), md=2),
        dbc.Col(html.Div([html.Div(f"${stats.get('comm', 0):.2f}", className="sv", style={"color": RED}),
                          html.Div("Commission", className="sl")], className="sc"), md=2),
    ], className="mt-3 mb-2")

    info = html.Div([
        html.P(f"📊 Lookback: {stats.get('lookback', 0)} | Actual: {stats.get('actual', 0)} | "
               f"از {stats.get('start', '—')} تا {stats.get('end', '—')} | "
               f"لوریج: {lev}x | "
               f"ارزش پوزیشن‌ها: ${stats.get('tpv', 0):,.0f} | "
               f"ماژین: ${stats.get('tmg', 0):,.0f}",
               style={"color": GOLD, "fontSize": "12px", "textAlign": "center",
                      "padding": "8px", "backgroundColor": CARD, "borderRadius": "5px",
                      "border": f"1px solid {GOLD}"})
    ], className="mb-2")

    fig = go.Figure()
    if eq:
        fig.add_trace(go.Scatter(x=eqt, y=eq, mode='lines', line=dict(color=GOLD, width=2),
                                 fill='tozeroy', fillcolor='rgba(240,185,11,0.08)'))
        fig.add_hline(y=eq[0], line_dash="dash", line_color=MUT, annotation_text=f"Start: ${eq[0]:.0f}")
        for t in trades:
            c = GREEN if t["pnl"] > 0 else RED
            fig.add_vline(x=t["entry_time"], line_color=c, line_width=1, opacity=0.3)
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
                      title=dict(text=f"📈 {sym} | {lev}x Leverage | Win Rate: {stats.get('wr', 0)}%",
                                 font=dict(color=GOLD, size=14)),
                      xaxis=dict(color=MUT, gridcolor=LINE), yaxis=dict(title="$", color=TXT, gridcolor=LINE),
                      height=300, margin=dict(l=50, r=30, t=50, b=40), hovermode="x unified")

    ft = []
    for t in trades:
        ft.append({
            "#": t["id"], "جهت": t["dir"],
            "ورود": t["entry_time"][:16],
            "قیمت ورود": fmt_p(t["entry"]),
            "SL": fmt_p(t["sl"]), "TP": fmt_p(t["tp"]),
            "لوریج": f"{t['lev']}x",
            "ارزش پوزیشن": f"${t['pos_value']:,.0f}",
            "مارجین": f"${t['margin_used']:,.2f}",
            "خروج": t["exit_time"][:16] if t["exit_time"] else "—",
            "قیمت خروج": fmt_p(t["exit_price"]) if t["exit_price"] else "—",
            "P&L": f"${t['pnl']:.2f}",
            "ROI/مارجین": f"{t['roi_margin']:.1f}%",
            "کمیسیون": f"${t['total_comm']:.4f}",
            "نتیجه": t["result"],
            "سرمایه": f"${t['cap_after']:.0f}"
        })

    tbl = dash_table.DataTable(
        data=ft, columns=[{"name": k, "id": k} for k in ft[0].keys()] if ft else [],
        style_table={'overflowX': 'auto', 'maxHeight': '450px', 'overflowY': 'auto',
                     'border': f'1px solid {LINE}'},
        style_cell={'backgroundColor': CARD, 'color': TXT, 'textAlign': 'center',
                    'border': f'1px solid {LINE}', 'fontSize': '11px', 'padding': '5px 6px',
                    'fontFamily': 'monospace'},
        style_header={'backgroundColor': '#1a2740', 'color': GOLD, 'fontWeight': 'bold', 'fontSize': '10px'},
        style_data_conditional=[
            {'if': {'filter_query': '{نتیجه} = "WIN ✅"'}, 'color': GREEN, 'fontWeight': 'bold'},
            {'if': {'filter_query': '{نتیجه} = "LOSS ❌"'}, 'color': RED},
        ], page_size=20, sort_action="native")

    return html.Div([info, cards, dcc.Graph(figure=fig),
                     html.H6("📋 معاملات", style={"color": GOLD, "textAlign": "center", "marginTop": "15px"}),
                     tbl, html.Div(style={"height": "30px"})])


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8073, use_reloader=False)