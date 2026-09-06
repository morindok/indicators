import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from record_screen import (
    WNDENUMPROC,
    find_chrome_hwnd,
    get_accurate_rect,
    get_window_title,
    grab_frame,
)

import ctypes

user32 = ctypes.windll.user32
OUTPUT = Path(__file__).with_name("tradingview_capture.png")


def find_all_chrome_windows():
    wins = []

    def collect(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        title = get_window_title(hwnd)
        low = title.lower()
        if ("chrome" in low) or ("btcusdt" in low) or ("tradingview" in low):
            wins.append((hwnd, title))
        return True

    proc = WNDENUMPROC(collect)
    user32.EnumWindows(proc, 0)
    return wins


def main():
    wins = find_all_chrome_windows()
    print(f"[OK] پنجره‌های مرورگر پیدا شده: {len(wins)}")
    for i, (h, t) in enumerate(wins):
        print(f"   [{i}] {t[:80]}")

    target = None
    for h, t in wins:
        if "btcusdt" in t.lower() or "tradingview" in t.lower():
            target = (h, t)
            break

    if not target:
        print("[!] هیچ پنجره‌ای با تب BTCUSDT/TradingView پیدا نشد.")
        if wins:
            target = wins[0]
            print(f"[!] جایگزین: {target[1][:60]}")
        else:
            sys.exit(1)

    hwnd, title = target
    try:
        user32.SetForegroundWindow(hwnd)
        time.sleep(1.2)
    except Exception as e:
        print(f"[!] فوکوس ناموفق: {e}")

    rect = get_accurate_rect(hwnd)
    frame = grab_frame(rect)
    frame.save(OUTPUT)

    print(f"[OK] کپچر شد: {OUTPUT}")
    print(f"[OK] پنجره: {title[:80]}")
    print(f"[OK] ابعاد: {frame.size[0]}x{frame.size[1]}")


if __name__ == "__main__":
    main()
