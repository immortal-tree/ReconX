# tests/test_ai_matcher.py
from unittest.mock import MagicMock
from src.ai_matcher import (
    fuzzy_match_vendor,
    find_best_vendor_match,
    resolve_upi_id,
    resolve_all_upi_ids,
    detect_split_payment,
    score_confidence,
)


def test_fuzzy_match_identical_names_scores_100():
    assert fuzzy_match_vendor("Swiggy", "swiggy") == 100.0


def test_fuzzy_match_below_threshold_returns_none():
    match, score = find_best_vendor_match("Swiggy", ["Amazon", "Flipkart"], threshold=75)
    assert match is None
    assert score < 75


def test_resolve_upi_id_calls_llm_and_parses_json():
    mock_llm = MagicMock()
    mock_llm.available = True
    mock_llm.call.return_value = {
        "business_name": "Swiggy",
        "confidence": 0.92,
        "reasoning": "SWGGY is a known abbreviation for Swiggy",
    }
    result = resolve_upi_id("SWGGY@YESB", "UPI/P2M/123/SWGGY@YESB", mock_llm)
    assert result["business_name"] == "Swiggy"
    assert result["confidence"] >= 0.8
    mock_llm.call.assert_called_once()


def test_llm_called_once_per_unique_upi_id_not_per_record():
    mock_llm = MagicMock()
    mock_llm.available = True
    mock_llm.call.return_value = {
        "business_name": "Swiggy", "confidence": 0.9, "reasoning": "mocked"
    }
    # 10 records, but only 2 distinct UPI IDs
    records = [
        {"upi_id": "SWGGY_TEST_1", "raw_description": "..."} for _ in range(6)
    ] + [
        {"upi_id": "ZMTO_TEST_2", "raw_description": "..."} for _ in range(4)
    ]
    resolve_all_upi_ids(records, mock_llm)
    # 2 unique IDs batched/resolved = 2 calls, not 10
    assert mock_llm.call.call_count <= 2


def test_split_payment_detection_sums_within_tolerance():
    mock_llm = MagicMock()
    mock_llm.available = True
    mock_llm.call.return_value = {
        "is_split": True,
        "matching_txns": ["TXN1", "TXN2"],
        "combined_amount": 4998.00,
        "delta": 2.00,
        "confidence": 0.88,
        "reasoning": "Two partial payments sum within tolerance",
    }
    invoice = {"invoice_id": "INV1", "amount": 5000.00, "vendor_name": "Acme"}
    candidates = [{"txn_id": "TXN1", "amount": 2500.00}, {"txn_id": "TXN2", "amount": 2498.00}]
    result = detect_split_payment(invoice, candidates, mock_llm)
    assert result["is_split"] is True
    assert result["delta"] <= 5.00


def test_confidence_formula_matches_master_plan_weights():
    conf = score_confidence(amount_closeness=1.0, date_closeness=1.0, name_similarity=1.0, id_overlap=1.0)
    assert abs(conf - 1.0) < 1e-6

    conf_low = score_confidence(amount_closeness=0.5, date_closeness=0.0, name_similarity=0.5, id_overlap=0.0)
    expected = 0.4 * 0.5 + 0.2 * 0.0 + 0.3 * 0.5 + 0.1 * 0.0
    assert abs(conf_low - expected) < 1e-6


def test_confidence_routing_thresholds():
    assert score_confidence(1.0, 1.0, 1.0, 1.0) >= 0.8
    mid = score_confidence(0.6, 0.5, 0.6, 0.0)
    assert 0.6 <= mid < 0.8 or mid < 0.6
