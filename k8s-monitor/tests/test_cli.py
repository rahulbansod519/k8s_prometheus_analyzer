"""End-to-end CLI tests for k8s_prometheus_analyzer.cli."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import jwt
import pytest

from k8s_prometheus_analyzer import cli
from k8s_prometheus_analyzer.exceptions import PrometheusConnectionError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_cli(*argv: str) -> int:
    """Invoke main() with the given argv and capture the SystemExit code."""
    with patch("sys.argv", ["k8s-analyze", *argv]):
        try:
            cli.main()
        except SystemExit as exc:
            code = exc.code
            if isinstance(code, int):
                return code
            if isinstance(code, str):
                try:
                    return int(code)
                except ValueError:
                    return 3
            return 0
    return 0


def _mock_client(mocker, *, available: bool = True, metrics: dict | None = None):
    """Patch PrometheusClient so it doesn't hit the network."""
    mock = mocker.MagicMock()
    if not available:
        mock.check_availability.side_effect = PrometheusConnectionError("unreachable")
    else:
        mock.check_availability.return_value = None
        mock.query_all.return_value = metrics or {
            "cpu_usage": [], "memory_usage": [], "cpu_requests": [], "memory_requests": [],
            "pod_owner": [], "rs_owner": [],
        }
    mocker.patch("k8s_prometheus_analyzer.cli.PrometheusClient", return_value=mock)
    return mock


# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------


def test_help_exits_zero():
    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.argv", ["k8s-analyze", "--help"]):
            cli._build_parser().parse_args(["--help"])
    assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# Exit code 3 — Prometheus not reachable
# ---------------------------------------------------------------------------


def test_exit_code_3_when_prometheus_unreachable(mocker, tmp_path):
    _mock_client(mocker, available=False)
    code = _run_cli(
        "--prometheus-url", "http://nowhere:9090",
        "--output", str(tmp_path / "out.json"),
    )
    assert code == cli.EXIT_ERROR


# ---------------------------------------------------------------------------
# Exit code 0 — no recommendations
# ---------------------------------------------------------------------------


def test_exit_code_0_when_no_recommendations(mocker, tmp_path):
    _mock_client(mocker, metrics={
        "cpu_usage": [], "memory_usage": [], "cpu_requests": [], "memory_requests": [],
    })
    code = _run_cli(
        "--prometheus-url", "http://prom:9090",
        "--output", str(tmp_path / "out.json"),
        "--log-level", "ERROR",   # suppress noise
    )
    assert code == cli.EXIT_OK


# ---------------------------------------------------------------------------
# Exit code 1 — warnings only
# ---------------------------------------------------------------------------


def test_exit_code_1_when_warnings_found(mocker, tmp_path):
    # A pod with low CPU → info-level recommendation → exit 1
    _mock_client(mocker, metrics={
        "cpu_usage": [{"metric": {"pod": "p", "namespace": "default"}, "value": [0, "0.01"]}],
        "memory_usage": [{"metric": {"pod": "p", "namespace": "default"}, "value": [0, str(10 * 1024**2)]}],
        "cpu_requests": [{"metric": {"pod": "p", "namespace": "default"}, "value": [0, "1.0"]}],
        "memory_requests": [{"metric": {"pod": "p", "namespace": "default"}, "value": [0, str(64 * 1024**2)]}],
        "pod_owner": [], "rs_owner": [],
    })
    code = _run_cli(
        "--prometheus-url", "http://prom:9090",
        "--output", str(tmp_path / "out.json"),
        "--log-level", "ERROR",
    )
    assert code in (cli.EXIT_WARNINGS, cli.EXIT_CRITICAL)


# ---------------------------------------------------------------------------
# Exit code 2 — critical issues
# ---------------------------------------------------------------------------


def test_exit_code_2_when_critical_found(mocker, tmp_path):
    # CPU throttled (usage 2.0 > request 1.0) → CRITICAL
    _mock_client(mocker, metrics={
        "cpu_usage": [{"metric": {"pod": "p", "namespace": "default"}, "value": [0, "2.0"]}],
        "memory_usage": [],
        "cpu_requests": [{"metric": {"pod": "p", "namespace": "default"}, "value": [0, "1.0"]}],
        "memory_requests": [],
        "pod_owner": [], "rs_owner": [],
    })
    code = _run_cli(
        "--prometheus-url", "http://prom:9090",
        "--output", str(tmp_path / "out.json"),
        "--log-level", "ERROR",
    )
    assert code == cli.EXIT_CRITICAL


# ---------------------------------------------------------------------------
# JSON output file is created
# ---------------------------------------------------------------------------


def test_json_output_file_is_created(mocker, tmp_path):
    out_file = tmp_path / "results.json"
    _mock_client(mocker)
    _run_cli(
        "--prometheus-url", "http://prom:9090",
        "--output", str(out_file),
        "--log-level", "ERROR",
    )
    assert out_file.exists()
    data = json.loads(out_file.read_text())
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Config file flag
# ---------------------------------------------------------------------------


