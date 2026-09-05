# AI Finance Controller

A multi-source bank reconciliation agent for Indian SMEs. It ingests synthetic
records from three sources (bank statement, invoice ledger, payment gateway
log), matches them using a layered pipeline (deterministic rules first, AI
for the hard cases), and outputs a scored reconciliation report with an
honest exception list.

Built for Razorpay's AI Buildathon 2026, Track 04 - AI Finance Controller.

## Results (synthetic dataset, this repo's `data/` as committed)

| Metric | Result | Target |
|---|---|---|
| Precision | 100% | >= 85% |
| Recall | 93.2% | >= 80% |
| F1 | 0.965 | >= 0.85 |
| Exception surfacing | 100% (0 silent drops) | 100% |
| Pipeline execution time | <1s for 216 records | <60s for ~180 |
| LLM calls (with API key) | ~16 Groq / batch | <30 |

These numbers hold even with **zero API keys configured** — every AI-assisted
step has a deterministic or template fallback (static UPI alias map, combo-sum
split detection, template exception explanations). Configuring
`GROQ_API_KEY` improves coverage on the hardest fuzzy-name and ambiguous
cases but isn't required for the pipeline to run correctly.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Optional - enables live LLM calls for cryptic UPI parsing, split-payment
# detection, and richer exception explanations. Without this, the pipeline
# still runs using deterministic fallbacks.
export GROQ_API_KEY="gsk_..."
```

## Usage

```bash
# Regenerate the synthetic dataset (bank.json, invoices.json, gateway.json, ground_truth.json)
python main.py generate-data

# Run the full 5-layer pipeline
python main.py run

# ...with exception detail printed to console
python main.py run --verbose
```

Output:
- `reports/reconciliation_report.json` - full machine-readable report (matches, exceptions, metrics)
- `reports/reconciliation_summary.md` - human-readable Markdown summary

## Architecture

1. **Ingestion & Normalization** (`src/ingestion.py`) - Pydantic validation,
   field standardization, SHA256-based deduplication, source tagging. Logs
   malformed rows instead of crashing.
2. **Deterministic Matching** (`src/deterministic_matcher.py`) - 3-pass:
   exact reference ID → amount+date (±1 day) → composite key (amount ±₹2,
   name prefix, date ±2 days). Enforces 1:1 matching.
3. **AI-Assisted Matching** (`src/ai_matcher.py`) - RapidFuzz fuzzy names
   (local, free), LLM via Groq for cryptic UPI IDs and split-payment detection
   (both with deterministic fallbacks), confidence scoring.
4. **Exception Handling** (`src/exception_handler.py`) - Classifies every
   remaining record as DUPLICATE / MISSING_COUNTERPART / PARTIAL_MATCH /
   AMBIGUOUS / AMOUNT_MISMATCH, with a reason code, plain-English
   explanation, and suggested action.
5. **Reporting** (`src/reporter.py`) - Precision/recall/F1 against ground
   truth, cash position delta, JSON + Markdown output.

## Project structure

```
ai-finance-controller/
├── main.py                     # Typer CLI
├── generate_synthetic_data.py  # synthetic dataset generator (9 scenario types)
├── requirements.txt
├── src/
│   ├── models.py                # Pydantic schemas
│   ├── ingestion.py              # Layer 1
│   ├── deterministic_matcher.py  # Layer 2
│   ├── ai_matcher.py             # Layer 3
│   ├── llm_client.py             # Groq API wrapper
│   ├── exception_handler.py      # Layer 4
│   └── reporter.py               # Layer 5
├── data/                        # generated synthetic data + ground truth
└── reports/                     # generated output (JSON + Markdown)
```

## Known limitations / honest notes

- The synthetic dataset is generated with a fixed random seed (42) for
  reproducibility - rerun `generate-data` without the seed if you want a
  fresh dataset each time.
- Cryptic-UPI records are occasionally caught earlier by the amount+date
  pass (Layer 2) since that pass matches on amount/date regardless of
  description text - this doesn't hurt accuracy but means Layer 3's UPI
  resolution sometimes has fewer records left to work on than the raw
  scenario count would suggest.
- Razorpay Test Mode API / MCP Server / Agent Studio integrations are
  scoped in the original build plan but not wired into this codebase -
  see the plan document for the intended integration points if you want to
  add them for the "should-have"/"nice-to-have" judging tiers.
