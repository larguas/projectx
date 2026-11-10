# P06 — Authentification : flux « device code » et trousseau

## Objectif
Connecter le module au compte de l'utilisateur sans jamais saisir son mot de passe dans le module ni embarquer de secret global (spec §13.2).

## Pré-requis backend
Feature 02 : `POST /api/v1/auth/device/code/`, `POST /api/v1/auth/device/token/`, `POST /api/v1/auth/refresh/`, `POST /api/v1/auth/logout/`, `GET /api/v1/users/me/`. L'utilisateur approuve le code dans l'application web (`/auth/device/approve/`).

## Périmètre
Flux de connexion, stockage des jetons, rafraîchissement, intégration httpx, commandes CLI, faux backend d'authentification.

## Hors périmètre
Appels métier (P07), UI de connexion (P12).

## Tâches
- [ ] `authentication/device_flow.py` : demande de code, affichage du `user_code`, ouverture de `verification_uri` (`platform.open_url`), polling selon `interval`, gestion de `authorization_pending`, `slow_down`, `access_denied`, `expired_token`, annulation, délai maximal.
- [ ] `authentication/token_store.py` : stockage via `keyring` (Trousseau macOS), clé par serveur (`api_base_url`) ; en l'absence de trousseau : erreur claire (option `--insecure-file-store` réservée au développement, fichier 0600, avertissement visible).
- [ ] `authentication/session.py` : `AuthSession` — rafraîchit avant expiration, **rotation** du refresh (nouvel jeton persisté immédiatement et de façon atomique), verrou « un seul rafraîchissement à la fois », sur `401` : un rafraîchissement puis un nouvel essai, sinon état `reauth_required` (événement, pas de boucle infinie).
- [ ] `httpx.Auth` partagé par tout le client (P07).
- [ ] CLI : `emg-agent login` (affiche le code et l'URL), `logout` (blacklist côté serveur + suppression locale), `whoami`.
- [ ] **Faux backend** `tests/fake_backend/` (FastAPI) : endpoints d'authentification, avec injection de pannes (révocation, expiration). Sera étendu en P07/P08 ; commande `make fake-backend`.
- [ ] Jamais de jeton ni de `device_code` dans les logs (test).

## Tests
- Flux complet contre le faux backend ; `slow_down` (intervalle augmenté), refus, code expiré, annulation.
- Rotation : 10 requêtes parallèles avec jeton expiré → un seul rafraîchissement.
- Client révoqué : passage en `reauth_required`, plus de nouvelles tentatives.
- Trousseau simulé en mémoire ; test manuel documenté avec le vrai Trousseau macOS (marqueur `macos`).
- Masquage des secrets dans les logs.

## Critères d'acceptation
- `emg-agent login` → approbation dans le navigateur → `emg-agent whoami` affiche l'utilisateur, sans mot de passe saisi.
- Après redémarrage, la session est restaurée depuis le trousseau.
- `make check` passe.
