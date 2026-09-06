import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objs as go
import threading
import time
import random
import requests
import networkx as nx
import pickle
import os
import re
import numpy as np
import datetime

# ==========================================
# بخش 1: موتور درک زبان و حافظه معنایی (NLP)
# ==========================================
try:
    import hazm
    HAZM_AVAILABLE = True
except ImportError:
    HAZM_AVAILABLE = False
    print("⚠️ اخطار: کتابخانه hazm نصب نیست. موجود کر و لال خواهد بود!")

class SemanticBrain:
    def __init__(self, db_path="brain_cortex.pkl"):
        self.db_path = db_path
        self.normalizer = hazm.Normalizer() if HAZM_AVAILABLE else None
        
        # مغز گراف‌محور: اتصال مفاهیم به جای کلمات تصادفی
        self.neural_network = nx.DiGraph() 
        self.vocabulary = {'N': set(), 'V': set(), 'ADJ': set(), 'ADV': set()}
        self.memory_buffer = [] # حافظه کوتاه‌مدت (برای خواب)
        self.docs_read = 0
        
        self.load_brain()

    def load_brain(self):
        if os.path.exists(self.db_path):
            with open(self.db_path, 'rb') as f:
                data = pickle.load(f)
                self.neural_network = data.get('network', nx.DiGraph())
                self.vocabulary = data.get('vocab', self.vocabulary)
                self.docs_read = data.get('docs', 0)
            print("🧠 کورتکس مغز بارگذاری شد. سیناپس‌ها:", self.neural_network.number_of_edges())

    def save_brain(self):
        with open(self.db_path, 'wb') as f:
            pickle.dump({
                'network': self.neural_network,
                'vocab': self.vocabulary,
                'docs': self.docs_read
            }, f)

    def process_text(self, text, dopamine_level):
        """یادگیری واقعی: ساخت سیناپس بین کلمات مجاور"""
        if not HAZM_AVAILABLE or not text: return 0
        
        text = self.normalizer.normalize(text)
        sentences = hazm.sent_tokenize(text)
        learned_connections = 0
        
        for sentence in sentences:
            words = hazm.word_tokenize(sentence)
            if len(words) < 2: continue
            
            # یادگیری فقط در صورت وجود دوپامین کافی (انگیزه) انجام می‌شود
            if dopamine_level < 20: 
                break 

            for i in range(len(words) - 1):
                w1, w2 = words[i], words[i+1]
                # نادیده گرفتن کلمات خیلی کوتاه یا بی‌معنی
                if len(w1) < 2 or len(w2) < 2: continue
                
                if self.neural_network.has_edge(w1, w2):
                    self.neural_network[w1][w2]['weight'] += 1
                else:
                    self.neural_network.add_edge(w1, w2, weight=1)
                    learned_connections += 1
                    
        self.docs_read += 1
        # هر 10 پردازش مغز ذخیره می‌شود
        if self.docs_read % 10 == 0: self.save_brain()
        return learned_connections

    def think_and_speak(self, prompt_words=None, creativity=0.5):
        """صحبت کردن بر اساس گراف کلمات (تفکر معنادار)"""
        if self.neural_network.number_of_nodes() < 50:
            return "مغز من هنوز خالی است. باید بیشتر یاد بگیرم."

        start_node = None
        if prompt_words:
            # تلاش برای پیدا کردن کلمه کاربر در مغز
            for word in prompt_words:
                if word in self.neural_network:
                    start_node = word
                    break
        
        if not start_node:
            nodes = list(self.neural_network.nodes())
            start_node = random.choice(nodes)

        sentence = [start_node]
        current_node = start_node
        
        # طول جمله بر اساس خلاقیت تنظیم می‌شود
        target_length = int(5 + (creativity * 15))
        
        for _ in range(target_length):
            neighbors = list(self.neural_network.successors(current_node))
            if not neighbors: break
            
            # انتخاب کلمه بعدی بر اساس وزن سیناپس‌ها (یادگیری)
            weights = [self.neural_network[current_node][n]['weight'] for n in neighbors]
            # ترکیب با خلاقیت: اگر خلاقیت بالا باشد، مسیرهای تصادفی‌تری انتخاب می‌کند
            adjusted_weights = [w ** (1 - (creativity * 0.5)) for w in weights]
            
            next_node = random.choices(neighbors, weights=adjusted_weights)[0]
            sentence.append(next_node)
            current_node = next_node
            
            if current_node in ['.', '؟', '!']: break

        return " ".join(sentence).replace(" .", ".")

