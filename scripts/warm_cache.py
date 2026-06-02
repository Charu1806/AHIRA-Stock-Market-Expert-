#!/usr/bin/env python3
"""
Cache warmup script — runs on Render startup before Streamlit accepts traffic.
Fills all 5 dashboard tabs with today's AI analysis so first visitors get
instant results. Skips any tab that already has today's disk cache.
"""
from __future__ import annotations
import sys, time, logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logging.basicConfig(format="%(asctime)s  %(message)s", datefmt="%H:%M:%S", level=logging.INFO)
log = logging.getLogger("warmup")

from utils.disk_cache import is_cached_today, load_tab

def warm():
    log.info("▶  Cache warmup starting…")
    t0 = time.time()

    from agents.news_agent    import NewsAgent
    from agents.stock_agent   import StockAgent
    from agents.learning_agent import LearningAgent

    period = "today"
    tasks = [
        ("news_world",   lambda: (NewsAgent().analyse_us_news(period),
                                  NewsAgent().analyse_global_news(period))),
        ("india_news",   lambda: NewsAgent().analyse_india_news(period)),
        ("us_stocks",    lambda: StockAgent().get_us_watchlist(period)),
        ("india_stocks", lambda: StockAgent().get_india_watchlist(period)),
        ("lesson",       lambda: LearningAgent().get_daily_lesson()),
    ]

    warmed, skipped, failed = 0, 0, 0
    for tab, fn in tasks:
        if is_cached_today(tab, period):
            log.info("  ✓ %-15s already cached — skipping", tab)
            skipped += 1
            continue
        try:
            log.info("  ⏳ %-15s calling AI…", tab)
            fn()
            log.info("  ✅ %-15s done", tab)
            warmed += 1
            time.sleep(3)   # respect TPM limits between calls
        except Exception as exc:
            log.warning("  ✗ %-15s failed: %s", tab, exc)
            failed += 1

    elapsed = round(time.time() - t0)
    log.info("▶  Warmup complete in %ds  (warmed=%d skipped=%d failed=%d)",
             elapsed, warmed, skipped, failed)

if __name__ == "__main__":
    warm()
