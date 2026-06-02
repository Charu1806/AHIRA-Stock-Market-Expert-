"""NewsAgent — real-headline-injected AI news analysis via AIEngine."""
from __future__ import annotations

import json
import logging
import time
from datetime import date
from pathlib import Path

logger = logging.getLogger("aria.news_agent")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s  [%(levelname)s]  %(message)s", "%H:%M:%S"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"
CACHE_TTL  = 3600  # 1 hour

# Max headlines injected per prompt — keeps prompt under ~800 tokens
_MAX_HEADLINES = 12


class NewsAgent:
    def __init__(self):
        from agents.ai_engine import AIEngine
        from fetchers.news_fetcher import NewsFetcher
        self._ai      = AIEngine()
        self._fetcher = NewsFetcher()

    # ------------------------------------------------------------------
    # 1. US News  (~500 prompt tokens + ~900 response tokens = ~1400 total)
    # ------------------------------------------------------------------

    def analyse_us_news(self, period: str = "today", sources: list[str] | None = None) -> dict:
        cache_key = f"news_us_{period}_{date.today()}"
        cached = _load_cache(cache_key)
        if cached:
            logger.info("[news_us] cache hit")
            return cached

        headlines = self._get_headlines("us", period, sources)

        prompt = f"""ARIA. Date:{date.today()} Period:{period}

HEADLINES:
{headlines}

Return JSON — 6 US market stories (layoffs,exec_change,earnings,product_launch,regulatory,m_and_a):
{{"period":"{period}","market":"us","macro_mood":"risk_on|risk_off|mixed","sector_rotation":"<1 sentence>",
"stories":[{{"headline":"<15 words>","source":"<name>","date":"YYYY-MM-DD","category":"<type>",
"summary":"<3 sentences>","aria_take":"<1 opinionated sentence>",
"impacted_stocks":[{{"ticker":"<SYM>","company":"<name>","signal":"bullish|bearish|neutral","impact_pct":0.0,"why":"<1 sentence>"}}]}}]}}"""

        result = self._call(prompt, cache_key)
        logger.info("[news_us] %d stories provider=%s", len(result.get("stories", [])), result.get("_provider"))
        return result

    # ------------------------------------------------------------------
    # 2. Global Macro  (~500 prompt tokens + ~900 response = ~1400 total)
    # ------------------------------------------------------------------

    def analyse_global_news(self, period: str = "today", sources: list[str] | None = None) -> dict:
        cache_key = f"news_global_{period}_{date.today()}"
        cached = _load_cache(cache_key)
        if cached:
            logger.info("[news_global] cache hit")
            return cached

        headlines = self._get_headlines("global", period, sources)

        prompt = f"""ARIA. Date:{date.today()} Period:{period}

HEADLINES:
{headlines}

Return JSON — 6 global macro stories (central_bank,geopolitical,commodity,currency,trade_policy,wildcard):
{{"period":"{period}","market":"global","dominant_theme":"<1 sentence>","tail_risk":"<1 sentence>",
"stories":[{{"headline":"<15 words>","source":"<name>","date":"YYYY-MM-DD","category":"<type>",
"summary":"<3 sentences>","aria_take":"<1 opinionated sentence>",
"cross_market_impact":{{"us_equities":"<Bullish/Bearish/Neutral — why>","india_equities":"<same>","commodities":"<direction>","currencies":"<FX pairs>"}}}}]}}"""

        result = self._call(prompt, cache_key)
        logger.info("[news_global] %d stories provider=%s", len(result.get("stories", [])), result.get("_provider"))
        return result

    # ------------------------------------------------------------------
    # 3. India News  (~500 prompt tokens + ~900 response = ~1400 total)
    # ------------------------------------------------------------------

    def analyse_india_news(self, period: str = "today", sources: list[str] | None = None) -> dict:
        cache_key = f"news_india_{period}_{date.today()}"
        cached = _load_cache(cache_key)
        if cached:
            logger.info("[news_india] cache hit")
            return cached

        headlines = self._get_headlines("india", period, sources)

        prompt = f"""ARIA. Date:{date.today()} Period:{period}

HEADLINES:
{headlines}

Return JSON — 6 India market stories (rbi_policy,fii_dii_flows,quarterly_results,index_driver,govt_policy,sector_news).
Use NSE tickers with .NS suffix.
{{"period":"{period}","market":"india","nifty_pulse":"<1 sentence>","fii_dii_summary":"<1 sentence>","rupee_view":"<1 sentence>",
"stories":[{{"headline":"<15 words>","source":"<name>","date":"YYYY-MM-DD","category":"<type>",
"summary":"<3 sentences>","aria_take":"<1 opinionated sentence>",
"impacted_stocks":[{{"ticker":"TCS.NS","company":"<name>","signal":"bullish|bearish|neutral","impact_pct":0.0,"why":"<1 sentence>"}}]}}]}}"""

        result = self._call(prompt, cache_key)
        logger.info("[news_india] %d stories provider=%s", len(result.get("stories", [])), result.get("_provider"))
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headlines(self, market: str, period: str, sources: list[str] | None) -> str:
        """Inject at most _MAX_HEADLINES titles — keeps prompt lean."""
        if sources:
            articles = self._fetcher.fetch_rss(sources, max_per_source=4)
        else:
            from config import settings
            urls = list(settings.get_active_sources(market).values())
            articles = self._fetcher.fetch_rss(urls, max_per_source=3)

        if not articles:
            return "No live headlines — use training knowledge."

        # Title only (no date/source in body — saves ~15 tokens per headline)
        lines = [f"- {a['title']}" for a in articles[:_MAX_HEADLINES]]
        return "\n".join(lines)

    def _call(self, prompt: str, cache_key: str) -> dict:
        logger.info("[%s] ~%d tokens", cache_key, len(prompt) // 4)
        result = self._ai.sync_call(prompt, max_tokens=1200)
        data   = result["data"]
        data["_provider"] = result["provider"]
        _save_cache(cache_key, data)
        return data


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"

def _load_cache(key: str) -> dict | None:
    p = _cache_path(key)
    if p.exists() and (time.time() - p.stat().st_mtime) < CACHE_TTL:
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    return None

def _save_cache(key: str, data: dict) -> None:
    try:
        _cache_path(key).write_text(json.dumps(data, indent=2))
    except Exception as exc:
        logger.warning("Cache write failed for %s: %s", key, exc)
