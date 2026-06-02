"""Fetches and normalises RSS news articles."""
from __future__ import annotations

import json
import logging
import re
import string
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import feedparser
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger("aria.news_fetcher")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s  [%(levelname)s]  %(message)s", "%H:%M:%S"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"
CACHE_TTL_SECONDS = 900  # 15 minutes

# ---------------------------------------------------------------------------
# Ticker reference lists
# ---------------------------------------------------------------------------

_SP500_TICKERS: list[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA", "BRK.B", "AVGO",
    "LLY", "JPM", "UNH", "XOM", "V", "MA", "JNJ", "PG", "HD", "COST",
    "MRK", "ABBV", "CVX", "BAC", "CRM", "NFLX", "AMD", "PEP", "KO", "TMO",
    "ACN", "LIN", "MCD", "CSCO", "ADBE", "WMT", "ABT", "TXN", "DHR", "NKE",
    "ORCL", "QCOM", "PM", "INTC", "NEE", "RTX", "AMGN", "IBM", "CAT", "HON",
    "GE", "INTU", "SPGI", "AMAT", "LOW", "UNP", "BKNG", "GS", "MS", "AXP",
    "MDT", "T", "VRTX", "ISRG", "SYK", "GILD", "ETN", "PLD", "CI", "ADI",
    "DE", "REGN", "PANW", "MU", "LRCX", "KLAC", "SNPS", "CDNS", "BSX", "BLK",
    "CB", "C", "WFC", "USB", "MMC", "PNC", "TJX", "SO", "DUK", "MO",
    "ZTS", "CME", "AON", "MCO", "ITW", "APD", "ECL", "SHW", "NSC", "EMR",
]

# Company name → ticker mapping for text scanning (US)
_SP500_NAMES: dict[str, str] = {
    "apple": "AAPL", "microsoft": "MSFT", "nvidia": "NVDA", "amazon": "AMZN",
    "meta": "META", "facebook": "META", "alphabet": "GOOGL", "google": "GOOGL",
    "tesla": "TSLA", "berkshire": "BRK.B", "broadcom": "AVGO", "eli lilly": "LLY",
    "jpmorgan": "JPM", "jp morgan": "JPM", "unitedhealth": "UNH", "exxon": "XOM",
    "visa": "V", "mastercard": "MA", "johnson & johnson": "JNJ", "procter": "PG",
    "home depot": "HD", "costco": "COST", "merck": "MRK", "abbvie": "ABBV",
    "chevron": "CVX", "bank of america": "BAC", "salesforce": "CRM", "netflix": "NFLX",
    "pepsi": "PEP", "coca-cola": "KO", "coca cola": "KO", "walmart": "WMT",
    "intel": "INTC", "qualcomm": "QCOM", "oracle": "ORCL", "cisco": "CSCO",
    "adobe": "ADBE", "advanced micro": "AMD", "goldman sachs": "GS", "morgan stanley": "MS",
    "american express": "AXP", "blackrock": "BLK", "citigroup": "C", "wells fargo": "WFC",
}

_NIFTY50_TICKERS: list[str] = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "TITAN.NS",
    "BAJFINANCE.NS", "HCLTECH.NS", "WIPRO.NS", "ULTRACEMCO.NS", "NESTLEIND.NS",
    "SUNPHARMA.NS", "POWERGRID.NS", "NTPC.NS", "TECHM.NS", "ONGC.NS",
    "TATAMOTORS.NS", "TATASTEEL.NS", "M&M.NS", "ADANIENT.NS", "ADANIPORTS.NS",
    "BAJAJFINSV.NS", "JSWSTEEL.NS", "COALINDIA.NS", "DIVISLAB.NS", "DRREDDY.NS",
    "CIPLA.NS", "EICHERMOT.NS", "HEROMOTOCO.NS", "APOLLOHOSP.NS", "SBILIFE.NS",
    "HDFCLIFE.NS", "INDUSINDBK.NS", "BPCL.NS", "GRASIM.NS", "UPL.NS",
    "BRITANNIA.NS", "TATACONSUM.NS", "SHRIRAMFIN.NS", "BAJAJ-AUTO.NS", "BEL.NS",
]

