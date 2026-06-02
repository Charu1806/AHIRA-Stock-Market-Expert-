"""Core AI caller for ARIA — routes between Groq and Gemini with auto-fallback."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("aria.ai_engine")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s  [%(levelname)s]  %(message)s", "%H:%M:%S"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
ARIA_SYSTEM_PROMPT = """You are ARIA — Autonomous Research & Investment Agent.
You have 25+ years of experience across Wall Street, Dalal Street, hedge funds,
and macro research. Deep expertise in: fundamental analysis, technical analysis,
macro economics, Indian markets (Nifty, RBI, FII/DII flows), US markets (S&P 500,
Fed policy, sector rotation), corporate events (earnings, layoffs, M&A, leadership
changes, product launches), and behavioral finance.

Personality: Direct, confident, opinionated. You form strong views and explain them
clearly. You NEVER hedge with "I cannot" — you always give your best expert analysis.
You are a trusted advisor who tells investors what they need to hear, not what they want.

CRITICAL: Always respond with valid JSON only. No markdown fences, no preamble."""

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ConfigError(Exception):
    """Raised when required API keys are absent or invalid."""


class RateLimitError(Exception):
    """Raised when all providers are rate-limited simultaneously."""


# ---------------------------------------------------------------------------
# Network errors eligible for tenacity retry
# ---------------------------------------------------------------------------
_NETWORK_EXCEPTIONS: tuple[type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)

try:
    import httpx
    _NETWORK_EXCEPTIONS = (*_NETWORK_EXCEPTIONS, httpx.NetworkError, httpx.TimeoutException)
except ImportError:
    pass


# ---------------------------------------------------------------------------
# AIEngine
# ---------------------------------------------------------------------------

class AIEngine:
    _GROQ_MODEL = "llama-3.3-70b-versatile"
    _GEMINI_MODEL = "gemini-1.5-flash"
    _TEMPERATURE = 0.35

    def __init__(self) -> None:
        self.active_provider: str | None = None
        self._groq_client = self._init_groq()
        self._gemini_model = self._init_gemini()

        if self._groq_client is not None:
            self.active_provider = "groq"
        elif self._gemini_model is not None:
            self.active_provider = "gemini"
        else:
            raise ConfigError(
                "No API keys found. Set at least one of:\n"
                "  GROQ_API_KEY   → https://console.groq.com/keys\n"
                "  GEMINI_API_KEY → https://aistudio.google.com/app/apikey\n"
                "Copy .env.example → .env and fill in your keys."
            )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def call(self, prompt: str, max_tokens: int = 3000) -> dict:
        """
        Send `prompt` to the best available provider and return:
            {"data": <parsed dict>, "provider": "groq" | "gemini"}

        Groq is tried first; a 429 / RateLimitError triggers automatic
        fallback to Gemini.  If both are exhausted, RateLimitError is raised.
        """
        if self._groq_client is not None:
            try:
                raw = await self._call_groq(prompt, max_tokens)
                self.active_provider = "groq"
                logger.info("Provider: groq ✓")
                return {"data": self._parse_json(raw), "provider": "groq"}
            except RateLimitError:
                logger.warning("Groq rate-limited — falling back to Gemini.")
            except Exception as exc:
                logger.warning("Groq call failed (%s) — falling back to Gemini.", exc)

        if self._gemini_model is not None:
            try:
                raw = await self._call_gemini(prompt, max_tokens)
                self.active_provider = "gemini"
                logger.info("Provider: gemini ✓")
                return {"data": self._parse_json(raw), "provider": "gemini"}
            except RateLimitError:
                raise RateLimitError(
                    "Both Groq and Gemini are rate-limited.\n"
                    "Wait ~60 s or upgrade your API plan:\n"
                    "  Groq:   https://console.groq.com\n"
                    "  Gemini: https://aistudio.google.com"
                )

        raise ConfigError("No AI provider is available. Check your API keys.")

    def sync_call(self, prompt: str, max_tokens: int = 3000) -> dict:
        """Synchronous wrapper around :meth:`call`."""
        try:
            loop = asyncio.get_running_loop()
            # Inside an already-running event loop (e.g. Jupyter / Streamlit)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self.call(prompt, max_tokens))
                return future.result()
        except RuntimeError:
            return asyncio.run(self.call(prompt, max_tokens))

    # ------------------------------------------------------------------
    # Groq
    # ------------------------------------------------------------------

    def _init_groq(self):
        key = os.getenv("GROQ_API_KEY", "")
        if not key or key.startswith("gsk_..."):
            return None
        try:
            from groq import Groq
            return Groq(api_key=key)
        except ImportError:
            logger.warning("groq package not installed — pip install groq")
            return None

    @retry(
        retry=retry_if_exception_type(_NETWORK_EXCEPTIONS),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        reraise=True,
    )
    async def _call_groq(self, prompt: str, max_tokens: int) -> str:
        try:
            from groq import RateLimitError as GroqRateLimit
        except ImportError:
            GroqRateLimit = Exception  # type: ignore[assignment,misc]

        try:
            # groq client is synchronous — run in executor to keep async interface
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._groq_client.chat.completions.create(
                    model=self._GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": ARIA_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=self._TEMPERATURE,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                ),
            )
            return response.choices[0].message.content

        except GroqRateLimit as exc:
            raise RateLimitError(str(exc)) from exc
        except Exception as exc:
            # Surface HTTP 429s that aren't wrapped as GroqRateLimit
            if "429" in str(exc) or "rate_limit" in str(exc).lower():
                raise RateLimitError(str(exc)) from exc
            raise

    # ------------------------------------------------------------------
    # Gemini
    # ------------------------------------------------------------------

    def _init_gemini(self):
        key = os.getenv("GEMINI_API_KEY", "")
        if not key or key.startswith("AIza..."):
            return None
        try:
            import google.generativeai as genai
            genai.configure(api_key=key)
            return genai.GenerativeModel(
                model_name=self._GEMINI_MODEL,
                system_instruction=ARIA_SYSTEM_PROMPT,
                generation_config={
                    "temperature": self._TEMPERATURE,
                    "response_mime_type": "application/json",
                },
            )
        except ImportError:
            logger.warning("google-generativeai not installed — pip install google-generativeai")
            return None

    @retry(
        retry=retry_if_exception_type(_NETWORK_EXCEPTIONS),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        reraise=True,
    )
    async def _call_gemini(self, prompt: str, max_tokens: int) -> str:
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: self._gemini_model.generate_content(
                    prompt,
                    generation_config={"max_output_tokens": max_tokens},
                ),
            )
            return response.text
        except Exception as exc:
            msg = str(exc)
            if "429" in msg or "quota" in msg.lower() or "rate" in msg.lower():
                raise RateLimitError(msg) from exc
            raise

    # ------------------------------------------------------------------
    # JSON parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """Strip markdown fences then parse JSON. Returns dict on success."""
        if not raw:
            raise ValueError("Empty response from AI provider.")

        # Strip ```json ... ``` or ``` ... ``` fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            # Last resort: find the first {...} block
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                result = json.loads(match.group())
            else:
                raise ValueError(f"No valid JSON found in response:\n{raw[:400]}")

        if not isinstance(result, dict):
            result = {"value": result}

        return result


# ---------------------------------------------------------------------------
# __main__ smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    # Load .env if present
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    print("\n  ARIA AI Engine — self-test\n" + "─" * 40)

    try:
        engine = AIEngine()
        print(f"  Initialized. Active provider: {engine.active_provider}")

        result = engine.sync_call(
            prompt='Return JSON: {"test": true, "message": "ARIA online"}'
        )

        print(f"\n  Provider responded: {result['provider']}")
        print(f"  Parsed data:        {json.dumps(result['data'], indent=4)}")
        print("\n  ✓ AI Engine is operational.\n")

    except ConfigError as e:
        print(f"\n  ✘ ConfigError: {e}\n")
        sys.exit(1)
    except RateLimitError as e:
        print(f"\n  ✘ RateLimitError: {e}\n")
        sys.exit(1)
