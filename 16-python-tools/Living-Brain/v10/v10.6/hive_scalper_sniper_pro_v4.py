from __future__ import annotations
import math, random
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
from typing import Dict, List

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

ASSETS = ["BTC/USD", "ETH/USD", "S&P 500", "Gold", "EUR/USD"]
PERSIAN = {"BTC/USD": "بیت‌کوین", "ETH/USD": "اتریوم", "S&P 500": "اس‌اندپی ۵۰۰", "Gold": "طلا", "EUR/USD": "یورو/دلار"}
CYAN, PINK, GREEN, AMBER, BG, PANEL = "#00e5ff", "#ff2bd6", "#39ff88", "#ffc857", "#070b16", "#101a2d"

@dataclass
class EmotionalState:
    fear: float = 0.35
    greed: float = 0.25
    fomo: float = 0.10
    patience: float = 0.75
    confidence: float = 0.55
    stress: float = 0.20
    state: str = "calm"
    history: deque = field(default_factory=lambda: deque(maxlen=100))

    def update(self, pnl: float, volatility: float, opportunity: float, regime: str) -> None:
        self.fear = float(np.clip(0.65 * self.fear + 0.35 * (volatility * 0.55 + (pnl < 0) * 0.25), 0, 1))
        self.greed = float(np.clip(0.75 * self.greed + 0.25 * max(0, pnl) * 2, 0, 1))
        self.fomo = float(np.clip(0.70 * self.fomo + 0.30 * max(0, opportunity - 0.65), 0, 1))
        self.stress = float(np.clip(0.6 * self.stress + 0.4 * (self.fear * 0.7 + self.fomo * 0.3), 0, 1))
        self.confidence = float(np.clip(0.92 * self.confidence + 0.08 * (0.7 if pnl >= 0 else 0.25), 0.05, 0.95))
        self.patience = float(np.clip(0.9 * self.patience + 0.1 * (1 - opportunity * 0.4 - self.fomo * 0.6), 0.05, 0.98))
        score = self.greed - self.fear
        self.state = "euphoric" if score > 0.42 else "depressed" if score < -0.42 else "anxious" if self.stress > 0.58 else "calm"
        self.history.append(self.snapshot())

    def snapshot(self) -> Dict[str, float]:
        return {"fear": self.fear, "greed": self.greed, "fomo": self.fomo, "patience": self.patience, "confidence": self.confidence, "stress": self.stress, "state": self.state}

    def gate(self, raw_score: float) -> float:
        return raw_score * (1 - 0.35 * self.fomo - 0.25 * self.greed) + 0.08 * self.patience + 0.05 * self.confidence - 0.18 * self.fear

@dataclass
class MarketSnapshot:
    prices: Dict[str, float]
    returns: Dict[str, float]
    volatility: float
    regime: str
    breadth: float
    timestamp: datetime

class MarketWorld:
    def __init__(self) -> None:
        self.t = 0
        self.prices = {a: p for a, p in zip(ASSETS, [43000, 2300, 5000, 2350, 1.08])}
        self.data = self._make_history(260)

    def _make_history(self, n: int) -> pd.DataFrame:
        x = {a: [self.prices[a]] for a in ASSETS}
        for i in range(n - 1):
            regime = 0.00035 if i < n * 0.45 else (-0.0002 if i < n * 0.72 else 0.00015)
            for a in ASSETS:
                vol = 0.010 if a in ASSETS[:2] else 0.004
                x[a].append(x[a][-1] * math.exp(np.random.normal(regime, vol)))
        return pd.DataFrame(x)

    def step(self) -> MarketSnapshot:
        self.t += 1
        old = self.prices.copy()
        regime = "trend" if self.t % 55 < 25 else "range" if self.t % 55 < 45 else "stress"
        drift = {"trend": 0.0012, "range": 0.0, "stress": -0.0015}[regime]
        for a in ASSETS:
            vol = 0.014 if a in ASSETS[:2] else 0.006
            self.prices[a] *= math.exp(drift + np.random.normal(0, vol))
        rets = {a: self.prices[a] / old[a] - 1 for a in ASSETS}
        return MarketSnapshot(self.prices.copy(), rets, float(np.std(list(rets.values())) * 12), regime, float(np.mean(np.array(list(rets.values())) > 0)), datetime.now())

    def snapshot(self) -> MarketSnapshot:
        r = self.data.pct_change().tail(30).mean().to_dict()
        return MarketSnapshot(self.prices.copy(), r, float(self.data.pct_change().tail(30).std().mean() * 3), "historical", 0.5, datetime.now())

