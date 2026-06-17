.PHONY: toolbox-up toolbox-down cluster-up cluster-down shell run kubectl rebuild

# Starts the toolbox container in the background (Relative to this Makefile)
toolbox-up:
	docker compose up -d --build

# Stops and removes the toolbox container
toolbox-down:
	docker compose down

# Uses the toolbox to create the K3s cluster. (Uses absolute paths inside the container)
cluster-up: toolbox-up
	@echo "Spinning up the cluster and auto-deploying manifests..."
	docker exec k8s-toolbox k3d cluster create --config backend/k8s/k3d-config.yaml
	@echo "Cluster is ready and resources are deploying!"

# Uses the toolbox to delete the cluster
cluster-down:
	docker exec k8s-toolbox k3d cluster delete dev-cluster

# Destroys everything and rebuilds from scratch
rebuild: cluster-down toolbox-down
	@sleep 2
	$(MAKE) cluster-up

# Opens an interactive terminal inside the toolbox for manual debugging
shell:
	docker exec -it k8s-toolbox bash

# Run arbitrary commands
run:
	@docker exec -it k8s-toolbox $(CMD)

# Run kubectl commands
kubectl:
	@docker exec -it k8s-toolbox kubectl $(CMD)
