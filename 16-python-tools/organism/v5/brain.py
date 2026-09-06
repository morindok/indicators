# -*- coding: utf-8 -*-
"""
====================================================================================================
 NOUS-EMBRYO : DASH EVOLUTION VISUALIZER
====================================================================================================
 اسپرم + تخمک -> لقاح -> رشد جنین -> تکامل ژنوم
 تمام مسیر تکامل به صورت بصری و زنده در Dash نمایش داده می‌شود:
   * رشد زنده سلول‌ها (تقسیم/تمایز/مرگ)
   * نمودار مسیر fitness در طول نسل‌ها
   * heatmap مسیر تغییر ژنوم در هر نسل
   * توزیع انواع سلول‌ها
   * میدان مورفوژن
====================================================================================================
"""

import dash
from dash import dcc, html, Input, Output, State, ctx
import plotly.graph_objects as go
import numpy as np
import random
import math
import threading
import time
from dataclasses import dataclass
from typing import List, Tuple, Optional

# ═══════════════════════════════════════════════════════════════
# تنظیمات
# ═══════════════════════════════════════════════════════════════

GRID_SIZE = 48
CENTER = GRID_SIZE / 2.0
MAX_CELLS = 350
GENOME_SIZE = 16

TYPE_NAMES = ["Stem", "Skin", "Muscle", "Neuron", "Germ"]
TYPE_COLORS = ["#c0c0c0", "#00ff88", "#ff5555", "#00ccff", "#ffd700"]

GENE_NAMES = [
    "تقسیم", "آستانه تقسیم", "بازده غذا", "هزینه",
    "مورفوژن+", "حساسیت", "چسبندگی", "دافعه",
    "آپوپتوز", "جهش", "انعطاف", "عمر",
    "پوست", "ماهیچه", "نورون", "زایا"
]

# ═══════════════════════════════════════════════════════════════
# توابع کمکی
# ═══════════════════════════════════════════════════════════════

def clamp(v, lo=0.0, hi=1.0): return max(lo, min(hi, v))

def sigmoid(x):
    x = clamp(x, -20, 20)
    return 1.0 / (1.0 + math.exp(-x))

def grid_index(pos):
    x, y = pos
    return int(np.clip(y, 0, GRID_SIZE-1)), int(np.clip(x, 0, GRID_SIZE-1))

def diffuse(field, rate, decay):
    lap = (np.roll(field,1,0)+np.roll(field,-1,0)+np.roll(field,1,1)+np.roll(field,-1,1)-4*field)
    return np.clip((field + rate*lap) * decay, 0.0, 1.0)

# ═══════════════════════════════════════════════════════════════
# ژنوم
# ═══════════════════════════════════════════════════════════════

def random_genome():
    g = np.random.rand(GENOME_SIZE)
    g[0]=random.uniform(0.35,0.75); g[1]=random.uniform(0.45,0.75)
    g[2]=random.uniform(0.45,0.95); g[3]=random.uniform(0.01,0.04)
    g[4]=random.uniform(0.15,0.65); g[5]=random.uniform(0.35,0.95)
    g[6]=random.uniform(0.15,0.65); g[7]=random.uniform(0.35,0.95)
    g[8]=random.uniform(0.05,0.35); g[9]=random.uniform(0.02,0.12)
    g[10]=random.uniform(0.25,0.85); g[11]=random.uniform(0.55,1.0)
    g[12]=random.uniform(0.58,0.75); g[13]=random.uniform(0.40,0.58)
    g[14]=random.uniform(0.22,0.40); g[15]=random.uniform(0.06,0.22)
    g[12:16] = np.sort(g[12:16])[::-1]
    return g

def mutate_genome(genome, rate=None, strength=0.08):
    g = genome.copy()
    if rate is None: rate = clamp(g[9]*0.5+0.01, 0.005, 0.35)
    mask = np.random.rand(GENOME_SIZE) < rate
    n = int(np.count_nonzero(mask))
    if n: g[mask] += np.random.normal(0, strength, n)
    g = np.clip(g, 0, 1)
    g[12:16] = np.sort(g[12:16])[::-1]
    return g

def crossover_combine(sperm_g, egg_g):
    w = np.random.beta(2,2,GENOME_SIZE)
    child = w*sperm_g + (1-w)*egg_g + np.random.normal(0,0.015,GENOME_SIZE)
    return mutate_genome(child, rate=max(0.01, child[9]*0.35), strength=0.035)

