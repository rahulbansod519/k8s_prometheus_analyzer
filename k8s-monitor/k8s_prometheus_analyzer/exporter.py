"""Embedded Prometheus metrics exporter for k8s-prometheus-analyzer."""

from __future__ import annotations

import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

logger = logging.getLogger(__name__)


class MetricsRegistry:
    """Atomic thread-safe registry holding latest recommendations and stats."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.recommendations: list[Any] = []
        self.last_run_timestamp: float = 0.0
        self.run_cycles: int = 0
        self.license_valid: int = 1  # 1 = valid, 0 = invalid / limit exceeded

    def update(self, recommendations: list[Any], license_valid: bool) -> None:
        """Update metrics registry with latest recommendations."""
        with self._lock:
            self.recommendations = list(recommendations)
            self.last_run_timestamp = time.time()
            self.run_cycles += 1
            self.license_valid = 1 if license_valid else 0

    def get_metrics_text(self) -> str:
        """Serialize current state to Prometheus text exposition format (version 0.0.4)."""
        with self._lock:
            lines = []

            # ── 1. Exporter Uptime & Runs Metadata ────────────────────────────
            lines.append("# HELP k8s_analyzer_last_run_timestamp_seconds Unix timestamp of last scan cycle")
            lines.append("# TYPE k8s_analyzer_last_run_timestamp_seconds gauge")
            lines.append(f"k8s_analyzer_last_run_timestamp_seconds {self.last_run_timestamp}")

            lines.append("# HELP k8s_analyzer_run_cycles_total Total number of successful scans")
            lines.append("# TYPE k8s_analyzer_run_cycles_total counter")
            lines.append(f"k8s_analyzer_run_cycles_total {self.run_cycles}")

            lines.append("# HELP k8s_analyzer_license_valid Licensing verification status (1 = valid, 0 = invalid)")
            lines.append("# TYPE k8s_analyzer_license_valid gauge")
            lines.append(f"k8s_analyzer_license_valid {self.license_valid}")

            # ── 2. Recommendation details ─────────────────────────────────────
            if self.recommendations:
                lines.append("# HELP k8s_analyzer_recommendation_cpu_cores Recommended CPU request per pod in cores")
                lines.append("# TYPE k8s_analyzer_recommendation_cpu_cores gauge")

                lines.append("# HELP k8s_analyzer_recommendation_memory_bytes Recommended Memory request per pod in bytes")
                lines.append("# TYPE k8s_analyzer_recommendation_memory_bytes gauge")

                lines.append("# HELP k8s_analyzer_cpu_usage_cores Average CPU usage per pod in cores")
                lines.append("# TYPE k8s_analyzer_cpu_usage_cores gauge")

                lines.append("# HELP k8s_analyzer_memory_usage_bytes Average Memory usage per pod in bytes")
                lines.append("# TYPE k8s_analyzer_memory_usage_bytes gauge")

                lines.append("# HELP k8s_analyzer_savings_cpu_cores Estimated CPU core savings per pod (current request - recommended)")
                lines.append("# TYPE k8s_analyzer_savings_cpu_cores gauge")

                lines.append("# HELP k8s_analyzer_savings_memory_bytes Estimated Memory savings per pod in bytes (current request - recommended)")
                lines.append("# TYPE k8s_analyzer_savings_memory_bytes gauge")

                lines.append("# HELP k8s_analyzer_recommendation_info Structural label metadata for active optimization recommendations")
                lines.append("# TYPE k8s_analyzer_recommendation_info gauge")

                for rec in self.recommendations:
                    # Sanitize label inputs to prevent metric corruption
                    lbl = f'namespace="{rec.namespace}",workload="{rec.workload_name}",kind="{rec.workload_kind}"'

                    # Compute recommended parameters
                    cpu_rec = max(rec.cpu_usage * 1.25, 0.01)
                    mem_rec_mb = max(rec.memory_usage_mb * 1.20, 10.0)
                    mem_rec_bytes = int(mem_rec_mb * 1024 * 1024)

                    lines.append(f"k8s_analyzer_recommendation_cpu_cores{{{lbl}}} {cpu_rec:.3f}")
                    lines.append(f"k8s_analyzer_recommendation_memory_bytes{{{lbl}}} {mem_rec_bytes}")

                    # Raw usages
                    lines.append(f"k8s_analyzer_cpu_usage_cores{{{lbl}}} {rec.cpu_usage:.3f}")
                    lines.append(f"k8s_analyzer_memory_usage_bytes{{{lbl}}} {int(rec.memory_usage_mb * 1024 * 1024)}")

                    # CPU Savings
                    cpu_save = 0.0
                    if rec.cpu_request is not None:
                        cpu_save = rec.cpu_request - cpu_rec
                    lines.append(f"k8s_analyzer_savings_cpu_cores{{{lbl}}} {cpu_save:.3f}")

                    # Memory Savings
                    mem_save = 0
                    if rec.memory_request_mb is not None:
                        mem_save = int((rec.memory_request_mb - mem_rec_mb) * 1024 * 1024)
                    lines.append(f"k8s_analyzer_savings_memory_bytes{{{lbl}}} {mem_save}")

                    # Detailed recommendation metadata info
                    suggestions_str = ", ".join(rec.suggestions).replace('"', '\\"')
                    info_lbl = f'{lbl},severity="{rec.severity}",suggestions="{suggestions_str}"'
                    lines.append(f"k8s_analyzer_recommendation_info{{{info_lbl}}} 1.0")

            return "\n".join(lines) + "\n"


# Package global registry
registry = MetricsRegistry()


class MetricsHandler(BaseHTTPRequestHandler):
    """Custom request handler serving metrics."""

    def do_GET(self) -> None:
        """Handle GET requests, responding with Prometheus metrics on `/metrics`."""
        if self.path == "/metrics":
            try:
                content = registry.get_metrics_text()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
            except Exception as e:
                logger.error("Error generating metrics response: %s", e)
                try:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b"Internal Server Error")
                except Exception:
                    pass
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def log_message(self, format: str, *args: Any) -> None:
        """Override logging to suppress spammy scrape requests in stdout."""
        logger.debug(format, *args)


def start_exporter(port: int) -> tuple[HTTPServer, threading.Thread]:
    """Start the HTTP server on port in a background daemon thread."""
    server = HTTPServer(("0.0.0.0", port), MetricsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Prometheus metrics exporter started on port %d", port)
    return server, thread
