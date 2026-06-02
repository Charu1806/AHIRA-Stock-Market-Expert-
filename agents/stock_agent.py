"""StockAgent — AI-driven watchlist generation + technical analysis via AIEngine."""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger("aria.stock_agent")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s  [%(levelname)s]  %(message)s", "%H:%M:%S"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"
CACHE_TTL  = 3600  # 1 hour


class StockAgent:
    """
    AI-curated watchlists (via AIEngine) + technical indicator calculations
    (pure pandas — no AI needed).
    """

    def __init__(self):
        from agents.ai_engine import AIEngine
        from fetchers.news_fetcher import NewsFetcher
        from fetchers.price_fetcher import PriceFetcher
        self._ai      = AIEngine()
        self._fetcher = NewsFetcher()
        self._prices  = PriceFetcher()

    # ------------------------------------------------------------------
    # 1. US Watchlist
    # ------------------------------------------------------------------

    def get_us_watchlist(self, period: str = "today") -> dict:
        """
        ARIA autonomously selects 10 US stocks (5 trending up, 5 down)
        based on current earnings cycle, sector momentum, and macro environment.
        No hardcoded ticker list — AI decides what matters right now.
        """
        cache_key = f"watchlist_us_{period}_{date.today()}"
        cached = _load_cache(cache_key)
        if cached:
            logger.info("[watchlist_us] Returning cached result.")
            return cached

        headlines = self._fetcher.fetch_headlines_context("us", period)
        snapshot  = self._prices.get_market_snapshot()
        us_snap   = snapshot.get("us", {})

        market_context = "\n".join(
            f"  {name}: {d.get('price', 'N/A')}  ({d.get('change_pct', 0):+.2f}%)"
            for name, d in us_snap.items() if "error" not in d
        )

        prompt = f"""You are ARIA. Today: {date.today()}.

LIVE US MARKET LEVELS:
{market_context}

LIVE HEADLINES:
{headlines}

Based on the above live data, select exactly 10 US stocks that matter RIGHT NOW:
- 5 stocks trending UP (catalysts, momentum, earnings beats, sector tailwinds)
- 5 stocks trending DOWN (misses, leadership issues, sector headwinds, macro pressure)

Do NOT use a fixed list. Pick based on current earnings cycle, Fed policy backdrop,
sector rotation, and news flow. Think like a hedge fund PM building a daily watchlist.

Respond with ONLY valid JSON:
{{
  "period": "{period}",
  "market": "us",
  "generated_on": "{date.today()}",
  "macro_context": "2 sentence backdrop explaining today's market environment.",
  "trending_up": [
    {{
      "ticker": "NVDA",
      "company": "NVIDIA Corporation",
      "sector": "Technology",
      "est_change": 3.5,
      "momentum": "strong|moderate|early",
      "why_up": "Specific reason with catalyst — not generic.",
      "catalyst": "earnings beat|product launch|analyst upgrade|sector rotation|buyback",
      "signal": "buy|add|watch",
      "risk": "What could invalidate this thesis?",
      "tags": ["AI", "semiconductors", "momentum"]
    }}
  ],
  "trending_down": [
    {{
      "ticker": "INTC",
      "company": "Intel Corporation",
      "sector": "Technology",
      "est_change": -2.8,
      "momentum": "strong|moderate|early",
      "why_down": "Specific reason — not generic.",
      "catalyst": "earnings miss|guidance cut|exec departure|competition|regulatory",
      "signal": "sell|reduce|avoid",
      "recovery_watch": "What would need to happen for a reversal?",
      "tags": ["semiconductors", "turnaround_risk"]
    }}
  ],
  "aria_summary": "ARIA's 3-sentence view on the US market setup today."
}}"""

        result = self._call(prompt, cache_key)
        logger.info(
            "[watchlist_us] up=%d down=%d provider=%s",
            len(result.get("trending_up", [])),
            len(result.get("trending_down", [])),
            result.get("_provider"),
        )
        return result

    # ------------------------------------------------------------------
    # 2. India Watchlist
    # ------------------------------------------------------------------

    def get_india_watchlist(self, period: str = "today") -> dict:
        """
        ARIA selects 10 NSE/BSE stocks (5 up, 5 down) incorporating
        FII/DII flows, RBI policy backdrop, and Nifty technical structure.
        """
        cache_key = f"watchlist_india_{period}_{date.today()}"
        cached = _load_cache(cache_key)
        if cached:
            logger.info("[watchlist_india] Returning cached result.")
            return cached

        headlines = self._fetcher.fetch_headlines_context("india", period)
        snapshot  = self._prices.get_market_snapshot()
        india_snap = snapshot.get("india", {})

        market_context = "\n".join(
            f"  {name}: {d.get('price', 'N/A')}  ({d.get('change_pct', 0):+.2f}%)"
            for name, d in india_snap.items() if "error" not in d
        )

        prompt = f"""You are ARIA. Today: {date.today()}.

LIVE INDIA MARKET LEVELS:
{market_context}

LIVE HEADLINES:
{headlines}

Select exactly 10 Indian stocks that matter RIGHT NOW:
- 5 stocks trending UP (from Nifty 50, Nifty Midcap 100, or Nifty Smallcap)
- 5 stocks trending DOWN

Think like a Mumbai-based fund manager. Factor in FII/DII flows, RBI policy,
quarterly results season, and global macro (Fed, crude oil, INR/USD).
Use NSE tickers with .NS suffix.

Respond with ONLY valid JSON:
{{
  "period": "{period}",
  "market": "india",
  "generated_on": "{date.today()}",
  "nifty_view": "Bullish|Bearish|Sideways",
  "nifty_target_near": 23800,
  "nifty_support": 23200,
  "fii_dii_note": "Current FII/DII posture and net flow trend.",
  "macro_context": "2 sentence backdrop: RBI stance, INR, global factors.",
  "trending_up": [
    {{
      "ticker": "RELIANCE.NS",
      "company": "Reliance Industries",
      "sector": "Conglomerate",
      "index": "Nifty 50|Nifty Midcap|Nifty Smallcap",
      "est_change": 2.1,
      "momentum": "strong|moderate|early",
      "why_up": "Specific catalyst — results, policy, flows.",
      "catalyst": "q_results|fii_buying|policy_tailwind|technical_breakout|promoter_buying",
      "signal": "buy|add|watch",
      "risk": "Key risk to this view.",
      "tags": ["large_cap", "energy", "momentum"]
    }}
  ],
  "trending_down": [
    {{
      "ticker": "TATASTEEL.NS",
      "company": "Tata Steel",
      "sector": "Metals",
      "index": "Nifty 50|Nifty Midcap|Nifty Smallcap",
      "est_change": -1.8,
      "momentum": "strong|moderate|early",
      "why_down": "Specific reason.",
      "catalyst": "q_miss|fii_selling|commodity_pressure|regulatory|technical_breakdown",
      "signal": "sell|reduce|avoid",
      "recovery_watch": "Trigger for reversal.",
      "tags": ["metals", "cyclical"]
    }}
  ],
  "aria_summary": "ARIA's 3-sentence view on Indian markets today."
}}"""

        result = self._call(prompt, cache_key)
        logger.info(
            "[watchlist_india] up=%d down=%d nifty_view=%s provider=%s",
            len(result.get("trending_up", [])),
            len(result.get("trending_down", [])),
            result.get("nifty_view", "?"),
            result.get("_provider"),
        )
        return result

    # ------------------------------------------------------------------
    # 3. Technical analysis (pure pandas — no AI, kept from v1)
    # ------------------------------------------------------------------

    def analyse(self, ticker: str, df: pd.DataFrame) -> dict:
        """
        Compute SMA-20, SMA-50, RSI-14 and derive a signal.
        Accepts a yfinance-style OHLCV DataFrame.
        """
        if df is None or df.empty:
            return {"ticker": ticker, "error": "No price data available."}

        close = df["Close"].squeeze().dropna()
        last  = close.iloc[-1].item()
        first = close.iloc[0].item()

        result: dict[str, Any] = {
            "ticker":          ticker,
            "current_price":   round(last, 2),
            "period_high":     round(close.max().item(), 2),
            "period_low":      round(close.min().item(), 2),
            "price_change_pct": round((last - first) / first * 100, 2),
            "sma_20":          self._sma(close, 20),
            "sma_50":          self._sma(close, 50),
            "rsi_14":          self._rsi(close, 14),
        }
        result["signal"] = self._derive_signal(result)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call(self, prompt: str, cache_key: str) -> dict:
        logger.info("[%s] Prompt length: %d chars", cache_key, len(prompt))
        result = self._ai.sync_call(prompt)
        data   = result["data"]
        data["_provider"] = result["provider"]
        _save_cache(cache_key, data)
        return data

    @staticmethod
    def _sma(series: pd.Series, window: int) -> float | None:
        if len(series) < window:
            return None
        return round(series.rolling(window).mean().iloc[-1].item(), 2)

    @staticmethod
    def _rsi(series: pd.Series, period: int = 14) -> float | None:
        if len(series) < period + 1:
            return None
        delta = series.diff()
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / loss.replace(0, float("nan"))
        rsi   = 100 - (100 / (1 + rs))
        return round(rsi.iloc[-1].item(), 2)

    @staticmethod
    def _derive_signal(data: dict) -> str:
        rsi   = data.get("rsi_14")
        sma20 = data.get("sma_20")
        price = data.get("current_price")
        if rsi is None or sma20 is None or price is None:
            return "insufficient_data"
        if rsi < 30 and price > sma20:
            return "buy"
        if rsi > 70 and price < sma20:
            return "sell"
        return "hold"


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
