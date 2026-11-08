# Feature 03 — Sportifs, coachs, équipes et partage de données

## Objectif
Modèle d'acteurs et système d'autorisation. C'est la fondation de toutes les permissions du projet : à soigner.

## Périmètre
- Profils sportif et coach rattachés à un utilisateur.
- Équipes/structures avec membres.
- Autorisations de partage explicites, révocables.
- Classe de permission et sélecteurs réutilisables par toutes les autres apps.

## Hors périmètre
Facturation, notifications d'invitation (simple statut en base pour l'instant).

## Règles métier (spec §6.4)
- Un utilisateur individuel autonome peut avoir un `AthleteProfile` sans coach ni équipe.
- Il peut ensuite rejoindre une équipe ou autoriser un coach sans nouveau compte.
- Un coach gère plusieurs sportifs ; un sportif peut avoir plusieurs coachs/équipes.
- Données privées par défaut. Un coach ne voit les données d'un sportif qu'avec une autorisation active.
- Une équipe n'accède qu'à ce qui lui est explicitement accordé.
- Les droits sont modifiables et révocables.

## Modèles
- `athletes.AthleteProfile` : `user` (OneToOne), `date_of_birth`, `sex` (optionnel), `height_cm`, `weight_kg`, `dominant_side`, `sport`, `notes`.
- `coaches.CoachProfile` : `user` (OneToOne), `organization_name`, `bio`.
- `teams.Team` : `name`, `owner` (user).
- `teams.TeamMembership` : `team`, `user`, `role` (`owner`/`coach`/`athlete`), `status`, unique `(team, user)`.
- `access` (dans `teams` ou une app `sharing` : à choisir et documenter) `AccessGrant` : `athlete`, `grantee_type` (`coach`/`team`), `grantee_coach` / `grantee_team` (un seul rempli), `scopes` (liste : `sessions:read`, `analytics:read`, `reports:read`, `devices:read`...), `status` (`pending`/`active`/`revoked`/`expired`), `granted_at`, `revoked_at`, `expires_at`.
- Les invitations sont des `AccessGrant` en `pending` ou des memberships en `pending`.

## Endpoints (indicatifs)
- `GET/POST /api/v1/athletes/`, `GET/PATCH /api/v1/athletes/{id}/`
- `GET/POST /api/v1/coaches/`, `GET/PATCH /api/v1/coaches/{id}/`
- `GET/POST /api/v1/teams/`, `GET/PATCH/DELETE /api/v1/teams/{id}/`
- `GET/POST /api/v1/teams/{id}/members/`, `DELETE .../members/{user_id}/`
- `GET/POST /api/v1/access-grants/` (côté sportif : voir/accorder), `POST /api/v1/access-grants/{id}/accept/`, `POST .../revoke/`
- `GET /api/v1/athletes/` côté coach : retourne uniquement les sportifs avec grant actif.

## Tâches
- [x] Créer les apps `athletes`, `coaches`, `teams` (+ `AccessGrant`).
- [x] Contraintes DB (unicité, un seul type de grantee rempli via `CheckConstraint`).
- [x] **Module central** `core/access.py` (ou `apps/teams/access.py`) :
  - `can_access_athlete(user, athlete, scope) -> bool`
  - `visible_athletes(user, scope) -> QuerySet`
  - Tests exhaustifs : cette API sera utilisée par toutes les features suivantes.
- [x] Permission DRF `HasAthleteScope(scope)` réutilisable.
- [x] Services : `grant_access`, `accept_grant`, `revoke_grant`, `add_member`, `remove_member`.
- [x] Un grant révoqué ou expiré n'ouvre plus aucun accès (vérifié dans les sélecteurs, pas seulement en vue).
- [x] Création automatique du profil sportif à la demande (endpoint dédié ou service), pas à l'inscription.
- [x] Filtres et pagination sur les listes.
- [x] Admin Django.

## Tests (prioritaires)
- Matrice d'accès : propriétaire, coach avec grant actif, coach sans grant, coach avec grant révoqué/expiré, membre d'équipe avec/sans grant, admin.
- Scopes : grant `sessions:read` n'ouvre pas `reports:read`.
- Un utilisateur ne peut pas créer un grant pour le compte d'un autre sportif.
- Révocation immédiate.
- Un utilisateur cumulant rôles sportif + coach.

## Ajouts (revue de roadmap)

### Audit minimal dès cette feature
Les autorisations de partage sont sensibles : on les trace dès leur création.
- [x] Créer l'app `audit` avec le modèle `AuditEvent` (`actor`, `action`, `target_type`, `target_id`, `athlete` nullable, `ip`, `user_agent`, `metadata` JSON, `created_at`), table en insertion seule.
- [x] Service `audit.services.record_event(actor, action, target, athlete=None, metadata=None, request=None)`.
- [x] L'appeler dans `grant_access`, `accept_grant`, `revoke_grant`, `add_member`, `remove_member` et à chaque lecture de données d'un sportif par un coach (au minimum la liste et le détail des sportifs).
- [x] Tests : un événement par action listée, aucun champ sensible dans `metadata`.
- Les endpoints de consultation, l'export et la politique de conservation restent en feature 14.

### Scopes centralisés
- [x] Remplir `core/scopes.py` : `sessions:read`, `sessions:write`, `analytics:read`, `reports:read`, `devices:read`, `setups:read`, `setups:write`. Validation d'un grant contre cette liste.
- [x] Un grant peut combiner plusieurs scopes ; les scopes inconnus sont refusés.

### Vérification d'email
- [x] Création/acceptation d'un grant refusées si `email_verified_at` est vide (permission `IsEmailVerified`, feature 02).

## Critères d'acceptation
- `can_access_athlete` et `visible_athletes` documentés (docstring + exemple) et couverts à 100 %.
- Aucune liste n'expose de sportif non autorisé.
- `make check` passe.
