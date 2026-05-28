.PHONY: help install dev build start lint test clean docker-build docker-up docker-down

CONTAINER_RUNTIME ?= podman
COMPOSE := $(CONTAINER_RUNTIME) compose

# Colors
GREEN  := $(shell tput -Txterm setaf 2)
YELLOW := $(shell tput -Txterm setaf 3)
RESET  := $(shell tput -Txterm sgr0)

help: ## Show this help
	@echo ''
	@echo 'Usage:'
	@echo '  ${YELLOW}make${RESET} ${GREEN}<target>${RESET}'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  ${YELLOW}%-15s${RESET} %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install dependencies
	npm ci

dev: ## Start development server
	npm run dev

build: ## Build for production
	npm run build

start: ## Start production server
	npm run start

lint: ## Run linting
	npm run lint

lint-fix: ## Fix linting issues
	npm run lint -- --fix

test: ## Run tests
	npm run test

test-coverage: ## Run tests with coverage
	npm run test -- --coverage

typecheck: ## Run TypeScript type checking
	npx tsc --noEmit

clean: ## Clean build artifacts
	rm -rf dist .vite node_modules tsconfig.tsbuildinfo

# Docker commands
docker-build: ## Build Docker image
	$(CONTAINER_RUNTIME) build -t fastapi_template .

docker-up: ## Start all services with Docker Compose
	$(COMPOSE) up -d

docker-down: ## Stop all Docker Compose services
	$(COMPOSE) down

docker-logs: ## View Docker Compose logs
	$(COMPOSE) logs -f

docker-shell: ## Open shell in frontend container
	$(COMPOSE) exec frontend sh

# Development helpers
setup: install ## Initial project setup
	npx husky install
	@echo "✅ Project setup complete!"

update-deps: ## Update dependencies
	npm update
	npm outdated
