# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools
RUN pip install --no-cache-dir build

# Copy only what's needed for packaging
COPY pyproject.toml README.md ./
COPY k8s_prometheus_analyzer/ ./k8s_prometheus_analyzer/

# Build the wheel
RUN python -m build --wheel --outdir /dist

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

LABEL org.opencontainers.image.title="k8s-prometheus-analyzer" \
      org.opencontainers.image.description="CLI tool to analyse Kubernetes resource usage from Prometheus" \
      org.opencontainers.image.source="https://github.com/rahulbansod519/k8s_prometheus_analyzer" \
      org.opencontainers.image.licenses="MIT"

# Create a non-root user
RUN useradd --create-home --shell /bin/sh analyzer
USER analyzer
WORKDIR /home/analyzer

# Copy the built wheel from the builder stage and install it
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Copy the example config for reference
COPY config.example.yaml ./config.example.yaml

ENTRYPOINT ["k8s-analyze"]
CMD ["--help"]

