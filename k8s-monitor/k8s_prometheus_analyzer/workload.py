"""Kubernetes workload resolution and metric aggregation.

Resolves raw pod names to their stable owner workload
(Deployment / StatefulSet / DaemonSet / Job / standalone Pod) by
consuming two Prometheus metric families:

* ``kube_pod_owner``        — pod → direct owner (ReplicaSet, StatefulSet, …)
* ``kube_replicaset_owner`` — ReplicaSet → Deployment (the second hop for Deployments)

Pods whose owner chain cannot be resolved fall back gracefully to a
"Pod" kind workload, so output is always produced even when
kube-state-metrics is not scraped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class WorkloadKey(NamedTuple):
    """Immutable, hashable identity for a Kubernetes workload."""

    name: str       # e.g. "frontend", "redis-0" (pod name for standalone pods)
    kind: str       # "Deployment" | "StatefulSet" | "DaemonSet" | "Job" | "Pod"
    namespace: str


@dataclass
class WorkloadMetrics:
    """Pod metrics accumulated (summed) at the workload level.

    Instantiate once per workload and call ``add_pod()`` for each pod.
    """

    key: WorkloadKey
    pod_names: list[str] = field(default_factory=list)

    total_cpu_usage: float = 0.0          # cores (sum across all pods)
    total_memory_mb: float = 0.0          # megabytes
    total_cpu_request: float = 0.0        # cores
    total_memory_request_mb: float = 0.0  # megabytes

    # ------------------------------------------------------------------
    # Computed properties (per-pod averages — used by analysis rules)
    # ------------------------------------------------------------------

    @property
    def replica_count(self) -> int:
        """Number of pods contributing to this workload's metrics."""
        return len(self.pod_names)

    @property
    def cpu_usage_per_pod(self) -> float:
        """Average CPU usage per pod in cores."""
        return self.total_cpu_usage / self.replica_count if self.replica_count else 0.0

    @property
    def memory_mb_per_pod(self) -> float:
        """Average memory usage per pod in MB."""
        return self.total_memory_mb / self.replica_count if self.replica_count else 0.0

    @property
    def cpu_request_per_pod(self) -> float | None:
        """Average CPU request per pod, or ``None`` if no requests are set."""
        if not self.replica_count or self.total_cpu_request == 0.0:
            return None
        return self.total_cpu_request / self.replica_count

    @property
    def memory_request_mb_per_pod(self) -> float | None:
        """Average memory request per pod in MB, or ``None`` if not set."""
        if not self.replica_count or self.total_memory_request_mb == 0.0:
            return None
        return self.total_memory_request_mb / self.replica_count

    def add_pod(
        self,
        pod_name: str,
        cpu_usage: float,
        memory_mb: float,
        cpu_request: float,
        memory_request_mb: float,
    ) -> None:
        """Accumulate a single pod's metrics into this workload."""
        self.pod_names.append(pod_name)
        self.total_cpu_usage += cpu_usage
        self.total_memory_mb += memory_mb
        self.total_cpu_request += cpu_request
        self.total_memory_request_mb += memory_request_mb


# ---------------------------------------------------------------------------
# Workload resolution
# ---------------------------------------------------------------------------


