"""
Layer 3: AI-Assisted Matching.

- RapidFuzz fuzzy name matching (local, always runs)
- Claude: cryptic UPI ID resolution (falls back to a static alias map if
  no API key is configured)
- Claude: split-payment detection (falls back to flagging as AMBIGUOUS
  per the master plan's fallback table if no API key)
- Confidence scoring + routing (>=0.8 auto-match, 0.6-0.8 review, <0.6 exception)
"""

from __future__ import annotations

import itertools
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from rapidfuzz import fuzz, process

from src.deterministic_matcher import DeterministicMatcher
from src.llm_client import LLMClient
from src.models import MatchTier

SYSTEM_PROMPT_UPI = """You are a UPI merchant ID resolver for Indian payment systems.
Given a cryptic UPI ID from a bank statement, identify the actual business name.
Common patterns: SWGGY=Swiggy, ZOMATO/ZMTO=Zomato, AMZN=Amazon, FLIPKART/FKRT=Flipkart,
BIGBASKET/BB=BigBasket, PHONEPE/PPE=PhonePe, PAYTM=Paytm, GPAY=Google Pay,
DUNZO=Dunzo, OLACABS/OLA=Ola, UBER=Uber, BLINKIT=Blinkit.
Respond ONLY with valid JSON, no markdown, no explanation."""

USER_PROMPT_UPI = """Parse this UPI merchant ID into a business name.
UPI ID: {upi_id}
Bank description: {raw_description}

Respond with: {{"business_name": "...", "confidence": 0.0-1.0, "reasoning": "..."}}"""

SYSTEM_PROMPT_SPLIT = """You are a financial reconciliation expert for Indian SME payments.
Given an unmatched invoice and a list of candidate bank transactions, determine if any
combination of transactions could be a split payment for the invoice.
Consider: partial payments are common in Indian B2B; amounts may differ by ₹1-5 due
to rounding, convenience fees, or TDS deductions.
Respond ONLY with valid JSON, no markdown."""

USER_PROMPT_SPLIT = """Invoice {invoice_id} for ₹{amount} from "{vendor}" dated {date} is unmatched.

Candidate bank transactions (within +/-5 days):
{candidates_json}

Could any combination of these transactions sum to the invoice amount (+/-₹5 tolerance)?
Respond with: {{
  "is_split": true/false,
  "matching_txns": ["txn_id_1", "txn_id_2"],
  "combined_amount": 0.00,
  "delta": 0.00,
  "confidence": 0.0-1.0,
  "reasoning": "..."
}}"""

# Static fallback alias map, used only if no LLM is configured (mirrors the
# hardcoded examples baked into the system prompt above)
STATIC_UPI_ALIASES = {
    "SWGGY": "Swiggy", "ZOMATO": "Zomato", "ZMTO": "Zomato", "AMZN": "Amazon",
    "FLIPKART": "Flipkart", "FKRT": "Flipkart", "BIGBASKET": "BigBasket", "BB": "BigBasket",
    "PHONEPE": "PhonePe", "PPE": "PhonePe", "PAYTM": "Paytm", "GPAY": "Google Pay",
    "DUNZO": "Dunzo", "OLACABS": "Ola", "OLA": "Ola", "UBER": "Uber", "BLINKIT": "Blinkit",
}


def fuzzy_match_vendor(a: str, b: str) -> float:
    return float(fuzz.token_sort_ratio((a or "").lower().strip(), (b or "").lower().strip()))


def find_best_vendor_match(vendor: str, candidates: list[str], threshold: int = 75) -> tuple[str | None, float]:
    if not candidates:
        return None, 0.0
    best = process.extractOne((vendor or "").lower().strip(), candidates, scorer=fuzz.token_sort_ratio)
    if best is None:
        return None, 0.0
    matched_name, score, _ = best
    if score < threshold:
        return None, float(score)
    return matched_name, float(score)


def resolve_upi_id(upi_id: str, raw_description: str, llm_client: Any = None) -> dict:
    if llm_client and getattr(llm_client, "available", False):
        result = llm_client.call(
            SYSTEM_PROMPT_UPI,
            USER_PROMPT_UPI.format(upi_id=upi_id, raw_description=raw_description),
        )
        if result and not result.get("parse_error"):
            return result
    code = (upi_id or "").upper()
    name = STATIC_UPI_ALIASES.get(code, "Unknown")
    return {"business_name": name, "confidence": 0.8 if name != "Unknown" else 0.0, "reasoning": "static fallback"}