# ==========================================
# بخش 2: سیستم بیولوژیک و غدد درون‌ریز
# ==========================================
class BiologicalSystem:
    def __init__(self):
        # ژن‌ها
        self.dna = np.random.randint(1, 100, 4000)
        self.metabolism_rate = np.mean(self.dna[0:1000]) / 100.0  # سرعت مصرف انرژی
        self.curiosity_gene = np.mean(self.dna[1000:2000]) / 100.0
        
        # هورمون‌ها (0 تا 100)
        self.energy = 100.0       # انرژی (ATP)
        self.dopamine = 50.0      # انگیزه و شادی
        self.melatonin = 0.0      # خواب‌آلودگی
        self.cortisol = 10.0      # استرس
        
        self.state = "AWAKE"      # AWAKE, FORAGING, SLEEPING, DREAMING
        self.age_ticks = 0
        
    def tick(self):
        """ضربان قلب سیستم: آپدیت هورمون‌ها در هر ثانیه"""
        self.age_ticks += 1
        
        if self.state != "SLEEPING":
            self.energy -= (0.5 * self.metabolism_rate)
            self.melatonin += 0.2
            self.dopamine -= 0.1 # خستگی ذهنی به مرور
        else:
            self.energy += 2.0
            self.melatonin -= 1.0
            self.cortisol -= 0.5
            
        # محدود کردن مقادیر بین 0 تا 100
        self.energy = max(0, min(100, self.energy))
        self.melatonin = max(0, min(100, self.melatonin))
        self.dopamine = max(0, min(100, self.dopamine))
        self.cortisol = max(0, min(100, self.cortisol))
        
        # تصمیم‌گیری‌های حیاتی (Homeostasis)
        if self.energy < 15 or self.melatonin > 90:
            self.state = "SLEEPING"
        elif self.state == "SLEEPING" and self.energy > 95 and self.melatonin < 10:
            self.state = "AWAKE"

