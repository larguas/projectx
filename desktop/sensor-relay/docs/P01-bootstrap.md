# P01 — Socle du module PC

## Objectif
Un projet Python `desktop/sensor-relay/` qui s'installe avec uv, avec config, logs, chemins, couche `platform/`, Makefile et CI (macOS + Linux).

## Périmètre
Projet uv, configuration, chemins par OS, logs structurés, abstraction de plateforme, CLI minimale, Makefile, CI.

## Hors périmètre
Tout le reste (protocole, capteurs, réseau).

## Tâches

### Projet
- [ ] `uv init` dans `desktop/sensor-relay/`, Python 3.12, layout `src/emg_agent/`, point d'entrée `emg-agent` (typer).
- [ ] Dépendances runtime : `typer`, `rich`, `pydantic`, `pydantic-settings`, `httpx`, `structlog`, `platformdirs`, `keyring`, `numpy`, `filelock`.
- [ ] Groupe dev : `pytest`, `pytest-asyncio`, `pytest-cov`, `respx`, `ruff`, `mypy`, `jsonschema`.
- [ ] Arborescence vide du `AGENTS.md` (packages avec `__init__.py`).

### Configuration et chemins
- [ ] `config.py` (pydantic-settings) : variables `EMGAGENT_*` + fichier TOML dans le dossier de config utilisateur. Champs : `api_base_url` (défaut `http://localhost:8000`), `web_base_url`, `block_duration_ms` (défaut 200), `spool_max_mb`, `log_level`, `control_port`.
- [ ] `paths.py` via `platformdirs` : données, config, logs, cache (sous macOS : `~/Library/Application Support/…`, `~/Library/Logs/…`). Nom d'application centralisé dans une constante.
- [ ] Création des dossiers avec permissions restrictives (0700 pour les données).

### Logs
- [ ] `logging.py` (structlog) : console lisible en dev, JSON dans un fichier avec rotation dans le dossier de logs.
- [ ] Processeur de **masquage** : `samples`, `token`, `access`, `refresh`, `Authorization`, `device_code` jamais écrits.
- [ ] Liaison de contexte (`session_id`, `device_id`) pour les logs d'une séance.

### Couche plateforme
- [ ] `platform/base.py` : protocole `PlatformServices` avec `prevent_sleep()`/`allow_sleep()`, `open_url(url)`, `notify(title, body)`, `autostart_enable()/disable()/is_enabled()`, `bluetooth_status()`. 
- [ ] `platform/macos.py` : implémentations simples (`open` pour les URLs, `osascript` pour les notifications, `caffeinate -i -w <pid>` pour empêcher la veille) ; autostart et Bluetooth en stubs documentés (P10/P14).
- [ ] `platform/generic.py` : repli (Linux, CI) sans effet de bord.
- [ ] Fabrique `get_platform()` selon `sys.platform`.

### CLI minimale
- [ ] `emg-agent version` et `emg-agent doctor` : version, Python, OS, chemins, configuration, disponibilité de `bleak`/`pyserial`, aide à diagnostiquer (étendu en P10/P13).

### Outillage et CI
- [ ] `Makefile` (cibles de l'`AGENTS.md`, `make help` avec descriptions ; `run-fake`, `fake-backend`, `build-macos` en stubs « implémenté en P0x »).
- [ ] Config ruff/mypy/pytest dans `pyproject.toml` (marqueurs `hardware`, `macos`, `integration`, `soak` ; ignorés par défaut).
- [ ] GitHub Actions `agent-ci.yml` : filtre de chemins `desktop/**`, matrice `macos-latest` + `ubuntu-latest`, `uv sync`, `make check`.
- [ ] `.gitignore`, `README.md` court (installation, commandes).

## Tests
- Chargement de config (défauts, variable d'environnement, fichier TOML).
- Chemins par OS (monkeypatch de `sys.platform`).
- Masquage des champs sensibles dans les logs.
- `doctor` s'exécute sans erreur.
- **Garde-fou multi-plateforme** : un test parcourt `src/emg_agent/` et échoue si `fcntl`, `os.getuid`, `/Users`, `~/Library` ou `AppData` apparaissent en dehors de `platform/` et des adaptateurs.

## Critères d'acceptation
- `make install && emg-agent doctor` fonctionne sur macOS.
- `make check` passe en local et en CI (macOS + Linux).