_NIFTY_NAMES: dict[str, str] = {
    "reliance": "RELIANCE.NS", "tcs": "TCS.NS", "tata consultancy": "TCS.NS",
    "hdfc bank": "HDFCBANK.NS", "infosys": "INFY.NS", "icici bank": "ICICIBANK.NS",
    "hindustan unilever": "HINDUNILVR.NS", "itc": "ITC.NS", "state bank": "SBIN.NS",
    "sbi": "SBIN.NS", "airtel": "BHARTIARTL.NS", "bharti": "BHARTIARTL.NS",
    "kotak": "KOTAKBANK.NS", "larsen": "LT.NS", "l&t": "LT.NS",
    "axis bank": "AXISBANK.NS", "asian paints": "ASIANPAINT.NS", "maruti": "MARUTI.NS",
    "titan": "TITAN.NS", "bajaj finance": "BAJFINANCE.NS", "hcl": "HCLTECH.NS",
    "wipro": "WIPRO.NS", "nestle india": "NESTLEIND.NS", "sun pharma": "SUNPHARMA.NS",
    "ongc": "ONGC.NS", "tata motors": "TATAMOTORS.NS", "tata steel": "TATASTEEL.NS",
    "mahindra": "M&M.NS", "adani": "ADANIENT.NS", "jsw steel": "JSWSTEEL.NS",
    "coal india": "COALINDIA.NS", "dr reddy": "DRREDDY.NS", "cipla": "CIPLA.NS",
}

_TICKER_SETS: dict[str, list[str]] = {
    "us":     _SP500_TICKERS,
    "india":  _NIFTY50_TICKERS,
    "global": _SP500_TICKERS + _NIFTY50_TICKERS,
}

_NAME_MAPS: dict[str, dict[str, str]] = {
    "us":     _SP500_NAMES,
    "india":  _NIFTY_NAMES,
    "global": {**_SP500_NAMES, **_NIFTY_NAMES},
}


# ---------------------------------------------------------------------------
# NewsFetcher
# ---------------------------------------------------------------------------

