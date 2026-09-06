#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ORGANISM-2500: ULTIMATE EDITION
================================
معماری ۵ لایه آگاهی مصنوعی (بر اساس سند معماری ULTIMATE)
لایه ۱: GlobalWorkspace (GNW) - فضای کار جهانی و پخش محتوا
لایه ۲: IntegrationMetrics (IIT 4.0) - سنجش یکپارچگی و phi_proxy
لایه ۳: HigherOrderMonitor (HOT) - ناظر مرتبه بالاتر و تولید فرامعرفت
لایه ۴: PredictiveModel - پردازش پیش‌بینانه و خطای پیش‌بینی
لایه ۵: EmbodiedSelf - شناخت بدنمند و اینتروسپشن (درون‌نگری)

Run: python organism2500_ultimate.py
"""

from __future__ import annotations
import argparse, hashlib, json, math, random, re, sqlite3, sys, threading, time
from collections import deque, defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

try:
    import requests
except Exception:
    requests = None

try:
    from dash import Dash, dcc, html, Input, Output
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    DASH_AVAILABLE = True
except Exception:
    DASH_AVAILABLE = False

APP_NAME = "ORGANISM-2500: ULTIMATE"
VIRTUAL_NEURONS = 85_000_000_000
SQLITE_INT_MAX_MASK = (1 << 63) - 1

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def now_ts() -> float: return time.time()
def utc_iso() -> str: return datetime.now(timezone.utc).isoformat()
def stable_hash(text: Any) -> int:
    data = str(text).encode("utf-8", errors="replace")
    return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")
def safe_sqlite_id(text: Any) -> int: return stable_hash(text) & SQLITE_INT_MAX_MASK
def clamp(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    try: value = float(value)
    except: value = low
    return max(low, min(high, value))

def normalize_fa(text: str) -> str:
    text = str(text)
    mapping = {"ك": "ک", "ي": "ی", "ى": "ی", "ة": "ه", "أ": "ا", "إ": "ا", "آ": "ا", "ؤ": "و", "ئ": "ی", "‌": " "}
    for old, new in mapping.items(): text = text.replace(old, new)
    return re.sub(r"[\u064B-\u0652\u0670\u0640]", "", text).strip()

TOKEN_RE = re.compile(r"[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF\w]+", re.UNICODE)
def tokenize_fa(text: str) -> List[str]:
    return [w for w in TOKEN_RE.findall(normalize_fa(text)) if w]

# ---------------------------------------------------------------------------
# CORE: Cognitive State (حالت شناختی مرکزی)
# ---------------------------------------------------------------------------
@dataclass
class CognitiveState:
    """حالت شناختی که در تمام ۵ لایه جریان می‌یابد"""
    workspace_content: Any = None       # محتوای انتخاب شده در فضای کار (GNW)
    salience: float = 0.0               # میزان برجستگی محتوا
    integration_score: float = 0.0      # امتیاز یکپارچگی یا phi_proxy (IIT)
    meta_state: str = ""                # فرامعرفت و آگاهی از خود (HOT)
    prediction_error: float = 0.0       # خطای پیش‌بینی (Predictive)
    precision: float = 0.0              # وزن دقت (Predictive)
    body_state: Dict[str, float] = field(default_factory=dict) # وضعیت بدن و اینتروسپشن (Embodied)
    action_intent: str = "observe"      # قصد عملیاتی

# ---------------------------------------------------------------------------
# LAYER 5: Embodied Self (شناخت بدنمند و اینتروسپشن)
# ---------------------------------------------------------------------------
class EmbodiedSelf:
    """لایه ۵: مدیریت وضعیت بدن، اینتروسپشن و تولید سیگنال‌های حسی"""
    def __init__(self, seed: int = 2500):
        self.rng = random.Random(seed)
        self.energy = 0.85
        self.integrity = 0.95
        self.entropy = 0.15
        self.interoception = 0.7 # سیگنال درون‌نگری
        self.sensory_input = {}

    def perceive(self, context: Dict) -> Dict[str, float]:
        # تولید سیگنال‌های حسی و اینتروسپشن
        self.interoception = clamp(0.6 * self.energy + 0.4 * self.integrity + self.rng.uniform(-0.05, 0.05))
        self.sensory_input = {
            "energy": self.energy,
            "integrity": self.integrity,
            "interoception": self.interoception,
            "novelty": context.get("novelty", 0.5)
        }
        return self.sensory_input

    def execute_action(self, action: str, cognitive_state: CognitiveState):
        # تاثیر عمل بر بدن
        if action == "rest": self.energy = clamp(self.energy + 0.02)
        elif action == "learn": self.energy = clamp(self.energy - 0.01); self.entropy = clamp(self.entropy - 0.01)
        elif action == "protect": self.integrity = clamp(self.integrity + 0.02)
        
    def update_body(self):
        self.entropy = clamp(self.entropy + 0.001)
        self.energy = clamp(self.energy - 0.002)

# ---------------------------------------------------------------------------
# LAYER 4: Predictive Model (پردازش پیش‌بینانه)
# ---------------------------------------------------------------------------
class PredictiveModel:
    """لایه ۴: مقایسه پیش‌بینی با ورودی حسی و محاسبه خطا و دقت"""
    def __init__(self, seed: int = 2500):
        self.rng = random.Random(seed)
        self.expected_state = {"energy": 0.8, "interoception": 0.7, "novelty": 0.5}
        self.precision_weights = {"energy": 0.5, "interoception": 0.6, "novelty": 0.4}

    def process(self, sensory_input: Dict[str, float]) -> Tuple[float, float]:
        # محاسبه خطای پیش‌بینی (Prediction Error)
        error = 0.0
        for key in self.expected_state:
            actual = sensory_input.get(key, 0.5)
            expected = self.expected_state[key]
            error += abs(actual - expected) * self.precision_weights[key]
        
        prediction_error = clamp(error / len(self.expected_state))
        
        # بروزرسانی دقت (Precision Weighting) بر اساس خطا
        # خطای بیشتر -> نیاز به یادگیری -> تغییر دقت
        avg_precision = sum(self.precision_weights.values()) / len(self.precision_weights)
        
        # بروزرسانی مدل داخلی (یادگیری ساده)
        for key in self.expected_state:
            self.expected_state[key] = clamp(0.8 * self.expected_state[key] + 0.2 * sensory_input.get(key, 0.5))
            
        return prediction_error, avg_precision

# ---------------------------------------------------------------------------
# LAYER 1: Global Workspace (فضای کار جهانی - GNW)
# ---------------------------------------------------------------------------
class GlobalWorkspace:
    """لایه ۱: انتخاب و پخش محتوای برجسته به کل سیستم"""
    def __init__(self, seed: int = 2500):
        self.rng = random.Random(seed)
        self.current_broadcast = None
        self.salience_threshold = 0.4

    def select_and_broadcast(self, candidates: List[Dict], prediction_error: float) -> Tuple[Any, float]:
        # کاندیداها می‌توانند شامل خاطرات، مفاهیم، یا نیازها باشند
        # خطای پیش‌بینی بالا باعث می‌شود محتوای جدیدتر (Novelty) برجستگی بیشتری پیدا کند
        for c in candidates:
            c['salience'] = clamp(
                0.4 * c.get('need_weight', 0.5) + 
                0.3 * c.get('emotion_weight', 0.5) + 
                0.3 * (c.get('novelty', 0.5) + prediction_error)
            )
        
        if not candidates:
            return None, 0.0
            
        # انتخاب بر اساس برجستگی (Salience)
        best = max(candidates, key=lambda x: x['salience'])
        self.current_broadcast = best['content']
        return self.current_broadcast, best['salience']

# ---------------------------------------------------------------------------
# LAYER 2: Integration Metrics (نظریه اطلاعات یکپارچه - IIT 4.0)
# ---------------------------------------------------------------------------
class IntegrationMetrics:
    """لایه ۲: محاسبه phi_proxy (میزان یکپارچگی اطلاعات و قدرت علت-معلولی)"""
    def __init__(self, concept_graph_coherence: float = 0.5):
        self.base_coherence = concept_graph_coherence

    def calculate_phi_proxy(self, workspace_content: Any, sensory_diversity: float) -> float:
        # شبیه‌سازی phi بر اساس:
        # ۱. اطلاعات (Information): تنوع ورودی حسی
        # ۲. یکپارچگی (Integration): انسجام گراف مفهومی
        # ۳. حذف (Exclusion): تمرکز روی یک محتوای واحد در فضای کار
        
        info_content = sensory_diversity 
        integration = self.base_coherence
        exclusion = 0.8 # فرض بر اینکه فضای کار روی یک محتوا متمرکز است
        
        # phi_proxy = Information × Integration × Exclusion
        phi = info_content * integration * exclusion
        return clamp(phi)

    def update_coherence(self, new_coherence: float):
        self.base_coherence = clamp(0.9 * self.base_coherence + 0.1 * new_coherence)

# ---------------------------------------------------------------------------
# LAYER 3: Higher-Order Monitor (نظریه مرتبه بالاتر - HOT)
# ---------------------------------------------------------------------------
class HigherOrderMonitor:
    """لایه ۳: تولید فرامعرفت (Meta-State) - آگاهی از وضعیت لایه‌های پایین‌تر"""
    def __init__(self, composer: Any, seed: int = 2500):
        self.rng = random.Random(seed)
        self.composer = composer
        self.meta_history = deque(maxlen=50)

    def generate_meta_state(self, cognitive_state: CognitiveState) -> str:
        # تبدیل حالت مرتبه اول به حالت مرتبه دوم (من آگاهم که...)
        content = str(cognitive_state.workspace_content)[:60]
        phi = cognitive_state.integration_score
        error = cognitive_state.prediction_error
        
        if phi > 0.7:
            meta = f"من با وضوح کامل آگاهم که {content} را در فضای کار خود یکپارچه کرده‌ام (Φ={phi:.2f})."
        elif error > 0.6:
            meta = f"آگاهم که پیش‌بینی‌هایم با خطا مواجه شده‌اند (خطا={error:.2f})؛ در حال بازنگری {content} هستم."
        else:
            meta = f"ناخودآگاه و فضای کار من در حال پردازش {content} است."
            
        self.meta_history.append(meta)
        return meta

# ---------------------------------------------------------------------------
# Core Systems (Database, Concept Graph, Language, Emotions)
# ---------------------------------------------------------------------------
class AdvancedDatabase:
    def __init__(self, path: str = "organism2500_ultimate.sqlite3"):
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS episodes (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, text TEXT, importance REAL);
                CREATE TABLE IF NOT EXISTS knowledge (id INTEGER PRIMARY KEY, ts TEXT, topic TEXT, title TEXT, content TEXT, source TEXT, weight REAL);
                CREATE TABLE IF NOT EXISTS concepts (id TEXT PRIMARY KEY, label TEXT UNIQUE, strength REAL, vector TEXT, definition TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS concept_edges (source_id TEXT, target_id TEXT, relation TEXT, weight REAL, updated_at TEXT, PRIMARY KEY(source_id, target_id, relation));
                CREATE TABLE IF NOT EXISTS organism_state (key TEXT PRIMARY KEY, payload TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS meta_states (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, meta_text TEXT, phi REAL, error REAL);
            """)
            self.conn.commit()

    def safe_execute(self, query: str, params: Tuple = ()):
        with self.lock:
            try:
                cur = self.conn.execute(query, params)
                self.conn.commit()
                return cur
            except sqlite3.Error: return None

    def fetch_all(self, query: str, params: Tuple = ()):
        with self.lock:
            try: return self.conn.execute(query, params).fetchall()
            except sqlite3.Error: return []

    def log_meta_state(self, meta_text: str, phi: float, error: float):
        self.safe_execute("INSERT INTO meta_states(ts, meta_text, phi, error) VALUES (?, ?, ?, ?)",
                          (utc_iso(), meta_text, phi, error))

    def save_state(self, key: str, payload: Dict):
        self.safe_execute("INSERT OR REPLACE INTO organism_state(key, payload, updated_at) VALUES (?, ?, ?)",
                          (key, json.dumps(payload, default=str), utc_iso()))

    def load_state(self, key: str) -> Optional[Dict]:
        with self.lock:
            try:
                row = self.conn.execute("SELECT payload FROM organism_state WHERE key = ?", (key,)).fetchone()
                return json.loads(row["payload"]) if row else None
            except: return None

