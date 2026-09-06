#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run.py — نقطه‌ی ورود اجرای ارگانیسم دیجیتال (نسخه‌ی فراآگاه/Super-Aware).

مثال‌ها:
    python run.py                          # اجرای رصدخانه‌ی Dash روی پورت 8050
    python run.py --headless               # اجرای بدون‌رابط در ترمینال
    python run.py --offline                # بدون اتصال اینترنت (کاملاً امن/آفلاین)
    python run.py --port 8060 --seed 7     # پورت و دانه‌ی تصادفی دلخواه
"""
import sys

from organism.cli import main

if __name__ == "__main__":
    sys.exit(main())
