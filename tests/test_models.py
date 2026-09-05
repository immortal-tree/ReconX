# tests/test_models.py
import pytest
from pydantic import ValidationError
from src.models import BankTransaction, Invoice, PaymentGateway


def test_bank_transaction_accepts_valid_record(sample_bank_txn):
    txn = BankTransaction(**sample_bank_txn)
    assert txn.amount > 0
    assert txn.debit_credit in ("credit", "debit")


def test_bank_transaction_rejects_negative_amount(sample_bank_txn):
    bad = {**sample_bank_txn, "amount": -100}
    with pytest.raises(ValidationError):
        BankTransaction(**bad)


def test_invoice_requires_amount_and_vendor(sample_invoice):
    incomplete = dict(sample_invoice)
    incomplete.pop("amount")
    with pytest.raises(ValidationError):
        Invoice(**incomplete)


def test_invoice_accepts_valid_record(sample_invoice):
    inv = Invoice(**sample_invoice)
    assert inv.status in ("unpaid", "paid", "partial")


def test_payment_gateway_status_validation(sample_gateway_txn):
    pg = PaymentGateway(**sample_gateway_txn)
    assert pg.status in ("success", "failed", "pending")


def test_payment_gateway_accepts_valid_record(sample_gateway_txn):
    pg = PaymentGateway(**sample_gateway_txn)
    assert pg.amount > 0
