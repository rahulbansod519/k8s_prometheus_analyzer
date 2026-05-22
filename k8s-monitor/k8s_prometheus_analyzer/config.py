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
    thresholds: Thresholds = field(default_factory=Thresholds)


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


def _apply_dict(cfg: Config, data: dict[str, Any]) -> None:
    """Overwrite *cfg* fields that appear in *data* (in-place)."""
    thresholds_data: dict[str, Any] = data.pop("thresholds", {})

    for f in fields(cfg):
        if f.name == "thresholds" or f.name not in data:
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


def _apply_env(cfg: Config) -> None:
    """Overwrite *cfg* fields from environment variables (K8S_ANALYZER_*) in-place."""
    for key, raw in os.environ.items():
        if not key.startswith(_ENV_PREFIX):
            continue
        field_name = key[len(_ENV_PREFIX) :].lower()
        for f in fields(cfg):
            if f.name != field_name:
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
