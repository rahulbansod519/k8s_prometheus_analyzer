import requests
import json
import logging
import textwrap
import argparse
from tabulate import tabulate

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Default Prometheus API URL
PROMETHEUS_URL = "http://localhost:9090/api/v1/query"

# Queries for CPU & Memory Usage/Requests
QUERIES = {
    "cpu_usage": 'sum(rate(container_cpu_usage_seconds_total{container!=""}[5m])) by (pod, namespace)',
    "memory_usage": 'sum(container_memory_usage_bytes{container!=""}) by (pod, namespace)',
    "cpu_requests": 'sum(kube_pod_container_resource_requests{resource="cpu"}) by (pod, namespace)',
    "memory_requests": 'sum(kube_pod_container_resource_requests{resource="memory"}) by (pod, namespace)'
}

def get_args():
    parser = argparse.ArgumentParser(description="Analyze Kubernetes resource usage from Prometheus")
    parser.add_argument("--prometheus-url", type=str, default=PROMETHEUS_URL,
                        help="URL of the Prometheus API (default: http://localhost:9090/api/v1/query)")
    parser.add_argument("--output", type=str, default="optimization_suggestions.json",
                        help="Output JSON file name (default: optimization_suggestions.json)")
    return parser.parse_args()

def check_prometheus_availability():
    """Check if Prometheus API is reachable"""
    try:
        response = requests.get(PROMETHEUS_URL[:-12], timeout=5)
        if response.status_code == 200:
            logging.info("✅ Prometheus is accessible.")
            return True
        else:
            logging.error(f"❌ Prometheus responded with status {response.status_code}.")
            return False
    except requests.exceptions.ConnectionError:
        logging.error("❌ Prometheus not available: Connection Error.")
    except requests.exceptions.Timeout:
        logging.error("❌ Prometheus not available: Timeout Error.")
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Unexpected error while checking Prometheus: {e}")
    return False

def query_prometheus(query):
    """Fetch data securely from Prometheus API using session reuse"""
    try:
        with requests.Session() as session:
            response = session.get(PROMETHEUS_URL, params={"query": query}, timeout=5)
            response.raise_for_status()
            return response.json().get("data", {}).get("result", [])
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Error querying Prometheus: {e}")
        return []

def analyze_usage(cpu_data, memory_data, cpu_requests, memory_requests):
    """Analyze CPU & Memory usage and suggest optimizations"""
    recommendations = []
    
    memory_map = {(m["metric"]["pod"], m["metric"]["namespace"]): float(m["value"][1]) / (1024**2) for m in memory_data}
    cpu_request_map = {(r["metric"]["pod"], r["metric"]["namespace"]): float(r["value"][1]) for r in cpu_requests}
    memory_request_map = {(r["metric"]["pod"], r["metric"]["namespace"]): float(r["value"][1]) / (1024**2) for r in memory_requests}

    for cpu in cpu_data:
        pod = cpu["metric"].get("pod")
        namespace = cpu["metric"].get("namespace")
        if not pod or not namespace:
            continue  

        try:
            cpu_usage = float(cpu["value"][1])
            mem_usage = memory_map.get((pod, namespace), 0)
            cpu_request = cpu_request_map.get((pod, namespace), None)
            mem_request = memory_request_map.get((pod, namespace), None)

            cpu_percentage = (cpu_usage / cpu_request * 100) if cpu_request and cpu_request > 0 else 0
            mem_percentage = (mem_usage / mem_request * 100) if mem_request and mem_request > 0 else 0

            suggestion, reason = [], []

            if cpu_request and cpu_usage < 0.1:
                suggestion.append("Reduce CPU requests")
                reason.append(f"Low CPU usage ({cpu_usage:.2f} cores) vs request ({cpu_request:.2f} cores)")

            if mem_request and mem_usage < 50:
                suggestion.append("Reduce memory requests")
                reason.append(f"Low Memory usage ({mem_usage:.2f} MB) vs request ({mem_request:.2f} MB)")

            if cpu_percentage > 80 or mem_usage > 500:
                suggestion.append("Consider scaling replicas")
                reason.append(f"High resource usage: CPU {cpu_percentage:.1f}%, Memory {mem_usage:.2f} MB")

            if suggestion:
                recommendations.append({
                    "namespace": namespace,
                    "pod_name": pod,
                    "cpu_usage": f"{cpu_usage:.2f} cores",
                    "cpu_percentage": f"{cpu_percentage:.1f}%",
                    "memory_usage": f"{mem_usage:.2f} MB",
                    "memory_percentage": f"{mem_percentage:.1f}%",
                    "suggested_optimization": ", ".join(suggestion),
                    "reason": "; ".join(reason)
                })

        except (KeyError, ValueError, TypeError) as e:
            logging.warning(f"⚠️ Skipping pod {pod} due to invalid data: {e}")

    return recommendations

def display_recommendations(recommendations):
    """Formats and displays optimization recommendations in a clean table format"""
    headers = ["Namespace", "Pod Name", "CPU Usage", "CPU %", "Memory Usage", "Memory %", "Suggested Optimization"]

    formatted_recommendations = [
        [rec["namespace"], rec["pod_name"], rec["cpu_usage"], rec["cpu_percentage"], rec["memory_usage"],
         rec["memory_percentage"], textwrap.fill(rec["suggested_optimization"], width=30)]
        for rec in recommendations
    ]

    if formatted_recommendations:
        print("\n🔍 Optimization Suggestions:\n")
        print(tabulate(formatted_recommendations, headers=headers, tablefmt="grid"))
    else:
        logging.info("✅ No optimizations needed. All pods are well-optimized.")

def export_to_json(recommendations, filename="optimization_suggestions.json"):
    """Exports recommendations to a JSON file securely"""
    try:
        with open(filename, "w") as json_file:
            json.dump(recommendations, json_file, indent=4)
        logging.info(f"✅ Data exported successfully to {filename}")
    except IOError as e:
        logging.error(f"❌ Error writing to file: {e}")

def main():
    args = get_args()
    global PROMETHEUS_URL
    PROMETHEUS_URL = args.prometheus_url

    logging.info(f"🔄 Checking Prometheus availability at {PROMETHEUS_URL}...")
    if not check_prometheus_availability():
        logging.error("❌ Exiting: Prometheus is not reachable.")
        return

    logging.info("🔄 Fetching data from Prometheus...")
    cpu_data = query_prometheus(QUERIES["cpu_usage"])
    memory_data = query_prometheus(QUERIES["memory_usage"])
    cpu_requests = query_prometheus(QUERIES["cpu_requests"])
    memory_requests = query_prometheus(QUERIES["memory_requests"])

    logging.info("🔎 Analyzing resource usage...")
    recommendations = analyze_usage(cpu_data, memory_data, cpu_requests, memory_requests)

    display_recommendations(recommendations)
    export_to_json(recommendations, args.output)

if __name__ == "__main__":
    main()
