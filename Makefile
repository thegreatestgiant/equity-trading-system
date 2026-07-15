.PHONY: all help
all: help

DOCKER   ?= docker
HOST_ROOT := $(shell pwd)
export HOST_ROOT

# Include all of our modular Make targets
-include make/cluster.mk
-include make/status.mk
-include make/shell.mk
-include make/db.mk
-include make/debug.mk
-include make/chaos.mk
-include make/logs.mk
-include make/k3s.mk

# ==========================================
# 🆘 HELP MENU
# ==========================================

help: ## Show this dynamic help menu
	@echo "=========================================================="
	@echo "🚀 EQUITY TRADING SYSTEM - DEVELOPER TOOLBOX"
	@echo "=========================================================="
	@echo "Usage: make [target]"
	@echo ""
	@grep -h -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
