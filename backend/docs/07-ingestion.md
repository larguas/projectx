# Feature 07 — Ingestion : protocole d'acquisition et réception des données

## Objectif
Recevoir de façon fiable et performante les blocs EMG/IMU envoyés par le module PC, le mobile ou l'import. Feature critique du MVP.

## Pré-requis
Feature 06b (spike capteur) terminée : le protocole ci-dessous est une hypothèse de départ, à aligner sur `SENSOR_FINDINGS.md`. En cas d'écart, **le spike prime** et ce fichier doit être mis à jour avant de coder.

## Périmètre
- Protocole d'acquisition versionné (doc partagé + schéma validable).
- Endpoint de réception par blocs, idempotent, avec accusés de réception.
- Stockage brut performant par segments.
- Détection des trous de séquence.
- Politique de version minimale du protocole et des clients.
- Synchronisation d'horloge entre appareils.
- Simulateur de données et test de charge.

## Hors périmètre
Traitement du signal (feature 08), analytics (feature 09), import CSV (feature 11).

## Protocole
- Documenter dans `shared/protocol/` : `PROTOCOL.md` et `block.schema.json` (JSON Schema, `protocol_version: "1.0"`).
- Champs (voir spec §5) : `protocol_version`, `session_id`, `device_id`, `sequence_number`, `acquisition_timestamp` (début du bloc, horloge de l'appareil/client, UTC), `client_sent_at` (horloge du client au moment de l'envoi), `sample_rate`, `data_type`, `channels[]` (`channel_id`, `units`, `samples`), `calibration`, `metadata` (`source`, `connection_type`, `device_model`, `client_version`).
- Optionnels : `sample_timestamps`, `dropped_samples` (déclaré par le client).
- Le serveur ajoute `received_at`.
- Transport : JSON avec `Content-Encoding: gzip` accepté et recommandé. Format binaire compact (ex. en-tête JSON + échantillons `int16`/`float32`) **seulement si le spike montre que le JSON ne suffit pas** ; le définir alors dans `PROTOCOL.md` comme `Content-Type: application/x-emg-block`.
- Limites configurables : taille maximale d'un bloc, nombre maximal d'échantillons, nombre maximal de blocs par requête.

## Versions du protocole et des clients
- Paramètres : `PROTOCOL_MIN_SUPPORTED`, `PROTOCOL_DEPRECATED`, `PROTOCOL_CURRENT`.
- Le client envoie `X-Protocol-Version` et `X-Client-Version` (et `X-Client-Type`: `pc_agent`/`mobile`/`import`).
- Version inférieure au minimum : réponse **`426 Upgrade Required`** avec `{ "min_version": ..., "current_version": ..., "upgrade_url": ... }`.
- Version dépréciée mais acceptée : réponses avec en-têtes `Deprecation` et `Sunset`, et avertissement dans le corps.
- Les versions de protocole sont enregistrées sur chaque séance (`protocol_version`) pour la traçabilité.
- Documenter la politique de dépréciation dans `PROTOCOL.md` (durée minimale de support).

## Modèles
- `measurements.RawSegment` : `id`, `session`, `device`, `data_type`, `index`, `storage_path`, `n_blocks`, `size_bytes`, `sealed` (bool), `created_at`. Unique `(session, device, data_type, index)`.
- `measurements.DataBlock` : `id`, `session`, `device`, `sequence_number`, `data_type`, `sample_rate`, `acquired_at`, `received_at`, `n_samples`, `channel_ids`, `checksum`, `segment` (FK), `offset`, `length`, `encoding`, `status`. Unique `(session, device, data_type, sequence_number)`.
- `measurements.RawFile` : `session`, `device`, `data_type`, `storage_path`, `size_bytes`, `checksum`, `n_samples`, `sample_rate`, `format` (`npz`/`parquet`...), `finalized_at`.
- `measurements.IngestionStats` (ou champs agrégés sur `SessionDevice`) : blocs reçus, séquences manquantes, dernière séquence, échantillons déclarés perdus, dernier `received_at`.

