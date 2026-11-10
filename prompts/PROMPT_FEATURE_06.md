Tu continues le développement du backend EMG (Django 5.x + DRF, géré par uv).
Les features 01 « Socle projet », 02 « Accounts », 03 « Sportifs, coachs,
équipes et partage de données », 04 « Devices », 05 « Exercices, muscles,
entraînements » et 05b « Setups de placement et calibrations » sont terminées
et commitées ; le repo est propre, les migrations des features 01–05b sont
appliquées sur la base live et `make check` passe.

Ta tâche : implémenter la feature 06 — Séances (sessions d'acquisition) — en
suivant strictement backend/docs/06-sessions.md (app sessions avec Session,
SessionDevice, SessionChannel, SessionAnnotation ; machine à états
created/recording/completed/cancelled/failed ; multi-appareils ; canaux figés
depuis le setup ; séances de calibration ; annotations/marqueurs).

Avant de coder, lis dans cet ordre :
1. backend/AGENT.md — conventions (UUID PKs, couche services, permissions
   deny-by-default, /api/v1/, format d'erreur unique, pagination par défaut)
2. backend/docs/00-index.md — les décisions d'architecture applicables ici
   (notamment n°2 : label d'app ; n°6 : traçabilité ; n°8 : scopes
   centralisés dans core/scopes.py ; n°11 : setup versionné et figé)
3. backend/docs/05b-setups-calibration.md + apps/setups/models.py — le point
   d'extension que cette feature doit brancher (docstring de l'app setups,
   propriétés ``SensorSetup.is_used`` / ``assert_editable``, champ
   ``used_at``)
4. backend/docs/06-sessions.md — périmètre, modèles, machine à états, règles
   métier, endpoints, tâches

Points d'attention :
- Nom d'app (décision n°2) : le label `sessions` est interdit (conflit avec
  `django.contrib.sessions`). Dossier `apps/sessions/` avec
  `AppConfig.name = "apps.sessions"` et `label = "training_sessions"`. Toutes
  les FK depuis d'autres apps référencent `"training_sessions.Session"`, jamais
  `"sessions.Session"`.
- Brancher le point d'extension de la feature 05b (documenté dans
  apps/setups/models.py) : à la première référence d'un setup par une séance,
  poser `used_at` par mise à jour en base ciblée
  (`SensorSetup.objects.filter(id=...).update(used_at=...)`) — JAMAIS via
  `save()` (qui déclencherait `assert_editable`). Élargir la propriété
  ``is_used`` pour vérifier aussi les séances réelles. Tests : setup figé
  après création d'une séance qui l'utilise, modification refusée, nouvelle
  version possible.
- Clôturer l'autre point ouvert de 05b : ajouter `Calibration.source_session`
  (FK nullable vers la séance de calibration) par migration — le docstring du
  modèle Calibration l'attend explicitement. Ne PAS créer de Calibration ici
  (c'est la feature 09, via le hook).
- Machine à états : transitions uniquement created→recording→completed,
  created→cancelled, recording→cancelled|failed ; toute autre transition =
  `409`. Services dédiés (`start_session`, `complete_session`,
  `cancel_session`) avec verrouillage `select_for_update` ; jamais de
  changement de statut depuis un serializer. Tests sur chaque transition
  valide/invalide + concurrence basique.
- Setup à la création : si fourni, copier les `SetupChannel` en `SessionChannel`
  (muscle/côté figés) et marquer le setup utilisé ; sinon `setup_declared=false`
  avec avertissement `setup_not_declared` dans la réponse ET le détail. Une
  séance `calibration` exige un `setup` ET un `calibration_type`.
- Multi-appareils : plus de FK `device` unique — `SessionDevice` (role
  primary/secondary) et `device` obligatoire sur chaque canal ; les canaux de
  chaque appareil sont distincts. À la création, vérifier que les appareils
  sont accessibles au créateur ET que les canaux sont compatibles avec les
  capacités du modèle (`DeviceModel.capabilities`, JSON).
- Autorisation : réutilise `core.access` (pattern devices/workouts) — lecture :
  sportif propriétaire + coachs/équipes avec grant actif scope `sessions:read`
  ; création/modification : scope `sessions:write` sur le sportif. Scopes déjà
  enregistrés dans core/scopes.py, ne re-enregistre rien.
- Annotations : CRUD, validation du `kind`, tri par `offset_ms` ; autorisées
  pendant `recording` et après `completed` (corrections), jamais sur
  `cancelled`.
- Audit : même principe que les features 05/05b — lectures de séances d'un
  sportif par un coach/équipier tracées ; décide aussi si les transitions
  d'état le sont, documente.
- Hook `on_session_completed(session)` : vide ici, branché en features 07 et
  09 ; il reçoit `session_type` (la feature 09 créera la calibration).
- Endpoint `suggested-setup` : setup de la dernière séance du sportif
  (proposition « même placement que la dernière fois ? »).

Règles de travail :
- Une session = une feature : uniquement la feature 06, dans l'ordre des tâches.
- uv pour les dépendances (pas de pip/requirements.txt).
- Les commandes (`make ...`, `manage.py ...`) s'exécutent depuis backend/.
- Coche les tâches dans backend/docs/06-sessions.md au fur et à mesure.
- `make check` doit passer en fin de session (lint + format --check + check +
  schema-check + tests) ; ajoute des tests pour chaque endpoint, les services
  et les modèles.
- Une fois `make check` vert, applique les migrations sur la base live
  (`make migrate`) et vérifie avec `showmigrations`.
- Régénère le contrat : `make schema` puis committe backend/openapi.yaml
  (la CI fait un drift check).
- Petits commits Conventional Commits (`feat(sessions): ...`, etc.).
- Termine par un court rapport : décisions, écarts, points ouverts.

Pièges connus des sessions précédentes (à éviter) :
- drf-spectacular : toute vue `GenericAPIView` sans `serializer_class` ni
  `queryset` en classe fait échouer la génération du schéma ; pour les vues
  custom (ex. start/complete/cancel, suggested-setup), utilise
  `@extend_schema(...)` + `queryset = Model.objects.none()` (pattern de l'app
  teams). Les actions d'URL imbriquées (channels/devices/annotations) ont
  fonctionné en 05b avec des routes imbriquées — reprends ce pattern.
- Le client de test Django n'accepte pas `format="json"` sur PATCH/PUT :
  `client.patch(url, data=json.dumps(payload), content_type="application/json",
  **auth_headers(user))`.
- Les données seedées (exercices, guides) sont toujours présentes dans les
  listes : dérive les ensembles attendus depuis la base
  (`Model.objects.filter(...)`), ne suppose jamais une baseline vide.
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
  cohérent avec .env.example) ; les migrations des features 01–05b y sont
  déjà appliquées.
- Les fichiers de backend/docs/ sont en lecture seule localement (mode 444) :
  `chmod u+w`, éditer, puis restaurer le mode 444 (sinon diff de mode git).
