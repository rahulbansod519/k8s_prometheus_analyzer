---
name: Bug Report
about: Something isn't working as expected
labels: bug
assignees: ''
---

## Describe the bug

<!-- A clear and concise description of what the bug is. -->

## Steps to reproduce

```bash
# The exact command that triggers the bug
k8s-analyze --prometheus-url http://localhost:9090
```

## Expected behavior

<!-- What you expected to happen. -->

## Actual behavior

<!-- What actually happened. Include the full error message and stack trace. -->

## Environment

| Item | Version |
|---|---|
| k8s-prometheus-analyzer | `k8s-analyze --version` |
| Python | `python --version` |
| Kubernetes | <!-- e.g. 1.28.4 --> |
| Prometheus | <!-- e.g. 2.47.0 --> |
| OS | <!-- e.g. Ubuntu 22.04, macOS 14 --> |

## Config file (if applicable)

```yaml
# Paste your config.yaml here (redact credentials)
```

## Log output

```
# k8s-analyze --log-level DEBUG --log-format json ...
```
