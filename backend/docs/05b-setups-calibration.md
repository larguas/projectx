# Feature 05b — Setups de placement et calibrations

## Objectif
Faire du placement des capteurs et de la calibration des données de premier niveau, pour que les comparaisons entre séances, entre muscles et entre côtés soient défendables (spec §8.5).

## Principes
1. **Déclaré** : l'utilisateur déclare où sont placés les canaux, mais ne ressaisit pas tout à chaque séance.
2. **Réutilisable** : un *setup* est défini une fois ; au démarrage d'une séance on propose « même placement que la dernière fois ? ».
3. **Versionné et figé** : un setup utilisé par une séance ne change jamais ; toute modification crée une nouvelle version. Les anciennes séances ne bougent pas.
4. **Comparabilité calculée par le backend** : le backend dit si deux séances sont comparables et pourquoi (caveats). Le frontend et l'IA ne devinent rien.
5. **Ne bloque pas, marque** : une séance sans setup est acceptée mais marquée « placement non déclaré » ; les comparaisons sont alors affaiblies ou désactivées.
6. **Deux niveaux** : `simple` (muscle + côté) pour les sportifs autonomes, `detailed` (position, distance inter-électrodes, préparation cutanée, photo) pour les coachs et contextes rigoureux.

## Périmètre
Setups, canaux de setup, guides de placement, calibrations (MVC, baseline repos), service de comparabilité.

## Hors périmètre
Calcul de la MVC à partir des signaux (feature 09), affichage des guides (frontend).

## Modèles
- `setups.SensorSetup` : `id`, `athlete`, `name`, `version` (int), `parent` (version précédente, nullable), `detail_level` (`simple`/`detailed`), `is_current`, `created_by`, `notes`, `created_at`. Unique `(athlete, name, version)`.
- `setups.SetupChannel` : `setup`, `device` (nullable), `channel_id` (canal du capteur), `muscle` (FK `exercises.Muscle`), `side` (`left`/`right`/`na`), `position_note`, `inter_electrode_distance_mm` (nullable), `skin_prep_done` (nullable bool), `photo` (fichier, nullable). Unique `(setup, device, channel_id)`.
- `setups.PlacementGuide` : `muscle`, `title`, `instructions`, `reference` (ex. recommandations SENIAM), `image` (nullable). Seed de quelques muscles courants.
- `setups.Calibration` : `id`, `athlete`, `setup` (version précise), `setup_channel`, `type` (`mvc`/`rest_baseline`), `values` (JSON : ex. `mvc_rms`, fenêtre, paramètres utilisés), `source_session` (nullable, FK vers la séance de calibration, ajoutée en feature 06), `algorithm_version`, `valid_from`, `valid_until` (nullable), `invalidated_at`, `invalidation_reason`.

## Règles métier
- Un setup est **modifiable librement tant qu'aucune séance ne l'utilise**. Ensuite : `POST /setups/{id}/new-version/` crée la version n+1.
- `new-version` accepte `placement_unchanged: true` quand l'utilisateur affirme que seul un détail non physique change (nom, notes). Dans ce cas les calibrations de la version précédente sont rattachées à la nouvelle. Sinon elles restent liées à l'ancienne version et ne s'appliquent pas à la nouvelle (une MVC n'a de sens que pour un placement donné).
- Une calibration est **applicable** si : non invalidée, non expirée, et rattachée au setup de la séance.
- Niveaux de comparabilité de deux setups (`compare_setups(a, b)`) :
  - `identical` : même version, ou même lignée avec `placement_unchanged`.
  - `equivalent` : deux setups `detailed`, mêmes muscle/côté par canal, mêmes distances inter-électrodes, même modèle d'appareil, lignées différentes.
  - `approximate` : au moins un setup `simple`, mais mêmes muscle/côté par canal.
  - `different` : correspondance muscle/côté différente.
  - `unknown` : un des deux setups est absent.
- Chaque résultat de comparaison renvoie une liste de `reasons` lisibles, réutilisées comme `caveats` par l'IA (feature 12).
- Comparaison gauche/droite : nécessite des setups `detailed`, même modèle d'appareil et calibrations MVC applicables pour les deux côtés ; sinon réserves explicites.

## Endpoints
- `GET/POST /api/v1/setups/`, `GET/PATCH/DELETE /api/v1/setups/{id}/` (DELETE refusé si utilisée)
- `POST /api/v1/setups/{id}/new-version/`
- `GET/PUT /api/v1/setups/{id}/channels/`
- `GET /api/v1/athletes/{id}/setups/current/`
- `GET /api/v1/setups/compare/?a={id}&b={id}` → `{level, reasons[]}`
- `GET /api/v1/muscles/{id}/placement-guide/`
- `GET /api/v1/athletes/{id}/calibrations/` (filtres : setup, type, applicable)
- `POST /api/v1/calibrations/{id}/invalidate/`

## Tâches
- [ ] Ajouter dans `core/scopes.py` les scopes `setups:read`, `setups:write`, `sessions:write` (compléter la liste de la feature 03) et les utiliser via `core.access`.
- [ ] App `setups`, modèles, contraintes, migrations.
- [ ] Services : `create_setup`, `new_version`, `set_channels`, `invalidate_calibration`, `applicable_calibrations(setup)`.
- [ ] Service `compare_setups` + tests exhaustifs (c'est la brique de crédibilité des analyses).
- [ ] Immutabilité : un setup utilisé par une séance refuse toute modification (vérifier au niveau service ET modèle).
- [ ] Mode `simple` : tous les champs détaillés optionnels, `detail_level` forcé à `simple` si les champs détaillés sont vides.
- [ ] Seed : guides de placement pour quelques muscles (biceps brachii, vastus lateralis, ...), référence citée, texte court.
- [ ] Fichiers photo via `default_storage`, taille/type limités.
- [ ] Admin Django.

## Tests
- Versionnement : modification libre avant usage, nouvelle version après usage, lignée `parent`.
- `placement_unchanged` vs placement modifié : devenir des calibrations.
- Matrice de `compare_setups` (identical / equivalent / approximate / different / unknown).
- Permissions : sportif, coach avec/sans scope, autre utilisateur.
- Suppression refusée si utilisée.

## Critères d'acceptation
- Un sportif peut déclarer un setup simple en moins de deux appels API ; un coach peut déclarer un setup détaillé.
- `GET /setups/compare/` retourne un niveau et des raisons stables.
- `make check` passe.
