"""
organism.cli

رابط خط فرمان: اجرای بدون‌رابط، گسترش سورس، ورودی اصلی.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional

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

from .utils import APP_NAME, stable_hash, utc_iso

from .organism_core import Organism2500
from .visualization import build_dash


# ---------------------------------------------------------------------------
# Headless mode
# ---------------------------------------------------------------------------

def run_headless(organism: Organism2500, print_every: float = 5.0) -> None:
    print("ORGANISM-2500 (Super-Aware Edition) is alive in headless mode. Press Ctrl+C to stop.")
    try:
        while organism.running:
            time.sleep(max(0.5, print_every))
            thoughts = organism.recent_thoughts(1)
            snap = organism.snapshot()
            sa = snap.get("super_awareness", {})
            thought = thoughts[-1] if thoughts else "..."
            print(
                f"[{utc_iso()}] "
                f"heart={snap['heart']['bpm']:.1f} "
                f"emotion={snap['dominant_emotion']} "
                f"action={snap['action']} "
                f"awareness={snap['awareness_level']:.2f} "
                f"consciousness={sa.get('consciousness_index', 0.0):.3f} "
                f"phi={sa.get('last_report', {}).get('phi_proxy', 0.0):.3f} "
                f"unity={snap['unity_score']:.2f} "
                f"eloquence={snap['eloquence']:.2f} "
                f"concepts={snap['concept_count']} "
                f"thought={thought}"
            )
    except KeyboardInterrupt:
        organism.stop()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--seed", type=int, default=2500, help="Genome seed")
    parser.add_argument("--db", type=str, default="organism2500.sqlite3", help="SQLite database path")
    parser.add_argument("--offline", action="store_true", help="Disable internet learning")
    parser.add_argument("--port", type=int, default=8050, help="Dash port")
    parser.add_argument("--interval", type=float, default=0.35, help="Organism tick interval")
    parser.add_argument("--headless", action="store_true", help="Run without Dash UI")
    parser.add_argument("--print-every", type=float, default=5.0, help="Headless print interval")
    args = parser.parse_args(argv)

    organism = Organism2500(seed=args.seed, db_path=args.db, offline=args.offline)
    organism.start_background(interval=args.interval)

    if DASH_AVAILABLE and not args.headless:
        app = build_dash(organism)
        print(f"Cosmic Observatory: http://127.0.0.1:{args.port}")
        app.run(host="127.0.0.1", port=args.port, debug=True, use_reloader=False)
    else:
        run_headless(organism, print_every=args.print_every)

    return 0


# MAIN_GUARD_BEGIN
if __name__ == "__main__":
    sys.exit(main())