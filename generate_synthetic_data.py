"""
Synthetic data generator for the AI Finance Controller.

Produces three source files (bank.json, invoices.json, gateway.json) plus
ground_truth.json describing the intended match/exception for every record,
so Phase 6 (Reporter) can compute precision/recall/F1 against something real.

Scenario types (9), each tagged in ground truth via `scenario`:
  1. clean_3way        - bank + invoice + gateway all match cleanly (exact ID)
  2. amount_date_only   - matches on amount+date, no shared reference number
  3. composite_fuzzy    - matches via composite key / fuzzy name only
  4. cryptic_upi        - bank description uses a cryptic UPI merchant code
  5. split_payment       - one invoice paid via 2-3 separate bank transactions
  6. duplicate           - a record duplicated within the same source
  7. missing_counterpart - exists in one source, no match anywhere else
  8. amount_mismatch     - same vendor/date, amount differs beyond tolerance
  9. malformed           - deliberately broken record (for ingestion testing)

Run:  python generate_synthetic_data.py
Output: data/bank.json, data/invoices.json, data/gateway.json, data/ground_truth.json
"""

import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

random.seed(42)  # reproducible runs

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

START_DATE = date(2026, 1, 1)

# Vendor pool: 9 named + 10 generic
NAMED_VENDORS = [
    "Swiggy", "Zomato", "Amazon", "Flipkart", "BigBasket",
    "Blinkit", "Dunzo", "Ola", "Uber",
]
GENERIC_VENDORS = [
    "Sharma Traders", "Kumar Enterprises", "Global Supplies Co",
    "Metro Logistics", "Prime Stationery", "Om Sai Textiles",
    "Vertex Solutions", "Ganga Hardware", "City Fresh Mart", "Apex Consultancy",
]
ALL_VENDORS = NAMED_VENDORS + GENERIC_VENDORS

UPI_ID_MAP = {
    "Swiggy": "SWGGY@YESB",
    "Zomato": "ZMTO@PAYTM",
    "Amazon": "AMZN@ICICI",
    "Flipkart": "FKRT@AXIS",
    "BigBasket": "BB@HDFC",
    "Blinkit": "BLINKIT@KOTAK",
    "Dunzo": "DUNZO@YESB",
    "Ola": "OLACABS@ICICI",
    "Uber": "UBER@AXIS",
}

_id_counters = {"bank": 0, "invoice": 0, "gateway": 0}


def next_id(kind: str) -> str:
    _id_counters[kind] += 1
    prefix = {"bank": "TXN", "invoice": "INV", "gateway": "PAY"}[kind]
    return f"{prefix}{_id_counters[kind]:04d}"


def rand_date(base: date, spread_days: int = 60) -> date:
    return base + timedelta(days=random.randint(0, spread_days))


def rand_amount(low=200, high=50000) -> Decimal:
    return Decimal(str(round(random.uniform(low, high), 2)))


bank_records = []
invoice_records = []
gateway_records = []
ground_truth = []  # list of {scenario, exception_type|None, record_ids: {...}}


def add_gt(scenario, exception_type, **record_ids):
    ground_truth.append({
        "scenario": scenario,
        "exception_type": exception_type,
        **record_ids,
    })


# --- Scenario 1: clean_3way (exact reference number across all 3) ---------
for _ in range(15):
    vendor = random.choice(ALL_VENDORS)
    amt = rand_amount()
    d = rand_date(START_DATE)
    ref = f"REF{random.randint(10**9, 10**10 - 1)}"

    inv_id = next_id("invoice")
    invoice_records.append({
        "invoice_id": inv_id, "date": d.isoformat(), "amount": str(amt),
        "vendor_name": vendor, "status": "paid",
    })

    pay_id = next_id("gateway")
    gateway_records.append({
        "payment_id": pay_id, "order_id": f"order_{pay_id.lower()}",
        "date": d.isoformat(), "amount": str(amt),
        "vpa_or_method": UPI_ID_MAP.get(vendor, "generic@bank"),
        "status": "success", "reference_number": ref,
    })

    txn_id = next_id("bank")
    bank_records.append({
        "txn_id": txn_id, "date": d.isoformat(), "amount": str(amt),
        "raw_description": f"UPI/{ref}/{vendor.upper().replace(' ', '')}",
        "reference_number": ref, "debit_credit": "debit",
    })

    add_gt("clean_3way", None, bank_txn_id=txn_id, invoice_id=inv_id, gateway_payment_id=pay_id)

