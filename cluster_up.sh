#!/usr/bin/env bash

# Highly defensive scripting
set -e
set -u
case "$SHELL" in
*bash*) set -o pipefail ;;
esac

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HOST_ROOT="$PROJECT_ROOT"

# ============================================================
# systemd-resolved Pre-Flight Check (Excluding Ubuntu)
# ============================================================

OS_ID="unknown"
if [ -f /etc/os-release ]; then
    # Source the OS release file safely
    . /etc/os-release
    OS_ID="${ID:-unknown}"
fi

# Trigger ONLY if resolvectl exists AND the OS is NOT Ubuntu
if command -v resolvectl >/dev/null 2>&1 && [[ "$OS_ID" != "cachyos" ]] && [[ "$OS_ID" != "ubuntu" ]]; then
    echo ""
    echo "🌐 SYSTEMD-RESOLVED DETECTED"
    echo "----------------------------------------------------------"
    echo "⚠️  WARNING: Your host uses systemd-resolved (127.0.0.53)."
    echo "   If you are using Docker, this local stub often breaks"
    echo "   container DNS resolution, causing them to lose internet."
    echo ""
    echo "   To prevent this, please ensure your /etc/docker/daemon.json"
    echo "   is configured to bypass the local stub with upstream servers:"
    echo '   {'
    echo '     "dns": ["1.0.0.1", "1.1.1.1"]'
    echo '   }'
    echo "   (Remember to run 'sudo systemctl restart docker' after updating)"
    echo "----------------------------------------------------------"
fi

# ============================================================
# Flag parsing — default to upstream if no flag is given
# ============================================================
REPO_NAME="main-repo"
TARGET_FILE="target-upstream.yaml"

case "${1:-}" in
--sean)
    REPO_NAME="dev-repo-sean"
    TARGET_FILE="target-sean.yaml"
    ;;
--max)
    REPO_NAME="dev-repo-max"
    TARGET_FILE="target-max.yaml"
    ;;
--will)
    REPO_NAME="dev-repo-will"
    TARGET_FILE="target-will.yaml"
    ;;
--yehuda)
    REPO_NAME="dev-repo-yehuda"
    TARGET_FILE="target-yehuda.yaml"
    ;;
"")
    : # use defaults
    ;;
*)
    echo "❌ Unknown flag: ${1}"
    echo "   Usage: ./cluster_up.sh [--sean | --max | --yehuda | --will]"
    echo "   No flag = upstream (production-like)"
    exit 1
    ;;
esac

echo "=========================================================="
echo "🚀 Deploying Equity Trading System"
echo "   Source : $REPO_NAME"
echo "   Target : $TARGET_FILE"
echo "=========================================================="

# ============================================================
# Detect container engine
# ============================================================
ENGINE=""
if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
    ENGINE="podman"
elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    ENGINE="docker"
else
    echo "❌ ERROR: Neither Docker nor Podman is running."
    exit 1
fi
echo "✅ Container engine: $ENGINE"

# ============================================================
# Detect socket path
# ============================================================
USER_ID=$(id -u)
ACTUAL_SOCK="/var/run/docker.sock"
OSTYPE_VAL="${OSTYPE:-unknown}"

if [[ "$ENGINE" == "podman" ]]; then
    if [ -S "/run/user/$USER_ID/podman/podman.sock" ]; then
        ACTUAL_SOCK="/run/user/$USER_ID/podman/podman.sock"
    elif [ -S "/run/podman/podman.sock" ]; then
        ACTUAL_SOCK="/run/podman/podman.sock"
    else
        ACTUAL_SOCK="$HOME/.local/share/containers/podman/machine/podman.sock"
    fi
else
    if [[ "$OSTYPE_VAL" =~ ^(msys|cygwin|win32)$ ]]; then
        ACTUAL_SOCK="//var/run/docker.sock"
    elif [ ! -S "$ACTUAL_SOCK" ]; then
        if [ -S "/run/user/$USER_ID/docker.sock" ]; then
            ACTUAL_SOCK="/run/user/$USER_ID/docker.sock"
        elif [ -S "$HOME/.docker/run/docker.sock" ]; then
            ACTUAL_SOCK="$HOME/.docker/run/docker.sock"
        fi
    fi
fi
echo "✅ Socket: $ACTUAL_SOCK"

# ============================================================
# Sanity check
# ============================================================
if [ ! -d "$PROJECT_ROOT/k8s" ]; then
    echo "❌ ERROR: 'k8s' not found. Are you running from the repo root?"
    exit 1
fi

cd "$PROJECT_ROOT/k8s"
echo "DOCKER_HOST_PATH=$ACTUAL_SOCK" >.env

# ============================================================
# Fix permissions
# ============================================================
chmod 755 . 2>/dev/null || true
chmod 644 k3d-*.yaml 2>/dev/null || true
chmod -R 755 manifests 2>/dev/null || true

