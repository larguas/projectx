Tu continues le développement du backend EMG (Django 5.x + DRF, géré par uv).
Les features 01 « Socle projet », 02 « Accounts », 03 « Sportifs, coachs,
équipes et partage de données », 04 « Devices » et 05 « Exercices, muscles,
entraînements » sont terminées et commitées ; le repo est propre, les
migrations des features 01–05 sont appliquées sur la base live et
`make check` passe.

Ta tâche : implémenter la feature 05b — Setups de placement et calibrations —
en suivant strictement backend/docs/05b-setups-calibration.md (app setups avec
SensorSetup versionné + SetupChannel, PlacementGuide, Calibration ; niveaux de
comparabilité `compare_setups` avec raisons réutilisables ; seed des guides de
placement).

Avant de coder, lis dans cet ordre :
1. backend/AGENT.md — conventions (UUID PKs, couche services, permissions
   deny-by-default, /api/v1/, format d'erreur unique, pagination par défaut)
2. backend/docs/00-index.md — les décisions d'architecture applicables ici
   (notamment n°3 : photos via default_storage ; n°8 : scopes centralisés
   dans core/scopes.py ; n°11 : setup versionné et figé ; n°12 :
   comparabilité calculée par le backend, avec raisons réutilisables)
3. backend/docs/05b-setups-calibration.md — périmètre, modèles, endpoints,
   règles métier, tâches

Points d'attention :
- Scopes : `setups:read` et `setups:write` sont DÉJÀ enregistrés dans
  core/scopes.py (comme `sessions:*`). La tâche du doc est en partie obsolète :
  vérifie ce qui existe, ne re-enregistre JAMAIS un scope déjà pris
  (`register_scope` lève ValueError sur un doublon), et utilise ces scopes via
  `core.access` — même pattern que devices (feature 04) et workouts (05).
- Muscle de la feature 05 : `SetupChannel.muscle` pointe vers
  `exercises.Muscle`, jamais `MuscleGroup` (point ouvert laissé par la feature
  05, à clôturer ici). Les codes stables du seed sont tes ancrages.
- Dépendances en avant (la feature 06 « séances » n'existe pas encore) :
  - `Calibration.source_session` sera ajouté comme vraie FK en feature 06 : ne
    crée PAS le champ maintenant ; l'applicabilité d'une calibration se calcule
    donc aujourd'hui sur « non invalidée, non expirée, rattachée au setup ».
    Documente ce point dans le compte rendu.
  - L'immutabilité « setup utilisé par une séance » doit être implémentée avec
    un point d'extension unique (méthode/marqueur que la feature 06 branchera
    sur les séances réelles), vérifié au niveau service ET modèle comme l'exige
    le doc. Décide de la mécanique, documente-la, et teste le mécanisme
    (pas les séances).
- Comparabilité : `compare_setups(a, b)` est la brique de crédibilité —
  niveaux identical/equivalent/approximate/different/unknown avec liste de
  `reasons` lisibles et stables ; tests exhaustifs sur toute la matrice.
- Versionnement : modification libre tant que le setup n'est pas utilisé ;
  ensuite `new-version` crée la version n+1 (lignée `parent`, unique
  `(athlete, name, version)`). `placement_unchanged: true` rattache les
  calibrations de l'ancienne version à la nouvelle ; sinon elles restent sur
  l'ancienne.
- Niveau `simple` : tous les champs détaillés optionnels ; si les champs
  détaillés sont vides, `detail_level` est forcé à `simple`.
- Photos (setups et guides) via `default_storage`, taille/type limités
  (décision n°3 : jamais d'`open()` direct).
- Audit : même principe que la feature 05 — les lectures de setups/calibrations
  d'un sportif par un coach/équipier sont tracées ; l'invalidation d'une
  calibration aussi. Décide et documente les événements.
- Seed : guides de placement pour quelques muscles courants (biceps brachii,
  vastus lateralis, …), référence citée (ex. SENIAM), texte court ; migration
  de données idempotente, même approche que la seed de la feature 05.

Règles de travail :
- Une session = une feature : uniquement la feature 05b, dans l'ordre des tâches.
- uv pour les dépendances (pas de pip/requirements.txt).
- Les commandes (`make ...`, `manage.py ...`) s'exécutent depuis backend/.
- Coche les tâches dans backend/docs/05b-setups-calibration.md au fur et à mesure.
- `make check` doit passer en fin de session (lint + format --check + check +
  schema-check + tests) ; ajoute des tests pour chaque endpoint, les services
  et les modèles.
- Une fois `make check` vert, applique les migrations sur la base live
  (`make migrate`) et vérifie avec `showmigrations`.
- Régénère le contrat : `make schema` puis committe backend/openapi.yaml
  (la CI fait un drift check).
- Petits commits Conventional Commits (`feat(setups): ...`, etc.).
- Termine par un court rapport : décisions, écarts, points ouverts.

Pièges connus des sessions précédentes (à éviter) :
- drf-spectacular : toute vue `GenericAPIView` sans `serializer_class` ni
  `queryset` en classe fait échouer la génération du schéma ; pour les vues
  custom (ex. compare), utilise `@extend_schema(...)` + `queryset =
  Model.objects.none()` (pattern de l'app teams).
- Le client de test Django n'accepte pas `format="json"` sur PATCH/PUT :
  `client.patch(url, data=json.dumps(payload), content_type="application/json",
  **auth_headers(user))`.
- Les données seedées sont toujours présentes dans les listes : dérive les
  ensembles attendus depuis la base (`Model.objects.filter(...)`), ne suppose
  jamais une baseline vide.

Spécificités de la machine (déjà vérifiées) :
- Docker nécessite sudo : `make up DOCKER="sudo docker"` / `make down
  DOCKER="sudo docker"` depuis backend/ (NOPASSWD configuré).
- L'infra est déjà en marche et healthy : emg-postgres + emg-redis sur
  127.0.0.1:5432/6379 (volumes persistants). Ne les recrée pas, n'utilise
  jamais `make down` sans y réfléchir (les données doivent survivre).
- NE PAS TOUCHER le conteneur `vela_db_prod` (postgres de prod sur
  192.168.1.50:5432).
- DB par défaut : postgres://emg:emg@localhost:5432/emg (défaut des settings,
  cohérent avec .env.example) ; les migrations des features 01–05 y sont
  déjà appliquées.
- Les fichiers de backend/docs/ sont en lecture seule localement (mode 444) :
  `chmod u+w`, éditer, puis restaurer le mode 444 (sinon diff de mode git).
