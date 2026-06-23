.PHONY: toolbox-up toolbox-down cluster-up cluster-up-sean cluster-up-max \
        cluster-down shell run kubectl rebuild status status-wide status-svc \
        sync reload-grafana \
        chaos-api chaos-streamlit chaos-worker chaos-redis chaos-node-stop chaos-node-start \
        shell-api shell-ui shell-worker shell-postgres psql redis-cli \
	seed-trades

DOCKER   ?= docker
HOST_ROOT := $(shell cd ../.. && pwd)
export HOST_ROOT

# ==========================================
# 🏗️ TOOLBOX
# ==========================================

toolbox-up:
	$(DOCKER) compose up -d --build

toolbox-down:
	$(DOCKER) compose down

# ==========================================
# 🚀 CLUSTER LIFECYCLE
# ==========================================

# Default: points to upstream (production-like) repo
cluster-up:
	@echo "🚀 Deploying from UPSTREAM (production-like)..."
	@cd ../.. && bash cluster_up.sh

# Your personal dev fork
cluster-up-sean:
	@echo "🚀 Deploying from Sean's fork..."
	@cd ../.. && bash cluster_up.sh --sean

# Max's dev fork
cluster-up-max:
	@echo "🚀 Deploying from Max's fork..."
	@cd ../.. && bash cluster_up.sh --max

cluster-down:
	-$(DOCKER) exec k8s-toolbox k3d cluster delete dev-cluster

# Nuke everything and rebuild from the upstream source
rebuild: cluster-down toolbox-down
	@sleep 2
	$(MAKE) --no-print-directory cluster-up-sean

# ==========================================
# 🔧 DEBUGGING
# ==========================================

shell:
	$(DOCKER) exec -it k8s-toolbox bash

run:
	@$(DOCKER) exec -it k8s-toolbox $(CMD)

kubectl:
	@$(DOCKER) exec -it k8s-toolbox kubectl $(CMD)

# ==========================================
# 📊 CLUSTER STATUS
# ==========================================

status:
	@echo "🟢 CURRENT POD STATUS:"
	@$(DOCKER) exec -it k8s-toolbox kubectl get pods -A

status-wide:
	@echo "🌐 WIDE POD OVERVIEW:"
	@$(DOCKER) exec -it k8s-toolbox kubectl get pods -A -o wide

status-svc:
	@echo "🔌 ACTIVE NETWORK SERVICES:"
	@$(DOCKER) exec -it k8s-toolbox kubectl get svc -A

sync:
	$(DOCKER) exec -it k8s-toolbox flux reconcile kustomization dev-stack --with-source

reload-grafana:
	@$(DOCKER) exec -it k8s-toolbox kubectl delete pod -l app.kubernetes.io/name=grafana -n monitoring

# ==========================================
# 🌪️ CHAOS ENGINEERING
# ==========================================

chaos-api:
	@echo "🔫 Terminating all FastAPI pods..."
	@$(DOCKER) exec -it k8s-toolbox kubectl delete pods -l app=fastapi -n backend

chaos-streamlit:
	@echo "🔫 Terminating all Streamlit pods..."
	@$(DOCKER) exec -it k8s-toolbox kubectl delete pods -l app=streamlit -n frontend

chaos-worker:
	@echo "🔫 Terminating Trade-Writer worker pods..."
	@$(DOCKER) exec -it k8s-toolbox kubectl delete pods -l app=trade-writer -n backend

chaos-redis:
	@echo "🧨 Terminating Redis Pod..."
	@$(DOCKER) exec -it k8s-toolbox kubectl delete pods -l app=redis -n backend

chaos-node-stop:
	@echo "🔥 Stopping the primary K3s node (Simulating Server Crash)..."
	@$(DOCKER) exec -it k8s-toolbox k3d node stop k3d-dev-cluster-server-0

chaos-node-start:
	@echo "🚑 Rebooting the primary K3s node..."
	@$(DOCKER) exec -it k8s-toolbox k3d node start k3d-dev-cluster-server-0

# ==========================================
# 🔍 INTERACTIVE SHELLS & DATABASES
# ==========================================

# Open a shell inside the Python FastAPI container
shell-api:
	@echo "🔌 Connecting to FastAPI backend..."
	@$(DOCKER) exec -it k8s-toolbox kubectl exec -it deployment/fastapi-api -n backend -- /bin/sh

# Open a shell inside the Python Streamlit container
shell-ui:
	@echo "🔌 Connecting to Streamlit frontend..."
	@$(DOCKER) exec -it k8s-toolbox kubectl exec -it deployment/streamlit -n frontend -- /bin/sh

# Open a shell inside the Rust Trade-Writer container
shell-worker:
	@echo "🔌 Connecting to Trade-Writer worker..."
	@$(DOCKER) exec -it k8s-toolbox kubectl exec -it deployment/trade-writer -n backend -- /bin/sh

# Open a shell inside the Postgres Database container
shell-postgres:
	@echo "🔌 Connecting to Postgres container..."
	@$(DOCKER) exec -it k8s-toolbox kubectl exec -it statefulset/postgres -n backend -- /bin/sh

# Open an interactive SQL prompt directly into your trading database!
psql:
	@echo "🐘 Starting interactive PostgreSQL session..."
	@$(DOCKER) exec -it k8s-toolbox kubectl exec -it statefulset/postgres -n backend -- psql -U trade_admin -d trades_database

# Open an interactive Redis CLI session
redis-cli:
	@echo "🔴 Connecting to Redis CLI..."
	@$(DOCKER) exec -it k8s-toolbox kubectl exec -it deployment/redis -n backend -- redis-cli

# ==========================================
# 💥 DATA GENERATION & SEEDING
# ==========================================

# Run the fake trades script inside a temporary cluster pod!
seed-trades:
	@echo "🌱 Spawning temporary uv pod to inject fake trades..."
	@cat ../DB/redis-postgres-syncers/test/send_fake_trades.py | \
	$(DOCKER) exec -i k8s-toolbox kubectl run trade-seeder --rm -i -n backend \
		--image=ghcr.io/astral-sh/uv:alpine \
		--env="REDIS_HOST=redis.backend.svc.cluster.local" \
		--restart=Never \
		-- sh -c "cat > script.py && uv run script.py"
