Tu continues le développement de la plateforme EMG (backend Django 5.x + DRF,
géré par uv). Les features 01 « Socle projet », 02 « Accounts », 03 « Sportifs,
coachs, équipes et partage de données », 04 « Devices », 05 « Exercices,
muscles, entraînements », 05b « Setups de placement et calibrations » et
06 « Séances » sont terminées et commitées ; la feature 06b « Spike capteur
réel » est en phase 1 (mini-projet uv `scripts/sensor_spike/` avec scripts de
détection/lecture/analyse, squelette des constats, protocole v1.0 d'hypothèse
et échantillon synthétique — le tout commité). Le repo est propre et
`make check` passe.

Ta tâche : implémenter la feature 07 — Ingestion (protocole d'acquisition,
réception des blocs idempotente, stockage brut par segments, synchronisation
d'horloge, simulateur et test de charge) — en suivant strictement
backend/docs/07-ingestion.md. Attention : c'est une feature critique du MVP ;
le protocole y est figé sur la base des constats du spike 06b.

Première étape obligatoire (avant tout code) : le protocole
(`shared/protocol/PROTOCOL.md` + `block.schema.json`) a été construit DEPUIS
l'hypothèse de départ — au spike, le capteur n'était pas connecté ni
détectable et les 11 questions de
`documentation/acquisition-protocol/SENSOR_FINDINGS.md` sont « inconnu ».
Vérifie donc d'abord si le capteur est détectable (depuis
`scripts/sensor_spike/` : `uv run python detect_device.py`).
- S'il l'est : fais la checklist « à faire avec le capteur » de
  SENSOR_FINDINGS.md, remplis les constats (jamais de valeur inventée) et
  aligne PROTOCOL.md / block.schema.json AVANT de coder — en cas d'écart,
  **le spike prime** sur 07-ingestion.md ; note les écarts dans ce dernier.
- S'il ne l'est pas : demande explicitement à l'utilisateur s'il attend ou
  s'il accepte de coder sur l'hypothèse de départ ; si oui, documente-le comme
  point ouvert (compte rendu + 07-ingestion.md).

Avant de coder, lis dans cet ordre :
1. backend/AGENT.md — conventions générales du repo
2. backend/docs/00-index.md — décisions applicables ici (notamment n°3 :
   stockage des signaux par segments via `core.storage.RawStore`, jamais de
   lignes PostgreSQL ; n°4 : un seul format de blocs versionné, le backend ne
   dépend jamais du modèle de capteur ; n°5 : idempotence par `(session,
   device, data_type, sequence_number)` ; n°9 : WebSocket pour les événements
   seulement, jamais les échantillons bruts ; n°13 : versions de
   protocole/client vérifiées — `426` sous le minimum, en-têtes
   `Deprecation`/`Sunset`)
3. shared/protocol/PROTOCOL.md + shared/protocol/block.schema.json — le
   contrat à implémenter (champs marqués « confirmé / à valider »)
4. documentation/acquisition-protocol/SENSOR_FINDINGS.md — constats et
   checklist capteur
5. backend/docs/07-ingestion.md — périmètre, protocole, modèles, endpoints,
   tâches, tests

Points d'attention :
- App `measurements` (nouvelle) : `RawSegment`, `DataBlock`, `RawFile`,
  `IngestionStats` comme dans le doc ; contraintes uniques `(session, device,
  data_type, index)` et `(session, device, data_type, sequence_number)`. Le
  label `measurements` est libre (seul `sessions` entre en conflit avec
  django.contrib — décision n°2). Aucun échantillon stocké en lignes
  PostgreSQL.
- `core/storage.py` EXISTE déjà : ABC `RawStore` (`write_segment`,
  `read_segment`, `exists`) + stub `LocalRawStore` (NotImplementedError « sera
  implémenté en feature 07 »). Le doc évoque `append`/`seal`/`open`/`delete` :
  réconcilie les deux interfaces (sémantique du doc : ajout à un segment,
  scellement, relecture), garde l'identité d'idempotence documentée dans
  l'ABC, et implémente le stockage local (écriture append sûre, `fsync`
  configurable). Échantillons en binaire compact dans les segments (pas de
  JSON texte). S3/MinIO plus tard : ne fais que l'interface.
- Idempotence et concurrence : transaction + contrainte unique ; même bloc
  renvoyé → accusé positif sans doublon ; même séquence avec contenu différent
  → `409`. Teste la concurrence.
- Versions du protocole : settings `PROTOCOL_MIN_SUPPORTED`,
  `PROTOCOL_DEPRECATED`, `PROTOCOL_CURRENT` ; en-têtes `X-Protocol-Version`,
  `X-Client-Version`, `X-Client-Type` (`pc_agent`/`mobile`/`import`) ; sous le
  minimum → `426 Upgrade Required` avec `{min_version, current_version,
  upgrade_url}` ; version dépréciée acceptée → en-têtes `Deprecation` +
  `Sunset` et avertissement dans le corps. `Session.protocol_version` existe
  déjà (PositiveIntegerField, default 1) : décide comment mapper « 1.0 » et
  documente. Politique de dépréciation à documenter dans PROTOCOL.md.
- Horloge : chaque réponse renvoie `server_time` ; estimation robuste du
  décalage par appareil (médiane de `received_at - client_sent_at` corrigée de
  la latence) stockée dans `SessionDevice.clock_offset_ms` (champ existe,
  null) pendant et à la fin de séance. Ne corrige JAMAIS entre EMG et IMU du
  même appareil. Les annotations `sync_pulse` sont conservées ; le recalage
  lui-même est en feature 09.
