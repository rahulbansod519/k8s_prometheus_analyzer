# Changelog

All notable changes to **k8s-prometheus-analyzer** are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned
- `--namespace` flag to scope analysis to a single Kubernetes namespace
- Prometheus label-selector support to filter metrics by custom labels
- GitHub Actions annotation output mode for inline PR comments
- CSV output format
- CronJob workload kind support

---

## [0.2.0] — 2026-05-23

### Highlights

Version 0.2.0 is a significant feature release that elevates `k8s-prometheus-analyzer` from a pod-level scanner to a full **workload-aware resource optimisation platform** with multi-channel alerting and a rich HTML dashboard.

### Added

#### Workload-level grouping (`workload.py`)
- **New `workload.py` module** — resolves pod-to-workload ownership using `kube_pod_owner` and `kube_replicaset_owner` Prometheus metrics exposed by kube-state-metrics
- Supports **Deployment**, **StatefulSet**, **DaemonSet**, and **Job** workload kinds
- Falls back to pod-level grouping when kube-state-metrics data is unavailable, with an explicit `WARNING` log message
- All analysis rules now operate on **per-pod averages**, keeping threshold values meaningful regardless of replica count
- `WorkloadMetrics` dataclass exposes `cpu_usage_per_pod`, `memory_mb_per_pod`, `cpu_request_per_pod`, `memory_request_mb_per_pod`, `total_cpu_usage`, `total_memory_mb`, and `replica_count`

#### Alerting subsystem (`alerting/`)
- **New `alerting/` package** with `dispatcher.py`, `slack.py`, `webhook.py`, and `base.py`
- **Slack integration** — sends a formatted Block Kit message to any Slack incoming webhook URL; supports custom `channel`, `username`, and `icon_emoji` overrides
- **Generic HTTP webhook** — POSTs (or GETs) the JSON recommendations payload to any HTTP endpoint; configurable `method`, `timeout`, and custom `headers`
- Alerts are filtered by **severity** (`critical`, `warning`, `info`) before firing — avoids alert fatigue from low-priority info suggestions
- Both channels are **independent** — configure one, both, or neither
- CLI flags `--alert-slack-url`, `--alert-webhook-url`, `--alert-on` for quick one-off runs
- Environment variables `K8S_ANALYZER_ALERTS_SLACK_WEBHOOK_URL` and `K8S_ANALYZER_ALERTS_WEBHOOK_URL` for secret management in Kubernetes

#### HTML dashboard report (`reporter/html_report.py`)
- **New `html_report.py` reporter** — generates a self-contained, single-file `k8s_report.html`
- Summary cards: total workloads scanned, critical / warning / info counts
- Interactive, sortable recommendations table with severity colour-coding (red · amber · blue)
- Pod drill-down: each row lists individual pod names
- Audit metadata: report timestamp and Prometheus URL embedded in header
- Zero external dependencies — no CDN, no JavaScript framework, opens in any browser

#### Configuration
- `alerts` section added to `config.example.yaml` with full inline documentation
- New `AlertsConfig`, `SlackConfig`, and `WebhookConfig` dataclasses in `config.py`
- `K8S_ANALYZER_ALERTS_ENABLED`, `K8S_ANALYZER_ALERTS_ON_SEVERITIES` environment variables

#### Analysis rules
- **Rule 5** — CPU throttling: flags workloads where actual CPU usage exceeds the requested amount (severity: `critical`)
- **Rule 6** — Memory overcommit: flags workloads where memory request exceeds usage by more than `mem_overcommit_ratio` × (severity: `warning`)
- **Rule 7** — Low-utilisation replica scaling: suggests replica reduction when both CPU and memory are below `replica_cpu_low` / `replica_mem_low_mb` thresholds

#### Observability
- `Recommendation.workload_kind` field — allows filtering and grouping by `Deployment`, `StatefulSet`, etc.
- `Recommendation.replica_count` and `Recommendation.pod_names` fields in JSON output
- `total_cpu_usage` and `total_memory_usage` aggregate fields added to JSON output for capacity planning

