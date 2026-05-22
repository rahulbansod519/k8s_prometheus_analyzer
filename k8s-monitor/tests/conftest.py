"""Shared pytest fixtures for k8s-prometheus-analyzer tests."""

from __future__ import annotations

import pytest

from k8s_prometheus_analyzer.config import Config, Thresholds
from k8s_prometheus_analyzer.workload import WorkloadKey, WorkloadMetrics

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def default_config() -> Config:
    """A Config with all defaults — no external services required."""
    return Config()


@pytest.fixture()
def strict_thresholds() -> Thresholds:
    """Very tight thresholds so most workloads trigger a recommendation."""
    return Thresholds(
        cpu_low=10.0,
        mem_low_mb=10_000.0,
        cpu_high_pct=1.0,
        mem_high_mb=1.0,
        mem_overcommit_ratio=1.01,
        replica_cpu_low=10.0,
        replica_mem_low_mb=10_000.0,
    )


# ---------------------------------------------------------------------------
# Raw Prometheus metric builders (used by test_workload.py)
# ---------------------------------------------------------------------------


def make_pod_owner_item(
    pod: str,
    namespace: str,
    owner_kind: str,
    owner_name: str,
    owner_is_controller: str = "true",
) -> dict:
    """Build a single kube_pod_owner result item."""
    return {
        "metric": {
            "pod": pod,
            "namespace": namespace,
            "owner_kind": owner_kind,
            "owner_name": owner_name,
            "owner_is_controller": owner_is_controller,
        },
        "value": [1_700_000_000, "1"],
    }


def make_rs_owner_item(
    replicaset: str,
    namespace: str,
    owner_name: str,
    owner_kind: str = "Deployment",
) -> dict:
    """Build a single kube_replicaset_owner result item."""
    return {
        "metric": {
            "replicaset": replicaset,
            "namespace": namespace,
            "owner_kind": owner_kind,
            "owner_name": owner_name,
        },
        "value": [1_700_000_000, "1"],
    }


def make_cpu_item(pod: str, namespace: str, value: float) -> dict:
    """Build a single cpu_usage result item."""
    return {
        "metric": {"pod": pod, "namespace": namespace},
        "value": [1_700_000_000, str(value)],
    }


# ---------------------------------------------------------------------------
# WorkloadMetrics builder (used by test_analyzer.py and test_cli.py)
# ---------------------------------------------------------------------------


def make_workload_metrics(
    *,
    workload_name: str = "my-deployment",
    workload_kind: str = "Deployment",
    namespace: str = "default",
    num_replicas: int = 1,
    cpu_usage_per_pod: float = 0.5,
    memory_mb_per_pod: float = 200.0,
    cpu_request_per_pod: float = 1.0,
    memory_request_mb_per_pod: float = 512.0,
) -> list[WorkloadMetrics]:
    """Return a one-element list with a pre-populated :class:`WorkloadMetrics`.

    All metrics are expressed *per pod*; totals are scaled by *num_replicas*.
    """
    pod_names = [f"{workload_name}-pod-{i}" for i in range(num_replicas)]
    n = num_replicas

    wm = WorkloadMetrics(
        key=WorkloadKey(name=workload_name, kind=workload_kind, namespace=namespace),
        pod_names=pod_names,
        total_cpu_usage=cpu_usage_per_pod * n,
        total_memory_mb=memory_mb_per_pod * n,
        total_cpu_request=cpu_request_per_pod * n,
        total_memory_request_mb=memory_request_mb_per_pod * n,
    )
    return [wm]
