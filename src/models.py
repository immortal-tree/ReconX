"""
Pydantic v2 schemas for the AI Finance Controller.

Covers: BankTransaction, Invoice, PaymentGateway (the 3 ingestion sources),
plus MatchResult and Exception (pipeline outputs).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------

class SourceType(str, Enum):
    BANK = "bank"
    INVOICE = "invoice"
    GATEWAY = "gateway"


class ExceptionType(str, Enum):
    DUPLICATE = "DUPLICATE"
    MISSING_COUNTERPART = "MISSING_COUNTERPART"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    AMBIGUOUS = "AMBIGUOUS"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"


class MatchTier(str, Enum):
    EXACT_ID = "exact_id"
    AMOUNT_DATE = "amount_date"
    COMPOSITE_KEY = "composite_key"
    FUZZY_NAME = "fuzzy_name"
    SPLIT_PAYMENT = "split_payment"
    AMBIGUOUS_LLM = "ambiguous_llm"


# --------------------------------------------------------------------------
# Source records
# --------------------------------------------------------------------------

class BankTransaction(BaseModel):
    txn_id: str
    date: date
    amount: Decimal = Field(gt=0)
    raw_description: str
    reference_number: Optional[str] = None
    debit_credit: str  # "debit" | "credit"

    # populated during ingestion (Layer 1), not part of raw source data
    normalized_merchant: Optional[str] = None
    source: SourceType = SourceType.BANK

    @field_validator("debit_credit")
    @classmethod
    def check_dc(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in ("debit", "credit"):
            raise ValueError("debit_credit must be 'debit' or 'credit'")
        return v

    @field_validator("raw_description")
    @classmethod
    def strip_desc(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("raw_description cannot be empty")
        return v


class Invoice(BaseModel):
    invoice_id: str
    date: date
    amount: Decimal = Field(gt=0)
    vendor_name: str
    status: str = "unpaid"  # unpaid | paid | partial

    normalized_merchant: Optional[str] = None
    source: SourceType = SourceType.INVOICE

    @field_validator("vendor_name")
    @classmethod
    def strip_vendor(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("vendor_name cannot be empty")
        return v


class PaymentGateway(BaseModel):
    payment_id: str
    order_id: Optional[str] = None
    date: date
    amount: Decimal = Field(gt=0)
    vpa_or_method: Optional[str] = None  # UPI VPA, card last4, etc.
    status: str = "success"  # success | failed | pending
    reference_number: Optional[str] = None

    normalized_merchant: Optional[str] = None
    source: SourceType = SourceType.GATEWAY


# --------------------------------------------------------------------------
# Pipeline outputs
# --------------------------------------------------------------------------

class MatchResult(BaseModel):
    match_id: str
    tier: MatchTier
    confidence: float = Field(ge=0.0, le=1.0)
    bank_txn_ids: list[str] = Field(default_factory=list)
    invoice_ids: list[str] = Field(default_factory=list)
    gateway_payment_ids: list[str] = Field(default_factory=list)
    reasoning: Optional[str] = None


class Exception_(BaseModel):
    """Named Exception_ to avoid clashing with the Python builtin."""
    record_id: str
    source: SourceType
    exception_type: ExceptionType
    reason_code: str
    explanation: Optional[str] = None
    suggested_action: Optional[str] = None
    closest_candidate_id: Optional[str] = None
    amount: Optional[str] = None
    date: Optional[str] = None
