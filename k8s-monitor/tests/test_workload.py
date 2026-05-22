"""Unit tests for k8s_prometheus_analyzer.workload."""

from __future__ import annotations

from k8s_prometheus_analyzer.workload import (
    WorkloadKey,
    WorkloadMetrics,
    aggregate_metrics,
    resolve_workload_map,
)

from .conftest import make_cpu_item, make_pod_owner_item, make_rs_owner_item

# ---------------------------------------------------------------------------
# resolve_workload_map — ownership resolution
# ---------------------------------------------------------------------------


class TestResolveWorkloadMap:
    def test_statefulset_direct(self):
        pod_owner = [make_pod_owner_item("redis-0", "default", "StatefulSet", "redis")]
        result = resolve_workload_map(pod_owner, [])
        assert result[("redis-0", "default")] == WorkloadKey("redis", "StatefulSet", "default")

    def test_daemonset_direct(self):
        pod_owner = [make_pod_owner_item("fluentd-abc", "kube-system", "DaemonSet", "fluentd")]
        result = resolve_workload_map(pod_owner, [])
        assert result[("fluentd-abc", "kube-system")] == WorkloadKey(
            "fluentd", "DaemonSet", "kube-system"
        )

    def test_job_direct(self):
        pod_owner = [make_pod_owner_item("migrate-xyz", "default", "Job", "db-migrate")]
        result = resolve_workload_map(pod_owner, [])
        assert result[("migrate-xyz", "default")] == WorkloadKey("db-migrate", "Job", "default")

    def test_replicaset_resolves_to_deployment(self):
        pod_owner = [make_pod_owner_item("api-abc-xyz", "default", "ReplicaSet", "api-abc")]
        rs_owner = [make_rs_owner_item("api-abc", "default", "api")]
        result = resolve_workload_map(pod_owner, rs_owner)
        assert result[("api-abc-xyz", "default")] == WorkloadKey("api", "Deployment", "default")

    def test_replicaset_without_deployment_falls_back_to_rs(self):
        """RS with no matching deploy entry → use RS directly (kind=ReplicaSet)."""
        pod_owner = [make_pod_owner_item("api-abc-xyz", "default", "ReplicaSet", "orphan-rs")]
        result = resolve_workload_map(pod_owner, [])
        wk = result[("api-abc-xyz", "default")]
        assert wk.name == "orphan-rs"
        assert wk.kind == "ReplicaSet"

    def test_unknown_owner_kind_falls_back_to_pod(self):
        pod_owner = [make_pod_owner_item("odd-pod", "default", "Node", "node-1")]
        result = resolve_workload_map(pod_owner, [])
        assert result[("odd-pod", "default")] == WorkloadKey("odd-pod", "Pod", "default")

    def test_multiple_pods_same_deployment(self):
        pod_owner = [
            make_pod_owner_item("api-abc-p1", "default", "ReplicaSet", "api-abc"),
            make_pod_owner_item("api-abc-p2", "default", "ReplicaSet", "api-abc"),
        ]
        rs_owner = [make_rs_owner_item("api-abc", "default", "api")]
        result = resolve_workload_map(pod_owner, rs_owner)
        assert result[("api-abc-p1", "default")] == WorkloadKey("api", "Deployment", "default")
        assert result[("api-abc-p2", "default")] == WorkloadKey("api", "Deployment", "default")

    def test_pods_missing_name_are_skipped(self):
        bad_item = {"metric": {"namespace": "default"}, "value": [0, "1"]}
        result = resolve_workload_map([bad_item], [])
        assert result == {}

    def test_empty_inputs_return_empty_map(self):
        assert resolve_workload_map([], []) == {}

    def test_cross_namespace_rs_not_confused(self):
        """RS with same name in different namespaces should resolve independently."""
        pod_owner = [
            make_pod_owner_item("api-abc-p1", "ns-a", "ReplicaSet", "api-abc"),
            make_pod_owner_item("api-abc-p2", "ns-b", "ReplicaSet", "api-abc"),
        ]
        rs_owner = [
            make_rs_owner_item("api-abc", "ns-a", "api-a"),
            make_rs_owner_item("api-abc", "ns-b", "api-b"),
        ]
        result = resolve_workload_map(pod_owner, rs_owner)
        assert result[("api-abc-p1", "ns-a")].name == "api-a"
        assert result[("api-abc-p2", "ns-b")].name == "api-b"


# ---------------------------------------------------------------------------
# WorkloadMetrics properties
# ---------------------------------------------------------------------------


