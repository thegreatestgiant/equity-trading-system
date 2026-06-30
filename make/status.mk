# ==========================================
# 📊 CLUSTER STATUS
# ==========================================

status: ## 🟢 CURRENT POD STATUS:
	@echo "🟢 CURRENT POD STATUS:"
	@$(DOCKER) exec -it k8s-toolbox kubectl get pods -A

status-wide: ## 🌐 WIDE POD OVERVIEW:
	@echo "🌐 WIDE POD OVERVIEW:"
	@$(DOCKER) exec -it k8s-toolbox kubectl get pods -A -o wide

status-svc: ## 🔌 ACTIVE NETWORK SERVICES:
	@echo "🔌 ACTIVE NETWORK SERVICES:"
	@$(DOCKER) exec -it k8s-toolbox kubectl get svc -A

check-sync: ## Verify all sync stages are Ready
	@$(DOCKER) exec -it k8s-toolbox flux get kustomizations

sync-app: ## Fast-sync the apps layer (Usage: make sync-app)
	@echo "[Syncing] Pulling latest source and reconciling 3-apps layer..."
	@$(MAKE) --no-print-directory run CMD="flux reconcile kustomization 3-apps -n flux-system --with-source"

sync:
	$(DOCKER) exec -it k8s-toolbox flux reconcile source git dev-repo-sean
	$(DOCKER) exec -it k8s-toolbox flux reconcile kustomization 1-infra --with-source

adminer-info: ## 🌐 Adminer UI: http://adminer.localhost:8080
	@echo "🌐 Adminer UI: http://adminer.localhost:8080"
	@echo "🔍 Fetching Postgres Credentials from cluster..."
	@echo -n "User: "
	@$(DOCKER) exec -it k8s-toolbox kubectl get secret db-credentials -n data -o jsonpath='{.data.POSTGRES_USER}' | base64 -d; echo ""
	@echo -n "Pass: "
	@$(DOCKER) exec -it k8s-toolbox kubectl get secret db-credentials -n data -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d; echo ""

status-images: ## 🏷️  Check the exact Docker images running for our custom apps
	@echo "🏷️  CUSTOM APP IMAGE VERSIONS:"
	@$(MAKE) --no-print-directory kubectl CMD="get pods -A -l 'app in (fastapi, streamlit, trade-writer, db-syncer)' -o custom-columns=NAMESPACE:.metadata.namespace,POD:.metadata.name,IMAGE:.spec.containers[*].image"