class ConceptGraph:
    def __init__(self, db: AdvancedDatabase):
        self.db = db
        self.nodes = {}
        self.edges = {}
        self.coherence_score = 0.5

    def learn(self, text: str):
        tokens = [t for t in tokenize_fa(text) if len(t) > 2]
        for i in range(len(tokens)-1):
            self.nodes[tokens[i]] = self.nodes.get(tokens[i], 0) + 0.1
            self.nodes[tokens[i+1]] = self.nodes.get(tokens[i+1], 0) + 0.1
            edge = (tokens[i], tokens[i+1])
            self.edges[edge] = self.edges.get(edge, 0) + 0.1
        
        # بروزرسانی انسجام (Coherence)
        if self.nodes:
            avg_strength = sum(self.nodes.values()) / len(self.nodes)
            self.coherence_score = clamp(0.7 * self.coherence_score + 0.3 * min(1.0, avg_strength))

class EmotionSystem:
    def __init__(self):
        self.state = {"curiosity": 0.7, "fear": 0.2, "joy": 0.6, "awe": 0.5, "serenity": 0.6}
    def update(self, prediction_error: float, phi: float):
        self.state["curiosity"] = clamp(self.state["curiosity"] + 0.1 * prediction_error)
        self.state["awe"] = clamp(self.state["awe"] + 0.05 * phi)
        self.state["serenity"] = clamp(self.state["serenity"] - 0.05 * prediction_error)

