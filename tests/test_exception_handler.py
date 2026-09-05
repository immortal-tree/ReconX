# tests/test_exception_handler.py
from unittest.mock import MagicMock
from src.exception_handler import classify_exception, generate_explanation, handle_unresolved_batch

VALID_TYPES = {"DUPLICATE", "MISSING_COUNTERPART", "PARTIAL_MATCH", "AMBIGUOUS", "AMOUNT_MISMATCH"}


def test_classify_exception_returns_valid_taxonomy_value(sample_bank_txn):
    result = classify_exception(sample_bank_txn, context={})
    assert result in VALID_TYPES


def test_generate_explanation_includes_amount_and_id(sample_bank_txn):
    mock_llm = MagicMock()
    mock_llm.available = True
    mock_llm.call.return_value = {
        "explanation": f"No invoice found matching {sample_bank_txn['txn_id']} for amount 2500.00",
        "suggested_action": "Check for a missing invoice from this vendor",
    }
    result = generate_explanation(sample_bank_txn, "MISSING_COUNTERPART", None, mock_llm)
    assert sample_bank_txn["txn_id"] in result["explanation"]
    assert result["suggested_action"]


def test_100_percent_exception_surfacing_no_silent_drops():
    mock_llm = MagicMock()
    mock_llm.available = True
    mock_llm.call.return_value = {"explanation": "placeholder", "suggested_action": "review"}
    unresolved = [{"id": f"REC{i}", "amount": 100 + i, "source": "bank"} for i in range(34)]
    exceptions = handle_unresolved_batch(unresolved, mock_llm)
    assert len(exceptions) == len(unresolved)
    for exc in exceptions:
        assert exc["exception_type"] in VALID_TYPES
        assert exc["explanation"]
        assert exc["suggested_action"]
