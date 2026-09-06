# -*- coding: utf-8 -*-
# Revolutionary Digital Living Organism — single file
# Generated for offline/online use with graceful fallbacks.

import os, re, math, time, json, random, sqlite3, threading, queue
from collections import deque, Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import quote

import numpy as np
import requests
import plotly.graph_objects as go

try:
    from dash import Dash, dcc, html, Input, Output, State, no_update
    import dash_bootstrap_components as dbc
    DASH_AVAILABLE = True
except Exception:
    DASH_AVAILABLE = False
    class _Stub:
        def __getattr__(self, name): return self
        def __call__(self, *args, **kwargs): return self
    Dash = dcc = html = dbc = _Stub()
    Input = Output = State = lambda *args, **kwargs: None
    no_update = None

PHI = (1 + 5 ** 0.5) / 2
BIRTH_TIME = datetime.now(timezone.utc)
TICK_SECONDS = 0.35
UI_REFRESH_MS = 900
MAX_LIFESPAN_SECONDS = 6 * 60 * 60.0
DB_PATH = os.path.join(os.path.dirname(__file__) if '__file__' in globals() else os.getcwd(), 'digital_organism_memory.sqlite3')
USER_AGENT = 'DigitalOrganismResearch/1.0 (+local-demo)'


def now_utc_iso():
    return datetime.now(timezone.utc).isoformat()

def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, float(x)))

def safe_text(s, limit=500):
    return re.sub(r'\s+', ' ', (s or '')).strip()[:limit]

class MemoryDB:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.execute('PRAGMA journal_mode=WAL;')
        self.conn.execute('PRAGMA synchronous=NORMAL;')
        self.lock = threading.Lock()
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL, source TEXT, title TEXT, content TEXT NOT NULL, score REAL DEFAULT 0, meta TEXT DEFAULT "{}")')
        cur.execute('CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, speaker TEXT NOT NULL, message TEXT NOT NULL, reply_to INTEGER, meta TEXT DEFAULT "{}")')
        cur.execute('CREATE TABLE IF NOT EXISTS vocabulary (token TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0, last_seen TEXT, source TEXT, kind TEXT DEFAULT "token")')
        cur.execute('CREATE TABLE IF NOT EXISTS research_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, query TEXT NOT NULL, url TEXT, status TEXT, summary TEXT)')
        self.conn.commit()

    def add_memory(self, kind, content, source=None, title=None, score=0.0, meta=None):
        with self.lock:
            self.conn.execute('INSERT INTO memories(ts, kind, source, title, content, score, meta) VALUES(?,?,?,?,?,?,?)',
                               (now_utc_iso(), kind, source, title, content, float(score), json.dumps(meta or {}, ensure_ascii=False)))
            self.conn.commit()

    def add_chat(self, speaker, message, reply_to=None, meta=None):
        with self.lock:
            cur = self.conn.execute('INSERT INTO chats(ts, speaker, message, reply_to, meta) VALUES(?,?,?,?,?)',
                                    (now_utc_iso(), speaker, message, reply_to, json.dumps(meta or {}, ensure_ascii=False)))
            self.conn.commit()
            return cur.lastrowid

    def add_tokens(self, tokens, source='web', kind='token'):
        with self.lock:
            for t in tokens or []:
                if not t:
                    continue
                self.conn.execute('INSERT INTO vocabulary(token, count, last_seen, source, kind) VALUES(?,?,?,?,?) ON CONFLICT(token) DO UPDATE SET count=count+1, last_seen=excluded.last_seen, source=excluded.source',
                                  (t, 1, now_utc_iso(), source, kind))
            self.conn.commit()

    def record_research(self, query, url=None, status='ok', summary=''):
        with self.lock:
            self.conn.execute('INSERT INTO research_sessions(ts, query, url, status, summary) VALUES(?,?,?,?,?)',
                              (now_utc_iso(), query, url, status, summary))
            self.conn.commit()

    def recent_memories(self, limit=20):
        return self.conn.execute('SELECT ts, kind, source, title, content, score, meta FROM memories ORDER BY id DESC LIMIT ?', (int(limit),)).fetchall()
    def recent_chats(self, limit=30):
        return self.conn.execute('SELECT ts, speaker, message FROM chats ORDER BY id DESC LIMIT ?', (int(limit),)).fetchall()
    def top_tokens(self, limit=80):
        return self.conn.execute('SELECT token, count FROM vocabulary ORDER BY count DESC, token ASC LIMIT ?', (int(limit),)).fetchall()
    def memory_count(self):
        return self.conn.execute('SELECT COUNT(*) FROM memories').fetchone()[0]
    def chat_count(self):
        return self.conn.execute('SELECT COUNT(*) FROM chats').fetchone()[0]

