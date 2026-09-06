"""Application configuration."""
import os

REST_CANDIDATES = ["https://api.bybit.com", "https://api.bytick.com", "https://api.bybit.kz"]
DEFAULT_SYMBOL = os.getenv("BYBIT_SYMBOL", "BTCUSDT")
DEFAULT_CATEGORY = os.getenv("BYBIT_CATEGORY", "linear")
DEFAULT_INTERVAL = os.getenv("BYBIT_INTERVAL", "15")
DEFAULT_LIMIT = 500
REFRESH_MS = 15_000
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8060"))
BG, PANEL, GRID, TEXT, MUTED = "#08111f", "#101d30", "#263750", "#e8eef7", "#91a4bd"
GOLD, UP, DOWN, CYAN = "#f2b84b", "#27c499", "#ef6b73", "#55c7e8"
GANN_ANGLES = {"1x8": 1/8, "1x4": 1/4, "1x3": 1/3, "1x2": 1/2, "1x1": 1.0, "2x1": 2.0, "3x1": 3.0, "4x1": 4.0, "8x1": 8.0}
