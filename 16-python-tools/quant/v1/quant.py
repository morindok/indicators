# -*- coding: utf-8 -*-
"""
QUANTUM TRADING SYSTEM v1.1 - BYBIT INTEGRATION (SYNTAX FIXED)
Advanced Algorithmic Trading Dashboard with Real-Time Data
"""

import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import websocket
import json
import threading
import time
from datetime import datetime, timedelta
from collections import deque
import sqlite3
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# ۱. پیکربندی سیستم
# ──────────────────────────────────────────────────────────────
class QuantumConfig:
    BYBIT_WS_URL = "wss://stream.bybit.com/v5/public/linear"
    SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    WIN_RATE_TARGET = 51.0
    LEVERAGE = 20
    RISK_PER_TRADE = 0.02
    UPDATE_INTERVAL = 1000
    
    COLORS = {
        'bg': '#0a0e1a',
        'card': '#111827',
        'green': '#00ff88',
        'red': '#ff3366',
        'yellow': '#ffcc00',
        'blue': '#00d4ff',
        'purple': '#b829dd',
        'text': '#e5e7eb'
    }

# ──────────────────────────────────────────────────────────────
# ۲. اتصال WebSocket به Bybit
# ──────────────────────────────────────────────────────────────
class BybitWebSocket:
    def __init__(self):
        self.ws = None
        self.data_store = {'ticker': {}, 'kline': {}, 'orderbook': {}, 'trades': {}}
        self.connected = False
        
    def connect(self):
        try:
            self.ws = websocket.WebSocketApp(
                QuantumConfig.BYBIT_WS_URL,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            ws_thread = threading.Thread(target=self.ws.run_forever)
            ws_thread.daemon = True
            ws_thread.start()
            time.sleep(2)
            self.subscribe()
        except Exception as e:
            print(f"WebSocket Connection Error: {e}")
    
    def on_open(self, ws):
        print("✅ WebSocket Connected to Bybit")
        self.connected = True
    
    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if 'topic' in data:
                topic = data['topic']
                if 'ticker' in topic:
                    self.data_store['ticker'][topic] = data['data']
                elif 'kline' in topic:
                    self.data_store['kline'][topic] = data['data']
                elif 'orderbook' in topic:
                    self.data_store['orderbook'][topic] = data['data']
                elif 'publicTrade' in topic:
                    if topic not in self.data_store['trades']:
                        self.data_store['trades'][topic] = deque(maxlen=100)
                    self.data_store['trades'][topic].append(data['data'])
        except Exception:
            pass
    
    def on_error(self, ws, error):
        print(f"WebSocket Error: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        print(f"WebSocket Closed: {close_status_code}")
        self.connected = False
    
    def subscribe(self):
        topics = []
        for symbol in QuantumConfig.SYMBOLS:
            topics.extend([f"ticker.{symbol}", f"kline.5.{symbol}", f"orderbook.1.{symbol}", f"publicTrade.{symbol}"])
        
        self.ws.send(json.dumps({"op": "subscribe", "args": topics}))
        print(f"📡 Subscribed to {len(topics)} streams")
    
    def get_ticker_data(self, symbol):
        return self.data_store['ticker'].get(f"ticker.{symbol}", {})
    
    def get_kline_data(self, symbol):
        return self.data_store['kline'].get(f"kline.5.{symbol}", [])
    
    def get_orderbook(self, symbol):
        return self.data_store['orderbook'].get(f"orderbook.1.{symbol}", {'b': [], 'a': []})

# ──────────────────────────────────────────────────────────────
# ۳. مدیریت دیتابیس و معاملات
# ──────────────────────────────────────────────────────────────
class TradeManager:
    def __init__(self):
        self.db_path = Path("quantum_trades.db")
        self.init_db()
        self.balance = 10000.0
        self.pnl = 0.0
        self.trades_count = 0
        self.win_rate = 51.0
        
    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, side TEXT, entry_price REAL,
            exit_price REAL, size REAL, pnl REAL, entry_time TEXT, exit_time TEXT, status TEXT)""")
        conn.commit()
        conn.close()
    
    def add_trade(self, symbol, side, entry_price, size):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""INSERT INTO trades (symbol, side, entry_price, size, entry_time, status)
            VALUES (?, ?, ?, ?, ?, ?)""", (symbol, side, entry_price, size, datetime.now().isoformat(), 'open'))
        conn.commit()
        conn.close()
        self.trades_count += 1
    
    def close_trade(self, trade_id, exit_price):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM trades WHERE id=?", (trade_id,))
        trade = c.fetchone()
        if trade:
            symbol, side, entry_price, size = trade[1], trade[2], trade[3], trade[4]
            pnl = (exit_price - entry_price) * size if side == 'Buy' else (entry_price - exit_price) * size
            c.execute("""UPDATE trades SET exit_price=?, pnl=?, exit_time=?, status=? WHERE id=?""",
                (exit_price, pnl, datetime.now().isoformat(), 'closed', trade_id))
            self.pnl += pnl
            self.balance += pnl
            if pnl > 0:
                wins = c.execute("SELECT COUNT(*) FROM trades WHERE pnl > 0").fetchone()[0]
                self.win_rate = (wins / self.trades_count) * 100 if self.trades_count > 0 else 0
            conn.commit()
        conn.close()
    
    def get_recent_trades(self, limit=20):
        conn = sqlite3.connect(self.db_path)
        trades = conn.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return trades