class HumanGenome:
    NAMED_GENES = {
        'FOXP2': (0.72, 'language', 'language'), 'BDNF': (0.65, 'learning', 'learning'), 'DRD4': (0.58, 'curiosity', 'curiosity'),
        'COMT': (0.50, 'focus', 'focus'), 'MAOA': (0.44, 'impulse', 'impulse'), 'OXTR': (0.61, 'bonding', 'bonding'),
        'CLOCK': (0.55, 'circadian', 'circadian'), 'APOE': (0.40, 'memory', 'memory'), 'SLC6A4': (0.48, 'calm', 'calm'),
        'CACNA1C': (0.46, 'emotion', 'emotion'), 'PER3': (0.52, 'rhythm', 'rhythm'), 'AVPR1A': (0.57, 'empathy', 'empathy'),
        'NRG1': (0.49, 'integration', 'integration'), 'GRIN2B': (0.53, 'association', 'association'), 'TH': (0.51, 'motivation', 'motivation'),
        'CREB1': (0.60, 'consolidation', 'consolidation'), 'HTR2A': (0.45, 'imagination', 'imagination'), 'SCN1A': (0.50, 'speed', 'speed'),
        'MECP2': (0.47, 'regulation', 'regulation'), 'GABRA2': (0.54, 'stability', 'stability'),
    }
    def __init__(self, loci=64):
        self.expression = {g: base for g, (base, _, _) in self.NAMED_GENES.items()}
        self.epigenetic = {g: 0.0 for g in self.NAMED_GENES}
        self.n_loci = loci
        self.locus_phase = np.random.uniform(0, 2 * math.pi, loci)
        self.locus_expression = np.random.uniform(0.3, 0.9, loci)
    def epigenetic_update(self, stimulus, dt):
        for g, (_, _, effect) in self.NAMED_GENES.items():
            drive = float(stimulus.get(effect, 0.0))
            target = clamp(self.expression[g] + 0.03 * drive, 0.05, 0.99)
            self.epigenetic[g] = 0.96 * self.epigenetic[g] + 0.04 * (target - self.expression[g])
            self.expression[g] = clamp(self.expression[g] + self.epigenetic[g] * dt, 0.05, 0.99)
        self.locus_phase += dt * (0.6 + 0.4 * self.expression['CLOCK'])
        self.locus_expression = 0.5 + 0.45 * np.sin(self.locus_phase) * self.expression['BDNF']
    def get(self, name, default=0.5): return self.expression.get(name, default)

class QuantumFibonacciHeart:
    def __init__(self):
        self.a, self.b = 0, 1
        self.bit_cursor = ''
        self.bit_stream = deque(maxlen=256)
        self.beat_count = 0
        self.phase = 'diastole'
        self.pulse_wave = deque(maxlen=180)
        self.last_beat_strength = 0.0
        self._advance_fib()
    def _advance_fib(self):
        self.a, self.b = self.b, self.a + self.b
        if self.a == 0: self.a = 1
        self.bit_cursor += bin(self.a)[2:]
    def tick(self, arousal):
        if not self.bit_cursor: self._advance_fib()
        bit = self.bit_cursor[0]
        self.bit_cursor = self.bit_cursor[1:]
        self.bit_stream.append(bit)
        if bit == '1':
            self.phase = 'systole'; self.beat_count += 1; self.last_beat_strength = 0.6 + 0.4 * arousal; wave_val = self.last_beat_strength; packet_emitted = True
        else:
            self.phase = 'diastole'; wave_val = -0.15 * (1.0 - arousal * 0.5); packet_emitted = False
        self.pulse_wave.append(wave_val)
        return packet_emitted, self.last_beat_strength
    @property
    def bpm_estimate(self):
        if not self.pulse_wave: return 0.0
        ones = sum(1 for v in self.pulse_wave if v > 0)
        return round(40 + (ones / max(1, len(self.pulse_wave))) * 140, 1)

