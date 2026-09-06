"""Dash UI for the adaptive Chrono-Gann matrix."""
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc
from bybit_connector import BybitConnector
from chrono_engine import ChronoEngine
from gann_matrix import GannMatrix
from config import *

app = Dash(__name__, external_stylesheets=[dbc.themes.CYBORG], title="Chrono-Gann Matrix")
server = app.server
connector, chrono, gann = BybitConnector(), ChronoEngine(), GannMatrix()
intervals = [{"label": x, "value": y} for x,y in [("1m","1"),("5m","5"),("15m","15"),("1h","60"),("4h","240"),("1D","D")]]

def empty(message):
    f=go.Figure(); f.add_annotation(text=message, x=.5, y=.5, xref="paper", yref="paper", showarrow=False, font={"color":DOWN,"size":15})
    f.update_layout(paper_bgcolor=BG, plot_bgcolor=PANEL, template="plotly_dark"); return f

def make_figure(df, matrix, angles, supports, resistances, symbol):
    fig=go.Figure(go.Candlestick(x=df.ts, open=df.open, high=df.high, low=df.low, close=df.close, name=symbol, increasing_line_color=UP, decreasing_line_color=DOWN))
    colors=["#315273","#386b72","#566d58","#876b42"]
    for i, layer in enumerate(matrix["layers"]):
        for level in layer["levels"]:
            fig.add_hline(y=level, line_color=colors[i%len(colors)], line_width=0.45, opacity=.6)
    for y, color, label in [(supports, CYAN, "Support"), (resistances, GOLD, "Resistance")]:
        for j, level in enumerate(y): fig.add_hline(y=level, line_color=color, line_width=1.5, line_dash="dash", annotation_text=f"{label} {j+1}", annotation_font_color=color)
    for line in angles:
        fig.add_trace(go.Scatter(x=[line["x0"],line["x1"]], y=[line["y0"],line["y1"]], mode="lines", name=line["name"], legendgroup=line["name"], line={"width":1, "color": GOLD if line["name"]=="1x1" else MUTED}, opacity=.7, showlegend=False, hovertemplate=line["name"]+"<extra></extra>"))
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=PANEL, font={"color":TEXT}, margin={"l":10,"r":10,"t":38,"b":10}, title={"text":f"{symbol}  |  Chrono-Gann adaptive square", "x":.5, "font":{"color":GOLD,"size":15}}, xaxis={"rangeslider_visible":False,"gridcolor":GRID}, yaxis={"gridcolor":GRID}, hovermode="x unified", legend={"orientation":"h","y":1.02})
    return fig

def side_panel(matrix, supports, resistances, df):
    def rows(vals, color): return [html.Div(f"{v:,.4f}", style={"color":color,"fontFamily":"monospace","padding":"2px 0"}) for v in vals] or [html.Div("-")]
    return html.Div([
      html.Div([html.Span("LIVE ", style={"color":UP}), html.Span(f"{df.close.iloc[-1]:,.4f}", style={"fontSize":22,"fontWeight":"700"})], className="metric"),
      html.Div([html.Div("STATIC SUPPORT", className="section-title"), *rows(supports,CYAN)], className="section"),
      html.Div([html.Div("STATIC RESISTANCE", className="section-title"), *rows(resistances,GOLD)], className="section"),
      html.Div([html.Div("MATRIX", className="section-title"), html.Div(f"Origin  {matrix['origin']:,.4f}"), html.Div(f"Unit step  {matrix['step']:,.6f}"), html.Div(f"Layers  {len(matrix['layers'])}"), html.Div("Angles  1x8 ... 8x1")], className="section")
    ])

app.layout=html.Div([
 html.Div([html.Div("CHRONO / GANN", className="brand"), html.Div("Dynamic price geometry", className="subtitle"),
   dcc.Input(id="symbol", value=DEFAULT_SYMBOL, className="input"), dcc.Dropdown(id="category", options=[{"label":x,"value":x} for x in ["linear","spot","inverse"]], value=DEFAULT_CATEGORY, clearable=False, className="control"), dcc.Dropdown(id="tf", options=intervals, value=DEFAULT_INTERVAL, clearable=False, className="control"), dbc.Button("Refresh", id="refresh", color="warning", className="refresh")], className="toolbar"),
 html.Div([dcc.Graph(id="chart", config={"displaylogo":False,"scrollZoom":True}, style={"height":"78vh"}), html.Div(id="side")], className="workspace"),
 dcc.Interval(id="clock", interval=REFRESH_MS, n_intervals=0), html.Div(id="status", className="status")
], style={"background":BG,"minHeight":"100vh"})

app.clientside_callback("""function(n){return n}""", Output("status","children"), Input("clock","n_intervals"))
@app.callback(Output("chart","figure"), Output("side","children"), Output("status","children"), Input("clock","n_intervals"), Input("refresh","n_clicks"), Input("symbol","value"), Input("tf","value"), Input("category","value"))
def update(_, __, symbol, tf, category):
    symbol=(symbol or DEFAULT_SYMBOL).strip().upper()
    df=connector.klines(symbol, tf or DEFAULT_INTERVAL, category or DEFAULT_CATEGORY, DEFAULT_LIMIT)
    if df.empty: return empty("Unable to fetch Bybit market data"), html.Div(), "OFFLINE | Bybit endpoints unavailable"
    matrix=gann.calculate(df, chrono.anchors(df)); sup,res=gann.support_resistance(df,matrix); fig=make_figure(df,matrix,gann.angle_lines(df,matrix),sup,res,symbol)
    return fig, side_panel(matrix,sup,res,df), f"ONLINE | {connector.active} | updated {df.ts.iloc[-1]} UTC"

# compact application styling
app.index_string=app.index_string.replace("</head>", """<style>
body{margin:0;font-family:Inter,Arial,sans-serif}.toolbar{display:flex;align-items:center;gap:10px;padding:14px 18px;border-bottom:1px solid #263750;background:#0d1828}.brand{color:#f2b84b;font-weight:800;letter-spacing:2px;font-size:18px}.subtitle{color:#91a4bd;font-size:11px;margin-right:auto}.input{width:110px;background:#101d30;border:1px solid #263750;color:#e8eef7;padding:9px}.control{width:120px;color:#111}.refresh{height:38px}.workspace{display:grid;grid-template-columns:minmax(0,1fr) 245px;gap:12px;max-width:1500px;margin:auto;padding:10px}.section,.metric{border-bottom:1px solid #263750;padding:14px 10px;color:#e8eef7}.section-title{color:#91a4bd;font-size:10px;letter-spacing:1px;margin-bottom:7px}.status{text-align:center;color:#91a4bd;font-size:11px;padding:4px}@media(max-width:750px){.toolbar{flex-wrap:wrap}.subtitle{display:none}.workspace{grid-template-columns:1fr}.workspace .side{display:block}}
</style></head>""")

if __name__ == "__main__": app.run(host=HOST, port=PORT, debug=False)
