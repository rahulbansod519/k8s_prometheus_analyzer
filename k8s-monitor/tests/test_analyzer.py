"""Unit tests for k8s_prometheus_analyzer.analyzer."""

from __future__ import annotations

from k8s_prometheus_analyzer.analyzer import SEVERITY_CRITICAL, analyze
from k8s_prometheus_analyzer.config import Thresholds

from .conftest import make_workload_metrics

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _single(wm_list):
    """Assert exactly one recommendation and return it."""
    recs = analyze(wm_list)
    assert len(recs) == 1, f"Expected 1 recommendation, got {len(recs)}: {recs}"
    return recs[0]


def _none(wm_list) -> None:
    """Assert no recommendations are generated."""
    recs = analyze(wm_list)
    assert recs == [], f"Expected no recommendations, got {recs}"


# ---------------------------------------------------------------------------
# Happy path — well-optimised workload produces no recommendation
# ---------------------------------------------------------------------------


def test_well_optimised_workload_no_recommendation():
    """A workload using 50 % of a reasonable request should generate nothing."""
    wm_list = make_workload_metrics(
        cpu_usage_per_pod=0.5,
        cpu_request_per_pod=1.0,
        memory_mb_per_pod=200.0,
        memory_request_mb_per_pod=400.0,
    )
    _none(wm_list)


# ---------------------------------------------------------------------------
# Rule 1 — CPU over-provisioned
# ---------------------------------------------------------------------------


def test_rule1_cpu_low_triggers_reduce_request():
    wm_list = make_workload_metrics(cpu_usage_per_pod=0.05, cpu_request_per_pod=1.0)
    rec = _single(wm_list)
    assert "Reduce CPU requests" in rec.suggestions


def test_rule1_cpu_at_threshold_not_triggered():
    """Exactly at the threshold should NOT trigger."""
    wm_list = make_workload_metrics(cpu_usage_per_pod=0.1, cpu_request_per_pod=1.0)
    recs = analyze(wm_list)
    assert not any("Reduce CPU requests" in r.suggestions for r in recs)


# ---------------------------------------------------------------------------
# Rule 2 — Memory over-provisioned
# ---------------------------------------------------------------------------


def test_rule2_memory_low_triggers_reduce_request():
    wm_list = make_workload_metrics(
        cpu_usage_per_pod=0.5,
        cpu_request_per_pod=1.0,
        memory_mb_per_pod=10.0,           # < 50 MB threshold
        memory_request_mb_per_pod=512.0,
    )
    recs = analyze(wm_list)
    assert any("Reduce memory requests" in r.suggestions for r in recs)


# ---------------------------------------------------------------------------
# Rule 3 — CPU over-utilised
# ---------------------------------------------------------------------------


def test_rule3_high_cpu_percentage_triggers_scale():
    wm_list = make_workload_metrics(cpu_usage_per_pod=0.9, cpu_request_per_pod=1.0)
    recs = analyze(wm_list)
    assert any("Increase CPU limits or add replicas" in r.suggestions for r in recs)


def test_rule3_severity_is_critical():
    wm_list = make_workload_metrics(cpu_usage_per_pod=0.9, cpu_request_per_pod=1.0)
    recs = analyze(wm_list)
    critical = [r for r in recs if r.severity == SEVERITY_CRITICAL]
    assert critical, "Expected at least one CRITICAL severity recommendation"


# ---------------------------------------------------------------------------
# Rule 4 — Memory over-utilised
# ---------------------------------------------------------------------------


def test_rule4_high_memory_triggers_increase_limits():
    wm_list = make_workload_metrics(
        cpu_usage_per_pod=0.3,
        cpu_request_per_pod=1.0,
        memory_mb_per_pod=600.0,          # > 500 MB threshold
        memory_request_mb_per_pod=800.0,
    )
    recs = analyze(wm_list)
    assert any("Increase Memory limits" in r.suggestions for r in recs)


# ---------------------------------------------------------------------------
# Rule 5 — CPU throttled
# ---------------------------------------------------------------------------


def test_rule5_cpu_usage_exceeds_request():
    wm_list = make_workload_metrics(cpu_usage_per_pod=1.5, cpu_request_per_pod=1.0)
    recs = analyze(wm_list)
    assert any("Increase CPU requests" in r.suggestions for r in recs)


def test_rule5_produces_critical_severity():
    wm_list = make_workload_metrics(cpu_usage_per_pod=1.5, cpu_request_per_pod=1.0)
    recs = analyze(wm_list)
    assert any(r.severity == SEVERITY_CRITICAL for r in recs)


