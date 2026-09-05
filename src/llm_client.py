"""
src/llm_client.py - thin wrapper around the Groq API (free tier, no credit
card required) for the reconciliation agent's AI-assisted matching and
exception explanation tasks.

Swapped from the original Anthropic Claude client because Claude API access
wasn't available for this build. Groq's free tier is fast and easy to get a
key for; get one at https://console.groq.com/keys

Design note: every call site in this project checks `LLMClient.available`
first and has a deterministic/template fallback, so the pipeline runs
end-to-end even with zero API keys configured (useful for grading/demo
without needing live credentials, and required by the hackathon's
"failure recovery" judging criterion). Swapping providers here doesn't
require touching ai_matcher.py or exception_handler.py - they only depend
on this class's `available`, `call()`, and `get_stats()` interface.
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

try:
    from groq import Groq
except ImportError:
    Groq = None  # library not installed - stays unavailable, same as a missing key


class LLMClient:
    # openai/gpt-oss-120b is Groq's current recommended free-tier general-purpose
    # model (llama-3.3-70b-versatile, used in earlier drafts of this project,
    # was deprecated by Groq in Aug 2026). Override via GROQ_MODEL if needed.
    def __init__(self, model: Optional[str] = None):
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        self.model = model or os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
        self.call_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.call_log: list[dict] = []
        self._client = None
        self.available = False
        self.last_error: Optional[str] = None

        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        is_placeholder = not api_key or api_key in ("gsk_...", "gsk_your_actual_groq_api_key_here") or "your_actual" in api_key or api_key.endswith("...")
        if api_key and not is_placeholder and Groq is not None:
            try:
                # max_retries=0: the SDK's own internal retry logic (2 retries
                # by default) would otherwise stack with our retry loop below,
                # turning one bad call into up to 9 attempts. timeout is kept
                # short (default 60s per attempt) since a hung network call
                # here blocks the whole batch - fail fast and fall back
                # instead of leaving the pipeline silent for minutes.
                timeout_s = float(os.environ.get("GROQ_TIMEOUT_SECONDS", "15"))
                self._client = Groq(api_key=api_key, max_retries=0, timeout=timeout_s)
                self.available = True
            except Exception:
                self.available = False

    def call(self, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> Optional[dict]:
        """Single LLM call with retry, logging, and cost tracking.
        Returns None (never raises) if the client isn't configured or all
        retries fail - callers must handle the fallback themselves."""
        if not self.available:
            return None

        start = time.perf_counter()
        for attempt in range(3):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    # Both of this project's prompts already say "Respond ONLY
                    # with valid JSON", which is what json_object mode requires.
                    response_format={"type": "json_object"},
                )
                elapsed = time.perf_counter() - start
                self.call_count += 1
                usage = response.usage
                in_tok = getattr(usage, "prompt_tokens", 0) or 0
                out_tok = getattr(usage, "completion_tokens", 0) or 0
                self.total_input_tokens += in_tok
                self.total_output_tokens += out_tok
                self.call_log.append({
                    "task": system_prompt[:50],
                    "latency_s": round(elapsed, 2),
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                })
                text = response.choices[0].message.content
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    cleaned = text.replace("```json", "").replace("```", "").strip()
                    try:
                        return json.loads(cleaned)
                    except json.JSONDecodeError:
                        return {"raw_text": text, "parse_error": True}
            except Exception as e:
                # Groq's SDK raises several distinct error types (rate limit,
                # bad request, connection); catch broadly since every path
                # here just falls through to the caller's deterministic fallback.
                # Stored (not raised) so callers still get a clean fallback,
                # but `last_error` / `get_stats()` now expose *why* it failed
                # instead of failing silently.
                self.last_error = f"{type(e).__name__}: {e}"
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                return None
        return None

    def get_stats(self) -> dict:
        return {
            "total_calls": self.call_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "call_log": self.call_log,
            "last_error": self.last_error,
        }
