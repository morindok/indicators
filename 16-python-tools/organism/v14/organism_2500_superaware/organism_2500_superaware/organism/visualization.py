"""
organism.visualization

پنل‌های Dash و رسم نمودارهای رصدخانه.
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict

try:
    from dash import Dash, dcc, html, Input, Output
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    DASH_AVAILABLE = True
except Exception:  # pragma: no cover
    Dash = dcc = html = Input = Output = None
    go = None
    make_subplots = None
    DASH_AVAILABLE = False

from .utils import APP_NAME, clamp, fa_join, stable_hash

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .affect import EmotionSystem, NeedsSystem
    from .organism_core import Organism2500

COSMIC_COLORS = [
    "#7aa2ff",
    "#b48eff",
    "#63e6be",
    "#ffd166",
    "#ff6e9c",
    "#8be9fd",
    "#c3a6ff",
]

def _dark_layout(title: str = "", **kwargs) -> Any:
    if go is None:
        return {}
    return go.Layout(
        title=title,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#dfe8ff"},
        margin=dict(l=45, r=22, t=58, b=42),
        colorway=COSMIC_COLORS,
        **kwargs,
    )


def _empty_figure(message: str = "داده‌ای وجود ندارد"):
    if go is None:
        return {}
    return go.Figure(layout=_dark_layout(message))


def make_timeline_figure(organism: Organism2500):
    try:
        logs = list(organism.state_log)[-180:]
        if not logs:
            return _empty_figure("هنوز روندی ثبت نشده است.")

        x = [item["tick"] for item in logs]
        energy = [item["body"]["energy"] * 100 for item in logs]
        vitality = [item["body"]["vitality"] * 100 for item in logs]
        coherence = [item["brain"]["coherence"] * 100 for item in logs]
        concept = [item.get("concept_coherence", 0.3) * 100 for item in logs]
        meaning = [item["needs"].get("meaning", 0.3) * 100 for item in logs]
        awareness = [item.get("awareness_level", 0.5) * 100 for item in logs]
        unity = [item.get("unity_score", 0.4) * 100 for item in logs]

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=energy, name="انرژی", line=dict(width=2)))
        fig.add_trace(go.Scatter(x=x, y=vitality, name="سرزندگی", line=dict(width=2)))
        fig.add_trace(go.Scatter(x=x, y=coherence, name="انسجام مغز", line=dict(width=2)))
        fig.add_trace(go.Scatter(x=x, y=concept, name="انسجام مفهومی", line=dict(width=2)))
        fig.add_trace(go.Scatter(x=x, y=meaning, name="معنا", line=dict(width=2)))
        fig.add_trace(go.Scatter(x=x, y=awareness, name="آگاهی", line=dict(width=2, dash="dot")))
        fig.add_trace(go.Scatter(x=x, y=unity, name="وحدت", line=dict(width=2, dash="dashdot")))

        fig.update_layout(_dark_layout("روند کیهانی: انرژی، سرزندگی، انسجام، مفهوم، معنا، آگاهی و وحدت"))
        fig.update_yaxes(range=[0, 105])
        return fig
    except Exception:
        return _empty_figure("خطا در رسم تایم‌لاین")


def make_body_gauges(organism: Organism2500):
    try:
        body = organism.body
        if make_subplots is None:
            return _empty_figure("make_subplots در دسترس نیست.")

        specs = [[{"type": "indicator"} for _ in range(3)] for _ in range(2)]
        fig = make_subplots(
            rows=2,
            cols=3,
            specs=specs,
            subplot_titles=("انرژی", "یکپارچگی", "سرزندگی", "آنتروپی", "دما", "ضربان قلب"),
        )

        fig.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=body.energy * 100,
                gauge={"axis": {"range": [0, 100]}, "bar": {"color": "#7aa2ff"}},
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=body.integrity * 100,
                gauge={"axis": {"range": [0, 100]}, "bar": {"color": "#63e6be"}},
            ),
            row=1,
            col=2,
        )
        fig.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=body.vitality * 100,
                gauge={"axis": {"range": [0, 100]}, "bar": {"color": "#b48eff"}},
            ),
            row=1,
            col=3,
        )
        fig.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=body.entropy * 100,
                gauge={"axis": {"range": [0, 100]}, "bar": {"color": "#ffd166"}},
            ),
            row=2,
            col=1,
        )
        fig.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=body.temperature,
                gauge={"axis": {"range": [35, 42]}, "bar": {"color": "#ff6e9c"}},
            ),
            row=2,
            col=2,
        )
        fig.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=body.heart.bpm,
                gauge={"axis": {"range": [30, 200]}, "bar": {"color": "#8be9fd"}},
            ),
            row=2,
            col=3,
        )

        fig.update_layout(
            height=430,
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            font={"color": "#dfe8ff"},
        )
        return fig
    except Exception:
        return _empty_figure("خطا در گیج‌های بدن")


def make_body_bars(organism: Organism2500):
    try:
        organs = organism.body.organs
        fig = go.Figure(
            data=[
                go.Bar(
                    x=list(organs.keys()),
                    y=list(organs.values()),
                    marker_color="#63e6be",
                )
            ],
            layout=_dark_layout("سلامت ارگان‌ها"),
        )
        fig.update_yaxes(range=[0, 1.05])
        return fig
    except Exception:
        return _empty_figure("خطا در نمودار بدن")


def make_emotion_figure(snap: Dict[str, Any]):
    try:
        names = [EmotionSystem.FA_MAP.get(k, k) for k in snap["emotions"].keys()]
        values = list(snap["emotions"].values())
        fig = go.Figure(
            data=[go.Bar(x=names, y=values, marker_color="#7aa2ff")],
            layout=_dark_layout("وضعیت هیجان‌ها"),
        )
        fig.update_yaxes(range=[0, 1])
        return fig
    except Exception:
        return _empty_figure("خطا در هیجان‌ها")


def make_needs_figure(snap: Dict[str, Any]):
    try:
        names = [NeedsSystem.FA_MAP.get(k, k) for k in snap["needs"].keys()]
        values = list(snap["needs"].values())
        fig = go.Figure(
            data=[go.Bar(x=names, y=values, marker_color="#ffd166")],
            layout=_dark_layout("وضعیت نیازها"),
        )
        fig.update_yaxes(range=[0, 1])
        return fig
    except Exception:
        return _empty_figure("خطا در نیازها")


def make_heart_figure(organism: Organism2500):
    try:
        heart_y = [h.get("bpm", 60.0) for h in organism.body.heart.history]
        if not heart_y:
            heart_y = [60.0]
        fig = go.Figure(
            data=[
                go.Scatter(
                    y=heart_y,
                    mode="lines+markers",
                    line={"color": "#ff6e9c", "width": 2},
                    marker={"size": 4, "color": "#ffd166"},
                )
            ],
            layout=_dark_layout("ضربان قلب فیبوناچی"),
        )
        return fig
    except Exception:
        return _empty_figure("خطا در قلب")


def make_brain_figure(organism: Organism2500):
    try:
        activities = organism.brain.activities
        fig = go.Figure(
            data=[
                go.Bar(
                    x=list(activities.keys()),
                    y=list(activities.values()),
                    marker_color="#b48eff",
                )
            ],
            layout=_dark_layout("فعالیت مناطق مغز"),
        )
        fig.update_yaxes(range=[0, 1])
        return fig
    except Exception:
        return _empty_figure("خطا در مغز")


def make_genome_radar(snap: Dict[str, Any]):
    try:
        traits = snap["genome"]["traits"]
        labels = list(traits.keys())
        values = list(traits.values())
        fig = go.Figure(
            data=[
                go.Scatterpolar(
                    r=values,
                    theta=labels,
                    fill="toself",
                    name="ژنوم",
                    line={"color": "#8be9fd"},
                )
            ],
            layout=_dark_layout("پروفایل ژنتیکی"),
        )
        fig.update_layout(polar=dict(radialaxis=dict(range=[0, 1])))
        return fig
    except Exception:
        return _empty_figure("خطا در ژنوم")


def make_concept_network(organism: Organism2500):
    try:
        graph = organism.concept_graph
        central = graph.central_concepts(18)
        if not central:
            return _empty_figure("هنوز گراف مفهومی شکل نگرفته است.")

        pos = {}
        n = len(central)
        for i, label in enumerate(central):
            angle = 2 * math.pi * i / max(1, n)
            pos[label] = (math.cos(angle), math.sin(angle))

        edge_x = []
        edge_y = []
        for (a, b, _rel), _w in graph.edges.items():
            if a in pos and b in pos:
                x0, y0 = pos[a]
                x1, y1 = pos[b]
                edge_x.extend([x0, x1, None])
                edge_y.extend([y0, y1, None])

        node_x = [pos[label][0] for label in central]
        node_y = [pos[label][1] for label in central]

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=edge_x,
                y=edge_y,
                mode="lines",
                line=dict(width=0.9, color="rgba(122,162,255,0.35)"),
                hoverinfo="none",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=node_x,
                y=node_y,
                mode="markers+text",
                text=central,
                textposition="top center",
                marker=dict(size=13, color="#7aa2ff", line=dict(width=1, color="#dfe8ff")),
                hovertext=central,
            )
        )
        fig.update_layout(
            title="شبکه‌ی مفاهیم زنده",
            showlegend=False,
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"color": "#dfe8ff"},
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        )
        return fig
    except Exception:
        return _empty_figure("خطا در گراف مفهومی")


def make_awareness_panel(organism: Organism2500):
    rows = list(organism.awareness.recent(14))[::-1]
    if not rows:
        return html.Div("هنوز رویداد آگاهی ثبت نشده است.")

    children = [
        html.Div(
            [
                html.B("سطح آگاهی: "),
                f"{organism.awareness.awareness_level:.2f}",
                html.Span(" | "),
                html.B("تعداد بیان‌های آگاهانه: "),
                str(organism.awareness.counter),
            ],
            style={"marginBottom": "10px"},
        )
    ]

    for item in rows:
        children.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.B(f"امتیاز آگاهی: {item['score']:.2f}"),
                            html.Span(f" — {item['emotion']}"),
                        ],
                        style={"marginBottom": "3px"},
                    ),
                    html.Div(item["text"], style={"opacity": 0.92}),
                    html.Div(item["meta"], style={"opacity": 0.55, "fontSize": "0.92em"}),
                ],
                style={
                    "padding": "8px",
                    "backgroundColor": "rgba(13,20,45,0.82)",
                    "border": "1px solid rgba(122,162,255,0.18)",
                    "borderRadius": "8px",
                    "marginBottom": "7px",
                },
            )
        )

    return html.Div(children)


def make_unconscious_panel(organism: Organism2500):
    uc = organism.unconscious
    events = list(uc.recent_events(12))[::-1]

    axes_rows = []
    sorted_axes = sorted(uc.latent.items(), key=lambda kv: kv[1], reverse=True)
    for axis, value in sorted_axes:
        axes_rows.append(
            html.Div(
                [
                    html.Span(uc.AXES_FA.get(axis, axis), style={"width": "90px", "display": "inline-block"}),
                    html.Div(
                        style={
                            "display": "inline-block",
                            "height": "10px",
                            "width": f"{int(clamp(value) * 220)}px",
                            "backgroundColor": "#7aa2ff",
                            "borderRadius": "5px",
                            "marginRight": "8px",
                        }
                    ),
                    html.Span(f"{value:.2f}", style={"opacity": 0.75}),
                ],
                style={"marginBottom": "5px"},
            )
        )

    children = [
        html.Div(
            [
                html.B("وحدت معنایی: "),
                f"{uc.unity_score:.2f}",
                html.Span(" | "),
                html.B("یکپارچه‌سازی‌ها: "),
                str(uc.integration_count),
                html.Span(" | "),
                html.B("جذب‌های ناخودآگاه: "),
                str(uc.absorb_count),
            ],
            style={"marginBottom": "12px"},
        ),
        html.Div(axes_rows, style={"marginBottom": "14px"}),
    ]

    if not events:
        children.append(html.Div("هنوز رویداد ناخودآگاه ثبت نشده است."))
    else:
        for ev in events:
            children.append(
                html.Div(
                    [
                        html.Div(
                            [
                                html.B(f"نوع: {ev['kind']}"),
                                html.Span(f" — وحدت: {float(ev['unity']):.2f}"),
                            ],
                            style={"marginBottom": "3px"},
                        ),
                        html.Div(ev["content"], style={"opacity": 0.92}),
                    ],
                    style={
                        "padding": "8px",
                        "backgroundColor": "rgba(16,12,35,0.82)",
                        "border": "1px solid rgba(180,142,255,0.18)",
                        "borderRadius": "8px",
                        "marginBottom": "7px",
                    },
                )
            )

    return html.Div(children)




def make_wormhole_panel(organism: Organism2500):
    wf = getattr(organism, "wormhole_field", None)
    if not wf:
        return html.Div("\u0645\u06cc\u062f\u0627\u0646 \u0645\u06cc\u06a9\u0631\u0648\u06a9\u0631\u0645\u0686\u0627\u0644\u0647 \u0641\u0639\u0627\u0644 \u0646\u06cc\u0633\u062a.")
    report = wf.report()
    experiences = list(wf.parallel_experiences)[-8:][::-1]
    children = [
        html.Div([
            html.B("\u0645\u06cc\u06a9\u0631\u0648\u06a9\u0631\u0645\u0686\u0627\u0644\u0647\u200c\u0647\u0627\u06cc \u0628\u0627\u0632: "), str(report["open_count"]),
            html.Span(" | "),
            html.B("\u062c\u0647\u0627\u0646\u200c\u0647\u0627\u06cc \u0645\u0644\u0627\u0642\u0627\u062a\u200c\u0634\u062f\u0647: "), str(report["worlds_visited"]),
            html.Span(" | "),
            html.B("\u0634\u062f\u062a: "), f"{report['intensity']:.2f}",
            html.Span(" | "),
            html.B("\u067e\u0627\u06cc\u062f\u0627\u0631\u06cc: "), f"{report['stability']:.2f}",
        ], style={"marginBottom": "10px"}),
        html.Div([
            html.B("\u062a\u0642\u0648\u06cc\u062a \u062a\u062e\u06cc\u0644: "), f"{report['imagination_boost']:.2f}",
            html.Span(" | "),
            html.B("\u062a\u0642\u0648\u06cc\u062a \u0628\u06cc\u0646\u0634: "), f"{report['insight_boost']:.2f}",
        ], style={"marginBottom": "12px"}),
    ]
    if experiences:
        children.append(html.B("\u062a\u062c\u0631\u0628\u0647\u200c\u0647\u0627\u06cc \u0645\u0648\u0627\u0632\u06cc \u0627\u062e\u06cc\u0631:"))
        for exp in experiences:
            children.append(html.Div(
                f"\u062c\u0647\u0627\u0646\u200c\u0647\u0627: {exp['worlds']} | \u0634\u062f\u062a: {exp['intensity']:.2f} | \u062a\u062e\u06cc\u0644: {exp['imagination']:.2f}",
                style={
                    "padding": "5px 8px",
                    "backgroundColor": "rgba(20,15,50,0.8)",
                    "border": "1px solid rgba(138,100,255,0.2)",
                    "borderRadius": "6px",
                    "marginBottom": "4px",
                    "fontSize": "0.9em",
                },
            ))
    return html.Div(children)


def make_ecosystem_panel(organism: Organism2500):
    eco = getattr(organism, "neuron_ecosystem", None)
    if not eco:
        return html.Div("\u0627\u06a9\u0648\u0633\u06cc\u0633\u062a\u0645 \u0646\u0648\u0631\u0648\u0646\u06cc \u0641\u0639\u0627\u0644 \u0646\u06cc\u0633\u062a.")
    report = eco.report()
    children = [
        html.Div([
            html.B("\u062c\u0645\u0639\u06cc\u062a \u0646\u0648\u0631\u0648\u0646\u06cc: "), str(report["population"]),
            html.Span(" | "),
            html.B("\u062a\u0646\u0648\u0639: "), f"{report['diversity']:.2f}",
            html.Span(" | "),
            html.B("\u0647\u0648\u0645\u0626\u0648\u0633\u062a\u0627\u0632\u06cc: "), f"{report['homeostasis']:.2f}",
            html.Span(" | "),
            html.B("\u0641\u0634\u0627\u0631 \u062a\u0639\u0627\u062f\u0644: "), f"{report['balance_pressure']:.2f}",
        ], style={"marginBottom": "12px"}),
        html.B("\u0646\u0642\u0634\u200c\u0647\u0627:"),
    ]
    for role_name, count in report["roles"].items():
        bar_width = int(clamp(count / max(1, report["population"]) * 200))
        children.append(html.Div([
            html.Span(role_name, style={"width": "80px", "display": "inline-block"}),
            html.Div(style={
                "display": "inline-block",
                "height": "10px",
                "width": f"{bar_width}px",
                "backgroundColor": "#63e6be",
                "borderRadius": "5px",
                "marginRight": "8px",
            }),
            html.Span(str(count), style={"opacity": 0.75}),
        ], style={"marginBottom": "4px"}))
    return html.Div(children)


# ---------------------------------------------------------------------------
# فراآگاهی: GWT + IIT + HOT + Predictive Processing + Homeostasis
# ---------------------------------------------------------------------------

def make_superawareness_panel(organism: Organism2500):
    sa = organism.super_awareness
    snap = sa.snapshot()
    last = snap.get("last_report", {})

    def stat_row(label: str, value: str):
        return html.Div(
            [html.B(f"{label}: "), value],
            style={"marginBottom": "4px"},
        )

    children = [
        html.Div(
            [
                stat_row("شاخص فراآگاهی", f"{snap.get('consciousness_index', 0.0):.3f}"),
                stat_row("Φ-پروکسی (IIT)", f"{last.get('phi_proxy', 0.0):.3f}"),
                stat_row("اطمینان مرتبه‌بالاتر (HOT)", f"{last.get('meta_confidence', 0.0):.2f}"),
                stat_row("انسجام پیش‌بینانه", f"{organism.super_awareness.predictive.coherence():.2f}"),
                stat_row("تعادل هوموستاتیک", f"{last.get('homeostatic_balance', 0.0):.2f}"),
                stat_row("سائق غالب بدنی", str(last.get("dominant_drive", "—"))),
            ],
            style={
                "padding": "10px",
                "backgroundColor": "rgba(13,20,45,0.82)",
                "border": "1px solid rgba(122,162,255,0.18)",
                "borderRadius": "8px",
                "marginBottom": "10px",
            },
        ),
        html.Div(
            [
                html.B("محتوای پخش‌شده در فضای‌کاری سراسری (GWT): "),
                str(last.get("workspace_winner") or "—"),
            ],
            style={"marginBottom": "8px", "opacity": 0.92},
        ),
        html.Div(
            [
                html.B("اندیشه‌ی مرتبه‌بالاتر (HOT): "),
                str(last.get("meta_thought") or "—"),
            ],
            style={"marginBottom": "8px", "opacity": 0.92},
        ),
        html.Div(
            [
                html.B("کانون توجه: "),
                "، ".join(last.get("attention_focus", []) or []) or "—",
            ],
            style={"marginBottom": "8px", "opacity": 0.8},
        ),
    ]

    channel = last.get("top_surprise_channel")
    if channel:
        children.append(
            html.Div(
                f"بیشترین شگفتی پیش‌بینانه در کانال «{channel}» "
                f"(شدت {last.get('predictive_surprise', 0.0):.3f})؛ "
                f"همین شگفتی می‌تواند بذر یک پرسش ژرف ناخودآگاه باشد.",
                style={"opacity": 0.65, "fontSize": "0.92em"},
            )
        )

    return html.Div(children)


def make_phi_trend_figure(organism: Organism2500):
    trend = organism.super_awareness.integration.snapshot().get("phi_trend", [])
    if not trend:
        return _empty_figure("هنوز داده‌ی کافی برای روند Φ وجود ندارد.")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            y=[v * 100 for v in trend],
            mode="lines",
            name="Φ-پروکسی",
            line=dict(width=2, color="#c3a6ff"),
            fill="tozeroy",
        )
    )
    fig.update_layout(_dark_layout("روند Φ-پروکسی (اطلاعات یکپارچه، الهام از IIT)"))
    fig.update_yaxes(range=[0, 105])
    return fig


def make_ideas_panel(organism: Organism2500):
    ideas = organism.idea_synthesizer.best_ideas(6)
    if not ideas:
        return html.Div("هنوز هیچ ایده‌ی انقلابی سنتز نشده است.")

    children = []
    for idea in ideas:
        a, b = idea["concepts"]
        children.append(
            html.Div(
                [
                    html.Div(
                        html.B(f"امتیاز ایده: {idea['score']:.2f}  (تازگی {idea['novelty']:.2f} × پیوستگی {idea['coherence']:.2f})"),
                        style={"marginBottom": "3px"},
                    ),
                    html.Div(idea["text"], style={"opacity": 0.92}),
                    html.Div(f"مفاهیم پیوندخورده: {a} ↔ {b}", style={"opacity": 0.55, "fontSize": "0.88em"}),
                ],
                style={
                    "padding": "8px",
                    "backgroundColor": "rgba(13,20,45,0.82)",
                    "border": "1px solid rgba(179,142,255,0.22)",
                    "borderRadius": "8px",
                    "marginBottom": "7px",
                },
            )
        )
    return html.Div(children)


def make_deep_inquiry_panel(organism: Organism2500):
    records = list(organism.deep_inquiry.history)[-8:][::-1]
    if not records:
        return html.Div("هنوز پرسش ژرف ناخودآگاهی مطرح نشده است.")

    children = []
    for r in records:
        children.append(
            html.Div(
                [
                    html.Div(
                        html.B(f"[عمق {r['depth']}] {r['question']}"),
                        style={"marginBottom": "3px"},
                    ),
                    html.Div(r["answer"][:280], style={"opacity": 0.9}),
                    html.Div(f"منبع: {r['source']}", style={"opacity": 0.55, "fontSize": "0.88em"}),
                ],
                style={
                    "padding": "8px",
                    "backgroundColor": "rgba(13,20,45,0.82)",
                    "border": "1px solid rgba(99,230,190,0.2)",
                    "borderRadius": "8px",
                    "marginBottom": "7px",
                },
            )
        )
    return html.Div(children)


# ---------------------------------------------------------------------------
# Dash cosmic observatory
# ---------------------------------------------------------------------------

def build_dash(organism: Organism2500):
    if not DASH_AVAILABLE:
        raise RuntimeError("Dash is not installed. Run: pip install dash")

    app = Dash(__name__, title=APP_NAME)

    cosmic_bg = (
        "radial-gradient(circle at 18% 22%, rgba(64,48,140,0.32), transparent 36%), "
        "radial-gradient(circle at 82% 12%, rgba(34,88,160,0.28), transparent 32%), "
        "radial-gradient(circle at 70% 78%, rgba(130,48,110,0.18), transparent 28%), "
        "radial-gradient(circle at 30% 80%, rgba(25,120,120,0.12), transparent 24%), "
        "#03040a"
    )

    panel_style = {
        "border": "1px solid rgba(122,162,255,0.24)",
        "borderRadius": "14px",
        "padding": "15px",
        "backgroundColor": "rgba(8,12,30,0.72)",
        "boxShadow": "0 0 22px rgba(84,110,255,0.10)",
        "marginBottom": "14px",
        "backdropFilter": "blur(2px)",
    }

    header_style = {
        "textAlign": "center",
        "color": "#e9efff",
        "textShadow": "0 0 16px rgba(120,150,255,0.35)",
        "marginBottom": "4px",
    }

    subheader_style = {
        "textAlign": "center",
        "opacity": 0.72,
        "color": "#c7d4ff",
        "marginBottom": "18px",
    }

    app.layout = html.Div(
        style={
            "direction": "rtl",
            "fontFamily": "Tahoma, Vazirmatn, sans-serif",
            "backgroundColor": "#03040a",
            "backgroundImage": cosmic_bg,
            "backgroundAttachment": "fixed",
            "color": "#e8f0ff",
            "minHeight": "100vh",
            "padding": "22px",
        },
        children=[
            html.H1("ارگانیسم دیجیتال زنده — سال ۲۵۰۰", style=header_style),
            html.Div(
                "رصد خاموش: ارگانیسم از وجود ناظر آگاه نیست، اما نسبت به هر جمله‌ی خود آگاه است و ناخودآگاه فعال دارد.",
                style=subheader_style,
            ),
            dcc.Interval(id="organ-interval", interval=1300, n_intervals=0),
            dcc.Tabs(
                style={"border": "none"},
                children=[
                    dcc.Tab(
                        label="کیهان‌نما",
                        children=[
                            html.Div(id="overview-cards", style=panel_style),
                            dcc.Graph(id="timeline-graph", config={"displayModeBar": False}),
                            dcc.Graph(id="body-gauges", config={"displayModeBar": False}),
                        ],
                    ),
                    dcc.Tab(
                        label="اندیشه‌های آگاهانه",
                        children=[html.Div(id="thoughts-panel", style=panel_style)],
                    ),
                    dcc.Tab(
                        label="هیجان و نیاز",
                        children=[
                            dcc.Graph(id="emotion-graph", config={"displayModeBar": False}),
                            dcc.Graph(id="needs-graph", config={"displayModeBar": False}),
                        ],
                    ),
                    dcc.Tab(
                        label="بدن و قلب",
                        children=[
                            dcc.Graph(id="heart-graph", config={"displayModeBar": False}),
                            dcc.Graph(id="body-bars", config={"displayModeBar": False}),
                        ],
                    ),
                    dcc.Tab(
                        label="مغز و ماتریس",
                        children=[
                            dcc.Graph(id="brain-graph", config={"displayModeBar": False}),
                            html.Div(id="matrix-panel", style=panel_style),
                        ],
                    ),
                    dcc.Tab(
                        label="مفاهیم و یکپارچگی",
                        children=[
                            dcc.Graph(id="concept-network", config={"displayModeBar": False}),
                            html.Div(id="concept-panel", style=panel_style),
                            html.Div(id="integrity-panel", style=panel_style),
                        ],
                    ),
                    dcc.Tab(
                        label="آگاهی گفتار",
                        children=[html.Div(id="awareness-panel", style=panel_style)],
                    ),
                    dcc.Tab(
                        label="ناخودآگاه",
                        children=[html.Div(id="unconscious-panel", style=panel_style)],
                    ),
                    dcc.Tab(
                        label="کرمچاله و اکوسیستم",
                        children=[
                            html.Div(id="wormhole-panel", style=panel_style),
                            html.Div(id="ecosystem-panel", style=panel_style),
                        ]),
                    dcc.Tab(
                        label="حافظه و کنش‌ها",
                        children=[
                            html.Div(id="memory-panel", style=panel_style),
                            html.Div(id="action-panel", style=panel_style),
                        ],
                    ),
                    dcc.Tab(
                        label="فراآگاهی",
                        children=[
                            html.Div(id="superawareness-panel", style=panel_style),
                            dcc.Graph(id="phi-trend-graph", config={"displayModeBar": False}),
                            html.Div(id="ideas-panel", style=panel_style),
                            html.Div(id="deep-inquiry-panel", style=panel_style),
                        ],
                    ),
                    dcc.Tab(
                        label="ژنوم و تکامل",
                        children=[
                            dcc.Graph(id="genome-radar", config={"displayModeBar": False}),
                            html.Div(id="genome-panel", style=panel_style),
                        ],
                    ),
                ],
            ),
        ],
    )

    @app.callback(
        [
            Output("overview-cards", "children"),
            Output("timeline-graph", "figure"),
            Output("body-gauges", "figure"),
            Output("thoughts-panel", "children"),
            Output("emotion-graph", "figure"),
            Output("needs-graph", "figure"),
            Output("heart-graph", "figure"),
            Output("body-bars", "figure"),
            Output("brain-graph", "figure"),
            Output("matrix-panel", "children"),
            Output("concept-network", "figure"),
            Output("concept-panel", "children"),
            Output("integrity-panel", "children"),
            Output("awareness-panel", "children"),
            Output("unconscious-panel", "children"),
            Output("wormhole-panel", "children"),
            Output("ecosystem-panel", "children"),
            Output("memory-panel", "children"),
            Output("action-panel", "children"),
            Output("genome-radar", "figure"),
            Output("genome-panel", "children"),
            Output("superawareness-panel", "children"),
            Output("phi-trend-graph", "figure"),
            Output("ideas-panel", "children"),
            Output("deep-inquiry-panel", "children"),
        ],
        [Input("organ-interval", "n_intervals")],
    )
    def refresh(n):
        snap = organism.snapshot()

        overview_cards = html.Div(
            [
                html.B("نام: "), snap["identity"]["name"],
                html.Span(" | "), html.B("سن: "), f"{snap['age_seconds']:.0f}s",
                html.Span(" | "), html.B("تیک: "), str(snap["tick"]),
                html.Span(" | "), html.B("قلب: "), f"{snap['heart']['bpm']:.1f} BPM",
                html.Span(" | "), html.B("هیجان غالب: "), snap["dominant_emotion"],
                html.Br(),
                html.B("کنش: "), snap["action"],
                html.Span(" | "), html.B("دانش: "), str(snap["knowledge_count"]),
                html.Span(" | "), html.B("واژگان: "), str(snap["lexicon_count"]),
                html.Span(" | "), html.B("مفاهیم: "), str(snap["concept_count"]),
                html.Span(" | "), html.B("پیوندها: "), str(snap["concept_edge_count"]),
                html.Br(),
                html.B("انسجام مفهومی: "), f"{snap['concept_coherence']:.2f}",
                html.Span(" | "), html.B("آگاهی: "), f"{snap['awareness_level']:.2f}",
                html.Span(" | "), html.B("تکلم: "), f"{snap['eloquence']:.2f}",
                html.Span(" | "), html.B("وحدت: "), f"{snap['unity_score']:.2f}",
                html.Span(" | "), html.B("نسل ژنوم: "), str(snap["genome"]["generation"]),
                html.Br(),
                html.B("روایت هویت: "), snap["identity"]["narrative"],
            ],
            style={"lineHeight": "2"},
        )

        timeline_figure = make_timeline_figure(organism)
        body_gauges = make_body_gauges(organism)

        thoughts = list(organism.thought_stream.history)[-20:][::-1]
        thoughts_panel = html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.B(f"آگاهی: {h.get('awareness', 0):.2f}"),
                                html.Span(f" — {h.get('emotion', '')}"),
                            ],
                            style={"marginBottom": "3px"},
                        ),
                        html.Div(h["text"]),
                    ],
                    style={
                        "margin": "7px 0",
                        "padding": "8px 10px",
                        "borderRight": "3px solid #7aa2ff",
                        "backgroundColor": "rgba(13,20,45,0.82)",
                        "borderRadius": "8px",
                    },
                )
                for h in thoughts
            ]
        )

        emotion_figure = make_emotion_figure(snap)
        needs_figure = make_needs_figure(snap)
        heart_figure = make_heart_figure(organism)
        body_bars = make_body_bars(organism)
        brain_figure = make_brain_figure(organism)

        matrix_panel = html.Pre(
            json.dumps(
                {
                    "virtual_neurons": snap["matrix"]["virtual_neurons"],
                    "active_samples": snap["matrix"]["active_samples"],
                    "activity": snap["matrix"]["activity"],
                    "coherence": snap["matrix"]["coherence"],
                    "state_bits_hash": format(
                        stable_hash(str(organism.matrix.state_bits)), "016x"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            ),
            style={
                "whiteSpace": "pre-wrap",
                "backgroundColor": "rgba(13,20,45,0.82)",
                "padding": "12px",
                "borderRadius": "8px",
            },
        )

        concept_network = make_concept_network(organism)

        central = organism.concept_graph.central_concepts(20)
        concept_statement = organism.concept_graph.generate_statement()
        concept_panel = html.Div(
            [
                html.B("گزارش گراف مفهومی: "),
                html.P(concept_statement, style={"marginTop": "6px"}),
                html.B("مفاهیم مرکزی: "),
                html.P(fa_join(central) if central else "هنوز مفهوم کافی شکل نگرفته است."),
                html.Br(),
                html.B("آمار: "),
                f"{snap['concept_count']} مفهوم، {snap['concept_edge_count']} پیوند",
            ],
            style={"lineHeight": "2"},
        )

        integrity_stats = snap.get("integrity", {})
        integrity_events = list(organism.guard.history)[-10:][::-1]
        integrity_children = [
            html.B("نگهبان یکپارچگی معنایی"),
            html.Br(),
            f"بررسی‌شده: {integrity_stats.get('checked', 0)} | "
            f"سالم: {integrity_stats.get('passed', 0)} | "
            f"بازنویسی: {integrity_stats.get('rewritten', 0)} | "
            f"مسدود: {integrity_stats.get('blocked', 0)}",
            html.Br(),
            f"تناقض‌ها: {integrity_stats.get('contradictions', 0)} | "
            f"بی‌ربط: {integrity_stats.get('unrelated', 0)} | "
            f"تکرار: {integrity_stats.get('repetition', 0)}",
            html.Hr(),
        ]
        for ev in integrity_events:
            integrity_children.append(
                html.Div(
                    [
                        html.B(f"امتیاز: {ev['score']:.2f} "),
                        html.Span("ایمن " if ev["safe"] else "نیازمند بازنویسی "),
                        html.Div(ev["sentence"], style={"opacity": 0.85}),
                        html.Div(
                            f"مسائل: {', '.join(ev['issues']) if ev['issues'] else '—'}",
                            style={"opacity": 0.6},
                        ),
                    ],
                    style={
                        "padding": "6px",
                        "backgroundColor": "rgba(13,20,45,0.82)",
                        "borderRadius": "6px",
                        "marginBottom": "6px",
                    },
                )
            )
        integrity_panel = html.Div(integrity_children, style={"lineHeight": "1.9"})

        awareness_panel = make_awareness_panel(organism)
        unconscious_panel = make_unconscious_panel(organism)
        awareness_panel = make_awareness_panel(organism)
        unconscious_panel = make_unconscious_panel(organism)
        wormhole_panel = make_wormhole_panel(organism)
        ecosystem_panel = make_ecosystem_panel(organism)
        episodes = organism.db.recent_episodes(16)
        if episodes:
            rows = []
            for ep in episodes:
                rows.append(
                    html.Tr(
                        [
                            html.Td(str(ep["ts"])[:19], style={"whiteSpace": "nowrap"}),
                            html.Td(str(ep["kind"])),
                            html.Td(str(ep["text"])[:170]),
                            html.Td(f"{float(ep['importance']):.2f}"),
                        ]
                    )
                )
            memory_panel = html.Table(
                [
                    html.Thead(
                        html.Tr(
                            [
                                html.Th("زمان"),
                                html.Th("نوع"),
                                html.Th("محتوا"),
                                html.Th("اهمیت"),
                            ]
                        )
                    ),
                    html.Tbody(rows),
                ],
                style={"width": "100%", "borderCollapse": "collapse"},
            )
        else:
            memory_panel = html.Div("هنوز خاطره‌ای ثبت نشده است.")

        actions = list(organism.action_log)[-20:][::-1]
        action_panel = html.Div(
            [
                html.Div(
                    f"{a['ts'][:19]} — {a['action']}",
                    style={
                        "padding": "4px 8px",
                        "backgroundColor": "rgba(13,20,45,0.82)",
                        "borderRadius": "6px",
                        "marginBottom": "4px",
                    },
                )
                for a in actions
            ]
        )

        genome_radar = make_genome_radar(snap)

        superawareness_panel = make_superawareness_panel(organism)
        phi_trend_graph = make_phi_trend_figure(organism)
        ideas_panel = make_ideas_panel(organism)
        deep_inquiry_panel = make_deep_inquiry_panel(organism)

        genome_panel = html.Pre(
            json.dumps(
                {
                    "generation": snap["genome"]["generation"],
                    "dna_hash": snap["genome"]["dna_hash"],
                    "traits": snap["genome"]["traits"],
                    "boldness": snap["boldness"],
                    "eloquence": snap["eloquence"],
                    "language_genes": snap["language_genes"],
                    "identity_values": snap["identity"]["values"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            style={
                "whiteSpace": "pre-wrap",
                "backgroundColor": "rgba(13,20,45,0.82)",
                "padding": "12px",
                "borderRadius": "8px",
            },
        )

        return (
            overview_cards,
            timeline_figure,
            body_gauges,
            thoughts_panel,
            emotion_figure,
            needs_figure,
            heart_figure,
            body_bars,
            brain_figure,
            matrix_panel,
            concept_network,
            concept_panel,
            integrity_panel,
            awareness_panel,
            unconscious_panel,
            wormhole_panel,
            ecosystem_panel,
            memory_panel,
            action_panel,
            genome_radar,
            genome_panel,
            superawareness_panel,
            phi_trend_graph,
            ideas_panel,
            deep_inquiry_panel,
        )

    return app


# ---------------------------------------------------------------------------
# Self-expansion
# ---------------------------------------------------------------------------
