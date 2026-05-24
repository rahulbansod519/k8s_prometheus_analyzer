"""Pure analysis logic — no I/O, fully unit-testable.

Operates on workload-aggregated metrics (one entry per Deployment /
StatefulSet / DaemonSet / Pod) produced by
:func:`~k8s_prometheus_analyzer.workload.aggregate_metrics`.
All threshold rules fire on **per-pod averages**, so their values remain
meaningful regardless of replica count.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .config import Thresholds
from .workload import WorkloadMetrics

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity constants
# ---------------------------------------------------------------------------

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class Recommendation:
    """A workload-level optimisation recommendation.

    Metrics are expressed as **per-pod averages** so that thresholds are
    comparable across workloads with different replica counts.
    """

    # ── Workload identity (stable across redeploys) ───────────────────────
    workload_name: str   # e.g. "frontend", "redis"
    workload_kind: str   # "Deployment" | "StatefulSet" | "DaemonSet" | "Pod" | …
    namespace: str
    replica_count: int
    pod_names: list[str] = field(default_factory=list)

    # ── Per-pod average metrics (what the rules fire on) ──────────────────
    cpu_usage: float = 0.0        # cores / pod
    memory_usage_mb: float = 0.0  # MB / pod
    cpu_usage_pct: float = 0.0
    memory_usage_pct: float = 0.0

    # ── Workload aggregate totals (context for the reader) ────────────────
    total_cpu_usage: float = 0.0
    total_memory_mb: float = 0.0

    # ── Baseline configuration ────────────────────────────────────────────
    cpu_request: float | None = None
    memory_request_mb: float | None = None

    suggestions: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    severity: str = SEVERITY_INFO

    def to_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "workload_name": self.workload_name,
            "workload_kind": self.workload_kind,
            "replica_count": self.replica_count,
            "pod_names": self.pod_names,
            "cpu_usage_per_pod": f"{self.cpu_usage:.2f} cores",
            "cpu_percentage": f"{self.cpu_usage_pct:.1f}%",
            "memory_usage_per_pod": f"{self.memory_usage_mb:.2f} MB",
            "memory_percentage": f"{self.memory_usage_pct:.1f}%",
            "total_cpu_usage": f"{self.total_cpu_usage:.2f} cores",
            "total_memory_usage": f"{self.total_memory_mb:.2f} MB",
            "severity": self.severity,
            "suggested_optimization": ", ".join(self.suggestions),
            "reason": "; ".join(self.reasons),
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _determine_severity(suggestions: list[str]) -> str:
    """Derive severity from the populated suggestion list."""
    critical_keywords = {"Increase CPU requests", "Increase CPU limits or add replicas"}
    if any(s in critical_keywords for s in suggestions):
        return SEVERITY_CRITICAL
    warning_keywords = {"Increase Memory limits", "Reduce memory requests"}
    if any(s in warning_keywords for s in suggestions):
        return SEVERITY_WARNING
    return SEVERITY_INFO


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def analyze(
    workload_metrics: list[WorkloadMetrics],
    thresholds: Thresholds | None = None,
) -> list[Recommendation]:
    """Analyse workload-aggregated metrics and return optimisation recommendations.

    Args:
        workload_metrics: List produced by
            :func:`~k8s_prometheus_analyzer.workload.aggregate_metrics`.
            One entry per unique Kubernetes workload.
        thresholds: Threshold configuration.  Defaults to :class:`~k8s_prometheus_analyzer.config.Thresholds`.

    Returns:
        List of :class:`Recommendation` objects — one per actionable workload.
        Well-optimised workloads are excluded.
    """
    thr = thresholds or Thresholds()
    recommendations: list[Recommendation] = []

    for wm in workload_metrics:
        # Per-pod averages — the rules compare against these
        cpu_usage = wm.cpu_usage_per_pod
        mem_usage = wm.memory_mb_per_pod
        cpu_request = wm.cpu_request_per_pod      # None if no requests configured
        mem_request = wm.memory_request_mb_per_pod

        cpu_usage_pct = (cpu_usage / cpu_request * 100) if cpu_request else 0.0
        mem_usage_pct = (mem_usage / mem_request * 100) if mem_request else 0.0

        suggestions: list[str] = []
        reasons: list[str] = []

        # ── Rule 1: CPU over-provisioned ─────────────────────────────────────
        if cpu_request and cpu_usage < thr.cpu_low:
            suggestions.append("Reduce CPU requests")
            reasons.append(
                f"CPU usage ({cpu_usage:.2f} cores/pod) is far lower than "
                f"request ({cpu_request:.2f} cores/pod)"
            )

        # ── Rule 2: Memory over-provisioned ──────────────────────────────────
        if mem_request and mem_usage < thr.mem_low_mb:
            suggestions.append("Reduce memory requests")
            reasons.append(
                f"Memory usage ({mem_usage:.2f} MB/pod) is significantly lower than "
                f"request ({mem_request:.2f} MB/pod)"
            )

        # ── Rule 3: CPU over-utilised ─────────────────────────────────────────
        if cpu_usage_pct > thr.cpu_high_pct:
            suggestions.append("Increase CPU limits or add replicas")
            reasons.append(f"High CPU utilisation: {cpu_usage_pct:.1f}% per pod")

        # ── Rule 4: Memory over-utilised ──────────────────────────────────────
        if mem_usage > thr.mem_high_mb:
            suggestions.append("Increase Memory limits")
            reasons.append(f"Memory usage is high: {mem_usage:.2f} MB/pod")

        # ── Rule 5: CPU throttled (usage exceeds request) ─────────────────────
        if cpu_request and cpu_usage > cpu_request:
            suggestions.append("Increase CPU requests")
            reasons.append(
                f"CPU usage ({cpu_usage:.2f} cores/pod) exceeds requested "
                f"({cpu_request:.2f} cores/pod)"
            )

        # ── Rule 6: Memory overcommitment ─────────────────────────────────────
        if mem_request and mem_request > mem_usage * thr.mem_overcommit_ratio:
            if "Reduce memory requests" not in suggestions:
                suggestions.append("Reduce memory requests")
            reasons.append(
                f"Memory request ({mem_request:.2f} MB/pod) is significantly higher than "
                f"usage ({mem_usage:.2f} MB/pod)"
            )

        # ── Rule 7: Consider reducing replicas ────────────────────────────────
        if cpu_usage < thr.replica_cpu_low and mem_usage < thr.replica_mem_low_mb:
            suggestions.append("Consider reducing replicas")
            reasons.append(
                f"Workload has {wm.replica_count} replica(s) each using minimal resources"
            )

        if suggestions:
            recommendations.append(
                Recommendation(
                    workload_name=wm.key.name,
                    workload_kind=wm.key.kind,
                    namespace=wm.key.namespace,
                    replica_count=wm.replica_count,
                    pod_names=list(wm.pod_names),
                    cpu_usage=cpu_usage,
                    memory_usage_mb=mem_usage,
                    cpu_usage_pct=cpu_usage_pct,
                    memory_usage_pct=mem_usage_pct,
                    total_cpu_usage=wm.total_cpu_usage,
                    total_memory_mb=wm.total_memory_mb,
                    cpu_request=cpu_request,
                    memory_request_mb=mem_request,
                    suggestions=suggestions,
                    reasons=reasons,
                    severity=_determine_severity(suggestions),
                )
            )

    return recommendations
