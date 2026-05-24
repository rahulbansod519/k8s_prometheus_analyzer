"""Unit tests for GitOps auto-PR functionality and manifest editing."""

from __future__ import annotations

import base64

import pytest
import yaml

from k8s_prometheus_analyzer.analyzer import Recommendation
from k8s_prometheus_analyzer.config import Config
from k8s_prometheus_analyzer.exceptions import K8sAnalyzerError
from k8s_prometheus_analyzer.gitops import open_github_pr, update_yaml_manifest

SAMPLE_MANIFEST = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: billing-service
  namespace: finance
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: web
          image: nginx:latest
          resources:
            requests:
              cpu: 500m
              memory: 256Mi
"""

SAMPLE_MULTI_MANIFEST = """apiVersion: v1
kind: Namespace
metadata:
  name: finance
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: billing-service
  namespace: finance
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: web
          resources:
            requests:
              cpu: 500m
              memory: 256Mi
"""


@pytest.fixture()
def mock_recommendations() -> list[Recommendation]:
    return [
        Recommendation(
            workload_name="billing-service",
            workload_kind="Deployment",
            namespace="finance",
            replica_count=2,
            cpu_usage=0.1,  # 100m usage
            memory_usage_mb=100.0,  # 100Mi usage
            suggestions=["Reduce CPU requests", "Reduce memory requests"],
            reasons=["CPU usage is low", "Memory usage is low"],
            severity="warning",
        )
    ]


def test_update_yaml_manifest_success(mock_recommendations):
    """Verify that update_yaml_manifest correctly resizes containers in a manifest."""
    updated = update_yaml_manifest(SAMPLE_MANIFEST, mock_recommendations)
    parsed = yaml.safe_load(updated)

    container = parsed["spec"]["template"]["spec"]["containers"][0]
    # CPU: usage 0.1 * 1.25 = 0.125 cores -> 125m
    assert container["resources"]["requests"]["cpu"] == "125m"
    # Memory: usage 100 * 1.20 = 120MB -> 120Mi
    assert container["resources"]["requests"]["memory"] == "120Mi"


def test_update_yaml_manifest_multi_document(mock_recommendations):
    """Verify that update_yaml_manifest handles multi-document files, modifying only matching workloads."""
    updated = update_yaml_manifest(SAMPLE_MULTI_MANIFEST, mock_recommendations)
    docs = list(yaml.safe_load_all(updated))

    assert len(docs) == 2
    # Namespace doc remains unchanged
    assert docs[0]["kind"] == "Namespace"
    # Deployment doc is updated
    container = docs[1]["spec"]["template"]["spec"]["containers"][0]
    assert container["resources"]["requests"]["cpu"] == "125m"
    assert container["resources"]["requests"]["memory"] == "120Mi"


def test_update_yaml_manifest_no_matching_workload(mock_recommendations):
    """Verify that update_yaml_manifest returns the original content if no workloads match."""
    # Recommendation for non-matching service
    recs = [
        Recommendation(
            workload_name="other-service",
            workload_kind="Deployment",
            namespace="finance",
            replica_count=1,
            cpu_usage=0.1,
            memory_usage_mb=50.0,
            suggestions=["Reduce CPU requests"],
        )
    ]
    updated = update_yaml_manifest(SAMPLE_MANIFEST, recs)
    assert updated == SAMPLE_MANIFEST


def test_open_github_pr_success(requests_mock, mock_recommendations):
    """Verify the entire successful GitHub API flow for creating a PR."""
    cfg = Config()
    cfg.gitops.enabled = True
    cfg.gitops.github_token = "mock-token"
    cfg.gitops.github_repo = "owner/repo"
    cfg.gitops.github_branch = "main"
    cfg.gitops.manifest_path = "deploy/deployment.yaml"

    base_url = "https://api.github.com/repos/owner/repo"

    # Mock 1: Base branch SHA lookup
    requests_mock.get(
        f"{base_url}/git/ref/heads/main",
        json={"object": {"sha": "base-sha-12345"}},
    )

    # Mock 2: Branch ref creation
    requests_mock.post(
        f"{base_url}/git/refs",
        status_code=201,
    )

    # Mock 3: Get manifest file contents
    encoded_manifest = base64.b64encode(SAMPLE_MANIFEST.encode("utf-8")).decode("utf-8")
    requests_mock.get(
        f"{base_url}/contents/deploy/deployment.yaml?ref=main",
        json={"sha": "file-sha-abc", "content": encoded_manifest},
    )

    # Mock 4: Update manifest content (commit)
    requests_mock.put(
        f"{base_url}/contents/deploy/deployment.yaml",
        status_code=200,
    )

    # Mock 5: Open Pull Request
    requests_mock.post(
        f"{base_url}/pulls",
        status_code=201,
        json={"html_url": "https://github.com/owner/repo/pull/42"},
    )

    pr_url = open_github_pr(cfg, mock_recommendations)
    assert pr_url == "https://github.com/owner/repo/pull/42"

    # Verify authorization header was passed
    last_req = requests_mock.last_request
    assert last_req.headers.get("Authorization") == "token mock-token"


def test_open_github_pr_missing_config():
    """Verify that open_github_pr raises K8sAnalyzerError on missing config parameters."""
    cfg = Config()
    cfg.gitops.enabled = True
    # Missing token, repo, manifest

    with pytest.raises(K8sAnalyzerError, match="GitHub Token must be provided"):
        open_github_pr(cfg, [])

    cfg.gitops.github_token = "token"
    with pytest.raises(K8sAnalyzerError, match="Target GitHub repository"):
        open_github_pr(cfg, [])

    cfg.gitops.github_repo = "owner/repo"
    with pytest.raises(K8sAnalyzerError, match="Target manifest path"):
        open_github_pr(cfg, [])


def test_open_github_pr_branch_not_found(requests_mock, mock_recommendations):
    """Verify that a 404 on base branch retrieval raises K8sAnalyzerError."""
    cfg = Config()
    cfg.gitops.enabled = True
    cfg.gitops.github_token = "token"
    cfg.gitops.github_repo = "owner/repo"
    cfg.gitops.github_branch = "invalid-branch"
    cfg.gitops.manifest_path = "deploy.yaml"

    requests_mock.get(
        "https://api.github.com/repos/owner/repo/git/ref/heads/invalid-branch",
        status_code=404,
    )

    with pytest.raises(K8sAnalyzerError, match="Base branch 'invalid-branch' or repository not found"):
        open_github_pr(cfg, mock_recommendations)


def test_open_github_pr_no_updates(requests_mock):
    """Verify that K8sAnalyzerError is raised if no workloads match in the manifest."""
    cfg = Config()
    cfg.gitops.enabled = True
    cfg.gitops.github_token = "token"
    cfg.gitops.github_repo = "owner/repo"
    cfg.gitops.github_branch = "main"
    cfg.gitops.manifest_path = "deploy.yaml"

    base_url = "https://api.github.com/repos/owner/repo"

    requests_mock.get(
        f"{base_url}/git/ref/heads/main",
        json={"object": {"sha": "base-sha"}},
    )
    requests_mock.post(
        f"{base_url}/git/refs",
        status_code=201,
    )
    encoded_manifest = base64.b64encode(SAMPLE_MANIFEST.encode("utf-8")).decode("utf-8")
    requests_mock.get(
        f"{base_url}/contents/deploy.yaml?ref=main",
        json={"sha": "sha", "content": encoded_manifest},
    )

    # recommendations has no matching workloads
    recs = [
        Recommendation(
            workload_name="non-existent",
            workload_kind="Deployment",
            namespace="default",
            replica_count=1,
            suggestions=["Reduce CPU requests"],
        )
    ]

    with pytest.raises(K8sAnalyzerError, match="No matching workloads found in the target manifest"):
        open_github_pr(cfg, recs)
