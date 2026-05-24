"""CLI entry point for k8s-prometheus-analyzer.

Exit codes
----------
0  All pods are well-configured — no action required.
1  Optimisation suggestions exist (INFO / WARNING level).
2  Critical issues detected (e.g. CPU throttling, resource exhaustion).
3  Tool error — Prometheus unreachable, bad configuration, etc.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from typing import Any, NoReturn

from .alerting.dispatcher import dispatch
from .analyzer import SEVERITY_CRITICAL, Recommendation, analyze
from .config import Config, load_config
from .exceptions import ConfigError, K8sAnalyzerError, LicenseError, LicenseLimitExceededError
from .fetcher import PrometheusClient
from .license import verify_license
from .reporter import html_report, json_report, table
from .workload import aggregate_metrics, resolve_workload_map

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_WARNINGS = 1
EXIT_CRITICAL = 2
EXIT_ERROR = 3


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def _setup_logging(level: str, fmt: str) -> None:
    handler = logging.StreamHandler(sys.stderr)
    if fmt == "json":
        try:
            from pythonjsonlogger import jsonlogger  # type: ignore[import]

            formatter: logging.Formatter = jsonlogger.JsonFormatter(
                fmt="%(asctime)s %(name)s %(levelname)s %(message)s"
            )
        except ImportError:
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            logging.getLogger(__name__).warning(
                "python-json-logger not installed; falling back to text format"
            )
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="k8s-analyze",
        description=(
            "Analyse Kubernetes resource usage from Prometheus and surface "
            "optimisation recommendations."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # Point at a local Prometheus
  k8s-analyze --prometheus-url http://localhost:9090

  # Use a config file
  k8s-analyze --config ~/.k8s-analyzer.yaml

  # Bearer-token auth with JSON logging (suitable for CI)
  k8s-analyze --prometheus-url https://prom.example.com \\
              --auth-type bearer --token "$TOKEN" --log-format json

  # Disable SSL verification (dev/test only)
  k8s-analyze --prometheus-url https://prom.local --no-verify-ssl

exit codes:
  0  No issues found — all pods are well-configured.
  1  Optimisation suggestions exist.
  2  Critical issues detected (CPU throttling / resource exhaustion).
  3  Tool error (connection failure, bad config, etc.).
""",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__import__('k8s_prometheus_analyzer').__version__}",
    )

    conn = parser.add_argument_group("connection")
    conn.add_argument(
        "--prometheus-url",
        metavar="URL",
        help="Base URL of the Prometheus server (default: http://localhost:9090)",
    )
    conn.add_argument(
        "--timeout",
        type=int,
        metavar="SECONDS",
        help="HTTP request timeout in seconds (default: 10)",
    )
    conn.add_argument(
        "--retries",
        type=int,
        metavar="N",
        help="Number of retries on transient errors (default: 3)",
    )

    auth = parser.add_argument_group("authentication")
    auth.add_argument(
        "--auth-type",
        choices=["none", "bearer", "basic"],
        help="Authentication method (default: none)",
    )
    auth.add_argument("--token", metavar="TOKEN", help="Bearer token")
    auth.add_argument("--username", metavar="USER", help="Basic-auth username")
    auth.add_argument("--password", metavar="PASS", help="Basic-auth password")
    auth.add_argument(
        "--ca-cert",
        metavar="PATH",
        help="Path to CA bundle for TLS verification",
    )
    auth.add_argument(
        "--no-verify-ssl",
        action="store_true",
        default=None,
        help="Disable TLS certificate verification (INSECURE — dev/test only)",
    )

    out = parser.add_argument_group("output")
    out.add_argument(
        "--output",
        metavar="FILE",
        help="JSON output file path (default: optimization_suggestions.json)",
    )
    out.add_argument(
        "--html-output",
        metavar="FILE",
        help="HTML report file path (default: optimization_report.html)",
    )
    out.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        metavar="LEVEL",
        help="Logging verbosity (default: INFO)",
    )
    out.add_argument(
        "--log-format",
        choices=["text", "json"],
        metavar="FORMAT",
        help="Log output format — text or json (default: text)",
    )

    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to a YAML config file",
    )

    parser.add_argument(
        "--license-file",
        metavar="PATH",
        help="Path to the enterprise license file (license.jwt)",
    )

    parser.add_argument(
        "--daemon",
        action="store_true",
        default=None,
        help="Run the analyzer continuously in background daemon mode",
    )

    parser.add_argument(
        "--daemon-interval",
        type=int,
        metavar="SECONDS",
        help="Interval in seconds to sleep between runs (default: 300)",
    )

    alert = parser.add_argument_group("alerting")
    alert.add_argument(
        "--alert-slack-url",
        metavar="URL",
        help="Slack incoming webhook URL — enables Slack alerts when set",
    )
    alert.add_argument(
        "--alert-webhook-url",
        metavar="URL",
        help="Generic HTTP webhook URL — enables webhook alerts when set",
    )
    alert.add_argument(
        "--alert-on",
        metavar="SEVERITY",
        action="append",
        choices=["critical", "warning", "info"],
        dest="alert_on",
        help=(
            "Severity level that triggers an alert (repeatable). "
            "Default: critical warning"
        ),
    )

    gitops = parser.add_argument_group("gitops")
    gitops.add_argument(
        "--gitops",
        action="store_true",
        default=None,
        help="Enable auto-generation of GitOps sizing Pull Requests on GitHub",
    )
    gitops.add_argument(
        "--github-token",
        metavar="TOKEN",
        help="GitHub Personal Access Token for creating branches and PRs",
    )
    gitops.add_argument(
        "--github-repo",
        metavar="OWNER/REPO",
        help="Target GitHub repository (e.g. 'rahulbansod519/k8s-gitops-config')",
    )
    gitops.add_argument(
        "--github-branch",
        metavar="BRANCH",
        help="Base branch for the Pull Request (default: main)",
    )
    gitops.add_argument(
        "--manifest-path",
        metavar="PATH",
        help="Path to the Kubernetes manifest file inside the repository to modify",
    )

    return parser


