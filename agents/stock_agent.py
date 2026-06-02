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
        self._fetcher = NewsFetcher(cache=True)
        self._prices  = PriceFetcher(cache=True)

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

        from config import settings as _cfg
        headlines = "\n".join(
            f"- {a['title']}"
            for a in self._fetcher.fetch_rss(
                list(_cfg.get_active_sources("us").values()), max_per_source=3
            )[:12]
        ) or "Use training knowledge."

        snapshot = self._prices.get_market_snapshot()
        us_snap  = snapshot.get("us", {})
        mkt = " | ".join(
            f"{n}:{d.get('price','?')}({d.get('change_pct',0):+.1f}%)"
            for n, d in us_snap.items() if "error" not in d
        )

        prompt = f"""ARIA. Date:{date.today()} Period:{period}
MARKET: {mkt}
HEADLINES:
{headlines}

Pick 10 US stocks RIGHT NOW — 5 up, 5 down. No fixed list; use earnings cycle, Fed policy, sector flows.
Return JSON:
{{"period":"{period}","market":"us","macro_context":"<2 sentences>","aria_summary":"<2 sentences>",
"trending_up":[{{"ticker":"<SYM>","company":"<name>","sector":"<s>","est_change":0.0,"momentum":"strong|moderate|early","why_up":"<specific>","catalyst":"<type>","signal":"buy|add|watch","risk":"<1 sentence>","tags":["<t>"]}}],
"trending_down":[{{"ticker":"<SYM>","company":"<name>","sector":"<s>","est_change":0.0,"momentum":"strong|moderate|early","why_down":"<specific>","catalyst":"<type>","signal":"sell|reduce|avoid","recovery_watch":"<1 sentence>","tags":["<t>"]}}]}}"""

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

        from config import settings as _cfg
        headlines = "\n".join(
            f"- {a['title']}"
            for a in self._fetcher.fetch_rss(
                list(_cfg.get_active_sources("india").values()), max_per_source=3
            )[:12]
        ) or "Use training knowledge."

        snapshot   = self._prices.get_market_snapshot()
        india_snap = snapshot.get("india", {})
        mkt = " | ".join(
            f"{n}:{d.get('price','?')}({d.get('change_pct',0):+.1f}%)"
            for n, d in india_snap.items() if "error" not in d
        )

        prompt = f"""ARIA. Date:{date.today()} Period:{period}
MARKET: {mkt}
HEADLINES:
{headlines}

Pick 10 Indian stocks RIGHT NOW — 5 up, 5 down (Nifty 50/Midcap/Smallcap). Use .NS suffix.
Factor: FII/DII flows, RBI policy, results season, crude oil, INR/USD.
Return JSON:
{{"period":"{period}","market":"india","nifty_view":"Bullish|Bearish|Sideways","nifty_target_near":0,"nifty_support":0,"fii_dii_note":"<1 sentence>","macro_context":"<2 sentences>","aria_summary":"<2 sentences>",
"trending_up":[{{"ticker":"<SYM>.NS","company":"<name>","sector":"<s>","index":"Nifty 50|Nifty Midcap|Nifty Smallcap","est_change":0.0,"momentum":"strong|moderate|early","why_up":"<specific>","catalyst":"<type>","signal":"buy|add|watch","risk":"<1 sentence>","tags":["<t>"]}}],
"trending_down":[{{"ticker":"<SYM>.NS","company":"<name>","sector":"<s>","index":"<i>","est_change":0.0,"momentum":"strong|moderate|early","why_down":"<specific>","catalyst":"<type>","signal":"sell|reduce|avoid","recovery_watch":"<1 sentence>","tags":["<t>"]}}]}}"""

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
        logger.info("[%s] ~%d tokens", cache_key, len(prompt) // 4)
        result = self._ai.sync_call(prompt, max_tokens=1200)
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
