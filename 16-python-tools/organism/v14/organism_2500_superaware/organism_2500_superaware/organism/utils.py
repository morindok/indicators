"""
organism.utils

توابع پایه، هش، زمان و نرمال‌سازی متن فارسی.
"""
from __future__ import annotations

import hashlib
import math
import re
import time
from datetime import datetime, timezone
from typing import Any, Iterable, List

APP_NAME = "ORGANISM-2500"
VIRTUAL_NEURONS = 85_000_000_000
ACTIVE_NEURON_SAMPLES = 2048
MAX_TEXT_STORE = 5000
SQLITE_INT_MAX_MASK = (1 << 63) - 1


def now_ts() -> float:
    return time.time()


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(text: Any) -> int:
    data = str(text).encode("utf-8", errors="replace")
    return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")


def safe_sqlite_id(text: Any) -> int:
    return stable_hash(text) & SQLITE_INT_MAX_MASK


def clamp(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    try:
        value = float(value)
    except Exception:
        value = low
    return max(low, min(high, value))


def sigmoid(x: float) -> float:
    x = clamp(x, -30.0, 30.0)
    return 1.0 / (1.0 + math.exp(-x))


def normalize_fa(text: str) -> str:
    text = str(text)
    mapping = {
        "ك": "ک",
        "ي": "ی",
        "ى": "ی",
        "ة": "ه",
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ؤ": "و",
        "ئ": "ی",
        "‌": " ",
    }
    for old, new in mapping.items():
        text = text.replace(old, new)
    text = re.sub(r"[\u064B-\u0652\u0670\u0640]", "", text)
    return text.strip()


TOKEN_RE = re.compile(r"[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF\w]+", re.UNICODE)


def tokenize_fa(text: str) -> List[str]:
    text = normalize_fa(text)
    return [w for w in TOKEN_RE.findall(text) if w]


def fa_join(items: Iterable[str]) -> str:
    items = [str(x) for x in items if x]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return "، ".join(items[:-1]) + " و " + items[-1]


# ---------------------------------------------------------------------------
# Fibonacci binary heartbeat
# ---------------------------------------------------------------------------

def fibonacci_binary_bits(seed: int = 2500):
    a, b = 0, 1
    mask = (1 << 64) - 1
    while True:
        a, b = b, (a + b) & mask
        bits = format(b, "064b")
        for bit in bits:
            yield int(bit)

