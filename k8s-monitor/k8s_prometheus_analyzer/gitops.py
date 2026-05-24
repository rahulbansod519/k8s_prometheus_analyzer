"""GitOps Auto-PR generator interfacing with the GitHub REST API."""

from __future__ import annotations

import base64
import logging
import time
from typing import TYPE_CHECKING

import requests
import yaml

from .exceptions import K8sAnalyzerError

if TYPE_CHECKING:
    from .analyzer import Recommendation
    from .config import Config

logger = logging.getLogger(__name__)


def update_yaml_manifest(original_content: str, recommendations: list[Recommendation]) -> str:
    """Parse YAML manifest, update resource requests for matching workloads, and return updated YAML.

    Applies standard sizing safety buffers:
    - CPU Request: Max of (average usage * 1.25, 0.01 cores) (25% buffer)
    - Memory Request: Max of (average usage * 1.20, 10.0 MB) (20% buffer)
    """
    try:
        docs = list(yaml.safe_load_all(original_content))
    except Exception as exc:
        raise ValueError(f"Failed to parse YAML manifest: {exc}") from exc

    updated_any = False

    for doc in docs:
        if not isinstance(doc, dict):
            continue

        kind = doc.get("kind")
        name = doc.get("metadata", {}).get("name")

        if not kind or not name:
            continue

        # Find matching recommendation
        match = None
        for rec in recommendations:
            if rec.workload_kind.lower() == kind.lower() and rec.workload_name == name:
                match = rec
                break

        if not match:
            continue

        # Resolve container spec path based on resource kind
        containers = None
        kind_lower = kind.lower()
        if kind_lower in ("deployment", "statefulset", "daemonset"):
            containers = doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers")
        elif kind_lower == "job":
            containers = doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers")
        elif kind_lower == "cronjob":
            containers = (
                doc.get("spec", {})
                .get("jobTemplate", {})
                .get("spec", {})
                .get("template", {})
                .get("spec", {})
                .get("containers")
            )
        elif kind_lower == "pod":
            containers = doc.get("spec", {}).get("containers")

        if not containers:
            continue

        # Apply sizing updates to each container resources block
        for container in containers:
            if not isinstance(container, dict):
                continue
            if "resources" not in container:
                container["resources"] = {}
            resources = container["resources"]
            if not isinstance(resources, dict):
                resources = {}
                container["resources"] = resources
            if "requests" not in resources:
                resources["requests"] = {}
            requests_block = resources["requests"]
            if not isinstance(requests_block, dict):
                requests_block = {}
                resources["requests"] = requests_block

            # Update requests based on optimization suggestions
            if any("cpu" in s.lower() for s in match.suggestions):
                cpu_req = max(match.cpu_usage * 1.25, 0.01)
                requests_block["cpu"] = f"{int(cpu_req * 1000)}m"
            if any("memory" in s.lower() or "mem" in s.lower() for s in match.suggestions):
                mem_req = max(match.memory_usage_mb * 1.2, 10.0)
                requests_block["memory"] = f"{int(mem_req)}Mi"
            updated_any = True

    if not updated_any:
        return original_content

    # Dump all documents back to a single YAML stream
    return yaml.safe_dump_all(docs)


