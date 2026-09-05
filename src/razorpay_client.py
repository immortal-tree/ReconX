# src/razorpay_client.py
#
# Thin wrapper around the Razorpay Test Mode SDK. Keeps the reconciliation
# pipeline decoupled from the SDK — only generate_gateway_data.py should
# import this module directly.

from __future__ import annotations

import os
from datetime import datetime, date
from decimal import Decimal
from typing import Any

import razorpay
from dotenv import load_dotenv

load_dotenv()


class RazorpayTestClient:
    def __init__(self):
        key_id = os.environ.get("RAZORPAY_KEY_ID")
        key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
        if not key_id or not key_secret:
            raise RuntimeError(
                "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set. "
                "Generate Test Mode keys at dashboard.razorpay.com → Settings → API Keys."
            )
        if not key_id.startswith("rzp_test_"):
            raise RuntimeError("Refusing to run: key does not look like a Test Mode key.")
        self.client = razorpay.Client(auth=(key_id, key_secret))

    def create_test_order(self, amount_rupees: float, receipt: str, notes: dict | None = None) -> dict:
        """Creates a Test Mode order. amount_rupees is converted to paise."""
        return self.client.order.create({
            "amount": int(round(amount_rupees * 100)),
            "currency": "INR",
            "receipt": receipt,
            "notes": notes or {},
        })

    def fetch_order(self, order_id: str) -> dict:
        return self.client.order.fetch(order_id)

    def fetch_payments_for_order(self, order_id: str) -> dict:
        return self.client.order.payments(order_id)

    def to_gateway_record(self, order: dict, payment: dict) -> dict[str, Any]:
        """Maps a Razorpay order+payment pair into the PaymentGateway schema in src/models.py."""
        created_at_ts = payment.get("created_at")
        if isinstance(created_at_ts, (int, float)):
            txn_date = datetime.fromtimestamp(created_at_ts).date().isoformat()
        else:
            txn_date = date.today().isoformat()

        raw_status = payment.get("status", "captured")
        mapped_status = {"captured": "success", "failed": "failed"}.get(raw_status, "pending")

        method = payment.get("vpa") or payment.get("method", "upi")

        return {
            "payment_id": payment.get("id"),
            "order_id": order.get("id"),
            "date": txn_date,
            "amount": float(Decimal(str(payment.get("amount", 0))) / Decimal("100")),
            "vpa_or_method": method,
            "status": mapped_status,
            "reference_number": order.get("receipt"),
            "normalized_merchant": None,
            "source": "gateway",
        }
