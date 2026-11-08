# Feature 01 — Socle projet

## Objectif
Un backend Django qui démarre, avec uv, Makefile, Docker (Postgres + Redis), lint, tests et CI.

## Périmètre
- Projet `backend/` géré par uv.
- Settings séparés, variables d'environnement.
- Docker Compose pour services d'infra.
- Makefile complet (voir `AGENTS.md`).
- Outillage qualité : ruff, pytest, couverture.
- Endpoint de santé, OpenAPI.

## Hors périmètre
Modèles métier, authentification (feature 02).

## Tâches

### Projet et dépendances
- [ ] `uv init` dans `backend/`, Python 3.12, `pyproject.toml`.
- [ ] Dépendances runtime : `django`, `djangorestframework`, `djangorestframework-simplejwt`, `drf-spectacular`, `django-environ`, `psycopg[binary]`, `celery`, `redis`, `django-cors-headers`, `django-filter`, `numpy`, `scipy`.
- [ ] Groupe dev : `pytest`, `pytest-django`, `pytest-cov`, `factory-boy`, `ruff`, `pytest-mock`.
- [ ] Django Channels et `channels-redis` seront ajoutés en feature 10.

### Django
- [ ] `django-admin startproject config .` puis découpage `config/settings/{base,development,production,testing}.py`.
- [ ] `DJANGO_SETTINGS_MODULE` par défaut en dev ; testing utilise une DB de test Postgres.
- [ ] Lecture de la config via `django-environ`, fichier `.env.example` complet.
- [ ] Package `core/` : `UUIDModel`, `TimestampedModel`, handler d'exceptions DRF (format d'erreur unique), pagination par défaut.
- [ ] Dossier `apps/` vide avec `__init__.py`.
- [ ] URLs `/api/v1/` ; endpoint `GET /api/v1/health/` (état app, DB, Redis).
- [ ] drf-spectacular : `/api/schema/`, `/api/docs/` (Swagger).
- [ ] CORS configurable (origine du frontend Vite par défaut en dev).
- [ ] `config/celery.py` + import dans `config/__init__.py` (broker Redis), tâche d'exemple `ping`.

### Docker
- [ ] `docker-compose.yml` à la racine du repo : `postgres`, `redis` (volumes nommés, healthchecks).
- [ ] `backend/Dockerfile` multi-stage avec uv (image de prod du backend).
- [ ] Variables de connexion cohérentes avec `.env.example`.

### Makefile
- [ ] Cibles : `install run migrate makemigrations worker test test-cov lint format check shell superuser schema up down`.
- [ ] Toutes les commandes passent par `uv run`.
- [ ] `make help` liste les cibles avec description (`## texte`).

### Qualité et CI
- [ ] Config ruff dans `pyproject.toml` (règles : E, F, I, B, UP, DJ ; longueur de ligne 100).
- [ ] Config pytest dans `pyproject.toml` (`--reuse-db`, settings testing).
- [ ] Workflow GitHub Actions : service Postgres + Redis, `uv sync`, `make check`.
- [ ] `.gitignore`, `.editorconfig`.

## Tests
- Test de l'endpoint `health`.
- Test du handler d'erreurs (format).
- Test de la pagination par défaut.

## Ajouts (revue de roadmap)

### Observabilité dès le départ
- [ ] Logs structurés JSON (`structlog` ou équivalent) en prod, lisibles en dev ; identifiant de requête (`X-Request-ID`) propagé dans les logs et les tâches Celery.
- [ ] Sentry configuré via `SENTRY_DSN` (désactivé si vide), avec nettoyage des champs sensibles (mots de passe, jetons, en-têtes d'autorisation, `samples`).
- [ ] Test vérifiant que les champs sensibles sont filtrés.

### Contrat d'API et client TypeScript
- [ ] Schéma OpenAPI écrit dans `backend/openapi.yaml` (committé) via `make schema`.
- [ ] `make schema-check` compare le schéma généré au fichier committé ; intégré à `make check` et à la CI.
- [ ] Documenter dans `documentation/api/` comment le frontend génère son client TypeScript (`openapi-typescript`) depuis ce fichier.
- [ ] Conventions de schéma : `operationId` stables, enums nommés, réponses d'erreur typées (`ErrorResponse`).

### Outillage
- [ ] Cibles Makefile `schema-check`, `simulate` et `loadtest` créées en stub (message « implémenté en feature 07 »).
- [ ] `core/scopes.py` créé vide avec le mécanisme d'enregistrement des scopes (rempli en feature 03).
- [ ] Squelette `core/storage.py` (interface `RawStore`, implémentée en feature 07).

### Critères d'acceptation supplémentaires
- `make schema-check` passe et échoue si l'on modifie un endpoint sans régénérer le schéma.
- Une exception levée dans une vue apparaît dans les logs structurés avec son identifiant de requête.

## Critères d'acceptation
- `make up && make migrate && make run` démarre le serveur.
- `make check` passe en local et en CI.
- `/api/docs/` affiche Swagger.
- `make help` est lisible.
