# Product Strategy & Architecture Playbook: k8s-prometheus-analyzer

This document outlines the end-to-end product design, packaging options, installation methods, onboarding flows, post-onboarding engagement, daily operational workflows, required internal operational tools, and visualization strategies for `k8s-prometheus-analyzer`.

---

## 🌐 1. The Marketing Website & Landing Page

The website is the front door. It must communicate **immediate financial and operational value** within 5 seconds.

### Core Sections of the Landing Page
1. **The Hero Section**:
   * **Headline**: *"Stop Paying for Idle Kubernetes Resources."*
   * **Subheadline**: *"Scan your cluster in 2 minutes. Identify waste, get optimization code, and reduce your cloud bills by 30% without changing your tools."*
   * **Primary CTA**: *"Run Free Scan (No Account Required)"* (CLI command copy-paste button).
   * **Secondary CTA**: *"Start Free Trial (SaaS)"*.
2. **Interactive Live Demo**:
   * An embedded mock dashboard showing a cluster saving $4,200/month. Users can toggle sliders to see how shifting CPU/memory thresholds dynamically updates the potential savings.
3. **The "Try it Locally" Box (CLI Hook)**:
   * A clean terminal snippet showing the install command:
     ```bash
     curl -s https://k8s-analyzer.com/install.sh | sh && k8s-analyze --sample
     ```
4. **SaaS vs. On-Premises Features Comparison**:
   * Highlight that data privacy is respected: *"Keep data local (On-Premises deployment available for Enterprise)."*

---

## ⚙️ 2. Installation & Integration Options

Depending on the customer type, the product is integrated differently:

### Option A: Cloud SaaS (For Individuals & Mid-Sized Startups)
* **How it works**: The user's cluster runs a lightweight agent that forwards metadata to the hosted control plane.
* **Installation steps**:
  1. The user logs into the SaaS dashboard and gets an **API Key** and **Cluster ID**.
  2. They install the agent in their cluster using Helm:
     ```bash
     helm repo add k8s-analyzer https://charts.k8s-analyzer.com
     helm install k8s-analyzer-agent k8s-analyzer/agent \
       --set apiKey="YOUR_API_KEY" \
       --set clusterId="prod-us-east-1"
     ```
  3. The agent starts sending anonymized stats to `https://api.k8s-analyzer.com`.

### Option B: Self-Hosted Enterprise (For Secure Corporates/Banks)
* **How it works**: The client receives a package containing the backend, database, and UI. No external internet traffic is allowed.
* **Packaging & Delivery**:
  * Distributed via a single enterprise Helm chart or using **Replicated KOTS** (Kubernetes Off-the-Shelf installer).
  * **License Key Enforcement**: During setup, the customer inputs an offline-decryptable license key file (`license.jwt`). The dashboard checks this signature to allow startup and set bounds (e.g. maximum nodes).
  * **Air-gapped Mode**: All Docker images are hosted in a secure, private container registry or shipped as tarballs.

---

## 🚀 3. Step-by-Step Onboarding Flow

Onboarding should minimize friction to reach the **"Aha!" moment** (seeing the first cost saving recommendation).

```
[Sign Up / Auth] ──> [Select Deployment Model] ──> [Install Agent] ──> [Aha! Moment (1st Report)]
```

* **Step 1: Auth**: Quick signup (GitHub, Google, SSO, or traditional email).
* **Step 2: Deployment Choice**:
  * *"Deploy via SaaS Agent (Fastest)"*
  * *"Deploy Self-Hosted (Secure / Private)"* (Downloads the Enterprise Helm chart + license key).
* **Step 3: Setup Wizard**:
  * Displays the customized Helm/Docker install command pre-filled with the user's API Key.
  * Shows a loading spinner: *"Waiting for first connection from your cluster..."*
* **Step 4: Immediate Analysis**:
  * As soon as the agent connects and pushes the first run, the screen transitions to the dashboard displaying:
    * 🔴 **Total Monthly Waste** (in Dollars).
    * ⚠️ **Resource Throttling Risks** (which apps are about to crash due to OOM/CPU limits).

