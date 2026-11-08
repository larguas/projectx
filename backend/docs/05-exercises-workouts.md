# Feature 05 — Exercices et entraînements

## Objectif
Bibliothèque d'exercices et notion d'entraînement (workout) regroupant des séances.

## Périmètre
- Exercices (globaux + personnalisés), groupes musculaires.
- Workouts : plan d'entraînement composé d'exercices.

## Hors périmètre
Séances d'acquisition (feature 06), analyses.

## Modèles
- `exercises.MuscleGroup` : `code` (unique), `name`, `body_region`.
- `exercises.Exercise` : `name`, `description`, `muscle_groups` (M2M avec rôle primaire/secondaire via table intermédiaire), `movement_type`, `default_parameters` (JSON : reps cibles, tempo...), `is_global` (bool), `created_by` (nullable), `is_archived`.
- `workouts.Workout` : `name`, `owner`, `athlete` (nullable : plan pour un sportif), `notes`.
- `workouts.WorkoutExercise` : `workout`, `exercise`, `order`, `target_sets`, `target_reps`, `parameters` (JSON).

## Endpoints
- `GET /api/v1/muscle-groups/`
- `GET/POST /api/v1/exercises/`, `GET/PATCH/DELETE /api/v1/exercises/{id}/`
- `GET/POST /api/v1/workouts/`, `GET/PATCH/DELETE /api/v1/workouts/{id}/`
- `PUT /api/v1/workouts/{id}/exercises/` (remplacement de la liste ordonnée)

## Tâches
- [ ] Apps `exercises` et `workouts`.
- [ ] Exercices globaux : lecture pour tous, écriture réservée au staff. Exercices personnalisés : propriétaire seulement.
- [ ] Seed : groupes musculaires et ~15 exercices courants (migration de données ou commande `seed_exercises`).
- [ ] Filtres : groupe musculaire, recherche texte, global/personnel.
- [ ] Workouts liés à un sportif : respecter `core.access` (scope `sessions:read`/écriture selon besoin, à documenter).
- [ ] Validation de l'ordre dans `WorkoutExercise`.

## Tests
- Visibilité global/personnel, droits d'écriture, filtres, remplacement ordonné d'un workout, accès coach.

## Ajouts (revue de roadmap) : niveau « muscle »

Les groupes musculaires sont trop grossiers pour le placement des capteurs et l'analyse ; il faut un niveau muscle précis.

- `exercises.Muscle` : `code` (unique), `name`, `latin_name` (nullable), `muscle_group` (FK `MuscleGroup`), `region`, `side_relevant` (bool : le muscle a une version gauche/droite).
- `exercises.ExerciseMuscle` : `exercise`, `muscle`, `role` (`primary`/`secondary`/`stabilizer`).
- Endpoint : `GET /api/v1/muscles/` (filtre par groupe, recherche texte).
- [ ] Modèles, migrations, admin.
- [ ] Seed : ~30 muscles courants (biceps brachii, triceps brachii, vastus lateralis, vastus medialis, rectus femoris, biceps femoris, gluteus maximus, gastrocnemius, tibialis anterior, erector spinae, trapezius, deltoid, pectoralis major, latissimus dorsi, rectus abdominis...) rattachés à leurs groupes ; exercices seedés reliés à leurs muscles.
- [ ] Les features 05b (setups) et 06 (canaux de séance) référencent `Muscle`, pas `MuscleGroup`.
- Tests : filtres, rôle d'un muscle dans un exercice, intégrité des références du seed.

## Critères d'acceptation
- Bibliothèque seedée consultable ; création d'un workout avec exercices ordonnés.
- `make check` passe.
