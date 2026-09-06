import ctypes
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import ImageGrab
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ctypes.windll.user32.SetProcessDPIAware()

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

OUTPUT = Path(__file__).with_name("screen_recording.mp4")
FPS = 12

WNDENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
)


def get_window_title(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def get_accurate_rect(hwnd):
    rect = wintypes.RECT()
    result = dwmapi.DwmGetWindowAttribute(
        hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)
    )
    if result != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def find_chrome_hwnd():
    candidates = []

    def collect(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        title = get_window_title(hwnd)
        if "chrome" in title.lower():
            candidates.append((hwnd, title))
        return True

    enum_proc = WNDENUMPROC(collect)
    user32.EnumWindows(enum_proc, 0)

    if not candidates:
        return None

    fg = user32.GetForegroundWindow()
    for hwnd, title in candidates:
        if hwnd == fg:
            return hwnd
    return candidates[0][0]


def grab_frame(rect):
    shot = ImageGrab.grab(all_screens=True)
    if rect:
        left, top, right, bottom = rect
        left = max(left, shot.getbbox()[0])
        top = max(top, shot.getbbox()[1])
        right = min(right, shot.getbbox()[2])
        bottom = min(bottom, shot.getbbox()[3])
        if right - left > 10 and bottom - top > 10:
            shot = shot.crop((left, top, right, bottom))
    frame = np.array(shot)
    return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)


def main():
    duration = None
    full_screen = "--full" in sys.argv

    for arg in sys.argv[1:]:
        if arg.startswith("--dur="):
            duration = float(arg.split("=")[1])

    if full_screen:
        rect = None
        title = "کل صفحه"
    else:
        hwnd = find_chrome_hwnd()
        if hwnd:
            rect = get_accurate_rect(hwnd)
            title = get_window_title(hwnd)
        else:
            rect = None
            title = "کل صفحه (پنجره کروم پیدا نشد)"

    first = grab_frame(rect)
    h, w = first.shape[:2]

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(OUTPUT), fourcc, FPS, (w, h))

    print(f"[REC] در حال ضبط از: {title}")
    print(f"[REC] رزولوشن: {w}x{h} | فریم‌برثانیه: {FPS}")
    if duration:
        print(f"[REC] مدت ضبط: {duration} ثانیه")
    else:
        print("[REC] برای توقف ضبط: Ctrl+C")

    frames_written = 0
    start = time.perf_counter()

    try:
        while True:
            elapsed = time.perf_counter() - start
            if duration and elapsed >= duration:
                break

            writer.write(grab_frame(rect))
            frames_written += 1

            wait = (1.0 / FPS) - (time.perf_counter() - start - frames_written * (1.0 / FPS))
            if wait > 0:
                time.sleep(wait)

            if not duration and int(elapsed) % 10 == 0:
                mins, secs = divmod(int(elapsed), 60)
                print(f"\r[REC] {mins:02d}:{secs:02d}", end="", flush=True)

    except KeyboardInterrupt:
        pass

    writer.release()

    size_mb = OUTPUT.stat().st_size / (1024 * 1024)
    total = time.perf_counter() - start
    print(f"\n[OK] ضبط تمام شد: {OUTPUT}")
    print(f"[OK] مدت: {total:.1f} ثانیه | فریم‌ها: {frames_written} | حجم: {size_mb:.2f} MB")


if __name__ == "__main__":
    main()