## Stockage : performance
- **Pas un fichier par bloc.** Les blocs sont ajoutés à des *segments* (un segment par `(session, device, data_type)`, fermé tous les N blocs ou à une taille limite). La base garde offset et longueur de chaque bloc dans le segment.
- Créer `core/storage.py` avec une interface `RawStore` (`append`, `seal`, `open`, `delete`) : implémentation locale pour le moment, implémentation S3/MinIO plus tard (écriture d'un objet par segment scellé). C'est l'exception à « toujours `default_storage` » : les signaux passent par `RawStore`, les autres fichiers par `default_storage`.
- Écrire les échantillons sous forme binaire compacte (pas de JSON texte dans les segments).
- À la fin de séance (tâche Celery `finalize_session_data`) : consolidation par `(device, data_type)` en un fichier compact (`.npz` ou Parquet), mise à jour des `RawFile`, vérification des séquences manquantes, scellement des segments.
- Aucun échantillon en lignes PostgreSQL.

## Synchronisation d'horloge entre appareils
- Chaque réponse renvoie `server_time`. Le client peut estimer son décalage.
- Le serveur calcule une estimation robuste du décalage de chaque appareil : médiane de `received_at - client_sent_at` corrigée de la latence estimée ; le résultat est stocké dans `SessionDevice.clock_offset_ms` et mis à jour pendant et à la fin de la séance.
- Les annotations `sync_pulse` (même événement physique observé sur plusieurs appareils) permettent un recalage plus précis ; le recalage est calculé en feature 09, la donnée est conservée ici.
- EMG et IMU d'un **même** appareil partagent une horloge : ne rien corriger entre eux.

## Endpoints
- `POST /api/v1/sessions/{id}/data/` : un bloc ou un tableau de blocs (taille limitée). Réponse : `{ "received": [seq...], "duplicates": [seq...], "rejected": [{seq, reason}], "next_expected": n, "server_time": "...", "warnings": [] }`.
- `GET /api/v1/sessions/{id}/ingestion/` : statistiques et séquences manquantes par appareil.
- `GET /api/v1/sessions/{id}/raw-files/`
- `GET /api/v1/protocol/` (public) : version courante, minimum supporté, versions dépréciées, limites de taille.

## Tâches
- [ ] Écrire/ajuster `shared/protocol/PROTOCOL.md` + `block.schema.json` selon `SENSOR_FINDINGS.md`.
- [ ] Middleware ou dépendance DRF `ProtocolVersionCheck` : `426`, en-têtes de dépréciation, enregistrement de la version cliente.
- [ ] Serializer de validation de bloc (cohérence canaux ↔ `SessionChannel`, `sample_rate`, taille, types, appareil de la séance).
- [ ] `core/storage.py` : `RawStore` + implémentation locale (écriture append sûre, `fsync` configurable).
- [ ] Service `ingest_block(session, payload, user)` : statut `recording`, droit d'écriture (scope `sessions:write`), appareil, idempotence (même bloc → doublon accepté ; même séquence avec contenu différent → `409`), écriture segment, `DataBlock`, `touch_device`.
- [ ] Gestion de la concurrence (transaction + contrainte unique).
- [ ] Détection des trous de séquence en temps réel et à la finalisation.
- [ ] Estimation de `clock_offset_ms` par appareil.
- [ ] Tâche Celery `finalize_session_data` déclenchée par `on_session_completed` (feature 06).
- [ ] Throttling adapté (débit élevé autorisé mais borné), limite de taille du corps de requête.
- [ ] Séance non `recording` : `409` avec message clair (pas d'auto-démarrage).
- [ ] **Simulateur** `scripts/data_simulator/` (client Python utilisant uniquement l'API publique) :
  - EMG synthétique (bruit + bursts d'activation), IMU simulé avec répétitions, plusieurs canaux/appareils ;
  - options : durée, fréquence, nombre de canaux, taux de perte, doublons, blocs hors ordre, encodage gzip/binaire, version de protocole ;
  - s'authentifie par JWT, crée un setup minimal, crée/démarre/termine la séance.
- [ ] Cibles Makefile : `make simulate` (paramétrable : `make simulate DURATION=30 CHANNELS=4`) et `make loadtest` (plusieurs simulateurs en parallèle ; rapport de débit, latence p50/p95, erreurs).
- [ ] Mesurer et documenter dans `documentation/` la capacité atteinte (nombre de séances simultanées × canaux × Hz) sur la machine de dev ; fixer des seuils d'alerte pour la CI nocturne éventuelle.
- [ ] Documentation OpenAPI de l'endpoint avec exemples.

## Tests
- Bloc valide, doublon, doublon avec contenu différent, séquence manquante, ordre inversé, bloc trop gros, séance non `recording`, utilisateur non autorisé, canal inconnu.
- Version de protocole : `426` sous le minimum, en-têtes de dépréciation pour une version dépréciée.
- Gzip : requête compressée acceptée.
- Segments : relecture identique des échantillons après finalisation, `RawFile` créé, blocs retrouvés par offset.
- Deux appareils avec décalage d'horloge simulé : `clock_offset_ms` estimé dans la tolérance.
- Test de charge léger en CI (centaines de blocs, aucun doublon, aucun trou non déclaré).

## Critères d'acceptation
- `make simulate` envoie une séance complète, `complete`, puis les fichiers bruts consolidés sont lisibles.
- Aucun échantillon stocké en lignes PostgreSQL ; pas de fichier par bloc.
- `make loadtest` produit un rapport chiffré.
- `make check` passe.
