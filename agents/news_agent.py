"""NewsAgent — real-headline-injected AI news analysis via AIEngine."""
from __future__ import annotations

import json
import logging
import sys
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


class NewsAgent:
    """
    Fetches live RSS headlines via NewsFetcher, injects them into
    ARIA prompts, and returns structured analysis from AIEngine.
    """

    def __init__(self):
        # Lazy imports avoid circular deps and missing-package crashes at module load
        from agents.ai_engine import AIEngine
        from fetchers.news_fetcher import NewsFetcher
        self._ai      = AIEngine()
        self._fetcher = NewsFetcher()

    # ------------------------------------------------------------------
    # 1. US News
    # ------------------------------------------------------------------

    def analyse_us_news(self, period: str = "today", sources: list[str] | None = None) -> dict:
        """
        6 US market stories covering layoffs, CEO changes, earnings surprises,
        product launches, regulatory actions, M&A.
        """
        cache_key = f"news_us_{period}_{date.today()}"
        cached = _load_cache(cache_key)
        if cached:
            logger.info("[news_us] Returning cached result.")
            return cached

        headlines = self._get_headlines("us", period, sources)

        prompt = f"""You are ARIA. Today's date: {date.today()}.

LIVE HEADLINES — US MARKETS ({period.upper()}):
{headlines}

Analyse the above headlines and identify exactly 6 significant US market stories.
Cover a spread across: layoffs/workforce, CEO/executive changes, earnings surprises,
product launches/innovations, regulatory/legal actions, M&A/dealmaking.

For each story return the following structure. ARIA autonomously decides which stocks
are impacted — do NOT restrict to a fixed list; identify any relevant tickers.

Respond with ONLY valid JSON in this exact schema:
{{
  "period": "{period}",
  "market": "us",
  "stories": [
    {{
      "headline": "Concise headline (max 15 words)",
      "source": "Publication name",
      "date": "YYYY-MM-DD or 'recent'",
      "category": "layoffs|executive_change|earnings|product_launch|regulatory|m_and_a",
      "summary": "3-4 sentence deep analysis with market context.",
      "impacted_stocks": [
        {{
          "ticker": "AAPL",
          "company": "Apple Inc.",
          "signal": "bullish|bearish|neutral",
          "impact_pct": 2.5,
          "why": "One sentence on mechanism of impact."
        }}
      ],
      "aria_take": "ARIA's direct opinionated view. What should investors do?"
    }}
  ],
  "macro_mood": "risk_on|risk_off|mixed",
  "sector_rotation": "One sentence on which sectors are gaining/losing flows today."
}}"""

        result = self._call(prompt, cache_key)
        logger.info("[news_us] %d stories, provider=%s", len(result.get("stories", [])), result.get("_provider"))
        return result

    # ------------------------------------------------------------------
    # 2. Global Macro News
    # ------------------------------------------------------------------

    def analyse_global_news(self, period: str = "today", sources: list[str] | None = None) -> dict:
        """
        6 global macro stories: central banks, geopolitics, commodities,
        currency crises, trade policy.
        """
        cache_key = f"news_global_{period}_{date.today()}"
        cached = _load_cache(cache_key)
        if cached:
            logger.info("[news_global] Returning cached result.")
            return cached

        headlines = self._get_headlines("global", period, sources)

        prompt = f"""You are ARIA. Today's date: {date.today()}.

LIVE HEADLINES — GLOBAL MARKETS ({period.upper()}):
{headlines}

Identify exactly 6 significant global macro stories from the headlines above.
Cover: central bank decisions (Fed/ECB/RBI/BOJ/PBOC), geopolitical events,
commodity moves (oil/gold/copper), currency crises or moves, trade policy/tariffs,
and one wildcard macro story that most analysts are underweighting.

Respond with ONLY valid JSON:
{{
  "period": "{period}",
  "market": "global",
  "stories": [
    {{
      "headline": "Concise headline (max 15 words)",
      "source": "Publication name",
      "date": "YYYY-MM-DD or 'recent'",
      "category": "central_bank|geopolitical|commodity|currency|trade_policy|wildcard",
      "summary": "3-4 sentence analysis including historical context.",
      "cross_market_impact": {{
        "us_equities":    "Bullish/Bearish/Neutral — one sentence why.",
        "india_equities": "Bullish/Bearish/Neutral — one sentence why.",
        "commodities":    "Direction and key commodity affected.",
        "currencies":     "Key FX pairs affected and direction."
      }},
      "aria_take": "ARIA's direct view. What does this mean for portfolio positioning?"
    }}
  ],
  "dominant_theme": "The single biggest macro force driving markets today.",
  "tail_risk": "The one event that could blow up the consensus view."
}}"""

        result = self._call(prompt, cache_key)
        logger.info("[news_global] %d stories, provider=%s", len(result.get("stories", [])), result.get("_provider"))
        return result

    # ------------------------------------------------------------------
    # 3. India News
    # ------------------------------------------------------------------

    def analyse_india_news(self, period: str = "today", sources: list[str] | None = None) -> dict:
        """
        6 India-specific stories: RBI, FII/DII flows, quarterly results,
        Nifty/Sensex drivers, govt policy, sector news.
        """
        cache_key = f"news_india_{period}_{date.today()}"
        cached = _load_cache(cache_key)
        if cached:
            logger.info("[news_india] Returning cached result.")
            return cached

        headlines = self._get_headlines("india", period, sources)

        prompt = f"""You are ARIA. Today's date: {date.today()}.

LIVE HEADLINES — INDIA MARKETS ({period.upper()}):
{headlines}

Identify exactly 6 significant India market stories from the headlines above.
Cover: RBI monetary policy/liquidity actions, FII/DII flow trends, Q4/annual
results season, Nifty 50/Sensex technical drivers, government policy (PLI schemes,
capex budget, divestment), and sector-specific news (IT, banking, pharma, auto, FMCG).

Use NSE tickers with .NS suffix (e.g. RELIANCE.NS, TCS.NS, HDFCBANK.NS).

Respond with ONLY valid JSON:
{{
  "period": "{period}",
  "market": "india",
  "stories": [
    {{
      "headline": "Concise headline (max 15 words)",
      "source": "Publication name",
      "date": "YYYY-MM-DD or 'recent'",
      "category": "rbi_policy|fii_dii_flows|quarterly_results|index_driver|govt_policy|sector_news",
      "summary": "3-4 sentence analysis with Indian market context.",
      "impacted_stocks": [
        {{
          "ticker": "TCS.NS",
          "company": "Tata Consultancy Services",
          "signal": "bullish|bearish|neutral",
          "impact_pct": 1.5,
          "why": "One sentence on the mechanism."
        }}
      ],
      "aria_take": "ARIA's direct view for Indian retail/institutional investors."
    }}
  ],
  "nifty_pulse": "One sentence on Nifty 50 direction and key resistance/support.",
  "fii_dii_summary": "Current FII/DII flow posture and what it signals.",
  "rupee_view": "INR/USD outlook given today's macro backdrop."
}}"""

        result = self._call(prompt, cache_key)
        logger.info("[news_india] %d stories, provider=%s", len(result.get("stories", [])), result.get("_provider"))
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headlines(self, market: str, period: str, sources: list[str] | None) -> str:
        """Return formatted headline block for prompt injection."""
        if sources:
            articles = self._fetcher.fetch_rss(sources, max_per_source=10)
            if articles:
                return "\n".join(
                    f"- [{a['source_name']}] {a['title']} ({a['published_date']})"
                    for a in articles
                )
        ctx = self._fetcher.fetch_headlines_context(market, period)
        return ctx or "No live headlines available — use your training knowledge."

    def _call(self, prompt: str, cache_key: str) -> dict:
        logger.info("[%s] Prompt length: %d chars", cache_key, len(prompt))
        result = self._ai.sync_call(prompt)
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
