.DEFAULT_GOAL := help
.PHONY: help install lint fmt type arch unit integration test coverage coverage-full run demo eval sweep

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install backend deps (uv)
	cd backend && uv sync

lint: ## ruff lint + format check + bandit
	cd backend && uv run ruff check src tests
	cd backend && uv run ruff format --check src tests
	cd backend && uv run bandit -c pyproject.toml -q -r src

fmt: ## Auto-format
	cd backend && uv run ruff check --fix src tests
	cd backend && uv run ruff format src tests

type: ## mypy --strict
	cd backend && uv run mypy

arch: ## import-linter architecture contracts
	cd backend && uv run lint-imports

unit: ## Unit tests (offline, no keys)
	cd backend && uv run pytest tests/unit -q

integration: ## Integration tests (offline, real SQLite + mock providers)
	cd backend && uv run pytest tests/integration -q

test: lint type arch unit ## The fast gate (what pre-push should run)

coverage: ## Layered gate: 100% on domain+application (unit tests only)
	cd backend && uv run pytest tests/unit -q --cov=src/notula --cov-report=term-missing:skip-covered
	cd backend && uv run coverage report --include="src/notula/domain/*,src/notula/application/*" --fail-under=100

coverage-full: ## Overall gate: 85% across unit+integration
	cd backend && uv run pytest tests/unit tests/integration -q --cov=src/notula --cov-report=term-missing:skip-covered
	cd backend && uv run coverage report --fail-under=85

run: ## Run the API + UI on :8000 (mock provider unless NOTULA_PROVIDER=live)
	cd backend && uv run uvicorn notula.main:build_app --factory --port 8000

demo: ## End-to-end offline demo: submit sample audio, stream progress, print summary
	cd backend && uv run python scripts/demo.py

eval: ## Offline eval suite (mock judge; see evals/)
	cd backend && uv sync --group eval && uv run llm-eval run ../evals/suite.yaml

sweep: ## Secret sweep: fail if anything key-shaped is tracked
	@if git grep -nE "(AIzaSy[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9-]{15,})" -- . ':!Makefile'; then echo "FOUND — do not push"; exit 1; else echo "clean"; fi
