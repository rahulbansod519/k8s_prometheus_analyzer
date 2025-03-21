# Kubernetes Prometheus Analyzer

Kubernetes Prometheus Analyzer is a CLI tool that analyzes resource usage in Kubernetes clusters using Prometheus metrics. It provides optimization suggestions for CPU and memory utilization.

## Installation & Usage

Follow these steps to install and use the tool:

### 1. Clone the Repository
```sh
git clone https://github.com/rahulbansod519/k8s_prometheus_analyzer.git
cd k8s_prometheus_analyzer
```

### 2. Navigate to the k8s-monitor Directory
```sh
cd k8s-monitor
```

### 3. Install the Package
```sh
pip install -e .
```

### 4. Run the Analyzer
```sh
k8s-analyze --prometheus-url http://your-prometheus-server:9090/api/v1/query
```

Replace `http://your-prometheus-server:9090` with the actual Prometheus server URL.

## Features
- Fetches CPU and memory usage metrics from Prometheus.
- Suggests optimizations for Kubernetes workloads.
- Provides structured output for easy analysis.



