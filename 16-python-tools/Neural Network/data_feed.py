# -*- coding: utf-8 -*-
"""
دریافت پایدار داده زنده و تاریخی از بایبیت (Bybit) - نسخه requests مستقیم

چرا این نسخه به‌جای pybit؟
    خطای قبلی ("rate limit / ip from usa") در بسیاری از موارد نه یک بلاک
    واقعی جغرافیایی، بلکه واکنش WAF/CDN بایبیت به کلاینت‌های بدون هدر
    مرورگر است (مثل هدرهای پیش‌فرض pybit/urllib). با ست‌کردن User-Agent و
    Referer شبیه مرورگر واقعی، این تشخیص ربات معمولاً رفع می‌شود.

سه لایه پایداری:
  1) هدرهای مرورگر‌مانند روی یک Session مشترک (به‌جای هر بار ساخت session جدید)
  2) دامنه‌ی «چسبنده» (sticky) - آخرین دامنه‌ی موفق را برای درخواست‌های بعدی
     اول امتحان می‌کند، و فقط در صورت شکست به بعدی می‌رود.
  3) Rate limiting سمت کلاینت + backoff نمایی با cool-down بلندتر برای 403.

⚠️ اگر بعد از این تغییر هم روی همه دامنه‌ها پیام صریح «ip is from the usa»
تکرار شد، آن‌وقت واقعاً یک بلاک جغرافیایی/انطباقی از سمت بایبیت است، نه
مشکل هدر - و راه‌حلش کدنویسی نیست (باید از سروری خارج آمریکا اجرا شود یا
با پشتیبانی بایبیت هماهنگ شود یا از صرافی/دیتاپرووایدر دیگری استفاده شود).
"""

import time
import random
import logging
import threading
from datetime import datetime, timezone

import requests
import pandas as pd

logger = logging.getLogger("morindok.data_feed")

# دامنه‌های رسمی بایبیت برای چرخش خودکار (متعلق به خود بایبیت، نه پراکسی شخص‌ثالث)
BYBIT_BASE_CANDIDATES = [
    "https://api.bybit.com",
    "https://api.bytick.com",
    "https://api.bybit.kz",
    "https://api.bybit-tr.com",
]

BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.bybit.com/",
    "Origin": "https://www.bybit.com",
}


def _is_geo_or_rate_block(msg: str) -> bool:
    m = msg.lower()
    return ("403" in m) or ("rate limit" in m) or ("ip rate limit" in m) or ("usa" in m)


