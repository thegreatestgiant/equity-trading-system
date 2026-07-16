.PHONY: db-backup db-restore db-clear psql redis-cli redis-sentinel adminer-info

# ==========================================
# 💾 DATABASE OPERATIONS
# ==========================================

db-clear: ## ⚠️ WIPE the entire trading database (Destructive)
	@echo "============================================="
	@echo "    ⚠️  DATABASE WIPE MENU"
	@echo "============================================="
	@echo "WARNING: This will permanently DROP all tables and data!"
	@read -p "Are you absolutely sure? (y/N): " confirm; \
	case "$$confirm" in [Yy]) \
		echo "💥 Truncating all data in the public schema..."; \
		$(DOCKER) exec -it k8s-toolbox bash -c '\
			POD=$$(kubectl get pods -n data -l "cnpg.io/cluster=trading-db,cnpg.io/instanceRole=primary" -o jsonpath="{.items[0].metadata.name}") && \
			kubectl exec -n data $$POD -- psql -U postgres -d trading -c "TRUNCATE TABLE trades, accounts, users, positions, users_sync_stage, accounts_sync_stage, positions_sync_stage CASCADE;" \
		'; \
		echo "✅ Database data completely cleared!"; \
		echo "🧹 Flushing Redis Cache completely..."; \
		$(DOCKER) exec -it k8s-toolbox bash -c '\
			REDIS_POD=$$(kubectl get pods -n data -l "app.kubernetes.io/name=redis" -o jsonpath="{.items[0].metadata.name}" 2>/dev/null || kubectl get pods -n data -l "app=redis" -o jsonpath="{.items[0].metadata.name}") && \
			kubectl exec -n data $$REDIS_POD -- sh -c "redis-cli --scan | xargs -r redis-cli del" \
		'; \
		echo "🚀 Triggering redis-populator job (to rebuild empty caches)..."; \
		JOB_NAME="redis-populator-manual-$$(date +%s)"; \
		$(DOCKER) exec -it k8s-toolbox kubectl create job --from=cronjob/redis-populator $$JOB_NAME -n backend; \
		echo "⏳ Waiting for redis-populator to finish..."; \
		$(DOCKER) exec -it k8s-toolbox kubectl wait --for=condition=complete job/$$JOB_NAME -n backend --timeout=60s; \
		echo "♻️ Restarting dependent deployments in correct sequence..."; \
		$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/trading-pooler -n data; \
		$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/trading-pooler-ro -n data; \
		$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/price-cacher -n backend; \
		$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/fastapi-api -n backend; \
		$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/trade-writer -n backend; \
		$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/db-syncer -n backend; \
		$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/adminer -n data; \
		$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/streamlit -n frontend; \
		$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/locust-load-tester -n load-testing; \
		;; \
	*) \
		echo "Aborted."; \
		;; \
	esac

adminer-info: ## 🌐 Adminer UI: http://adminer.localhost:8080
	@echo "🌐 Adminer UI: http://adminer.localhost:8080"
	@echo "🔍 Fetching Postgres Credentials from cluster..."
	@echo -n "User: "
	@$(DOCKER) exec k8s-toolbox kubectl get secret db-credentials -n data -o jsonpath='{.data.POSTGRES_USER}' | base64 -d; echo ""
	@echo -n "Pass: "
	@$(DOCKER) exec k8s-toolbox kubectl get secret db-credentials -n data -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d; echo ""

psql: ## 🐘 Open an interactive PostgreSQL session
	@echo "🐘 Starting interactive PostgreSQL session..."
	@$(DOCKER) exec -it k8s-toolbox bash -c 'POD=$$(kubectl get pods -n data -l "cnpg.io/cluster=trading-db,cnpg.io/instanceRole=primary" -o jsonpath="{.items[0].metadata.name}"); kubectl exec -it $$POD -n data -- psql -U trade_admin -d trading'

redis-cli: ## 🔴 Open the Redis CLI on the active node
	@echo "🔴 Finding active Redis node and launching CLI..."
	@$(DOCKER) exec -it k8s-toolbox bash -c 'POD=$$(kubectl get pods -n data -l "app.kubernetes.io/name=redis" -o jsonpath="{.items[0].metadata.name}" 2>/dev/null || kubectl get pods -n data -l "app=redis" -o jsonpath="{.items[0].metadata.name}"); kubectl exec -it $$POD -n data -- redis-cli'

redis-sentinel: ## 🛡️ Check Redis Sentinel quorum status
	@echo "🛡️ Connecting to Sentinel to check quorum..."
	@$(DOCKER) exec -it k8s-toolbox bash -c 'POD=$$(kubectl get pods -n data -l "app.kubernetes.io/name=redis,app.kubernetes.io/component=sentinel" -o jsonpath="{.items[0].metadata.name}"); kubectl exec -it $$POD -n data -- redis-cli -p 26379 info sentinel'

