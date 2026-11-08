"""Tests de l'API entraînements : ``GET/POST /api/v1/workouts/``.

La liste est filtrée par le sélecteur (``apps.workouts.selectors.visible_workouts``) :
un utilisateur y voit ses plans + les plans RATTACHÉS à ses sportifs couverts
par un grant actif portant le scope ``sessions:read`` (réutilisation des scopes
existants — décision documentée dans ``workouts/selectors.py``). Un plan sans
athlète n'est accessible que par son propriétaire. La création porte sur
l'utilisateur connecté ; rattacher un plan à un sportif exige l'accès en
écriture (``sessions:write``) à ce sportif.

Audit : la liste émet ``workout.listed`` uniquement quand au moins un plan
non propriétaire est visible (comportement identique aux capteurs).
"""

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers, post_json
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.audit.models import AuditEvent
from apps.coaches.tests.factories import CoachProfileFactory
from apps.teams.models import AccessGrant
from apps.teams.tests.factories import (
    AccessGrantFactory,
    TeamAccessGrantFactory,
    TeamFactory,
    TeamMembershipFactory,
)
from apps.workouts.tests.factories import WorkoutFactory

SCOPE_READ = "sessions:read"
SCOPE_WRITE = "sessions:write"


class TestWorkoutList:
    def test_anonymous_refused(self, client):
        assert client.get("/api/v1/workouts/").status_code == 401

    def test_owner_sees_own_workouts_only(self, client):
        owner = UserFactory()
        own_a = WorkoutFactory(owner=owner)
        own_b = WorkoutFactory(owner=owner)
        athlete_profile = AthleteProfileFactory()
        WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)  # tiers : invisible
        response = client.get("/api/v1/workouts/", **auth_headers(owner))
        assert response.status_code == 200
        assert {w["id"] for w in response.json()["results"]} == {str(own_a.pk), str(own_b.pk)}

    def test_coach_sees_only_plans_with_sessions_read_grant(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        granted_athlete = AthleteProfileFactory()
        other_athlete = AthleteProfileFactory()
        granted_plan = WorkoutFactory(owner=granted_athlete.user, athlete=granted_athlete)
        WorkoutFactory(owner=other_athlete.user, athlete=other_athlete)  # sans grant : invisible
        AccessGrantFactory(athlete=granted_athlete, grantee_coach=coach, scopes=[SCOPE_READ])
        response = client.get("/api/v1/workouts/", **auth_headers(coach_user))
        assert response.status_code == 200
        assert [w["id"] for w in response.json()["results"]] == [str(granted_plan.pk)]

    def test_grant_without_sessions_read_scope_excluded(self, client):
        """Un grant ``devices:read`` n'ouvre pas la lecture des plans."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=["devices:read"])
        response = client.get("/api/v1/workouts/", **auth_headers(coach_user))
        assert response.json()["results"] == []

    def test_revoked_grant_excluded(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)
        AccessGrantFactory(
            athlete=athlete_profile, grantee_coach=coach, status=AccessGrant.Status.REVOKED
        )
        response = client.get("/api/v1/workouts/", **auth_headers(coach_user))
        assert response.json()["results"] == []

    def test_expired_grant_excluded(self, client):
        from datetime import timedelta

        from django.utils import timezone

        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)
        AccessGrantFactory(
            athlete=athlete_profile,
            grantee_coach=coach,
            expires_at=timezone.now() - timedelta(days=1),
        )
        response = client.get("/api/v1/workouts/", **auth_headers(coach_user))
        assert response.json()["results"] == []

    def test_team_member_sees_plans_with_team_grant(self, client):
        """Un membre actif de l'équipe bénéficiaire d'un grant y accède."""
        team = TeamFactory()
        member_user = UserFactory()
        TeamMembershipFactory(team=team, user=member_user)
        athlete_profile = AthleteProfileFactory()
        plan = WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)
        TeamAccessGrantFactory(athlete=athlete_profile, grantee_team=team, scopes=[SCOPE_READ])
        response = client.get("/api/v1/workouts/", **auth_headers(member_user))
        assert [w["id"] for w in response.json()["results"]] == [str(plan.pk)]

    def test_orphan_plan_not_adoptable_by_coach(self, client):
        """Un plan SANS athlète reste invisible même avec un grant actif."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        orphan = WorkoutFactory(owner=UserFactory())  # athlete=None, d'un tiers
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = client.get("/api/v1/workouts/", **auth_headers(coach_user))
        results = response.json()["results"]
        assert str(orphan.pk) not in {w["id"] for w in results}
        assert results == []  # le coach n'a aucun autre plan visible

    def test_superuser_sees_everything(self, client):
        superuser = UserFactory(is_superuser=True)
        athlete_profile = AthleteProfileFactory()
        plans = [
            WorkoutFactory(),
            WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile),
        ]
        response = client.get("/api/v1/workouts/", **auth_headers(superuser))
        assert {w["id"] for w in response.json()["results"]} == {str(p.pk) for p in plans}

    def test_list_audit_emitted_for_coach_with_granted_plans(self, client):
        """``workout.listed`` émis quand un plan non propriétaire est visible."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        athlete_profile = AthleteProfileFactory()
        WorkoutFactory(owner=athlete_profile.user, athlete=athlete_profile)
        AccessGrantFactory(athlete=athlete_profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = client.get("/api/v1/workouts/", **auth_headers(coach_user))
        assert response.status_code == 200
        event = AuditEvent.objects.get(action="workout.listed")
        assert event.actor_id == coach_user.pk
        assert event.target_id is None
        assert event.metadata == {"granted_workouts": 1}

    def test_list_audit_not_emitted_for_owner_only(self, client):
        owner = UserFactory()
        WorkoutFactory(owner=owner)
        response = client.get("/api/v1/workouts/", **auth_headers(owner))
        assert response.status_code == 200
        assert not AuditEvent.objects.filter(action="workout.listed").exists()


class TestWorkoutCreate:
    def test_anonymous_cannot_create(self, client):
        assert post_json(client, "/api/v1/workouts/", {"name": "Nope"}).status_code == 401

    def test_user_creates_personal_plan_without_athlete(self, client):
        user = UserFactory()
        response = post_json(client, "/api/v1/workouts/", {"name": "Mon plan"}, **auth_headers(user))
        assert response.status_code == 201, response.data
        body = response.json()
        assert "owner" not in body  # identité du propriétaire jamais exposée
        assert "email" not in body
        assert body["athlete"] is None
        assert body["editable"] is True

    def test_owner_can_attach_own_athlete_profile(self, client):
        user = UserFactory()
        profile = AthleteProfileFactory(user=user)
        response = post_json(
            client,
            "/api/v1/workouts/",
            {"name": "Plan sportif", "athlete": str(profile.pk)},
            **auth_headers(user),
        )
        assert response.status_code == 201, response.data
        athlete_ref = response.json()["athlete"]
        assert athlete_ref["id"] == str(profile.pk)
        assert athlete_ref["sport"] == profile.sport

    def test_coach_attaches_plan_with_write_grant(self, client):
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_WRITE])
        response = post_json(
            client,
            "/api/v1/workouts/",
            {"name": "Plan coach", "athlete": str(profile.pk)},
            **auth_headers(coach_user),
        )
        assert response.status_code == 201, response.data

    def test_coach_cannot_attach_athlete_with_read_only_grant(self, client):
        """``sessions:read`` n'ouvre pas l'attachement (écriture requise)."""
        coach_user = UserFactory()
        coach = CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        AccessGrantFactory(athlete=profile, grantee_coach=coach, scopes=[SCOPE_READ])
        response = post_json(
            client,
            "/api/v1/workouts/",
            {"name": "Injection ?", "athlete": str(profile.pk)},
            **auth_headers(coach_user),
        )
        assert response.status_code == 403

    def test_coach_cannot_attach_athlete_without_grant(self, client):
        coach_user = UserFactory()
        CoachProfileFactory(user=coach_user)
        profile = AthleteProfileFactory()
        response = post_json(
            client,
            "/api/v1/workouts/",
            {"name": "Injection ?", "athlete": str(profile.pk)},
            **auth_headers(coach_user),
        )
        assert response.status_code == 403

    def test_missing_name_refused(self, client):
        user = UserFactory()
        response = post_json(client, "/api/v1/workouts/", {}, **auth_headers(user))
        assert response.status_code == 400
