"""Generic HTTP webhook alert channel."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from ..analyzer import Recommendation
from ..config import WebhookAlertConfig
from ..exceptions import AlertDeliveryError
from .base import AlertChannel

logger = logging.getLogger(__name__)


class WebhookChannel(AlertChannel):
    """Delivers alerts as a JSON POST (or GET) to any HTTP endpoint.

    Suitable for PagerDuty, Microsoft Teams, Opsgenie, or custom receivers.

    Args:
        cfg: :class:`~k8s_prometheus_analyzer.config.WebhookAlertConfig`.
    """

    def __init__(self, cfg: WebhookAlertConfig) -> None:
        self._cfg = cfg

    # ------------------------------------------------------------------
    # AlertChannel implementation
    # ------------------------------------------------------------------

    def send(self, recommendations: list[Recommendation], prometheus_url: str) -> None:
        payload = self._build_payload(recommendations, prometheus_url)

        try:
            resp = requests.request(
                method=self._cfg.method.upper(),
                url=self._cfg.url,
                json=payload,
                headers=self._cfg.headers,
                timeout=self._cfg.timeout,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise AlertDeliveryError(f"Webhook request to {self._cfg.url} failed: {exc}") from exc

        logger.info(
            "Webhook alert delivered to %s — %d recommendation(s) reported",
            self._cfg.url,
            len(recommendations),
        )

    # ------------------------------------------------------------------
    # Payload construction
    # ------------------------------------------------------------------

    def _build_payload(
        self, recommendations: list[Recommendation], prometheus_url: str
    ) -> dict[str, Any]:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "timestamp": ts,
            "prometheus_url": prometheus_url,
            "total": len(recommendations),
            "critical": sum(1 for r in recommendations if r.severity == "critical"),
            "warning": sum(1 for r in recommendations if r.severity == "warning"),
            "info": sum(1 for r in recommendations if r.severity == "info"),
            "recommendations": [r.to_dict() for r in recommendations],
        }
