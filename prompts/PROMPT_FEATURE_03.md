Tu continues le développement du backend EMG (Django 5.x + DRF, géré par uv).
Les features 01 « Socle projet » et 02 « Accounts » sont terminées et commitées ;
le repo est propre et `make check` passe.

Ta tâche : implémenter la feature 03 — Sportifs, coachs, équipes et partage de
données — en suivant strictement backend/docs/03-profiles-access.md (apps
athletes/coaches/teams avec AthleteProfile, CoachProfile, Team, TeamMembership,
AccessGrant ; module central d'accès ; permission DRF réutilisable ; services
grant/membres ; app audit minimale ; scopes centralisés).

Avant de coder, lis dans cet ordre :
1. backend/AGENT.md — conventions (UUID PKs, couche services, permissions
   deny-by-default, /api/v1/, format d'erreur unique, pagination par défaut)
2. backend/docs/00-index.md — les 15 décisions d'architecture applicables ici
3. backend/docs/03-profiles-access.md — périmètre, modèles, endpoints, tâches

Points d'attention (c'est la fondation de toutes les permissions du projet) :
- Le module central d'accès (`can_access_athlete`, `visible_athletes`) sera
  utilisé par toutes les features suivantes : docstrings + exemples, tests
  exhaustifs sur toute la matrice d'accès du doc.
- Un grant révoqué ou expiré n'ouvre plus aucun accès : vérifié dans les
  sélecteurs, pas seulement en vue.
- Scopes centralisés (`core/scopes.py`) ; un grant combine plusieurs scopes,
  les inconnus sont refusés.
- Création/acceptation d'un grant refusées si l'email n'est pas vérifié
  (permission `IsEmailVerified`, déjà fournie par la feature 02).
- Audit minimal dès maintenant : app `audit` + `AuditEvent` en insertion seule,
  appelé dans chaque mutation de droits et à chaque lecture de données sportif
  par un coach.

Règles de travail :
- Une session = une feature : uniquement la feature 03, dans l'ordre des tâches.
- uv pour les dépendances (pas de pip/requirements.txt).
- Coche les tâches dans backend/docs/03-profiles-access.md au fur et à mesure.
- `make check` doit passer en fin de session (lint + format --check + check +
  schema-check + tests) ; ajoute des tests pour chaque endpoint, le module
  d'accès et les modèles.
- Régénère le contrat : `make schema` puis committe backend/openapi.yaml
  (la CI fait un drift check).
- Petits commits Conventional Commits (`feat(athletes): ...`, etc.).
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
  cohérent avec .env.example).
- Les fichiers de backend/docs/ sont en lecture seule localement (mode 444) :
  `chmod u+w`, éditer, puis restaurer le mode 444 (sinon diff de mode git).