### Changed
- `analyzer.py` — analysis now operates on `WorkloadMetrics` objects (previously `PodMetrics`); all threshold comparisons use per-pod averages
- `cli.py` — main pipeline reordered: fetch → resolve workloads → aggregate → analyse → report → alert → exit
- `Recommendation.to_dict()` — extended with `workload_kind`, `replica_count`, `pod_names`, `total_cpu_usage`, `total_memory_usage`
- Exit code logic — `EXIT_CRITICAL` (`2`) is now returned only when at least one recommendation has `severity == "critical"`; previously any recommendation triggered exit `1`
- JSON output schema — `suggested_optimization` field is now a comma-joined string of all suggestions for a workload; `reason` is a semicolon-joined string of all reasons
- Default `output` filename unchanged (`optimization_suggestions.json`); HTML report is always written alongside it as `k8s_report.html`

### Fixed
- Config loading now correctly merges `alerts` subsection from YAML files (previously ignored)
- `--no-verify-ssl` flag now correctly propagates to all retry attempts via urllib3 session configuration
- Structured JSON logs no longer emit a double-encoded `message` field when using `python-json-logger`

### Testing
- Test coverage increased from ~71% to **84%**
- New test files: `test_alerting.py` (Slack, webhook, dispatcher), `test_workload.py` (ownership resolution, aggregation)
- `conftest.py` extended with workload-level fixtures and mock Prometheus responses

---

## [0.1.0] — 2026-05-01

### Highlights

Initial public release. Core analysis pipeline, JSON output, Docker support, and layered configuration.

### Added

#### Core analysis
- `fetcher.py` — `PrometheusClient` class that queries the Prometheus HTTP API for:
  - `container_cpu_usage_seconds_total` (5-minute rate)
  - `container_memory_working_set_bytes`
  - `kube_pod_container_resource_requests` (CPU and memory)
- `analyzer.py` — four threshold-based analysis rules operating on per-pod CPU and memory metrics:
  - Rule 1: CPU over-provisioned (usage < `cpu_low`)
  - Rule 2: Memory over-provisioned (usage < `mem_low_mb`)
  - Rule 3: CPU over-utilised (utilisation > `cpu_high_pct` %)
  - Rule 4: Memory over-utilised (usage > `mem_high_mb` MB/pod)
- `Recommendation` dataclass with `to_dict()` serialisation for JSON export
- Severity levels: `info`, `warning`, `critical`

#### Configuration
- `config.py` — `AppConfig` dataclass with `Thresholds` sub-config
- Layered resolution: **CLI flags → environment variables (`K8S_ANALYZER_*`) → YAML file → defaults**
- Auto-discovery of `~/.k8s-analyzer.yaml`
- `config.example.yaml` — fully documented reference config
- Authentication: `none`, `bearer` token, `basic` (username + password)
- TLS: `verify_ssl` flag, `ca_cert` custom CA bundle path
- HTTP retries: configurable `retries` count with urllib3 `Retry` on `5xx` status codes
- Logging: `log_level` (`DEBUG`/`INFO`/`WARNING`/`ERROR`), `log_format` (`text`/`json`) via `python-json-logger`

#### Output
- `reporter/table.py` — colour-coded terminal table via `tabulate`
- `reporter/json_report.py` — exports `optimization_suggestions.json`

#### CLI
- `cli.py` — `k8s-analyze` entry point built on `argparse`
- Argument groups: `connection`, `authentication`, `output`
- Exit codes: `0` (OK), `1` (warnings), `2` (critical), `3` (error)
- Inline `--help` with usage examples in the epilog

#### Infrastructure
- `Dockerfile` — multi-stage build, non-root user, minimal final image
- `pyproject.toml` — PEP 517 build config, `[dev]` optional dependencies, `ruff` and `mypy` tool config
- `setup.py` — compatibility shim for editable installs
- `exceptions.py` — `K8sAnalyzerError` and `ConfigError` base classes

#### Testing
- `tests/` — initial test suite for `config.py`, `analyzer.py`, `fetcher.py`, `cli.py`
- `conftest.py` with shared fixtures
- `pytest-cov` integration; coverage threshold set to 80%

---

[Unreleased]: https://github.com/rahulbansod519/k8s_prometheus_analyzer/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/rahulbansod519/k8s_prometheus_analyzer/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/rahulbansod519/k8s_prometheus_analyzer/releases/tag/v0.1.0
