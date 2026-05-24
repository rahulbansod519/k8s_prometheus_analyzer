"""Tests for the alerting sub-package (Slack, webhook, dispatcher)."""

from __future__ import annotations

import pytest
import requests

from typing import Any

from k8s_prometheus_analyzer.alerting.dispatcher import dispatch
from k8s_prometheus_analyzer.alerting.slack import SlackChannel
from k8s_prometheus_analyzer.alerting.webhook import WebhookChannel
from k8s_prometheus_analyzer.config import AlertConfig, SlackAlertConfig, WebhookAlertConfig
from k8s_prometheus_analyzer.exceptions import AlertDeliveryError

from .conftest import make_workload_metrics

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

PROM_URL = "http://prometheus:9090"


def _make_slack_cfg(**kwargs: Any) -> SlackAlertConfig:
    defaults: dict[str, Any] = {
        "enabled": True,
        "webhook_url": "https://hooks.slack.com/test/token",
        "username": "k8s-analyzer",
        "icon_emoji": ":kubernetes:",
    }
    defaults.update(kwargs)
    return SlackAlertConfig(**defaults)


def _make_webhook_cfg(**kwargs: Any) -> WebhookAlertConfig:
    defaults: dict[str, Any] = {
        "enabled": True,
        "url": "https://example.com/alerts",
        "method": "POST",
        "headers": {},
        "timeout": 5,
    }
    defaults.update(kwargs)
    return WebhookAlertConfig(**defaults)


def _make_alert_cfg(**kwargs) -> AlertConfig:
    cfg = AlertConfig(enabled=True)
    cfg.slack = _make_slack_cfg()
    cfg.webhook = _make_webhook_cfg()
    for k, v in kwargs.items():
        setattr(cfg, k, v)
    return cfg


def _critical_recs():
    """Return one critical recommendation (CPU throttled)."""
    return make_workload_metrics(
        workload_name="frontend",
        namespace="production",
        cpu_usage_per_pod=1.5,
        cpu_request_per_pod=1.0,
    )


def _warning_recs():
    """Return one warning recommendation (memory over-committed)."""
    return make_workload_metrics(
        workload_name="backend",
        namespace="production",
        cpu_usage_per_pod=0.3,
        cpu_request_per_pod=1.0,
        memory_mb_per_pod=10.0,
        memory_request_mb_per_pod=800.0,
    )


# ---------------------------------------------------------------------------
# SlackChannel tests
# ---------------------------------------------------------------------------


class TestSlackChannel:
    def test_send_posts_to_webhook_url(self, mocker):
        mock_post = mocker.patch("requests.post")
        mock_post.return_value.raise_for_status = mocker.MagicMock()

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())
        channel = SlackChannel(_make_slack_cfg())
        channel.send(recs, PROM_URL)

        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert call_url == "https://hooks.slack.com/test/token"

    def test_payload_contains_blocks(self, mocker):
        mock_post = mocker.patch("requests.post")
        mock_post.return_value.raise_for_status = mocker.MagicMock()

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())
        channel = SlackChannel(_make_slack_cfg())
        channel.send(recs, PROM_URL)

        payload = mock_post.call_args.kwargs["json"]
        assert "blocks" in payload
        assert len(payload["blocks"]) >= 3  # header + summary + divider at minimum

    def test_payload_has_header_with_count(self, mocker):
        mock_post = mocker.patch("requests.post")
        mock_post.return_value.raise_for_status = mocker.MagicMock()

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())
        channel = SlackChannel(_make_slack_cfg())
        channel.send(recs, PROM_URL)

        payload = mock_post.call_args.kwargs["json"]
        header_block = payload["blocks"][0]
        assert header_block["type"] == "header"
        assert str(len(recs)) in header_block["text"]["text"]

    def test_payload_includes_username_and_emoji(self, mocker):
        mock_post = mocker.patch("requests.post")
        mock_post.return_value.raise_for_status = mocker.MagicMock()

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())
        channel = SlackChannel(_make_slack_cfg(username="my-bot", icon_emoji=":robot:"))
        channel.send(recs, PROM_URL)

        payload = mock_post.call_args.kwargs["json"]
        assert payload["username"] == "my-bot"
        assert payload["icon_emoji"] == ":robot:"

    def test_channel_included_when_set(self, mocker):
        mock_post = mocker.patch("requests.post")
        mock_post.return_value.raise_for_status = mocker.MagicMock()

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())
        channel = SlackChannel(_make_slack_cfg(channel="#my-channel"))
        channel.send(recs, PROM_URL)

        payload = mock_post.call_args.kwargs["json"]
        assert payload.get("channel") == "#my-channel"

    def test_channel_omitted_when_not_set(self, mocker):
        mock_post = mocker.patch("requests.post")
        mock_post.return_value.raise_for_status = mocker.MagicMock()

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())
        channel = SlackChannel(_make_slack_cfg(channel=""))
        channel.send(recs, PROM_URL)

        payload = mock_post.call_args.kwargs["json"]
        assert "channel" not in payload

    def test_truncates_at_10_workloads(self, mocker):
        mock_post = mocker.patch("requests.post")
        mock_post.return_value.raise_for_status = mocker.MagicMock()

        # Build 15 critical recommendations
        from k8s_prometheus_analyzer.analyzer import SEVERITY_CRITICAL, Recommendation
        recs = [
            Recommendation(
                workload_name=f"svc-{i}",
                workload_kind="Deployment",
                namespace="default",
                replica_count=1,
                pod_names=[f"pod-{i}"],
                cpu_usage=1.5, memory_usage_mb=100,
                cpu_usage_pct=150, memory_usage_pct=20,
                total_cpu_usage=1.5, total_memory_mb=100,
                suggestions=["Increase CPU requests"],
                reasons=["throttled"],
                severity=SEVERITY_CRITICAL,
            )
            for i in range(15)
        ]
        channel = SlackChannel(_make_slack_cfg())
        channel.send(recs, PROM_URL)

        payload = mock_post.call_args.kwargs["json"]
        # Check a "...and N more" section exists
        texts = [
            b.get("text", {}).get("text", "")
            for b in payload["blocks"]
            if b.get("type") == "section"
        ]
        assert any("more" in t for t in texts)

    def test_raises_alert_delivery_error_on_http_failure(self, mocker):
        mock_post = mocker.patch("requests.post")
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())
        channel = SlackChannel(_make_slack_cfg())

        with pytest.raises(AlertDeliveryError):
            channel.send(recs, PROM_URL)

    def test_raises_alert_delivery_error_on_bad_status(self, mocker):
        mock_post = mocker.patch("requests.post")
        mock_resp = mocker.MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("403")
        mock_post.return_value = mock_resp

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())
        channel = SlackChannel(_make_slack_cfg())

        with pytest.raises(AlertDeliveryError):
            channel.send(recs, PROM_URL)


