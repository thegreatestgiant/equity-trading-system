#!/usr/bin/env bash
# Bootstraps the k3s Control Plane and required host-level CLI tools.
# Supports initializing a new HA cluster OR joining an existing one as a Control Plane.

set -e

JOIN_IP=""
if [ "${1:-}" == "--join" ] && [ -n "${2:-}" ]; then
    JOIN_IP="$2"
    if [ -z "${K3S_TOKEN}" ]; then
        echo "❌ ERROR: K3S_TOKEN must be set when joining an existing control plane."
        echo "Usage: sudo K3S_TOKEN=<token> ./remote_cp_up.sh --join <EXISTING_CP_IP>"
        exit 1
    fi
fi

echo "🚀 Bootstrapping K3s Control Plane..."

# 1. Install & Verify Tailscale
if ! command -v tailscale &>/dev/null; then
    echo "📦 Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
fi

if ! tailscale status &>/dev/null; then
    echo "⚠️  Tailscale is not connected. Please authenticate:"
    sudo tailscale up
fi

TAILSCALE_IP=$(tailscale ip -4)
echo "✅ Tailscale IP detected: ${TAILSCALE_IP}"

# 2. Install K3s (Control Plane)
if ! command -v k3s &>/dev/null; then
    if [ -z "$JOIN_IP" ]; then
        echo "📦 Initializing New HA K3s Server (embedded etcd)..."
        curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server \
          --cluster-init \
          --node-ip=${TAILSCALE_IP} \
          --flannel-iface=tailscale0 \
          --bind-address=${TAILSCALE_IP} \
          --advertise-address=${TAILSCALE_IP} \
          --tls-san=${TAILSCALE_IP}" sh -s -
    else
        echo "📦 Joining Existing HA Cluster as a Control Plane..."
        curl -sfL https://get.k3s.io | K3S_TOKEN="${K3S_TOKEN}" INSTALL_K3S_EXEC="server \
          --server https://${JOIN_IP}:6443 \
          --node-ip=${TAILSCALE_IP} \
          --flannel-iface=tailscale0 \
          --bind-address=${TAILSCALE_IP} \
          --advertise-address=${TAILSCALE_IP} \
          --tls-san=${TAILSCALE_IP}" sh -s -
    fi
else
    echo "✅ K3s is already installed."
fi

# Wait for k3s to be ready
echo "⏳ Waiting for K3s API to become available..."
until sudo k3s kubectl get nodes &>/dev/null; do
    sleep 2
done

# 3. Install Host CLI Tools (Flux, Helm)
if ! command -v flux &>/dev/null; then
    echo "📦 Installing Flux CLI..."
    curl -s https://fluxcd.io/install.sh | sudo bash
fi

if ! command -v helm &>/dev/null; then
    echo "📦 Installing Helm..."
    curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

# Setup local kubeconfig access for root/user
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config
sed -i "s/127.0.0.1/${TAILSCALE_IP}/g" ~/.kube/config

# 4. Extract Node Token and Generate Worker Command
NODE_TOKEN=$(sudo cat /var/lib/rancher/k3s/server/node-token)

echo ""
echo "================================================================="
echo "🎉 Control Plane Bootstrap Complete!"
echo "Your API Server is reachable at: https://${TAILSCALE_IP}:6443"
echo "================================================================="
echo ""
echo "To join another CONTROL PLANE node, run:"
echo "-----------------------------------------------------------------"
echo "sudo K3S_TOKEN=${NODE_TOKEN} ./remote_cp_up.sh --join ${TAILSCALE_IP}"
echo "-----------------------------------------------------------------"
echo ""
echo "To join a WORKER node, run:"
echo "-----------------------------------------------------------------"
echo "sudo K3S_TOKEN=${NODE_TOKEN} CONTROL_PLANE_IP=${TAILSCALE_IP} ./remote_worker_up.sh"
echo "-----------------------------------------------------------------"
