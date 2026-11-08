"""Tests du cycle de vie des grants : acceptation et révocation.

L'acceptation est réservée au coach bénéficiaire (l'email vérifié est contrôlé
côté vue par ``IsEmailVerified``) ; la révocation par le propriétaire a un
effet immédiat, vérifié au niveau du sélecteur central.
"""

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.coaches.tests.factories import CoachProfileFactory
from apps.teams import services
from apps.teams.models import AccessGrant
from core import access

SCOPE = "sessions:read"


class TestAcceptGrant:
    def test_beneficiary_accepts_pending_grant(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        grant = services.grant_access(athlete.user, athlete, "coach", coach.pk, [SCOPE])
        accepted = services.accept_grant(coach.user, grant.pk)
        assert accepted.status == AccessGrant.Status.ACTIVE
        assert access.can_access_athlete(coach.user, athlete, SCOPE) is True

    def test_non_beneficiary_cannot_accept(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        other_coach = CoachProfileFactory()
        grant = services.grant_access(athlete.user, athlete, "coach", coach.pk, [SCOPE])
        with pytest.raises(services.TeamsServiceError) as exc:
            services.accept_grant(other_coach.user, grant.pk)
        assert exc.value.code == "not_found"

    def test_athlete_cannot_accept_own_grant(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        grant = services.grant_access(athlete.user, athlete, "coach", coach.pk, [SCOPE])
        with pytest.raises(services.TeamsServiceError) as exc:
            services.accept_grant(athlete.user, grant.pk)
        assert exc.value.code == "not_found"

    def test_double_accept_conflict(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        grant = services.grant_access(athlete.user, athlete, "coach", coach.pk, [SCOPE])
        services.accept_grant(coach.user, grant.pk)
        with pytest.raises(services.TeamsServiceError) as exc:
            services.accept_grant(coach.user, grant.pk)
        assert exc.value.code == "conflict"

    def test_expired_grant_accept_flips_status(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        # Un grant déjà expiré au moment de l'acceptation : on fabrique un
        # pending avec une expiration passée via le modèle (le service refuse
        # les expirations passées à la création).
        from apps.teams.tests.factories import AccessGrantFactory

        grant = AccessGrantFactory(
            athlete=athlete,
            grantee_coach=coach,
            status=AccessGrant.Status.PENDING,
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        with pytest.raises(services.TeamsServiceError) as exc:
            services.accept_grant(coach.user, grant.pk)
        assert exc.value.code == "grant_expired"
        grant.refresh_from_db()
        assert grant.status == AccessGrant.Status.EXPIRED
        assert access.can_access_athlete(coach.user, athlete, SCOPE) is False

    def test_accept_nonexistent_grant(self):
        coach = CoachProfileFactory()
        with pytest.raises(services.TeamsServiceError) as exc:
            services.accept_grant(coach.user, "0" * 32)
        assert exc.value.code == "not_found"


class TestRevokeGrant:
    def test_owner_revokes_active_grant(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        grant = services.grant_access(athlete.user, athlete, "coach", coach.pk, [SCOPE])
        services.accept_grant(coach.user, grant.pk)
        revoked = services.revoke_grant(athlete.user, grant.pk)
        assert revoked.status == AccessGrant.Status.REVOKED
        assert revoked.revoked_at is not None

    def test_revocation_effect_immediate(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        grant = services.grant_access(athlete.user, athlete, "coach", coach.pk, [SCOPE])
        services.accept_grant(coach.user, grant.pk)
        assert access.can_access_athlete(coach.user, athlete, SCOPE) is True
        services.revoke_grant(athlete.user, grant.pk)
        # Effet immédiat au niveau du sélecteur.
        assert access.can_access_athlete(coach.user, athlete, SCOPE) is False
        assert not access.visible_athletes(coach.user, SCOPE).filter(pk=athlete.pk).exists()

    def test_revocation_of_pending_grant(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        grant = services.grant_access(athlete.user, athlete, "coach", coach.pk, [SCOPE])
        revoked = services.revoke_grant(athlete.user, grant.pk)
        assert revoked.status == AccessGrant.Status.REVOKED

    def test_non_owner_cannot_revoke(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        stranger = UserFactory()
        grant = services.grant_access(athlete.user, athlete, "coach", coach.pk, [SCOPE])
        with pytest.raises(services.TeamsServiceError) as exc:
            services.revoke_grant(stranger, grant.pk)
        assert exc.value.code == "forbidden"

    def test_beneficiary_cannot_revoke(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        grant = services.grant_access(athlete.user, athlete, "coach", coach.pk, [SCOPE])
        with pytest.raises(services.TeamsServiceError) as exc:
            services.revoke_grant(coach.user, grant.pk)
        assert exc.value.code == "forbidden"

    def test_superuser_can_revoke(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        superuser = UserFactory(is_superuser=True)
        grant = services.grant_access(athlete.user, athlete, "coach", coach.pk, [SCOPE])
        revoked = services.revoke_grant(superuser, grant.pk)
        assert revoked.status == AccessGrant.Status.REVOKED

    def test_double_revoke_conflict(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        grant = services.grant_access(athlete.user, athlete, "coach", coach.pk, [SCOPE])
        services.revoke_grant(athlete.user, grant.pk)
        with pytest.raises(services.TeamsServiceError) as exc:
            services.revoke_grant(athlete.user, grant.pk)
        assert exc.value.code == "conflict"

    def test_revoked_grant_not_listed(self):
        athlete = AthleteProfileFactory()
        coach = CoachProfileFactory()
        grant = services.grant_access(athlete.user, athlete, "coach", coach.pk, [SCOPE])
        services.revoke_grant(athlete.user, grant.pk)
        assert list(access.visible_athletes(coach.user, SCOPE)) == []