# ---------------------------------------------------------------------------
# WebhookChannel tests
# ---------------------------------------------------------------------------


class TestWebhookChannel:
    def test_send_posts_json_to_url(self, mocker):
        mock_req = mocker.patch("requests.request")
        mock_req.return_value.raise_for_status = mocker.MagicMock()

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())
        channel = WebhookChannel(_make_webhook_cfg())
        channel.send(recs, PROM_URL)

        mock_req.assert_called_once()
        kwargs = mock_req.call_args.kwargs
        assert kwargs["url"] == "https://example.com/alerts"
        assert kwargs["method"] == "POST"

    def test_payload_has_required_keys(self, mocker):
        mock_req = mocker.patch("requests.request")
        mock_req.return_value.raise_for_status = mocker.MagicMock()

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())
        channel = WebhookChannel(_make_webhook_cfg())
        channel.send(recs, PROM_URL)

        payload = mock_req.call_args.kwargs["json"]
        for key in ("timestamp", "prometheus_url", "total", "critical", "warning", "info", "recommendations"):
            assert key in payload, f"Missing key '{key}' in webhook payload"

    def test_payload_severity_counts_correct(self, mocker):
        mock_req = mocker.patch("requests.request")
        mock_req.return_value.raise_for_status = mocker.MagicMock()

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())  # 1 critical
        channel = WebhookChannel(_make_webhook_cfg())
        channel.send(recs, PROM_URL)

        payload = mock_req.call_args.kwargs["json"]
        assert payload["critical"] >= 1
        assert payload["total"] == len(recs)
        assert payload["prometheus_url"] == PROM_URL

    def test_custom_headers_forwarded(self, mocker):
        mock_req = mocker.patch("requests.request")
        mock_req.return_value.raise_for_status = mocker.MagicMock()

        headers = {"Authorization": "Bearer secret", "X-Source": "k8s-analyzer"}
        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())
        channel = WebhookChannel(_make_webhook_cfg(headers=headers))
        channel.send(recs, PROM_URL)

        forwarded = mock_req.call_args.kwargs["headers"]
        assert forwarded["Authorization"] == "Bearer secret"
        assert forwarded["X-Source"] == "k8s-analyzer"

    def test_get_method_used_when_configured(self, mocker):
        mock_req = mocker.patch("requests.request")
        mock_req.return_value.raise_for_status = mocker.MagicMock()

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())
        channel = WebhookChannel(_make_webhook_cfg(method="GET"))
        channel.send(recs, PROM_URL)

        assert mock_req.call_args.kwargs["method"] == "GET"

    def test_raises_alert_delivery_error_on_failure(self, mocker):
        mock_req = mocker.patch("requests.request")
        mock_req.side_effect = requests.exceptions.Timeout("timed out")

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())
        channel = WebhookChannel(_make_webhook_cfg())

        with pytest.raises(AlertDeliveryError):
            channel.send(recs, PROM_URL)

    def test_timeout_applied(self, mocker):
        mock_req = mocker.patch("requests.request")
        mock_req.return_value.raise_for_status = mocker.MagicMock()

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())
        channel = WebhookChannel(_make_webhook_cfg(timeout=7))
        channel.send(recs, PROM_URL)

        assert mock_req.call_args.kwargs["timeout"] == 7


