"""
organism.database

پایگاه‌داده‌ی پایدار ارگانیسم (SQLite).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from .utils import MAX_TEXT_STORE, clamp, normalize_fa, safe_sqlite_id, stable_hash, utc_iso

from .utils import clamp, normalize_fa, safe_sqlite_id, stable_hash, utc_iso

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .genome import Genome

class AdvancedDatabase:
    TABLE_WHITELIST = {
        "episodes",
        "knowledge",
        "lexicon",
        "patterns",
        "evolution",
        "concepts",
        "concept_edges",
        "organism_state",
        "language_markov",
        "language_sentences",
        "integrity_events",
        "awareness_events",
        "unconscious_events",
    }

    def __init__(self, path: str = "organism2500.sqlite3"):
        self.path = str(path)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT,
                    kind TEXT,
                    text TEXT,
                    importance REAL
                );

                CREATE TABLE IF NOT EXISTS knowledge (
                    id INTEGER PRIMARY KEY,
                    ts TEXT,
                    topic TEXT,
                    title TEXT,
                    content TEXT,
                    source TEXT,
                    weight REAL
                );

                CREATE TABLE IF NOT EXISTS lexicon (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT UNIQUE,
                    freq INTEGER DEFAULT 1,
                    vector TEXT,
                    meaning TEXT,
                    last_seen TEXT
                );

                CREATE TABLE IF NOT EXISTS patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    payload TEXT
                );

                CREATE TABLE IF NOT EXISTS evolution (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT,
                    genome_hash TEXT,
                    generation INTEGER,
                    traits_json TEXT
                );

                CREATE TABLE IF NOT EXISTS concepts (
                    id TEXT PRIMARY KEY,
                    label TEXT UNIQUE,
                    strength REAL,
                    vector TEXT,
                    definition TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS concept_edges (
                    source_id TEXT,
                    target_id TEXT,
                    source_label TEXT,
                    target_label TEXT,
                    relation TEXT,
                    weight REAL,
                    updated_at TEXT,
                    PRIMARY KEY(source_id, target_id, relation)
                );

                CREATE TABLE IF NOT EXISTS organism_state (
                    key TEXT PRIMARY KEY,
                    payload TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS language_markov (
                    word TEXT,
                    next_word TEXT,
                    weight INTEGER,
                    PRIMARY KEY(word, next_word)
                );

                CREATE TABLE IF NOT EXISTS language_sentences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sentence TEXT UNIQUE,
                    score REAL,
                    ts TEXT
                );

                CREATE TABLE IF NOT EXISTS integrity_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT,
                    kind TEXT,
                    sentence TEXT,
                    score REAL,
                    issues TEXT
                );

                CREATE TABLE IF NOT EXISTS awareness_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT,
                    text TEXT,
                    emotion TEXT,
                    intent TEXT,
                    score REAL,
                    meta TEXT
                );

                CREATE TABLE IF NOT EXISTS unconscious_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT,
                    kind TEXT,
                    content TEXT,
                    unity REAL
                );

                CREATE INDEX IF NOT EXISTS idx_episodes_ts ON episodes(ts);
                CREATE INDEX IF NOT EXISTS idx_episodes_kind ON episodes(kind);
                CREATE INDEX IF NOT EXISTS idx_knowledge_topic ON knowledge(topic);
                CREATE INDEX IF NOT EXISTS idx_lexicon_word ON lexicon(word);
                CREATE INDEX IF NOT EXISTS idx_concepts_strength ON concepts(strength);
                CREATE INDEX IF NOT EXISTS idx_integrity_ts ON integrity_events(ts);
                CREATE INDEX IF NOT EXISTS idx_awareness_ts ON awareness_events(ts);
                CREATE INDEX IF NOT EXISTS idx_unconscious_ts ON unconscious_events(ts);
                """
            )
            self.conn.commit()

    def safe_execute(self, query: str, params: Tuple = ()):
        with self.lock:
            try:
                cur = self.conn.execute(query, params)
                self.conn.commit()
                return cur
            except sqlite3.Error:
                return None

    def fetch_one(self, query: str, params: Tuple = ()):
        with self.lock:
            try:
                return self.conn.execute(query, params).fetchone()
            except sqlite3.Error:
                return None

    def fetch_all(self, query: str, params: Tuple = ()):
        with self.lock:
            try:
                return self.conn.execute(query, params).fetchall()
            except sqlite3.Error:
                return []

    def log_episode(self, kind: str, text: str, importance: float = 0.5) -> None:
        self.safe_execute(
            "INSERT INTO episodes(ts, kind, text, importance) VALUES (?, ?, ?, ?)",
            (utc_iso(), kind, str(text)[:MAX_TEXT_STORE], clamp(importance)),
        )

    def store_knowledge(
        self,
        topic: str,
        title: str,
        content: str,
        source: str,
        weight: float = 0.5,
    ) -> None:
        # Fixed OverflowError: use a safe 63-bit integer ID for SQLite INTEGER PRIMARY KEY.
        kid = safe_sqlite_id(f"{topic}:{title}:{source}")
        self.safe_execute(
            """
            INSERT OR REPLACE INTO knowledge(id, ts, topic, title, content, source, weight)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                kid,
                utc_iso(),
                str(topic)[:300],
                str(title)[:500],
                str(content)[:MAX_TEXT_STORE],
                str(source)[:500],
                clamp(weight),
            ),
        )

    def learn_word(self, word: str, vector: str, meaning: str) -> None:
        word = normalize_fa(word)
        if not word:
            return
        now = utc_iso()
        row = self.fetch_one("SELECT id, freq FROM lexicon WHERE word = ?", (word,))
        if row:
            self.safe_execute(
                """
                UPDATE lexicon
                SET freq = ?, vector = ?, meaning = ?, last_seen = ?
                WHERE id = ?
                """,
                (row["freq"] + 1, vector, meaning, now, row["id"]),
            )
        else:
            self.safe_execute(
                """
                INSERT INTO lexicon(word, freq, vector, meaning, last_seen)
                VALUES (?, ?, ?, ?, ?)
                """,
                (word, 1, vector, meaning, now),
            )

    def recent_episodes(self, limit: int = 20) -> List[sqlite3.Row]:
        return self.fetch_all(
            """
            SELECT ts, kind, text, importance
            FROM episodes
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        )

    def search_knowledge(self, query: str, limit: int = 12) -> List[sqlite3.Row]:
        like = f"%{normalize_fa(query)}%"
        return self.fetch_all(
            """
            SELECT ts, topic, title, content, source, weight
            FROM knowledge
            WHERE title LIKE ? OR content LIKE ? OR topic LIKE ?
            ORDER BY weight DESC, id DESC
            LIMIT ?
            """,
            (like, like, like, max(1, int(limit))),
        )

    def count(self, table: str) -> int:
        if table not in self.TABLE_WHITELIST:
            return 0
        row = self.fetch_one(f"SELECT COUNT(*) AS c FROM {table}")
        return int(row["c"]) if row else 0

    def log_evolution(self, genome: Genome) -> None:
        self.safe_execute(
            """
            INSERT INTO evolution(ts, genome_hash, generation, traits_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                utc_iso(),
                format(genome.dna_hash, "016x"),
                genome.generation,
                json.dumps(genome.traits, ensure_ascii=False),
            ),
        )

    def upsert_concept(
        self,
        concept_id: str,
        label: str,
        strength: float,
        vector: str,
        definition: str,
    ) -> None:
        self.safe_execute(
            """
            INSERT OR REPLACE INTO concepts(id, label, strength, vector, definition, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                concept_id,
                normalize_fa(label),
                clamp(strength, 0.0, 10.0),
                vector,
                str(definition)[:800],
                utc_iso(),
            ),
        )

    def fetch_concepts(self, limit: int = 5000) -> List[sqlite3.Row]:
        return self.fetch_all(
            """
            SELECT id, label, strength, vector, definition, updated_at
            FROM concepts
            ORDER BY strength DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        )

    def upsert_concept_edge(
        self,
        source_label: str,
        target_label: str,
        relation: str,
        weight: float,
    ) -> None:
        source_label = normalize_fa(source_label)
        target_label = normalize_fa(target_label)
        relation = normalize_fa(relation) or "related"

        source_id = format(stable_hash(source_label) & ((1 << 64) - 1), "016x")
        target_id = format(stable_hash(target_label) & ((1 << 64) - 1), "016x")

        row = self.fetch_one(
            """
            SELECT weight
            FROM concept_edges
            WHERE source_id = ? AND target_id = ? AND relation = ?
            """,
            (source_id, target_id, relation),
        )

        if row:
            new_weight = clamp(float(row["weight"]) + float(weight), 0.0, 20.0)
            self.safe_execute(
                """
                UPDATE concept_edges
                SET weight = ?, updated_at = ?, source_label = ?, target_label = ?
                WHERE source_id = ? AND target_id = ? AND relation = ?
                """,
                (
                    new_weight,
                    utc_iso(),
                    source_label,
                    target_label,
                    source_id,
                    target_id,
                    relation,
                ),
            )
        else:
            self.safe_execute(
                """
                INSERT INTO concept_edges(
                    source_id, target_id, source_label, target_label, relation, weight, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    target_id,
                    source_label,
                    target_label,
                    relation,
                    clamp(float(weight), 0.0, 20.0),
                    utc_iso(),
                ),
            )

    def fetch_concept_edges(self, limit: int = 10000) -> List[sqlite3.Row]:
        return self.fetch_all(
            """
            SELECT source_label, target_label, relation, weight
            FROM concept_edges
            ORDER BY weight DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        )

    def save_state(self, key: str, payload: Dict[str, Any]) -> None:
        self.safe_execute(
            """
            INSERT OR REPLACE INTO organism_state(key, payload, updated_at)
            VALUES (?, ?, ?)
            """,
            (key, json.dumps(payload, ensure_ascii=False, default=str), utc_iso()),
        )

    def load_state(self, key: str) -> Optional[Dict[str, Any]]:
        row = self.fetch_one("SELECT payload FROM organism_state WHERE key = ?", (key,))
        if not row:
            return None
        try:
            return json.loads(row["payload"])
        except Exception:
            return None

    def save_markov_word(self, word: str, next_words: List[str]) -> None:
        word = normalize_fa(word)
        if not word:
            return
        with self.lock:
            try:
                self.conn.execute("DELETE FROM language_markov WHERE word = ?", (word,))
                counts = Counter(next_words)
                for nxt, weight in counts.items():
                    nxt = normalize_fa(nxt)
                    if not nxt:
                        continue
                    self.conn.execute(
                        """
                        INSERT OR REPLACE INTO language_markov(word, next_word, weight)
                        VALUES (?, ?, ?)
                        """,
                        (word, nxt, int(weight)),
                    )
                self.conn.commit()
            except sqlite3.Error:
                pass

    def fetch_markov(self, limit: int = 20000) -> List[sqlite3.Row]:
        return self.fetch_all(
            """
            SELECT word, next_word, weight
            FROM language_markov
            ORDER BY weight DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        )

    def save_sentence(self, sentence: str, score: float) -> None:
        sentence = normalize_fa(sentence)[:700]
        if len(sentence) < 12:
            return
        self.safe_execute(
            """
            INSERT OR IGNORE INTO language_sentences(sentence, score, ts)
            VALUES (?, ?, ?)
            """,
            (sentence, clamp(score), utc_iso()),
        )

    def fetch_sentences(self, limit: int = 1200) -> List[sqlite3.Row]:
        return self.fetch_all(
            """
            SELECT sentence, score
            FROM language_sentences
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        )

    def log_integrity_event(self, kind: str, sentence: str, score: float, issues: str) -> None:
        self.safe_execute(
            """
            INSERT INTO integrity_events(ts, kind, sentence, score, issues)
            VALUES (?, ?, ?, ?, ?)
            """,
            (utc_iso(), kind, str(sentence)[:700], clamp(score), str(issues)[:700]),
        )

    def fetch_integrity_events(self, limit: int = 30) -> List[sqlite3.Row]:
        return self.fetch_all(
            """
            SELECT ts, kind, sentence, score, issues
            FROM integrity_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        )

    def log_awareness(self, text: str, emotion: str, intent: str, score: float, meta: str) -> None:
        self.safe_execute(
            """
            INSERT INTO awareness_events(ts, text, emotion, intent, score, meta)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                utc_iso(),
                str(text)[:700],
                str(emotion)[:80],
                str(intent)[:80],
                clamp(score),
                str(meta)[:700],
            ),
        )

    def fetch_awareness(self, limit: int = 30) -> List[sqlite3.Row]:
        return self.fetch_all(
            """
            SELECT ts, text, emotion, intent, score, meta
            FROM awareness_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        )

    def log_unconscious(self, kind: str, content: str, unity: float) -> None:
        self.safe_execute(
            """
            INSERT INTO unconscious_events(ts, kind, content, unity)
            VALUES (?, ?, ?, ?)
            """,
            (utc_iso(), kind, str(content)[:1200], clamp(unity)),
        )

    def fetch_unconscious(self, limit: int = 30) -> List[sqlite3.Row]:
        return self.fetch_all(
            """
            SELECT ts, kind, content, unity
            FROM unconscious_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        )

    def close(self) -> None:
        with self.lock:
            try:
                self.conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Short-term memory
# ---------------------------------------------------------------------------
