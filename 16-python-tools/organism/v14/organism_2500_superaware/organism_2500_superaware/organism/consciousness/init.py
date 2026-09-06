"""
organism.consciousness

بسته‌ی فراآگاهی: پیاده‌سازی ماژولار پنج نظریه‌ی علم شناخت درباره‌ی آگاهی.
"""
from .attention import AttentionCandidate, AttentionSystem
from .workspace import GlobalWorkspace, WorkspaceProposal
from .integration import IntegratedInformationEstimator
from .metacognition import HigherOrderThoughtEngine
from .predictive import PredictiveProcessingEngine
from .homeostasis import EmbodimentHomeostasis
from .core import SuperAwarenessCore

__all__ = [
    "AttentionCandidate",
    "AttentionSystem",
    "GlobalWorkspace",
    "WorkspaceProposal",
    "IntegratedInformationEstimator",
    "HigherOrderThoughtEngine",
    "PredictiveProcessingEngine",
    "EmbodimentHomeostasis",
    "SuperAwarenessCore",
]
