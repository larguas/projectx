# AGENTS.md — Conventions backend Plateforme EMG

Ce fichier est lu au début de CHAQUE session. Il contient les règles communes. Chaque feature a son propre fichier `NN-*.md` : ne traiter que la feature demandée.

## Règles de travail

- Une session = une feature. Ne pas déborder sur les features suivantes.
- Lire `AGENTS.md` + le fichier de la feature + `00-index.md` (section "Décisions d'architecture") uniquement.
- Ne pas modifier le code d'une feature précédente, sauf bug bloquant (le signaler dans le compte rendu).
- Écrire les tests en même temps que le code. Une feature n'est terminée que si `make check` passe.
- À la fin : cocher les tâches dans le fichier de la feature et lister les décisions prises / écarts.
- Commits petits, format Conventional Commits (`feat(devices): ...`).

## Stack

Python 3.12, Django 5.x, Django REST Framework, PostgreSQL, Redis, Celery, Django Channels, NumPy/SciPy, pytest, drf-spectacular (OpenAPI), ruff.

Gestion des dépendances : **uv uniquement** (`uv add`, `uv sync`, `uv run`). Jamais `pip install` ni `requirements.txt` à la main.

## Structure

```text
backend/
├── pyproject.toml          # dépendances + config ruff/pytest
├── uv.lock
├── Makefile
├── manage.py
├── config/
│   ├── settings/{base,development,production,testing}.py
│   ├── urls.py  asgi.py  wsgi.py  celery.py
├── apps/<app>/
│   ├── models.py  serializers.py  views.py  urls.py
│   ├── services.py  selectors.py  permissions.py  tasks.py
│   └── tests/
├── core/                   # code transverse (base models, pagination, exceptions, storage)
└── tests/                  # tests d'intégration transverses
```

## Règles de code

- Clés primaires : UUID (`core.models.UUIDModel`), plus `created_at` / `updated_at` (`TimestampedModel`).
- Vues fines : validation (serializer) puis appel d'un service. La logique métier est dans `services.py`, les lectures complexes dans `selectors.py`.
- API versionnée sous `/api/v1/`. Format d'erreur unique (handler d'exceptions DRF dans `core`).
- Pagination par défaut sur toutes les listes.
- Permissions : deny by default. Toute vue déclare explicitement ses permissions.
- Aucun secret dans le code : variables d'environnement via `django-environ` (`.env`, avec `.env.example` versionné).
- Le moteur `signal_processing` est du Python pur (NumPy/SciPy) : **aucun import Django** dans ce package.
- Fichiers : signaux bruts via `core.storage.RawStore` (segments), autres fichiers (photos, rapports) via `django.core.files.storage` (jamais `open()` direct), pour migrer vers S3/MinIO plus tard sans changement de code métier.
- Scopes d'accès : définis uniquement dans `core/scopes.py`, jamais en chaînes libres dans le code.
- Toute action sensible (partage, export, suppression, accès coach) appelle `audit.services.record_event(...)` (disponible dès la feature 03).
- Chaque modification de l'API met à jour le schéma OpenAPI committé (`make schema`) ; `make check` échoue en cas de dérive.
- Typage : annotations de types sur le code des services.

## Commandes (Makefile)

| Commande | Rôle |
|---|---|
| `make install` | `uv sync` |
| `make run` | serveur de dev Django |
| `make migrate` / `make makemigrations` | migrations |
| `make worker` | worker Celery |
| `make test` | pytest |
| `make test-cov` | pytest avec couverture |
| `make lint` | ruff check |
| `make format` | ruff format |
| `make check` | lint + format --check + `manage.py check` + tests |
| `make shell` | shell Django |
| `make superuser` | création d'un superuser |
| `make schema` | génère et écrit le schéma OpenAPI (`openapi.yaml`) |
| `make schema-check` | échoue si le schéma committé diffère du schéma généré |
| `make up` / `make down` | docker compose (postgres, redis) |
| `make simulate` | simulateur de données (feature 07), ex. `make simulate DURATION=30 CHANNELS=4` |
| `make loadtest` | test de charge de l'ingestion (feature 07) |

`make check` = lint + format --check + `manage.py check` + `schema-check` + tests.
