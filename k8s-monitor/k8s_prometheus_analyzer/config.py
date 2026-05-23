"""Configuration management for k8s-prometheus-analyzer.

Loading priority (highest wins):
    CLI args  >  environment variables (K8S_ANALYZER_*)  >  YAML file  >  built-in defaults
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

from .exceptions import ConfigError

logger = logging.getLogger(__name__)

_ENV_PREFIX = "K8S_ANALYZER_"

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------


@dataclass
class Thresholds:
    """Resource-utilisation thresholds that drive optimisation recommendations."""

    cpu_low: float = 0.1
    """CPU usage (cores) below which a pod is considered under-utilised."""

    mem_low_mb: float = 50.0
    """Memory usage (MB) below which a pod is considered under-utilised."""

    cpu_high_pct: float = 80.0
    """CPU utilisation % above which scaling is recommended."""

    mem_high_mb: float = 500.0
    """Memory usage (MB) above which limits should be reviewed."""

    mem_overcommit_ratio: float = 3.0
    """request/usage ratio above which memory over-provisioning is flagged."""

    replica_cpu_low: float = 0.05
    """CPU (cores) threshold for the 'consider reducing replicas' suggestion."""

    replica_mem_low_mb: float = 20.0
    """Memory (MB) threshold for the 'consider reducing replicas' suggestion."""


# ---------------------------------------------------------------------------
# Alert config
# ---------------------------------------------------------------------------


@dataclass
class SlackAlertConfig:
    """Slack incoming-webhook alert settings."""

    enabled: bool = False
    webhook_url: str = ""
    channel: str = ""           # optional — overrides the webhook's default channel
    username: str = "k8s-analyzer"
    icon_emoji: str = ":kubernetes:"


@dataclass
class WebhookAlertConfig:
    """Generic HTTP webhook alert settings."""

    enabled: bool = False
    url: str = ""
    method: str = "POST"        # "GET" | "POST"
    headers: dict = field(default_factory=dict)
    timeout: int = 10


@dataclass
class AlertConfig:
    """Top-level alert configuration block."""

    enabled: bool = False
    on_severities: list = field(default_factory=lambda: ["critical", "warning"])
    """Only recommendations with these severities will trigger an alert."""

    slack: SlackAlertConfig = field(default_factory=SlackAlertConfig)
    webhook: WebhookAlertConfig = field(default_factory=WebhookAlertConfig)


# ---------------------------------------------------------------------------
# Main Config
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """Top-level configuration for the analyser."""

    prometheus_url: str = "http://localhost:9090"
    auth_type: str = "none"          # "none" | "bearer" | "basic"
    token: str = ""
    username: str = ""
    password: str = ""
    ca_cert: str = ""
    verify_ssl: bool = True
    timeout: int = 10
    retries: int = 3
    log_level: str = "INFO"
    log_format: str = "text"         # "text" | "json"
    output: str = "optimization_suggestions.json"
    html_output: str = "optimization_report.html"
    thresholds: Thresholds = field(default_factory=Thresholds)
    alerts: AlertConfig = field(default_factory=AlertConfig)


# ---------------------------------------------------------------------------
# Loader helpers
# ---------------------------------------------------------------------------


def _coerce(current_val: Any, raw: str) -> Any:
    """Cast *raw* string to the same type as *current_val*."""
    if isinstance(current_val, bool):
        return raw.lower() in ("1", "true", "yes")
    if isinstance(current_val, int):
        return int(raw)
    if isinstance(current_val, float):
        return float(raw)
    return raw


def _apply_slack_dict(slack: SlackAlertConfig, data: dict[str, Any]) -> None:
    for f in fields(slack):
        if f.name not in data:
            continue
        try:
            setattr(slack, f.name, type(getattr(slack, f.name))(data[f.name]))
        except (ValueError, TypeError) as exc:
            logger.warning("Slack alert config '%s' invalid value %r: %s", f.name, data[f.name], exc)


def _apply_webhook_dict(wh: WebhookAlertConfig, data: dict[str, Any]) -> None:
    for f in fields(wh):
        if f.name not in data:
            continue
        if f.name == "headers":
            if isinstance(data[f.name], dict):
                wh.headers = data[f.name]
        else:
            try:
                setattr(wh, f.name, type(getattr(wh, f.name))(data[f.name]))
            except (ValueError, TypeError) as exc:
                logger.warning("Webhook alert config '%s' invalid value %r: %s", f.name, data[f.name], exc)


def _apply_alert_dict(alert: AlertConfig, data: dict[str, Any]) -> None:
    slack_data: dict[str, Any] = data.pop("slack", {})
    webhook_data: dict[str, Any] = data.pop("webhook", {})

    for f in fields(alert):
        if f.name in ("slack", "webhook") or f.name not in data:
            continue
        if f.name == "on_severities":
            val = data[f.name]
            if isinstance(val, list):
                alert.on_severities = [str(s) for s in val]
        else:
            try:
                setattr(alert, f.name, type(getattr(alert, f.name))(data[f.name]))
            except (ValueError, TypeError) as exc:
                logger.warning("Alert config '%s' invalid value %r: %s", f.name, data[f.name], exc)

    if slack_data:
        _apply_slack_dict(alert.slack, slack_data)
    if webhook_data:
        _apply_webhook_dict(alert.webhook, webhook_data)


def _apply_dict(cfg: Config, data: dict[str, Any]) -> None:
    """Overwrite *cfg* fields that appear in *data* (in-place)."""
    thresholds_data: dict[str, Any] = data.pop("thresholds", {})
    alerts_data: dict[str, Any] = data.pop("alerts", {})

    for f in fields(cfg):
        if f.name in ("thresholds", "alerts") or f.name not in data:
            continue
        val = data[f.name]
        current = getattr(cfg, f.name)
        try:
            setattr(cfg, f.name, type(current)(val))
        except (ValueError, TypeError) as exc:
            logger.warning("Config key '%s' has invalid value %r: %s", f.name, val, exc)

    if thresholds_data:
        thr = cfg.thresholds
        for f in fields(thr):
            if f.name in thresholds_data:
                try:
                    setattr(thr, f.name, float(thresholds_data[f.name]))
                except (ValueError, TypeError) as exc:
                    logger.warning(
                        "Threshold '%s' has invalid value %r: %s",
                        f.name,
                        thresholds_data[f.name],
                        exc,
                    )

    if alerts_data:
        _apply_alert_dict(cfg.alerts, alerts_data)


def _apply_env(cfg: Config) -> None:
    """Overwrite *cfg* fields from environment variables (K8S_ANALYZER_*) in-place."""
    _ALERT_PFX = _ENV_PREFIX + "ALERTS_"
    _SLACK_PFX = _ALERT_PFX + "SLACK_"
    _WEBHOOK_PFX = _ALERT_PFX + "WEBHOOK_"

    for key, raw in os.environ.items():
        if not key.startswith(_ENV_PREFIX):
            continue

        # ── Nested: Slack alert config ────────────────────────────────────
        if key.startswith(_SLACK_PFX):
            field_name = key[len(_SLACK_PFX):].lower()
            for f in fields(cfg.alerts.slack):
                if f.name == field_name:
                    current = getattr(cfg.alerts.slack, f.name)
                    try:
                        setattr(cfg.alerts.slack, f.name, _coerce(current, raw))
                    except (ValueError, TypeError):
                        logger.warning("Ignoring invalid env var %s=%r", key, raw)
            continue

        # ── Nested: webhook alert config ──────────────────────────────────
        if key.startswith(_WEBHOOK_PFX):
            field_name = key[len(_WEBHOOK_PFX):].lower()
            for f in fields(cfg.alerts.webhook):
                if f.name == field_name and f.name != "headers":
                    current = getattr(cfg.alerts.webhook, f.name)
                    try:
                        setattr(cfg.alerts.webhook, f.name, _coerce(current, raw))
                    except (ValueError, TypeError):
                        logger.warning("Ignoring invalid env var %s=%r", key, raw)
            continue

        # ── Nested: top-level alert config ────────────────────────────────
        if key.startswith(_ALERT_PFX):
            field_name = key[len(_ALERT_PFX):].lower()
            for f in fields(cfg.alerts):
                if f.name in ("slack", "webhook", "on_severities"):
                    continue
                if f.name == field_name:
                    current = getattr(cfg.alerts, f.name)
                    try:
                        setattr(cfg.alerts, f.name, _coerce(current, raw))
                    except (ValueError, TypeError):
                        logger.warning("Ignoring invalid env var %s=%r", key, raw)
            continue

        # ── Top-level config fields ───────────────────────────────────────
        field_name = key[len(_ENV_PREFIX):].lower()
        for f in fields(cfg):
            if f.name in ("thresholds", "alerts") or f.name != field_name:
                continue
            current = getattr(cfg, f.name)
            try:
                setattr(cfg, f.name, _coerce(current, raw))
            except (ValueError, TypeError):
                logger.warning(
                    "Ignoring invalid env var %s=%r (expected %s)",
                    key,
                    raw,
                    type(current).__name__,
                )


def load_config(config_file: str | Path | None = None) -> Config:
    """Return a :class:`Config` built by layering YAML file → env vars.

    CLI args are applied on top by the caller (``cli.py``).
    """
    cfg = Config()

    # Layer 1: YAML file
    if config_file:
        path = Path(config_file)
        if not path.exists():
            raise ConfigError(f"Config file not found: {path}")
        try:
            with path.open() as fh:
                data: dict[str, Any] = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML in config file '{path}': {exc}") from exc
        _apply_dict(cfg, data)

    # Layer 2: Environment variables
    _apply_env(cfg)

    return cfg