class TestWorkloadMetrics:
    def _make(self, n: int, cpu: float, mem: float, cpu_req: float, mem_req: float):
        wm = WorkloadMetrics(
            key=WorkloadKey("test", "Deployment", "default"),
        )
        for i in range(n):
            wm.add_pod(f"pod-{i}", cpu, mem, cpu_req, mem_req)
        return wm

    def test_replica_count_equals_pod_count(self):
        wm = self._make(3, 0.1, 50, 0.5, 128)
        assert wm.replica_count == 3

    def test_cpu_usage_per_pod_average(self):
        wm = self._make(3, 0.3, 100, 1.0, 256)
        # 3 pods × 0.3 = 0.9 total, avg = 0.3
        assert abs(wm.cpu_usage_per_pod - 0.3) < 1e-9

    def test_memory_mb_per_pod_average(self):
        wm = self._make(2, 0.5, 200.0, 1.0, 512.0)
        assert abs(wm.memory_mb_per_pod - 200.0) < 1e-9

    def test_cpu_request_per_pod_none_when_zero(self):
        wm = WorkloadMetrics(key=WorkloadKey("t", "Pod", "default"))
        wm.add_pod("p", 0.1, 50, 0.0, 0.0)  # no requests set
        assert wm.cpu_request_per_pod is None

    def test_memory_request_per_pod_none_when_zero(self):
        wm = WorkloadMetrics(key=WorkloadKey("t", "Pod", "default"))
        wm.add_pod("p", 0.1, 50, 0.0, 0.0)
        assert wm.memory_request_mb_per_pod is None

    def test_empty_workload_returns_zero_for_averages(self):
        wm = WorkloadMetrics(key=WorkloadKey("t", "Pod", "default"))
        assert wm.cpu_usage_per_pod == 0.0
        assert wm.memory_mb_per_pod == 0.0
        assert wm.replica_count == 0


# ---------------------------------------------------------------------------
# aggregate_metrics
# ---------------------------------------------------------------------------


class TestAggregateMetrics:
    def _raw(self, pods: list[dict]) -> dict:
        """Build a minimal raw_metrics dict with only cpu_usage."""
        return {
            "cpu_usage": pods,
            "memory_usage": [],
            "cpu_requests": [],
            "memory_requests": [],
        }

    def test_single_pod_no_workload_map(self):
        raw = self._raw([make_cpu_item("my-pod", "default", 0.5)])
        result = aggregate_metrics(raw, {})
        assert len(result) == 1
        wm = result[0]
        assert wm.key == WorkloadKey("my-pod", "Pod", "default")
        assert abs(wm.total_cpu_usage - 0.5) < 1e-9

    def test_two_pods_same_deployment_merged(self):
        raw = self._raw([
            make_cpu_item("api-p1", "default", 0.3),
            make_cpu_item("api-p2", "default", 0.2),
        ])
        workload_map = {
            ("api-p1", "default"): WorkloadKey("api", "Deployment", "default"),
            ("api-p2", "default"): WorkloadKey("api", "Deployment", "default"),
        }
        result = aggregate_metrics(raw, workload_map)
        assert len(result) == 1
        wm = result[0]
        assert wm.key.name == "api"
        assert wm.replica_count == 2
        assert abs(wm.total_cpu_usage - 0.5) < 1e-9
        assert abs(wm.cpu_usage_per_pod - 0.25) < 1e-9

    def test_two_pods_different_workloads_not_merged(self):
        raw = self._raw([
            make_cpu_item("api-p1", "default", 0.3),
            make_cpu_item("worker-p1", "default", 0.7),
        ])
        workload_map = {
            ("api-p1", "default"): WorkloadKey("api", "Deployment", "default"),
            ("worker-p1", "default"): WorkloadKey("worker", "Deployment", "default"),
        }
        result = aggregate_metrics(raw, workload_map)
        assert len(result) == 2

    def test_pod_missing_namespace_skipped(self):
        bad_item = {"metric": {"pod": "orphan"}, "value": [0, "0.5"]}
        raw = self._raw([bad_item])
        result = aggregate_metrics(raw, {})
        assert result == []

    def test_pod_invalid_cpu_value_skipped(self):
        # Use a string that cannot be parsed by float() at all
        bad_item = {"metric": {"pod": "bad", "namespace": "default"}, "value": [0, "not-a-number"]}
        raw = self._raw([bad_item])
        result = aggregate_metrics(raw, {})
        assert result == []

    def test_memory_bytes_converted_to_mb(self):
        """Memory data is in bytes; aggregate_metrics must divide by 1024²."""
        raw = {
            "cpu_usage": [make_cpu_item("p", "default", 0.1)],
            "memory_usage": [{"metric": {"pod": "p", "namespace": "default"},
                              "value": [0, str(200 * 1024**2)]}],
            "cpu_requests": [],
            "memory_requests": [],
        }
        result = aggregate_metrics(raw, {})
        assert len(result) == 1
        assert abs(result[0].total_memory_mb - 200.0) < 1e-6

    def test_empty_raw_metrics_returns_empty_list(self):
        raw = {"cpu_usage": [], "memory_usage": [], "cpu_requests": [], "memory_requests": []}
        assert aggregate_metrics(raw, {}) == []
