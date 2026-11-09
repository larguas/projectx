# Feature 06 — Séances (sessions d'acquisition)

## Objectif
Gérer le cycle de vie d'une séance : création, démarrage, fin, annulation. La séance est l'objet auquel se rattachent les données, les analyses, les annotations et les rapports. Elle référence un setup de placement figé (feature 05b).

## Attention : nom d'app
`sessions` entre en conflit avec `django.contrib.sessions`. Utiliser `AppConfig.name = "apps.sessions"` avec `label = "training_sessions"` (ou nommer le dossier `training_sessions`). Voir `00-index.md`, décision n°2.

## Périmètre
Modèle de séance, machine à états, appareils multiples, canaux figés depuis le setup, séances de calibration, annotations/marqueurs.

## Hors périmètre
Réception des blocs de données (feature 07), création de la calibration depuis les signaux (feature 09).

## Modèles
- `Session` : `id` UUID, `athlete`, `created_by`, `session_type` (`training`/`calibration`/`test`), `setup` (FK `SensorSetup`, nullable), `setup_declared` (bool), `exercise` (nullable), `workout` (nullable), `status` (`created` → `recording` → `completed` | `cancelled` | `failed`), `source` (`mobile`/`pc`/`import`), `protocol_version`, `started_at`, `ended_at`, `notes`, `acquisition_config` (JSON : sample_rate prévu, canaux), `calibration_type` (nullable : `mvc`/`rest_baseline`, requis si `session_type = calibration`).
- `SessionDevice` : `session`, `device`, `role` (`primary`/`secondary`), `clock_offset_ms` (nullable, estimé en feature 07), unique `(session, device)`. Une séance peut utiliser plusieurs appareils (il n'y a plus de FK `device` unique).
- `SessionChannel` : `session`, `device`, `channel_id`, `muscle` (FK), `side`, `data_type` (`emg_raw`, `emg_envelope`, `imu_accel`, `imu_gyro`...), `units`, `calibration` (JSON, copie figée des informations utiles), `setup_channel` (nullable), unique `(session, device, channel_id)`.
- `SessionAnnotation` : `session`, `kind` (`set_start`, `set_end`, `rep_start`, `rep_end`, `note`, `artifact`, `sync_pulse`), `offset_ms` (par rapport au début d'acquisition, horloge de l'appareil primaire), `text`, `metadata` (JSON), `author`, `created_at`.

## Machine à états
```text
created → recording → completed
created → cancelled
recording → cancelled | failed
```
Toute autre transition renvoie `409`. Services dédiés (`start_session`, `complete_session`, `cancel_session`) ; jamais de changement de statut direct depuis un serializer.

## Règles métier
- **Setup** : si `setup` est fourni, les `SessionChannel` sont créés automatiquement en copiant les `SetupChannel` (muscle, côté figés). Le setup devient alors immuable (voir 05b).
- Sans `setup` : la séance est acceptée avec `setup_declared = false` et un avertissement `setup_not_declared` renvoyé dans la réponse et dans le détail de la séance. Les canaux peuvent être déclarés à la main.
- Une séance `calibration` exige un `setup` (une calibration sans placement connu n'est pas exploitable) et un `calibration_type`.
- Plusieurs appareils : les canaux de chaque appareil sont distincts ; `device` obligatoire sur chaque canal.
- Les annotations sont autorisées pendant `recording` et après `completed` (corrections du coach), jamais sur `cancelled`.

## Endpoints
- `GET/POST /api/v1/sessions/`
- `GET/PATCH /api/v1/sessions/{id}/`
- `POST /api/v1/sessions/{id}/start/`, `/complete/`, `/cancel/`
- `GET/PUT /api/v1/sessions/{id}/channels/`
- `GET/PUT /api/v1/sessions/{id}/devices/`
- `GET/POST /api/v1/sessions/{id}/annotations/`, `PATCH/DELETE /api/v1/sessions/{id}/annotations/{aid}/`
- `GET /api/v1/athletes/{id}/sessions/suggested-setup/` : renvoie le setup de la dernière séance (proposition « même placement que la dernière fois ? »).

## Tâches
- [x] App, modèles, migrations.
- [x] Services de transition avec verrouillage (`select_for_update`).
- [x] Création : vérifier le droit du créateur sur le sportif (`core.access`, scope `sessions:write`), que les appareils lui sont accessibles, et que les canaux sont compatibles avec les capacités du modèle d'appareil.
- [x] Copie des canaux depuis le setup et marquage `setup_declared`.
- [x] Calibration : validation `session_type=calibration`.
- [x] Hook `on_session_completed(session)` (vide ici, branché en features 07 et 09) ; il reçoit `session_type` pour que la feature 09 puisse créer la calibration.
- [x] Annotations : CRUD, validation du `kind`, tri par `offset_ms`.
- [x] Lecture : sportif propriétaire + coachs/équipes avec scope `sessions:read`.
- [x] Filtres : sportif, statut, dates, exercice, appareil, `session_type`, `setup_declared`.
- [x] Admin Django.

## Tests
- Chaque transition valide/invalide, concurrence basique.
- Droits de création/lecture, appareil d'un autre utilisateur refusé.
- Création avec setup : canaux copiés, setup immuable ensuite ; sans setup : avertissement et `setup_declared=false`.
- Calibration sans setup refusée.
- Plusieurs appareils, canaux distincts.
- Annotations : création pendant/après la séance, refus sur séance annulée.
- Filtres.

## Critères d'acceptation
- Un sportif crée, démarre et termine une séance avec un setup ; un coach autorisé la consulte.
- Une séance sans setup est possible mais clairement marquée.
- `make check` passe.
