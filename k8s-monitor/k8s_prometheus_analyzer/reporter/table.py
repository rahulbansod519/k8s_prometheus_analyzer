"""Terminal table reporter using tabulate."""

from __future__ import annotations

import textwrap

from tabulate import tabulate

from ..analyzer import Recommendation

_HEADERS = [
    "Namespace",
    "Workload (Kind)",
    "Replicas",
    "CPU / pod",
    "CPU %",
    "Mem / pod",
    "Mem %",
    "Severity",
    "Suggested Optimisation",
]

_SEVERITY_ICON = {
    "critical": "🔴",
    "warning":  "🟡",
    "info":     "🟢",
}


def print_table(recommendations: list[Recommendation]) -> None:
    """Print a formatted optimisation table to stdout.

    If *recommendations* is empty, prints an 'all clear' message instead.
    """
    if not recommendations:
        print("\n✅  No optimisations needed — all workloads are well-configured.\n")
        return

    rows = []
    for rec in recommendations:
        icon = _SEVERITY_ICON.get(rec.severity, "⚪")
        rows.append(
            [
                rec.namespace,
                f"{rec.workload_name} ({rec.workload_kind})",
                str(rec.replica_count),
                f"{rec.cpu_usage:.2f} cores",
                f"{rec.cpu_usage_pct:.1f}%",
                f"{rec.memory_usage_mb:.2f} MB",
                f"{rec.memory_usage_pct:.1f}%",
                f"{icon} {rec.severity}",
                textwrap.fill(", ".join(rec.suggestions), width=30),
            ]
        )

    print("\n🔍  Optimisation Suggestions\n")
    print(tabulate(rows, headers=_HEADERS, tablefmt="grid"))
    print()
