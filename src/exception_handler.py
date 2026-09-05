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


def classify_exception(record: dict, context: dict | None = None) -> str:
    # Check explicitly assigned type or default to MISSING_COUNTERPART
    exc_type = record.get("exception_type")
    if exc_type:
        return str(exc_type)
    reason = record.get("reason_code")
    if reason == "DUPLICATE_RECORD":
        return ExceptionType.DUPLICATE.value
    if reason == "AMOUNT_DELTA_EXCEEDS_TOLERANCE":
        return ExceptionType.AMOUNT_MISMATCH.value
    if reason == "NO_LLM_RESOLUTION_AVAILABLE":
        return ExceptionType.AMBIGUOUS.value
    return ExceptionType.MISSING_COUNTERPART.value


def generate_explanation(record: dict, exception_type: str, candidate: dict | None = None, llm_client: Any = None) -> dict:
    rec_id = record.get("id") or record.get("txn_id") or record.get("invoice_id") or record.get("payment_id") or "REC"
    src = record.get("source") or record.get("source_tag") or "bank"
    amt = record.get("amount") or "0.00"
    dt = str(record.get("date") or record.get("txn_date") or record.get("invoice_date") or "")

    if llm_client and getattr(llm_client, "available", False):
        result = llm_client.call(
            SYSTEM_PROMPT_EXCEPTION,
            USER_PROMPT_EXCEPTION.format(
                record_json={"id": rec_id, "source": str(src), "amount": str(amt), "date": dt},
                exception_type=exception_type,
                candidate_json={"id": candidate.get("id")} if candidate else "none",
            ),
        )
        if result and not result.get("parse_error"):
            return {
                "explanation": result.get("explanation", ""),
                "suggested_action": result.get("suggested_action", ""),
            }

    try:
        etype_enum = ExceptionType(exception_type)
    except ValueError:
        etype_enum = ExceptionType.MISSING_COUNTERPART

    tmpl_expl, tmpl_action = TEMPLATE_EXPLANATIONS[etype_enum]
    return {
        "explanation": tmpl_expl.format(record_id=rec_id, source=src, amount=amt, date=dt),
        "suggested_action": tmpl_action,
    }


def handle_unresolved_batch(unresolved: list[dict], llm_client: Any = None) -> list[dict]:
    exceptions = []
    for rec in unresolved:
        etype = classify_exception(rec)
        expl_data = generate_explanation(rec, etype, llm_client=llm_client)
        rec_id = rec.get("id") or rec.get("txn_id") or rec.get("invoice_id") or rec.get("payment_id") or "REC"
        src = rec.get("source") or rec.get("source_tag") or "bank"
        exceptions.append({
            "record_id": rec_id,
            "source": src,
            "exception_type": etype,
            "reason_code": rec.get("reason_code", "NO_CANDIDATE_FOUND"),
            "explanation": expl_data["explanation"],
            "suggested_action": expl_data["suggested_action"],
        })
    return exceptions


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
            amount=str(amount), date=date_str,
        )

    def classify_all(self) -> list[Exception_]:
        items_to_explain = []

        # Bank
        for b in self.matcher.unmatched_bank():
            nearest = self._nearest_invoice_by_name_date(b)
            if nearest and abs(b.amount - nearest.amount) <= Decimal("500.00"):
                items_to_explain.append((
                    b.txn_id, SourceType.BANK, ExceptionType.AMOUNT_MISMATCH,
                    b.amount, b.date.isoformat(), "AMOUNT_DELTA_EXCEEDS_TOLERANCE",
                    nearest.invoice_id,
                ))
            else:
                items_to_explain.append((
                    b.txn_id, SourceType.BANK, ExceptionType.MISSING_COUNTERPART,
                    b.amount, b.date.isoformat(), "NO_CANDIDATE_FOUND",
                    None,
                ))

        # Invoices
        ambiguous_ids = set(self.ai_matcher.ambiguous_flagged)
        for inv in self.matcher.unmatched_invoices():
            nearest = self._nearest_bank_by_name_date(inv)
            if nearest and abs(inv.amount - nearest.amount) <= Decimal("500.00"):
                items_to_explain.append((
                    inv.invoice_id, SourceType.INVOICE, ExceptionType.AMOUNT_MISMATCH,
                    inv.amount, inv.date.isoformat(), "AMOUNT_DELTA_EXCEEDS_TOLERANCE",
                    nearest.txn_id,
                ))
            elif inv.invoice_id in ambiguous_ids:
                items_to_explain.append((
                    inv.invoice_id, SourceType.INVOICE, ExceptionType.AMBIGUOUS,
                    inv.amount, inv.date.isoformat(), "NO_LLM_RESOLUTION_AVAILABLE",
                    None,
                ))
            else:
                items_to_explain.append((
                    inv.invoice_id, SourceType.INVOICE, ExceptionType.MISSING_COUNTERPART,
                    inv.amount, inv.date.isoformat(), "NO_CANDIDATE_FOUND",
                    None,
                ))

        # Gateway
        for g in self.matcher.unmatched_gateway():
            items_to_explain.append((
                g.payment_id, SourceType.GATEWAY, ExceptionType.MISSING_COUNTERPART,
                g.amount, g.date.isoformat(), "NO_CANDIDATE_FOUND",
                None,
            ))

        if self.llm and getattr(self.llm, "available", False):
            from concurrent.futures import ThreadPoolExecutor
            def _worker(item):
                return self._explain(*item)
            with ThreadPoolExecutor(max_workers=min(5, len(items_to_explain) or 1)) as executor:
                self.exceptions = list(executor.map(_worker, items_to_explain))
        else:
            self.exceptions = [self._explain(*item) for item in items_to_explain]

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