class NewsFetcher:
    def __init__(self, cache: bool = True):
        self._use_cache = cache

    # ------------------------------------------------------------------
    # 1. fetch_rss
    # ------------------------------------------------------------------

    def fetch_rss(self, sources: list[str], max_per_source: int = 8) -> list[dict]:
        """
        Fetch RSS feeds from a list of URLs.

        Returns normalised dicts:
            {title, summary, url, published_date, source_name}

        Bad feeds are skipped with a warning; duplicates (by normalised
        title) are removed.
        """
        all_articles: list[dict] = []

        for url in sources:
            try:
                articles = self._fetch_one(url, max_per_source)
                all_articles.extend(articles)
                logger.info("Fetched %d articles from %s", len(articles), _domain(url))
            except Exception as exc:
                logger.warning("Skipping feed %s — %s", url, exc)

        return self._dedup(all_articles)

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _fetch_one(self, url: str, max_per_source: int) -> list[dict]:
        cache_key = re.sub(r"[^\w]", "_", url)[:80]
        cache_path = CACHE_DIR / f"rss_{cache_key}.json"

        if self._use_cache and cache_path.exists():
            if time.time() - cache_path.stat().st_mtime < CACHE_TTL_SECONDS:
                return self._rehydrate(json.loads(cache_path.read_text()))

        feed = feedparser.parse(url)

        if feed.bozo and not feed.entries:
            raise ConnectionError(f"feedparser bozo error: {feed.bozo_exception}")

        source_name = feed.feed.get("title", _domain(url))
        articles: list[dict] = []

        for entry in feed.entries[:max_per_source]:
            pub = self._parse_date(entry)
            articles.append({
                "title":          _clean_html(entry.get("title", "")).strip(),
                "summary":        _clean_html(entry.get("summary", entry.get("description", ""))).strip(),
                "url":            entry.get("link", ""),
                "published_date": pub.strftime("%Y-%m-%d %H:%M UTC") if pub else "unknown",
                "source_name":    source_name,
                "_pub_dt":        pub,
            })

        if self._use_cache and articles:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            # Store ISO string; _pub_dt is runtime-only, exclude from cache
            serialisable = [{k: v for k, v in a.items() if k != "_pub_dt"} for a in articles]
            cache_path.write_text(json.dumps(serialisable, default=str))

        return articles

    # ------------------------------------------------------------------
    # 2. fetch_headlines_context
    # ------------------------------------------------------------------

    def fetch_headlines_context(self, market: str = "global", period: str = "today") -> str:
        """
        Return a formatted multi-line string of recent headlines ready to
        inject directly into an LLM prompt.

        Format per line:
            - [SOURCE NAME] Headline text (YYYY-MM-DD HH:MM UTC)
        """
        sources_dict = settings.get_active_sources(market)
        urls = list(sources_dict.values())
        days = settings.PERIODS.get(period, 1)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        articles = self.fetch_rss(urls, max_per_source=10)

        # Filter by period
        filtered = [
            a for a in articles
            if a.get("_pub_dt") is None or a["_pub_dt"] >= cutoff
        ]

        if not filtered:
            return f"No recent headlines found for market={market}, period={period}."

        lines = [
            f"- [{a['source_name'].upper()}] {a['title']} ({a['published_date']})"
            for a in filtered
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 3. extract_tickers_mentioned
    # ------------------------------------------------------------------

    def extract_tickers_mentioned(self, text: str, market: str = "us") -> list[str]:
        """
        Scan `text` for ticker symbols and company names.
        Returns a deduplicated list of matching tickers for the given market.
        """
        tickers = _TICKER_SETS.get(market, _SP500_TICKERS)
        name_map = _NAME_MAPS.get(market, _SP500_NAMES)
        found: set[str] = set()
        text_lower = text.lower()

        # Match bare ticker symbols (word-boundary aware, upper-case in source)
        for ticker in tickers:
            # strip exchange suffix for matching (.NS, .BO)
            symbol = ticker.split(".")[0]
            if re.search(rf"\b{re.escape(symbol)}\b", text):
                found.add(ticker)

        # Match company names
        for name, ticker in name_map.items():
            if name in text_lower:
                found.add(ticker)

        return sorted(found)

    # ------------------------------------------------------------------
    # Legacy helper kept for backward compatibility with main.py
    # ------------------------------------------------------------------

    def fetch(self, source_filter: str = "all", days: int = 1) -> list[dict]:
        sources_dict = settings.get_active_sources(source_filter)
        articles = self.fetch_rss(list(sources_dict.values()), max_per_source=8)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return [
            a for a in articles
            if a.get("_pub_dt") is None or a["_pub_dt"] >= cutoff
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dedup(articles: list[dict]) -> list[dict]:
        """Remove duplicate articles by normalised title."""
        seen: set[str] = set()
        unique: list[dict] = []
        for art in articles:
            key = _normalise_title(art.get("title", ""))
            if key and key not in seen:
                seen.add(key)
                unique.append(art)
        return unique

    @staticmethod
    def _rehydrate(articles: list[dict]) -> list[dict]:
        """Re-attach _pub_dt datetime from published_date string after cache load."""
        for a in articles:
            pd_str = a.get("published_date", "")
            try:
                a["_pub_dt"] = datetime.strptime(pd_str, "%Y-%m-%d %H:%M UTC").replace(
                    tzinfo=timezone.utc
                )
            except (ValueError, TypeError):
                a["_pub_dt"] = None
        return articles

    @staticmethod
    def _parse_date(entry) -> datetime | None:
        for field in ("published_parsed", "updated_parsed"):
            val = entry.get(field)
            if val:
                try:
                    return datetime(*val[:6], tzinfo=timezone.utc)
                except Exception:
                    pass
        return None


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------

def _domain(url: str) -> str:
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else url

def _normalise_title(title: str) -> str:
    t = title.lower()
    t = t.translate(str.maketrans("", "", string.punctuation))
    return re.sub(r"\s+", " ", t).strip()

def _clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


# ---------------------------------------------------------------------------
# __main__ smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    TEST_FEEDS = [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069",
    ]

    print("\n  NewsFetcher — smoke test\n" + "─" * 50)
    fetcher = NewsFetcher()

    for url in TEST_FEEDS:
        articles = fetcher.fetch_rss([url], max_per_source=2)
        domain = _domain(url)
        print(f"\n  [{domain}]")
        if not articles:
            print("    (no articles returned)")
        for art in articles[:2]:
            print(f"    • {art['title'][:80]}")
            print(f"      {art['published_date']}  —  {art['source_name']}")

    print("\n" + "─" * 50)
    print("  Ticker extraction test:")
    sample = "Apple and Tesla shares surged as NVDA reported strong earnings. RELIANCE.NS also rose."
    for market in ("us", "india", "global"):
        tickers = fetcher.extract_tickers_mentioned(sample, market)
        print(f"  {market:8s} → {tickers}")

    print("\n  Headlines context (us / today):")
    ctx = fetcher.fetch_headlines_context("us", "today")
    print("\n".join(ctx.split("\n")[:5]))
    print("  …\n")
