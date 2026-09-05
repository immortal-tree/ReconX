# Reconciliation Summary Report

_Generated: 2026-09-05T17:36:53.739318+00:00_

## Summary

| Metric | Value |
|---|---|
| Total records ingested | 216 |
| Total matches found | 68 |
| Records matched | 186 |
| Match rate | 86.1% |
| Total exceptions | 30 |

## Accuracy vs Ground Truth

| Metric | Value | Target | Status |
|---|---|---|---|
| Precision | 100.0% | >= 85% | ✅ |
| Recall | 93.2% | >= 80% | ✅ |
| F1 | 0.965 | >= 0.85 | ✅ |

## Matches by Tier

| Tier | Count |
|---|---|
| exact_id | 44 |
| amount_date | 17 |
| composite_key | 3 |
| split_payment | 4 |

## Cash Position

- Matched bank debits total: ₹1462669.63
- Matched invoice amount total: ₹1462665.13
- **Cash position delta: ₹4.50**

## Exceptions by Type

| Type | Count |
|---|---|
| MISSING_COUNTERPART | 12 |
| AMOUNT_MISMATCH | 8 |
| AMBIGUOUS | 10 |

## Exception Detail

| Record ID | Type | Explanation | Suggested Action |
|---|---|---|---|
| `TXN0054` | MISSING_COUNTERPART | The bank transaction TXN0054 of $3,728.70 dated 2026-01-16 has no matching counterpart in our ledger. | Search the internal records for a corresponding entry or create a matching journal entry to resolve the discrepancy. |
| `TXN0064` | AMOUNT_MISMATCH | TXN0064 for ₹43179.59 on 2026-02-27 is close to a candidate match but the amount differs beyond the allowed tolerance. | Confirm whether a partial payment, fee, or data-entry error explains the gap. |
| `TXN0032` | MISSING_COUNTERPART | The bank transaction TXN0032 for $42,116.63 dated 2026-02-01 has no matching counterpart in the internal records. | Investigate the missing internal entry and create or locate the corresponding record. |
| `TXN0062` | AMOUNT_MISMATCH | TXN0062 for ₹48021.01 on 2026-03-01 is close to a candidate match but the amount differs beyond the allowed tolerance. | Confirm whether a partial payment, fee, or data-entry error explains the gap. |
| `TXN0058` | MISSING_COUNTERPART | TXN0058 (bank) for ₹6789.13 on 2026-03-01 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `TXN0063` | AMOUNT_MISMATCH | TXN0063 for ₹8186.29 on 2026-02-01 is close to a candidate match but the amount differs beyond the allowed tolerance. | Confirm whether a partial payment, fee, or data-entry error explains the gap. |
| `TXN0059` | MISSING_COUNTERPART | TXN0059 (bank) for ₹33733.55 on 2026-02-11 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `TXN0031` | MISSING_COUNTERPART | TXN0031 (bank) for ₹38147.22 on 2026-01-31 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `TXN0055` | MISSING_COUNTERPART | TXN0055 (bank) for ₹33515.09 on 2026-01-14 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `TXN0061` | AMOUNT_MISMATCH | TXN0061 for ₹4749.85 on 2026-02-11 is close to a candidate match but the amount differs beyond the allowed tolerance. | Confirm whether a partial payment, fee, or data-entry error explains the gap. |
| `TXN0027` | MISSING_COUNTERPART | TXN0027 (bank) for ₹26551.39 on 2026-02-03 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `TXN0051` | MISSING_COUNTERPART | The bank transaction TXN0051 dated 2026-01-03 for $3,556.54 has no matching counterpart in our records, indicating it is missing from the opposite ledger. | Review the bank statement and internal ledgers to locate the missing entry or contact the bank to confirm the transaction details. |
| `TXN0060` | MISSING_COUNTERPART | The bank transaction TXN0060 for $20,250.54 dated 2026-01-22 has no corresponding entry in the ledger, causing a missing counterpart exception. | Search the internal records for a matching entry or create one to reconcile the transaction. |
| `TXN0029` | MISSING_COUNTERPART | TXN0029 (bank) for ₹5756.80 on 2026-01-27 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `TXN0030` | MISSING_COUNTERPART | TXN0030 (bank) for ₹363.12 on 2026-02-17 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `INV0027` | AMBIGUOUS | INV0027 for ₹26549.89 on 2026-02-05 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `INV0049` | AMBIGUOUS | INV0049 for ₹43749.4 on 2026-01-05 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `INV0047` | AMBIGUOUS | INV0047 for ₹9741.19 on 2026-02-04 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `INV0053` | AMOUNT_MISMATCH | INV0053 for ₹43259.59 on 2026-02-27 is close to a candidate match but the amount differs beyond the allowed tolerance. | Confirm whether a partial payment, fee, or data-entry error explains the gap. |
| `INV0031` | AMBIGUOUS | INV0031 for ₹38145.72 on 2026-02-02 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `INV0048` | AMBIGUOUS | INV0048 for ₹21209.71 on 2026-01-18 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `INV0046` | AMBIGUOUS | The invoice INV0046 dated 2026-01-27 for $17,844.02 could not be matched to any transaction, making its classification ambiguous. | Review the original invoice and related payment records to determine the correct matching transaction. |
| `INV0051` | AMOUNT_MISMATCH | INV0051 for ₹48456.01 on 2026-03-01 is close to a candidate match but the amount differs beyond the allowed tolerance. | Confirm whether a partial payment, fee, or data-entry error explains the gap. |
| `INV0030` | AMBIGUOUS | The invoice INV0030 dated 2026-02-16 for $361.62 could not be matched to any corresponding record, resulting in an ambiguous classification. | Manually review the invoice and related payment documents to confirm the correct match or contact the vendor for clarification. |
| `INV0045` | AMBIGUOUS | INV0045 for ₹28895.34 on 2026-01-16 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `INV0052` | AMOUNT_MISMATCH | INV0052 for ₹8482.29 on 2026-02-01 is close to a candidate match but the amount differs beyond the allowed tolerance. | Confirm whether a partial payment, fee, or data-entry error explains the gap. |
| `INV0050` | AMOUNT_MISMATCH | INV0050 for ₹5075.85 on 2026-02-11 is close to a candidate match but the amount differs beyond the allowed tolerance. | Confirm whether a partial payment, fee, or data-entry error explains the gap. |
| `INV0032` | AMBIGUOUS | INV0032 for ₹42115.13 on 2026-02-02 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `INV0029` | AMBIGUOUS | The invoice INV0029 for $5,755.30 dated 2026-01-28 could not be matched to any corresponding payment, leaving its status ambiguous. | Review the original invoice and related payment records and contact the vendor to confirm whether the invoice has been paid or requires further action. |
| `PAY0016` | MISSING_COUNTERPART | PAY0016 (gateway) for ₹9682.41 on 2026-01-07 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |

## Execution Metadata

- Pipeline execution time: 30.51s
- LLM calls made: 20
- LLM available: True
