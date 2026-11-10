# AGENTS.md — Conventions du module PC (sensor-relay)

À lire au début de CHAQUE session sur le module PC. Les règles Django de `backend/AGENTS.md` **ne s'appliquent pas** à `desktop/`.
Chaque feature a son fichier `desktop/sensor-relay/docs/PNN-*.md` : ne traiter que la feature demandée.

## Règles de travail

- Une session = une feature. Ne pas déborder sur les suivantes.
- Lire uniquement : ce fichier + `desktop/sensor-relay/docs/00-index.md` (section « Décisions d'architecture ») + le fichier de la feature.
- Ne pas modifier le backend ni `shared/protocol/` : si un écart est découvert, le signaler dans le compte rendu (section « À corriger côté backend »).
- Tests écrits en même temps que le code. Une feature n'est terminée que si `make check` passe.
- À la fin : cocher les tâches dans le fichier de la feature, puis donner un compte rendu court (décisions, écarts, points ouverts).
- Commits petits, Conventional Commits (`feat(agent): ...`).

## Stack

Python 3.12, **uv uniquement** (`uv add`, `uv sync`, `uv run`), asyncio, httpx, pydantic v2, structlog, typer, platformdirs, keyring, numpy, bleak (BLE), pyserial, FastAPI + uvicorn (API de contrôle locale), SQLite (stdlib). Tests : pytest, pytest-asyncio, respx, pytest-cov. Qualité : ruff, mypy.

## Structure

```text
desktop/sensor-relay/
├── pyproject.toml  uv.lock  Makefile  AGENTS.md
├── docs/              # 00-index.md + P01…P15 (consignes de développement)
├── src/emg_agent/
│   ├── cli.py  config.py  paths.py  logging.py
│   ├── platform/      # TOUT ce qui dépend de l'OS (base.py, macos.py, generic.py)
│   ├── protocol/      # blocs, encodage, séquences, horloge d'acquisition
│   ├── adapters/      # base, replay, synthetic, ble, serial, profils capteurs
│   ├── devices/       # Device Manager
│   ├── collector/     # Data Collector + Data Validator
│   ├── buffer/        # Signal Buffer + Data Formatter
│   ├── storage/       # outbox SQLite
│   ├── authentication/
│   ├── transport/     # Backend Client, uploader, Connection Manager
│   ├── sessions/      # orchestration d'une séance
│   ├── control/       # API locale (FastAPI) + événements
│   ├── monitoring/    # métriques, diagnostics
│   └── ui/            # (P12) UI locale statique embarquée + tray
└── tests/  (fake_backend/, data/, soak/)
```
Écart assumé par rapport au spec (§15) : package `src/emg_agent/` (layout uv) au lieu de `app/` + `requirements/`.

## Règles de code

- **Aucune perte silencieuse de données** : toute perte (capteur, file pleine, rejet serveur) est comptée, journalisée, exposée dans le statut et déclarée au backend (`dropped_samples`).
- **Écrire avant d'envoyer** : un bloc est persisté dans l'outbox avant tout envoi ; il n'est supprimé qu'après accusé et vérification de fin de séance.
- Les timestamps d'acquisition viennent du compteur d'échantillons / de l'horloge monotone, jamais de l'heure d'arrivée d'un paquet quand mieux existe.
- Aucun secret en clair : jetons dans le trousseau de l'OS (`keyring`). Les logs ne contiennent **jamais** d'échantillons, de jetons ni d'en-têtes d'autorisation.
- Tout code dépendant de l'OS vit dans `platform/` (ou dans un adaptateur capteur). Pas de `fcntl`, `os.getuid`, chemins en dur (`/Users`, `~/Library`) ailleurs : utiliser `platformdirs` et `platform/`. Un test garde-fou le vérifie (P01).
- Chaque capteur = un profil + un parser pur (`bytes → frames`) + un transport. Le reste du code ne connaît jamais le modèle de capteur.
- Code asynchrone : pas d'appel bloquant dans la boucle asyncio (SQLite, série, disque via exécuteur/thread).
- Annotations de types partout ; `mypy` doit passer.

## Marqueurs de tests

| Marqueur | Sens | Par défaut |
|---|---|---|
| `hardware` | nécessite le vrai capteur | ignoré |
| `macos` | ne tourne que sous macOS | auto-skip ailleurs |
| `integration` | nécessite le vrai backend lancé | ignoré |
| `soak` | tests de robustesse longs | ignoré |

## Commandes (Makefile, dans `desktop/sensor-relay/`)

| Commande | Rôle |
|---|---|
| `make install` | `uv sync` |
| `make run` | `emg-agent daemon` |
| `make run-fake` | daemon avec capteur simulé (replay) et faux backend |
| `make fake-backend` | lance le faux backend local (tests/fake_backend) |
| `make test` / `make test-cov` | pytest (sans hardware/integration/soak) |
| `make test-hw` | tests avec le vrai capteur |
| `make integration` | tests contre le vrai backend |
| `make soak` | tests de robustesse longs |
| `make lint` / `make format` / `make typecheck` | ruff, ruff format, mypy |
| `make check` | lint + format --check + typecheck + tests |
| `make sync-protocol` | copie `shared/protocol/block.schema.json` dans le package |
| `make build-macos` | `.app` macOS (P14) |