class ExperienceMemory:
    def __init__(self, capacity: int = 1000) -> None:
        self.items = deque(maxlen=capacity)
        self.wisdom = deque(maxlen=100)

    def remember(self, state, action, reward, outcome, reason) -> None:
        self.items.append({"state": state, "action": action, "reward": reward, "outcome": outcome, "reason": reason, "time": datetime.now()})

    def learn(self) -> Dict[str, float]:
        if not self.items:
            return {"win_rate": 0.5, "edge": 0.0, "lesson": "هنوز تجربه‌ای ثبت نشده است"}
        df = pd.DataFrame(self.items)
        wins = df.reward > 0
        wr = float(wins.mean())
        edge = float(df.reward.mean())
        lesson = "از ستاپ‌های موفق کلون شد: تأیید روند + صبر" if wr > 0.58 else "خطاهای اخیر: کاهش اندازه در نوسان و توقف FOMO"
        self.wisdom.append(lesson)
        return {"win_rate": wr, "edge": edge, "lesson": lesson}

    def intuition(self, asset: str, snap: MarketSnapshot) -> float:
        relevant = [x for x in self.items if x["state"].get("asset") == asset]
        if not relevant:
            return 0.0
        return float(np.clip(np.mean([x["reward"] for x in relevant]) * 0.15, -0.15, 0.15))

@dataclass
class Opinion:
    agent: str
    asset: str
    score: float
    confidence: float
    rationale: str
    risk: float

class Agent:
    name = "Agent"
    def decide(self, snap, asset, memory, emotion):
        raise NotImplementedError

class TechnicalAnalyst(Agent):
    name = "تحلیل‌گر تکنیکال"
    def decide(self, snap, asset, memory, emotion):
        r = snap.returns.get(asset, 0)
        score = np.clip(r * 18 + (snap.breadth - 0.5) * 0.5 + np.random.normal(0, 0.08), -1, 1)
        return Opinion(self.name, asset, float(score), 0.78, "مومنتوم، پرایس‌اکشن و نوسان", 0.35 + snap.volatility)

class FundamentalAnalyst(Agent):
    name = "تحلیل‌گر بنیادی"
    def decide(self, snap, asset, memory, emotion):
        bias = 0.15 if asset in ["Gold", "S&P 500"] and snap.regime != "stress" else -0.08 if snap.regime == "stress" else 0.03
        return Opinion(self.name, asset, float(np.clip(bias + np.random.normal(0, 0.09), -1, 1)), 0.65, "ماکرو، رویداد و ریسک رژیم", 0.28)

class RiskManager(Agent):
    name = "مدیر ریسک"
    def decide(self, snap, asset, memory, emotion):
        risk = np.clip(snap.volatility * 1.3 + emotion.fear * 0.5, 0, 1)
        return Opinion(self.name, asset, float(0.25 - risk), 0.92, "بودجه ریسک، افت سرمایه و اهرم", float(risk))

class PsychologyCoach(Agent):
    name = "مربی روان‌شناسی"
    def decide(self, snap, asset, memory, emotion):
        score = emotion.patience - emotion.fomo - emotion.fear * 0.5
        return Opinion(self.name, asset, float(np.clip(score, -1, 1)), 0.88, "کنترل ترس، طمع و FOMO", emotion.stress)

class PortfolioArchitect(Agent):
    name = "معمار پرتفوی"
    def decide(self, snap, asset, memory, emotion):
        diversification = 0.2 if asset in ["Gold", "EUR/USD"] else -0.05
        return Opinion(self.name, asset, float(diversification), 0.72, "همبستگی و تنوع‌سازی", 0.3)

class ExecutionSpecialist(Agent):
    name = "متخصص اجرا"
    def decide(self, snap, asset, memory, emotion):
        return Opinion(self.name, asset, float(np.clip(snap.returns.get(asset, 0) * 10 + np.random.normal(0, 0.04), -1, 1)), 0.74, "زمان‌بندی، اسلیپیج و نقدشوندگی", 0.25)

