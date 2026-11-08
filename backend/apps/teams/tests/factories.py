"""Factories de test de la feature 03 (app ``teams``).

Usage : ``from apps.teams.tests.factories import TeamFactory, AccessGrantFactory``.
"""

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.coaches.tests.factories import CoachProfileFactory
from apps.teams.models import AccessGrant, Team, TeamMembership


class TeamFactory(DjangoModelFactory):
    """Équipe de test (l'utilisateur propriétaire est distinct).

    Comme ``services.create_team``, le propriétaire porte une membership active :
    sans elle, il ne verrait pas sa propre équipe (``get_team_for_user`` exige
    une membership non retirée).
    """

    class Meta:
        model = Team

    name = factory.Sequence(lambda n: f"Équipe {n}")
    owner = factory.SubFactory(UserFactory)

    @factory.post_generation
    def owner_membership(self, create, extracted):
        if not create:
            return
        TeamMembership.objects.get_or_create(
            team=self,
            user=self.owner,
            defaults={
                "role": TeamMembership.Role.OWNER,
                "status": TeamMembership.Status.ACTIVE,
            },
        )


class TeamMembershipFactory(DjangoModelFactory):
    """Appartenance active par défaut."""

    class Meta:
        model = TeamMembership

    team = factory.SubFactory(TeamFactory)
    user = factory.SubFactory(UserFactory)
    role = TeamMembership.Role.ATHLETE
    status = TeamMembership.Status.ACTIVE


class AccessGrantFactory(DjangoModelFactory):
    """Grant actif accordé à un coach (le cas par défaut)."""

    class Meta:
        model = AccessGrant

    athlete = factory.SubFactory(AthleteProfileFactory)
    granted_by = factory.LazyAttribute(lambda o: o.athlete.user)
    grantee_type = AccessGrant.GranteeType.COACH
    grantee_coach = factory.SubFactory(CoachProfileFactory)
    scopes = ["sessions:read"]
    status = AccessGrant.Status.ACTIVE
    granted_at = factory.LazyFunction(timezone.now)


class TeamAccessGrantFactory(AccessGrantFactory):
    """Grant actif accordé à une équipe (le coach bénéficiaire est absent)."""

    grantee_type = AccessGrant.GranteeType.TEAM
    grantee_coach = None
    grantee_team = factory.SubFactory(TeamFactory)
