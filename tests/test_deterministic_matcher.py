# tests/test_deterministic_matcher.py
from datetime import timedelta
from decimal import Decimal
from src.deterministic_matcher import run_deterministic_pipeline


def test_exact_id_match_confidence_is_1(sample_bank_txn, sample_gateway_txn):
    bank = {**sample_bank_txn, "raw_description": "UPI/P2M/123456789012/SWGGY@YESB"}
    gateway = {**sample_gateway_txn, "reference_number": "123456789012"}
    matched, unmatched = run_deterministic_pipeline({"bank": [bank], "gateway": [gateway], "invoice": []})
    assert len(matched) == 1
    assert matched[0]["confidence"] == 1.0
    assert matched[0]["match_method"] == "exact_id"


def test_amount_date_match_within_one_day(sample_bank_txn, sample_invoice):
    bank = dict(sample_bank_txn)
    invoice = {**sample_invoice, "date": bank["date"] + timedelta(days=1)}
    matched, unmatched = run_deterministic_pipeline({"bank": [bank], "invoice": [invoice], "gateway": []})
    assert len(matched) == 1
    assert matched[0]["confidence"] == 0.95


def test_amount_date_no_match_beyond_one_day(sample_bank_txn, sample_invoice):
    bank = dict(sample_bank_txn)
    invoice = {**sample_invoice, "date": bank["date"] + timedelta(days=3)}
    matched, unmatched = run_deterministic_pipeline({"bank": [bank], "invoice": [invoice], "gateway": []})
    assert len(matched) == 0


def test_composite_key_tolerates_two_rupee_delta(sample_bank_txn, sample_invoice):
    bank = {**sample_bank_txn, "amount": Decimal("2501.50")}
    invoice = dict(sample_invoice)
    matched, unmatched = run_deterministic_pipeline({"bank": [bank], "invoice": [invoice], "gateway": []})
    assert len(matched) == 1
    assert matched[0]["confidence"] == 0.85


def test_enforces_1to1_matching_keeps_highest_confidence(sample_bank_txn, sample_invoice):
    bank = dict(sample_bank_txn)
    exact_invoice = {**sample_invoice, "invoice_id": "INV_EXACT"}
    composite_invoice = {**sample_invoice, "invoice_id": "INV_COMPOSITE", "amount": Decimal("2501.50")}
    matched, unmatched = run_deterministic_pipeline(
        {"bank": [bank], "invoice": [exact_invoice, composite_invoice], "gateway": []}
    )
    bank_appearances = [m for m in matched if bank["txn_id"] in m.get("bank_txn_ids", []) or m.get("source_a_id") == bank["txn_id"]]
    assert len(bank_appearances) == 1


def test_zero_false_positives_on_clean_batch(sample_bank_txn, sample_invoice, sample_gateway_txn):
    records = {"bank": [], "invoice": [], "gateway": []}
    for i in range(20):
        b = {**sample_bank_txn, "txn_id": f"TXN{i}", "amount": Decimal(f"{1000 + i}.00")}
        inv = {**sample_invoice, "invoice_id": f"INV{i}", "amount": Decimal(f"{1000 + i}.00"),
               "date": b["date"]}
        records["bank"].append(b)
        records["invoice"].append(inv)
    matched, unmatched = run_deterministic_pipeline(records)
    assert len(matched) == 20
    assert len(unmatched) == 0
