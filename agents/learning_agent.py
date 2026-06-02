"""LearningAgent — daily market education concept via AIEngine."""
from __future__ import annotations

import json
import logging
import time
from datetime import date
from pathlib import Path

logger = logging.getLogger("aria.learning_agent")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s  [%(levelname)s]  %(message)s", "%H:%M:%S"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

CACHE_DIR    = Path(__file__).resolve().parents[1] / "data" / "cache"
HISTORY_FILE = Path(__file__).resolve().parents[1] / "data" / "reports" / "signal_history.json"
CACHE_TTL    = 86400  # full day — one AI call per tab per day


class LearningAgent:
    """
    Two responsibilities:
    1. get_daily_lesson() — AI picks a market concept relevant to today.
    2. Signal history tracking — record(), evaluate(), accuracy_report().
    """

    def __init__(self):
        from agents.ai_engine import AIEngine
        from fetchers.news_fetcher import NewsFetcher
        self._ai      = AIEngine()
        self._fetcher = NewsFetcher()
        self._history: list[dict] = self._load_history()

    # ------------------------------------------------------------------
    # 1. Daily Lesson
    # ------------------------------------------------------------------

    def get_daily_lesson(self) -> dict:
        """
        ARIA picks ONE financial concept that is highly relevant to what is
        happening in markets RIGHT NOW — not a textbook definition but a
        live, applicable lesson tied to current macro/earnings/events.
        """
        cache_key = f"lesson_{date.today()}"
        cached = _load_cache(cache_key)
        if cached:
            logger.info("[lesson] Returning cached lesson.")
            return cached

        from config import settings as _cfg
        articles = self._fetcher.fetch_rss(
            list(_cfg.get_active_sources("global").values()), max_per_source=2
        )[:10]
        headlines = "\n".join(f"- {a['title']}" for a in articles) or "Use training knowledge."

        prompt = f"""ARIA. Date:{date.today()}

HEADLINES:
{headlines}

Pick ONE financial concept highly relevant to markets RIGHT NOW (not textbook — live and applicable).
Return JSON:
{{"concept":"<4-8 words>","tagline":"<1 punchy sentence>","difficulty":"beginner|intermediate|advanced",
"relevance":"<why now — 2 sentences>",
"explanation":{{"core_idea":"<2 sentences>","mechanics":"<2 sentences>","why_it_matters_now":"<2 sentences>"}},
"real_example":{{"title":"<recent event>","body":"<3 sentences with names/numbers>"}},
"india_angle":"<2 sentences>","us_angle":"<2 sentences>",
"takeaway":"<1 actionable sentence>","common_mistake":"<1 sentence>",
"next_steps":["<action 1>","<action 2>","<action 3>"]}}"""

        logger.info("[lesson] ~%d tokens", len(prompt) // 4)
        result = self._ai.sync_call(prompt, max_tokens=1000)
        data   = result["data"]
        data["_provider"]   = result["provider"]
        data["_date"]       = str(date.today())
        _save_cache(cache_key, data)
        logger.info("[lesson] Concept: '%s' via %s", data.get("concept", "?"), result["provider"])
        return data

    # ------------------------------------------------------------------
    # 2. Signal history (unchanged contract from v1)
    # ------------------------------------------------------------------

    def record(self, signal_dict: dict, actual_price: float | None = None) -> None:
        from datetime import datetime, timezone
        entry = {
            **signal_dict,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "actual_price_at_record": actual_price,
            "outcome": None,
        }
        self._history.append(entry)
        self._save_history()

    def evaluate(self, ticker: str, current_price: float) -> list[dict]:
        updated = []
        for entry in self._history:
            if entry.get("ticker") != ticker or entry.get("outcome") is not None:
                continue
            basis = entry.get("actual_price_at_record")
            if basis is None:
                continue
            change_pct = (current_price - basis) / basis * 100
            rec = entry.get("recommendation", "hold")
            if rec == "buy":
                entry["outcome"] = "correct" if change_pct > 1 else "incorrect"
            elif rec == "sell":
                entry["outcome"] = "correct" if change_pct < -1 else "incorrect"
            else:
                entry["outcome"] = "neutral"
            updated.append(entry)
        if updated:
            self._save_history()
        return updated

    def accuracy_report(self) -> dict:
        resolved = [e for e in self._history if e.get("outcome") not in (None, "neutral")]
        if not resolved:
            return {"total": 0, "correct": 0, "incorrect": 0, "accuracy_pct": None}
        correct = sum(1 for e in resolved if e["outcome"] == "correct")
        return {
            "total":        len(resolved),
            "correct":      correct,
            "incorrect":    len(resolved) - correct,
            "accuracy_pct": round(correct / len(resolved) * 100, 1),
        }

    # ------------------------------------------------------------------
    # History persistence
    # ------------------------------------------------------------------

    def _load_history(self) -> list[dict]:
        if HISTORY_FILE.exists():
            try:
                return json.loads(HISTORY_FILE.read_text())
            except json.JSONDecodeError:
                return []
        return []

    def _save_history(self) -> None:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(json.dumps(self._history, indent=2))


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
