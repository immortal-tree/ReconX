# Reconciliation Summary Report

_Generated: 2026-09-05T13:38:00.156392+00:00_

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
| MISSING_COUNTERPART | 13 |
| AMOUNT_MISMATCH | 6 |
| AMBIGUOUS | 11 |

## Exception Detail

| Record ID | Type | Explanation | Suggested Action |
|---|---|---|---|
| `TXN0054` | MISSING_COUNTERPART | TXN0054 (bank) for ₹3728.7 on 2026-01-16 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `TXN0064` | AMOUNT_MISMATCH | TXN0064 for ₹43179.59 on 2026-02-27 is close to a candidate match but the amount differs beyond the allowed tolerance. | Confirm whether a partial payment, fee, or data-entry error explains the gap. |
| `TXN0032` | MISSING_COUNTERPART | TXN0032 (bank) for ₹42116.63 on 2026-02-01 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `TXN0062` | AMOUNT_MISMATCH | TXN0062 for ₹48021.01 on 2026-03-01 is close to a candidate match but the amount differs beyond the allowed tolerance. | Confirm whether a partial payment, fee, or data-entry error explains the gap. |
| `TXN0058` | MISSING_COUNTERPART | TXN0058 (bank) for ₹6789.13 on 2026-03-01 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `TXN0063` | AMOUNT_MISMATCH | TXN0063 for ₹8186.29 on 2026-02-01 is close to a candidate match but the amount differs beyond the allowed tolerance. | Confirm whether a partial payment, fee, or data-entry error explains the gap. |
| `TXN0059` | MISSING_COUNTERPART | TXN0059 (bank) for ₹33733.55 on 2026-02-11 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `TXN0031` | MISSING_COUNTERPART | TXN0031 (bank) for ₹38147.22 on 2026-01-31 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `TXN0055` | MISSING_COUNTERPART | TXN0055 (bank) for ₹33515.09 on 2026-01-14 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `TXN0061` | MISSING_COUNTERPART | TXN0061 (bank) for ₹4749.85 on 2026-02-11 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `TXN0027` | MISSING_COUNTERPART | TXN0027 (bank) for ₹26551.39 on 2026-02-03 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `TXN0051` | MISSING_COUNTERPART | TXN0051 (bank) for ₹3556.54 on 2026-01-03 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `TXN0060` | MISSING_COUNTERPART | TXN0060 (bank) for ₹20250.54 on 2026-01-22 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `TXN0029` | MISSING_COUNTERPART | TXN0029 (bank) for ₹5756.80 on 2026-01-27 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `TXN0030` | MISSING_COUNTERPART | TXN0030 (bank) for ₹363.12 on 2026-02-17 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |
| `INV0027` | AMBIGUOUS | INV0027 for ₹26549.89 on 2026-02-05 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `INV0049` | AMBIGUOUS | INV0049 for ₹43749.4 on 2026-01-05 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `INV0047` | AMBIGUOUS | INV0047 for ₹9741.19 on 2026-02-04 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `INV0053` | AMOUNT_MISMATCH | INV0053 for ₹43259.59 on 2026-02-27 is close to a candidate match but the amount differs beyond the allowed tolerance. | Confirm whether a partial payment, fee, or data-entry error explains the gap. |
| `INV0031` | AMBIGUOUS | INV0031 for ₹38145.72 on 2026-02-02 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `INV0048` | AMBIGUOUS | INV0048 for ₹21209.71 on 2026-01-18 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `INV0046` | AMBIGUOUS | INV0046 for ₹17844.02 on 2026-01-27 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `INV0051` | AMOUNT_MISMATCH | INV0051 for ₹48456.01 on 2026-03-01 is close to a candidate match but the amount differs beyond the allowed tolerance. | Confirm whether a partial payment, fee, or data-entry error explains the gap. |
| `INV0030` | AMBIGUOUS | INV0030 for ₹361.62 on 2026-02-16 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `INV0045` | AMBIGUOUS | INV0045 for ₹28895.34 on 2026-01-16 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `INV0052` | AMOUNT_MISMATCH | INV0052 for ₹8482.29 on 2026-02-01 is close to a candidate match but the amount differs beyond the allowed tolerance. | Confirm whether a partial payment, fee, or data-entry error explains the gap. |
| `INV0050` | AMBIGUOUS | INV0050 for ₹5075.85 on 2026-02-11 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `INV0032` | AMBIGUOUS | INV0032 for ₹42115.13 on 2026-02-02 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `INV0029` | AMBIGUOUS | INV0029 for ₹5755.3 on 2026-01-28 has multiple plausible matches and could not be resolved automatically. | Manual review recommended - compare candidate records side by side. |
| `PAY0016` | MISSING_COUNTERPART | PAY0016 (gateway) for ₹9682.41 on 2026-01-07 has no matching record in the other two sources. | Check for a missing invoice/bank entry or confirm this was a one-off transaction. |

## Execution Metadata

- Pipeline execution time: 0.01s
- LLM calls made: 0
- LLM available: False
