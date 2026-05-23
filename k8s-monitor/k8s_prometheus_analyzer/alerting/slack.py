"""Slack alert channel using the Incoming Webhooks API with Block Kit formatting."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from ..analyzer import Recommendation
from ..config import SlackAlertConfig
from ..exceptions import AlertDeliveryError
from .base import AlertChannel

logger = logging.getLogger(__name__)

_SEVERITY_ICON = {
    "critical": "🔴",
    "warning": "🟡",
    "info": "🟢",
}

_MAX_WORKLOADS_IN_MESSAGE = 10


class SlackChannel(AlertChannel):
    """Delivers alerts to a Slack channel via an Incoming Webhook URL.

    Uses Slack's Block Kit layout for rich, colour-coded formatting.

    Args:
        cfg: :class:`~k8s_prometheus_analyzer.config.SlackAlertConfig`.
    """

    def __init__(self, cfg: SlackAlertConfig) -> None:
        self._cfg = cfg

    # ------------------------------------------------------------------
    # AlertChannel implementation
    # ------------------------------------------------------------------

    def send(self, recommendations: list[Recommendation], prometheus_url: str) -> None:
        payload = self._build_payload(recommendations, prometheus_url)

        try:
            resp = requests.post(
                self._cfg.webhook_url,
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise AlertDeliveryError(f"Slack webhook request failed: {exc}") from exc

        logger.info(
            "Slack alert delivered — %d recommendation(s) reported", len(recommendations)
        )

    # ------------------------------------------------------------------
    # Payload construction
    # ------------------------------------------------------------------

    def _build_payload(
        self, recommendations: list[Recommendation], prometheus_url: str
    ) -> dict[str, Any]:
        n_critical = sum(1 for r in recommendations if r.severity == "critical")
        n_warning = sum(1 for r in recommendations if r.severity == "warning")
        n_info = sum(1 for r in recommendations if r.severity == "info")
        total = len(recommendations)

        blocks: list[dict[str, Any]] = [
            # ── Header ────────────────────────────────────────────────────
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🔍 k8s-prometheus-analyzer — {total} issue(s) found",
                    "emoji": True,
                },
            },
            # ── Severity summary ──────────────────────────────────────────
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"🔴 *{n_critical} critical*  "
                        f"🟡 *{n_warning} warning*  "
                        f"🟢 *{n_info} info*"
                    ),
                },
            },
            {"type": "divider"},
        ]

        # ── Workload sections (capped) ─────────────────────────────────────
        shown = recommendations[:_MAX_WORKLOADS_IN_MESSAGE]
        remainder = total - len(shown)

        for rec in shown:
            icon = _SEVERITY_ICON.get(rec.severity, "⚪")
            suggestion_text = "\n".join(f"• {s}" for s in rec.suggestions)
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"{icon} *{rec.workload_name}* ({rec.workload_kind})"
                            f" — `{rec.namespace}`\n"
                            f"{suggestion_text}"
                        ),
                    },
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Replicas:* {rec.replica_count}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": (
                                f"*CPU/pod:* {rec.cpu_usage:.2f} cores"
                                f" ({rec.cpu_usage_pct:.0f}%)"
                            ),
                        },
                        {
                            "type": "mrkdwn",
                            "text": (
                                f"*Mem/pod:* {rec.memory_usage_mb:.0f} MB"
                                f" ({rec.memory_usage_pct:.0f}%)"
                            ),
                        },
                    ],
                }
            )

        if remainder > 0:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"_…and {remainder} more workload(s). See the full report._",
                    },
                }
            )

        # ── Footer ────────────────────────────────────────────────────────
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Prometheus: {prometheus_url} | {ts}",
                    }
                ],
            }
        )

        payload: dict[str, Any] = {
            "username": self._cfg.username,
            "icon_emoji": self._cfg.icon_emoji,
            "text": f"k8s-prometheus-analyzer: {total} issue(s) found",
            "blocks": blocks,
        }
        if self._cfg.channel:
            payload["channel"] = self._cfg.channel

        return payload
