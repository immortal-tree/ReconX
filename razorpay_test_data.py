"""
razorpay_test_data.py - populate data/gateway.json with a handful of REAL
Razorpay test-mode transactions, mixed in alongside the synthetic ones.

WHY: the reconciliation engine's Payment Gateway Log source is currently
100% synthetic (generate_synthetic_data.py). Swapping in a few live
test-mode Razorpay transactions lets the demo/pitch video honestly say
"reconciled against real Razorpay test-mode data," not just synthetic JSON.

WHAT THIS DOES vs WHAT IT CAN'T DO:
  - Orders API (create-orders): fully automatable server-side. Creates
    real Razorpay test orders, optionally with amounts/notes matching
    existing invoices in invoices.json so they actually reconcile.
  - Completing a payment against an order: Razorpay does NOT expose a
    plain server-to-server "mark this paid" call in test mode. A payment
    only exists once someone goes through Checkout (or the S2S UPI intent
    flow, which isn't enabled on all test accounts). So after
    create-orders, you complete each one manually via the printed
    checkout link (~30s each, using Razorpay's test UPI VPA
    "success@razorpay" or test card 4111 1111 1111 1111).
  - sync-payments: fully automatable. Fetches whichever orders you did
    complete, converts them to the PAYMENT_GATEWAY schema from the
    architecture doc's ER diagram, and merges them into gateway.json
    (tagged so you can tell live vs synthetic apart, and re-running is
    idempotent - it won't duplicate already-merged payments).

SETUP:
    pip install requests python-dotenv --break-system-packages
    # In .env:
    RAZORPAY_KEY_ID=rzp_test_xxxxxxxx
    RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxx

USAGE:
    # 1. Create N test orders (optionally matched to invoices.json amounts)
    python razorpay_test_data.py create-orders --count 5 \
        --invoices data/invoices.json

    # -> prints a checkout link per order. Open each, pay with:
    #      UPI: use VPA "success@razorpay" (auto-succeeds in test mode)
    #      Card: 4111 1111 1111 1111, any future expiry, any CVV
    #    Takes ~30s per order.

    # 2. After completing some/all of them, pull the real payments in:
    python razorpay_test_data.py sync-payments \
        --gateway-file data/gateway.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import string
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("Missing dependency. Run: pip install requests python-dotenv --break-system-packages")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # ok if .env is already exported into the shell some other way

RAZORPAY_BASE = "https://api.razorpay.com/v1"
# Tag used both to mark rows we added and to make this script idempotent
# (re-running sync-payments won't duplicate rows already merged in).
LIVE_TAG = "razorpay_test_live"


def _auth() -> tuple[str, str]:
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        print("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set (check your .env).")
        sys.exit(1)
    if not key_id.startswith("rzp_test_"):
        print(f"Warning: key '{key_id[:12]}...' doesn't look like a TEST key "
              f"(expected prefix 'rzp_test_'). Refusing to continue - "
              f"double check you're using test mode, not live keys.")
        sys.exit(1)
    return key_id, key_secret


def _receipt_id() -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"recon-demo-{suffix}"


def create_orders(count: int, invoices_path: Optional[str], min_amount: float, max_amount: float):
    """Create `count` test-mode orders. If invoices_path is given, sample
    that many invoices and use their amount + vendor name so the resulting
    gateway record has a real shot at reconciling against an existing
    invoice in the demo dataset - much better demo footage than a random
    amount that dead-ends as an exception."""
    key_id, key_secret = _auth()
    auth = (key_id, key_secret)

    candidates: list[dict] = []
    if invoices_path and Path(invoices_path).exists():
        with open(invoices_path) as f:
            invoices = json.load(f)
        # Prefer invoices that are still 'open' - matching a paid one just
        # recreates a duplicate exception rather than a clean reconciliation.
        open_invoices = [inv for inv in invoices if inv.get("status") == "open"] or invoices
        sample_size = min(count, len(open_invoices))
        candidates = random.sample(open_invoices, sample_size)
        if sample_size < count:
            print(f"Only {sample_size} open invoices available; "
                  f"creating {count - sample_size} extra orders with random amounts.")
    else:
        if invoices_path:
            print(f"'{invoices_path}' not found - creating all {count} orders with random amounts.")

    created = []
    for i in range(count):
        if i < len(candidates):
            inv = candidates[i]
            amount_rupees = float(inv["amount"])
            vendor = inv.get("vendor_name", "Test Vendor")
            notes = {"source": LIVE_TAG, "matched_invoice_id": inv.get("invoice_id", ""), "vendor_name": vendor}
        else:
            amount_rupees = round(random.uniform(min_amount, max_amount), 2)
            vendor = f"Test Vendor {i + 1}"
            notes = {"source": LIVE_TAG, "matched_invoice_id": "", "vendor_name": vendor}

        payload = {
            "amount": int(round(amount_rupees * 100)),  # Razorpay wants paise
            "currency": "INR",
            "receipt": _receipt_id(),
            "notes": notes,
        }
        resp = requests.post(f"{RAZORPAY_BASE}/orders", auth=auth, json=payload, timeout=15)
        if resp.status_code != 200:
            print(f"  [{i + 1}/{count}] FAILED: {resp.status_code} {resp.text[:200]}")
            continue

        order = resp.json()
        created.append(order)
        checkout_link = (
            f"https://api.razorpay.com/v1/checkout/embedded?order_id={order['id']}&key_id={key_id}"
        )
        print(f"  [{i + 1}/{count}] order {order['id']}  amount=Rs.{amount_rupees}  "
              f"vendor='{vendor}'")
        print(f"       complete it: https://checkout.razorpay.com/v1/checkout.js "
              f"(or open Razorpay's hosted page for order_id={order['id']} from your dashboard's "
              f"'Test Mode > Orders' tab and pay with UPI VPA 'success@razorpay')")

    print(f"\nCreated {len(created)}/{count} orders. "
          f"Complete each in test mode, then run: sync-payments")
    return created


def sync_payments(gateway_file: str, days_back: int = 1):
    """Fetch recent test-mode payments and merge any not already present
    into gateway.json, converting to the PAYMENT_GATEWAY schema."""
    key_id, key_secret = _auth()
    auth = (key_id, key_secret)

    resp = requests.get(f"{RAZORPAY_BASE}/payments", auth=auth,
                         params={"count": 100}, timeout=15)
    if resp.status_code != 200:
        print(f"Failed to fetch payments: {resp.status_code} {resp.text[:300]}")
        sys.exit(1)

    payments = resp.json().get("items", [])
    # Only pull payments we created for this demo (tagged via notes on the
    # parent order) - a real Razorpay test account can accumulate unrelated
    # test payments from other experiments, and we don't want those mixed in.
    relevant = [p for p in payments if (p.get("notes") or {}).get("source") == LIVE_TAG]

    gateway_path = Path(gateway_file)
    existing: list[dict] = []
    if gateway_path.exists():
        with open(gateway_path) as f:
            existing = json.load(f)
    existing_ids = {rec.get("pg_txn_id") for rec in existing}

    added = 0
    for p in relevant:
        if p["id"] in existing_ids:
            continue  # idempotent re-run
        if p.get("status") not in ("captured", "authorized"):
            continue  # skip failed/created-but-unpaid orders

        notes = p.get("notes") or {}
        record = {
            "pg_txn_id": p["id"],
            "txn_date": datetime.fromtimestamp(p["created_at"], tz=timezone.utc).date().isoformat(),
            "amount": round(p["amount"] / 100, 2),
            "merchant_id": p.get("id", "")[:14],
            "normalized_merchant": notes.get("vendor_name", "unknown").strip().lower(),
            "payment_method": p.get("method", "unknown"),
            "reference_number": p.get("order_id", ""),
            "status": "success" if p["status"] == "captured" else "pending",
            "source_tag": "gateway",
            "_origin": LIVE_TAG,  # marker so you can filter/audit these later; harmless extra field
        }
        existing.append(record)
        existing_ids.add(p["id"])
        added += 1
        print(f"  + merged {p['id']}  Rs.{record['amount']}  {record['normalized_merchant']}  "
              f"({record['status']})")

    gateway_path.parent.mkdir(parents=True, exist_ok=True)
    with open(gateway_path, "w") as f:
        json.dump(existing, f, indent=2)

    print(f"\n{added} live test-mode payment(s) merged into {gateway_file} "
          f"({len(relevant) - added} skipped: already present, or not yet paid).")
    if added == 0 and relevant:
        print("Tip: orders exist but none are 'captured' yet - "
              "complete the checkout step for at least one order first.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create-orders", help="Create N test-mode orders")
    p_create.add_argument("--count", type=int, default=5)
    p_create.add_argument("--invoices", type=str, default=None,
                           help="Path to invoices.json to sample amounts/vendors from")
    p_create.add_argument("--min-amount", type=float, default=500.0)
    p_create.add_argument("--max-amount", type=float, default=25000.0)

    p_sync = sub.add_parser("sync-payments", help="Pull completed test payments into gateway.json")
    p_sync.add_argument("--gateway-file", type=str, default="data/gateway.json")

    args = parser.parse_args()

    if args.command == "create-orders":
        create_orders(args.count, args.invoices, args.min_amount, args.max_amount)
    elif args.command == "sync-payments":
        sync_payments(args.gateway_file)


if __name__ == "__main__":
    main()
