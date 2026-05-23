# Security Policy

## Supported Versions

The following versions of **k8s-prometheus-analyzer** currently receive security fixes:

| Version | Supported |
|---|---|
| `0.2.x` (latest) | ✅ Active support |
| `0.1.x` | ⚠️ Critical fixes only |
| `< 0.1.0` (pre-release) | ❌ End of life |

We strongly recommend always running the latest published version. Security fixes are released as **patch versions** (`0.2.x`) and announced in the [CHANGELOG](CHANGELOG.md) under a dedicated **Security** heading.

---

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.** Public disclosure before a fix is available puts all users at risk.

### Preferred method — GitHub Private Security Advisory

1. Navigate to the repository on GitHub
2. Click **Security** → **Advisories** → **Report a vulnerability**
3. Fill in the advisory form with as much detail as possible (see below)
4. Submit — this creates a private, encrypted thread visible only to you and the maintainers

GitHub's private advisory system is the fastest way to reach the maintainers securely and is our preferred channel.

### Alternative — Email

If you are unable to use GitHub's advisory system, email the maintainers directly. Include `[SECURITY]` in the subject line. Contact details are listed in the repository's [SECURITY.md](https://github.com/rahulbansod519/k8s_prometheus_analyzer/security/policy) page on GitHub.

### What to include in your report

Please provide as much of the following as possible to help us reproduce and fix the issue quickly:

- **Description** — a clear explanation of the vulnerability and its potential impact
- **Affected versions** — which version(s) you tested against
- **Steps to reproduce** — a minimal, reliable reproduction scenario
- **Proof of concept** — sample code, curl commands, or configuration (if safe to share)
- **Suggested fix** — if you have one (optional but very welcome)
- **CVSS score estimate** — if you are able to calculate one

### Response timeline

| Stage | Target timeframe |
|---|---|
| Acknowledgement | Within **48 hours** of receiving the report |
| Initial assessment | Within **5 business days** |
| Fix development | Depends on severity — Critical: **7 days**, High: **14 days**, Medium/Low: **30 days** |
| Public disclosure | Coordinated with reporter — typically after fix is released |

We will keep you informed throughout the process and credit you in the release notes (unless you prefer to remain anonymous).

---

## Security Considerations

### Credential handling

> [!CAUTION]
> `k8s-prometheus-analyzer` never logs credentials. If you observe credential data appearing in log output, please report it immediately as a security bug.

- **Bearer tokens** and **basic-auth passwords** are stored only in memory during a single run and are never written to disk, JSON output, or log files
- The tool intentionally omits authentication fields from all log messages (even at `DEBUG` level)
- The HTML report and JSON output files do **not** contain any authentication credentials

### Prometheus URL in output

The Prometheus base URL (without credentials) is included in:
- Log messages at `INFO` level
- The HTML report header (for audit trail purposes)
- Alert payloads sent to Slack / webhook endpoints

If your Prometheus URL itself encodes sensitive information (e.g. a token in the path), configure authentication via `--auth-type bearer` / `--token` instead of embedding credentials in the URL.

### TLS verification

> [!WARNING]
> The `--no-verify-ssl` flag and `verify_ssl: false` config option **disable TLS certificate verification entirely**. Use these only in isolated development or test environments — **never in production**.

When connecting to a Prometheus endpoint with a self-signed or private-CA certificate, use the `--ca-cert` flag or `ca_cert` config key to supply a CA bundle instead of disabling verification:

```bash
# ✅ Correct — supply the CA bundle
k8s-analyze --prometheus-url https://prom.internal --ca-cert /etc/ssl/certs/corp-ca.pem

# ❌ Avoid — disables all certificate validation
k8s-analyze --prometheus-url https://prom.internal --no-verify-ssl
```

### Secret management in Kubernetes

When running the tool as a Kubernetes CronJob or Job, store Prometheus credentials in a `Secret` and inject them as environment variables — do **not** embed them in `ConfigMap` values or command-line arguments visible in pod specs:

```yaml
env:
  - name: K8S_ANALYZER_TOKEN
    valueFrom:
      secretKeyRef:
        name: prometheus-credentials
        key: token
  - name: K8S_ANALYZER_ALERTS_SLACK_WEBHOOK_URL
    valueFrom:
      secretKeyRef:
        name: k8s-analyzer-secrets
        key: slack-webhook-url
```

### Output file permissions

The JSON and HTML output files are written with the default umask of the running process. If the output directory is shared or world-readable, restrict permissions explicitly:

```bash
umask 0027  # rw-r----- for new files
k8s-analyze --output /secure/reports/suggestions.json
```

### Network access

`k8s-prometheus-analyzer` makes outbound HTTP(S) connections to:

1. **Prometheus** — the URL you specify via `--prometheus-url` / `K8S_ANALYZER_PROMETHEUS_URL`
2. **Slack** — `https://hooks.slack.com` (only if Slack alerting is configured and enabled)
3. **Webhook endpoint** — the URL you specify via `--alert-webhook-url` (only if webhook alerting is configured and enabled)

No other outbound connections are made. The tool does not call home, check for updates, or send telemetry.

### Docker image

The official `Dockerfile` uses:
- A **multi-stage build** to minimise the final image size and exclude build tools
- A **non-root user** (`appuser`) in the final image — the tool should never be run as root
- Pinned base image tags — update regularly to pick up OS-level security patches

```bash
# Check for base image vulnerabilities
docker scout cves ghcr.io/rahulbansod519/k8s-prometheus-analyzer:latest
```

### Dependencies

All Python dependencies are pinned to minimum versions in `pyproject.toml`. We monitor dependencies for known vulnerabilities using GitHub's Dependabot. If you discover a vulnerable transitive dependency, please report it via the private advisory process above.

---

## Scope

The following are considered **in-scope** for security reports:

- Credential leakage via logs, output files, or alert payloads
- TLS/certificate bypass vulnerabilities
- Arbitrary code execution via malformed Prometheus responses or config files
- Path traversal in output file paths
- Authentication bypass in the HTTP client

The following are considered **out-of-scope**:

- Vulnerabilities in Prometheus itself or kube-state-metrics
- Social engineering attacks
- Physical access to systems running the tool
- Issues that require an attacker to already have write access to the config file or environment

---

## Security Acknowledgements

We thank the following researchers for responsibly disclosing security issues:

_(No disclosures to date — this section will be updated as applicable.)_