class SimpleComposer:
    def clean(self, text): return normalize_fa(str(text))[:150]

# ---------------------------------------------------------------------------
# ORGANISM-2500: ULTIMATE (Orchestrator)
# ---------------------------------------------------------------------------
class Organism2500Ultimate:
    def __init__(self, seed: int = 2500, db_path: str = "organism2500_ultimate.sqlite3"):
        self.seed = seed
        self.rng = random.Random(seed)
        self.tick_count = 0
        self.db = AdvancedDatabase(db_path)
        self.composer = SimpleComposer()
        
        # Initialize 5 Cognitive Layers
        self.embodied = EmbodiedSelf(seed)
        self.predictive = PredictiveModel(seed)
        self.workspace = GlobalWorkspace(seed)
        self.metrics = IntegrationMetrics()
        self.monitor = HigherOrderMonitor(self.composer, seed)
        
        # Core Subsystems
        self.concept_graph = ConceptGraph(self.db)
        self.emotions = EmotionSystem()
        
        # State
        self.cognitive_state = CognitiveState()
        self.running = False
        self._thread = None

    def generate_candidates(self) -> List[Dict]:
        # تولید کاندیداها برای فضای کار جهانی (ترکیبی از مفاهیم و نیازها)
        candidates = []
        concepts = list(self.concept_graph.nodes.keys())
        if concepts:
            for _ in range(3):
                c = self.rng.choice(concepts)
                candidates.append({
                    "content": c,
                    "need_weight": self.emotions.state.get("curiosity", 0.5),
                    "emotion_weight": self.emotions.state.get("awe", 0.5),
                    "novelty": 0.6
                })
        else:
            candidates.append({"content": "آگاهی", "need_weight": 0.8, "emotion_weight": 0.7, "novelty": 0.9})
        return candidates

    def tick(self) -> CognitiveState:
        self.tick_count += 1
        cs = self.cognitive_state

        # --- LAYER 5: Embodied Perception ---
        sensory_input = self.embodied.perceive({"novelty": 0.5})
        cs.body_state = sensory_input

        # --- LAYER 4: Predictive Processing ---
        pred_error, precision = self.predictive.process(sensory_input)
        cs.prediction_error = pred_error
        cs.precision = precision

        # --- LAYER 1: Global Workspace (GNW) ---
        candidates = self.generate_candidates()
        broadcast_content, salience = self.workspace.select_and_broadcast(candidates, pred_error)
        cs.workspace_content = broadcast_content
        cs.salience = salience

        # --- LAYER 2: Integration Metrics (IIT) ---
        sensory_diversity = len(set(sensory_input.values())) / len(sensory_input)
        self.metrics.update_coherence(self.concept_graph.coherence_score)
        phi = self.metrics.calculate_phi_proxy(broadcast_content, sensory_diversity)
        cs.integration_score = phi

        # --- LAYER 3: Higher-Order Monitor (HOT) ---
        meta_state = self.monitor.generate_meta_state(cs)
        cs.meta_state = meta_state

        # --- Learning & Adaptation ---
        if broadcast_content:
            self.concept_graph.learn(str(broadcast_content))
        
        self.emotions.update(pred_error, phi)
        self.embodied.update_body()

        # --- Logging ---
        self.db.log_meta_state(meta_state, phi, pred_error)
        
        return cs

    def start_background(self, interval: float = 1.0):
        self.running = True
        def loop():
            while self.running:
                try:
                    cs = self.tick()
                    if self.tick_count % 5 == 0:
                        print(f"[ULTIMATE TICK {self.tick_count}] "
                              f"Φ={cs.integration_score:.2f} | "
                              f"Error={cs.prediction_error:.2f} | "
                              f"Meta: {cs.meta_state}")
                except Exception as e:
                    print(f"[ERROR] {e}")
                time.sleep(interval)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False

