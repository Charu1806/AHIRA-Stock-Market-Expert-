#!/usr/bin/env python3
"""ARIA Stock Agent — CLI entry point and scheduler."""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Load .env before any config/agent imports
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

import schedule

from config import settings
from agents.news_agent     import NewsAgent
from agents.stock_agent    import StockAgent
from agents.learning_agent import LearningAgent
from fetchers.price_fetcher import PriceFetcher
from notifier.telegram     import TelegramNotifier

# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s  [%(levelname)s]  %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger("aria.main")

IST = ZoneInfo("Asia/Kolkata")

BANNER = """
╔══════════════════════════════════════════╗
║        ARIA STOCK AGENT  v0.2            ║
║  News · Technicals · Signals · Alerts    ║
╚══════════════════════════════════════════╝
"""

# ---------------------------------------------------------------------------
# Core jobs
# ---------------------------------------------------------------------------

def run_morning(period: str = "today", notify: bool = True) -> dict:
    """
    Full morning pipeline:
      1. Fetch market snapshot
      2. Analyse US + India news
      3. Build US + India watchlists
      4. Send Telegram digest (if notify=True)
    Returns dict with all data for downstream use.
    """
    logger.info("▶  ARIA Morning run started  [%s]", datetime.now(IST).strftime("%H:%M IST"))
    result: dict = {}

    # 1. Market snapshot
    logger.info("  Fetching market snapshot…")
    pf = PriceFetcher()
    result["snapshot"] = pf.get_market_snapshot()

    # 2. News analysis
    na = NewsAgent()
    logger.info("  Analysing US news…")
    result["us_news"]    = na.analyse_us_news(period)

    logger.info("  Analysing India news…")
    result["india_news"] = na.analyse_india_news(period)

    logger.info("  Analysing global news…")
    result["global_news"] = na.analyse_global_news(period)

    # 3. Watchlists
    sa = StockAgent()
    logger.info("  Building US watchlist…")
    result["us_stocks"]    = sa.get_us_watchlist(period)

    logger.info("  Building India watchlist…")
    result["india_stocks"] = sa.get_india_watchlist(period)

    # 4. Digest
    if notify:
        notifier = TelegramNotifier()
        stocks_merged = {"us": result["us_stocks"], "india": result["india_stocks"]}
        ok = notifier.send_daily_digest(
            us_data    = result["us_news"],
            india_data = result["india_news"],
            stocks_data= stocks_merged,
            snapshot   = result["snapshot"],
        )
        logger.info("  Digest sent: %s", "✓" if ok else "✗")
        result["digest_sent"] = ok

        # Send high-confidence signal alerts
        _fire_signal_alerts(result["us_stocks"],    notifier, market="US")
        _fire_signal_alerts(result["india_stocks"], notifier, market="India")

    logger.info("▶  Morning run complete")
    return result


def run_evening(notify: bool = True) -> dict:
    """Evening pipeline: fetch daily lesson and send to Telegram."""
    logger.info("▶  ARIA Evening run started  [%s]", datetime.now(IST).strftime("%H:%M IST"))
    la = LearningAgent()
    logger.info("  Fetching daily lesson…")
    lesson = la.get_daily_lesson()
    logger.info("  Concept: %s", lesson.get("concept", "?"))

    result = {"lesson": lesson}
    if notify:
        notifier = TelegramNotifier()
        ok = notifier.send_learning(lesson)
        logger.info("  Lesson sent: %s", "✓" if ok else "✗")
        result["lesson_sent"] = ok

    logger.info("▶  Evening run complete")
    return result


