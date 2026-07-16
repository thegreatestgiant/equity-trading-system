Kubernetes/GitOps layer: manifests, cluster bootstrap config, and the local dev toolbox container. See [DEVELOPERS.md](../DEVELOPERS.md) for the day-to-day workflow.

### Layout
- **`manifests/base/`** — the canonical app/data-layer/infrastructure manifests, organized into `apps/` (fastapi, streamlit, locust, db-syncer, trade-writer, price-cacher, redis-populator, adminer, redisinsight, error-pages), `data-layer/` (cnpg, redis, redis-proxy), and `infrastructure/` (cnpg-operator, keda, monitoring).
- **`manifests/overlays/<dev-name>/`** — one per-developer Kustomize overlay (`dev-sean`, `dev-max`, `dev-will`, `dev-yehuda`), each able to override images/resources/replicas from base.
- **`manifests/overlays/upstream/`** — the production-like overlay Flux deploys by default.
- **`manifests/overlays/k3s/`** — overlay for the distributed remote K3s cluster.
- **`flux-system/`** — the local k3d bootstrap: installs Flux itself (`kustomization.yaml`) and one `targets/target-<dev>.yaml` GitRepository+Kustomization set per developer, each pointing at that dev's overlay and reconciled in three ordered stages (`1-infra` → `2-data` → `3-apps`).
- **`clusters/k3s/`** — the equivalent bootstrap Flux uses for the remote K3s cluster (`k3s_manager.sh`'s `flux bootstrap` target path).
- **`compose.yml`** / **`Dockerfile.toolbox`** — the `k8s-toolbox` container: a privileged sidecar with `kubectl`/`k3d`/`flux` that mounts the Docker/Podman socket, used by every `make` target to run cluster commands without installing tooling on the host.
- **`k3d-config.yaml`** — the local k3d cluster topology (nodes, port mappings).

### How it fits together
`cluster_up.sh` starts `k8s-toolbox`, creates the k3d cluster, applies `flux-system/` to bootstrap Flux, then applies the target for the selected developer (`--sean`/`--max`/`--will`/`--yehuda`, default upstream). From there Flux reconciles `manifests/overlays/<target>/` into the cluster on its own; `make sync` forces an immediate reconciliation.