# --- Scenario 2: amount_date_only (no shared ref, match on amount+date) ---
for _ in range(10):
    vendor = random.choice(ALL_VENDORS)
    amt = rand_amount()
    d = rand_date(START_DATE)

    inv_id = next_id("invoice")
    invoice_records.append({
        "invoice_id": inv_id, "date": d.isoformat(), "amount": str(amt),
        "vendor_name": vendor, "status": "paid",
    })
    txn_id = next_id("bank")
    # date within +/-1 day, no reference number overlap
    bank_records.append({
        "txn_id": txn_id, "date": (d + timedelta(days=random.choice([-1, 0, 1]))).isoformat(),
        "amount": str(amt), "raw_description": f"NEFT/{vendor.upper().replace(' ', '')}/SETTLEMENT",
        "reference_number": None, "debit_credit": "debit",
    })
    add_gt("amount_date_only", None, bank_txn_id=txn_id, invoice_id=inv_id)

# --- Scenario 3: composite_fuzzy (amount +/-2, name partial, date +/-2) ---
for _ in range(8):
    vendor = random.choice(ALL_VENDORS)
    amt = rand_amount()
    d = rand_date(START_DATE)
    fuzzed_name = vendor.replace("a", "").replace(" ", "")[:6]  # mangled short form

    inv_id = next_id("invoice")
    invoice_records.append({
        "invoice_id": inv_id, "date": d.isoformat(), "amount": str(amt),
        "vendor_name": vendor, "status": "paid",
    })
    txn_id = next_id("bank")
    bank_records.append({
        "txn_id": txn_id, "date": (d + timedelta(days=random.choice([-2, -1, 1, 2]))).isoformat(),
        "amount": str(amt + Decimal("1.50")),  # small rounding delta
        "raw_description": f"IMPS/{fuzzed_name.upper()}/PYMT",
        "reference_number": None, "debit_credit": "debit",
    })
    add_gt("composite_fuzzy", None, bank_txn_id=txn_id, invoice_id=inv_id)

# --- Scenario 4: cryptic_upi (needs LLM to resolve merchant code) ---------
for _ in range(7):
    vendor = random.choice(NAMED_VENDORS)
    amt = rand_amount(100, 3000)
    d = rand_date(START_DATE)
    upi_id = UPI_ID_MAP[vendor]

    inv_id = next_id("invoice")
    invoice_records.append({
        "invoice_id": inv_id, "date": d.isoformat(), "amount": str(amt),
        "vendor_name": vendor, "status": "paid",
    })
    txn_id = next_id("bank")
    bank_records.append({
        "txn_id": txn_id, "date": d.isoformat(), "amount": str(amt),
        "raw_description": f"UPI/{upi_id}/{random.randint(10**11,10**12-1)}",
        "reference_number": None, "debit_credit": "debit",
    })
    add_gt("cryptic_upi", None, bank_txn_id=txn_id, invoice_id=inv_id)

# --- Scenario 5: split_payment (1 invoice, 2-3 bank txns) -----------------
for _ in range(4):
    vendor = random.choice(GENERIC_VENDORS)
    total = rand_amount(5000, 40000)
    d = rand_date(START_DATE)
    n_splits = random.choice([2, 3])
    parts = []
    remaining = total
    for i in range(n_splits - 1):
        part = (remaining / n_splits).quantize(Decimal("0.01"))
        parts.append(part)
        remaining -= part
    parts.append(remaining)

    inv_id = next_id("invoice")
    invoice_records.append({
        "invoice_id": inv_id, "date": d.isoformat(), "amount": str(total),
        "vendor_name": vendor, "status": "partial",
    })
    txn_ids = []
    for i, part in enumerate(parts):
        txn_id = next_id("bank")
        txn_ids.append(txn_id)
        bank_records.append({
            "txn_id": txn_id, "date": (d + timedelta(days=i)).isoformat(),
            "amount": str(part), "raw_description": f"NEFT/{vendor.upper().replace(' ', '')}/PART{i+1}",
            "reference_number": None, "debit_credit": "debit",
        })
    add_gt("split_payment", None, bank_txn_ids=txn_ids, invoice_id=inv_id)

