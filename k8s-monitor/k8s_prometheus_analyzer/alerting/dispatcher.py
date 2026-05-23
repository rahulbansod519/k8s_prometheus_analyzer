"""Alert dispatcher — fans out to all configured channels after severity filtering."""

from __future__ import annotations

import logging

from ..analyzer import Recommendation
from ..config import AlertConfig
from ..exceptions import AlertDeliveryError
from .slack import SlackChannel
from .webhook import WebhookChannel

logger = logging.getLogger(__name__)


def dispatch(
    recommendations: list[Recommendation],
    alert_cfg: AlertConfig,
    prometheus_url: str,
) -> None:
    """Send alerts to all enabled channels for recommendations that match *on_severities*.

    This function is **always safe to call** — it never raises.  Any delivery
    failure is logged as a ``WARNING`` and the tool continues normally.

    Args:
        recommendations: Full list of recommendations from :func:`~k8s_prometheus_analyzer.analyzer.analyze`.
        alert_cfg:       The ``alerts`` section of the loaded :class:`~k8s_prometheus_analyzer.config.Config`.
        prometheus_url:  Included in alert payloads for traceability.
    """
    if not alert_cfg.enabled:
        logger.debug("Alerting disabled — skipping dispatch")
        return

    # Filter to only the configured severities
    filtered = [r for r in recommendations if r.severity in alert_cfg.on_severities]
    if not filtered:
        logger.debug(
            "No recommendations match alert severities %s — skipping dispatch",
            alert_cfg.on_severities,
        )
        return

    logger.info(
        "Dispatching alerts: %d recommendation(s) match severities %s",
        len(filtered),
        alert_cfg.on_severities,
    )

    # Build list of active channels
    channels: list[SlackChannel | WebhookChannel] = []

    if alert_cfg.slack.enabled:
        if alert_cfg.slack.webhook_url:
            channels.append(SlackChannel(alert_cfg.slack))
        else:
            logger.warning("Slack alerts enabled but no webhook_url configured — skipping Slack")

    if alert_cfg.webhook.enabled:
        if alert_cfg.webhook.url:
            channels.append(WebhookChannel(alert_cfg.webhook))
        else:
            logger.warning("Webhook alerts enabled but no url configured — skipping webhook")

    if not channels:
        logger.warning("Alerting enabled but no channels are configured — nothing sent")
        return

    # Deliver to each channel independently
    for channel in channels:
        channel_name = type(channel).__name__
        try:
            channel.send(filtered, prometheus_url)
            logger.info("✓ Alert delivered via %s", channel_name)
        except AlertDeliveryError as exc:
            logger.warning("✗ Alert delivery failed via %s: %s", channel_name, exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("✗ Unexpected error sending via %s: %s", channel_name, exc)
