# Feature 09 — Analytics : pipeline asynchrone et résultats traçables

## Objectif
Relier ingestion et moteur de signal : après une séance, lancer le traitement en tâche Celery, stocker indicateurs et paramètres, les exposer par API. Termine le MVP technique.

## Périmètre
Tâches Celery, modèles de résultats, API de lecture, retraitement.

## Hors périmètre
ML, assistant IA (feature 12), rapports (feature 11).

## Modèles
- `analytics.AnalysisRun` : `id`, `session`, `status` (`pending`/`running`/`succeeded`/`failed`), `algorithm_version`, `params` (JSON), `input_summary` (sample_rate, device_model, calibration, protocol_version), `started_at`, `finished_at`, `error`, `triggered_by` (`auto`/`user`).
- `analytics.AnalyticsResult` : `run`, `channel_id` (nullable pour résultats globaux), `metric` (ex. `rms`, `median_frequency`, `repetition_count`), `scope` (`session`/`window`/`repetition`), `value` (float, nullable), `result` (JSON pour séries/structures), `window_start`/`window_end` (nullable).
- Option : séries temporelles volumineuses (enveloppe, fenêtres) stockées en fichier `processed/{session_id}/{run_id}/...` + référence en base.
- `analytics.ProcessedFile` : `run`, `kind` (`filtered`, `envelope`, ...), `storage_path`.

## Endpoints
- `GET /api/v1/sessions/{id}/analytics/` : dernier run réussi (ou `?run=<id>`) avec indicateurs.
- `GET /api/v1/sessions/{id}/analytics/runs/`
- `POST /api/v1/sessions/{id}/analytics/runs/` : relancer avec des paramètres (retraitement).
- `GET /api/v1/sessions/{id}/signals/` : séries filtrées/enveloppe décimées pour la visualisation (`?channel=&start=&end=&max_points=`).
- Compatibilité avec la route du spec : `GET /api/v1/analytics/{id}/` → un `AnalysisRun`.

## Tâches
- [ ] App `analytics` (et adaptateur `signal_processing` côté Django : lecture RawFile → `Signal`, appel `engine.pipeline`).
- [ ] Tâche `run_analysis(run_id)` : idempotente, retries sur erreurs transitoires, statut mis à jour, erreurs enregistrées.
- [ ] Branchement sur `on_session_completed` : la finalisation des fichiers bruts (feature 07) déclenche l'analyse (chaînage Celery).
- [ ] Persistance : paramètres, version algo, sample_rate, modèle capteur, calibration, version protocole, date (voir `00-index.md`, décision 6).
- [ ] Un retraitement ne supprime pas les anciens runs.
- [ ] Endpoint de signaux décimés (min/max par bucket) pour que le frontend n'ait pas à recevoir des millions de points.
- [ ] Permissions via `core.access` (scope `analytics:read`).
- [ ] Configuration Celery : queues séparées (`default`, `processing`), timeouts, `acks_late`.
- [ ] En tests, `CELERY_TASK_ALWAYS_EAGER = True`.

## Tests
- Pipeline complet de bout en bout dans un test d'intégration : créer séance, envoyer des blocs simulés, `complete`, vérifier `AnalysisRun` réussi et métriques.
- Échec du moteur ⇒ run `failed` avec erreur, séance inchangée.
- Retraitement avec params différents ⇒ nouveau run, ancien conservé.
- Permissions.
- Décimation (taille de sortie, valeurs min/max conservées).

## Ajouts (revue de roadmap)

### Calibration MVC / baseline
- [ ] À la fin d'une séance `session_type = calibration` (hook `on_session_completed`), créer une `setups.Calibration` : MVC = valeur maximale du RMS glissant (fenêtre configurable, par défaut 500 ms) par canal ; baseline repos = niveau moyen du signal au repos. Paramètres et version d'algorithme enregistrés.
- [ ] La nouvelle calibration remplace l'ancienne pour le même `(setup, canal, type)` : l'ancienne reçoit `valid_until`, reste consultable.
- [ ] Les valeurs normalisées (% MVC) ne sont produites que si une calibration applicable existe (voir 05b). Sinon : seules les valeurs brutes, avec un caveat `no_applicable_calibration`.
- [ ] Séance de calibration de mauvaise qualité (signal saturé, effort trop faible) : calibration non créée, run marqué `failed` avec message explicite.

### Comparabilité entre séances
- [ ] Endpoint `GET /api/v1/athletes/{id}/comparability/?a={session}&b={session}` renvoyant : niveau de comparabilité des setups (`compare_setups`), statut des calibrations applicables de chaque séance, même modèle d'appareil ou non, liste de `caveats`.
- [ ] Les endpoints de comparaison et de progression (feature 12) utilisent ce service ; aucune comparaison sans passer par lui.
- [ ] Les résultats d'une séance sans setup déclaré portent le caveat `setup_not_declared`.

### Annotations et plusieurs appareils
- [ ] Le pipeline utilise les annotations `rep_start`/`rep_end` manuelles comme référence prioritaire sur la détection automatique de répétitions.
- [ ] Alignement temporel des signaux de plusieurs appareils en appliquant `clock_offset_ms`, affiné par les annotations `sync_pulse` quand elles existent. L'alignement appliqué est enregistré dans `input_summary`.

### Retraitement en masse
- [ ] Endpoint admin `POST /api/v1/admin/reprocess/` et commande `make reprocess ARGS="--algorithm-version-below 1.2.0"` : sélection par version d'algorithme, période, athlète, type de séance.
- [ ] Traitement par lots (Celery), limitation du débit, reprise après interruption, rapport (succès/échecs).
- [ ] Les anciens runs sont conservés ; le « dernier run » affiché peut être épinglé (`is_pinned`) pour ne pas changer des résultats déjà communiqués sans action explicite.

### Tests supplémentaires
- Séance de calibration → calibration créée, ancienne invalidée par `valid_until`, valeurs en % MVC présentes seulement si la calibration est applicable.
- Calibration refusée sur signal saturé.
- Endpoint de comparabilité sur les cinq niveaux de `compare_setups`.
- Alignement de deux appareils avec décalage connu.
- Reprocess en masse : sélection correcte, reprise après échec, run épinglé non remplacé.

## Critères d'acceptation
- MVP technique validé : signal simulé → API → stockage → analyse → résultats via API.
- `make check` passe.
