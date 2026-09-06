"""Bybit V5 public market connector with endpoint failover."""
import requests
import pandas as pd
from config import REST_CANDIDATES

class BybitConnector:
    def __init__(self, timeout=10):
        self.timeout = timeout
        self.active = None
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "GannChronoDash/1.0", "Accept": "application/json", "Referer": "https://www.bybit.com/"})

    def _get(self, path, params):
        bases = ([self.active] if self.active else []) + [x for x in REST_CANDIDATES if x != self.active]
        for base in bases:
            try:
                r = self.session.get(base + path, params=params, timeout=self.timeout)
                if r.status_code in (403, 451):
                    continue
                r.raise_for_status()
                data = r.json()
                if data.get("retCode") == 0:
                    self.active = base
                    return data
            except (requests.RequestException, ValueError):
                continue
        return None

    def klines(self, symbol, interval, category="linear", limit=500):
        data = self._get("/v5/market/kline", {"category": category, "symbol": symbol.upper(), "interval": interval, "limit": min(int(limit), 1000)})
        rows = (data or {}).get("result", {}).get("list", [])
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
        df["ts"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms", utc=True).dt.tz_localize(None)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.sort_values("ts").dropna().reset_index(drop=True)
