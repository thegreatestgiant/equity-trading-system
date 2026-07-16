.PHONY: shell run kubectl shell-api shell-ui shell-postgres shell-pooler

# ==========================================
# 🔍 INTERACTIVE SHELLS
# ==========================================

shell: ## Opens an interactive Shell
	$(DOCKER) exec -it k8s-toolbox bash

run: ## Runs anything in CMD=""
	@$(DOCKER) exec -it k8s-toolbox $(CMD)

kubectl: ## Runs kubectl CMD=""
	@$(DOCKER) exec -it k8s-toolbox kubectl $(CMD)

shell-api: ## 🔌 Open a shell in the FastAPI backend pod
	@echo "🔌 Connecting to FastAPI backend..."
	@$(DOCKER) exec -it k8s-toolbox kubectl exec -it deployment/fastapi-api -n backend -- /bin/sh

shell-ui: ## 🔌 Open a shell in the Streamlit frontend pod
	@echo "🔌 Connecting to Streamlit frontend..."
	@$(DOCKER) exec -it k8s-toolbox kubectl exec -it deployment/streamlit -n frontend -- /bin/sh

shell-postgres: ## 🔌 Open a shell in the CNPG primary Postgres pod
	@echo "🔌 Connecting to CNPG primary..."
	@$(DOCKER) exec -it k8s-toolbox bash -c 'POD=$$(kubectl get pods -n data -l "cnpg.io/cluster=trading-db,cnpg.io/instanceRole=primary" -o jsonpath="{.items[0].metadata.name}"); kubectl exec -it $$POD -n data -- /bin/bash'

shell-pooler: ## 🔌 Open a shell in the PgBouncer pooler pod
	@echo "🔌 Connecting to PgBouncer pooler..."
	@$(DOCKER) exec -it k8s-toolbox bash -c 'POD=$$(kubectl get pods -n data -l "cnpg.io/poolerName=trading-pooler" -o jsonpath="{.items[0].metadata.name}"); kubectl exec -it $$POD -n data -- /bin/bash'
