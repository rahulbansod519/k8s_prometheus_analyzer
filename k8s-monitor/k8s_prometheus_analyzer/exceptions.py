"""Custom exception hierarchy for k8s-prometheus-analyzer."""


class K8sAnalyzerError(Exception):
    """Base exception for all k8s-prometheus-analyzer errors."""


class PrometheusConnectionError(K8sAnalyzerError):
    """Raised when Prometheus cannot be reached or returns a non-2xx status."""


class PrometheusQueryError(K8sAnalyzerError):
    """Raised when a PromQL query fails or returns an unexpected payload."""


class ConfigError(K8sAnalyzerError):
    """Raised when configuration is invalid or a required file is missing."""


class AlertDeliveryError(K8sAnalyzerError):
    """Raised when an alert cannot be delivered to a notification channel."""


class LicenseError(K8sAnalyzerError):
    """Base exception for all license-related errors."""


class LicenseSignatureError(LicenseError):
    """Raised when the license token signature is invalid or tampered with."""


class LicenseExpiredError(LicenseError):
    """Raised when the license token has expired."""


class LicenseLimitExceededError(LicenseError):
    """Raised when the node limit is exceeded for community or enterprise tier."""

