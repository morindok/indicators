# -*- coding: utf-8 -*-
"""
🌌 Golden Spiral Fractal Timeframe Analyzer - Bybit (v7 - Volume-Based S/R)
------------------------------------------------------------------
استخراج حمایت/مقاومت بر اساس حجم انباشته زیر اسپیرال‌ها
هر کندل حجم خود را در طول مسیر اسپیرال پخش می‌کند
"""

import numpy as np
import pandas as pd
import requests
import dash
from dash import dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

# ==============================================================================
# 0) تنظیمات رنگی و تم
# ==============================================================================
BG, CARD, LINE, TXT, MUT = "#0b1220", "#121c30", "#23314d", "#e8ecf4", "#8fa3c0"
GOLD = "#f0b90b"
GREEN, RED = "#00e676", "#ff5252"
GREEN_LTF, RED_LTF = "#69f0ae", "#ff8a80"
NODE_COLOR = "#ffffff"
SR_SUPPORT = "#00e676"
SR_RESIST = "#ff5252"

DEFAULT_SYMBOL = "BTCUSDT"
TIMEFRAMES = ['1', '3', '5', '15', '30', '60', '120', '240', '360', '720', 'D', 'W', 'M']

# ─── پارامترهای بصری ───
SPREAD_FACTOR = 4.0
HTF_LOOPS = 1.0
LTF_LOOPS = 0.75
LTF_SCALE = 0.12
HTF_LINE_WIDTH = 2.0
LTF_LINE_WIDTH = 1.0
NODE_SIZE = 4
NUM_POINTS_HTF = 40
NUM_POINTS_LTF = 16

# ─── پارامترهای S/R حجمی ───
SR_BINS = 100
SR_THRESHOLD = 1.4
SR_MAX_LEVELS = 15
HTF_VOL_WEIGHT = 3.0     # ضریب وزن حجم HTF
LTF_VOL_WEIGHT = 1.0     # ضریب وزن حجم LTF
NODE_VOL_WEIGHT = 2.0    # ضریب وزن حجم گره‌ها


# ==============================================================================
# 1) ⭐ فرمت هوشمند قیمت
# ==============================================================================
def get_price_decimals(price):
    abs_p = abs(price)
    if abs_p == 0: return 2
    elif abs_p >= 10000: return 0
    elif abs_p >= 1000: return 1
    elif abs_p >= 1: return 2
    elif abs_p >= 0.1: return 4
    elif abs_p >= 0.01: return 5
    elif abs_p >= 0.001: return 6
    elif abs_p >= 0.0001: return 7
    elif abs_p >= 0.00001: return 8
    else: return 10


def format_price(price):
    d = get_price_decimals(price)
    return f"{price:.{d}f}"


def format_price_array(prices):
    if len(prices) == 0: return []
    median_p = np.nanmedian(prices)
    d = get_price_decimals(median_p)
    return [f"{p:.{d}f}" for p in prices]


def format_volume(vol):
    """فرمت حجم به صورت خوانا."""
    if vol >= 1_000_000_000: return f"{vol/1_000_000_000:.2f}B"
    elif vol >= 1_000_000: return f"{vol/1_000_000:.2f}M"
    elif vol >= 1_000: return f"{vol/1_000:.1f}K"
    else: return f"{vol:.0f}"


# ==============================================================================
# 2) اتصال REST بایبیت
# ==============================================================================
REST_CANDIDATES = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
})
_ACTIVE_REST_BASE = {"url": None}

