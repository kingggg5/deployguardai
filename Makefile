.DEFAULT_GOAL := help

PYTHON ?= python3
NPM ?= npm
COMPOSE ?= docker compose

.PHONY: help install dev stop test test-backend test-frontend coverage demo demo-down compose-config

help:
	@printf '%s\n' 'DeployGuard development commands:' \
	  '  make install        Install locked frontend and backend dependencies' \
	  '  make dev            Start the connected-mode API, worker, and UI' \
	  '  make stop           Stop only processes started by make dev' \
	  '  make test           Run backend and frontend tests' \
	  '  make coverage       Run test suites with coverage reports' \
	  '  make demo           Start an isolated, visibly-labelled synthetic demo' \
	  '  make demo-down      Stop the isolated demo without removing volumes' \
	  '  make compose-config Validate the default Compose configuration'

install:
	@$(PYTHON) -m venv backend/.venv
	@backend/.venv/bin/python -m pip install --disable-pip-version-check -r backend/requirements.txt
	@$(NPM) --prefix frontend ci

dev:
	@./scripts/run-dev.sh

stop:
	@./scripts/stop-dev.sh

test: test-backend test-frontend

test-backend:
	@cd backend && .venv/bin/python -m pytest

test-frontend:
	@$(NPM) --prefix frontend test -- --watch=false

coverage:
	@cd backend && .venv/bin/python -m pytest -p pytest_cov --cov=app --cov-report=term-missing --cov-report=xml:coverage.xml --cov-fail-under=80
	@$(NPM) --prefix frontend run test:coverage

demo:
	@$(COMPOSE) -p deployguard-demo -f docker-compose.yml -f docker-compose.demo.yml up --build

demo-down:
	@$(COMPOSE) -p deployguard-demo -f docker-compose.yml -f docker-compose.demo.yml down

compose-config:
	@$(COMPOSE) config --quiet
