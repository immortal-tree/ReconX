"""
main.py - CLI entrypoint for the AI Finance Controller reconciliation agent.

Usage:
    python main.py run                 # run full pipeline, print summary
    python main.py run --verbose        # also print exception detail
    python main.py generate-data        # regenerate synthetic data
"""

import json
import time
from pathlib import Path

import typer

from src.ai_matcher import AIMatcher
from src.deterministic_matcher import DeterministicMatcher
from src.exception_handler import ExceptionHandler
from src.ingestion import ingest
from src.reporter import build_report, write_reports

app = typer.Typer(help="AI Finance Controller - multi-source bank reconciliation agent")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"


@app.command()
def run(verbose: bool = typer.Option(False, help="Print exception detail to console")):
    """Run the full 5-layer reconciliation pipeline and write reports."""
    start = time.perf_counter()

    typer.echo("Layer 1: Ingesting & normalizing...")
    ing = ingest(DATA_DIR)
    typer.echo(f"  -> {json.dumps(ing.summary())}")

    typer.echo("Layer 2: Deterministic matching (3-pass)...")
    det = DeterministicMatcher(ing)
    det.run_all()
    typer.echo(f"  -> {json.dumps(det.stats())}")

    typer.echo("Layer 3: AI-assisted matching (fuzzy names, UPI parsing, split detection)...")
    ai = AIMatcher(det)
    ai.run_all()
    typer.echo(f"  -> fuzzy={ai.fuzzy_matches_made} upi_resolved={ai.upi_resolutions} "
               f"splits={ai.split_detections} ambiguous={len(ai.ambiguous_flagged)} "
               f"llm_available={ai.llm.available}")

    typer.echo("Layer 4: Exception handling...")
    handler = ExceptionHandler(ai)
    handler.classify_all()
    typer.echo(f"  -> {json.dumps(handler.stats())}")

    elapsed = time.perf_counter() - start

    typer.echo("Layer 5: Reporting...")
    ground_truth = json.loads((DATA_DIR / "ground_truth.json").read_text())
    execution_metadata = {
        "execution_seconds": round(elapsed, 2),
        "llm_calls": ai.llm.call_count,
        "llm_available": ai.llm.available,
    }
    report = build_report(ai, handler, ground_truth, execution_metadata)
    write_reports(report, REPORTS_DIR)

    typer.echo("\n=== SUMMARY ===")
    typer.echo(json.dumps(report["summary"], indent=2))
    typer.echo("\n=== METRICS vs GROUND TRUTH ===")
    typer.echo(json.dumps(report["metrics_vs_ground_truth"], indent=2))
    typer.echo(f"\nReports written to {REPORTS_DIR}/reconciliation_report.json "
               f"and {REPORTS_DIR}/reconciliation_summary.md")

    if verbose:
        typer.echo("\n=== EXCEPTIONS ===")
        for e in handler.exceptions:
            typer.echo(f"[{e.exception_type.value}] {e.record_id}: {e.explanation}")


@app.command("generate-data")
def generate_data():
    """Regenerate the synthetic dataset (bank/invoices/gateway/ground truth)."""
    import subprocess
    subprocess.run(["python3", str(BASE_DIR / "generate_synthetic_data.py")], check=True)


if __name__ == "__main__":
    app()