def open_github_pr(cfg: Config, recommendations: list[Recommendation]) -> str:
    """Create a new branch, commit updated manifest sizing changes, and open a Pull Request.

    Args:
        cfg: The Config containing gitops credential configurations.
        recommendations: Sizing recommendations to apply.

    Returns:
        str: The URL of the created GitHub Pull Request.

    Raises:
        K8sAnalyzerError: On any API failures.
    """
    g_cfg = cfg.gitops
    if not g_cfg.github_token:
        raise K8sAnalyzerError("GitHub Token must be provided to use GitOps features.")
    if not g_cfg.github_repo:
        raise K8sAnalyzerError("Target GitHub repository (owner/repo) must be specified.")
    if not g_cfg.manifest_path:
        raise K8sAnalyzerError("Target manifest path in the repository must be specified.")

    base_url = f"https://api.github.com/repos/{g_cfg.github_repo}"
    headers = {
        "Authorization": f"token {g_cfg.github_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    session = requests.Session()
    session.headers.update(headers)

    # ── 1. Fetch latest SHA of base branch ──────────────────────────────────
    ref_url = f"{base_url}/git/ref/heads/{g_cfg.github_branch}"
    try:
        resp = session.get(ref_url, timeout=10)
        if resp.status_code == 404:
            raise K8sAnalyzerError(f"Base branch '{g_cfg.github_branch}' or repository not found.")
        resp.raise_for_status()
        base_sha = resp.json()["object"]["sha"]
    except requests.exceptions.RequestException as exc:
        raise K8sAnalyzerError(f"Failed to fetch base branch ref: {exc}") from exc

    # ── 2. Create new branch ────────────────────────────────────────────────
    branch_name = f"k8s-optimize-{int(time.time())}"
    new_ref_url = f"{base_url}/git/refs"
    try:
        resp = session.post(
            new_ref_url,
            json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise K8sAnalyzerError(f"Failed to create new branch '{branch_name}': {exc}") from exc

    # ── 3. Fetch current file content and file SHA ──────────────────────────
    file_url = f"{base_url}/contents/{g_cfg.manifest_path}"
    try:
        resp = session.get(file_url, params={"ref": g_cfg.github_branch}, timeout=10)
        if resp.status_code == 404:
            raise K8sAnalyzerError(f"Manifest path '{g_cfg.manifest_path}' not found in repo.")
        resp.raise_for_status()
        payload = resp.json()
        file_sha = payload["sha"]
        raw_content = base64.b64decode(payload["content"]).decode("utf-8")
    except requests.exceptions.RequestException as exc:
        raise K8sAnalyzerError(f"Failed to fetch manifest contents: {exc}") from exc

    # ── 4. Modify manifest content and commit ───────────────────────────────
    try:
        updated_content = update_yaml_manifest(raw_content, recommendations)
    except ValueError as exc:
        raise K8sAnalyzerError(str(exc)) from exc

    if updated_content == raw_content:
        raise K8sAnalyzerError("No matching workloads found in the target manifest to optimize.")

    try:
        resp = session.put(
            file_url,
            json={
                "message": f"🤖 k8s-prometheus-analyzer: optimize resources in {g_cfg.manifest_path}",
                "content": base64.b64encode(updated_content.encode("utf-8")).decode("utf-8"),
                "sha": file_sha,
                "branch": branch_name,
            },
            timeout=10,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise K8sAnalyzerError(f"Failed to commit updated manifest: {exc}") from exc

    # ── 5. Open Pull Request ────────────────────────────────────────────────
    pr_url = f"{base_url}/pulls"
    pr_body = (
        "### 🤖 Kubernetes Resource Optimization\n\n"
        "This Pull Request contains recommended resource right-sizing modifications generated by "
        "`k8s-prometheus-analyzer`.\n\n"
        "| Workload | Kind | Suggestion | Reason |\n"
        "| :--- | :--- | :--- | :--- |\n"
    )
    for rec in recommendations:
        suggestions_str = ", ".join(rec.suggestions)
        reasons_str = "; ".join(rec.reasons)
        pr_body += f"| `{rec.workload_name}` | {rec.workload_kind} | {suggestions_str} | {reasons_str} |\n"

    try:
        resp = session.post(
            pr_url,
            json={
                "title": f"🤖 Sizing Optimization: {g_cfg.manifest_path}",
                "body": pr_body,
                "head": branch_name,
                "base": g_cfg.github_branch,
            },
            timeout=10,
        )
        resp.raise_for_status()
        pr_html_url = resp.json()["html_url"]
        if not isinstance(pr_html_url, str):
            raise K8sAnalyzerError("GitHub API response html_url is not a string")
        return pr_html_url
    except requests.exceptions.RequestException as exc:
        raise K8sAnalyzerError(f"Failed to create Pull Request: {exc}") from exc
