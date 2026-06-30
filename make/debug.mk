## ==========================================
# 🕵️ DOWNWARD API & ENV DEBUGGING
# ==========================================

debug-api-manifest: ## 1. Check if the cluster actually received your new YAML
	@echo "🔍 Inspecting the Deployment manifest directly on the cluster..."
	@$(DOCKER) exec -it k8s-toolbox kubectl get deployment fastapi-api -n backend -o yaml | grep -A 15 "env:"

debug-api-env: ## 2. Check the live environment variables inside the running Pod
	@echo "🔍 Executing 'env' inside the active FastAPI pod..."
	@$(DOCKER) exec -it k8s-toolbox kubectl exec deployment/fastapi-api -n backend -- env | grep -E "NODE|POD|Worker|GIT|ENV"

bounce-api: ## 3. Force a graceful restart of the FastAPI pods to pick up new Env Vars
	@echo "🔄 Forcing a rolling restart of the FastAPI deployment..."
	@$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/fastapi-api -n backend
# ==========================================
# 🔍 INTERACTIVE SHELLS & DATABASES
# ==========================================

shell: ## Opens an interactive Shell
	$(DOCKER) exec -it k8s-toolbox bash

run: ## Runs anything in CMD=""
	@$(DOCKER) exec -it k8s-toolbox $(CMD)

kubectl: ## Runs kubectl CMD=""
	@$(DOCKER) exec -it k8s-toolbox kubectl $(CMD)

shell-api: ## 🔌 Connecting to FastAPI backend...
	@echo "🔌 Connecting to FastAPI backend..."
	@$(DOCKER) exec -it k8s-toolbox kubectl exec -it deployment/fastapi-api -n backend -- /bin/sh

shell-ui: ## 🔌 Connecting to Streamlit frontend...
	@echo "🔌 Connecting to Streamlit frontend..."
	@$(DOCKER) exec -it k8s-toolbox kubectl exec -it deployment/streamlit -n frontend -- /bin/sh

shell-worker: ## 🔌 Connecting to Trade-Writer worker...
	@echo "🔌 Connecting to Trade-Writer worker..."
	@$(DOCKER) exec -it k8s-toolbox kubectl exec -it deployment/trade-writer -n backend -- /bin/sh

shell-postgres: ## 🔌 Connecting to Postgres container...
	@echo "🔌 Connecting to Postgres container..."
	@$(DOCKER) exec -it k8s-toolbox kubectl exec -it statefulset/postgres -n data -- /bin/sh

psql: ## 🐘 Starting interactive PostgreSQL session...
	@echo "🐘 Starting interactive PostgreSQL session..."
	@$(DOCKER) exec -it k8s-toolbox kubectl exec -it statefulset/postgres -n data -- psql -U trade_admin -d trading

redis-cli: ## 🔴 Connecting to Redis CLI...
	@echo "🔴 Connecting to Redis CLI..."
	@$(DOCKER) exec -it k8s-toolbox kubectl exec -it redis-0 -n data -- redis-cli

seed-all: ## 🌱 Spawning temporary pod to inject all test data (trades, users, accounts, positions)...
	@echo "🌱 Injecting full test data suite..."
	@cd db/redis-postgres-syncers/test && \
	tar cf - . | $(DOCKER) exec -i k8s-toolbox kubectl run data-seeder --rm -i -n backend \
		--image=ghcr.io/astral-sh/uv:alpine \
		--env="REDIS_HOST=redis.data.svc.cluster.local" \
		--restart=Never \
		-- sh -c "mkdir /app && cd /app && tar xf - && uv run test_all.py"

scale-streamlit: ## Temporarily suspend Flux and scale Streamlit (Usage: make scale-streamlit REPLICAS=X)
	@if [ -z "$(REPLICAS)" ]; then echo "Error: REPLICAS is not set. Usage: make scale-streamlit REPLICAS=1"; exit 1; fi
	@bash -c '\
	trap "echo \"\n\n[Restoring] Caught Ctrl+C! Resuming Flux...\"; $(MAKE) --no-print-directory run CMD=\"flux resume kustomization 3-apps -n flux-system\"; exit 0" INT; \
	echo "[Suspending] Pausing Flux reconciliation..."; \
	$(MAKE) --no-print-directory run CMD="flux suspend kustomization 3-apps -n flux-system"; \
	echo "[Scaling] Imperatively overriding Streamlit replicas to $(REPLICAS)..."; \
	$(MAKE) --no-print-directory kubectl CMD="scale deployment streamlit --replicas=$(REPLICAS) -n frontend"; \
	echo "\n=== OVERRIDE ACTIVE ==="; \
	echo "Streamlit scaled to $(REPLICAS). Press Ctrl+C to release override and resume Flux..."; \
	while true; do sleep 1; done'

scale-api: ## Temporarily suspend Flux and scale API (Usage: make scale-api REPLICAS=X)
	@if [ -z "$(REPLICAS)" ]; then echo "Error: REPLICAS is not set. Usage: make scale-api REPLICAS=1"; exit 1; fi
	@bash -c '\
	trap "echo \"\n\n[Restoring] Caught Ctrl+C! Resuming Flux...\"; $(MAKE) --no-print-directory run CMD=\"flux resume kustomization 3-apps -n flux-system\"; exit 0" INT; \
	echo "[Suspending] Pausing Flux reconciliation..."; \
	$(MAKE) --no-print-directory run CMD="flux suspend kustomization 3-apps -n flux-system"; \
	echo "[Scaling] Imperatively overriding FastAPI replicas to $(REPLICAS)..."; \
	$(MAKE) --no-print-directory kubectl CMD="scale deployment fastapi-api --replicas=$(REPLICAS) -n backend"; \
	echo "\n=== OVERRIDE ACTIVE ==="; \
	echo "FastAPI scaled to $(REPLICAS). Press Ctrl+C to release override and resume Flux..."; \
	while true; do sleep 1; done'
