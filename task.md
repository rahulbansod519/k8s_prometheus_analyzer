# Tasks: Prometheus Exporter & Grafana Dashboard Integration

- [x] Add `exporter_port` configurations to `config.py`
- [x] Add baseline request fields to `Recommendation` class in `analyzer.py`
- [x] Implement `exporter.py` with standard HTTP server and metrics formatting
- [x] Integrate background exporter thread startup/teardown in `cli.py`
- [x] Write unit tests in `tests/test_exporter.py`
- [x] Run `pytest` and verify code coverage > 80%
- [x] Create Grafana dashboard JSON config in `grafana/dashboard.json`
- [x] Embed dashboard JSON in `helm/k8s-prometheus-analyzer/templates/grafana-dashboard.yaml`
- [x] Expose configuration options in `helm/k8s-prometheus-analyzer/values.yaml`
- [x] Run static code quality checks (`ruff`, `mypy`)
- [x] Update `walkthrough.md` and playbooks