@dataclass
class Gamete:
    sex: str
    genome: np.ndarray
    energy: float = 0.2

def make_gamete(parent, sex):
    g = mutate_genome(parent, rate=0.08, strength=0.05)
    e = random.uniform(1.6,2.1) if sex=="egg" else random.uniform(0.15,0.30)
    return Gamete(sex, g, e)

@dataclass
class Cell:
    pos: np.ndarray
    genome: np.ndarray
    energy: float
    age: int = 0
    type: int = 0
    alive: bool = True
    vx: float = 0.0
    vy: float = 0.0

# ═══════════════════════════════════════════════════════════════
# جنین
# ═══════════════════════════════════════════════════════════════

class Embryo:
    def __init__(self, genome, initial_energy=2.0):
        self.genome = genome.copy()
        self.tick = 0; self.alive = True; self.fitness = 0.0
        self.last_counts = np.zeros(5, dtype=int)
        center = np.array([CENTER, CENTER], dtype=float)
        self.cells = [Cell(pos=center, genome=self.genome.copy(), energy=initial_energy)]
        self.nutrient = np.ones((GRID_SIZE, GRID_SIZE))
        self.morphogen = np.zeros((GRID_SIZE, GRID_SIZE))

    def _update_fields(self):
        self.nutrient = diffuse(self.nutrient, 0.22, 0.997) + 0.006
        self.nutrient[0,:]=1; self.nutrient[-1,:]=1; self.nutrient[:,0]=1; self.nutrient[:,-1]=1
        np.clip(self.nutrient,0,1,out=self.nutrient)
        self.morphogen = diffuse(self.morphogen, 0.30, 0.965)

    def _density_grid(self):
        d = np.zeros((GRID_SIZE,GRID_SIZE), dtype=int)
        for c in self.cells:
            iy,ix = grid_index(c.pos); d[iy,ix]+=1
        return d

    def _cell_fate(self, cell, morph, dens):
        if random.random() > cell.genome[10]*0.5 + 0.05: return cell.type
        m = morph*(0.4+1.2*cell.genome[5]) + 0.02*dens + random.gauss(0,0.02)
        if dens<=2 and cell.energy>0.8 and random.random()<clamp(0.02+cell.genome[15]*0.2,0,0.25): return 4
        if m>cell.genome[12]: return 1
        elif m>cell.genome[13]: return 2
        elif m>cell.genome[14]: return 3
        elif m<cell.genome[15]: return 4
        return 0

    def _try_divide(self, cell, dens, births):
        if len(self.cells)+len(births) >= MAX_CELLS: return
        if cell.age < 8: return
        if cell.energy <= cell.genome[1]: return
        prob = cell.genome[0]*sigmoid((cell.energy-cell.genome[1])*6)*(1/(1+0.4*max(0,dens-2)))*0.35
        if random.random() < clamp(prob,0,0.7):
            cg = mutate_genome(cell.genome, rate=cell.genome[9]*0.2+0.001, strength=0.02)
            ang = random.uniform(0,2*math.pi)
            off = np.array([math.cos(ang), math.sin(ang)])*0.55
            births.append(Cell(pos=cell.pos+off, genome=cg, energy=cell.energy*0.45, type=cell.type))
            cell.energy *= 0.45

    def _should_die(self, cell, dens):
        if cell.energy <= 0: return True
        if cell.age > 700*(0.4+cell.genome[11]): return True
        stress = clamp(max(0,dens-8)*0.02*cell.genome[8] + max(0,-cell.energy)*0.5, 0, 0.3)
        return random.random() < stress

    def _mechanics(self):
        cells = self.cells; n = len(cells)
        if n < 2: return
        for i in range(n):
            ci = cells[i]
            for j in range(i+1, n):
                cj = cells[j]
                dx=ci.pos[0]-cj.pos[0]; dy=ci.pos[1]-cj.pos[1]
                dist = math.hypot(dx,dy)
                if dist < 1e-6: continue
                if dist < 1.0:
                    f=(1-dist)*0.12*(0.5+0.25*(ci.genome[7]+cj.genome[7]))
                    ux,uy=dx/dist,dy/dist
                    ci.vx+=ux*f; ci.vy+=uy*f; cj.vx-=ux*f; cj.vy-=uy*f
                elif ci.type==cj.type and ci.type!=0 and dist<2.2:
                    f=0.015*(0.5+0.25*(ci.genome[6]+cj.genome[6]))*(dist-1.15)
                    ux,uy=dx/dist,dy/dist
                    ci.vx-=ux*f; ci.vy-=uy*f; cj.vx+=ux*f; cj.vy+=uy*f
        max_r = CENTER-2.0
        for c in cells:
            c.vx=clamp(c.vx*0.65+random.gauss(0,0.015),-0.5,0.5)
            c.vy=clamp(c.vy*0.65+random.gauss(0,0.015),-0.5,0.5)
            c.pos[0]=clamp(c.pos[0]+c.vx,1,GRID_SIZE-2); c.pos[1]=clamp(c.pos[1]+c.vy,1,GRID_SIZE-2)
            dx=c.pos[0]-CENTER; dy=c.pos[1]-CENTER; r=math.hypot(dx,dy)
            if r>max_r and r>1e-6:
                c.pos[0]=CENTER+dx/r*max_r; c.pos[1]=CENTER+dy/r*max_r
                c.vx*=-0.2; c.vy*=-0.2

    def _compute_fitness(self):
        if not self.cells:
            self.last_counts = np.zeros(5,dtype=int)
            return clamp(0.10*(self.tick/700.0),0,1)
        counts = np.bincount([c.type for c in self.cells], minlength=5)
        self.last_counts = counts
        count_score = min(len(self.cells)/300.0,1.0)
        diff = counts[1:]; tot=float(np.sum(diff))
        if tot>0:
            p=diff.astype(float)/(tot+1e-12); p=p[p>0]
            diversity = -float(np.sum(p*np.log(p)))/math.log(4)
        else: diversity=0
        germ = min(counts[4]/12.0,1.0)
        energy = clamp(float(np.mean([c.energy for c in self.cells])),0,1)
        survival = min(self.tick/700.0,1.0)
        return clamp(0.30*survival+0.25*count_score+0.20*diversity+0.15*germ+0.10*energy,0,1)

    def step(self):
        if not self.alive: return
        self.tick += 1
        self._update_fields()
        dens_grid = self._density_grid()
        births=[]
        for cell in self.cells:
            cell.age += 1
            iy,ix = grid_index(cell.pos)
            taken = min(self.nutrient[iy,ix], 0.09)
            self.nutrient[iy,ix]-=taken
            cell.energy += taken*cell.genome[2]*2.0 - (cell.genome[3]*0.35+0.004+0.001*cell.age/50) - 0.004*max(0,dens_grid[iy,ix]-4)
            sec = cell.genome[4]*0.02
            if cell.type==1: sec*=1.5
            elif cell.type==3: sec*=0.6
            self.morphogen[iy,ix]+=sec
            cell.type = self._cell_fate(cell, self.morphogen[iy,ix], dens_grid[iy,ix])
            self._try_divide(cell, dens_grid[iy,ix], births)
            if self._should_die(cell, dens_grid[iy,ix]): cell.alive=False
        self.cells = [c for c in self.cells if c.alive] + births
        if not self.cells:
            self.alive=False; self.fitness=self._compute_fitness(); return
        self._mechanics()
        self.fitness = self._compute_fitness()

    def snapshot(self):
        if not self.cells:
            return {"tick":self.tick,"pos":np.empty((0,2)),"types":np.empty(0,dtype=int),"energy":np.empty(0)}
        return {
            "tick": self.tick,
            "pos": np.array([[c.pos[0],c.pos[1]] for c in self.cells]),
            "types": np.array([c.type for c in self.cells]),
            "energy": np.array([c.energy for c in self.cells])
        }

    def run_recorded(self, max_ticks=160, record_every=4):
        frames=[]
        for t in range(max_ticks):
            self.step()
            if t % record_every == 0: frames.append(self.snapshot())
            if not self.alive: break
        frames.append(self.snapshot())
        self.fitness = self._compute_fitness()
        return self.fitness, frames

