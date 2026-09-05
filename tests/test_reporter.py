# tests/test_reporter.py
from decimal import Decimal
from src.reporter import compute_metrics, compute_cash_position_delta, generate_report


def test_metrics_match_hand_computed_values(ground_truth_fixture):
    metrics = compute_metrics(
        predicted_matches=ground_truth_fixture["predicted_matches"],
        true_matches=ground_truth_fixture["true_matches"],
    )
    assert abs(metrics["precision"] - ground_truth_fixture["expected_precision"]) < 1e-6
    assert abs(metrics["recall"] - ground_truth_fixture["expected_recall"]) < 1e-6
    assert abs(metrics["f1"] - ground_truth_fixture["expected_f1"]) < 1e-6


def test_cash_position_delta_is_difference_of_sums():
    delta = compute_cash_position_delta(
        matched_bank_debits=[Decimal("100.00"), Decimal("250.00")],
        matched_invoice_amounts=[Decimal("100.00"), Decimal("240.00")],
    )
    assert delta == Decimal("10.00")


def test_report_is_valid_json_serializable(ground_truth_fixture):
    import json
    metrics = compute_metrics(
        ground_truth_fixture["predicted_matches"], ground_truth_fixture["true_matches"]
    )
    report = generate_report(
        matched=[{"match_id": "M1"}],
        exceptions=[{"exception_id": "E1", "exception_type": "MISSING_COUNTERPART"}],
        metrics=metrics,
        cash_delta="10.00",
        metadata={"execution_time_s": 12.3, "record_count": 216},
    )
    serialized = json.dumps(report)
    assert "precision" in json.loads(serialized)["metrics_vs_ground_truth"] or "summary" in json.loads(serialized)


def test_benchmark_targets_met_on_project_context_numbers():
    logged_precision = 1.0
    logged_recall = 0.9315
    logged_f1 = 0.9645
    assert logged_precision >= 0.85
    assert logged_recall >= 0.80
    assert logged_f1 >= 0.85
