# Makefile — shortcuts for common tasks
# Run `make help` to see all available commands.
#
# Requires: docker, docker compose, python3, bash
# All docker commands use the compose file at the repo root.

.DEFAULT_GOAL := help
SHELL         := /bin/bash

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN  := \033[0;32m
YELLOW := \033[0;33m
RESET  := \033[0m

# ── Help ─────────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help message
	@echo ""
	@echo "  Hybrid Search Engine — available commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ── Local dev (no Docker) ─────────────────────────────────────────────────────

.PHONY: setup
setup: ## Create .venv and install all dependencies
	python3 -m venv .venv
	. .venv/bin/activate && pip install -q \
		torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu
	. .venv/bin/activate && pip install -q -r requirements.txt
	@echo -e "$(GREEN)[OK]$(RESET) Virtual env ready — activate with: source .venv/bin/activate"

.PHONY: up
up: ## Start API + dashboard locally (bash up.sh)
	bash up.sh

.PHONY: down
down: ## Stop API + dashboard (bash down.sh)
	bash down.sh

.PHONY: test
test: ## Run pytest with coverage (activates .venv automatically)
	. .venv/bin/activate && cd backend && \
		pytest --tb=short --cov=app --cov-report=term-missing -q

.PHONY: test-file
test-file: ## Run a specific test file: make test-file FILE=tests/test_bm25.py
	. .venv/bin/activate && cd backend && pytest $(FILE) -v

.PHONY: lint
lint: ## Quick sanity check — import all modules (catches syntax errors)
	. .venv/bin/activate && cd backend && \
		python -c "import app.main; import app.search.hybrid; print('Imports OK')"

# ── Docker ────────────────────────────────────────────────────────────────────

.PHONY: build
build: ## Build both Docker images
	docker compose build

.PHONY: docker-up
docker-up: ## Build (if needed) and start all containers in the foreground
	docker compose up --build

.PHONY: docker-up-d
docker-up-d: ## Build and start all containers in the background
	docker compose up --build -d

.PHONY: docker-down
docker-down: ## Stop and remove containers (keeps data volume)
	docker compose down

.PHONY: docker-reset
docker-reset: ## Stop containers AND delete all data volumes (full reset)
	docker compose down -v
	@echo -e "$(YELLOW)[WARN]$(RESET) Data volume deleted — indexes will be rebuilt on next start."

.PHONY: logs
logs: ## Tail logs from all containers (Ctrl+C to stop)
	docker compose logs -f

.PHONY: logs-api
logs-api: ## Tail API container logs only
	docker compose logs -f api

.PHONY: logs-dashboard
logs-dashboard: ## Tail dashboard container logs only
	docker compose logs -f dashboard

.PHONY: ps
ps: ## Show running containers and their status
	docker compose ps

.PHONY: shell-api
shell-api: ## Open a bash shell inside the running API container
	docker compose exec api bash

.PHONY: shell-dashboard
shell-dashboard: ## Open a bash shell inside the running dashboard container
	docker compose exec dashboard sh

# ── Cleanup ───────────────────────────────────────────────────────────────────

.PHONY: clean
clean: ## Remove .venv, __pycache__, *.pyc, and *.log files
	rm -rf .venv
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f uvicorn.log streamlit.log

.PHONY: env
env: ## Copy .env.example → .env if .env doesn't already exist
	@if [ -f .env ]; then \
		echo -e "$(YELLOW)[SKIP]$(RESET) .env already exists."; \
	else \
		cp .env.example .env; \
		echo -e "$(GREEN)[OK]$(RESET) .env created from .env.example"; \
	fi
