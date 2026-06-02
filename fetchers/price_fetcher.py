"""Downloads price data via yfinance with caching."""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger("aria.price_fetcher")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s  [%(levelname)s]  %(message)s", "%H:%M:%S"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

CACHE_DIR       = Path(__file__).resolve().parents[1] / "data" / "cache"
CACHE_TTL_PRICE = 1800   # 30 minutes for quote snapshots
CACHE_TTL_HIST  = 300    # 5 minutes for historical bars

# Indices shown in market snapshot
_MARKET_INDICES: dict[str, dict[str, str]] = {
    "us": {
        "S&P 500": "^GSPC",
        "NASDAQ":  "^IXIC",
        "VIX":     "^VIX",
    },
    "india": {
        "NIFTY 50": "^NSEI",
        "SENSEX":   "^BSESN",
        "INDIA VIX": "^INDIAVIX",
    },
}


class PriceFetcher:
    def __init__(self, cache: bool = True):
        self._use_cache = cache

    # ------------------------------------------------------------------
    # 1. get_prices
    # ------------------------------------------------------------------

    def get_prices(self, tickers: list[str]) -> dict[str, dict]:
        """
        Return a snapshot dict for each ticker:
            {price, change_pct, volume, high_52w, low_52w,
             market_cap, pe_ratio, sector}

        Fetches metadata via yf.Ticker (per-ticker) because yfinance's
        batch download doesn't expose fundamentals.  Results are cached
        as JSON with a 30-minute TTL.
        """
        results: dict[str, dict] = {}
        for ticker in tickers:
            try:
                results[ticker] = self._get_quote(ticker)
            except Exception as exc:
                logger.warning("Price fetch failed for %s: %s", ticker, exc)
                results[ticker] = {"error": str(exc)}
        return results

    def _get_quote(self, ticker: str) -> dict:
        cache_path = CACHE_DIR / f"quote_{ticker.replace('/', '_')}.json"

        if self._use_cache and cache_path.exists():
            if time.time() - cache_path.stat().st_mtime < CACHE_TTL_PRICE:
                return json.loads(cache_path.read_text())

        info = yf.Ticker(ticker).info

        # yfinance key names vary; fall back gracefully
        def _get(*keys, default=None):
            for k in keys:
                v = info.get(k)
                if v is not None:
                    return v
            return default

        current = _get("currentPrice", "regularMarketPrice", "previousClose")
        prev    = _get("previousClose", "regularMarketPreviousClose")
        change_pct = (
            round((current - prev) / prev * 100, 2)
            if current and prev and prev != 0 else None
        )

        quote = {
            "price":      round(float(current), 2) if current else None,
            "change_pct": change_pct,
            "volume":     _get("volume", "regularMarketVolume"),
            "high_52w":   _get("fiftyTwoWeekHigh"),
            "low_52w":    _get("fiftyTwoWeekLow"),
            "market_cap": _get("marketCap"),
            "pe_ratio":   _get("trailingPE", "forwardPE"),
            "sector":     _get("sector", "category", default="Unknown"),
        }

        if self._use_cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(quote))

        return quote

    # ------------------------------------------------------------------
    # 2. get_history
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def get_history(self, ticker: str, period: str = "1mo") -> pd.DataFrame:
        """
        Return OHLCV DataFrame for `ticker` over `period`.
        `period` accepts yfinance strings: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y.
        Result is cached as parquet with a 5-minute TTL.
        """
        cache_path = CACHE_DIR / f"hist_{ticker.replace('/', '_')}_{period}.parquet"

        if self._use_cache and cache_path.exists():
            if time.time() - cache_path.stat().st_mtime < CACHE_TTL_HIST:
                return pd.read_parquet(cache_path)

        df = yf.download(ticker, period=period, progress=False, auto_adjust=True)

        if df.empty:
            raise ValueError(f"yfinance returned no history for {ticker} ({period})")

        # Flatten MultiIndex columns produced by newer yfinance versions
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if self._use_cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cache_path)

        logger.info("History fetched: %s %s (%d bars)", ticker, period, len(df))
        return df

    # ------------------------------------------------------------------
    # 3. get_market_snapshot
    # ------------------------------------------------------------------

    def get_market_snapshot(self) -> dict:
        """
        Return current values for major US and India indices.

        Structure:
            {
              "us":    {"S&P 500":  {"price": ..., "change_pct": ...}, ...},
              "india": {"NIFTY 50": {"price": ..., "change_pct": ...}, ...},
            }
        """
        snapshot: dict[str, dict] = {}

        for region, indices in _MARKET_INDICES.items():
            snapshot[region] = {}
            for name, ticker in indices.items():
                try:
                    data = self._get_index_quote(ticker)
                    snapshot[region][name] = data
                    logger.info(
                        "Snapshot %s (%s): %s  %s%%",
                        name, ticker,
                        data.get("price", "N/A"),
                        data.get("change_pct", "N/A"),
                    )
                except Exception as exc:
                    logger.warning("Index fetch failed %s (%s): %s", name, ticker, exc)
                    snapshot[region][name] = {"error": str(exc)}

        return snapshot

    def _get_index_quote(self, ticker: str) -> dict:
        cache_path = CACHE_DIR / f"idx_{ticker.replace('^', '').replace('/', '_')}.json"

        if self._use_cache and cache_path.exists():
            if time.time() - cache_path.stat().st_mtime < CACHE_TTL_PRICE:
                return json.loads(cache_path.read_text())

        # Use Yahoo Finance chart API directly — much faster than yf.Ticker().info
        # and works reliably on cloud servers (no cookie/consent issues)
        import requests as _req
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{_req.utils.quote(ticker, safe='')}?interval=1d&range=2d"
        )
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ARIA-bot/1.0)"}
        resp = _req.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        meta = resp.json()["chart"]["result"][0]["meta"]

        current = meta.get("regularMarketPrice") or meta.get("previousClose")
        prev    = meta.get("previousClose") or meta.get("chartPreviousClose")
        change_pct = (
            round((current - prev) / prev * 100, 2)
            if current and prev and prev != 0 else None
        )

        data = {
            "price":      round(float(current), 2) if current else None,
            "change_pct": change_pct,
            "ticker":     ticker,
        }

        if self._use_cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(data))

        return data

    # ------------------------------------------------------------------
    # Legacy helper kept for backward compatibility with main.py / agents
    # ------------------------------------------------------------------

    def fetch(self, ticker: str, period_key: str = "week") -> pd.DataFrame:
        days = settings.PERIODS.get(period_key, 7)
        period = f"{days}d" if days <= 59 else f"{days // 30}mo"
        return self.get_history(ticker, period=period)

    def current_price(self, ticker: str) -> float | None:
        try:
            df = self.get_history(ticker, period="1d")
            close = df["Close"].squeeze()
            return close.iloc[-1].item()
        except Exception:
            return None


