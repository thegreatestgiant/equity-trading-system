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
# Flag parsing — default to upstream if no flag is given
# ============================================================
REPO_NAME="main-repo"
TARGET_FILE="target-upstream.yaml"

case "${1:-}" in
--sean)
    REPO_NAME="dev-repo"
    TARGET_FILE="target-fork.yaml"
    ;;
--max)
    REPO_NAME="dev-repo-max"
    TARGET_FILE="target-max.yaml"
    ;;
"")
    : # use defaults
    ;;
*)
    echo "❌ Unknown flag: ${1}"
    echo "   Usage: ./cluster_up.sh [--sean | --max]"
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
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    ENGINE="docker"
elif command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
    ENGINE="podman"
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
if [ ! -d "$PROJECT_ROOT/backend/k8s" ]; then
    echo "❌ ERROR: 'backend/k8s' not found. Are you running from the repo root?"
    exit 1
fi

cd "$PROJECT_ROOT/backend/k8s"
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
$ENGINE exec -e HOST_ROOT="$PROJECT_ROOT" -i k8s-toolbox \
    k3d cluster create --config backend/k8s/k3d-config.yaml

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

# Also wait for Flux CRDs to be established before we apply
# GitRepository/Kustomization objects, otherwise apply fails
echo "⏳ Waiting for Flux CRDs..."
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
    kubectl apply -f "backend/k8s/flux-system/targets/$TARGET_FILE"

# ============================================================
# Force an immediate reconciliation so we don't wait 1 minute
# ============================================================
echo "⚡ Forcing Flux sync..."
$ENGINE exec -i k8s-toolbox flux reconcile source git "$REPO_NAME"
$ENGINE exec -i k8s-toolbox flux reconcile kustomization dev-stack --with-source

echo ""
echo "📈 ======================================================= 📈"
echo "               BULL MARKET ENGAGED: SYSTEM LIVE              "
echo " --------------------------------------------------------- "
echo " 🟢 API Gateway       -> http://localhost:8080"
echo " 📊 Streamlit UI      -> http://streamlit.localhost:8080"
echo " 🦗 Locust Load Test  -> http://locust.localhost:8080"
echo " 🔭 Grafana Metrics   -> http://grafana.localhost:8080"
echo " "
echo " 🔐 Default Credentials:"
echo "    User: admin  |  Pass: Rust!"
echo "📈 ======================================================= 📈"
