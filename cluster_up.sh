#!/usr/bin/env bash

# Highly defensive scripting
set -e
set -u
case "$SHELL" in
*bash*) set -o pipefail ;;
esac

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HOST_ROOT="$PROJECT_ROOT"

REPO_NAME="main-repo"
TARGET_FILE="target-upstream.yaml"

if [[ "${1:-}" == "--sean" ]]; then
    REPO_NAME="dev-repo"
    TARGET_FILE="target-fork.yaml"
elif [[ "${1:-}" == "--max" ]]; then
    REPO_NAME="dev-repo-max"
    TARGET_FILE="target-max.yaml"
fi

echo "=========================================================="
echo "🚀 Deploying to Cluster (Source: $REPO_NAME)"
echo "=========================================================="

# 3. Check for Container Engine
ENGINE=""
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    ENGINE="docker"
elif command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
    ENGINE="podman"
else
    echo "❌ ERROR: Neither Docker nor Podman is running or accessible."
    exit 1
fi
echo "✅ Detected container engine: $ENGINE"

# 4. Locate the correct Socket (Cross-Platform / Rootless Support)
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
    if [[ "$OSTYPE_VAL" == "msys" || "$OSTYPE_VAL" == "cygwin" || "$OSTYPE_VAL" == "win32" ]]; then
        ACTUAL_SOCK="//var/run/docker.sock"
    elif [ ! -S "$ACTUAL_SOCK" ]; then
        if [ -S "/run/user/$USER_ID/docker.sock" ]; then
            ACTUAL_SOCK="/run/user/$USER_ID/docker.sock"
        elif [ -S "$HOME/.docker/run/docker.sock" ]; then
            ACTUAL_SOCK="$HOME/.docker/run/docker.sock"
        fi
    fi
fi
echo "✅ Using socket at: $ACTUAL_SOCK"

# 5. Navigate securely into the Kubernetes directory
if [ ! -d "$PROJECT_ROOT/backend/k8s" ]; then
    echo "❌ ERROR: Directory 'backend/k8s' not found!"
    exit 1
fi
cd "$PROJECT_ROOT/backend/k8s"

# Write the .env file so Compose can read the socket path
echo "DOCKER_HOST_PATH=$ACTUAL_SOCK" >.env

# 6. Fix File Permissions safely
echo "✅ Fixing configuration file permissions..."
chmod 755 . 2>/dev/null || true
chmod 644 k3d-*.yaml 2>/dev/null || true
chmod -R 755 manifests 2>/dev/null || true

# 7. Boot Sequence Cleanup
echo "🧹 Cleaning up previous dev environment..."
set +e # Disable strict mode temporarily for cleanup
$ENGINE exec k8s-toolbox k3d cluster delete dev-cluster >/dev/null 2>&1
$ENGINE compose down -v >/dev/null 2>&1
set -e # Re-enable strict mode

echo "📦 Starting the k8s-toolbox..."
$ENGINE compose up -d --build

# Give the engine a moment to attach the volume before firing commands
sleep 2

echo "🚀 Spinning up the cluster with the FULL infrastructure stack..."
$ENGINE exec -e HOST_ROOT="$PROJECT_ROOT" -i k8s-toolbox k3d cluster create --config backend/k8s/k3d-config.yaml

echo "🔄 Updating Source to: $REPO_NAME"

# 1. Apply the target (which now creates BOTH the GitRepository AND the Kustomization)
$ENGINE exec -i k8s-toolbox kubectl apply -f "backend/k8s/flux-system/targets/$TARGET_FILE"

# 2. Force Reconciliation
echo "⚡ Forcing Sync..."
$ENGINE exec -i k8s-toolbox flux reconcile source git "$REPO_NAME"
$ENGINE exec -i k8s-toolbox flux reconcile kustomization dev-stack --with-source

echo "✅ Environment synced to $REPO_NAME via $TARGET_FILE overlay"

echo ""
echo "=========================================================="
echo "✅ FULL TRADING ENVIRONMENT DEPLOYED"
echo "🌐 API URL:     http://localhost:8080 (or api.localhost)"
echo "🌐 Streamlit URL:     http://streamlit.localhost:8080 (or api.localhost)"
echo "🐛 Locust URL:  http://locust.localhost:8080"
echo "📊 Grafana:     http://grafana.localhost:8080"
echo "👤 Username:    admin"
echo "🔑 Password:    Rust!"
echo "=========================================================="