def resolve_workload_map(
    pod_owner_data: list[dict[str, Any]],
    rs_owner_data: list[dict[str, Any]],
) -> dict[tuple[str, str], WorkloadKey]:
    """Map ``(pod_name, namespace)`` → :class:`WorkloadKey`.

    Resolution strategy:

    1. ``kube_pod_owner`` gives the *direct* owner.
    2. If the direct owner is a ``ReplicaSet``, look up
       ``kube_replicaset_owner`` to find the parent ``Deployment``.
    3. ``StatefulSet``, ``DaemonSet``, ``Job``, ``CronJob`` are used directly.
    4. Anything else (``Node``, unknown) → treat pod as a standalone ``Pod``.

    Args:
        pod_owner_data: Results of ``kube_pod_owner{owner_is_controller="true"}``.
        rs_owner_data:  Results of ``kube_replicaset_owner{owner_kind="Deployment"}``.

    Returns:
        Mapping of ``(pod_name, namespace)`` to the resolved :class:`WorkloadKey`.
        Pods whose owner cannot be determined are omitted — callers fall back
        to a ``Pod``-kind workload for those.
    """
    # ── Step 1: Build ReplicaSet → Deployment index ──────────────────────────
    # (replicaset, namespace) → (deployment_name, namespace)
    rs_to_deploy: dict[tuple[str, str], tuple[str, str]] = {}
    for item in rs_owner_data:
        m = item.get("metric", {})
        rs_name = m.get("replicaset")
        ns = m.get("namespace")
        owner_name = m.get("owner_name")
        owner_kind = m.get("owner_kind")
        if rs_name and ns and owner_name and owner_kind == "Deployment":
            rs_to_deploy[(rs_name, ns)] = (owner_name, ns)

    # ── Step 2: Resolve each pod ──────────────────────────────────────────────
    _DIRECT_KINDS = {"StatefulSet", "DaemonSet", "Job", "CronJob"}
    workload_map: dict[tuple[str, str], WorkloadKey] = {}

    for item in pod_owner_data:
        m = item.get("metric", {})
        pod = m.get("pod")
        ns = m.get("namespace")
        owner_kind = m.get("owner_kind", "")
        owner_name = m.get("owner_name", "")

        if not pod or not ns:
            continue

        if owner_kind == "ReplicaSet" and owner_name:
            deploy_info = rs_to_deploy.get((owner_name, ns))
            if deploy_info:
                workload_map[(pod, ns)] = WorkloadKey(
                    name=deploy_info[0], kind="Deployment", namespace=ns
                )
            else:
                # RS not in deploy index — use RS directly (e.g. standalone RS)
                logger.debug(
                    "Pod %s/%s owned by RS %s with no parent Deployment",
                    ns, pod, owner_name,
                )
                workload_map[(pod, ns)] = WorkloadKey(
                    name=owner_name, kind="ReplicaSet", namespace=ns
                )
        elif owner_kind in _DIRECT_KINDS and owner_name:
            workload_map[(pod, ns)] = WorkloadKey(
                name=owner_name, kind=owner_kind, namespace=ns
            )
        else:
            # Standalone pod or unrecognised owner — pod is its own workload
            workload_map[(pod, ns)] = WorkloadKey(name=pod, kind="Pod", namespace=ns)

    return workload_map


# ---------------------------------------------------------------------------
# Metric aggregation
# ---------------------------------------------------------------------------


def _pod_value_index(
    data: list[dict[str, Any]], scale: float = 1.0
) -> dict[tuple[str, str], float]:
    """Build a ``(pod, namespace) → value`` lookup from Prometheus results."""
    index: dict[tuple[str, str], float] = {}
    for item in data:
        pod = item.get("metric", {}).get("pod")
        ns = item.get("metric", {}).get("namespace")
        if not pod or not ns:
            continue
        try:
            index[(pod, ns)] = float(item["value"][1]) / scale
        except (KeyError, ValueError, TypeError):
            pass
    return index


def aggregate_metrics(
    raw_metrics: dict[str, list[dict[str, Any]]],
    workload_map: dict[tuple[str, str], WorkloadKey],
) -> list[WorkloadMetrics]:
    """Aggregate pod-level Prometheus metrics to workload level.

    Pods not present in *workload_map* are treated as standalone ``Pod``
    workloads — this is the graceful-degradation path when
    ``kube_pod_owner`` data is unavailable.

    Args:
        raw_metrics:  Dict produced by
            :meth:`~k8s_prometheus_analyzer.fetcher.PrometheusClient.query_all`
            (without the ``pod_owner`` / ``rs_owner`` keys, which the caller
            has already popped).
        workload_map: Output of :func:`resolve_workload_map`.

    Returns:
        One :class:`WorkloadMetrics` object per unique workload.
    """
    mem_mb = _pod_value_index(raw_metrics.get("memory_usage", []), scale=1024**2)
    cpu_req = _pod_value_index(raw_metrics.get("cpu_requests", []))
    mem_req = _pod_value_index(raw_metrics.get("memory_requests", []), scale=1024**2)

    workloads: dict[WorkloadKey, WorkloadMetrics] = {}

    for item in raw_metrics.get("cpu_usage", []):
        m = item.get("metric", {})
        pod = m.get("pod")
        ns = m.get("namespace")
        if not pod or not ns:
            continue

        try:
            cpu_usage = float(item["value"][1])
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Skipping pod %s/%s — invalid CPU data: %s", ns, pod, exc)
            continue

        pod_key = (pod, ns)
        wk = workload_map.get(pod_key) or WorkloadKey(name=pod, kind="Pod", namespace=ns)

        if wk not in workloads:
            workloads[wk] = WorkloadMetrics(key=wk)

        workloads[wk].add_pod(
            pod_name=pod,
            cpu_usage=cpu_usage,
            memory_mb=mem_mb.get(pod_key, 0.0),
            cpu_request=cpu_req.get(pod_key, 0.0),
            memory_request_mb=mem_req.get(pod_key, 0.0),
        )

    return list(workloads.values())
