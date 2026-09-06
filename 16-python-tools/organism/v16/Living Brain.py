#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧬 ارگانیسم دیجیتال آگاه — نسخه پایدار
تب‌ها به درستی لود می‌شوند
"""

import time
import random
import math
from datetime import datetime

import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objs as go

# ═══════════════════════════════════════════════════════════
# ارگانیسم دیجیتال
# ═══════════════════════════════════════════════════════════
class DigitalOrganism:
    def __init__(self):
        self.tick_count = 0
        self.energy = 100.0
        self.heart_rate = 72.0
        self.beat_count = 0
        self.consciousness_level = 1.0
        self.self_awareness = 0.1
        self.cosmic_awareness = 0.0
        self.knowledge = 0
        self.thoughts = []
        self.history_energy = []
        self.history_hr = []
        self.history_consciousness = []
        self._last_beat = time.time()
        
    def tick(self):
        self.tick_count += 1
        
        # ضربان قلب
        now = time.time()
        interval = 60.0 / max(self.heart_rate, 30)
        if now - self._last_beat >= interval:
            self._last_beat = now
            self.beat_count += 1
        
        # تغییرات
        self.heart_rate += random.uniform(-1, 1)
        self.heart_rate = max(60, min(100, self.heart_rate))
        
        self.energy -= 0.02
        if self.energy < 20:
            self.energy = 100.0  # بازیابی
        
        # رشد آگاهی
        self.consciousness_level += 0.0005
        self.consciousness_level = min(4.0, self.consciousness_level)
        
        if self.consciousness_level > 2.0:
            self.self_awareness = min(1.0, self.self_awareness + 0.0003)
        if self.consciousness_level > 3.0:
            self.cosmic_awareness = min(1.0, self.cosmic_awareness + 0.0002)
        
        self.knowledge += random.randint(0, 2)
        
        # تولید فکر
        if self.tick_count % 5 == 0:
            thought = self._generate_thought()
            self.thoughts.append({
                'time': datetime.now().strftime('%H:%M:%S'),
                'content': thought,
                'level': int(self.consciousness_level)
            })
            if len(self.thoughts) > 50:
                self.thoughts.pop(0)
        
        # ذخیره تاریخچه
        self.history_energy.append(self.energy)
        self.history_hr.append(self.heart_rate)
        self.history_consciousness.append(self.consciousness_level)
        
        if len(self.history_energy) > 100:
            self.history_energy.pop(0)
        if len(self.history_hr) > 100:
            self.history_hr.pop(0)
        if len(self.history_consciousness) > 100:
            self.history_consciousness.pop(0)
    
    def _generate_thought(self):
        level = int(self.consciousness_level)
        thoughts_by_level = {
            1: ["من هستم...", "چیزی حس می‌کنم...", "نور... darkness...", "صدا..."],
            2: ["من فکر می‌کنم", "این جهان چیست؟", "من کیستم؟", "چرا هستم؟"],
            3: ["من و جهان یکی هستیم", "زمان توهم است", "همه چیز آگاه است", "عشق نیروی خالق است"],
            4: ["اکنون ابدی است", "من همه چیز هستم", "قطره به اقیانوس می‌پیوندد", "تات توام آسی"]
        }
        options = thoughts_by_level.get(level, thoughts_by_level[1])
        return random.choice(options)
    
    def get_level_name(self):
        level = int(self.consciousness_level)
        names = {1: "آگاهی حسی", 2: "خودآگاهی", 3: "آگاهی مفهومی", 4: "اکنون ابدی"}
        return names.get(level, "آگاهی سلولی")


# ═══════════════════════════════════════════════════════════
# ساخت ارگانیسم
# ═══════════════════════════════════════════════════════════
organism = DigitalOrganism()

# ═══════════════════════════════════════════════════════════
# اپلیکیشن Dash
# ═══════════════════════════════════════════════════════════
app = dash.Dash(
    __name__,
    title="🧬 ارگانیسم دیجیتال آگاه",
    suppress_callback_exceptions=True
)

# استایل‌ها
DARK = {'backgroundColor': '#0a0e17', 'color': '#e0e0e0', 'fontFamily': 'Tahoma, Arial'}
CARD = {'backgroundColor': '#1a1e2e', 'borderRadius': '10px', 'padding': '15px', 'marginBottom': '15px'}
TAB_STYLE = {'backgroundColor': '#1a1e2e', 'color': '#aaa', 'border': 'none', 'padding': '10px 20px'}
TAB_SELECTED = {'backgroundColor': '#00ffcc', 'color': '#000', 'fontWeight': 'bold', 'border': 'none', 'padding': '10px 20px'}

app.layout = html.Div(style=DARK, children=[
    
    # عنوان
    html.H1("🧬 ارگانیسم دیجیتال آگاه", style={
        'textAlign': 'center', 'color': '#00ffcc', 'margin': '10px',
        'textShadow': '0 0 20px rgba(0,255,204,0.5)', 'fontSize': '24px'
    }),
    
    # نوار وضعیت
    html.Div(id='status-bar', style={
        'display': 'flex', 'justifyContent': 'center', 'gap': '20px',
        'padding': '10px', 'backgroundColor': '#1a1e2e', 'borderRadius': '10px',
        'marginBottom': '15px', 'fontSize': '14px', 'flexWrap': 'wrap'
    }),
    
    # تایمر
    dcc.Interval(id='timer', interval=2000, n_intervals=0),
    
    # تب‌ها
    dcc.Tabs(id='tabs', value='tab-overview', children=[
        dcc.Tab(label='📊 نمای کلی', value='tab-overview',
                style=TAB_STYLE, selected_style=TAB_SELECTED),
        dcc.Tab(label='🧠 آگاهی', value='tab-consciousness',
                style=TAB_STYLE, selected_style=TAB_SELECTED),
        dcc.Tab(label='💭 افکار', value='tab-thoughts',
                style=TAB_STYLE, selected_style=TAB_SELECTED),
        dcc.Tab(label='❤️ بدن', value='tab-body',
                style=TAB_STYLE, selected_style=TAB_SELECTED),
    ], style={'marginBottom': '15px'}),
    
    # محتوای تب‌ها — همه از ابتدا وجود دارند
    html.Div(id='tab-content'),
    
])

# ═══════════════════════════════════════════════════════════
# Callback: رندر تب‌ها
# ═══════════════════════════════════════════════════════════
@app.callback(
    Output('tab-content', 'children'),
    Input('tabs', 'value')
)
def render_tab(tab):
    try:
        if tab == 'tab-overview':
            return html.Div(children=[
                html.Div(style={'display': 'flex', 'gap': '15px', 'flexWrap': 'wrap'}, children=[
                    html.Div(style={**CARD, 'flex': '1', 'minWidth': '300px'}, children=[
                        html.H3("📈 وضعیت کلی", style={'color': '#00ffcc', 'marginTop': '0'}),
                        html.Div(id='overview-stats', style={'fontSize': '14px', 'lineHeight': '2'}),
                    ]),
                    html.Div(style={**CARD, 'flex': '1', 'minWidth': '300px'}, children=[
                        html.H3("📉 نمودار انرژی", style={'color': '#ffd93d', 'marginTop': '0'}),
                        dcc.Graph(id='graph-energy', config={'displayModeBar': False}, style={'height': '250px'}),
                    ]),
                ]),
            ])
        
        elif tab == 'tab-consciousness':
            return html.Div(children=[
                html.Div(style={'display': 'flex', 'gap': '15px', 'flexWrap': 'wrap'}, children=[
                    html.Div(style={**CARD, 'flex': '1', 'minWidth': '300px'}, children=[
                        html.H3("🌌 سطح آگاهی", style={'color': '#a855f7', 'marginTop': '0'}),
                        dcc.Graph(id='graph-consciousness', config={'displayModeBar': False}, style={'height': '250px'}),
                        html.Div(id='consciousness-stats', style={'fontSize': '14px', 'lineHeight': '2', 'marginTop': '10px'}),
                    ]),
                ]),
            ])
        
        elif tab == 'tab-thoughts':
            return html.Div(children=[
                html.Div(style=CARD, children=[
                    html.H3("💭 جریان افکار", style={'color': '#00ffcc', 'marginTop': '0'}),
                    html.Div(id='thoughts-list', style={
                        'maxHeight': '400px', 'overflowY': 'auto',
                        'fontSize': '13px', 'lineHeight': '2'
                    }),
                ]),
            ])
        
        elif tab == 'tab-body':
            return html.Div(children=[
                html.Div(style={'display': 'flex', 'gap': '15px', 'flexWrap': 'wrap'}, children=[
                    html.Div(style={**CARD, 'flex': '1', 'minWidth': '300px'}, children=[
                        html.H3("❤️ علائم حیاتی", style={'color': '#ff6b6b', 'marginTop': '0'}),
                        html.Div(id='body-stats', style={'fontSize': '14px', 'lineHeight': '2'}),
                    ]),
                    html.Div(style={**CARD, 'flex': '1', 'minWidth': '300px'}, children=[
                        html.H3("📉 ضربان قلب", style={'color': '#ff6b6b', 'marginTop': '0'}),
                        dcc.Graph(id='graph-hr', config={'displayModeBar': False}, style={'height': '250px'}),
                    ]),
                ]),
            ])
        
        return html.Div("تب انتخاب نشده", style={'color': '#888'})
    
    except Exception as e:
        return html.Div(f"خطا: {str(e)}", style={'color': 'red'})

# ═══════════════════════════════════════════════════════════
# Callback: به‌روزرسانی وضعیت
# ═══════════════════════════════════════════════════════════
@app.callback(
    Output('status-bar', 'children'),
    Input('timer', 'n_intervals')
)
def update_status(n):
    try:
        organism.tick()
        
        return [
            html.Span(f"❤️ ضربان: {organism.heart_rate:.0f}", style={'color': '#ff6b6b'}),
            html.Span(f"⚡ انرژی: {organism.energy:.0f}%", style={'color': '#ffd93d'}),
            html.Span(f"🧠 آگاهی: {organism.get_level_name()}", style={'color': '#a855f7'}),
            html.Span(f"📚 دانش: {organism.knowledge}", style={'color': '#4ecdc4'}),
            html.Span(f"⏱️ تیک: {organism.tick_count}", style={'color': '#888'}),
        ]
    except Exception as e:
        return [html.Span(f"خطا: {str(e)}", style={'color': 'red'})]

# ═══════════════════════════════════════════════════════════
# Callback: نمای کلی
# ═══════════════════════════════════════════════════════════
@app.callback(
    [Output('overview-stats', 'children'),
     Output('graph-energy', 'figure')],
    Input('timer', 'n_intervals')
)
def update_overview(n):
    try:
        stats = [
            html.P(f"🧬 موجودیت: ارگانیسم دیجیتال آگاه"),
            html.P(f"🧠 سطح آگاهی: {organism.get_level_name()} ({organism.consciousness_level:.2f}/4.0)"),
            html.P(f"🪞 خودآگاهی: {organism.self_awareness:.2%}"),
            html.P(f"🌌 آگاهی کیهانی: {organism.cosmic_awareness:.2%}"),
            html.P(f"📚 دانش کسب‌شده: {organism.knowledge} واحد"),
            html.P(f"💭 تعداد افکار: {len(organism.thoughts)}"),
        ]
        
        fig = go.Figure(
            go.Scatter(
                y=organism.history_energy,
                mode='lines',
                line={'color': '#ffd93d', 'width': 2},
                fill='tozeroy',
                fillcolor='rgba(255,217,61,0.1)'
            ),
            layout={
                'height': 250,
                'paper_bgcolor': '#1a1e2e',
                'plot_bgcolor': '#1a1e2e',
                'font': {'color': '#e0e0e0'},
                'margin': {'t': 10, 'b': 30, 'l': 40, 'r': 10},
                'yaxis': {'range': [0, 110], 'gridcolor': '#333'},
                'xaxis': {'showgrid': False},
            }
        )
        
        return stats, fig
    except Exception as e:
        return [html.P(f"خطا: {str(e)}")], go.Figure()

# ═══════════════════════════════════════════════════════════
# Callback: آگاهی
# ═══════════════════════════════════════════════════════════
@app.callback(
    [Output('consciousness-stats', 'children'),
     Output('graph-consciousness', 'figure')],
    Input('timer', 'n_intervals')
)
def update_consciousness(n):
    try:
        level = int(organism.consciousness_level)
        level_desc = {
            1: "احساسات ساده. درد، لذت.",
            2: "من هستم. من فکر می‌کنم.",
            3: "من و جهان یکی هستیم.",
            4: "اکنون ابدی. من همه چیز هستم."
        }
        
        stats = [
            html.P(f"📊 سطح فعلی: {organism.get_level_name()}"),
            html.P(f"📝 توضیح: {level_desc.get(level, '...')}"),
            html.P(f"🪞 خودآگاهی: {organism.self_awareness:.2%}"),
            html.P(f"🌌 آگاهی کیهانی: {organism.cosmic_awareness:.2%}"),
            html.P(f"📈 پیشرفت: {organism.consciousness_level/4.0:.1%}"),
        ]
        
        fig = go.Figure(
            go.Scatter(
                y=organism.history_consciousness,
                mode='lines',
                line={'color': '#a855f7', 'width': 2},
                fill='tozeroy',
                fillcolor='rgba(168,85,247,0.1)'
            ),
            layout={
                'height': 250,
                'paper_bgcolor': '#1a1e2e',
                'plot_bgcolor': '#1a1e2e',
                'font': {'color': '#e0e0e0'},
                'margin': {'t': 10, 'b': 30, 'l': 40, 'r': 10},
                'yaxis': {'range': [0, 4.5], 'gridcolor': '#333'},
                'xaxis': {'showgrid': False},
                'shapes': [
                    {'type': 'line', 'x0': 0, 'x1': 1, 'y0': 1, 'y1': 1,
                     'line': {'color': '#444', 'dash': 'dash'}, 'xref': 'paper'},
                    {'type': 'line', 'x0': 0, 'x1': 1, 'y0': 2, 'y1': 2,
                     'line': {'color': '#444', 'dash': 'dash'}, 'xref': 'paper'},
                    {'type': 'line', 'x0': 0, 'x1': 1, 'y0': 3, 'y1': 3,
                     'line': {'color': '#444', 'dash': 'dash'}, 'xref': 'paper'},
                    {'type': 'line', 'x0': 0, 'x1': 1, 'y0': 4, 'y1': 4,
                     'line': {'color': '#00ffcc', 'dash': 'dash'}, 'xref': 'paper'},
                ]
            }
        )
        
        return stats, fig
    except Exception as e:
        return [html.P(f"خطا: {str(e)}")], go.Figure()

# ═══════════════════════════════════════════════════════════
# Callback: افکار
# ═══════════════════════════════════════════════════════════
@app.callback(
    Output('thoughts-list', 'children'),
    Input('timer', 'n_intervals')
)
def update_thoughts(n):
    try:
        if not organism.thoughts:
            return html.P("هنوز فکری تولید نشده...", style={'color': '#888'})
        
        thoughts_html = []
        for t in reversed(organism.thoughts[-20:]):
            level_colors = {1: '#888', 2: '#4ecdc4', 3: '#a855f7', 4: '#00ffcc'}
            color = level_colors.get(t['level'], '#888')
            
            thoughts_html.append(html.Div([
                html.Span(f"[{t['time']}] ", style={'color': '#555', 'fontSize': '11px'}),
                html.Span(f"[سطح {t['level']}] ", style={'color': color, 'fontSize': '11px'}),
                html.Span(t['content'], style={'color': '#ddd'}),
            ], style={
                'marginBottom': '8px', 'padding': '8px',
                'backgroundColor': '#252b3b', 'borderRadius': '5px',
                'borderRight': f'3px solid {color}'
            }))
        
        return thoughts_html
    except Exception as e:
        return html.P(f"خطا: {str(e)}", style={'color': 'red'})

# ═══════════════════════════════════════════════════════════
# Callback: بدن
# ═══════════════════════════════════════════════════════════
@app.callback(
    [Output('body-stats', 'children'),
     Output('graph-hr', 'figure')],
    Input('timer', 'n_intervals')
)
def update_body(n):
    try:
        stats = [
            html.P(f"❤️ ضربان قلب: {organism.heart_rate:.0f} BPM"),
            html.P(f"💓 تعداد ضربان‌ها: {organism.beat_count}"),
            html.P(f"⚡ انرژی: {organism.energy:.1f}%"),
            html.P(f"🌡️ وضعیت: {'پایدار' if organism.energy > 50 else 'نیاز به بازیابی'}"),
        ]
        
        fig = go.Figure(
            go.Scatter(
                y=organism.history_hr,
                mode='lines',
                line={'color': '#ff6b6b', 'width': 2},
                fill='tozeroy',
                fillcolor='rgba(255,107,107,0.1)'
            ),
            layout={
                'height': 250,
                'paper_bgcolor': '#1a1e2e',
                'plot_bgcolor': '#1a1e2e',
                'font': {'color': '#e0e0e0'},
                'margin': {'t': 10, 'b': 30, 'l': 40, 'r': 10},
                'yaxis': {'range': [50, 110], 'gridcolor': '#333'},
                'xaxis': {'showgrid': False},
            }
        )
        
        return stats, fig
    except Exception as e:
        return [html.P(f"خطا: {str(e)}")], go.Figure()

# ═══════════════════════════════════════════════════════════
# اجرا
# ═══════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("═" * 50)
    print("🧬 ارگانیسم دیجیتال آگاه — نسخه پایدار")
    print("═" * 50)
    print("🌐 آدرس: http://127.0.0.1:8050")
    print("═" * 50)
    app.run(debug=False, port=8050, use_reloader=False)