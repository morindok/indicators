"""Chrono-Gann timing engine: turns price history into adaptive time/price anchors."""
import numpy as np
import pandas as pd

class ChronoEngine:
    def __init__(self, periods=(8, 13, 21, 34, 55, 89)):
        self.periods = tuple(periods)

    def anchors(self, df, lookback=144):
        if df.empty:
            return []
        src = df.tail(lookback)
        hi = float(src.high.max()); lo = float(src.low.min())
        # The latest close is the active chrono origin; each Fibonacci timing ring
        # projects a price band from the observed range.
        close = float(df.close.iloc[-1])
        span = max(hi - lo, close * 1e-6)
        levels = []
        for p in self.periods:
            levels.extend([close + span * (p / 144), close - span * (p / 144)])
        return sorted(set(round(x, 10) for x in levels if x > 0))

    def timing_marks(self, df, count=5):
        if df.empty: return []
        step = max(1, len(df) // 12)
        return [df.ts.iloc[min(len(df)-1, len(df)-1-i*step)] for i in range(count)]
