"""Unit tests for k8s_prometheus_analyzer.config."""

from __future__ import annotations

import pytest
import yaml

from k8s_prometheus_analyzer.config import Config, Thresholds, load_config
from k8s_prometheus_analyzer.exceptions import ConfigError

# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


def test_default_config_values():
    cfg = Config()
    assert cfg.prometheus_url == "http://localhost:9090"
    assert cfg.auth_type == "none"
    assert cfg.verify_ssl is True
    assert cfg.timeout == 10
    assert cfg.retries == 3
    assert cfg.log_level == "INFO"
    assert cfg.log_format == "text"


def test_default_thresholds():
    thr = Thresholds()
    assert thr.cpu_low == 0.1
    assert thr.mem_low_mb == 50.0
    assert thr.cpu_high_pct == 80.0
    assert thr.mem_overcommit_ratio == 3.0


# ---------------------------------------------------------------------------
# load_config — no file, no env
# ---------------------------------------------------------------------------


def test_load_config_no_args_returns_defaults():
    cfg = load_config()
    assert cfg.prometheus_url == "http://localhost:9090"


# ---------------------------------------------------------------------------
# YAML file loading
# ---------------------------------------------------------------------------


def test_load_config_from_yaml(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.dump({
            "prometheus_url": "http://prom:9090",
            "auth_type": "bearer",
            "token": "abc123",
            "timeout": 30,
            "thresholds": {"cpu_low": 0.2, "mem_high_mb": 1000.0},
        })
    )
    cfg = load_config(config_file=str(config_file))
    assert cfg.prometheus_url == "http://prom:9090"
    assert cfg.auth_type == "bearer"
    assert cfg.token == "abc123"
    assert cfg.timeout == 30
    assert cfg.thresholds.cpu_low == 0.2
    assert cfg.thresholds.mem_high_mb == 1000.0


def test_load_config_missing_file_raises():
    with pytest.raises(ConfigError, match="not found"):
        load_config(config_file="/nonexistent/path/config.yaml")


def test_load_config_invalid_yaml_raises(tmp_path):
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("key: [\ninvalid yaml")
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_config(config_file=str(bad_file))


def test_load_config_empty_yaml_returns_defaults(tmp_path):
    empty_file = tmp_path / "empty.yaml"
    empty_file.write_text("")
    cfg = load_config(config_file=str(empty_file))
    assert cfg.prometheus_url == "http://localhost:9090"


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------


def test_env_var_overrides_prometheus_url(monkeypatch):
    monkeypatch.setenv("K8S_ANALYZER_PROMETHEUS_URL", "http://env-prom:9090")
    cfg = load_config()
    assert cfg.prometheus_url == "http://env-prom:9090"


def test_env_var_bool_true(monkeypatch):
    monkeypatch.setenv("K8S_ANALYZER_VERIFY_SSL", "false")
    cfg = load_config()
    assert cfg.verify_ssl is False


def test_env_var_bool_variants(monkeypatch):
    for truthy in ("1", "true", "yes", "True", "YES"):
        monkeypatch.setenv("K8S_ANALYZER_VERIFY_SSL", truthy)
        cfg = load_config()
        assert cfg.verify_ssl is True, f"Expected True for '{truthy}'"

    for falsy in ("0", "false", "no", "False"):
        monkeypatch.setenv("K8S_ANALYZER_VERIFY_SSL", falsy)
        cfg = load_config()
        assert cfg.verify_ssl is False, f"Expected False for '{falsy}'"


def test_env_var_int(monkeypatch):
    monkeypatch.setenv("K8S_ANALYZER_TIMEOUT", "60")
    cfg = load_config()
    assert cfg.timeout == 60


def test_env_var_invalid_int_ignored(monkeypatch, caplog):
    monkeypatch.setenv("K8S_ANALYZER_TIMEOUT", "not-a-number")
    import logging
    with caplog.at_level(logging.WARNING):
        cfg = load_config()
    assert cfg.timeout == 10  # default preserved
    assert any("K8S_ANALYZER_TIMEOUT" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# YAML file + env var interaction (env wins)
# ---------------------------------------------------------------------------


def test_env_var_overrides_yaml(tmp_path, monkeypatch):
    config_file = tmp_path / "cfg.yaml"
    config_file.write_text(yaml.dump({"prometheus_url": "http://yaml-prom:9090"}))
    monkeypatch.setenv("K8S_ANALYZER_PROMETHEUS_URL", "http://env-prom:9090")

    cfg = load_config(config_file=str(config_file))
    assert cfg.prometheus_url == "http://env-prom:9090"
