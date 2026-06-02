"""Core AI caller for ARIA — Groq → Gemini → Mistral → Anthropic fallback chain."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
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
# Provider metadata — order defines fallback priority
# ---------------------------------------------------------------------------
PROVIDER_META = {
    "groq":      {"label": "Groq",      "model": "llama-3.3-70b-versatile", "free": True,  "paid": False},
    "gemini":    {"label": "Gemini",    "model": "gemini-1.5-flash",         "free": True,  "paid": False},
    "mistral":   {"label": "Mistral",   "model": "mistral-small-latest",     "free": True,  "paid": False},
    "anthropic": {"label": "Anthropic", "model": "claude-sonnet-4-6",        "free": False, "paid": True},
}

# Anthropic triggers a dashboard warning — notify user they are being billed
PAID_PROVIDERS = {"anthropic"}

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ConfigError(Exception):
    """Raised when no usable API key is found."""

class RateLimitError(Exception):
    """Raised when every configured provider is rate-limited."""

# ---------------------------------------------------------------------------
# Network errors eligible for tenacity retry
# ---------------------------------------------------------------------------
_NETWORK_EXCEPTIONS: tuple[type[Exception], ...] = (ConnectionError, TimeoutError, OSError)
try:
    import httpx
    _NETWORK_EXCEPTIONS = (*_NETWORK_EXCEPTIONS, httpx.NetworkError, httpx.TimeoutException)
except ImportError:
    pass


# ---------------------------------------------------------------------------
# AIEngine
# ---------------------------------------------------------------------------

class AIEngine:
    _TEMPERATURE = 0.35

    def __init__(self) -> None:
        self.active_provider: str | None = None
        self.using_paid_provider: bool = False

        # Build the ordered list of available clients
        self._clients: dict[str, Any] = {}
        for name, init_fn in [
            ("groq",      self._init_groq),
            ("gemini",    self._init_gemini),
            ("mistral",   self._init_mistral),
            ("anthropic", self._init_anthropic),
        ]:
            client = init_fn()
            if client is not None:
                self._clients[name] = client
                if self.active_provider is None:
                    self.active_provider = name

        if not self._clients:
            raise ConfigError(
                "No API keys found. Set at least one of:\n"
                "  GROQ_API_KEY      → https://console.groq.com/keys        (free)\n"
                "  GEMINI_API_KEY    → https://aistudio.google.com/apikey   (free)\n"
                "  MISTRAL_API_KEY   → https://console.mistral.ai            (free tier)\n"
                "  ANTHROPIC_API_KEY → https://console.anthropic.com         (paid)\n"
                "Copy .env.example → .env and fill in your keys."
            )

        logger.info(
            "AIEngine ready. Providers available: %s",
            " → ".join(self._clients.keys()),
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def call(self, prompt: str, max_tokens: int = 3000) -> dict:
        """
        Try each provider in priority order (Groq → Gemini → Mistral → Anthropic).
        Rate limits trigger automatic fallback to the next provider.
        Returns {"data": dict, "provider": str}.
        """
        last_error: Exception | None = None

        for name, client in self._clients.items():
            try:
                raw = await self._dispatch(name, client, prompt, max_tokens)
                self.active_provider = name
                self.using_paid_provider = name in PAID_PROVIDERS
                if self.using_paid_provider:
                    logger.warning(
                        "⚠ Using PAID provider: %s — you will be charged for this call.",
                        PROVIDER_META[name]["label"],
                    )
                else:
                    logger.info("Provider: %s ✓", name)
                return {"data": self._parse_json(raw), "provider": name}

            except RateLimitError as exc:
                logger.warning("%s rate-limited — trying next provider.", name)
                last_error = exc
            except Exception as exc:
                logger.warning("%s failed (%s) — trying next provider.", name, exc)
                last_error = exc

        # All providers exhausted
        names = list(self._clients.keys())
        raise RateLimitError(
            f"All {len(names)} providers exhausted: {', '.join(names)}.\n"
            f"Last error: {last_error}\n"
            "Wait ~60s and retry, or add more API keys."
        )

    def sync_call(self, prompt: str, max_tokens: int = 3000) -> dict:
        """Synchronous wrapper around :meth:`call`."""
        try:
            asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, self.call(prompt, max_tokens)).result()
        except RuntimeError:
            return asyncio.run(self.call(prompt, max_tokens))

    # ------------------------------------------------------------------
    # Dispatcher
    # ------------------------------------------------------------------

    async def _dispatch(self, name: str, client: Any, prompt: str, max_tokens: int) -> str:
        if name == "groq":
            return await self._call_groq(client, prompt, max_tokens)
        if name == "gemini":
            return await self._call_gemini(client, prompt, max_tokens)
        if name == "mistral":
            return await self._call_mistral(client, prompt, max_tokens)
        if name == "anthropic":
            return await self._call_anthropic(client, prompt, max_tokens)
        raise ValueError(f"Unknown provider: {name}")

    # ------------------------------------------------------------------
    # Groq  (free — 14,400 req/day)
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

    @retry(retry=retry_if_exception_type(_NETWORK_EXCEPTIONS),
           stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8), reraise=True)
    async def _call_groq(self, client, prompt: str, max_tokens: int) -> str:
        try:
            from groq import RateLimitError as GroqRL
        except ImportError:
            GroqRL = Exception  # type: ignore[assignment,misc]
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, lambda: client.chat.completions.create(
                model=PROVIDER_META["groq"]["model"],
                messages=[{"role": "system", "content": ARIA_SYSTEM_PROMPT},
                          {"role": "user",   "content": prompt}],
                temperature=self._TEMPERATURE,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            ))
            return resp.choices[0].message.content
        except GroqRL as e:
            raise RateLimitError(str(e)) from e
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                raise RateLimitError(str(e)) from e
            raise

    # ------------------------------------------------------------------
    # Gemini  (free — 1,500 req/day)
    # ------------------------------------------------------------------

    def _init_gemini(self):
        key = os.getenv("GEMINI_API_KEY", "")
        if not key or key.startswith("AIza..."):
            return None
        try:
            import google.generativeai as genai
            genai.configure(api_key=key)
            return genai.GenerativeModel(
                model_name=PROVIDER_META["gemini"]["model"],
                system_instruction=ARIA_SYSTEM_PROMPT,
                generation_config={"temperature": self._TEMPERATURE,
                                   "response_mime_type": "application/json"},
            )
        except ImportError:
            logger.warning("google-generativeai not installed")
            return None

    @retry(retry=retry_if_exception_type(_NETWORK_EXCEPTIONS),
           stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8), reraise=True)
    async def _call_gemini(self, client, prompt: str, max_tokens: int) -> str:
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(None, lambda: client.generate_content(
                prompt, generation_config={"max_output_tokens": max_tokens}
            ))
            return resp.text
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower() or "rate" in str(e).lower():
                raise RateLimitError(str(e)) from e
            raise

    # ------------------------------------------------------------------
    # Mistral  (free tier — mistral-small-latest)
    # ------------------------------------------------------------------

    def _init_mistral(self):
        key = os.getenv("MISTRAL_API_KEY", "")
        if not key or key.startswith("..."):
            return None
        try:
            from mistralai import Mistral
            return Mistral(api_key=key)
        except ImportError:
            logger.warning("mistralai package not installed — pip install mistralai")
            return None

    @retry(retry=retry_if_exception_type(_NETWORK_EXCEPTIONS),
           stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8), reraise=True)
    async def _call_mistral(self, client, prompt: str, max_tokens: int) -> str:
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(None, lambda: client.chat.complete(
                model=PROVIDER_META["mistral"]["model"],
                messages=[{"role": "system", "content": ARIA_SYSTEM_PROMPT},
                          {"role": "user",   "content": prompt}],
                temperature=self._TEMPERATURE,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            ))
            return resp.choices[0].message.content
        except Exception as e:
            msg = str(e)
            if "429" in msg or "rate" in msg.lower() or "quota" in msg.lower():
                raise RateLimitError(msg) from e
            raise

    # ------------------------------------------------------------------
    # Anthropic  (PAID — last resort, triggers dashboard warning)
    # ------------------------------------------------------------------

    def _init_anthropic(self):
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key or key.startswith("..."):
            return None
        try:
            import anthropic
            return anthropic.Anthropic(api_key=key)
        except ImportError:
            logger.warning("anthropic package not installed — pip install anthropic")
            return None

    @retry(retry=retry_if_exception_type(_NETWORK_EXCEPTIONS),
           stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8), reraise=True)
    async def _call_anthropic(self, client, prompt: str, max_tokens: int) -> str:
        loop = asyncio.get_event_loop()
        try:
            # Prefill the assistant turn with "{" — forces Claude to start JSON immediately,
            # preventing any preamble text that breaks JSON parsing.
            resp = await loop.run_in_executor(None, lambda: client.messages.create(
                model=PROVIDER_META["anthropic"]["model"],
                max_tokens=max_tokens,
                system=ARIA_SYSTEM_PROMPT,
                messages=[
                    {"role": "user",      "content": prompt},
                    {"role": "assistant", "content": "{"},   # prefill
                ],
            ))
            # Prepend the prefill character we consumed
            return "{" + resp.content[0].text
        except Exception as e:
            msg = str(e)
            if "429" in msg or "rate" in msg.lower() or "overloaded" in msg.lower():
                raise RateLimitError(msg) from e
            raise

    # ------------------------------------------------------------------
    # JSON parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """
        Robustly parse JSON from any LLM response.
        Handles: markdown fences, preamble text, trailing commas,
        truncated responses, and unescaped characters.
        """
        if not raw:
            raise ValueError("Empty response from AI provider.")

        # 1. Strip markdown fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned.strip())

        # 2. Try straight parse first
        try:
            result = json.loads(cleaned)
            return result if isinstance(result, dict) else {"value": result}
        except json.JSONDecodeError:
            pass

        # 3. Extract the outermost { ... } block (skips preamble text)
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            candidate = match.group()
            try:
                result = json.loads(candidate)
                return result if isinstance(result, dict) else {"value": result}
            except json.JSONDecodeError:
                # 4. Repair common JSON issues before giving up
                repaired = _repair_json(candidate)
                try:
                    result = json.loads(repaired)
                    return result if isinstance(result, dict) else {"value": result}
                except json.JSONDecodeError:
                    pass

        raise ValueError(f"No valid JSON found in response:\n{raw[:500]}")


# ---------------------------------------------------------------------------
# JSON repair helper
# ---------------------------------------------------------------------------

def _repair_json(s: str) -> str:
    """
    Best-effort repair of common JSON syntax errors produced by LLMs:
    - Trailing commas before } or ]
    - Single quotes instead of double quotes
    - Unescaped newlines inside strings
    - Truncated JSON (add closing braces/brackets)
    """
    # Remove trailing commas before closing braces/brackets
    s = re.sub(r",\s*([\}\]])", r"\1", s)

    # Replace single-quoted keys/values with double quotes
    # Only when the single quote is used as a JSON delimiter
    s = re.sub(r"(?<![\\])'", '"', s)

    # Remove control characters inside strings that break parsing
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s)

    # Try to close unclosed structures by counting braces
    open_braces   = s.count('{') - s.count('}')
    open_brackets = s.count('[') - s.count(']')
    if open_braces > 0 or open_brackets > 0:
        # Strip trailing comma if present before closing
        s = re.sub(r",\s*$", "", s.rstrip())
        s += ']' * max(open_brackets, 0)
        s += '}' * max(open_braces, 0)

    return s


# ---------------------------------------------------------------------------
# __main__ smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[2] / "aria-stock-agent" / ".env")
        load_dotenv()
    except ImportError:
        pass

    print("\n  ARIA AI Engine — self-test\n" + "─" * 44)
    try:
        engine = AIEngine()
        print(f"  Providers available : {' → '.join(engine._clients)}")
        print(f"  Active provider     : {engine.active_provider}")
        result = engine.sync_call('Return JSON: {"test": true, "message": "ARIA online"}')
        print(f"\n  ✓ Response from     : {result['provider']}")
        print(f"  ✓ Paid provider     : {engine.using_paid_provider}")
        print(f"  ✓ Data              : {result['data']}\n")
    except ConfigError as e:
        print(f"\n  ✘ ConfigError: {e}\n"); sys.exit(1)
    except RateLimitError as e:
        print(f"\n  ✘ RateLimitError: {e}\n"); sys.exit(1)
