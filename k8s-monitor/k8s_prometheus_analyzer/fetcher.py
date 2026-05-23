"""Prometheus HTTP client with authentication, TLS, and retry support."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Config
from .exceptions import PrometheusConnectionError, PrometheusQueryError

logger = logging.getLogger(__name__)

# PromQL queries executed on every run
DEFAULT_QUERIES: dict[str, str] = {
    "cpu_usage": (
        'sum(rate(container_cpu_usage_seconds_total{container!=""}[5m])) by (pod, namespace)'
    ),
    "memory_usage": (
        'sum(container_memory_usage_bytes{container!=""}) by (pod, namespace)'
    ),
    "cpu_requests": (
        'sum(kube_pod_container_resource_requests{resource="cpu"}) by (pod, namespace)'
    ),
    "memory_requests": (
        'sum(kube_pod_container_resource_requests{resource="memory"}) by (pod, namespace)'
    ),
    # Workload ownership — used to group pods by Deployment / StatefulSet / etc.
    "pod_owner": 'kube_pod_owner{owner_is_controller="true"}',
    "rs_owner":  'kube_replicaset_owner{owner_kind="Deployment"}',
}


def _build_url(base: str, path: str) -> str:
    """Safely join *base* URL with *path*, ignoring any existing path in *base*."""
    parsed = urlparse(base)
    clean_base = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    return urljoin(clean_base + "/", path.lstrip("/"))


def _build_session(cfg: Config) -> requests.Session:
    """Create a :class:`requests.Session` pre-configured with auth, TLS, and retries."""
    session = requests.Session()

    # --- Authentication ---
    if cfg.auth_type == "bearer":
        if not cfg.token:
            raise PrometheusConnectionError(
                "auth_type is 'bearer' but no token was provided"
            )
        session.headers.update({"Authorization": f"Bearer {cfg.token}"})
    elif cfg.auth_type == "basic":
        if not cfg.username:
            raise PrometheusConnectionError(
                "auth_type is 'basic' but no username was provided"
            )
        session.auth = (cfg.username, cfg.password)

    # --- TLS ---
    if cfg.ca_cert:
        session.verify = cfg.ca_cert
    elif not cfg.verify_ssl:
        session.verify = False
        import urllib3  # noqa: PLC0415

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        logger.warning("SSL verification is disabled — do NOT use this in production")

    # --- Retry strategy ---
    retry = Retry(
        total=cfg.retries,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


class PrometheusClient:
    """High-level Prometheus API client.

    Args:
        cfg: Fully-populated :class:`~k8s_prometheus_analyzer.config.Config`.
    """

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._session = _build_session(cfg)
        self._query_url = _build_url(cfg.prometheus_url, "/api/v1/query")
        self._health_url = _build_url(cfg.prometheus_url, "/-/healthy")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_availability(self) -> None:
        """Verify that Prometheus is reachable.

        Raises:
            PrometheusConnectionError: If the health endpoint cannot be reached
                or returns a non-2xx status.
        """
        try:
            resp = self._session.get(self._health_url, timeout=self._cfg.timeout)
            resp.raise_for_status()
            logger.info("Prometheus is reachable at %s", self._cfg.prometheus_url)
        except requests.exceptions.ConnectionError as exc:
            raise PrometheusConnectionError(
                f"Cannot connect to Prometheus at {self._cfg.prometheus_url}: {exc}"
            ) from exc
        except requests.exceptions.Timeout:
            raise PrometheusConnectionError(
                f"Prometheus at {self._cfg.prometheus_url} timed out after "
                f"{self._cfg.timeout}s"
            )
        except requests.exceptions.HTTPError as exc:
            raise PrometheusConnectionError(
                f"Prometheus health check returned {exc.response.status_code}"
            ) from exc

    def query(self, promql: str) -> list[dict[str, Any]]:
        """Execute a single instant PromQL query.

        Args:
            promql: A valid PromQL expression.

        Returns:
            The ``result`` list from the Prometheus API response.

        Raises:
            PrometheusQueryError: On HTTP error or malformed response.
        """
        try:
            resp = self._session.get(
                self._query_url,
                params={"query": promql},
                timeout=self._cfg.timeout,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise PrometheusQueryError(f"Query failed: {exc}") from exc

        try:
            payload = resp.json()
            result: list[dict[str, Any]] = payload["data"]["result"]
            return result
        except (KeyError, ValueError) as exc:
            raise PrometheusQueryError(
                f"Unexpected Prometheus response format: {exc}"
            ) from exc

    def query_all(
        self, queries: dict[str, str] | None = None
    ) -> dict[str, list[dict[str, Any]]]:
        """Execute all queries and return results keyed by metric name.

        Args:
            queries: Mapping of metric name → PromQL. Defaults to
                :data:`DEFAULT_QUERIES`.

        Returns:
            Dict mapping metric name to the list of Prometheus result items.
        """
        queries = queries or DEFAULT_QUERIES
        results: dict[str, list[dict[str, Any]]] = {}
        for name, promql in queries.items():
            logger.debug("Querying Prometheus for '%s'", name)
            try:
                results[name] = self.query(promql)
            except PrometheusQueryError:
                logger.warning("Query '%s' failed — using empty result set", name)
                results[name] = []
        return results