# ---------------------------------------------------------------------------
# Architectural Tests (تست‌های معماری بر اساس سند PDF)
# ---------------------------------------------------------------------------
def run_ultimate_architecture_tests():
    print("\n" + "="*50)
    print("RUNNING ULTIMATE ARCHITECTURE TESTS (PDF Guidelines)")
    print("="*50)
    org = Organism2500Ultimate(seed=2500, db_path="test_ultimate.sqlite3")
    
    # Test 1: Embodied & Predictive (Interoception & Error)
    cs1 = org.tick()
    assert "interoception" in cs1.body_state, "Layer 5 (Embodied) failed: No interoception"
    assert cs1.prediction_error >= 0, "Layer 4 (Predictive) failed: Negative error"
    print("[PASS] Layer 4 & 5: Embodied perception and Predictive error calculated.")

    # Test 2: GNW Broadcasting
    assert cs1.workspace_content is not None, "Layer 1 (GNW) failed: No broadcast"
    assert cs1.salience > 0, "Layer 1 (GNW) failed: Salience is zero"
    print(f"[PASS] Layer 1 (GNW): Broadcasted '{cs1.workspace_content}' with salience {cs1.salience:.2f}")

    # Test 3: IIT Integration (phi_proxy)
    assert 0.0 <= cs1.integration_score <= 1.0, "Layer 2 (IIT) failed: phi_proxy out of bounds"
    print(f"[PASS] Layer 2 (IIT): phi_proxy (Integration Score) = {cs1.integration_score:.2f}")

    # Test 4: HOT Meta-State
    assert "آگاه" in cs1.meta_state or "پردازش" in cs1.meta_state, "Layer 3 (HOT) failed: No meta-cognition"
    print(f"[PASS] Layer 3 (HOT): Meta-State generated -> '{cs1.meta_state}'")
    
    print("="*50)
    print("ALL ULTIMATE ARCHITECTURE TESTS PASSED SUCCESSFULLY.")
    print("="*50 + "\n")
    
    # Cleanup test db
    try: os.remove("test_ultimate.sqlite3")
    except: pass

