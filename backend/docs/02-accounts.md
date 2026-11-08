# Feature 02 — Accounts : utilisateurs et authentification

## Objectif
Création de compte, connexion JWT, profil utilisateur. Base d'authentification pour le web, le mobile et le module PC.

## Périmètre
- Modèle utilisateur personnalisé (email comme identifiant).
- Inscription, connexion, refresh, déconnexion, mot de passe oublié.
- Endpoint profil.

## Hors périmètre
Profils sportif/coach, partage de données (feature 03), abonnements.

## Modèles
- `accounts.User` (AbstractBaseUser + PermissionsMixin) : `id` UUID, `email` (unique, normalisé en minuscules), `first_name`, `last_name`, `is_active`, `is_staff`, `date_joined`, `email_verified_at` (nullable), `locale`, `timezone`.
- Pas de champ `role` unique : un utilisateur peut cumuler des rôles (individuel, sportif, coach). Les rôles seront portés par les profils en feature 03. Seul `is_staff`/superuser représente l'administrateur de la plateforme.

## Endpoints
| Méthode | Route | Rôle |
|---|---|---|
| POST | `/api/v1/auth/register/` | Inscription |
| POST | `/api/v1/auth/login/` | Connexion (access + refresh) |
| POST | `/api/v1/auth/refresh/` | Renouvellement |
| POST | `/api/v1/auth/logout/` | Blacklist du refresh token |
| POST | `/api/v1/auth/password/forgot/` | Demande de réinitialisation |
| POST | `/api/v1/auth/password/reset/` | Réinitialisation avec token |
| POST | `/api/v1/auth/password/change/` | Changement (authentifié) |
| GET/PATCH | `/api/v1/users/me/` | Profil |

## Tâches
- [ ] Créer `apps/accounts`, déclarer `AUTH_USER_MODEL` **avant** la première migration.
- [ ] `UserManager` (create_user, create_superuser).
- [ ] simplejwt : durée access courte, refresh avec rotation + blacklist (`rest_framework_simplejwt.token_blacklist`).
- [ ] Serializers et services (`register_user`, `change_password`, ...).
- [ ] Validation des mots de passe (validateurs Django), politique documentée.
- [ ] Mots de passe oubliés : token signé à durée limitée, email via backend console en dev (`EMAIL_BACKEND`).
- [ ] Throttling sur login et reset (DRF throttle scopes).
- [ ] Permission par défaut globale `IsAuthenticated`, endpoints publics déclarés explicitement.
- [ ] Admin Django pour `User`.
- [ ] Factories de test (`UserFactory`) réutilisables par les autres apps dans `core/testing` ou `apps/accounts/tests/factories.py`.

## Tests
- Inscription (succès, email dupliqué insensible à la casse, mot de passe faible).
- Login, refresh, logout (token blacklisté inutilisable).
- Accès à `users/me/` avec et sans token.
- Reset de mot de passe (token valide, expiré, réutilisé).
- Throttling.

## Ajouts (revue de roadmap)

### Vérification d'email
- Champ `email_verified_at` déjà prévu sur `User`.
- Endpoints : `POST /api/v1/auth/email/verify/` (token signé à durée limitée), `POST /api/v1/auth/email/resend/` (throttlé).
- Politique : un utilisateur non vérifié peut se connecter et utiliser son espace personnel, mais **ne peut pas accepter ni créer d'autorisation de partage** (feature 03) ni demander d'export. À appliquer via une permission `IsEmailVerified` réutilisable.
- Tests : token valide/expiré/réutilisé, politique appliquée.

### Autorisation du module PC (flux « device code »)
Un logiciel de bureau ne doit pas demander le mot de passe ni embarquer de secret global.
- Modèle `DeviceAuthorization` : `device_code_hash`, `user_code` (court, saisissable), `status` (`pending`/`approved`/`denied`/`expired`/`consumed`), `user` (nullable), `client_type` (`pc_agent`/`mobile`), `client_name`, `client_version`, `expires_at`, `last_polled_at`.
- Endpoints :
  - `POST /api/v1/auth/device/code/` (public, throttlé) → `device_code`, `user_code`, `verification_uri`, `expires_in`, `interval`.
  - `POST /api/v1/auth/device/token/` (public) : le client interroge avec `device_code` ; réponses `authorization_pending`, `slow_down`, `access_denied`, `expired_token` ou une paire JWT.
  - `POST /api/v1/auth/device/approve/` (utilisateur connecté, depuis l'application web) : saisie du `user_code`, approbation ou refus.
- Les JWT émis par ce flux portent un claim `client_type` et peuvent être listés et révoqués : `GET /api/v1/auth/clients/`, `DELETE /api/v1/auth/clients/{id}/`.
- Les codes sont à usage unique, courte durée, stockés hachés, avec limitation de tentatives.
- Tests : flux complet, code expiré, code réutilisé, polling trop rapide, révocation d'un client, tentative de force brute.

### Critères d'acceptation supplémentaires
- Un client de test peut obtenir un JWT via le flux device code sans jamais manipuler le mot de passe de l'utilisateur.
- Un client révoqué ne peut plus renouveler son jeton.

## Critères d'acceptation
- Parcours inscription → login → `users/me/` → logout OK via Swagger.
- Aucun endpoint hors auth/health accessible sans token.
- `make check` passe.
