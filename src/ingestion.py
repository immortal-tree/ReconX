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
UPI_P2M_RE = re.compile(r"UPI/\w+/(\d{12})/(\S+)")


def parse_upi_narration(raw_description: str) -> dict[str, str] | None:
    if not raw_description:
        return None
    m_p2m = UPI_P2M_RE.search(raw_description)
    if m_p2m:
        return {"reference_number": m_p2m.group(1), "vpa": m_p2m.group(2)}
    m_ref = UPI_REF_RE.search(raw_description)
    if m_ref:
        return {"reference_number": m_ref.group(2), "vpa": m_ref.group(1)}
    return None


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


def deduplicate(records: list[dict]) -> tuple[list[dict], list[dict]]:
    seen_hashes: set[str] = set()
    unique: list[dict] = []
    dropped: list[dict] = []
    for r in records:
        amt = r.get("amount")
        d = r.get("date") or r.get("txn_date") or r.get("invoice_date")
        src = r.get("source") or r.get("source_tag") or "bank"
        name = r.get("normalized_merchant") or r.get("normalized_vendor") or r.get("vendor_name") or r.get("raw_description") or ""
        if amt is None or d is None or not isinstance(d, (str, type(None))) and not hasattr(d, "isoformat"):
            dropped.append(r)
            continue
        date_str = d.isoformat() if hasattr(d, "isoformat") else str(d)
        h = _record_hash(str(src), str(amt), date_str, str(name))
        if h in seen_hashes:
            dropped.append(r)
        else:
            seen_hashes.add(h)
            unique.append(r)
    return unique, dropped


def normalize_records(records: list[dict]) -> list[dict]:
    normalized = []
    for r in records:
        rec = dict(r)
        amt = rec.get("amount")
        if amt is None:
            continue
        try:
            from decimal import Decimal
            rec["amount"] = Decimal(str(amt))
        except Exception:
            continue
        
        vendor = rec.get("vendor_name")
        if vendor:
            rec["normalized_vendor"] = _normalize_name(vendor)
            rec["normalized_merchant"] = rec["normalized_vendor"]
        normalized.append(rec)
    return normalized


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