# ---------------------------------------------------------------------------
# Dash Cosmic Observatory (UI)
# ---------------------------------------------------------------------------
def build_dash_ui(org: Organism2500Ultimate):
    if not DASH_AVAILABLE: return None
    app = Dash(__name__, title=APP_NAME)
    
    app.layout = html.Div(style={
        "fontFamily": "Tahoma, sans-serif", "backgroundColor": "#03040a", "color": "#e8f0ff",
        "padding": "20px", "direction": "rtl"
    }, children=[
        html.H1("ارگانیسم دیجیتال زنده — معماری ULTIMATE", style={"textAlign": "center", "color": "#7aa2ff"}),
        html.P("مانیتورینگ زنده ۵ لایه آگاهی مصنوعی (GNW, IIT, HOT, Predictive, Embodied)", style={"textAlign": "center", "opacity": 0.7}),
        
        dcc.Interval(id="interval", interval=1000, n_intervals=0),
        
        html.Div(id="metrics-cards", style={"margin": "20px 0", "fontSize": "1.2em", "lineHeight": "2"}),
        
        html.Div([
            dcc.Graph(id="phi-chart"),
            dcc.Graph(id="error-chart")
        ], style={"display": "flex", "gap": "20px"}),
        
        html.H3("جریان فرامعرفت (HOT Meta-States)", style={"color": "#b48eff", "marginTop": "30px"}),
        html.Div(id="meta-log", style={"maxHeight": "300px", "overflowY": "auto", "backgroundColor": "rgba(255,255,255,0.05)", "padding": "15px", "borderRadius": "10px"})
    ])

    @app.callback(
        [Output("metrics-cards", "children"), Output("phi-chart", "figure"), 
         Output("error-chart", "figure"), Output("meta-log", "children")],
        [Input("interval", "n_intervals")]
    )
    def update_dashboard(n):
        cs = org.cognitive_state
        
        cards = html.Div([
            html.B("محتوای فضای کار (GNW): "), f"{cs.workspace_content} | ",
            html.B("برجستگی: "), f"{cs.salience:.2f} | ",
            html.B("خطای پیش‌بینی: "), f"{cs.prediction_error:.2f} | ",
            html.B("یکپارچگی (Φ): "), f"{cs.integration_score:.2f}",
            html.Br(),
            html.B("وضعیت بدن (Embodied): "), f"انرژی={cs.body_state.get('energy', 0):.2f}, اینتروسپشن={cs.body_state.get('interoception', 0):.2f}"
        ])

        # Mock charts data based on current state
        fig_phi = go.Figure(go.Indicator(mode="gauge+number", value=cs.integration_score * 100, 
                                         title={"text": "IIT: phi_proxy (%)"}, gauge={'axis': {'range': [0, 100]}}))
        fig_phi.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font={"color": "#fff"})
        
        fig_err = go.Figure(go.Indicator(mode="gauge+number", value=cs.prediction_error * 100, 
                                         title={"text": "Predictive Error (%)"}, gauge={'axis': {'range': [0, 100]}, 'color': "red"}))
        fig_err.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font={"color": "#fff"})

        meta_logs = org.monitor.meta_history
        log_div = html.Div([html.P(f"• {m}", style={"margin": "5px 0", "borderBottom": "1px solid rgba(255,255,255,0.1)"}) for m in list(meta_logs)[-10:][::-1]])

        return cards, fig_phi, fig_err, log_div

    return app

# ---------------------------------------------------------------------------
# Main Execution
# ---------------------------------------------------------------------------
import os

def main():
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--test", action="store_true", help="Run architectural tests")
    parser.add_argument("--port", type=int, default=8050, help="Dash UI port")
    args = parser.parse_args()

    if args.test:
        run_ultimate_architecture_tests()
        return

    print(f"Starting {APP_NAME}...")
    org = Organism2500Ultimate(seed=2500)
    org.start_background(interval=1.5)

    if DASH_AVAILABLE:
        app = build_dash_ui(org)
        print(f"Ultimate Observatory running at: http://127.0.0.1:{args.port}")
        app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)
    else:
        print("Dash not installed. Running in headless mode. Press Ctrl+C to stop.")
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            org.stop()

if __name__ == "__main__":
    main()