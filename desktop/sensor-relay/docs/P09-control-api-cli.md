# P09 — API de contrôle locale, daemon et CLI

## Objectif
Exposer le cœur du module par une API locale **sécurisée**, un daemon et une CLI complète. L'UI (P12) et la barre de menus utiliseront la même API.

## Périmètre
Daemon, API locale FastAPI, événements en direct, CLI, instance unique, arrêt propre.

## Hors périmètre
Interface graphique (P12).

## API locale (`control/`)
- Écoute **127.0.0.1 uniquement** (port configurable ; repli sur un port libre, écrit dans un fichier d'exécution).
- **Sécurité** : jeton aléatoire généré à l'installation (fichier 0600 dans le dossier de données), exigé dans `Authorization: Bearer` ; contrôle strict des en-têtes `Host` et `Origin` (refus de tout ce qui n'est pas localhost/l'origine de l'UI embarquée) pour empêcher qu'une page web quelconque pilote le module (DNS rebinding, requêtes cross-site) ; CORS désactivé par défaut.
- Endpoints (préfixe `/v1`) : `status` (agrégat : connexion, serveur, protocole, capteurs, séance, outbox, qualité, horloge) · `events` (SSE ou WebSocket) · `auth/login` (démarrer/état/annuler), `auth/logout` · `sensors` (scan, liste, connexion, déconnexion) · `athletes`, `setups` · `session` (préparer, contrôle préalable, démarrer, arrêter, annuler, reprendre, forcer la fin) · `markers` · `outbox` (stats, relancer les rejets, séances à synchroniser) · `diagnostics/export` · `live` (WebSocket de signal décimé pour l'UI).
- Schéma OpenAPI local committé (`desktop/sensor-relay/openapi-local.yaml`) + `make schema-check`.

## Daemon
- `emg-agent daemon` : cœur asyncio + API locale ; **instance unique** (`filelock`) ; arrêt propre sur SIGTERM/SIGINT : en cours d'enregistrement, vider l'outbox et conserver l'état (ne **jamais** terminer automatiquement la séance).

## CLI (client de l'API, typer + rich)
`daemon`, `status`, `login`/`logout`/`whoami`, `sensors scan|connect|disconnect|info`, `athletes`, `record start --athlete … --setup … --sensor … [--type calibration]`, `record stop`, `mark KIND [texte]`, `outbox`, `doctor`, `logs`. Barre de progression à l'arrêt (vidage). `emg-agent run` : daemon + session interactive en un seul processus pour les essais.

## Tâches
- [ ] Application FastAPI, authentification par jeton, contrôles `Host`/`Origin`.
- [ ] Endpoints et flux d'événements branchés sur le cœur (P04–P08).
- [ ] Daemon, instance unique, arrêt propre.
- [ ] CLI complète et schéma OpenAPI local committé.

## Tests
- API via client ASGI : tous les endpoints, flux d'événements.
- **Sécurité** : sans jeton, mauvais jeton, `Host` étranger, `Origin` étranger → refus ; aucune écoute hors 127.0.0.1.
- Instance unique ; arrêt en cours d'enregistrement sans perte.
- CLI (CliRunner, API simulée).
- Scénario complet via la CLI avec capteur simulé + faux backend.

## Critères d'acceptation
- `make run-fake` puis `emg-agent record start …` / `record stop` enregistre une séance simulée jusqu'au faux backend.
- `make check` passe.
