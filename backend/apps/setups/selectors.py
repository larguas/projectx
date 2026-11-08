"""Sélecteurs de lecture de la feature 05b (app ``setups``).

Toute autorisation passe par le module central ``core.access`` (décision
d'architecture n°8) — jamais de requête directe sur les grants ici :
- un setup est TOUJOURS rattaché à un sportif (``athlete`` non nul) : l'accès
  à un setup est l'accès au profil du sportif rattaché — le PROPRIÉTAIRE du
  profil y accède toujours, un coach / membre d'équipe si un grant actif
  (statut ``active`` ET non expiré — vérifié dans ``core.access``, au niveau
  du sélecteur) porte le scope adéquat sur ce profil ;
- la LECTURE (setups, canaux, calibrations, guides) exige le scope
  ``setups:read`` et l'ÉCRITURE (création, PATCH, DELETE, new-version,
  remplacement des canaux, invalidation de calibration) le scope
  ``setups:write`` ;
- un superutilisateur Django voit tout (usage opérationnel/administratif).

Décision documentée (tâche du doc 05b « ajouter les scopes setups:read /
setups:write dans core/scopes.py ») : ces deux scopes sont DÉJÀ enregistrés en
feature 03 — ``core/scopes.py`` (``SETUPS_READ``, ``SETUPS_WRITE``). Ils ne
sont PAS re-registrés ici (``register_scope`` lèverait ``ValueError``) ; cette
app les consomme via ``core.access``, conformément à la décision n°8.

``created_by`` sur un setup est une donnée d'audit : ni critère d'accès, ni
jamais exposé par les sérialiseurs (l'identité du créateur ne fuit pas).
"""

from django.db.models import QuerySet

from core import access, scopes


def visible_setups(user) -> QuerySet:
    """Setups visibles par ``user`` (sélecteur de liste).

    Base de ``GET /api/v1/setups/`` : setups rattachés à un profil dont
    ``user`` est le propriétaire ou qu'un grant actif portant le scope
    ``setups:read`` couvre. Un setup n'existe que pour un sportif, donc aucun
    « orphelin » accessible en direct (contrairement aux plans d'entraînement).
    """
    from apps.setups.models import SensorSetup

    qs = SensorSetup.objects.all()
    if user is None or not getattr(user, "is_authenticated", False):
        return qs.none()
    if user.is_superuser:
        return qs
    granted_athlete_ids = access.visible_athletes(user, scopes.SETUPS_READ.name).values_list(
        "pk", flat=True
    )
    return qs.filter(athlete_id__in=granted_athlete_ids)


def can_read_setup(user, setup) -> bool:
    """Lecture d'un setup (et de ses canaux) : propriétaire, superutilisateur,
    ou grant actif ``setups:read`` sur le profil rattaché."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or setup.athlete.user_id == user.pk:
        return True
    return access.can_access_athlete(user, setup.athlete, scopes.SETUPS_READ.name)


def can_write_setup(user, setup) -> bool:
    """Écriture d'un setup (PATCH/DELETE/new-version/canaux) : propriétaire,
    superutilisateur, ou grant actif ``setups:write`` sur le profil rattaché.

    Un grant ``setups:read`` n'ouvre PAS l'écriture (un scope ne déborde jamais
    sur un autre, cf. ``core.access``).
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or setup.athlete.user_id == user.pk:
        return True
    return access.can_access_athlete(user, setup.athlete, scopes.SETUPS_WRITE.name)


def can_read_calibration(user, calibration) -> bool:
    """Lecture d'une calibration : même règle que son setup (profil rattaché,
    scope ``setups:read``)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or calibration.athlete.user_id == user.pk:
        return True
    return access.can_access_athlete(user, calibration.athlete, scopes.SETUPS_READ.name)


def can_write_calibration(user, calibration) -> bool:
    """Invalidation d'une calibration : scope ``setups:write`` sur le profil
    rattaché (propriétaire ou grant actif)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or calibration.athlete.user_id == user.pk:
        return True
    return access.can_access_athlete(user, calibration.athlete, scopes.SETUPS_WRITE.name)
