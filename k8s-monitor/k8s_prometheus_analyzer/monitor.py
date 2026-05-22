"""Backward-compatibility shim.

All logic has moved to :mod:`k8s_prometheus_analyzer.cli`.
This module is kept so that any direct invocations of
``python -m k8s_prometheus_analyzer.monitor`` continue to work.
"""

from k8s_prometheus_analyzer.cli import main  # noqa: F401

if __name__ == "__main__":
    main()