# --- Scenario 6: duplicate (identical record appears twice in bank) -------
for _ in range(4):
    vendor = random.choice(ALL_VENDORS)
    amt = rand_amount()
    d = rand_date(START_DATE)
    base = {
        "date": d.isoformat(), "amount": str(amt),
        "raw_description": f"UPI/{vendor.upper().replace(' ', '')}/DUP",
        "reference_number": None, "debit_credit": "debit",
    }
    txn_id1 = next_id("bank")
    txn_id2 = next_id("bank")
    bank_records.append({"txn_id": txn_id1, **base})
    bank_records.append({"txn_id": txn_id2, **base})
    add_gt("duplicate", "DUPLICATE", bank_txn_ids=[txn_id1, txn_id2])

# --- Scenario 7: missing_counterpart (exists in exactly one source) -------
for _ in range(8):
    vendor = random.choice(ALL_VENDORS)
    amt = rand_amount()
    d = rand_date(START_DATE)
    choice = random.choice(["bank", "invoice", "gateway"])
    if choice == "bank":
        txn_id = next_id("bank")
        bank_records.append({
            "txn_id": txn_id, "date": d.isoformat(), "amount": str(amt),
            "raw_description": f"UPI/{vendor.upper().replace(' ', '')}/LONE",
            "reference_number": None, "debit_credit": "debit",
        })
        add_gt("missing_counterpart", "MISSING_COUNTERPART", bank_txn_id=txn_id)
    elif choice == "invoice":
        inv_id = next_id("invoice")
        invoice_records.append({
            "invoice_id": inv_id, "date": d.isoformat(), "amount": str(amt),
            "vendor_name": vendor, "status": "unpaid",
        })
        add_gt("missing_counterpart", "MISSING_COUNTERPART", invoice_id=inv_id)
    else:
        pay_id = next_id("gateway")
        gateway_records.append({
            "payment_id": pay_id, "order_id": f"order_{pay_id.lower()}",
            "date": d.isoformat(), "amount": str(amt),
            "vpa_or_method": "generic@bank", "status": "success",
            "reference_number": None,
        })
        add_gt("missing_counterpart", "MISSING_COUNTERPART", gateway_payment_id=pay_id)

# --- Scenario 8: amount_mismatch (same vendor/date, amount differs a lot) -
for _ in range(4):
    vendor = random.choice(ALL_VENDORS)
    amt = rand_amount()
    d = rand_date(START_DATE)

    inv_id = next_id("invoice")
    invoice_records.append({
        "invoice_id": inv_id, "date": d.isoformat(), "amount": str(amt),
        "vendor_name": vendor, "status": "unpaid",
    })
    txn_id = next_id("bank")
    bank_records.append({
        "txn_id": txn_id, "date": d.isoformat(),
        "amount": str(amt - Decimal(str(random.randint(50, 500)))),  # mismatch beyond tolerance
        "raw_description": f"UPI/{vendor.upper().replace(' ', '')}/PART",
        "reference_number": None, "debit_credit": "debit",
    })
    add_gt("amount_mismatch", "AMOUNT_MISMATCH", bank_txn_id=txn_id, invoice_id=inv_id)

# --- Scenario 9: malformed (broken rows for ingestion-layer testing) ------
# These are injected as raw dicts bypassing amount>0 / required-field rules.
malformed_bank = [
    {"txn_id": "TXN_BAD1", "date": "2026-01-05", "amount": "-100.00",
     "raw_description": "UPI/BADAMOUNT", "reference_number": None, "debit_credit": "debit"},
    {"txn_id": "TXN_BAD2", "date": "not-a-date", "amount": "500.00",
     "raw_description": "UPI/BADDATE", "reference_number": None, "debit_credit": "debit"},
]
bank_records.extend(malformed_bank)
for rec in malformed_bank:
    add_gt("malformed", None, bank_txn_id=rec["txn_id"])


# --- Pad with MORE MATCHED records first, exceptions only as a small,
# deliberate top-up. This keeps the dataset realistically match-heavy
# (real-world recon batches are mostly clean; exceptions are the minority
# the agent needs to surface, not the bulk of the data).
#
# Targets are asymmetric on purpose: gateway naturally has fewer entries
# than bank in real SME finance (not every bank txn is a digital-gateway
# payment - rent, salaries, NEFT-to-vendor, etc. never touch a gateway).
BANK_TARGET = 70
INVOICE_TARGET = 65
GATEWAY_TARGET = 45
MAX_EXTRA_ORPHANS = 8  # cap deliberate extra missing_counterpart padding


