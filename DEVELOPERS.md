# 📈 Equity Trading App: Developer Onboarding Guide

Welcome to the Equity Trading App repository! This guide will help you operate our local Kubernetes (k3d) environment.

Our infrastructure strictly follows a **GitOps** methodology. Every component of our infrastructure is declarative and version-controlled. You **do not** need to manually modify Kubernetes manifests or understand Helm to run this locally; you just need to use the provided scripts.

---

## 🚀 1. Activating the Observability Stack

To conserve local system resources, the comprehensive observability stack (Loki, Promtail, Prometheus, Grafana) is disabled by default.

Run this command to start up the whole cluster

```bash
./cluster_up.sh
```

Max, this command will sync all of the changes to your github repo as opposed to the org one

```bash
./cluster_up.sh --max
```

> ⚠️ **IMPORTANT: BE PATIENT!** > After running `./cluster_up.sh`, it takes about **1 to 2 minutes** for the GitOps controllers to reconcile, pull the necessary images, initialize the Loki database, and start the Grafana web server. If the page doesn't load immediately, grab a coffee and wait for the pods to spin up!

---

## 📊 2. Accessing & Using Grafana

Once the cluster is up, Grafana is accessible via your browser. Because of how our local Traefik load balancer is configured, you must specify **port 8080**.

* **URL:** `http://grafana.localhost:8080`
* **Username:** `admin`
* **Password:** `Rust!`

Navigate to **Dashboards -> FastAPI Developer Dashboard** (or k3d Stats) to view the live log feeds and cluster statistics.

## 📝 3. Writing Your Logs (Strict Conventions)

**Required Format:**
`[YYYY-MM-DD HH:MM:SS] LEVEL: Message`

**Example (Python Logbook):**
If you are working on the FastAPI or Streamlit services, configure your FileHandler format string exactly like this:

```python
import logbook
from pathlib import Path

# 1. Point to your specific subfolder!
LOG_FILE = Path("../../logs/FastAPI/app.log")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# 2. Use this exact format string
file_handler = logbook.FileHandler(
    LOG_FILE, 
    level='INFO', 
    format_string='[{record.time:%Y-%m-%d %H:%M:%S}] {record.level_name}: {record.channel}: {record.message}'
)
file_handler.push_application()
```

---

## 🦊 5. Important Notice for Max: GitOps and Locust Load Testing

Hey Max! As you configure or execute load tests against the FastAPI backend using Locust, please adhere to our architectural standards.

### GitOps Principles

We utilize **Flux** for GitOps operations. The `main` branch of this GitHub repository is the absolute source of truth for the cluster's state. Any manual, imperative changes (e.g., using `kubectl edit` or temporary UI workarounds) will be detected as configuration drift and immediately overwritten by Flux controllers.

### Updating and Testing `locustfile.py`

Locust is deployed via our GitOps pipeline and is strictly maintained at 1 replica. The load-testing script (`locustfile.py`) is injected into the Locust Pod via a dynamically generated ConfigMap.

To update and test your load-testing scripts locally without conflicting with Flux, utilize the provided deployment script:

1. **Modify the Script:** Make your required changes to `backend/Locust/locustfile.py`.
2. **Execute the Reload Script:** From the repository root, run:

    ```bash
    ./locust_reload.sh
    ```

3. **Validate:** This script synchronizes your local code changes with the cluster and forces a rollout of the Locust Pod, allowing you to immediately validate your updated load profiles.