- Finalisation : tâche Celery `finalize_session_data` branchée sur le hook
  `on_session_completed` (actuellement vide dans apps/sessions/services.py,
  son docstring l'attend) : consolidation par `(device, data_type)` en un
  fichier compact (.npz ou Parquet), mise à jour des `RawFile`, vérification
  des séquences manquantes, scellement des segments. Celery existe déjà
  (config/celery.py) ; utilise la base `RequestIDTask` de core/tasks.py pour
  la propagation du request_id. Un échec du hook ne doit pas casser l'état de
  la séance (log + continue).
- Autorisation : réutilise `core.access` — écriture des blocs : scope
  `sessions:write`, lecture des stats/fichiers bruts : `sessions:read` ; les
  deux scopes sont déjà enregistrés dans core/scopes.py, ne re-enregistre
  rien. Séance non `recording` → `409` avec message clair (pas
  d'auto-démarrage).
- Bornes configurables : taille max d'un bloc, nombre max d'échantillons,
  nombre max de blocs par requête ; throttling adapté (débit élevé autorisé
  mais borné), limite de taille du corps de requête.
- Simulateur `scripts/data_simulator/` : client Python utilisant UNIQUEMENT
  l'API publique (JWT, création d'un setup minimal, création/démarrage/fin de
  séance) ; EMG synthétique (bruit + bursts d'activation), IMU avec
  répétitions, plusieurs canaux/appareils ; options : durée, fréquence,
  nombre de canaux, taux de perte, doublons, blocs hors ordre, encodage
  gzip/binaire, version de protocole. Aucune dépendance HTTP dans le backend
  (ni httpx ni requests) : décide entre mini-projet uv indépendant (pattern de
  `scripts/sensor_spike/`) et ajout d'`httpx` au groupe dev — documente le
  choix.
- Makefile : remplace les cibles placeholders `simulate`/`loadtest`
  (actuellement « Implémenté en feature 07 ») par des vraies, paramétrables
  (`make simulate DURATION=30 CHANNELS=4`) ; `make loadtest` lance plusieurs
  simulateurs en parallèle et produit un rapport chiffré (débit, latence
  p50/p95, erreurs).
- Mesure et documentation : capacité atteinte (séances simultanées × canaux ×
  Hz) sur la machine de dev, écrite dans `documentation/`, avec seuils
  d'alerte pour une CI nocturne éventuelle.
- Échantillon existant : `backend/tests/data/sample_emg_imu.npz` (synthétique
  déterministe, seed 20261109, généré par
  `scripts/sensor_spike/make_sample_data.py`) est la référence de format pour
  les features 08/09 ; si un enregistrement réel devient disponible,
  remplace-le par un extrait anonymisé et documente.

Règles de travail :
- Une session = une feature : uniquement la feature 07 (sauf la première
  étape spike ci-dessus), dans l'ordre des tâches du doc.
- uv pour les dépendances (pas de pip/requirements.txt).
- Les commandes (`make ...`, `manage.py ...`) s'exécutent depuis backend/.
- Coche les tâches dans backend/docs/07-ingestion.md au fur et à mesure.
- `make check` doit passer en fin de session (lint + format --check + check +
  schema-check + tests) ; ajoute des tests pour chaque endpoint, les services,
  le stockage et les versions de protocole (liste de tests du doc).
- Une fois `make check` vert, applique les migrations sur la base live
  (`make migrate`) et vérifie avec `showmigrations`.
- Régénère le contrat : `make schema` puis committe backend/openapi.yaml (la
  CI fait un drift check) ; documente l'endpoint d'ingestion avec des exemples.
- Petits commits Conventional Commits (`feat(ingestion): ...`, etc.).
- Termine par un court rapport : décisions, écarts par rapport au protocole
  supposé, points ouverts.

Pièges connus des sessions précédentes (à éviter) :
- drf-spectacular : toute vue `GenericAPIView` sans `serializer_class` ni
  `queryset` en classe fait échouer la génération du schéma ; pour les vues
  custom (ex. ingestion, stats), utilise `@extend_schema(...)` +
  `queryset = Model.objects.none()` (pattern de l'app teams).
- Le client de test Django n'accepte pas `format="json"` sur PATCH/PUT :
  `client.patch(url, data=json.dumps(payload), content_type="application/json",
  **auth_headers(user))`.
- Les données seedées sont toujours présentes dans les listes : dérive les
  ensembles attendus depuis la base (`Model.objects.filter(...)`), ne suppose
  jamais une baseline vide.
- `make check` inclut le format : applique `ruff format` avant de valider
  (l'outil de write peut produire des fichiers non formatés).

Spécificités de la machine (déjà vérifiées) :
- Docker nécessite sudo : `make up DOCKER="sudo docker"` / `make down
  DOCKER="sudo docker"` depuis backend/ (NOPASSWD configuré).
- L'infra est déjà en marche et healthy : emg-postgres + emg-redis sur
  127.0.0.1:5432/6379 (volumes persistants). Ne les recrée pas, n'utilise
  jamais `make down` sans y réfléchir (les données doivent survivre).
- NE PAS TOUCHER le conteneur `vela_db_prod` (postgres de prod sur
  192.168.1.50:5432).
- DB par défaut : postgres://emg:emg@localhost:5432/emg (défaut des settings,
  cohérent avec .env.example) ; les migrations des features 01–06 y sont déjà
  appliquées.
- Les fichiers de backend/docs/ sont en lecture seule localement (mode 444) :
  `chmod u+w`, éditer, puis restaurer le mode 444 (sinon diff de mode git).
