#!/usr/bin/env bash
# Bootstraps a k3s Agent (Worker Node) and connects it to the Control Plane.

set -e

if [ -z "${K3S_TOKEN}" ] || [ -z "${CONTROL_PLANE_IP}" ]; then
    echo "❌ ERROR: K3S_TOKEN and CONTROL_PLANE_IP must be set."
    echo "Usage: sudo K3S_TOKEN=<token> CONTROL_PLANE_IP=<ip> ./remote_worker_up.sh"
    exit 1
fi

echo "🚀 Bootstrapping K3s Worker Node..."

# 1. Install & Verify Tailscale
if ! command -v tailscale &> /dev/null; then
    echo "📦 Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
fi

if ! tailscale status &> /dev/null; then
    echo "⚠️  Tailscale is not connected. Please authenticate:"
    sudo tailscale up
fi

AGENT_TAILSCALE_IP=$(tailscale ip -4)
echo "✅ Tailscale Agent IP detected: ${AGENT_TAILSCALE_IP}"

# 2. Install K3s (Agent)
if ! command -v k3s &> /dev/null; then
    echo "📦 Joining K3s Cluster..."
    curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="agent \
      --node-ip=${AGENT_TAILSCALE_IP} \
      --flannel-iface=tailscale0" \
      K3S_URL="https://${CONTROL_PLANE_IP}:6443" \
      K3S_TOKEN="${K3S_TOKEN}" sh -s -
else
    echo "✅ K3s is already installed. If you need to rejoin, uninstall k3s-agent first."
fi

echo "================================================================="
echo "🎉 Worker Node Bootstrap Complete!"
echo "The node should appear in the cluster shortly. Verify on the Control Plane."
echo "================================================================="
