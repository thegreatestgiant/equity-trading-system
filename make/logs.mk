# ==========================================
# 📜 LOGS
# ==========================================

logs-api: ## 📜 FastAPI logs...
	@echo "📜 FastAPI logs..."
	@$(DOCKER) exec -it k8s-toolbox kubectl logs -l app=fastapi -n backend --tail=100 -f

logs-ui: ## 📜 Streamlit logs...
	@echo "📜 Streamlit logs..."
	@$(DOCKER) exec -it k8s-toolbox kubectl logs -l app=streamlit -n frontend --tail=100 -f

logs-worker: ## 📜 Trade-Writer logs...
	@echo "📜 Trade-Writer logs..."
	@$(DOCKER) exec -it k8s-toolbox kubectl logs -l app=trade-writer -n backend --tail=100 -f

logs-syncer: ## 📜 DB-Syncer logs...
	@echo "📜 DB-Syncer logs..."
	@$(DOCKER) exec -it k8s-toolbox kubectl logs -l app=db-syncer -n backend --tail=100 -f

logs-adminer: ## 📜 Adminer logs...
	@echo "📜 Adminer logs..."
	@$(DOCKER) exec -it k8s-toolbox kubectl logs -l app=adminer -n data --tail=100 -f

logs-postgres: ## 📜 Postgres logs...
	@echo "📜 Postgres logs..."
	@$(DOCKER) exec -it k8s-toolbox kubectl logs -l app=postgres -n data --tail=100 -f

logs-pgbouncer:  ## 📜 PGBouncer logs...
	@echo "📜 PGBouncer logs..."
	@$(DOCKER) exec -it k8s-toolbox kubectl logs -l app=pgbouncer -n data --tail=100 -f

logs-redis: ## 📜 Redis logs...
	@echo "📜 Redis logs..."
	@$(DOCKER) exec -it k8s-toolbox kubectl logs -l app=redis -n data --tail=100 -f

logs-flux: ## 📜 Flux reconciliation events...
	@echo "📜 Flux reconciliation events..."
	@$(DOCKER) exec -it k8s-toolbox flux logs --follow

logs-keda: ## 📜 KEDA Operator logs...
	@echo "📜 KEDA Operator logs..."
	@$(DOCKER) exec -it k8s-toolbox kubectl logs -l app=keda-operator -n keda --tail=100 -f

logs-all: ## 📜 All pods (last 50 lines each, no follow)...
	@echo "📜 All pods (last 50 lines each, no follow)..."
	@$(DOCKER) exec -it k8s-toolbox kubectl logs -l app=fastapi    -n backend      --tail=50 --prefix
	@$(DOCKER) exec -it k8s-toolbox kubectl logs -l app=streamlit  -n frontend     --tail=50 --prefix
	@$(DOCKER) exec -it k8s-toolbox kubectl logs -l app=trade-writer -n backend    --tail=50 --prefix
	@$(DOCKER) exec -it k8s-toolbox kubectl logs -l app=db-syncer  -n backend      --tail=50 --prefix
	@$(DOCKER) exec -it k8s-toolbox kubectl logs -l app=postgres   -n data         --tail=50 --prefix
	@$(DOCKER) exec -it k8s-toolbox kubectl logs -l app=redis      -n data         --tail=50 --prefix