def bybit_get(path, params, timeout=10):
    cands = ([_ACTIVE_REST_BASE["url"]] if _ACTIVE_REST_BASE["url"] else []) + \
            [b for b in REST_CANDIDATES if b != _ACTIVE_REST_BASE["url"]]
    for base in cands:
        try:
            r = SESSION.get(f"{base}{path}", params=params, timeout=timeout)
            if r.status_code in (403, 451): continue
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
    if not d or "list" not in (d.get("result") or {}): return pd.DataFrame()
    lst = d["result"]["list"]
    if not lst: return pd.DataFrame()
    df = pd.DataFrame(lst, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
    df["ts_num"] = df["ts"].astype(float) / 1000.0
    for c in ["open", "high", "low", "close", "volume", "turnover"]:
        df[c] = df[c].astype(float)
    return df.sort_values("ts_num").reset_index(drop=True)

def get_interval_seconds(tf):
    tf = str(tf)
    if tf == 'D': return 86400
    if tf == 'W': return 604800
    if tf == 'M': return 2592000
    return int(tf) * 60


# ==============================================================================
# 3) موتور هندسه اسپیرال (Vectorized)
# ==============================================================================
def generate_spirals_vectorized(x0, y0, x1, y1, directions, num_points=40, loops=1.0):
    N = len(x0)
    if N == 0:
        return np.empty((0, num_points)), np.empty((0, num_points))

    b = 0.3063489
    dx, dy = x1 - x0, y1 - y0
    dist = np.hypot(dx, dy)
    target_angle = np.arctan2(dy, dx)

    theta_base = np.linspace(0, loops * 2 * np.pi, num_points)
    r = np.exp(b * theta_base) - 1
    max_r = r[-1]
    scale = np.where(max_r > 0, dist / max_r, 0)

    theta_directed = directions[:, None] * theta_base[None, :]
    x_std = r[None, :] * np.cos(theta_directed) * scale[:, None]
    y_std = r[None, :] * np.sin(theta_directed) * scale[:, None]

    end_angle_std = np.arctan2(y_std[:, -1], x_std[:, -1])
    rotation = target_angle - end_angle_std

    cos_rot = np.cos(rotation)[:, None]
    sin_rot = np.sin(rotation)[:, None]

    x_rot = x_std * cos_rot - y_std * sin_rot
    y_rot = x_std * sin_rot + y_std * cos_rot

    return x_rot + x0[:, None], y_rot + y0[:, None]


def flatten_with_nan(X, Y, mask=None):
    if mask is not None:
        X, Y = X[mask], Y[mask]
    N = len(X)
    if N == 0:
        return np.array([]), np.array([])
    np_ = X.shape[1]
    X_flat, Y_flat = X.flatten(), Y.flatten()
    if N > 1:
        ni = np.arange(1, N) * np_
        X_flat = np.insert(X_flat, ni, np.nan)
        Y_flat = np.insert(Y_flat, ni, np.nan)
    return X_flat, Y_flat


def build_customdata_list(times_flat, prices_str_flat, n_spirals, num_points):
    custom_list = [[t, p] for t, p in zip(times_flat, prices_str_flat)]
    if n_spirals > 1:
        for idx in sorted(np.arange(1, n_spirals) * num_points):
            custom_list.insert(idx, [None, None])
    return custom_list


# ==============================================================================
# 4) 🎯 استخراج S/R بر اساس حجم انباشته زیر اسپیرال‌ها
# ==============================================================================
def extract_sr_levels_by_volume(Y_htf_raw, Y_ltf_raw, node_y_htf,
                                 htf_volumes, ltf_volumes_valid,
                                 price_min, price_scale, current_price):
    """
    ═══════════════════════════════════════════════════════════
    منطق حجم انباشته:
    
    هر کندل حجم خود را در طول مسیر اسپیرال «پخش» می‌کند.
    اگر یک کندل 1000 واحد حجم داشته باشد و اسپیرال آن 40 نقطه دارد،
    هر نقطه 25 واحد حجم دریافت می‌کند.
    
    سطوحی که حجم انباشته بیشتری دارند = حمایت/مقاومت قوی‌تر.
    
    وزن‌دهی:
      • HTF × 3.0 (حجم تایم بالا مهم‌تر)
      • LTF × 1.0
      • گره‌ها × 2.0 (تمرکز حجم در نقاط اتصال)
    ═══════════════════════════════════════════════════════════
    """
    
    # ─── HTF: پخش حجم روی اسپیرال ───
    htf_prices_flat = (Y_htf_raw.flatten() / price_scale) + price_min
    n_htf = len(htf_volumes)
    
    # هر کندل حجمش را بین NUM_POINTS_HTF نقطه تقسیم می‌کند
    htf_vol_per_point = np.repeat(htf_volumes * HTF_VOL_WEIGHT / NUM_POINTS_HTF, NUM_POINTS_HTF)
    
    valid_h = ~np.isnan(htf_prices_flat)
    htf_p = htf_prices_flat[valid_h]
    htf_w = htf_vol_per_point[valid_h]
    
    # ─── LTF: پخش حجم روی اسپیرال ───
    ltf_p, ltf_w = np.array([]), np.array([])
    if Y_ltf_raw is not None and len(Y_ltf_raw) > 0 and len(ltf_volumes_valid) > 0:
        ltf_prices_flat = (Y_ltf_raw.flatten() / price_scale) + price_min
        ltf_vol_per_point = np.repeat(ltf_volumes_valid * LTF_VOL_WEIGHT / NUM_POINTS_LTF, NUM_POINTS_LTF)
        
        valid_l = ~np.isnan(ltf_prices_flat)
        ltf_p = ltf_prices_flat[valid_l]
        ltf_w = ltf_vol_per_point[valid_l]
    
    # ─── گره‌ها: تمرکز حجم در نقاط اتصال ───
    node_prices = (node_y_htf / price_scale) + price_min
    node_weights = htf_volumes * NODE_VOL_WEIGHT  # حجم کامل در گره
    
    # ─── ترکیب همه ───
    all_prices = np.concatenate([htf_p, ltf_p, node_prices])
    all_weights = np.concatenate([htf_w, ltf_w, node_weights])
    
    if len(all_prices) == 0:
        return [], np.array([]), np.array([])
    
    price_range = all_prices.max() - all_prices.min()
    if price_range == 0:
        price_range = 1
    
    # ─── هیستوگرام حجمی ───
    hist, bin_edges = np.histogram(all_prices, bins=SR_BINS, weights=all_weights)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    
    # ─── شناسایی قله‌های حجمی ───
    mean_hist = np.mean(hist)
    peaks = []
    for i in range(2, len(hist) - 2):
        if (hist[i] > hist[i-1] and hist[i] > hist[i+1] and
            hist[i] > hist[i-2] and hist[i] > hist[i+2] and
            hist[i] > mean_hist * SR_THRESHOLD):
            peaks.append((bin_centers[i], hist[i]))
    
    peaks.sort(key=lambda x: x[1], reverse=True)
    
    # ─── ساخت سطوح S/R ───
    sr_levels = []
    max_vol = peaks[0][1] if peaks else 1
    total_volume = np.sum(all_weights)
    
    for idx, (price, vol_strength) in enumerate(peaks[:SR_MAX_LEVELS]):
        norm_strength = int((vol_strength / max_vol) * 100)
        vol_pct = (vol_strength / total_volume) * 100
        
        if price < current_price:
            level_type = "Support 🟢"
            type_code = "support"
        else:
            level_type = "Resistance 🔴"
            type_code = "resistance"
        
        distance_pct = ((price - current_price) / current_price) * 100
        
        # تفکیک حجم هر منبع در این بازه
        band_w = price_range / SR_BINS * 1.5
        htf_vol_in_band = np.sum(htf_w[np.abs(htf_p - price) < band_w]) if len(htf_w) > 0 else 0
        ltf_vol_in_band = np.sum(ltf_w[np.abs(ltf_p - price) < band_w]) if len(ltf_w) > 0 else 0
        node_vol_in_band = np.sum(node_weights[np.abs(node_prices - price) < band_w])
        
        # تعیین منبع غالب
        sources = []
        if htf_vol_in_band > 0: sources.append(f"HTF({format_volume(htf_vol_in_band)})")
        if ltf_vol_in_band > 0: sources.append(f"LTF({format_volume(ltf_vol_in_band)})")
        if node_vol_in_band > 0: sources.append(f"Node({format_volume(node_vol_in_band)})")
        source_str = " + ".join(sources) if sources else "—"
        
        sr_levels.append({
            "rank": idx + 1,
            "price": price,
            "price_str": format_price(price),
            "type": level_type,
            "type_code": type_code,
            "strength": norm_strength,
            "vol_accumulated": format_volume(vol_strength),
            "vol_pct": round(vol_pct, 2),
            "htf_vol": format_volume(htf_vol_in_band),
            "ltf_vol": format_volume(ltf_vol_in_band),
            "node_vol": format_volume(node_vol_in_band),
            "source": source_str,
            "distance_%": round(distance_pct, 4)
        })
    
    return sr_levels, bin_centers, hist


# ==============================================================================
# 5) نگاشت فراکتالی کامل
# ==============================================================================
def map_ltf_to_htf_spiral_optimized(ltf_df, htf_df, htf_interval_sec, ltf_interval_sec):
    min_ts = htf_df["ts_num"].min()
    time_span = htf_df["ts_num"].max() - min_ts
    price_min = htf_df["low"].min()
    price_max = htf_df["high"].max()
    price_span = price_max - price_min

    if price_span == 0: price_span = 1
    if time_span == 0: time_span = 1

    spread_time = time_span * SPREAD_FACTOR
    price_scale = spread_time / price_span

    htf_ts = htf_df["ts_num"].values
    htf_open = htf_df["open"].values
    htf_close = htf_df["close"].values
    htf_volumes = htf_df["volume"].values

    x0_htf = (htf_ts - min_ts) * SPREAD_FACTOR
    y0_htf = (htf_open - price_min) * price_scale
    x1_htf = x0_htf + htf_interval_sec * SPREAD_FACTOR
    y1_htf = (htf_close - price_min) * price_scale

    bullish_htf = htf_close >= htf_open
    directions_htf = np.where(bullish_htf, 1.0, -1.0)

    X_htf_raw, Y_htf_raw = generate_spirals_vectorized(
        x0_htf, y0_htf, x1_htf, y1_htf,
        directions=directions_htf,
        num_points=NUM_POINTS_HTF, loops=HTF_LOOPS
    )

    alphas = np.linspace(0, 1, NUM_POINTS_HTF)
    t_ends = htf_ts + htf_interval_sec
    times_mat = htf_ts[:, None] + alphas[None, :] * (t_ends - htf_ts)[:, None]
    prices_mat = htf_open[:, None] + alphas[None, :] * (htf_close - htf_open)[:, None]

    traces = []

    for mask, color in [(bullish_htf, GREEN), (~bullish_htf, RED)]:
        n_sub = mask.sum()
        if n_sub == 0: continue
        X_sub, Y_sub = flatten_with_nan(X_htf_raw, Y_htf_raw, mask)
        times_str_sub = pd.to_datetime(times_mat[mask].flatten(), unit='s').strftime('%Y-%m-%d %H:%M').values
        prices_str_sub = format_price_array(prices_mat[mask].flatten())
        custom_list = build_customdata_list(times_str_sub, prices_str_sub, n_sub, NUM_POINTS_HTF)
        traces.append(go.Scattergl(
            x=X_sub, y=Y_sub, mode='lines',
            line=dict(color=color, width=HTF_LINE_WIDTH), opacity=0.9,
            customdata=custom_list,
            hovertemplate="<b>⏱ %{customdata[0]}</b><br>💰 %{customdata[1]}<extra></extra>",
            showlegend=False
        ))

    # گره‌ها
    node_colors = np.where(bullish_htf, GREEN, RED)
    node_times = pd.to_datetime(htf_ts, unit='s').strftime('%Y-%m-%d %H:%M').values
    node_prices_str = format_price_array(htf_open)
    traces.append(go.Scattergl(
        x=x0_htf, y=y0_htf, mode='markers',
        marker=dict(size=NODE_SIZE, color=node_colors, symbol='circle',
                    line=dict(width=1, color=NODE_COLOR)),
        customdata=[[t, p] for t, p in zip(node_times, node_prices_str)],
        hovertemplate="<b>🔗 Node</b><br>⏱ %{customdata[0]}<br>💰 %{customdata[1]}<extra></extra>",
        showlegend=False
    ))

    # LTF
    ltf_ts = ltf_df["ts_num"].values
    ltf_open = ltf_df["open"].values
    ltf_close = ltf_df["close"].values
    ltf_volumes = ltf_df["volume"].values

    parent_indices = np.searchsorted(htf_ts, ltf_ts, side='right') - 1
    htf_ends = htf_ts + htf_interval_sec
    valid_mask = (parent_indices >= 0) & (parent_indices < len(htf_ts))
    valid_mask &= (ltf_ts < htf_ends[parent_indices])

    valid_ltf_ts = ltf_ts[valid_mask]
    valid_ltf_open = ltf_open[valid_mask]
    valid_ltf_close = ltf_close[valid_mask]
    valid_ltf_volumes = ltf_volumes[valid_mask]
    valid_parents = parent_indices[valid_mask]

    X_ltf_raw, Y_ltf_raw = None, None

    if len(valid_ltf_ts) > 0:
        parent_start = htf_ts[valid_parents]
        parent_end = htf_ends[valid_parents]
        progress_ratio = (valid_ltf_ts - parent_start) / (parent_end - parent_start)
        point_indices = (progress_ratio * (NUM_POINTS_HTF - 1)).astype(int)

        base_x = X_htf_raw[valid_parents, point_indices]
        base_y = Y_htf_raw[valid_parents, point_indices]

        x1_ltf = base_x + ltf_interval_sec * SPREAD_FACTOR * LTF_SCALE
        y1_ltf = base_y + (valid_ltf_close - valid_ltf_open) * price_scale * LTF_SCALE

        bullish_ltf = valid_ltf_close >= valid_ltf_open
        directions_ltf = np.where(bullish_ltf, 1.0, -1.0)

        X_ltf_raw, Y_ltf_raw = generate_spirals_vectorized(
            base_x, base_y, x1_ltf, y1_ltf,
            directions=directions_ltf,
            num_points=NUM_POINTS_LTF, loops=LTF_LOOPS
        )

        alphas_ltf = np.linspace(0, 1, NUM_POINTS_LTF)
        t_ends_ltf = valid_ltf_ts + ltf_interval_sec
        times_mat_ltf = valid_ltf_ts[:, None] + alphas_ltf[None, :] * (t_ends_ltf - valid_ltf_ts)[:, None]
        prices_mat_ltf = valid_ltf_open[:, None] + alphas_ltf[None, :] * (valid_ltf_close - valid_ltf_open)[:, None]

        for mask, color in [(bullish_ltf, GREEN_LTF), (~bullish_ltf, RED_LTF)]:
            n_sub = mask.sum()
            if n_sub == 0: continue
            X_sub, Y_sub = flatten_with_nan(X_ltf_raw, Y_ltf_raw, mask)
            times_str_sub = pd.to_datetime(times_mat_ltf[mask].flatten(), unit='s').strftime('%Y-%m-%d %H:%M').values
            prices_str_sub = format_price_array(prices_mat_ltf[mask].flatten())
            custom_list = build_customdata_list(times_str_sub, prices_str_sub, n_sub, NUM_POINTS_LTF)
            traces.append(go.Scattergl(
                x=X_sub, y=Y_sub, mode='lines',
                line=dict(color=color, width=LTF_LINE_WIDTH), opacity=0.6,
                customdata=custom_list,
                hovertemplate="<b>⏱ %{customdata[0]}</b><br>💰 %{customdata[1]}<extra></extra>",
                showlegend=False
            ))

    return (traces, spread_time, price_min, price_scale,
            X_htf_raw, Y_htf_raw, X_ltf_raw, Y_ltf_raw,
            y0_htf, htf_volumes, valid_ltf_volumes)


# ==============================================================================
# 6) رابط کاربری Dash
# ==============================================================================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])
app.title = "Golden Spiral Fractals + Volume S/R"

app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}<title>{%title%}</title>{%favicon%}{%css%}
        <style>
            .dash-dropdown .Select-control { background-color: #121c30 !important; border: 1px solid #23314d !important; }
            .dash-dropdown .Select-value-label, .dash-dropdown .Select-placeholder { color: #e8ecf4 !important; }
            .dash-dropdown .Select-menu-outer { background-color: #121c30 !important; border: 1px solid #23314d !important; }
            .dash-dropdown .Select-option { background-color: #121c30 !important; color: #e8ecf4 !important; }
            .dash-dropdown .Select-option:hover { background-color: #23314d !important; }
            body { background-color: #0b1220; }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>{%config%}{%scripts%}{%renderer%}</footer>
    </body>
</html>
'''

app.layout = html.Div([
    dbc.Container([
        html.H3("🌀 فراکتال اسپیرال + حمایت/مقاومت حجمی",
                style={"color": GOLD, "textAlign": "center", "marginTop": "15px", "fontWeight": "bold"}),
        html.P("📊 حجم هر کندل در طول مسیر اسپیرال پخش می‌شود → انباشت حجم = سطح قوی",
               style={"color": MUT, "textAlign": "center", "fontSize": "13px"}),

        dbc.Row([
            dbc.Col([
                html.Label("نماد:", style={"color": TXT}),
                dcc.Input(id="symbol-input", value=DEFAULT_SYMBOL, type="text",
                          className="form-control bg-dark text-light")
            ], md=2),
            dbc.Col([
                html.Label("HTF:", style={"color": TXT}),
                dcc.Dropdown(id="htf-dropdown",
                    options=[{'label': f'{tf}m' if tf not in ['D','W','M'] else tf, 'value': tf} for tf in TIMEFRAMES],
                    value='60')
            ], md=2),
            dbc.Col([
                html.Label("LTF:", style={"color": TXT}),
                dcc.Dropdown(id="ltf-dropdown",
                    options=[{'label': f'{tf}m' if tf not in ['D','W','M'] else tf, 'value': tf} for tf in TIMEFRAMES],
                    value='15')
            ], md=2),
            dbc.Col([
                html.Label("کندل HTF:", style={"color": TXT}),
                dcc.Input(id="htf-limit", value=200, type="number", min=10, max=1000,
                          className="form-control bg-dark text-light")
            ], md=2),
            dbc.Col([
                html.Label("کندل LTF:", style={"color": TXT}),
                dcc.Input(id="ltf-limit", value=600, type="number", min=10, max=1000,
                          className="form-control bg-dark text-light")
            ], md=2),
            dbc.Col([
                dbc.Button("🌌 تحلیل حجمی", id="draw-btn", color="warning",
                           className="mt-4 w-100", style={"fontWeight": "bold"})
            ], md=2)
        ], className="justify-content-center mt-2 align-items-end"),

        dbc.Row([
            dbc.Col([
                html.Label("📐 Spread:", style={"color": MUT, "fontSize": "12px"}),
                dcc.Slider(id="spread-slider", min=1, max=10, step=0.5, value=SPREAD_FACTOR,
                           marks={i: str(i) for i in range(1, 11)})
            ], md=6),
            dbc.Col([
                html.Label("🔄 Loops:", style={"color": MUT, "fontSize": "12px"}),
                dcc.Slider(id="loops-slider", min=0.5, max=2.5, step=0.25, value=HTF_LOOPS,
                           marks={i: str(i) for i in [1, 2]})
            ], md=6),
        ], className="mt-2 mb-1"),

        # ─── نمودار اسپیرال ───
        dcc.Loading(
            id="loading-chart", type="circle", color=GOLD,
            children=dcc.Graph(id="spiral-chart", style={"height": "55vh"},
                               config={'scrollZoom': True})
        ),

        # ─── نمودار پروفایل حجم ───
        dcc.Loading(
            id="loading-vol", type="circle", color=CYAN if 'CYAN' in dir() else "#00e5ff",
            children=dcc.Graph(id="volume-profile-chart", style={"height": "25vh"})
        ),

        # ─── جدول S/R ───
        html.H5("📊 سطوح حمایت/مقاومت بر اساس حجم انباشته زیر اسپیرال‌ها",
                style={"color": GOLD, "textAlign": "center", "marginTop": "15px"}),
        html.Div(id="sr-summary", style={"color": MUT, "textAlign": "center", "fontSize": "13px", "marginBottom": "8px"}),

        html.Div([
            dash_table.DataTable(
                id="sr-table",
                columns=[
                    {"name": "#", "id": "rank"},
                    {"name": "قیمت", "id": "price_str"},
                    {"name": "نوع", "id": "type"},
                    {"name": "قدرت", "id": "strength"},
                    {"name": "حجم انباشته", "id": "vol_accumulated"},
                    {"name": "٪ حجم", "id": "vol_pct"},
                    {"name": "حجم HTF", "id": "htf_vol"},
                    {"name": "حجم LTF", "id": "ltf_vol"},
                    {"name": "حجم گره", "id": "node_vol"},
                    {"name": "فاصله%", "id": "distance_%"},
                ],
                style_table={
                    'overflowX': 'auto',
                    'borderRadius': '8px',
                    'border': f'1px solid {LINE}'
                },
                style_cell={
                    'backgroundColor': CARD,
                    'color': TXT,
                    'textAlign': 'center',
                    'border': f'1px solid {LINE}',
                    'fontSize': '12px',
                    'padding': '7px 10px',
                    'fontFamily': 'monospace'
                },
                style_header={
                    'backgroundColor': '#1a2740',
                    'color': GOLD,
                    'fontWeight': 'bold',
                    'fontSize': '12px',
                    'border': f'1px solid {LINE}'
                },
                style_data_conditional=[
                    {'if': {'filter_query': '{type_code} = "support"'}, 'color': GREEN, 'fontWeight': 'bold'},
                    {'if': {'filter_query': '{type_code} = "resistance"'}, 'color': RED, 'fontWeight': 'bold'},
                    {'if': {'column_id': 'strength', 'filter_query': '{strength} > 70'},
                     'backgroundColor': '#1a3a1a', 'color': '#00ff88', 'fontWeight': 'bold'},
                ],
                page_size=15,
                sort_action="native",
                sort_mode="single",
            )
        ], style={"marginTop": "8px", "marginBottom": "30px"}),

        dcc.Store(id='graph-state', storage_type='session')
    ], fluid=True)
], style={"background": BG, "minHeight": "100vh"})


# ==============================================================================
# 7) کال‌بک اصلی
# ==============================================================================
@app.callback(
    [Output('spiral-chart', 'figure'),
     Output('volume-profile-chart', 'figure'),
     Output('sr-table', 'data'),
     Output('sr-summary', 'children')],
    Input('draw-btn', 'n_clicks'),
    Input('spread-slider', 'value'),
    Input('loops-slider', 'value'),
    State('symbol-input', 'value'),
    State('htf-dropdown', 'value'),
    State('ltf-dropdown', 'value'),
    State('htf-limit', 'value'),
    State('ltf-limit', 'value'),
    State('graph-state', 'data')
)
def update_dashboard(n_clicks, spread_val, loops_val, symbol, htf_tf, ltf_tf,
                     htf_limit, ltf_limit, graph_state):
    symbol = (symbol or DEFAULT_SYMBOL).upper()
    htf_sec = get_interval_seconds(htf_tf)
    ltf_sec = get_interval_seconds(ltf_tf)

    global SPREAD_FACTOR, HTF_LOOPS
    SPREAD_FACTOR = spread_val or 4.0
    HTF_LOOPS = loops_val or 1.0

    df_htf = get_klines(symbol, htf_tf, limit=int(htf_limit or 200))
    df_ltf = get_klines(symbol, ltf_tf, limit=int(ltf_limit or 600))

    if df_htf.empty or df_ltf.empty:
        empty = go.Figure(layout=dict(paper_bgcolor=BG, plot_bgcolor=CARD,
                          title=dict(text="⚠️ دیتا یافت نشد", font=dict(color=TXT))))
        return empty, empty, [], "دیتایی دریافت نشد"

    # ─── تولید اسپیرال‌ها ───
    (traces, time_span, price_min, price_scale,
     X_htf_raw, Y_htf_raw, X_ltf_raw, Y_ltf_raw,
     node_y, htf_volumes, ltf_volumes_valid) = \
        map_ltf_to_htf_spiral_optimized(df_ltf, df_htf, htf_sec, ltf_sec)

    current_price = df_htf["close"].iloc[-1]
    current_price_str = format_price(current_price)

    # ─── استخراج S/R حجمی ───
    sr_levels, bin_centers, hist = extract_sr_levels_by_volume(
        Y_htf_raw, Y_ltf_raw, node_y,
        htf_volumes, ltf_volumes_valid,
        price_min, price_scale, current_price
    )

    # ─── نمودار اسپیرال + خطوط S/R ───
    fig = go.Figure(data=traces)

    for level in sr_levels:
        color = SR_SUPPORT if level["type_code"] == "support" else SR_RESIST
        y_val = (level["price"] - price_min) * price_scale
        fig.add_hline(
            y=y_val, line_dash="dash", line_color=color,
            line_width=1 + (level["strength"] / 40),
            opacity=0.3 + (level["strength"] / 250),
            annotation_text=f'{level["price_str"]} | Vol:{level["vol_accumulated"]} ({level["strength"]}%)',
            annotation_position="right",
            annotation_font_size=9,
            annotation_font_color=color
        )

    y_ticks = np.linspace(0, time_span, 6)
    y_labels = [format_price(price_min + (v / price_scale)) for v in y_ticks]

    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
        title=dict(text=f"Fractal Volume S/R: {symbol} | HTF:{htf_tf} / LTF:{ltf_tf} | Price: {current_price_str}",
                   font=dict(color=GOLD, size=13)),
        xaxis=dict(showgrid=False, zeroline=False, visible=False),
        yaxis=dict(tickmode='array', tickvals=y_ticks, ticktext=y_labels,
                   showgrid=True, gridcolor=LINE, title="Price", color=TXT,
                   scaleanchor="x", scaleratio=1),
        margin=dict(l=70, r=140, t=55, b=30),
        hovermode="closest", uirevision='constant'
    )

    if graph_state:
        if 'xaxis.range' in graph_state and isinstance(graph_state['xaxis.range'], list):
            fig.update_xaxes(range=graph_state['xaxis.range'])
        if 'yaxis.range' in graph_state and isinstance(graph_state['yaxis.range'], list):
            fig.update_yaxes(range=graph_state['yaxis.range'])

    # ─── نمودار پروفایل حجم ───
    vol_fig = go.Figure()
    
    if len(bin_centers) > 0 and len(hist) > 0:
        # رنگ‌بندی بر اساس حمایت/مقاومت
        bar_colors = [SR_SUPPORT if p < current_price else SR_RESIST for p in bin_centers]
        
        vol_fig.add_trace(go.Bar(
            x=hist, y=bin_centers, orientation='h',
            marker_color=bar_colors, opacity=0.7,
            hovertemplate="💰 Price: %{y}<br>📊 Volume: %{x}<extra></extra>"
        ))
        
        # خط قیمت فعلی
        vol_fig.add_hline(y=current_price, line_dash="solid", line_color=GOLD,
                          line_width=2, annotation_text=f"Current: {current_price_str}",
                          annotation_position="right", annotation_font_color=GOLD)
        
        # خطوط S/R
        for level in sr_levels[:8]:
            c = SR_SUPPORT if level["type_code"] == "support" else SR_RESIST
            vol_fig.add_hline(y=level["price"], line_dash="dot", line_color=c,
                              line_width=1, opacity=0.5)
    
    vol_fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=CARD,
        title=dict(text="📊 Volume Profile (Accumulated under Spirals)", font=dict(color=MUT, size=12)),
        xaxis=dict(title="Accumulated Volume", color=MUT, gridcolor=LINE),
        yaxis=dict(title="Price", color=TXT, gridcolor=LINE),
        margin=dict(l=60, r=30, t=40, b=30),
        height=200
    )

    # ─── خلاصه ───
    n_sup = sum(1 for l in sr_levels if l["type_code"] == "support")
    n_res = sum(1 for l in sr_levels if l["type_code"] == "resistance")
    total_vol = sum(float(l["vol_pct"]) for l in sr_levels) if sr_levels else 0
    summary = (f"🟢 {n_sup} حمایت | 🔴 {n_res} مقاومت | "
               f"📊 {total_vol:.1f}% حجم در سطوح کلیدی | "
               f"💰 قیمت: {current_price_str}")

    # ─── داده جدول ───
    table_data = [{k: v for k, v in l.items() if k not in ("price", "type_code")} 
                  for l in sr_levels]
    # type_code را برای conditional styling نگه می‌داریم
    for i, l in enumerate(sr_levels):
        table_data[i]["type_code"] = l["type_code"]

    return fig, vol_fig, table_data, summary


@app.callback(
    Output('graph-state', 'data'),
    Input('spiral-chart', 'relayoutData'),
    State('graph-state', 'data'),
    prevent_initial_call=True
)
def save_relayout(relayoutData, current_state):
    if not relayoutData: return current_state
    state = current_state or {}
    if 'xaxis.range' in relayoutData: state['xaxis.range'] = relayoutData['xaxis.range']
    elif 'xaxis.range[0]' in relayoutData and 'xaxis.range[1]' in relayoutData:
        state['xaxis.range'] = [relayoutData['xaxis.range[0]'], relayoutData['xaxis.range[1]']]
    if 'xaxis.autorange' in relayoutData: state.pop('xaxis.range', None)
    if 'yaxis.range' in relayoutData: state['yaxis.range'] = relayoutData['yaxis.range']
    elif 'yaxis.range[0]' in relayoutData and 'yaxis.range[1]' in relayoutData:
        state['yaxis.range'] = [relayoutData['yaxis.range[0]'], relayoutData['yaxis.range[1]']]
    if 'yaxis.autorange' in relayoutData: state.pop('yaxis.range', None)
    return state


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8070, use_reloader=False)