# ---------------------------------------------------------------------------
# __main__ smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    print("\n  PriceFetcher — smoke test\n" + "─" * 50)
    pf = PriceFetcher()

    print("\n  [1] Quote snapshots — AAPL, TSLA, INFY.NS")
    quotes = pf.get_prices(["AAPL", "TSLA", "INFY.NS"])
    for t, q in quotes.items():
        if "error" in q:
            print(f"  {t:12s}  ERROR: {q['error']}")
        else:
            print(
                f"  {t:12s}  ${q.get('price', 'N/A'):>10}  "
                f"{(q.get('change_pct') or 0):+.2f}%  "
                f"sector: {q.get('sector', 'N/A')}"
            )

    print("\n  [2] History — AAPL 5d")
    df = pf.get_history("AAPL", period="5d")
    print(df[["Open", "High", "Low", "Close", "Volume"]].tail(3).to_string())

    print("\n  [3] Market snapshot")
    snap = pf.get_market_snapshot()
    for region, indices in snap.items():
        print(f"\n  {region.upper()}")
        for name, data in indices.items():
            if "error" in data:
                print(f"    {name:12s}  ERROR")
            else:
                print(
                    f"    {name:12s}  {data.get('price', 'N/A'):>10}  "
                    f"{(data.get('change_pct') or 0):+.2f}%"
                )
    print()
