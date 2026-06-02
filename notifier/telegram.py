"""Telegram notifier for ARIA — daily digest, signal alerts, and evening lessons."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import date, datetime
from typing import Any

logger = logging.getLogger("aria.telegram")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s  [%(levelname)s]  %(message)s", "%H:%M:%S"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# MarkdownV2 escaping
# Telegram MarkdownV2 requires escaping: _ * [ ] ( ) ~ ` > # + - = | { } . !
# ---------------------------------------------------------------------------
_MDV2_SPECIAL = r"\_*[]()~`>#+=|{}.!-"

def _esc(text: str) -> str:
    """Escape a plain string for Telegram MarkdownV2."""
    if not text:
        return ""
    for ch in _MDV2_SPECIAL:
        text = text.replace(ch, f"\\{ch}")
    return text

def _bold(text: str) -> str:
    return f"*{_esc(text)}*"

def _italic(text: str) -> str:
    return f"_{_esc(text)}_"

def _link(label: str, url: str) -> str:
    return f"[{_esc(label)}]({url})"

def _line() -> str:
    return "\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-"

def _chg_emoji(pct: float | None) -> str:
    if pct is None:
        return "⚪"
    return "🟢" if pct >= 0 else "🔴"

def _sig_emoji(sig: str) -> str:
    return {"buy": "🟢", "bullish": "🟢", "sell": "🔴", "bearish": "🔴",
            "hold": "🟡", "watch": "👀", "neutral": "⚪"}.get(sig.lower(), "⚪")

def _confidence_bar(c: float) -> str:
    filled = round(c * 5)
    return "█" * filled + "░" * (5 - filled)


# ---------------------------------------------------------------------------
# TelegramNotifier
# ---------------------------------------------------------------------------

class TelegramNotifier:
    """
    All public methods are synchronous wrappers around async python-telegram-bot
    calls, so they can be called from any sync context (scheduler, main.py, etc.)
    """

    MAX_MSG_LEN = 4096   # Telegram hard limit

    def __init__(self):
        self._token    = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id  = os.getenv("TELEGRAM_CHAT_ID", "")
        self._dash_url = os.getenv("DASHBOARD_URL", "")
        self._bot: Any = None   # lazy-init

    # ------------------------------------------------------------------
    # 1. Daily digest
    # ------------------------------------------------------------------

    def send_daily_digest(
        self,
        us_data: dict,
        india_data: dict,
        stocks_data: dict,
        snapshot: dict | None = None,
    ) -> bool:
        """
        Sends the ARIA Morning Brief digest.

        Parameters
        ----------
        us_data     : result of NewsAgent.analyse_us_news()
        india_data  : result of NewsAgent.analyse_india_news()
        stocks_data : result of StockAgent.get_us_watchlist() or merged dict
        snapshot    : result of PriceFetcher.get_market_snapshot() (optional)
        """
        parts: list[str] = []

        # ── Header ────────────────────────────────────────────────────
        today = date.today().strftime("%d %b %Y")
        parts += [
            f"🤖 {_bold('ARIA Morning Brief')} — {_esc(today)}",
            _line(),
            "",
        ]

        # ── Section 1: Market Snapshot ────────────────────────────────
        parts.append(f"📊 {_bold('Market Snapshot')}")
        if snapshot:
            us_snap    = snapshot.get("us", {})
            india_snap = snapshot.get("india", {})
            index_rows = [
                ("S\\&P 500",   us_snap.get("S&P 500", {})),
                ("NASDAQ",     us_snap.get("NASDAQ", {})),
                ("VIX",        us_snap.get("VIX", {})),
                ("NIFTY 50",   india_snap.get("NIFTY 50", {})),
                ("SENSEX",     india_snap.get("SENSEX", {})),
                ("INDIA VIX",  india_snap.get("INDIA VIX", {})),
            ]
            for label, d in index_rows:
                if "error" in d or not d:
                    parts.append(f"  {_esc(label)}: N/A")
                    continue
                price = d.get("price", "—")
                chg   = d.get("change_pct")
                emoji = _chg_emoji(chg)
                chg_s = _esc(f"{chg:+.2f}%") if chg is not None else "—"
                parts.append(f"  {emoji} {_esc(str(label))}: {_esc(str(price))} \\({chg_s}\\)")
        else:
            parts.append(_italic("Market data unavailable"))
        parts.append("")

        # ── Section 2: Top US Story ───────────────────────────────────
        parts += [_line(), f"🇺🇸 {_bold('Top US Story')}", ""]
        us_story = _pick_top_story(us_data)
        if us_story:
            parts.append(_bold(us_story.get("headline", "No headline")))
            summary = us_story.get("summary", "")
            if summary:
                # Truncate to 2 sentences for compactness
                sentences = re.split(r"(?<=[.!?])\s+", summary)
                parts.append(_esc(" ".join(sentences[:2])))
            for imp in us_story.get("impacted_stocks", [])[:2]:
                sig   = imp.get("signal", "neutral")
                pct   = imp.get("impact_pct", 0)
                parts.append(
                    f"  {_sig_emoji(sig)} {_bold(imp.get('ticker','?'))} "
                    f"{_esc(imp.get('company',''))} "
                    f"\\({_esc(f'{pct:+.1f}%')}\\)"
                )
            take = us_story.get("aria_take", "")
            if take:
                sentences = re.split(r"(?<=[.!?])\s+", take)
                parts.append(f"💡 {_italic(' '.join(sentences[:1]))}")
        else:
            parts.append(_italic("No US stories available"))
        parts.append("")

        # ── Section 3: Top India Story ────────────────────────────────
        parts += [_line(), f"🇮🇳 {_bold('Top India Story')}", ""]
        in_story = _pick_top_story(india_data)
        if in_story:
            parts.append(_bold(in_story.get("headline", "No headline")))
            summary = in_story.get("summary", "")
            if summary:
                sentences = re.split(r"(?<=[.!?])\s+", summary)
                parts.append(_esc(" ".join(sentences[:2])))
            for imp in in_story.get("impacted_stocks", [])[:2]:
                sig  = imp.get("signal", "neutral")
                pct  = imp.get("impact_pct", 0)
                parts.append(
                    f"  {_sig_emoji(sig)} {_bold(imp.get('ticker','?'))} "
                    f"{_esc(imp.get('company',''))} "
                    f"\\({_esc(f'{pct:+.1f}%')}\\)"
                )
            take = in_story.get("aria_take", "")
            if take:
                sentences = re.split(r"(?<=[.!?])\s+", take)
                parts.append(f"💡 {_italic(' '.join(sentences[:1]))}")

        nifty_pulse = india_data.get("nifty_pulse", "")
        if nifty_pulse:
            sentences = re.split(r"(?<=[.!?])\s+", nifty_pulse)
            parts.append(f"\n📍 {_italic(' '.join(sentences[:1]))}")
        parts.append("")

        # ── Section 4: ARIA Watchlist ─────────────────────────────────
        watchlist_header = _bold("ARIA's Watchlist")
        parts += [_line(), f"⚡ {watchlist_header}", ""]

        buys  = _collect_signals(stocks_data, "buy",  limit=3)
        sells = _collect_signals(stocks_data, "sell", limit=2)

        if buys:
            parts.append(f"🟢 {_bold('BUY signals:')}")
            for s in buys:
                chg = s.get("est_change", 0)
                parts.append(
                    f"  • {_bold(s.get('ticker','?'))} {_esc(s.get('company',''))} "
                    f"\\({_esc(f'{chg:+.1f}%')}\\) — {_esc(s.get('catalyst',''))}"
                )
        if sells:
            parts.append(f"\n🔴 {_bold('AVOID:')}")
            for s in sells:
                chg = s.get("est_change", 0)
                parts.append(
                    f"  • {_bold(s.get('ticker','?'))} {_esc(s.get('company',''))} "
                    f"\\({_esc(f'{chg:+.1f}%')}\\) — {_esc(s.get('catalyst',''))}"
                )
        if not buys and not sells:
            parts.append(_italic("No high-confidence signals today"))
        parts.append("")

        # ── Footer ────────────────────────────────────────────────────
        parts.append(_line())
        footer = "⚠️ Not financial advice \\| Powered by ARIA"
        if self._dash_url:
            footer += f"\n📱 {_link('Open Dashboard', self._dash_url)}"
        parts.append(footer)

        message = "\n".join(parts)
        return self._send_mdv2(message)

    # ------------------------------------------------------------------
    # 2. Signal alert (high-confidence only)
    # ------------------------------------------------------------------

    def send_signal_alert(
        self,
        ticker: str,
        signal: str,
        reason: str,
        confidence: float,
    ) -> bool:
        """
        Fires only for BUY or SELL signals. Silently skips HOLD/WATCH.
        confidence: 0.0–1.0
        """
        sig_upper = signal.upper()
        if sig_upper not in ("BUY", "SELL"):
            logger.info("[alert] Skipping non-actionable signal %s %s", ticker, sig_upper)
            return True

        emoji  = "🚀" if sig_upper == "BUY" else "🔻"
        bar    = _confidence_bar(confidence)
        pct    = int(confidence * 100)

        lines = [
            f"🚨 {_bold('ARIA ALERT')}: {_bold(ticker)} — {_bold(sig_upper)}",
            "",
            _esc(reason),
            "",
            f"Confidence: {_esc(bar)} {_esc(str(pct))}%",
            "",
            _italic("Not financial advice"),
        ]
        return self._send_mdv2("\n".join(lines))

    # ------------------------------------------------------------------
    # 3. Evening lesson
    # ------------------------------------------------------------------

    def send_learning(self, lesson_data: dict) -> bool:
        """Evening message with today's concept and key takeaway."""
        concept  = lesson_data.get("concept", "Daily Lesson")
        tagline  = lesson_data.get("tagline", "")
        diff     = lesson_data.get("difficulty", "")
        takeaway = lesson_data.get("takeaway", "")
        mistake  = lesson_data.get("common_mistake", "")

        diff_emoji = {"beginner": "🟢", "intermediate": "🟡", "advanced": "🔴"}.get(diff, "⚪")
        today = date.today().strftime("%d %b")

        lines = [
            f"🎓 {_bold('ARIA Evening Lesson')} — {_esc(today)}",
            _line(),
            "",
            f"{diff_emoji} {_bold(concept)}",
        ]
        if tagline:
            lines.append(_italic(tagline))
        lines.append("")

        expl = lesson_data.get("explanation", {})
        core = expl.get("core_idea", "") or expl.get("why_it_matters_now", "")
        if core:
            sentences = re.split(r"(?<=[.!?])\s+", core)
            lines += [f"📖 {_esc(' '.join(sentences[:2]))}", ""]

        if takeaway:
            lines += [f"✅ {_bold('Takeaway')}", _esc(takeaway), ""]

        if mistake:
            sentences = re.split(r"(?<=[.!?])\s+", mistake)
            lines += [f"❌ {_bold('Common mistake')}", _esc(" ".join(sentences[:1])), ""]

        steps = lesson_data.get("next_steps", [])
        if steps:
            lines.append(f"➡️ {_bold('Next steps')}")
            for step in steps[:2]:
                lines.append(f"  • {_esc(step)}")
            lines.append("")

        lines += [_line(), "⚠️ Not financial advice \\| Powered by ARIA"]
        return self._send_mdv2("\n".join(lines))

    # ------------------------------------------------------------------
    # 4. Test connection
    # ------------------------------------------------------------------

    def test_connection(self) -> bool:
        """Sends a simple connectivity check message."""
        msg = (
            f"✅ {_bold('ARIA connected')}\n"
            f"{_esc(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}\n"
            + _italic("Stock Intelligence Agent is online.")
        )
        ok = self._send_mdv2(msg)
        if ok:
            logger.info("[telegram] Connection test passed.")
        return ok

    # ------------------------------------------------------------------
    # Legacy helper (kept for backward compatibility)
    # ------------------------------------------------------------------

    def send_text(self, message: str) -> bool:
        """Send a plain (non-MarkdownV2) text message."""
        return self._send_raw(message, parse_mode=None)

    def send_signal(self, signal: Any) -> bool:
        """Legacy single-signal dispatch."""
        d     = signal.as_dict() if hasattr(signal, "as_dict") else dict(signal)
        rec   = d.get("recommendation", "hold")
        emoji = _sig_emoji(rec)
        lines = [
            f"{emoji} {_bold(d.get('ticker','?'))} — {_bold(rec.upper())}",
            "Confidence: " + _esc(f"{d.get('confidence', 0):.0%}"),
            f"Sentiment: {_esc(d.get('sentiment','n/a'))}",
        ]
        if d.get("summary"):
            sentences = re.split(r"(?<=[.!?])\s+", d["summary"])
            lines += ["", _esc(" ".join(sentences[:2]))]
        return self._send_mdv2("\n".join(lines))

    # ------------------------------------------------------------------
    # Internal — async send via python-telegram-bot
    # ------------------------------------------------------------------

    async def _async_send(self, text: str, parse_mode: str | None = "MarkdownV2") -> bool:
        try:
            from telegram import Bot
        except ImportError:
            raise RuntimeError(
                "python-telegram-bot not installed. Run: pip install python-telegram-bot"
            )
        # Create a fresh Bot per call — reusing a Bot across asyncio.run() calls
        # causes "Event loop is closed" because httpx.AsyncClient is loop-bound.
        async with Bot(token=self._token) as bot:
            chunks = _split_message(text, self.MAX_MSG_LEN)
            for chunk in chunks:
                kwargs: dict = {"chat_id": self._chat_id, "text": chunk}
                if parse_mode:
                    kwargs["parse_mode"] = parse_mode
                await bot.send_message(**kwargs)
        return True

    def _send_mdv2(self, text: str) -> bool:
        return self._dispatch(text, parse_mode="MarkdownV2")

    def _send_raw(self, text: str, parse_mode: str | None = None) -> bool:
        return self._dispatch(text, parse_mode=parse_mode)

    def _dispatch(self, text: str, parse_mode: str | None) -> bool:
        if not self._token or self._token.endswith("..."):
            logger.warning("[telegram] Bot token not configured — skipping.")
            return False
        if not self._chat_id or self._chat_id.endswith("..."):
            logger.warning("[telegram] Chat ID not configured — skipping.")
            return False

        for attempt in range(1, 4):
            try:
                return _run_async(self._async_send(text, parse_mode))
            except Exception as exc:
                logger.warning("[telegram] Attempt %d/3 failed: %s", attempt, exc)
                if attempt < 3:
                    time.sleep(5)
        logger.error("[telegram] All 3 attempts failed.")
        return False


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _run_async(coro) -> Any:
    """Run an async coroutine from sync code, handling existing event loops."""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


