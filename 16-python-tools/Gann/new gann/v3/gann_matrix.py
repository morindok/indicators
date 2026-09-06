"""Layered adaptive Gann square calculations."""
import numpy as np
from config import GANN_ANGLES

class GannMatrix:
    def __init__(self, layers=(1, 2, 3, 4), angle_map=None):
        self.layers = tuple(layers)
        self.angle_map = angle_map or GANN_ANGLES

    @staticmethod
    def _step(df):
        closes = df.close.to_numpy(float)
        if len(closes) < 3: return max(float(closes[-1]) * .01, 1e-8)
        return max(float(np.median(np.abs(np.diff(closes)))), float(closes[-1]) * 0.0001)

    def calculate(self, df, chrono_levels=()):
        if df.empty: return {"origin": 0, "step": 0, "layers": [], "levels": []}
        origin = float(df.close.iloc[-1]); step = self._step(df)
        out_layers = []; all_levels = []
        # Every layer is a square around the current chrono origin, so a tick
        # update changes the grid while preserving its measurable scale.
        for layer in self.layers:
            radius = layer * 8
            vals = sorted(set(round(origin + i * step, 10) for i in range(-radius, radius + 1)))
            out_layers.append({"layer": layer, "radius": radius, "levels": vals})
            all_levels.extend(vals)
        all_levels.extend(float(x) for x in chrono_levels)
        return {"origin": origin, "step": step, "layers": out_layers, "levels": sorted(set(all_levels))}

    def angle_lines(self, df, matrix):
        if df.empty: return []
        origin = matrix["origin"]; step = matrix["step"]
        x0 = df.ts.iloc[-min(len(df), 89)]
        x1 = df.ts.iloc[-1]
        bars = max((x1-x0).total_seconds() / 60, 1)
        lines = []
        for name, slope in self.angle_map.items():
            delta = slope * step * min(bars / 15, 30)
            lines.append({"name": name, "x0": x0, "x1": x1, "y0": origin-delta, "y1": origin})
            lines.append({"name": name, "x0": x0, "x1": x1, "y0": origin+delta, "y1": origin})
        return lines

    def support_resistance(self, df, matrix, tolerance=2):
        if df.empty: return [], []
        levels = np.array(matrix["levels"]); last = matrix["origin"]
        nearby = levels[np.abs(levels-last) <= matrix["step"]*24]
        supports = sorted((float(x) for x in nearby if x < last), reverse=True)[:5]
        resistances = sorted(float(x) for x in nearby if x > last)[:5]
        return supports, resistances
