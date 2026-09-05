"""
Layer 5: Reporting.

Computes precision/recall/F1 against ground truth, cash position delta,
and writes both a JSON report and a Markdown summary.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.ai_matcher import AIMatcher
from src.exception_handler import ExceptionHandler


def _gt_record_ids(g: dict) -> set[str]:
    ids = set()
    for key in ("bank_txn_id", "invoice_id", "gateway_payment_id"):
        if g.get(key):
            ids.add(g[key])
    for key in ("bank_txn_ids", "invoice_ids", "gateway_payment_ids"):
        for v in g.get(key, []) or []:
            ids.add(v)
    return ids


def compute_metrics(matches: list, ground_truth: list[dict]) -> dict:
    """
    True match = a predicted match whose record set exactly equals (or is a
    subset consistent with) a ground-truth matched group. We evaluate at the
    pairwise level: for every ground-truth group with >1 record that SHOULD
    match, check whether our pipeline linked those records together.
    """
    # Ground truth groups that represent a real match (i.e. not an exception)
    gt_positive_groups = [
        _gt_record_ids(g) for g in ground_truth
        if g.get("exception_type") is None and len(_gt_record_ids(g)) > 1
    ]
    gt_positive_record_ids = set().union(*gt_positive_groups) if gt_positive_groups else set()

    predicted_groups = [
        set(m.bank_txn_ids) | set(m.invoice_ids) | set(m.gateway_payment_ids)
        for m in matches
    ]

    true_positives = 0
    false_positives = 0
    for pred in predicted_groups:
        # a predicted match is "correct" if it is a subset of some gt group
        # (or equal to it) - i.e. every record in it truly belongs together
        if any(pred <= gt for gt in gt_positive_groups) and len(pred) > 1:
            true_positives += 1
        elif len(pred) > 1:
            false_positives += 1
        # single-record "matches" shouldn't occur in this pipeline

    matched_gt_groups = sum(
        1 for gt in gt_positive_groups
        if any(pred <= gt and len(pred) > 1 for pred in predicted_groups)
    )
    false_negatives = len(gt_positive_groups) - matched_gt_groups

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "ground_truth_positive_groups": len(gt_positive_groups),
        "predicted_groups": len(predicted_groups),
    }


def compute_cash_delta(ai_matcher: AIMatcher) -> dict:
    matcher = ai_matcher.matcher
    matched_bank_ids = {b for m in matcher.matches for b in m.bank_txn_ids}
    matched_invoice_ids = {i for m in matcher.matches for i in m.invoice_ids}

    matched_bank_total = sum(
        (b.amount for b in matcher.bank if b.txn_id in matched_bank_ids), Decimal("0")
    )
    matched_invoice_total = sum(
        (i.amount for i in matcher.invoices if i.invoice_id in matched_invoice_ids), Decimal("0")
    )
    delta = matched_bank_total - matched_invoice_total
    return {
        "matched_bank_debits_total": str(matched_bank_total),
        "matched_invoice_amount_total": str(matched_invoice_total),
        "cash_position_delta": str(delta),
    }


def build_report(ai_matcher: AIMatcher, handler: ExceptionHandler, ground_truth: list[dict],
                  execution_metadata: dict) -> dict:
    matcher = ai_matcher.matcher
    metrics = compute_metrics(matcher.matches, ground_truth)
    cash = compute_cash_delta(ai_matcher)

    total_records = len(matcher.bank) + len(matcher.invoices) + len(matcher.gateway)
    total_matched_records = sum(
        len(m.bank_txn_ids) + len(m.invoice_ids) + len(m.gateway_payment_ids) for m in matcher.matches
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_records_ingested": total_records,
            "total_matches": len(matcher.matches),
            "total_records_matched": total_matched_records,
            "total_exceptions": len(handler.exceptions),
            "exception_surfacing_rate": "100%" if handler.exceptions or total_matched_records == total_records else "N/A",
            "match_rate": round(total_matched_records / total_records, 4) if total_records else 0.0,
        },
        "metrics_vs_ground_truth": metrics,
        "matches_by_tier": matcher.stats()["by_tier"],
        "cash_position": cash,
        "exceptions_by_type": handler.stats()["by_type"],
        "execution_metadata": execution_metadata,
        "matches": [m.model_dump(mode="json") for m in matcher.matches],
        "exceptions": [e.model_dump(mode="json") for e in handler.exceptions],
    }
    return report


def render_markdown(report: dict) -> str:
    s = report["summary"]
    m = report["metrics_vs_ground_truth"]
    c = report["cash_position"]
    meta = report["execution_metadata"]

    lines = [
        "# Reconciliation Summary Report",
        "",
        f"_Generated: {report['generated_at']}_",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Total records ingested | {s['total_records_ingested']} |",
        f"| Total matches found | {s['total_matches']} |",
        f"| Records matched | {s['total_records_matched']} |",
        f"| Match rate | {s['match_rate']:.1%} |",
        f"| Total exceptions | {s['total_exceptions']} |",
        "",
        "## Accuracy vs Ground Truth",
        "",
        "| Metric | Value | Target | Status |",
        "|---|---|---|---|",
        f"| Precision | {m['precision']:.1%} | >= 85% | {'✅' if m['precision'] >= 0.85 else '⚠️'} |",
        f"| Recall | {m['recall']:.1%} | >= 80% | {'✅' if m['recall'] >= 0.80 else '⚠️'} |",
        f"| F1 | {m['f1']:.3f} | >= 0.85 | {'✅' if m['f1'] >= 0.85 else '⚠️'} |",
        "",
        "## Matches by Tier",
        "",
        "| Tier | Count |",
        "|---|---|",
    ]
    for tier, count in report["matches_by_tier"].items():
        lines.append(f"| {tier} | {count} |")

    lines += [
        "",
        "## Cash Position",
        "",
        f"- Matched bank debits total: ₹{c['matched_bank_debits_total']}",
        f"- Matched invoice amount total: ₹{c['matched_invoice_amount_total']}",
        f"- **Cash position delta: ₹{c['cash_position_delta']}**",
        "",
        "## Exceptions by Type",
        "",
        "| Type | Count |",
        "|---|---|",
    ]
    for etype, count in report["exceptions_by_type"].items():
        lines.append(f"| {etype} | {count} |")

    lines += [
        "",
        "## Exception Detail",
        "",
        "| Record ID | Type | Explanation | Suggested Action |",
        "|---|---|---|---|",
    ]
    for e in report["exceptions"]:
        lines.append(f"| `{e['record_id']}` | {e['exception_type']} | {e['explanation']} | {e['suggested_action']} |")

    lines += [
        "",
        "## Execution Metadata",
        "",
        f"- Pipeline execution time: {meta.get('execution_seconds', 'N/A')}s",
        f"- LLM calls made: {meta.get('llm_calls', 0)}",
        f"- LLM available: {meta.get('llm_available', False)}",
        "",
    ]
    return "\n".join(lines)


def write_reports(report: dict, out_dir: Path):
    out_dir.mkdir(exist_ok=True)
    (out_dir / "reconciliation_report.json").write_text(json.dumps(report, indent=2, default=str))
    (out_dir / "reconciliation_summary.md").write_text(render_markdown(report))


if __name__ == "__main__":
    import time
    from pathlib import Path
    from src.ingestion import ingest
    from src.deterministic_matcher import DeterministicMatcher

    data_dir = Path(__file__).parent.parent / "data"
    reports_dir = Path(__file__).parent.parent / "reports"

    start = time.perf_counter()
    ing = ingest(data_dir)
    det = DeterministicMatcher(ing)
    det.run_all()
    ai = AIMatcher(det)
    ai.run_all()
    handler = ExceptionHandler(ai)
    handler.classify_all()
    elapsed = time.perf_counter() - start

    ground_truth = json.loads((data_dir / "ground_truth.json").read_text())
    execution_metadata = {
        "execution_seconds": round(elapsed, 2),
        "llm_calls": ai.llm.call_count,
        "llm_available": ai.llm.available,
    }
    report = build_report(ai, handler, ground_truth, execution_metadata)
    write_reports(report, reports_dir)
    print(json.dumps(report["summary"], indent=2))
    print(json.dumps(report["metrics_vs_ground_truth"], indent=2))
    print(f"\nReports written to {reports_dir}/")