def run_tab(tab: str, period: str = "today", notify: bool = False) -> None:
    """Run a single agent tab and print a summary."""
    logger.info("▶  Running tab: %s", tab)
    if tab == "us-news":
        data = NewsAgent().analyse_us_news(period)
        _print_stories(data.get("stories", []), "US News")
    elif tab == "india-news":
        data = NewsAgent().analyse_india_news(period)
        _print_stories(data.get("stories", []), "India News")
    elif tab == "global-news":
        data = NewsAgent().analyse_global_news(period)
        _print_stories(data.get("stories", []), "Global News")
    elif tab == "us-stocks":
        data = StockAgent().get_us_watchlist(period)
        _print_watchlist(data, "US Watchlist")
    elif tab == "india-stocks":
        data = StockAgent().get_india_watchlist(period)
        _print_watchlist(data, "India Watchlist")
    elif tab == "lesson":
        lesson = LearningAgent().get_daily_lesson()
        print(f"\n  🎓 {lesson.get('concept')}")
        print(f"  {lesson.get('tagline')}")
        print(f"\n  Takeaway: {lesson.get('takeaway','')[:200]}\n")
        if notify:
            TelegramNotifier().send_learning(lesson)
    elif tab == "snapshot":
        snap = PriceFetcher().get_market_snapshot()
        for region, indices in snap.items():
            print(f"\n  {region.upper()}")
            for name, d in indices.items():
                pct = d.get("change_pct", 0) or 0
                arrow = "▲" if pct >= 0 else "▼"
                print(f"    {name:12s}  {d.get('price','N/A'):>10}  {arrow} {pct:+.2f}%")
    else:
        logger.error("Unknown tab '%s'. Choose: us-news, india-news, global-news, "
                     "us-stocks, india-stocks, lesson, snapshot", tab)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

def _ist_to_utc(hhmm: str) -> str:
    """Convert 'HH:MM' IST to 'HH:MM' UTC string for the schedule library."""
    h, m = map(int, hhmm.split(":"))
    # IST = UTC+5:30
    total_minutes = h * 60 + m - 330  # subtract 5h30m
    total_minutes %= 1440              # wrap around midnight
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def start_scheduler(period: str = "today") -> None:
    """Register weekday jobs and run the blocking schedule loop."""
    # Convert IST times to UTC for schedule (which uses local/system time)
    morning_utc = _ist_to_utc("08:45")
    evening_utc = _ist_to_utc("19:00")

    logger.info("Scheduling morning digest at 08:45 IST (%s UTC)", morning_utc)
    logger.info("Scheduling evening lesson  at 19:00 IST (%s UTC)", evening_utc)

    (schedule.every().monday.at(morning_utc).do(run_morning, period=period))
    (schedule.every().tuesday.at(morning_utc).do(run_morning, period=period))
    (schedule.every().wednesday.at(morning_utc).do(run_morning, period=period))
    (schedule.every().thursday.at(morning_utc).do(run_morning, period=period))
    (schedule.every().friday.at(morning_utc).do(run_morning, period=period))

    (schedule.every().monday.at(evening_utc).do(run_evening))
    (schedule.every().tuesday.at(evening_utc).do(run_evening))
    (schedule.every().wednesday.at(evening_utc).do(run_evening))
    (schedule.every().thursday.at(evening_utc).do(run_evening))
    (schedule.every().friday.at(evening_utc).do(run_evening))

    print(BANNER)
    logger.info("Scheduler running. Press Ctrl+C to stop.")
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped.")


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------

def _print_stories(stories: list[dict], label: str) -> None:
    print(f"\n  {label} ({len(stories)} stories)")
    print("  " + "─" * 50)
    for i, s in enumerate(stories, 1):
        print(f"  {i}. [{s.get('category','?').upper()}] {s.get('headline','')}")
        tickers = [imp.get("ticker","") for imp in s.get("impacted_stocks",[])]
        if tickers:
            print(f"     Tickers: {', '.join(tickers)}")
        take = s.get("aria_take","")
        if take:
            print(f"     ARIA: {take[:120]}…")
    print()