# ---------------------------------------------------------------------------
# Rule 6 — Memory overcommitment
# ---------------------------------------------------------------------------


def test_rule6_memory_overcommit_triggers():
    wm_list = make_workload_metrics(
        cpu_usage_per_pod=0.3,
        cpu_request_per_pod=1.0,
        memory_mb_per_pod=50.0,
        memory_request_mb_per_pod=800.0,  # ratio = 16 > 3 default
    )
    recs = analyze(wm_list)
    assert any("Reduce memory requests" in r.suggestions for r in recs)


def test_rule6_no_duplicate_reduce_memory_suggestion():
    """When both rule 2 and rule 6 apply, 'Reduce memory requests' appears once."""
    wm_list = make_workload_metrics(
        cpu_usage_per_pod=0.3,
        cpu_request_per_pod=1.0,
        memory_mb_per_pod=10.0,           # < 50 MB AND big ratio
        memory_request_mb_per_pod=800.0,
    )
    recs = analyze(wm_list)
    assert len(recs) == 1
    count = recs[0].suggestions.count("Reduce memory requests")
    assert count == 1, f"'Reduce memory requests' appeared {count} times"


# ---------------------------------------------------------------------------
# Rule 7 — Consider reducing replicas
# ---------------------------------------------------------------------------


def test_rule7_minimal_usage_suggests_replica_reduction():
    wm_list = make_workload_metrics(
        cpu_usage_per_pod=0.01,
        cpu_request_per_pod=0.1,
        memory_mb_per_pod=5.0,
        memory_request_mb_per_pod=64.0,
    )
    recs = analyze(wm_list)
    assert any("Consider reducing replicas" in r.suggestions for r in recs)


def test_rule7_reason_mentions_replica_count():
    wm_list = make_workload_metrics(
        num_replicas=3,
        cpu_usage_per_pod=0.01,
        cpu_request_per_pod=0.1,
        memory_mb_per_pod=5.0,
        memory_request_mb_per_pod=64.0,
    )
    recs = analyze(wm_list)
    assert recs
    assert "3" in recs[0].reasons[-1]  # replica count mentioned in reason


# ---------------------------------------------------------------------------
# Workload identity fields
# ---------------------------------------------------------------------------


def test_recommendation_carries_workload_info():
    wm_list = make_workload_metrics(
        workload_name="frontend",
        workload_kind="Deployment",
        namespace="production",
        num_replicas=3,
        cpu_usage_per_pod=1.5,
        cpu_request_per_pod=1.0,
    )
    recs = analyze(wm_list)
    assert recs
    rec = recs[0]
    assert rec.workload_name == "frontend"
    assert rec.workload_kind == "Deployment"
    assert rec.namespace == "production"
    assert rec.replica_count == 3
    assert len(rec.pod_names) == 3


def test_recommendation_aggregate_totals_correct():
    wm_list = make_workload_metrics(
        num_replicas=4,
        cpu_usage_per_pod=1.5,
        cpu_request_per_pod=1.0,
        memory_mb_per_pod=200.0,
        memory_request_mb_per_pod=300.0,
    )
    recs = analyze(wm_list)
    assert recs
    rec = recs[0]
    assert abs(rec.total_cpu_usage - 6.0) < 1e-9   # 4 × 1.5
    assert abs(rec.total_memory_mb - 800.0) < 1e-9  # 4 × 200


# ---------------------------------------------------------------------------
# Custom thresholds
# ---------------------------------------------------------------------------


def test_custom_thresholds_respected():
    """With a very low cpu_low threshold, rule 1 should NOT fire."""
    custom = Thresholds(cpu_low=0.001)
    wm_list = make_workload_metrics(cpu_usage_per_pod=0.05, cpu_request_per_pod=1.0)
    recs = analyze(wm_list, thresholds=custom)
    assert not any("Reduce CPU requests" in r.suggestions for r in recs)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_workload_metrics_returns_empty_list():
    assert analyze([]) == []


def test_to_dict_has_required_keys():
    wm_list = make_workload_metrics(cpu_usage_per_pod=1.5, cpu_request_per_pod=1.0)
    recs = analyze(wm_list)
    assert recs
    d = recs[0].to_dict()
    for key in (
        "namespace", "workload_name", "workload_kind", "replica_count", "pod_names",
        "cpu_usage_per_pod", "cpu_percentage", "memory_usage_per_pod", "memory_percentage",
        "total_cpu_usage", "total_memory_usage", "severity",
        "suggested_optimization", "reason",
    ):
        assert key in d, f"Missing key '{key}' in Recommendation.to_dict()"