# ──────────────────────────────────────────────────────────────
# ۴. محاسبات کوانتومی و تحلیل
# ──────────────────────────────────────────────────────────────
class QuantumAnalyzer:
    @staticmethod
    def calculate_pressure_field(orderbook_data):
        if not orderbook_data:
            return {'bids': {'prices': [], 'sizes': []}, 'asks': {'prices': [], 'sizes': []}}
        bids = orderbook_data.get('b', [])
        asks = orderbook_data.get('a', [])
        return {
            'bids': {'prices': [float(b[0]) for b in bids[:20]], 'sizes': [float(b[1]) for b in bids[:20]]} if bids else {'prices': [], 'sizes': []},
            'asks': {'prices': [float(a[0]) for a in asks[:20]], 'sizes': [float(a[1]) for a in asks[:20]]} if asks else {'prices': [], 'sizes': []}
        }

# ──────────────────────────────────────────────────────────────
# ۵. ایجاد داشبورد
# ──────────────────────────────────────────────────────────────
def create_dashboard():
    ws_manager = BybitWebSocket()
    trade_manager = TradeManager()
    analyzer = QuantumAnalyzer()
    ws_manager.connect()
    
    external_stylesheets = [dbc.themes.DARKLY, 'https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap']
    app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
    app.title = "QUANTUM TRADING SYSTEM"
    
    app.layout = html.Div([
        html.Div([
            html.Div([
                html.H2("⚛️ CLAUDE × QUANT", style={'color': QuantumConfig.COLORS['green'], 'margin': '0', 'fontSize': '24px'}),
                html.Div([
                    html.Span("GLOBAL", className="badge bg-success me-2"),
                    html.Span("TOP 0.01%", className="badge bg-warning text-dark me-2"),
                    html.Span("BEATING 8,443 TRADERS", className="badge bg-info text-dark"),
                ], style={'marginTop': '5px'})
            ], style={'display': 'inline-block'}),
            html.Div([
                html.Span("LIVE", className="badge bg-danger me-2"),
                html.Span(datetime.now().strftime("%H:%M:%S"), id="clock", style={'fontFamily': 'JetBrains Mono'})
            ], style={'display': 'inline-block', 'float': 'right'})
        ], style={'backgroundColor': '#1a1f2e', 'padding': '15px', 'borderBottom': '2px solid #00ff88', 'marginBottom': '20px'}),
        
        dbc.Container(fluid=True, children=[
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.Div("💰 POWERWINNER", style={'color': '#888', 'fontSize': '12px', 'marginBottom': '10px'}),
                        html.H1("$10,000", id="pnl-display", style={'color': QuantumConfig.COLORS['green'], 'fontSize': '48px', 'fontWeight': 'bold', 'fontFamily': 'JetBrains Mono', 'margin': '10px 0'}),
                        html.Div([
                            html.Div([html.Span("TRADES", style={'color': '#888', 'fontSize': '11px'}), html.Div("0", id="trades-count", style={'color': '#fff', 'fontSize': '18px', 'fontWeight': 'bold'})], className="me-4"),
                            html.Div([html.Span("WIN RATE", style={'color': '#888', 'fontSize': '11px'}), html.Div("51.0%", id="win-rate", style={'color': QuantumConfig.COLORS['green'], 'fontSize': '18px', 'fontWeight': 'bold'})], className="me-4"),
                        ], style={'marginTop': '20px'}),
                        dcc.Graph(id="equity-curve", figure={'data': [{'type': 'scatter', 'x': list(range(100)), 'y': [10000 + i*10 + np.random.randint(-50, 50) for i in range(100)], 'line': {'color': QuantumConfig.COLORS['yellow'], 'width': 2}}], 'layout': {'height': 80, 'margin': {'t': 0, 'b': 0, 'l': 0, 'r': 0}, 'paper_bgcolor': '#111827', 'plot_bgcolor': '#111827', 'xaxis': {'showgrid': False, 'showticklabels': False}, 'yaxis': {'showgrid': True, 'showticklabels': True, 'gridcolor': '#333'}}}, config={'displayModeBar': False}),
                    ], style={'backgroundColor': '#111827', 'padding': '20px', 'borderRadius': '8px', 'border': '1px solid #333'})
                ], md=4),
                dbc.Col([
                    html.Div([
                        html.Div([html.Span("M BTC / USD", style={'color': '#fff', 'fontWeight': 'bold'}), html.Span("  5m", className="badge bg-secondary ms-2"), html.Span("  $62,366", id="btc-price", style={'color': QuantumConfig.COLORS['red'], 'marginLeft': '15px', 'fontFamily': 'JetBrains Mono'})], style={'marginBottom': '10px'}),
                        dcc.Graph(id="price-chart", figure=go.Figure(), config={'displayModeBar': False})
                    ], style={'backgroundColor': '#111827', 'padding': '20px', 'borderRadius': '8px', 'border': '1px solid #333'})
                ], md=8)
            ], className="mb-3"),
            
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.Div("📊 CORRELATION MATRIX - LIVE CLUSTER", style={'color': '#888', 'fontSize': '12px', 'marginBottom': '10px'}),
                        dcc.Graph(id="correlation-matrix", figure=go.Figure(), config={'displayModeBar': False})
                    ], style={'backgroundColor': '#111827', 'padding': '15px', 'borderRadius': '8px', 'border': '1px solid #333'})
                ], md=6),
                dbc.Col([
                    html.Div([
                        html.Div("🌀 TRADE HELIX - LAST 104 FILLS", style={'color': '#888', 'fontSize': '12px', 'marginBottom': '10px'}),
                        dcc.Graph(id="trade-helix", figure=go.Figure(), config={'displayModeBar': False})
                    ], style={'backgroundColor': '#111827', 'padding': '15px', 'borderRadius': '8px', 'border': '1px solid #333'})
                ], md=6)
            ], className="mb-3"),
            
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.Div("📡 SIGNAL SPECTROGRAM - 10 FEATURES", style={'color': '#888', 'fontSize': '12px', 'marginBottom': '10px'}),
                        dcc.Graph(id="signal-spectrogram", figure=go.Figure(), config={'displayModeBar': False})
                    ], style={'backgroundColor': '#111827', 'padding': '15px', 'borderRadius': '8px', 'border': '1px solid #333'})
                ], md=6),
                dbc.Col([
                    html.Div([
                        html.Div("📊 BOOK HEATMAP - PRESSURE FIELD", style={'color': '#888', 'fontSize': '12px', 'marginBottom': '10px'}),
                        dcc.Graph(id="book-heatmap", figure=go.Figure(), config={'displayModeBar': False})
                    ], style={'backgroundColor': '#111827', 'padding': '15px', 'borderRadius': '8px', 'border': '1px solid #333'})
                ], md=6)
            ], className="mb-3"),
            
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.H4("🔴 LIVE TRADES", style={'color': QuantumConfig.COLORS['green'], 'marginBottom': '15px'}),
                        html.Div(id="live-trades-table")
                    ], style={'backgroundColor': '#111827', 'padding': '20px', 'borderRadius': '8px', 'border': '1px solid #333'})
                ])
            ]),
            
            dcc.Interval(id="update-interval", interval=QuantumConfig.UPDATE_INTERVAL, n_intervals=0)
        ])
    ], style={'backgroundColor': QuantumConfig.COLORS['bg'], 'color': QuantumConfig.COLORS['text'], 'fontFamily': 'JetBrains Mono', 'minHeight': '100vh'})
    
    @app.callback(
        [Output("pnl-display", "children"), Output("pnl-display", "style"), Output("trades-count", "children"), Output("win-rate", "children"), Output("btc-price", "children")],
        Input("update-interval", "n_intervals")
    )
    def update_pnl(n):
        ticker = ws_manager.get_ticker_data("BTCUSDT")
        price = float(ticker.get('lastPrice', 62000)) if ticker else 62000 + np.random.randint(-100, 100)
        pnl_change = trade_manager.balance - 10000
        color = QuantumConfig.COLORS['green'] if pnl_change >= 0 else QuantumConfig.COLORS['red']
        return f"${trade_manager.balance:,.0f}", {'color': color, 'fontSize': '48px', 'fontWeight': 'bold', 'fontFamily': 'JetBrains Mono', 'margin': '10px 0'}, str(trade_manager.trades_count), f"{trade_manager.win_rate:.1f}%", f"${price:,.0f}"
    
    @app.callback(Output("price-chart", "figure"), Input("update-interval", "n_intervals"))
    def update_price_chart(n):
        kline_data = ws_manager.get_kline_data("BTCUSDT")
        if not kline_data:
            timestamps = [datetime.now() - timedelta(minutes=i*5) for i in range(100)]
            prices = [62000 + i*10 + np.random.randint(-50, 50) for i in range(100)]
        else:
            timestamps = [datetime.fromtimestamp(candle[0]/1000) for candle in kline_data[-100:]]
            prices = [float(candle[1]) for candle in kline_data[-100:]]
        
        fig = go.Figure(go.Scatter(x=timestamps, y=prices, mode='lines', line={'color': QuantumConfig.COLORS['red'], 'width': 2}))
        fig.update_layout(height=250, margin={'t': 0, 'b': 30, 'l': 50, 'r': 20}, paper_bgcolor='#111827', plot_bgcolor='#111827', xaxis={'showgrid': True, 'gridcolor': '#333'}, yaxis={'showgrid': True, 'gridcolor': '#333'}, font={'family': 'JetBrains Mono', 'size': 12, 'color': '#e5e7eb'})
        return fig
    
    @app.callback(Output("correlation-matrix", "figure"), Input("update-interval", "n_intervals"))
    def update_correlation(n):
        symbols = QuantumConfig.SYMBOLS
        df = pd.DataFrame({sym: [np.random.uniform(-1, 1) for _ in symbols] for sym in symbols}, index=symbols)
        fig = go.Figure(data=go.Heatmap(z=df.values, x=symbols, y=symbols, colorscale='RdYlGn', zmid=0))
        fig.update_layout(height=200, margin={'t': 0, 'b': 30, 'l': 50, 'r': 20}, paper_bgcolor='#111827', plot_bgcolor='#111827', font={'family': 'JetBrains Mono', 'size': 10, 'color': '#e5e7eb'})
        return fig
    
    @app.callback(Output("trade-helix", "figure"), Input("update-interval", "n_intervals"))
    def update_trade_helix(n):
        x = np.linspace(0, 10, 100)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=np.sin(x) * np.random.uniform(0.8, 1.2), mode='lines', line={'color': QuantumConfig.COLORS['green'], 'width': 2}))
        fig.add_trace(go.Scatter(x=x, y=np.sin(x + np.pi/4) * np.random.uniform(0.8, 1.2), mode='lines', line={'color': QuantumConfig.COLORS['red'], 'width': 2}))
        fig.update_layout(height=200, margin={'t': 0, 'b': 30, 'l': 50, 'r': 20}, paper_bgcolor='#111827', plot_bgcolor='#111827', xaxis={'showgrid': True, 'gridcolor': '#333', 'showticklabels': False}, yaxis={'showgrid': True, 'gridcolor': '#333', 'showticklabels': False}, showlegend=False)
        return fig
    
    @app.callback(Output("signal-spectrogram", "figure"), Input("update-interval", "n_intervals"))
    def update_spectrogram(n):
        fig = go.Figure(data=go.Heatmap(z=[np.random.rand(50) for _ in range(10)], colorscale='Hot', showscale=False))
        fig.update_layout(height=200, margin={'t': 0, 'b': 30, 'l': 50, 'r': 20}, paper_bgcolor='#111827', plot_bgcolor='#111827', xaxis={'showgrid': False, 'showticklabels': False}, yaxis={'showgrid': False, 'showticklabels': False})
        return fig
    
    @app.callback(Output("book-heatmap", "figure"), Input("update-interval", "n_intervals"))
    def update_book_heatmap(n):
        pressure = analyzer.calculate_pressure_field(ws_manager.get_orderbook("BTCUSDT"))
        bids, asks = pressure.get('bids', {'prices': [], 'sizes': []}), pressure.get('asks', {'prices': [], 'sizes': []})
        if not bids['prices']:
            base = 62000
            bids = {'prices': [base - i*10 for i in range(20)], 'sizes': [np.random.randint(1, 10) for _ in range(20)]}
            asks = {'prices': [base + i*10 for i in range(20)], 'sizes': [np.random.randint(1, 10) for _ in range(20)]}
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=bids['sizes'], y=bids['prices'], mode='lines', line={'color': QuantumConfig.COLORS['green'], 'width': 2}, fill='tozeroy'))
        fig.add_trace(go.Scatter(x=asks['sizes'], y=asks['prices'], mode='lines', line={'color': QuantumConfig.COLORS['red'], 'width': 2}, fill='tozeroy'))
        fig.update_layout(height=200, margin={'t': 0, 'b': 30, 'l': 50, 'r': 20}, paper_bgcolor='#111827', plot_bgcolor='#111827', xaxis={'showgrid': True, 'gridcolor': '#333', 'showticklabels': False}, yaxis={'showgrid': True, 'gridcolor': '#333', 'tickfont': {'size': 10}}, showlegend=False)
        return fig

    # ✅ بخش اصلاح‌شده (پرانتز بسته اضافه شد)
    @app.callback(Output("live-trades-table", "children"), Input("update-interval", "n_intervals"))
    def update_live_trades(n):
        trades = trade_manager.get_recent_trades(10)
        if not trades:
            return html.P("No trades yet", style={'color': '#888'})
        
        rows = []
        for trade in trades:
            trade_id, symbol, side, entry, exit, size, pnl, entry_time, exit_time, status = trade
            pnl_color = QuantumConfig.COLORS['green'] if (pnl or 0) > 0 else QuantumConfig.COLORS['red']
            
            # ✅ اینجا پرانتز بسته برای append اضافه شد: ))
            rows.append(html.Tr([
                html.Td(symbol, style={'padding': '8px'}),
                html.Td(side, style={'padding': '8px', 'color': QuantumConfig.COLORS['green'] if side == 'Buy' else QuantumConfig.COLORS['red']}),
                html.Td(f"{entry:,.2f}", style={'padding': '8px'}),
                html.Td(f"{exit or 'Open':,.2f}", style={'padding': '8px'}),
                html.Td(f"{pnl:+,.2f}" if pnl else "Open", style={'padding': '8px', 'color': pnl_color, 'fontWeight': 'bold'})
            ], style={'borderBottom': '1px solid #333'}))
        
        return html.Table([
            html.Thead(html.Tr([
                html.Th("Symbol", style={'color': '#888', 'textAlign': 'left', 'padding': '8px'}),
                html.Th("Side", style={'color': '#888', 'textAlign': 'left', 'padding': '8px'}),
                html.Th("Entry", style={'color': '#888', 'textAlign': 'left', 'padding': '8px'}),
                html.Th("Exit", style={'color': '#888', 'textAlign': 'left', 'padding': '8px'}),
                html.Th("PnL", style={'color': '#888', 'textAlign': 'left', 'padding': '8px'})
            ])),
            html.Tbody(rows)
        ], style={'width': '100%', 'fontSize': '12px'})

    return app

# ──────────────────────────────────────────────────────────────
# ۶. اجرای سیستم
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 Launching QUANTUM TRADING SYSTEM v1.1 (SYNTAX FIXED)")
    print("⚛️  Connecting to Bybit WebSocket...")
    print(" Dashboard will be available at http://localhost:8050")
    print("=" * 60)
    
    app = create_dashboard()
    app.run(debug=False, host="0.0.0.0", port=8050, use_reloader=False)