def add_clean_3way():
    """Grows bank + invoice + gateway together via a clean exact-ID match."""
    vendor = random.choice(ALL_VENDORS)
    amt = rand_amount()
    d = rand_date(START_DATE)
    ref = f"REF{random.randint(10**9, 10**10 - 1)}"

    inv_id = next_id("invoice")
    invoice_records.append({
        "invoice_id": inv_id, "date": d.isoformat(), "amount": str(amt),
        "vendor_name": vendor, "status": "paid",
    })
    pay_id = next_id("gateway")
    gateway_records.append({
        "payment_id": pay_id, "order_id": f"order_{pay_id.lower()}",
        "date": d.isoformat(), "amount": str(amt),
        "vpa_or_method": UPI_ID_MAP.get(vendor, "generic@bank"),
        "status": "success", "reference_number": ref,
    })
    txn_id = next_id("bank")
    bank_records.append({
        "txn_id": txn_id, "date": d.isoformat(), "amount": str(amt),
        "raw_description": f"UPI/{ref}/{vendor.upper().replace(' ', '')}",
        "reference_number": ref, "debit_credit": "debit",
    })
    add_gt("clean_3way", None, bank_txn_id=txn_id, invoice_id=inv_id, gateway_payment_id=pay_id)


def add_amount_date_pair():
    """Grows bank + invoice together (no gateway leg) - a NEFT/cheque style payment."""
    vendor = random.choice(ALL_VENDORS)
    amt = rand_amount()
    d = rand_date(START_DATE)

    inv_id = next_id("invoice")
    invoice_records.append({
        "invoice_id": inv_id, "date": d.isoformat(), "amount": str(amt),
        "vendor_name": vendor, "status": "paid",
    })
    txn_id = next_id("bank")
    bank_records.append({
        "txn_id": txn_id, "date": (d + timedelta(days=random.choice([-1, 0, 1]))).isoformat(),
        "amount": str(amt), "raw_description": f"NEFT/{vendor.upper().replace(' ', '')}/SETTLEMENT",
        "reference_number": None, "debit_credit": "debit",
    })
    add_gt("amount_date_only", None, bank_txn_id=txn_id, invoice_id=inv_id)


# 1. Grow gateway (and bank+invoice alongside it) via clean matches
while len(gateway_records) < GATEWAY_TARGET:
    add_clean_3way()

# 2. Grow invoice (and bank alongside it) via amount+date matches
while len(invoice_records) < INVOICE_TARGET:
    add_amount_date_pair()

# 3. Top off bank with a small, capped number of genuine orphan exceptions
#    (bank-only transactions with no invoice/gateway counterpart - real SMEs
#    do have unexplained bank activity, but it should be the minority)
orphans_added = 0
while len(bank_records) < BANK_TARGET and orphans_added < MAX_EXTRA_ORPHANS:
    vendor = random.choice(ALL_VENDORS)
    amt = rand_amount()
    d = rand_date(START_DATE)
    txn_id = next_id("bank")
    bank_records.append({
        "txn_id": txn_id, "date": d.isoformat(), "amount": str(amt),
        "raw_description": f"UPI/{vendor.upper().replace(' ', '')}/MISC",
        "reference_number": None, "debit_credit": "debit",
    })
    add_gt("missing_counterpart", "MISSING_COUNTERPART", bank_txn_id=txn_id)
    orphans_added += 1

# 4. If still short of the bank target, close the gap with more clean matches
#    (keeps the ratio matched-heavy rather than exception-heavy)
while len(bank_records) < BANK_TARGET:
    add_amount_date_pair()

random.shuffle(bank_records)
random.shuffle(invoice_records)
random.shuffle(gateway_records)

(DATA_DIR / "bank.json").write_text(json.dumps(bank_records, indent=2))
(DATA_DIR / "invoices.json").write_text(json.dumps(invoice_records, indent=2))
(DATA_DIR / "gateway.json").write_text(json.dumps(gateway_records, indent=2))
(DATA_DIR / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2))

print(f"bank.json:         {len(bank_records)} records")
print(f"invoices.json:     {len(invoice_records)} records")
print(f"gateway.json:      {len(gateway_records)} records")
print(f"ground_truth.json: {len(ground_truth)} scenario entries")
print(f"Total records: {len(bank_records) + len(invoice_records) + len(gateway_records)}")
