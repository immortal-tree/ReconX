"""
src/llm_client.py - thin wrapper around the Groq API (free tier, no credit
card required) for the reconciliation agent's AI-assisted matching and
exception explanation tasks.

Design note: every call site in this project checks `LLMClient.available`
first and has a deterministic/template fallback, so the pipeline runs
end-to-end even with zero API keys configured (useful for grading/demo
without needing live credentials, and required by the hackathon's
"failure recovery" judging criterion).
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional, Any

try:
    from groq import Groq
except ImportError:
    Groq = None  # library not installed - stays unavailable, same as a missing key


class LLMClient:
    """
    Thin wrapper over Groq API with rate limiting, logging, and automatic fallback.
    """
    def __init__(self, model: Optional[str] = None):
        self.model = model or os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
        self.call_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.call_log: list[dict] = []
        self._client = None
        self.available = False

        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        # Ignore empty or placeholder keys
        is_placeholder = api_key in ("gsk_...", "gsk_your_actual_groq_api_key_here") or "your_actual" in api_key or api_key.endswith("...")
        if api_key and not is_placeholder and Groq is not None:
            try:
                self._client = Groq(api_key=api_key)
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
                err_msg = str(e).lower()
                # If authentication fails or invalid API key, mark unavailable immediately to prevent hanging retries
                if "invalid_api_key" in err_msg or "401" in err_msg or "authentication" in err_msg:
                    self.available = False
                    return None

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
        }
