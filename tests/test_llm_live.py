# tests/test_llm_live.py
#
# Skipped by default. Run explicitly with:
#   pytest tests/test_llm_live.py --run-live
#
# Hits the REAL Groq API — costs quota.

import pytest
from src.llm_client import LLMClient

pytestmark = pytest.mark.skipif(
    "not config.getoption('--run-live')",
    reason="live LLM test skipped by default; pass --run-live to enable",
)


def test_live_upi_parse_returns_expected_keys():
    client = LLMClient()
    result = client.call(
        system_prompt="You are a UPI merchant ID resolver. Respond ONLY with valid JSON.",
        user_prompt='Parse this UPI merchant ID into a business name.\nUPI ID: SWGGY@YESB\n'
                    'Bank description: UPI/P2M/123456789012/SWGGY@YESB\n'
                    'Respond with: {"business_name": "...", "confidence": 0.0-1.0, "reasoning": "..."}',
    )
    assert "business_name" in result
    assert "confidence" in result