def fertilize(sperm, egg):
    return Embryo(crossover_combine(sperm.genome, egg.genome), sperm.energy+egg.energy)

# ═══════════════════════════════════════════════════════════════
# موتور تکامل
# ═══════════════════════════════════════════════════════════════

class EvolutionEngine:
    def __init__(self, pop_size=6, generations=6, dev_ticks=160):
        self.pop_size=max(3,pop_size); self.generations=max(1,generations); self.dev_ticks=max(60,dev_ticks)
        self.on_generation=None; self.stop_flag=False

    def run(self):
        parents=[random_genome() for _ in range(max(2,self.pop_size))]
        best_genome=parents[0]
        for gen in range(self.generations):
            if self.stop_flag: break
            scored=[]
            for i in range(self.pop_size):
                if self.stop_flag: break
                father = random.choice(parents) if gen>0 else random_genome()
                mother = random.choice(parents) if gen>0 else random_genome()
                embryo = fertilize(make_gamete(father,"sperm"), make_gamete(mother,"egg"))
                fitness, frames = embryo.run_recorded(self.dev_ticks)
                scored.append((fitness, embryo.genome, frames))
            if not scored: break
            scored.sort(key=lambda x:x[0], reverse=True)
            best_fitness, best_genome, best_frames = scored[0]
            entry = {
                "gen":gen, "best":float(best_fitness),
                "mean":float(np.mean([s[0] for s in scored])),
                "best_genome":best_genome.copy(), "best_frames":best_frames
            }
            if self.on_generation: self.on_generation(entry)
            elite_n=max(2,self.pop_size//3)
            parents=[s[1].copy() for s in scored[:elite_n]]
            parents.append(mutate_genome(best_genome, rate=0.12, strength=0.08))
        return best_genome

# ═══════════════════════════════════════════════════════════════
# وضعیت سراسری اپ
# ═══════════════════════════════════════════════════════════════

class AppState:
    def __init__(self):
        self.lock = threading.RLock()
        self.status="idle"
        self.history=[]
        self.replay_frames=[]
        self.replay_idx=0
        self.replay_label="—"
        self.final_embryo=None
        self.best_genome=None
        self.initial_genome=None
        self.engine=None

    def start(self, generations, pop_size):
        with self.lock:
            self.history=[]; self.replay_frames=[]; self.replay_idx=0
            self.final_embryo=None; self.best_genome=None
            self.initial_genome=random_genome()
            self.status="evolving"
        threading.Thread(target=self._worker, args=(generations,pop_size), daemon=True).start()

    def _worker(self, generations, pop_size):
        engine = EvolutionEngine(pop_size, generations)
        self.engine = engine
        def on_gen(entry):
            with self.lock:
                self.history.append(entry)
                self.replay_frames = entry["best_frames"]
                self.replay_idx = 0
                self.replay_label = f"قهرمان نسل {entry['gen']+1}"
        engine.on_generation = on_gen
        best = engine.run()
        final = fertilize(make_gamete(best,"sperm"), make_gamete(mutate_genome(best,0.03,0.03),"egg"))
        with self.lock:
            self.best_genome = best
            self.final_embryo = final
            self.status = "growing"

    def reset(self):
        with self.lock:
            if self.engine: self.engine.stop_flag=True
            self.status="idle"; self.history=[]; self.replay_frames=[]
            self.final_embryo=None; self.best_genome=None

STATE = AppState()

# ═══════════════════════════════════════════════════════════════
# Dash UI
# ═══════════════════════════════════════════════════════════════

app = dash.Dash(__name__, title="NOUS-EMBRYO Evolution")

C = {"bg":"#05050A","panel":"#0A0A15","cyan":"#00FFFF","gold":"#FFD700",
     "green":"#00FF00","red":"#FF3333","magenta":"#FF00FF","text":"#E0E0FF"}

def panel(color):
    return {"backgroundColor":C["panel"],"border":f"1px solid {color}",
            "borderRadius":"10px","padding":"10px","boxShadow":f"0 0 12px {color}40"}

app.layout = html.Div(dir="rtl", style={"backgroundColor":C["bg"],"color":C["text"],
    "fontFamily":"Vazirmatn, monospace","padding":"15px","minHeight":"100vh"}, children=[

    html.H1("🧬 NOUS-EMBRYO : مسیر تکامل زنده", style={"textAlign":"center","color":C["cyan"],
        "textShadow":"0 0 20px #00FFFF"}),
    html.P("اسپرم + تخمک -> لقاح -> رشد جنین -> انتخاب طبیعی ژنوم",
           style={"textAlign":"center","color":C["gold"]}),
    html.Hr(style={"borderColor":C["cyan"]}),

    # کنترل‌ها
    html.Div(style={"display":"flex","gap":"15px","justifyContent":"center","alignItems":"center","flexWrap":"wrap"}, children=[
        html.Div([html.Label("نسل‌ها"), dcc.Input(id="in-generations", type="number", value=6, min=1, max=20,
            style={"background":"#111","color":C["text"],"marginRight":"5px"})]),
        html.Div([html.Label("جمعیت"), dcc.Input(id="in-pop", type="number", value=6, min=3, max=12,
            style={"background":"#111","color":C["text"],"marginRight":"5px"})]),
        html.Div([html.Label("سرعت"), dcc.Input(id="in-speed", type="number", value=3, min=1, max=10,
            style={"background":"#111","color":C["text"],"marginRight":"5px"})]),
        html.Button("🚀 شروع تکامل", id="btn-start",
            style={"background":C["green"],"color":"#000","fontWeight":"bold","border":"none",
                   "borderRadius":"8px","padding":"10px 20px","cursor":"pointer"}),
        html.Button("♻️ ریست", id="btn-reset",
            style={"background":C["red"],"color":"#fff","border":"none","borderRadius":"8px",
                   "padding":"10px 20px","cursor":"pointer"}),
    ]),

    html.Div(id="stats-bar", style={"display":"grid","gridTemplateColumns":"repeat(5,1fr)",
        "gap":"10px","margin":"15px 0"}),

    html.Div(style={"display":"grid","gridTemplateColumns":"2fr 1fr","gap":"15px"}, children=[
        html.Div(id="graph-embryo", style=panel(C["cyan"])),
        html.Div(id="graph-evolution", style=panel(C["green"])),
    ]),

    html.Div(style={"display":"grid","gridTemplateColumns":"1fr 1fr 1fr","gap":"15px","marginTop":"15px"}, children=[
        html.Div(id="graph-genome-path", style=panel(C["gold"])),
        html.Div(id="graph-types", style=panel(C["magenta"])),
        html.Div(id="graph-field", style=panel(C["red"])),
    ]),

    html.Div(id="message", style={"textAlign":"center","marginTop":"10px","color":"#888"}),
    dcc.Interval(id="interval", interval=250, n_intervals=0),
])

# ═══════════════════════════════════════════════════════════════
# سازنده نمودارها
# ═══════════════════════════════════════════════════════════════

def empty_snap():
    return {"tick":0,"pos":np.empty((0,2)),"types":np.empty(0,dtype=int),"energy":np.empty(0)}

def fig_embryo(snap, title):
    fig = go.Figure()
    for t in range(5):
        mask = snap["types"]==t
        if not np.any(mask): continue
        fig.add_trace(go.Scatter(x=snap["pos"][mask,0], y=snap["pos"][mask,1], mode="markers",
            name=TYPE_NAMES[t], marker=dict(size=11, color=TYPE_COLORS[t],
            line=dict(width=1,color="black"))))
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", title=title, height=420,
        xaxis=dict(visible=False), yaxis=dict(visible=False, scaleanchor="x"),
        margin=dict(l=10,r=10,t=40,b=10), legend=dict(orientation="h",y=-0.05))
    return fig

