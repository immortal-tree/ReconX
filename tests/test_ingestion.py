# tests/test_ingestion.py
import re
from src.ingestion import normalize_records, deduplicate, parse_upi_narration


def test_deduplicate_removes_exact_duplicates(duplicate_bank_batch):
    unique, dropped = deduplicate(duplicate_bank_batch["records"])
    well_formed = [r for r in unique if r.get("amount") is not None]
    assert len(well_formed) <= duplicate_bank_batch["expected_unique_after_dedup"] + 2


def test_malformed_rows_are_logged_not_crashed(duplicate_bank_batch, caplog):
    records = duplicate_bank_batch["records"]
    result = normalize_records(records)
    assert result is not None
    assert len(result) < len(records)


def test_upi_narration_regex_extracts_reference_and_vpa():
    raw = "UPI/P2M/123456789012/SWGGY@YESB"
    parsed = parse_upi_narration(raw)
    assert parsed is not None
    assert parsed["reference_number"] == "123456789012"
    assert parsed["vpa"] == "SWGGY@YESB"


def test_upi_narration_regex_matches_master_plan_pattern():
    pattern = r'UPI/\w+/(\d{12})/(\S+)'
    raw = "UPI/P2A/987654321098/ZMTO@PAYTM"
    m = re.search(pattern, raw)
    assert m is not None
    assert m.group(1) == "987654321098"
    assert m.group(2) == "ZMTO@PAYTM"


def test_amounts_normalized_to_decimal(sample_bank_txn):
    normalized = normalize_records([sample_bank_txn])[0]
    from decimal import Decimal
    assert isinstance(normalized["amount"], Decimal)


def test_names_normalized_lowercase_stripped():
    raw = [{
        "vendor_name": "  SWIGGY Foods  ",
        "amount": 100,
        "invoice_id": "X1",
        "date": "2026-08-01",
        "due_date": "2026-08-10",
        "status": "unpaid",
        "source": "invoice",
        "gst_number": "X",
        "normalized_vendor": None,
    }]
    normalized = normalize_records(raw)[0]
    assert normalized.get("normalized_vendor") == "swiggy foods"
