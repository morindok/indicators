"""Durable SQLite memory for the BioTrader organism.

The exchange adapter remains read-only.  This module stores only local demo
state: expressed genes, mutation events, organism metadata and a detailed
paper-trading journal.  It intentionally uses SQLite from the standard
library so the organism can resume without an external database service.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if result == result else default
    except (TypeError, ValueError):
        return default


class BioMemory:
    """Thread-safe local persistence layer with a deliberately small API."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        configured = path if path is not None else os.getenv("BIO_DB_PATH", "bio_trader.db")
        self.path = str(configured)
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(
            self.path,
            check_same_thread=False,
            timeout=15,
        )
        self.connection.row_factory = sqlite3.Row
        self._initialise()

    def _initialise(self) -> None:
        with self._lock, self.connection:
            self.connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS organism_meta (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    generation INTEGER NOT NULL DEFAULT 0,
                    scan_count INTEGER NOT NULL DEFAULT 0,
                    neuron_count INTEGER NOT NULL DEFAULT 0,
                    state_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS genes (
                    key TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    base_weight REAL NOT NULL,
                    mutation REAL NOT NULL,
                    expression REAL NOT NULL,
                    mutation_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mutation_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gene_key TEXT NOT NULL,
                    old_mutation REAL NOT NULL,
                    new_mutation REAL NOT NULL,
                    reward REAL NOT NULL,
                    trigger TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trade_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    status TEXT NOT NULL,
                    entry REAL NOT NULL,
                    exit REAL,
                    tp REAL,
                    sl REAL,
                    margin REAL NOT NULL,
                    leverage INTEGER NOT NULL,
                    quantity REAL NOT NULL,
                    gross_pnl REAL NOT NULL DEFAULT 0,
                    fees REAL NOT NULL DEFAULT 0,
                    spread_cost REAL NOT NULL DEFAULT 0,
                    net_pnl REAL NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0,
                    quality REAL NOT NULL DEFAULT 0,
                    regime TEXT NOT NULL DEFAULT '',
                    heartbeat INTEGER NOT NULL DEFAULT 0,
                    decision_json TEXT NOT NULL DEFAULT '{}',
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    exit_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_trade_journal_created
                    ON trade_journal(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_mutation_events_created
                    ON mutation_events(created_at DESC);
                CREATE TABLE IF NOT EXISTS risk_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    state_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS risk_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_risk_events_created
                    ON risk_events(created_at DESC);
                """
            )

    def close(self) -> None:
        with self._lock:
            try:
                self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                pass
            self.connection.close()

    def ensure_genes(self, defaults: list[dict[str, Any]]) -> None:
        now = utc_iso()
        with self._lock, self.connection:
            for gene in defaults:
                self.connection.execute(
                    """
                    INSERT OR IGNORE INTO genes
                        (key, label, base_weight, mutation, expression, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(gene["key"]),
                        str(gene["label"]),
                        _num(gene.get("base_weight")),
                        _num(gene.get("mutation")),
                        _num(gene.get("expression"), 1.0),
                        now,
                    ),
                )

    def load_genes(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM genes ORDER BY rowid"
            ).fetchall()
        return {str(row["key"]): dict(row) for row in rows}

    def save_gene(
        self,
        gene: dict[str, Any],
        *,
        old_mutation: float,
        reward: float,
        trigger: str,
    ) -> None:
        now = utc_iso()
        with self._lock, self.connection:
            self.connection.execute(
                """
                UPDATE genes
                   SET label = ?, base_weight = ?, mutation = ?, expression = ?,
                       mutation_count = mutation_count + 1, updated_at = ?
                 WHERE key = ?
                """,
                (
                    str(gene["label"]),
                    _num(gene.get("base_weight")),
                    _num(gene.get("mutation")),
                    _num(gene.get("expression"), 1.0),
                    now,
                    str(gene["key"]),
                ),
            )
            self.connection.execute(
                """
                INSERT INTO mutation_events
                    (gene_key, old_mutation, new_mutation, reward, trigger, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(gene["key"]),
                    _num(old_mutation),
                    _num(gene.get("mutation")),
                    _num(reward),
                    str(trigger),
                    now,
                ),
            )

    def load_meta(self) -> dict[str, Any] | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT * FROM organism_meta WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        try:
            result["state"] = json.loads(result.pop("state_json") or "{}")
        except json.JSONDecodeError:
            result["state"] = {}
        return result

    def save_meta(
        self,
        *,
        generation: int,
        scan_count: int,
        neuron_count: int,
        state: dict[str, Any],
    ) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO organism_meta
                    (id, generation, scan_count, neuron_count, state_json, updated_at)
                VALUES (1, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    generation = excluded.generation,
                    scan_count = excluded.scan_count,
                    neuron_count = excluded.neuron_count,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (
                    int(generation),
                    int(scan_count),
                    int(neuron_count),
                    json.dumps(state, ensure_ascii=False, default=str),
                    utc_iso(),
                ),
            )

    def record_open(self, position: Any, decision: dict[str, Any] | None = None) -> int:
        """Insert a paper trade and return its durable journal id."""
        opened_at = str(getattr(position, "opened_at", utc_iso()))
        with self._lock, self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO trade_journal
                    (symbol, side, status, entry, tp, sl, margin, leverage, quantity,
                     fees, spread_cost, confidence, quality, regime, heartbeat,
                     decision_json, opened_at, created_at, updated_at)
                VALUES (?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(getattr(position, "symbol", "")),
                    str(getattr(position, "side", "")),
                    _num(getattr(position, "entry", 0)),
                    _num(getattr(position, "tp", 0)),
                    _num(getattr(position, "sl", 0)),
                    _num(getattr(position, "margin", 0)),
                    int(getattr(position, "leverage", 0)),
                    _num(getattr(position, "qty", 0)),
                    _num(getattr(position, "entry_fee", 0)),
                    _num(getattr(position, "entry_spread_cost", 0)),
                    _num(getattr(position, "confidence", 0)),
                    _num(getattr(position, "quality", 0)),
                    str(getattr(position, "regime", "")),
                    int(getattr(position, "heartbeat_at_open", 0)),
                    json.dumps(decision or {}, ensure_ascii=False, default=str),
                    opened_at,
                    opened_at,
                    opened_at,
                ),
            )
            return int(cursor.lastrowid)

    def record_close(
        self,
        journal_id: int | None,
        position: Any,
        *,
        gross_pnl: float,
        exit_fee: float,
        net_pnl: float,
        reason: str,
    ) -> None:
        closed_at = utc_iso()
        with self._lock, self.connection:
            if journal_id:
                self.connection.execute(
                    """
                    UPDATE trade_journal
                       SET status = 'CLOSED', exit = ?, gross_pnl = ?, fees = fees + ?,
                           net_pnl = ?, closed_at = ?, exit_reason = ?, updated_at = ?
                     WHERE id = ?
                    """,
                    (
                        _num(getattr(position, "mark", 0)),
                        _num(gross_pnl),
                        _num(exit_fee),
                        _num(net_pnl),
                        closed_at,
                        str(reason),
                        closed_at,
                        int(journal_id),
                    ),
                )
                return
            # Defensive fallback for positions created before persistence was
            # enabled or for a manually injected test position.
            self.connection.execute(
                """
                INSERT INTO trade_journal
                    (symbol, side, status, entry, exit, tp, sl, margin, leverage, quantity,
                     gross_pnl, fees, spread_cost, net_pnl, confidence, quality, regime,
                     heartbeat, opened_at, closed_at, exit_reason, created_at, updated_at)
                VALUES (?, ?, 'CLOSED', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(getattr(position, "symbol", "")),
                    str(getattr(position, "side", "")),
                    _num(getattr(position, "entry", 0)),
                    _num(getattr(position, "mark", 0)),
                    _num(getattr(position, "tp", 0)),
                    _num(getattr(position, "sl", 0)),
                    _num(getattr(position, "margin", 0)),
                    int(getattr(position, "leverage", 0)),
                    _num(getattr(position, "qty", 0)),
                    _num(gross_pnl),
                    _num(exit_fee) + _num(getattr(position, "entry_fee", 0)),
                    _num(getattr(position, "entry_spread_cost", 0)),
                    _num(net_pnl),
                    _num(getattr(position, "confidence", 0)),
                    _num(getattr(position, "quality", 0)),
                    str(getattr(position, "regime", "")),
                    int(getattr(position, "heartbeat_at_open", 0)),
                    str(getattr(position, "opened_at", closed_at)),
                    closed_at,
                    str(reason),
                    closed_at,
                    closed_at,
                ),
            )

    def journal(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM trade_journal ORDER BY id DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["decision"] = json.loads(item.pop("decision_json") or "{}")
            except json.JSONDecodeError:
                item["decision"] = {}
            result.append(item)
        return result

    def mutation_history(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM mutation_events ORDER BY id DESC LIMIT ?",
                (max(1, min(int(limit), 300)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def memory_summary(self) -> dict[str, Any]:
        with self._lock:
            genes = int(self.connection.execute("SELECT COUNT(*) FROM genes").fetchone()[0])
            mutations = int(
                self.connection.execute("SELECT COUNT(*) FROM mutation_events").fetchone()[0]
            )
            trades = int(
                self.connection.execute("SELECT COUNT(*) FROM trade_journal").fetchone()[0]
            )
            closed = int(
                self.connection.execute(
                    "SELECT COUNT(*) FROM trade_journal WHERE status = 'CLOSED'"
                ).fetchone()[0]
            )
        return {
            "path": self.path,
            "genes": genes,
            "mutations": mutations,
            "trades": trades,
            "closed_trades": closed,
        }

    # -- risk desk persistence ----------------------------------------------
    def save_risk_state(self, state: dict[str, Any]) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO risk_state (id, state_json, updated_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (json.dumps(state, ensure_ascii=False, default=str), utc_iso()),
            )

    def load_risk_state(self) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute(
                "SELECT state_json FROM risk_state WHERE id = 1"
            ).fetchone()
        if row is None:
            return {}
        try:
            return json.loads(row["state_json"] or "{}")
        except json.JSONDecodeError:
            return {}

    def record_risk_event(self, kind: str, detail: str = "") -> None:
        with self._lock, self.connection:
            self.connection.execute(
                "INSERT INTO risk_events (kind, detail, created_at) VALUES (?, ?, ?)",
                (str(kind), str(detail), utc_iso()),
            )

    def risk_events(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM risk_events ORDER BY id DESC LIMIT ?",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return [dict(row) for row in rows]


__all__ = ["BioMemory"]
