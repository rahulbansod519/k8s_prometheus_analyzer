"""Tests for k8s_prometheus_analyzer.reporter.html_report."""

from __future__ import annotations

import json
import os

import pytest

from k8s_prometheus_analyzer.reporter.html_report import _build_data, export_html

from .conftest import make_workload_metrics

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROM_URL = "http://prometheus:9090"


def _critical_recs():
    from k8s_prometheus_analyzer.analyzer import analyze
    return analyze(make_workload_metrics(
        workload_name="frontend", namespace="production",
        cpu_usage_per_pod=1.5, cpu_request_per_pod=1.0,
    ))


def _warning_recs():
    from k8s_prometheus_analyzer.analyzer import analyze
    return analyze(make_workload_metrics(
        workload_name="backend", namespace="staging",
        cpu_usage_per_pod=0.3, cpu_request_per_pod=1.0,
        memory_mb_per_pod=10.0, memory_request_mb_per_pod=800.0,
    ))


def _export(tmp_path, recs, prom_url=PROM_URL):
    """Helper: export and return (path, content)."""
    out = tmp_path / "report.html"
    export_html(recs, str(out), prom_url)
    return out, out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# _build_data — data structure tests
# ---------------------------------------------------------------------------


class TestBuildData:
    def test_total_count(self):
        recs = _critical_recs() + _warning_recs()
        data = _build_data(recs, PROM_URL)
        assert data["total"] == len(recs)

    def test_severity_counts_accurate(self):
        recs = _critical_recs()  # at least 1 critical
        data = _build_data(recs, PROM_URL)
        n_critical = sum(1 for r in recs if r.severity == "critical")
        assert data["critical"] == n_critical

    def test_prometheus_url_embedded(self):
        data = _build_data([], "http://custom:9999")
        assert data["prometheus_url"] == "http://custom:9999"

    def test_generated_at_iso_format(self):
        data = _build_data([], PROM_URL)
        ts = data["generated_at"]
        assert ts.endswith("Z")
        assert "T" in ts

    def test_recommendation_fields_present(self):
        recs = _critical_recs()
        data = _build_data(recs, PROM_URL)
        assert data["recommendations"]
        rec = data["recommendations"][0]
        for key in (
            "namespace", "workload_name", "workload_kind", "replica_count",
            "pod_names", "cpu_usage", "cpu_usage_pct", "memory_usage_mb",
            "memory_usage_pct", "total_cpu_usage", "total_memory_mb",
            "severity", "suggestions", "reasons",
        ):
            assert key in rec, f"Missing key '{key}' in recommendation data"

    def test_empty_recommendations(self):
        data = _build_data([], PROM_URL)
        assert data["total"] == 0
        assert data["critical"] == 0
        assert data["warning"] == 0
        assert data["info"] == 0
        assert data["recommendations"] == []


# ---------------------------------------------------------------------------
# export_html — file output tests
# ---------------------------------------------------------------------------


class TestExportHtml:
    def test_file_is_created(self, tmp_path):
        out, _ = _export(tmp_path, [])
        assert out.exists()

    def test_file_has_html_structure(self, tmp_path):
        _, content = _export(tmp_path, [])
        assert "<!DOCTYPE html>" in content
        assert "</html>" in content

    def test_file_has_title(self, tmp_path):
        _, content = _export(tmp_path, [])
        assert "<title>" in content
        assert "k8s-prometheus-analyzer" in content

    def test_data_blob_embedded(self, tmp_path):
        recs = _critical_recs()
        _, content = _export(tmp_path, recs)
        # The workload name should appear in the embedded JSON
        assert "frontend" in content

    def test_prometheus_url_in_content(self, tmp_path):
        _, content = _export(tmp_path, [], "http://myprom:9090")
        assert "http://myprom:9090" in content

    def test_severity_counts_in_json_blob(self, tmp_path):
        recs = _critical_recs()
        _, content = _export(tmp_path, recs)
        # Find the embedded JSON
        start = content.index("const DATA = ") + len("const DATA = ")
        end = content.index(";\n\n  // ── Constants", start)
        data = json.loads(content[start:end])
        assert data["total"] == len(recs)
        assert data["critical"] >= 1

    def test_empty_recs_renders_all_clear_text(self, tmp_path):
        _, content = _export(tmp_path, [])
        assert "All Clear" in content

    def test_overwrite_existing_file(self, tmp_path):
        out = tmp_path / "report.html"
        out.write_text("old content", encoding="utf-8")
        export_html([], str(out), PROM_URL)
        assert "<!DOCTYPE html>" in out.read_text(encoding="utf-8")

    def test_atomic_write_no_partial_file(self, tmp_path, mocker):
        """If the write fails mid-way, no partial file at the destination."""
        # Patch os.replace to verify it's called (atomic rename)
        replace_called = []
        real_replace = os.replace

        def fake_replace(src, dst):
            replace_called.append((src, dst))
            real_replace(src, dst)

        mocker.patch("os.replace", side_effect=fake_replace)
        out = tmp_path / "report.html"
        export_html([], str(out), PROM_URL)
        assert replace_called, "os.replace (atomic rename) was not called"

    def test_multiple_workloads_all_embedded(self, tmp_path):
        recs = _critical_recs() + _warning_recs()
        _, content = _export(tmp_path, recs)
        assert "frontend" in content
        assert "backend" in content

    def test_html_contains_script_tag(self, tmp_path):
        _, content = _export(tmp_path, [])
        assert "<script>" in content

    def test_html_contains_style_tag(self, tmp_path):
        _, content = _export(tmp_path, [])
        assert "<style>" in content

    def test_invalid_output_path_raises_os_error(self, tmp_path):
        bad_path = str(tmp_path / "nonexistent_dir" / "report.html")
        with pytest.raises(OSError):
            export_html([], bad_path, PROM_URL)