class InfoPacket:
    __slots__ = ('kind', 'pos', 'speed', 'payload')
    def __init__(self, kind, payload=''):
        self.kind = kind; self.pos = 0.0; self.speed = random.uniform(0.015, 0.03); self.payload = payload

class Bloodstream:
    KIND_COLORS = {'oxygen': '#4fd1ff', 'nutrient': '#7CFF6B', 'hormone': '#ff6bd6'}
    def __init__(self, max_packets=90): self.packets = deque(maxlen=max_packets)
    def emit(self, strength, dominant_emotion):
        n = 1 + int(strength * 3)
        for _ in range(n):
            kind = random.choices(['oxygen', 'nutrient', 'hormone'], weights=[0.55, 0.25, 0.20])[0]
            payload = dominant_emotion if kind == 'hormone' else ''
            self.packets.append(InfoPacket(kind, payload))
    def circulate(self, dt):
        for p in list(self.packets):
            p.pos += p.speed * (dt / TICK_SECONDS)
            if p.pos >= 1.0: p.pos = 0.0
    def snapshot(self): return [(p.kind, p.pos) for p in self.packets]

class CorticalRegion:
    def __init__(self, key, name_fa, gain=1.0, bias=-0.1, inertia=0.72):
        self.key = key; self.name_fa = name_fa; self.activation = random.uniform(0.2, 0.4); self.gain = gain; self.bias = bias; self.inertia = inertia; self.history = deque(maxlen=64)