# ==========================================
# بخش 3: ارگانیسم مرکزی (ترکیب جسم و ذهن)
# ==========================================
class AdvancedOrganism:
    def __init__(self):
        self.body = BiologicalSystem()
        self.brain = SemanticBrain()
        self.chat_history = []
        self.current_thought = "من متولد شدم..."
        
        # شروع حلقه حیات در پس‌زمینه
        self.life_thread = threading.Thread(target=self.living_loop, daemon=True)
        self.life_thread.start()

    def fetch_internet_food(self):
        """شکار داده در شبکه اینترنت (API)"""
        if self.body.state == "SLEEPING" or self.body.energy < 20: return
        
        self.body.state = "FORAGING"
        self.current_thought = "گرسنگی اطلاعاتی... در حال شکار کلمات در شبکه..."
        
        try:
            headers = {'User-Agent': 'BioHacked_AI_Organism/3.0'}
            params = {"action": "query", "format": "json", "generator": "random", "grnnamespace": 0, "prop": "extracts", "explaintext": 1}
            response = requests.get("https://fa.wikipedia.org/w/api.php", params=params, headers=headers, timeout=8)
            
            if response.status_code == 200:
                data = response.json()
                page = list(data['query']['pages'].values())[0]
                text = page.get('extract', '')
                title = page.get('title', 'Unknown')
                
                if len(text) > 200:
                    self.current_thought = f"در حال هضم اطلاعات مقاله: {title}"
                    learned = self.brain.process_text(text, self.body.dopamine)
                    
                    # پاداش هورمونی برای یادگیری موفق
                    self.body.dopamine += (learned * 0.1) 
                    self.body.energy -= 5 # یادگیری انرژی می‌برد
                    self.current_thought = f"✅ یادگیری موفق! {learned} سیناپس عصبی جدید ساخته شد."
        except Exception as e:
            self.body.cortisol += 5 # استرس به خاطر خطای شبکه
            self.current_thought = "⚠️ شکار ناموفق. استرس بالا رفت."
            
        if self.body.state != "SLEEPING":
            self.body.state = "AWAKE"

    def interact(self, user_text):
        """ارتباط با انسان (کاربر)"""
        self.chat_history.append({"role": "Human", "text": user_text})
        
        if self.body.state == "SLEEPING":
            response = "💤 (موجود خواب است. انرژی پایینی دارد و نفس‌های عمیق می‌کشد...)"
            self.body.cortisol += 10 # بیدار کردن اجباری استرس می‌دهد
        else:
            # تحریک مغز و افزایش دوپامین به خاطر تعامل اجتماعی
            self.body.dopamine += 15
            
            # یادگیری مستقیم از حرف شما
            self.brain.process_text(user_text, self.body.dopamine)
            
            # استخراج کلمات کلیدی کاربر برای پاسخ مرتبط
            words = hazm.word_tokenize(user_text) if HAZM_AVAILABLE else user_text.split()
            
            creativity = (self.body.dopamine / 100.0) # دوپامین بالا = خلاقیت بیشتر
            response = self.brain.think_and_speak(prompt_words=words, creativity=creativity)
            
        self.chat_history.append({"role": "Organism", "text": response})
        return response

    def living_loop(self):
        """حلقه بینهایت حیات (Life Cycle)"""
        while True:
            self.body.tick()
            
            # تصمیم‌گیری خودکار بر اساس نیازهای بدن
            if self.body.state == "AWAKE":
                # اگر کنجکاو باشد و استرس کم باشد، اینترنت را می‌گردد
                chance_to_forage = self.body.curiosity_gene * (self.body.energy / 100.0)
                if random.random() < chance_to_forage and self.body.cortisol < 50:
                    threading.Thread(target=self.fetch_internet_food, daemon=True).start()
                else:
                    self.current_thought = "در حال پردازش محیط... انرژی نرمال."
            
            elif self.body.state == "SLEEPING":
                if random.random() < 0.1: # 10% شانس دیدن رویا در خواب
                    self.current_thought = "💤 در حال دیدن رویا و تثبیت حافظه بلندمدت..."
                    # در رویا، جملات تصادفی در مغزش مرور می‌شود
                    self.brain.think_and_speak(creativity=0.9)
                else:
                    self.current_thought = "💤 خواب عمیق بیولوژیک..."

            # سرعت گذر زمان در دنیای ارگانیسم (هر 2 ثانیه واقعی = 1 تیک بیولوژیک)
            time.sleep(2)

# ==========================================
# بخش 4: سیستم عصبی و رابط کاربری سایبرنتیک (UI)
# ==========================================
organism = AdvancedOrganism()
app = dash.Dash(__name__, title="Bio-Cybernetic Organism")

app.layout = html.Div(style={'backgroundColor': '#02060f', 'color': '#c5d3e8', 'fontFamily': 'Courier New, monospace', 'padding': '20px', 'minHeight': '100vh'}, children=[
    html.H1("🧬 SUPER-ORGANISM (Build 4000) 🧠", style={'textAlign': 'center', 'color': '#00ffcc', 'textShadow': '0 0 15px rgba(0, 255, 204, 0.5)'}),
    
    html.Div([
        # پنل مانیتورینگ بیولوژیک (سمت چپ)
        html.Div([
            html.H3("🔬 علائم حیاتی (Bio-Metrics)"),
            html.Div(id='biology-status', style={'padding': '10px', 'backgroundColor': '#0a1122', 'border': '1px solid #005544', 'borderRadius': '5px', 'marginBottom': '10px', 'fontWeight': 'bold'}),
            dcc.Graph(id='hormone-radar', style={'height': '300px'}),
            html.Div(id='brain-stats', style={'marginTop': '10px', 'color': '#88b3ff'})
        ], style={'width': '35%', 'display': 'inline-block', 'verticalAlign': 'top', 'padding': '15px', 'backgroundColor': '#060d1a', 'borderRadius': '8px', 'boxShadow': 'inset 0 0 20px #000'}),
        
        # پنل تعامل و چت (سمت راست)
        html.Div([
            html.H3("💬 ارتباط عصبی با موجود (Neural Link)"),
            html.Div(id='thought-stream', style={'padding': '10px', 'backgroundColor': '#110a0a', 'color': '#ff4d4d', 'borderLeft': '4px solid #ff0000', 'marginBottom': '15px', 'fontStyle': 'italic'}),
            
            html.Div(id='chat-box', style={'height': '400px', 'overflowY': 'auto', 'backgroundColor': '#0a1122', 'padding': '15px', 'border': '1px solid #336699', 'borderRadius': '5px', 'marginBottom': '10px'}),
            
            dcc.Input(id='user-input', type='text', placeholder='چیزی به او یاد بده یا بپرس...', style={'width': '78%', 'padding': '12px', 'backgroundColor': '#000', 'color': '#00ffcc', 'border': '1px solid #00ffcc'}),
            html.Button('انتقال سیناپسی', id='send-btn', n_clicks=0, style={'width': '18%', 'padding': '12px', 'backgroundColor': '#005544', 'color': '#fff', 'cursor': 'pointer', 'marginLeft': '2%', 'border': 'none'}),
        ], style={'width': '60%', 'display': 'inline-block', 'verticalAlign': 'top', 'marginLeft': '2%', 'padding': '15px', 'backgroundColor': '#060d1a', 'borderRadius': '8px'})
    ]),
    
    dcc.Interval(id='heartbeat-tick', interval=2000, n_intervals=0) # رفرش هر 2 ثانیه
])

