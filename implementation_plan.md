# Implementation Plan: Production-grade YAML Parsing with Comment Preservation

This plan details transitioning the GitOps resource modification pipeline from standard `PyYAML` to `ruamel.yaml`. This ensures that when the GitOps engine automatically right-sizes container resources in your infrastructure repository, all developer comments, document formatting, custom indentation, and quote styles are fully preserved.

## User Review Required

> [!NOTE]
> **Licensing Feature Gating (Future Option)**: As discussed, we are not adding stricter licensing gates for GitOps/Daemon features now. We will keep these features enabled for free under the 15-node Community Edition limit, and document feature-gating as a future roadmap item in the playbooks.

## Proposed Changes

### Dependencies

#### [MODIFY] [pyproject.toml](file:///Users/rahulbansod01/Projects/k8s_prometheus_analyzer/k8s-monitor/pyproject.toml)
* Add `"ruamel.yaml>=0.17.40"` to the `dependencies` list under `[project]`.
* Add `"types-ruamel.yaml>=0.17.0"` to the `dev` optional-dependencies list to ensure static type checking compiles cleanly under `mypy`.

---

### Core GitOps Manifest Modification

#### [MODIFY] [gitops.py](file:///Users/rahulbansod01/Projects/k8s_prometheus_analyzer/k8s-monitor/k8s_prometheus_analyzer/gitops.py)
* Replace standard `yaml` import with `from ruamel.yaml import YAML`.
* Update `update_yaml_manifest`:
  * Initialize the round-trip YAML parser:
    ```python
    ryaml = YAML()
    ryaml.preserve_quotes = True
    ```
  * Load all YAML documents using `ryaml.load_all()`. This returns `CommentedMap` collections that preserve spacing, layout, structure, and comments.
  * Traverse and modify the matching workloads (CPU and memory limits/requests) in-place.
  * Serialize the mutated documents back to a string using `ryaml.dump_all()`.

---

## Verification Plan

### Automated Tests
* Create a new test case in `tests/test_gitops.py`:
  * `test_update_yaml_manifest_preserves_comments`:
    * Feed `update_yaml_manifest` a sample multi-document Kubernetes manifest containing inline and header comments.
    * Assert that the resources are optimized, and all original comments are retained in the output.
* Run the standard test suite to verify no regressions in existing GitOps test coverage.

### Manual Verification
* Run tests locally:
  ```bash
  ./venv/bin/pip install -e '.[dev]'
  ./venv/bin/pytest tests/test_gitops.py
  ```
