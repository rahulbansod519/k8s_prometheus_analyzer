"""Custom exception hierarchy for k8s-prometheus-analyzer."""


class K8sAnalyzerError(Exception):
    """Base exception for all k8s-prometheus-analyzer errors."""


class PrometheusConnectionError(K8sAnalyzerError):
    """Raised when Prometheus is not reachable or returns an unexpected status."""


class PrometheusQueryError(K8sAnalyzerError):
    """Raised when a PromQL query fails or returns malformed data."""


class ConfigError(K8sAnalyzerError):
    """Raised when the configuration is invalid or cannot be loaded."""
