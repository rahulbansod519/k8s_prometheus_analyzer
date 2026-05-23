"""Abstract base class for alert notification channels."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..analyzer import Recommendation


class AlertChannel(ABC):
    """Contract every alert channel must implement."""

    @abstractmethod
    def send(
        self,
        recommendations: list[Recommendation],
        prometheus_url: str,
    ) -> None:
        """Deliver an alert for the given recommendations.

        Args:
            recommendations: Pre-filtered list (already checked against
                ``on_severities`` by the dispatcher).
            prometheus_url:  The Prometheus base URL — included in the alert
                payload for traceability.

        Raises:
            AlertDeliveryError: If the notification cannot be delivered.
                The dispatcher catches this and logs a warning rather than
                crashing the tool.
        """
