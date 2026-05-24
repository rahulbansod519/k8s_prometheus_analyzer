# k8s-prometheus-analyzer

[![PyPI version](https://img.shields.io/pypi/v/k8s-prometheus-analyzer?color=blue&logo=pypi&logoColor=white)](https://pypi.org/project/k8s-prometheus-analyzer/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://github.com/rahulbansod519/k8s_prometheus_analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/rahulbansod519/k8s_prometheus_analyzer/actions)
[![Coverage: 84%](https://img.shields.io/badge/coverage-84%25-brightgreen)](https://github.com/rahulbansod519/k8s_prometheus_analyzer)

> **Spot Kubernetes resource waste in seconds — straight from your Prometheus.**

`k8s-prometheus-analyzer` is a zero-dependency-on-kubectl Python CLI tool that queries Prometheus for live Kubernetes resource metrics, groups them by workload (Deployment, StatefulSet, DaemonSet, Job), applies configurable threshold rules, and delivers actionable optimization recommendations in a colour-coded terminal table, a machine-readable JSON file, and a rich HTML dashboard — with optional Slack and webhook alerts.

---

## 📸 HTML Dashboard Preview

The generated HTML report (`k8s_report.html`) is a self-contained, single-file dashboard that opens in any browser with no server required. It includes:

- **Summary cards** — total workloads scanned, critical / warning / info counts at a glance
- **Interactive table** — sortable columns for namespace, workload name, kind, replica count, CPU & memory usage per pod, utilisation percentages, severity badge, and recommendations
- **Severity colour-coding** — 🔴 critical · 🟡 warning · 🔵 info rows highlighted for fast triage
- **Pod drill-down** — expand any workload row to see individual pod names and their resource contributions
- **Timestamp & Prometheus URL** — recorded at report generation time for audit trails

---

## ✨ Features

- 🔍 **Workload-aware grouping** — aggregates pod metrics up to Deployment, StatefulSet, DaemonSet, or Job level via `kube-state-metrics` owner references; falls back to pod-level gracefully
- 📊 **Seven analysis rules** — over-provisioned CPU/memory, under-provisioned CPU/memory, CPU throttling, memory overcommit, and low-utilisation replica scaling
- ⚙️ **Fully configurable thresholds** — tune every rule to match your cluster's SLO targets without touching source code
- 🖥️ **Terminal table output** — colour-coded, human-readable summary printed to stdout after every run
- 📄 **JSON output** — machine-readable `optimization_suggestions.json` for CI pipelines, GitOps workflows, and downstream tooling
- 🌐 **HTML dashboard report** — self-contained, browser-ready report with no external dependencies
- 🔔 **Slack alerts** — sends a formatted message to any Slack incoming webhook when issues are found
- 🪝 **Generic HTTP webhook** — compatible with PagerDuty, Microsoft Teams, Opsgenie, or any custom endpoint
- 🔐 **Flexible authentication** — `none`, `bearer` token, or `basic` auth for secured Prometheus endpoints
- 🔒 **TLS support** — custom CA bundles, optional verification disable for dev/test environments
- 🔄 **Automatic retries** — exponential backoff on transient `5xx` errors
- 📝 **Structured logging** — `text` or `json` log format, configurable verbosity (`DEBUG`→`ERROR`)
- 🏗️ **Layered configuration** — CLI flags → environment variables (`K8S_ANALYZER_*`) → YAML file → sane defaults
- 🚦 **Meaningful exit codes** — integrate directly into CI/CD gates without parsing output
- 🐳 **Docker-ready** — official `Dockerfile` included; runs as non-root

---

## ⚡ Quick Start

```bash
# 1. Install
pip install k8s-prometheus-analyzer

# 2. Point at your Prometheus (port-forward if needed)
kubectl port-forward svc/prometheus-operated 9090:9090 -n monitoring

# 3. Run
k8s-analyze --prometheus-url http://localhost:9090
```

That's it. A colour-coded table appears in your terminal, `optimization_suggestions.json` is written to the current directory, and `k8s_report.html` opens in your default browser.

---

## 📦 Installation

### pip (recommended)

```bash
pip install k8s-prometheus-analyzer
```

Requires **Python 3.10+**. The package installs the `k8s-analyze` command globally (or within your active virtual environment).

### Docker

```bash
# Pull and run — mount a directory to retrieve output files
docker run --rm \
  -e K8S_ANALYZER_PROMETHEUS_URL=http://prometheus:9090 \
  -v "$(pwd)/output:/output" \
  ghcr.io/rahulbansod519/k8s-prometheus-analyzer:latest \
  --output /output/suggestions.json
```

### From source

```bash
git clone https://github.com/rahulbansod519/k8s_prometheus_analyzer.git
cd k8s_prometheus_analyzer/k8s-monitor

# Editable install (changes to source are reflected immediately)
pip install -e .

# With dev dependencies (pytest, ruff, mypy, etc.)
pip install -e '.[dev]'
```

---

## 🚀 Usage Examples

### Basic analysis against a local Prometheus

```bash
k8s-analyze --prometheus-url http://localhost:9090
```

### Use a YAML config file

```bash
k8s-analyze --config ~/.k8s-analyzer.yaml
```

### Bearer-token auth (e.g. Prometheus behind an Ingress with OAuth proxy)

```bash
k8s-analyze \
  --prometheus-url https://prometheus.example.com \
  --auth-type bearer \
  --token "$PROMETHEUS_TOKEN"
```

### Basic auth

```bash
k8s-analyze \
  --prometheus-url https://prometheus.internal \
  --auth-type basic \
  --username admin \
  --password "$PROM_PASSWORD"
```

### Custom CA certificate (self-signed or private PKI)

```bash
k8s-analyze \
  --prometheus-url https://prom.corp.internal \
  --ca-cert /etc/ssl/certs/corp-ca-bundle.pem
```

### Disable TLS verification (dev / test only — never in production)

```bash
k8s-analyze --prometheus-url https://prom.local --no-verify-ssl
```

### JSON structured logging — ideal for CI pipelines and log aggregators

```bash
k8s-analyze \
  --prometheus-url http://localhost:9090 \
  --log-format json \
  --log-level DEBUG
```

### Custom output file path

```bash
k8s-analyze \
  --prometheus-url http://localhost:9090 \
  --output /tmp/k8s-report/suggestions.json
```

### Send Slack alert when issues are found

```bash
k8s-analyze \
  --prometheus-url http://localhost:9090 \
  --alert-slack-url "https://hooks.slack.com/services/T.../B.../.." \
  --alert-on critical \
  --alert-on warning
```

### Send to a generic HTTP webhook (e.g. PagerDuty, Teams, Opsgenie)

```bash
k8s-analyze \
  --prometheus-url http://localhost:9090 \
  --alert-webhook-url "https://events.pagerduty.com/v2/enqueue"
```

### Use in a CI/CD gate (non-zero exit on critical issues)

```bash
k8s-analyze --prometheus-url http://prom.ci:9090 || {
  echo "Critical Kubernetes resource issues detected — blocking deployment"
  exit 1
}
```

---

## ⚙️ Configuration Reference

All flags, environment variables, and YAML keys share the same names and precedence:
**CLI flags** override **environment variables**, which override **YAML file** values, which override **built-in defaults**.

### Connection

| CLI Flag | Env Variable | YAML Key | Default | Description |
|---|---|---|---|---|
| `--prometheus-url` | `K8S_ANALYZER_PROMETHEUS_URL` | `prometheus_url` | `http://localhost:9090` | Prometheus base URL |
| `--timeout` | `K8S_ANALYZER_TIMEOUT` | `timeout` | `10` | HTTP request timeout (seconds) |
| `--retries` | `K8S_ANALYZER_RETRIES` | `retries` | `3` | Retries on transient `5xx` errors |

### Authentication

| CLI Flag | Env Variable | YAML Key | Default | Description |
|---|---|---|---|---|
| `--auth-type` | `K8S_ANALYZER_AUTH_TYPE` | `auth_type` | `none` | Auth method: `none` · `bearer` · `basic` |
| `--token` | `K8S_ANALYZER_TOKEN` | `token` | _(empty)_ | Bearer token value |
| `--username` | `K8S_ANALYZER_USERNAME` | `username` | _(empty)_ | Basic-auth username |
| `--password` | `K8S_ANALYZER_PASSWORD` | `password` | _(empty)_ | Basic-auth password |
| `--ca-cert` | `K8S_ANALYZER_CA_CERT` | `ca_cert` | _(empty)_ | Path to a CA bundle file |
| `--no-verify-ssl` | `K8S_ANALYZER_NO_VERIFY_SSL` | `verify_ssl: false` | `true` (verify) | Disable TLS verification |

### Output & Logging

| CLI Flag | Env Variable | YAML Key | Default | Description |
|---|---|---|---|---|
| `--output` | `K8S_ANALYZER_OUTPUT` | `output` | `optimization_suggestions.json` | JSON output file path |
| `--log-level` | `K8S_ANALYZER_LOG_LEVEL` | `log_level` | `INFO` | `DEBUG` · `INFO` · `WARNING` · `ERROR` |
| `--log-format` | `K8S_ANALYZER_LOG_FORMAT` | `log_format` | `text` | `text` · `json` |
| `--config` | _(n/a)_ | _(n/a)_ | `~/.k8s-analyzer.yaml` | Path to YAML config file |

### Analysis Thresholds

| YAML Key | Default | Description |
|---|---|---|
| `thresholds.cpu_low` | `0.1` | CPU cores/pod below which requests are over-provisioned |
| `thresholds.mem_low_mb` | `50.0` | Memory MB/pod below which requests are over-provisioned |
| `thresholds.cpu_high_pct` | `80.0` | CPU utilisation % above which scaling is recommended |
| `thresholds.mem_high_mb` | `500.0` | Memory MB/pod above which limits should be reviewed |
| `thresholds.mem_overcommit_ratio` | `3.0` | Request/usage ratio above which overcommit is flagged |
| `thresholds.replica_cpu_low` | `0.05` | CPU threshold for "consider reducing replicas" suggestion |
| `thresholds.replica_mem_low_mb` | `20.0` | Memory threshold for "consider reducing replicas" suggestion |

### Alerting

| CLI Flag | Env Variable | YAML Key | Default | Description |
|---|---|---|---|---|
| `--alert-slack-url` | `K8S_ANALYZER_ALERTS_SLACK_WEBHOOK_URL` | `alerts.slack.webhook_url` | _(empty)_ | Slack incoming webhook URL |
| `--alert-webhook-url` | `K8S_ANALYZER_ALERTS_WEBHOOK_URL` | `alerts.webhook.url` | _(empty)_ | Generic HTTP webhook URL |
| `--alert-on` | `K8S_ANALYZER_ALERTS_ON_SEVERITIES` | `alerts.on_severities` | `critical warning` | Severities that trigger alerts (repeatable) |

---

## 📋 Config File Reference

Copy `config.example.yaml` from the repository and save it to `~/.k8s-analyzer.yaml` (auto-discovered) or pass it with `--config`:

```yaml
# ~/.k8s-analyzer.yaml
# Priority: CLI flags → env vars (K8S_ANALYZER_*) → this file → defaults

# ── Prometheus connection ────────────────────────────────────────────────────
prometheus_url: "http://localhost:9090"

# Authentication: "none" | "bearer" | "basic"
auth_type: "none"
token: ""           # Bearer token (auth_type: bearer)
username: ""        # Basic auth user (auth_type: basic)
password: ""        # Basic auth password

# TLS
verify_ssl: true
ca_cert: ""         # /path/to/ca-bundle.pem

# ── HTTP client ──────────────────────────────────────────────────────────────
timeout: 10         # seconds
retries: 3

# ── Output ───────────────────────────────────────────────────────────────────
output: "optimization_suggestions.json"

# ── Logging ──────────────────────────────────────────────────────────────────
log_level: "INFO"   # DEBUG | INFO | WARNING | ERROR
log_format: "text"  # text | json

# ── Analysis thresholds ───────────────────────────────────────────────────────
thresholds:
  cpu_low: 0.1              # over-provisioned if usage < this (cores/pod)
  mem_low_mb: 50.0          # over-provisioned if usage < this (MB/pod)
  cpu_high_pct: 80.0        # scale out if utilisation > this %
  mem_high_mb: 500.0        # review limits if usage > this MB/pod
  mem_overcommit_ratio: 3.0 # flag if request > usage × this ratio
  replica_cpu_low: 0.05     # scale-in candidate: CPU (cores/pod)
  replica_mem_low_mb: 20.0  # scale-in candidate: memory (MB/pod)

# ── Alerting ─────────────────────────────────────────────────────────────────
alerts:
  enabled: true
  on_severities:
    - critical
    - warning

  slack:
    enabled: true
    webhook_url: "https://hooks.slack.com/services/T.../B.../.."
    channel: "#k8s-alerts"      # overrides webhook default channel
    username: "k8s-analyzer"
    icon_emoji: ":kubernetes:"

  webhook:
    enabled: false
    url: "https://your-endpoint.example.com/alerts"
    method: "POST"
    timeout: 10
    headers:
      Authorization: "Bearer my-api-key"
      X-Source: "k8s-analyzer"
```

---

## 🌍 Environment Variables

All environment variables are prefixed with `K8S_ANALYZER_`. They are useful for secrets management in Kubernetes (via `Secret` → `envFrom`) and CI/CD pipelines.

| Variable | Equivalent Flag | Description |
|---|---|---|
| `K8S_ANALYZER_PROMETHEUS_URL` | `--prometheus-url` | Prometheus base URL |
| `K8S_ANALYZER_AUTH_TYPE` | `--auth-type` | `none` · `bearer` · `basic` |
| `K8S_ANALYZER_TOKEN` | `--token` | Bearer token |
| `K8S_ANALYZER_USERNAME` | `--username` | Basic-auth username |
| `K8S_ANALYZER_PASSWORD` | `--password` | Basic-auth password |
| `K8S_ANALYZER_CA_CERT` | `--ca-cert` | Path to CA bundle |
| `K8S_ANALYZER_NO_VERIFY_SSL` | `--no-verify-ssl` | `true` to disable TLS verification |
| `K8S_ANALYZER_TIMEOUT` | `--timeout` | Request timeout in seconds |
| `K8S_ANALYZER_RETRIES` | `--retries` | Retry count for transient errors |
| `K8S_ANALYZER_OUTPUT` | `--output` | JSON output file path |
| `K8S_ANALYZER_LOG_LEVEL` | `--log-level` | Logging verbosity |
| `K8S_ANALYZER_LOG_FORMAT` | `--log-format` | `text` or `json` |
| `K8S_ANALYZER_ALERTS_ENABLED` | _(n/a)_ | `true` to enable alerting subsystem |
| `K8S_ANALYZER_ALERTS_SLACK_WEBHOOK_URL` | `--alert-slack-url` | Slack webhook URL |
| `K8S_ANALYZER_ALERTS_WEBHOOK_URL` | `--alert-webhook-url` | Generic webhook URL |
| `K8S_ANALYZER_ALERTS_ON_SEVERITIES` | `--alert-on` | Comma-separated severities |

### Example — Kubernetes Secret + Pod env

```yaml
# secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: k8s-analyzer-secrets
stringData:
  prometheus-token: "eyJhbGci..."
  slack-webhook: "https://hooks.slack.com/..."
---
# cronjob.yaml (run analysis every hour)
env:
  - name: K8S_ANALYZER_PROMETHEUS_URL
    value: "https://prometheus.monitoring.svc.cluster.local:9090"
  - name: K8S_ANALYZER_AUTH_TYPE
    value: "bearer"
  - name: K8S_ANALYZER_TOKEN
    valueFrom:
      secretKeyRef:
        name: k8s-analyzer-secrets
        key: prometheus-token
  - name: K8S_ANALYZER_ALERTS_SLACK_WEBHOOK_URL
    valueFrom:
      secretKeyRef:
        name: k8s-analyzer-secrets
        key: slack-webhook
```

---

## 🔔 Alert Configuration

### Slack

Alerts fire after analysis completes when at least one recommendation matches a severity in `on_severities`. The Slack message includes:

- 🔴 Total critical / 🟡 warning / 🔵 info counts
- A table listing affected workloads, namespaces, and recommendations
- A footer with the Prometheus URL and timestamp

```bash
# One-liner — no config file needed
k8s-analyze \
  --prometheus-url http://localhost:9090 \
  --alert-slack-url "https://hooks.slack.com/services/T.../B.../.." \
  --alert-on critical
```

### Generic HTTP Webhook

The webhook body is a JSON object with the same schema as the JSON output file. This makes it directly compatible with:

| Platform | Endpoint |
|---|---|
| **PagerDuty** | `https://events.pagerduty.com/v2/enqueue` |
| **Microsoft Teams** | Incoming webhook connector URL |
| **Opsgenie** | `https://api.opsgenie.com/v2/alerts` |
| **Custom SIEM** | Any HTTP endpoint that accepts JSON |

```yaml
# config.yaml
alerts:
  webhook:
    enabled: true
    url: "https://events.pagerduty.com/v2/enqueue"
    method: "POST"
    headers:
      Authorization: "Token token=YOUR_PAGERDUTY_INTEGRATION_KEY"
```

---

## 🌐 HTML Report

The HTML report is generated alongside the JSON file and saved as `k8s_report.html` in the current working directory (or the same directory as `--output`). It is a **self-contained single file** — no CDN calls, no JavaScript frameworks, no server required.

### What's inside

| Section | Description |
|---|---|
| **Header** | Tool name, Prometheus URL, report generation timestamp |
| **Summary cards** | Total workloads, critical / warning / info counts |
| **Recommendations table** | Namespace, workload, kind, replicas, CPU/memory metrics, severity badge, suggestions |
| **Severity colour coding** | Critical = red, Warning = amber, Info = blue row highlights |
| **Pod names** | Each row expandable to show individual pod names |
| **Empty state** | Friendly message when all workloads are well-configured |

### Opening the report

```bash
# macOS
open k8s_report.html

# Linux
xdg-open k8s_report.html

# Or just drag-and-drop into any browser
```

---

## 🚦 Exit Codes

Use exit codes to drive CI/CD gates and alerting pipelines without parsing output.

| Code | Meaning | When |
|---|---|---|
| `0` | **OK** | No recommendations — all workloads are well-configured |
| `1` | **Warnings** | At least one INFO or WARNING recommendation exists |
| `2` | **Critical** | At least one CRITICAL recommendation exists (CPU throttling / resource exhaustion) |
| `3` | **Error** | Tool error — Prometheus unreachable, invalid config, unexpected exception |

```bash
k8s-analyze --prometheus-url http://prom:9090
EXIT=$?

case $EXIT in
  0) echo "✅ All good";;
  1) echo "⚠️  Optimisation suggestions available — review k8s_report.html";;
  2) echo "🚨 Critical issues detected — blocking pipeline"; exit 1;;
  3) echo "💥 Tool error — check Prometheus connectivity"; exit 1;;
esac
```

---

## 📋 Requirements

### Python dependencies

| Package | Version | Purpose |
|---|---|---|
| `requests` | ≥ 2.31 | HTTP client for Prometheus API |
| `tabulate` | ≥ 0.9 | Terminal table formatting |
| `PyYAML` | ≥ 6.0 | YAML config file parsing |
| `urllib3` | ≥ 2.0 | Retry logic and connection pooling |
| `python-json-logger` | ≥ 2.0.7 | Structured JSON log output |

### Kubernetes prerequisites

> [!IMPORTANT]
> **kube-state-metrics must be deployed and scraped by your Prometheus instance.**
>
> `k8s-prometheus-analyzer` relies on the `kube_pod_owner` and `kube_replicaset_owner` metrics exposed by [`kube-state-metrics`](https://github.com/kubernetes/kube-state-metrics) to resolve pod-to-workload ownership (Deployment → ReplicaSet → Pod). Without it, the tool falls back to **pod-level** grouping and logs a warning.

#### Quick kube-state-metrics setup (Helm)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install kube-state-metrics prometheus-community/kube-state-metrics \
  --namespace monitoring --create-namespace
```

Verify metrics are being scraped:

```bash
curl http://localhost:9090/api/v1/query?query=kube_pod_owner | jq '.data.result | length'
# Should return > 0
```

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        k8s-prometheus-analyzer                        │
│                                                                        │
│  CLI (k8s-analyze)                                                     │
│       │                                                                │
│       ▼                                                                │
│  Config Loader ──► YAML file / env vars (K8S_ANALYZER_*) / defaults   │
│       │                                                                │
│       ▼                                                                │
│  PrometheusClient                                                      │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │  Queries:                                                    │      │
│  │   • container_cpu_usage_seconds_total (rate)                │      │
│  │   • container_memory_working_set_bytes                      │      │
│  │   • kube_pod_container_resource_requests (cpu/memory)       │      │
│  │   • kube_pod_owner  (pod → ReplicaSet/StatefulSet/DaemonSet)│      │
│  │   • kube_replicaset_owner  (ReplicaSet → Deployment)        │      │
│  └─────────────────────────────────────────────────────────────┘      │
│       │                                                                │
│       ▼                                                                │
│  Workload Resolver  ── pod_owner + rs_owner ──► workload_map          │
│       │                                                                │
│       ▼                                                                │
│  Aggregator  ── per-pod averages ──► WorkloadMetrics[]                │
│       │                                                                │
│       ▼                                                                │
│  Analyzer  ── 7 threshold rules ──► Recommendation[]                  │
│       │                                                                │
│       ├──► table.print_table()     → stdout (colour-coded)            │
│       ├──► json_report.export()    → optimization_suggestions.json    │
│       ├──► html_report.export()    → k8s_report.html                  │
│       └──► alerting.dispatch()                                         │
│                 │                                                       │
│                 ├──► SlackAlerter  → Slack Incoming Webhook            │
│                 └──► WebhookAlerter → Generic HTTP endpoint            │
│                                                                        │
│  Exit codes:  0=OK  1=warnings  2=critical  3=error                   │
└──────────────────────────────────────────────────────────────────────┘
             │                               ▲
             │  HTTP / PromQL                │ metrics
             ▼                               │
    ┌─────────────────┐           ┌──────────────────────┐
    │   Prometheus    │◄──scrape──│  kube-state-metrics  │
    │   (9090)        │           │  node-exporter       │
    └─────────────────┘           └──────────────────────┘
```

### Analysis Rules

| Rule | Condition | Suggestion | Severity |
|---|---|---|---|
| 1 | CPU usage < `cpu_low` (cores/pod) | Reduce CPU requests | info |
| 2 | Memory usage < `mem_low_mb` (MB/pod) | Reduce memory requests | warning |
| 3 | CPU utilisation > `cpu_high_pct` % | Increase CPU limits or add replicas | critical |
| 4 | Memory usage > `mem_high_mb` MB/pod | Increase Memory limits | warning |
| 5 | CPU usage > CPU request | Increase CPU requests | critical |
| 6 | Memory request > usage × `mem_overcommit_ratio` | Reduce memory requests | warning |
| 7 | CPU < `replica_cpu_low` AND memory < `replica_mem_low_mb` | Consider reducing replicas | info |

---

## 🤝 Contributing

Contributions are welcome! Please read the [CONTRIBUTING guide](k8s-monitor/CONTRIBUTING.md) for development setup, code style, testing, and the PR process.

### Quick start for contributors

```bash
git clone https://github.com/rahulbansod519/k8s_prometheus_analyzer.git
cd k8s_prometheus_analyzer/k8s-monitor
pip install -e '.[dev]'

# Run tests
pytest

# Lint
ruff check .

# Type-check
mypy k8s_prometheus_analyzer
```

Please review our [Security Policy](k8s-monitor/SECURITY.md) before reporting vulnerabilities.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgements

- [Prometheus](https://prometheus.io/) — the open-source monitoring backbone
- [kube-state-metrics](https://github.com/kubernetes/kube-state-metrics) — Kubernetes object state metrics
- [tabulate](https://github.com/astanin/python-tabulate) — beautiful terminal tables
- [python-json-logger](https://github.com/madzak/python-json-logger) — structured log output

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/rahulbansod519">Rahul Bansod</a>
</p>