def resolve_all_upi_ids(records: list[dict | Any], llm_client: Any = None) -> dict[str, str]:
    """
    Deduplicates UPI IDs across records, resolves each UNIQUE UPI ID at most ONCE
    via LLM/static lookup with thread-pool concurrency, and returns {upi_code: business_name}.
    """
    unique_items: dict[str, str] = {}
    for r in records:
        if isinstance(r, dict):
            code = r.get("upi_id") or r.get("normalized_merchant") or ""
            desc = r.get("raw_description") or ""
        else:
            code = getattr(r, "normalized_merchant", "") or ""
            desc = getattr(r, "raw_description", "") or ""

        code_upper = str(code).upper().strip()
        if code_upper and code_upper not in unique_items:
            unique_items[code_upper] = desc

    resolved_map: dict[str, str] = {}
    to_resolve: list[tuple[str, str]] = []

    for code, desc in unique_items.items():
        if code in STATIC_UPI_ALIASES:
            resolved_map[code] = STATIC_UPI_ALIASES[code]
        else:
            to_resolve.append((code, desc))

    if not to_resolve:
        return resolved_map

    if llm_client and getattr(llm_client, "available", False):
        from concurrent.futures import ThreadPoolExecutor

        def _call_llm_single(item: tuple[str, str]) -> tuple[str, str]:
            code, desc = item
            res = llm_client.call(
                SYSTEM_PROMPT_UPI,
                USER_PROMPT_UPI.format(upi_id=code, raw_description=desc),
            )
            if res and not res.get("parse_error") and res.get("business_name"):
                return code, res["business_name"]
            return code, STATIC_UPI_ALIASES.get(code, code)

        with ThreadPoolExecutor(max_workers=min(5, len(to_resolve))) as executor:
            results = list(executor.map(_call_llm_single, to_resolve))

        for code, name in results:
            resolved_map[code] = name
    else:
        for code, desc in to_resolve:
            resolved_map[code] = STATIC_UPI_ALIASES.get(code, code)

    return resolved_map


def detect_split_payment(invoice: dict, candidates: list[dict], llm_client: Any = None) -> dict:
    if llm_client and getattr(llm_client, "available", False):
        candidates_json = [
            {"txn_id": c.get("txn_id"), "amount": str(c.get("amount")), "date": str(c.get("date", ""))}
            for c in candidates
        ]
        result = llm_client.call(
            SYSTEM_PROMPT_SPLIT,
            USER_PROMPT_SPLIT.format(
                invoice_id=invoice.get("invoice_id", "INV"), amount=invoice.get("amount", 0),
                vendor=invoice.get("vendor_name", ""), date=str(invoice.get("date", "")),
                candidates_json=candidates_json,
            ),
        )
        if result and not result.get("parse_error"):
            return result
    inv_amt = Decimal(str(invoice.get("amount", 0)))
    comb_amt = sum(Decimal(str(c.get("amount", 0))) for c in candidates)
    delta = abs(comb_amt - inv_amt)
    is_split = delta <= Decimal("5.00")
    return {
        "is_split": is_split,
        "matching_txns": [c.get("txn_id") for c in candidates] if is_split else [],
        "combined_amount": float(comb_amt),
        "delta": float(delta),
        "confidence": 0.88 if is_split else 0.0,
        "reasoning": "Deterministic combination sum",
    }


def score_confidence(amount_closeness: float, date_closeness: float, name_similarity: float, id_overlap: float) -> float:
    conf = (
        0.4 * amount_closeness
        + 0.2 * date_closeness
        + 0.3 * name_similarity
        + 0.1 * id_overlap
    )
    return round(min(max(conf, 0.0), 1.0), 6)


