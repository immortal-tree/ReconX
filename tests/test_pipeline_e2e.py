# tests/test_pipeline_e2e.py
import time
from unittest.mock import MagicMock
from src.pipeline import run_pipeline


def _mock_llm():
    mock = MagicMock()
    mock.available = True
    mock.call.return_value = {
        "business_name": "Swiggy",
        "confidence": 0.9,
        "reasoning": "mocked",
        "is_split": False,
        "explanation": "mocked exception note",
        "suggested_action": "review manually",
    }
    mock.call_count = 0
    return mock


def test_pipeline_runs_end_to_end_without_crashing(sample_bank_txn, sample_invoice, sample_gateway_txn):
    llm = _mock_llm()
    report = run_pipeline(
        bank=[sample_bank_txn], invoices=[sample_invoice], gateway=[sample_gateway_txn], llm_client=llm
    )
    assert report is not None
    assert "metrics_vs_ground_truth" in report or "summary" in report


def test_no_record_is_silently_dropped(sample_bank_txn, sample_invoice, sample_gateway_txn):
    llm = _mock_llm()
    total_in = 3
    report = run_pipeline(
        bank=[sample_bank_txn], invoices=[sample_invoice], gateway=[sample_gateway_txn], llm_client=llm
    )
    accounted_for = len(report.get("matches", [])) * 2 + len(report.get("exceptions", []))
    assert accounted_for >= total_in


def test_execution_stays_under_60_seconds_for_small_batch(sample_bank_txn, sample_invoice, sample_gateway_txn):
    llm = _mock_llm()
    start = time.perf_counter()
    run_pipeline(
        bank=[sample_bank_txn] * 10,
        invoices=[sample_invoice] * 10,
        gateway=[sample_gateway_txn] * 10,
        llm_client=llm,
    )
    assert time.perf_counter() - start < 60


def test_llm_call_budget_not_exceeded_for_small_batch(sample_bank_txn, sample_invoice, sample_gateway_txn):
    llm = _mock_llm()
    run_pipeline(
        bank=[sample_bank_txn] * 5,
        invoices=[sample_invoice] * 5,
        gateway=[sample_gateway_txn] * 5,
        llm_client=llm,
    )
    assert llm.call.call_count <= 30
