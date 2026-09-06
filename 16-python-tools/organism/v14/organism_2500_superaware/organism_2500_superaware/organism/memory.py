"""
organism.memory

حافظه‌ی کوتاه‌مدت.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional

from .utils import utc_iso

from .utils import utc_iso

class ShortTermMemory:
    def __init__(self, capacity: int = 48):
        self.items: deque = deque(maxlen=capacity)

    def add(self, item: Any) -> None:
        self.items.append({"ts": utc_iso(), "item": item})

    def recent(self, n: int = 12) -> List[Dict[str, Any]]:
        return list(self.items)[-max(0, int(n)):]

    def focus(self) -> Optional[Dict[str, Any]]:
        return self.items[-1] if self.items else None


# ---------------------------------------------------------------------------
# Digital senses
# ---------------------------------------------------------------------------
