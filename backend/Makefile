.DEFAULT_GOAL := help

UV ?= uv
DOCKER ?= docker
COMPOSE_FILE ?= ../docker-compose.yml

.PHONY: help install run migrate makemigrations worker test test-cov lint format \
        check shell superuser schema schema-check simulate loadtest up down

help: ## Affiche cette aide
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z0-9_-]+:.*?##/ {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Installe les dépendances (uv sync, groupe dev inclus)
	$(UV) sync --all-groups

run: ## Démarre le serveur de développement Django
	$(UV) run python manage.py runserver 0.0.0.0:8000

migrate: ## Applique les migrations
	$(UV) run python manage.py migrate

makemigrations: ## Crée des migrations (option : make makemigrations APP=accounts)
	$(UV) run python manage.py makemigrations $(if $(APP),$(APP))

worker: ## Démarre un worker Celery
	$(UV) run celery -A config worker --loglevel=info

test: ## Lance la suite de tests (pytest)
	$(UV) run pytest

test-cov: ## Tests avec mesure de couverture
	$(UV) run pytest --cov --cov-report=term-missing

lint: ## Ruff check
	$(UV) run ruff check .

format: ## Formate le code (ruff format + correctifs automatiques)
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

check: ## Lint + format + check Django + schéma OpenAPI + tests
	$(MAKE) lint
	$(UV) run ruff format --check .
	$(UV) run python manage.py check
	$(MAKE) schema-check
	$(UV) run pytest

shell: ## Ouvre un shell Django
	$(UV) run python manage.py shell

superuser: ## Crée un superutilisateur
	$(UV) run python manage.py createsuperuser

schema: ## Génère le schéma OpenAPI (openapi.yaml, à committer)
	$(UV) run python manage.py spectacular --file openapi.yaml --validate

schema-check: ## Échoue si le schéma committé diffère du schéma généré
	$(UV) run python manage.py spectacular --file .openapi-check.yaml --validate
	@if diff -u openapi.yaml .openapi-check.yaml > /dev/null; then \
		rm -f .openapi-check.yaml; \
	else \
		echo "Erreur : openapi.yaml est en dérive par rapport au schéma généré."; \
		echo "Relancez 'make schema' et commitez le résultat."; \
		exit 1; \
	fi

simulate: ## Simulateur de données (implémenté en feature 07)
	@echo "Implémenté en feature 07."

loadtest: ## Test de charge de l'ingestion (implémenté en feature 07)
	@echo "Implémenté en feature 07."

up: ## Démarre Postgres + Redis (docker compose, racine du repo)
	$(DOCKER) compose -f $(COMPOSE_FILE) up -d --wait

down: ## Arrête Postgres + Redis (docker compose)
	$(DOCKER) compose -f $(COMPOSE_FILE) down
