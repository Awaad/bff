.DEFAULT_GOAL := help

UV ?= uv
PNPM ?= pnpm
DOCKER ?= docker
BFF_HOST ?= 127.0.0.1
BFF_PORT ?= 8000

.PHONY: help doctor doctor-auth deps infra-up infra-down infra-status db-current db-upgrade db-roles db-sync bootstrap api auth-live test test-db check

help:
	@printf '%s\n' \
		'Backend for Framer local development' \
		'' \
		'  make doctor       Validate local tooling and .env' \
		'  make doctor-auth  Validate WorkOS live-auth configuration' \
		'  make bootstrap    Install deps, start infra, migrate DB, apply roles' \
		'  make infra-up     Start local infrastructure and wait for readiness' \
		'  make infra-down   Stop local infrastructure without deleting volumes' \
		'  make infra-status Show local infrastructure status' \
		'  make db-current   Show current Alembic revision' \
		'  make db-sync      Upgrade DB to head and apply current application roles' \
		'  make api          Run the control API locally' \
		'  make auth-live    Run the real WorkOS PKCE authentication proof' \
		'  make test         Run non-PostgreSQL Python tests' \
		'  make test-db      Run PostgreSQL-marked tests' \
		'  make check        Run the non-PostgreSQL CI quality gates'

doctor:
	$(UV) run --no-sync python scripts/dev/doctor.py

doctor-auth:
	$(UV) run --no-sync python scripts/dev/doctor.py --profile auth

deps:
	$(UV) sync --locked
	$(PNPM) install --frozen-lockfile

infra-up:
	$(DOCKER) compose --env-file .env up -d --wait

infra-down:
	$(DOCKER) compose --env-file .env down

infra-status:
	$(DOCKER) compose --env-file .env ps

db-current:
	$(UV) run alembic current

db-upgrade:
	$(UV) run alembic upgrade head

db-roles:
	$(UV) run python scripts/db/bootstrap_roles.py

db-sync:
	$(MAKE) db-upgrade
	$(MAKE) db-roles

bootstrap:
	$(MAKE) doctor
	$(MAKE) deps
	$(MAKE) infra-up
	$(MAKE) db-sync

api: doctor
	$(UV) run uvicorn bff_control.main:app --host $(BFF_HOST) --port $(BFF_PORT)

auth-live: doctor-auth
	$(UV) run python scripts/auth/workos_live_probe.py

test:
	$(UV) run pytest -m "not postgres"

test-db:
	$(UV) run pytest -m postgres -vv

check:
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy -p bff_control -p scripts -p tests
	$(UV) run pytest -m "not postgres"
	$(UV) run python scripts/check_python_boundaries.py
	$(UV) run python scripts/api/export_openapi.py --check
	$(UV) run python scripts/check_github_actions_pins.py
	$(PNPM) exec prettier --check .
	node --test tests/boundaries/ts-boundaries.test.mjs
	node scripts/check_ts_boundaries.mjs
	$(PNPM) --filter @bff/api-contract test
	$(PNPM) --filter @bff/api-contract check

format:
	$(UV) run ruff format .