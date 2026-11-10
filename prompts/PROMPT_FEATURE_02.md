Tu continues le développement du backend EMG (Django 5.x + DRF, géré par uv).
La feature 01 « Socle projet » est terminée et commitée ; le repo est propre et
`make check` passe.

Ta tâche : implémenter la feature 02 — Accounts : utilisateurs et
authentification JWT — en suivant strictement backend/docs/02-accounts.md
(modèle User custom email-based, register/login/refresh/logout, forgot/reset/
change password, GET/PATCH /api/v1/users/me/).

Avant de coder, lis dans cet ordre :
1. backend/AGENT.md — conventions (UUID PKs, couche services, permissions
   deny-by-default, /api/v1/, format d'erreur unique, pagination par défaut)
2. backend/docs/00-index.md — les 15 décisions d'architecture applicables ici
3. backend/docs/02-accounts.md — périmètre, modèles, endpoints, tâches

Règles de travail :
- Une session = une feature : uniquement la feature 02, dans l'ordre des tâches.
- uv pour les dépendances (pas de pip/requirements.txt).
- Coche les tâches dans backend/docs/02-accounts.md au fur et à mesure.
- `make check` doit passer en fin de session (lint + format + check +
  schema-check + tests) ; ajoute des tests pour chaque endpoint et le modèle.
- Régénère le contrat : `make schema` puis committe backend/openapi.yaml
  (la CI fait un drift check).
- Petits commits Conventional Commits.
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
