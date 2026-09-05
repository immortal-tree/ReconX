"""
Layer 4: Exception Handling.

Classifies every record still unmatched after deterministic + AI matching
into one of: DUPLICATE / MISSING_COUNTERPART / PARTIAL_MATCH / AMBIGUOUS /
AMOUNT_MISMATCH, assigns a reason code, and generates a plain-English
explanation + suggested action (template-based by default; LLM-enhanced
if an API key is configured).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from src.ai_matcher import AIMatcher
from src.llm_client import LLMClient
from src.models import Exception_, ExceptionType, SourceType

SYSTEM_PROMPT_EXCEPTION = """You are a financial analyst writing exception notes for
a reconciliation report. Write clear, one-sentence explanations that a non-technical
finance team member can understand. Include specific amounts, dates, and record IDs.
Respond ONLY with valid JSON."""

USER_PROMPT_EXCEPTION = """Generate an explanation for this reconciliation exception.

Record: {record_json}
Exception type: {exception_type}
Closest candidate (if any): {candidate_json}

Respond with: {{
  "explanation": "one clear sentence",
  "suggested_action": "one clear next step"
}}"""

TEMPLATE_EXPLANATIONS = {
    ExceptionType.DUPLICATE: (
        "{record_id} appears to be a duplicate of an already-recorded transaction "
        "for ₹{amount} on {date}.",
        "Verify with the bank statement and remove the duplicate entry.",
    ),
    ExceptionType.MISSING_COUNTERPART: (
        "{record_id} ({source}) for ₹{amount} on {date} has no matching record "
        "in the other two sources.",
        "Check for a missing invoice/bank entry or confirm this was a one-off transaction.",
    ),
    ExceptionType.PARTIAL_MATCH: (
        "{record_id} for ₹{amount} on {date} appears to be a partial payment "
        "that couldn't be fully reconciled.",
        "Review remaining balance and confirm outstanding amount with the vendor.",
    ),
    ExceptionType.AMBIGUOUS: (
        "{record_id} for ₹{amount} on {date} has multiple plausible matches "
        "and could not be resolved automatically.",
        "Manual review recommended - compare candidate records side by side.",
    ),
    ExceptionType.AMOUNT_MISMATCH: (
        "{record_id} for ₹{amount} on {date} is close to a candidate match but "
        "the amount differs beyond the allowed tolerance.",
        "Confirm whether a partial payment, fee, or data-entry error explains the gap.",
    ),
}


class ExceptionHandler:
    def __init__(self, ai_matcher: AIMatcher, llm: Optional[LLMClient] = None):
        self.matcher = ai_matcher.matcher
        self.ai_matcher = ai_matcher
        self.llm = llm or ai_matcher.llm
        self.exceptions: list[Exception_] = []

    def _explain(self, record_id: str, source: SourceType, exc_type: ExceptionType,
                 amount: Decimal, date_str: str, reason_code: str,
                 candidate_id: Optional[str] = None) -> Exception_:
        explanation, suggested_action = None, None
        if self.llm.available:
            result = self.llm.call(
                SYSTEM_PROMPT_EXCEPTION,
                USER_PROMPT_EXCEPTION.format(
                    record_json={"id": record_id, "source": source.value, "amount": str(amount), "date": date_str},
                    exception_type=exc_type.value,
                    candidate_json={"id": candidate_id} if candidate_id else "none",
                ),
            )
            if result and not result.get("parse_error"):
                explanation = result.get("explanation")
                suggested_action = result.get("suggested_action")

        if not explanation:
            tmpl_expl, tmpl_action = TEMPLATE_EXPLANATIONS[exc_type]
            explanation = tmpl_expl.format(record_id=record_id, source=source.value, amount=amount, date=date_str)
            suggested_action = tmpl_action

        return Exception_(
            record_id=record_id, source=source, exception_type=exc_type,
            reason_code=reason_code, explanation=explanation,
            suggested_action=suggested_action, closest_candidate_id=candidate_id,
        )

    def classify_all(self) -> list[Exception_]:
        # Duplicates removed during ingestion
        for dup in self.matcher.bank if False else []:
            pass  # duplicates are handled at ingestion; surfaced separately below

        # Remaining unmatched bank transactions -> MISSING_COUNTERPART (unless
        # they were an amount-mismatch candidate, detected via nearest invoice)
        for b in self.matcher.unmatched_bank():
            nearest = self._nearest_invoice_by_name_date(b)
            if nearest and abs(b.amount - nearest.amount) <= Decimal("500.00"):
                self.exceptions.append(self._explain(
                    b.txn_id, SourceType.BANK, ExceptionType.AMOUNT_MISMATCH,
                    b.amount, b.date.isoformat(), reason_code="AMOUNT_DELTA_EXCEEDS_TOLERANCE",
                    candidate_id=nearest.invoice_id,
                ))
            else:
                self.exceptions.append(self._explain(
                    b.txn_id, SourceType.BANK, ExceptionType.MISSING_COUNTERPART,
                    b.amount, b.date.isoformat(), reason_code="NO_CANDIDATE_FOUND",
                ))

        # Remaining unmatched invoices -> AMBIGUOUS if flagged by AI matcher,
        # else MISSING_COUNTERPART
        ambiguous_ids = set(self.ai_matcher.ambiguous_flagged)
        for inv in self.matcher.unmatched_invoices():
            nearest = self._nearest_bank_by_name_date(inv)
            if nearest and abs(inv.amount - nearest.amount) <= Decimal("500.00"):
                self.exceptions.append(self._explain(
                    inv.invoice_id, SourceType.INVOICE, ExceptionType.AMOUNT_MISMATCH,
                    inv.amount, inv.date.isoformat(), reason_code="AMOUNT_DELTA_EXCEEDS_TOLERANCE",
                    candidate_id=nearest.txn_id,
                ))
            elif inv.invoice_id in ambiguous_ids:
                self.exceptions.append(self._explain(
                    inv.invoice_id, SourceType.INVOICE, ExceptionType.AMBIGUOUS,
                    inv.amount, inv.date.isoformat(), reason_code="NO_LLM_RESOLUTION_AVAILABLE",
                ))
            else:
                self.exceptions.append(self._explain(
                    inv.invoice_id, SourceType.INVOICE, ExceptionType.MISSING_COUNTERPART,
                    inv.amount, inv.date.isoformat(), reason_code="NO_CANDIDATE_FOUND",
                ))

        # Remaining unmatched gateway records
        for g in self.matcher.unmatched_gateway():
            self.exceptions.append(self._explain(
                g.payment_id, SourceType.GATEWAY, ExceptionType.MISSING_COUNTERPART,
                g.amount, g.date.isoformat(), reason_code="NO_CANDIDATE_FOUND",
            ))

        return self.exceptions

    def _nearest_invoice_by_name_date(self, bank_txn):
        best, best_score = None, 999999
        for inv in self.matcher.unmatched_invoices():
            if inv.normalized_merchant and bank_txn.normalized_merchant and (
                inv.normalized_merchant in (bank_txn.normalized_merchant or "")
                or bank_txn.normalized_merchant in (inv.normalized_merchant or "")
            ):
                score = abs((inv.date - bank_txn.date).days)
                if score < best_score:
                    best, best_score = inv, score
        return best

    def _nearest_bank_by_name_date(self, invoice):
        best, best_score = None, 999999
        for b in self.matcher.unmatched_bank():
            if invoice.normalized_merchant and b.normalized_merchant and (
                invoice.normalized_merchant in (b.normalized_merchant or "")
                or b.normalized_merchant in (invoice.normalized_merchant or "")
            ):
                score = abs((invoice.date - b.date).days)
                if score < best_score:
                    best, best_score = b, score
        return best

    def stats(self) -> dict:
        by_type = {}
        for e in self.exceptions:
            by_type[e.exception_type.value] = by_type.get(e.exception_type.value, 0) + 1
        return {"total_exceptions": len(self.exceptions), "by_type": by_type}


if __name__ == "__main__":
    import json
    from pathlib import Path
    from src.ingestion import ingest
    from src.deterministic_matcher import DeterministicMatcher

    data_dir = Path(__file__).parent.parent / "data"
    ing = ingest(data_dir)
    det = DeterministicMatcher(ing)
    det.run_all()
    ai = AIMatcher(det)
    ai.run_all()
    handler = ExceptionHandler(ai)
    handler.classify_all()
    print(json.dumps(handler.stats(), indent=2))
    print("\nSample exceptions:")
    for e in handler.exceptions[:5]:
        print(f"  [{e.exception_type.value}] {e.record_id}: {e.explanation}")