# ---------------------------------------------------------------------------
# Dispatcher tests
# ---------------------------------------------------------------------------


class TestDispatcher:
    def test_skips_all_when_alerts_disabled(self, mocker):
        mock_slack = mocker.patch("k8s_prometheus_analyzer.alerting.dispatcher.SlackChannel")
        mock_webhook = mocker.patch("k8s_prometheus_analyzer.alerting.dispatcher.WebhookChannel")

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())
        cfg = _make_alert_cfg()
        cfg.enabled = False

        dispatch(recs, cfg, PROM_URL)

        mock_slack.assert_not_called()
        mock_webhook.assert_not_called()

    def test_skips_when_no_recommendations_match_severities(self, mocker):
        mock_slack = mocker.patch("k8s_prometheus_analyzer.alerting.dispatcher.SlackChannel")
        mock_slack.return_value.send = mocker.MagicMock()

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())  # CRITICAL recs

        cfg = _make_alert_cfg()
        cfg.slack.enabled = True
        cfg.webhook.enabled = False
        cfg.on_severities = ["info"]  # won't match critical

        dispatch(recs, cfg, PROM_URL)

        mock_slack.return_value.send.assert_not_called()

    def test_sends_to_slack_when_enabled(self, mocker):
        mock_post = mocker.patch("requests.post")
        mock_post.return_value.raise_for_status = mocker.MagicMock()

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())

        cfg = AlertConfig(enabled=True)
        cfg.slack = _make_slack_cfg()
        cfg.webhook.enabled = False
        cfg.on_severities = ["critical"]

        dispatch(recs, cfg, PROM_URL)

        mock_post.assert_called_once()

    def test_sends_to_webhook_when_enabled(self, mocker):
        mock_req = mocker.patch("requests.request")
        mock_req.return_value.raise_for_status = mocker.MagicMock()

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())

        cfg = AlertConfig(enabled=True)
        cfg.slack.enabled = False
        cfg.webhook = _make_webhook_cfg()
        cfg.on_severities = ["critical"]

        dispatch(recs, cfg, PROM_URL)

        mock_req.assert_called_once()

    def test_channel_failure_does_not_crash(self, mocker):
        """A failing Slack channel must not prevent webhook from running."""
        mock_post = mocker.patch("requests.post")
        mock_post.side_effect = requests.exceptions.ConnectionError("down")

        mock_req = mocker.patch("requests.request")
        mock_req.return_value.raise_for_status = mocker.MagicMock()

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())

        cfg = AlertConfig(enabled=True)
        cfg.slack = _make_slack_cfg()
        cfg.webhook = _make_webhook_cfg()
        cfg.on_severities = ["critical"]

        # Must not raise
        dispatch(recs, cfg, PROM_URL)

        # Webhook should still have been called despite Slack failure
        mock_req.assert_called_once()

    def test_only_filtered_recs_sent_to_channels(self, mocker):
        """When on_severities=["critical"], warning recs are not sent."""
        mock_req = mocker.patch("requests.request")
        mock_req.return_value.raise_for_status = mocker.MagicMock()

        from k8s_prometheus_analyzer.analyzer import analyze
        crit_recs = analyze(_critical_recs())  # critical
        warn_recs = analyze(_warning_recs())   # warning (memory overcommit)
        all_recs = crit_recs + warn_recs

        cfg = AlertConfig(enabled=True)
        cfg.slack.enabled = False
        cfg.webhook = _make_webhook_cfg()
        cfg.on_severities = ["critical"]  # only critical

        dispatch(all_recs, cfg, PROM_URL)

        payload = mock_req.call_args.kwargs["json"]
        sent_severities = {r["severity"] for r in payload["recommendations"]}
        assert sent_severities == {"critical"}

    def test_slack_skipped_when_no_webhook_url(self, mocker):
        """Slack enabled but webhook_url empty → skip with warning, no crash."""
        mock_post = mocker.patch("requests.post")

        from k8s_prometheus_analyzer.analyzer import analyze
        recs = analyze(_critical_recs())

        cfg = AlertConfig(enabled=True)
        cfg.slack = _make_slack_cfg(webhook_url="")  # missing URL
        cfg.webhook.enabled = False

        dispatch(recs, cfg, PROM_URL)  # must not raise

        mock_post.assert_not_called()

    def test_dispatch_noop_when_no_recs(self, mocker):
        """Empty recommendations list → nothing sent even if alerting enabled."""
        mock_post = mocker.patch("requests.post")
        mock_req = mocker.patch("requests.request")

        cfg = _make_alert_cfg()
        dispatch([], cfg, PROM_URL)

        mock_post.assert_not_called()
        mock_req.assert_not_called()
