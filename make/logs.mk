.PHONY: logs-api logs-ui logs-worker logs-syncer logs-cacher logs-timeseries logs-adminer logs-postgres logs-pooler logs-redis logs-flux logs-keda logs-all

# ==========================================
# 📜 LOGS
# ==========================================

logs-api: ## 📜 Tail FastAPI logs
	@echo "📜 FastAPI logs..."
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l app=fastapi -n backend --tail=100 -f

logs-ui: ## 📜 Tail Streamlit logs
	@echo "📜 Streamlit logs..."
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l app=streamlit -n frontend --tail=100 -f

logs-worker: ## 📜 Tail Trade-Writer logs
	@echo "📜 Trade-Writer logs..."
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l app=trade-writer -n backend --tail=100 -f

logs-syncer: ## 📜 Tail DB-Syncer logs
	@echo "📜 DB-Syncer logs..."
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l app=db-syncer -n backend --tail=100 -f

logs-cacher: ## 📜 Tail price-cacher logs
	@echo "📜 price-cacher logs..."
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l app=price-cacher -n backend --tail=100 -f

logs-populator: ## 📜 Tail redis-populator logs
	@echo "📜 redis-populator logs..."
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l app=redis-populator -n backend --tail=100 -f

logs-adminer: ## 📜 Tail Adminer logs
	@echo "📜 Adminer logs..."
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l app=adminer -n data --tail=100 -f

logs-postgres: ## 📜 Tail CNPG Postgres logs
	@echo "📜 CNPG Postgres logs..."
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l cnpg.io/cluster=trading-db -n data --tail=100 -f

logs-pooler:  ## 📜 Tail CNPG PgBouncer Pooler logs
	@echo "📜 CNPG PgBouncer Pooler logs..."
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l cnpg.io/poolerName=trading-pooler -n data --tail=100 -f

logs-redis: ## 📜 Tail Redis logs
	@echo "📜 Redis logs..."
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l app=redis -n data --tail=100 -f

logs-flux: ## 📜 Tail Flux reconciliation events
	@echo "📜 Flux reconciliation events..."
	@$(DOCKER) exec -i k8s-toolbox flux logs --follow

logs-keda: ## 📜 Tail KEDA Operator logs
	@echo "📜 KEDA Operator logs..."
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l app=keda-operator -n keda --tail=100 -f

logs-all: ## 📜 Show the last 50 lines from every pod (no follow)
	@echo "📜 All pods (last 50 lines each, no follow)..."
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l app=fastapi    -n backend      --tail=50 --prefix
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l app=streamlit  -n frontend     --tail=50 --prefix
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l app=trade-writer -n backend    --tail=50 --prefix
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l app=db-syncer  -n backend      --tail=50 --prefix
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l app=price-cacher  -n backend      --tail=50 --prefix
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l app=redis-populator -n backend    --tail=50 --prefix
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l cnpg.io/cluster=trading-db -n data --tail=50 --prefix
	@$(DOCKER) exec -i k8s-toolbox kubectl logs -l app=redis      -n data         --tail=50 --prefix