def get_node_count(client: PrometheusClient) -> int:
    """Query Prometheus for the active node count in the cluster.

    Default to 1 if the query fails or returns no nodes.
    """
    try:
        res = client.query("count(kube_node_info)")
        if res and "value" in res[0] and len(res[0]["value"]) > 1:
            return int(res[0]["value"][1])
    except Exception as exc:
        logger.warning("Failed to query node count from Prometheus: %s. Defaulting to 1.", exc)
    return 1


def _run_analysis_cycle(cfg: Config, client: PrometheusClient) -> list[Recommendation] | None:
    """Run a single analysis, reporting, and alerting cycle.

    Returns:
        list[Recommendation]: The list of recommendations generated.
        None: If a transient error occurred.
    """
    try:
        client.check_availability()

        # ── License checks ──
        node_count = get_node_count(client)
        logger.info("Detected %d active node(s) in the cluster", node_count)

        if cfg.license_file:
            logger.info("Loading license file from %s", cfg.license_file)
            try:
                with open(cfg.license_file) as f:
                    license_token = f.read().strip()
            except FileNotFoundError as exc:
                raise ConfigError(f"License file not found: {cfg.license_file}") from exc

            payload = verify_license(license_token)
            license_limit = payload.get("limits", {}).get("nodes", 0)
            logger.info(
                "License verified successfully for %s (Limit: %d nodes)",
                payload.get("sub", "Unknown Tenant"),
                license_limit,
            )
            if node_count > license_limit:
                raise LicenseLimitExceededError(
                    f"Active node count ({node_count}) exceeds your licensed limit of {license_limit} nodes."
                )
        else:
            logger.warning("No license file specified. Running in Community Edition mode.")
            COMMUNITY_NODE_LIMIT = 15
            if node_count > COMMUNITY_NODE_LIMIT:
                raise LicenseLimitExceededError(
                    f"Free Community Edition is limited to {COMMUNITY_NODE_LIMIT} nodes. "
                    f"Your cluster has {node_count} nodes. Please purchase an Enterprise license."
                )

        logger.info("Fetching metrics from Prometheus …")
        metrics = client.query_all()
    except (LicenseError, ConfigError):
        raise
    except K8sAnalyzerError as exc:
        logger.error("Transient error during metrics fetch: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during metrics fetch: %s", exc)
        return None

    # ── Resolve workloads & aggregate metrics ──
    pod_owner_data = metrics.pop("pod_owner", [])
    rs_owner_data = metrics.pop("rs_owner", [])

    if pod_owner_data:
        logger.info(
            "Resolving workload ownership for %d pod entries", len(pod_owner_data)
        )
    else:
        logger.warning(
            "No kube_pod_owner data found — falling back to pod-level grouping. "
            "Ensure kube-state-metrics is deployed and scraped by Prometheus."
        )

    workload_map = resolve_workload_map(pod_owner_data, rs_owner_data)
    workload_metrics = aggregate_metrics(metrics, workload_map)

    logger.info(
        "Aggregated %d pods into %d workload(s)", len(pod_owner_data), len(workload_metrics)
    )

    # ── Analyse ──
    recommendations = analyze(workload_metrics, cfg.thresholds)
    logger.info(
        "Analysis complete — %d recommendation(s) generated", len(recommendations)
    )

    # ── Report ──
    table.print_table(recommendations)

    try:
        json_report.export_json(recommendations, cfg.output)
    except OSError as exc:
        logger.error("Failed to write JSON report: %s", exc)

    try:
        html_report.export_html(recommendations, cfg.html_output, cfg.prometheus_url)
    except OSError as exc:
        logger.error("Failed to write HTML report: %s", exc)

    # ── Alert ──
    try:
        dispatch(recommendations, cfg.alerts, cfg.prometheus_url)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to dispatch alerts: %s", exc)

    # ── GitOps auto-PR trigger ──
    if cfg.gitops.enabled and recommendations:
        logger.info("GitOps auto-PR generation is enabled. Triggering Pull Request...")
        try:
            from .gitops import open_github_pr
            pr_url = open_github_pr(cfg, recommendations)
            logger.info("Successfully created GitOps Pull Request: %s", pr_url)
        except K8sAnalyzerError as exc:
            logger.error("GitOps PR generation failed: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error in GitOps trigger: %s", exc)

    return recommendations


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> NoReturn:
    parser = _build_parser()
    args = parser.parse_args()

    # ── 1. Load configuration (YAML → env vars) ───────────────────────────
    try:
        cfg = load_config(config_file=args.config)
    except ConfigError as exc:
        # Logging not set up yet; write directly to stderr
        print(f"[ERROR] Configuration error: {exc}", file=sys.stderr)
        sys.exit(EXIT_ERROR)

    # ── 2. Apply CLI overrides (highest priority) ─────────────────────────
    if args.prometheus_url is not None:
        cfg.prometheus_url = args.prometheus_url
    if args.auth_type is not None:
        cfg.auth_type = args.auth_type
    if args.token is not None:
        cfg.token = args.token
    if args.username is not None:
        cfg.username = args.username
    if args.password is not None:
        cfg.password = args.password
    if args.ca_cert is not None:
        cfg.ca_cert = args.ca_cert
    if args.no_verify_ssl:
        cfg.verify_ssl = False
    if args.timeout is not None:
        cfg.timeout = args.timeout
    if args.retries is not None:
        cfg.retries = args.retries
    if args.output is not None:
        cfg.output = args.output
    if args.html_output is not None:
        cfg.html_output = args.html_output
    if args.log_level is not None:
        cfg.log_level = args.log_level
    if args.log_format is not None:
        cfg.log_format = args.log_format
    if args.license_file is not None:
        cfg.license_file = args.license_file
    if args.daemon is not None:
        cfg.daemon = args.daemon
    if args.daemon_interval is not None:
        cfg.daemon_interval = args.daemon_interval

    # ── GitOps CLI overrides ──────────────────────────────────────────────
    if args.gitops:
        cfg.gitops.enabled = True
    if args.github_token is not None:
        cfg.gitops.github_token = args.github_token
    if args.github_repo is not None:
        cfg.gitops.github_repo = args.github_repo
    if args.github_branch is not None:
        cfg.gitops.github_branch = args.github_branch
    if args.manifest_path is not None:
        cfg.gitops.manifest_path = args.manifest_path

    # ── Alert CLI overrides ───────────────────────────────────────────────
    if args.alert_slack_url:
        cfg.alerts.enabled = True
        cfg.alerts.slack.enabled = True
        cfg.alerts.slack.webhook_url = args.alert_slack_url
    if args.alert_webhook_url:
        cfg.alerts.enabled = True
        cfg.alerts.webhook.enabled = True
        cfg.alerts.webhook.url = args.alert_webhook_url
    if args.alert_on:
        cfg.alerts.on_severities = args.alert_on

    # ── 3. Initialise logging ─────────────────────────────────────────────
    _setup_logging(cfg.log_level, cfg.log_format)

    logger.info(
        "k8s-prometheus-analyzer starting",
        extra={"prometheus_url": cfg.prometheus_url, "auth_type": cfg.auth_type},
    )

    # ── 4. Connect & fetch ────────────────────────────────────────────────
    try:
        client = PrometheusClient(cfg)
    except K8sAnalyzerError as exc:
        logger.error("Fatal initialization error: %s", exc)
        sys.exit(EXIT_ERROR)

    # Setup signal handlers for graceful daemon shutdown
    shutdown_event = threading.Event()

    def handle_shutdown(signum: int, frame: Any) -> None:
        logger.info("Received signal %d. Shutting down gracefully...", signum)
        shutdown_event.set()

    # signal.signal can only be registered on the main thread
    try:
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
    except ValueError as exc:
        logger.warning("Could not register signal handlers: %s", exc)

    if cfg.daemon:
        logger.info(
            "Running in daemon mode. Scan interval: %d seconds",
            cfg.daemon_interval,
        )
        # Verify the license once before entering the loop so fatal license issues crash immediately
        try:
            client.check_availability()
            node_count = get_node_count(client)
            if cfg.license_file:
                with open(cfg.license_file) as f:
                    license_token = f.read().strip()
                payload = verify_license(license_token)
                license_limit = payload.get("limits", {}).get("nodes", 0)
                if node_count > license_limit:
                    raise LicenseLimitExceededError(
                        f"Active node count ({node_count}) exceeds your licensed limit of {license_limit} nodes."
                    )
            else:
                COMMUNITY_NODE_LIMIT = 15
                if node_count > COMMUNITY_NODE_LIMIT:
                    raise LicenseLimitExceededError(
                        f"Free Community Edition is limited to {COMMUNITY_NODE_LIMIT} nodes. "
                        f"Your cluster has {node_count} nodes. Please purchase an Enterprise license."
                    )
        except (LicenseError, ConfigError) as exc:
            logger.error("Fatal licensing check failed: %s", exc)
            sys.exit(EXIT_ERROR)
        except K8sAnalyzerError as exc:
            logger.warning("Initial connection check encountered a transient error: %s. Continuing in loop.", exc)

        while not shutdown_event.is_set():
            logger.info("Starting analysis cycle...")
            try:
                _run_analysis_cycle(cfg, client)
            except (LicenseError, ConfigError) as exc:
                logger.error("Fatal license/config error encountered: %s. Terminating daemon.", exc)
                sys.exit(EXIT_ERROR)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unexpected error in daemon loop: %s", exc)

            if shutdown_event.is_set():
                break

            logger.info("Cycle complete. Sleeping for %d seconds...", cfg.daemon_interval)
            shutdown_event.wait(timeout=cfg.daemon_interval)

        logger.info("Daemon shut down cleanly.")
        sys.exit(EXIT_OK)
    else:
        # Single execution mode
        try:
            recommendations = _run_analysis_cycle(cfg, client)
            if recommendations is None:
                # Transient fetch error occurred
                sys.exit(EXIT_ERROR)

            if not recommendations:
                sys.exit(EXIT_OK)

            has_critical = any(r.severity == SEVERITY_CRITICAL for r in recommendations)
            sys.exit(EXIT_CRITICAL if has_critical else EXIT_WARNINGS)
        except (LicenseError, ConfigError) as exc:
            logger.error("Fatal: %s", exc)
            sys.exit(EXIT_ERROR)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected fatal error: %s", exc)
            sys.exit(EXIT_ERROR)
