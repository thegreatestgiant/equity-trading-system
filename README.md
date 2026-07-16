# Equity Trading System

A containerized, Kubernetes-native high-frequency equity trading system: a FastAPI backend, a Streamlit UI, and Rust workers syncing Redis and Postgres.

### The Stack
* **API**: FastAPI (Python) with `uv` package management. See [`api/README.md`](api/README.md).
* **UI**: Streamlit (Python) with AG Grid tables for mass trading and data visualization. See [`web-ui/README.md`](web-ui/README.md).
* **Workers**: Rust syncers (`db-syncer`, `trade-writer`, `price-cacher`, `price-timeseries-cacher`, `redis-populator`) moving data between Redis and Postgres. See [`db/redis-postgres-syncers/README.md`](db/redis-postgres-syncers/README.md).
* **Data Layer**: Redis with Redis Sentinel (HA, fast ingestion), PostgreSQL via CloudNativePG (HA persistence), PgBouncer for connection pooling, Adminer and RedisInsight for DB inspection.
* **Autoscaling & Ingress**: KEDA for event-driven autoscaling, Traefik for ingress, Reloader for dynamic config updates.
* **Testing**: Locust for distributed load testing. See [`locust/README.md`](locust/README.md).
* **Infrastructure**: Kubernetes (k3d for local dev, K3s for distributed remote), Flux for GitOps, Loki/Grafana for observability. See [`k8s/README.md`](k8s/README.md).

### Getting Started
See [DEVELOPERS.md](DEVELOPERS.md) to set up your environment, manage overlays, and debug the cluster.

#### K3S Manager option
You can clone our k3s manager here 
```sh 
curl -sSL "https://raw.githubusercontent.com/SM26-Industrial-Software-Dev/equity-trading-system/main/k3s_manager.sh" -o k3s_manager.sh && chmod +x k3s_manager.sh
```

