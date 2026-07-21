.PHONY: update-ui update-api clean-images

# ==========================================
# 🐳 IMAGE BUILDING & CLEANUP
# ==========================================

update-ui-%: ## Rebuild UI image tagged dev-<name>, import to k3d, and restart UI (e.g. make update-ui-sean)
	@echo "🚀 Rebuilding web-ui docker image (web-ui-image:dev-$*)..."
	$(DOCKER) build -t web-ui-image:dev-$* ./web-ui
	@echo "🧹 Cleaning up dangling host layers..."
	$(DOCKER) image prune -f
	@echo "📦 Importing image into k3d..."
	$(DOCKER) exec k8s-toolbox k3d image import web-ui-image:dev-$* -c dev-cluster
	@echo "♻️  Restarting frontend pods to apply new image..."
	$(MAKE) --no-print-directory kubectl CMD="delete pod -n frontend -l app=streamlit"
	@echo "✅ Done!"

update-api: ## Rebuild API docker image, import to k3d, clear cache, and restart API
	@echo "🚀 Rebuilding api docker image..."
	$(DOCKER) build -t api-image:dev-sean ./api
	@echo "🧹 Cleaning up dangling host layers..."
	$(DOCKER) image prune -f
	@echo "📦 Importing image into k3d..."
	$(DOCKER) exec k8s-toolbox k3d image import api-image:dev-sean -c dev-cluster
	@echo "♻️  Restarting backend pods to apply new image..."
	$(MAKE) --no-print-directory kubectl CMD="delete pod -n backend -l app=fastapi"
	@echo "✅ Done!"

clean-images: ## Aggressively clean docker host images and k3d image cache
	@echo "🧹 Pruning unused host docker images..."
	$(DOCKER) image prune -a -f
	@echo "🧹 Pruning unused containerd images inside k3d..."
	-$(DOCKER) exec k3d-dev-cluster-agent-0 crictl rmi --prune
	-$(DOCKER) exec k3d-dev-cluster-agent-1 crictl rmi --prune
	-$(DOCKER) exec k3d-dev-cluster-server-0 crictl rmi --prune
	@echo "✅ Done!"

# ==========================================
# 🌍 CROSS-COMPILE & PUSH (PROD/ORG REPO)
# ==========================================

push-ui: ## Cross-compile (amd64/arm64) and push UI to org repo (e.g. make push-ui REPO=org/web-ui TAG=v1.0.0)
	@if [ -z "$(REPO)" ] || [ -z "$(TAG)" ]; then \
		echo "❌ Error: REPO and TAG are required."; \
		echo "💡 Usage: make push-ui REPO=myorg/web-ui TAG=v1.0.0"; \
		exit 1; \
	fi
	@echo "🚀 Cross-compiling and pushing UI to $(REPO):$(TAG)..."
	$(DOCKER) buildx build --platform linux/amd64,linux/arm64 -t $(REPO):$(TAG) --push ./web-ui
	@echo "✅ Done!"