class HiveFirm:
    def __init__(self) -> None:
        self.emotion = EmotionalState()
        self.memory = ExperienceMemory()
        self.world = MarketWorld()
        self.equity = 100000.0
        self.peak = self.equity
        self.positions = {a: 0 for a in ASSETS}
        self.last = None
        self.agents = [TechnicalAnalyst(), FundamentalAnalyst(), RiskManager(), PsychologyCoach(), PortfolioArchitect(), ExecutionSpecialist()]

    def consensus(self, snap: MarketSnapshot):
        rows = []
        for asset in ASSETS:
            ops = [a.decide(snap, asset, self.memory, self.emotion) for a in self.agents]
            w = np.array([o.confidence for o in ops])
            raw = float(np.average([o.score for o in ops], weights=w))
            h = self.memory.intuition(asset, snap)
            final = self.emotion.gate(raw + h)
            risk = float(np.mean([o.risk for o in ops]))
            rows.append({"asset": asset, "signal": final, "confidence": float(np.mean(w)), "risk": risk, "votes": ops})
        return rows

    def optimize_paths(self, signals):
        candidates = []
        base = np.array([max(0, s["signal"]) for s in signals])
        base = base / base.sum() if base.sum() else np.ones(len(ASSETS)) / len(ASSETS)
        learning_edge = self.memory.learn()["edge"]
        for _ in range(180):
            w = np.random.dirichlet(1.5 + base * 8)
            ret = float(np.dot(w, [s["signal"] for s in signals]))
            risk = float(np.dot(w, [s["risk"] for s in signals]))
            concentration = float(np.sum(w * w))
            drawdown = risk * 0.55 + concentration * 0.18
            score = ret - 0.75 * risk - 0.45 * drawdown + learning_edge * 0.12
            candidates.append((score, w, ret, risk, drawdown))
        return max(candidates, key=lambda x: x[0])

    def cycle(self):
        snap = self.world.step()
        self.emotion.update(float(np.random.normal(0.002, 0.01)), snap.volatility, max(snap.breadth, 0.5), snap.regime)
        sig = self.consensus(snap)
        score, w, ret, risk, dd = self.optimize_paths(sig)
        pnl = float(ret * 0.004 * self.equity)
        self.equity *= 1 + pnl / self.equity
        self.peak = max(self.peak, self.equity)
        for a, x in zip(ASSETS, w):
            self.positions[a] = float(x)
        for s in sig:
            self.memory.remember({"asset": s["asset"], "regime": snap.regime}, "allocate", pnl / len(ASSETS), "win" if pnl >= 0 else "loss", str(s["signal"]))
        self.last = {"snap": snap, "signals": sig, "weights": w, "score": score, "ret": ret, "risk": risk, "drawdown": (self.peak - self.equity) / self.peak, "learning": self.memory.learn()}
        return self.last

firm = HiveFirm()
firm.cycle()

def card(title, value, color=CYAN):
    return html.Div([html.Div(title, className="metric-title"), html.Div(value, className="metric-value", style={"color": color})], className="metric-card")

def fig_layout(fig, title=""):
    fig.update_layout(title=title, paper_bgcolor=PANEL, plot_bgcolor=PANEL, font={"color": "#d8e7ff", "family": "Vazirmatn, Arial"}, margin={"l": 35, "r": 20, "t": 45, "b": 35}, legend={"orientation": "h"})
    fig.update_xaxes(gridcolor="#24324b")
    fig.update_yaxes(gridcolor="#24324b")
    return fig

