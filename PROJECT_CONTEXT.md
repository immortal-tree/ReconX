# AI Finance Controller — Project Context & Status Log

> **For Multi-Agent Handshake & Progress Tracking.** This document maintains the up-to-date execution status, architectural decisions, live benchmark metrics, and context state for all collaborating agents.

---

## 1. Project Overview

- **Track:** Razorpay AI Buildathon 2026 — Track 04 (AI Finance Controller)
- **Goal:** Multi-source bank reconciliation engine (Bank Statement × Invoice Ledger × Payment Gateway Log) for Indian SMEs.
- **Repository:** `https://github.com/immortal-tree/ReconX` (Branch: `main`)

---

## 2. Current Benchmark & Execution Metrics

- **Pipeline Execution:** Runs end-to-end via `python main.py run --verbose`
- **Dataset Size:** 216 synthetic records across 3 sources
- **Precision:** `100.0%` (1.0)
- **Recall:** `93.15%` (0.9315)
- **F1 Score:** `0.9645` (Target: ≥ 0.85)
- **Exception Surfacing Rate:** `100.0%` (0 silent drops, 30 exceptions classified)
- **Live LLM Integration:** `GROQ_API_KEY` active (`llm_available = True`, `llm_calls = 57` per batch)
- **LLM Model:** `openai/gpt-oss-120b` via Groq SDK (`src/llm_client.py`)

---

## 3. Architecture & File Structure

```
.
├── main.py                     # Typer CLI entrypoint (`run`, `generate-data`)
├── generate_synthetic_data.py  # Synthetic dataset generator (9 scenario types)
├── requirements.txt            # Project dependencies (groq, pydantic, rapidfuzz, pandas, typer)
├── .env                        # Local environment variables (GROQ_API_KEY)
├── .gitignore                  # Excludes venv, __pycache__, .env
├── PROJECT_CONTEXT.md          # Multi-agent context & progress tracking file
├── src/
│   ├── __init__.py
│   ├── models.py               # Pydantic data schemas
│   ├── ingestion.py             # Layer 1: Normalization & deduplication
│   ├── deterministic_matcher.py # Layer 2: 3-pass exact/amount-date/composite matching
│   ├── ai_matcher.py            # Layer 3: Fuzzy matching & LLM-assisted UPI/split parsing
│   ├── llm_client.py            # Thin Groq API wrapper with dotenv & fast-fail fallback
│   ├── exception_handler.py     # Layer 4: Exception taxonomy & explanation generation
│   └── reporter.py              # Layer 5: Ground truth metrics & report generator
├── data/
│   ├── bank.json
│   ├── gateway.json
│   ├── invoices.json
│   └── ground_truth.json
└── reports/
    ├── reconciliation_report.json
    └── reconciliation_summary.md
```

---

## 4. Layer Pipeline Breakdown

1. **Layer 1: Ingestion & Normalization (`src/ingestion.py`)**
   - Validates records via Pydantic (`models.py`)
   - Normalizes UPI narration regex (`r'UPI/\w+/(\d{12})/(\S+)'`)
   - Removes duplicate records using SHA256 hashing

2. **Layer 2: Deterministic Matching (`src/deterministic_matcher.py`)**
   - Pass 1: Exact reference ID matching
   - Pass 2: Exact amount + date within ±1 day
   - Pass 3: Composite key (amount ±₹2, name prefix, date ±2 days)

3. **Layer 3: AI-Assisted Matching (`src/ai_matcher.py`)**
   - RapidFuzz token sort ratio for merchant names
   - Live Groq LLM queries for cryptic UPI merchant ID resolution
   - Live Groq LLM queries for split payment combination detection

4. **Layer 4: Exception Handling (`src/exception_handler.py`)**
   - Categorizes unresolved records into taxonomy: `DUPLICATE`, `MISSING_COUNTERPART`, `PARTIAL_MATCH`, `AMBIGUOUS`, `AMOUNT_MISMATCH`
   - Generates plain-English explanations and suggested resolution actions

5. **Layer 5: Reporting (`src/reporter.py`)**
   - Computes precision, recall, F1, and cash position delta
   - Writes `reconciliation_report.json` and `reconciliation_summary.md`

---

## 5. Progress History & Key Milestones

| Timestamp | Milestone | Status | Details |
|---|---|---|---|
| 2026-09-05 | File Restructuring | Completed | Organized root files into `src/`, `data/`, `reports/` |
| 2026-09-05 | GitHub Repo Push | Completed | Pushed missing modules (`reporter.py`, `__init__.py`) to GitHub |
| 2026-09-05 | Groq Provider Migration | Completed | Migrated `LLMClient` from Anthropic to Groq API |
| 2026-09-05 | Fast-Fail & Dotenv Setup | Completed | Added `.env` loading and fast-fail placeholder handling |
| 2026-09-05 | Live LLM Verification | Completed | Verified live API execution (`llm_available = True`) with `llama-3.3-70b-versatile` |

---

## 6. Guidelines for Subagents

- Always load environment variables using `from dotenv import load_dotenv; load_dotenv()` before initializing `LLMClient`.
- Do not commit `.env` or sensitive API keys to Git.
- When modifying matching logic or exception rules, verify that precision stays ≥ 85% and recall ≥ 80% by running `python main.py run`.
- Keep `PROJECT_CONTEXT.md` updated after major architectural changes or benchmark updates.
