.PHONY: ks events status status-wide status-svc check-sync sync adminer-info status-images

# ==========================================
# 📊 CLUSTER STATUS
# ==========================================

ks: check-sync      ## Super short alias for flux get kustomizations

events: ## ⚠️  Show recent cluster events sorted by time
	@echo "⚠️  RECENT CLUSTER EVENTS:"
	@$(DOCKER) exec k8s-toolbox bash -c 'kubectl get events --sort-by=".metadata.creationTimestamp" -A | tail -n 30'

status: ## 🟢 CURRENT POD STATUS:
	@echo "🟢 CURRENT POD STATUS:"
	@$(DOCKER) exec k8s-toolbox kubectl get pods -A

status-wide: ## 🌐 WIDE POD OVERVIEW:
	@echo "🌐 WIDE POD OVERVIEW:"
	@$(DOCKER) exec k8s-toolbox kubectl get pods -A -o wide

status-svc: ## 🔌 ACTIVE NETWORK SERVICES:
	@echo "🔌 ACTIVE NETWORK SERVICES:"
	@$(DOCKER) exec k8s-toolbox kubectl get svc -A

check-sync: ## Verify all sync stages are Ready
	@$(DOCKER) exec k8s-toolbox flux get kustomizations

sync: ## Force Flux to reconcile (Accepts LAYER=all, apps, or data-layer)
	@echo "🔄 Forcing Flux to synchronize Git..."
	@REPO=$$( $(DOCKER) exec k8s-toolbox kubectl get gitrepositories -n flux-system -o jsonpath='{.items[0].metadata.name}' ); \
	if [ -n "$$REPO" ]; then \
		echo "Found repo: $$REPO, reconciling..."; \
		$(DOCKER) exec k8s-toolbox flux reconcile source git $$REPO -n flux-system; \
	else \
		echo "⚠️ No GitRepository found in flux-system, skipping source sync."; \
	fi
	@if [ "$(LAYER)" = "all" ] || [ -z "$(LAYER)" ]; then \
		echo "🔄 Syncing all Kustomizations in dependency order..."; \
		$(DOCKER) exec k8s-toolbox flux reconcile kustomization 1-infra --with-source; \
		$(DOCKER) exec k8s-toolbox flux reconcile kustomization 2-data --with-source; \
		$(DOCKER) exec k8s-toolbox flux reconcile kustomization 3-apps --with-source; \
	elif [ "$(LAYER)" = "apps" ]; then \
		$(DOCKER) exec k8s-toolbox flux reconcile kustomization 3-apps --with-source; \
	elif [ "$(LAYER)" = "data-layer" ]; then \
		$(DOCKER) exec k8s-toolbox flux reconcile kustomization 2-data --with-source; \
	fi

adminer-info: ## 🌐 Adminer UI: http://adminer.localhost:8080
	@echo "🌐 Adminer UI: http://adminer.localhost:8080"
	@echo "🔍 Fetching Postgres Credentials from cluster..."
	@echo -n "User: "
	@$(DOCKER) exec k8s-toolbox kubectl get secret db-credentials -n data -o jsonpath='{.data.POSTGRES_USER}' | base64 -d; echo ""
	@echo -n "Pass: "
	@$(DOCKER) exec k8s-toolbox kubectl get secret db-credentials -n data -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d; echo ""

status-images: ## 🏷️  Check the exact Docker images running for our custom apps
	@echo "🏷️  CUSTOM APP IMAGE VERSIONS:"
	@$(MAKE) --no-print-directory kubectl CMD="get pods -A -l 'app in (fastapi, streamlit, trade-writer, db-syncer, price-cacher, price-timeseries-cacher)' -o custom-columns=NAMESPACE:.metadata.namespace,POD:.metadata.name,IMAGE:.spec.containers[*].image"