db-backup: ## 💾 Take a snapshot of the trading DB and save to project root
	@echo "============================================="
	@echo "    💾 DATABASE BACKUP MENU"
	@echo "============================================="
	@read -p "Enter backup name (default: trading_backup): " input; \
	bname="trading_backup"; \
	if [ -n "$$input" ]; then bname="$$input"; fi; \
	bname=$${bname// /_}; \
	while [ -f "$${bname}.dump" ]; do \
		read -p "⚠️  File $${bname}.dump exists! (o)verwrite, (a)utoincrement, (r)ename, or (c)ancel? " choice; \
		case "$$choice" in \
			[Oo]*) break ;; \
			[Aa]*) \
				i=1; \
				while [ -f "$${bname}_$${i}.dump" ]; do i=$$((i+1)); done; \
				bname="$${bname}_$${i}"; \
				echo "✅ Autoincremented to $${bname}.dump"; \
				break ;; \
			[Rr]*) \
				read -p "Enter new backup name: " input; \
				if [ -n "$$input" ]; then bname="$$input"; fi; \
				;; \
			*) echo "Aborted."; exit 1 ;; \
		esac; \
	done; \
	echo "💾 Taking snapshot of 'trading' database from primary node..."; \
	$(DOCKER) exec -e BNAME="$$bname" -it k8s-toolbox bash -c '\
		POD=$$(kubectl get pods -n data -l "cnpg.io/cluster=trading-db,cnpg.io/instanceRole=primary" -o jsonpath="{.items[0].metadata.name}") && \
		echo "📦 Creating dump inside pod $$POD..." && \
		kubectl exec -n data $$POD -- pg_dump -U postgres -d trading -F c -f /dev/shm/dump.tmp && \
		echo "⬇️ Copying backup to host as \"$$BNAME.dump\"..." && \
		kubectl cp data/$$POD:/dev/shm/dump.tmp "/workspace/$$BNAME.dump" \
	'; \
	echo "✅ Backup successfully saved to ./$$bname.dump!"

db-restore: ## ⚠️ RESTORE snapshot to the trading DB (Destructive)
	@echo "============================================="
	@echo "    ⚠️  DATABASE RESTORE MENU"
	@echo "============================================="
	@DUMPS=$$(ls *.dump 2>/dev/null); \
	if [ -z "$$DUMPS" ]; then \
		echo "❌ No .dump files found in the current directory!"; \
		exit 1; \
	fi; \
	PS3="Select a backup file to restore (or type a number to exit): "; \
	select file in $$DUMPS "Exit"; do \
		if [ "$$file" = "Exit" ]; then echo "Gracefully exiting."; break; fi; \
		if [ -n "$$file" ]; then \
			echo "⚠️  WARNING: This will drop and replace the current 'trading' database!"; \
			echo "⏳ Copying $$file into the primary pod and restoring..."; \
			$(DOCKER) exec -e BNAME="$$file" -it k8s-toolbox bash -c '\
				POD=$$(kubectl get pods -n data -l "cnpg.io/cluster=trading-db,cnpg.io/instanceRole=primary" -o jsonpath="{.items[0].metadata.name}") && \
				echo "⬆️ Copying backup file into pod $$POD..." && \
				kubectl cp "/workspace/$$BNAME" data/$$POD:/dev/shm/trading_backup.dump && \
				echo "🔥 Restoring database (with clean)..." && \
				kubectl exec -n data $$POD -- pg_restore -U postgres -d trading --clean --if-exists /dev/shm/trading_backup.dump \
			'; \
			echo "✅ Database restored successfully!"; \
			echo "🧹 Flushing Redis Cache completely to remove stale streams..."; \
			$(DOCKER) exec -it k8s-toolbox bash -c '\
				REDIS_POD=$$(kubectl get pods -n data -l "app.kubernetes.io/name=redis" -o jsonpath="{.items[0].metadata.name}" 2>/dev/null || kubectl get pods -n data -l "app=redis" -o jsonpath="{.items[0].metadata.name}") && \
				kubectl exec -n data $$REDIS_POD -- sh -c "redis-cli --scan | xargs -r redis-cli del" \
			'; \
			echo "🚀 Triggering redis-populator job to rebuild caches..."; \
			JOB_NAME="redis-populator-manual-$$(date +%s)"; \
			$(DOCKER) exec -it k8s-toolbox kubectl create job --from=cronjob/redis-populator $$JOB_NAME -n backend; \
			echo "⏳ Waiting for redis-populator to finish..."; \
			$(DOCKER) exec -it k8s-toolbox kubectl wait --for=condition=complete job/$$JOB_NAME -n backend --timeout=60s; \
			echo "♻️ Restarting dependent deployments in correct sequence..."; \
			$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/trading-pooler -n data; \
			$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/trading-pooler-ro -n data; \
			$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/price-cacher -n backend; \
			$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/fastapi-api -n backend; \
			$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/trade-writer -n backend; \
			$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/db-syncer -n backend; \
			$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/adminer -n data; \
			$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/streamlit -n frontend; \
			$(DOCKER) exec -it k8s-toolbox kubectl rollout restart deployment/locust-load-tester -n load-testing; \
			break; \
		fi; \
	done
