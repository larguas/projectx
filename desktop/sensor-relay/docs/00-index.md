# Module PC (sensor-relay) — Découpage en features

Chaque feature = une session opencode. Ordre à respecter (dépendances indiquées). Cible : **macOS d'abord**, Windows ensuite (P15). Les fichiers sont nommés `P01` à `P15` pour ne pas les confondre avec ceux du backend.

| # | Fichier | Feature | Dépend de | Taille |
|---|---|---|---|---|
| P01 | `P01-bootstrap.md` | Socle : uv, Makefile, config, logs, couche `platform/`, CI | — | M |
| P02 | `P02-protocol-core.md` | Blocs, encodage, séquences, horloge d'acquisition | P01, `shared/protocol/` | M |
| P03 | `P03-adapters-replay.md` | Interface capteur, Device Manager, capteur simulé/replay | P02 | M |
| P04 | `P04-pipeline.md` | Collector, Validator, Buffer, Formatter | P03 | L |
| P05 | `P05-storage-outbox.md` | Outbox SQLite, stockage local temporaire | P02 | M |
| P06 | `P06-auth.md` | Connexion « device code », trousseau, refresh | P01, backend 02 | M |
| P07 | `P07-backend-client-uploader.md` | Client API, envoi, reprise, Connection Manager | P05, P06, backend 07 | L |
| P08 | `P08-session-orchestration.md` | Déroulé d'une séance, reprise après crash, calibration, marqueurs | P04, P07, backend 03–06 | L |
| P09 | `P09-control-api-cli.md` | API locale sécurisée + CLI + daemon | P08 | M |
| P10 | `P10-ble-adapter-macos.md` | Adaptateur BLE (bleak) + profil du capteur | P03, 06b | L |
| P11 | `P11-serial-adapter.md` | Adaptateur USB/série (si le capteur en a besoin) | P03, 06b | M |
| P12 | `P12-local-ui-menubar.md` | UI locale + barre de menus macOS | P09 | L |
| P13 | `P13-monitoring-robustness.md` | Métriques, diagnostics, tests de robustesse | P08 | M |
| P14 | `P14-packaging-macos.md` | `.app`, signature, notarisation, démarrage auto | P12 | L |
| P15 | `P15-windows-port.md` | Port Windows (plus tard) | P14 | M |

## Lien avec le spike backend (06b)

Le spike 06b reste un **script jetable** (`scripts/sensor_spike/read_sensor.py`) : il faut les données réelles du capteur pour tout le reste, ne le retarde pas. Pendant que tu analyses ses résultats, P01 à P09 se font **sans capteur** (capteur simulé + faux backend). P10 (adaptateur BLE réel) vient ensuite, avec `SENSOR_FINDINGS.md` en entrée ; sa commande `sensors dump` remplace le script du spike.

Prérequis avant P02 : `shared/protocol/PROTOCOL.md` et `block.schema.json` existent (écrits en 06b/07). Sinon, terminer d'abord cette partie du 06b.

## Parcours le plus court « capteur → backend »

P01 → P02 → (P03 ∥ P05) → P04 → P06 → P07 → P08 → P09 → P10.
**MVP module PC = P01 à P10** : un utilisateur lance `emg-agent record ...` dans un terminal et la séance arrive dans le backend. P12 à P14 rendent le module installable par un coach non technique.

## Prérequis backend par feature

| Feature | Backend nécessaire |
|---|---|
| P06 | 02 (flux device code, refresh) |
| P07 | 02 ; **07** pour la phase B (tests d'intégration réels). Avant : faux backend |
| P08 | 03 (accès/scopes), 04 (devices), 05b (setups), 06 (séances, annotations) |
| P10 / P11 | spike 06b (`SENSOR_FINDINGS.md`) |

## Décisions d'architecture (à respecter dans toutes les features)

1. **Cœur headless asyncio + API de contrôle locale.** L'UI, la barre de menus et la CLI sont des clients de cette API ; aucune logique métier dans l'UI.
2. **Adaptateur par capteur** derrière une interface unique (profil + parser pur + transport). Le backend ne dépend jamais du modèle de capteur.
3. **Pipeline** : capteur → collector → validator → buffer → formatter → outbox → uploader → backend (conforme au spec §4.2).
4. **Outbox SQLite** : écrire avant d'envoyer ; numéros de séquence persistés dans la même transaction que le bloc ; reprise exacte après crash.
5. **Fin de séance** : `complete` n'est appelé qu'après envoi **et** accusé de tous les blocs (le backend refuse les blocs sur une séance non `recording`).
6. **Authentification** : flux « device code » (backend feature 02), jetons dans le trousseau OS, jamais de secret global ni de mot de passe saisi dans le module.
7. **API locale sécurisée** : 127.0.0.1 uniquement, jeton local, contrôle strict de `Host`/`Origin` (une page web quelconque ne doit pas pouvoir piloter le module).
8. **Multi-plateforme** : tout ce qui dépend de l'OS est dans `platform/` ou un adaptateur ; CI macOS + Linux dès P01, Windows en P15.
9. **Horloge** : `acquisition_timestamp` dérivé du compteur d'échantillons ancré sur l'horloge monotone ; une coupure crée un trou visible, jamais un recollage.
10. **Traitement léger seulement** : contrôles de qualité locaux simples (signal plat, saturation, pertes) ; le moteur de signal reste côté backend.
11. **Versions** : le module envoie `X-Protocol-Version`, `X-Client-Version`, `X-Client-Type: pc_agent` ; sur `426` il s'arrête avec un message clair (lien de mise à jour).
12. **Confidentialité** : spool dans le dossier utilisateur, purge après vérification ; logs et diagnostics sans échantillons ni jetons.

## Points à vérifier côté backend (à signaler, pas à corriger depuis le module)

- **Idempotence et `client_sent_at`** : le module met à jour `client_sent_at` à chaque tentative d'envoi. Le backend (feature 07) doit ignorer ce champ quand il compare le contenu d'un bloc rejoué (sinon : faux `409`). À vérifier en phase B de P07.
- **Fin de séance hors ligne** : le backend ne permet pas de démarrer une séance sans réseau (création + `start` côté serveur). C'est hors périmètre du MVP ; si besoin plus tard, prévoir un mode « séance locale puis import ».

## Décisions à prendre par toi

- **Nom du produit** : la commande s'appelle `emg-agent` en attendant ; elle est renommable (un seul endroit : `pyproject.toml`).
- **Compte Apple Developer (99 $/an)** : indispensable en P14 pour distribuer l'appli sans avertissement Gatekeeper. Pas nécessaire avant.
- **UI locale** (P12) : par défaut React + Vite (même stack que le frontend). Alternative plus légère : pages servies par Python avec htmx.
- **Architectures Mac** : Apple Silicon d'abord ; Intel en build séparé (pas de universal2 garanti avec numpy/pyobjc).

## Format de chaque fichier

Objectif · Périmètre · Hors périmètre · Interfaces/modules · Tâches (cases à cocher) · Tests · Critères d'acceptation.

## Prompt type pour opencode

```text
Lis desktop/sensor-relay/AGENTS.md, puis desktop/sensor-relay/docs/00-index.md
(section Décisions d'architecture), puis desktop/sensor-relay/docs/PNN-xxx.md.
Implémente uniquement cette feature, dans l'ordre des tâches. Coche les tâches
terminées. Termine quand `make check` passe (depuis desktop/sensor-relay/) et
donne un court compte rendu (décisions, écarts, points ouverts, « à corriger
côté backend »).
```
