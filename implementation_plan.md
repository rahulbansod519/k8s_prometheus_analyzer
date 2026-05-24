# Implementation Plan: Prometheus Exporter & Grafana Dashboard Integration

This plan details the implementation of an **embedded Prometheus metrics exporter** and a **readymade Grafana dashboard** for `k8s-prometheus-analyzer`. This allows self-hosted and enterprise customers to expose right-sizing recommendations directly to their existing monitoring stack with zero dashboard overhead.

## User Review Required

> [!IMPORTANT]
> **Exporter Daemon Port**: The embedded exporter runs a lightweight HTTP server inside the daemon process. It defaults to port `8000` but is configurable via the CLI `--exporter-port` or the configuration variable `exporter_port`. 
> 
> **Zero External Dependencies**: The metrics server is built using the standard Python library (`http.server` and `threading`), ensuring no new Python packages are introduced, keeping the container image size lightweight and secure.

## Proposed Changes

### Exporter Config & Core Data Structures

#### [MODIFY] [config.py](file:///Users/rahulbansod01/Projects/k8s_prometheus_analyzer/k8s-monitor/k8s_prometheus_analyzer/config.py)
* Add `exporter_port: int = 8000` to the core `Config` dataclass.
* Add mapping support in `_apply_dict` and `_apply_env` for the config parameter `exporter_port` and env variable `K8S_ANALYZER_EXPORTER_PORT`.

#### [MODIFY] [analyzer.py](file:///Users/rahulbansod01/Projects/k8s_prometheus_analyzer/k8s-monitor/k8s_prometheus_analyzer/analyzer.py)
* Update the `Recommendation` dataclass to store the baseline configuration values:
  ```python
  cpu_request: float | None = None
  memory_request_mb: float | None = None
  ```
* Populate these properties inside the `analyze` function when creating `Recommendation` objects.

---

### Embedded Exporter Module

#### [NEW] [exporter.py](file:///Users/rahulbansod01/Projects/k8s_prometheus_analyzer/k8s-monitor/k8s_prometheus_analyzer/exporter.py)
* Create a lightweight, thread-safe metrics registry and HTTP exporter:
  * Uses `http.server.HTTPServer` and `http.server.BaseHTTPRequestHandler`.
  * Serves `/metrics` endpoint with Prometheus text exposition format.
  * Implements `MetricsRegistry` to manage state atomically:
    * `k8s_analyzer_recommendation_cpu_cores` (gauge): Recommended CPU request.
    * `k8s_analyzer_recommendation_memory_bytes` (gauge): Recommended memory request.
    * `k8s_analyzer_cpu_usage_cores` (gauge): Actual CPU usage.
    * `k8s_analyzer_memory_usage_bytes` (gauge): Actual memory usage.
    * `k8s_analyzer_savings_cpu_cores` (gauge): Core savings (current request - recommended).
    * `k8s_analyzer_savings_memory_bytes` (gauge): Memory savings in bytes (current request - recommended).
    * `k8s_analyzer_recommendation_info` (gauge): Labeled with `severity` and `suggestions` (value 1).
    * `k8s_analyzer_last_run_timestamp_seconds` (gauge): Unix timestamp of last scan.
    * `k8s_analyzer_run_cycles_total` (counter): Count of successful daemon runs.
    * `k8s_analyzer_license_valid` (gauge): 1 if valid, 0 if invalid/community-limit-exceeded.
  * Exposes `start_exporter(port: int) -> tuple[HTTPServer, threading.Thread]` to start the server in a background daemon thread.

---

### CLI Daemon Integration

#### [MODIFY] [cli.py](file:///Users/rahulbansod01/Projects/k8s_prometheus_analyzer/k8s-monitor/k8s_prometheus_analyzer/cli.py)
* Add `--exporter-port` command-line argument.
* In daemon mode (`cfg.daemon` is true):
  * Initialize the global `MetricsRegistry`.
  * Start the background HTTP exporter thread.
  * In the execution loop, after `_run_analysis_cycle()` completes, update the registry with:
    * The latest `list[Recommendation]`.
    * Increment `run_cycles_total`.
    * Update `last_run_timestamp_seconds` and `license_valid` status.
  * Register cleanup logic in the signal handler/shutdown loop to close the HTTP server socket cleanly.

---

### Grafana Dashboard & Helm Packaging

#### [NEW] [dashboard.json](file:///Users/rahulbansod01/Projects/k8s_prometheus_analyzer/grafana/dashboard.json)
* Design a premium dark-themed Grafana dashboard configuration:
  * **Summary KPI Cards**: Total CPU cores salvageable, total Memory (GiB) salvageable, total workloads optimized.
  * **Optimizations Table**: List of workloads requiring attention, including current vs recommended size, savings, severity, and remediation steps.
  * **Severity Distribution**: Pie chart or bar gauge highlighting critical, warning, and info level alerts.
  * **System Status**: Exporter uptime, run cycle counters, and last run age.

#### [NEW] [grafana-dashboard.yaml](file:///Users/rahulbansod01/Projects/k8s_prometheus_analyzer/helm/k8s-prometheus-analyzer/templates/grafana-dashboard.yaml)
* Add a Kubernetes template that outputs a ConfigMap containing the `dashboard.json` payload, annotated with the labels required by the Grafana Dashboard Sidecar (`grafana_dashboard: "1"`) for auto-import.

#### [MODIFY] [values.yaml](file:///Users/rahulbansod01/Projects/k8s_prometheus_analyzer/helm/k8s-prometheus-analyzer/values.yaml)
* Add configuration blocks:
  ```yaml
  exporter:
    port: 8000
    service:
      enabled: true
      type: ClusterIP
    serviceMonitor:
      enabled: false  # For Prometheus Operator users
  grafana:
    dashboard:
      enabled: false
      namespace: ""    # Target namespace for dashboard ConfigMap
  ```

---

## Verification Plan

### Automated Tests
* Create `tests/test_exporter.py` targeting:
  * Exporter server startup, connection binding, and teardown.
  * Validation of formatting output on GET `/metrics`.
  * Correct mathematical calculations of savings (CPU/Memory) given different baseline requests and recommendations.
  * Increment of run counters and updating of timestamp variables.

### Manual Verification
* Run the analyzer locally in daemon mode:
  ```bash
  k8s-analyze --daemon --daemon-interval 10 --exporter-port 8000
  ```
* Perform `curl http://localhost:8000/metrics` and check response metrics validity.
