import sys
from pathlib import Path
from datetime import date
from decimal import Decimal
import pytest

# Ensure root directory is on sys.path for src imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run tests that make real LLM API calls (costs quota).",
    )


@pytest.fixture
def sample_bank_txn():
    return {
        "txn_id": "TXN0001",
        "date": date(2026, 8, 1),
        "amount": Decimal("2500.00"),
        "debit_credit": "debit",
        "raw_description": "UPI/P2M/123456789012/SWGGY@YESB",
        "reference_number": "123456789012",
        "normalized_merchant": None,
        "source": "bank",
    }


@pytest.fixture
def sample_invoice():
    return {
        "invoice_id": "INV1001",
        "date": date(2026, 7, 30),
        "due_date": date(2026, 8, 15),
        "amount": Decimal("2500.00"),
        "vendor_name": "Swiggy",
        "normalized_merchant": "swiggy",
        "gst_number": "29ABCDE1234F1Z5",
        "status": "unpaid",
        "source": "invoice",
    }


@pytest.fixture
def sample_gateway_txn():
    return {
        "payment_id": "PG5001",
        "date": date(2026, 8, 1),
        "amount": Decimal("2500.00"),
        "vpa_or_method": "SWGGY@YESB",
        "normalized_merchant": None,
        "reference_number": "123456789012",
        "status": "success",
        "source": "gateway",
    }


@pytest.fixture
def duplicate_bank_batch(sample_bank_txn):
    """4 duplicates + 2 malformed rows, per the Phase 2 checkpoint in master_build_plan.md."""
    good = sample_bank_txn
    duplicate = dict(good)  # identical hash key
    malformed_missing_amount = {**good, "txn_id": "TXN0099", "amount": None}
    malformed_bad_date = {**good, "txn_id": "TXN0098", "date": "not-a-date"}
    return {
        "records": [good, duplicate, duplicate, duplicate, duplicate,
                    malformed_missing_amount, malformed_bad_date],
        "expected_unique_after_dedup": 1,
        "expected_malformed_logged": 2,
    }


@pytest.fixture
def ground_truth_fixture():
    """Tiny hand-computed ground truth set for reporter.py metric tests."""
    return {
        "true_matches": [
            {"bank_txn_id": "TXN0001", "invoice_id": "INV1001"},
            {"bank_txn_id": "TXN0002", "invoice_id": "INV1002"},
        ],
        "predicted_matches": [
            {"bank_txn_id": "TXN0001", "invoice_id": "INV1001"},
            {"bank_txn_id": "TXN0003", "invoice_id": "INV1003"},
        ],
        "expected_precision": 0.5,
        "expected_recall": 0.5,
        "expected_f1": 0.5,
    }