---

## 📦 4. Packaging the Product: Individual vs. Company

| Customer Segment | Needs | Package Offered | Pricing |
| :--- | :--- | :--- | :--- |
| **Individual Developer / Indie Hacker** | Quick sizing recommendations, local reports. | **CLI / Open Source Edition** (The current script + basic HTML report). | **Free** (Open Source) |
| **Mid-Market Company (SaaS Model)** | Multi-cluster overview, alerts, team access, and basic Slack integrations. | **SaaS Starter/Growth** (Hosted dashboard, cloud-processed metrics). | **Usage-based** (e.g., $10 per monitored node per month). |
| **Enterprise / Secure Corp** | Zero data export, SAML SSO, high-availability setups, custom rules. | **Self-Hosted / On-Premise Enterprise** (Fully deployed in client's VPC, air-gapped). | **Annual contract** (e.g., $12k to $60k/year based on cluster scale). |

---

## 📈 5. Post-Onboarding Engagement: Retaining the Customer

Once a customer is onboarded, you must continuously demonstrate value so they don't churn:

1. **Weekly Cost-Saving Digest Email**:
   * Sent to engineering managers: *"This week, we found $1,200 of new waste. Click here to auto-apply optimizations."*
2. **Interactive Pull Request Action (GitOps)**:
   * When the client's codebase updates, the tool checks resource requirements. If they drift back into over-provisioning, the tool automatically posts a warning on their PR.
3. **Anomaly Alerts**:
   * If a service starts consuming 10x its normal CPU or throttling heavily, the tool pushes high-priority alerts via PagerDuty/Slack.
4. **Quantified ROI Reporting**:
   * A "Monthly Summary" report for CTOs: *"In the last 30 days, we saved your team $8,450. Your software license paid for itself 8x over."*

---

## 🔄 6. Daily Operational Workflows

To operate this business successfully, we must split our workflows into **how the Customer uses it** and **how your Company builds/operates it**.

### A. The Customer's Daily Workflow (How they use it)
A DevOps/SRE Engineer or FinOps Manager integrates the tool into their regular routine:

1. **Morning Slack/Alerts Review**:
   * SRE check their alert channel. If a pod started throttling CPU or is close to running out of memory (OOM), they see it directly in Slack with a link to the dashboard.
2. **Reviewing Auto-Generated Pull Requests (GitOps)**:
   * The team reviews their Git repository (GitHub/GitLab). They see a Pull Request opened by `k8s-analyzer-bot` recommending a reduction of memory requests on a non-production service. They click **Merge** to instantly optimize the cluster.
3. **Weekly Planning**:
   * During planning, the SRE team opens the dashboard to check the **Top 5 Wasteful Workloads** and assigns tasks to adjust their Helm values.

### B. Your Company's Daily Workflow (How you run the business)
Your startup team works across Engineering, Customer Success, and Sales:

#### 1. Engineering & Infrastructure (Build & Run)
* **Ingestion Monitoring**: Monitor the SaaS API gateway. Ensure that payload delivery from thousands of active customer agents is fast, secure, and has low latency.
* **Refining PromQL & Rule Quality**: Analyze edge cases. (e.g., *"Why did a client's DaemonSet report false over-provisioning?"*). Tweak the default threshold rules in [analyzer.py](file:///Users/rahulbansod01/Projects/k8s_prometheus_analyzer/k8s-monitor/k8s_prometheus_analyzer/analyzer.py) to prevent false alerts.
* **Integrations Maintenance**: Ensure the GitHub/GitLab integrations for GitOps PR generation remain functional and secure.

#### 2. Customer Success & Support (Onboarding & Help)
* **Prometheus Configuration Support**: Every company configures Prometheus differently. A main support task is helping customers fix their Helm/agent configurations when metrics aren't reporting properly due to missing labels (`kube-state-metrics`).
* **Self-Hosted License Management**: Issue and manage license key files (`license.jwt`) for newly onboarded enterprise trials or annual contracts.

#### 3. Sales & Growth (Revenue Generation)
* **Reviewing Free Visualizer Uploads**: Check who is uploading JSON files on the website's free visualizer. If an anonymous user uploads a file showing **$20,000/month in waste**, reach out to them based on their domain/network metadata to pitch the automated enterprise version.
* **Enterprise Funnel Nurturing**: Follow up with trial users whose trials are ending, offering custom rule config support.

---

## 🛠️ 7. Required Internal Operations Tools

To support these daily workflows, your company needs to build/use five key internal tools:

### 1. The Internal Admin Portal (The "Control Tower")
A secure, internal web interface for your Customer Success and Sales teams.
* **Tenant Search**: Search for any customer account, view their active clusters, see how many nodes they monitor, and verify if their agent is actively pushing metrics.
* **Feature Flags Management**: Turn on/off premium features (like GitOps auto-PRs or advanced alerts) manually for pilot users.
* **System Limits Configurator**: Set ingestion rate limits (e.g., *"Tenant X can only push metrics once every 15 minutes"* to protect server load).

### 2. License Key Manager (Offline JWT Signer)
A secure utility (CLI or web tool) used by Sales/CS to generate offline license files for **Self-Hosted Enterprise** customers.
* **Input Fields**: Customer ID, Max Node Limit, Max Clusters, Expiration Date.
* **Function**: Cryptographically signs a JSON Web Token using an offline private key.
* **Output**: A `license.jwt` file that the client drops into their self-hosted Helm installation. The client's local platform checks this signature against your public key to authenticate the installation without needing internet access.

### 3. Lead Enrichment Engine (For Free Uploads)
An automated pipeline that monitors files uploaded to the website's free visualizer.
* **Data Enrichment**: When someone uploads a scan, capture their IP address and run it through services like **Clearbit** or **Apollo** to identify the company name (e.g., *"A user from Stripe uploaded a cluster report showing $15,000/month waste"*).
* **Slack Alerts**: Push a notification directly to the Sales team's internal Slack channel: *"🔥 Hot Lead: User from [Company] uploaded a scan with $X,XXX/mo waste. Click here to view report and target outreach."*

### 4. Anonymized Diagnostic Bundle Tool
Enterprise support teams are not allowed to join screen-shares or access client servers directly.
* **What it is**: A script packaged in the Self-Hosted Helm installation. When a client encounters an error, they run:
  `k8s-analyze --generate-diagnostics`
* **Output**: Generates a ZIP file containing anonymized config settings, execution logs, and raw metric schemas (with actual workload names and namespaces replaced by hashes). The client uploads this ZIP to your support portal so engineers can debug safely.

### 5. SaaS Telemetry & Cost Dashboard
A Grafana/Prometheus dashboard to monitor your own SaaS infrastructure.
* **Key Metrics to Track**:
  * Agent payload processing latency (in milliseconds).
  * Rate-limited requests (HTTP 429).
  * Webhook delivery failure rates (Slack API limits/timeouts).
  * Storage footprint growth (to calculate your own database storage costs).

---

## 📊 8. Dashboard & Visualization Architecture

To support different deployment environments, the visualization layer is decoupled:

### Native Self-Hosted UI
* An embedded, lightweight web server packaged in the Enterprise Helm installation.
* Provides a secure local console for teams who want an immediate, dedicated right-sizing UI.

### Grafana Dashboard Integration (Optional / Alternative)
* **How it works**: For clients who want zero UI overhead and prefer using their existing monitoring stack, the agent can export optimization recommendations back to their local Prometheus instance (via HTTP `/metrics` endpoint or pushing to a Pushgateway).
* **Delivery**: We provide a readymade `grafana/dashboard.json` ConfigMap template. Grafana scrapes the analyzer metrics and populates the dashboard automatically. No dedicated native UI server needs to run.
