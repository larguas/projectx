"""Sélecteurs de lecture de la feature 04 (app ``devices``).

Toute autorisation passe par le module central ``core.access`` (décision
d'architecture n°8) — jamais de requête directe sur les grants ici :
- un utilisateur voit TOUJOURS ses propres capteurs, qu'il ait ou non un
  profil sportif ;
- un coach / membre d'équipe ne voit les capteurs de ses sportifs que si un
  grant actif (statut ``active`` ET non expiré — vérifié dans
  ``core.access``, au niveau du sélecteur) porte le scope ``devices:read``
  sur le profil du propriétaire ;
- un superutilisateur Django voit tout.
"""

from django.db.models import Q, QuerySet

from core import access, scopes


def visible_devices(user) -> QuerySet:
    """Capteurs visibles par ``user`` (sélecteur de liste).

    Base de ``GET /api/v1/devices/`` : capteurs dont le propriétaire est
    l'utilisateur lui-même, ou un de ses sportifs couverts par un grant actif
    portant le scope ``devices:read``.
    """
    from apps.devices.models import Device

    qs = Device.objects.all()
    if user is None or not getattr(user, "is_authenticated", False):
        return qs.none()
    if user.is_superuser:
        return qs
    granted_user_ids = access.visible_athletes(user, scopes.DEVICES_READ.name).values_list(
        "user_id", flat=True
    )
    return qs.filter(Q(owner=user) | Q(owner_id__in=granted_user_ids)).distinct()


def can_read_device(user, device) -> bool:
    """Lecture d'un capteur : propriétaire, superutilisateur, ou grant actif.

    Pour un non-propriétaire, l'accès exige un grant ``devices:read`` actif et
    non expiré sur le profil sportif du propriétaire (vérifié par
    ``core.access.can_access_athlete``). Un propriétaire sans profil sportif
    n'est accessible que par lui-même.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or device.owner_id == user.pk:
        return True
    from apps.athletes.models import AthleteProfile

    profile = AthleteProfile.objects.filter(user_id=device.owner_id).first()
    if profile is None:
        return False
    return access.can_access_athlete(user, profile, scopes.DEVICES_READ.name)