def test_config_file_flag_is_respected(mocker, tmp_path):
    import yaml

    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(yaml.dump({"prometheus_url": "http://yaml-prom:9090"}))

    captured_url = {}

    def fake_client_init(self, cfg):
        captured_url["url"] = cfg.prometheus_url
        self._cfg = cfg
        self.check_availability = MagicMock()
        self.query_all = MagicMock(return_value={
            "cpu_usage": [], "memory_usage": [], "cpu_requests": [],
            "memory_requests": [], "pod_owner": [], "rs_owner": [],
        })
    mocker.patch.object(cli.PrometheusClient, "__init__", fake_client_init)

    _run_cli("--config", str(cfg_file), "--output", str(tmp_path / "out.json"), "--log-level", "ERROR")
    assert captured_url.get("url") == "http://yaml-prom:9090"


# ---------------------------------------------------------------------------
# CLI args override config file
# ---------------------------------------------------------------------------


def test_cli_args_override_config_file(mocker, tmp_path):
    import yaml

    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(yaml.dump({"prometheus_url": "http://yaml-prom:9090"}))

    captured_url = {}

    def fake_client_init(self, cfg):
        captured_url["url"] = cfg.prometheus_url
        self._cfg = cfg
        self.check_availability = MagicMock()
        self.query_all = MagicMock(return_value={
            "cpu_usage": [], "memory_usage": [], "cpu_requests": [],
            "memory_requests": [], "pod_owner": [], "rs_owner": [],
        })

    mocker.patch.object(cli.PrometheusClient, "__init__", fake_client_init)

    _run_cli(
        "--config", str(cfg_file),
        "--prometheus-url", "http://cli-override:9090",
        "--output", str(tmp_path / "out.json"),
        "--log-level", "ERROR",
    )
    assert captured_url.get("url") == "http://cli-override:9090"


# ---------------------------------------------------------------------------
# Licensing Integration Tests
# ---------------------------------------------------------------------------


def test_cli_community_limit_under(mocker, tmp_path):
    """Under 15 nodes should run successfully in community mode."""
    _mock_client(mocker)
    mocker.patch("k8s_prometheus_analyzer.cli.get_node_count", return_value=10)
    code = _run_cli(
        "--prometheus-url", "http://prom:9090",
        "--output", str(tmp_path / "out.json"),
        "--log-level", "ERROR",
    )
    assert code == cli.EXIT_OK


def test_cli_community_limit_over(mocker, tmp_path):
    """Over 15 nodes should fail in community mode (exit code 3)."""
    _mock_client(mocker)
    mocker.patch("k8s_prometheus_analyzer.cli.get_node_count", return_value=25)
    code = _run_cli(
        "--prometheus-url", "http://prom:9090",
        "--output", str(tmp_path / "out.json"),
        "--log-level", "ERROR",
    )
    assert code == cli.EXIT_ERROR


def test_cli_enterprise_license_valid(mocker, tmp_path):
    """Valid enterprise license should allow running on larger clusters."""
    from .test_license import TEST_PRIVATE_KEY, TEST_PUBLIC_KEY

    # Generate a valid JWT for 100 nodes
    payload = {
        "sub": "acme-corp",
        "exp": int(time.time()) + 3600,
        "limits": {"nodes": 100},
    }
    token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")

    license_file = tmp_path / "license.jwt"
    license_file.write_text(token)

    _mock_client(mocker)
    mocker.patch("k8s_prometheus_analyzer.cli.get_node_count", return_value=50)
    mocker.patch("k8s_prometheus_analyzer.license.get_public_key", return_value=TEST_PUBLIC_KEY)

    code = _run_cli(
        "--prometheus-url", "http://prom:9090",
        "--output", str(tmp_path / "out.json"),
        "--license-file", str(license_file),
        "--log-level", "ERROR",
    )
    assert code == cli.EXIT_OK


def test_cli_enterprise_license_exceeded(mocker, tmp_path):
    """Exceeding the licensed node count should fail (exit code 3)."""
    from .test_license import TEST_PRIVATE_KEY, TEST_PUBLIC_KEY

    payload = {
        "sub": "acme-corp",
        "exp": int(time.time()) + 3600,
        "limits": {"nodes": 100},
    }
    token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")

    license_file = tmp_path / "license.jwt"
    license_file.write_text(token)

    _mock_client(mocker)
    mocker.patch("k8s_prometheus_analyzer.cli.get_node_count", return_value=120)
    mocker.patch("k8s_prometheus_analyzer.license.get_public_key", return_value=TEST_PUBLIC_KEY)

    code = _run_cli(
        "--prometheus-url", "http://prom:9090",
        "--output", str(tmp_path / "out.json"),
        "--license-file", str(license_file),
        "--log-level", "ERROR",
    )
    assert code == cli.EXIT_ERROR


def test_cli_enterprise_license_expired(mocker, tmp_path):
    """An expired enterprise license should fail (exit code 3)."""
    from .test_license import TEST_PRIVATE_KEY, TEST_PUBLIC_KEY

    payload = {
        "sub": "acme-corp",
        "exp": int(time.time()) - 3600,
        "limits": {"nodes": 100},
    }
    token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")

    license_file = tmp_path / "license.jwt"
    license_file.write_text(token)

    _mock_client(mocker)
    mocker.patch("k8s_prometheus_analyzer.cli.get_node_count", return_value=50)
    mocker.patch("k8s_prometheus_analyzer.license.get_public_key", return_value=TEST_PUBLIC_KEY)

    code = _run_cli(
        "--prometheus-url", "http://prom:9090",
        "--output", str(tmp_path / "out.json"),
        "--license-file", str(license_file),
        "--log-level", "ERROR",
    )
    assert code == cli.EXIT_ERROR

