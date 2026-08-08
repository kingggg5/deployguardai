.DEFAULT_GOAL := help

PYTHON ?= python3
NPM ?= npm
COMPOSE ?= docker compose

.PHONY: help install dev stop test test-verify test-backend test-dotnet test-frontend coverage bench demo demo-down compose-config

help:
	@printf '%s\n' 'DeployGuard development commands:' \
	  '  make install        Restore control-plane and install app dependencies' \
	  '  make dev            Start the connected-mode API, worker, and UI' \
	  '  make stop           Stop only processes started by make dev' \
	  '  make test           Run backend, control-plane, and frontend tests' \
	  '  make test-verify    Run the standalone Evidence Receipt tests' \
	  '  make coverage       Run test suites with coverage reports' \
	  '  make bench          Run evaluation and verify dataset artifacts' \
	  '  make demo           Start an isolated, visibly-labelled synthetic demo' \
	  '  make demo-down      Stop the isolated demo without removing volumes' \
	  '  make compose-config Validate the default Compose configuration'

install:
	@$(PYTHON) -m venv backend/.venv
	@backend/.venv/bin/python -m pip install --disable-pip-version-check -r backend/requirements.txt
	@backend/.venv/bin/python -m pip install --disable-pip-version-check -e './verify[test]'
	@dotnet restore control-plane/DeployGuard.ControlPlane.slnx --nologo
	@$(NPM) --prefix frontend ci

dev:
	@./scripts/run-dev.sh

stop:
	@./scripts/stop-dev.sh

test: test-verify test-backend test-dotnet test-frontend

test-verify:
	@backend/.venv/bin/python -m pytest verify/tests

test-backend:
	@cd backend && .venv/bin/python -m pytest

test-dotnet:
	@dotnet test control-plane/DeployGuard.ControlPlane.slnx --nologo

test-frontend:
	@$(NPM) --prefix frontend test -- --watch=false

coverage:
	@cd backend && .venv/bin/python -m pytest -p pytest_cov --cov=app --cov-report=term-missing --cov-report=xml:coverage.xml --cov-fail-under=80
	@dotnet test control-plane/DeployGuard.ControlPlane.slnx --nologo --collect:"XPlat Code Coverage" --results-directory control-plane/TestResults
	@$(NPM) --prefix frontend run test:coverage

bench:
	@$(PYTHON) scripts/evaluate_benchmarks.py --output .runtime/evaluation-results.json
	@$(PYTHON) scripts/export_operational_dataset.py --check --output-dir bench/datasets/synthetic-v0.1

demo:
	@$(COMPOSE) -p deployguard-demo -f docker-compose.yml -f docker-compose.demo.yml up --build

demo-down:
	@$(COMPOSE) -p deployguard-demo -f docker-compose.yml -f docker-compose.demo.yml down

compose-config:
	@$(COMPOSE) config --quiet