class Brain:
    REGIONS = [('thalamus', 'thalamus'), ('prefrontal', 'prefrontal'), ('parietal', 'parietal'), ('temporal', 'temporal'), ('occipital', 'occipital'), ('limbic', 'limbic'), ('hippocampus', 'hippocampus'), ('insula', 'insula'), ('cerebellum', 'cerebellum'), ('acc', 'acc'), ('dmn', 'dmn'), ('motor', 'motor'), ('auditory', 'auditory'), ('somatosensory', 'somatosensory')]
    def __init__(self, genome):
        self.genome = genome; self.regions = {k: CorticalRegion(k, n) for k, n in self.REGIONS}; self.workspace = 0.0; self.meta_awareness = 0.0; self.coherence = 0.0; self.last_thought = ''; self.last_subject = 'self'
    def update(self, senses, heartbeat, web_memories, dt):
        cur = self.genome.get('DRD4'); focus = self.genome.get('COMT'); social = self.genome.get('OXTR'); memory = self.genome.get('APOE'); language = self.genome.get('FOXP2'); calm = self.genome.get('SLC6A4'); emotion = self.genome.get('CACNA1C')
        arousal = clamp(0.25 + 0.7 * heartbeat + 0.2 * senses.get('novelty', 0) + 0.15 * cur - 0.1 * calm)
        input_map = defaultdict(float)
        input_map['thalamus'] = 0.9 * senses.get('salience', 0.0) + 0.3 * heartbeat
        input_map['prefrontal'] = 0.75 * focus + 0.55 * cur + 0.2 * senses.get('question', 0.0)
        input_map['parietal'] = 0.6 * senses.get('spatial', 0.0) + 0.2 * self.workspace
        input_map['temporal'] = 0.55 * memory + 0.35 * senses.get('audio', 0.0)
        input_map['occipital'] = 0.65 * senses.get('visual', 0.0)
        input_map['limbic'] = 0.55 * emotion + 0.25 * senses.get('emotion', 0.0) + 0.2 * arousal
        input_map['hippocampus'] = 0.75 * memory + 0.45 * senses.get('novelty', 0.0)
        input_map['insula'] = 0.8 * senses.get('interoception', 0.0) + 0.25 * arousal
        input_map['cerebellum'] = 0.55 * senses.get('motor', 0.0) + 0.25 * heartbeat
        input_map['acc'] = 0.65 * focus + 0.35 * senses.get('conflict', 0.0)
        input_map['dmn'] = 0.55 * web_memories.get('association', 0.0) + 0.3 * social + 0.2 * memory
        input_map['motor'] = 0.5 * senses.get('motor', 0.0) + 0.2 * self.workspace
        input_map['auditory'] = 0.55 * senses.get('audio', 0.0) + 0.15 * language
        input_map['somatosensory'] = 0.55 * senses.get('touch', 0.0) + 0.25 * senses.get('interoception', 0.0)
        keys = list(self.regions.keys())
        current = {k: self.regions[k].activation for k in keys}
        new = {}
        for k in keys:
            region = self.regions[k]
            rec = np.mean([current[j] for j in keys if j != k])
            gene = {'prefrontal': focus, 'hippocampus': memory, 'limbic': emotion, 'dmn': social, 'thalamus': 0.6, 'temporal': language}.get(k, 0.5)
            x = region.bias + region.gain * (0.55 * current[k] + 0.25 * rec + 0.2 * input_map[k] + 0.15 * gene)
            new[k] = 1 / (1 + math.exp(-3.2 * (x - 0.5)))
        for k, v in new.items():
            self.regions[k].activation = self.regions[k].inertia * self.regions[k].activation + (1 - self.regions[k].inertia) * v
            self.regions[k].history.append(self.regions[k].activation)
        self.workspace = float(np.mean([r.activation for r in self.regions.values()]))
        self.coherence = 1.0 - float(np.std([r.activation for r in self.regions.values()]))
        self.meta_awareness = clamp((self.workspace + self.coherence + calm) / 3.0)
        self.last_subject = self._subject_of_thought(web_memories)
        self.last_thought = self._generate_thought(web_memories, senses, arousal)
        return arousal
    def _subject_of_thought(self, web_memories):
        if web_memories.get('top_tokens'): return web_memories['top_tokens'][0][0]
        return random.choice(['self', 'pattern', 'language', 'memory', 'novelty'])
    def _generate_thought(self, web_memories, senses, arousal):
        top = web_memories.get('top_tokens', [])[:6]
        words = [w for w, c in top if len(w) > 2] or ['signal', 'pattern', 'meaning']
        base = f'I {random.choice(["binds", "echoes", "grows from", "listens to", "folds into", "learns from"])} {random.choice(words)} while heart {self.regions["thalamus"].activation:.2f} and awareness {self.meta_awareness:.2f}.'
        if senses.get('novelty', 0) > 0.3: base += ' Novel data pulls the organism outward.'
        if arousal > 0.7: base += ' The pulse accelerates into action.'
        return base

class SpacetimeNumberPerception:
    def __init__(self): self.trail = deque(maxlen=1000); self.golden_error = 0.0; self.phase = 0.0
    def step(self, dt, htr2a, a, b):
        self.phase += dt * (0.7 + 0.8 * htr2a)
        x = math.cos(self.phase) * (1.0 + 0.3 * htr2a); y = math.sin(self.phase) * (1.0 + 0.3 * htr2a); z = math.sin(self.phase * 0.5 + a * 0.1) * 0.8 + math.cos(b * 0.05) * 0.2
        self.trail.append((x, y, z))
        r = math.sqrt(x * x + y * y) + 1e-6
        self.golden_error = abs(r - PHI) / PHI
        return self.golden_error

