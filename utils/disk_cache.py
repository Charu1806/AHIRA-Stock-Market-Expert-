"""
Shared disk cache utility for the dashboard.
Cache files are named:  data/cache/{key}_{YYYY-MM-DD}.json
They are valid for the entire calendar day — no TTL arithmetic needed.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"

# Maps dashboard tab key → the agent cache-key prefix
# These must match the keys used inside each agent's _save_cache() call.
_TAB_TO_CACHE: dict[str, list[str]] = {
    "news_world":   [
        "news_us_today_{date}",
        "news_global_today_{date}",
    ],
    "india_news":   ["news_india_today_{date}"],
    "us_stocks":    ["watchlist_us_today_{date}"],
    "india_stocks": ["watchlist_india_today_{date}"],
    "lesson":       ["lesson_{date}"],
}


def today() -> str:
    return str(date.today())


def cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


def load_today(cache_key: str) -> dict | None:
    """Load a single agent cache file if it was written today."""
    p = cache_path(cache_key)
    if not p.exists():
        return None
    # Date is encoded in the filename — if the file exists it's today's
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def is_cached_today(tab: str, period: str = "today") -> bool:
    """Return True if ALL cache files for this tab exist for today."""
    keys = _tab_keys(tab, period)
    return all(cache_path(k).exists() for k in keys)


def load_tab(tab: str, period: str = "today") -> dict | None:
    """
    Load all cache files for a tab and merge them into one dict.
    Returns None if any file is missing.
    """
    keys = _tab_keys(tab, period)
    results = []
    for k in keys:
        data = load_today(k)
        if data is None:
            return None
        results.append(data)

    if tab == "news_world":
        return {"us": results[0], "global": results[1]}
    return results[0]


def cache_written_at(tab: str, period: str = "today") -> str:
    """Human-readable time the cache was last written, e.g. '09:14 AM'."""
    keys = _tab_keys(tab, period)
    for k in keys:
        p = cache_path(k)
        if p.exists():
            import datetime as _dt
            mtime = _dt.datetime.fromtimestamp(p.stat().st_mtime)
            return mtime.strftime("%I:%M %p")
    return "today"


def _tab_keys(tab: str, period: str) -> list[str]:
    templates = _TAB_TO_CACHE.get(tab, [])
    d = today()
    return [t.replace("{date}", d).replace("today", period).replace(f"_{period}_{d}", f"_{period}_{d}") for t in templates]
