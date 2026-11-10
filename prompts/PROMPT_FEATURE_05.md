Tu continues le développement du backend EMG (Django 5.x + DRF, géré par uv).
Les features 01 « Socle projet », 02 « Accounts », 03 « Sportifs, coachs,
équipes et partage de données » et 04 « Devices » sont terminées et commitées ;
le repo est propre, les migrations des features 01–04 sont appliquées sur la
base live et `make check` passe.

Ta tâche : implémenter la feature 05 — Exercices, muscles, entraînements — en
suivant strictement backend/docs/05-exercises-workouts.md (apps exercises et
workouts : MuscleGroup, Muscle, Exercise avec rôles primaire/secondaire/
stabilisateur, Workout + WorkoutExercise ordonné ; bibliothèque globale et
personnelle ; seed des groupes, ~15 exercices et ~30 muscles).

Avant de coder, lis dans cet ordre :
1. backend/AGENT.md — conventions (UUID PKs, couche services, permissions
   deny-by-default, /api/v1/, format d'erreur unique, pagination par défaut)
2. backend/docs/00-index.md — les décisions d'architecture applicables ici
   (notamment n°8 : scopes centralisés dans core/scopes.py)
3. backend/docs/05-exercises-workouts.md — périmètre, modèles, endpoints,
   tâches ; la section « Ajouts (revue de roadmap) : niveau muscle » fait
   partie de cette feature

Points d'attention :
- Niveau muscle : `Muscle` + table intermédiaire `ExerciseMuscle` (role
  primary/secondary/stabilizer). Les features 05b (setups) et 06 (canaux de
  séance) référenceront `Muscle`, pas `MuscleGroup` — le modèle doit être
  stable et bien documenté.
- Visibilité global/personnel : exercices globaux lisibles par tous, écriture
  réservée au staff (définis et documente ce que « staff » signifie ici) ;
  exercices personnalisés visibles et modifiables par leur créateur seul. Les
  tests couvrent toute la matrice (global × personnel × rôles).
- Workouts liés à un sportif : réutilise `core.access` de la feature 03, ne
  reinvente rien. Un coach/équipier accède au plan d'un sportif uniquement
  avec un grant actif et non expiré (`sessions:read` / `sessions:write`, déjà
  enregistrés dans core/scopes.py), vérifié au niveau des sélecteurs — même
  pattern que devices. Documente tout choix de scope supplémentaire.
- Audit : même principe que les features 03/04 — les lectures de workouts
  d'un sportif par un coach/équipier sont tracées ; décide et documente.
- Seed (groupes musculaires, ~15 exercices courants, ~30 muscles rattachés à
  leurs groupes) : migration de données idempotente, même approche que la seed
  prototype_v1 de la feature 04 ; les exercices seedés sont reliés à leurs
  muscles et l'intégrité du seed est testée.
- `PUT /api/v1/workouts/{id}/exercises/` remplace la liste ordonnée : valide
  l'ordre (pas de doublon d'exercice), application atomique, tests dédiés.

Règles de travail :
- Une session = une feature : uniquement la feature 05, dans l'ordre des tâches.
- uv pour les dépendances (pas de pip/requirements.txt).
- Les commandes (`make ...`, `manage.py ...`) s'exécutent depuis backend/.
- Coche les tâches dans backend/docs/05-exercises-workouts.md au fur et à mesure.
- `make check` doit passer en fin de session (lint + format --check + check +
  schema-check + tests) ; ajoute des tests pour chaque endpoint, les services
  et les modèles.
- Une fois `make check` vert, applique les migrations sur la base live
  (`make migrate`) et vérifie avec `showmigrations`.
- Régénère le contrat : `make schema` puis committe backend/openapi.yaml
  (la CI fait un drift check).
- Petits commits Conventional Commits (`feat(exercises): ...`,
  `feat(workouts): ...`, etc.).
- Termine par un court rapport : décisions, écarts, points ouverts.

Spécificités de la machine (déjà vérifiées) :
- Docker nécessite sudo : `make up DOCKER="sudo docker"` / `make down
  DOCKER="sudo docker"` depuis backend/ (NOPASSWD configuré).
- L'infra est déjà en marche et healthy : emg-postgres + emg-redis sur
  127.0.0.1:5432/6379 (volumes persistants). Ne les recrée pas, n'utilise
  jamais `make down` sans y réfléchir (les données doivent survivre).
- NE PAS TOUCHER le conteneur `vela_db_prod` (postgres de prod sur
  192.168.1.50:5432).
- DB par défaut : postgres://emg:emg@localhost:5432/emg (défaut des settings,
  cohérent avec .env.example) ; les migrations des features 01–04 y sont
  déjà appliquées.
- Les fichiers de backend/docs/ sont en lecture seule localement (mode 444) :
  `chmod u+w`, éditer, puis restaurer le mode 444 (sinon diff de mode git).
