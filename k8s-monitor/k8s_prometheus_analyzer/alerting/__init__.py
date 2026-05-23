"""Alerting sub-package for k8s-prometheus-analyzer.

Supported channels
------------------
* :mod:`~k8s_prometheus_analyzer.alerting.slack`   — Slack incoming webhooks (Block Kit)
* :mod:`~k8s_prometheus_analyzer.alerting.webhook` — Generic HTTP webhook

Use :func:`~k8s_prometheus_analyzer.alerting.dispatcher.dispatch` as the
single entry point from ``cli.py``.
"""
