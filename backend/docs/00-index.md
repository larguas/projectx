# Backend EMG — Découpage en features

Chaque feature = une session opencode. Ordre à respecter (dépendances indiquées).

| # | Fichier | Feature | Dépend de | Taille |
|---|---|---|---|---|
| 01 | `01-bootstrap.md` | Socle projet : uv, Makefile, Django, Docker, CI, Sentry, contrat OpenAPI | — | M |
| 02 | `02-accounts.md` | Utilisateurs, JWT, vérification email, autorisation du module PC | 01 | L |
| 03 | `03-profiles-access.md` | Sportifs, coachs, équipes, partage de données, audit minimal | 02 | L |
| 04 | `04-devices.md` | Capteurs | 02, 03 | S |
| 05 | `05-exercises-workouts.md` | Exercices, muscles, entraînements | 03 | S |
| 05b | `05b-setups-calibration.md` | Setups de placement, calibrations, comparabilité | 03, 04, 05 | M |
| 06 | `06-sessions.md` | Cycle de vie des séances, annotations, multi-appareils | 03, 04, 05, 05b | M |
| 06b | `06b-hardware-spike.md` | **Spike capteur réel** (en partie manuel) | 01 | S |
| 07 | `07-ingestion.md` | Protocole, réception des blocs, stockage par segments, simulateur, charge | 06, 06b | L |
| 08 | `08-signal-processing.md` | Moteur de traitement EMG/IMU (Python pur) | 01 (indépendant) | L |
| 09 | `09-analytics.md` | Pipeline Celery, indicateurs, calibration MVC, comparabilité, retraitement | 05b, 07, 08 | L |
| 10 | `10-realtime-notifications.md` | Channels/WebSocket, notifications | 06, 09 | M |
| 11 | `11-import-reports.md` | Import CSV, rapports/exports | 07, 09 | M |
| 12 | `12-ai-engine.md` | Analyses avancées, ML, assistant structuré | 09 | L |
| 13 | `13-subscriptions.md` | Abonnements et droits | 02 | M |
| 14 | `14-audit-security-prod.md` | Audit complet, RGPD, durcissement, déploiement | toutes | M |

Parallélisme possible :
- 06b (spike) peut se faire dès la 01, en parallèle de 02 à 06. Il **doit** être fini avant 07.
- 08 (moteur de signal) peut se faire à tout moment après la 01, idéalement après le spike pour disposer de données réelles.
- 13 peut se faire après la 02.

**MVP technique** (capteur → résultats) : 01 à 09, avec le spike. Les features 10 à 14 viennent ensuite. Prévoir large sur les durées : le hardware et la calibration sont les principales sources d'imprévus.

## Décisions d'architecture (à respecter dans toutes les features)

1. **Monolithe Django modulaire**, pas de microservices.
2. **Label d'app `sessions`** : conflit avec `django.contrib.sessions`. Le dossier peut s'appeler `apps/sessions/` mais l'`AppConfig.label` doit être `training_sessions` (et `name = "apps.sessions"`). Alternative : `apps/training_sessions/`. Ne jamais utiliser le label `sessions`.
3. **Stockage des signaux bruts** : jamais en lignes PostgreSQL, jamais un fichier par bloc. Les signaux passent par l'abstraction `core.storage.RawStore` (segments, local au départ, S3/MinIO plus tard). Les autres fichiers (photos, rapports) passent par `default_storage`. PostgreSQL ne garde que métadonnées, chemins et offsets.
4. **Format de blocs** : un seul format versionné (`protocol_version`) pour mobile, PC et import. Le backend ne dépend jamais du modèle de capteur. Le protocole est validé sur le vrai capteur (spike 06b) avant d'être figé.
5. **Idempotence** : un bloc est identifié par `(session, device, data_type, sequence_number)` ; renvoyer un bloc déjà reçu donne un accusé positif sans doublon.
6. **Traçabilité** : chaque résultat d'analyse stocke version d'algorithme, paramètres, `sample_rate`, modèle capteur, calibration, setup, version de protocole, date.
7. **Authentification des clients PC/mobile** : JWT par utilisateur ; le module PC s'autorise par un flux « device code » (approbation dans le navigateur). Aucune clé secrète globale partagée.
8. **Permissions** : données privées par défaut ; accès coach/équipe uniquement via une autorisation explicite, à scopes, révocable (feature 03). La liste des scopes est centralisée dans `core/scopes.py`.
9. **Temps réel** : WebSocket uniquement pour les événements, jamais pour les échantillons bruts.
10. **Moteur de signal** indépendant de Django (réutilisable en CSV, Celery, notebooks).
11. **Setup de placement versionné** : une séance référence un setup figé ; toute modification crée une nouvelle version. Une séance sans setup est acceptée mais marquée.
12. **Comparabilité calculée côté backend** : le backend dit si deux séances sont comparables (setup + calibration) et fournit les raisons ; l'IA et le frontend reprennent ces caveats, ils ne les devinent pas.
13. **Évolution des clients installés** : versions de protocole/client vérifiées par le backend (`426` sous le minimum, en-têtes `Deprecation`/`Sunset` pour les versions dépréciées).
14. **Contrat d'API** : le schéma OpenAPI est versionné dans le repo ; la CI détecte toute dérive non committée. Le client TypeScript du frontend est généré depuis ce schéma.
15. **Observabilité dès le départ** : logs structurés et Sentry configurés en feature 01.

## Format de chaque fichier feature

Objectif · Périmètre · Hors périmètre · Modèles · Endpoints · Tâches (cases à cocher) · Tests · Critères d'acceptation.

## Prompt type pour opencode

```text
Lis AGENTS.md puis 00-index.md (section Décisions d'architecture) puis NN-xxx.md.
Implémente uniquement cette feature, dans l'ordre des tâches.
Coche les tâches terminées dans le fichier. Termine quand `make check` passe
et donne un court compte rendu (décisions, écarts, points ouverts).
```