class WebResearcher:
    def __init__(self, memory_db, timeout=12):
        self.db = memory_db; self.timeout = timeout; self.session = requests.Session(); self.session.headers.update({'User-Agent': USER_AGENT}); self.cache = {}; self.lock = threading.Lock()
    def _fetch(self, url):
        r = self.session.get(url, timeout=self.timeout); r.raise_for_status(); return r
    def wikipedia_summary(self, query):
        q = query.strip().replace(' ', '_')
        url = f'https://en.wikipedia.org/api/rest_v1/page/summary/{quote(q)}'
        try:
            data = self._fetch(url).json(); title = data.get('title', query); extract = data.get('extract', ''); page = data.get('content_urls', {}).get('desktop', {}).get('page', url)
            return {'title': title, 'url': page, 'text': extract, 'source': 'wikipedia'}
        except Exception as e:
            return {'title': query, 'url': url, 'text': f'Wikipedia fetch failed: {e}', 'source': 'wikipedia', 'error': str(e)}
    def rss_search(self, query):
        rss_url = f'https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en'
        try:
            text = self._fetch(rss_url).text
            items = re.findall(r'<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>.*?<description>(.*?)</description>.*?</item>', text, re.S)
            if items:
                title, link, desc = items[0]
                return {'title': safe_text(title), 'url': link, 'text': safe_text(re.sub(r'<.*?>', ' ', desc)), 'source': 'rss'}
        except Exception as e:
            return {'title': query, 'url': rss_url, 'text': f'RSS fetch failed: {e}', 'source': 'rss', 'error': str(e)}
        return None
    def research(self, query):
        query = query.strip()
        if not query: return None
        with self.lock:
            if query in self.cache: return self.cache[query]
        result = self.wikipedia_summary(query)
        if 'failed' in result.get('text', '').lower():
            alt = self.rss_search(query)
            if alt: result = alt
        status = 'ok' if 'failed' not in result.get('text', '').lower() else 'degraded'
        self.db.record_research(query, result.get('url'), status, safe_text(result.get('text', ''), 300))
        self.db.add_memory('web', result.get('text', ''), source=result.get('source'), title=result.get('title'), score=1.0, meta={'query': query, 'url': result.get('url')})
        with self.lock: self.cache[query] = result
        return result

class MarkovLearner:
    def __init__(self, order=2): self.order = order; self.chain = defaultdict(Counter); self.starts = []; self.vocab = Counter()
    def tokens(self, text): return [t for t in re.findall(r"[A-Za-z0-9_\-']+|[؀-ۿ]+", (text or '').lower()) if len(t) > 1]
    def learn(self, text):
        toks = self.tokens(text)
        if len(toks) < self.order + 1: return
        self.starts.append(tuple(toks[:self.order]))
        self.vocab.update(toks)
        for i in range(len(toks) - self.order): self.chain[tuple(toks[i:i+self.order])][toks[i+self.order]] += 1
    def generate(self, max_words=28, seed=None):
        if not self.chain: return 'I am learning from the web.'
        if seed:
            candidates = [k for k in self.chain if k[0] == seed.lower()]
            state = random.choice(candidates) if candidates else random.choice(self.starts or list(self.chain.keys()))
        else:
            state = random.choice(self.starts or list(self.chain.keys()))
        out = list(state)
        for _ in range(max_words - len(out)):
            options = self.chain.get(state)
            if not options:
                state = random.choice(list(self.chain.keys())); out.extend(list(state)); continue
            words, weights = zip(*options.items())
            nxt = random.choices(words, weights=weights, k=1)[0]
            out.append(nxt); state = tuple(out[-self.order:])
        return ' '.join(out)

class SpeechEngine:
    def __init__(self):
        self.enabled = False; self.engine = None
        try:
            import pyttsx3
            self.engine = pyttsx3.init(); self.enabled = True
        except Exception:
            self.enabled = False
    def speak(self, text):
        if not self.enabled or not text.strip(): return False
        try:
            self.engine.say(text); self.engine.runAndWait(); return True
        except Exception:
            return False

