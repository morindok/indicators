import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ctypes.windll.user32.SetProcessDPIAware()

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

OUTPUT = Path(__file__).with_name("screen_share.png")

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


def main():
    full_screen = "--full" in sys.argv

    if full_screen:
        rect = None
        hwnd = None
    else:
        hwnd = find_chrome_hwnd()
        rect = get_accurate_rect(hwnd) if hwnd else None

    shot = ImageGrab.grab(all_screens=True)

    if rect:
        left, top, right, bottom = rect
        left = max(left, shot.getbbox()[0])
        top = max(top, shot.getbbox()[1])
        right = min(right, shot.getbbox()[2])
        bottom = min(bottom, shot.getbbox()[3])
        if right - left > 10 and bottom - top > 10:
            shot = shot.crop((left, top, right, bottom))

    shot.save(OUTPUT)

    if hwnd:
        print(f"[OK] پنجره کروم پیدا شد: {get_window_title(hwnd)}")
    else:
        print("[!] پنجره کروم فعال پیدا نشد؛ کل صفحه ذخیره شد.")

    print(f"[OK] اسکرین‌شات ذخیره شد: {OUTPUT}")
    print(f"[OK] ابعاد تصویر: {shot.size[0]}x{shot.size[1]}")


if __name__ == "__main__":
    main()
