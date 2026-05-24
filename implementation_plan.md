# Implementation Plan: GitOps Auto-PR Prototype

This plan details the implementation of the **GitOps Auto-PR Prototype** for `k8s-prometheus-analyzer`. It enables the tool to automatically branch, modify resource sizes in your infrastructure repository, and open a Pull Request on GitHub when waste or throttling is detected.

## User Review Required

> [!IMPORTANT]
> **GitHub Authentication**: The GitOps module requires a GitHub Personal Access Token (PAT) with `repo` permissions, configured via environment variable `K8S_ANALYZER_GITHUB_TOKEN` or CLI argument `--github-token`.
> 
> **YAML Parsing Limitations**: The prototype will use the standard `PyYAML` library to parse and write manifests. Note that standard PyYAML does not preserve file comments. For production, we will transition to `ruamel.yaml` to preserve formatting and comments.

## Proposed Changes

### Configuration Updates

#### [MODIFY] [config.py](file:///Users/rahulbansod01/Projects/k8s_prometheus_analyzer/k8s-monitor/k8s_prometheus_analyzer/config.py)
* Add a `GitOpsConfig` block:
  ```python
  @dataclass
  class GitOpsConfig:
      enabled: bool = False
      github_token: str = ""
      github_repo: str = ""        # e.g. "owner/repo"
      github_branch: str = "main"  # base branch
      manifest_path: str = ""      # path to the YAML inside the repo
  ```
* Add `gitops: GitOpsConfig = field(default_factory=GitOpsConfig)` to `Config`.

---

### Core GitOps Logic

#### [NEW] [gitops.py](file:///Users/rahulbansod01/Projects/k8s_prometheus_analyzer/k8s-monitor/k8s_prometheus_analyzer/gitops.py)
* Create a GitOps manager to interface with the GitHub REST API (using the existing `requests` library).
* Implement `update_yaml_manifest(original_content: str, workload_name: str, workload_kind: str, cpu_cores: float, mem_mb: float) -> str`:
  * Parses the manifest (YAML), locates the matching workload, updates its container `resources` block (setting requests to the recommended CPU and Memory), and serializes it back to YAML.
* Implement `open_github_pr(cfg: Config, recommendations: list[Recommendation]) -> str`:
  * Connects to GitHub API.
  * Checks base branch ref and grabs the latest commit SHA.
  * Creates a new branch: `refs/heads/k8s-optimize-<timestamp>`.
  * Fetches the original manifest file from the base branch.
  * Calls `update_yaml_manifest` to modify the CPU/Memory values.
  * Commits the updated manifest to the new branch.
  * Creates a Pull Request on GitHub with a description summarizing the cost/resource savings.
  * Returns the URL of the created Pull Request.

---

### Integration into the CLI

#### [MODIFY] [cli.py](file:///Users/rahulbansod01/Projects/k8s_prometheus_analyzer/k8s-monitor/k8s_prometheus_analyzer/cli.py)
* Add CLI arguments:
  * `--gitops`: Enable auto-PR generation.
  * `--github-token`: Personal Access Token.
  * `--github-repo`: Target repository (e.g. `owner/repo`).
  * `--github-branch`: Target branch (default: `main`).
  * `--manifest-path`: Target YAML file path in the repository.
* In the single run cycle or daemon loop, if GitOps is enabled and recommendations exist:
  * Trigger `open_github_pr`.
  * Log the created PR URL.

---

## Verification Plan

### Automated Tests
* Write unit tests in `tests/test_gitops.py` to:
  * Verify `update_yaml_manifest` successfully modifies container resource configurations in single-document and multi-document YAMLs.
  * Mock the GitHub REST API calls (ref, branch creation, file get/put, PR post) using `requests_mock` to verify the step-by-step API flow.

### Manual Verification
* Run the tool targeting a test repository with a valid token, and confirm a new branch and PR are created.