def fig_evolution(history):
    fig = go.Figure()
    if history:
        gens=[h["gen"]+1 for h in history]
        fig.add_trace(go.Scatter(x=gens,y=[h["best"] for h in history],mode="lines+markers",
            name="بهترین",line=dict(color=C["green"],width=3)))
        fig.add_trace(go.Scatter(x=gens,y=[h["mean"] for h in history],mode="lines+markers",
            name="میانگین",line=dict(color=C["gold"],width=2,dash="dash")))
    fig.update_layout(template="plotly_dark",paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
        title="مسیر تکامل Fitness", height=420, xaxis_title="نسل", yaxis_title="Fitness",
        margin=dict(l=40,r=10,t=40,b=40))
    return fig

def fig_genome_path(history, initial):
    fig = go.Figure()
    rows=[]; labels=[]
    if initial is not None: rows.append(initial); labels.append("شروع")
    for h in (history or []): rows.append(h["best_genome"]); labels.append(f"نسل {h['gen']+1}")
    if rows:
        fig.add_trace(go.Heatmap(z=np.array(rows), x=GENE_NAMES, y=labels,
            colorscale="Viridis", zmin=0, zmax=1))
    fig.update_layout(template="plotly_dark",paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
        title="مسیر تغییر ژنوم در طول تکامل", height=320, margin=dict(l=10,r=10,t=40,b=60))
    return fig