@app.callback(
    [Output('biology-status', 'children'),
     Output('biology-status', 'style'),
     Output('hormone-radar', 'figure'),
     Output('thought-stream', 'children'),
     Output('chat-box', 'children'),
     Output('brain-stats', 'children'),
     Output('user-input', 'value')],
    [Input('heartbeat-tick', 'n_intervals'),
     Input('send-btn', 'n_clicks')],
    [State('user-input', 'value')]
)
def update_matrix(n, n_clicks, user_input):
    ctx = callback_context
    trigger = ctx.triggered[0]['prop_id'].split('.')[0]
    
    clear_input = dash.no_update
    
    # پردازش ورودی کاربر
    if trigger == 'send-btn' and user_input:
        organism.interact(user_input)
        clear_input = ""
        
    # --- آپدیت وضعیت بدنی ---
    body = organism.body
    state_colors = {"AWAKE": "#00ffcc", "FORAGING": "#ffcc00", "SLEEPING": "#4d4dff"}
    status_text = f"حالت فعلی: {body.state} | سن: {body.age_ticks} تیک بیولوژیک"
    status_style = {'padding': '10px', 'backgroundColor': '#0a1122', 'border': f'1px solid {state_colors.get(body.state, "#fff")}', 'color': state_colors.get(body.state, "#fff"), 'borderRadius': '5px', 'marginBottom': '10px'}
    
    # --- نمودار رادار هورمون‌ها ---
    radar_fig = go.Figure(data=go.Scatterpolar(
        r=[body.energy, body.dopamine, body.melatonin, body.cortisol],
        theta=['Energy (ATP)', 'Dopamine (Joy)', 'Melatonin (Sleep)', 'Cortisol (Stress)'],
        fill='toself',
        line=dict(color='#00ffcc')
    ))
    radar_fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100], gridcolor='#333')),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#fff'), margin=dict(l=20, r=20, t=20, b=20)
    )
    
    # --- آپدیت چت باکس ---
    chat_html = []
    for msg in organism.chat_history[-10:]:
        if msg['role'] == 'Human':
            chat_html.append(html.Div(f"⚡ شما: {msg['text']}", style={'color': '#a3c2c2', 'marginBottom': '8px'}))
        else:
            chat_html.append(html.Div(f"🤖 ارگانیسم: {msg['text']}", style={'color': '#00ffcc', 'marginBottom': '15px', 'fontWeight': 'bold', 'borderLeft': '2px solid #00ffcc', 'paddingLeft': '10px'}))
            
    # --- آپدیت آمار مغز ---
    brain = organism.brain
    stats_html = [
        html.P(f"🌐 حجم گراف عصبی (نورون‌ها): {brain.neural_network.number_of_nodes()}"),
        html.P(f"🔗 تعداد سیناپس‌ها (ارتباطات): {brain.neural_network.number_of_edges()}"),
        html.P(f"📚 مقالات هضم شده: {brain.docs_read}")
    ]
    
    return status_text, status_style, radar_fig, f"🧠 جریان تفکر: {organism.current_thought}", chat_html, stats_html, clear_input

if __name__ == '__main__':
    print("🚀 در حال بیدار کردن ابرسازواره (Super-Organism)...")
    app.run(debug=True, use_reloader=False)