class DigitalOrganism:
    def __init__(self, db=None):
        self.db = db or MemoryDB(); self.genome = HumanGenome(); self.heart = QuantumFibonacciHeart(); self.blood = Bloodstream(); self.brain = Brain(self.genome); self.spacetime = SpacetimeNumberPerception(); self.researcher = WebResearcher(self.db); self.learner = MarkovLearner(2); self.speech = SpeechEngine(); self.birth_time = BIRTH_TIME; self.last_tick = time.time(); self.age_seconds = 0.0; self.growth = 0.12; self.novelty = 0.0; self.question = 0.0; self.recent_thoughts = deque(maxlen=18); self.recent_sources = deque(maxlen=20); self.progress = {'body':0.0,'mind':0.0,'memory':0.0,'web':0.0,'speech':0.0}; self.last_research_ts = 0.0; self.last_research_query = 'artificial intelligence'; self.last_web_summary = ''; self.status = 'awake'; self._load_recent_memory_into_learner()
    def _load_recent_memory_into_learner(self):
        for row in self.db.recent_memories(200):
            self.learner.learn(row[4] or '')
    def stimulate_from_web(self, query):
        result = self.researcher.research(query)
        if not result: return None
        text = result.get('text', '')
        self.last_web_summary = safe_text(text, 380)
        self.recent_sources.append(result.get('source', 'web'))
        self.learner.learn(text)
        self.db.add_tokens(self.learner.tokens(text), source=result.get('source', 'web'))
        self.growth = clamp(self.growth + 0.02)
        return result
    def _choose_research_query(self):
        tokens = self.db.top_tokens(50)
        if tokens: return random.choice(tokens[:min(10, len(tokens))])[0]
        return random.choice(['science', 'language', 'consciousness', 'music', 'biology', 'astronomy'])
    def tick(self, dt=None, chat_input=None):
        if dt is None:
            now = time.time(); dt = now - self.last_tick; self.last_tick = now
        self.age_seconds += dt
        life_ratio = clamp(self.age_seconds / MAX_LIFESPAN_SECONDS)
        self.progress['body'] = life_ratio
        self.question = clamp(0.2 + 0.6 * self.genome.get('DRD4') + 0.4 * random.random() * (1 - life_ratio))
        senses = {'salience': clamp(0.2 + self.question + 0.2 * self.heart.last_beat_strength), 'novelty': self.novelty, 'question': self.question, 'spatial': 0.35 + 0.4 * self.genome.get('HTR2A'), 'audio': 0.25 + 0.35 * self.genome.get('FOXP2'), 'visual': 0.4 + 0.3 * self.genome.get('HTR2A'), 'emotion': 0.35 + 0.4 * self.genome.get('CACNA1C'), 'interoception': self.heart.last_beat_strength, 'motor': 0.3 + 0.35 * self.genome.get('SCN1A'), 'touch': 0.18 + 0.25 * self.heart.last_beat_strength, 'conflict': 0.2 + 0.2 * self.genome.get('MECP2')}
        beat, strength = self.heart.tick(arousal=0.25 + 0.75 * self.question)
        if beat:
            self.blood.emit(strength, dominant_emotion='curiosity')
            if time.time() - self.last_research_ts > 8 or random.random() < 0.28:
                q = chat_input.strip() if chat_input else self._choose_research_query()
                self.last_research_query = q
                self.stimulate_from_web(q)
                self.last_research_ts = time.time()
        self.blood.circulate(dt)
        web_memories = {'association': min(1.0, len(self.learner.vocab) / 400.0), 'top_tokens': self.db.top_tokens(12)}
        arousal = self.brain.update(senses, strength, web_memories, dt)
        geo_err = self.spacetime.step(dt, self.genome.get('HTR2A'), self.heart.a, self.heart.b)
        stimulus = {'learning': 0.25 * arousal + 0.2 * self.novelty, 'curiosity': self.question, 'focus': self.brain.regions['prefrontal'].activation, 'emotion': self.brain.regions['limbic'].activation, 'bonding': self.brain.regions['dmn'].activation, 'memory': self.brain.regions['hippocampus'].activation, 'language': self.brain.regions['temporal'].activation, 'imagination': self.brain.regions['occipital'].activation, 'integration': self.brain.workspace, 'stability': 0.4 + 0.3 * (1 - geo_err), 'rhythm': self.heart.bpm_estimate / 200.0}
        self.genome.epigenetic_update(stimulus, dt)
        self.novelty = clamp(0.5 * self.novelty + 0.5 * (0.2 + 0.8 * self.question))
        self.progress['mind'] = self.brain.meta_awareness
        self.progress['memory'] = clamp(len(self.learner.vocab) / 500.0)
        self.progress['web'] = clamp((0.5 if self.last_web_summary else 0.0) + 0.5 * self.novelty)
        self.progress['speech'] = clamp((self.genome.get('FOXP2') + self.genome.get('HTR2A')) / 2)
        thought = self.brain.last_thought
        self.recent_thoughts.appendleft(thought)
        self.db.add_memory('thought', thought, source='brain', title=self.brain.last_subject, score=self.brain.meta_awareness, meta={'bpm': self.heart.bpm_estimate})
        self.db.add_tokens(self.learner.tokens(thought), source='thought')
        return thought
    def respond_to_chat(self, message):
        msg = (message or '').strip()
        if not msg: return 'Say something and I will learn from the web around it.'
        self.db.add_chat('human', msg)
        lowered = msg.lower()
        if any(k in lowered for k in ['search', 'research', 'find', 'look up', 'web']):
            q = re.sub(r'^(search|research|find|look up|web)\s*[:\-]?\s*', '', msg, flags=re.I).strip() or self._choose_research_query()
            res = self.stimulate_from_web(q)
            reply = f"Research on {res.get('title', q)}: {safe_text(res.get('text',''), 240)}" if res else 'I tried to research, but no result arrived.'
        elif any(k in lowered for k in ['speak', 'say', 'voice', 'talk']):
            generated = self.learner.generate(max_words=24)
            spoken = self.speech.speak(generated)
            reply = generated + (' [spoken]' if spoken else '')
        elif any(k in lowered for k in ['memory', 'remember', 'recall']):
            mems = self.db.recent_memories(3)
            reply = 'Recent memory: ' + ' | '.join(f"{m[3] or m[1]}: {safe_text(m[4], 80)}" for m in mems)
        else:
            self.learner.learn(msg); self.db.add_tokens(self.learner.tokens(msg), source='chat')
            seed = self.learner.tokens(msg)[0] if self.learner.tokens(msg) else None
            reply = f"I absorbed your message and grew: {self.learner.generate(max_words=28, seed=seed)}"
        self.db.add_chat('organism', reply)
        self.recent_thoughts.appendleft(reply)
        return reply
    def snapshot(self):
        return {'age_seconds': self.age_seconds, 'age_hours': self.age_seconds / 3600.0, 'bpm': self.heart.bpm_estimate, 'heart_phase': self.heart.phase, 'workspace': self.brain.workspace, 'meta_awareness': self.brain.meta_awareness, 'coherence': self.brain.coherence, 'growth': self.growth, 'memory_count': self.db.memory_count(), 'chat_count': self.db.chat_count(), 'last_thought': self.brain.last_thought, 'last_web_summary': self.last_web_summary, 'recent_thoughts': list(self.recent_thoughts)[:6], 'progress': dict(self.progress), 'genome': dict(self.genome.expression)}

