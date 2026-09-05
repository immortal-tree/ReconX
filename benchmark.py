"""
benchmark.py - runs the full 5-layer reconciliation pipeline N times (default
5, per the master build plan's Phase 7 checkpoint) against the data already
in data/, and reports mean/stddev for execution time, precision, recall, F1,
and LLM call count against the plan's benchmark targets:

    Precision >= 85%, Recall >= 80%, F1 >= 0.85
    Execution < 60s for ~180 records
    < 30 LLM calls per batch

Usage:
    python benchmark.py                  # 5 runs (default)
    python benchmark.py --runs 10
    python benchmark.py --runs 5 --json-out reports/benchmark_results.json
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Optional

import typer

from src.ai_matcher import AIMatcher
from src.deterministic_matcher import DeterministicMatcher
from src.exception_handler import ExceptionHandler
from src.ingestion import ingest
from src.reporter import build_report

app = typer.Typer(help="Benchmark the reconciliation pipeline across multiple runs.")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# (stat used for the check, comparison operator, target value)
TARGET_CHECKS = {
    "precision": ("mean", ">=", 0.85),
    "recall": ("mean", ">=", 0.80),
    "f1": ("mean", ">=", 0.85),
    "execution_seconds": ("max", "<", 60.0),
    "llm_calls": ("max", "<", 30),
}


def _run_once(ground_truth: list[dict]) -> dict:
    """Run all 5 layers once against data/ and return the metrics that matter
    for benchmarking. Re-ingests fresh each run so ingestion/dedup cost is
    included in the timing, matching what a real batch invocation looks like."""
    start = time.perf_counter()
    ing = ingest(DATA_DIR)
    det = DeterministicMatcher(ing)
    det.run_all()
    ai = AIMatcher(det)
    ai.run_all()
    handler = ExceptionHandler(ai)
    handler.classify_all()
    elapsed = time.perf_counter() - start

    execution_metadata = {
        "execution_seconds": round(elapsed, 4),
        "llm_calls": ai.llm.call_count,
        "llm_available": ai.llm.available,
    }
    report = build_report(ai, handler, ground_truth, execution_metadata)
    m = report["metrics_vs_ground_truth"]

    return {
        "execution_seconds": elapsed,
        "precision": m["precision"],
        "recall": m["recall"],
        "f1": m["f1"],
        "llm_calls": ai.llm.call_count,
        "llm_available": ai.llm.available,
        "total_matches": report["summary"]["total_matches"],
        "total_exceptions": report["summary"]["total_exceptions"],
    }


def _mean_std(values: list[float]) -> tuple[float, float]:
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return mean, std


@app.command()
def benchmark(
    runs: int = typer.Option(5, "--runs", help="Number of pipeline runs"),
    json_out: Optional[str] = typer.Option(
        None, "--json-out", help="Optional path to write raw per-run results + summary as JSON"
    ),
):
    """Run the pipeline `runs` times and report mean/stddev vs the master plan's benchmark targets."""
    gt_path = DATA_DIR / "ground_truth.json"
    if not gt_path.exists():
        typer.secho("No data/ground_truth.json found - run `python main.py generate-data` first.",
                     fg=typer.colors.RED)
        raise typer.Exit(1)

    ground_truth = json.loads(gt_path.read_text())

    typer.echo(f"Running pipeline {runs} time(s) against data/ ...\n")
    results = []
    for i in range(1, runs + 1):
        r = _run_once(ground_truth)
        results.append(r)
        typer.echo(
            f"  Run {i}/{runs}: {r['execution_seconds']:.2f}s | "
            f"P={r['precision']:.1%} R={r['recall']:.1%} F1={r['f1']:.3f} | "
            f"llm_calls={r['llm_calls']} (available={r['llm_available']})"
        )

    if results[0]["llm_available"] and all(r["llm_calls"] == 0 for r in results):
        typer.secho(
            "\n  WARNING: llm_available=True but llm_calls=0 on every run. "
            "The API key is configured but every call is failing (bad model name, "
            "expired key, or rate limit) and silently falling back to the "
            "deterministic/template path. Check the model name in src/llm_client.py.",
            fg=typer.colors.YELLOW,
        )

    metrics = ["execution_seconds", "precision", "recall", "f1", "llm_calls"]
    summary = {}
    for key in metrics:
        vals = [r[key] for r in results]
        mean, std = _mean_std(vals)
        summary[key] = {
            "mean": round(mean, 4), "stddev": round(std, 4),
            "min": round(min(vals), 4), "max": round(max(vals), 4),
        }

    typer.echo(f"\n=== BENCHMARK SUMMARY (n={runs}) ===")
    header = f"{'Metric':<20}{'Mean':>10}{'StdDev':>10}{'Min':>10}{'Max':>10}{'Target':>12}{'Status':>8}"
    typer.echo(header)
    typer.echo("-" * len(header))

    all_pass = True
    for key in metrics:
        s = summary[key]
        stat_key, op, target = TARGET_CHECKS[key]
        val = s[stat_key]
        ok = (val >= target) if op == ">=" else (val < target)
        all_pass = all_pass and ok
        status = "PASS" if ok else "FAIL"
        label = key.replace("_", " ").title()
        target_str = f"{op}{target}"
        typer.echo(f"{label:<20}{s['mean']:>10}{s['stddev']:>10}{s['min']:>10}{s['max']:>10}{target_str:>12}{status:>8}")

    typer.echo(f"\nOverall: {'ALL TARGETS MET' if all_pass else 'SOME TARGETS MISSED'}")

    if json_out:
        out_path = Path(json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"runs": results, "summary": summary}, indent=2))
        typer.echo(f"\nRaw results written to {out_path}")


if __name__ == "__main__":
    app()
