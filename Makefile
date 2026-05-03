.PHONY: up down logs status seed demo reset openmrs-up openmrs-down help

# Full stack — all services
up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

logs:
	docker compose -f infra/docker-compose.yml logs -f

status:
	docker compose -f infra/docker-compose.yml ps

# OpenMRS only — heavy, start once and leave running
openmrs-up:
	docker compose -f infra/docker-compose.openmrs.yml up -d

openmrs-down:
	docker compose -f infra/docker-compose.openmrs.yml down

# Phase 1+
seed:
	bash scripts/seed.sh

# Phase 2+
demo:
	python scripts/run-demo.py

reset:
	bash scripts/reset-demo.sh

help:
	@echo "Targets: up, down, logs, status, seed, demo, reset, openmrs-up, openmrs-down"
