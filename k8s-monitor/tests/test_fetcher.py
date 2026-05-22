"""Unit tests for k8s_prometheus_analyzer.fetcher (PrometheusClient)."""

from __future__ import annotations

import pytest
import requests

from k8s_prometheus_analyzer.config import Config
from k8s_prometheus_analyzer.exceptions import PrometheusConnectionError, PrometheusQueryError
from k8s_prometheus_analyzer.fetcher import PrometheusClient, _build_url

# ---------------------------------------------------------------------------
# URL building helper
# ---------------------------------------------------------------------------


def test_build_url_strips_existing_path():
    assert _build_url("http://prom:9090/some/path", "/api/v1/query") == "http://prom:9090/api/v1/query"


def test_build_url_no_trailing_slash():
    assert _build_url("http://prom:9090", "/-/healthy") == "http://prom:9090/-/healthy"


def test_build_url_handles_trailing_slash_on_base():
    assert _build_url("http://prom:9090/", "/api/v1/query") == "http://prom:9090/api/v1/query"


# ---------------------------------------------------------------------------
# Auth header tests (inspect the session directly)
# ---------------------------------------------------------------------------


def test_bearer_auth_sets_header():
    cfg = Config(auth_type="bearer", token="mysecrettoken")
    client = PrometheusClient(cfg)
    assert client._session.headers.get("Authorization") == "Bearer mysecrettoken"


def test_basic_auth_sets_auth_tuple():
    cfg = Config(auth_type="basic", username="admin", password="pass123")
    client = PrometheusClient(cfg)
    assert client._session.auth == ("admin", "pass123")


def test_no_auth_does_not_set_header():
    cfg = Config(auth_type="none")
    client = PrometheusClient(cfg)
    assert "Authorization" not in client._session.headers


def test_bearer_missing_token_raises():
    cfg = Config(auth_type="bearer", token="")
    with pytest.raises(PrometheusConnectionError, match="no token"):
        PrometheusClient(cfg)


def test_basic_missing_username_raises():
    cfg = Config(auth_type="basic", username="", password="p")
    with pytest.raises(PrometheusConnectionError, match="no username"):
        PrometheusClient(cfg)


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> PrometheusClient:
    return PrometheusClient(Config(prometheus_url="http://prom:9090"))


@pytest.mark.parametrize("exc_class", [
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
])
def test_check_availability_raises_on_network_error(client, mocker, exc_class):
    mocker.patch.object(client._session, "get", side_effect=exc_class("boom"))
    with pytest.raises(PrometheusConnectionError):
        client.check_availability()


def test_check_availability_raises_on_http_error(client, mocker):
    mock_resp = mocker.MagicMock()
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=mocker.MagicMock(status_code=503)
    )
    mocker.patch.object(client._session, "get", return_value=mock_resp)
    with pytest.raises(PrometheusConnectionError):
        client.check_availability()


def test_check_availability_succeeds(client, mocker):
    mock_resp = mocker.MagicMock()
    mock_resp.raise_for_status.return_value = None
    mocker.patch.object(client._session, "get", return_value=mock_resp)
    client.check_availability()  # should not raise


# ---------------------------------------------------------------------------
# query()
# ---------------------------------------------------------------------------


def _make_prom_response(result: list) -> dict:
    return {"status": "success", "data": {"resultType": "vector", "result": result}}


def test_query_returns_result_list(client, mocker):
    expected = [{"metric": {"pod": "p"}, "value": [0, "1.0"]}]
    mock_resp = mocker.MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = _make_prom_response(expected)
    mocker.patch.object(client._session, "get", return_value=mock_resp)

    result = client.query("up")
    assert result == expected


def test_query_raises_on_http_error(client, mocker):
    mocker.patch.object(
        client._session, "get",
        side_effect=requests.exceptions.HTTPError("500"),
    )
    with pytest.raises(PrometheusQueryError):
        client.query("up")


def test_query_raises_on_malformed_response(client, mocker):
    mock_resp = mocker.MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"unexpected": "shape"}
    mocker.patch.object(client._session, "get", return_value=mock_resp)
    with pytest.raises(PrometheusQueryError):
        client.query("up")


# ---------------------------------------------------------------------------
# query_all()
# ---------------------------------------------------------------------------


def test_query_all_returns_all_keys(client, mocker):
    mock_result = [{"metric": {}, "value": [0, "1"]}]
    mocker.patch.object(client, "query", return_value=mock_result)

    results = client.query_all()
    for key in ("cpu_usage", "memory_usage", "cpu_requests", "memory_requests"):
        assert key in results


def test_query_all_continues_on_partial_failure(client, mocker):
    """If one query raises, query_all should still return the other keys with []."""
    call_count = {"n": 0}

    def side_effect(promql):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise PrometheusQueryError("flaky")
        return []

    mocker.patch.object(client, "query", side_effect=side_effect)
    results = client.query_all()
    # Should have all 6 keys (4 metrics + pod_owner + rs_owner); the failing one gets []
    assert len(results) == 6
    assert all(isinstance(v, list) for v in results.values())