class BybitDataFeed:
    """
    دریافت کندل‌های OHLCV از بایبیت به‌صورت پایدار، مستقیم روی REST API عمومی V5.
    category: "linear" (پرپچوال USDT) یا "spot"
    interval: طبق مستندات Bybit V5 -> "1","3","5","15","30","60","120","240","D","W"
    """

    def __init__(self, symbol="BTCUSDT", category="linear", interval="5",
                 history_len=1000, poll_seconds=15,
                 max_retries=5, base_backoff=2.0, min_request_interval=1.2,
                 block_cooldown_base=15.0, request_timeout=10):
        self.symbol = symbol
        self.category = category
        self.interval = interval
        self.history_len = history_len
        self.poll_seconds = poll_seconds
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.min_request_interval = min_request_interval
        self.block_cooldown_base = block_cooldown_base
        self.request_timeout = request_timeout

        self.session = requests.Session()
        self.session.headers.update(BROWSER_HEADERS)

        # دامنه‌ی چسبنده: آخرین دامنه‌ی موفق را حفظ می‌کند
        self._active_base = None

        self._lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._last_request_ts = 0.0

        self._df = pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"]
        )
        self._last_update = None
        self._last_error = None
        self._connected = False

        self._stop_flag = threading.Event()
        self._thread = None

    # -------------------------------------------------------------
    def _candidate_bases(self):
        """دامنه‌ی چسبنده (اگر موفق بوده) اول، بقیه به ترتیب بعدش."""
        if self._active_base:
            rest = [b for b in BYBIT_BASE_CANDIDATES if b != self._active_base]
            return [self._active_base] + rest
        return list(BYBIT_BASE_CANDIDATES)

    # -------------------------------------------------------------
    def _throttle(self):
        """اطمینان از فاصله حداقلی بین درخواست‌ها تا لیمیت بایبیت زودتر نقض نشود."""
        with self._request_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_ts
            wait = self.min_request_interval - elapsed
            if wait > 0:
                time.sleep(wait)
            self._last_request_ts = time.monotonic()

    # -------------------------------------------------------------
    def _try_one_base(self, base, path, params):
        """یک تلاش خام روی یک دامنه مشخص. در صورت شکست، None برمی‌گرداند (نه exception)."""
        self._throttle()
        try:
            resp = self.session.get(f"{base}{path}", params=params, timeout=self.request_timeout)
            if resp.status_code == 403:
                return None, f"HTTP 403 از {base} (احتمالاً بلاک WAF/Rate-Limit/Geo)"
            resp.raise_for_status()
            data = resp.json()
            if data.get("retCode") != 0:
                return None, f"Bybit retCode={data.get('retCode')} msg={data.get('retMsg')} [{base}]"
            return data, None
        except requests.exceptions.RequestException as exc:
            return None, f"خطای شبکه روی {base}: {exc}"

    # -------------------------------------------------------------
    def _fetch_klines_raw(self, limit):
        """
        هر «دور» یعنی یک بار امتحان‌کردن همه دامنه‌های کاندید (دامنه چسبنده اول).
        اگر هیچ‌کدام جواب ندادند، طبق نوع خطا (بلاک/شبکه) صبر می‌کند و دور بعدی را
        تا max_retries بار تکرار می‌کند.
        """
        params = {
            "category": self.category,
            "symbol": self.symbol,
            "interval": self.interval,
            "limit": limit,
        }
        last_error = None
        attempt = 0
        while attempt < self.max_retries:
            attempt += 1
            any_block = False
            for base in self._candidate_bases():
                data, err = self._try_one_base(base, "/v5/market/kline", params)
                if data is not None:
                    self._active_base = base   # این دامنه را برای دفعات بعد "چسبنده" کن
                    rows = data["result"]["list"]
                    if not rows:
                        last_error = f"پاسخ خالی از {base}"
                        continue
                    return rows
                last_error = err
                if err and _is_geo_or_rate_block(err):
                    any_block = True
                logger.warning("تلاش %d/%d ناموفق روی %s: %s", attempt, self.max_retries, base, err)

            self._last_error = last_error
            if any_block:
                wait = self.block_cooldown_base * (2 ** (attempt - 1)) + random.uniform(0, 2.0)
                logger.warning("همه دامنه‌ها بلاک/محدود شدند - صبر %.1fs قبل از دور بعدی", wait)
            else:
                wait = self.base_backoff ** attempt + random.uniform(0, 1.0)
                logger.warning("خطای شبکه روی همه دامنه‌ها - صبر %.1fs قبل از دور بعدی", wait)
            time.sleep(wait)

        raise ConnectionError(
            f"دریافت داده از بایبیت پس از {self.max_retries} دور تلاش روی {len(BYBIT_BASE_CANDIDATES)} "
            f"دامنه ناموفق بود. آخرین خطا: {last_error}"
        )

    # -------------------------------------------------------------
    def _rows_to_df(self, rows):
        # بایبیت کندل‌ها را از جدید به قدیم برمی‌گرداند
        df = pd.DataFrame(
            rows,
            columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ms", utc=True)
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.sort_values("timestamp").reset_index(drop=True)
        df = df.dropna(subset=["open", "high", "low", "close"])
        return df

    # -------------------------------------------------------------
    def refresh(self):
        """یک‌بار داده را می‌گیرد و DataFrame داخلی را به‌روز می‌کند."""
        rows = self._fetch_klines_raw(self.history_len)
        df = self._rows_to_df(rows)
        with self._lock:
            self._df = df
            self._last_update = datetime.now(timezone.utc)
            self._connected = True
            self._last_error = None
        return df

    # -------------------------------------------------------------
    def get_df(self):
        with self._lock:
            return self._df.copy()

    def get_status(self):
        with self._lock:
            return {
                "connected": self._connected,
                "last_update": self._last_update,
                "last_error": self._last_error,
                "rows": len(self._df),
                "active_base": self._active_base,
            }

    # -------------------------------------------------------------
    def _loop(self):
        while not self._stop_flag.is_set():
            try:
                self.refresh()
            except Exception as exc:  # noqa: BLE001
                logger.error("حلقه پس‌زمینه دریافت داده متوقف نشد اما خطا داد: %s", exc)
                with self._lock:
                    self._connected = False
                    self._last_error = str(exc)
            self._stop_flag.wait(self.poll_seconds)

    def start(self):
        """اجرای دریافت داده در ترد پس‌زمینه (غیرمسدودکننده برای Dash)."""
        if self._thread is not None and self._thread.is_alive():
            return
        try:
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            logger.error("دریافت اولیه داده ناموفق بود، تلاش در پس‌زمینه ادامه می‌یابد: %s", exc)
            with self._lock:
                self._connected = False
                self._last_error = str(exc)
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_flag.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