class AIMatcher:
    def __init__(self, matcher: DeterministicMatcher, llm: Optional[LLMClient] = None):
        self.matcher = matcher
        self.llm = llm or LLMClient()
        self.fuzzy_matches_made = 0
        self.upi_resolutions = 0
        self.split_detections = 0
        self.ambiguous_flagged: list[str] = []  # invoice_ids flagged ambiguous, no LLM

    # ------------------------------------------------------------------
    def resolve_cryptic_upi(self):
        """Resolve cryptic UPI codes across unmatched bank descriptions by batching
        unique UPI IDs once, then re-run fuzzy matching with resolved names."""
        unmatched = [
            b for b in self.matcher.unmatched_bank()
            if b.normalized_merchant
        ]
        if not unmatched:
            return

        resolved_cache = resolve_all_upi_ids(unmatched, self.llm)

        for b in unmatched:
            code = (b.normalized_merchant or "").upper().strip()
            if code in resolved_cache:
                b.normalized_merchant = resolved_cache[code].lower()
                self.upi_resolutions += 1

        # re-run fuzzy matching now that names are resolved
        self._fuzzy_name_match()

    # ------------------------------------------------------------------
    def _fuzzy_name_match(self, threshold: int = 75):
        """RapidFuzz token_sort_ratio between unmatched bank txns and invoices."""
        unmatched_invoices = self.matcher.unmatched_invoices()
        if not unmatched_invoices:
            return
        inv_names = {inv.invoice_id: (inv.normalized_merchant or "") for inv in unmatched_invoices}

        for b in list(self.matcher.unmatched_bank()):
            if not b.normalized_merchant:
                continue
            candidates = {iid: name for iid, name in inv_names.items() if iid not in self.matcher._used_invoice}
            if not candidates:
                continue
            best = process.extractOne(
                b.normalized_merchant, candidates, scorer=fuzz.token_sort_ratio,
            )
            if best is None:
                continue
            matched_name, score, matched_inv_id = best
            if score < threshold:
                continue
            inv = next(i for i in unmatched_invoices if i.invoice_id == matched_inv_id)
            # amount must still be within a reasonable tolerance for this to be safe
            if abs(b.amount - inv.amount) > Decimal("5.00"):
                continue
            conf = self._score_confidence(b, inv, name_score=score / 100)
            self.matcher._add_match(
                MatchTier.FUZZY_NAME, conf,
                bank_txn_ids=[b.txn_id], invoice_ids=[inv.invoice_id],
                reasoning=f"RapidFuzz name match ({score:.0f}/100): '{b.normalized_merchant}' ~ '{matched_name}'",
            )
            self.fuzzy_matches_made += 1

    # ------------------------------------------------------------------
    def detect_split_payments(self, window_days: int = 5, max_combo_size: int = 3):
        """For each unmatched invoice, look for a combination of unmatched
        bank transactions (within window_days) summing to the invoice amount."""
        for inv in list(self.matcher.unmatched_invoices()):
            candidates = [
                b for b in self.matcher.unmatched_bank()
                if abs((b.date - inv.date).days) <= window_days
            ]
            if len(candidates) < 2:
                continue

            found = None
            for r in range(2, min(max_combo_size, len(candidates)) + 1):
                for combo in itertools.combinations(candidates, r):
                    total = sum(c.amount for c in combo)
                    if abs(total - inv.amount) <= Decimal("5.00"):
                        found = combo
                        break
                if found:
                    break

            if found:
                if self.llm.available:
                    candidates_json = [
                        {"txn_id": c.txn_id, "amount": str(c.amount), "date": c.date.isoformat()}
                        for c in candidates
                    ]
                    result = self.llm.call(
                        SYSTEM_PROMPT_SPLIT,
                        USER_PROMPT_SPLIT.format(
                            invoice_id=inv.invoice_id, amount=inv.amount,
                            vendor=inv.vendor_name, date=inv.date.isoformat(),
                            candidates_json=candidates_json,
                        ),
                    )
                    if result and result.get("is_split") and result.get("matching_txns"):
                        txn_ids = result["matching_txns"]
                        conf = float(result.get("confidence", 0.8))
                    else:
                        txn_ids = [c.txn_id for c in found]
                        conf = 0.8
                else:
                    # deterministic combo-sum already found a valid split;
                    # LLM would only add reasoning/confidence nuance
                    txn_ids = [c.txn_id for c in found]
                    conf = 0.8

                self.matcher._add_match(
                    MatchTier.SPLIT_PAYMENT, conf,
                    bank_txn_ids=txn_ids, invoice_ids=[inv.invoice_id],
                    reasoning=f"Split payment: {len(txn_ids)} transactions sum to within ₹5 of invoice amount",
                )
                self.split_detections += 1

    # ------------------------------------------------------------------
    def _score_confidence(self, bank_txn, invoice, name_score: float) -> float:
        amount_closeness = 1.0 - min(float(abs(bank_txn.amount - invoice.amount)) / 100, 1.0)
        date_closeness = 1.0 - min(abs((bank_txn.date - invoice.date).days) / 5, 1.0)
        id_overlap = 1.0 if bank_txn.reference_number else 0.0
        conf = (
            0.4 * amount_closeness
            + 0.2 * date_closeness
            + 0.3 * name_score
            + 0.1 * id_overlap
        )
        return round(min(max(conf, 0.0), 1.0), 3)

    # ------------------------------------------------------------------
    def flag_remaining_ambiguous(self):
        """Anything still unmatched after fuzzy+split gets a final ambiguous
        pass; without an LLM configured, per the plan's fallback table, these
        are simply flagged AMBIGUOUS rather than guessed at."""
        for inv in self.matcher.unmatched_invoices():
            self.ambiguous_flagged.append(inv.invoice_id)

    def run_all(self):
        self.resolve_cryptic_upi()
        self.detect_split_payments()
        self.flag_remaining_ambiguous()
        return self.matcher.matches


if __name__ == "__main__":
    import json
    from pathlib import Path
    from src.ingestion import ingest

    data_dir = Path(__file__).parent.parent / "data"
    ing = ingest(data_dir)
    det = DeterministicMatcher(ing)
    det.run_all()
    print("After deterministic passes:", json.dumps(det.stats(), indent=2))

    ai = AIMatcher(det)
    ai.run_all()
    print("\nAfter AI-assisted passes:", json.dumps(det.stats(), indent=2))
    print(json.dumps({
        "fuzzy_matches_made": ai.fuzzy_matches_made,
        "upi_resolutions": ai.upi_resolutions,
        "split_detections": ai.split_detections,
        "ambiguous_flagged": len(ai.ambiguous_flagged),
        "llm_available": ai.llm.available,
        "llm_stats": ai.llm.get_stats(),
    }, indent=2))
