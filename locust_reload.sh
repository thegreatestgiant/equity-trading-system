#!/usr/bin/env bash

# Highly defensive scripting
set -e
set -u
case "$SHELL" in
*bash*) set -o pipefail ;;
esac

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================================="
echo "🔄 Reloading Locust configuration..."
echo "=========================================================="

# 1. Detect Container Engine
ENGINE=""
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    ENGINE="docker"
elif command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
    ENGINE="podman"
else
    echo "❌ ERROR: Neither Docker nor Podman is running."
    exit 1
fi

# 2. Recreate the ConfigMap by piping the local Python file into the toolbox
echo "📦 Updating ConfigMap 'locust-config'..."
cat "$PROJECT_ROOT/backend/Locust/locustfile.py" |
    $ENGINE exec -i k8s-toolbox sh -c 'kubectl create configmap locust-config --from-file=locustfile.py=/dev/stdin -o yaml --dry-run=client | kubectl apply -f -'

# 3. Force the Locust deployment to restart and pick up the new configuration
echo "♻️ Restarting Locust pods to apply changes..."
$ENGINE exec -i k8s-toolbox kubectl rollout restart deployment/locust-load-tester

echo "✅ Locust configuration successfully reloaded!"