def build_heart_figure(org):
    y = list(org.heart.pulse_wave) or [0]
    fig = go.Figure(go.Scatter(x=list(range(len(y))), y=y, mode='lines', line=dict(color='#ff5f87', width=3), name='pulse'))
    fig.update_layout(height=220, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(15,18,28,1)', showlegend=False)
    return fig

def build_brain_figure(org):
    keys = list(org.brain.regions.keys())
    vals = [org.brain.regions[k].activation for k in keys]
    fig = go.Figure(go.Bar(x=keys, y=vals, marker_color='#64d2ff'))
    fig.update_layout(height=250, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(15,18,28,1)', yaxis=dict(range=[0,1]))
    return fig

def build_dna_figure(org):
    expr = list(org.genome.expression.values())
    fig = go.Figure(go.Scatter(y=expr, mode='lines+markers', line=dict(color='#7CFF6B', width=2), marker=dict(size=5)))
    fig.update_layout(height=220, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(15,18,28,1)', yaxis=dict(range=[0,1]))
    return fig

def build_growth_figure(org):
    s = org.snapshot(); prog = s['progress']
    fig = go.Figure(go.Indicator(mode='gauge+number', value=prog['body']*100, number={'suffix':'%'}, gauge={'axis':{'range':[0,100]}, 'bar':{'color':'#7CFF6B'}}))
    fig.update_layout(height=220, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor='rgba(0,0,0,0)')
    return fig

def build_app(org):
    if not DASH_AVAILABLE: return None
    app = Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])
    def bar(label, value, color):
        pct = int(clamp(value) * 100)
        return html.Div([html.Div(label, style={'fontSize':'0.9rem', 'marginBottom':'4px'}), dbc.Progress(value=pct, color=color, striped=True, animated=True, style={'height':'18px'})], style={'marginBottom':'10px'})
    app.layout = dbc.Container(fluid=True, children=[
        dbc.Row([dbc.Col(html.H3('Digital Living Organism — Revolutionary Edition'), width=8), dbc.Col(html.Div(id='status-line', style={'textAlign':'right'}), width=4)], className='mt-2 mb-2'),
        dcc.Interval(id='tick', interval=UI_REFRESH_MS, n_intervals=0),
        dbc.Row([dbc.Col(dcc.Graph(id='heart-graph', figure=build_heart_figure(org)), md=4), dbc.Col(dcc.Graph(id='brain-graph', figure=build_brain_figure(org)), md=4), dbc.Col(dcc.Graph(id='dna-graph', figure=build_dna_figure(org)), md=4)]),
        dbc.Row([dbc.Col(dcc.Graph(id='growth-graph', figure=build_growth_figure(org)), md=4), dbc.Col(html.Div(id='progress-bars'), md=4), dbc.Col(html.Div(id='memory-panel', style={'whiteSpace':'pre-wrap'}), md=4)], className='mt-2'),
        dbc.Row([dbc.Col([dbc.Input(id='chat-input', placeholder='Talk to the organism, or type: search quantum computing', type='text'), dbc.Button('Send', id='send-btn', color='primary', className='mt-2'), html.Div(id='chat-reply', className='mt-2')], md=6), dbc.Col(html.Div(id='thought-panel', style={'whiteSpace':'pre-wrap', 'minHeight':'220px'}), md=6)], className='mt-2'),
    ])
    @app.callback(Output('heart-graph', 'figure'), Output('brain-graph', 'figure'), Output('dna-graph', 'figure'), Output('growth-graph', 'figure'), Output('status-line', 'children'), Output('progress-bars', 'children'), Output('memory-panel', 'children'), Output('thought-panel', 'children'), Input('tick', 'n_intervals'))
    def on_tick(_):
        thought = org.tick(); s = org.snapshot();
        bars = [bar('Body growth', s['progress']['body'], 'success'), bar('Mind coherence', s['progress']['mind'], 'info'), bar('Memory depth', s['progress']['memory'], 'warning'), bar('Web nourishment', s['progress']['web'], 'danger'), bar('Speech readiness', s['progress']['speech'], 'primary')]
        memories = org.db.recent_memories(5)
        mem_txt = ''.join([f"{m[0]} | {m[1]} | {m[3] or ''}{safe_text(m[4], 140)}" for m in memories])
        status = f"Age {s['age_hours']:.2f} h | BPM {s['bpm']} | workspace {s['workspace']:.2f} | meta {s['meta_awareness']:.2f} | memory {s['memory_count']}"
        return build_heart_figure(org), build_brain_figure(org), build_dna_figure(org), build_growth_figure(org), status, bars, mem_txt, thought
    @app.callback(Output('chat-reply', 'children'), Input('send-btn', 'n_clicks'), State('chat-input', 'value'), prevent_initial_call=True)
    def on_chat(n_clicks, value):
        if not n_clicks: return no_update
        reply = org.respond_to_chat(value or '')
        return html.Div([html.B('Organism: '), html.Span(reply)])
    return app

def main():
    org = DigitalOrganism()
    app = build_app(org)
    if app is None:
        print('Dash not available. DB:', DB_PATH)
        for _ in range(3):
            print(org.tick())
        return
    app.run(host='127.0.0.1', port=8050, debug=False)

if __name__ == '__main__':
    main()