# ============================================================
# Tear down any previous environment
# ============================================================
echo "🧹 Tearing down previous environment..."
set +e
$ENGINE compose up -d >/dev/null 2>&1
$ENGINE exec k8s-toolbox k3d cluster delete dev-cluster >/dev/null 2>&1
$ENGINE compose down -v >/dev/null 2>&1
$ENGINE network rm k3d-network >/dev/null 2>&1
$ENGINE rm -f $($ENGINE ps -aq -f name=k3d-dev-cluster) >/dev/null 2>&1
set -e

# ============================================================
# Start toolbox + create cluster (injects Flux controllers only)
# ============================================================
echo "📦 Starting k8s-toolbox..."
$ENGINE compose up -d --build
sleep 2

echo "🚀 Creating cluster (bootstrapping Flux controllers)..."

# Use --no-host-dns to stop K3d from touching /etc/resolv.conf
$ENGINE exec -e HOST_ROOT="$PROJECT_ROOT" -i k8s-toolbox \
    k3d cluster create --config k8s/k3d-config.yaml \
    --k3s-arg "--resolv-conf=/tmp/custom-resolv.conf@server:*" \
    --k3s-arg "--resolv-conf=/tmp/custom-resolv.conf@agent:*"

# ============================================================
# Wait for API server — check the API endpoint directly,
# not just node readiness, to avoid the openapi dial error
# ============================================================
echo "⏳ Waiting for Kubernetes API server..."
until $ENGINE exec k8s-toolbox kubectl get --raw /readyz >/dev/null 2>&1; do
    echo "   ...still waiting"
    sleep 5
done
echo "✅ API server is ready."

# ============================================================
# Create Postgres Password
# ============================================================

echo "🔐 Generating db-credentials secret..."

# Pre-create the namespaces that need the secret before Flux runs
for NS in data backend secrets; do
    $ENGINE exec -i k8s-toolbox kubectl create namespace "$NS" \
        --dry-run=client -o yaml |
        $ENGINE exec -i k8s-toolbox kubectl apply -f -
done

# Generate once, apply to all consumer namespaces
PG_PASS=$(openssl rand -base64 24 | tr -d '=+/' | cut -c1-24)
for NS in data backend; do
    $ENGINE exec -i k8s-toolbox kubectl create secret generic db-credentials \
        --from-literal=POSTGRES_USER=trade_admin \
        --from-literal=POSTGRES_PASSWORD="$PG_PASS" \
        --namespace="$NS" \
        --dry-run=client -o yaml |
        $ENGINE exec -i k8s-toolbox kubectl apply -f -
done
echo "✅ db-credentials created in data and backend namespaces."

# ============================================================
# Bootstrapping Flux (Pure IaC)
# ============================================================
echo "📦 Bootstrapping Flux Controllers (Declarative Kustomize)..."

# Apply the 4-line kustomization.yaml file directly from your repo.
# Kubernetes will automatically download the required images in the background!
$ENGINE exec -i k8s-toolbox kubectl apply -k "k8s/flux-system"

# Wait for Flux CRDs to be established before we apply targets
echo "⏳ Waiting for Flux CRDs to initialize..."
until $ENGINE exec k8s-toolbox kubectl get crd gitrepositories.source.toolkit.fluxcd.io >/dev/null 2>&1; do
    echo "   ...waiting for Flux CRDs"
    sleep 5
done
echo "✅ Flux CRDs are ready."

# ============================================================
# Apply the correct target (GitRepository + Kustomization)
# ============================================================
echo "🔄 Applying target: $TARGET_FILE"
$ENGINE exec -i k8s-toolbox \
    kubectl apply -f "k8s/flux-system/targets/$TARGET_FILE"

# ============================================================
# Force an immediate reconciliation so we don't wait 1 minute
# ============================================================
echo "⚡ Forcing Flux sync..."
$ENGINE exec -i k8s-toolbox flux reconcile source git "$REPO_NAME"
$ENGINE exec -i k8s-toolbox flux reconcile kustomization 1-infra --with-source

echo ""
echo "📈 ======================================================= 📈"
echo "               BULL MARKET ENGAGED: SYSTEM LIVE              "
echo " --------------------------------------------------------- "
echo " 🟢 API Gateway       -> http://api.localhost:8080"
echo " 📊 Streamlit UI      -> http://streamlit.localhost:8080"
echo " 🦗 Locust Load Test  -> http://locust.localhost:8080"
echo " 🔭 Grafana Metrics   -> http://grafana.localhost:8080"
echo " 🐘 Adminer Database  -> http://adminer.localhost:8080"
echo " "
echo " 🔐 Default System Credentials:"
echo "    Grafana UI -> User: admin | Pass: Rust!"
echo "    PostgreSQL -> User: trade_admin | Pass: $PG_PASS"
echo "📈 ======================================================= 📈"
