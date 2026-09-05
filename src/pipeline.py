"""
src/pipeline.py - programmatic entrypoint for running the 5-layer reconciliation pipeline.
Accepts raw record dicts or Pydantic model objects, executes layers 1-5, and returns the full JSON report.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from src.ai_matcher import AIMatcher
from src.deterministic_matcher import DeterministicMatcher
from src.exception_handler import ExceptionHandler
from src.ingestion import IngestionResult
from src.llm_client import LLMClient
from src.models import BankTransaction, Invoice, PaymentGateway
from src.reporter import build_report


def run_pipeline(
    bank: list[dict | BankTransaction],
    invoices: list[dict | Invoice],
    gateway: list[dict | PaymentGateway],
    llm_client: Optional[LLMClient] = None,
    ground_truth: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """
    Executes the 5-layer reconciliation pipeline on provided record lists.
    Returns the report dictionary containing summary, matches, exceptions, and metrics.
    """
    start = time.perf_counter()

    # Layer 1: Ingestion / Normalization
    ing = IngestionResult()
    for b in bank:
        if isinstance(b, dict):
            try:
                txn = BankTransaction(**b)
                txn.normalized_merchant = (txn.raw_description or "").lower()
                ing.bank.append(txn)
            except Exception as e:
                ing.rejected.append({"source": "bank", "raw": b, "error": str(e)})
        else:
            ing.bank.append(b)

    for inv in invoices:
        if isinstance(inv, dict):
            try:
                i_obj = Invoice(**inv)
                i_obj.normalized_merchant = (i_obj.vendor_name or "").lower()
                ing.invoices.append(i_obj)
            except Exception as e:
                ing.rejected.append({"source": "invoice", "raw": inv, "error": str(e)})
        else:
            ing.invoices.append(inv)

    for gw in gateway:
        if isinstance(gw, dict):
            try:
                g_obj = PaymentGateway(**gw)
                g_obj.normalized_merchant = (g_obj.vpa_or_method or "").lower()
                ing.gateway.append(g_obj)
            except Exception as e:
                ing.rejected.append({"source": "gateway", "raw": gw, "error": str(e)})
        else:
            ing.gateway.append(gw)

    # Layer 2: Deterministic Matching
    det = DeterministicMatcher(ing)
    det.run_all()

    # Layer 3: AI Matching
    ai = AIMatcher(det, llm=llm_client)
    ai.run_all()

    # Layer 4: Exception Handling
    handler = ExceptionHandler(ai, llm=llm_client)
    handler.classify_all()

    elapsed = time.perf_counter() - start

    # Layer 5: Reporting
    gt = ground_truth or []
    execution_metadata = {
        "execution_seconds": round(elapsed, 3),
        "llm_calls": ai.llm.call_count if ai.llm else 0,
        "llm_available": ai.llm.available if ai.llm else False,
    }
    report = build_report(ai, handler, gt, execution_metadata)
    return report
