.PHONY: copy-env setup bootstrap-local bootstrap-staging docs docs-check deploy-readiness backend-lint backend-test backend-dev backend-migrate frontend-lint frontend-test frontend-dev mobile-lint mobile-test mobile-dev dev-up infra-up dev-down infra-down health-check lint test baseline-checks dev ci

copy-env:
	./scripts/copy_env_templates.sh

setup:
	./scripts/setup_template.sh

bootstrap-local:
	./scripts/bootstrap.sh local

bootstrap-staging:
	./scripts/bootstrap.sh staging

docs:
	python3 scripts/validate_documentation.py

docs-check: docs

deploy-readiness:
	python3 scripts/validate_documentation.py
	python3 scripts/check_deploy_readiness.py

backend-lint:
	cd backend && uv run ruff check src tests

backend-test:
	cd backend && uv run --group test pytest

backend-dev:
	cd backend && uv run task start

backend-migrate:
	cd backend && uv run task migrate

frontend-lint:
	cd frontend && npm run lint

frontend-test:
	cd frontend && npm run typecheck && npm run test && npm run build

frontend-dev:
	cd frontend && npm run dev

mobile-lint:
	@if command -v flutter >/dev/null 2>&1; then \
		cd mobile && flutter analyze; \
	else \
		echo "⚠️  flutter not found; skipping mobile-lint"; \
	fi

mobile-test:
	@if command -v flutter >/dev/null 2>&1; then \
		cd mobile && flutter test; \
	else \
		echo "⚠️  flutter not found; skipping mobile-test"; \
	fi

mobile-dev:
	@if command -v flutter >/dev/null 2>&1; then \
		cd mobile && flutter run; \
	else \
		echo "flutter is required for mobile-dev. Install Flutter and re-run."; \
		exit 1; \
	fi

dev-up:
	docker compose up --build

infra-up:
	docker compose up -d db redis

dev-down:
	docker compose down -v

infra-down:
	docker compose down -v

health-check:
	python3 scripts/check_template_health.py

lint: backend-lint frontend-lint mobile-lint

test: backend-test frontend-test mobile-test

baseline-checks: backend-lint backend-test frontend-lint frontend-test mobile-lint mobile-test

dev:
	@echo "Run services in separate terminals:"
	@echo "  make backend-dev"
	@echo "  make frontend-dev"
	@echo "  make mobile-dev"

ci: docs deploy-readiness lint test