def dashboard(data):
    if not data:
        data = firm.last
    s = data["snap"]
    learn = data["learning"]
    e = firm.emotion
    emotional = go.Figure(go.Bar(x=["ترس", "طمع", "FOMO", "صبر", "اعتمادبه‌نفس"], y=[e.fear, e.greed, e.fomo, e.patience, e.confidence], marker_color=[PINK, AMBER, PINK, GREEN, CYAN]))
    fig_layout(emotional, "لایهٔ هوش هیجانی")
    votes = go.Figure(go.Bar(x=[PERSIAN[x["asset"]] for x in data["signals"]], y=[x["signal"] for x in data["signals"]], marker_color=[GREEN if x["signal"] > 0 else PINK for x in data["signals"]]))
    fig_layout(votes, "اجماع تیمی و سیگنال نهایی")
    path = go.Figure()
    w = data["weights"]
    path.add_trace(go.Bar(x=[PERSIAN[a] for a in ASSETS], y=w, marker_color=CYAN, name="وزن تخصیص"))
    fig_layout(path, "مسیر منتخب پرتفوی - بهینه‌سازی ریسک‌محور")
    hist = list(e.history)
    lf = go.Figure()
    if hist:
        for k, c in [("fear", PINK), ("greed", AMBER), ("confidence", CYAN), ("patience", GREEN)]:
            lf.add_trace(go.Scatter(y=[z[k] for z in hist], mode="lines", name=k, line={"color": c}))
    fig_layout(lf, "تکامل هیجانات")
    return html.Div([
        html.Div([
            card("ارزش پرتفوی", f"${firm.equity:,.0f}", GREEN),
            card("حالت آگاه", e.state, AMBER),
            card("رژیم بازار", s.regime, CYAN),
            card("نرخ موفقیت یادگیری", f'{learn["win_rate"]:.0%}', PINK),
            card("افت سرمایه", f'{data["drawdown"]:.2%}', PINK)
        ], className="metrics"),
        html.Div([dcc.Graph(figure=emotional), dcc.Graph(figure=votes)], className="grid2"),
        html.Div([dcc.Graph(figure=path), dcc.Graph(figure=lf)], className="grid2"),
        html.Div([
            html.H3("دفتر بینش و تجربه", className="section-title"),
            html.P(learn["lesson"]),
            html.P(f'امتیاز مسیر: {data["score"]:.3f} | ریسک: {data["risk"]:.3f} | صبر: {e.patience:.0%}'),
            html.Div([html.Span(f"● {a.name}  ", className="agent-pill") for a in firm.agents])
        ], className="insight")
    ])

app = Dash(__name__)
app.title = "HIVE SCALPER-SNIPER PRO v4"
app.layout = html.Div([
    html.Div([
        html.H1("HIVE SCALPER-SNIPER PRO v4", className="neon"),
        html.Div("The Conscious Trading Entity | موسسهٔ خودآگاه معامله‌گری", className="subtitle"),
        html.Button("اجرای چرخهٔ جدید", id="run", n_clicks=0, className="run-btn"),
        dcc.Interval(id="clock", interval=12000, n_intervals=0)
    ], className="header"),
    html.Div(id="dashboard", children=dashboard(firm.last))
], className="app")

@app.callback(Output("dashboard", "children"), Input("run", "n_clicks"), Input("clock", "n_intervals"))
def update(n, clock):
    return dashboard(firm.cycle())

app.index_string = """<!DOCTYPE html><html lang="fa" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>HIVE</title><style>
@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;800&display=swap');
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 80% 0%,#152444 0,#070b16 45%);color:#d8e7ff;font-family:Vazirmatn,Arial}.app{max-width:1500px;margin:auto;padding:28px}.header{position:relative;padding:25px 28px;margin-bottom:22px;background:rgba(16,26,45,.78);border:1px solid #20416a;border-radius:20px;box-shadow:0 0 30px #00e5ff18}.neon{margin:0;color:#00e5ff;text-shadow:0 0 14px #00e5ff;font-size:clamp(25px,4vw,48px);direction:ltr;text-align:right}.subtitle{color:#aebbd0;margin-top:5px}.run-btn{position:absolute;left:25px;top:32px;background:#00e5ff;color:#06101c;border:0;border-radius:10px;padding:12px 20px;font:inherit;font-weight:800;cursor:pointer;box-shadow:0 0 18px #00e5ff88}.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:18px}.metric-card,.insight{background:rgba(16,26,45,.8);border:1px solid #203b5d;border-radius:16px;padding:18px;box-shadow:inset 0 0 22px #00e5ff08}.metric-title{color:#96a9c4;font-size:13px}.metric-value{font-size:24px;font-weight:800;margin-top:8px}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}.grid2 .dash-graph{border-radius:16px;overflow:hidden}.section-title{color:#00e5ff}.agent-pill{display:inline-block;background:#172b48;border:1px solid #27547c;border-radius:20px;padding:7px 12px;margin:4px;font-size:12px;color:#8eeaff}@media(max-width:800px){.metrics,.grid2{grid-template-columns:1fr}.run-btn{position:static;margin-top:15px}.header{display:flex;flex-direction:column}}</style></head><body>{app_entry}<footer>{config}{scripts}{renderer}</footer></body></html>"""

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)