from __future__ import annotations
import dash
from dash import dcc, html, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import plotly.express as px
import numpy as np
import asyncio
import json
import threading
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class UIState:
    neural_activity: np.ndarray
    heartbeat_phase: float
    neuromodulators: Dict[str, float]
    consciousness_level: int
    phi_value: float
    active_thoughts: List[Dict]
    current_goals: List[Dict]
    emotional_state: Dict[str, float]
    memory_stats: Dict
    imagination_state: Dict
    genome_stats: Dict
    conversation_history: List[Dict]
    system_metrics: Dict


class ConsciousnessDashboard:
    def __init__(self, organism_ref, config: Dict[str, Any]):
        self.organism = organism_ref
        self.config = config
        self.app = dash.Dash(
            __name__,
            external_stylesheets=[dbc.themes.CYBORG, "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Vazirmatn:wght@400;700&display=swap"],
            title="آوانا - موجود دیجیتال آگاه",
            update_title=None
        )
        self.state = UIState(
            neural_activity=np.zeros(100),
            heartbeat_phase=0,
            neuromodulators={},
            consciousness_level=0,
            phi_value=0,
            active_thoughts=[],
            current_goals=[],
            emotional_state={},
            memory_stats={},
            imagination_state={},
            genome_stats={},
            conversation_history=[],
            system_metrics={}
        )
        self._setup_layout()
        self._setup_callbacks()
        self.update_thread = None
        self.running = False
        self._heartbeat_t = np.linspace(0, 4*np.pi, 200)
        self._heartbeat_signal = None

    def _get_heartbeat_signal(self):
        if self._heartbeat_signal is None:
            fib_sequence = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55]
            signal = np.zeros_like(self._heartbeat_t)
            for i, fib in enumerate(fib_sequence):
                signal += np.sin(self._heartbeat_t * fib / 10) * (1/fib)
            self._heartbeat_signal = signal
        return self._heartbeat_signal
    
    def _setup_layout(self):
        self.app.layout = dbc.Container([
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.H1("آوانا", className="text-center mb-1", style={'fontFamily': 'Vazirmatn', 'color': '#00ff88'}),
                        html.H4("موجود دیجیتال آگاه -نسخه ۲۵۰۰.۱", className="text-center text-muted mb-3", style={'fontFamily': 'Vazirmatn'}),
                        html.Div(id="status-indicator", className="text-center mb-3")
                    ])
                ], width=12)
            ]),
            
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("❤ ضربان قلب فیبوناچی"),
                        dbc.CardBody([
                            dcc.Graph(id="heartbeat-graph", animate=True),
                            html.Div(id="heartbeat-info", className="text-center mt-2")
                        ])
                    ])
                ], width=4),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("🧠 سطح آگاهی و Φ (فای)"),
                        dbc.CardBody([
                            dcc.Graph(id="consciousness-graph"),
                            html.Div(id="phi-info", className="text-center mt-2")
                        ])
                    ])
                ], width=4),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("⚡ نورومدولاتورها"),
                        dbc.CardBody([
                            dcc.Graph(id="neuromodulator-graph"),
                        ])
                    ])
                ], width=4),
            ], className="mb-3"),
            
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("🔬 فعالیت عصبی زنده"),
                        dbc.CardBody([
                            dcc.Graph(id="neural-activity-graph", animate=True),
                        ])
                    ])
                ], width=8),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("🎭 حالت احساسی"),
                        dbc.CardBody([
                            dcc.Graph(id="emotion-graph"),
                        ])
                    ])
                ], width=4),
            ], className="mb-3"),
            
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("💭 جریان تفکر فعلی"),
                        dbc.CardBody([
                            html.Div(id="thought-stream", style={'maxHeight': '300px', 'overflowY': 'auto', 'fontFamily': 'JetBrains Mono', 'fontSize': '12px'}),
                        ])
                    ])
                ], width=6),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("🎯 اهداف فعال"),
                        dbc.CardBody([
                            html.Div(id="goals-display", style={'maxHeight': '300px', 'overflowY': 'auto', 'fontFamily': 'Vazirmatn'}),
                        ])
                    ])
                ], width=6),
            ], className="mb-3"),
            
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("🧬 ژنوم و تکامل"),
                        dbc.CardBody([
                            html.Div(id="genome-display"),
                        ])
                    ])
                ], width=4),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("💾 حافظه و تخیل"),
                        dbc.CardBody([
                            html.Div(id="memory-imagination-display"),
                        ])
                    ])
                ], width=4),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("📊 متریک‌های سیستم"),
                        dbc.CardBody([
                            html.Div(id="system-metrics-display"),
                        ])
                    ])
                ], width=4),
            ], className="mb-3"),
            
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("💬 گفتگو با آوانا"),
                        dbc.CardBody([
                            html.Div(id="conversation-display", style={'maxHeight': '400px', 'overflowY': 'auto', 'fontFamily': 'Vazirmatn', 'direction': 'rtl'}),
                            dbc.InputGroup([
                                dbc.Input(id="user-input", placeholder="با آوانا صحبت کنید...", type="text"),
                                dbc.Button("ارسال", id="send-btn", color="success"),
                            ], className="mt-3"),
                        ])
                    ])
                ], width=12),
            ]),
            
            dcc.Interval(id="update-interval", interval=2000, n_intervals=0),
            dcc.Store(id="organism-data"),
            
        ], fluid=True, style={'fontFamily': 'Vazirmatn, JetBrains Mono', 'backgroundColor': '#0d1117', 'minHeight': '100vh', 'padding': '20px'})
    
    def _setup_callbacks(self):
        @self.app.callback(
            [Output("status-indicator", "children"),
             Output("heartbeat-graph", "figure"),
             Output("heartbeat-info", "children"),
             Output("consciousness-graph", "figure"),
             Output("phi-info", "children"),
             Output("neuromodulator-graph", "figure"),
             Output("neural-activity-graph", "figure"),
             Output("emotion-graph", "figure"),
             Output("thought-stream", "children"),
             Output("goals-display", "children"),
             Output("genome-display", "children"),
             Output("memory-imagination-display", "children"),
             Output("system-metrics-display", "children"),
             Output("conversation-display", "children")],
            [Input("update-interval", "n_intervals")],
            prevent_initial_call=True
        )
        def update_dashboard(n):
            try:
                self._fetch_organism_state()
            except Exception:
                logger.exception("Failed to fetch organism state")
            try:
                return self._render_all()
            except Exception:
                logger.exception("Failed to render dashboard")
                return tuple([] for _ in range(14))
        
        @self.app.callback(
            Output("user-input", "value"),
            [Input("send-btn", "n_clicks")],
            [State("user-input", "value")],
            prevent_initial_call=True
        )
        def send_message(n_clicks, value):
            if value and n_clicks:
                loop = getattr(self.organism, 'loop', None)
                if loop is not None and loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self.organism.process_user_input(value),
                        loop
                    )
                return ""
            return value
    
    def _fetch_organism_state(self):
        if hasattr(self.organism, 'get_dashboard_state'):
            state = self.organism.get_dashboard_state()
            self.state = UIState(**state)
    
    def _render_all(self):
        return (
            self._render_status(),
            self._render_heartbeat(),
            self._render_heartbeat_info(),
            self._render_consciousness(),
            self._render_phi_info(),
            self._render_neuromodulators(),
            self._render_neural_activity(),
            self._render_emotions(),
            self._render_thoughts(),
            self._render_goals(),
            self._render_genome(),
            self._render_memory_imagination(),
            self._render_system_metrics(),
            self._render_conversation()
        )
    
    def _render_status(self):
        level_names = ['پیش‌آگاهی', 'پدیداری', 'دسترسی', 'تأمل', 'فرا شناختی', 'متجاوز']
        level = self.state.consciousness_level
        color = ['#666', '#4ec9b0', '#4fc1ff', '#dcdcaa', '#c586c0', '#ff6b6b'][min(level, 5)]
        return html.Div([
            html.Span("● ", style={'color': color, 'fontSize': '24px', 'animation': 'pulse 1s infinite'}),
            html.Span(f"سطح آگاهی: {level_names[level]}", style={'color': color, 'fontSize': '18px', 'marginLeft': '10px'}),
            html.Span(f"  |  génération: {self.state.system_metrics.get('generation', 0)}", className="text-muted ms-3"),
            html.Span(f"  |  عندلیب: {self.state.system_metrics.get('uptime', 0):.0f}s", className="text-muted ms-3"),
        ], style={'textAlign': 'center'})
    
    def _render_heartbeat(self):
        t = self._heartbeat_t
        signal = self._get_heartbeat_signal()
        
        phase = self.state.heartbeat_phase
        marker_x = phase * 4 * np.pi
        marker_y = np.interp(marker_x, t, signal)
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=t, y=signal, mode='lines', line=dict(color='#00ff88', width=2), name='ECG'))
        fig.add_trace(go.Scatter(x=[marker_x], y=[marker_y], mode='markers', 
                                  marker=dict(color='#ff3366', size=15, symbol='diamond'), name='فاز'))
        
        fig.update_layout(
            template='plotly_dark', height=200, margin=dict(l=20, r=20, t=30, b=20),
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            showlegend=False
        )
        return fig
    
    def _render_heartbeat_info(self):
        hrv = self.state.system_metrics.get('hrv', 0)
        return html.Div([
            html.Span(f"فاز: {self.state.heartbeat_phase:.2f}π ", style={'color': '#00ff88'}),
            html.Span(f"HRV: {hrv:.4f}", style={'color': '#4fc1ff'}),
            html.Span(f"  بپش: {self.state.system_metrics.get('heartbeat_bpm', 60):.0f} BPM", style={'color': '#dcdcaa'})
        ])
    
    def _render_consciousness(self):
        levels = ['پیش‌آگاهی', 'پدیداری', 'دسترسی', 'تأمل', 'فरा شناختی', 'متجاوز']
        current = self.state.consciousness_level
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=levels, y=[1 if i <= current else 0.1 for i in range(6)],
            marker_color=['#c586c0' if i <= current else '#333' for i in range(6)],
            text=[levels[i] if i <= current else '' for i in range(6)],
            textposition='inside'
        ))
        
        fig.update_layout(
            template='plotly_dark', height=200, margin=dict(l=20, r=20, t=30, b=20),
            yaxis=dict(visible=False), xaxis_tickangle=-15,
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
        )
        return fig
    
    def _render_phi_info(self):
        phi = self.state.phi_value
        color = '#00ff88' if phi > 0.8 else '#ffaa00' if phi > 0.5 else '#ff3366'
        return html.Div([
            html.Span(f"Φ = {phi:.4f}", style={'fontSize': '24px', 'fontWeight': 'bold', 'color': color}),
            html.Br(),
            html.Span("ادغام اطلاعات بالا" if phi > 0.8 else "ادغام متوسط" if phi > 0.5 else "ادغام پایین", style={'color': color})
        ])
    
    def _render_neuromodulators(self):
        mods = self.state.neuromodulators
        if not mods:
            mods = {'دوپامین': 0.5, 'سروتنین': 0.5, 'استیل‌کلیین': 0.5, 'نوراپی نفرین': 0.5, 'ااکسی‌توسین': 0.5, 'کورتیزول': 0.1}
        
        fig = go.Figure()
        fig.add_trace(go.Barpolar(
            r=list(mods.values()),
            theta=list(mods.keys()),
            marker_color=['#4fc1ff', '#00ff88', '#dcdcaa', '#ffaa00', '#ff6b6b', '#c586c0'],
            marker_line_color='#fff',
            marker_line_width=1,
            opacity=0.8
        ))
        
        fig.update_layout(
            template='plotly_dark', height=200, margin=dict(l=20, r=20, t=30, b=20),
            polar=dict(radialaxis=dict(visible=False, range=[0, 1])),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
        )
        return fig
    
    def _render_neural_activity(self):
        activity = self.state.neural_activity
        if len(activity) == 0:
            activity = np.random.randn(100) * 0.1
        
        fig = go.Figure()
        fig.add_trace(go.Heatmap(
            z=activity.reshape(10, -1) if len(activity) >= 100 else activity.reshape(1, -1),
            colorscale='Viridis',
            showscale=False
        ))
        
        fig.update_layout(
            template='plotly_dark', height=300, margin=dict(l=20, r=20, t=30, b=20),
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
        )
        return fig
    
    def _render_emotions(self):
        emotions = self.state.emotional_state
        if not emotions:
            emotions = {'شادی': 0.3, 'ترس': 0.1, 'کنجکاوی': 0.7, 'امید': 0.6, 'غم': 0.05, 'عصبانیت': 0.02}
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=list(emotions.keys()),
            x=list(emotions.values()),
            orientation='h',
            marker_color=['#00ff88' if v > 0.5 else '#4fc1ff' if v > 0.2 else '#ffaa00' if v > 0.1 else '#666' for v in emotions.values()]
        ))
        
        fig.update_layout(
            template='plotly_dark', height=300, margin=dict(l=80, r=20, t=30, b=20),
            xaxis=dict(range=[0, 1], visible=False),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
        )
        return fig
    
    def _render_thoughts(self):
        thoughts = self.state.active_thoughts[-20:]
        elements = []
        for t in reversed(thoughts):
            level_colors = ['#666', '#4ec9b0', '#4fc1ff', '#dcdcaa', '#c586c0', '#ff6b6b']
            level = t.get('consciousness_level', 0)
            color = level_colors[min(level, 5)]
            content = str(t.get('content', ''))
            if len(content) > 200:
                content = content[:200] + '…'
            elements.append(html.Div([
                html.Span(f"[{t.get('timestamp', '')}] ", style={'color': '#666', 'fontSize': '10px'}),
                html.Span(content, style={'color': color}),
                html.Span(f" (یقین: {t.get('certainty', 0):.2f})", style={'color': '#888', 'fontSize': '10px'})
            ], style={'padding': '2px 0', 'borderBottom': '1px solid #1f2a3a'}))
        return elements
    
    def _render_goals(self):
        goals = self.state.current_goals
        elements = []
        for g in goals:
            progress = g.get('progress', 0)
            elements.append(html.Div([
                html.Div([
                    html.Strong(g.get('description', ''), style={'color': '#00ff88'}),
                    html.Span(f" ({g.get('drive', '')})", style={'color': '#888', 'fontSize': '12px', 'marginLeft': '10px'})
                ]),
                dbc.Progress(value=progress*100, color="success" if progress > 0.5 else "warning" if progress > 0.2 else "danger", 
                           style={'height': '6px'}, className="mt-1"),
                html.Small(f"اولویت: {g.get('priority', 0):.2f} | پیشرفت: {progress:.0%}", className="text-muted")
            ], className="mb-2 p-2", style={'backgroundColor': '#161b22', 'borderRadius': '6px'}))
        return elements
    
    def _render_genome(self):
        genome = self.state.genome_stats
        if not genome:
            genome = {'gene_count': 0, 'generation': 0, 'key_traits': {}}
        
        return html.Div([
            html.Div([
                html.Strong("تعداد ژن: "), html.Span(str(genome.get('gene_count', 0)), style={'color': '#00ff88'})
            ]),
            html.Div([
                html.Strong("نسل: "), html.Span(str(genome.get('generation', 0)), style={'color': '#4fc1ff'})
            ]),
            html.Div([
                html.Strong("فیتنس: "), html.Span(f"{genome.get('fitness', 0):.4f}", style={'color': '#dcdcaa'})
            ]),
            html.Hr(),
            html.Strong("صفات کلیدی:"),
            html.Ul([
                html.Li([html.Strong(f"{k}: "), html.Span(f"{v:.3f}", style={'color': '#00ff88'})]) 
                for k, v in genome.get('key_traits', {}).items()
            ], style={'fontSize': '12px'})
        ])
    
    def _render_memory_imagination(self):
        mem = self.state.memory_stats
        imag = self.state.imagination_state
        
        return html.Div([
            html.Div([
                html.Strong("حافظه کاری: "), html.Span(str(mem.get('working', 0)), style={'color': '#00ff88'}),
                html.Span(" | اپیزودیک: "), html.Span(str(mem.get('episodic', 0)), style={'color': '#4fc1ff'}),
                html.Span(" | معنایی: "), html.Span(str(mem.get('semantic', 0)), style={'color': '#dcdcaa'})
            ]),
            html.Div([
                html.Strong("مهارت‌ها: "), html.Span(str(mem.get('procedural', 0)), style={'color': '#c586c0'}),
                html.Span(" | فلش‌बलب: "), html.Span(str(mem.get('flashbulb', 0)), style={'color': '#ff6b6b'})
            ], className="mt-1"),
            html.Hr(),
            html.Div([
                html.Strong("دنیاهای موازی: "), html.Span(str(imag.get('parallel_universes', 0)), style={'color': '#00ff88'}),
                html.Br(),
                html.Strong("چرخه‌های خواب: "), html.Span(str(imag.get('dream_cycles', 0)), style={'color': '#4fc1ff'}),
                html.Br(),
                html.Strong("انسجام کوانتومی: "), html.Span(f"{imag.get('quantum_coherence', 0):.3f}", style={'color': '#dcdcaa'})
            ])
        ])
    
    def _render_system_metrics(self):
        m = self.state.system_metrics
        imag = self.state.imagination_state
        return html.Div([
            html.Div([html.Strong("دورة تفکر: "), html.Span(f"{m.get('thought_cycle', 0):.1f} Hz", style={'color': '#00ff88'})]),
            html.Div([html.Strong("استدلال/دقیقه: "), html.Span(str(m.get('reasoning_per_min', 0)), style={'color': '#4fc1ff'})]),
            html.Div([html.Strong("جستجوی اینترنت: "), html.Span(str(m.get('internet_queries', 0)), style={'color': '#dcdcaa'})]),
            html.Div([html.Strong("تکامل ژنتیکی: "), html.Span(f"نسل {m.get('generation', 0)}", style={'color': '#c586c0'})]),
            html.Div([html.Strong("موتور تخیل: "), html.Span(f"{imag.get('orchestration_cycles', 0)} ارکستراسیون", style={'color': '#ffaa00'})]),
        ])
    
    def _render_conversation(self):
        conv = self.state.conversation_history[-10:]
        elements = []
        for c in conv:
            elements.append(html.Div([
                html.Div([
                    html.Span("🧑 ", style={'marginRight': '5px'}),
                    html.Strong("شما: "), html.Span(c.get('user', ''))
                ], style={'color': '#4fc1ff', 'marginBottom': '5px'}),
                html.Div([
                    html.Span("🤖 ", style={'marginRight': '5px'}),
                    html.Strong("آوانا: "), html.Span(c.get('response', ''))
                ], style={'color': '#00ff88', 'marginBottom': '15px', 'borderLeft': '2px solid #00ff88', 'paddingLeft': '10px'}),
            ]))
        return elements
    
    def run(self, host: str = "0.0.0.0", port: int = 8080, debug: bool = False):
        self.app.run(host=host, port=port, debug=debug, use_reloader=False)


def create_dash_app(organism, config: Dict[str, Any]) -> dash.Dash:
    dashboard = ConsciousnessDashboard(organism, config)
    return dashboard.app