def _print_watchlist(data: dict, label: str) -> None:
    print(f"\n  {label}")
    print("  " + "─" * 50)
    up   = data.get("trending_up",   [])
    down = data.get("trending_down", [])
    print(f"  ▲ TRENDING UP ({len(up)} stocks)")
    for s in up:
        print(f"    🟢 {s.get('ticker','?'):12s} {s.get('est_change',0):+.1f}%  {s.get('catalyst','')}")
    print(f"\n  ▼ TRENDING DOWN ({len(down)} stocks)")
    for s in down:
        print(f"    🔴 {s.get('ticker','?'):12s} {s.get('est_change',0):+.1f}%  {s.get('catalyst','')}")
    summary = data.get("aria_summary","")
    if summary:
        print(f"\n  ARIA: {summary[:160]}")
    print()

def _fire_signal_alerts(watchlist: dict, notifier: TelegramNotifier, market: str) -> None:
    """Send individual alerts for high-confidence signals (est_change ≥ 3%)."""
    THRESHOLD = 3.0
    for s in watchlist.get("trending_up", []):
        if abs(s.get("est_change", 0)) >= THRESHOLD:
            notifier.send_signal_alert(
                ticker     = s.get("ticker", "?"),
                signal     = "BUY",
                reason     = f"[{market}] {s.get('why_up', s.get('catalyst',''))}",
                confidence = min(abs(s.get("est_change", 0)) / 10, 1.0),
            )
    for s in watchlist.get("trending_down", []):
        if abs(s.get("est_change", 0)) >= THRESHOLD:
            notifier.send_signal_alert(
                ticker     = s.get("ticker", "?"),
                signal     = "SELL",
                reason     = f"[{market}] {s.get('why_down', s.get('catalyst',''))}",
                confidence = min(abs(s.get("est_change", 0)) / 10, 1.0),
            )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_TAB_CHOICES = ["us-news", "india-news", "global-news", "us-stocks",
                "india-stocks", "lesson", "snapshot"]

def main() -> None:
    print(BANNER)
    parser = argparse.ArgumentParser(
        description="ARIA Stock Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --now              Run full morning analysis + send digest
  python main.py --evening          Run evening lesson
  python main.py --test             Test Telegram connection
  python main.py --tab us-news      Run single tab
  python main.py --tab us-stocks --notify
  python main.py --schedule         Start weekday scheduler (blocking)
  python main.py --dashboard        Launch Streamlit dashboard
        """,
    )
    parser.add_argument("--now",       action="store_true",  help="Run full morning analysis immediately")
    parser.add_argument("--evening",   action="store_true",  help="Run evening lesson immediately")
    parser.add_argument("--test",      action="store_true",  help="Test Telegram connection")
    parser.add_argument("--tab",       choices=_TAB_CHOICES, help="Run a single tab")
    parser.add_argument("--schedule",  action="store_true",  help="Start the weekday scheduler")
    parser.add_argument("--dashboard", action="store_true",  help="Launch Streamlit dashboard")
    parser.add_argument("--period",    choices=list(settings.PERIODS.keys()), default="today")
    parser.add_argument("--notify",    action="store_true",  help="Send Telegram alerts")
    args = parser.parse_args()

    if args.dashboard:
        import subprocess
        dashboard = Path(__file__).parent / "dashboard" / "app.py"
        subprocess.run(["streamlit", "run", str(dashboard)], check=True)
        return

    if args.test:
        logger.info("Testing Telegram connection…")
        ok = TelegramNotifier().test_connection()
        print(f"  Connection: {'✓ OK' if ok else '✗ FAILED'}")
        sys.exit(0 if ok else 1)

    if args.now:
        run_morning(period=args.period, notify=args.notify)
        return

    if args.evening:
        run_evening(notify=args.notify)
        return

    if args.tab:
        run_tab(args.tab, period=args.period, notify=args.notify)
        return

    if args.schedule:
        start_scheduler(period=args.period)
        return

    # Default: print help
    parser.print_help()


if __name__ == "__main__":
    main()
