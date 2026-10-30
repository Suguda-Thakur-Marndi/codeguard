.PHONY: help install dev test lint format migrate migration docker-up docker-down check-release

PYTHON ?= python
VENV_BIN ?= .venv/bin
ifeq ($(OS),Windows_NT)
	VENV_BIN := .venv/Scripts
endif

help:
	@echo "CodeGuard - Production Release & Developer Commands"
	@echo "  make install            Install backend and frontend dependencies"
	@echo "  make dev                Start development servers (API & Web)"
	@echo "  make test               Run backend test suite with pytest"
	@echo "  make lint               Run Ruff linter and TypeScript type check"
	@echo "  make format             Format codebase using Ruff"
	@echo "  make check-release      Run complete pre-release validation pipeline"
	@echo "  make migrate            Apply Alembic database migrations"
	@echo "  make docker-up          Start full container stack with Docker Compose"
	@echo "  make docker-down        Stop all running Docker Compose containers"

install:
	$(PYTHON) -m venv .venv
	$(VENV_BIN)/pip install --upgrade pip
	$(VENV_BIN)/pip install -e "./packages/code-intelligence" -e "./apps/api[dev]"
	cd apps/web && npm install

dev:
	@echo "Starting API on http://localhost:8000 and Web on http://localhost:3000..."
	$(VENV_BIN)/uvicorn app.main:app --app-dir apps/api --reload --port 8000

test:
	$(VENV_BIN)/pytest apps/api/tests -v

lint:
	$(VENV_BIN)/ruff check apps/api packages/code-intelligence scripts
	cd apps/web && npm run lint

format:
	$(VENV_BIN)/ruff check --fix apps/api packages/code-intelligence scripts

check-release: lint test
	cd apps/web && npm run build
	@echo "All pre-release quality gates passed successfully."

migrate:
	cd apps/api && ../../$(VENV_BIN)/alembic upgrade head

migration:
	@if [ -z "$(MSG)" ]; then echo "Error: Specify MSG parameter (e.g. make migration MSG='create_table')"; exit 1; fi
	cd apps/api && ../../$(VENV_BIN)/alembic revision --autogenerate -m "$(MSG)"

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down -v
