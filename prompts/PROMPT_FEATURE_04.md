Tu continues le développement du backend EMG (Django 5.x + DRF, géré par uv).
Les features 01 « Socle projet », 02 « Accounts » et 03 « Sportifs, coachs,
équipes et partage de données » sont terminées et commitées ; le repo est
propre, les migrations des features 01–03 sont appliquées sur la base live et
`make check` passe.

Ta tâche : implémenter la feature 04 — Devices : capteurs — en suivant
strictement backend/docs/04-devices.md (app devices avec DeviceModel et Device,
catalogue de modèles géré en admin, CRUD des appareils avec propriétaire,
désactivation logique, service touch_device, seed prototype_v1).

Avant de coder, lis dans cet ordre :
1. backend/AGENT.md — conventions (UUID PKs, couche services, permissions
   deny-by-default, /api/v1/, format d'erreur unique, pagination par défaut)
2. backend/docs/00-index.md — les décisions d'architecture applicables ici
   (notamment n°4 : le backend ne dépend jamais du modèle de capteur)
3. backend/docs/04-devices.md — périmètre, modèles, endpoints, tâches

Points d'attention :
- Autorisation : réutilise `core.access` de la feature 03, ne reinvente rien.
  Un utilisateur voit ses appareils ; un coach voit ceux de ses sportifs
  uniquement avec le scope `devices:read` (déjà enregistré dans
  core/scopes.py) — grant actif et non expiré, vérifié au niveau des
  sélecteurs. C'est le premier consommateur réel du module central : les tests
  doivent couvrir coach avec/sans scope, grant révoqué et expiré.
- Indépendance du fabricant (décision d'archi n°4) : le catalogue DeviceModel
  porte protocol_version, connection_types et capabilities ; aucune logique ne
  doit brancher sur un modèle de capteur particulier.
- `serial_number` : unicité `(device_model, serial_number)` en base + message
  d'erreur clair (code stable, même pattern services/vues que la feature 03).
- DELETE = désactivation logique (`status → retired`), jamais de suppression
  physique (les séances et l'ingestion feront référence aux appareils).
- `touch_device(device)` : service qui met à jour `last_seen_at`, appelé par
  l'ingestion (feature 07) — rester dans la couche services, testé.
- Seed du catalogue : un modèle `prototype_v1` via migration de données ou
  fixture — décide et documente le choix.
- Audit : la feature 03 trace les lectures de données sportif par un coach ;
  décide et documente si la lecture d'appareils par un coach suit le même
  principe (ou justifie l'écart).

Règles de travail :
- Une session = une feature : uniquement la feature 04, dans l'ordre des tâches.
- uv pour les dépendances (pas de pip/requirements.txt).
- Coche les tâches dans backend/docs/04-devices.md au fur et à mesure.
- `make check` doit passer en fin de session (lint + format --check + check +
  schema-check + tests) ; ajoute des tests pour chaque endpoint, les services
  et les modèles.
- Une fois `make check` vert, applique les migrations sur la base live
  (`make migrate`) et vérifie avec `showmigrations`.
- Régénère le contrat : `make schema` puis committe backend/openapi.yaml
  (la CI fait un drift check).
- Petits commits Conventional Commits (`feat(devices): ...`, etc.).
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
  cohérent avec .env.example) ; les migrations des features 01–03 y sont
  déjà appliquées.
- Les fichiers de backend/docs/ sont en lecture seule localement (mode 444) :
  `chmod u+w`, éditer, puis restaurer le mode 444 (sinon diff de mode git).