def fig_types(snap):
    counts=[int(np.sum(snap["types"]==t)) for t in range(5)]
    fig = go.Figure(go.Pie(labels=TYPE_NAMES, values=counts,
        marker=dict(colors=TYPE_COLORS)))
    fig.update_layout(template="plotly_dark",paper_bgcolor="rgba(0,0,0,0)",
        title="توزیع انواع سلول", height=320, margin=dict(l=10,r=10,t=40,b=10))
    return fig

def fig_field(embryo):
    z = embryo.morphogen if embryo is not None else np.zeros((GRID_SIZE,GRID_SIZE))
    fig = go.Figure(go.Heatmap(z=z, colorscale="Hot"))
    fig.update_layout(template="plotly_dark",paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
        title="میدان مورفوژن", height=320,
        xaxis=dict(visible=False), yaxis=dict(visible=False), margin=dict(l=10,r=10,t=40,b=10))
    return fig

# ═══════════════════════════════════════════════════════════════
# Callback اصلی
# ═══════════════════════════════════════════════════════════════

@app.callback(
    [Output("stats-bar","children"), Output("graph-embryo","children"),
     Output("graph-evolution","children"), Output("graph-genome-path","children"),
     Output("graph-types","children"), Output("graph-field","children"),
     Output("message","children")],
    Input("interval","n_intervals"),
    Input("btn-start","n_clicks"),
    Input("btn-reset","n_clicks"),
    State("in-generations","value"), State("in-pop","value"), State("in-speed","value")
)
def update(n, start_clicks, reset_clicks, gens, pop, speed):
    triggered = ctx.triggered_id
    speed = int(speed or 3)

    if triggered == "btn-reset":
        STATE.reset()
    elif triggered == "btn-start":
        with STATE.lock:
            if STATE.status in ("idle","growing") or (STATE.status=="done"):
                STATE.start(int(gens or 6), int(pop or 6))

    # پیشبرد نمایش
    with STATE.lock:
        status = STATE.status
        if status == "evolving" and STATE.replay_frames:
            STATE.replay_idx = (STATE.replay_idx + 1) % len(STATE.replay_frames)
            snap = STATE.replay_frames[STATE.replay_idx]
            label = f"{STATE.replay_label} | تیک {snap['tick']}"
        elif status in ("growing","done") and STATE.final_embryo is not None:
            emb = STATE.final_embryo
            for _ in range(speed): emb.step()
            if not emb.alive and status=="growing": STATE.status="done"; status="done"
            snap = emb.snapshot()
            label = f"جنین نهایی | تیک {emb.tick}"
        else:
            snap = empty_snap(); label = "در انتظار شروع..."

        history = list(STATE.history)
        initial = STATE.initial_genome
        final_embryo = STATE.final_embryo
        best = history[-1]["best"] if history else 0.0

    # کارت‌های آمار
    stats = [
        html.Div(f"وضعیت: {status}", style={**panel(C["cyan"]),"textAlign":"center","fontWeight":"bold"}),
        html.Div(f"نسل: {len(history)}", style={**panel(C["green"]),"textAlign":"center"}),
        html.Div(f"بهترین Fitness: {best:.3f}", style={**panel(C["gold"]),"textAlign":"center"}),
        html.Div(f"سلول‌ها: {len(snap['pos'])}", style={**panel(C["magenta"]),"textAlign":"center"}),
        html.Div(f"تیک: {snap['tick']}", style={**panel(C["red"]),"textAlign":"center"}),
    ]

    msg = {
        "idle":"روی «شروع تکامل» بزنید.",
        "evolving":"در حال تکامل... رشد قهرمان هر نسل بازپخش می‌شود.",
        "growing":"تکامل کامل شد. جنین نهایی در حال رشد زنده است.",
        "done":"جنین نهایی به پایان چرخه حیات رسید. می‌توانید دوباره شروع کنید."
    }.get(status,"")

    return (
        stats,
        dcc.Graph(figure=fig_embryo(snap,label), config={"displayModeBar":False}),
        dcc.Graph(figure=fig_evolution(history), config={"displayModeBar":False}),
        dcc.Graph(figure=fig_genome_path(history,initial), config={"displayModeBar":False}),
        dcc.Graph(figure=fig_types(snap), config={"displayModeBar":False}),
        dcc.Graph(figure=fig_field(final_embryo), config={"displayModeBar":False}),
        msg
    )

if __name__ == "__main__":
    print("🧬 NOUS-EMBRYO Dash Visualizer")
    print("🌐 http://127.0.0.1:8050")
    app.run(debug=False, host="127.0.0.1", port=8050)