def _split_message(text: str, limit: int) -> list[str]:
    """Split a long message at newline boundaries to stay under Telegram's limit."""
    if len(text) <= limit:
        return [text]
    chunks, current = [], []
    current_len = 0
    for line in text.split("\n"):
        line_len = len(line) + 1  # +1 for newline
        if current_len + line_len > limit and current:
            chunks.append("\n".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks


def _pick_top_story(analysis: dict) -> dict | None:
    """Pick the most impactful story: prefers stories with stock impacts."""
    stories = analysis.get("stories", [])
    if not stories:
        return None
    # Prefer stories with impacted stocks
    with_impacts = [s for s in stories if s.get("impacted_stocks")]
    return with_impacts[0] if with_impacts else stories[0]


def _collect_signals(stocks_data: dict, direction: str, limit: int) -> list[dict]:
    """
    Collect BUY (trending_up) or SELL (trending_down) signals from watchlist data.
    Works with both US and India watchlist dicts, or a merged {'us':..., 'india':...} dict.
    """
    pool: list[dict] = []
    key = "trending_up" if direction == "buy" else "trending_down"

    # Direct watchlist dict
    if key in stocks_data:
        pool.extend(stocks_data[key])
    # Merged dict with 'us' / 'india' keys
    for sub in ("us", "india"):
        sub_data = stocks_data.get(sub, {})
        if isinstance(sub_data, dict):
            pool.extend(sub_data.get(key, []))

    # Sort by abs(est_change) descending
    pool.sort(key=lambda s: abs(s.get("est_change", 0)), reverse=True)
    return pool[:limit]
