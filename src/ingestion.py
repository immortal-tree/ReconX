"""
Layer 1: Ingestion & Normalization.

Loads raw JSON for each source, validates via Pydantic (logging - not
crashing on - malformed rows), normalizes fields, deduplicates, and
source-tags every record.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.models import BankTransaction, Invoice, PaymentGateway, SourceType

UPI_REF_RE = re.compile(r"UPI/([^/]+)/(\d{12})")


class IngestionResult:
    def __init__(self):
        self.bank: list[BankTransaction] = []
        self.invoices: list[Invoice] = []
        self.gateway: list[PaymentGateway] = []
        self.rejected: list[dict[str, Any]] = []      # failed Pydantic validation
        self.duplicates_removed: list[dict[str, Any]] = []  # removed as dupes

    def summary(self) -> dict:
        return {
            "bank_count": len(self.bank),
            "invoice_count": len(self.invoices),
            "gateway_count": len(self.gateway),
            "rejected_count": len(self.rejected),
            "duplicates_removed_count": len(self.duplicates_removed),
        }


def _normalize_name(name: str) -> str:
    return name.lower().strip()


def _record_hash(source: str, amount: str, date: str, name: str) -> str:
    key = f"{source}|{amount}|{date}|{_normalize_name(name)}"
    return hashlib.sha256(key.encode()).hexdigest()


def _load_json(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def ingest(data_dir: Path) -> IngestionResult:
    result = IngestionResult()
    seen_hashes: set[str] = set()

    # --- Bank ---
    for i, raw in enumerate(_load_json(data_dir / "bank.json")):
        try:
            txn = BankTransaction(**raw)
        except ValidationError as e:
            result.rejected.append({"source": "bank", "original_index": i, "raw": raw, "error": str(e)})
            continue

        # Normalize merchant name from raw_description (best-effort regex;
        # cryptic UPI codes get resolved later by the AI matcher in Layer 3)
        m = UPI_REF_RE.search(txn.raw_description)
        if m:
            txn.normalized_merchant = _normalize_name(m.group(1))
        else:
            # fall back: strip prefix tokens like UPI/, NEFT/, IMPS/
            parts = re.split(r"[/]", txn.raw_description)
            candidate = parts[1] if len(parts) > 1 else txn.raw_description
            txn.normalized_merchant = _normalize_name(candidate)

        h = _record_hash("bank", str(txn.amount), txn.date.isoformat(), txn.normalized_merchant or "")
        if h in seen_hashes:
            result.duplicates_removed.append({"source": "bank", "txn_id": txn.txn_id})
            continue
        seen_hashes.add(h)
        result.bank.append(txn)

    # --- Invoices ---
    for i, raw in enumerate(_load_json(data_dir / "invoices.json")):
        try:
            inv = Invoice(**raw)
        except ValidationError as e:
            result.rejected.append({"source": "invoice", "original_index": i, "raw": raw, "error": str(e)})
            continue
        inv.normalized_merchant = _normalize_name(inv.vendor_name)
        h = _record_hash("invoice", str(inv.amount), inv.date.isoformat(), inv.normalized_merchant)
        if h in seen_hashes:
            result.duplicates_removed.append({"source": "invoice", "invoice_id": inv.invoice_id})
            continue
        seen_hashes.add(h)
        result.invoices.append(inv)

    # --- Gateway ---
    for i, raw in enumerate(_load_json(data_dir / "gateway.json")):
        try:
            gw = PaymentGateway(**raw)
        except ValidationError as e:
            result.rejected.append({"source": "gateway", "original_index": i, "raw": raw, "error": str(e)})
            continue
        gw.normalized_merchant = _normalize_name(gw.vpa_or_method or "")
        h = _record_hash("gateway", str(gw.amount), gw.date.isoformat(), gw.normalized_merchant)
        if h in seen_hashes:
            result.duplicates_removed.append({"source": "gateway", "payment_id": gw.payment_id})
            continue
        seen_hashes.add(h)
        result.gateway.append(gw)

    return result


if __name__ == "__main__":
    data_dir = Path(__file__).parent.parent / "data"
    res = ingest(data_dir)
    print(json.dumps(res.summary(), indent=2))
    if res.rejected:
        print("\nRejected records (malformed, logged not crashed):")
        for r in res.rejected:
            print(f"  [{r['source']}] index {r['original_index']}: {r['error'].splitlines()[0]}")
    if res.duplicates_removed:
        print("\nDuplicates removed:")
        for d in res.duplicates_removed:
            print(f"  {d}")
