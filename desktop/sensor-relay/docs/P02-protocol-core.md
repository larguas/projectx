# P02 — Cœur du protocole d'acquisition

## Objectif
Construire, valider et encoder des blocs conformes au protocole partagé, avec numéros de séquence fiables et timestamps cohérents.

## Pré-requis
`shared/protocol/PROTOCOL.md` et `block.schema.json` existent (spike 06b / backend 07). Si absents : s'arrêter et le signaler. En cas d'écart avec `SENSOR_FINDINGS.md`, le spike prime.

## Périmètre
Modèles de blocs, validation par le schéma JSON, encodage, compteurs de séquence, horloge d'acquisition, en-têtes de version.

## Hors périmètre
Capteurs réels, réseau, stockage (le compteur persistant est branché en P05).

## Modules (`protocol/`)
- `models.py` : modèles pydantic `Block`, `ChannelData`, `BlockMetadata`, enum `DataType` (`emg_raw`, `emg_envelope`, `imu_accel`, `imu_gyro`…). Champs : `protocol_version`, `session_id`, `device_id`, `sequence_number`, `acquisition_timestamp`, `client_sent_at`, `sample_rate`, `data_type`, `channels[]`, `calibration`, `metadata`, optionnels `sample_timestamps`, `dropped_samples`.
- `schema.py` : charge `block.schema.json` (copie embarquée dans le package, `make sync-protocol`), `validate_block(dict)`.
- `encoding.py` : interface `BlockEncoder` ; `JsonGzipEncoder` (défaut) ; encodeur binaire **uniquement si** `SENSOR_FINDINGS.md` le demande (sinon stub documenté).
- `sequence.py` : `SequenceCounter` par `(session, device, data_type)`, interface `SequenceStore` (mémoire ici, SQLite en P05), reprise après redémarrage.
- `clock.py` : `AcquisitionClock` — ancre l'heure UTC sur l'horloge monotone au début du flux ; `timestamp_for_sample(index)` calculé depuis `sample_rate` et le nombre d'échantillons ; `reanchor(gap)` après coupure ; mesure de dérive.
- `versions.py` : `PROTOCOL_VERSION`, `client_version()` (métadonnées du package), `headers()` → `X-Protocol-Version`, `X-Client-Version`, `X-Client-Type: pc_agent`.

## Tâches
- [ ] Modèles et validation, avec messages d'erreur exploitables.
- [ ] Copie du schéma dans le package + `make sync-protocol` + test de dérive (copie identique à `shared/`).
- [ ] `JsonGzipEncoder` + décodeur (pour les tests) ; taille mesurée sur un exemple réaliste.
- [ ] `SequenceCounter` : strictement croissant, sans trou, reprise via `SequenceStore`.
- [ ] `AcquisitionClock` : pas de dérive cumulée sur des millions d'échantillons ; coupure = nouveau point d'ancrage explicite.
- [ ] En-têtes de version.

## Tests
- Bloc valide accepté par le schéma ; bloc invalide (type, canal vide, taux manquant) refusé.
- Aller-retour encodage/décodage identique ; gzip réduit la taille.
- Séquences : monotones, reprise après « redémarrage » simulé, indépendantes par flux.
- Horloge : 1 kHz pendant 1 M d'échantillons sans dérive ; coupure de 5 s reflétée dans les timestamps.
- Test de dérive de la copie du schéma.

## Critères d'acceptation
- Un bloc généré par le module valide contre le **vrai** `shared/protocol/block.schema.json`.
- `make check` passe.
