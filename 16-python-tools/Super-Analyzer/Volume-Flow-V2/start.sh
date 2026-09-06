#!/usr/bin/env bash
# Morindok - Bybit Volume Flow Monitor
# اجرا برای مک / لینوکس:  در ترمینال بنویسید:  bash start.sh
set -e
cd "$(dirname "$0")"

echo "============================================================"
echo "  Morindok  -  Bybit Volume Flow Monitor"
echo "  Telegram: @BITMOON618"
echo "============================================================"

PYEXE=""
if command -v python3 >/dev/null 2>&1; then
    PYEXE="python3"
elif command -v python >/dev/null 2>&1; then
    PYEXE="python"
else
    echo "[خطا] پایتون پیدا نشد. از https://www.python.org/downloads/ نصب کنید."
    exit 1
fi

if [ ! -f ".venv/bin/python" ]; then
    echo "[1/3] در حال ساخت محیط مجازی پایتون ..."
    "$PYEXE" -m venv .venv
fi

echo "[2/3] در حال بررسی و نصب کتابخانه‌ها ..."
".venv/bin/python" -m pip install --upgrade pip -q
".venv/bin/python" -m pip install -q -r requirements.txt

echo "[3/3] در حال اجرای برنامه ..."
echo "آدرس: http://127.0.0.1:8050"
( sleep 3 && (open http://127.0.0.1:8050 2>/dev/null || xdg-open http://127.0.0.1:8050 2>/dev/null || true) ) &

".venv/bin/python" app.py
