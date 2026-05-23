# Contributing to k8s-prometheus-analyzer

Thank you for considering a contribution to **k8s-prometheus-analyzer**! Whether you're fixing a bug, improving documentation, adding a new analysis rule, or building a new alert channel — your help is genuinely appreciated.

Please take a few minutes to read this guide before opening a pull request. It keeps the review process smooth for everyone.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Clone and install](#clone-and-install)
  - [Project layout](#project-layout)
- [Development Workflow](#development-workflow)
  - [Running tests](#running-tests)
  - [Linting with Ruff](#linting-with-ruff)
  - [Type checking with mypy](#type-checking-with-mypy)
  - [Running all checks at once](#running-all-checks-at-once)
- [Code Style Guidelines](#code-style-guidelines)
- [Pull Request Process](#pull-request-process)
- [How to Add a New Analysis Rule](#how-to-add-a-new-analysis-rule)
- [How to Add a New Alert Channel](#how-to-add-a-new-alert-channel)
- [Reporting Bugs](#reporting-bugs)
- [Requesting Features](#requesting-features)

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). By participating, you agree to uphold a respectful and inclusive environment. Please report unacceptable behaviour to the maintainers via [GitHub Issues](https://github.com/rahulbansod519/k8s_prometheus_analyzer/issues).

---

## Getting Started

### Prerequisites

| Tool | Minimum version | Purpose |
|---|---|---|
| Python | 3.10 | Runtime |
| pip | 23+ | Package management |
| git | Any recent | Version control |

Optional but recommended:
- A local or port-forwarded Prometheus instance for end-to-end testing
- Docker (for building/testing the container image)

### Clone and install

```bash
# 1. Fork the repository on GitHub, then clone your fork
git clone https://github.com/<YOUR_USERNAME>/k8s_prometheus_analyzer.git
cd k8s_prometheus_analyzer/k8s-monitor

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows

# 3. Install in editable mode with all dev dependencies
pip install -e '.[dev]'

# 4. Verify the CLI is available
k8s-analyze --help
```

> **Editable install (`-e`)** means any changes you make to the source files under `k8s_prometheus_analyzer/` take effect immediately — no reinstall needed.

### Project layout

```
k8s-monitor/
├── k8s_prometheus_analyzer/      # Main package
│   ├── __init__.py
│   ├── cli.py                    # Argument parsing, pipeline orchestration
│   ├── config.py                 # Layered config loading (CLI → env → YAML → defaults)
│   ├── fetcher.py                # Prometheus HTTP client, PromQL queries
│   ├── workload.py               # Pod-to-workload ownership resolution & aggregation
│   ├── analyzer.py               # Pure analysis logic — threshold rules, Recommendation type
│   ├── exceptions.py             # K8sAnalyzerError, ConfigError
│   ├── alerting/
│   │   ├── __init__.py
│   │   ├── base.py               # BaseAlerter abstract class
│   │   ├── dispatcher.py         # Calls each enabled alert channel
│   │   ├── slack.py              # Slack Incoming Webhooks implementation
│   │   └── webhook.py            # Generic HTTP webhook implementation
│   └── reporter/
│       ├── __init__.py
│       ├── table.py              # Terminal table output (tabulate)
│       ├── json_report.py        # JSON file export
│       └── html_report.py        # Self-contained HTML dashboard
├── tests/
│   ├── conftest.py               # Shared fixtures and mock data
│   ├── test_analyzer.py
│   ├── test_alerting.py
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_fetcher.py
│   └── test_workload.py
├── config.example.yaml           # Reference configuration
├── pyproject.toml                # Build config, tool settings
├── Dockerfile
├── CHANGELOG.md
├── CONTRIBUTING.md               # This file
└── SECURITY.md
```

---

## Development Workflow

### Running tests

The test suite uses **pytest** with **pytest-cov** for coverage reporting.

```bash
# Run all tests and show coverage summary
pytest

# Run a specific test file
pytest tests/test_analyzer.py

# Run a specific test by name
pytest tests/test_analyzer.py::test_cpu_over_provisioned

# Run with verbose output
pytest -v

# Run and open the HTML coverage report
pytest --cov-report=html
open htmlcov/index.html         # macOS
xdg-open htmlcov/index.html     # Linux
```

The CI pipeline requires **≥ 80% coverage**. If you add new code, please add corresponding tests. Aim to keep coverage at or above the current **84%** baseline.

#### Writing tests

- Place tests in `tests/test_<module>.py` mirroring the source structure
- Use `conftest.py` for shared fixtures — do not duplicate fixture setup across files
- Mock all external I/O (HTTP calls, file writes) using `pytest-mock` / `unittest.mock`
- Test both the happy path and edge cases (empty results, missing metrics, config errors)
- Keep tests fast — no real network calls, no sleeping

```python
# Example: testing an analysis rule
def test_cpu_throttled_is_critical(thresholds):
    wm = make_workload_metrics(cpu_usage_per_pod=0.5, cpu_request_per_pod=0.3)
    results = analyze([wm], thresholds)
    assert len(results) == 1
    assert results[0].severity == SEVERITY_CRITICAL
    assert "Increase CPU requests" in results[0].suggestions
```

### Linting with Ruff

The project uses [Ruff](https://docs.astral.sh/ruff/) for linting and import sorting. Configuration lives in `pyproject.toml` under `[tool.ruff]`.

```bash
# Check for issues
ruff check .

# Auto-fix fixable issues
ruff check --fix .

# Check a single file
ruff check k8s_prometheus_analyzer/analyzer.py
```

The enabled rule sets are `E` (pycodestyle errors), `F` (Pyflakes), `W` (pycodestyle warnings), `I` (isort), and `UP` (pyupgrade). Line length is set to **100 characters**.

### Type checking with mypy

The codebase is fully type-annotated. Run mypy before submitting a PR:

```bash
# Type-check the main package
mypy k8s_prometheus_analyzer

# Type-check with explicit config
mypy --config-file pyproject.toml k8s_prometheus_analyzer
```

All new code **must** include type annotations. Use `from __future__ import annotations` at the top of every module for forward-reference compatibility. Avoid `Any` unless absolutely necessary — prefer `object` or a proper union type.

### Running all checks at once

```bash
# The full CI pipeline locally
ruff check . && mypy k8s_prometheus_analyzer && pytest
```

You can also add this as a pre-commit hook:

```bash
# .git/hooks/pre-commit
#!/usr/bin/env bash
set -e
ruff check .
mypy k8s_prometheus_analyzer
pytest -q
```

---

## Code Style Guidelines

1. **Formatter**: Ruff's formatter (`ruff format`) follows Black-compatible style. Run it before committing.
2. **Line length**: 100 characters maximum (enforced by Ruff).
3. **Imports**: Grouped and sorted by `isort` rules (Ruff's `I` ruleset). Standard library → third-party → local. Use `from __future__ import annotations` as the first import in every module.
4. **Docstrings**: Write Google-style docstrings for all public classes, functions, and methods. One-line docstrings are fine for simple helpers.
5. **Type annotations**: All function signatures must be fully annotated. Use `list[...]` and `dict[...]` (not `List`/`Dict` from `typing`) on Python 3.10+.
6. **Naming**: `snake_case` for functions and variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for module-level constants.
7. **No magic numbers**: Extract threshold defaults and other numeric constants into named variables or dataclass defaults.
8. **Error handling**: Raise `K8sAnalyzerError` (or a subclass) for recoverable tool errors. Use `ConfigError` for configuration problems. Never swallow exceptions silently.
9. **Logging**: Use `logger = logging.getLogger(__name__)` at module level. Log at `DEBUG` for internal state, `INFO` for user-facing progress, `WARNING` for degraded operation, `ERROR` for failures. Never log credentials.
10. **Pure functions preferred**: Analysis logic in `analyzer.py` must remain pure (no I/O, no side effects). Keep I/O at the edges (CLI, reporter, alerting).

---

## Pull Request Process

1. **Fork** the repository and create a descriptive branch:
   ```bash
   git checkout -b feat/add-namespace-filter
   git checkout -b fix/slack-empty-payload
   git checkout -b docs/improve-threshold-docs
   ```

2. **Make your changes** — keep commits atomic and use [Conventional Commits](https://www.conventionalcommits.org/) style:
   ```
   feat: add --namespace flag to scope analysis
   fix: handle empty Prometheus response for kube_pod_owner
   docs: expand threshold configuration table in README
   test: add test for memory overcommit rule edge case
   refactor: extract _build_slack_blocks() into slack.py helper
   ```

3. **Run all checks** and ensure they pass:
   ```bash
   ruff check . && mypy k8s_prometheus_analyzer && pytest
   ```

4. **Update documentation** — if you change behaviour, CLI flags, config keys, or exit codes, update `README.md` and `CHANGELOG.md` accordingly.

5. **Open a Pull Request** against the `main` branch:
   - Fill in the PR template (describe what changed and why)
   - Link any related issues (`Closes #123`)
   - Ensure all CI checks pass (GitHub Actions runs lint, type-check, and test matrix)

6. **Review process**:
   - At least one maintainer review is required before merging
   - Address all review comments before requesting re-review
   - Squash or rebase to keep a clean history (maintainer may do this on merge)

---

## How to Add a New Analysis Rule

All analysis rules live in `k8s_prometheus_analyzer/analyzer.py` inside the `analyze()` function. Each rule:

1. Reads from the `WorkloadMetrics` object (per-pod averages)
2. Compares against a `Thresholds` field
3. Appends to `suggestions` and `reasons` lists

### Step-by-step

**1. Add a threshold field to `Thresholds` in `config.py`:**

```python
@dataclass
class Thresholds:
    # ... existing fields ...
    # New threshold for your rule
    cpu_limit_ratio: float = 2.0  # Warn if limit > request × this ratio
```

**2. Expose the new threshold in the YAML schema** (`config.example.yaml`):

```yaml
thresholds:
  # ... existing ...
  cpu_limit_ratio: 2.0  # Flag if CPU limit > request × this ratio
```

**3. Add the environment variable mapping** in `config.py`'s `_load_env()` function:

```python
if val := os.getenv("K8S_ANALYZER_CPU_LIMIT_RATIO"):
    cfg.thresholds.cpu_limit_ratio = float(val)
```

**4. Implement the rule in `analyzer.py`:**

```python
# ── Rule N: CPU limit over-provisioned ───────────────────────────────────
cpu_limit = wm.cpu_limit_per_pod
if cpu_limit and cpu_request and cpu_limit > cpu_request * thr.cpu_limit_ratio:
    suggestions.append("Reduce CPU limits")
    reasons.append(
        f"CPU limit ({cpu_limit:.2f} cores/pod) is {cpu_limit/cpu_request:.1f}× "
        f"the request ({cpu_request:.2f} cores/pod)"
    )
```

**5. Update `_determine_severity()`** if the new suggestion should map to a non-`info` severity:

```python
warning_keywords = {"Increase Memory limits", "Reduce memory requests", "Reduce CPU limits"}
```

**6. Fetch the required metric** in `fetcher.py` if it's not already queried (e.g. `kube_pod_container_resource_limits`).

**7. Write tests** in `tests/test_analyzer.py`:

```python
def test_cpu_limit_over_provisioned(thresholds):
    wm = make_workload_metrics(cpu_limit_per_pod=2.0, cpu_request_per_pod=0.5)
    results = analyze([wm], thresholds)
    assert any("Reduce CPU limits" in r.suggestions for r in results)
```

**8. Document** the new rule in `README.md`'s Analysis Rules table.

---

## How to Add a New Alert Channel

Alert channels live in `k8s_prometheus_analyzer/alerting/`. Each channel is a class that inherits from `BaseAlerter`.

### Step-by-step

**1. Create a new file** `k8s_prometheus_analyzer/alerting/pagerduty.py`:

```python
"""PagerDuty Events API v2 alert channel."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from ..analyzer import Recommendation
from .base import BaseAlerter

logger = logging.getLogger(__name__)


@dataclass
class PagerDutyConfig:
    enabled: bool = False
    integration_key: str = ""
    severity: str = "error"  # critical | error | warning | info


class PagerDutyAlerter(BaseAlerter):
    def __init__(self, cfg: PagerDutyConfig) -> None:
        self._cfg = cfg

    def send(self, recommendations: list[Recommendation], prometheus_url: str) -> None:
        if not self._cfg.enabled or not self._cfg.integration_key:
            return

        payload = self._build_payload(recommendations, prometheus_url)
        try:
            resp = requests.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("PagerDuty alert sent successfully")
        except requests.RequestException as exc:
            logger.error("Failed to send PagerDuty alert: %s", exc)

    def _build_payload(
        self, recommendations: list[Recommendation], prometheus_url: str
    ) -> dict:
        # Build PagerDuty Events API v2 payload
        return {
            "routing_key": self._cfg.integration_key,
            "event_action": "trigger",
            "payload": {
                "summary": f"{len(recommendations)} Kubernetes resource issue(s) detected",
                "source": prometheus_url,
                "severity": self._cfg.severity,
                "custom_details": {
                    "workloads": [r.to_dict() for r in recommendations],
                },
            },
        }
```

**2. Add the config dataclass** to `config.py`:

```python
@dataclass
class PagerDutyConfig:
    enabled: bool = False
    integration_key: str = ""
    severity: str = "error"

@dataclass
class AlertsConfig:
    # ... existing fields ...
    pagerduty: PagerDutyConfig = field(default_factory=PagerDutyConfig)
```

**3. Register the new alerter** in `alerting/dispatcher.py`:

```python
from .pagerduty import PagerDutyAlerter

def dispatch(recommendations, alerts_cfg, prometheus_url):
    # ... existing channels ...
    if alerts_cfg.pagerduty.enabled:
        PagerDutyAlerter(alerts_cfg.pagerduty).send(filtered, prometheus_url)
```

**4. Expose CLI flags** in `cli.py` (`_build_parser()`):

```python
alert.add_argument(
    "--alert-pagerduty-key",
    metavar="KEY",
    help="PagerDuty Events API v2 integration key",
)
```

**5. Wire the CLI override** in `main()`:

```python
if args.alert_pagerduty_key:
    cfg.alerts.enabled = True
    cfg.alerts.pagerduty.enabled = True
    cfg.alerts.pagerduty.integration_key = args.alert_pagerduty_key
```

**6. Write tests** in `tests/test_alerting.py` — mock `requests.post` and assert the payload structure.

**7. Update** `README.md` (Alert Configuration section) and `CHANGELOG.md` ([Unreleased]).

---

## Reporting Bugs

1. Search [existing issues](https://github.com/rahulbansod519/k8s_prometheus_analyzer/issues) first
2. Open a new issue with the **Bug Report** template
3. Include: Python version, OS, `k8s-analyze --version` output, full error traceback, and the minimal config/command to reproduce

---

## Requesting Features

1. Search [existing issues](https://github.com/rahulbansod519/k8s_prometheus_analyzer/issues) and [discussions](https://github.com/rahulbansod519/k8s_prometheus_analyzer/discussions)
2. Open a new issue with the **Feature Request** template
3. Describe the use case, not just the solution — explain *why* the feature is needed

---

Thank you for contributing! 🎉
