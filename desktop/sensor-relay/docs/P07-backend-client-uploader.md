# P07 — Client API, envoi des blocs et gestion de la connexion

## Objectif
Envoyer les blocs de l'outbox au backend de façon fiable, idempotente et reprenable, et exposer un client typé pour tout le reste de l'API.

## Pré-requis
P05 (outbox), P06 (auth). Backend feature 07 pour la **phase B** ; en phase A on utilise le faux backend.

## Périmètre
Client HTTP, vérification de version, uploader, Connection Manager, extension du faux backend, tests d'intégration réels.

## Hors périmètre
Logique de séance (P08).

## Modules (`transport/`)
- `client.py` : `BackendClient` (httpx async, timeouts, en-têtes de version, `Content-Encoding: gzip` sur l'envoi de blocs, identifiant de requête). Méthodes typées : protocole, `users/me`, athlètes, appareils et modèles d'appareils, setups, séances (création, `start`, `complete`, `cancel`, canaux, appareils, annotations), envoi de données, statistiques d'ingestion. Erreurs typées : `ProtocolTooOld` (426), `AuthRequired` (401), `Forbidden` (403), `Conflict` (409), `ValidationFailed` (400), `RateLimited` (429 + `Retry-After`), `ServerError` (5xx), `NetworkError`.
- `protocol_check.py` : au démarrage `GET /api/v1/protocol/` ; version sous le minimum → blocage avec message et `upgrade_url` ; version dépréciée ou en-têtes `Deprecation`/`Sunset` → avertissement (événement).
- `uploader.py` : boucle qui prend des lots dans l'outbox (limites de taille et de nombre issues de `/protocol/`) → `POST /sessions/{id}/data/` → interprète la réponse : `received` et `duplicates` → acquittés ; `rejected` → **permanent** (marqué `rejected`, conservé pour diagnostic, alerte) ou **transitoire** (réessai) ; `409` contenu différent → quarantaine + alerte ; `next_expected` sert à la resynchronisation. `client_sent_at` posé à chaque tentative.
- `connection.py` : Connection Manager — état en ligne/hors ligne déduit des résultats de requêtes + sonde légère (`/api/v1/health/`), backoff exponentiel avec gigue, respect de `Retry-After`, pause en `reauth_required`, reprise automatique ; estimation du décalage d'horloge via `server_time` (avertissement au-delà d'un seuil).
- **Rétention** : les blocs acquittés sont conservés jusqu'à la vérification de fin de séance (`GET /sessions/{id}/ingestion/` sans séquence manquante non déclarée), puis `purge_acked`. Si le serveur déclare des trous que le client possède encore → renvoi.

## Tâches
- [ ] Client typé et erreurs.
- [ ] Vérification de version au démarrage.
- [ ] Uploader (lots, accusés, rejets, quarantaine, resynchronisation par `next_expected`).
- [ ] Connection Manager (état, backoff, sonde, décalage d'horloge).
- [ ] Rétention et purge après vérification.
- [ ] Étendre `tests/fake_backend/` : endpoint de données **idempotent**, `426`, `429`, `5xx` aléatoires, délais, coupures, rejets.
- [ ] Test de contrat : requêtes et réponses du client validées contre `backend/openapi.yaml` (`openapi-core` ou équivalent).
- [ ] **Phase B** (backend 07 prêt) : tests `integration` contre le vrai backend ; vérifier le point « `client_sent_at` ignoré dans l'idempotence » (voir index) et le signaler s'il échoue.

## Tests
- Envoi nominal, doublons, rejet permanent vs transitoire, `409`, `426`, `401` avec refresh, `429` avec `Retry-After`.
- Coupure réseau de 2 min en plein envoi : rien de perdu, reprise ordonnée, pas de doublon côté faux backend.
- Redémarrage du processus pendant des envois en cours.
- Débit soutenu : 8 canaux × 1 kHz pendant 10 min sans accumulation de retard.
- Rétention : purge uniquement après vérification.

## Critères d'acceptation
- Avec le capteur simulé et un faux backend défaillant, 100 % des blocs arrivent une seule fois, dans l'ordre par flux.
- `make check` passe (et `make integration` en phase B).
