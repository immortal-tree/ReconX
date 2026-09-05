"""
Layer 2: Deterministic Matching.

3-pass matcher, cheapest/highest-confidence first:
  Pass 1: exact reference number / invoice ID substring match  (conf 1.0)
  Pass 2: same amount, date within +/-1 day, cross-source        (conf 0.95)
  Pass 3: composite key - amount +/-2, first-4-char name match,
          date within +/-2 days                                   (conf 0.85)

Enforces 1:1 matching: each record can appear in at most one match.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from src.models import BankTransaction, Invoice, PaymentGateway, MatchResult, MatchTier
from src.ingestion import IngestionResult


class DeterministicMatcher:
    def __init__(self, ingestion: IngestionResult):
        self.bank = list(ingestion.bank)
        self.invoices = list(ingestion.invoices)
        self.gateway = list(ingestion.gateway)

        # track consumed record ids to enforce 1:1 matching
        self._used_bank: set[str] = set()
        self._used_invoice: set[str] = set()
        self._used_gateway: set[str] = set()

        self.matches: list[MatchResult] = []
        self._match_counter = 0

    # ------------------------------------------------------------------
    def _next_match_id(self) -> str:
        self._match_counter += 1
        return f"MATCH{self._match_counter:04d}"

    def _add_match(self, tier: MatchTier, confidence: float, **ids) -> MatchResult:
        m = MatchResult(
            match_id=self._next_match_id(),
            tier=tier,
            confidence=confidence,
            bank_txn_ids=ids.get("bank_txn_ids", []),
            invoice_ids=ids.get("invoice_ids", []),
            gateway_payment_ids=ids.get("gateway_payment_ids", []),
            reasoning=ids.get("reasoning"),
        )
        self.matches.append(m)
        for bid in m.bank_txn_ids:
            self._used_bank.add(bid)
        for iid in m.invoice_ids:
            self._used_invoice.add(iid)
        for gid in m.gateway_payment_ids:
            self._used_gateway.add(gid)
        return m

    def unmatched_bank(self) -> list[BankTransaction]:
        return [b for b in self.bank if b.txn_id not in self._used_bank]

    def unmatched_invoices(self) -> list[Invoice]:
        return [i for i in self.invoices if i.invoice_id not in self._used_invoice]

    def unmatched_gateway(self) -> list[PaymentGateway]:
        return [g for g in self.gateway if g.payment_id not in self._used_gateway]

    # ------------------------------------------------------------------
    # Pass 1: exact ID match
    # ------------------------------------------------------------------
    def pass1_exact_id(self):
        # bank.reference_number <-> gateway.reference_number
        gw_by_ref = {g.reference_number: g for g in self.unmatched_gateway() if g.reference_number}
        for b in self.unmatched_bank():
            if b.reference_number and b.reference_number in gw_by_ref:
                gw = gw_by_ref[b.reference_number]
                if gw.payment_id in self._used_gateway:
                    continue
                self._add_match(
                    MatchTier.EXACT_ID, 1.0,
                    bank_txn_ids=[b.txn_id], gateway_payment_ids=[gw.payment_id],
                    reasoning=f"Shared reference number {b.reference_number}",
                )

        # invoice_id as substring of bank raw_description
        for b in self.unmatched_bank():
            for inv in self.unmatched_invoices():
                if inv.invoice_id in b.raw_description:
                    self._add_match(
                        MatchTier.EXACT_ID, 1.0,
                        bank_txn_ids=[b.txn_id], invoice_ids=[inv.invoice_id],
                        reasoning=f"Invoice ID {inv.invoice_id} found in bank description",
                    )
                    break

        # Now also tie together any bank txn that matched BOTH an invoice
        # (via substring) and a gateway (via reference) into a single 3-way
        # match instead of leaving two separate 2-way matches.
        self._merge_3way_matches()

    def _merge_3way_matches(self):
        by_bank: dict[str, list[MatchResult]] = {}
        for m in self.matches:
            for bid in m.bank_txn_ids:
                by_bank.setdefault(bid, []).append(m)
        merged = []
        removed_ids = set()
        for bid, ms in by_bank.items():
            if len(ms) > 1:
                inv_ids = sorted({i for m in ms for i in m.invoice_ids})
                gw_ids = sorted({g for m in ms for g in m.gateway_payment_ids})
                merged.append((bid, inv_ids, gw_ids))
                removed_ids.update(id(m) for m in ms)
        if merged:
            self.matches = [m for m in self.matches if id(m) not in removed_ids]
            for bid, inv_ids, gw_ids in merged:
                self._add_match(
                    MatchTier.EXACT_ID, 1.0,
                    bank_txn_ids=[bid], invoice_ids=inv_ids, gateway_payment_ids=gw_ids,
                    reasoning="Merged 3-way exact match (shared reference + invoice ID)",
                )

    def _attach_invoice_to_existing_matches(self):
        """
        Pass-1 only ties bank<->gateway (shared ref) or bank<->invoice
        (ID substring). A clean 3-way match's invoice shares amount+date
        with the bank/gateway pair but has no ID to match on, so without
        this step it would incorrectly fall through as unmatched. Attach
        it here before moving on to pass 2/3.
        """
        for m in self.matches:
            if m.invoice_ids or not m.bank_txn_ids:
                continue
            bank_rec = next((b for b in self.bank if b.txn_id == m.bank_txn_ids[0]), None)
            if not bank_rec:
                continue
            for inv in self.unmatched_invoices():
                if bank_rec.amount == inv.amount and abs((bank_rec.date - inv.date).days) <= 1:
                    m.invoice_ids.append(inv.invoice_id)
                    self._used_invoice.add(inv.invoice_id)
                    break

    # ------------------------------------------------------------------
    # Pass 2: amount + date (+/-1 day), cross-source
    # ------------------------------------------------------------------
    def pass2_amount_date(self):
        for b in self.unmatched_bank():
            for inv in self.unmatched_invoices():
                if b.amount == inv.amount and abs((b.date - inv.date).days) <= 1:
                    self._add_match(
                        MatchTier.AMOUNT_DATE, 0.95,
                        bank_txn_ids=[b.txn_id], invoice_ids=[inv.invoice_id],
                        reasoning=f"Amount {b.amount} matches, dates within 1 day",
                    )
                    break

    # ------------------------------------------------------------------
    # Pass 3: composite key - amount +/-2, first-4-char name, date +/-2 days
    # ------------------------------------------------------------------
    def pass3_composite_key(self):
        for b in self.unmatched_bank():
            for inv in self.unmatched_invoices():
                amt_close = abs(b.amount - inv.amount) <= Decimal("2.00")
                date_close = abs((b.date - inv.date).days) <= 2
                name_key = (inv.normalized_merchant or "")[:4]
                b_name = ((b.normalized_merchant or "") + " " + (b.raw_description or "")).lower()
                name_match = bool(name_key) and name_key in b_name
                if amt_close and date_close and name_match:
                    self._add_match(
                        MatchTier.COMPOSITE_KEY, 0.85,
                        bank_txn_ids=[b.txn_id], invoice_ids=[inv.invoice_id],
                        reasoning=f"Composite key: amount within 2, date within 2 days, name prefix '{name_key}' matched",
                    )
                    break

    # ------------------------------------------------------------------
    def run_all(self) -> list[MatchResult]:
        self.pass1_exact_id()
        self._attach_invoice_to_existing_matches()
        self.pass2_amount_date()
        self.pass3_composite_key()
        return self.matches

    def stats(self) -> dict:
        by_tier = {}
        for m in self.matches:
            by_tier[m.tier.value] = by_tier.get(m.tier.value, 0) + 1
        return {
            "total_matches": len(self.matches),
            "by_tier": by_tier,
            "unmatched_bank": len(self.unmatched_bank()),
            "unmatched_invoices": len(self.unmatched_invoices()),
            "unmatched_gateway": len(self.unmatched_gateway()),
        }


def run_deterministic_pipeline(records: dict[str, list[dict | Any]]) -> tuple[list[dict], list[dict]]:
    from src.ai_matcher import STATIC_UPI_ALIASES
    ing = IngestionResult()
    for b in records.get("bank", []):
        rec = dict(b) if isinstance(b, dict) else b.model_dump()
        if "txn_date" in rec and "date" not in rec:
            rec["date"] = rec.pop("txn_date")
        if "direction" in rec and "debit_credit" not in rec:
            rec["debit_credit"] = rec.pop("direction")
        if not rec.get("normalized_merchant") and rec.get("raw_description"):
            desc_upper = rec["raw_description"].upper()
            for code, name in STATIC_UPI_ALIASES.items():
                if code in desc_upper:
                    rec["normalized_merchant"] = name.lower()
                    break
            if not rec.get("normalized_merchant"):
                rec["normalized_merchant"] = rec["raw_description"].lower()
        txn = BankTransaction(**rec) if isinstance(rec, dict) else rec
        ing.bank.append(txn)

    for i in records.get("invoice", []) or records.get("invoices", []):
        rec = dict(i) if isinstance(i, dict) else i.model_dump()
        if "invoice_date" in rec and "date" not in rec:
            rec["date"] = rec.pop("invoice_date")
        inv = Invoice(**rec) if isinstance(rec, dict) else rec
        ing.invoices.append(inv)

    for g in records.get("gateway", []):
        rec = dict(g) if isinstance(g, dict) else g.model_dump()
        if "txn_date" in rec and "date" not in rec:
            rec["date"] = rec.pop("txn_date")
        if "pg_txn_id" in rec and "payment_id" not in rec:
            rec["payment_id"] = rec.pop("pg_txn_id")
        if "merchant_id" in rec and "vpa_or_method" not in rec:
            rec["vpa_or_method"] = rec.pop("merchant_id")
        gw = PaymentGateway(**rec) if isinstance(rec, dict) else rec
        ing.gateway.append(gw)

    matcher = DeterministicMatcher(ing)
    matcher.run_all()

    matched_dicts = []
    for m in matcher.matches:
        d = m.model_dump()
        d["match_method"] = m.tier.value
        d["source_a_id"] = m.bank_txn_ids[0] if m.bank_txn_ids else (m.invoice_ids[0] if m.invoice_ids else None)
        d["source_b_id"] = m.invoice_ids[0] if m.invoice_ids else (m.gateway_payment_ids[0] if m.gateway_payment_ids else None)
        matched_dicts.append(d)

    unmatched_dicts = (
        [b.model_dump() for b in matcher.unmatched_bank()] +
        [i.model_dump() for i in matcher.unmatched_invoices()] +
        [g.model_dump() for g in matcher.unmatched_gateway()]
    )
    return matched_dicts, unmatched_dicts


if __name__ == "__main__":
    import json
    from pathlib import Path
    from src.ingestion import ingest

    data_dir = Path(__file__).parent.parent / "data"
    ing = ingest(data_dir)
    matcher = DeterministicMatcher(ing)
    matcher.run_all()
    print(json.dumps(matcher.stats(), indent=2))
