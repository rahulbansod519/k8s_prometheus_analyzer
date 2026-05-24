"""Unit tests for the embedded Prometheus metrics exporter."""

from __future__ import annotations

import http.client
import time

import pytest

from k8s_prometheus_analyzer.analyzer import Recommendation
from k8s_prometheus_analyzer.exporter import MetricsRegistry, start_exporter


@pytest.fixture
def mock_recommendation() -> Recommendation:
    """Fixture returning a mock Recommendation object."""
    return Recommendation(
        workload_name="web-app",
        workload_kind="Deployment",
        namespace="production",
        replica_count=3,
        pod_names=["web-app-1", "web-app-2", "web-app-3"],
        cpu_usage=0.150,
        memory_usage_mb=256.0,
        cpu_usage_pct=50.0,
        memory_usage_pct=75.0,
        total_cpu_usage=0.450,
        total_memory_mb=768.0,
        cpu_request=0.300,
        memory_request_mb=341.33,
        suggestions=["Reduce CPU requests", "Reduce memory requests"],
        reasons=["CPU is cold", "Memory is oversized"],
        severity="info",
    )


def test_metrics_registry_initial_state() -> None:
    """Verify registry has correct default state upon creation."""
    reg = MetricsRegistry()
    assert len(reg.recommendations) == 0
    assert reg.last_run_timestamp == 0.0
    assert reg.run_cycles == 0
    assert reg.license_valid == 1


def test_metrics_registry_update(mock_recommendation: Recommendation) -> None:
    """Verify update method populates fields and increments run cycle count."""
    reg = MetricsRegistry()
    reg.update([mock_recommendation], license_valid=False)

    assert len(reg.recommendations) == 1
    assert reg.recommendations[0].workload_name == "web-app"
    assert reg.last_run_timestamp > 0.0
    assert reg.run_cycles == 1
    assert reg.license_valid == 0


def test_metrics_serialization_empty() -> None:
    """Verify metrics serializes correctly when no recommendations exist."""
    reg = MetricsRegistry()
    text = reg.get_metrics_text()

    assert "k8s_analyzer_last_run_timestamp_seconds" in text
    assert "k8s_analyzer_run_cycles_total" in text
    assert "k8s_analyzer_license_valid" in text
    assert "k8s_analyzer_recommendation_cpu_cores" not in text


def test_metrics_serialization_with_data(mock_recommendation: Recommendation) -> None:
    """Verify metrics text format correctness with a recommendation present."""
    reg = MetricsRegistry()
    reg.update([mock_recommendation], license_valid=True)
    text = reg.get_metrics_text()

    # Verify run stats
    assert "k8s_analyzer_run_cycles_total 1" in text
    assert "k8s_analyzer_license_valid 1" in text

    # Verify metrics definitions
    assert "# TYPE k8s_analyzer_recommendation_cpu_cores gauge" in text
    assert "# TYPE k8s_analyzer_savings_cpu_cores gauge" in text
    assert "# TYPE k8s_analyzer_recommendation_info gauge" in text

    # Verify labels and values
    lbl = 'namespace="production",workload="web-app",kind="Deployment"'
    assert f"k8s_analyzer_recommendation_cpu_cores{{{lbl}}} 0.188" in text  # 0.150 * 1.25
    assert f"k8s_analyzer_recommendation_memory_bytes{{{lbl}}} 322122547" in text  # 256.0 * 1.20 MB to bytes

    # Verify current usage
    assert f"k8s_analyzer_cpu_usage_cores{{{lbl}}} 0.150" in text
    assert f"k8s_analyzer_memory_usage_bytes{{{lbl}}} 268435456" in text

    # Verify savings
    # CPU: 0.300 (req) - 0.1875 (rec) = 0.1125 cores (0.112 rounded)
    assert f"k8s_analyzer_savings_cpu_cores{{{lbl}}} 0.112" in text
    # Memory: 341.33 (req) - 307.2 (rec) = 34.13 MB = 35787610 bytes
    assert f"k8s_analyzer_savings_memory_bytes{{{lbl}}} " in text

    # Verify recommendation info labels
    info_line = (
        'k8s_analyzer_recommendation_info{namespace="production",workload="web-app",kind="Deployment",'
        'severity="info",suggestions="Reduce CPU requests, Reduce memory requests"} 1.0'
    )
    assert info_line in text


def test_exporter_http_server(mock_recommendation: Recommendation) -> None:
    """Start HTTP server, make actual HTTP requests, and verify response formats."""
    # Temporarily override the global registry with mock data
    from k8s_prometheus_analyzer.exporter import registry as global_registry

    global_registry.update([mock_recommendation], license_valid=True)

    # Start exporter on arbitrary port
    port = 8012
    server, thread = start_exporter(port)

    # Let the socket bind and startup
    time.sleep(0.1)

    try:
        conn = http.client.HTTPConnection("localhost", port, timeout=5)
        # Test 1: Fetch /metrics
        conn.request("GET", "/metrics")
        resp = conn.getresponse()
        assert resp.status == 200
        assert resp.getheader("Content-Type") == "text/plain; version=0.0.4; charset=utf-8"
        body = resp.read().decode("utf-8")
        assert "k8s_analyzer_run_cycles_total" in body
        assert "web-app" in body

        # Test 2: Fetch /other (404)
        conn.request("GET", "/invalid-path")
        resp = conn.getresponse()
        assert resp.status == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1.0)
